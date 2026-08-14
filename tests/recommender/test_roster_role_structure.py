"""Tests for on-demand roster role-structure grouping."""

from __future__ import annotations

from dataclasses import fields

from recommender.anchor_roles import classify_anchor_role, resolve_anchor_build
from recommender.move_narrowing import WEATHER_SETTING_MOVES
from recommender.roster_role_structure import (
    RoleFunctionGroup,
    RosterRoleStructureReport,
    summarize_roster_role_structure,
)
from recommender.slot_fill import LockedAnchorContext
from recommender.state import Attr, Slot
from recommender.support_needs import RoleShapeContext


def _context(
    slot_index: int,
    slot: Slot,
    *,
    user_role: str | None = None,
) -> LockedAnchorContext:
    build = resolve_anchor_build(slot)
    decision = classify_anchor_role(build, user_role=user_role)
    species = build.species or "unknown"
    return LockedAnchorContext(
        slot_index=slot_index,
        anchor_id=species.lower().replace("-", ""),
        pokemon=build.as_pokemon(),
        resolved_build=build,
        role_decision=decision,
        role_shape_context=RoleShapeContext(
            primary_function=decision.primary_function,
            tankiness="unknown",
            requires_setup_turn=False,
        ),
        support_needs=(),
    )


def _rain_fixture() -> tuple[LockedAnchorContext, ...]:
    return (
        _context(
            0,
            Slot(
                species=Attr(value="Pelipper", locked=True),
                ability=Attr(value="Drizzle", locked=True),
                moveset=Attr(
                    value=["Hurricane", "Weather Ball", "U-turn", "Tailwind"],
                    locked=True,
                ),
            ),
        ),
        _context(
            1,
            Slot(
                species=Attr(value="Sableye", locked=True),
                moveset=Attr(
                    value=["Will-O-Wisp", "Light Screen", "Reflect", "Rain Dance"],
                    locked=True,
                ),
            ),
        ),
        _context(
            2,
            Slot(
                species=Attr(value="Archaludon", locked=True),
                ability=Attr(value="Stamina", locked=True),
                moveset=Attr(
                    value=["Electro Shot", "Dragon Pulse", "Flash Cannon", "Body Press"],
                    locked=True,
                ),
            ),
            user_role="bulky_rain_attacker",
        ),
        _context(
            3,
            Slot(
                species=Attr(value="Swampert", locked=True),
                item=Attr(value="Swampertite", locked=True),
                ability=Attr(value="Swift Swim", locked=True),
                moveset=Attr(
                    value=["Waterfall", "Earthquake", "Ice Punch", "Protect"],
                    locked=True,
                ),
            ),
            user_role="physical_rain_attacker",
        ),
        _context(
            4,
            Slot(
                species=Attr(value="Sinistcha", locked=True),
                ability=Attr(value="Hospitality", locked=True),
                moveset=Attr(
                    value=["Matcha Gotcha", "Rage Powder", "Trick Room", "Protect"],
                    locked=True,
                ),
            ),
        ),
        _context(
            5,
            Slot(
                species=Attr(value="Maushold", locked=True),
                ability=Attr(value="Technician", locked=True),
                moveset=Attr(
                    value=["Population Bomb", "Tidy Up", "Encore", "Bite"],
                    locked=True,
                ),
            ),
        ),
    )


def _group(report: RosterRoleStructureReport, key: str) -> RoleFunctionGroup:
    return next(g for g in report.groups if g.function_key == key)


def test_weather_setting_moves_export_smoke():
    assert "raindance" in WEATHER_SETTING_MOVES


def test_rain_setter_contested_pelipper_sableye():
    report = summarize_roster_role_structure(_rain_fixture())
    rain = _group(report, "rain_setter")
    assert rain.status == "contested"
    assert rain.cardinality == 2
    assert {m.species for m in rain.members} == {"Pelipper", "Sableye"}


def test_attacker_contested_includes_technician_maushold():
    report = summarize_roster_role_structure(_rain_fixture())
    attackers = _group(report, "attacker")
    assert attackers.status == "contested"
    assert attackers.cardinality == 3
    assert {m.species for m in attackers.members} == {
        "Archaludon",
        "Swampert",
        "Maushold",
    }


def test_sinistcha_uncontested_redirection_and_trick_room():
    report = summarize_roster_role_structure(_rain_fixture())
    redirection = _group(report, "redirection")
    trick = _group(report, "trick_room_setter")
    assert redirection.status == "uncontested"
    assert {m.species for m in redirection.members} == {"Sinistcha"}
    assert trick.status == "uncontested"
    assert {m.species for m in trick.members} == {"Sinistcha"}


def test_pelipper_tailwind_uncontested():
    report = summarize_roster_role_structure(_rain_fixture())
    tw = _group(report, "tailwind_setter")
    assert tw.status == "uncontested"
    assert {m.species for m in tw.members} == {"Pelipper"}


def test_step_a_gaps_absent_honestly():
    report = summarize_roster_role_structure(_rain_fixture())
    keys = {g.function_key for g in report.groups}
    for gap in (
        "disruption",
        "disruption_utility",
        "hospitality",
        "ally_heal",
    ):
        assert gap not in keys


def test_sableye_screens_uncontested():
    report = summarize_roster_role_structure(_rain_fixture())
    screens = _group(report, "screens_support")
    assert screens.status == "uncontested"
    assert {m.species for m in screens.members} == {"Sableye"}
    assert screens.label == "screens"


def test_friend_guard_follow_me_maushold_not_attacker():
    locked = (
        _context(
            0,
            Slot(
                species=Attr(value="Maushold", locked=True),
                ability=Attr(value="Friend Guard", locked=True),
                moveset=Attr(
                    value=["Follow Me", "Population Bomb", "Encore", "Protect"],
                    locked=True,
                ),
            ),
        ),
        _context(
            1,
            Slot(
                species=Attr(value="Archaludon", locked=True),
                ability=Attr(value="Stamina", locked=True),
                moveset=Attr(
                    value=["Electro Shot", "Dragon Pulse", "Flash Cannon", "Body Press"],
                    locked=True,
                ),
            ),
            user_role="bulky_rain_attacker",
        ),
    )
    report = summarize_roster_role_structure(locked)
    keys_by_species = {
        m.species: {k for k, _ in m.groups} for m in report.members
    }
    assert "attacker" not in keys_by_species["Maushold"]
    assert "redirection" in keys_by_species["Maushold"]
    assert "attacker" in keys_by_species["Archaludon"]


def test_no_recommended_four_fields():
    forbidden = (
        "recommended_four",
        "default_bring",
        "preferred",
        "ranking",
        "bring",
    )
    for cls in (RoleFunctionGroup, RosterRoleStructureReport):
        names = {f.name for f in fields(cls)}
        for bad in forbidden:
            assert not any(bad in n for n in names), names
    report = summarize_roster_role_structure(_rain_fixture())
    for group in report.groups:
        if group.notes is None:
            continue
        note = group.notes.lower()
        assert "recommend" not in note
        assert "prefer" not in note
        assert "bring" not in note
        assert "rank" not in note


def test_sableye_in_rain_even_without_utility_emission():
    report = summarize_roster_role_structure(_rain_fixture())
    rain = _group(report, "rain_setter")
    assert any(m.species == "Sableye" for m in rain.members)
    keys = {g.function_key for g in report.groups}
    assert "screens_support" in keys
    assert "disruption" not in keys


def test_empty_locked_roster_returns_empty_report():
    report = summarize_roster_role_structure(())
    assert report.groups == ()
    assert report.members == ()
