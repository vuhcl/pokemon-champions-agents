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


def test_floette_excluded_from_ingame_slice():
    assert set_from_ingame("floette", regulation="champions") is None


def test_relevant_threats_glue_maushold_vivillon():
    threats = get_relevant_threats({"regulation_mod": "champions"})
    maushold = [t for t in threats if t.ladder_species == "Maushold Family of Four"]
    vivillon = [t for t in threats if t.ladder_species == "Vivillon Fancy Pattern"]
    assert {to_id(t.spec["species"]) for t in maushold} == {"mausholdfour"}
    assert {to_id(t.spec["species"]) for t in vivillon} == {"vivillonfancy"}
    assert not any(t.ladder_species == "Floette" for t in threats)
