"""Best-effort JSONL tool-call logging (no hosted observability deps)."""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable
from contextvars import ContextVar
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")

_DEFAULT_LOG = Path("artifacts/tool_calls.jsonl")

# ContextVars: visible to LLM worker threads via copy_context().run in
# invoke_with_timeout. LangGraph may start each node with a fresh context, so
# threading.local is the same-thread fallback that survives node boundaries.
current_turn: ContextVar[int | None] = ContextVar("current_turn", default=None)
current_thread_id: ContextVar[str | None] = ContextVar(
    "current_thread_id", default=None
)
_local = threading.local()


def bind_correlation(*, turn: int | None = None, thread_id: str | None = None) -> None:
    """Bind turn/thread for tool + LLM logs (ContextVar + same-thread fallback)."""
    if turn is not None:
        current_turn.set(turn)
        _local.turn = turn
    if thread_id is not None:
        current_thread_id.set(thread_id)
        _local.thread_id = thread_id


def _corr_turn() -> int | None:
    v = current_turn.get()
    if v is not None:
        return v
    return getattr(_local, "turn", None)


def _corr_thread_id() -> str | None:
    v = current_thread_id.get()
    if v is not None:
        return v
    return getattr(_local, "thread_id", None)


def _log_path() -> Path:
    override = os.environ.get("RECOMMENDER_TOOL_LOG")
    return Path(override) if override else _DEFAULT_LOG


def log_tool_call(
    tool: str,
    args: dict[str, Any],
    *,
    latency_ms: float,
    ok: bool,
    retries: int = 0,
    error: str | None = None,
    provider: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> None:
    """Append one JSON line; never raises into the caller."""
    record: dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tool": tool,
        "args": args,
        "latency_ms": round(latency_ms, 3),
        "ok": ok,
        "retries": retries,
    }
    thread_id = _corr_thread_id()
    turn = _corr_turn()
    if thread_id is not None:
        record["thread_id"] = thread_id
    if turn is not None:
        record["turn"] = turn
    if error is not None:
        record["error"] = error
    if provider is not None:
        record["provider"] = provider
    if prompt_tokens is not None:
        record["prompt_tokens"] = prompt_tokens
    if completion_tokens is not None:
        record["completion_tokens"] = completion_tokens
    try:
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, separators=(",", ":")) + "\n")
    except OSError:
        return


def timed_tool_call(
    tool: str,
    args: dict[str, Any],
    fn: Callable[[], T],
    *,
    retries: int = 0,
) -> T:
    """Run fn(), log latency/ok/error, re-raise on failure."""
    t0 = time.perf_counter()
    try:
        result = fn()
    except Exception as exc:
        log_tool_call(
            tool,
            args,
            latency_ms=(time.perf_counter() - t0) * 1000,
            ok=False,
            retries=retries,
            error=type(exc).__name__,
        )
        raise
    log_tool_call(
        tool,
        args,
        latency_ms=(time.perf_counter() - t0) * 1000,
        ok=True,
        retries=retries,
    )
    return result
