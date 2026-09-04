"""Eval-only oracle booleans (no recommender.legality gate imports)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.eval.oracle import item_legal, species_legal


def test_mythical_tag_banned_vs_legal_species():
    snap = {
        "flat_rules": {"banlist": ["Mythical"]},
        "species": {
            "mew": {
                "is_nonstandard": None,
                "tier": None,
                "effective_tags": ["Mythical"],
            },
            "incineroar": {
                "is_nonstandard": None,
                "tier": None,
                "effective_tags": [],
            },
            "pastmon": {
                "is_nonstandard": "Past",
                "tier": None,
                "effective_tags": [],
            },
            "illegalmon": {
                "is_nonstandard": None,
                "tier": "Illegal",
                "effective_tags": [],
            },
        },
        "items": {},
    }
    assert not species_legal(snap, "Mew")
    assert species_legal(snap, "Incineroar")
    assert not species_legal(snap, "Pastmon")
    assert not species_legal(snap, "Illegalmon")
    assert not species_legal(snap, "MissingNo")


def test_item_nonstandard_vs_legal():
    snap = {
        "flat_rules": {"banlist": []},
        "species": {},
        "items": {
            "leftovers": {"is_nonstandard": None},
            "olditem": {"is_nonstandard": "Past"},
        },
    }
    assert item_legal(snap, "Leftovers")
    assert not item_legal(snap, "Old Item")
    assert not item_legal(snap, "Missing Item")
    assert item_legal(snap, "")  # empty: no item claim
