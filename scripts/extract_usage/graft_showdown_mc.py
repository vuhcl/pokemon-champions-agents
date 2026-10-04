#!/usr/bin/env python3
"""Graft Smogon chaos Showdown half into champions-reg-mc.v1.json (bridge).

Preserves MunchStats ingame + munchstats_* meta. Format id must be in the
TEMPORARY allowlist in fetch_usage_mc_munchstats (exact Bo1 VGC only).

Example:

    uv run python -m scripts.extract_usage.graft_showdown_mc --month 2026-09
    uv run python -m scripts.extract_usage.graft_showdown_mc --month 2026-09 --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from scripts.extract_usage.fetch_usage_mb import (
    extract_showdown_chaos,
    merge_species_flat,
)
from scripts.extract_usage.fetch_usage_mc_munchstats import (
    DEFAULT_OUT,
    EXPECTED_SHOWDOWN_FORMAT,
    SHOWDOWN_BATTLES_FLOOR,
    SHOWDOWN_FORMAT_ALLOWLIST,
    SHOWDOWN_SPECIES_FLOOR,
    SOURCE,
)

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def _assert_format_allowed(format_id: str) -> None:
    if format_id not in SHOWDOWN_FORMAT_ALLOWLIST:
        raise ValueError(
            f"format_id {format_id!r} not in SHOWDOWN_FORMAT_ALLOWLIST "
            f"{sorted(SHOWDOWN_FORMAT_ALLOWLIST)}"
        )


def _fetch_chaos(
    month: str, format_id: str, rating: int
) -> tuple[dict[str, dict], dict]:
    try:
        return extract_showdown_chaos(month, format_id, rating)
    except SystemExit as e:
        raise RuntimeError(str(e) or "Smogon chaos fetch failed") from e


def graft(
    *,
    base: dict[str, Any],
    showdown: dict[str, dict],
    info: dict[str, Any],
    month: str,
    format_id: str,
    rating: int,
) -> dict[str, Any]:
    battles = info.get("number of battles")
    try:
        battles_n = int(battles) if battles is not None else 0
    except (TypeError, ValueError):
        battles_n = 0
    n = len(showdown)
    if n < SHOWDOWN_SPECIES_FLOOR:
        raise ValueError(f"showdown species {n} < floor {SHOWDOWN_SPECIES_FLOOR}")
    if battles_n < SHOWDOWN_BATTLES_FLOOR:
        raise ValueError(
            f"showdown battles {battles_n} < floor {SHOWDOWN_BATTLES_FLOOR}"
        )

    meta = dict(base.get("meta") or {})
    meta["showdown_rating"] = rating
    meta["showdown_format"] = format_id
    meta["showdown_month"] = month
    meta["showdown_source"] = "smogon-chaos"
    meta["showdown_pct_kind"] = "set"
    meta["showdown_move_limit"] = None
    meta["showdown_battles"] = battles_n
    if "extracted_at" in (base.get("meta") or {}):
        meta["showdown_extracted_at"] = (base.get("meta") or {}).get("extracted_at")
    meta["attribution"] = (
        "In-game doubles: MunchStats champions-data branch "
        "(OCR capture via raw.githubusercontent.com). "
        "Showdown VGC: Smogon chaos stats (set% = weight / Raw count; "
        "no move/item cap)."
    )
    sources = list(meta.get("sources") or [])
    if SOURCE not in sources:
        sources.insert(0, SOURCE)
    if "smogon-chaos" not in sources:
        sources.append("smogon-chaos")
    meta["sources"] = sources

    ingame = ((base.get("ingame_doubles") or {}).get("species")) or {}
    return {
        "meta": meta,
        "ingame_doubles": base.get("ingame_doubles") or {"species": {}},
        "showdown_vgc_mb": {"species": showdown},
        "species": merge_species_flat(ingame, showdown),
    }


def already_grafted(
    base: dict[str, Any],
    *,
    month: str,
    format_id: str,
    battles: int,
    species_n: int,
) -> bool:
    meta = base.get("meta") or {}
    sd_n = len(((base.get("showdown_vgc_mb") or {}).get("species")) or {})
    try:
        base_battles = int(meta.get("showdown_battles") or 0)
    except (TypeError, ValueError):
        base_battles = 0
    return (
        meta.get("showdown_format") == format_id
        and meta.get("showdown_month") == month
        and base_battles == battles
        and sd_n == species_n
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--month", required=True, help="YYYY-MM Smogon stats month")
    p.add_argument("--format", default=EXPECTED_SHOWDOWN_FORMAT, dest="format_id")
    p.add_argument("--rating", type=int, default=1500)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change; write nothing",
    )
    args = p.parse_args(argv)

    if not _MONTH_RE.match(args.month):
        print(f"invalid --month {args.month!r} (want YYYY-MM)", file=sys.stderr)
        return 2
    try:
        _assert_format_allowed(args.format_id)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    if not args.out.exists():
        print(f"missing base file: {args.out}", file=sys.stderr)
        return 1
    base = json.loads(args.out.read_text(encoding="utf-8"))

    showdown, info = _fetch_chaos(args.month, args.format_id, args.rating)
    try:
        battles_n = int(info.get("number of battles") or 0)
    except (TypeError, ValueError):
        battles_n = 0

    if already_grafted(
        base,
        month=args.month,
        format_id=args.format_id,
        battles=battles_n,
        species_n=len(showdown),
    ):
        print(
            f"idempotent: already grafted {args.format_id} {args.month} "
            f"battles={battles_n} species={len(showdown)}",
            file=sys.stderr,
        )
        return 0

    try:
        out = graft(
            base=base,
            showdown=showdown,
            info=info,
            month=args.month,
            format_id=args.format_id,
            rating=args.rating,
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    summary = {
        "out": str(args.out),
        "showdown_format": args.format_id,
        "showdown_month": args.month,
        "showdown_battles": battles_n,
        "showdown_species_n": len(showdown),
        "ingame_n": len(((out.get("ingame_doubles") or {}).get("species")) or {}),
        "flat_n": len(out.get("species") or {}),
        "munchstats_generated_at": (out.get("meta") or {}).get("munchstats_generated_at"),
    }
    print(json.dumps(summary, indent=2))
    if args.dry_run:
        print("dry-run: not writing", file=sys.stderr)
        return 0

    args.out.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
