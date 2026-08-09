"""Tests for recommender.support_needs.query_support_needs."""

from __future__ import annotations

from dataclasses import fields

from recommender.state import Attr, Slot
from recommender.support_needs import (
    RoleShapeContext,
    SupportNeed,
    _field_matches,
    _has_offensive_priority,
    _has_self_heal,
    _layer3_needs,
    _spe_tier,
    query_support_needs,
)


def _cats(needs: list[SupportNeed]) -> set[str]:
    return {n.category for n in needs}


def _by_cat(needs: list[SupportNeed], cat: str) -> list[SupportNeed]:
    return [n for n in needs if n.category == cat]


def test_clean_classification_does_not_suppress_raw_analysis():
    out = query_support_needs(
        {"species": "Archaludon"},
        RoleShapeContext(
            match_status="clean",
            primary_function="offense",
            tankiness="tanky",
            setup_dependent=True,
        ),
    )
    assert out


def test_archaludon_offense_tank_coverage_and_healing():
    out = query_support_needs(
        {"species": "Archaludon"},
        RoleShapeContext(
            match_status="partial",
            primary_function="offense",
            tankiness="tanky",
        ),
    )
    cov = _by_cat(out, "defensive_coverage")
    assert len(cov) == 1
    assert cov[0].weak_side == "spd"
    assert cov[0].trigger == "def_spd_asymmetry:offense_tank"

    heal = _by_cat(out, "healing_cleric")
    assert len(heal) == 1
    assert heal[0].trigger == "tank_no_self_heal"

    assert "screens" in _cats(out)
    # Coverage and healing are distinct categories (not merged).
    assert "defensive_coverage" in _cats(out)
    assert "healing_cleric" in _cats(out)


def test_attacker_universal_screens_and_healing():
    out = query_support_needs(
        {"species": "Archaludon", "ability": "Stamina", "moves": ["Dragon Pulse"]},
        RoleShapeContext(
            match_status="partial",
            primary_function="offense",
            tankiness="glass",
        ),
    )
    assert "screens" in _cats(out)
    heal = _by_cat(out, "healing_cleric")
    assert len(heal) == 1
    assert heal[0].trigger is None  # glass: no tank_no_self_heal enrich


def test_tailwind_support_no_screens_or_healing():
    out = query_support_needs(
        {"species": "Tornadus", "ability": "Prankster", "moves": ["Tailwind", "Protect"]},
        RoleShapeContext(
            match_status="partial",
            primary_function="support",
            tankiness="unknown",
        ),
    )
    assert "screens" not in _cats(out)
    assert "healing_cleric" not in _cats(out)


def test_support_tank_asymmetry_no_screens():
    out = query_support_needs(
        {"species": "Archaludon"},
        RoleShapeContext(
            match_status="partial",
            primary_function="support",
            tankiness="tanky",
        ),
    )
    cov = _by_cat(out, "defensive_coverage")
    assert len(cov) == 1
    assert cov[0].trigger == "def_spd_asymmetry:support_tank"
    assert "screens" not in _cats(out)
    heal = _by_cat(out, "healing_cleric")
    assert len(heal) == 1
    assert heal[0].trigger == "tank_no_self_heal"


def test_glass_gate_no_defensive_coverage():
    out = query_support_needs(
        {"species": "Archaludon"},
        RoleShapeContext(
            match_status="partial",
            primary_function="offense",
            tankiness="glass",
        ),
    )
    assert "defensive_coverage" not in _cats(out)
    assert "screens" in _cats(out)
    assert "healing_cleric" in _cats(out)


def test_setup_dependent_fake_out_and_taunt():
    out = query_support_needs(
        {"species": "Farigiraf"},
        RoleShapeContext(
            match_status="partial",
            primary_function="support",
            setup_dependent=True,
        ),
    )
    fo = _by_cat(out, "fake_out_protection")
    assert len(fo) == 1
    assert fo[0].trigger == "requires_setup_turn:fake_out"
    taunt = _by_cat(out, "taunt_disruption")
    assert len(taunt) == 1
    assert taunt[0].notes and "no clean mechanical counter" in taunt[0].notes.lower()
    assert "screens" not in _cats(out)


def test_setup_offense_kingambit_still_fake_out():
    """Kingambit-shaped: setup_dependent offense still surfaces FO (existing path)."""
    out = query_support_needs(
        {"species": "Kingambit"},
        RoleShapeContext(
            match_status="partial",
            primary_function="offense",
            tankiness="tanky",
            setup_dependent=True,
        ),
    )
    fo = _by_cat(out, "fake_out_protection")
    assert len(fo) == 1
    assert fo[0].trigger == "requires_setup_turn:fake_out"
    assert "taunt_disruption" in _cats(out)


def test_glass_offense_fake_out_not_setup():
    """Garchomp-shaped: glass offense, not setup_dependent → FO yes, Taunt no."""
    out = query_support_needs(
        {"species": "Garchomp"},
        RoleShapeContext(
            match_status="partial",
            primary_function="offense",
            tankiness="glass",
            setup_dependent=False,
        ),
    )
    fo = _by_cat(out, "fake_out_protection")
    assert len(fo) == 1
    assert fo[0].trigger == "glass_offense:fake_out"
    assert "taunt_disruption" not in _cats(out)


def test_tanky_offense_no_fake_out_without_setup():
    """Non-glass, non-setup offense must not get the widened FO gate."""
    out = query_support_needs(
        {"species": "Archaludon"},
        RoleShapeContext(
            match_status="partial",
            primary_function="offense",
            tankiness="tanky",
            setup_dependent=False,
        ),
    )
    assert "fake_out_protection" not in _cats(out)
    assert "taunt_disruption" not in _cats(out)


def test_contrary_stat_lowering_partner():
    # Species-only: featured may say "noability"; must fall back to legality Contrary.
    out = query_support_needs(
        {"species": "Staraptor-Mega"},
        RoleShapeContext(match_status="partial", primary_function="offense"),
    )
    sl = _by_cat(out, "stat_lowering_partner")
    assert len(sl) == 1
    assert sl[0].trigger == "ability:contrary"


def test_inconclusive_no_attacker_universals():
    out = query_support_needs(
        {"species": "Archaludon"},
        RoleShapeContext(match_status="partial", primary_function="unknown"),
    )
    assert "screens" not in _cats(out)
    assert "healing_cleric" not in _cats(out)


def test_speed_boost_layer1_no_speed_needs():
    out = query_support_needs(
        {
            "species": "Scolipede",
            "ability": "Speed Boost",
            "moves": ["Megahorn", "Protect"],
        },
        RoleShapeContext(
            match_status="partial",
            primary_function="offense",
            tankiness="glass",
        ),
    )
    assert "trick_room" not in _cats(out)
    assert "tailwind" not in _cats(out)
    assert "condition_setter" not in _cats(out)


def test_unburden_layer1_no_speed_needs():
    out = query_support_needs(
        {
            "species": "Scolipede",
            "ability": "Unburden",
            "moves": ["Megahorn", "Protect"],
        },
        RoleShapeContext(
            match_status="partial",
            primary_function="offense",
            tankiness="glass",
        ),
    )
    assert "trick_room" not in _cats(out)
    assert "tailwind" not in _cats(out)
    assert "condition_setter" not in _cats(out)


def test_quick_feet_layer1_no_speed_needs():
    out = query_support_needs(
        {
            "species": "Scolipede",
            "ability": "Quick Feet",
            "moves": ["Megahorn", "Protect"],
        },
        RoleShapeContext(
            match_status="partial",
            primary_function="offense",
            tankiness="glass",
        ),
    )
    assert "trick_room" not in _cats(out)
    assert "tailwind" not in _cats(out)
    assert "condition_setter" not in _cats(out)


def test_swift_swim_no_rain_needs_condition_setter():
    out = query_support_needs(
        {
            "species": "Kingdra",
            "ability": "Swift Swim",
            "moves": ["Hydro Pump", "Protect"],
        },
        RoleShapeContext(
            match_status="partial",
            primary_function="offense",
            tankiness="glass",
        ),
        team_draft=None,
    )
    cond = _by_cat(out, "condition_setter")
    assert len(cond) == 1
    assert cond[0].notes and "Rain" in cond[0].notes
    assert "trick_room" not in _cats(out)
    assert "tailwind" not in _cats(out)


def test_swift_swim_rain_locked_no_speed_need():
    pelipper = Slot(species=Attr(value="Pelipper", locked=True))
    out = query_support_needs(
        {
            "species": "Kingdra",
            "ability": "Swift Swim",
            "moves": ["Hydro Pump", "Protect"],
        },
        RoleShapeContext(
            match_status="partial",
            primary_function="offense",
            tankiness="glass",
        ),
        team_draft=[pelipper],
    )
    assert "condition_setter" not in _cats(out)
    assert "trick_room" not in _cats(out)
    assert "tailwind" not in _cats(out)


def test_field_matches_primal_weather_equivalence():
    assert _field_matches({"weather": "Sun"}, {"weather": "Harsh Sunshine"})
    assert _field_matches({"weather": "Harsh Sunshine"}, {"weather": "Sun"})
    assert _field_matches({"weather": "Rain"}, {"weather": "Heavy Rain"})
    assert _field_matches({"weather": "Heavy Rain"}, {"weather": "Rain"})
    assert _field_matches({"weather": "Strong Winds"}, {"weather": "Strong Winds"})
    assert not _field_matches({"weather": "Sun"}, {"weather": "Strong Winds"})
    assert not _field_matches({"weather": "Rain"}, {"weather": "Strong Winds"})
    assert not _field_matches({"weather": "Sand"}, {"weather": "Harsh Sunshine"})


def test_chlorophyll_desolate_land_clears_condition_setter():
    from unittest.mock import patch

    primal = Slot(species=Attr(value="Groudon-Primal", locked=True))
    with patch(
        "recommender.support_needs.featured_or_common_set",
        return_value={"ability": "Desolate Land"},
    ):
        out = query_support_needs(
            {
                "species": "Venusaur",
                "ability": "Chlorophyll",
                "moves": ["Giga Drain", "Protect"],
            },
            RoleShapeContext(
                match_status="partial",
                primary_function="offense",
                tankiness="glass",
            ),
            team_draft=[primal],
        )
    assert "condition_setter" not in _cats(out)


def test_swift_swim_primordial_sea_clears_condition_setter():
    from unittest.mock import patch

    primal = Slot(species=Attr(value="Kyogre-Primal", locked=True))
    with patch(
        "recommender.support_needs.featured_or_common_set",
        return_value={"ability": "Primordial Sea"},
    ):
        out = query_support_needs(
            {
                "species": "Kingdra",
                "ability": "Swift Swim",
                "moves": ["Hydro Pump", "Protect"],
            },
            RoleShapeContext(
                match_status="partial",
                primary_function="offense",
                tankiness="glass",
            ),
            team_draft=[primal],
        )
    assert "condition_setter" not in _cats(out)


def test_sand_force_needs_condition_setter():
    out = query_support_needs(
        {
            "species": "Garchomp",
            "ability": "Sand Force",
            "moves": ["Earthquake", "Protect"],
        },
        RoleShapeContext(
            match_status="partial",
            primary_function="offense",
            tankiness="glass",
        ),
        team_draft=None,
    )
    cond = _by_cat(out, "condition_setter")
    assert len(cond) == 1
    assert cond[0].notes and "Sand" in cond[0].notes
    assert cond[0].trigger == "field_condition:any:sand"


def test_sand_force_sand_locked_clears_condition_setter():
    ttar = Slot(species=Attr(value="Tyranitar", locked=True))
    out = query_support_needs(
        {
            "species": "Garchomp",
            "ability": "Sand Force",
            "moves": ["Earthquake", "Protect"],
        },
        RoleShapeContext(
            match_status="partial",
            primary_function="offense",
            tankiness="glass",
        ),
        team_draft=[ttar],
    )
    assert "condition_setter" not in _cats(out)


def test_dry_skin_needs_rain_only():
    out = query_support_needs(
        {
            "species": "Toxicroak",
            "ability": "Dry Skin",
            "moves": ["Poison Jab", "Protect"],
        },
        RoleShapeContext(
            match_status="partial",
            primary_function="offense",
            tankiness="glass",
        ),
        team_draft=None,
    )
    cond = _by_cat(out, "condition_setter")
    assert len(cond) == 1
    assert cond[0].notes == "Requires Rain"
    assert "Sun" not in (cond[0].notes or "")
    assert cond[0].trigger == "field_condition:any:rain"


def test_forecast_multi_condition_and_any_secures():
    out = query_support_needs(
        {
            "species": "Castform",
            "ability": "Forecast",
            "moves": ["Weather Ball", "Protect"],
        },
        RoleShapeContext(
            match_status="partial",
            primary_function="offense",
            tankiness="glass",
        ),
        team_draft=None,
    )
    cond = _by_cat(out, "condition_setter")
    assert len(cond) == 1
    assert cond[0].trigger == "field_condition:any:rain|sun|snow"
    assert "any of" in (cond[0].notes or "").lower() or "Rain" in (cond[0].notes or "")

    pelipper = Slot(species=Attr(value="Pelipper", locked=True))
    secured = query_support_needs(
        {
            "species": "Castform",
            "ability": "Forecast",
            "moves": ["Weather Ball", "Protect"],
        },
        RoleShapeContext(
            match_status="partial",
            primary_function="offense",
            tankiness="glass",
        ),
        team_draft=[pelipper],
    )
    assert "condition_setter" not in _cats(secured)


def test_mimicry_multi_terrain_emit_and_secure():
    from unittest.mock import patch

    out = query_support_needs(
        {
            "species": "Stunfisk",
            "ability": "Mimicry",
            "moves": ["Earth Power", "Protect"],
        },
        RoleShapeContext(
            match_status="partial",
            primary_function="offense",
            tankiness="glass",
        ),
        team_draft=None,
    )
    cond = _by_cat(out, "condition_setter")
    assert len(cond) == 1
    assert cond[0].trigger == "field_condition:any:electric|grassy|misty|psychic"

    koko = Slot(species=Attr(value="Tapu Koko", locked=True))
    with patch(
        "recommender.support_needs.featured_or_common_set",
        return_value={"ability": "Electric Surge"},
    ):
        secured = query_support_needs(
            {
                "species": "Stunfisk",
                "ability": "Mimicry",
                "moves": ["Earth Power", "Protect"],
            },
            RoleShapeContext(
                match_status="partial",
                primary_function="offense",
                tankiness="glass",
            ),
            team_draft=[koko],
        )
    assert "condition_setter" not in _cats(secured)


def test_protosynthesis_needs_sun_setter():
    out = query_support_needs(
        {
            "species": "Great Tusk",
            "ability": "Protosynthesis",
            "moves": ["Headlong Rush", "Protect"],
        },
        RoleShapeContext(
            match_status="partial",
            primary_function="offense",
            tankiness="glass",
        ),
        team_draft=None,
    )
    cond = _by_cat(out, "condition_setter")
    assert len(cond) == 1
    assert cond[0].notes and "Sun" in cond[0].notes
    assert cond[0].trigger == "field_condition:any:sun"


def test_spe_tier_boundaries():
    assert _spe_tier(50, [100, 100, 100]) == "low"  # f=1.0
    assert _spe_tier(50, [100, 100, 40]) == "low"  # f=2/3
    assert _spe_tier(80, [100, 100, 100, 60, 50, 40]) == "middling"  # f=3/6
    assert _spe_tier(120, [100, 100, 90]) == "already_fast"  # f=0
    assert _spe_tier(100, [110, 90, 80]) == "already_fast"  # f=1/3
    assert _spe_tier(50, []) is None


def test_layer3_need_want_matrix():
    low_no = _layer3_needs("low", False)
    assert len(low_no) == 1
    assert low_no[0].category == "trick_room" and low_no[0].stance == "need"
    assert low_no[0].trigger == "speed_tier:low_no_priority"

    low_prio = _layer3_needs("low", True)
    assert len(low_prio) == 1
    assert low_prio[0].category == "trick_room" and low_prio[0].stance == "want"
    assert low_prio[0].trigger == "speed_tier:low_with_priority"

    mid = _layer3_needs("middling", False)
    assert {(n.category, n.stance) for n in mid} == {
        ("tailwind", "need"),
        ("trick_room", "want"),
    }

    fast = _layer3_needs("already_fast", False)
    assert len(fast) == 1
    assert fast[0].category == "tailwind" and fast[0].stance == "want"


def test_offensive_priority_phase3_adds():
    for mid in ("Fake Out", "Feint", "Jet Punch", "Upper Hand"):
        assert _has_offensive_priority([mid]) is True
    assert _has_offensive_priority(["Tackle"]) is False


def test_self_heal_excludes_life_dew():
    assert _has_self_heal(["Recover"]) is True
    assert _has_self_heal(["Roost"]) is True
    assert _has_self_heal(["Life Dew"]) is False


def test_tank_with_only_life_dew_still_wants_healing_cleric():
    out = query_support_needs(
        {
            "species": "Archaludon",
            "ability": "Stamina",
            "moves": ["Dragon Pulse", "Life Dew"],
        },
        RoleShapeContext(
            match_status="partial",
            primary_function="offense",
            tankiness="tanky",
        ),
    )
    heal = _by_cat(out, "healing_cleric")
    assert len(heal) == 1
    assert heal[0].trigger == "tank_no_self_heal"


def test_layer3_smoke_slow_attacker_emits_speed_control():
    # Explicit no L1/L2 ability; low base Spe species.
    out = query_support_needs(
        {
            "species": "Torkoal",
            "ability": "Drought",
            "moves": ["Eruption", "Protect"],
        },
        RoleShapeContext(
            match_status="partial",
            primary_function="offense",
            tankiness="tanky",
        ),
    )
    assert "trick_room" in _cats(out) or "tailwind" in _cats(out)


def test_no_ranking_or_resolution_fields():
    names = {f.name for f in fields(SupportNeed)}
    assert "score" not in names
    assert "rank" not in names
    assert "resolution_path" not in names
    assert "candidates" not in names

    out = query_support_needs(
        {"species": "Archaludon"},
        RoleShapeContext(
            match_status="partial",
            primary_function="offense",
            tankiness="tanky",
        ),
    )
    for n in out:
        assert not hasattr(n, "score")
        assert n.stance is None or n.stance in ("need", "want")


def test_role_shape_context_has_only_projection_fields():
    assert {f.name for f in fields(RoleShapeContext)} == {
        "primary_function",
        "tankiness",
        "requires_setup_turn",
    }


def test_speed_analysis_uses_anchor_evs_and_nature(monkeypatch):
    seen: list[tuple[dict[str, int], str]] = []

    def fake_effective_spe(
        species: str,
        spread: dict[str, int],
        nature: str,
        **_: object,
    ) -> int:
        seen.append((spread, nature))
        return 100

    monkeypatch.setattr("recommender.support_needs.effective_spe", fake_effective_spe)
    monkeypatch.setattr("recommender.support_needs._threat_speeds", lambda *_: [120])
    query_support_needs(
        {
            "species": "Archaludon",
            "ability": "Stamina",
            "moves": ["Dragon Pulse"],
            "evs": {"spe": 32},
            "nature": "Timid",
        },
        RoleShapeContext(primary_function="offense"),
    )
    assert seen[0] == ({"spe": 32}, "Timid")
