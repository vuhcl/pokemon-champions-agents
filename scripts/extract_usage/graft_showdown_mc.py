#!/usr/bin/env python3
"""Graft Smogon chaos Showdown into champions-reg-mc.showdown_doubles.v1.json.

Format id must equal the registry Bo1 VGC chaos id for champions-reg-mc
(rejects bo3 / OU / BSS / …). Integrity: nonempty species + format match.
Absolute TEMPORARY battle/species floors are gone (B3a).

Example:

    uv run python -m scripts.extract_usage.graft_showdown_mc --month 2026-09
    uv run python -m scripts.extract_usage.graft_showdown_mc --month 2026-10 --force
    uv run python -m scripts.extract_usage.graft_showdown_mc --month 2026-10 --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from recommender.regulation_registry import REGULATIONS
from scripts.extract_usage.fetch_usage_mb import (
    extract_showdown_chaos,
    showdown_teammates_descriptor,
)
from scripts.extract_usage.fetch_usage_mc_munchstats import (
    EXPECTED_SHOWDOWN_FORMAT,
    REGULATION_TAG,
    SOURCE,
)
from recommender.usage_split import SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = (
    ROOT / "data" / "usage" / f"{REGULATION_TAG}.showdown_doubles.v1.json"
)

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _assert_format_allowed(format_id: str) -> None:
    """Exact Bo1 VGC format from the registry; reject bo3 and any other id."""
    expected = REGULATIONS[REGULATION_TAG]["showdown_format"]
    if format_id != expected:
        raise ValueError(
            f"format_id {format_id!r} != registry Bo1 VGC {expected!r} "
            f"(bo3/OU/BSS/other formats rejected)"
        )
    if "bo3" in format_id.lower():
        raise ValueError(f"format_id {format_id!r} looks like bo3; rejected")


def _fetch_chaos(
    month: str, format_id: str, rating: int
) -> tuple[dict[str, dict], dict]:
    try:
        return extract_showdown_chaos(month, format_id, rating)
    except SystemExit as e:
        raise RuntimeError(str(e) or "Smogon chaos fetch failed") from e


def graft(
    *,
    showdown: dict[str, dict],
    info: dict[str, Any],
    month: str,
    format_id: str,
    rating: int,
    extracted_at: str | None = None,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build showdown per-source file. Integrity: nonempty + format match."""
    del previous  # no cross-file preserve; this file is Showdown-only
    _assert_format_allowed(format_id)
    n = len(showdown)
    if n < 1:
        raise ValueError("showdown species empty")
    battles = info.get("number of battles")
    try:
        battles_n = int(battles) if battles is not None else 0
    except (TypeError, ValueError):
        battles_n = 0

    clock = extracted_at if extracted_at is not None else _utc_now_z()
    meta: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "regulation": REGULATION_TAG,
        "section": "showdown_doubles",
        "showdown_rating": rating,
        "showdown_format": format_id,
        "showdown_month": month,
        "showdown_source": "smogon-chaos",
        "showdown_pct_kind": "set",
        "showdown_move_limit": None,
        "showdown_battles": battles_n,
        "showdown_extracted_at": clock,
        "showdown_teammates_extracted_at": clock,
        "showdown_teammates": showdown_teammates_descriptor(),
        "attribution": (
            "Showdown VGC: Smogon chaos stats (set% = weight / Raw count; "
            "no move/item cap)."
        ),
        "sources": ["smogon-chaos"],
    }
    return {
        "meta": meta,
        "showdown_doubles": {"species": showdown},
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
    sd_n = len(((base.get("showdown_doubles") or {}).get("species")) or {})
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
    p.add_argument(
        "--force",
        action="store_true",
        help="Rewrite even when format/month/battles/species already match",
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

    previous = None
    if args.out.exists():
        try:
            previous = json.loads(args.out.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = None

    showdown, info = _fetch_chaos(args.month, args.format_id, args.rating)
    try:
        battles_n = int(info.get("number of battles") or 0)
    except (TypeError, ValueError):
        battles_n = 0

    if (
        previous is not None
        and already_grafted(
            previous,
            month=args.month,
            format_id=args.format_id,
            battles=battles_n,
            species_n=len(showdown),
        )
        and not args.force
    ):
        print(
            f"idempotent: already grafted {args.format_id} {args.month} "
            f"battles={battles_n} species={len(showdown)}",
            file=sys.stderr,
        )
        return 0

    try:
        out = graft(
            showdown=showdown,
            info=info,
            month=args.month,
            format_id=args.format_id,
            rating=args.rating,
            previous=previous,
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
        "showdown_extracted_at": (out.get("meta") or {}).get("showdown_extracted_at"),
        "forced": bool(args.force),
    }
    print(json.dumps(summary, indent=2))
    if args.dry_run:
        print("dry-run: not writing", file=sys.stderr)
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Wrote {args.out}", file=sys.stderr)
    # Invalidate usage loader cache if imported in-process.
    try:
        from recommender.usage_data import load_usage

        load_usage.cache_clear()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
