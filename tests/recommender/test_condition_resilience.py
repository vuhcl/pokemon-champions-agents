"""Tests for condition resilience classification and gap need dedupe."""

from __future__ import annotations

from dataclasses import replace

import pytest

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


def test_gap_support_needs_does_not_fire_for_single_provider_spof_tailwind():
    """Regression: live testing (2026-08-21) showed Whimsicott/Aerodactyl kept
    surfacing as compendium-backed 'tailwind_setter' support picks *after* a
    real Tailwind provider (Pelipper) was already locked. Root cause: the
    already-provided filter in team_candidates.py strips satisfied tailwind/
    trick_room needs out of anchored_needs *before* passing that same tuple
    into gap_support_needs as existing_needs, so _condition_already_covered
    could never see the coverage it was supposed to check for, and
    gap_support_needs re-emitted a full-strength need for the
    single_provider_spof case every time. A real team never wants a second
    *primary* setter once one exists, so single_provider_spof must never
    reach gap_support_needs at all, regardless of what existing_needs
    contains.
    """
    report = ConditionResilienceReport(
        conditions=(
            ConditionResilienceRow(
                condition="Tailwind",
                classification="essential",
                provider_count=1,
                providers=(ConditionProviderMember(1, "Pelipper", "Tailwind"),),
                dependents=(),
                gap="single_provider_spof",
            ),
        )
    )
    # Even with existing_needs empty (the exact failure mode: the coverage
    # signal was already stripped upstream), single_provider_spof must not
    # generate a gap need on its own.
    assert gap_support_needs(report, ()) == ()


def test_gap_support_needs_does_not_fire_for_single_provider_spof_trick_room():
    report = ConditionResilienceReport(
        conditions=(
            ConditionResilienceRow(
                condition="Trick Room",
                classification="preferred",
                provider_count=1,
                providers=(ConditionProviderMember(1, "Sinistcha", "Trick Room"),),
                dependents=(),
                gap="single_provider_spof",
            ),
        )
    )
    assert gap_support_needs(report, ()) == ()


def test_gap_support_needs_does_not_fire_for_single_provider_spof_weather():
    report = ConditionResilienceReport(
        conditions=(
            ConditionResilienceRow(
                condition="Rain",
                classification="essential",
                provider_count=1,
                providers=(ConditionProviderMember(1, "Pelipper", "Drizzle"),),
                dependents=(),
                gap="single_provider_spof",
            ),
        )
    )
    # Backup-Rain-setter value is real but must come exclusively through
    # fills_spof_backup_gap / _candidate_fills_condition_gap, which annotates
    # candidates already in the pool for other reasons rather than searching
    # the Role Compendium's primary-setter tier list for a second specialist.
    assert gap_support_needs(report, ()) == ()


def test_anchor_has_obvious_need_archaludon_real_external_dependency():
    """Archaludon needs Rain for Electro Shot and can't provide it itself
    -- a real, unmet, needed-importance benefits_from dependency. Direct
    unit test using the real anchor pipeline (classify_anchor_role/
    resolve_anchor_build/query_support_needs), not a hand-constructed
    mock, matching this project's verification discipline.
    """
    from recommender.anchor_roles import classify_anchor_role, resolve_anchor_build
    from recommender.condition_resilience import anchor_has_obvious_need
    from recommender.support_needs import RoleShapeContext, query_support_needs

    build = resolve_anchor_build("Archaludon")
    decision = classify_anchor_role(build)
    shape = RoleShapeContext(
        primary_function="offense", tankiness="tanky", requires_setup_turn=False
    )
    needs = query_support_needs(build.as_pokemon(), shape)
    assert anchor_has_obvious_need(decision, needs) is True


def test_anchor_has_obvious_need_charizard_mega_y_self_sufficient():
    """Regression, confirmed live (2026-08-21): Charizard-Mega-Y needs Sun
    for Solar Beam but provides Sun itself via Drought -- a real needed
    dependency, but self-satisfied, so there's nothing external left to
    fill. Its only other real signal is a deliberately weak,
    stance="want" speed_tier:already_fast Tailwind ask ("further Speed
    still helps"), not a genuine gap -- must not count as obvious on its
    own, or this anchor would incorrectly keep single_locked's weaker
    candidate-generation path despite having nothing real to drive it.
    """
    from recommender.anchor_roles import classify_anchor_role, resolve_anchor_build
    from recommender.condition_resilience import anchor_has_obvious_need
    from recommender.support_needs import RoleShapeContext, query_support_needs

    build = resolve_anchor_build("Charizard-Mega-Y")
    decision = classify_anchor_role(build)
    shape = RoleShapeContext(
        primary_function="offense", tankiness="frail", requires_setup_turn=False
    )
    needs = query_support_needs(build.as_pokemon(), shape)
    assert anchor_has_obvious_need(decision, needs) is False


def test_anchor_has_obvious_need_handles_missing_mechanisms_attribute():
    """anchor_has_obvious_need must not raise when anchor_role_decision
    doesn't have a real .mechanisms attribute at all (e.g. a test double
    or an as-yet-unresolved decision) -- getattr default, not an
    assumption every caller passes a fully-resolved AnchorRoleDecision.
    """
    from recommender.condition_resilience import anchor_has_obvious_need

    assert anchor_has_obvious_need(object(), None) is False
    assert anchor_has_obvious_need(object(), []) is False


def _locked_for_reliability_test(species: str, **kw):
    from recommender.state import Attr, Slot

    return Slot(
        role=Attr(kw.get("role", "bulky_attacker"), locked=True),
        species=Attr(species, locked=True),
        ability=Attr(kw.get("ability", "Pressure"), locked=True),
        item=Attr(kw.get("item", "Leftovers"), locked=True),
        moveset=Attr(
            kw.get("moves") or ["Tackle", "Protect", "Rest", "Sleep Talk"], locked=True
        ),
        spread=Attr(
            kw.get("spread")
            or {"hp": 32, "atk": 32, "def": 2, "spa": 0, "spd": 0, "spe": 0},
            locked=True,
        ),
        nature=Attr(kw.get("nature", "Adamant"), locked=True),
    )


def test_condition_provider_reliability_reflects_real_commitment_split():
    """Regression, confirmed live (2026-08-22): Sinistcha's real, aggregate
    Trick Room commitment (57.2%) is barely more than a coinflip against
    its actual defining move, Rage Powder (95.6%) -- its real primary job
    is redirection, not a genuine Trick-Room-specialist build. Confirms
    the raw reliability primitive reflects this directly against real
    in-game data, and that a genuine specialist (Farigiraf) scores
    meaningfully higher on the same check.
    """
    from recommender.condition_resilience import condition_provider_reliability
    from recommender.state import empty_slot
    from recommender.team_candidates import collect_locked_anchor_contexts

    sinistcha_state = {
        "team_draft": [
            _locked_for_reliability_test(
                "Sinistcha",
                role="trick_room_setter",
                ability="Hospitality",
                item="Kasib Berry",
                moves=["Matcha Gotcha", "Rage Powder", "Trick Room", "Protect"],
                nature="Bold",
                spread={"hp": 32, "atk": 0, "def": 32, "spa": 2, "spd": 0, "spe": 0},
            ),
            *[empty_slot() for _ in range(5)],
        ]
    }
    contexts = collect_locked_anchor_contexts(sinistcha_state)
    reliability = condition_provider_reliability(
        "Trick Room", contexts, regulation="champions-reg-mb"
    )
    assert reliability == pytest.approx(0.572, abs=0.001)

    farigiraf_state = {
        "team_draft": [
            _locked_for_reliability_test(
                "Farigiraf",
                role="trick_room_setter",
                ability="Armor Tail",
                moves=["Trick Room", "Hyper Voice", "Helping Hand", "Protect"],
                nature="Sassy",
                spread={"hp": 32, "atk": 0, "def": 8, "spa": 0, "spd": 28, "spe": 0},
            ),
            *[empty_slot() for _ in range(5)],
        ]
    }
    contexts2 = collect_locked_anchor_contexts(farigiraf_state)
    reliability2 = condition_provider_reliability(
        "Trick Room", contexts2, regulation="champions-reg-mb"
    )
    assert reliability2 > reliability


def test_condition_provider_reliability_ability_based_is_always_full():
    """An ability-based provider (e.g. Drizzle) is mechanically certain
    and always-active -- must be 1.0 regardless of any move-commitment
    data, the same "ability-based = most mechanically certain evidence"
    reasoning already established for a different purpose (ADR-028
    Amendment 2026-08-20a).
    """
    from recommender.condition_resilience import condition_provider_reliability
    from recommender.state import empty_slot
    from recommender.team_candidates import collect_locked_anchor_contexts

    state = {
        "team_draft": [
            _locked_for_reliability_test(
                "Pelipper",
                role="support_speed_control",
                ability="Drizzle",
                item="Focus Sash",
                moves=["Hurricane", "Weather Ball", "Tailwind", "Wide Guard"],
                nature="Modest",
                spread={"hp": 2, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 32},
            ),
            *[empty_slot() for _ in range(5)],
        ]
    }
    contexts = collect_locked_anchor_contexts(state)
    assert (
        condition_provider_reliability("Rain", contexts, regulation="champions-reg-mb")
        == 1.0
    )


def test_condition_provider_reliability_no_provider_defaults_to_full():
    """No locked provider of the condition at all is a different, existing
    concern (missing dependency, not unreliable provision) -- must not be
    conflated with "unreliable," which would double-penalize a candidate
    already correctly handled by candidate_wastes_core_slot /
    candidate_has_unmet_needed_weather_dependency.
    """
    from recommender.condition_resilience import condition_provider_reliability

    assert (
        condition_provider_reliability("Trick Room", (), regulation="champions-reg-mb")
        == 1.0
    )


def test_candidate_dependency_reliability_mawile_mega_real_data():
    """Regression, confirmed live (2026-08-22): the actual motivating
    case -- Mawile-Mega's real Trick Room dependency (classified
    "wanted", not "needed" -- confirmed directly, every Trick Room
    benefits_from mechanism in this codebase is "wanted", never "needed",
    a real, deliberate distinction from weather-move dependencies like
    Electro Shot/Rain) inherits Sinistcha's real, middling reliability
    when Sinistcha is the team's provider, and a much higher one when a
    genuine specialist (Farigiraf) is.
    """
    from recommender.anchor_roles import classify_anchor_role, resolve_anchor_build
    from recommender.condition_resilience import candidate_dependency_reliability
    from recommender.state import empty_slot
    from recommender.team_candidates import collect_locked_anchor_contexts

    build = resolve_anchor_build("Mawile-Mega")
    decision = classify_anchor_role(build)

    sinistcha_state = {
        "team_draft": [
            _locked_for_reliability_test(
                "Sinistcha",
                role="trick_room_setter",
                ability="Hospitality",
                item="Kasib Berry",
                moves=["Matcha Gotcha", "Rage Powder", "Trick Room", "Protect"],
                nature="Bold",
                spread={"hp": 32, "atk": 0, "def": 32, "spa": 2, "spd": 0, "spe": 0},
            ),
            *[empty_slot() for _ in range(5)],
        ]
    }
    contexts = collect_locked_anchor_contexts(sinistcha_state)
    reliability = candidate_dependency_reliability(
        decision, contexts, regulation="champions-reg-mb"
    )
    assert reliability == pytest.approx(0.572, abs=0.001)

    farigiraf_state = {
        "team_draft": [
            _locked_for_reliability_test(
                "Farigiraf",
                role="trick_room_setter",
                ability="Armor Tail",
                moves=["Trick Room", "Hyper Voice", "Helping Hand", "Protect"],
                nature="Sassy",
                spread={"hp": 32, "atk": 0, "def": 8, "spa": 0, "spd": 28, "spe": 0},
            ),
            *[empty_slot() for _ in range(5)],
        ]
    }
    contexts2 = collect_locked_anchor_contexts(farigiraf_state)
    reliability2 = candidate_dependency_reliability(
        decision, contexts2, regulation="champions-reg-mb"
    )
    assert reliability2 > reliability


def test_candidate_dependency_reliability_no_dependency_is_full():
    """A candidate with no real TRACKED_CONDITIONS dependency at all must
    always get 1.0, regardless of what the locked team looks like --
    this function only judges reliability of a dependency that actually
    exists, never penalizes a candidate for having none.
    """
    from recommender.anchor_roles import classify_anchor_role, resolve_anchor_build
    from recommender.condition_resilience import candidate_dependency_reliability
    from recommender.state import empty_slot
    from recommender.team_candidates import collect_locked_anchor_contexts

    build = resolve_anchor_build("Garchomp")
    decision = classify_anchor_role(build)
    state = {
        "team_draft": [
            _locked_for_reliability_test(
                "Sinistcha",
                role="trick_room_setter",
                ability="Hospitality",
                item="Kasib Berry",
                moves=["Matcha Gotcha", "Rage Powder", "Trick Room", "Protect"],
            ),
            *[empty_slot() for _ in range(5)],
        ]
    }
    contexts = collect_locked_anchor_contexts(state)
    assert (
        candidate_dependency_reliability(
            decision, contexts, regulation="champions-reg-mb"
        )
        == 1.0
    )


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
