#!/usr/bin/env python3
"""Frozen manifest for the Part G *state* arm (draft until Vu approves).

    uv run python -m scripts.eval.part_g_arm.state.freeze_manifest_arm_state write
    uv run python -m scripts.eval.part_g_arm.state.freeze_manifest_arm_state verify

write: (re)write FROZEN_MANIFEST_ARM_STATE.json from FILES (does not set git freeze).
verify: exit 0 only when (1) git working tree is clean and (2) every listed sha matches.
         Fails on a dirty tree even if file bytes match the manifest.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "FROZEN_MANIFEST_ARM_STATE.json"
STATE = "scripts/eval/part_g_arm/state/"

FILES = [
    STATE + "prompt.md",
    STATE + "tools.py",
    STATE + "covered_list.json",
    STATE + "errata.json",
    STATE + "errata_read.py",
    STATE + "request_set_runner.py",
    STATE + "exploratory_runner.py",
    STATE + "class_scorer.py",
    STATE + "compare_runs.py",
    STATE + "hand_audit_form.py",
    STATE + "judge_prompt.md",
    STATE + "harness.py",
    STATE + "pending.py",
    STATE + "fixtures.py",
    STATE + "dev_keys.json",
    STATE + "dev_keys_prankster_weather.json",
    STATE + "dev_rows.json",
    STATE + "b1_discovery.json",
    STATE + "clopper_pearson.py",
    STATE + "freeze_manifest_arm_state.py",
    STATE + "seeds/SHA256SUMS",
    STATE + "seeds/cs_pending.json",
    STATE + "seeds/fbc_pending.json",
    STATE + "seeds/hc2_after_t1.json",
    STATE + "seeds/hd1_history.json",
    STATE + "seeds/mt3_after_t1.json",
    "scripts/eval/part_g_arm/config.py",
    "scripts/eval/run_params.py",
]


def sha256(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


def table() -> dict[str, str]:
    return {rel: sha256(rel) for rel in sorted(FILES)}


def manifest_sha256(files: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def git_dirty() -> list[str]:
    """Return porcelain lines if the worktree is dirty; empty if clean."""
    out = subprocess.check_output(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        text=True,
    )
    return [ln for ln in out.splitlines() if ln.strip()]


def differences() -> list[str]:
    saved = json.loads(MANIFEST.read_text(encoding="utf-8"))
    now = table()
    out = [
        f"{rel}: manifest {saved['files'].get(rel, 'absent')[:12]} != now {h[:12]}"
        for rel, h in now.items()
        if saved["files"].get(rel) != h
    ]
    out += [f"{rel}: listed in the manifest but no longer in FILES" for rel in saved["files"] if rel not in now]
    if saved.get("manifest_sha256") != manifest_sha256(saved["files"]):
        out.append("manifest_sha256 does not match the file table")
    return out


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1 or argv[0] not in ("write", "verify"):
        print(__doc__, file=sys.stderr)
        return 2
    if argv[0] == "write":
        files = table()
        doc = {
            "schema": "part_g_arm_state_frozen_manifest_v0",
            "status": "draft",
            "note": (
                "DRAFT only — Vu must approve before treating as frozen. "
                "verify requires a clean git tree. Do not set status=frozen until then."
            ),
            "files": files,
            "manifest_sha256": manifest_sha256(files),
            "model": {
                "id": "qwen3.5:latest",
                "digest": "44a38603922e14f1e3ae68c5d900cc39f2a925a9749d12ab6d268d75a01a399f",
                "temperature": 0.0,
                "think": False,
                "num_ctx": 16384,
                "num_predict": 2048,
            },
            "prompt_sha256": files[STATE + "prompt.md"],
            "tools_py_sha256": files[STATE + "tools.py"],
            "covered_list_sha256": files[STATE + "covered_list.json"],
            "keys_sha256": "e70672541b5215e7bfff7eccb34dc321b2bde3a4b9cf08d1f5a6419be1d2309a",
        }
        MANIFEST.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(
            f"wrote {MANIFEST.name}: {len(files)} files, "
            f"manifest sha256 {doc['manifest_sha256']} (status=draft)"
        )
        return 0

    if not MANIFEST.is_file():
        print("FAIL: FROZEN_MANIFEST_ARM_STATE.json missing — run write first", file=sys.stderr)
        return 1
    dirty = git_dirty()
    if dirty:
        print("FAIL frozen manifest: dirty git tree (clean tree required):")
        for ln in dirty[:40]:
            print(f" - {ln}")
        if len(dirty) > 40:
            print(f" - … {len(dirty) - 40} more")
        return 1
    diff = differences()
    print("PASS frozen manifest (clean tree)" if not diff else "FAIL frozen manifest:\n - " + "\n - ".join(diff))
    return 1 if diff else 0


if __name__ == "__main__":
    raise SystemExit(main())
