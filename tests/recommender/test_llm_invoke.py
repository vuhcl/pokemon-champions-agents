"""Tests for the shared LLM-invoke-with-timeout helper."""

from __future__ import annotations

import json
import threading
import time
from contextvars import ContextVar
from pathlib import Path
from typing import TypedDict

import pytest
from langgraph.graph import END, START, StateGraph

from recommender.llm_invoke import LLMInvokeTimeout, invoke_with_timeout
from recommender.tool_log import log_tool_call


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


def test_explicit_kwargs_logged_from_worker(tool_log_path: Path):
    """Worker path closes over explicit turn/thread_id (not ContextVars)."""
    invoke_with_timeout(
        _FastParser(),
        {"user_text": "x"},
        timeout=5.0,
        tool="llm.probe",
        turn=7,
        thread_id="team-abc",
    )
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


class _CorrState(TypedDict, total=False):
    turn: int
    obs_thread_id: str


def test_cross_node_llm_and_calc_share_turn_correlation(tool_log_path: Path):
    """LLM log in node A + calc log in node B share explicit state-plumbed ids."""

    def node_llm(state: _CorrState) -> _CorrState:
        invoke_with_timeout(
            _FastParser(),
            {"user_text": "x"},
            timeout=5.0,
            tool="llm.turn_intent",
            turn=9,
            thread_id="team-cross-node",
        )
        return {"turn": 9, "obs_thread_id": "team-cross-node"}

    def node_calc(state: _CorrState) -> _CorrState:
        log_tool_call(
            "CalcClient.POST /calculate/batch",
            {"n": 1},
            latency_ms=0.5,
            ok=True,
            turn=state["turn"],
            thread_id=state["obs_thread_id"],
        )
        return state

    g = StateGraph(_CorrState)
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


def test_sequential_invokes_and_parent_contamination_do_not_leak(
    tool_log_path: Path,
):
    """Two invokes with different turns, then a third after stray parent writes.

    The contamination step mirrors the old cli.py pre-invoke bind_correlation
    pollution: writes on the calling thread outside any graph must not affect
    explicitly plumbed log lines.
    """

    def _run_once(turn: int, thread_id: str) -> None:
        def node_llm(state: _CorrState) -> _CorrState:
            invoke_with_timeout(
                _FastParser(),
                {"user_text": "x"},
                timeout=5.0,
                tool="llm.turn_intent",
                turn=turn,
                thread_id=thread_id,
            )
            return {"turn": turn, "obs_thread_id": thread_id}

        def node_calc(state: _CorrState) -> _CorrState:
            log_tool_call(
                "CalcClient.POST /calculate/batch",
                {"n": 1},
                latency_ms=0.5,
                ok=True,
                turn=state["turn"],
                thread_id=state["obs_thread_id"],
            )
            return state

        g = StateGraph(_CorrState)
        g.add_node("llm", node_llm)
        g.add_node("calc", node_calc)
        g.add_edge(START, "llm")
        g.add_edge("llm", "calc")
        g.add_edge("calc", END)
        g.compile().invoke({})

    _run_once(9, "team-a")
    _run_once(42, "team-b")

    # Stray parent-thread writes — not part of any graph invocation.
    stray_cv: ContextVar[int | None] = ContextVar("stray_turn", default=None)
    stray_cv.set(1)
    local = threading.local()
    local.turn = 1

    _run_once(42, "team-c")

    rows = _read_log(tool_log_path)
    calc_turns = [
        r["turn"]
        for r in rows
        if r["tool"] == "CalcClient.POST /calculate/batch"
    ]
    llm_turns = [r["turn"] for r in rows if r["tool"] == "llm.turn_intent"]
    assert calc_turns == [9, 42, 42]
    assert llm_turns == [9, 42, 42]
