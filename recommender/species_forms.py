"""Species forme resolution from held items (cycle-free shared helper)."""

from __future__ import annotations

from typing import Any

from recommender.legality import is_species_legal


def _species_id_is_mega(sid: str) -> bool:
    return sid.endswith("mega") or sid.endswith("megax") or sid.endswith("megay")


def mega_capable_base_ids(snap: dict[str, Any]) -> frozenset[str]:
    """Bases with at least one legal mega forme in the legality snapshot."""
    bases: set[str] = set()
    for sid, entry in (snap.get("species") or {}).items():
        if not is_species_legal(snap, sid) or not _species_id_is_mega(sid):
            continue
        base_id = entry.get("base_species_id")
        if base_id:
            bases.add(base_id)
    return frozenset(bases)


def ingame_excluded_species_ids(snap: dict[str, Any]) -> frozenset[str]:
    """Mega-capable bases and their legal child forme ids."""
    bases = mega_capable_base_ids(snap)
    excluded: set[str] = set(bases)
    for sid, entry in (snap.get("species") or {}).items():
        if not is_species_legal(snap, sid):
            continue
        base_id = entry.get("base_species_id")
        if base_id and base_id in bases:
            excluded.add(sid)
    return frozenset(excluded)


def item_mega_forme(item_id: str, base_species_id: str, snap: dict[str, Any]) -> str | None:
    if item_id.endswith("itex"):
        candidate = f"{base_species_id}megax"
    elif item_id.endswith("itey"):
        candidate = f"{base_species_id}megay"
    elif item_id.endswith("ite"):
        candidate = f"{base_species_id}mega"
    else:
        return None
    species = snap.get("species") or {}
    if candidate in species:
        return candidate
    # Showdown's ungendered meowstic is the male/default; F/M Megas are
    # mechanically identical (same stats, both Trace). meowsticf already
    # resolves via {base}mega → meowsticfmega.
    if base_species_id == "meowstic" and item_id.endswith("ite") and "meowsticmmega" in species:
        return "meowsticmmega"
    return None
