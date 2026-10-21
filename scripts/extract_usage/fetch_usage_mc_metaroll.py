#!/usr/bin/env python3
"""Build champions-reg-mc.ingame_doubles.v1.json from MetaRoll's in-game ladder export.

One request (``all.json``). Showdown half is a separate per-source file (graft /
monthly rollover); this writer never touches it. Attribution is MetaRoll's only
licence term: the snapshot carries its text, and consumers must not present the
numbers as official or endorsed.

    uv run python -m scripts.extract_usage.fetch_usage_mc_metaroll
    uv run python -m scripts.extract_usage.fetch_usage_mc_metaroll --out /tmp/mc.ingame.json --dry-validate
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from recommender.ids import to_id
from recommender.legality import is_species_legal, load_snapshot
from recommender.usage_split import SCHEMA_VERSION
from scripts.extract_usage.fetch_usage_mc_munchstats import (
    ABS_FLOOR,
    DEFAULT_OUT,
    DROP_ABS,
    DROP_RATIO,
    LADDER_RATIO,
    REGULATION_TAG,
    fetch_json,
    legal_lookup_ids,
    parse_generated_at,
)

ALL_URL = "https://metaroll.app/api/v1/all.json"
SOURCE = "metaroll"
TOP_SPREADS_N = 8  # same cap as the MunchStats extractor; MetaRoll publishes 30

JsonFetch = Callable[[str], dict[str, Any] | None]

_ROW_KEYS = (
    "id",
    "name",
    "common_moves",
    "common_items",
    "common_abilities",
    "teammates",
    "top_spreads",
    "featured_sets",
    "source",
)
_STATS = ("hp", "atk", "def", "spa", "spd", "spe")


def _pct_rows(rows: Any, names: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """``names`` maps to_id → canonical display name; MetaRoll strips punctuation from some."""
    out: list[dict[str, Any]] = []
    for r in rows or []:
        name = str((r or {}).get("name") or "").strip()
        if not name:
            continue
        name = (names or {}).get(to_id(name), name)
        item: dict[str, Any] = {"name": name}
        if r.get("percent") is not None:
            item["pct"] = float(r["percent"])
        out.append(item)
    return out


def spreads_with_natures(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """statPoints → top_spreads; ``nature`` attached by rank from the separate ``natures`` list.

    MetaRoll publishes spreads and natures as two unpaired distributions, so the pairing is
    positional (as it was for MunchStats), not a joint observation. The loaders read
    ``nature`` from these rows; the unpaired distribution is kept as ``common_natures``.
    """
    natures = _pct_rows(entry.get("natures"))
    out: list[dict[str, Any]] = []
    for i, s in enumerate(entry.get("spreads") or []):
        sp = (s or {}).get("statPoints")
        if not isinstance(sp, dict):
            continue
        row: dict[str, Any] = {"evs": {k: int(sp.get(k) or 0) for k in _STATS}}
        if s.get("percent") is not None:
            row["pct"] = float(s["percent"])
        if i < len(natures):
            row["nature"] = natures[i]["name"]
        out.append(row)
        if len(out) >= TOP_SPREADS_N:
            break
    return out


def entry_from_metaroll(
    entry: dict[str, Any], *, showdown_id: str, move_names: dict[str, str] | None = None
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": showdown_id,
        "name": str(entry.get("name") or showdown_id),
        "common_moves": _pct_rows(entry.get("moves"), move_names),
        "common_abilities": _pct_rows(entry.get("abilities")),
        "common_items": _pct_rows(entry.get("items")),
        "teammates": [t["name"] for t in _pct_rows(entry.get("teammates"))],
        "top_spreads": spreads_with_natures(entry),
        "common_natures": _pct_rows(entry.get("natures")),
        "featured_sets": [],
        "source": SOURCE,
    }
    if entry.get("rank") is not None:
        out["usage_rank"] = int(entry["rank"])
    return out


def build_ingame(
    payload: dict[str, Any], *, legality: dict[str, Any] | None = None
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Join MetaRoll entries to legal species by hyphen-stripped id; return (species, stats)."""
    snap = legality or load_snapshot()
    legal = legal_lookup_ids(snap)
    move_names = {
        mid: str(m["name"]) for mid, m in (snap.get("moves") or {}).items() if m.get("name")
    }
    species: dict[str, dict[str, Any]] = {}
    unmatched: list[str] = []
    entries = payload.get("entries") or []
    for e in entries:
        if not isinstance(e, dict):
            continue
        lid = to_id(str(e.get("id") or ""))
        # legal_lookup_ids collapses Megas onto their base, which can be illegal itself
        # (floette: its Mega child is legal, it is not); a row must be a legal species.
        if lid in legal and is_species_legal(snap, lid) and lid not in species:
            species[lid] = entry_from_metaroll(e, showdown_id=lid, move_names=move_names)
        else:
            unmatched.append(str(e.get("id")))
    stats = {
        "join_n": len(species),
        "index_count": int(payload.get("count") or len(entries)),
        "unmatched_ids": unmatched,
    }
    return species, stats


def _attribution(payload: dict[str, Any]) -> str:
    text = ((payload.get("attribution") or {}).get("text")) or ""
    return (
        f"{text}; https://metaroll.app. In-game ranked doubles ladder, season "
        f"{payload.get('season')}, captured {payload.get('capturedAt')}; not official "
        "data and not endorsed by MetaRoll. "
        "Showdown VGC: separate *.showdown_doubles.v1.json (Smogon chaos)."
    )


def build_snapshot(
    ingame: dict[str, dict[str, Any]], payload: dict[str, Any], stats: dict[str, Any]
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "regulation": REGULATION_TAG,
        "section": "ingame_doubles",
        "extracted_at": now,
        "ingame_doubles_extracted_at": now,
        "ingame_ladder_n": len(ingame),
        "join_n": stats.get("join_n"),
        "index_count": stats.get("index_count"),
        "source": SOURCE,
        "capturedAt": payload.get("capturedAt"),
        "season": payload.get("season"),
        "comparedTo": payload.get("comparedTo"),
        "spread_nature_pairing": "rank-paired; MetaRoll publishes spreads and natures unpaired",
        "attribution": _attribution(payload),
        "sources": [SOURCE],
    }
    return {"meta": meta, "ingame_doubles": {"species": ingame}}


def validate_snapshot(
    snap: dict[str, Any],
    *,
    index: dict[str, Any],
    stats: dict[str, Any],
    previous: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Return (decision, reason); decision in {ok, noop, fail}. Ingame file only."""
    meta = snap.get("meta") or {}
    species = (snap.get("ingame_doubles") or {}).get("species")
    if not isinstance(species, dict):
        return "fail", "ingame_doubles.species missing"
    if meta.get("schema_version") != SCHEMA_VERSION:
        return "fail", f"schema_version != {SCHEMA_VERSION}"
    for sid, row in species.items():
        if not isinstance(row, dict):
            return "fail", f"species {sid} not object"
        for k in _ROW_KEYS:
            if k not in row:
                return "fail", f"species {sid} missing {k}"

    attr = index.get("attribution") or {}
    if attr.get("required") and not attr.get("text"):
        return "fail", "attribution required but text missing"
    new_cap = parse_generated_at(meta.get("capturedAt"))
    if new_cap is None:
        return "fail", "missing/unparseable capturedAt"
    if not meta.get("season"):
        return "fail", "missing season"

    prev_cap = parse_generated_at(((previous or {}).get("meta") or {}).get("capturedAt"))
    if prev_cap is not None and new_cap <= prev_cap:
        return "noop", "capturedAt not newer than previous snapshot"

    n = len(species)
    index_count = int(stats.get("index_count") or index.get("count") or 0)
    if n < ABS_FLOOR:
        return "fail", f"species count {n} < floor {ABS_FLOOR}"
    if index_count and n < LADDER_RATIO * index_count:
        return "fail", f"species count {n} < {LADDER_RATIO} * index_count {index_count}"

    if previous is not None:
        prev_n = len(((previous.get("ingame_doubles") or {}).get("species")) or {})
        if prev_n and (n < prev_n * DROP_RATIO or (prev_n - n) > DROP_ABS):
            return "fail", f"drop vs previous {n} vs {prev_n}"
    return "ok", "validated"


def extract(
    *,
    fetch: JsonFetch = fetch_json,
    legality: dict[str, Any] | None = None,
    previous: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    del previous  # validation, not extraction, compares against it
    payload = fetch(ALL_URL)
    if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
        raise RuntimeError(f"all.json fetch failed or malformed: {ALL_URL}")
    ingame, stats = build_ingame(payload, legality=legality)
    return build_snapshot(ingame, payload, stats), payload, stats


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--dry-validate", action="store_true", help="Validate without writing")
    args = p.parse_args(argv)

    previous = None
    if args.out.exists():
        try:
            previous = json.loads(args.out.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = None

    try:
        snap, payload, stats = extract(previous=previous)
    except Exception as e:
        print(f"extract failed: {e}", file=sys.stderr)
        return 1
    decision, reason = validate_snapshot(snap, index=payload, stats=stats, previous=previous)
    print(
        f"validate decision={decision} reason={reason} join={stats['join_n']}"
        f"/{stats['index_count']} unmatched={stats['unmatched_ids']}",
        file=sys.stderr,
    )
    if decision == "fail":
        return 1
    if decision == "noop" or args.dry_validate:
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
