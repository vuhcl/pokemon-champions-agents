"""Fail if ability Phase B left open flags (do not silent-approve new abilities)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ABILITIES = ROOT / "data" / "abilities" / "all.v1.json"


def main() -> int:
    data = json.loads(ABILITIES.read_text(encoding="utf-8"))
    meta = data.get("meta") or {}
    phase_b = meta.get("phase_b") or {}
    flags_open = int(phase_b.get("flags_open") or 0)
    status = meta.get("taxonomy_status")
    if flags_open > 0:
        print(
            f"ability phase_b flags_open={flags_open} taxonomy_status={status!r} "
            "— refusing retarget/approve; human taxonomy required",
            file=sys.stderr,
        )
        return 1
    if status not in ("phase_b_flags_pending", "approved", "sample_pending_review"):
        # phase_b just ran → expect phase_b_flags_pending with flags_open 0
        print(f"unexpected taxonomy_status after phase_b: {status!r}", file=sys.stderr)
        return 1
    print(f"ability phase_b clear (flags_open=0, status={status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
