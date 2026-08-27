#!/usr/bin/env python3
"""Rebuild the Champions usage snapshot (CBD doubles + Showdown chaos).

ADR-014 offline prep. Callable on regulation change — do not hardcode a month.

    uv run python scripts/extract_usage/fetch_usage_mb.py \\
        --month 2026-07 \\
        --format gen9championsvgc2026regmb \\
        --rating 1500 \\
        --regulation champions-reg-mb

Defaults reuse the existing CBD slice and pull full Smogon chaos (no move/item
cap, pct = set% = weight / Raw count). Pass --refresh-cbd to re-fetch in-game.
--source munchstats is the legacy per-species mirror (also untruncated).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from recommender.ids import regulation_file_tag, to_id
from recommender.species_forms import ingame_excluded_species_ids
from recommender.teammates import (
    TEAMMATE_LIMIT,
    normalize_munch_teammates,
    without_snapshot_teammates,
)
from recommender.usage_cbd import (
    CBD_API,
    fetch_ingame_doubles_species,
    fetch_json,
)
from recommender.usage_chaos import (
    DEFAULT_FORMAT,
    DEFAULT_MONTH,
    DEFAULT_RATING,
    DEFAULT_REGULATION,
    chaos_species_row,
    chaos_url,
    chaos_weights_to_common,
    detail_raw_count,
)

ROOT = Path(__file__).resolve().parents[2]
USAGE_DIR = ROOT / "data" / "usage"

# Legacy cap for partial dev pulls (--cbd-top-n N). Default extract is full ladder.
TEAM_LADDER_N = 50
_SPREAD_LIMIT = 8  # spreads are not the truncation bug; keep a short featured list


def extract_ingame(top_n: int | None = None) -> tuple[dict[str, dict], dict[str, int]]:
    legality = json.loads((ROOT / "data" / "legality" / "champions.v1.json").read_text())
    excluded = ingame_excluded_species_ids(legality)
    idx = fetch_json(f"{CBD_API}/api/index")
    if not isinstance(idx, dict):
        raise SystemExit("CBD /api/index failed")
    ranked: list[tuple[int, str, str]] = []
    for p in idx.get("pokemon") or []:
        bs = ((p.get("summary") or {}).get("battleSummary") or {}).get("Current") or {}
        doubles = bs.get("Doubles") or {}
        pos = doubles.get("position")
        if pos is None:
            continue
        name = p.get("showdownName") or p.get("name")
        sid = to_id(p.get("showdownId") or p.get("slug") or name)
        ranked.append((int(pos), name, sid))
    ranked.sort()
    ladder_slice = ranked if top_n is None else ranked[:top_n]
    species: dict[str, dict] = {}
    excluded_n = 0
    fetch_failed_n = 0
    for pos, name, sid in ladder_slice:
        if sid in excluded:
            excluded_n += 1
            species[sid] = {
                "id": sid,
                "name": name,
                "usage_rank": pos,
                "ladder_rank_only": True,
            }
            print(f"  ingame #{pos} {sid} SKIP mega-capable (rank-only)", file=sys.stderr)
            continue
        entry = fetch_ingame_doubles_species(name)
        if entry is None:
            fetch_failed_n += 1
            print(f"  ingame #{pos} {sid} SKIP (fetch failed)", file=sys.stderr)
            continue
        entry["usage_rank"] = pos
        if not entry.get("id"):
            entry["id"] = sid
        species[str(entry["id"])] = entry
        print(f"  ingame #{pos} {entry['id']}", file=sys.stderr)
    ranked_n = len(ladder_slice)
    stub_n = sum(1 for row in species.values() if row.get("ladder_rank_only"))
    assert ranked_n == len(species) + fetch_failed_n
    assert stub_n == excluded_n
    return species, {
        "ranked_n": ranked_n,
        "excluded_n": excluded_n,
        "fetch_failed_n": fetch_failed_n,
        "build_n": len(species) - stub_n,
    }


def _name_resolvers(legality: dict) -> tuple:
    items = legality.get("items") or {}
    moves = legality.get("moves") or {}
    abilities: dict[str, str] = {}
    for ent in (legality.get("species") or {}).values():
        for name in (ent.get("abilities") or {}).values():
            if isinstance(name, str) and name:
                abilities[to_id(name)] = name

    def item(raw: str) -> str:
        ent = items.get(to_id(raw))
        return (ent or {}).get("name") or raw

    def move(raw: str) -> str:
        ent = moves.get(to_id(raw))
        return (ent or {}).get("name") or raw

    def ability(raw: str) -> str:
        return abilities.get(to_id(raw), raw)

    return item, move, ability


def _munch_spreads(d: dict) -> list[dict]:
    raw = d.get("Spreads") or {}
    if not isinstance(raw, dict):
        return []
    items = sorted(raw.items(), key=lambda kv: -float(kv[1]))
    out = []
    for label, w in items[:_SPREAD_LIMIT]:
        if ":" not in label:
            continue
        nature, rest = label.split(":", 1)
        parts = rest.split("/")
        if len(parts) != 6:
            continue
        hp, atk, df, spa, spd, spe = (int(float(x)) for x in parts)
        out.append(
            {
                "nature": nature,
                "evs": {"hp": hp, "atk": atk, "def": df, "spa": spa, "spd": spd, "spe": spe},
                "pct": float(w),
            }
        )
    return out


def _row_from_detail(
    name: str,
    detail: dict,
    *,
    usage: float,
    resolve_item,
    resolve_move,
    resolve_ability,
    source: str,
) -> dict:
    teammates = normalize_munch_teammates(detail)
    spreads = _munch_spreads(detail)
    if source == "smogon-chaos":
        row = chaos_species_row(
            name,
            detail,
            resolve_move=resolve_move,
            resolve_item=resolve_item,
            resolve_ability=resolve_ability,
            teammates=teammates.snapshot_rows(),
            teammates_meta=teammates.snapshot_meta(),
            spreads=spreads,
        )
        if usage:
            row["usage_pct"] = usage * 100.0 if usage <= 1.0 else usage
        return row
    raw_count = detail_raw_count(detail)
    moves = chaos_weights_to_common(
        detail.get("Moves"), raw_count=raw_count, resolve=resolve_move
    )
    items = chaos_weights_to_common(
        detail.get("Items"), raw_count=raw_count, resolve=resolve_item
    )
    abilities = chaos_weights_to_common(
        detail.get("Abilities"), raw_count=raw_count, resolve=resolve_ability
    )
    featured = []
    if moves and items:
        fs: dict = {
            "item": items[0]["name"],
            "moves": [m["name"] for m in moves[:4] if str(m.get("name") or "").strip()],
        }
        if abilities:
            fs["ability"] = abilities[0]["name"]
        if spreads and spreads[0].get("nature"):
            fs["nature"] = spreads[0]["nature"]
        featured.append(fs)
    return {
        "name": name,
        "id": to_id(name),
        "usage_pct": usage * 100.0 if usage <= 1.0 else usage,
        "common_moves": moves,
        "common_abilities": abilities,
        "common_items": items,
        "top_spreads": spreads,
        "featured_sets": featured,
        "teammates": teammates.snapshot_rows(),
        "teammates_meta": teammates.snapshot_meta(),
        "source": source,
    }


def _fetch_chaos_json(url: str) -> dict | None:
    import json as _json
    import urllib.request

    req = urllib.request.Request(
        url, headers={"User-Agent": "pokemon-champions-agents/0.1"}
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            payload = _json.loads(resp.read().decode())
    except Exception as exc:
        print(f"  chaos fetch error: {exc}", file=sys.stderr)
        return None
    return payload if isinstance(payload, dict) else None


def extract_showdown_chaos(
    month: str, format_id: str, rating: int
) -> tuple[dict[str, dict], dict]:
    url = chaos_url(month, format_id, rating)
    payload = _fetch_chaos_json(url)
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        raise SystemExit(f"Smogon chaos fetch failed: {url}")
    source_info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    legality = json.loads((ROOT / "data" / "legality" / "champions.v1.json").read_text())
    resolve_item, resolve_move, resolve_ability = _name_resolvers(legality)
    out: dict[str, dict] = {}
    for name, detail in payload["data"].items():
        if not isinstance(detail, dict):
            continue
        sid = to_id(name)
        try:
            usage = float(detail.get("usage") or 0.0)
        except (TypeError, ValueError):
            usage = 0.0
        out[sid] = _row_from_detail(
            str(name),
            detail,
            usage=usage,
            resolve_item=resolve_item,
            resolve_move=resolve_move,
            resolve_ability=resolve_ability,
            source="smogon-chaos",
        )
        print(f"  chaos {sid} usage={out[sid]['usage_pct']:.2f}%", file=sys.stderr)
    return out, dict(source_info)


def extract_showdown_munchstats(
    month: str, format_id: str, rating: int
) -> tuple[dict[str, dict], dict]:
    base = (
        "https://raw.githubusercontent.com/PizzaTimeJoshua/munchstats/main/"
        f"stats/{month}/{format_id}/{rating}"
    )
    index = fetch_json(f"{base}/_index.json")
    if not isinstance(index, dict):
        raise SystemExit("MunchStats _index.json failed")
    source_info = index.get("info") if isinstance(index.get("info"), dict) else {}
    poke = index.get("pokemon") or {}
    legality = json.loads((ROOT / "data" / "legality" / "champions.v1.json").read_text())
    resolve_item, resolve_move, resolve_ability = _name_resolvers(legality)
    out: dict[str, dict] = {}
    for name, meta in poke.items():
        sid = to_id(name)
        usage = float((meta or {}).get("usage") or 0.0)
        detail = fetch_json(f"{base}/{urllib.parse.quote(str(name))}.json")
        if not isinstance(detail, dict):
            out[sid] = {
                "name": name,
                "id": sid,
                "usage_pct": usage * 100.0,
                "common_moves": [],
                "common_abilities": [],
                "common_items": [],
                "top_spreads": [],
                "featured_sets": [],
                "teammates": [],
                "teammates_meta": {},
                "source": "munchstats-showdown",
            }
            continue
        out[sid] = _row_from_detail(
            str(name),
            detail,
            usage=usage,
            resolve_item=resolve_item,
            resolve_move=resolve_move,
            resolve_ability=resolve_ability,
            source="munchstats-showdown",
        )
        print(f"  munchstats {sid} usage={usage * 100:.2f}%", file=sys.stderr)
    return out, dict(source_info)


def _merge_species_flat(ingame: dict[str, dict], showdown: dict[str, dict]) -> dict[str, dict]:
    """Backward-compat flat map: prefer Showdown builds when present, else in-game."""
    flat: dict[str, dict] = {}
    for sid, e in ingame.items():
        flat[sid] = dict(e)
    for sid, e in showdown.items():
        if sid in flat:
            merged = dict(flat[sid])
            for k in (
                "common_moves",
                "common_abilities",
                "common_items",
                "top_spreads",
                "featured_sets",
                "usage_pct",
                "name",
            ):
                if e.get(k):
                    merged[k] = e[k]
            merged["source"] = "merged"
            flat[sid] = merged
        else:
            flat[sid] = without_snapshot_teammates(e)
    return flat


def build_snapshot(
    ingame: dict[str, dict],
    showdown: dict[str, dict],
    showdown_info: dict,
    *,
    month: str,
    format_id: str,
    rating: int,
    regulation: str,
    source: str,
    base_meta: dict | None = None,
) -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta = dict(base_meta or {})
    meta.update(
        {
            "schema_version": 3,
            "regulation": regulation,
            "showdown_rating": rating,
            "showdown_format": format_id,
            "showdown_month": month,
            "showdown_source": source,
            "showdown_pct_kind": "set",
            "showdown_move_limit": None,
            "showdown_battles": showdown_info.get("number of battles"),
            "showdown_teammates_extracted_at": now,
            "showdown_teammates": {
                "source_field": "Teammates",
                "weight_kind": "chaos_weight",
                "percentage_kind": "conditional_probability",
                "denominator_rule": (
                    "max(sum(valid Abilities), sum(valid Teammates) / 6, 1)"
                ),
                "limit": TEAMMATE_LIMIT,
                "caveats": [
                    "weighted ladder estimate, not independent sample count",
                    "not curated tournament data",
                    "retained top-10 rows only",
                ],
            },
            "attribution": (
                "In-game doubles: championsbattledata.com. "
                "Showdown VGC: Smogon chaos stats (set% = weight / Raw count; "
                "no move/item cap)."
                if source == "smogon-chaos"
                else (
                    "In-game doubles: championsbattledata.com. "
                    "Showdown VGC: MunchStats mirror of Smogon chaos stats "
                    "(set% when Raw count present; no move/item cap)."
                )
            ),
            "sources": [
                "championsbattledata",
                "smogon-chaos" if source == "smogon-chaos" else "munchstats-showdown",
            ],
        }
    )
    if not base_meta or "extracted_at" not in meta:
        meta["extracted_at"] = now
    return {
        "meta": meta,
        "ingame_doubles": {"species": ingame},
        "showdown_vgc_mb": {"species": showdown},
        "species": _merge_species_flat(ingame, showdown),
    }


def _load_existing_cbd(path: Path) -> dict[str, dict]:
    if not path.exists():
        raise SystemExit(f"no existing snapshot to reuse CBD from: {path}")
    snap = json.loads(path.read_text())
    ingame = (snap.get("ingame_doubles") or {}).get("species") or {}
    if not isinstance(ingame, dict) or not ingame:
        raise SystemExit(f"existing snapshot has empty ingame_doubles: {path}")
    return {sid: dict(row) for sid, row in ingame.items() if isinstance(row, dict)}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--month", default=DEFAULT_MONTH, help="YYYY-MM Smogon stats month")
    p.add_argument("--format", dest="format_id", default=DEFAULT_FORMAT)
    p.add_argument("--rating", type=int, default=DEFAULT_RATING)
    p.add_argument("--regulation", default=DEFAULT_REGULATION)
    p.add_argument(
        "--source",
        choices=("chaos", "munchstats"),
        default="chaos",
        help="Showdown pull: full Smogon chaos JSON (default) or MunchStats mirror",
    )
    p.add_argument(
        "--refresh-cbd",
        action="store_true",
        help="Re-fetch Champions in-game doubles ladder instead of reusing the snapshot",
    )
    p.add_argument(
        "--cbd-top-n",
        type=int,
        default=0,
        help="CBD species to fetch; 0 = full ranked ladder (default)",
    )
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args(argv)

    tag = regulation_file_tag(args.regulation)
    out_path = args.out or (USAGE_DIR / f"{tag}.v1.json")
    source_label = "smogon-chaos" if args.source == "chaos" else "munchstats-showdown"

    if args.refresh_cbd:
        print("extracting in-game doubles ladder...", file=sys.stderr)
        top_n = args.cbd_top_n if args.cbd_top_n > 0 else None
        ingame, ingame_stats = extract_ingame(top_n)
    else:
        print(f"reusing CBD slice from {out_path}...", file=sys.stderr)
        ingame = _load_existing_cbd(out_path)
        ingame_stats = None

    legality = json.loads((ROOT / "data" / "legality" / "champions.v1.json").read_text())
    ingame_meta: dict[str, Any] = {
        "ingame_ladder_n": (
            ingame_stats["build_n"] if ingame_stats is not None else len(ingame)
        ),
        "ingame_exclusion_policy": "mega_capable_lineages",
    }
    if ingame_stats is not None:
        ingame_meta.update(
            {
                "ingame_ranked_n": ingame_stats["ranked_n"],
                "ingame_excluded_mega_capable_n": ingame_stats["excluded_n"],
                "ingame_fetch_failed_n": ingame_stats["fetch_failed_n"],
            }
        )
    else:
        existing = {}
        if out_path.exists():
            existing = (
                json.loads(out_path.read_text()).get("meta") or {}
            )
        ingame_meta.setdefault(
            "ingame_excluded_mega_capable_n",
            existing.get("ingame_excluded_mega_capable_n"),
        )
        ingame_meta.setdefault("ingame_ranked_n", existing.get("ingame_ranked_n"))
        ingame_meta.setdefault(
            "ingame_fetch_failed_n", existing.get("ingame_fetch_failed_n")
        )

    print(
        f"extracting showdown {args.source} {args.month} "
        f"{args.format_id}@{args.rating}...",
        file=sys.stderr,
    )
    if args.source == "chaos":
        showdown, showdown_info = extract_showdown_chaos(
            args.month, args.format_id, args.rating
        )
    else:
        showdown, showdown_info = extract_showdown_munchstats(
            args.month, args.format_id, args.rating
        )
    snap = build_snapshot(
        ingame,
        showdown,
        showdown_info,
        month=args.month,
        format_id=args.format_id,
        rating=args.rating,
        regulation=tag,
        source=source_label,
        base_meta=ingame_meta,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snap, indent=2) + "\n")
    print(
        f"Wrote {out_path} ingame={len(ingame)} showdown={len(showdown)} "
        f"flat={len(snap['species'])} month={args.month} source={source_label}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
