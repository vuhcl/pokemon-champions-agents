"""Ability usage maps + Psychic Terrain priority denial."""

from __future__ import annotations

from recommender.ability_classification import (
    flinch_denial_ability_ids,
    priority_denial_ability_ids,
)
from recommender.legality import load_snapshot
from recommender.role_compendium import (
    TRICK_ROOM_SETTER_CRITERIA,
    _ABILITY_MEMBERSHIP_PCT_FLOOR,
    _modal_ability_map,
    _usage_ability_map,
    construct_role_category,
    legal_species_pool,
)


REG = "champions-reg-mc"


def test_ability_membership_floor_is_policy_10():
    assert _ABILITY_MEMBERSHIP_PCT_FLOOR == 10.0


def test_priority_denial_includes_psychic_surge_not_other_surges():
    ids = priority_denial_ability_ids()
    assert "psychicsurge" in ids
    assert "electricsurge" not in ids
    assert "grassysurge" not in ids
    assert flinch_denial_ability_ids() < ids


def test_indeedee_modal_is_psychic_surge():
    snap = load_snapshot()
    assert _modal_ability_map(snap, "indeedee", regulation=REG) == {
        "psychicsurge": "Psychic Surge"
    }
    assert _modal_ability_map(snap, "indeedeef", regulation=REG) == {
        "psychicsurge": "Psychic Surge"
    }


def test_vivillon_usage_map_excludes_friend_guard():
    snap = load_snapshot()
    usage = _usage_ability_map(snap, "vivillon", regulation=REG)
    assert "friendguard" not in usage
    assert "compoundeyes" in usage


def test_trick_room_indeedee_excellent_via_terrain():
    snap = load_snapshot()
    draft = construct_role_category(
        "trick_room_setter",
        TRICK_ROOM_SETTER_CRITERIA,
        legal_species_pool(snap),
        snap=snap,
        live_fetch=None,
        showdown_fetch=None,
        regulation=REG,
    )
    by = {c.species: c for c in draft.candidates if c.tier}
    assert by["Indeedee"].tier == "Excellent"
    assert by["Indeedee"].excellence_basis == "psychic_terrain_priority_denial"
    assert by["Indeedee-F"].tier == "Excellent"
    assert by["Indeedee-F"].excellence_basis == "psychic_terrain_priority_denial"


def test_sandaconda_non_modal_sand_spit_grant():
    """Sand Spit ~41% ≥10% while modal is Sand Veil — setter credit uses Sand Spit."""
    snap = load_snapshot()
    from recommender.role_compendium import _effective_ability_for_predicate

    amap, grant = _effective_ability_for_predicate(
        snap,
        "sandaconda",
        regulation=REG,
        predicate_ids=frozenset({"sandspit"}),
    )
    assert grant == "sandspit"
    assert amap == {"sandspit": "Sand Spit"}
    modal = _modal_ability_map(snap, "sandaconda", regulation=REG)
    assert "sandveil" in modal


def test_kingambit_swords_dance_stays_good():
    from recommender.role_compendium import SWORDS_DANCE_ATTACKER_CRITERIA

    snap = load_snapshot()
    draft = construct_role_category(
        "swords_dance_attacker",
        SWORDS_DANCE_ATTACKER_CRITERIA,
        legal_species_pool(snap),
        snap=snap,
        live_fetch=None,
        showdown_fetch=None,
        regulation=REG,
    )
    by = {c.species: c for c in draft.candidates if c.tier}
    assert by["Kingambit"].tier == "Good"
