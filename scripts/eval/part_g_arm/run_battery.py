#!/usr/bin/env python3
"""Run the arm over a claim battery and write one JSONL answer record per item (no keys are read).

    python scripts/eval/part_g_arm/run_battery.py --battery dev_seed1/claim_battery_v4.json --out runs/dev1 [--limit 5]

Seed 0 is the held-out battery: the runner refuses it unless HEAD is --registration-commit, the tree is clean, that
commit's docs/pre_registration.md has a "## PRE-MD-CLAIM" section, and --run-params RECORD verifies. The calc service must be up
on the port in the config and started from this worktree.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.eval.part_g_arm.config import ArmConfig, system_prompt_hash  # noqa: E402

FROZEN_DIR = (ROOT / "scripts/eval/part_g_v4/battery").resolve()
OLLAMA = "http://127.0.0.1:11434"


def _run_params():
    spec = importlib.util.spec_from_file_location("run_params", ROOT / "scripts/eval/run_params.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_params"] = mod
    spec.loader.exec_module(mod)
    return mod


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout


def seed0_gate(battery: Path, record: Path | None, registration_commit: str | None, *, root: Path = ROOT, verify=None) -> None:
    """Refuse the seed-0 battery unless HEAD is the registration commit, the tree is clean, that commit's
    docs/pre_registration.md has a "## PRE-MD-CLAIM" section, and run_params verification passes."""
    if FROZEN_DIR not in battery.resolve().parents and json.loads(battery.read_text()).get("seed") != 0:
        return
    if record is None or registration_commit is None:
        raise SystemExit("refused: seed 0 is held out; needs --run-params and --registration-commit")
    try:
        want = _git(root, "rev-parse", "--verify", f"{registration_commit}^{{commit}}").strip()
    except subprocess.CalledProcessError:
        raise SystemExit(f"refused: {registration_commit} is not a commit in {root}") from None
    if _git(root, "rev-parse", "HEAD").strip() != want:
        raise SystemExit(f"refused: HEAD is not the registration commit {want}")
    if _git(root, "status", "--porcelain").strip():
        raise SystemExit("refused: the worktree is not clean")
    try:
        doc = _git(root, "show", f"{want}:docs/pre_registration.md")
    except subprocess.CalledProcessError:
        doc = ""
    if not any(line.startswith("## PRE-MD-CLAIM") for line in doc.splitlines()):
        raise SystemExit(f"refused: no '## PRE-MD-CLAIM' section in docs/pre_registration.md at {want}")
    errors = (verify or _run_params().verify)(root, json.loads(record.read_text()), allow_pending=True)
    if errors:
        raise SystemExit("refused: run_params verification failed:\n - " + "\n - ".join(errors))


def _ollama(path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(OLLAMA + path, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"} if body else {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def model_facts(cfg: ArmConfig) -> dict:
    digest = next((m["digest"] for m in _ollama("/api/tags")["models"] if m["name"] == cfg.model), None)
    if digest != cfg.model_digest:
        raise SystemExit(f"refused: {cfg.model} digest {digest} != pinned {cfg.model_digest}")
    return {"digest": digest, "modelfile_parameters": _ollama("/api/show", {"model": cfg.model}).get("parameters", "")}


def write_record(cfg: ArmConfig, out: Path, facts: dict) -> dict:
    rp = _run_params()
    rec = rp.collect(ROOT, allow_live=False)
    rec["arm_config"] = cfg.to_dict()
    pending = rp.PENDING
    rec["run_time"] = {
        "num_ctx": cfg.num_ctx,
        "num_predict": cfg.num_predict,
        "fixed_now_utc": cfg.fixed_now_utc or pending,
        "calc_process": {**{k: v for k, v in rec["port"].items() if k in ("pid", "command", "cwd", "owner_toplevel", "same_worktree")},
                         "source_sha256": {n: hashlib.sha256((ROOT / "services/calc" / n).read_bytes()).hexdigest()
                                           for n in ("server.ts", "handlers.ts", "recoil.ts")}},
        "model_digest": facts["digest"],
        "decoding_parameters": {"temperature": cfg.temperature, "num_ctx": cfg.num_ctx, "num_predict": cfg.num_predict,
                                "modelfile_defaults_left_as_is": facts["modelfile_parameters"]},
        "seed": None,
        "think_setting": cfg.think,
        "system_prompt_hash": system_prompt_hash(),
        "max_turns": cfg.max_turns,
        "timeouts": {"call_s": cfg.call_timeout_s, "item_s": cfg.item_timeout_s, "run_s": cfg.run_timeout_s},
    }
    rec["record_sha256"] = rp.record_hash(rec)
    (out / "run_params.json").write_text(json.dumps(rec, sort_keys=True, indent=1) + "\n")
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--battery", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=None, help="first N items")
    ap.add_argument("--ids", nargs="+", default=None)
    ap.add_argument("--run-params", type=Path, default=None)
    ap.add_argument("--registration-commit", default=None)
    ap.add_argument("--fixed-now", default=None, help="RECOMMENDER_FIXED_NOW_UTC; unset is recorded as pending_at_run")
    args = ap.parse_args()
    seed0_gate(args.battery, args.run_params, args.registration_commit)

    from scripts.eval.part_g_arm.loop import ArmLoop  # after the gate: nothing heavy loads for a refusal

    fixed = args.fixed_now or os.environ.get("RECOMMENDER_FIXED_NOW_UTC")
    cfg = dataclasses.replace(ArmConfig(), fixed_now_utc=fixed)
    items = json.loads(args.battery.read_text())["items"]
    if args.ids:
        items = [i for i in items if i["id"] in set(args.ids)]
    if args.limit:
        items = items[: args.limit]
    args.out.mkdir(parents=True, exist_ok=True)
    arm = ArmLoop(cfg)
    try:
        arm.tools.calc.health()
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"calc service is down at {cfg.calc_base_url} ({exc}); start it (npm start) from this worktree") from None
    facts = model_facts(cfg)
    write_record(cfg, args.out, facts)
    answers = args.out / "answers.jsonl"
    done = {json.loads(line)["id"] for line in answers.read_text().splitlines()} if answers.exists() else set()
    t0 = time.monotonic()
    with answers.open("a") as fh:
        for it in items:
            if it["id"] in done:
                continue
            if time.monotonic() - t0 > cfg.run_timeout_s:
                print("run timeout reached; stopping")
                break
            rec = {"id": it["id"], "claim_type": it["claim_type"], **arm.run_item(it["prompt"])}
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
            fh.flush()
            print(f"{rec['id']}: {rec['stop_reason']} turns={rec['turns']} tools={len(rec['tool_calls'])} {rec['wall_s']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
