from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from recommender import nodes
from recommender.state import RecommenderState


def build_graph() -> StateGraph:
    g = StateGraph(RecommenderState)
    g.add_node("initialize", nodes.initialize)
    g.add_node("accept_available_pool", nodes.accept_available_pool)
    g.add_node("propose_team_draft", nodes.propose_team_draft)
    # Linear record_* stubs until steering routing exists (avoids detached-node warn/raise).
    g.add_node("record_constraint", nodes.record_constraint)
    g.add_node("record_rejection", nodes.record_rejection)

    g.add_edge(START, "initialize")
    g.add_edge("initialize", "accept_available_pool")
    g.add_edge("accept_available_pool", "propose_team_draft")
    g.add_edge("propose_team_draft", "record_constraint")
    g.add_edge("record_constraint", "record_rejection")
    g.add_edge("record_rejection", END)
    return g
