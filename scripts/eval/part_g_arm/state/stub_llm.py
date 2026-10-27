"""Deterministic fake LLM for runner shakedown (no real model behavior)."""

from __future__ import annotations

from typing import Any


class _AI:
    def __init__(self, *, content: str = "", tool_calls: list[dict[str, Any]] | None = None):
        self.content = content
        self.tool_calls = tool_calls or []


class StubLLM:
    """First invoke → no_lookup_needed; second → short final text. Deterministic."""

    def __init__(self) -> None:
        self.calls = 0

    def bind_tools(self, _specs: object) -> StubLLM:
        return self

    def invoke(self, _messages: object) -> _AI:
        self.calls += 1
        if self.calls % 2 == 1:
            return _AI(
                tool_calls=[
                    {
                        "name": "no_lookup_needed",
                        "args": {"category": "other", "reason": "stub"},
                        "id": f"stub-{self.calls}",
                    }
                ]
            )
        return _AI(content="stub final: no usable model — scripted reply only.")
