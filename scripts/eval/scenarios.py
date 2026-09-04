"""Fifteen scripted legality-eval scenarios (Task A)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from unittest.mock import patch

from recommender.state import (
    Attr,
    Slot,
    TargetRoleDecision,
    UnresolvedSlotRefinement,
    empty_slot,
)
from scripts.eval.harness import (
    ScenarioResult,
    accept_recommended_until_terminal,
    locked_pairs,
    seed_state,
    terminal_reason,
    turn,
)

SPREAD = {"hp": 32, "atk": 0, "def": 0, "spa": 32, "spd": 2, "spe": 0}


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    path: str
    doc: str
    run: Callable[[Any, dict, dict], ScenarioResult]


def _locked(
    species: str,
    *,
    role: str = "bulky_attacker",
    ability: str = "Pressure",
    item: str = "Sitrus Berry",
    moves: list[str] | None = None,
    nature: str = "Adamant",
    spread: dict[str, int] | None = None,
) -> Slot:
    return Slot(
        role=Attr(role, locked=True),
        species=Attr(species, locked=True),
        ability=Attr(ability, locked=True),
        item=Attr(item, locked=True),
        moveset=Attr(
            moves or ["Protect", "Tackle", "Rest", "Sleep Talk"], locked=True
        ),
        nature=Attr(nature, locked=True),
        spread=Attr(dict(spread or SPREAD), locked=True),
    )


def _locked_pelipper() -> Slot:
    return _locked(
        "Pelipper",
        role="rain_setter",
        ability="Drizzle",
        item="Focus Sash",
        moves=["Hurricane", "Tailwind", "Weather Ball", "Wide Guard"],
        nature="Timid",
        spread={"hp": 2, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 32},
    )


def _locked_gholdengo() -> Slot:
    return _locked(
        "Gholdengo",
        role="fast_special_attacker",
        ability="Good as Gold",
        item="Life Orb",
        moves=["Make It Rain", "Shadow Ball", "Protect", "Nasty Plot"],
        nature="Timid",
        spread={"hp": 4, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 30},
    )


def _locked_incineroar() -> Slot:
    return _locked(
        "Incineroar",
        role="support",  # role string on Attr, not TargetRoleId
        ability="Intimidate",
        item="Sitrus Berry",
        moves=["Fake Out", "Knock Off", "Flare Blitz", "Parting Shot"],
        nature="Careful",
        spread={"hp": 32, "atk": 4, "def": 0, "spa": 0, "spd": 28, "spe": 2},
    )


def _pad(draft: list[Slot]) -> list[Slot]:
    return [*draft, *[empty_slot() for _ in range(max(0, 6 - len(draft)))]]


def _candidate_pending(
    species: str,
    *,
    slot_index: int = 0,
    role_id: str | None = None,
    source: str = "need",
) -> dict[str, Any]:
    option: dict[str, Any] = {"species": species, "source": source}
    if role_id:
        option["target_role_decision"] = TargetRoleDecision(
            role_id=role_id,  # type: ignore[arg-type]
            source="other",
        )
    return {
        "schema_version": 1,
        "kind": "candidate_selection",
        "slot_index": slot_index,
        "options": [option],
    }


def _result(
    scenario_id: str,
    path: str,
    state: dict[str, Any],
    terminal: str,
    *,
    notes: str = "",
) -> ScenarioResult:
    return ScenarioResult(
        scenario_id=scenario_id,
        path=path,
        terminal=terminal,
        pairs=locked_pairs(state),
        state=state,
        notes=notes,
    )


def _bootstrap(direction: str, anchor: str) -> dict[str, Any]:
    return {
        "direction_text": direction,
        "anchor_text": anchor,
        "pool_entries": None,
        "delegated": False,
        "ownership_mode": None,
    }


def _run_baseline(
    scenario_id: str,
    path: str,
    direction: str,
    anchor: str,
) -> Callable[[Any, dict, dict], ScenarioResult]:
    def run(graph, config, state) -> ScenarioResult:
        state, terminal = accept_recommended_until_terminal(
            graph,
            config,
            state,
            bootstrap_payload=_bootstrap(direction, anchor),
        )
        return _result(scenario_id, path, state, terminal)

    return run


def _select_and_confirm(
    graph,
    config,
    state: dict[str, Any],
    pending: dict[str, Any],
    *,
    abandon: bool = False,
    usage_miss: bool = False,
) -> dict[str, Any]:
    seed_state(
        graph,
        config,
        team_draft=state["team_draft"],
        pending_presentation=pending,
        bootstrap_intake_complete=True,
    )
    patches = []
    if usage_miss:
        patches.append(
            patch("recommender.propose.featured_or_common_set", return_value=None)
        )
        patches.append(
            patch(
                "recommender.usage_data.featured_or_common_set",
                return_value=None,
            )
        )
        patches.append(
            patch(
                "recommender.usage_data.build_team_aware_default_set",
                return_value=None,
            )
        )
    for p in patches:
        p.start()
    try:
        state = turn(graph, config, {
            "turn_intent": "slot_candidate_selected",
            "selected_option": pending["options"][0],
        })
    finally:
        for p in patches:
            p.stop()

    if abandon:
        if state.get("pending_presentation", {}).get("kind") == "full_build_confirmation":
            state = turn(graph, config, {"turn_intent": "build_abandoned"})
        return state

    if state.get("pending_presentation", {}).get("kind") == "full_build_confirmation":
        # Avoid rediscovery calc after commit for single-slot risky paths.
        with patch(
            "recommender.slot_fill.build_anchored_slot_fill_context"
        ) as discovery:
            discovery.return_value.context = None
            with patch(
                "recommender.nodes.discover_multi_locked",
                return_value={
                    "coverage": [],
                    "spofs": [],
                    "shared_teammates": None,
                    "last_team_review": None,
                    "candidate_discovery_error": None,
                    "pending_presentation": None,
                },
            ):
                state = turn(graph, config, {"turn_intent": "full_slot_confirmed"})
    return state


def _run_select_confirm(
    scenario_id: str,
    path: str,
    species: str,
    *,
    role_id: str | None = None,
    draft: list[Slot] | None = None,
    slot_index: int = 0,
    usage_miss: bool = False,
    abandon: bool = False,
) -> Callable[[Any, dict, dict], ScenarioResult]:
    def run(graph, config, state) -> ScenarioResult:
        base = _pad(list(draft or []))
        seed_state(graph, config, team_draft=base, bootstrap_intake_complete=True)
        state = graph.get_state(config).values
        pending = _candidate_pending(
            species, slot_index=slot_index, role_id=role_id
        )
        state = _select_and_confirm(
            graph,
            config,
            state,
            pending,
            abandon=abandon,
            usage_miss=usage_miss,
        )
        term = terminal_reason(state) or (
            "build_abandoned"
            if abandon
            else (
                "incomplete_build"
                if isinstance(state.get("provisional_refinement"), UnresolvedSlotRefinement)
                else "stalled_after_select"
            )
        )
        if abandon and state.get("turn_intent") == "build_abandoned":
            term = "build_abandoned"
        if isinstance(state.get("provisional_refinement"), UnresolvedSlotRefinement):
            term = state["provisional_refinement"].reason or "incomplete_build"
        # Single-slot risky paths won't reach team-complete; committed pairs = success.
        if (
            term == "stalled_after_select"
            and locked_pairs(state)
            and state.get("slot_commit_error") is None
            and not isinstance(state.get("provisional_refinement"), UnresolvedSlotRefinement)
        ):
            term = "slot_committed"
        return _result(scenario_id, path, state, term)

    return run


def _run_revise(
    scenario_id: str,
    path: str,
    *,
    field: str,
    value: str,
) -> Callable[[Any, dict, dict], ScenarioResult]:
    def run(graph, config, state) -> ScenarioResult:
        draft = _pad([_locked_gholdengo()])
        seed_state(graph, config, team_draft=draft, bootstrap_intake_complete=True)
        state = turn(
            graph,
            config,
            {
                "turn_intent": "revise_locked_slot",
                "turn_payload": {
                    "slot_index": 0,
                    "field": field,
                    "value": value,
                    "scope": "field_only",
                },
            },
        )
        if state.get("pending_presentation", {}).get("kind") == "full_build_confirmation":
            with patch(
                "recommender.slot_fill.build_anchored_slot_fill_context"
            ) as discovery:
                discovery.return_value.context = None
                state = turn(graph, config, {"turn_intent": "full_slot_confirmed"})
        term = terminal_reason(state) or "revise_done"
        # One locked slot is not team-complete; treat successful item lock as ok.
        if locked_pairs(state) and state.get("slot_commit_error") is None:
            term = "revise_committed"
        return _result(scenario_id, path, state, term)

    return run


def _run_repick(
    scenario_id: str,
    path: str,
    replacement: str,
    *,
    role_id: str = "bulky_attacker",
) -> Callable[[Any, dict, dict], ScenarioResult]:
    def run(graph, config, state) -> ScenarioResult:
        draft = _pad([_locked_gholdengo(), _locked_incineroar(), _locked_pelipper()])
        seed_state(graph, config, team_draft=draft, bootstrap_intake_complete=True)
        # Unlock slot 0 → still ≥2 locked → multi_locked rediscovery.
        pending = _candidate_pending(replacement, slot_index=0, role_id=role_id)
        with patch(
            "recommender.nodes.discover_multi_locked",
            return_value={
                "coverage": [],
                "spofs": [],
                "shared_teammates": None,
                "last_team_review": None,
                "candidate_discovery_error": None,
                "pending_presentation": pending,
            },
        ):
            state = turn(
                graph,
                config,
                {
                    "turn_intent": "repick_locked_slot",
                    "turn_payload": {"slot_index": 0},
                },
            )
        state = _select_and_confirm(graph, config, state, pending)
        term = terminal_reason(state) or "repick_done"
        if any(s == replacement for s, _ in locked_pairs(state)):
            term = "repick_committed"
        return _result(scenario_id, path, state, term)

    return run


SCENARIOS: list[Scenario] = [
    Scenario(
        "baseline_rain",
        "baseline",
        "Ordinary intake: Rain / Pelipper bootstrap through accept-recommended.",
        _run_baseline("baseline_rain", "baseline", "Rain", "Pelipper"),
    ),
    Scenario(
        "baseline_trick_room",
        "baseline",
        "Ordinary intake: Trick Room / Farigiraf.",
        _run_baseline(
            "baseline_trick_room", "baseline", "Trick Room", "Farigiraf"
        ),
    ),
    Scenario(
        "baseline_intimidate",
        "baseline",
        "Ordinary intake: Intimidate core / Incineroar.",
        _run_baseline(
            "baseline_intimidate", "baseline", "Intimidate core", "Incineroar"
        ),
    ),
    Scenario(
        "last_resort_commit",
        "last_resort",
        "ADR-015 Amendment 2026-08-09a: usage miss → last-resort synthesis (Mimikyu).",
        _run_select_confirm(
            "last_resort_commit",
            "last_resort",
            "Mimikyu",
            role_id="fast_physical_attacker",
            usage_miss=True,
        ),
    ),
    Scenario(
        "last_resort_incomplete",
        "last_resort",
        "ADR-015 Amendment 2026-08-09a: usage miss expected incomplete_build.",
        _run_select_confirm(
            "last_resort_incomplete",
            "last_resort",
            "Ditto",
            role_id="screens_support",
            usage_miss=True,
        ),
    ),
    Scenario(
        "role_aware_sableye_screens",
        "role_aware",
        "ADR-053: Sableye for screens_support via role-aware synthesis.",
        _run_select_confirm(
            "role_aware_sableye_screens",
            "role_aware",
            "Sableye",
            role_id="screens_support",
        ),
    ),
    Scenario(
        "role_aware_ninetales_screens",
        "role_aware",
        "ADR-053: Ninetales-Alola for screens_support.",
        _run_select_confirm(
            "role_aware_ninetales_screens",
            "role_aware",
            "Ninetales-Alola",
            role_id="screens_support",
        ),
    ),
    Scenario(
        "provisional_confirm",
        "provisional",
        "Usage-backed provisional → full_slot_confirmed (Gholdengo).",
        _run_select_confirm(
            "provisional_confirm",
            "provisional",
            "Gholdengo",
            role_id="fast_special_attacker",
        ),
    ),
    Scenario(
        "provisional_abandon",
        "provisional",
        "Reach full_build_confirmation then build_abandoned.",
        _run_select_confirm(
            "provisional_abandon",
            "provisional",
            "Gholdengo",
            role_id="fast_special_attacker",
            abandon=True,
        ),
    ),
    Scenario(
        "revise_item",
        "revise_locked_slot",
        "revise_locked_slot item edit on locked Gholdengo.",
        _run_revise("revise_item", "revise_locked_slot", field="item", value="Focus Sash"),
    ),
    Scenario(
        "revise_nature",
        "revise_locked_slot",
        "revise_locked_slot nature edit on locked Gholdengo.",
        _run_revise(
            "revise_nature", "revise_locked_slot", field="nature", value="Modest"
        ),
    ),
    Scenario(
        "repick_gholdengo",
        "repick_locked_slot",
        "repick_locked_slot → replace with Archaludon.",
        _run_repick(
            "repick_gholdengo",
            "repick_locked_slot",
            "Archaludon",
            role_id="bulky_special_attacker",
        ),
    ),
    Scenario(
        "repick_sinistcha",
        "repick_locked_slot",
        "repick_locked_slot → replace with Sinistcha.",
        _run_repick(
            "repick_sinistcha",
            "repick_locked_slot",
            "Sinistcha",
            role_id="redirection",
        ),
    ),
    Scenario(
        "team_conditioned_sableye",
        "team_conditioned",
        "ADR-056: locked Pelipper → Sableye team-conditioned build.",
        _run_select_confirm(
            "team_conditioned_sableye",
            "team_conditioned",
            "Sableye",
            role_id="screens_support",
            draft=[_locked_pelipper()],
            slot_index=1,
        ),
    ),
    Scenario(
        "team_conditioned_basculegion",
        "team_conditioned",
        "ADR-056: locked Pelipper → Basculegion team-conditioned build.",
        _run_select_confirm(
            "team_conditioned_basculegion",
            "team_conditioned",
            "Basculegion",
            role_id="fast_physical_attacker",
            draft=[_locked_pelipper()],
            slot_index=1,
        ),
    ),
]


assert len(SCENARIOS) == 15
