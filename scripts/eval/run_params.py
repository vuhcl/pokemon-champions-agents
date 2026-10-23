#!/usr/bin/env python3
"""Run-parameter record for a gate or pilot run: collect it, then verify the live environment against it.

    python scripts/eval/run_params.py collect --out record.json [--allow-live false]
    python scripts/eval/run_params.py verify record.json [--allow-live false] [--allow-pending]

`collect` writes everything it can see without a model or arm and marks the fields only known at run time
as "pending_at_run". `verify` recomputes the live fields and exits 1, naming each field, on any mismatch.
Without --allow-pending it also fails while any field is still "pending_at_run" (the post-run check).
Standalone: it imports nothing from recommender, and the part_g_v4 independence check does not scan it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

PENDING = "pending_at_run"
DEFAULT_PORT = 4173
ENV_FIXED_NOW = "RECOMMENDER_FIXED_NOW_UTC"
RUN_TIME_FIELDS = (
    "model_digest", "decoding_parameters", "seed", "think_setting", "system_prompt_hash", "max_turns", "timeouts",
    "num_ctx", "num_predict", "calc_process", "fixed_now_utc",
)
# Env variables outside the code that can change a run; names are read from the source, not hardcoded.
EXTRA_ENV = ("RECOMMENDER_TOOL_LOG", "POKEMON_CHAMPIONS_CHECKPOINT_DB", "XDG_DATA_HOME")


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True).stdout


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_toplevel(path: Path) -> str | None:
    try:
        return str(Path(_run(["git", "-C", str(path), "rev-parse", "--show-toplevel"]).strip()).resolve())
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None


def llm_env_names(root: Path) -> list[str]:
    src = (root / "recommender" / "llm_provider.py").read_text() if (root / "recommender" / "llm_provider.py").is_file() else ""
    names = re.findall(r'_ENV_\w+\s*=\s*"([A-Z0-9_]+)"', src)
    return sorted(set(names + ["POKEMON_CHAMPIONS_LLM_PROVIDER", "ANTHROPIC_API_KEY"]))


def worktree_state(root: Path) -> dict[str, Any]:
    return {
        "toplevel": str(root.resolve()),
        "commit": _run(["git", "rev-parse", "HEAD"], cwd=root).strip(),
        "clean": _run(["git", "status", "--porcelain"], cwd=root).strip() == "",
    }


def calc_build(root: Path) -> dict[str, Any]:
    pins = json.loads((root / "scripts/eval/part_g_v4/pins_manifest.json").read_text())
    vendor = root / "vendor" / "smogon-calc"
    tree = _run(["git", "rev-parse", "HEAD:vendor/smogon-calc"], cwd=root).strip()
    dirty = _run(["git", "status", "--porcelain", "--", "vendor/smogon-calc"], cwd=root).strip() != ""
    return {
        "pins_manifest_version": pins["calc_service"]["version"],
        "vendor_package_version": json.loads((vendor / "package.json").read_text())["version"],
        "vendor_tree": tree,
        "vendor_dirty": dirty,
    }


def node_modules_vs_lock(root: Path) -> dict[str, Any]:
    lock = json.loads((root / "package-lock.json").read_text())["packages"]
    hidden = root / "node_modules" / ".package-lock.json"
    if not hidden.is_file():
        return {"checked": 0, "missing": None, "mismatched": None, "error": "node_modules/.package-lock.json is missing"}
    installed = json.loads(hidden.read_text())["packages"]
    checked, missing, bad = 0, [], []
    for key, entry in sorted(lock.items()):
        if key == "":
            continue
        have = installed.get(key)
        if have is None:
            if not (entry.get("optional") or entry.get("os") or entry.get("cpu")):
                missing.append(key)
            continue
        checked += 1
        if have.get("integrity") != entry.get("integrity") or have.get("version") != entry.get("version"):
            bad.append(key)
    return {"checked": checked, "missing": sorted(missing), "mismatched": sorted(bad)}


def port_owner(port: int, root: Path) -> dict[str, Any]:
    """Who listens on 127.0.0.1:port and which git worktree it was started from (its cwd)."""
    pid = None
    if shutil.which("lsof"):
        out = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fp"], capture_output=True, text=True).stdout
        m = re.search(r"^p(\d+)$", out, re.M)
        pid = int(m.group(1)) if m else None
    elif Path("/proc/net/tcp").exists():
        inode = None
        for line in Path("/proc/net/tcp").read_text().splitlines()[1:]:
            parts = line.split()
            if parts[3] == "0A" and int(parts[1].split(":")[1], 16) == port:
                inode = parts[9]
        if inode:
            for fd in Path("/proc").glob("[0-9]*/fd/*"):
                try:
                    if os.readlink(fd) == f"socket:[{inode}]":
                        pid = int(fd.parts[2])
                        break
                except OSError:
                    continue
    if pid is None:
        return {"port": port, "listening": False}
    cwd = None
    if shutil.which("lsof"):
        out = subprocess.run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"], capture_output=True, text=True).stdout
        m = re.search(r"^n(.+)$", out, re.M)
        cwd = m.group(1) if m else None
    else:
        try:
            cwd = os.readlink(f"/proc/{pid}/cwd")
        except OSError:
            cwd = None
    cmd = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    top = _git_toplevel(Path(cwd)) if cwd else None
    return {
        "port": port, "listening": True, "pid": pid, "cwd": cwd, "command": cmd,
        "owner_toplevel": top, "same_worktree": top is not None and top == str(root.resolve()),
    }


def collect(root: Path, *, port: int = DEFAULT_PORT, allow_live: bool = False) -> dict[str, Any]:
    names = llm_env_names(root) + list(EXTRA_ENV)
    rec: dict[str, Any] = {
        "schema": "run_parameter_record_v1",
        "worktree": worktree_state(root),
        "date": {"fixed_now_utc": os.environ.get(ENV_FIXED_NOW)},
        "allow_live": allow_live,
        "calc_build": calc_build(root),
        "lockfiles": {n: _sha256(root / n) for n in ("package-lock.json", "uv.lock")},
        "node_modules_vs_lockfile": node_modules_vs_lock(root),
        "runtimes": {"python": sys.version.split()[0], "node": _run(["node", "--version"]).strip()},
        "port": port_owner(port, root),
        # presence only for secrets
        "env": {n: (("set" if os.environ.get(n) else None) if "KEY" in n else os.environ.get(n)) for n in sorted(set(names))},
        "run_time": {k: PENDING for k in RUN_TIME_FIELDS},
    }
    rec["record_sha256"] = record_hash(rec)
    return rec


def record_hash(rec: dict[str, Any]) -> str:
    body = {k: v for k, v in rec.items() if k != "record_sha256"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _flat(d: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(d, dict):
        out: dict[str, Any] = {}
        for k, v in d.items():
            out.update(_flat(v, f"{prefix}.{k}" if prefix else k))
        return out
    return {prefix: d}


def verify(root: Path, saved: dict[str, Any], *, port: int | None = None, allow_live: bool = False,
           allow_pending: bool = False) -> list[str]:
    """Return one message per mismatch, each naming the field."""
    errors: list[str] = []
    if saved.get("record_sha256") != record_hash(saved):
        errors.append("record_sha256: the saved record was edited after it was written")
    live = collect(root, port=port or saved["port"]["port"], allow_live=allow_live)
    if not saved["worktree"]["clean"]:
        errors.append("worktree.clean: the saved record was taken on a dirty tree")
    if not live["worktree"]["clean"]:
        errors.append("worktree.clean: the live worktree has uncommitted changes")
    if live["allow_live"] is not False:
        errors.append("allow_live: must be false for a gate run")
    for field in ("worktree.commit", "worktree.toplevel", "date.fixed_now_utc", "allow_live", "calc_build.pins_manifest_version",
                  "calc_build.vendor_package_version", "calc_build.vendor_tree", "lockfiles.package-lock.json",
                  "lockfiles.uv.lock", "runtimes.python", "runtimes.node"):
        a, b = _flat(saved).get(field), _flat(live).get(field)
        if a != b:
            errors.append(f"{field}: saved {a!r} != live {b!r}")
    if not saved["date"]["fixed_now_utc"]:
        errors.append(f"date.fixed_now_utc: {ENV_FIXED_NOW} was not set when the record was taken")
    if live["calc_build"]["vendor_dirty"]:
        errors.append("calc_build.vendor_dirty: vendor/smogon-calc differs from HEAD")
    nm = live["node_modules_vs_lockfile"]
    if nm.get("error"):
        errors.append(f"node_modules_vs_lockfile: {nm['error']}")
    elif nm["mismatched"] or nm["missing"]:
        errors.append(f"node_modules_vs_lockfile: mismatched {nm['mismatched'][:5]}, missing {nm['missing'][:5]}")
    p = live["port"]
    if not p["listening"]:
        errors.append(f"port.listening: nothing listens on {p['port']}")
    elif not p["same_worktree"]:
        errors.append(f"port.same_worktree: port {p['port']} is held by pid {p['pid']} started from {p['owner_toplevel'] or p['cwd']}")
    for name, val in saved["env"].items():
        if live["env"].get(name) != val:
            errors.append(f"env.{name}: saved {val!r} != live {live['env'].get(name)!r}")
    if not allow_pending:
        for name, val in saved["run_time"].items():
            if val == PENDING:
                errors.append(f"run_time.{name}: still {PENDING}")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--out", type=Path, required=True)
    v = sub.add_parser("verify")
    v.add_argument("record", type=Path)
    v.add_argument("--allow-pending", action="store_true")
    for sp in (c, v):
        sp.add_argument("--allow-live", choices=("true", "false"), default="false")
        sp.add_argument("--port", type=int, default=None)
        sp.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = ap.parse_args()
    allow_live = args.allow_live == "true"
    if args.mode == "collect":
        rec = collect(args.root, port=args.port or DEFAULT_PORT, allow_live=allow_live)
        args.out.write_text(json.dumps(rec, sort_keys=True, indent=1) + "\n")
        print(f"wrote {args.out} (record_sha256 {rec['record_sha256']})")
        return 0
    errors = verify(args.root, json.loads(args.record.read_text()), port=args.port, allow_live=allow_live,
                    allow_pending=args.allow_pending)
    if errors:
        print("FAIL run_params verify:")
        for e in errors:
            print(" -", e)
        return 1
    print("PASS run_params verify")
    return 0


if __name__ == "__main__":
    sys.exit(main())
