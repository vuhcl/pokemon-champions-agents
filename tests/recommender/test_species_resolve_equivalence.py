"""resolve_species_label must behave exactly as before lookup_species_id was factored out."""

from __future__ import annotations

from recommender.ids import to_id
from recommender.legality import is_species_legal, load_snapshot
from recommender.species_resolve import (
    ResolvedSpecies,
    _female_sibling,
    _forme_rewrite,
    _gender_rewrite,
    lookup_species_id,
    resolve_species_label,
)

SNAP = load_snapshot()


def _legacy(raw, snap):
    """Verbatim body of resolve_species_label before the refactor."""
    sid = to_id(raw)
    if not sid:
        return None
    species = snap.get("species") or {}
    aliases = snap.get("species_aliases") or {}
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


def _inputs() -> list[str]:
    species = SNAP["species"]
    out: list[str] = ["", "  ", "???", "Notamon"]
    for sid, entry in species.items():
        out += [sid, str(entry.get("name") or sid), str(entry.get("name") or sid).upper()]
    out += list((SNAP.get("species_aliases") or {}).keys())
    bases = [s for s, e in species.items() if not e.get("base_species_id")]
    for b in bases[::7]:
        for tok in ("a", "alola", "alolan", "g", "galar", "galarian", "h", "hisui", "p", "paldea", "mega", "primal"):
            out += [tok + b, b + tok, f"{tok}-{b}", f"{b}-{tok}"]
        out += [b + "male", b + "female"]
    return out


def test_resolve_species_label_unchanged_over_snapshot_names_aliases_and_formes():
    inputs = _inputs()
    assert len(inputs) > 5000
    for raw in inputs:
        assert resolve_species_label(raw, SNAP) == _legacy(raw, SNAP), raw


def test_lookup_species_id_ignores_legality_but_agrees_when_legal():
    for sid in SNAP["species"]:
        assert lookup_species_id(sid, SNAP) == sid
    assert lookup_species_id("Flutter Mane", SNAP) == "fluttermane"
    assert resolve_species_label("Flutter Mane", SNAP) is None
    assert lookup_species_id("Notamon", SNAP) is None
