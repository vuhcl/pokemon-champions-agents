"""Shared helper for invoking LLM-backed Runnables with a hard timeout.

A blocking Runnable.invoke() call has no universal, provider-agnostic timeout
mechanism in LangChain — different providers expose different (or no) timeout
knobs. This wraps any Runnable.invoke() call in a thread with a hard
wall-clock deadline, so a pathological hang in the underlying provider (seen
live: 7-8 minute hangs on certain multi-species bootstrap utterances,
requiring a manual kill) cannot block the graph forever.
"""

from __future__ import annotations

import contextvars
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any

from langchain_core.runnables import Runnable

from recommender.tool_log import log_tool_call

LLM_INVOKE_TIMEOUT_S = 300.0


class LLMInvokeTimeout(Exception):
    """Raised when a Runnable.invoke() call exceeds the configured timeout."""


def _usage_tokens(result: Any) -> tuple[int | None, int | None]:
    """Extract LangChain usage_metadata from an include_raw structured result."""
    if not isinstance(result, dict):
        return None, None
    if not {"raw", "parsed", "parsing_error"}.issubset(result):
        return None, None
    raw = result.get("raw")
    usage = getattr(raw, "usage_metadata", None)
    if usage is None:
        return None, None
    if isinstance(usage, dict):
        prompt = usage.get("input_tokens")
        completion = usage.get("output_tokens")
    else:
        prompt = getattr(usage, "input_tokens", None)
        completion = getattr(usage, "output_tokens", None)
    return (
        int(prompt) if isinstance(prompt, int) else None,
        int(completion) if isinstance(completion, int) else None,
    )


def invoke_with_timeout(
    parser: Runnable,
    payload: dict[str, Any],
    *,
    timeout: float = LLM_INVOKE_TIMEOUT_S,
    tool: str = "llm.invoke",
    provider: str | None = None,
) -> Any:
    """Invoke parser.invoke(payload) with a hard timeout.

    Raises LLMInvokeTimeout if the call has not returned within `timeout`
    seconds. Python has no safe way to forcibly kill a running thread, so the
    background call is not stopped — it is abandoned and may continue running
    until the provider itself returns or errors, but this function returns
    control to the caller immediately once the deadline passes. The executor
    is shut down with wait=False specifically so cleanup never blocks on the
    abandoned call — using it as a context manager (the usual `with
    ThreadPoolExecutor(...)` idiom) would defeat the timeout entirely, since
    that blocks on exit until every submitted task finishes.

    ContextVars from the parent (turn / thread_id) are copied into the worker
    via copy_context().run so LLM log lines carry the same correlation fields
    as in-graph tool calls. An abandoned Event suppresses a late success/error
    log if the worker finishes after the parent already timed out.
    """
    abandoned = threading.Event()
    ctx = contextvars.copy_context()

    def _run() -> Any:
        t0 = time.perf_counter()
        try:
            result = parser.invoke(payload)
        except Exception as exc:
            if not abandoned.is_set():
                log_tool_call(
                    tool,
                    {"keys": sorted(payload)},
                    latency_ms=(time.perf_counter() - t0) * 1000,
                    ok=False,
                    error=type(exc).__name__,
                    provider=provider,
                )
            raise
        if not abandoned.is_set():
            prompt_tokens, completion_tokens = _usage_tokens(result)
            log_tool_call(
                tool,
                {"keys": sorted(payload)},
                latency_ms=(time.perf_counter() - t0) * 1000,
                ok=True,
                provider=provider,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        return result

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(ctx.run, _run)
    try:
        result = future.result(timeout=timeout)
    except FutureTimeoutError as exc:
        abandoned.set()
        log_tool_call(
            tool,
            {"keys": sorted(payload)},
            latency_ms=timeout * 1000,
            ok=False,
            error="LLMInvokeTimeout",
            provider=provider,
        )
        executor.shutdown(wait=False)
        raise LLMInvokeTimeout(
            f"LLM call did not return within {timeout:.0f}s"
        ) from exc
    executor.shutdown(wait=False)
    return result
