from __future__ import annotations

from dataclasses import replace
from typing import Any

from langgraph.types import RunnableConfig

from recommender.coverage import (
    compute_team_coverage,
    detect_spof,
    get_relevant_threats,
)
from recommender.format import resolve_format
from recommender.reconcile import reconcile_on_archetype_change, reconcile_on_sibling_change
from recommender.state import (
    ArchetypeChangePayload,
    Attr,
    Constraint,
    ConstraintPayload,
    LockPayload,
    ReasonRef,
    RecommenderState,
    RejectedEntry,
    RejectionPayload,
    ResetPayload,
    RestorePayload,
    SupersededEntry,
    TeamReviewResult,
    empty_slot,
)

SLOT_ATTRS = ("role", "species", "item", "moveset", "spread")


def classify_pending(text: str) -> dict[str, Any]:
    """Monkeypatch seam for LLM intent classification (ADR-013)."""
    raise NotImplementedError(
        "classify_pending is not wired; monkeypatch in tests or configure ADR-013 LLM"
    )


def initialize(state: RecommenderState) -> dict:
    format_id = state.get("format_id")
    if not format_id:
        raise ValueError("format_id is required")
    derived = resolve_format(format_id)
    out: dict = {**derived}
    if "team_draft" not in state or not state["team_draft"]:
        out["team_draft"] = [empty_slot() for _ in range(6)]
    if "archetype" not in state:
        out["archetype"] = Attr()
    if "rejected" not in state:
        out["rejected"] = []
    if "constraints" not in state:
        out["constraints"] = []
    if "available_pool" not in state:
        out["available_pool"] = []
    if "turn" not in state:
        out["turn"] = 0
    if "superseded" not in state:
        out["superseded"] = []
    if "pending_flags" not in state:
        out["pending_flags"] = []
    return out


def accept_available_pool(state: RecommenderState) -> dict:
    return {}


def classify_input(state: RecommenderState) -> dict:
    text = state.get("pending_input")
    if not text:
        raise ValueError("pending_input is required for subsequent turns")
    result = classify_pending(text)
    return {
        "turn_intent": result["turn_intent"],
        "turn_payload": result.get("turn_payload"),
        "pending_input": None,
        "turn": state.get("turn", 0) + 1,
    }


def apply_lock(state: RecommenderState) -> dict:
    payload: LockPayload = state["turn_payload"]  # type: ignore[assignment]
    slot_index = payload["slot_index"]
    attr_name = payload["attr"]
    draft = list(state["team_draft"])
    slot = draft[slot_index]
    current: Attr[Any] = getattr(slot, attr_name)
    siblings_locked = any(
        getattr(slot, a).locked for a in SLOT_ATTRS if a != attr_name
    )

    if "value" in payload:
        new_attr = Attr(
            value=payload["value"],
            locked=True,
            reason=ReasonRef(kind="user_stated"),
            exempt_from_theme=current.exempt_from_theme,
        )
    else:
        new_attr = replace(current, locked=True)

    slot = replace(slot, **{attr_name: new_attr})
    out: dict = {}

    if siblings_locked:
        components = (state.get("archetype") or Attr()).value
        slot, superseded, pending_flags = reconcile_on_sibling_change(
            slot,
            attr_name,
            slot_index=slot_index,
            turn=state.get("turn", 0),
            components=components,
        )
        if superseded:
            out["superseded"] = [*state.get("superseded", []), *superseded]
        if pending_flags:
            out["pending_flags"] = [*state.get("pending_flags", []), *pending_flags]

    draft[slot_index] = slot
    out["team_draft"] = draft
    return out


def record_constraint(state: RecommenderState) -> dict:
    payload: ConstraintPayload = state["turn_payload"]  # type: ignore[assignment]
    constraint = Constraint(
        type=payload["type"],
        predicate=payload["predicate"],
        source_turn=state.get("turn", 0),
        scope=payload["scope"],
        groundedness=payload["groundedness"],
    )
    return {"constraints": [*state.get("constraints", []), constraint]}


def record_rejection(state: RecommenderState) -> dict:
    payload: RejectionPayload = state["turn_payload"]  # type: ignore[assignment]
    turn = state.get("turn", 0)
    entry = RejectedEntry(
        species=payload["species"],
        reason=payload.get("reason", ""),
        turn=turn,
    )
    out: dict = {"rejected": [*state.get("rejected", []), entry]}

    slot_index = payload.get("slot_index")
    if slot_index is not None:
        draft = list(state["team_draft"])
        slot = draft[slot_index]
        if not slot.species.locked:
            draft[slot_index] = replace(slot, species=Attr())
            out["team_draft"] = draft

    return out


def handle_archetype_change(state: RecommenderState) -> dict:
    payload: ArchetypeChangePayload = state["turn_payload"]  # type: ignore[assignment]
    new_components = payload["components"]
    out: dict = {
        "archetype": Attr(
            value=new_components,
            locked=True,
            reason=ReasonRef(kind="user_stated"),
        )
    }
    out.update(reconcile_on_archetype_change(state, new_components))
    return out


def restore_superseded(state: RecommenderState) -> dict:
    payload: RestorePayload = state["turn_payload"]  # type: ignore[assignment]
    slot_index = payload["slot_index"]
    attr_name = payload["attr"]
    superseded = list(state.get("superseded", []))
    match_idx = None
    for i in range(len(superseded) - 1, -1, -1):
        entry = superseded[i]
        if entry["slot_index"] == slot_index and entry["attr"] == attr_name:
            match_idx = i
            break
    if match_idx is None:
        return {}

    entry: SupersededEntry = superseded.pop(match_idx)
    draft = list(state["team_draft"])
    slot = draft[slot_index]
    restored = Attr(
        value=entry["value"],
        locked=True,
        reason=ReasonRef(kind="user_stated"),
        still_active=True,
    )
    draft[slot_index] = replace(slot, **{attr_name: restored})
    return {"team_draft": draft, "superseded": superseded}


def reset_team(state: RecommenderState) -> dict:
    payload: ResetPayload | None = state.get("turn_payload")  # type: ignore[assignment]
    out: dict = {
        "team_draft": [empty_slot() for _ in range(6)],
        "archetype": Attr(),
        "constraints": [],
    }
    if payload:
        if "archetype" in payload:
            out["archetype"] = Attr(value=payload["archetype"])
        if "constraint" in payload:
            c = payload["constraint"]
            out["constraints"] = [
                Constraint(
                    type=c["type"],
                    predicate=c["predicate"],
                    source_turn=state.get("turn", 0),
                    scope=c["scope"],
                    groundedness=c["groundedness"],
                )
            ]
    return out


def propose_team_draft(state: RecommenderState) -> dict:
    return {}


def generate_team_review(state: RecommenderState, config: RunnableConfig) -> dict:
    from recommender.matchup import bind_matchup_memo_thread

    thread_id = (config.get("configurable") or {}).get("thread_id")
    bind_matchup_memo_thread(thread_id)
    candidates = get_relevant_threats(state)
    specs = [c.spec for c in candidates]
    regulation = state.get("regulation_mod") or "champions"
    draft = state["team_draft"]
    coverage = compute_team_coverage(draft, specs, regulation=regulation)
    spofs = detect_spof(draft, specs, regulation=regulation)
    return {
        "last_team_review": TeamReviewResult(
            threats=candidates,
            coverage=coverage,
            spofs=spofs,
        )
    }
