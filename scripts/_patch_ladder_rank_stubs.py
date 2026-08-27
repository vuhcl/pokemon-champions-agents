#!/usr/bin/env python3
"""Add rank-only ingame ladder stubs for mega-capable species missing from snapshot."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from recommender.ids import regulation_file_tag, to_id
from recommender.species_forms import ingame_excluded_species_ids
from recommender.usage_cbd import CBD_API, fetch_json

USAGE_PATH = ROOT / "data" / "usage" / f"{regulation_file_tag('champions-reg-mb')}.v1.json"


def main() -> None:
    snap = json.loads(USAGE_PATH.read_text())
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
        ranked.append((int(pos), str(name), sid))
    ranked.sort()

    ingame = snap.setdefault("ingame_doubles", {}).setdefault("species", {})
    added = 0
    for pos, name, sid in ranked:
        if sid not in excluded or sid in ingame:
            continue
        ingame[sid] = {
            "id": sid,
            "name": name,
            "usage_rank": pos,
            "ladder_rank_only": True,
        }
        added += 1

    build_n = sum(
        1 for row in ingame.values() if not row.get("ladder_rank_only")
    )
    stub_n = sum(1 for row in ingame.values() if row.get("ladder_rank_only"))
    meta = snap.setdefault("meta", {})
    meta.update(
        {
            "ingame_ladder_n": build_n,
            "ingame_ranked_n": len(ranked),
            "ingame_excluded_mega_capable_n": stub_n,
            "ingame_fetch_failed_n": meta.get("ingame_fetch_failed_n", 0),
            "ingame_exclusion_policy": "mega_capable_lineages",
        }
    )
    USAGE_PATH.write_text(json.dumps(snap, indent=2) + "\n")
    print(f"added {added} rank-only stubs; build_n={build_n} stub_n={stub_n} ranked_n={len(ranked)}")


if __name__ == "__main__":
    main()
