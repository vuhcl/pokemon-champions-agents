"""Read helpers for state/errata.json."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ERRATA = HERE / "errata.json"
V4_KEYS = HERE.parents[1] / "part_g_v4" / "key_artifacts" / "derived_keys.json"


def load_errata() -> dict[str, Any]:
    return json.loads(ERRATA.read_text(encoding="utf-8"))


def key_overrides() -> dict[str, Any]:
    """G7 (and later) derived_keys leaf overrides. Empty dict if absent."""
    entry = load_errata().get("key_overrides")
    return dict(entry) if isinstance(entry, dict) else {}


def key_override_leaves() -> dict[str, Any]:
    leaves = key_overrides().get("leaves") or {}
    return dict(leaves) if isinstance(leaves, dict) else {}


def apply_key_overrides(keys: dict[str, Any]) -> dict[str, Any]:
    """Deep-copy derived_keys and apply errata leaf paths (dot-separated)."""
    out = copy.deepcopy(keys)
    for path, value in key_override_leaves().items():
        parts = str(path).split(".")
        cur: Any = out
        for p in parts[:-1]:
            if not isinstance(cur, dict) or p not in cur:
                cur = None
                break
            cur = cur[p]
        if isinstance(cur, dict) and parts[-1] in cur:
            cur[parts[-1]] = value
    return out


def load_derived_keys_effective() -> dict[str, Any]:
    """derived_keys.json with G7 key_overrides applied (file itself untouched)."""
    raw = json.loads(V4_KEYS.read_text(encoding="utf-8"))
    return apply_key_overrides(raw)


def acceptance_with_key_overrides(row_id: str, acceptance: str) -> str:
    """Rewrite acceptance substrings listed under key_overrides.row_acceptance_rewrites."""
    text = acceptance or ""
    rewrites = (key_overrides().get("row_acceptance_rewrites") or {}).get(row_id) or []
    for item in rewrites:
        if not isinstance(item, dict):
            continue
        src, dst = item.get("from"), item.get("to")
        if isinstance(src, str) and isinstance(dst, str) and src in text:
            text = text.replace(src, dst)
    return text


def key_override_hand_note(row_id: str) -> str | None:
    """Append for hand-audit when this row's key leaves are overridden."""
    ov = key_overrides()
    leaves = key_override_leaves()
    if not leaves:
        return None
    # IS3 ↔ Dragapult scarf_tw/max_stack; IS4 ↔ Pincurchin.
    relevant = {
        "IS3": ("is3_is4.Dragapult.",),
        "IS4": ("is3_is4.Pincurchin.",),
    }.get(row_id)
    if not relevant:
        return None
    lines = [
        f"{path}={val}"
        for path, val in sorted(leaves.items())
        if any(path.startswith(p) for p in relevant)
    ]
    if not lines:
        return None
    sec = ov.get("section") or "key_overrides"
    return f"ERRATA {sec} key_overrides: {'; '.join(lines)}."


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
