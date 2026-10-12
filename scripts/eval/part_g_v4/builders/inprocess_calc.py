"""Long-lived Node @smogon/calc worker (same handlers as HTTP /calculate)."""
from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[4]
WORKER = REPO / "services" / "calc" / "batch_worker.ts"

_lock = threading.Lock()
_proc: subprocess.Popen[str] | None = None
_next_id = 0


def _ensure() -> subprocess.Popen[str]:
    global _proc
    if _proc is not None and _proc.poll() is None:
        return _proc
    env = os.environ.copy()
    _proc = subprocess.Popen(
        ["npx", "tsx", str(WORKER)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(REPO),
        bufsize=1,
        env=env,
    )
    return _proc


def close() -> None:
    global _proc
    with _lock:
        if _proc is None:
            return
        try:
            _proc.stdin.close()  # type: ignore[union-attr]
        except Exception:
            pass
        try:
            _proc.terminate()
        except Exception:
            pass
        _proc = None


def calculate_batch(requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run requests through vendored calc; returns list of response bodies (same as HTTP)."""
    global _next_id
    with _lock:
        proc = _ensure()
        _next_id += 1
        mid = _next_id
        assert proc.stdin and proc.stdout
        proc.stdin.write(json.dumps({"id": mid, "requests": requests}) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        if not line:
            err = ""
            if proc.stderr:
                err = proc.stderr.read()
            raise RuntimeError(f"inprocess calc worker died: {err[:500]}")
        msg = json.loads(line)
        if msg.get("id") != mid:
            raise RuntimeError(f"inprocess calc id mismatch: {msg.get('id')!r} != {mid}")
        if "error" in msg and not msg.get("results"):
            raise RuntimeError(f"inprocess calc error: {msg['error']}")
        return list(msg.get("results") or [])


def calculate_one(req: dict[str, Any]) -> dict[str, Any]:
    return calculate_batch([req])[0]
