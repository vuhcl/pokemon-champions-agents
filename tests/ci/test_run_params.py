"""run_params.py: a clean worktree verifies; each kind of drift fails with a message naming the field."""

from __future__ import annotations

import importlib.util
import json
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "eval" / "run_params.py"
spec = importlib.util.spec_from_file_location("run_params", SCRIPT)
rp = importlib.util.module_from_spec(spec)
sys.modules["run_params"] = rp
spec.loader.exec_module(rp)

pytestmark = pytest.mark.skipif(
    not (shutil.which("lsof") or Path("/proc/net/tcp").exists()), reason="needs lsof or /proc to find a port owner"
)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def make_tree(path: Path) -> Path:
    (path / "scripts/eval/part_g_v4").mkdir(parents=True)
    (path / "vendor/smogon-calc").mkdir(parents=True)
    (path / "node_modules").mkdir()
    (path / "recommender").mkdir()
    (path / "scripts/eval/part_g_v4/pins_manifest.json").write_text(json.dumps({"calc_service": {"version": "0.0.1-test"}}))
    (path / "vendor/smogon-calc/package.json").write_text(json.dumps({"version": "0.0.1-test"}))
    lock = {"packages": {"": {}, "node_modules/a": {"version": "1.0.0", "integrity": "sha512-aaa"}}}
    (path / "package-lock.json").write_text(json.dumps(lock))
    (path / "node_modules/.package-lock.json").write_text(json.dumps({"packages": {"node_modules/a": lock["packages"]["node_modules/a"]}}))
    (path / "uv.lock").write_text("lock v1\n")
    (path / "recommender/llm_provider.py").write_text('_ENV_PROVIDER = "POKEMON_CHAMPIONS_LLM_PROVIDER"\n')
    (path / ".gitignore").write_text("node_modules/\n")
    _git(path, "init", "-q")
    _git(path, "-c", "user.email=a@b", "-c", "user.name=n", "add", "-A")
    _git(path, "-c", "user.email=a@b", "-c", "user.name=n", "commit", "-q", "-m", "init")
    return path


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def listener():
    procs = []

    def start(cwd: Path) -> int:
        port = free_port()
        code = f"import socket,time;s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('127.0.0.1',{port}));s.listen(1);time.sleep(60)"
        procs.append(subprocess.Popen([sys.executable, "-c", code], cwd=cwd))
        for _ in range(50):
            with socket.socket() as c:
                if c.connect_ex(("127.0.0.1", port)) == 0:
                    return port
            time.sleep(0.1)
        raise RuntimeError("listener did not start")

    yield start
    for p in procs:
        p.kill()


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv(rp.ENV_FIXED_NOW, "2026-11-05T12:00:00Z")


def test_clean_worktree_verifies(tmp_path, listener, env):
    root = make_tree(tmp_path / "wt")
    port = listener(root)
    rec = rp.collect(root, port=port)
    assert rp.verify(root, rec, port=port, allow_pending=True) == []
    # the post-run check also needs the run-time fields
    assert any(e.startswith("run_time.model_digest") for e in rp.verify(root, rec, port=port))


def test_dirty_tree_fails(tmp_path, listener, env):
    root = make_tree(tmp_path / "wt")
    port = listener(root)
    rec = rp.collect(root, port=port)
    (root / "uv.lock").write_text("lock v1\n# edit\n")
    errs = rp.verify(root, rec, port=port, allow_pending=True)
    assert any(e.startswith("worktree.clean") for e in errs)


def test_changed_lockfile_fails(tmp_path, listener, env):
    root = make_tree(tmp_path / "wt")
    port = listener(root)
    rec = rp.collect(root, port=port)
    (root / "package-lock.json").write_text(json.dumps({"packages": {"": {}}}))
    errs = rp.verify(root, rec, port=port, allow_pending=True)
    assert any(e.startswith("lockfiles.package-lock.json") for e in errs)


def test_node_modules_integrity_mismatch_fails(tmp_path, listener, env):
    root = make_tree(tmp_path / "wt")
    port = listener(root)
    rec = rp.collect(root, port=port)
    hidden = root / "node_modules/.package-lock.json"
    hidden.write_text(json.dumps({"packages": {"node_modules/a": {"version": "1.0.0", "integrity": "sha512-zzz"}}}))
    errs = rp.verify(root, rec, port=port, allow_pending=True)
    assert any(e.startswith("node_modules_vs_lockfile") for e in errs)


def test_wrong_date_fails(tmp_path, listener, env, monkeypatch):
    root = make_tree(tmp_path / "wt")
    port = listener(root)
    rec = rp.collect(root, port=port)
    monkeypatch.setenv(rp.ENV_FIXED_NOW, "2026-11-06T12:00:00Z")
    errs = rp.verify(root, rec, port=port, allow_pending=True)
    assert any(e.startswith("date.fixed_now_utc") for e in errs)


def test_allow_live_true_fails(tmp_path, listener, env):
    root = make_tree(tmp_path / "wt")
    port = listener(root)
    rec = rp.collect(root, port=port)
    errs = rp.verify(root, rec, port=port, allow_live=True, allow_pending=True)
    assert any(e.startswith("allow_live") for e in errs)


def test_port_owned_by_another_tree_fails(tmp_path, listener, env):
    root = make_tree(tmp_path / "wt")
    other = make_tree(tmp_path / "other")
    port = listener(other)
    rec = rp.collect(root, port=port)
    assert rec["port"]["owner_toplevel"] == str(other.resolve())
    errs = rp.verify(root, rec, port=port, allow_pending=True)
    assert any(e.startswith("port.same_worktree") for e in errs)


def test_unset_date_fails(tmp_path, listener, monkeypatch):
    monkeypatch.delenv(rp.ENV_FIXED_NOW, raising=False)
    root = make_tree(tmp_path / "wt")
    port = listener(root)
    rec = rp.collect(root, port=port)
    errs = rp.verify(root, rec, port=port, allow_pending=True)
    assert any(e.startswith("date.fixed_now_utc") for e in errs)


def test_edited_record_fails(tmp_path, listener, env):
    root = make_tree(tmp_path / "wt")
    port = listener(root)
    rec = rp.collect(root, port=port)
    rec["run_time"]["seed"] = 7
    errs = rp.verify(root, rec, port=port, allow_pending=True)
    assert any(e.startswith("record_sha256") for e in errs)
