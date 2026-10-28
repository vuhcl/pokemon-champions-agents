"""Re-emit Part 0 not-covered re-triage table from part0_retriage.json (report only)."""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "part0_retriage.json"


def main() -> None:
    doc = json.loads(SRC.read_text(encoding="utf-8"))
    rows = doc["rows"]
    print(f"rows={len(rows)} coverable_now={doc['coverable_now_ids']}")
    print("| id | coverable_now | needs | scorable |")
    print("|---|---|---|---|")
    for r in rows:
        print(
            f"| {r['id']} | {'yes' if r['coverable_now'] else 'no'} | "
            f"{r['needs']} | {r['scorable']} |"
        )


if __name__ == "__main__":
    main()
