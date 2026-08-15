"""Dex-equivalent species label lookup, then existing is_species_legal."""

from __future__ import annotations

from typing import Any, NamedTuple

from recommender.ids import to_id
from recommender.legality import is_species_legal

# Showdown DexSpecies.getByID formeNames (longer tokens last).
_FORME_NAMES: dict[str, tuple[str, ...]] = {
    "alola": ("a", "alola", "alolan"),
    "galar": ("g", "galar", "galarian"),
    "hisui": ("h", "hisui", "hisuian"),
    "paldea": ("p", "paldea", "paldean"),
    "mega": ("m", "mega"),
    "primal": ("p", "primal"),
}


class ResolvedSpecies(NamedTuple):
    name: str
    notice: str | None = None


def _female_sibling(species: dict[str, Any], stem: str) -> dict[str, Any] | None:
    child = species.get(stem + "f")
    if child and child.get("base_species_id") == stem:
        return child
    return None


def _forme_rewrite(
    sid: str,
    aliases: dict[str, str],
    species: dict[str, Any],
) -> str | None:
    for forme, tokens in _FORME_NAMES.items():
        poke_name = ""
        for token in tokens:
            if sid.startswith(token):
                poke_name = sid[len(token) :]
            elif sid.endswith(token):
                poke_name = sid[: -len(token)]
        poke_name = aliases.get(poke_name) or poke_name
        if poke_name and poke_name + forme in species:
            return poke_name + forme
    return None


def _gender_rewrite(sid: str, species: dict[str, Any]) -> str | None:
    if sid.endswith("female"):
        stem = sid[: -len("female")]
        return stem + "f" if _female_sibling(species, stem) else None
    if sid.endswith("male"):
        stem = sid[: -len("male")]
        return stem if _female_sibling(species, stem) else None
    return None


def resolve_species_label(raw: str, snap: dict[str, Any]) -> ResolvedSpecies | None:
    sid = to_id(raw)
    if not sid:
        return None
    species: dict[str, Any] = snap.get("species") or {}
    aliases: dict[str, str] = snap.get("species_aliases") or {}
    candidate = aliases.get(sid, sid)
    if candidate not in species:
        candidate = _forme_rewrite(sid, aliases, species) or _gender_rewrite(sid, species) or ""
    if not candidate or candidate not in species or not is_species_legal(snap, candidate):
        return None
    entry = species[candidate]
    name = str(entry.get("name") or raw)
    notice = None
    if to_id(raw) == candidate:
        female = _female_sibling(species, candidate)
        if female and is_species_legal(snap, candidate + "f"):
            notice = f"{name} is the male forme; {female.get('name')} is also legal."
    return ResolvedSpecies(name, notice)
