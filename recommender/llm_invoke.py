"""Shared helper for invoking LLM-backed Runnables with a hard timeout.

A blocking Runnable.invoke() call has no universal, provider-agnostic timeout
mechanism in LangChain — different providers expose different (or no) timeout
knobs. This wraps any Runnable.invoke() call in a thread with a hard
wall-clock deadline, so a pathological hang in the underlying provider (seen
live: 7-8 minute hangs on certain multi-species bootstrap utterances,
requiring a manual kill) cannot block the graph forever.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any

from langchain_core.runnables import Runnable

LLM_INVOKE_TIMEOUT_S = 120.0


class LLMInvokeTimeout(Exception):
    """Raised when a Runnable.invoke() call exceeds the configured timeout."""


def invoke_with_timeout(
    parser: Runnable,
    payload: dict[str, Any],
    *,
    timeout: float = LLM_INVOKE_TIMEOUT_S,
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
    """
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(parser.invoke, payload)
    try:
        result = future.result(timeout=timeout)
    except FutureTimeoutError as exc:
        executor.shutdown(wait=False)
        raise LLMInvokeTimeout(
            f"LLM call did not return within {timeout:.0f}s"
        ) from exc
    executor.shutdown(wait=False)
    return result
