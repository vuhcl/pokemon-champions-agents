from __future__ import annotations

import pytest

from recommender.legality import load_snapshot
from recommender.species_resolve import resolve_species_label


def _name(raw: str) -> str | None:
    hit = resolve_species_label(raw, load_snapshot())
    return None if hit is None else hit.name


def _notice(raw: str) -> str | None:
    hit = resolve_species_label(raw, load_snapshot())
    return None if hit is None else hit.notice


@pytest.mark.parametrize(
    ("raw", "name"),
    [
        ("A-Ninetales", "Ninetales-Alola"),
        ("Ninetales-A", "Ninetales-Alola"),
        ("M-Swampert", "Swampert-Mega"),
        ("Floette-E", "Floette-Eternal"),
        ("Basculegion Male", "Basculegion"),
        ("Swampert-M", "Swampert-Mega"),
        ("Meowstic Female", "Meowstic-F"),
        ("Eternal Floette", "Floette-Eternal"),
    ],
)
def test_resolve_legal_canonical_names(raw, name):
    hit = resolve_species_label(raw, load_snapshot())
    assert hit is not None
    assert hit.name == name
    assert hit.notice is None


@pytest.mark.parametrize(
    "raw",
    ["Swampert Male", "Pelipper Female", "M-Charizard", "Charizard-M", "P-Tauros", "Floette"],
)
def test_resolve_fail_closed(raw):
    assert resolve_species_label(raw, load_snapshot()) is None


def test_bare_gender_base_notices_explicit_qualifier_does_not():
    male = "Basculegion is the male forme; Basculegion-F is also legal."
    meow = "Meowstic is the male forme; Meowstic-F is also legal."
    assert _name("Basculegion") == "Basculegion"
    assert _notice("Basculegion") == male
    assert _name("Basculegion Male") == "Basculegion"
    assert _notice("Basculegion Male") is None
    assert _name("Meowstic") == "Meowstic"
    assert _notice("Meowstic") == meow
    assert _name("Meowstic Female") == "Meowstic-F"
    assert _notice("Meowstic Female") is None


def test_missing_species_aliases_key_is_empty_map():
    snap = dict(load_snapshot())
    snap.pop("species_aliases", None)
    hit = resolve_species_label("Swampert", snap)
    assert hit is not None
    assert hit.name == "Swampert"
