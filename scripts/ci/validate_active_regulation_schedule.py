"""Validate data/active_regulation.json ends against Champions-news Duration pages.

Uses the same scan_for_letter scraper as ADR-065's regulation_extract_gate.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from scripts.ci.champions_news import scan_for_letter

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEDULE_PATH = ROOT / "data" / "active_regulation.json"


def _parse_utc(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def validate_schedule_against_news(
    *,
    schedule_path: Path | None = None,
    fetch: Callable[[str], str] | None = None,
    start_page_id: int | None = None,
    window: int = 80,
) -> list[str]:
    """Return mismatch warnings (empty if schedule matches news Duration windows)."""
    path = schedule_path or DEFAULT_SCHEDULE_PATH
    raw = json.loads(path.read_text(encoding="utf-8"))
    bookmark = start_page_id
    if bookmark is None:
        bookmark = int(raw.get("news_bookmark_page_id") or 816)
    warnings: list[str] = []
    kwargs: dict = {"start_page_id": bookmark, "window": window}
    if fetch is not None:
        kwargs["fetch"] = fetch
    for row in raw.get("regulations") or []:
        letter = str(row["letter"]).upper()
        scheduled_end = _parse_utc(str(row["end"]))
        scheduled_start = _parse_utc(str(row["start"]))
        page = scan_for_letter(letter, **kwargs)
        if page.start_utc != scheduled_start or page.end_utc != scheduled_end:
            warnings.append(
                f"schedule_mismatch M-{letter}: schedule "
                f"[{scheduled_start.isoformat()} .. {scheduled_end.isoformat()}) "
                f"vs news [{page.start_utc.isoformat()} .. {page.end_utc.isoformat()}]"
            )
    return warnings


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--schedule",
        type=Path,
        default=DEFAULT_SCHEDULE_PATH,
        help="Path to active_regulation.json",
    )
    p.add_argument(
        "--start-page-id",
        type=int,
        default=None,
        help="Champions-news scan start id (default: schedule news_bookmark_page_id)",
    )
    p.add_argument("--window", type=int, default=80)
    args = p.parse_args(argv)
    # Historical letters (e.g. M-B at 776) sit before the current bookmark (816).
    start = args.start_page_id
    if start is None:
        raw = json.loads(args.schedule.read_text(encoding="utf-8"))
        bookmark = int(raw.get("news_bookmark_page_id") or 816)
        start = max(1, bookmark - 80)
    warnings = validate_schedule_against_news(
        schedule_path=args.schedule,
        start_page_id=start,
        window=args.window,
    )
    if warnings:
        for w in warnings:
            print(w, file=sys.stderr)
        print(f"FAIL: {len(warnings)} schedule mismatch(es)", file=sys.stderr)
        return 1
    print(
        f"OK: schedule matches Champions-news Duration pages "
        f"(start_page_id={start}, window={args.window})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
