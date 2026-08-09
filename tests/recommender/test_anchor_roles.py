from dataclasses import fields

from recommender.anchor_roles import (
    classify_anchor_role,
    derive_role_shape_context,
    resolve_anchor_build,
)
from recommender.state import Attr, Slot
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


def test_kingambit_explicit_strategy_keeps_active_kit_non_setup():
    build = resolve_anchor_build("Kingambit")
    decision = classify_anchor_role(build, user_role="trick_room_sweeper")
    assert decision.role_id == "trick_room_sweeper"
    assert decision.kit_role == "bulky_attacker"
    assert decision.compendium.species
    assert not decision.compendium.exact
    shape = derive_role_shape_context(decision)
    assert shape.requires_setup_turn is False
    assert any(
        mechanism.supply == "teammate_expected"
        and mechanism.mechanic == "Trick Room"
        for mechanism in decision.mechanisms
    )
    categories = {need.category for need in query_support_needs(build.as_pokemon(), shape)}
    assert "fake_out_protection" not in categories
    assert "taunt_disruption" not in categories


def test_archaludon_stamina_is_durability_not_rain_inference():
    decision = classify_anchor_role(
        resolve_anchor_build("Archaludon"), user_role="bulky_rain_attacker"
    )
    assert decision.role_id == "bulky_rain_attacker"
    assert decision.match_quality == "clean"
    assert decision.durability_intent == "tanky"
    assert any(m.mechanic == "Stamina" and m.kind == "reactive_durability" for m in decision.mechanisms)
    assert not any("rain" in (m.role_id or "") for m in decision.mechanisms)
    assert derive_role_shape_context(decision).requires_setup_turn is False


def test_pelipper_primary_rain_secondary_tailwind_without_setup():
    decision = classify_anchor_role(resolve_anchor_build("Pelipper"))
    tailwind = next(m for m in decision.mechanisms if m.mechanic == "Tailwind")
    assert decision.role_id == "rain_setter"
    assert decision.secondary_role_ids == ("tailwind_setter",)
    assert tailwind.importance == "wanted"
    assert derive_role_shape_context(decision).requires_setup_turn is False


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
    }
