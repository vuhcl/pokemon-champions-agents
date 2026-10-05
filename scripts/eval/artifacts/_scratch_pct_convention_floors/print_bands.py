"""Print near-floor bands and propose holes (no constant edits)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = json.loads((ROOT / "distributions.json").read_text(encoding="utf-8"))


def main() -> None:
    for name, old in (
        ("usage_set_2.3", 2.3),
        ("trick_room_22.5", 22.5),
        ("setup_presence_0.1", 0.1),
        ("dd_presence_1.0", 1.0),
    ):
        block = DATA["distributions"][name]
        band = block.get("near_old_floor_band") or []
        print(f"\n==== {name} old={old} band_n={len(band)} clear_old={block.get('n_clear_old_floor')}/{block.get('n_eligible')}")
        prev = None
        for r in band:
            pct = float(r["pct"])
            gap = (float(prev["pct"]) - pct) if prev else 0.0
            mark = ""
            if abs(pct - old) < 0.3:
                mark += " <<<OLD"
            if gap >= 1.0:
                mark += f" GAP({gap:.3f})"
            sid = r.get("sid", "")
            move = r.get("move", "")
            src = r.get("max_source", "")
            print(f"{pct:8.3f} {sid:22} {move:14} {src:10} gap={gap:.3f}{mark}")
            prev = r


if __name__ == "__main__":
    main()
