"""Scripted LangGraph harness for eval scenarios (no live LLM)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
from unittest.mock import patch

from langgraph.checkpoint.memory import MemorySaver

from recommender.graph import compile_graph
from recommender.nodes import team_phase
from recommender.state import (
    TeamReviewResult,
    UnresolvedSlotRefinement,
    all_locked,
)

VGC_MB = "[Gen 9 Champions] VGC 2026 Reg M-B"
TURN_CAP = 40


@dataclass
class ScenarioResult:
    scenario_id: str
    path: str
    terminal: str
    pairs: list[tuple[str, str]] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)
    notes: str = ""


def start_graph(*, thread_id: str, calc_degraded: bool = False):
    graph = compile_graph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": thread_id}}
    review_patch = None
    if calc_degraded:
        review_patch = patch(
            "recommender.nodes._compute_team_review",
            return_value=TeamReviewResult(
                threats=[], coverage=[], spofs=[], status="available"
            ),
        )
        review_patch.start()
    state = graph.invoke({"format_id": VGC_MB}, config=config)
    return graph, config, state, review_patch


def seed_state(graph, config, **updates: Any) -> None:
    """Seed only explicit keys — never clobber regulation_mod from initialize."""
    graph.update_state(config, updates)


def turn(graph, config, intent: dict[str, Any], *, text: str = "x") -> dict[str, Any]:
    with patch("recommender.nodes.classify_pending", return_value=intent):
        return graph.invoke({"pending_input": text}, config=config)


def locked_pairs(state: dict[str, Any]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for slot in state.get("team_draft") or []:
        if not all_locked(slot):
            continue
        species = str(slot.species.value or "")
        item = str(slot.item.value or "")
        out.append((species, item))
    return out


def terminal_reason(state: dict[str, Any]) -> str | None:
    if team_phase(state) == "complete":
        return "complete"
    if state.get("turn_intent") == "build_abandoned":
        return "build_abandoned"
    ref = state.get("provisional_refinement")
    if isinstance(ref, UnresolvedSlotRefinement):
        return ref.reason or "incomplete_build"
    err = state.get("candidate_discovery_error")
    if err is not None and state.get("pending_presentation") is None:
        kind = getattr(err, "kind", None) or (
            err.get("kind") if isinstance(err, dict) else "discovery_error"
        )
        return f"discovery:{kind}"
    return None


def _select_first_candidate(pending: dict[str, Any]) -> dict[str, Any]:
    options = pending.get("options") or []
    if not options:
        raise RuntimeError("candidate_selection with no options")
    return {
        "turn_intent": "slot_candidate_selected",
        "selected_option": options[0],
    }


def _select_first_preference(pending: dict[str, Any]) -> dict[str, Any]:
    prefs = pending.get("preference_options") or ()
    if not prefs:
        raise RuntimeError("completion_preference with no options")
    return {
        "turn_intent": "continue",
        "team_completion_preference": prefs[0],
        "pending_presentation": None,
    }


def accept_recommended_until_terminal(
    graph,
    config,
    state: dict[str, Any],
    *,
    bootstrap_payload: dict[str, Any] | None = None,
    turn_cap: int = TURN_CAP,
) -> tuple[dict[str, Any], str]:
    """Drive ordinary discovery by always accepting the first recommended option."""
    for _ in range(turn_cap):
        reason = terminal_reason(state)
        if reason:
            return state, reason

        pending = state.get("pending_presentation")
        if pending is None:
            return state, "stalled_no_pending"

        kind = pending.get("kind")
        if kind == "bootstrap_intake":
            if bootstrap_payload is None:
                return state, "stalled_bootstrap_no_payload"
            state = turn(
                graph,
                config,
                {
                    "turn_intent": "bootstrap_response",
                    "turn_payload": bootstrap_payload,
                    "pending_presentation": None,
                },
            )
        elif kind == "candidate_selection":
            try:
                state = turn(graph, config, _select_first_candidate(pending))
            except RuntimeError:
                return state, "stalled_empty_candidates"
        elif kind == "completion_preference":
            try:
                state = turn(graph, config, _select_first_preference(pending))
            except RuntimeError:
                return state, "stalled_empty_preferences"
        elif kind == "full_build_confirmation":
            state = turn(graph, config, {"turn_intent": "full_slot_confirmed"})
        else:
            return state, f"stalled_unknown_pending:{kind}"

    return state, "stalled_turn_cap"


def run_scenario(
    scenario_id: str,
    path: str,
    runner: Callable[..., ScenarioResult],
    *,
    calc_degraded: bool = False,
) -> ScenarioResult:
    graph, config, state, review_patch = start_graph(
        thread_id=f"eval-{scenario_id}", calc_degraded=calc_degraded
    )
    try:
        return runner(graph, config, state)
    finally:
        if review_patch is not None:
            review_patch.stop()
