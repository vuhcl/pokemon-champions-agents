"""CAP / nonstandard provenance on the move-accuracy snapshot."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACCURACY_PATH = ROOT / "data" / "moves" / "gen9_accuracy.v1.json"
CAP_MOVES = ("paleowave", "shadowstrike", "polarflare")


def test_cap_moves_flagged_in_accuracy_table():
    acc = json.loads(ACCURACY_PATH.read_text())
    for mid in CAP_MOVES:
        assert acc[mid]["is_nonstandard"] == "CAP", mid


def test_every_accuracy_entry_has_is_nonstandard():
    acc = json.loads(ACCURACY_PATH.read_text())
    for mid, e in acc.items():
        assert "is_nonstandard" in e, mid
    non_null = sum(1 for e in acc.values() if e.get("is_nonstandard") is not None)
    assert non_null == 454
    assert any(e.get("is_nonstandard") == "Past" for e in acc.values())
    assert any(e.get("is_nonstandard") == "LGPE" for e in acc.values())
