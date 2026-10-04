"""Constant equality, allowlist introspection, and parse/provider/timeout ordering."""

from __future__ import annotations

import pytest
from langchain_core.runnables import RunnableLambda
from pydantic import ValidationError

import recommender.bootstrap as bootstrap_mod
from recommender.bootstrap import (
    BOOTSTRAP_INTAKE_MISSING_PAYLOAD_MSG,
    BOOTSTRAP_INTAKE_PARSE_FAIL_MSG,
    BOOTSTRAP_INTAKE_PROVIDER_FAIL_MSG,
    BOOTSTRAP_INTAKE_TIMEOUT_MSG,
    BOOTSTRAP_INTAKE_UNSUPPORTED_SCHEMA_MSG,
    BootstrapIntakeParseError,
    parse_bootstrap_intake,
)
from recommender.llm_invoke import LLMInvokeTimeout
from recommender.nodes import (
    bootstrap_direction,
    classify_input,
    initialize,
    record_bootstrap_response,
)
from recommender.present_text import (
    BOOTSTRAP_INTAKE_ERROR_ALLOWLIST,
    BOOTSTRAP_PARSER_NOT_CONFIGURED,
    format_turn,
)

VGC_MB = "[Gen 9 Champions] VGC 2026 Reg M-B"


def _state(**overrides):
    raw = {"format_id": VGC_MB, **overrides}
    return {**raw, **initialize(raw)}


def test_all_bootstrap_intake_msg_constants_are_allowlisted():
    names = [
        name
        for name in dir(bootstrap_mod)
        if name.startswith("BOOTSTRAP_INTAKE_") and name.endswith("_MSG")
    ]
    assert names, "expected BOOTSTRAP_INTAKE_*_MSG constants on bootstrap module"
    for name in names:
        value = getattr(bootstrap_mod, name)
        assert isinstance(value, str)
        assert value in BOOTSTRAP_INTAKE_ERROR_ALLOWLIST, name


def test_validation_error_stores_parse_fail_constant():
    parser = RunnableLambda(
        lambda _: {
            "direction_text": "x",
            "anchor_text": None,
            "pool_entries": None,
            "delegated": "not-a-bool",
            "ownership_mode": None,
        }
    )
    state = _state()
    pending = bootstrap_direction(state)["pending_presentation"]
    updates = classify_input(
        {**state, "pending_presentation": pending, "pending_input": "x"},
        bootstrap_intake_parser=parser,
    )
    assert updates["bootstrap_intake_error"] == BOOTSTRAP_INTAKE_PARSE_FAIL_MSG
    rendered = format_turn({**state, **updates}, unmatched=True)
    assert BOOTSTRAP_INTAKE_PARSE_FAIL_MSG in rendered


def test_provider_error_stores_provider_fail_constant():
    parser = RunnableLambda(lambda _: (_ for _ in ()).throw(ConnectionError("down")))
    state = _state()
    pending = bootstrap_direction(state)["pending_presentation"]
    updates = classify_input(
        {**state, "pending_presentation": pending, "pending_input": "x"},
        bootstrap_intake_parser=parser,
    )
    assert updates["bootstrap_intake_error"] == BOOTSTRAP_INTAKE_PROVIDER_FAIL_MSG


def test_timeout_maps_to_timeout_code_and_constant():
    parser = RunnableLambda(
        lambda _: (_ for _ in ()).throw(
            LLMInvokeTimeout("LLM call did not return within 300s")
        )
    )
    with pytest.raises(BootstrapIntakeParseError) as caught:
        parse_bootstrap_intake(parser, "x")
    assert caught.value.args[0] == BOOTSTRAP_INTAKE_TIMEOUT_MSG
    assert caught.value.code == "bootstrap_timeout"

    state = _state()
    pending = bootstrap_direction(state)["pending_presentation"]
    updates = classify_input(
        {**state, "pending_presentation": pending, "pending_input": "x"},
        bootstrap_intake_parser=parser,
    )
    assert updates["bootstrap_intake_error"] == BOOTSTRAP_INTAKE_TIMEOUT_MSG


def test_include_raw_parse_fail_code_and_message():
    parser = RunnableLambda(
        lambda _: {"raw": object(), "parsed": None, "parsing_error": ValueError("bad")}
    )
    with pytest.raises(BootstrapIntakeParseError) as caught:
        parse_bootstrap_intake(parser, "x")
    assert caught.value.code == "bootstrap_parse"
    assert str(caught.value) == BOOTSTRAP_INTAKE_PARSE_FAIL_MSG


def test_validation_error_maps_to_parse_code():
    parser = RunnableLambda(
        lambda _: {
            "direction_text": None,
            "anchor_text": None,
            "pool_entries": "not-a-list",
            "delegated": True,
            "ownership_mode": None,
        }
    )
    with pytest.raises(BootstrapIntakeParseError) as caught:
        parse_bootstrap_intake(parser, "x")
    assert caught.value.code == "bootstrap_parse"
    assert isinstance(caught.value.__cause__, ValidationError)


def test_provider_valueerror_subclass_maps_to_provider_not_parse():
    class ProviderValueError(ValueError):
        pass

    parser = RunnableLambda(
        lambda _: (_ for _ in ()).throw(ProviderValueError("provider said no"))
    )
    with pytest.raises(BootstrapIntakeParseError) as caught:
        parse_bootstrap_intake(parser, "x")
    assert caught.value.code == "bootstrap_provider"
    assert str(caught.value) == BOOTSTRAP_INTAKE_PROVIDER_FAIL_MSG
    assert isinstance(caught.value.__cause__, ProviderValueError)


def test_bootstrap_intake_parse_error_from_invoke_not_rewrapped():
    inner = BootstrapIntakeParseError(
        BOOTSTRAP_INTAKE_PARSE_FAIL_MSG, code="bootstrap_parse"
    )
    parser = RunnableLambda(lambda _: (_ for _ in ()).throw(inner))
    with pytest.raises(BootstrapIntakeParseError) as caught:
        parse_bootstrap_intake(parser, "x")
    assert caught.value is inner
    assert caught.value.code == "bootstrap_parse"


def test_include_raw_bootstrap_intake_parse_error_not_rewrapped_as_valueerror():
    parser = RunnableLambda(
        lambda _: {"raw": object(), "parsed": None, "parsing_error": ValueError("x")}
    )
    with pytest.raises(BootstrapIntakeParseError) as caught:
        parse_bootstrap_intake(parser, "x")
    assert caught.value.code == "bootstrap_parse"
    assert not isinstance(caught.value.__cause__, BootstrapIntakeParseError)


def test_unsupported_schema_and_missing_payload_constants():
    state = _state()
    pending = {
        **bootstrap_direction(state)["pending_presentation"],
        "schema_version": 99,
    }
    updates = classify_input(
        {**state, "pending_presentation": pending, "pending_input": "x"},
        bootstrap_intake_parser=RunnableLambda(lambda _: {}),
    )
    assert updates["bootstrap_intake_error"] == BOOTSTRAP_INTAKE_UNSUPPORTED_SCHEMA_MSG

    missing = record_bootstrap_response({**state, "turn_payload": None})
    assert missing["bootstrap_intake_error"] == BOOTSTRAP_INTAKE_MISSING_PAYLOAD_MSG


def test_legacy_raw_displays_parse_fail_constant():
    rendered = format_turn(
        {"bootstrap_intake_error": "legacy raw with secrets"}, unmatched=False
    )
    assert BOOTSTRAP_INTAKE_PARSE_FAIL_MSG in rendered
    assert "legacy raw" not in rendered


def test_missing_parser_still_uses_fix_hint():
    state = _state()
    pending = bootstrap_direction(state)["pending_presentation"]
    updates = classify_input(
        {**state, "pending_presentation": pending, "pending_input": "x"},
        bootstrap_intake_parser=None,
    )
    assert updates["bootstrap_intake_error"] == BOOTSTRAP_PARSER_NOT_CONFIGURED
