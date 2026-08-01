from unittest.mock import patch

from langgraph.checkpoint.memory import MemorySaver

from recommender.graph import compile_graph
from recommender.state import Attr, ReasonRef, Slot

VGC_MB = "[Gen 9 Champions] VGC 2026 Reg M-B"


def _graph():
    return compile_graph(checkpointer=MemorySaver())


def _thread(suffix: str):
    return {"configurable": {"thread_id": f"steering-{suffix}"}}


def _seed_first_turn(graph, suffix: str):
    return graph.invoke({"format_id": VGC_MB}, config=_thread(suffix))


def _second_turn(graph, suffix: str, text, classification):
    with patch("recommender.nodes.classify_pending", return_value=classification):
        return graph.invoke({"pending_input": text}, config=_thread(suffix))


def test_first_turn_initializes():
    result = _seed_first_turn(_graph(), "first")
    assert result["game_type"] == "doubles"
    assert result["regulation_mod"] == "champions"
    assert result["picked_team_size"] == 4
    assert len(result["team_draft"]) == 6
    assert all(isinstance(s, Slot) for s in result["team_draft"])
    assert all(not s.role.locked and s.species.value is None for s in result["team_draft"])
    assert isinstance(result["archetype"], Attr)
    assert result["archetype"].value is None
    assert result.get("turn", 0) == 0


def test_lock_turn_with_value():
    graph = _graph()
    suffix = "lock-value"
    state = _seed_first_turn(graph, suffix)
    draft = list(state["team_draft"])
    draft[0] = Slot(species=Attr(value="Garchomp"))
    graph.update_state(_thread(suffix), {"team_draft": draft})

    result = _second_turn(
        graph,
        suffix,
        "lock Garchomp slot 0",
        {
            "turn_intent": "lock",
            "turn_payload": {"slot_index": 0, "attr": "species", "value": "Garchomp"},
        },
    )
    assert result["turn"] == 1
    slot = result["team_draft"][0]
    assert slot.species.value == "Garchomp"
    assert slot.species.locked
    assert slot.species.reason is not None
    assert slot.species.reason.kind == "user_stated"


def test_lock_turn_confirm_without_value():
    graph = _graph()
    suffix = "lock-confirm"
    state = _seed_first_turn(graph, suffix)
    reason = ReasonRef(kind="archetype")
    draft = list(state["team_draft"])
    draft[1] = Slot(species=Attr(value="Kingambit", reason=reason))
    graph.update_state(_thread(suffix), {"team_draft": draft})

    result = _second_turn(
        graph,
        suffix,
        "confirm Kingambit",
        {
            "turn_intent": "lock",
            "turn_payload": {"slot_index": 1, "attr": "species"},
        },
    )
    slot = result["team_draft"][1]
    assert slot.species.value == "Kingambit"
    assert slot.species.locked
    assert slot.species.reason == reason


def test_constraint_turn():
    graph = _graph()
    suffix = "constraint"
    _seed_first_turn(graph, suffix)
    result = _second_turn(
        graph,
        suffix,
        "no duplicate items",
        {
            "turn_intent": "constraint",
            "turn_payload": {
                "type": "hard",
                "predicate": "no duplicate items",
                "scope": "team_wide",
                "groundedness": "mechanically-checkable",
            },
        },
    )
    assert len(result["constraints"]) == 1
    c = result["constraints"][0]
    assert c.type == "hard"
    assert c.predicate == "no duplicate items"
    assert c.scope == "team_wide"
    assert c.groundedness == "mechanically-checkable"
    assert c.source_turn == 1


def test_rejection_unlocked_clears_species():
    graph = _graph()
    suffix = "reject-unlocked"
    state = _seed_first_turn(graph, suffix)
    draft = list(state["team_draft"])
    draft[2] = Slot(species=Attr(value="Tornadus"))
    graph.update_state(_thread(suffix), {"team_draft": draft})

    result = _second_turn(
        graph,
        suffix,
        "reject Tornadus",
        {
            "turn_intent": "rejection",
            "turn_payload": {
                "species": "Tornadus",
                "slot_index": 2,
                "reason": "too fragile",
            },
        },
    )
    assert len(result["rejected"]) == 1
    assert result["rejected"][0]["species"] == "Tornadus"
    assert result["team_draft"][2].species.value is None
    assert not result["team_draft"][2].species.locked


def test_rejection_locked_keeps_species():
    graph = _graph()
    suffix = "reject-locked"
    state = _seed_first_turn(graph, suffix)
    draft = list(state["team_draft"])
    draft[3] = Slot(
        species=Attr(value="Incineroar", locked=True, reason=ReasonRef(kind="user_stated"))
    )
    graph.update_state(_thread(suffix), {"team_draft": draft})

    result = _second_turn(
        graph,
        suffix,
        "reject Incineroar anyway",
        {
            "turn_intent": "rejection",
            "turn_payload": {
                "species": "Incineroar",
                "slot_index": 3,
                "reason": "dislike it",
            },
        },
    )
    assert len(result["rejected"]) == 1
    slot = result["team_draft"][3]
    assert slot.species.value == "Incineroar"
    assert slot.species.locked


def test_reset_wipes_draft_preserves_rejected():
    graph = _graph()
    suffix = "reset"
    state = _seed_first_turn(graph, suffix)
    draft = list(state["team_draft"])
    draft[0] = Slot(species=Attr(value="Garchomp", locked=True))
    graph.update_state(
        _thread(suffix),
        {
            "team_draft": draft,
            "archetype": Attr(value=["offense"], locked=True),
            "constraints": [],
            "rejected": [{"species": "Tornadus", "reason": "nope", "turn": 1}],
        },
    )

    result = _second_turn(
        graph,
        suffix,
        "start over",
        {"turn_intent": "reset", "turn_payload": {}},
    )
    assert all(s.species.value is None for s in result["team_draft"])
    assert result["archetype"].value is None
    assert result["constraints"] == []
    assert len(result["rejected"]) == 1
    assert result["rejected"][0]["species"] == "Tornadus"


def test_checkpointer_persists_across_invokes():
    saver = MemorySaver()
    graph = compile_graph(checkpointer=saver)
    thread = {"configurable": {"thread_id": "persist-test"}}

    first = graph.invoke({"format_id": VGC_MB}, config=thread)
    assert first["game_type"] == "doubles"

    with patch(
        "recommender.nodes.classify_pending",
        return_value={
            "turn_intent": "constraint",
            "turn_payload": {
                "type": "soft",
                "predicate": "prefer tailwind",
                "scope": "team_wide",
                "groundedness": "judgment-only",
            },
        },
    ):
        second = graph.invoke({"pending_input": "want tailwind"}, config=thread)

    assert second["game_type"] == "doubles"
    assert len(second["team_draft"]) == 6
    assert len(second["constraints"]) == 1
    assert second["constraints"][0].predicate == "prefer tailwind"
    assert second["turn"] == 1
