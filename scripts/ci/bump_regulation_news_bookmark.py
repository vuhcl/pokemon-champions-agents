"""Bump regulation_news_bookmark.json from a successful gate extract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOOKMARK = ROOT / "data" / "legality" / "fixtures" / "regulation_news_bookmark.json"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gate", type=Path, required=True)
    args = p.parse_args(argv)
    gate = json.loads(args.gate.read_text(encoding="utf-8"))
    page_id = gate.get("news_page_id")
    letter = gate.get("live_letter")
    if page_id is None or not letter:
        print(
            "gate missing news_page_id/live_letter — not bumping bookmark",
            file=sys.stderr,
        )
        return 1
    bm = {
        "last_seen_page_id": int(page_id),
        "letter": str(letter).upper(),
        "note": (
            "champions-news.pokemon-home.com /en/page/{id}.html — "
            "page id is not a calendar date"
        ),
    }
    BOOKMARK.write_text(json.dumps(bm, indent=2) + "\n", encoding="utf-8")
    print(f"bumped bookmark → page_id={page_id} letter={letter}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
