from dataclasses import fields
from unittest.mock import patch

from recommender.anchor_roles import (
    classify_anchor_role,
    derive_role_shape_context,
    provided_weather_conditions,
    resolve_anchor_build,
    weather_beneficiary_ability_ids,
)
from recommender.state import Attr, ReasonRef, Slot
from recommender.support_needs import query_support_needs


def test_confirmed_fields_win_and_fingerprint_tracks_confirmation():
    slot = Slot(
        species=Attr("Pelipper", locked=True),
        ability=Attr("Keen Eye", locked=True),
        item=Attr("Leftovers", locked=True),
    )
    confirmed = resolve_anchor_build(slot)
    provisional = resolve_anchor_build(
        Slot(species=Attr("Pelipper")),
        provisional={"ability": "Keen Eye", "item": "Leftovers"},
    )
    assert confirmed.ability == "Keen Eye"
    assert confirmed.source_for("ability") == "user_confirmed"
    assert confirmed.fingerprint != provisional.fingerprint


def test_representative_fields_do_not_claim_cooccurrence():
    build = resolve_anchor_build("Kingambit")
    assert build.source_for("moves") == "usage_derived"
    assert all(p.cooccurrence_group is None for p in build.provenance)


def test_kingambit_trick_room_sweeper_still_teammate_expected_dependent():
    build = resolve_anchor_build("Kingambit")
    decision = classify_anchor_role(build, user_role="trick_room_sweeper")
    assert decision.role_id == "trick_room_sweeper"
    assert decision.kit_role == "standard_physical_attacker"
    assert decision.compendium.species
    assert not decision.compendium.exact
    shape = derive_role_shape_context(decision)
    assert shape.requires_setup_turn is False
    trick = next(m for m in decision.mechanisms if m.mechanic == "Trick Room")
    assert trick.supply == "teammate_expected"
    assert trick.present is False
    assert "condition:Trick Room" in trick.evidence
    categories = {need.category for need in query_support_needs(build.as_pokemon(), shape)}
    assert "fake_out_protection" not in categories
    assert "taunt_disruption" not in categories


def test_archaludon_electro_shot_emits_needed_rain_benefit():
    decision = classify_anchor_role(
        resolve_anchor_build("Archaludon"), user_role="bulky_rain_attacker"
    )
    assert decision.role_id == "bulky_rain_attacker"
    assert decision.match_quality == "clean"
    assert decision.durability_intent == "tanky"
    assert any(
        m.mechanic == "Stamina" and m.kind == "reactive_durability"
        for m in decision.mechanisms
    )
    rain = next(
        m
        for m in decision.mechanisms
        if m.relation == "benefits_from" and "condition:Rain" in m.evidence
    )
    assert rain.present is True
    assert rain.importance == "needed"
    assert rain.mechanic == "Electro Shot"
    assert derive_role_shape_context(decision).requires_setup_turn is False


def test_pelipper_primary_rain_secondary_tailwind_without_setup():
    decision = classify_anchor_role(resolve_anchor_build("Pelipper"))
    drizzle = next(m for m in decision.mechanisms if m.mechanic == "Drizzle")
    tailwind = next(m for m in decision.mechanisms if m.mechanic == "Tailwind")
    assert decision.role_id == "rain_setter"
    assert decision.secondary_role_ids == ("tailwind_setter",)
    assert "condition:Rain" in drizzle.evidence
    assert "condition:Tailwind" in tailwind.evidence
    assert tailwind.importance == "wanted"
    assert drizzle.confidence == "medium"
    assert drizzle.source == "usage_derived"
    assert derive_role_shape_context(decision).requires_setup_turn is False
    assert provided_weather_conditions(decision) == ("Rain",)


def test_provided_weather_conditions_ignore_tailwind_and_trick_room():
    assert provided_weather_conditions(
        classify_anchor_role(resolve_anchor_build("Whimsicott"))
    ) == ()
    assert provided_weather_conditions(
        classify_anchor_role(resolve_anchor_build("Torkoal"))
    ) == ("Sun",)
    assert provided_weather_conditions(
        classify_anchor_role(resolve_anchor_build("Tyranitar"))
    ) == ("Sand",)
    assert provided_weather_conditions(
        classify_anchor_role(resolve_anchor_build("Ninetales-Alola"))
    ) == ("Snow",)


def test_weather_beneficiary_ability_ids_canonicalizes_needed_and_wanted():
    rain = weather_beneficiary_ability_ids("Rain")
    assert "swiftswim" in rain
    assert "hydration" in rain
    assert "chlorophyll" not in rain
    sun = weather_beneficiary_ability_ids("Sun")
    assert "chlorophyll" in sun
    assert "solarpower" in sun
    sand = weather_beneficiary_ability_ids("Sand")
    assert "sandrush" in sand
    assert "sandforce" in sand
    snow = weather_beneficiary_ability_ids("Snow")
    assert "slushrush" in snow


def test_unknown_ability_makes_no_ability_claim(monkeypatch):
    monkeypatch.setattr(
        "recommender.anchor_roles.featured_or_common_set", lambda *args, **kwargs: None
    )
    monkeypatch.setattr("recommender.anchor_roles._unique_legal_ability", lambda _s: None)
    build = resolve_anchor_build("Pelipper")
    decision = classify_anchor_role(build)
    assert build.ability is None
    assert not any(m.kind in {"automatic_condition_setting", "reactive_durability"} for m in decision.mechanisms)


def test_role_shape_context_is_only_the_projection():
    assert {f.name for f in fields(derive_role_shape_context(classify_anchor_role(resolve_anchor_build("Pelipper"))))} == {
        "primary_function",
        "tankiness",
        "requires_setup_turn",
        "needed_weathers",
        "needed_trick_room",
    }


def _mock_no_usage(monkeypatch):
    monkeypatch.setattr(
        "recommender.anchor_roles.featured_or_common_set", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        "recommender.anchor_roles.find_set_matching", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        "recommender.anchor_roles.get_resolved_build", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        "recommender.anchor_roles.select_usage_spread", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        "recommender.anchor_roles._unique_legal_ability", lambda _s: None
    )


def _empty_compendium():
    from recommender.role_compendium import ReverseCompendiumEvidence

    return ReverseCompendiumEvidence()


def test_synthesized_drizzle_does_not_claim_present_rain(monkeypatch):
    _mock_no_usage(monkeypatch)
    build = resolve_anchor_build("Pelipper", synthesized={"ability": "Drizzle"})
    assert build.source_for("ability") == "synthesized"
    decision = classify_anchor_role(build, compendium=_empty_compendium())
    assert not any(
        m.kind == "automatic_condition_setting" and m.present
        for m in decision.mechanisms
    )
    assert decision.role_id != "rain_setter"
    assert decision.role_id == "unresolved"
    assert decision.match_quality != "clean"


def test_provisional_drizzle_does_not_claim_present_rain(monkeypatch):
    _mock_no_usage(monkeypatch)
    build = resolve_anchor_build("Pelipper", provisional={"ability": "Drizzle"})
    assert build.source_for("ability") == "provisional"
    decision = classify_anchor_role(build, compendium=_empty_compendium())
    assert not any(
        m.kind == "automatic_condition_setting" and m.present
        for m in decision.mechanisms
    )
    assert decision.role_id != "rain_setter"


def test_mimikyu_unique_ability_is_legality_only():
    build = resolve_anchor_build("Mimikyu")
    assert build.ability == "Disguise"
    assert build.source_for("ability") == "legality_only"


def test_slot_legality_only_reason_maps_to_field_provenance():
    slot = Slot(
        species=Attr("Mimikyu", locked=True),
        ability=Attr(
            "Disguise",
            locked=False,
            reason=ReasonRef(kind="tier2_heuristic", ref="legality_only"),
        ),
    )
    with patch("recommender.anchor_roles.featured_or_common_set", return_value=None):
        build = resolve_anchor_build(slot)
    assert build.source_for("ability") == "legality_only"


def test_slot_usage_reason_maps_to_usage_derived():
    slot = Slot(
        species=Attr("Politoed", locked=True),
        ability=Attr(
            "Drizzle",
            locked=False,
            reason=ReasonRef(kind="tier2_heuristic", ref="usage"),
        ),
    )
    with patch("recommender.anchor_roles.featured_or_common_set", return_value=None):
        build = resolve_anchor_build(slot)
    assert build.source_for("ability") == "usage_derived"
    assert build.confirmed("ability") is False
