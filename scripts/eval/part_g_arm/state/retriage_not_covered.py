"""Re-emit not-covered re-triage table (report only).

Default: part0_retriage_final.json (2026-10-28). Pass --legacy for 2026-10-27 part0_retriage.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--legacy",
        action="store_true",
        help="use part0_retriage.json (2026-10-27) instead of part0_retriage_final.json",
    )
    args = p.parse_args(argv)
    src = HERE / ("part0_retriage.json" if args.legacy else "part0_retriage_final.json")
    doc = json.loads(src.read_text(encoding="utf-8"))
    rows = doc["rows"]
    print(f"src={src.name} rows={len(rows)} coverable_now={doc['coverable_now_ids']}")
    print("| id | coverable_now | blocker | scorable |")
    print("|---|---|---|---|")
    for r in rows:
        blocker = r.get("blocker") or r.get("needs") or ""
        print(
            f"| {r['id']} | {'yes' if r['coverable_now'] else 'no'} | "
            f"{blocker} | {r['scorable']} |"
        )


if __name__ == "__main__":
    main()
