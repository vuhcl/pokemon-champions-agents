"""M-C Showdown common_moves must carry stamped chaos weights."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MC_SHOWDOWN = ROOT / "data" / "usage" / "champions-reg-mc.showdown_doubles.v1.json"


def test_mc_showdown_every_common_move_has_weight():
    data = json.loads(MC_SHOWDOWN.read_text(encoding="utf-8"))
    species = (data.get("showdown_doubles") or {}).get("species") or {}
    assert species, "expected showdown_doubles.species"
    missing: list[str] = []
    for sid, row in species.items():
        for i, m in enumerate(row.get("common_moves") or []):
            w = m.get("weight") if isinstance(m, dict) else None
            if not isinstance(m, dict) or "weight" not in m:
                missing.append(f"{sid}[{i}]")
                continue
            try:
                float(w)
            except (TypeError, ValueError):
                missing.append(f"{sid}[{i}]=bad")
    assert missing == [], missing[:20]


def test_mc_showdown_pct_kind_stale_guard():
    data = json.loads(MC_SHOWDOWN.read_text(encoding="utf-8"))
    kind = (data.get("meta") or {}).get("showdown_pct_kind")
    assert kind == "weight_over_abilities_sum", kind
