"""Ability classification table loader + live legality join.

Grounding data only (ADR-021) — coarse three-axis tags + verbatim descriptions.
No per-ability resolution logic.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from recommender.ids import to_id
from recommender.legality import is_species_legal, load_snapshot

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ABILITIES = ROOT / "data" / "abilities" / "all.v1.json"

Target = str  # "self" | "ally" | "opponent"
Activation = str  # "unconditional" | "triggered"
Purpose = str  # "boost" | "support" | "disrupt"


@lru_cache(maxsize=1)
def load_abilities(path: str | None = None) -> dict[str, Any]:
    p = Path(path) if path else DEFAULT_ABILITIES
    return json.loads(p.read_text())


def get_ability(ability_id: str, data: dict[str, Any] | None = None) -> dict[str, Any] | None:
    table = data if data is not None else load_abilities()
    return (table.get("abilities") or {}).get(to_id(ability_id))


def abilities_with_tag(
    *,
    target: Target | None = None,
    activation: Activation | None = None,
    purpose: Purpose | None = None,
    data: dict[str, Any] | None = None,
) -> list[str]:
    """Return ability ids that have at least one tag matching all provided fields."""
    table = data if data is not None else load_abilities()
    out: list[str] = []
    for aid, entry in (table.get("abilities") or {}).items():
        for tag in entry.get("tags") or []:
            if target is not None and tag.get("target") != target:
                continue
            if activation is not None and tag.get("activation") != activation:
                continue
            if purpose is not None and tag.get("purpose") != purpose:
                continue
            out.append(aid)
            break
    return out


def actionable_abilities(
    snap: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
) -> set[str]:
    """Ability ids present on ≥1 currently legal species and in the classification table.

    Legality is a live join — never a stored per-ability field.
    """
    table = data if data is not None else load_abilities()
    known = set((table.get("abilities") or {}).keys())
    legality = snap if snap is not None else load_snapshot()
    found: set[str] = set()
    for sid, entry in (legality.get("species") or {}).items():
        if not is_species_legal(legality, sid):
            continue
        for name in (entry.get("abilities") or {}).values():
            if not isinstance(name, str):
                continue
            aid = to_id(name)
            if aid in known:
                found.add(aid)
    return found
