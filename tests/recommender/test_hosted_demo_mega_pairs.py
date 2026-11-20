"""Normalization of the two mega pairs on the Worlds 2026 target, as written.

The v0 score function does not exist yet. These checks are the normalizers it
would call. Floette-Eternal + Floettite does not resolve: the snapshot mega is
floettemega, whose base is floette, and item_mega_forme looks up
floetteeternalmega.
"""

from __future__ import annotations

import json
from pathlib import Path

from recommender.forme_identity import canonical_usage_species_id
from recommender.ids import to_id
from recommender.legality import load_snapshot
from recommender.species_forms import item_mega_forme

_TARGET = (
    Path(__file__).resolve().parents[2]
    / "docs/hosted_demo/targets/target_worlds_2026_yamazaki.json"
)


def test_worlds_mega_pairs_as_written():
    target = json.loads(_TARGET.read_text())
    snap = load_snapshot()
    regulation = target["regulation"]["tag"]
    members = {m["species"]: m for m in target["members"]}

    for species in ("Floette-Eternal", "Dragonite"):
        member = members[species]
        sid = to_id(member["species"])
        iid = to_id(member["item"])
        assert sid in snap["species"]
        assert iid in snap["items"]
        assert canonical_usage_species_id(snap, sid, regulation=regulation) == sid

    assert item_mega_forme(to_id("Dragoninite"), to_id("Dragonite"), snap) == "dragonitemega"
    assert item_mega_forme(to_id("Floettite"), to_id("Floette-Eternal"), snap) is None
    assert item_mega_forme(to_id("Floettite"), "floette", snap) == "floettemega"
