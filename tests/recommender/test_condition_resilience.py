"""Tests for condition resilience classification and gap need dedupe."""

from __future__ import annotations

from dataclasses import replace

from recommender.anchor_roles import (
    MechanismEvidence,
    classify_anchor_role,
    resolve_anchor_build,
)
from recommender.condition_resilience import (
    MIN_WANTED_DEPENDENTS_FOR_ESSENTIAL,
    ConditionProviderMember,
    ConditionResilienceReport,
    ConditionResilienceRow,
    assess_condition_resilience,
    gap_support_needs,
)
from recommender.ids import to_id
from recommender.slot_fill import AnchoredSupportNeed, LockedAnchorContext
from recommender.support_needs import RoleShapeContext, query_support_needs


def _context_from_decision(
    slot_index: int,
    species: str,
    decision,
    *,
    support_needs: tuple[AnchoredSupportNeed, ...] = (),
) -> LockedAnchorContext:
    build = resolve_anchor_build(species)
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
        support_needs=support_needs,
    )


def _benefit(
    condition: str,
    *,
    importance: str = "wanted",
    present: bool = True,
    mechanic: str | None = None,
) -> MechanismEvidence:
    return MechanismEvidence(
        mechanic=mechanic or condition,
        kind="teammate_condition_benefit",
        relation="benefits_from",
        importance=importance,  # type: ignore[arg-type]
        role_id=None,
        present=present,
        prerequisite=False,
        activation="passive_reactive",
        interruptible=False,
        source="synthesized",
        supply="teammate_expected",
        evidence=(f"condition:{condition}",),
    )


def _provide(condition: str, mechanic: str, role_id: str) -> MechanismEvidence:
    return MechanismEvidence(
        mechanic=mechanic,
        kind="automatic_condition_setting",
        relation="provides",
        importance="needed",
        role_id=role_id,
        present=True,
        prerequisite=False,
        activation="automatic",
        interruptible=False,
        source="synthesized",
        supply="self_supplied",
        evidence=(f"condition:{condition}", f"ability:{mechanic.lower()}"),
    )


def test_essential_via_needed_dependent():
    rain_setter = classify_anchor_role(resolve_anchor_build("Pelipper"))
    swimmer = replace(
        classify_anchor_role(resolve_anchor_build("Kingambit")),
        mechanisms=(_benefit("Rain", importance="needed", mechanic="Swift Swim"),),
        primary_function="offense",
        role_id="bulky_attacker",
    )
    report = assess_condition_resilience(
        (
            _context_from_decision(0, "Pelipper", rain_setter),
            _context_from_decision(1, "Kingambit", swimmer),
        )
    )
    rain = next(row for row in report.conditions if row.condition == "Rain")
    assert rain.classification == "essential"
    assert rain.provider_count == 1
    assert rain.gap == "single_provider_spof"


def test_essential_via_wanted_times_two_still_emits_gap_need():
    """Aggregate essentiality with no per-anchor condition ask still generates a gap need."""
    assert MIN_WANTED_DEPENDENTS_FOR_ESSENTIAL == 2
    first = replace(
        classify_anchor_role(resolve_anchor_build("Kingambit")),
        mechanisms=(_benefit("Rain", importance="wanted"),),
        primary_function="offense",
        role_id="bulky_attacker",
    )
    second = replace(
        classify_anchor_role(resolve_anchor_build("Archaludon")),
        mechanisms=(_benefit("Rain", importance="wanted", mechanic="Dry Skin"),),
        primary_function="offense",
        role_id="bulky_attacker",
    )
    report = assess_condition_resilience(
        (
            _context_from_decision(0, "Kingambit", first),
            _context_from_decision(1, "Archaludon", second),
        )
    )
    rain = next(row for row in report.conditions if row.condition == "Rain")
    assert rain.classification == "essential"
    assert rain.gap == "missing_provider"
    # No Spe/ability condition_setter on these synthetic contexts' support_needs.
    residual = gap_support_needs(report, ())
    assert any(
        n.category == "condition_setter"
        and n.trigger == "field_condition:any:rain"
        for n in residual
    )


def test_preferred_via_single_wanted_dependent():
    dependent = replace(
        classify_anchor_role(resolve_anchor_build("Kingambit")),
        mechanisms=(_benefit("Rain", importance="wanted"),),
        primary_function="offense",
        role_id="bulky_attacker",
    )
    provider = classify_anchor_role(resolve_anchor_build("Pelipper"))
    report = assess_condition_resilience(
        (
            _context_from_decision(0, "Pelipper", provider),
            _context_from_decision(1, "Kingambit", dependent),
        )
    )
    # One wanted + needed Electro Shot on Archaludon path avoided; Kingambit wanted only.
    # With Pelipper provider and one wanted dependent → preferred unless needed.
    rain = next(row for row in report.conditions if row.condition == "Rain")
    assert rain.classification == "preferred"
    assert rain.gap == "single_provider_spof"


def test_preferred_via_setter_direction_policy():
    setter = classify_anchor_role(resolve_anchor_build("Pelipper"))
    offense = replace(
        classify_anchor_role(resolve_anchor_build("Kingambit")),
        mechanisms=(),
        primary_function="offense",
        role_id="bulky_attacker",
        secondary_role_ids=(),
    )
    report = assess_condition_resilience(
        (
            _context_from_decision(0, "Pelipper", setter),
            _context_from_decision(1, "Kingambit", offense),
        )
    )
    rain = next(row for row in report.conditions if row.condition == "Rain")
    assert rain.classification == "preferred"
    assert rain.gap == "single_provider_spof"


def test_provider_count_zero_one_two():
    dependent = replace(
        classify_anchor_role(resolve_anchor_build("Kingambit")),
        mechanisms=(_benefit("Rain", importance="needed", mechanic="Swift Swim"),),
        primary_function="offense",
        role_id="bulky_attacker",
    )
    zero = assess_condition_resilience(
        (_context_from_decision(0, "Kingambit", dependent),)
    )
    assert next(r for r in zero.conditions if r.condition == "Rain").provider_count == 0

    one = assess_condition_resilience(
        (
            _context_from_decision(0, "Pelipper", classify_anchor_role(resolve_anchor_build("Pelipper"))),
            _context_from_decision(1, "Kingambit", dependent),
        )
    )
    assert next(r for r in one.conditions if r.condition == "Rain").provider_count == 1


def test_two_automatic_rain_setters_count_as_two():
    pelipper = classify_anchor_role(resolve_anchor_build("Pelipper"))
    politoed = replace(
        classify_anchor_role(resolve_anchor_build("Politoed")),
        mechanisms=(_provide("Rain", "Drizzle", "rain_setter"),),
        role_id="rain_setter",
        primary_function="support",
    )
    dependent = replace(
        classify_anchor_role(resolve_anchor_build("Kingambit")),
        mechanisms=(_benefit("Rain", importance="needed", mechanic="Swift Swim"),),
        primary_function="offense",
        role_id="bulky_attacker",
    )
    report = assess_condition_resilience(
        (
            _context_from_decision(0, "Pelipper", pelipper),
            _context_from_decision(1, "Politoed", politoed),
            _context_from_decision(2, "Kingambit", dependent),
        )
    )
    rain = next(row for row in report.conditions if row.condition == "Rain")
    assert rain.provider_count == 2
    assert rain.gap == "none"


def test_gap_single_provider_spof_when_essential():
    report = assess_condition_resilience(
        (
            _context_from_decision(
                0, "Pelipper", classify_anchor_role(resolve_anchor_build("Pelipper"))
            ),
            _context_from_decision(
                1,
                "Archaludon",
                classify_anchor_role(
                    resolve_anchor_build("Archaludon"), user_role="bulky_rain_attacker"
                ),
            ),
        )
    )
    rain = next(row for row in report.conditions if row.condition == "Rain")
    assert rain.classification == "essential"
    assert rain.provider_count == 1
    assert rain.gap == "single_provider_spof"


def test_optional_provider_only_omits_irrelevant():
    report = assess_condition_resilience(
        (
            _context_from_decision(
                0, "Pelipper", classify_anchor_role(resolve_anchor_build("Pelipper"))
            ),
        )
    )
    # Pelipper alone: preferred via setter direction needs offense teammate — without
    # dependents or preferred trigger, Rain may be optional if only provider.
    # Lone rain_setter with no offense partner and no dependents → optional.
    rain = next((row for row in report.conditions if row.condition == "Rain"), None)
    assert rain is not None
    assert rain.classification == "optional"
    assert rain.gap == "none"
    assert not any(row.condition == "Sand" for row in report.conditions)


def test_kingambit_present_false_counts_as_dependent_in_assess():
    decision = classify_anchor_role(
        resolve_anchor_build("Kingambit"), user_role="trick_room_sweeper"
    )
    report = assess_condition_resilience(
        (_context_from_decision(0, "Kingambit", decision),)
    )
    tr = next(row for row in report.conditions if row.condition == "Trick Room")
    assert tr.classification == "preferred"
    assert any(d.importance == "wanted" for d in tr.dependents)
    assert tr.gap == "missing_provider"


def test_gap_support_needs_dedupes_anchored_trick_room():
    decision = classify_anchor_role(
        resolve_anchor_build("Kingambit"), user_role="trick_room_sweeper"
    )
    shape = RoleShapeContext(
        primary_function="offense", tankiness="tanky", requires_setup_turn=False
    )
    needs = tuple(
        AnchoredSupportNeed(0, "kingambit", need)
        for need in query_support_needs(
            resolve_anchor_build("Kingambit").as_pokemon(), shape
        )
    )
    report = ConditionResilienceReport(
        conditions=(
            ConditionResilienceRow(
                condition="Trick Room",
                classification="preferred",
                provider_count=0,
                providers=(),
                dependents=(),
                gap="missing_provider",
            ),
        )
    )
    assert any(n.need.category == "trick_room" for n in needs)
    assert gap_support_needs(report, needs) == ()


def _kingambit_tr():
    return classify_anchor_role(
        resolve_anchor_build("Kingambit"), user_role="trick_room_sweeper"
    )


def _secondary_kinds(decision) -> list[tuple[str, tuple[str, ...]]]:
    return [
        (m.kind, m.evidence)
        for m in decision.mechanisms
        if m.kind == "secondary_speed_control"
    ]


def test_gengar_emits_icy_wind_secondary_speed_control():
    build = resolve_anchor_build("Gengar")
    assert build.ability == "Cursed Body"
    assert tuple(build.moves) == (
        "Shadow Ball",
        "Sludge Bomb",
        "Protect",
        "Icy Wind",
    )
    kinds = _secondary_kinds(classify_anchor_role(build))
    assert ("secondary_speed_control", ("move:icywind",)) in kinds
    assert not any("condition:" in tag for _, ev in kinds for tag in ev)


def test_milotic_and_rotom_wash_do_not_emit_secondary_speed_control():
    milotic = resolve_anchor_build("Milotic")
    assert milotic.ability == "Competitive"
    assert tuple(milotic.moves) == ("Protect", "Scald", "Muddy Water", "Coil")
    assert _secondary_kinds(classify_anchor_role(milotic)) == []

    rotom = resolve_anchor_build("Rotom-Wash")
    assert rotom.ability == "Levitate"
    assert tuple(rotom.moves) == (
        "Hydro Pump",
        "Thunderbolt",
        "Will-O-Wisp",
        "Volt Switch",
    )
    assert "electroweb" not in {to_id(m) for m in rotom.moves}
    assert _secondary_kinds(classify_anchor_role(rotom)) == []


def test_icy_wind_softens_tr_without_changing_classification_or_gap():
    king = _kingambit_tr()
    baseline = assess_condition_resilience(
        (_context_from_decision(0, "Kingambit", king),)
    )
    base_tr = next(r for r in baseline.conditions if r.condition == "Trick Room")
    gengar = classify_anchor_role(resolve_anchor_build("Gengar"))
    report = assess_condition_resilience(
        (
            _context_from_decision(0, "Kingambit", king),
            _context_from_decision(1, "Gengar", gengar),
        )
    )
    tr = next(r for r in report.conditions if r.condition == "Trick Room")
    assert [m.mechanic for m in tr.secondary_speed_control] == ["Icy Wind"]
    assert tr.classification == base_tr.classification
    assert tr.gap == base_tr.gap
    assert tr.provider_count == base_tr.provider_count


def test_whimsicott_tailwind_icy_wind_is_adjacent_not_a_second_provider():
    whims = classify_anchor_role(resolve_anchor_build("Whimsicott"))
    gengar = classify_anchor_role(resolve_anchor_build("Gengar"))
    build = resolve_anchor_build("Whimsicott")
    assert "tailwind" in {to_id(m) for m in build.moves}
    report = assess_condition_resilience(
        (
            _context_from_decision(0, "Whimsicott", whims),
            _context_from_decision(1, "Gengar", gengar),
        )
    )
    tw = next(r for r in report.conditions if r.condition == "Tailwind")
    assert tw.provider_count == 1
    assert [p.species for p in tw.providers] == [
        resolve_anchor_build("Whimsicott").species or "Whimsicott"
    ]
    assert "Icy Wind" in [m.mechanic for m in tw.secondary_speed_control]
    assert not any(p.mechanic == "Icy Wind" for p in tw.providers)


def test_milotic_usage_icy_wind_not_on_kit_does_not_soften():
    king = _kingambit_tr()
    milotic = classify_anchor_role(resolve_anchor_build("Milotic"))
    report = assess_condition_resilience(
        (
            _context_from_decision(0, "Kingambit", king),
            _context_from_decision(1, "Milotic", milotic),
        )
    )
    tr = next(r for r in report.conditions if r.condition == "Trick Room")
    assert tr.secondary_speed_control == ()


def test_rotom_wash_thunderbolt_does_not_soften():
    king = _kingambit_tr()
    rotom = classify_anchor_role(resolve_anchor_build("Rotom-Wash"))
    report = assess_condition_resilience(
        (
            _context_from_decision(0, "Kingambit", king),
            _context_from_decision(1, "Rotom-Wash", rotom),
        )
    )
    tr = next(r for r in report.conditions if r.condition == "Trick Room")
    assert tr.secondary_speed_control == ()


def test_goodra_sap_sipper_and_thunderbolt_do_not_soften():
    build = resolve_anchor_build("Goodra")
    assert build.ability == "Sap Sipper"
    assert tuple(build.moves) == (
        "Protect",
        "Flamethrower",
        "Thunderbolt",
        "Ice Beam",
    )
    king = _kingambit_tr()
    goodra = classify_anchor_role(build)
    report = assess_condition_resilience(
        (
            _context_from_decision(0, "Kingambit", king),
            _context_from_decision(1, "Goodra", goodra),
        )
    )
    tr = next(r for r in report.conditions if r.condition == "Trick Room")
    assert tr.secondary_speed_control == ()


def test_ampharos_static_softens_tr():
    build = resolve_anchor_build("Ampharos")
    assert build.ability == "Static"
    assert tuple(build.moves) == (
        "Protect",
        "Dragon Pulse",
        "Parabolic Charge",
        "Rising Voltage",
    )
    assert "cottonspore" not in {to_id(m) for m in build.moves}
    king = _kingambit_tr()
    ampharos = classify_anchor_role(build)
    report = assess_condition_resilience(
        (
            _context_from_decision(0, "Kingambit", king),
            _context_from_decision(1, "Ampharos", ampharos),
        )
    )
    tr = next(r for r in report.conditions if r.condition == "Trick Room")
    assert "Static" in [m.mechanic for m in tr.secondary_speed_control]


def test_gap_support_needs_still_fires_when_secondary_speed_control_present():
    report = ConditionResilienceReport(
        conditions=(
            ConditionResilienceRow(
                condition="Trick Room",
                classification="preferred",
                provider_count=0,
                providers=(),
                dependents=(),
                gap="missing_provider",
                secondary_speed_control=(
                    ConditionProviderMember(1, "Gengar", "Icy Wind"),
                ),
            ),
        )
    )
    residual = gap_support_needs(report, ())
    assert any(n.category == "trick_room" for n in residual)


def test_weather_rows_never_populate_secondary_speed_control():
    report = assess_condition_resilience(
        (
            _context_from_decision(
                0, "Pelipper", classify_anchor_role(resolve_anchor_build("Pelipper"))
            ),
            _context_from_decision(
                1,
                "Archaludon",
                classify_anchor_role(
                    resolve_anchor_build("Archaludon"), user_role="bulky_rain_attacker"
                ),
            ),
        )
    )
    for row in report.conditions:
        if row.condition not in ("Trick Room", "Tailwind"):
            assert row.secondary_speed_control == ()
