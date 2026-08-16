"""Gap-fill turn-intent parser: fake-parser unit tests (no live provider)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.runnables import RunnableLambda

from recommender.nodes import classify_input, classify_pending
from recommender.state import (
    CandidateDiscoveryError,
    PendingSlotIntent,
    ProvisionalSlot,
    TargetRoleDecision,
    TeamReviewResult,
    empty_slot,
)
from recommender.turn_intent import (
    TurnIntentExtraction,
    build_anthropic_turn_intent_parser,
    build_ollama_turn_intent_parser,
    parse_turn_intent,
)

try:
    import langchain_ollama  # noqa: F401

    OLLAMA_INSTALLED = True
except ImportError:
    OLLAMA_INSTALLED = False


def _full_build_pending():
    return {
        "schema_version": 1,
        "kind": "full_build_confirmation",
        "slot_index": 0,
        "provisional_fingerprint": "fp1",
    }


def _clarify_parser(message: str = "What should change about the build?"):
    return RunnableLambda(
        lambda _: {
            "turn_intent": "pending_response",
            "message": message,
        }
    )


def _constraint_parser():
    return RunnableLambda(
        lambda _: {
            "turn_intent": "constraint",
            "type": "hard",
            "predicate": "no duplicate items",
            "scope": "team_wide",
            "groundedness": "mechanically-checkable",
        }
    )


def test_rules_win_yes_on_full_build_without_calling_parser():
    calls: list[object] = []

    def tracking(_payload):
        calls.append(_payload)
        return {"turn_intent": "pending_response", "message": "should not run"}

    result = classify_pending(
        "yes",
        _full_build_pending(),
        turn_intent_parser=RunnableLambda(tracking),
    )
    assert result["turn_intent"] == "full_slot_confirmed"
    assert calls == []


def test_gap_fill_bare_no_on_full_build_keeps_pending():
    parser = _clarify_parser("Which field should change?")
    result = classify_pending(
        "no",
        _full_build_pending(),
        turn_intent_parser=parser,
        gap_fill_context={
            "pending_kind": "full_build_confirmation",
            "pending_context": "full build confirmation for Pelipper",
            "roster_summary": "",
        },
    )
    assert result["turn_intent"] == "pending_response"
    assert result["turn_payload"]["message"] == "Which field should change?"
    assert "pending_presentation" not in result


def test_actionable_gap_fill_with_no_pending():
    result = classify_pending(
        "no duplicate items",
        None,
        turn_intent_parser=_constraint_parser(),
        gap_fill_context={"pending_kind": "none", "pending_context": "", "roster_summary": ""},
    )
    assert result["turn_intent"] == "constraint"
    assert result["turn_payload"]["predicate"] == "no duplicate items"
    assert "pending_presentation" not in result


def test_actionable_gap_fill_clears_provisional_when_pending_open():
    result = classify_pending(
        "no duplicate items",
        _full_build_pending(),
        turn_intent_parser=_constraint_parser(),
        gap_fill_context={
            "pending_kind": "full_build_confirmation",
            "pending_context": "full build confirmation for Pelipper",
            "roster_summary": "",
        },
    )
    assert result["turn_intent"] == "constraint"
    assert result["pending_presentation"] is None
    assert result["pending_slot_intent"] is None
    assert result["provisional_slot"] is None
    assert result["provisional_refinement"] is None


def test_schema_error_pending_response_does_not_call_parser():
    calls: list[object] = []

    def tracking(_payload):
        calls.append(_payload)
        return {"turn_intent": "pending_response", "message": "nope"}

    result = classify_pending(
        "yes",
        {
            "schema_version": 99,
            "kind": "full_build_confirmation",
            "slot_index": 0,
        },
        turn_intent_parser=RunnableLambda(tracking),
    )
    assert result["turn_intent"] == "pending_response"
    assert result["pending_presentation"] is None
    assert "unsupported pending schema" in result["slot_commit_error"]
    assert calls == []


def test_classify_input_defer_forwards_compare_analysis_clear():
    discovery = CandidateDiscoveryError(
        kind="calc_unavailable",
        stage="coverage",
        message="calc down",
        retryable=True,
    )
    review = TeamReviewResult([], [], [])
    result = classify_input(
        {
            "pending_input": "defer",
            "pending_presentation": _full_build_pending(),
            "compare_analysis": "Spe vs bulk",
            "team_draft": [],
            "candidate_discovery_error": discovery,
            "last_team_review": review,
        }  # type: ignore[arg-type]
    )
    assert "compare_analysis" in result
    assert result["compare_analysis"] is None
    assert "candidate_discovery_error" not in result
    assert "last_team_review" not in result


def test_fail_closed_on_malformed_parser_output():
    from recommender.turn_intent import CLASSIFY_FAIL_USER_MSG

    parser = RunnableLambda(lambda _: {"turn_intent": "pending_response"})
    result = classify_pending(
        "xyzzy",
        _full_build_pending(),
        turn_intent_parser=parser,
    )
    assert result["turn_intent"] == "pending_response"
    assert result["turn_payload"]["message"] == CLASSIFY_FAIL_USER_MSG
    assert "OUTPUT_PARSING_FAILURE" not in result["turn_payload"]["message"]
    assert "pending_presentation" not in result


def test_fail_closed_on_parser_raise():
    from recommender.turn_intent import CLASSIFY_FAIL_USER_MSG

    def boom(_payload):
        raise RuntimeError("provider down")

    result = classify_pending(
        "xyzzy",
        _full_build_pending(),
        turn_intent_parser=RunnableLambda(boom),
    )
    assert result["turn_intent"] == "pending_response"
    assert result["turn_payload"]["message"] == CLASSIFY_FAIL_USER_MSG
    assert "RuntimeError" not in result["turn_payload"]["message"]
    assert "provider down" not in result["turn_payload"]["message"]


def test_no_parser_pending_none_still_raises():
    with pytest.raises(NotImplementedError):
        classify_pending("anything", None)


def test_no_parser_unrecognized_fallthrough_is_bare_pending_response():
    result = classify_pending("xyzzy", _full_build_pending())
    assert result == {"turn_intent": "pending_response"}


def test_parse_turn_intent_lock_payload():
    parser = RunnableLambda(
        lambda _: {
            "turn_intent": "lock",
            "slot_index": 0,
            "attr": "species",
            "value": "Pelipper",
        }
    )
    result = parse_turn_intent(parser, user_text="lock Pelipper", had_pending=False)
    assert result["turn_intent"] == "lock"
    assert result["turn_payload"]["attr"] == "species"
    assert result["turn_payload"]["value"] == "Pelipper"


@pytest.mark.skipif(not OLLAMA_INSTALLED, reason="langchain-ollama not installed")
def test_ollama_factory_uses_json_schema_and_include_raw():
    chat = MagicMock()
    chat.with_structured_output.return_value = RunnableLambda(lambda value: value)
    with patch("langchain_ollama.ChatOllama", return_value=chat) as constructor:
        parser = build_ollama_turn_intent_parser("test-model", num_ctx=2048)
    assert parser is not None
    constructor.assert_called_once_with(
        model="test-model", temperature=0, num_ctx=2048
    )
    chat.with_structured_output.assert_called_once_with(
        TurnIntentExtraction,
        method="json_schema",
        include_raw=True,
    )


def test_anthropic_factory_uses_json_schema_and_include_raw():
    chat = MagicMock()
    chat.with_structured_output.return_value = RunnableLambda(lambda value: value)
    fake_mod = MagicMock()
    fake_mod.ChatAnthropic = MagicMock(return_value=chat)
    with patch.dict("sys.modules", {"langchain_anthropic": fake_mod}):
        parser = build_anthropic_turn_intent_parser("claude-test")
    assert parser is not None
    fake_mod.ChatAnthropic.assert_called_once_with(model="claude-test", temperature=0)
    chat.with_structured_output.assert_called_once_with(
        TurnIntentExtraction,
        method="json_schema",
        include_raw=True,
    )


def test_build_gap_fill_context_full_build_uses_species():
    from recommender.nodes import build_gap_fill_context

    decision = TargetRoleDecision(
        role_id="rain_setter",
        source="other",
        evidence=(),
        needed_constraints=(),
        confidence="medium",
        provenance=(),
        producer_name="test",
    )
    intent = PendingSlotIntent(
        schema_version=1,
        slot_index=0,
        species="Pelipper",
        target_role_decision=decision,
        source="bootstrap",
    )
    provisional = ProvisionalSlot(
        schema_version=1,
        slot_index=0,
        target_role_decision=decision,
        species="Pelipper",
        ability="Drizzle",
        item="Damp Rock",
        moves=("Hurricane", "Weather Ball", "Tailwind", "Wide Guard"),
        nature="Modest",
        spread=(("hp", 4), ("spa", 252), ("spe", 252)),
        fingerprint="fp1",
    )
    state = {
        "pending_presentation": _full_build_pending(),
        "pending_slot_intent": intent,
        "provisional_slot": provisional,
        "team_draft": [empty_slot() for _ in range(6)],
    }
    ctx = build_gap_fill_context(state)  # type: ignore[arg-type]
    assert ctx["pending_kind"] == "full_build_confirmation"
    assert "Pelipper" in ctx["pending_context"]


def test_edit_field_only_does_not_clear_pending():
    parser = RunnableLambda(
        lambda _: {
            "turn_intent": "edit",
            "field": "nature",
            "value_text": "Modest",
            "edit_scope": "field_only",
        }
    )
    result = parse_turn_intent(
        parser,
        user_text="run Modest instead, just the nature",
        pending_kind="full_build_confirmation",
        had_pending=True,
    )
    assert result["turn_intent"] == "edit"
    assert result["turn_payload"] == {
        "field": "nature",
        "value": "Modest",
        "scope": "field_only",
    }
    assert "pending_presentation" not in result
    assert "provisional_slot" not in result


def test_edit_maps_moveset_to_moves():
    parser = RunnableLambda(
        lambda _: {
            "turn_intent": "edit",
            "field": "moveset",
            "value_moves": ["A", "B", "C", "D"],
            "edit_scope": "regenerate",
        }
    )
    result = parse_turn_intent(parser, user_text="rebuild with these moves")
    assert result["turn_payload"]["field"] == "moves"
    assert result["turn_payload"]["value"] == ["A", "B", "C", "D"]
    assert result["turn_payload"]["scope"] == "regenerate"


def test_edit_tolerates_null_constraint_object():
    parser = RunnableLambda(
        lambda _: {
            "turn_intent": "edit",
            "field": "nature",
            "value_text": "Modest",
            "edit_scope": "field_only",
            "constraint": {
                "type": None,
                "predicate": None,
                "scope": None,
                "groundedness": None,
            },
        }
    )
    result = parse_turn_intent(parser, user_text="run Modest, just the nature")
    assert result["turn_intent"] == "edit"
    assert result["turn_payload"]["value"] == "Modest"


def test_incomplete_edit_returns_friendly_pending_response():
    from recommender.turn_intent import CLASSIFY_FAIL_USER_MSG

    parser = RunnableLambda(
        lambda _: {
            "turn_intent": "edit",
            "field": "nature",
            "constraint": {
                "type": None,
                "predicate": None,
                "scope": None,
                "groundedness": None,
            },
        }
    )
    result = parse_turn_intent(
        parser,
        user_text="run Modest, just the nature",
        pending_kind="full_build_confirmation",
        had_pending=True,
    )
    assert result["turn_intent"] == "pending_response"
    assert result["turn_payload"]["message"] == CLASSIFY_FAIL_USER_MSG
    assert "OUTPUT_PARSING_FAILURE" not in result["turn_payload"]["message"]
    assert "validation error" not in result["turn_payload"]["message"].casefold()
    assert "pending_presentation" not in result


def test_include_raw_parsing_error_is_friendly():
    from recommender.turn_intent import CLASSIFY_FAIL_USER_MSG

    parser = RunnableLambda(
        lambda _: {
            "raw": object(),
            "parsed": None,
            "parsing_error": "OUTPUT_PARSING_FAILURE\nvalidation error for …",
        }
    )
    result = parse_turn_intent(parser, user_text="run Modest", had_pending=True)
    assert result["turn_intent"] == "pending_response"
    assert result["turn_payload"]["message"] == CLASSIFY_FAIL_USER_MSG
    assert "OUTPUT_PARSING_FAILURE" not in result["turn_payload"]["message"]


def test_edit_rejects_wrong_value_slot():
    from recommender.turn_intent import CLASSIFY_FAIL_USER_MSG

    parser = RunnableLambda(
        lambda _: {
            "turn_intent": "edit",
            "field": "nature",
            "value_moves": ["A", "B", "C", "D"],
            "edit_scope": "field_only",
        }
    )
    result = parse_turn_intent(parser, user_text="Modest")
    assert result["turn_intent"] == "pending_response"
    assert result["turn_payload"]["message"] == CLASSIFY_FAIL_USER_MSG


def test_constraint_still_uses_scope_not_edit_scope():
    result = parse_turn_intent(
        _constraint_parser(),
        user_text="no duplicate items",
        had_pending=False,
    )
    assert result["turn_intent"] == "constraint"
    assert result["turn_payload"]["scope"] == "team_wide"


def test_species_change_is_not_edit_via_rejection():
    parser = RunnableLambda(
        lambda _: {"turn_intent": "rejection", "species": "Pelipper"}
    )
    result = parse_turn_intent(parser, user_text="use Pelipper instead")
    assert result["turn_intent"] == "rejection"


_MISMATCH_MSG = "That action isn't available here."
_CONFIRM_IDS = (
    "spread_nature:default",
    "spread_nature:2",
    "spread_nature:3",
    "spread_nature:4",
)
_CLEAR_KEYS = (
    "pending_presentation",
    "pending_slot_intent",
    "provisional_slot",
    "provisional_refinement",
)


def _spread_option(option_id: str) -> dict:
    return {
        "option_id": option_id,
        "label": option_id,
        "axis": "spread_nature",
        "provenance": "usage_spread",
        "overrides": {"nature": "Modest"},
        "diff_summary": "spread",
        "tradeoff": "tradeoff",
    }


def _confirmation_with_groups():
    return {
        "schema_version": 1,
        "kind": "full_build_confirmation",
        "slot_index": 0,
        "provisional_fingerprint": "fp1",
        "build_option_groups": (
            {
                "axis": "spread_nature",
                "prompt": "Choose spread/nature:",
                "options": tuple(_spread_option(oid) for oid in _CONFIRM_IDS),
            },
        ),
    }


def _candidate_pending():
    return {
        "schema_version": 1,
        "kind": "candidate_selection",
        "slot_index": 0,
        "options": [{"species": "Farigiraf", "source": "bootstrap"}],
    }


def _preference_pending():
    return {
        "schema_version": 2,
        "kind": "completion_preference",
        "preference_options": ("attacker", "support", "balanced"),
    }


def _select_parser(ids: list[str]):
    return RunnableLambda(
        lambda _: {"turn_intent": "select_build_option", "option_ids": ids}
    )


def _compare_parser(ids: list[str]):
    return RunnableLambda(lambda _: {"turn_intent": "compare", "option_ids": ids})


def _edit_parser():
    return RunnableLambda(
        lambda _: {
            "turn_intent": "edit",
            "field": "nature",
            "value_text": "Modest",
            "edit_scope": "field_only",
        }
    )


def _lock_parser():
    return RunnableLambda(
        lambda _: {
            "turn_intent": "lock",
            "slot_index": 0,
            "attr": "species",
            "value": "Farigiraf",
        }
    )


def _assert_screen_kept(result: dict) -> None:
    for key in _CLEAR_KEYS:
        assert key not in result
    assert "slot_commit_error" not in result


def test_unknown_option_id_on_confirmation_is_membership_fail():
    result = classify_pending(
        "I want the faster one",
        _confirmation_with_groups(),
        turn_intent_parser=_select_parser(["2"]),
    )
    assert result["turn_intent"] == "pending_response"
    message = result["turn_payload"]["message"]
    assert message.startswith("Unknown build option id: 2.")
    assert message.endswith("Valid ids: " + ", ".join(_CONFIRM_IDS))
    _assert_screen_kept(result)


def test_real_option_id_on_confirmation_still_selects():
    result = classify_pending(
        "I want the faster one",
        _confirmation_with_groups(),
        turn_intent_parser=_select_parser(["spread_nature:2"]),
    )
    assert result["turn_intent"] == "select_build_option"
    assert result["turn_payload"]["option_ids"] == ("spread_nature:2",)
    _assert_screen_kept(result)


def test_select_build_option_on_candidate_selection_is_mismatch():
    from recommender.present_text import _FOOTERS, format_turn

    pending = _candidate_pending()
    result = classify_pending(
        "lock the species",
        pending,
        turn_intent_parser=_select_parser(["2"]),
    )
    assert result["turn_intent"] == "pending_response"
    assert result["turn_payload"]["message"] == _MISMATCH_MSG
    _assert_screen_kept(result)
    rendered = format_turn(
        {**result, "pending_presentation": pending},
        unmatched=True,
    )
    assert rendered.startswith(_MISMATCH_MSG)
    footer = _FOOTERS["candidate_selection"]
    assert rendered.count(footer) == 1


def test_edit_on_candidate_selection_is_mismatch():
    result = classify_pending(
        "run Modest instead",
        _candidate_pending(),
        turn_intent_parser=_edit_parser(),
    )
    assert result["turn_intent"] == "pending_response"
    assert result["turn_payload"]["message"] == _MISMATCH_MSG
    _assert_screen_kept(result)


def test_edit_on_completion_preference_is_mismatch():
    result = classify_pending(
        "run Modest instead",
        _preference_pending(),
        turn_intent_parser=_edit_parser(),
    )
    assert result["turn_intent"] == "pending_response"
    assert result["turn_payload"]["message"] == _MISMATCH_MSG
    _assert_screen_kept(result)


def test_edit_on_confirmation_still_allowed():
    result = classify_pending(
        "run Modest, just the nature",
        _confirmation_with_groups(),
        turn_intent_parser=_edit_parser(),
    )
    assert result["turn_intent"] == "edit"
    assert result["turn_payload"]["field"] == "nature"
    _assert_screen_kept(result)


def test_compare_fabricated_ids_on_confirmation_is_membership_fail():
    result = classify_pending(
        "compare these for me",
        _confirmation_with_groups(),
        turn_intent_parser=_compare_parser(["default", "2", "3", "4"]),
    )
    assert result["turn_intent"] == "pending_response"
    message = result["turn_payload"]["message"]
    assert message.startswith("Unknown build option ids: default, 2, 3, 4.")
    assert "spread_nature:2" in message
    _assert_screen_kept(result)


def test_compare_real_ids_on_confirmation_still_compares():
    result = classify_pending(
        "walk me through the tradeoffs",
        _confirmation_with_groups(),
        turn_intent_parser=_compare_parser(
            ["spread_nature:default", "spread_nature:2"]
        ),
    )
    assert result["turn_intent"] == "compare"
    assert result["turn_payload"]["option_ids"] == (
        "spread_nature:default",
        "spread_nature:2",
    )
    _assert_screen_kept(result)


def test_lock_on_candidate_selection_still_classifies():
    result = classify_pending(
        "lock the species",
        _candidate_pending(),
        turn_intent_parser=_lock_parser(),
    )
    assert result["turn_intent"] == "lock"
    assert result["turn_payload"]["value"] == "Farigiraf"


def test_reset_and_archetype_change_on_confirmation_still_clear_pending():
    reset = classify_pending(
        "start over",
        _confirmation_with_groups(),
        turn_intent_parser=RunnableLambda(lambda _: {"turn_intent": "reset"}),
    )
    assert reset["turn_intent"] == "reset"
    for key in _CLEAR_KEYS:
        assert reset[key] is None

    changed = classify_pending(
        "switch to trick room",
        _confirmation_with_groups(),
        turn_intent_parser=RunnableLambda(
            lambda _: {
                "turn_intent": "archetype_change",
                "components": ["TrickRoom"],
            }
        ),
    )
    assert changed["turn_intent"] == "archetype_change"
    for key in _CLEAR_KEYS:
        assert changed[key] is None


def test_continue_and_team_review_on_confirmation_still_clear_pending():
    """Cluster B boundary: A-type steering still destroys confirmation pending.

    This gate does not add a confirmation step before continue/team_review.
    """
    for intent in ("continue", "team_review"):
        result = classify_pending(
            "show me the team",
            _confirmation_with_groups(),
            turn_intent_parser=RunnableLambda(
                lambda _, name=intent: {"turn_intent": name}
            ),
        )
        assert result["turn_intent"] == intent
        for key in _CLEAR_KEYS:
            assert result[key] is None


def test_lock_on_confirmation_does_not_clear_pending():
    result = classify_pending(
        "lock this nature",
        _confirmation_with_groups(),
        turn_intent_parser=_lock_parser(),
    )
    assert result["turn_intent"] == "pending_response"
    assert result["turn_payload"]["message"] == _MISMATCH_MSG
    _assert_screen_kept(result)
