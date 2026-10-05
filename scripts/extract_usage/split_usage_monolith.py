#!/usr/bin/env python3
"""Split a monolithic usage snapshot into per-source files (schema v4).

Deterministic and idempotent: same monolith bytes → same split file bytes.
Used for B3a migration and for merge recovery after modify/delete on the monolith.

Example:

    uv run python -m scripts.extract_usage.split_usage_monolith \\
      --in data/usage/champions-reg-mc.v1.json

    # Merge recovery (after rebase onto main's monolith):
    uv run python -m scripts.extract_usage.split_usage_monolith \\
      --in data/usage/champions-reg-mc.v1.json --usage-dir data/usage
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from recommender.usage_split import (
    SCHEMA_VERSION,
    assemble_from_split,
    split_monolith,
)

assert SCHEMA_VERSION == 4


def _dump(obj: dict[str, Any]) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def write_split(
    monolith: dict[str, Any],
    *,
    usage_dir: Path,
    tag: str,
) -> tuple[Path, Path]:
    ingame_file, showdown_file = split_monolith(monolith)
    usage_dir.mkdir(parents=True, exist_ok=True)
    ingame_path = usage_dir / f"{tag}.ingame_doubles.v1.json"
    showdown_path = usage_dir / f"{tag}.showdown_doubles.v1.json"
    ingame_path.write_text(_dump(ingame_file), encoding="utf-8")
    showdown_path.write_text(_dump(showdown_file), encoding="utf-8")
    return ingame_path, showdown_path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--in",
        dest="in_path",
        type=Path,
        required=True,
        help="Monolithic usage JSON to split",
    )
    p.add_argument(
        "--usage-dir",
        type=Path,
        default=None,
        help="Output directory (default: parent of --in)",
    )
    p.add_argument(
        "--tag",
        default=None,
        help="File tag (default: meta.regulation or stem before .v1.json)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print paths and counts; write nothing",
    )
    args = p.parse_args(argv)

    if not args.in_path.exists():
        print(f"missing input: {args.in_path}", file=sys.stderr)
        return 1
    monolith = json.loads(args.in_path.read_text(encoding="utf-8"))
    tag = args.tag or str((monolith.get("meta") or {}).get("regulation") or "")
    if not tag:
        stem = args.in_path.name
        tag = stem[: -len(".v1.json")] if stem.endswith(".v1.json") else args.in_path.stem
    usage_dir = args.usage_dir or args.in_path.parent

    ingame_file, showdown_file = split_monolith(monolith)
    ingame_n = len((ingame_file.get("ingame_doubles") or {}).get("species") or {})
    sd_n = len((showdown_file.get("showdown_doubles") or {}).get("species") or {})
    assembled = assemble_from_split(ingame_file, showdown_file)
    summary = {
        "tag": tag,
        "usage_dir": str(usage_dir),
        "ingame_n": ingame_n,
        "showdown_n": sd_n,
        "flat_n": len(assembled.get("species") or {}),
        "ingame_out": str(usage_dir / f"{tag}.ingame_doubles.v1.json"),
        "showdown_out": str(usage_dir / f"{tag}.showdown_doubles.v1.json"),
    }
    print(json.dumps(summary, indent=2))
    if args.dry_run:
        return 0
    write_split(monolith, usage_dir=usage_dir, tag=tag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
