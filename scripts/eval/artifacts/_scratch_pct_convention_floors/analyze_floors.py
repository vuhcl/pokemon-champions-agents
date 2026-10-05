"""One-shot floor-distribution analysis for Step 1 commit-2 review (no constant edits)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = json.loads((ROOT / "distributions.json").read_text(encoding="utf-8"))


def _rows(block: dict) -> list[dict]:
    for key in ("sorted_desc", "all", "full", "rows", "top40"):
        if isinstance(block.get(key), list) and block[key]:
            return list(block[key])
    return []


def analyze(name: str, old: float) -> None:
    block = DATA["distributions"][name]
    rows = _rows(block)
    gaps = block.get("gaps") or []
    print(f"\n======= {name} old={old} =======")
    print("keys", sorted(block.keys()))
    print(
        "n_elig",
        block.get("n_eligible"),
        "n_clear_old",
        block.get("n_clear_old_floor"),
        "n_rows",
        len(rows),
        "n_gaps",
        len(gaps),
    )
    for g in gaps[:25]:
        print(" GAP", json.dumps(g, sort_keys=True))
    # Print descending series near/below old floor and notable gaps
    for i, r in enumerate(rows):
        pct = float(r["pct"])
        if pct > max(old * 3, old + 30) and i < 5:
            continue
        prev = rows[i - 1] if i else None
        gap = (float(prev["pct"]) - pct) if prev else 0.0
        interesting = (
            pct <= max(old + 25, 40)
            or gap >= 1.0
            or abs(pct - old) < 1.0
            or pct < 0.05
        )
        if not interesting and pct > old + 25:
            continue
        if pct < 0 and False:
            break
        sid = r.get("sid", "")
        move = r.get("move", "")
        src = r.get("max_source", "")
        mark = " <<<" if abs(pct - old) < 0.5 else ""
        if gap >= 1.0 or abs(pct - old) < 2 or pct <= old + 5:
            print(
                f"  {pct:8.3f} {sid:22} {move:16} {src:10} gap={gap:.3f}{mark}"
            )


def main() -> None:
    for name, old in (
        ("usage_set_2.3", 2.3),
        ("trick_room_22.5", 22.5),
        ("setup_presence_0.1", 0.1),
        ("dd_presence_1.0", 1.0),
    ):
        analyze(name, old)


if __name__ == "__main__":
    main()
