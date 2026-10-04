"""Local bare-remote tests for scripts/ci/push_to_main.sh (no network)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ci" / "push_to_main.sh"


def _run(
    args: list[str],
    *,
    cwd: Path,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        args,
        cwd=cwd,
        check=check,
        text=True,
        capture_output=True,
        env=merged,
    )


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return _run(["git", *args], cwd=cwd, check=check)


def _init_user(cwd: Path) -> None:
    _git(cwd, "config", "user.name", "test")
    _git(cwd, "config", "user.email", "test@example.com")


def _bare_pair(tmp_path: Path) -> tuple[Path, Path, Path]:
    bare = tmp_path / "remote.git"
    a = tmp_path / "clone_a"
    b = tmp_path / "clone_b"
    _git(tmp_path, "init", "--bare", str(bare))
    _git(tmp_path, "clone", str(bare), str(a))
    _init_user(a)
    (a / "README").write_text("base\n", encoding="utf-8")
    (a / "shared.txt").write_text("shared-base\n", encoding="utf-8")
    _git(a, "add", "README", "shared.txt")
    _git(a, "commit", "-m", "init")
    # Ensure default branch is main.
    _git(a, "branch", "-M", "main")
    _git(a, "push", "-u", "origin", "main")
    _git(tmp_path, "clone", str(bare), str(b))
    _init_user(b)
    _git(b, "checkout", "main")
    return bare, a, b


def _push_env(**extra: str) -> dict[str, str]:
    env = {
        "PUSH_TO_MAIN_BRANCH": "main",
        "PUSH_TO_MAIN_RETRIES": "3",
        "PUSH_TO_MAIN_BACKOFF_SECS": "0",
    }
    env.update(extra)
    return env


def test_dirty_tree_breaks_bare_rebase_then_script_succeeds(tmp_path: Path) -> None:
    """RED: dirty tracked file blocks rebase. GREEN: script stashes and pushes."""
    bare, a, b = _bare_pair(tmp_path)

    (b / "from_b.txt").write_text("b\n", encoding="utf-8")
    _git(b, "add", "from_b.txt")
    _git(b, "commit", "-m", "b commit")
    _git(b, "push", "origin", "main")

    (a / "from_a.txt").write_text("a\n", encoding="utf-8")
    _git(a, "add", "from_a.txt")
    _git(a, "commit", "-m", "a commit")
    (a / "shared.txt").write_text("dirty-local\n", encoding="utf-8")

    # RED: bare rebase fails with unstaged changes.
    _git(a, "fetch", "origin", "main")
    red = _git(a, "rebase", "origin/main", check=False)
    assert red.returncode != 0
    assert "unstaged changes" in (red.stderr + red.stdout).lower() or red.returncode != 0
    _git(a, "rebase", "--abort", check=False)

    # GREEN: shared script succeeds and preserves dirty content.
    green = _run(
        ["bash", str(SCRIPT)],
        cwd=a,
        check=False,
        env=_push_env(),
    )
    assert green.returncode == 0, green.stderr + green.stdout
    assert (a / "shared.txt").read_text(encoding="utf-8") == "dirty-local\n"
    log = _git(bare, "log", "main", "--oneline")
    assert "a commit" in log.stdout
    assert "b commit" in log.stdout


def test_concurrent_push_succeeds_after_rebase(tmp_path: Path) -> None:
    bare, a, b = _bare_pair(tmp_path)

    (a / "a_only.txt").write_text("a\n", encoding="utf-8")
    _git(a, "add", "a_only.txt")
    _git(a, "commit", "-m", "a only")

    (b / "b_only.txt").write_text("b\n", encoding="utf-8")
    _git(b, "add", "b_only.txt")
    _git(b, "commit", "-m", "b only")
    _git(b, "push", "origin", "main")

    proc = _run(["bash", str(SCRIPT)], cwd=a, check=False, env=_push_env())
    assert proc.returncode == 0, proc.stderr + proc.stdout
    names = _git(bare, "log", "main", "--name-only", "--pretty=format:").stdout
    assert "a_only.txt" in names
    assert "b_only.txt" in names


def test_persistent_rejection_exits_nonzero(tmp_path: Path) -> None:
    bare, a, _b = _bare_pair(tmp_path)
    hook = bare / "hooks" / "update"
    hook.write_text("#!/bin/sh\necho reject-all >&2\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)

    (a / "x.txt").write_text("x\n", encoding="utf-8")
    _git(a, "add", "x.txt")
    _git(a, "commit", "-m", "will be rejected")

    proc = _run(
        ["bash", str(SCRIPT)],
        cwd=a,
        check=False,
        env=_push_env(PUSH_TO_MAIN_RETRIES="3"),
    )
    assert proc.returncode != 0
    assert "failed after 3 attempts" in proc.stderr


def test_stash_pop_conflict_after_successful_push_exits_zero(tmp_path: Path) -> None:
    """Rebase brings remote change to the same dirty file; stash pop conflicts; exit 0."""
    bare, a, b = _bare_pair(tmp_path)

    (b / "shared.txt").write_text("remote-shared\n", encoding="utf-8")
    _git(b, "add", "shared.txt")
    _git(b, "commit", "-m", "remote touches shared")
    _git(b, "push", "origin", "main")

    (a / "marker.txt").write_text("marker\n", encoding="utf-8")
    _git(a, "add", "marker.txt")
    _git(a, "commit", "-m", "local marker")
    (a / "shared.txt").write_text("local-dirty\n", encoding="utf-8")

    proc = _run(["bash", str(SCRIPT)], cwd=a, check=False, env=_push_env())
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "stash pop failed after successful push" in proc.stderr
    # Marker commit landed despite stash-pop conflict.
    assert "marker.txt" in _git(
        bare, "log", "main", "--name-only", "--pretty=format:"
    ).stdout
