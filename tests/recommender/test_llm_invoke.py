"""Tests for the shared LLM-invoke-with-timeout helper."""

from __future__ import annotations

import time

import pytest

from recommender.llm_invoke import LLMInvokeTimeout, invoke_with_timeout


class _FastParser:
    def invoke(self, payload):
        return {"echo": payload}


class _SlowParser:
    def __init__(self, delay: float) -> None:
        self.delay = delay

    def invoke(self, payload):
        time.sleep(self.delay)
        return {"echo": payload}


def test_invoke_with_timeout_returns_result_on_success():
    result = invoke_with_timeout(_FastParser(), {"user_text": "hi"}, timeout=5.0)
    assert result == {"echo": {"user_text": "hi"}}


def test_invoke_with_timeout_raises_on_hang():
    """The whole point of this helper: a hung call must not block forever.

    This is the direct, real-timed proof — not just that LLMInvokeTimeout
    gets raised, but that it gets raised near the configured timeout, not
    after the full (much longer) underlying delay.
    """
    start = time.monotonic()
    with pytest.raises(LLMInvokeTimeout):
        invoke_with_timeout(_SlowParser(delay=10.0), {}, timeout=0.5)
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
