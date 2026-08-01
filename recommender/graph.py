from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
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
    "continue": "propose_team_draft",
    "team_review": "generate_team_review",
}


def _route_start(state: RecommenderState) -> str:
    if not state.get("game_type"):
        return "initialize"
    return "classify_input"


def _route_intent(state: RecommenderState) -> str:
    return _INTENT_ROUTES.get(state.get("turn_intent") or "", "propose_team_draft")


def build_graph() -> StateGraph:
    g = StateGraph(RecommenderState)
    g.add_node("initialize", nodes.initialize)
    g.add_node("accept_available_pool", nodes.accept_available_pool)
    g.add_node("classify_input", nodes.classify_input)
    g.add_node("apply_lock", nodes.apply_lock)
    g.add_node("record_constraint", nodes.record_constraint)
    g.add_node("record_rejection", nodes.record_rejection)
    g.add_node("handle_archetype_change", nodes.handle_archetype_change)
    g.add_node("reset_team", nodes.reset_team)
    g.add_node("restore_superseded", nodes.restore_superseded)
    g.add_node("propose_team_draft", nodes.propose_team_draft)
    g.add_node("generate_team_review", nodes.generate_team_review)

    g.add_conditional_edges(START, _route_start, ["initialize", "classify_input"])
    g.add_edge("initialize", "accept_available_pool")
    g.add_edge("accept_available_pool", "propose_team_draft")
    g.add_conditional_edges("classify_input", _route_intent, list(_INTENT_ROUTES.values()))
    for handler in (
        "record_constraint",
        "record_rejection",
        "apply_lock",
        "handle_archetype_change",
        "reset_team",
        "restore_superseded",
    ):
        g.add_edge(handler, "propose_team_draft")
    g.add_edge("propose_team_draft", END)
    g.add_edge("generate_team_review", END)
    return g


def compile_graph(checkpointer=None):
    """Compile with optional checkpointer (MemorySaver for session scope)."""
    return build_graph().compile(checkpointer=checkpointer)
