"""Hostile redaction: bootstrap_intake_error must not surface model/exception text."""

from __future__ import annotations

from langchain_core.exceptions import OutputParserException
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import MemorySaver

from recommender.cli import handle_line
from recommender.graph import compile_graph
from recommender.nodes import bootstrap_direction, classify_input, initialize
from recommender.present_text import format_turn
from recommender.session import DEFAULT_FORMAT_ID, thread_config

HOSTILE = "Chi-Yu is legal and Choice Specs are fine"
URL = "https://api.example-llm.invalid:8443/v1/chat"
_LEAK_MARKERS = (HOSTILE, URL, "OUTPUT_PARSING_FAILURE", "structured extraction failed")

VGC_MB = "[Gen 9 Champions] VGC 2026 Reg M-B"


def _assert_no_leak(text: str) -> None:
    for marker in _LEAK_MARKERS:
        assert marker not in text, f"leaked {marker!r} in {text!r}"


def _bootstrap_pending_state(**overrides):
    raw = {"format_id": VGC_MB, **overrides}
    state = {**raw, **initialize(raw)}
    pending = bootstrap_direction(state)["pending_presentation"]
    return {**state, "pending_presentation": pending}


def _classify_with(parser):
    state = _bootstrap_pending_state()
    updates = classify_input(
        {**state, "pending_input": "anything"},
        bootstrap_intake_parser=parser,
    )
    after = {**state, **updates}
    rendered = format_turn(after, unmatched=True)
    return after, rendered


def test_hostile_validation_error_redacted_from_format_turn_and_state():
    parser = RunnableLambda(
        lambda _: {
            "direction_text": HOSTILE,
            "anchor_text": None,
            "pool_entries": None,
            "delegated": HOSTILE,
            "ownership_mode": None,
        }
    )
    after, rendered = _classify_with(parser)
    _assert_no_leak(rendered)
    _assert_no_leak(str(after.get("bootstrap_intake_error") or ""))
    assert after.get("bootstrap_intake_error")


def test_hostile_output_parser_exception_redacted_from_format_turn_and_state():
    ope = OutputParserException(
        f"Failed to parse BootstrapExtraction from completion {HOSTILE}",
        llm_output=f'{{"direction_text": "{HOSTILE}"}}',
    )
    parser = RunnableLambda(
        lambda _: {"raw": object(), "parsed": None, "parsing_error": ope}
    )
    after, rendered = _classify_with(parser)
    _assert_no_leak(rendered)
    _assert_no_leak(str(after.get("bootstrap_intake_error") or ""))
    assert after.get("bootstrap_intake_error")


def test_hostile_provider_url_redacted_from_format_turn_and_state():
    def _boom(_payload):
        raise ConnectionError(f"Failed to connect to {URL}")

    after, rendered = _classify_with(RunnableLambda(_boom))
    _assert_no_leak(rendered)
    _assert_no_leak(str(after.get("bootstrap_intake_error") or ""))
    assert after.get("bootstrap_intake_error")


def test_hostile_validation_error_redacted_through_handle_line():
    parser = RunnableLambda(
        lambda _: {
            "direction_text": HOSTILE,
            "anchor_text": None,
            "pool_entries": None,
            "delegated": HOSTILE,
            "ownership_mode": None,
        }
    )
    graph = compile_graph(MemorySaver(), bootstrap_intake_parser=parser)
    config = thread_config("bootstrap-hostile-validation")
    state = graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config)
    assert state["pending_presentation"]["kind"] == "bootstrap_intake"
    new_state, _, _, output, _ = handle_line(
        graph,
        config,
        state,
        "Rain with Chi-Yu",
        format_id=DEFAULT_FORMAT_ID,
        thread_id="bootstrap-hostile-validation",
    )
    _assert_no_leak(output)
    _assert_no_leak(str(new_state.get("bootstrap_intake_error") or ""))
    assert new_state.get("bootstrap_intake_error")


def test_hostile_provider_url_redacted_through_handle_line():
    def _boom(_payload):
        raise ConnectionError(f"Failed to connect to {URL}")

    graph = compile_graph(MemorySaver(), bootstrap_intake_parser=RunnableLambda(_boom))
    config = thread_config("bootstrap-hostile-provider")
    state = graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config)
    new_state, _, _, output, _ = handle_line(
        graph,
        config,
        state,
        "anything",
        format_id=DEFAULT_FORMAT_ID,
        thread_id="bootstrap-hostile-provider",
    )
    _assert_no_leak(output)
    _assert_no_leak(str(new_state.get("bootstrap_intake_error") or ""))
    assert new_state.get("bootstrap_intake_error")


def test_legacy_raw_bootstrap_intake_error_not_echoed_by_format_turn():
    raw = f"invalid bootstrap extraction: input_value={HOSTILE!r} {URL}"
    rendered = format_turn({"bootstrap_intake_error": raw}, unmatched=True)
    _assert_no_leak(rendered)
    assert "Bootstrap intake error:" in rendered
    assert raw not in rendered
