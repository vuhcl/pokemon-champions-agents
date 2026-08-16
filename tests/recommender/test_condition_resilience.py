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
    _tr_spe_discount_floor,
    assess_condition_resilience,
    gap_support_needs,
)
from recommender.ids import to_id
from recommender.slot_fill import AnchoredSupportNeed, LockedAnchorContext
from recommender.support_needs import (
    RoleShapeContext,
    _spe_tier,
    _threat_speeds,
    query_support_needs,
)
from recommender.usage_spreads import _SPEED_MINUS, _SPEED_PLUS, effective_spe


def _context_from_decision(
    slot_index: int,
    species: str,
    decision,
    *,
    support_needs: tuple[AnchoredSupportNeed, ...] = (),
    resolved_build=None,
) -> LockedAnchorContext:
    build = resolved_build or resolve_anchor_build(species)
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


def _with_spe(build, spe: int, **kwargs):
    evs = dict(build.evs)
    evs["spe"] = spe
    return replace(build, evs=tuple(sorted(evs.items())), **kwargs)


def _tr_row(locked):
    report = assess_condition_resilience(locked)
    return next((r for r in report.conditions if r.condition == "Trick Room"), None)


def _tr_wanted(locked) -> int:
    row = _tr_row(locked)
    if row is None:
        return 0
    return sum(1 for d in row.dependents if d.importance == "wanted")


def _has_tr_benefit(decision) -> bool:
    return any(
        m.relation == "benefits_from" and "condition:Trick Room" in m.evidence
        for m in decision.mechanisms
    )


def _declared_tr(build):
    return classify_anchor_role(build, user_role="trick_room_sweeper")


def test_tr_spe_discount_floor_interior_gap_and_fallback():
    frozen = [70, 72, 80, 83, 90, 125, 136, 151, 167, 171]
    assert _tr_spe_discount_floor(frozen) == 125
    tight = [100, 105, 110, 115, 120, 125]
    assert _tr_spe_discount_floor(tight) == next(
        s for s in range(0, max(tight) + 2) if _spe_tier(s, tight) == "already_fast"
    )
    assert _tr_spe_discount_floor([]) is None


def test_live_tr_spe_discount_floor_is_125():
    assert _tr_spe_discount_floor(_threat_speeds(None, "champions-reg-mb")) == 125


def test_kingambit_declared_sweeper_counts_as_wanted_tr():
    build = resolve_anchor_build("Kingambit")
    assert build.nature == "Adamant"
    assert build.spread.get("spe", 0) == 0
    assert to_id(build.item or "") != "choicescarf"
    ctx = _context_from_decision(0, "Kingambit", _declared_tr(build), resolved_build=build)
    assert _tr_wanted((ctx,)) == 1


def test_garchomp_mega_default_is_discounted():
    build = resolve_anchor_build("Garchomp-Mega")
    ctx = _context_from_decision(
        0, "Garchomp-Mega", _declared_tr(build), resolved_build=build
    )
    assert _has_tr_benefit(_declared_tr(build))
    assert _tr_wanted((ctx,)) == 0


def test_basculegion_scarf_stripped_is_discounted():
    build = replace(resolve_anchor_build("Basculegion"), item=None)
    decision = _declared_tr(build)
    assert _has_tr_benefit(decision)
    ctx = _context_from_decision(0, "Basculegion", decision, resolved_build=build)
    assert _tr_wanted((ctx,)) == 0


def test_kangaskhan_mega_brave_counts_without_declared_sweeper():
    build = resolve_anchor_build("Kangaskhan-Mega")
    assert build.nature == "Brave"
    decision = classify_anchor_role(build)
    assert decision.role_id != "trick_room_sweeper"
    ctx = _context_from_decision(0, "Kangaskhan-Mega", decision, resolved_build=build)
    assert _tr_wanted((ctx,)) == 1
    declared = _declared_tr(build)
    assert sum(
        1
        for m in declared.mechanisms
        if m.relation == "benefits_from" and "condition:Trick Room" in m.evidence
    ) == 1
    ctx2 = _context_from_decision(0, "Kangaskhan-Mega", declared, resolved_build=build)
    assert _tr_wanted((ctx2,)) == 1


def test_spe_floor_only_discounts_dragapult_zero_hardy():
    build = _with_spe(resolve_anchor_build("Dragapult"), 0, nature="Hardy", item=None)
    assert build.nature not in _SPEED_PLUS
    assert effective_spe(build.species, build.spread, build.nature or "Hardy") >= 125
    ctx = _context_from_decision(
        0, "Dragapult", _declared_tr(build), resolved_build=build
    )
    assert _tr_wanted((ctx,)) == 0


def test_spe_ev_only_discounts_kingambit():
    build = _with_spe(resolve_anchor_build("Kingambit"), 1)
    assert build.nature == "Adamant"
    assert to_id(build.item or "") != "choicescarf"
    ctx = _context_from_decision(
        0, "Kingambit", _declared_tr(build), resolved_build=build
    )
    assert _tr_wanted((ctx,)) == 0


def test_scarf_only_discounts_kingambit():
    build = replace(resolve_anchor_build("Kingambit"), item="Choice Scarf")
    assert build.spread.get("spe", 0) == 0
    assert build.nature == "Adamant"
    ctx = _context_from_decision(
        0, "Kingambit", _declared_tr(build), resolved_build=build
    )
    assert _tr_wanted((ctx,)) == 0


def test_plus_nature_only_discounts_kingambit_and_does_not_emit():
    build = replace(resolve_anchor_build("Kingambit"), nature="Jolly")
    assert build.spread.get("spe", 0) == 0
    assert to_id(build.item or "") != "choicescarf"
    assert not _has_tr_benefit(classify_anchor_role(build))
    ctx = _context_from_decision(
        0, "Kingambit", _declared_tr(build), resolved_build=build
    )
    assert _tr_wanted((ctx,)) == 0


def test_adamant_kingambit_without_sweeper_is_not_a_tr_dependent():
    build = resolve_anchor_build("Kingambit")
    assert build.nature == "Adamant"
    decision = classify_anchor_role(build)
    assert not _has_tr_benefit(decision)
    ctx = _context_from_decision(0, "Kingambit", decision, resolved_build=build)
    assert _tr_wanted((ctx,)) == 0


def test_two_hindering_natures_without_declared_sweeper_make_tr_essential():
    king = replace(resolve_anchor_build("Kingambit"), nature="Brave")
    goodra = replace(resolve_anchor_build("Goodra"), nature="Quiet")
    k_dec = classify_anchor_role(king)
    g_dec = classify_anchor_role(goodra)
    assert k_dec.role_id != "trick_room_sweeper"
    assert g_dec.role_id != "trick_room_sweeper"
    report = assess_condition_resilience(
        (
            _context_from_decision(0, "Kingambit", k_dec, resolved_build=king),
            _context_from_decision(1, "Goodra", g_dec, resolved_build=goodra),
        )
    )
    tr = next(r for r in report.conditions if r.condition == "Trick Room")
    assert tr.classification == "essential"
    assert sum(1 for d in tr.dependents if d.importance == "wanted") == 2
    live_kanga = resolve_anchor_build("Kangaskhan-Mega")
    live_torkoal = resolve_anchor_build("Torkoal")
    if live_kanga.nature == "Brave" and live_torkoal.nature == "Quiet":
        live = assess_condition_resilience(
            (
                _context_from_decision(
                    0,
                    "Kangaskhan-Mega",
                    classify_anchor_role(live_kanga),
                    resolved_build=live_kanga,
                ),
                _context_from_decision(
                    1,
                    "Torkoal",
                    classify_anchor_role(live_torkoal),
                    resolved_build=live_torkoal,
                ),
            )
        )
        live_tr = next(r for r in live.conditions if r.condition == "Trick Room")
        assert live_tr.classification == "essential"


def test_hatterene_quiet_is_not_a_tr_dependent():
    build = replace(resolve_anchor_build("Hatterene"), nature="Quiet")
    decision = classify_anchor_role(build)
    assert not _has_tr_benefit(decision)
    ctx = _context_from_decision(0, "Hatterene", decision, resolved_build=build)
    row = _tr_row((ctx,))
    assert row is None or not row.dependents


def test_brave_with_spe_ev_emits_but_does_not_vote():
    build = _with_spe(resolve_anchor_build("Kingambit"), 1, nature="Brave")
    decision = classify_anchor_role(build)
    assert _has_tr_benefit(decision)
    ctx = _context_from_decision(0, "Kingambit", decision, resolved_build=build)
    assert _tr_wanted((ctx,)) == 0


def test_garchomp_three_build_and_scarf_kingambit_are_discounted():
    cases = (
        resolve_anchor_build("Garchomp"),
        resolve_anchor_build("Garchomp", role_hint="trick_room_sweeper"),
        replace(resolve_anchor_build("Kingambit"), item="Choice Scarf"),
    )
    for build in cases:
        decision = _declared_tr(build)
        assert _has_tr_benefit(decision)
        ctx = _context_from_decision(
            0, build.species or "", decision, resolved_build=build
        )
        assert _tr_wanted((ctx,)) == 0


def test_declared_garchomp_mega_plus_kingambit_is_preferred_not_essential():
    garchomp = resolve_anchor_build("Garchomp-Mega")
    king = resolve_anchor_build("Kingambit")
    report = assess_condition_resilience(
        (
            _context_from_decision(
                0, "Garchomp-Mega", _declared_tr(garchomp), resolved_build=garchomp
            ),
            _context_from_decision(1, "Kingambit", _declared_tr(king), resolved_build=king),
        )
    )
    tr = next(r for r in report.conditions if r.condition == "Trick Room")
    assert tr.classification == "preferred"
    assert sum(1 for d in tr.dependents if d.importance == "wanted") == 1
    assert tr.gap == "missing_provider"
    residual = gap_support_needs(report, ())
    assert any(n.category == "trick_room" for n in residual)


def test_declared_kingambit_plus_kangaskhan_mega_is_essential():
    king = resolve_anchor_build("Kingambit")
    kanga = resolve_anchor_build("Kangaskhan-Mega")
    report = assess_condition_resilience(
        (
            _context_from_decision(0, "Kingambit", _declared_tr(king), resolved_build=king),
            _context_from_decision(
                1, "Kangaskhan-Mega", _declared_tr(kanga), resolved_build=kanga
            ),
        )
    )
    tr = next(r for r in report.conditions if r.condition == "Trick Room")
    assert tr.classification == "essential"
    assert sum(1 for d in tr.dependents if d.importance == "wanted") == 2


def test_needed_tr_is_never_discounted():
    build = _with_spe(resolve_anchor_build("Dragapult"), 0, nature="Hardy", item=None)
    decision = replace(
        classify_anchor_role(build),
        mechanisms=(_benefit("Trick Room", importance="needed", present=False),),
    )
    ctx = _context_from_decision(0, "Dragapult", decision, resolved_build=build)
    row = _tr_row((ctx,))
    assert row is not None
    assert any(d.importance == "needed" for d in row.dependents)
    assert row.classification == "essential"


def test_two_fast_tailwind_wants_still_essential():
    first = replace(
        classify_anchor_role(resolve_anchor_build("Dragapult")),
        mechanisms=(_benefit("Tailwind"),),
        primary_function="offense",
    )
    second = replace(
        classify_anchor_role(resolve_anchor_build("Gengar")),
        mechanisms=(_benefit("Tailwind"),),
        primary_function="offense",
    )
    report = assess_condition_resilience(
        (
            _context_from_decision(0, "Dragapult", first),
            _context_from_decision(1, "Gengar", second),
        )
    )
    tw = next(r for r in report.conditions if r.condition == "Tailwind")
    assert tw.classification == "essential"


def test_hatterene_plus_discounted_mega_garchomp_is_preferred_via_setter_direction():
    hatterene = resolve_anchor_build("Hatterene")
    garchomp = resolve_anchor_build("Garchomp-Mega")
    report = assess_condition_resilience(
        (
            _context_from_decision(
                0, "Hatterene", classify_anchor_role(hatterene), resolved_build=hatterene
            ),
            _context_from_decision(
                1, "Garchomp-Mega", _declared_tr(garchomp), resolved_build=garchomp
            ),
        )
    )
    tr = next(r for r in report.conditions if r.condition == "Trick Room")
    assert tr.classification == "preferred"
    assert sum(1 for d in tr.dependents if d.importance == "wanted") == 0
    assert tr.provider_count == 1


def test_speed_plus_and_minus_are_disjoint():
    assert not (_SPEED_PLUS & _SPEED_MINUS)
