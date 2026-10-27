"""Read helpers for state/errata.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ERRATA = HERE / "errata.json"


def load_errata() -> dict[str, Any]:
    return json.loads(ERRATA.read_text(encoding="utf-8"))


def expected_turns(row_id: str, class_cell: str) -> list[str]:
    err = load_errata()
    cell = (err.get("class_cells") or {}).get(row_id)
    if cell and cell.get("turns"):
        return list(cell["turns"])
    return [class_cell]


def expected_readback(row_id: str) -> dict[str, str] | None:
    sub = (load_errata().get("substitutions") or {}).get(row_id)
    if not sub:
        return None
    out = {}
    for key in ("species", "ability", "item"):
        if key in sub:
            out[key] = sub[key]
    return out or None


def stale_pin_rows() -> set[str]:
    return set(load_errata().get("stale_pin_rows") or [])
