#!/usr/bin/env python3
"""Verify pins_manifest.json against files at PR base (current checkout)."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
ROOT = PKG.parents[2]
MANIFEST = PKG / "pins_manifest.json"

EXPECTED_BLOB = {
    "data/legality/champions.v1.json": "ca5bb8181448765875396ce3b02561923c3e4694",
    "data/usage/champions-reg-mc.ingame_doubles.v1.json": "e21ebb1fb8c75b1c018ff05fe7d3e487b15e1a2e",
    "data/usage/champions-reg-mc.showdown_doubles.v1.json": "63bcefe4512a202d75b62e79f2ccc5436527b46e",
    "data/moves/static.v1.json": "c4f2aabe8ffb420a70e77afaa50b5a4d616a1f54",
    "data/moves/flags.v1.json": "89a00b2c46df4c139027f81f77627a4a85fdd631",
    "data/moves/gen9_accuracy.v1.json": "4eeb96eacfdee56ccaf7e9a7b8d6a65c6fb1da20",
    "data/moves/stat_boosts.v1.json": "040059884684b27f0894e484c7c987fb5aef158e",
}


def content_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_blob_sha(path: Path) -> str:
    return (
        subprocess.check_output(["git", "hash-object", str(path)], cwd=str(ROOT))
        .decode()
        .strip()
    )


def main() -> int:
    if not MANIFEST.is_file():
        print("FAIL check_pins: pins_manifest.json missing")
        return 1
    man = json.loads(MANIFEST.read_text())
    errors = []
    mismatches = []

    for rel, expected_blob in EXPECTED_BLOB.items():
        path = ROOT / rel
        if not path.is_file():
            errors.append(f"missing pin file: {rel}")
            continue
        blob = git_blob_sha(path)
        csha = content_sha256(path)
        entry = next((p for p in man.get("pins", []) if p.get("path") == rel), None)
        if entry is None:
            errors.append(f"manifest missing pin: {rel}")
            continue
        if entry.get("git_blob_sha") != blob:
            mismatches.append(f"{rel}: manifest blob {entry.get('git_blob_sha')} != file {blob}")
        if entry.get("content_sha256") != csha:
            mismatches.append(f"{rel}: manifest content sha mismatch")
        if blob != expected_blob:
            mismatches.append(f"{rel}: file blob {blob} != expected {expected_blob}")

    if man.get("refresh_merge") != "6674b74c41810f63d1a25453d26ea8498d0b9341":
        errors.append(f"refresh_merge mismatch: {man.get('refresh_merge')}")
    if man.get("eval_pin_repo_commit") != "e935de9b2051da6fe968b87087b27c7b5901168b":
        errors.append(f"eval_pin_repo_commit mismatch: {man.get('eval_pin_repo_commit')}")

    if errors or mismatches:
        print("FAIL check_pins:")
        for e in errors + mismatches:
            print(" -", e)
        return 1
    print(f"PASS check_pins: {len(EXPECTED_BLOB)} pins match; calc={man.get('calc_service')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
