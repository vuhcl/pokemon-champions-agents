"""Best-effort JSONL tool-call logging (no hosted observability deps)."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")

_DEFAULT_LOG = Path("artifacts/tool_calls.jsonl")


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
    if error is not None:
        record["error"] = error
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
