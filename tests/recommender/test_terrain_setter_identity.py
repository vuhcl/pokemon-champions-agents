"""Terrain setter identity wiring (TargetRoleId / mechanisms / field state)."""

from __future__ import annotations

from recommender.anchor_roles import (
    FieldProvenance,
    ResolvedAnchorBuild,
    classify_anchor_role,
    resolve_anchor_build,
)
from recommender.bootstrap import resolve_bootstrap_direction
from recommender.calc_client import CalcClient, CalcClientError
from recommender.condition_resilience import team_field_states
from recommender.contingent_value import categorize_champions_pool
from recommender.coverage import ABILITY_TO_FIELD
from recommender.ids import to_id
from recommender.role_compendium_read import ReverseCompendiumEvidence
from recommender.slot_fill import LockedAnchorContext
from recommender.slot_fill_target_role import (
    REVIEWED_STRATEGIC_TARGET_ROLES,
    target_role_from_needs,
)
from recommender.support_needs import RoleShapeContext, query_support_needs


def _empty_compendium() -> ReverseCompendiumEvidence:
    return ReverseCompendiumEvidence()


def _context(slot_index: int, build: ResolvedAnchorBuild, decision) -> LockedAnchorContext:
    return LockedAnchorContext(
        slot_index=slot_index,
        anchor_id=to_id(build.species or ""),
        pokemon=build.as_pokemon(),
        resolved_build=build,
        role_decision=decision,
        role_shape_context=RoleShapeContext(
            primary_function=decision.primary_function,
            tankiness="unknown",
            requires_setup_turn=False,
        ),
        support_needs=(),
    )


def test_seedsower_maps_to_grassy_field_and_contingent_pool():
    assert ABILITY_TO_FIELD["seedsower"]["terrain"] == "Grassy"
    pool = categorize_champions_pool()
    assert "arboliva" in pool["terrain_setter"]
    assert set(pool["terrain_setter"]) >= {
        "raichumegax",
        "pincurchin",
        "rillaboom",
        "indeedee",
        "indeedeef",
        "arboliva",
    }


def test_bootstrap_terrain_phrases_resolve_live_only():
    assert resolve_bootstrap_direction("electric") == "electric_terrain_setter"
    assert resolve_bootstrap_direction("Electric Terrain") == "electric_terrain_setter"
    assert resolve_bootstrap_direction("electric offense") == "electric_terrain_setter"
    assert resolve_bootstrap_direction("grassy") == "grassy_terrain_setter"
    assert resolve_bootstrap_direction("Grassy Terrain") == "grassy_terrain_setter"
    assert resolve_bootstrap_direction("psychic") == "psychic_terrain_setter"
    assert resolve_bootstrap_direction("Psychic Terrain") == "psychic_terrain_setter"
    assert resolve_bootstrap_direction("misty") is None
    assert resolve_bootstrap_direction("Misty Terrain") is None
    assert "mistyterrainsetter" in REVIEWED_STRATEGIC_TARGET_ROLES


def test_writeup_grassy_surge_emits_terrain_mechanism(monkeypatch):
    monkeypatch.setattr(
        "recommender.anchor_roles.featured_or_common_set", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "recommender.anchor_roles.get_writeup_ability",
        lambda *a, **k: {
            "ability": "Grassy Surge",
            "source_tier": "analogous_format_writeup",
            "source_format": "sv/vgc",
            "ability_candidates": ["Grassy Surge"],
            "ability_pick_index": 0,
            "ability_pick_policy": "first_listed",
        },
    )
    monkeypatch.setattr(
        "recommender.anchor_roles.species_can_have_ability", lambda *a, **k: True
    )
    build = resolve_anchor_build("Rillaboom", regulation="champions-reg-mb")
    assert build.ability == "Grassy Surge"
    decision = classify_anchor_role(build, compendium=_empty_compendium())
    auto = [
        m
        for m in decision.mechanisms
        if m.kind == "automatic_condition_setting" and m.present
    ]
    assert auto
    assert auto[0].role_id == "grassy_terrain_setter"
    assert "condition:Grassy" in auto[0].evidence


def test_writeup_psychic_surge_emits_terrain_mechanism(monkeypatch):
    monkeypatch.setattr(
        "recommender.anchor_roles.featured_or_common_set", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "recommender.anchor_roles.get_writeup_ability",
        lambda *a, **k: {
            "ability": "Psychic Surge",
            "source_tier": "analogous_format_writeup",
            "source_format": "sv/vgc",
            "ability_candidates": ["Psychic Surge"],
            "ability_pick_index": 0,
            "ability_pick_policy": "first_listed",
        },
    )
    monkeypatch.setattr(
        "recommender.anchor_roles.species_can_have_ability", lambda *a, **k: True
    )
    build = resolve_anchor_build("Indeedee", regulation="champions-reg-mb")
    decision = classify_anchor_role(build, compendium=_empty_compendium())
    auto = next(
        m
        for m in decision.mechanisms
        if m.kind == "automatic_condition_setting" and m.present
    )
    assert auto.role_id == "psychic_terrain_setter"
    assert "condition:Psychic" in auto.evidence


def test_arboliva_seed_sower_emits_grassy_mechanism():
    build = ResolvedAnchorBuild(
        species="Arboliva",
        ability="Seed Sower",
        item=None,
        nature=None,
        evs=(),
        moves=("Giga Drain", "Earth Power", "Protect", "Dazzling Gleam"),
        regulation="champions-reg-mb",
        provenance=(FieldProvenance("ability", "user_confirmed"),),
        fingerprint="test",
    )
    decision = classify_anchor_role(build, compendium=_empty_compendium())
    auto = next(
        m
        for m in decision.mechanisms
        if m.kind == "automatic_condition_setting" and m.present
    )
    assert auto.role_id == "grassy_terrain_setter"
    assert "Seed Sower" in auto.mechanic


def test_team_field_states_forces_grassy_terrain_for_calc():
    build = ResolvedAnchorBuild(
        species="Rillaboom",
        ability="Grassy Surge",
        item=None,
        nature=None,
        evs=(),
        moves=("Grassy Glide", "Wood Hammer", "Fake Out", "U-turn"),
        regulation="champions-reg-mb",
        provenance=(FieldProvenance("ability", "user_confirmed"),),
        fingerprint="test",
    )
    decision = classify_anchor_role(build, compendium=_empty_compendium())
    fields = team_field_states([_context(0, build, decision)])
    assert any(f.get("terrain") == "Grassy" for f in fields)

    client = CalcClient()
    try:
        client.health()
    except Exception:
        return
    field = next(f for f in fields if f.get("terrain") == "Grassy")
    try:
        result = client.calculate(
            {
                "species": "Rillaboom",
                "ability": "Grassy Surge",
                "moves": ["Grassy Glide"],
            },
            {"species": "Incineroar"},
            "Grassy Glide",
            field=field,
        )
    except CalcClientError:
        return
    assert "damageRange" in result


def test_grass_pelt_need_resolves_to_grassy_terrain_setter(monkeypatch):
    monkeypatch.setattr(
        "recommender.support_needs.featured_or_common_set",
        lambda *a, **k: {"ability": "Grass Pelt", "moves": ["Wood Hammer"]},
    )
    needs = query_support_needs(
        {"species": "Gogoat", "ability": "Grass Pelt"},
        RoleShapeContext(primary_function="offense", tankiness="tanky"),
        team_draft=None,
        regulation="champions-reg-mb",
    )
    terrain_needs = [
        n for n in needs if n.category == "condition_setter" and n.trigger
    ]
    assert terrain_needs
    assert "grassy" in (terrain_needs[0].trigger or "")
    decision = target_role_from_needs(terrain_needs)
    assert decision is not None
    assert getattr(decision, "role_id", None) == "grassy_terrain_setter"
