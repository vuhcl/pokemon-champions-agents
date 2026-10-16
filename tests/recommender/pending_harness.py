"""Shared harness for pending-state tests: real graph, stub turn-intent parser, discovery stubbed.

Discovery nodes are replaced by call-counting no-ops while the graph is built, so the
end state of a turn is exactly what the handler (or its absence) left behind.
"""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import MemorySaver

from recommender.graph import build_graph
from recommender.state import (
    Attr,
    PendingSlotIntent,
    ProvisionalSlot,
    Slot,
    TargetRoleDecision,
    empty_slot,
    slot_fingerprint,
)

VGC = "[Gen 9 Champions] VGC 2026 Reg M-B"
DISCOVERY_NODES = (
    "bootstrap_direction",
    "discover_single_locked",
    "discover_multi_locked",
    "generate_team_review",
)
_DECISION = TargetRoleDecision(role_id="rain_setter", source="user_choice")


def provisional(species: str = "Pelipper", *, slot_index: int = 1, fingerprint: str = "fp") -> ProvisionalSlot:
    return ProvisionalSlot(
        schema_version=1, slot_index=slot_index, target_role_decision=_DECISION, species=species,
        ability="Drizzle", item="Damp Rock", moves=("Hurricane", "Weather Ball", "Tailwind", "Wide Guard"),
        nature="Modest", spread=(("hp", 4), ("spa", 252), ("spe", 252)), fingerprint=fingerprint,
    )


def slot_intent(draft: list[Slot], species: str = "Pelipper", slot_index: int = 1) -> PendingSlotIntent:
    return PendingSlotIntent(
        schema_version=1, slot_index=slot_index, species=species, target_role_decision=_DECISION,
        source="need", base_slot_fingerprint=slot_fingerprint(draft[slot_index]),
    )


def pending(kind: str) -> dict | None:
    """A minimal live pending presentation of each kind."""
    base = {"schema_version": 1, "kind": kind, "slot_index": 1}
    if kind == "none":
        return None
    if kind == "candidate_selection":
        return {**base, "options": [{"species": "Farigiraf", "source": "both", "evidence": ()}]}
    if kind == "completion_preference":
        return {**base, "schema_version": 2, "preference_options": ("offense", "defense")}
    if kind == "full_build_confirmation":
        return {**base, "provisional_fingerprint": "fp"}
    if kind == "bootstrap_intake":
        return {**base, "prompt_text": "describe your team"}
    if kind == "confirm_abandon_build":
        return {**base, "queued_turn_intent": "continue", "held_pending": pending("full_build_confirmation")}
    if kind == "spread_reallocation_question":
        return {**base, "reallocation_attempted_spread": {"hp": 4}, "reallocation_diff": 2,
                "reallocation_excluded_stats": (), "reallocation_edited_fields": ("spread",),
                "reallocation_rejection_reason": "x"}
    if kind == "spread_target_question":
        return {**base, "target_question_diffs": ("x",), "target_question_edited_fields": ("spread",),
                "target_question_rejection_reason": "x"}
    if kind == "item_moveset_conflict_question":
        return base
    raise ValueError(kind)


ALL_KINDS = (
    "none", "candidate_selection", "completion_preference", "full_build_confirmation",
    "bootstrap_intake", "confirm_abandon_build", "spread_reallocation_question",
    "spread_target_question", "item_moveset_conflict_question",
)
# Kinds on which a typed lock can reach apply_lock (classify_pending + _BLOCKED_ON_KIND).
LOCK_REACHABLE = ("none", "candidate_selection", "completion_preference")
RESTORE_REACHABLE = ("none", "candidate_selection", "completion_preference", "full_build_confirmation")


def anchor_draft() -> list[Slot]:
    """Slot 0 holds a locked Incineroar; slots 1-5 open."""
    return [Slot(species=Attr("Incineroar", locked=True)), *[empty_slot() for _ in range(5)]]


class Harness:
    def __init__(self, intent: dict, *, replace: dict | None = None):
        self.parser = RunnableLambda(lambda _: dict(intent))
        self.spies: dict[str, MagicMock] = {}
        with ExitStack() as stack:
            for name in DISCOVERY_NODES:
                spy = MagicMock(return_value={})
                self.spies[name] = spy
                stack.enter_context(patch(f"recommender.graph.nodes.{name}", spy))
            for name, repl in (replace or {}).items():
                self.spies[name] = repl
                stack.enter_context(patch(f"recommender.graph.nodes.{name}", repl))
            self.graph = build_graph(turn_intent_parser=self.parser).compile(checkpointer=MemorySaver())
        self.cfg = {"configurable": {"thread_id": f"h-{id(self)}"}}
        self.graph.invoke({"format_id": VGC}, self.cfg)
        for spy in self.spies.values():
            spy.reset_mock()

    def seed(self, **values) -> dict:
        self.graph.update_state(self.cfg, values)
        return self.state()

    def state(self) -> dict:
        return dict(self.graph.get_state(self.cfg).values)

    def turn(self, text: str = "x") -> dict:
        return dict(self.graph.invoke({"pending_input": text}, self.cfg))

    def discovery_calls(self) -> int:
        return sum(self.spies[n].call_count for n in DISCOVERY_NODES)


def changed_keys(before: dict, after: dict) -> set[str]:
    return {k for k in set(before) | set(after) if repr(before.get(k)) != repr(after.get(k))}


PENDING_KEYS = ("pending_presentation", "pending_slot_intent", "provisional_slot", "provisional_refinement")
LOCK_GARCHOMP = {"turn_intent": "lock", "slot_index": 1, "attr": "species", "value": "Garchomp"}
