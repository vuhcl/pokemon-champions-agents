"""Data-driven forme class for Role Compendium pool + usage collapse."""

from __future__ import annotations

from typing import Any, Literal

from recommender.ids import to_id
from recommender.legality import resolve_learnset
from recommender.usage_data import ingame_species_map, showdown_species_map

FormeClass = Literal[
    "root",
    "cosmetic",
    "battle_transform",
    "mechanical_selectable",
]

_COLLAPSE = frozenset({"cosmetic", "battle_transform"})


def _base_stats(entry: dict[str, Any]) -> dict[str, int]:
    raw = entry.get("baseStats") or entry.get("base_stats") or {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): int(v) for k, v in raw.items()}


def _types(entry: dict[str, Any]) -> tuple[str, ...]:
    raw = entry.get("types") or []
    if not isinstance(raw, list):
        return ()
    return tuple(str(t) for t in raw)


def _ability_ids(entry: dict[str, Any]) -> frozenset[str]:
    ab = entry.get("abilities") or {}
    if not isinstance(ab, dict):
        return frozenset()
    return frozenset(to_id(v) for v in ab.values() if isinstance(v, str) and v)


def _learnset_ids(snap: dict[str, Any], sid: str) -> frozenset[str]:
    ls = resolve_learnset(snap, sid) or []
    return frozenset(to_id(m) for m in ls)


def _usage_corpus_empty(*, regulation: str) -> bool:
    """True when both in-game and Showdown maps have zero species for this regulation.

    Absence of a per-species row is only evidence when a corpus exists. An empty
    corpus (e.g. next-letter day 0) must not be treated as 'every forme unused'.
    """
    return (not ingame_species_map(regulation)) and (
        not showdown_species_map(regulation)
    )


def _has_independent_usage_row(sid: str, *, regulation: str) -> bool:
    """True when sid appears in ingame OR showdown (player-selectable export)."""
    return sid in ingame_species_map(regulation) or sid in showdown_species_map(
        regulation
    )


def classify_forme(
    snap: dict[str, Any],
    sid: str,
    *,
    regulation: str,
) -> FormeClass:
    """Classify forme vs its ``base_species_id`` (data axes only; no name patterns)."""
    sid = to_id(sid)
    entry = (snap.get("species") or {}).get(sid) or {}
    base = entry.get("base_species_id")
    if not base or to_id(base) == sid:
        return "root"
    base_sid = to_id(base)
    base_entry = (snap.get("species") or {}).get(base_sid) or {}
    if not base_entry:
        return "mechanical_selectable"

    same_stats = _base_stats(entry) == _base_stats(base_entry)
    same_types = _types(entry) == _types(base_entry)
    same_abilities = _ability_ids(entry) == _ability_ids(base_entry)
    same_learnset = _learnset_ids(snap, sid) == _learnset_ids(snap, base_sid)

    if same_stats and same_types and same_abilities and same_learnset:
        return "cosmetic"
    # Fail closed: with no usage corpus, missing rows prove nothing — do not
    # collapse mechanical size/formes (Gourgeist) or battle transforms into base.
    if _usage_corpus_empty(regulation=regulation):
        return "mechanical_selectable"
    if (
        same_abilities
        and same_learnset
        and (not same_stats or not same_types)
        and not _has_independent_usage_row(sid, regulation=regulation)
    ):
        return "battle_transform"
    return "mechanical_selectable"


def canonical_usage_species_id(
    snap: dict[str, Any],
    sid: str,
    *,
    regulation: str,
) -> str:
    """Usage lookup id: cosmetic / battle_transform → base; else self."""
    sid = to_id(sid)
    cls = classify_forme(snap, sid, regulation=regulation)
    if cls not in _COLLAPSE:
        return sid
    base = ((snap.get("species") or {}).get(sid) or {}).get("base_species_id")
    return to_id(base) if base else sid


def should_skip_pool_member(
    snap: dict[str, Any],
    sid: str,
    *,
    regulation: str,
    pool_ids: set[str] | None = None,
) -> bool:
    """Skip cosmetic/battle_transform when base is legal (in pool when provided)."""
    sid = to_id(sid)
    cls = classify_forme(snap, sid, regulation=regulation)
    if cls not in _COLLAPSE:
        return False
    base = ((snap.get("species") or {}).get(sid) or {}).get("base_species_id")
    if not base:
        return False
    base_sid = to_id(base)
    if pool_ids is not None:
        return base_sid in pool_ids
    from recommender.legality import is_species_legal

    return is_species_legal(snap, base_sid)
