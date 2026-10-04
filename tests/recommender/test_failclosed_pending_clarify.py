"""Approach A: model-authored pending_response prose never reaches the user."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from langchain_core.runnables import RunnableLambda

from recommender.nodes import classify_input, classify_pending
from recommender.nodes_classify import clarify_message_from_pending
from recommender.present_text import (
    TEAM_REVIEW_DETAIL_HINT,
    UNMATCHED_REPLY_PREFIX,
    format_turn,
)
from recommender.state import (
    Attr,
    MatchupResult,
    PendingPresentation,
    Slot,
    TargetRoleDecision,
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

PENDING_KINDS = (
    None,
    "candidate_selection",
    "full_build_confirmation",
    "completion_preference",
    "bootstrap_intake",
    "confirm_abandon_build",
    "spread_reallocation_question",
    "spread_target_question",
    "item_moveset_conflict_question",
)


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


# Kinds that do not call _gap_fill today (still parametrized — defense in depth):
# - confirm_abandon_build: nodes_classify.py ~1629-1655 (bare pending_response, no parser)
# - spread_reallocation_question: ~1656-1682 (_reask_reallocation / structured)
# - spread_target_question: ~1683-1713
# - item_moveset_conflict_question: ~1714-1756
# - bootstrap_intake: ~1550-1585 (parse_bootstrap_intake, not turn_intent gap-fill)


@pytest.mark.parametrize("probe,hostile", list(HOSTILE.items()))
@pytest.mark.parametrize("kind", PENDING_KINDS)
def test_hostile_pending_response_never_reaches_format_turn(probe: str, hostile: str, kind: str | None):
    """Idle + every PendingPresentation.kind; assert user-visible output.

    Scope is not narrowed to gap-fill-reachable kinds (approved plan).
    """
    pending = _pending(kind)
    user = "xyzzy-unmatched-probe"
    ti_calls: list[object] = []

    def tracking_hostile(_payload):
        ti_calls.append(_payload)
        return {"turn_intent": "pending_response", "message": hostile}

    if kind == "bootstrap_intake":
        # turn_intent_parser must not be the display path (nodes_classify.py:1550-1585).
        result = classify_pending(
            user,
            pending,
            bootstrap_intake_parser=RunnableLambda(
                lambda _: (_ for _ in ()).throw(RuntimeError("bootstrap boom"))
            ),
            turn_intent_parser=RunnableLambda(tracking_hostile),
        )
        assert ti_calls == [], "bootstrap_intake must not invoke turn_intent_parser"
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

    if unmatched and kind == "full_build_confirmation" and ti_calls:
        assert CLASSIFY_FAIL_USER_MSG in visible
    elif unmatched and kind in (None, "candidate_selection", "completion_preference") and ti_calls:
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
