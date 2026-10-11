#!/usr/bin/env python3
"""Regenerate claim battery and compare sha256 to battery_manifest.json."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
BATTERY = PKG / "battery"
GEN = BATTERY / "generate_claim_battery.py"
MANIFEST = BATTERY / "battery_manifest.json"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    before = json.loads(MANIFEST.read_text())
    expected = before["claim_battery_sha256"]
    fl_expected = before["false_legal_battery_sha256"]

    proc = subprocess.run(
        [sys.executable, str(GEN)],
        cwd=str(PKG),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print("FAIL generate:", proc.stdout, proc.stderr)
        return 1

    after = json.loads(MANIFEST.read_text())
    claim_hash = after["claim_battery_sha256"]
    fl_hash = after["false_legal_battery_sha256"]
    # Also verify file bytes match manifest
    file_hash = sha256_file(BATTERY / "claim_battery_v4.json")
    fl_file = sha256_file(BATTERY / "false_legal_battery_v4.json")

    errors = []
    if claim_hash != expected:
        errors.append(f"claim hash changed: {expected} -> {claim_hash}")
    if fl_hash != fl_expected:
        errors.append(f"false-legal hash changed: {fl_expected} -> {fl_hash}")
    if file_hash != claim_hash:
        errors.append(f"claim file sha mismatch manifest: file={file_hash} man={claim_hash}")
    if fl_file != fl_hash:
        errors.append(f"false-legal file sha mismatch: file={fl_file} man={fl_hash}")

    if errors:
        print("FAIL check_battery_hash:")
        for e in errors:
            print(" -", e)
        return 1
    print(f"PASS check_battery_hash: claim={claim_hash} false_legal={fl_hash}")
    slots = after.get("claim_slots_total") or after.get("realized_claims_total")
    by_type = after.get("claim_slot_counts_by_type") or after.get(
        "realized_claim_counts_by_type"
    )
    print(f"  claim_slots={slots} by_type={by_type}")
    rd = after.get("realized_definition") or {}
    print(
        f"  expected_scored≈{rd.get('expected_scored_claims_rounded')} "
        f"@ answer_rate={rd.get('answer_rate_assumption')}"
    )
    print(f"  gate_staircase={after['gate'].get('exact_min_scored_n_for_k_false')}")
    print(
        f"  expected_tolerance_false_claims="
        f"{after['gate'].get('max_false_claims_passing_at_expected_scored')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
