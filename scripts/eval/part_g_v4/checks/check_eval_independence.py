#!/usr/bin/env python3
"""Static check: part_g_v4 eval code must not import recommender (ADR-060)."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
BANNED_MODULES = {
    "recommender",
    "recommender.legality",
    "recommender.calc_client",
    "recommender.items",
    "recommender.moves",
}
BANNED_NAMES = {
    "TYPE_BOOST_ITEMS",
    "species_has_damaging_type_move",
    "mega_stones_by_item_id",
}


def check_file(path: Path) -> list[str]:
    errors = []
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as e:
        return [f"{path}: syntax error: {e}"]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root == "recommender" or alias.name in BANNED_MODULES:
                    errors.append(f"{path}:{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            root = mod.split(".")[0] if mod else ""
            if root == "recommender" or mod in BANNED_MODULES:
                errors.append(f"{path}:{node.lineno}: from {mod} import ...")
            for alias in node.names:
                if alias.name in BANNED_NAMES:
                    errors.append(f"{path}:{node.lineno}: imports banned name {alias.name}")
    return errors


def main() -> int:
    py_files = sorted(PKG.rglob("*.py"))
    errors: list[str] = []
    for path in py_files:
        if "__pycache__" in str(path):
            continue
        errors.extend(check_file(path))

    if errors:
        print("FAIL check_eval_independence:")
        for e in errors:
            print(" -", e)
        return 1
    print(f"PASS check_eval_independence: scanned {len(py_files)} files; no recommender imports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
