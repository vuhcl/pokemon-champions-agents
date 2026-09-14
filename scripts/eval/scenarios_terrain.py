"""Terrain mechanism eval scenarios (discovery + seeded field spy)."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from recommender.anchor_roles import classify_anchor_role, resolve_anchor_build
from recommender.bootstrap import discover_bootstrap_directions
from recommender.condition_resilience import team_field_states
from recommender.ids import to_id
from recommender.matchup import classify_matchup
from recommender.nodes import initialize, record_bootstrap_response
from recommender.slot_fill import LockedAnchorContext
from recommender.state import Attr, Slot, empty_slot
from recommender.support_needs import RoleShapeContext
from scripts.eval.harness import VGC_MC, seed_state, turn

SPREAD = {"hp": 32, "atk": 0, "def": 0, "spa": 0, "spd": 2, "spe": 32}


def _bootstrap_state(anchor: str) -> dict[str, Any]:
    raw: dict[str, Any] = {"format_id": VGC_MC}
    state = {**raw, **initialize(raw)}
    payload = {
        "direction_text": None,
        "anchor_text": anchor,
        "pool_entries": None,
        "delegated": False,
        "ownership_mode": None,
    }
    return {**state, **record_bootstrap_response({**state, "turn_payload": payload})}


def _locked_context(slot_index: int, build, decision) -> LockedAnchorContext:
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


def _discovery_case(species: str, expected_setter: str) -> dict[str, Any]:
    state = _bootstrap_state(species)
    discovery = discover_bootstrap_directions(state)
    checks: list[str] = []
    first = discovery.candidates[0] if discovery.candidates else None
    strategic = getattr(first, "strategic_role_id", None) if first else None
    if strategic != expected_setter:
        checks.append(f"strategic_role_id={strategic!r} want {expected_setter}")

    build = resolve_anchor_build(species)
    decision = classify_anchor_role(build)
    auto = [
        m
        for m in decision.mechanisms
        if m.kind == "automatic_condition_setting" and m.present
    ]
    if not auto:
        checks.append("no automatic_condition_setting mechanism post-lock")
    elif expected_setter and auto[0].role_id != expected_setter:
        checks.append(f"mechanism role_id={auto[0].role_id!r} want {expected_setter}")

    return {
        "scenario_id": f"terrain_discovery_{to_id(species)}",
        "species": species,
        "strategic_role_id": strategic,
        "mechanism_role_ids": [m.role_id for m in auto],
        "passed": not checks,
        "checks": checks,
    }


def _locked_rillaboom() -> Slot:
    return Slot(
        role=Attr("grassy_terrain_setter", locked=True),
        species=Attr("Rillaboom", locked=True),
        ability=Attr("Grassy Surge", locked=True),
        item=Attr("Assault Vest", locked=True),
        moveset=Attr(
            ["Grassy Glide", "Wood Hammer", "Fake Out", "U-turn"], locked=True
        ),
        nature=Attr("Adamant", locked=True),
        spread=Attr(dict(SPREAD), locked=True),
    )


def _seeded_field_spy() -> dict[str, Any]:
    """Seed locked Rillaboom; spy matchup fields and team_field_states."""
    from scripts.eval.harness import start_graph

    graph, config, state, review_patch = start_graph(
        thread_id="eval-terrain-seeded-rillaboom", format_id=VGC_MC
    )
    matchup_fields: list[Any] = []

    real_classify = classify_matchup

    def spy_classify(a, b, field=None, *args, **kwargs):
        if field is not None:
            matchup_fields.append(dict(field) if isinstance(field, dict) else field)
        return real_classify(a, b, field, *args, **kwargs)

    try:
        draft = [_locked_rillaboom(), *[empty_slot() for _ in range(5)]]
        seed_state(
            graph,
            config,
            team_draft=draft,
            bootstrap_intake_complete=True,
            pending_presentation={
                "schema_version": 1,
                "kind": "completion_preference",
                "preference_options": ("fill_remaining",),
            },
        )
        with patch("recommender.matchup.classify_matchup", side_effect=spy_classify):
            state = turn(
                graph,
                config,
                {
                    "turn_intent": "continue",
                    "team_completion_preference": "fill_remaining",
                    "pending_presentation": None,
                },
            )

        build = resolve_anchor_build("Rillaboom")
        decision = classify_anchor_role(build)
        fields_seen = list(team_field_states([_locked_context(0, build, decision)]))
    finally:
        if review_patch is not None:
            review_patch.stop()

    grassy_direct = any(f.get("terrain") == "Grassy" for f in fields_seen)
    grassy_spy = any(
        isinstance(f, dict) and f.get("terrain") == "Grassy" for f in matchup_fields
    )
    checks: list[str] = []
    if not grassy_direct:
        checks.append("team_field_states missing terrain=Grassy")
    return {
        "scenario_id": "terrain_seeded_rillaboom_field",
        "passed": not checks,
        "checks": checks,
        "team_field_states": fields_seen,
        "matchup_spy_grassy": grassy_spy,
        "matchup_spy_n": len(matchup_fields),
        "pending_kind": (state.get("pending_presentation") or {}).get("kind"),
    }


DISCOVERY_SPECIES = (
    ("Rillaboom", "grassy_terrain_setter"),
    ("Indeedee", "psychic_terrain_setter"),
    ("Arboliva", "grassy_terrain_setter"),
)


def run_all_terrain() -> list[dict[str, Any]]:
    results = [_discovery_case(sp, role) for sp, role in DISCOVERY_SPECIES]
    results.append(_seeded_field_spy())
    return results
