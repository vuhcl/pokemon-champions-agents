#!/usr/bin/env python3
"""Fail if committed derived_keys.json contains any truthy \"error\" leaf.

Builders that read offline Showdown cache must hard-fail instead of writing
error strings into the keys (see key_artifacts/SHOWDOWN_CACHE.md).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
KEYS = PKG / "key_artifacts" / "derived_keys.json"


def walk_errors(obj, path: str = "") -> list[tuple[str, object]]:
    found: list[tuple[str, object]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else str(k)
            if k == "error" and v not in (None, "", False, 0):
                found.append((p, v))
            found.extend(walk_errors(v, p))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found.extend(walk_errors(v, f"{path}[{i}]"))
    return found


def main() -> int:
    if not KEYS.is_file():
        print(f"FAIL check_keys_no_error_fields: missing {KEYS}")
        return 1
    data = json.loads(KEYS.read_text())
    errs = walk_errors(data)
    if errs:
        print(f"FAIL check_keys_no_error_fields: {len(errs)} truthy error leaf(ves)")
        for p, v in errs[:20]:
            preview = repr(v)
            if len(preview) > 120:
                preview = preview[:117] + "..."
            print(f"  {p}: {preview}")
        return 1
    print("PASS check_keys_no_error_fields: no truthy error leaves in derived_keys.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
