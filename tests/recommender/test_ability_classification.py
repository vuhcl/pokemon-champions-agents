"""Tests for ability classification table + legality join."""

from __future__ import annotations

from recommender.ability_classification import (
    abilities_with_tag,
    ability_self_def_drop_on_physical_hit,
    actionable_abilities,
    get_ability,
    hit_triggered_opponent_disrupt_ids,
    load_abilities,
)

INTENTIONAL_EMPTY = {
    "asone",
    "ballfetch",
    "honeygather",
    "hungerswitch",
    "noability",
    "powerconstruct",
    "runaway",
    "schooling",
    "shieldsdown",
    "stancechange",
    "terashift",
    "zenmode",
    "zerotohero",
}


def test_table_nonempty_and_meta():
    load_abilities.cache_clear()
    data = load_abilities()
    abilities = data["abilities"]
    assert len(abilities) >= 300
    assert data["meta"]["taxonomy"] == "target_activation_purpose_v1"
    assert data["meta"]["taxonomy_status"] == "approved"
    assert data["meta"]["phase_b"]["flags_open"] == 0
    assert data["meta"]["phase_b"]["prankster_class_count"] == 4
    assert data["meta"]["target_axis"] == ["self", "ally", "opponent"]
    drizzle = abilities["drizzle"]
    assert drizzle["description"] == "On switch-in, this Pokemon summons Rain Dance."


def _tag_set(entry: dict) -> set[tuple[str, str, str]]:
    return {
        (t["target"], t["activation"], t["purpose"]) for t in entry.get("tags") or []
    }


def test_no_other_target():
    load_abilities.cache_clear()
    data = load_abilities()
    for aid, e in data["abilities"].items():
        for t in e.get("tags") or []:
            assert t["target"] != "other", aid
            assert t["target"] in {"self", "ally", "opponent"}, (aid, t)


def test_intentional_empties_only():
    load_abilities.cache_clear()
    data = load_abilities()
    empty = {aid for aid, e in data["abilities"].items() if not e.get("tags")}
    assert empty == INTENTIONAL_EMPTY
    assert data["abilities"]["asone"]["note"] == "placeholder_see_forme_variants"
    assert data["abilities"]["noability"]["note"] == "no_competitive_effect"
    assert data["abilities"]["schooling"]["note"] == "forme_primary_excluded"


def test_sample_and_resolutions():
    load_abilities.cache_clear()
    a = load_abilities()["abilities"]

    assert _tag_set(a["intimidate"]) == {("opponent", "unconditional", "disrupt")}
    assert _tag_set(a["friendguard"]) == {("ally", "unconditional", "support")}
    assert _tag_set(a["drizzle"]) == {
        ("ally", "unconditional", "support"),
        ("opponent", "unconditional", "support"),
    }
    assert _tag_set(a["neutralizinggas"]) == {
        ("ally", "unconditional", "disrupt"),
        ("opponent", "unconditional", "disrupt"),
    }
    assert _tag_set(a["darkaura"]) == {
        ("ally", "unconditional", "boost"),
        ("opponent", "unconditional", "boost"),
    }
    assert _tag_set(a["fairyaura"]) == _tag_set(a["darkaura"])
    assert _tag_set(a["battery"]) == {("ally", "unconditional", "boost")}
    assert ("ally", "triggered", "support") in _tag_set(a["lightningrod"])
    assert _tag_set(a["illusion"]) == {("opponent", "unconditional", "disrupt")}
    assert _tag_set(a["commander"]) == {
        ("ally", "unconditional", "boost"),
        ("self", "unconditional", "disrupt"),
        ("opponent", "unconditional", "disrupt"),
    }
    assert _tag_set(a["gulpmissile"]) == {("opponent", "triggered", "disrupt")}
    assert _tag_set(a["heavymetal"]) == {
        ("self", "unconditional", "boost"),
        ("self", "unconditional", "support"),
        ("self", "unconditional", "disrupt"),
    }
    assert _tag_set(a["lightmetal"]) == {
        ("self", "unconditional", "disrupt"),
        ("self", "unconditional", "support"),
    }
    assert _tag_set(a["dancer"]) == {("self", "unconditional", "support")}
    assert _tag_set(a["asoneglastrier"]) == {
        ("opponent", "unconditional", "disrupt"),
        ("self", "triggered", "boost"),
    }
    assert a["asoneglastrier"]["composed_of"] == ["unnerve", "chillingneigh"]
    assert _tag_set(a["flashfire"]) == {
        ("self", "unconditional", "support"),
        ("self", "triggered", "boost"),
    }
    assert _tag_set(a["eelevate"]) == {
        ("self", "unconditional", "support"),
        ("self", "triggered", "boost"),
    }


def test_get_ability_and_filter():
    load_abilities.cache_clear()
    assert get_ability("Drizzle") is not None
    assert get_ability("not-an-ability") is None
    disrupt_opp = abilities_with_tag(target="opponent", purpose="disrupt")
    assert "intimidate" in disrupt_opp
    assert "friendguard" not in disrupt_opp


def test_actionable_abilities_live_join():
    load_abilities.cache_clear()
    found = actionable_abilities()
    assert "drizzle" in found
    assert "notarealabilityxyz" not in found
    data = load_abilities()
    assert found <= set(data["abilities"])


# Oracle of description+KO filter over opponent+triggered+disrupt — not a runtime source.
_HIT_TRIGGERED_OPPONENT_DISRUPT_EXPECTED = frozenset(
    {
        "cottondown",
        "cursedbody",
        "cutecharm",
        "effectspore",
        "flamebody",
        "gooey",
        "gulpmissile",
        "ironbarbs",
        "lingeringaroma",
        "mummy",
        "perishbody",
        "poisonpoint",
        "roughskin",
        "spicyspray",
        "static",
        "tanglinghair",
        "toxicdebris",
        "wanderingspirit",
    }
)


def test_hit_triggered_opponent_disrupt_ids():
    load_abilities.cache_clear()
    hit_triggered_opponent_disrupt_ids.cache_clear()
    got = hit_triggered_opponent_disrupt_ids()
    assert got == _HIT_TRIGGERED_OPPONENT_DISRUPT_EXPECTED
    assert "spicyspray" in got and "flamebody" in got
    for excluded in (
        "baddreams",
        "aftermath",
        "innardsout",
        "synchronize",
        "magicbounce",
        "liquidooze",
        "mirrorarmor",
        "poisonpuppeteer",
        "rebound",
        "teraformzero",
    ):
        assert excluded not in got


def test_ability_self_def_drop_on_physical_hit():
    load_abilities.cache_clear()
    assert ability_self_def_drop_on_physical_hit("Weak Armor") is True
    assert ability_self_def_drop_on_physical_hit("Intimidate") is False
