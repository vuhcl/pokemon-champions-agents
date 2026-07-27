from __future__ import annotations

from recommender.format import resolve_format
from recommender.state import RecommenderState, empty_slot


def initialize(state: RecommenderState) -> dict:
    format_id = state.get("format_id")
    if not format_id:
        raise ValueError("format_id is required")
    derived = resolve_format(format_id)
    out: dict = {**derived}
    if "team_draft" not in state or not state["team_draft"]:
        out["team_draft"] = [empty_slot(i) for i in range(6)]
    if "rejected" not in state:
        out["rejected"] = []
    if "constraints" not in state:
        out["constraints"] = []
    if "verification_log" not in state:
        out["verification_log"] = []
    if "available_pool" not in state:
        out["available_pool"] = []
    return out


def accept_available_pool(state: RecommenderState) -> dict:
    return {}


def propose_team_draft(state: RecommenderState) -> dict:
    return {}


def record_constraint(state: RecommenderState) -> dict:
    return {}


def record_rejection(state: RecommenderState) -> dict:
    return {}
