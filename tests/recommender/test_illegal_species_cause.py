"""illegal_species refusals name the pin condition (Mythical / Restricted / is_nonstandard / tier)."""

from __future__ import annotations

from recommender.legality import load_snapshot
from recommender.state import empty_slot
from recommender.team_validation import validate_team_value


def test_illegal_species_names_mythical():
    draft = [empty_slot() for _ in range(6)]
    v = validate_team_value("species", "Mew", slot_index=0, team_draft=draft)
    assert v.refusal and v.refusal.kind == "illegal_species"
    assert "Mythical" in v.refusal.message
    assert "not legal" in v.refusal.message


def test_illegal_species_names_restricted_legendary():
    draft = [empty_slot() for _ in range(6)]
    v = validate_team_value("species", "Mewtwo", slot_index=0, team_draft=draft)
    assert v.refusal and "Restricted Legendary" in v.refusal.message
    assert "not legal" in v.refusal.message


def test_illegal_species_names_is_nonstandard():
    draft = [empty_slot() for _ in range(6)]
    v = validate_team_value("species", "Bulbasaur", slot_index=0, team_draft=draft)
    assert v.refusal and "is_nonstandard" in v.refusal.message and "Past" in v.refusal.message
    assert "not legal" in v.refusal.message


def test_illegal_species_names_tier_illegal():
    draft = [empty_slot() for _ in range(6)]
    snap = load_snapshot()
    fake = {
        **snap,
        "species": {
            **snap["species"],
            "fakemon": {
                "id": "fakemon",
                "name": "Fakemon",
                "is_nonstandard": None,
                "tier": "Illegal",
                "effective_tags": [],
                "base_stats": {"hp": 1, "atk": 1, "def": 1, "spa": 1, "spd": 1, "spe": 1},
                "abilities": {"0": "Overgrow"},
            },
        },
    }
    v = validate_team_value(
        "species", "Fakemon", slot_index=0, team_draft=draft, snap=fake
    )
    assert v.refusal and "tier Illegal" in v.refusal.message
    assert "not legal" in v.refusal.message
