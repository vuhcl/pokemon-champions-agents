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


# Hit/contact-triggered opponent disrupt (redirection execution reinforce).
# Phrases verified against all.v1.json opponent+triggered+disrupt tag set.
_HIT_TRIGGER_PHRASES = (
    "hit by an attack",
    "hit by a physical attack",
    "making contact with this pokemon",
    "gets hit",
)
_KO_TRIGGER_PHRASE = "knocked out with"


def _description_is_hit_triggered(description: str) -> bool:
    d = description.lower()
    if _KO_TRIGGER_PHRASE in d:
        return False
    return any(p in d for p in _HIT_TRIGGER_PHRASES)


@lru_cache(maxsize=1)
def hit_triggered_opponent_disrupt_ids(path: str | None = None) -> frozenset[str]:
    """Ability ids: opponent+triggered+disrupt tags AND hit/contact description.

    Re-derived from data/abilities/all.v1.json — not a chat-assembled name list.
    Excludes KO-only / residual / bounce / etc. that share the coarse tags.
    """
    table = load_abilities(path)
    out: set[str] = set()
    for aid in abilities_with_tag(
        target="opponent",
        activation="triggered",
        purpose="disrupt",
        data=table,
    ):
        entry = (table.get("abilities") or {}).get(aid) or {}
        if _description_is_hit_triggered(str(entry.get("description") or "")):
            out.add(aid)
    return frozenset(out)


# Self-provided protection against the two disruptions every slow-by-design
# setter is maximally exposed to: Fake Out and Taunt. Phrases verified against
# all.v1.json; the sets are re-derived, not chat-assembled name lists.
_PRIORITY_DENIAL_PHRASES = (
    "priority moves used by opposing pokemon",
    "prevented from having an effect",
)
_FLINCH_IMMUNITY_PHRASE = "cannot be made to flinch"
_TAUNT_IMMUNITY_PHRASES = (
    "cannot become affected by",
    "cannot be infatuated or taunted",
)
# Blanket status-move denial covers Taunt without naming it (Magic Bounce
# reflects it, Good as Gold ignores it), so name-matching alone misses them.
_STATUS_DENIAL_PHRASES = (
    "immune to status moves",
    "unaffected by certain non-damaging moves directed at it",
)


def _description_denies_flinch(description: str) -> bool:
    """Fake Out is stopped outright (priority denial) or its flinch cannot land."""
    d = description.lower()
    if all(p in d for p in _PRIORITY_DENIAL_PHRASES):
        return True
    return _FLINCH_IMMUNITY_PHRASE in d


def _description_denies_taunt(description: str) -> bool:
    d = description.lower()
    if any(p in d for p in _STATUS_DENIAL_PHRASES):
        return True
    if "taunt" not in d:
        return False
    return any(p in d for p in _TAUNT_IMMUNITY_PHRASES)


def _derived_ids(path: str | None, predicate: Any, label: str) -> frozenset[str]:
    table = load_abilities(path)
    out = {
        aid
        for aid, entry in (table.get("abilities") or {}).items()
        if predicate(str(entry.get("description") or ""))
    }
    if not out:
        raise ValueError(f"{label} derived an empty set from the ability table")
    return frozenset(out)


@lru_cache(maxsize=1)
def flinch_denial_ability_ids(path: str | None = None) -> frozenset[str]:
    """Ability ids that stop a Fake Out from denying the turn.

    Re-derived from data/abilities/all.v1.json — priority denial (the move is
    prevented outright) or explicit flinch immunity. Shield Dust is excluded on
    purpose: Fake Out's flinch is a primary effect, not a secondary one.
    """
    return _derived_ids(path, _description_denies_flinch, "flinch_denial_ability_ids")


@lru_cache(maxsize=1)
def taunt_denial_ability_ids(path: str | None = None) -> frozenset[str]:
    """Ability ids granting immunity to Taunt, re-derived from descriptions."""
    return _derived_ids(path, _description_denies_taunt, "taunt_denial_ability_ids")


def execution_reinforce_abilities(
    abs_map: dict[str, str],
    *,
    path: str | None = None,
) -> list[tuple[str, str, str]]:
    """Species ability-map ∩ hit-triggered disrupt — (id, display_name, description)."""
    hits = hit_triggered_opponent_disrupt_ids(path)
    table = load_abilities(path)
    rows: list[tuple[str, str, str]] = []
    for aid in sorted(set(abs_map) & hits):
        entry = (table.get("abilities") or {}).get(aid) or {}
        display = str(abs_map.get(aid) or entry.get("name") or aid)
        desc = str(entry.get("description") or "")
        rows.append((aid, display, desc))
    return rows
