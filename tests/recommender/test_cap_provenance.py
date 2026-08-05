"""CAP / non-official provenance: stored markers + exclusion (not join-only)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from recommender.ability_classification import load_abilities
from recommender.legality import is_move_legal, is_species_legal, load_snapshot

ROOT = Path(__file__).resolve().parents[2]
ACCURACY_PATH = ROOT / "data" / "moves" / "gen9_accuracy.v1.json"

# Known CAP-only Showdown ids (data/moves.ts / formats-data.ts isNonstandard: "CAP").
CAP_MOVES = ("paleowave", "shadowstrike", "polarflare")
CAP_ABILITIES = ("mountaineer", "rebound", "persistent")
CAP_SPECIES = ("syclant", "tomohawk", "cawmodore")


def test_cap_moves_flagged_in_legality_snapshot():
    snap = load_snapshot()
    for mid in CAP_MOVES:
        entry = snap["moves"][mid]
        assert entry["is_nonstandard"] == "CAP", mid
        assert is_move_legal(snap, mid) is False, mid


def test_cap_abilities_flagged_in_classification_table():
    load_abilities.cache_clear()
    abilities = load_abilities()["abilities"]
    for aid in CAP_ABILITIES:
        assert abilities[aid]["is_nonstandard"] == "CAP", aid
    assert abilities["asone"]["is_nonstandard"] is None
    assert abilities["asoneglastrier"]["is_nonstandard"] is None
    assert abilities["asonespectrier"]["is_nonstandard"] is None


def test_every_ability_has_is_nonstandard_key():
    load_abilities.cache_clear()
    abilities = load_abilities()["abilities"]
    for aid, e in abilities.items():
        assert "is_nonstandard" in e, aid
    assert any(e["is_nonstandard"] == "Past" for e in abilities.values())
    assert any(e["is_nonstandard"] == "Future" for e in abilities.values())


@pytest.mark.skipif(not ACCURACY_PATH.is_file(), reason='move accuracy snapshot lands with feat/query-counters')
def test_cap_moves_flagged_in_accuracy_table():
    acc = json.loads(ACCURACY_PATH.read_text())
    for mid in CAP_MOVES:
        assert acc[mid]["is_nonstandard"] == "CAP", mid


@pytest.mark.skipif(not ACCURACY_PATH.is_file(), reason='move accuracy snapshot lands with feat/query-counters')
def test_every_accuracy_entry_has_is_nonstandard():
    acc = json.loads(ACCURACY_PATH.read_text())
    for mid, e in acc.items():
        assert "is_nonstandard" in e, mid
    non_null = sum(1 for e in acc.values() if e.get("is_nonstandard") is not None)
    assert non_null == 454
    assert any(e.get("is_nonstandard") == "Past" for e in acc.values())
    assert any(e.get("is_nonstandard") == "LGPE" for e in acc.values())


def test_cap_species_absent_from_champions_snapshot():
    """CAP species are absent from the Champions-scoped formats-data join.

    This is NOT “present with is_nonstandard: CAP” (unlike moves in the legality
    snapshot). Protection is a property of the current pipeline *shape* — the
    Champions formats-data keys never include CAP — not a stored positive
    assertion on a CAP row. If the species-merging pipeline is later broadened
    to pull from a wider source before filtering, CAP could enter unmarked and
    this absence-assumption would need revisiting. Known pipeline-shape-
    dependent risk; not an immediate action item.
    """
    snap = load_snapshot()
    for sid in CAP_SPECIES:
        assert sid not in snap["species"], sid
        assert is_species_legal(snap, sid) is False, sid


def test_stored_nonstandard_species_flag_excludes():
    """When a nonstandard species *is* stored, is_nonstandard is read and used."""
    snap = load_snapshot()
    past = next(
        (sid, e)
        for sid, e in snap["species"].items()
        if e.get("is_nonstandard") == "Past"
    )
    sid, entry = past
    assert entry["is_nonstandard"] == "Past"
    assert is_species_legal(snap, sid) is False
