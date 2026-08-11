from __future__ import annotations

from functools import partial

from langgraph.graph import END, START, StateGraph

from recommender import nodes
from recommender.state import RecommenderState

_INTENT_ROUTES = {
    "constraint": "record_constraint",
    "rejection": "record_rejection",
    "lock": "apply_lock",
    "archetype_change": "handle_archetype_change",
    "reset": "reset_team",
    "restore": "restore_superseded",
    "continue": "route_team_phase",
    "team_review": "generate_team_review",
    "bootstrap_response": "record_bootstrap_response",
    "pending_response": "finish_pending_response",
    "slot_candidate_selected": "refine_provisional_slot",
    "full_slot_confirmed": "commit_full_slot",
}

_PHASE_ROUTES = {
    "empty": "bootstrap_direction",
    "single_locked": "discover_single_locked",
    "multi_locked": "discover_multi_locked",
    "complete": "generate_team_review",
}


def _route_start(state: RecommenderState) -> str:
    if not state.get("game_type"):
        return "initialize"
    return "classify_input"


def _route_intent(state: RecommenderState) -> str:
    return _INTENT_ROUTES.get(state.get("turn_intent") or "", "route_team_phase")


def _route_team_phase(state: RecommenderState) -> str:
    return nodes.team_phase(state)


def _route_after_refine(state: RecommenderState) -> str:
    """Successful refine ends on confirmation; failures rediscover so the CLI is not stuck."""
    if state.get("provisional_slot") is not None:
        return END
    return "route_team_phase"


def build_graph(*, bootstrap_intake_parser=None) -> StateGraph:
    g = StateGraph(RecommenderState)
    g.add_node("initialize", nodes.initialize)
    g.add_node("accept_available_pool", nodes.accept_available_pool)
    g.add_node(
        "classify_input",
        partial(
            nodes.classify_input,
            bootstrap_intake_parser=bootstrap_intake_parser,
        ),
    )
    g.add_node("apply_lock", nodes.apply_lock)
    g.add_node("record_constraint", nodes.record_constraint)
    g.add_node("record_rejection", nodes.record_rejection)
    g.add_node("handle_archetype_change", nodes.handle_archetype_change)
    g.add_node("reset_team", nodes.reset_team)
    g.add_node("restore_superseded", nodes.restore_superseded)
    g.add_node("route_team_phase", nodes.route_team_phase)
    g.add_node("bootstrap_direction", nodes.bootstrap_direction)
    g.add_node("record_bootstrap_response", nodes.record_bootstrap_response)
    g.add_node("discover_single_locked", nodes.discover_single_locked)
    g.add_node("refresh_team_signals", nodes.refresh_team_signals)
    g.add_node("discover_multi_locked", nodes.discover_multi_locked)
    g.add_node("generate_team_review", nodes.generate_team_review)
    g.add_node("finish_pending_response", nodes.finish_pending_response)
    g.add_node("refine_provisional_slot", nodes.refine_provisional_slot)
    g.add_node("commit_full_slot", nodes.commit_full_slot)

    g.add_conditional_edges(START, _route_start, ["initialize", "classify_input"])
    g.add_edge("initialize", "accept_available_pool")
    g.add_edge("accept_available_pool", "route_team_phase")
    g.add_conditional_edges(
        "classify_input", _route_intent, list(dict.fromkeys(_INTENT_ROUTES.values()))
    )
    for handler in (
        "record_constraint",
        "record_rejection",
        "apply_lock",
        "handle_archetype_change",
        "reset_team",
        "restore_superseded",
        "commit_full_slot",
        "record_bootstrap_response",
    ):
        g.add_edge(handler, "route_team_phase")
    g.add_conditional_edges("route_team_phase", _route_team_phase, _PHASE_ROUTES)
    g.add_edge("bootstrap_direction", END)
    g.add_edge("discover_single_locked", END)
    g.add_edge("discover_multi_locked", END)
    g.add_edge("generate_team_review", END)
    g.add_edge("finish_pending_response", END)
    g.add_conditional_edges(
        "refine_provisional_slot",
        _route_after_refine,
        [END, "route_team_phase"],
    )
    return g


def compile_graph(checkpointer=None, *, bootstrap_intake_parser=None):
    """Compile with a caller-owned checkpointer, which may be durable."""
    return build_graph(
        bootstrap_intake_parser=bootstrap_intake_parser
    ).compile(checkpointer=checkpointer)


def compile_cli_graph(*, path=None, bootstrap_intake_parser=None):
    """Open the SQLite checkpointer and compile. Returns ``(graph, saver)``.

    Caller owns ``saver.conn`` for process lifetime.
    """
    from recommender.checkpointer import open_sqlite_checkpointer

    saver = open_sqlite_checkpointer(path)
    graph = compile_graph(
        checkpointer=saver, bootstrap_intake_parser=bootstrap_intake_parser
    )
    return graph, saver