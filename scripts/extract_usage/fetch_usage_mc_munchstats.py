#!/usr/bin/env python3
"""Build champions-reg-mc.v1.json from MunchStats champions-data (raw GitHub).

    uv run python -m scripts.extract_usage.fetch_usage_mc_munchstats
    uv run python -m scripts.extract_usage.fetch_usage_mc_munchstats --out /tmp/mc.json --dry-validate
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from recommender.ids import to_id
from recommender.legality import is_species_legal, load_snapshot
from recommender.usage_cbd import pct_rows, spreads_from_rows

ROOT = Path(__file__).resolve().parents[2]
USAGE_DIR = ROOT / "data" / "usage"
DEFAULT_OUT = USAGE_DIR / "champions-reg-mc.v1.json"

INDEX_URL = (
    "https://raw.githubusercontent.com/PizzaTimeJoshua/munchstats/"
    "champions-data/champions/index.json"
)
DETAIL_TMPL = (
    "https://raw.githubusercontent.com/PizzaTimeJoshua/munchstats/"
    "champions-data/champions/battle/Doubles/{slug}.json"
)
UA = "pokemon-champions-agents/0.1 (usage-refresh-mc)"
SOURCE = "munchstats-champions-data"

ABS_FLOOR = 220
LADDER_RATIO = 0.85
DROP_RATIO = 0.90
DROP_ABS = 25
PARTIAL_OK_RATIO = 0.95
MAX_WORKERS = 5
TIMEOUT_S = 30.0

JsonFetch = Callable[[str], dict[str, Any] | None]


def _is_mega_sid(sid: str) -> bool:
    return sid.endswith(("megax", "megay", "megaz", "mega"))


def _strip_mega_suffix(sid: str) -> str:
    for suf in ("megax", "megay", "megaz", "mega"):
        if sid.endswith(suf) and len(sid) > len(suf):
            return sid[: -len(suf)]
    return sid


def lookup_id_for_species(sid: str, entry: dict[str, Any]) -> str:
    """Mega → base showdownId; regional/gender formes unchanged."""
    if not _is_mega_sid(sid):
        return sid
    base = entry.get("base_species_id")
    if isinstance(base, str) and base:
        return base
    return _strip_mega_suffix(sid)


def doubles_position(poke: dict[str, Any], *, default_season: str) -> int | None:
    summary = ((poke.get("summary") or {}).get("battleSummary") or {}).get(
        default_season
    ) or {}
    doubles = summary.get("Doubles") or {}
    pos = doubles.get("position")
    return int(pos) if pos is not None else None


def spreads_with_natures(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """stat_points → top_spreads; attach nature from same-rank/position stat_alignment."""
    natures: dict[int, str] = {}
    for r in rows:
        if r.get("category") != "stat_alignment":
            continue
        key = r.get("rank") if r.get("rank") is not None else r.get("position")
        name = (r.get("name") or "").strip()
        if key is None or not name:
            continue
        natures[int(key)] = name

    out: list[dict[str, Any]] = []
    for r in rows:
        if r.get("category") != "stat_points":
            continue
        evs = {
            "hp": int(r.get("hp_points") or 0),
            "atk": int(r.get("attack_points") or 0),
            "def": int(r.get("defense_points") or 0),
            "spa": int(r.get("sp_atk_points") or 0),
            "spd": int(r.get("sp_def_points") or 0),
            "spe": int(r.get("speed_points") or 0),
        }
        entry: dict[str, Any] = {"evs": evs}
        pv = r.get("percentage_value")
        if pv is not None:
            entry["pct"] = float(pv)
        key = r.get("rank") if r.get("rank") is not None else r.get("position")
        if key is not None and int(key) in natures:
            entry["nature"] = natures[int(key)]
        out.append(entry)
        if len(out) >= 8:
            break
    return out


def entry_from_champions_detail(
    detail: dict[str, Any],
    *,
    showdown_id: str,
    display_name: str,
    usage_rank: int | None,
) -> dict[str, Any]:
    rows = detail.get("rows") or []
    if not isinstance(rows, list):
        rows = []
    out: dict[str, Any] = {
        "id": showdown_id,
        "name": display_name,
        "common_moves": pct_rows(rows, "move"),
        "common_abilities": pct_rows(rows, "ability"),
        "common_items": pct_rows(rows, "held_item"),
        "teammates": [r["name"] for r in pct_rows(rows, "teammate")],
        "top_spreads": spreads_with_natures(rows) or spreads_from_rows(rows),
        "featured_sets": [],
        "source": SOURCE,
    }
    if usage_rank is not None:
        out["usage_rank"] = usage_rank
    return out


def fetch_json(url: str, *, timeout: float = TIMEOUT_S) -> dict[str, Any] | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    delays = (0.5, 1.5, 4.0)
    last_err: Exception | None = None
    for attempt, delay in enumerate([0.0, *delays]):
        if delay:
            time.sleep(delay)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
                return data if isinstance(data, dict) else None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code in {429, 403, 500, 502, 503} and attempt < len(delays):
                last_err = e
                continue
            raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            last_err = e
            if attempt < len(delays):
                continue
            raise
    if last_err:
        raise last_err
    return None


def legal_lookup_ids(legality: dict[str, Any] | None = None) -> dict[str, str]:
    """Map lookup_id → preferred display name from legal species (post mega→base)."""
    snap = legality or load_snapshot()
    out: dict[str, str] = {}
    for sid, entry in (snap.get("species") or {}).items():
        if not isinstance(entry, dict) or not is_species_legal(snap, sid):
            continue
        lid = lookup_id_for_species(str(sid), entry)
        name = str(entry.get("name") or sid)
        # Prefer the base entry's display name when megas collapse onto it.
        if lid not in out or sid == lid:
            out[lid] = name
    return out


def index_by_showdown_id(index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by: dict[str, dict[str, Any]] = {}
    for p in index.get("pokemon") or []:
        if not isinstance(p, dict):
            continue
        sid = str(p.get("showdownId") or "").strip()
        if sid:
            by[sid] = p
    return by


def build_ingame_from_index(
    index: dict[str, Any],
    *,
    legality: dict[str, Any] | None = None,
    fetch: JsonFetch = fetch_json,
    max_workers: int = MAX_WORKERS,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Fetch details for legal∩index; return (species_map, stats)."""
    default_season = str(index.get("defaultSeason") or "Current")
    legal = legal_lookup_ids(legality)
    by_id = index_by_showdown_id(index)
    join: list[tuple[str, dict[str, Any], str]] = []
    for lid, display in legal.items():
        poke = by_id.get(lid)
        if poke is None:
            continue
        slug = str(poke.get("slug") or "").strip()
        if not slug:
            continue
        join.append((lid, poke, display))

    species: dict[str, dict[str, Any]] = {}
    ok = 0
    fail = 0

    def one(item: tuple[str, dict[str, Any], str]) -> tuple[str, dict[str, Any] | None]:
        lid, poke, display = item
        slug = str(poke["slug"])
        url = DETAIL_TMPL.format(slug=urllib.parse.quote(slug, safe=""))
        try:
            detail = fetch(url)
        except Exception:
            return lid, None
        if not isinstance(detail, dict):
            return lid, None
        rank = doubles_position(poke, default_season=default_season)
        name = str(poke.get("showdownName") or poke.get("name") or display)
        return lid, entry_from_champions_detail(
            detail, showdown_id=lid, display_name=name, usage_rank=rank
        )

    workers = max(1, min(max_workers, len(join) or 1))
    if not join:
        stats = {
            "join_n": 0,
            "detail_fetch_ok_n": 0,
            "detail_fetch_fail_n": 0,
            "index_count": int(index.get("count") or len(by_id)),
        }
        return species, stats

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(one, item) for item in join]
        for fut in as_completed(futs):
            lid, entry = fut.result()
            if entry is None:
                fail += 1
                print(f"  detail FAIL {lid}", file=sys.stderr)
                continue
            species[lid] = entry
            ok += 1
            print(f"  detail ok {lid} rank={entry.get('usage_rank')}", file=sys.stderr)

    stats = {
        "join_n": len(join),
        "detail_fetch_ok_n": ok,
        "detail_fetch_fail_n": fail,
        "index_count": int(index.get("count") or len(by_id)),
    }
    return species, stats


def build_snapshot(
    ingame: dict[str, dict[str, Any]],
    index: dict[str, Any],
    stats: dict[str, Any],
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta = {
        "schema_version": 3,
        "regulation": "champions-reg-mc",
        "extracted_at": now,
        "ingame_doubles_extracted_at": now,
        "ingame_ladder_n": len(ingame),
        "detail_fetch_ok_n": stats.get("detail_fetch_ok_n"),
        "detail_fetch_fail_n": stats.get("detail_fetch_fail_n"),
        "join_n": stats.get("join_n"),
        "index_count": stats.get("index_count"),
        "munchstats_generated_at": index.get("generatedAt"),
        "munchstats_published_at": index.get("publishedAt"),
        "munchstats_captured_on": index.get("capturedOn"),
        "munchstats_default_season": index.get("defaultSeason"),
        "attribution": (
            "In-game doubles: MunchStats champions-data branch "
            "(OCR capture via raw.githubusercontent.com). "
            "Showdown chaos half empty until an M-C source exists."
        ),
        "sources": [SOURCE],
    }
    return {
        "meta": meta,
        "ingame_doubles": {"species": ingame},
        "showdown_vgc_mb": {"species": {}},
        "species": {sid: dict(row) for sid, row in ingame.items()},
    }


def parse_generated_at(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    s = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def validate_snapshot(
    snap: dict[str, Any],
    *,
    index: dict[str, Any],
    stats: dict[str, Any],
    previous: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Return (decision, reason). decision in {ok, noop, fail}."""
    meta = snap.get("meta") or {}
    species = (snap.get("ingame_doubles") or {}).get("species") or {}
    if not isinstance(species, dict):
        return "fail", "ingame_doubles.species missing"
    required_top = {"meta", "ingame_doubles", "showdown_vgc_mb", "species"}
    if not required_top.issubset(snap):
        return "fail", "schema top-level keys missing"
    if meta.get("schema_version") != 3:
        return "fail", "schema_version != 3"

    for sid, row in species.items():
        if not isinstance(row, dict):
            return "fail", f"species {sid} not object"
        for k in (
            "id",
            "name",
            "common_moves",
            "common_items",
            "common_abilities",
            "teammates",
            "top_spreads",
            "featured_sets",
            "source",
        ):
            if k not in row:
                return "fail", f"species {sid} missing {k}"

    new_gen = parse_generated_at(meta.get("munchstats_generated_at") or index.get("generatedAt"))
    if new_gen is None:
        return "fail", "missing/unparseable generatedAt"

    prev_meta = (previous or {}).get("meta") or {}
    prev_gen = parse_generated_at(prev_meta.get("munchstats_generated_at"))
    if previous is not None and prev_gen is not None and new_gen <= prev_gen:
        return "noop", "generatedAt not newer than previous snapshot"

    n = len(species)
    index_count = int(stats.get("index_count") or index.get("count") or 0)
    if n < ABS_FLOOR:
        return "fail", f"species count {n} < floor {ABS_FLOOR}"
    if index_count and n < LADDER_RATIO * index_count:
        return "fail", f"species count {n} < {LADDER_RATIO} * index_count {index_count}"

    join_n = int(stats.get("join_n") or 0)
    ok_n = int(stats.get("detail_fetch_ok_n") or 0)
    if join_n and ok_n / join_n < PARTIAL_OK_RATIO:
        return "fail", f"partial fetch {ok_n}/{join_n} < {PARTIAL_OK_RATIO}"

    if previous is not None:
        prev_n = len(((previous.get("ingame_doubles") or {}).get("species")) or {})
        if prev_n:
            if n < prev_n * DROP_RATIO or (prev_n - n) > DROP_ABS:
                return "fail", f"drop vs previous {n} vs {prev_n}"

    return "ok", "validated"


def extract(
    *,
    fetch: JsonFetch = fetch_json,
    legality: dict[str, Any] | None = None,
    max_workers: int = MAX_WORKERS,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    index = fetch(INDEX_URL)
    if not isinstance(index, dict):
        raise RuntimeError(f"index fetch failed: {INDEX_URL}")
    ingame, stats = build_ingame_from_index(
        index, legality=legality, fetch=fetch, max_workers=max_workers
    )
    snap = build_snapshot(ingame, index, stats)
    return snap, index, stats


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument(
        "--dry-validate",
        action="store_true",
        help="Validate without writing (still fetches unless fixtures injected via tests)",
    )
    p.add_argument("--max-workers", type=int, default=MAX_WORKERS)
    args = p.parse_args(argv)

    try:
        snap, index, stats = extract(max_workers=args.max_workers)
    except Exception as e:
        print(f"extract failed: {e}", file=sys.stderr)
        return 1

    previous = None
    if args.out.exists():
        try:
            previous = json.loads(args.out.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = None

    decision, reason = validate_snapshot(
        snap, index=index, stats=stats, previous=previous
    )
    print(f"validate decision={decision} reason={reason}", file=sys.stderr)
    print(
        f"stats join={stats.get('join_n')} ok={stats.get('detail_fetch_ok_n')} "
        f"fail={stats.get('detail_fetch_fail_n')} n={len((snap.get('ingame_doubles') or {}).get('species') or {})}",
        file=sys.stderr,
    )
    if decision == "fail":
        return 1
    if decision == "noop":
        return 0
    if args.dry_validate:
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
