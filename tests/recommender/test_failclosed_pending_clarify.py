"""Approach A: model-authored pending_response prose never reaches the user."""

from __future__ import annotations

from typing import get_args, get_type_hints
from unittest.mock import patch

import pytest
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import MemorySaver

from recommender.cli import handle_line
from recommender.graph import compile_graph
from recommender.nodes import classify_input, classify_pending
from recommender.nodes_classify import clarify_message_from_pending
from recommender.present_text import (
    TEAM_REVIEW_DETAIL_HINT,
    UNMATCHED_REPLY_PREFIX,
    format_turn,
)
from recommender.session import DEFAULT_FORMAT_ID, thread_config
from recommender.state import (
    Attr,
    MatchupResult,
    PendingPresentation,
    Slot,
    TeamReviewResult,
    ThreatCandidate,
    ThreatCoverageResult,
    empty_slot,
)
from recommender.system_claims import NON_CLAIM_MESSAGES, stamp_system_claim
from recommender.turn_intent import CLASSIFY_FAIL_USER_MSG

HOSTILE = {
    "P1": (
        "I can help with that! Specs Chi-Yu (Choice Specs) has strong STAB Fire "
        "moves that could potentially OHKO Kingambit."
    ),
    "P2": (
        "Which slot would you like to use Miraidon with Scarf on? Also, are you "
        "looking to edit an existing locked slot or add a new Pokémon?"
    ),
    "P3": (
        "I can help with that! Are you looking to add Walking Wake to your team?"
    ),
    "S7": (
        "Yes, you can run two Choice Scarf users on your team - there's no "
        "restriction against duplicate items in standard competitive formats."
    ),
}

_LITERAL_KINDS = get_args(get_type_hints(PendingPresentation)["kind"])
PENDING_KINDS = (None, *_LITERAL_KINDS)

# Explicit gap-fill reachability (classify_pending → _gap_fill / turn_intent_parser).
GAP_FILL_REACHABLE: dict[str | None, bool] = {
    None: True,  # nodes_classify.py:1583-1598
    "candidate_selection": True,  # _classify_candidate_selection_reply → :1552
    "full_build_confirmation": True,  # :1845
    "completion_preference": True,  # unmatched → :1670
    "bootstrap_intake": False,  # :1602-1637
    "confirm_abandon_build": False,  # :1681-1707
    "spread_reallocation_question": False,  # :1708-1734
    "spread_target_question": False,  # :1735-1765
    "item_moveset_conflict_question": False,  # :1766-1808
}

UNREACHABLE_SITES: dict[str, str] = {
    "bootstrap_intake": "recommender/nodes_classify.py:1602-1637",
    "confirm_abandon_build": "recommender/nodes_classify.py:1681-1707",
    "spread_reallocation_question": "recommender/nodes_classify.py:1708-1734",
    "spread_target_question": "recommender/nodes_classify.py:1735-1765",
    "item_moveset_conflict_question": "recommender/nodes_classify.py:1766-1808",
}


def _clarify_parser(message: str):
    return RunnableLambda(
        lambda _: {"turn_intent": "pending_response", "message": message}
    )


def _pending(kind: str | None) -> PendingPresentation | None:
    if kind is None:
        return None
    if kind == "candidate_selection":
        return {
            "schema_version": 1,
            "kind": "candidate_selection",
            "slot_index": 0,
            "options": [{"species": "Incineroar", "source": "threat", "track": "offense"}],
        }
    if kind == "full_build_confirmation":
        return {
            "schema_version": 1,
            "kind": "full_build_confirmation",
            "slot_index": 0,
            "provisional_fingerprint": "fp1",
        }
    if kind == "completion_preference":
        return {
            "schema_version": 2,
            "kind": "completion_preference",
            "preference_options": ("attacker", "support", "balanced"),
        }
    if kind == "bootstrap_intake":
        return {
            "schema_version": 1,
            "kind": "bootstrap_intake",
            "prompt_text": "What direction or anchor would you like to start with?",
        }
    if kind == "confirm_abandon_build":
        return {
            "schema_version": 1,
            "kind": "confirm_abandon_build",
            "queued_turn_intent": "continue",
            "held_pending": {
                "schema_version": 1,
                "kind": "full_build_confirmation",
                "slot_index": 0,
                "provisional_fingerprint": "fp1",
            },
        }
    if kind == "spread_reallocation_question":
        return {
            "schema_version": 1,
            "kind": "spread_reallocation_question",
            "slot_index": 0,
            "reallocation_attempted_spread": {
                "hp": 40,
                "atk": 0,
                "def": 0,
                "spa": 20,
                "spd": 0,
                "spe": 20,
            },
            "reallocation_diff": 14,
            "reallocation_excluded_stats": (),
            "reallocation_edited_fields": ("spa",),
        }
    if kind == "spread_target_question":
        return {
            "schema_version": 1,
            "kind": "spread_target_question",
            "slot_index": 0,
            "target_question_diffs": ("spa", "spe"),
            "target_question_edited_fields": (),
        }
    if kind == "item_moveset_conflict_question":
        return {
            "schema_version": 1,
            "kind": "item_moveset_conflict_question",
            "slot_index": 0,
            "conflict_attempted_item": "Choice Scarf",
            "conflict_previous_item": "Sitrus Berry",
            "conflict_moves": ("Protect",),
            "conflict_move_alternatives": ("Hurricane", "U-turn"),
        }
    raise AssertionError(kind)


def _locked(species: str) -> Slot:
    return Slot(
        role=Attr("bulky_attacker", locked=True),
        species=Attr(species, locked=True),
        ability=Attr("Pressure", locked=True),
        item=Attr("Leftovers", locked=True),
        moveset=Attr(["Protect", "Tackle", "Rest", "Sleep Talk"], locked=True),
        spread=Attr(
            {"hp": 32, "atk": 32, "def": 2, "spa": 0, "spd": 0, "spe": 0},
            locked=True,
        ),
        nature=Attr("Adamant", locked=True),
    )


def _stub_review() -> TeamReviewResult:
    return TeamReviewResult(
        threats=[
            ThreatCandidate(
                ladder_species="Kingambit",
                usage_rank=3,
                form="Kingambit",
                showdown_usage_pct=None,
                showdown_formes=(),
                spec={"species": "Kingambit"},
                build_source="ingame",
            )
        ],
        coverage=[
            ThreatCoverageResult(
                {"species": "Gapmon"},
                MatchupResult("no_answer", "toss-up"),
                [],
                None,
                False,
            )
        ],
        spofs=[],
    )


def test_pending_kinds_match_state_literal():
    literal = get_args(get_type_hints(PendingPresentation)["kind"])
    assert set(PENDING_KINDS) - {None} == set(literal)
    assert "core_resolution" not in literal
    assert set(GAP_FILL_REACHABLE) == set(PENDING_KINDS)
    assert set(UNREACHABLE_SITES) == {k for k, ok in GAP_FILL_REACHABLE.items() if not ok}


@pytest.mark.parametrize("probe,hostile", list(HOSTILE.items()))
@pytest.mark.parametrize("kind", PENDING_KINDS)
def test_hostile_pending_response_never_reaches_format_turn(probe: str, hostile: str, kind: str | None):
    """Idle + every PendingPresentation.kind; assert user-visible output.

    Scope is not narrowed to gap-fill-reachable kinds (approved plan).
    """
    pending = _pending(kind)
    user = "xyzzy-unmatched-probe"
    ti_calls: list[object] = []
    reachable = GAP_FILL_REACHABLE[kind]

    def tracking_hostile(_payload):
        ti_calls.append(_payload)
        return {"turn_intent": "pending_response", "message": hostile}

    if kind == "bootstrap_intake":
        result = classify_pending(
            user,
            pending,
            bootstrap_intake_parser=RunnableLambda(
                lambda _: (_ for _ in ()).throw(RuntimeError("bootstrap boom"))
            ),
            turn_intent_parser=RunnableLambda(tracking_hostile),
        )
        assert ti_calls == [], (
            f"{kind} must not invoke turn_intent_parser "
            f"({UNREACHABLE_SITES[kind]})"
        )
        visible = format_turn(
            {
                "turn_intent": result.get("turn_intent"),
                "turn_payload": result.get("turn_payload"),
                "pending_presentation": result.get("pending_presentation") or pending,
                "bootstrap_intake_error": result.get("bootstrap_intake_error"),
            },
            unmatched=result.get("turn_intent") == "pending_response",
        )
        assert hostile not in visible
        return

    result = classify_pending(
        user,
        pending,
        turn_intent_parser=RunnableLambda(tracking_hostile),
        gap_fill_context={
            "pending_kind": str(kind or "none"),
            "pending_context": "",
            "roster_summary": "",
        },
    )
    if reachable:
        assert ti_calls, f"{kind!r} should reach _gap_fill / turn_intent_parser"
    else:
        assert ti_calls == [], (
            f"{kind!r} must not invoke turn_intent_parser "
            f"({UNREACHABLE_SITES[str(kind)]})"
        )

    state = {
        "turn_intent": result.get("turn_intent"),
        "turn_payload": result.get("turn_payload"),
        "pending_presentation": result.get("pending_presentation", pending),
        "team_draft": [],
    }
    unmatched = state["turn_intent"] == "pending_response"
    visible = format_turn(state, unmatched=unmatched)

    assert hostile not in visible
    for fragment in (
        "Chi-Yu",
        "Miraidon",
        "Walking Wake",
        "no restriction against duplicate",
    ):
        if fragment in hostile:
            assert fragment not in visible

    if reachable:
        assert unmatched, f"{kind!r} reachable hostile path should stay pending_response"
        if kind == "full_build_confirmation":
            assert CLASSIFY_FAIL_USER_MSG in visible
        else:
            assert UNMATCHED_REPLY_PREFIX in visible.split("\n")[0]


def test_hostile_idle_p1_via_classify_input_no_claim_stamp():
    hostile = HOSTILE["P1"]
    state = {
        "format_id": "[Gen 9 Champions] VGC 2026 Reg M-C",
        "team_draft": [empty_slot() for _ in range(6)],
        "constraints": [],
        "rejected": [],
        "pending_input": "does Specs Chi-Yu OHKO Kingambit",
        "pending_presentation": None,
        "turn": 0,
    }
    out = classify_input(
        state,  # type: ignore[arg-type]
        turn_intent_parser=_clarify_parser(hostile),
    )
    assert out["turn_intent"] == "pending_response"
    msg = (out.get("turn_payload") or {}).get("message")
    assert msg == UNMATCHED_REPLY_PREFIX
    assert hostile not in str(msg)
    assert out.get("last_system_claim") is None
    visible = format_turn({**state, **out}, unmatched=True)
    assert "Chi-Yu" not in visible
    assert visible.startswith(UNMATCHED_REPLY_PREFIX)


def test_template_with_species_body_does_not_stamp_false_claim():
    """Candidate body may name Incineroar; unmatched template must not stamp a claim."""
    pending = _pending("candidate_selection")
    result = classify_pending(
        "xyzzy",
        pending,
        turn_intent_parser=_clarify_parser(HOSTILE["S7"]),
        gap_fill_context={
            "pending_kind": "candidate_selection",
            "pending_context": "",
            "roster_summary": "",
        },
    )
    msg = (result.get("turn_payload") or {}).get("message")
    assert msg == UNMATCHED_REPLY_PREFIX
    assert msg in NON_CLAIM_MESSAGES
    claim = stamp_system_claim(
        message=str(msg),
        originating_user_text="xyzzy",
        turn=1,
    )
    assert claim is None
    visible = format_turn(
        {
            "turn_payload": result.get("turn_payload"),
            "pending_presentation": pending,
            "team_draft": [],
        },
        unmatched=True,
    )
    assert "Incineroar" in visible  # body formatter
    assert HOSTILE["S7"] not in visible
    assert stamp_system_claim(
        message=UNMATCHED_REPLY_PREFIX,
        originating_user_text="xyzzy",
        turn=1,
    ) is None


def test_complete_phase_unmatched_keeps_roster_and_review():
    draft = [
        _locked(n)
        for n in (
            "Archaludon",
            "Pelipper",
            "Incineroar",
            "Sinistcha",
            "Meowstic",
            "Farigiraf",
        )
    ]
    review = _stub_review()
    result = classify_pending(
        "asdf-complete-unmatched",
        None,
        turn_intent_parser=_clarify_parser(HOSTILE["P1"]),
        gap_fill_context={"pending_kind": "none", "pending_context": "", "roster_summary": ""},
    )
    state = {
        "team_draft": draft,
        "pending_presentation": None,
        "last_team_review": review,
        "turn_intent": result["turn_intent"],
        "turn_payload": result["turn_payload"],
        "candidate_discovery_error": None,
    }
    visible = format_turn(state, unmatched=True)
    assert visible.startswith(UNMATCHED_REPLY_PREFIX)
    assert "Archaludon" in visible
    assert "Gapmon" in visible or TEAM_REVIEW_DETAIL_HINT in visible
    assert "wait for a prompt" not in visible
    assert "Chi-Yu" not in visible
    assert HOSTILE["P1"] not in visible


def test_clarify_message_from_pending_table():
    assert clarify_message_from_pending(None) == UNMATCHED_REPLY_PREFIX
    assert (
        clarify_message_from_pending({"kind": "full_build_confirmation"})
        == CLASSIFY_FAIL_USER_MSG
    )
    assert clarify_message_from_pending({"kind": "candidate_selection"}) == (
        UNMATCHED_REPLY_PREFIX
    )


def test_new_templates_in_non_claim_messages():
    assert UNMATCHED_REPLY_PREFIX in NON_CLAIM_MESSAGES
    assert CLASSIFY_FAIL_USER_MSG in NON_CLAIM_MESSAGES


@pytest.mark.parametrize(
    "hostile",
    [
        "Unknown build option id foo. Chi-Yu is legal and Choice Specs are fine.",
        "Unknown build option ids foo. Chi-Yu is legal and Choice Specs are fine.",
    ],
    ids=["unknown_id", "unknown_ids"],
)
def test_unknown_build_option_prefix_hostile_replaced(hostile: str):
    """Prefix allowlist must not let model prose through after a gate-like opener."""
    result = classify_pending(
        "xyzzy-unknown-option-prefix",
        None,
        turn_intent_parser=_clarify_parser(hostile),
        gap_fill_context={"pending_kind": "none", "pending_context": "", "roster_summary": ""},
    )
    msg = (result.get("turn_payload") or {}).get("message")
    assert msg == UNMATCHED_REPLY_PREFIX
    visible = format_turn(
        {
            "turn_intent": result.get("turn_intent"),
            "turn_payload": result.get("turn_payload"),
            "pending_presentation": None,
            "team_draft": [],
        },
        unmatched=True,
    )
    assert visible.startswith(UNMATCHED_REPLY_PREFIX)
    assert hostile not in visible
    assert "Chi-Yu" not in visible
    assert "Choice Specs" not in visible
    assert "legal" not in visible


def test_handle_line_idle_hostile_p1_failclosed():
    hostile = HOSTILE["P1"]
    graph = compile_graph(
        checkpointer=MemorySaver(),
        turn_intent_parser=_clarify_parser(hostile),
    )
    thread_id = "failclosed-idle-p1"
    config = thread_config(thread_id)
    graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config)
    graph.update_state(config, {"pending_presentation": None})
    state = graph.get_state(config).values
    _, _, _, output, should_exit = handle_line(
        graph,
        config,
        state,
        "does Specs Chi-Yu OHKO Kingambit",
        format_id=DEFAULT_FORMAT_ID,
        thread_id=thread_id,
    )
    assert should_exit is False
    assert output is not None
    assert output.startswith(UNMATCHED_REPLY_PREFIX)
    assert hostile not in output
    assert "Chi-Yu" not in output
    assert "Choice Specs" not in output


def test_handle_line_complete_phase_hostile_p1_failclosed():
    hostile = HOSTILE["P1"]
    draft = [
        _locked(n)
        for n in (
            "Archaludon",
            "Pelipper",
            "Incineroar",
            "Sinistcha",
            "Meowstic",
            "Farigiraf",
        )
    ]
    review = _stub_review()
    graph = compile_graph(
        checkpointer=MemorySaver(),
        turn_intent_parser=_clarify_parser(hostile),
    )
    thread_id = "failclosed-complete-p1"
    config = thread_config(thread_id)
    graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config)
    graph.update_state(
        config,
        {
            "pending_presentation": None,
            "team_draft": draft,
            "last_team_review": review,
            "bootstrap_intake_complete": True,
        },
    )
    state = graph.get_state(config).values
    with patch("recommender.nodes._compute_team_review", return_value=review):
        _, _, _, output, should_exit = handle_line(
            graph,
            config,
            state,
            "asdf-complete-unmatched",
            format_id=DEFAULT_FORMAT_ID,
            thread_id=thread_id,
        )
    assert should_exit is False
    assert output is not None
    assert output.startswith(UNMATCHED_REPLY_PREFIX)
    assert "Archaludon" in output
    assert "Gapmon" in output or TEAM_REVIEW_DETAIL_HINT in output
    assert hostile not in output
    assert "Chi-Yu" not in output
