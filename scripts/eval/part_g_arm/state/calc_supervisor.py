"""Auto-restart supervisor for the Node calc service (macOS / local harness).

Mechanism: Python child-process manager (`subprocess.Popen` + `npm start` on
fixed port 4173), same lifecycle as `recommender.calc_service.CalcService` but
with restart logging for the request-set runner. Not launchd — stays in-process
with the runner so restart count is readable without a second daemon.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from recommender.calc_client import CalcClient

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PORT = 4173
HEALTH_TIMEOUT_S = 30
STOP_GRACE_S = 5


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class CalcSupervisor:
    """Owns one calc service process; logs every start/restart."""

    def __init__(
        self,
        *,
        repo_root: Path | None = None,
        port: int = DEFAULT_PORT,
        log_path: Path | None = None,
        attach_only: bool = False,
    ) -> None:
        self._repo_root = repo_root or DEFAULT_REPO_ROOT
        self._port = port
        self._log_path = log_path
        self._attach_only = attach_only
        self._proc: subprocess.Popen[bytes] | None = None
        self.restart_count = 0
        self.restart_timestamps: list[str] = []
        self._events: list[dict[str, Any]] = []

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    def snapshot(self) -> dict[str, Any]:
        return {
            "restart_count": self.restart_count,
            "restart_timestamps": list(self.restart_timestamps),
            "events": list(self._events),
            "port": self._port,
            "attach_only": self._attach_only,
        }

    def _record(self, kind: str, **extra: Any) -> None:
        ev = {"ts": _utc_now(), "kind": kind, "restart_count": self.restart_count, **extra}
        self._events.append(ev)
        if self._log_path is not None:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(ev) + "\n")

    def _wait_healthy(self, client: CalcClient) -> None:
        deadline = time.monotonic() + HEALTH_TIMEOUT_S
        while time.monotonic() < deadline:
            if self._proc is not None and self._proc.poll() is not None:
                raise RuntimeError(
                    f"calc service exited early with code {self._proc.returncode}"
                )
            try:
                if client.health(timeout=1.0).get("status") == "ok":
                    return
            except Exception:
                pass
            time.sleep(0.1)
        raise TimeoutError(
            f"calc service not healthy after {HEALTH_TIMEOUT_S}s on {self.base_url}"
        )

    def ensure_running(self) -> None:
        """Start if needed, or attach when an existing service already answers /health."""
        client = CalcClient(self.base_url)
        try:
            if client.health(timeout=1.0).get("status") == "ok":
                self._record("attached_existing")
                return
        except Exception:
            pass
        if self._attach_only:
            raise RuntimeError(
                f"calc service not reachable at {self.base_url} (attach_only)"
            )
        self._spawn(reason="initial")

    def _free_port(self) -> None:
        """Best-effort: stop anything still bound to our port (macOS/Linux)."""
        try:
            out = subprocess.check_output(
                ["lsof", "-nP", f"-iTCP:{self._port}", "-sTCP:LISTEN", "-t"],
                stderr=subprocess.DEVNULL,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return
        for pid_s in out.decode().split():
            try:
                os.kill(int(pid_s), signal.SIGTERM)
            except (ProcessLookupError, ValueError):
                continue
        time.sleep(0.3)

    def restart(self, *, reason: str = "infra") -> None:
        """Kill owned child (if any) and start a fresh process; bump restart_count."""
        self._stop_owned()
        self._free_port()
        self.restart_count += 1
        ts = _utc_now()
        self.restart_timestamps.append(ts)
        self._record("restart", reason=reason, ts=ts)
        if self._attach_only:
            # Expect an external supervisor; wait for health only.
            self._wait_healthy(CalcClient(self.base_url))
            return
        self._spawn(reason=reason)

    def _spawn(self, *, reason: str) -> None:
        self._proc = subprocess.Popen(
            ["npm", "start"],
            cwd=self._repo_root,
            env={**os.environ, "PORT": str(self._port)},
            start_new_session=True,
        )
        self._record("spawn", reason=reason, pid=self._proc.pid)
        self._wait_healthy(CalcClient(self.base_url))

    def _stop_owned(self) -> None:
        proc = self._proc
        if proc is None:
            return
        self._proc = None
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            proc.wait()
            return
        try:
            proc.wait(timeout=STOP_GRACE_S)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()

    def stop(self) -> None:
        self._stop_owned()
        self._record("stop")
