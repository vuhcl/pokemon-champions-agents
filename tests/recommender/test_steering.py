from unittest.mock import patch

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END

from recommender.graph import _route_after_refine, compile_graph
from recommender.nodes import classify_input, classify_pending
from recommender.state import (
    Attr,
    CandidateEvidence,
    PendingSlotIntent,
    ReasonRef,
    Slot,
    TargetRoleDecision,
    UnresolvedSlotRefinement,
    all_locked,
    empty_slot,
)

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


def _seed_pending_presentation(graph, suffix: str):
    state = _seed_first_turn(graph, suffix)
    pending = {
        "schema_version": 1,
        "kind": "candidate_selection",
        "slot_index": 1,
        "options": [
            {
                "species": "Farigiraf",
                "source": "both",
                "evidence": (
                    CandidateEvidence(
                        "compendium_backed",
                        "medium",
                        "role_category_evidence",
                        ("role:trick_room_setter",),
                    ),
                ),
                "target_role_decision": TargetRoleDecision(
                    role_id="trick_room_setter",
                    source="support_need",
                    evidence=("trick_room",),
                ),
            },
            {"species": "Incineroar", "source": "threat"},
        ],
    }
    graph.update_state(_thread(suffix), {"pending_presentation": pending})
    return state, pending


def test_completion_preference_schema_v2_updates_state_key():
    result = classify_input(
        {
            "pending_input": "support",
            "pending_presentation": {
                "schema_version": 2,
                "kind": "completion_preference",
                "preference_options": ("attacker", "support", "balanced"),
            },
            "team_draft": [],
        }  # type: ignore[arg-type]
    )
    assert result["turn_intent"] == "continue"
    assert result["team_completion_preference"] == "support"
    assert result["pending_presentation"] is None


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


def test_pending_presentation_second_option_creates_intent_across_turn_boundary():
    graph = _graph()
    suffix = "pending-second"
    _seed_pending_presentation(graph, suffix)

    result = graph.invoke(
        {"pending_input": "the second one"}, config=_thread(suffix)
    )

    assert result["team_draft"][1].species.value is None
    assert result["pending_slot_intent"].species == "Incineroar"
    assert result["pending_slot_intent"].evidence == ()
    # Threat-only option had no role on the presentation; refine recovers via kit.
    assert result["provisional_slot"] is not None
    assert result["provisional_slot"].species == "Incineroar"
    assert result["pending_presentation"]["kind"] == "full_build_confirmation"


@pytest.mark.parametrize("reply", ["Incineroar", "option 2"])
def test_pending_presentation_explicit_selection(reply: str):
    graph = _graph()
    suffix = f"pending-explicit-{reply}"
    _seed_pending_presentation(graph, suffix)

    result = graph.invoke({"pending_input": reply}, config=_thread(suffix))

    assert result["team_draft"][1].species.value is None
    assert result["pending_slot_intent"].species == "Incineroar"
    assert result["pending_presentation"]["kind"] == "full_build_confirmation"


def test_pending_presentation_affirmative_selects_default_without_locking():
    graph = _graph()
    suffix = "pending-default"
    _seed_pending_presentation(graph, suffix)

    result = graph.invoke({"pending_input": "yes"}, config=_thread(suffix))

    assert result["team_draft"][1].species.value is None
    assert result["pending_slot_intent"].species == "Farigiraf"
    assert result["pending_slot_intent"].evidence[0].basis == "compendium_backed"


def test_route_after_refine_sends_unresolved_back_to_team_phase():
    assert _route_after_refine({"provisional_slot": None}) == "route_team_phase"
    assert _route_after_refine({}) == "route_team_phase"
    assert _route_after_refine({"provisional_slot": object()}) is END


def test_unresolved_refine_rediscovers_pending_presentation():
    """Failed refine must not end the turn with no prompt (3c dead-end).

    UnresolvedSlotRefinement clears provisional_slot → `_route_after_refine` →
    `route_team_phase` → phase discovery, which must install a new pending.
    """

    spread = {"hp": 32, "atk": 32, "def": 2, "spa": 0, "spd": 0, "spe": 0}
    locked = Slot(
        role=Attr("standard_physical_attacker", locked=True),
        species=Attr("Kingambit", locked=True),
        ability=Attr("Defiant", locked=True),
        item=Attr("Black Glasses", locked=True),
        moveset=Attr(
            ["Kowtow Cleave", "Sucker Punch", "Iron Head", "Protect"], locked=True
        ),
        spread=Attr(dict(spread), locked=True),
        nature=Attr("Adamant", locked=True),
    )
    pending = {
        "schema_version": 1,
        "kind": "candidate_selection",
        "slot_index": 1,
        "options": [
            {
                "species": "Tsareena",
                "source": "need",
                "evidence": (
                    CandidateEvidence(
                        "mechanical_only",
                        "low",
                        "narrow_candidates_for_move",
                        ("need:screens",),
                    ),
                ),
                "target_role_decision": TargetRoleDecision(
                    role_id="screens_support",
                    source="other",
                    evidence=("kit_role:screens_support",),
                    needed_constraints=("role:screens_support",),
                    confidence="medium",
                    producer_name="slot_fill_kit_role_policy",
                ),
            }
        ],
    }
    rediscovered = {
        "coverage": [],
        "spofs": [],
        "shared_teammates": None,
        "last_team_review": None,
        "candidate_discovery_error": None,
        "pending_presentation": {
            "schema_version": 1,
            "kind": "candidate_selection",
            "slot_index": 1,
            "options": [{"species": "Sinistcha", "source": "need"}],
        },
    }
    unresolved = UnresolvedSlotRefinement(
        schema_version=1,
        intent=PendingSlotIntent(
            schema_version=1,
            slot_index=1,
            species="Tsareena",
            target_role_decision=None,
            source="need",
        ),
        unresolved_fields=("moves",),
        reason="incomplete_build",
    )

    with patch(
        "recommender.nodes.discover_single_locked", return_value=rediscovered
    ) as discover:
        graph = compile_graph(checkpointer=MemorySaver())
        suffix = "refine-rediscover"
        config = _thread(suffix)
        graph.invoke({"format_id": VGC_MB}, config=config)
        graph.update_state(
            config,
            {
                "team_draft": [locked, *[empty_slot() for _ in range(5)]],
                "pending_presentation": pending,
            },
        )
        with patch(
            "recommender.slot_fill.build_provisional_slot", return_value=unresolved
        ):
            result = graph.invoke({"pending_input": "1"}, config=config)

    discover.assert_called_once()
    assert result["provisional_slot"] is None
    assert isinstance(result["provisional_refinement"], UnresolvedSlotRefinement)
    assert result["provisional_refinement"].reason == "incomplete_build"
    assert result["slot_commit_error"] is not None
    assert "Tsareena" in result["slot_commit_error"]
    assert result["pending_presentation"] is not None
    assert result["pending_presentation"]["kind"] == "candidate_selection"
    assert result["pending_presentation"]["options"][0]["species"] == "Sinistcha"


def test_unresolved_target_role_refine_rediscovers_pending_presentation():
    """3c is reason-agnostic: kit-unresolved beneficiaries rediscover, not END.

    Real ``build_provisional_slot`` (not mocked). Untruncated usage now maps
    Qwilfish to fast_pivot; stub kit fallback so this still covers Swift Swim
    without a TargetRoleId (the Sun/Sand/Snow unresolvable-hit path).
    """
    spread = {"hp": 32, "atk": 32, "def": 2, "spa": 0, "spd": 0, "spe": 0}
    locked = Slot(
        role=Attr("rain_setter", locked=True),
        species=Attr("Pelipper", locked=True),
        ability=Attr("Drizzle", locked=True),
        item=Attr("Damp Rock", locked=True),
        moveset=Attr(
            ["Hurricane", "Weather Ball", "Tailwind", "Protect"], locked=True
        ),
        spread=Attr(dict(spread), locked=True),
        nature=Attr("Modest", locked=True),
    )
    pending = {
        "schema_version": 1,
        "kind": "candidate_selection",
        "slot_index": 1,
        "options": [
            {
                "species": "Qwilfish",
                "source": "need",
                "evidence": (
                    CandidateEvidence(
                        "mechanical_only",
                        "low",
                        "resolve_condition_beneficiaries",
                        ("need:condition_beneficiary", "condition:Rain"),
                    ),
                ),
            }
        ],
    }
    rediscovered = {
        "coverage": [],
        "spofs": [],
        "shared_teammates": None,
        "last_team_review": None,
        "candidate_discovery_error": None,
        "pending_presentation": {
            "schema_version": 1,
            "kind": "candidate_selection",
            "slot_index": 1,
            "options": [{"species": "Basculegion", "source": "need"}],
        },
    }

    with patch(
        "recommender.nodes.discover_single_locked", return_value=rediscovered
    ) as discover, patch(
        "recommender.slot_fill._kit_fallback_target_role", return_value=None
    ):
        graph = compile_graph(checkpointer=MemorySaver())
        suffix = "refine-unresolved-target-role"
        config = _thread(suffix)
        graph.invoke({"format_id": VGC_MB}, config=config)
        graph.update_state(
            config,
            {
                "team_draft": [locked, *[empty_slot() for _ in range(5)]],
                "pending_presentation": pending,
            },
        )
        result = graph.invoke({"pending_input": "1"}, config=config)

    discover.assert_called_once()
    assert _route_after_refine(
        {"provisional_slot": None, "provisional_refinement": result["provisional_refinement"]}
    ) == "route_team_phase"
    assert result["provisional_slot"] is None
    assert isinstance(result["provisional_refinement"], UnresolvedSlotRefinement)
    assert result["provisional_refinement"].reason == "unresolved_target_role"
    assert result["provisional_refinement"].unresolved_fields == ("target_role",)
    assert result["slot_commit_error"] is not None
    assert "Qwilfish" in result["slot_commit_error"]
    assert result["pending_presentation"] is not None
    assert result["pending_presentation"]["kind"] == "candidate_selection"
    assert result["pending_presentation"]["options"][0]["species"] == "Basculegion"


def test_full_build_confirmation_atomically_locks_slot():
    graph = _graph()
    suffix = "pending-full-confirm"
    _seed_pending_presentation(graph, suffix)
    moves = ["Psychic", "Hyper Voice", "Trick Room", "Protect"]
    spread = {"hp": 32, "atk": 0, "def": 0, "spa": 32, "spd": 2, "spe": 0}
    with (
        patch(
            "recommender.propose.featured_or_common_set",
            return_value={
                "species": "Farigiraf",
                "ability": "Armor Tail",
                "moves": moves,
                "item": "Sitrus Berry",
                "nature": "Modest",
            },
        ),
        patch(
            "recommender.propose.get_resolved_build",
            return_value={"spread": spread, "source_tier": "test", "verified": True},
        ),
    ):
        selected = graph.invoke({"pending_input": "yes"}, config=_thread(suffix))

    assert selected["pending_presentation"]["kind"] == "full_build_confirmation"
    assert selected["provisional_slot"].target_role_decision.role_id == "trick_room_setter"

    with patch(
        "recommender.slot_fill.build_anchored_slot_fill_context"
    ) as next_slot_discovery:
        next_slot_discovery.return_value.context = None
        committed = graph.invoke({"pending_input": "yes"}, config=_thread(suffix))
    slot = committed["team_draft"][1]
    assert all_locked(slot)
    assert slot.role.value == "trick_room_setter"
    assert slot.species.value == "Farigiraf"
    assert slot.ability.value == "Armor Tail"
    assert slot.moveset.value == moves
    assert committed["pending_slot_intent"] is None
    assert committed["provisional_slot"] is None


def test_pending_presentation_defer_clears_without_locking():
    graph = _graph()
    suffix = "pending-defer"
    before, _pending = _seed_pending_presentation(graph, suffix)

    result = graph.invoke({"pending_input": "not now"}, config=_thread(suffix))

    assert result["pending_presentation"] is None
    assert result["turn_intent"] == "deferred"
    assert result["team_draft"] == before["team_draft"]


@pytest.mark.parametrize(
    "pending",
    [
        {
            "schema_version": 1,
            "kind": "candidate_selection",
            "slot_index": 1,
            "options": [{"species": "Farigiraf", "source": "both"}],
        },
        {
            "schema_version": 2,
            "kind": "completion_preference",
            "preference_options": ("attacker", "support", "balanced"),
        },
        {"schema_version": 1, "kind": "full_build_confirmation"},
    ],
)
def test_classify_pending_defer_emits_deferred(pending):
    result = classify_pending("defer", pending)
    assert result["turn_intent"] == "deferred"
    assert result["pending_presentation"] is None
    if pending["kind"] == "full_build_confirmation":
        assert result["pending_slot_intent"] is None
        assert result["provisional_slot"] is None
        assert result["provisional_refinement"] is None


def test_classify_pending_unmatched_keeps_pending_out_of_update():
    pending = {
        "schema_version": 1,
        "kind": "candidate_selection",
        "slot_index": 1,
        "options": [{"species": "Farigiraf", "source": "both"}],
    }
    result = classify_pending("xyzzy", pending)
    assert result["turn_intent"] == "pending_response"
    assert "pending_presentation" not in result


@pytest.mark.parametrize(
    "reply", ["none", "option 9", "yes, second one", "surprise me"]
)
def test_pending_presentation_unresolved_reply_is_safe(reply: str):
    graph = _graph()
    suffix = f"pending-unresolved-{reply}"
    before, pending = _seed_pending_presentation(graph, suffix)

    result = graph.invoke({"pending_input": reply}, config=_thread(suffix))

    assert result["pending_presentation"]["kind"] == pending["kind"]
    assert [
        option["species"] for option in result["pending_presentation"]["options"]
    ] == [option["species"] for option in pending["options"]]
    assert result["team_draft"] == before["team_draft"]


def test_unknown_pending_schema_is_cleared_without_mutating_team():
    graph = _graph()
    suffix = "pending-unknown-schema"
    before, pending = _seed_pending_presentation(graph, suffix)
    graph.update_state(
        _thread(suffix), {"pending_presentation": {**pending, "schema_version": 99}}
    )
    result = graph.invoke({"pending_input": "yes"}, config=_thread(suffix))
    assert result["pending_presentation"] is None
    assert result["team_draft"] == before["team_draft"]
    assert "unsupported pending schema" in result["slot_commit_error"]


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
