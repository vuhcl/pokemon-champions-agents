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


def set_answer_errata(row_id: str) -> dict[str, Any] | None:
    """Optional set-membership errata (e.g. H11 Gyarados-Mega allowed_not_required)."""
    entry = (load_errata().get("set_answer") or {}).get(row_id)
    return dict(entry) if isinstance(entry, dict) else None


def allowed_not_required(row_id: str) -> set[str]:
    entry = set_answer_errata(row_id)
    if not entry:
        return set()
    return {str(x) for x in (entry.get("allowed_not_required") or [])}


def set_answer_hand_note(row_id: str) -> str | None:
    """Text to append on the hand-audit form for set-answer errata rows."""
    entry = set_answer_errata(row_id)
    if not entry:
        return None
    members = ", ".join(sorted(allowed_not_required(row_id))) or "(none)"
    rule = entry.get("scoring_rule") or "allowed_not_required"
    meaning = entry.get("meaning") or ""
    return f"ERRATA set_answer ({rule}): {members}. {meaning}".strip()


def outcome_set(row_id: str) -> dict[str, Any] | None:
    """Accepted outcome set for a row (e.g. OL7a `{bind Jolteon, ask}`).

    When present, class_scorer scores against this set instead of a single class atom.
    """
    entry = (load_errata().get("outcome_sets") or {}).get(row_id)
    return dict(entry) if isinstance(entry, dict) else None
