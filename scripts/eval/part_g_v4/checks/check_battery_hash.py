#!/usr/bin/env python3
"""Regenerate the seed-0 batteries into a temp directory and compare them byte-for-byte with the committed files.

Never writes to battery/. Fails when a regenerated file differs from the committed one, or when the committed
manifest's hashes do not match the committed files.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
BATTERY = PKG / "battery"
GEN = BATTERY / "generate_claim_battery.py"
FILES = ("claim_battery_v4.json", "false_legal_battery_v4.json", "battery_manifest.json")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    manifest = json.loads((BATTERY / "battery_manifest.json").read_text())
    errors = []
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run(
            [sys.executable, str(GEN), "--seed", "0", "--out-dir", tmp], cwd=str(PKG), capture_output=True, text=True
        )
        if proc.returncode != 0:
            print("FAIL generate:", proc.stdout, proc.stderr)
            return 1
        regen = Path(tmp)
        for name in FILES:
            if (regen / name).read_bytes() != (BATTERY / name).read_bytes():
                errors.append(f"{name}: committed {sha256_file(BATTERY / name)} != regenerated {sha256_file(regen / name)}")
    for key, name in (("claim_battery_sha256", FILES[0]), ("false_legal_battery_sha256", FILES[1])):
        if manifest[key] != sha256_file(BATTERY / name):
            errors.append(f"{name}: manifest {manifest[key]} != file {sha256_file(BATTERY / name)}")
    if errors:
        print("FAIL check_battery_hash:")
        for e in errors:
            print(" -", e)
        return 1
    print(f"PASS check_battery_hash: claim={manifest['claim_battery_sha256']} false_legal={manifest['false_legal_battery_sha256']}")
    slots = manifest.get("claim_slots_total") or manifest.get("realized_claims_total")
    by_type = manifest.get("claim_slot_counts_by_type") or manifest.get("realized_claim_counts_by_type")
    print(f"  claim_slots={slots} by_type={by_type}")
    rd = manifest.get("realized_definition") or {}
    print(f"  expected_scored≈{rd.get('expected_scored_claims_rounded')} @ answer_rate={rd.get('answer_rate_assumption')}")
    print(f"  gate_staircase={manifest['gate'].get('exact_min_scored_n_for_k_false')}")
    print(f"  expected_tolerance_false_claims={manifest['gate'].get('max_false_claims_passing_at_expected_scored')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
