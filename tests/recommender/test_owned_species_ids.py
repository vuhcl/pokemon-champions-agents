from __future__ import annotations

from recommender.team_candidates import owned_species_ids


def _pool(*rows: dict) -> dict:
    return {"available_pool": list(rows)}


def test_swampert_expands_to_mega():
    owned = owned_species_ids(_pool({"species": "Swampert"}))
    assert "swampert" in owned
    assert "swampertmega" in owned


def test_item_field_is_ignored_for_expansion():
    bare = owned_species_ids(_pool({"species": "Swampert"}))
    with_item = owned_species_ids(
        _pool({"species": "Swampert", "item": "Focus Sash"})
    )
    assert bare == with_item


def test_raichu_expands_both_megas_alola_does_not():
    base = owned_species_ids(_pool({"species": "Raichu"}))
    assert "raichumegax" in base and "raichumegay" in base
    assert "raichualola" not in base

    alola = owned_species_ids(_pool({"species": "Raichu-Alola"}))
    assert alola == frozenset({"raichualola"})


def test_slowbro_expands_galar_does_not():
    base = owned_species_ids(_pool({"species": "Slowbro"}))
    assert "slowbromega" in base

    galar = owned_species_ids(_pool({"species": "Slowbro-Galar"}))
    assert galar == frozenset({"slowbrogalar"})


def test_rotom_does_not_expand_to_appliances():
    owned = owned_species_ids(_pool({"species": "Rotom"}))
    assert owned == frozenset({"rotom"})
    assert "rotomwash" not in owned


def test_charizard_expands_both_xy_megas():
    owned = owned_species_ids(_pool({"species": "Charizard"}))
    assert "charizardmegax" in owned
    assert "charizardmegay" in owned


def test_meowstic_expands_both_gender_megas():
    owned = owned_species_ids(_pool({"species": "Meowstic"}))
    assert "meowsticfmega" in owned
    assert "meowsticmmega" in owned


def test_floette_eternal_named_exception_expands_mega():
    owned = owned_species_ids(_pool({"species": "Floette-Eternal"}))
    assert "floetteeternal" in owned
    assert "floettemega" in owned


def test_plain_floette_explicit_deny_does_not_expand():
    owned = owned_species_ids(_pool({"species": "Floette"}))
    assert owned == frozenset({"floette"})
    assert "floettemega" not in owned


def test_owned_mega_alone_does_not_add_sibling_megas():
    owned = owned_species_ids(_pool({"species": "Swampert-Mega"}))
    assert owned == frozenset({"swampertmega"})

    x_only = owned_species_ids(_pool({"species": "Charizard-Mega-X"}))
    assert x_only == frozenset({"charizardmegax"})
    assert "charizardmegay" not in x_only
