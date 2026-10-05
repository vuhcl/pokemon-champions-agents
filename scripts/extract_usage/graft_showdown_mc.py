#!/usr/bin/env python3
"""Graft Smogon chaos Showdown into champions-reg-mc.showdown_doubles.v1.json.

Format id must equal the registry Bo1 VGC chaos id for champions-reg-mc
(rejects bo3 / OU / BSS / …). Integrity: nonempty species + format match.
Absolute TEMPORARY battle/species floors are gone (B3a).

Example:

    uv run python -m scripts.extract_usage.graft_showdown_mc --from-meta --force
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
from recommender.usage_chaos import (
    SHOWDOWN_PCT_KIND_PUBLISHED,
    fallback_counts_from_species,
)
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


def _assert_format_allowed(
    format_id: str, *, regulation: str = REGULATION_TAG
) -> None:
    """Exact Bo1 VGC format from the registry; reject bo3 and any other id."""
    reg = REGULATIONS.get(regulation) or {}
    expected = reg.get("showdown_format")
    if not expected:
        raise ValueError(f"unknown regulation {regulation!r} (no showdown_format)")
    if format_id != expected:
        raise ValueError(
            f"format_id {format_id!r} != registry Bo1 VGC {expected!r} "
            f"(bo3/OU/BSS/other formats rejected)"
        )


def showdown_out_path(regulation: str = REGULATION_TAG) -> Path:
    return ROOT / "data" / "usage" / f"{regulation}.showdown_doubles.v1.json"


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
    regulation: str = REGULATION_TAG,
) -> dict[str, Any]:
    """Build showdown per-source file. Integrity: nonempty + format match."""
    _assert_format_allowed(format_id, regulation=regulation)
    n = len(showdown)
    if n < 1:
        raise ValueError("showdown species empty")
    battles = info.get("number of battles")
    try:
        battles_n = int(battles) if battles is not None else 0
    except (TypeError, ValueError):
        battles_n = 0

    clock = extracted_at if extracted_at is not None else _utc_now_z()
    fallbacks = fallback_counts_from_species(showdown)
    meta: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "regulation": regulation,
        "section": "showdown_doubles",
        "showdown_rating": rating,
        "showdown_format": format_id,
        "showdown_month": month,
        "showdown_source": "smogon-chaos",
        "showdown_pct_kind": SHOWDOWN_PCT_KIND_PUBLISHED,
        "showdown_move_limit": None,
        "showdown_battles": battles_n,
        "showdown_extracted_at": clock,
        "showdown_teammates_extracted_at": clock,
        "showdown_teammates": showdown_teammates_descriptor(),
        **fallbacks,
        "attribution": (
            "Showdown VGC: Smogon chaos stats "
            "(common_* pct = weight / sum(Abilities); "
            "top_spreads[].pct = raw chaos Spreads weight; "
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
    p.add_argument(
        "--month",
        default=None,
        help="YYYY-MM Smogon stats month (required unless --from-meta)",
    )
    p.add_argument(
        "--from-meta",
        action="store_true",
        help=(
            "Read showdown_month / showdown_format / showdown_rating from the "
            "existing out-file meta (default M-C path)"
        ),
    )
    p.add_argument(
        "--regulation",
        default=REGULATION_TAG,
        help=f"Regulation file tag (default {REGULATION_TAG})",
    )
    p.add_argument("--format", default=None, dest="format_id")
    p.add_argument("--rating", type=int, default=None)
    p.add_argument("--out", type=Path, default=None)
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

    regulation = str(args.regulation)
    reg = REGULATIONS.get(regulation) or {}
    expected = reg.get("showdown_format")
    if not expected:
        print(f"unknown regulation {regulation!r}", file=sys.stderr)
        return 2
    out_path = args.out or showdown_out_path(regulation)

    previous = None
    if out_path.exists():
        try:
            previous = json.loads(out_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = None

    month = args.month
    format_id = args.format_id or expected
    rating = args.rating if args.rating is not None else 1500
    if args.from_meta:
        meta = (previous or {}).get("meta") or {}
        month = str(meta.get("showdown_month") or "") or month
        format_id = str(meta.get("showdown_format") or "") or format_id
        try:
            rating = int(meta.get("showdown_rating") or rating)
        except (TypeError, ValueError):
            pass
        if not month:
            print(
                f"--from-meta requires showdown_month in {out_path}",
                file=sys.stderr,
            )
            return 2

    if not month:
        print("need --month YYYY-MM or --from-meta", file=sys.stderr)
        return 2
    if not _MONTH_RE.match(month):
        print(f"invalid --month {month!r} (want YYYY-MM)", file=sys.stderr)
        return 2
    try:
        _assert_format_allowed(format_id, regulation=regulation)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    showdown, info = _fetch_chaos(month, format_id, rating)
    try:
        battles_n = int(info.get("number of battles") or 0)
    except (TypeError, ValueError):
        battles_n = 0

    if (
        previous is not None
        and already_grafted(
            previous,
            month=month,
            format_id=format_id,
            battles=battles_n,
            species_n=len(showdown),
        )
        and not args.force
    ):
        print(
            f"idempotent: already grafted {format_id} {month} "
            f"battles={battles_n} species={len(showdown)}",
            file=sys.stderr,
        )
        return 0

    try:
        out = graft(
            showdown=showdown,
            info=info,
            month=month,
            format_id=format_id,
            rating=rating,
            regulation=regulation,
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    summary = {
        "out": str(out_path),
        "regulation": regulation,
        "showdown_format": format_id,
        "showdown_month": month,
        "showdown_battles": battles_n,
        "showdown_species_n": len(showdown),
        "showdown_extracted_at": (out.get("meta") or {}).get("showdown_extracted_at"),
        "showdown_pct_kind": (out.get("meta") or {}).get("showdown_pct_kind"),
        "forced": bool(args.force),
        "from_meta": bool(args.from_meta),
    }
    print(json.dumps(summary, indent=2))
    if args.dry_run:
        print("dry-run: not writing", file=sys.stderr)
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Wrote {out_path}", file=sys.stderr)
    # Invalidate usage loader cache if imported in-process.
    try:
        from recommender.usage_data import load_usage

        load_usage.cache_clear()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
