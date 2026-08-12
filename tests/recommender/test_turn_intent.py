"""Gap-fill turn-intent parser: fake-parser unit tests (no live provider)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.runnables import RunnableLambda

from recommender.nodes import classify_pending
from recommender.state import (
    PendingSlotIntent,
    ProvisionalSlot,
    TargetRoleDecision,
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
