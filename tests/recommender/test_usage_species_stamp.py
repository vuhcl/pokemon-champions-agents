"""Usage display names that do not to_id into calc must stamp a calc-valid label."""

from __future__ import annotations

from recommender.coverage import get_relevant_threats
from recommender.ids import to_id
from recommender.usage_data import featured_or_common_set, set_from_ingame

_REMAP = (
    ("mausholdfour", "Maushold Family of Four"),
    ("vivillonfancy", "Vivillon Fancy Pattern"),
    ("basculegion", "Basculegion Male"),
    ("ninetalesalola", "Alolan Ninetales"),
)


def test_ingame_flavor_names_stamp_calc_valid_ids():
    for sid, flavor in _REMAP:
        built = set_from_ingame(sid, regulation="champions")
        assert built is not None, sid
        assert to_id(built["species"]) == sid
        assert built["species"] != flavor


def test_featured_or_common_set_stamps_calc_valid_ids():
    for sid, flavor in _REMAP:
        built = featured_or_common_set(sid, regulation="champions")
        assert built is not None, sid
        assert to_id(built["species"]) == sid
        assert built["species"] != flavor


def test_basculegion_and_alolan_ninetales_keep_showdown_hyphenation():
    assert featured_or_common_set("basculegion", regulation="champions")["species"] == "Basculegion"
    assert (
        featured_or_common_set("ninetalesalola", regulation="champions")["species"]
        == "Ninetales-Alola"
    )


def test_floette_display_name_is_unchanged():
    built = set_from_ingame("floette", regulation="champions")
    assert built is not None
    assert built["species"] == "Floette"


def test_relevant_threats_glue_maushold_vivillon_floette():
    threats = get_relevant_threats({"regulation_mod": "champions"})
    by_ladder = {t.ladder_species: t for t in threats}
    maushold = by_ladder["Maushold Family of Four"]
    vivillon = by_ladder["Vivillon Fancy Pattern"]
    assert to_id(maushold.spec["species"]) == "mausholdfour"
    assert to_id(vivillon.spec["species"]) == "vivillonfancy"
    forms = {t.spec["species"] for t in threats if t.ladder_species == "Floette"}
    assert "Floette-Eternal" in forms
    assert "Floette-Mega" in forms
