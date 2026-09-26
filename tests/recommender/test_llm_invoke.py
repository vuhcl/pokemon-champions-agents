"""Tests for the shared LLM-invoke-with-timeout helper."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from recommender.llm_invoke import LLMInvokeTimeout, invoke_with_timeout
from recommender.tool_log import current_thread_id, current_turn


class _FastParser:
    def invoke(self, payload):
        return {"echo": payload}


class _SlowParser:
    def __init__(self, delay: float) -> None:
        self.delay = delay

    def invoke(self, payload):
        time.sleep(self.delay)
        return {"echo": payload}


class _RawMessage:
    def __init__(self, usage_metadata):
        self.usage_metadata = usage_metadata


@pytest.fixture()
def tool_log_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "tool_calls.jsonl"
    monkeypatch.setenv("RECOMMENDER_TOOL_LOG", str(path))
    return path


def _read_log(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_invoke_with_timeout_returns_result_on_success():
    result = invoke_with_timeout(_FastParser(), {"user_text": "hi"}, timeout=5.0)
    assert result == {"echo": {"user_text": "hi"}}


def test_invoke_with_timeout_raises_on_hang(tool_log_path: Path):
    """The whole point of this helper: a hung call must not block forever.

    This is the direct, real-timed proof — not just that LLMInvokeTimeout
    gets raised, but that it gets raised near the configured timeout, not
    after the full (much longer) underlying delay.
    """
    start = time.monotonic()
    with pytest.raises(LLMInvokeTimeout):
        invoke_with_timeout(_SlowParser(delay=10.0), {}, timeout=0.5, tool="llm.test")
    elapsed = time.monotonic() - start
    assert elapsed < 2.0, (
        f"invoke_with_timeout blocked for {elapsed:.2f}s — it must return near "
        "the configured timeout (0.5s), not wait out the abandoned call's full "
        "delay (10s). A naive `with ThreadPoolExecutor(...)` context-manager "
        "usage would fail this exact assertion."
    )


def test_invoke_with_timeout_does_not_swallow_provider_exceptions():
    class _RaisingParser:
        def invoke(self, payload):
            raise RuntimeError("provider exploded")

    with pytest.raises(RuntimeError, match="provider exploded"):
        invoke_with_timeout(_RaisingParser(), {}, timeout=5.0)


def test_copy_context_carries_turn_thread_into_worker(tool_log_path: Path):
    """Real proof: worker sees parent ContextVars (not just 'should work')."""
    seen: dict[str, object] = {}

    class _Probe:
        def invoke(self, payload):
            seen["turn"] = current_turn.get()
            seen["thread_id"] = current_thread_id.get()
            return {"ok": True}

    tok_t = current_turn.set(7)
    tok_id = current_thread_id.set("team-abc")
    try:
        invoke_with_timeout(_Probe(), {"user_text": "x"}, timeout=5.0, tool="llm.probe")
    finally:
        current_turn.reset(tok_t)
        current_thread_id.reset(tok_id)

    assert seen == {"turn": 7, "thread_id": "team-abc"}
    rows = _read_log(tool_log_path)
    assert len(rows) == 1
    assert rows[0]["turn"] == 7
    assert rows[0]["thread_id"] == "team-abc"
    assert rows[0]["tool"] == "llm.probe"
    assert rows[0]["ok"] is True


def test_timeout_does_not_double_log_when_worker_finishes_late(tool_log_path: Path):
    with pytest.raises(LLMInvokeTimeout):
        invoke_with_timeout(
            _SlowParser(delay=1.5),
            {},
            timeout=0.3,
            tool="llm.slow",
            provider="ollama",
        )
    # Wait past the abandoned worker so a buggy late success log would appear.
    time.sleep(1.8)
    rows = [r for r in _read_log(tool_log_path) if r.get("tool") == "llm.slow"]
    assert len(rows) == 1
    assert rows[0]["ok"] is False
    assert rows[0]["error"] == "LLMInvokeTimeout"


def test_usage_metadata_logged_from_include_raw(tool_log_path: Path):
    class _UsageParser:
        def invoke(self, payload):
            return {
                "raw": _RawMessage(
                    {"input_tokens": 11, "output_tokens": 4, "total_tokens": 15}
                ),
                "parsed": {"x": 1},
                "parsing_error": None,
            }

    invoke_with_timeout(
        _UsageParser(),
        {"user_text": "hi"},
        timeout=5.0,
        tool="llm.turn_intent",
        provider="ollama",
    )
    rows = _read_log(tool_log_path)
    assert len(rows) == 1
    assert rows[0]["prompt_tokens"] == 11
    assert rows[0]["completion_tokens"] == 4
    assert rows[0]["provider"] == "ollama"


def test_cross_node_llm_and_calc_share_turn_correlation(tool_log_path: Path):
    """LLM log in node A + calc log in node B share (thread_id, turn).

    This is the bug the threading.local fallback exists to fix — not a generic
    "does threading.local store a value" check. LangGraph may start each node
    with a fresh ContextVar context, so a ContextVar set while handling the LLM
    call is invisible to a later node that logs a tool call. Without the
    same-thread fallback, the calc line would lack turn/thread_id and turn
    rollup could not join LLM + tools.
    """
    from typing import TypedDict

    from langgraph.graph import END, START, StateGraph

    from recommender.tool_log import bind_correlation, log_tool_call

    class St(TypedDict, total=False):
        ok: bool

    ctx_seen_in_calc: dict[str, object] = {}

    def node_llm(state: St) -> St:
        bind_correlation(turn=9, thread_id="team-cross-node")
        invoke_with_timeout(
            _FastParser(), {"user_text": "x"}, timeout=5.0, tool="llm.turn_intent"
        )
        return {"ok": True}

    def node_calc(state: St) -> St:
        # Capture what ContextVars alone would see in this later node.
        ctx_seen_in_calc["turn"] = current_turn.get()
        ctx_seen_in_calc["thread_id"] = current_thread_id.get()
        log_tool_call(
            "CalcClient.POST /calculate/batch",
            {"n": 1},
            latency_ms=0.5,
            ok=True,
        )
        return state

    g = StateGraph(St)
    g.add_node("llm", node_llm)
    g.add_node("calc", node_calc)
    g.add_edge(START, "llm")
    g.add_edge("llm", "calc")
    g.add_edge("calc", END)
    g.compile().invoke({})

    rows = _read_log(tool_log_path)
    llm_rows = [r for r in rows if r["tool"] == "llm.turn_intent"]
    calc_rows = [r for r in rows if r["tool"] == "CalcClient.POST /calculate/batch"]
    assert len(llm_rows) == 1 and len(calc_rows) == 1
    assert llm_rows[0]["turn"] == 9
    assert calc_rows[0]["turn"] == 9
    assert llm_rows[0]["thread_id"] == "team-cross-node"
    assert calc_rows[0]["thread_id"] == "team-cross-node"
    # Explicit proof ContextVars alone do not bridge the node boundary.
    assert ctx_seen_in_calc["turn"] is None
    assert ctx_seen_in_calc["thread_id"] is None


def test_missing_usage_metadata_omits_token_fields(tool_log_path: Path):
    class _NoUsage:
        def invoke(self, payload):
            return {
                "raw": _RawMessage(None),
                "parsed": {"x": 1},
                "parsing_error": None,
            }

    invoke_with_timeout(_NoUsage(), {}, timeout=5.0, tool="llm.bootstrap_intake")
    rows = _read_log(tool_log_path)
    assert len(rows) == 1
    assert "prompt_tokens" not in rows[0]
    assert "completion_tokens" not in rows[0]
