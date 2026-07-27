"""Subprocess lifecycle manager for the Node calc HTTP service."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
from pathlib import Path

from recommender.calc_client import CalcClient

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
HEALTH_TIMEOUT_S = 30
STOP_GRACE_S = 5


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class CalcService:
    def __init__(
        self,
        repo_root: Path | None = None,
        port: int | None = None,
    ) -> None:
        self._repo_root = repo_root or DEFAULT_REPO_ROOT
        self._port = port if port is not None else _pick_free_port()
        self._proc: subprocess.Popen[bytes] | None = None

    @property
    def port(self) -> int:
        return self._port

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    def start(self) -> None:
        if self._proc is not None:
            return
        self._proc = subprocess.Popen(
            ["npm", "start"],
            cwd=self._repo_root,
            env={**os.environ, "PORT": str(self._port)},
            start_new_session=True,
        )
        client = CalcClient(self.base_url)
        deadline = time.monotonic() + HEALTH_TIMEOUT_S
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(
                    f"calc service exited early with code {self._proc.returncode}"
                )
            try:
                if client.health().get("status") == "ok":
                    return
            except Exception:
                pass
            time.sleep(0.1)
        raise TimeoutError(
            f"calc service not healthy after {HEALTH_TIMEOUT_S}s on {self.base_url}"
        )

    def stop(self) -> None:
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
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()

    def __enter__(self) -> CalcService:
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.stop()
