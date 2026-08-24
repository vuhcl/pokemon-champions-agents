"""Team-wide condition essentiality, provider cardinality, and gap needs."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from recommender.calc_client import FieldSpec

from recommender.anchor_roles import MechanismEvidence, ResolvedAnchorBuild
from recommender.condition_types import (
    MIN_WANTED_DEPENDENTS_FOR_ESSENTIAL,
    TRACKED_CONDITIONS,
    ConditionClass,
    ConditionDependentMember,
    ConditionGap,
    ConditionProviderMember,
    ConditionResilienceReport,
    ConditionResilienceRow,
)
from recommender.ids import to_id
from recommender.slot_fill import AnchoredSupportNeed, LockedAnchorContext
from recommender.support_needs import (
    SupportNeed,
    _spe_tier,
    _threat_speeds,
    field_labels_from_trigger,
)
from recommender.usage_spreads import _SPEED_PLUS, effective_spe

_SETTER_ROLE_FOR_CONDITION = {
    "Rain": "rain_setter",
    "Sun": "sun_setter",
    "Sand": "sand_setter",
    "Snow": "snow_setter",
    "Trick Room": "trick_room_setter",
    "Tailwind": "tailwind_setter",
}
_WEATHER_LABEL = {
    "Rain": "rain",
    "Sun": "sun",
    "Sand": "sand",
    "Snow": "snow",
}

__all__ = [
    "MIN_WANTED_DEPENDENTS_FOR_ESSENTIAL",
    "TRACKED_CONDITIONS",
    "ConditionClass",
    "ConditionDependentMember",
    "ConditionGap",
    "ConditionProviderMember",
    "ConditionResilienceReport",
    "ConditionResilienceRow",
    "assess_condition_resilience",
    "gap_support_needs",
    "mechanism_condition",
]


def mechanism_condition(m: MechanismEvidence) -> str | None:
    """Prefer evidence tag condition:X; else role_id *_setter; else mechanic name."""
    for item in m.evidence:
        if item.startswith("condition:"):
            condition = item.removeprefix("condition:")
            if condition in TRACKED_CONDITIONS:
                return condition
    if m.role_id:
        for condition, role_id in _SETTER_ROLE_FOR_CONDITION.items():
            if m.role_id == role_id:
                return condition
    if m.mechanic in {"Trick Room", "Tailwind"}:
        return m.mechanic
    return None


def _skipped_slots(
    *,
    exclude_slot: int | None = None,
    exclude_slots: frozenset[int] = frozenset(),
) -> frozenset[int]:
    skip = set(exclude_slots)
    if exclude_slot is not None:
        skip.add(exclude_slot)
    return frozenset(skip)


def provided_conditions(
    locked: Sequence[LockedAnchorContext],
    *,
    exclude_slot: int | None = None,
    exclude_slots: frozenset[int] = frozenset(),
) -> frozenset[str]:
    """The set of TRACKED_CONDITIONS this locked team already provides
    (e.g. {"Rain", "Tailwind"}) -- same mechanism-detection team_field_states
    uses, but returning condition names directly rather than FieldSpec
    dicts, for callers that just need to check "does the team already
    have X" (e.g. filtering already-satisfied support needs) rather than
    build calc input.
    """
    out: set[str] = set()
    skip = _skipped_slots(exclude_slot=exclude_slot, exclude_slots=exclude_slots)
    for context in locked:
        if context.slot_index in skip:
            continue
        role_decision = getattr(context, "role_decision", None)
        if role_decision is None:
            continue
        for mechanism in role_decision.mechanisms:
            if not mechanism.present or mechanism.relation != "provides":
                continue
            condition = mechanism_condition(mechanism)
            if condition is not None and condition in TRACKED_CONDITIONS:
                out.add(condition)
    return frozenset(out)


def _provider_move_commitment(
    species: str, move_id: str, regulation: str
) -> float | None:
    """Real in-game commitment (0-100) to move_id on species, or None if
    the species isn't in the in-game dataset at all -- a real data gap,
    distinct from "confirmed low commitment," matching the same
    distinction already established for usage/confidence elsewhere in
    this codebase (see ADR-028 Amendment 2026-08-22a).
    """
    from recommender.ids import to_id
    from recommender.usage_data import ingame_species_map

    entry = ingame_species_map(regulation).get(to_id(species))
    if entry is None:
        return None
    for m in entry.get("common_moves") or []:
        if to_id(str(m.get("name") or "")) == move_id:
            pct = m.get("pct")
            return float(pct) if pct is not None else None
    return 0.0


def condition_provider_reliability(
    condition: str, locked: Sequence[LockedAnchorContext], *, regulation: str
) -> float:
    """How much a dependent candidate should trust condition being real,
    reliable support -- 1.0 (fully reliable) down to 0.0, based on the
    BEST (most reliable) locked provider of condition, since a dependent
    only needs one good enabler.

    Confirmed live (2026-08-22): Mawile-Mega's real Trick Room dependency
    can be "satisfied" by a locked Sinistcha whose real, aggregate
    Trick Room commitment (57.2%) is barely more than a coinflip against
    its actual defining move, Rage Powder (95.6%) -- Sinistcha's real
    primary job is redirection, with Trick Room as a secondary, often-
    dropped tech option, not a genuine Trick-Room-specialist build the
    way Farigiraf is. The condition being physically present in THIS
    locked build doesn't resolve that: a low aggregate commitment rate is
    a proxy for "this isn't really a dedicated setter's build" (EVs,
    item, and moveset choices for a real specialist are generally
    optimized around reliably getting the condition up, in ways a
    secondary carrier's usually aren't), not a claim that the locked
    move might vanish.

    Ability-based providers (e.g. Drizzle) are always 1.0 -- an ability
    is mechanically certain/always-active, the same "ability-based match
    is the most mechanically certain evidence tier" reasoning already
    established (ADR-028 Amendment 2026-08-20a) for a different purpose.
    Move-based providers use their real in-game commitment percentage,
    normalized to 0-1. A real data gap (provider absent from the in-game
    dataset entirely) defaults to 1.0 -- not evidence of unreliability,
    the same "don't penalize a data gap as a negative signal" principle
    already established (ADR-034 Amendment 2026-08-23a) for a different
    purpose.
    """
    best = 0.0
    found_any = False
    for context in locked:
        role_decision = getattr(context, "role_decision", None)
        if role_decision is None:
            continue
        for mechanism in role_decision.mechanisms:
            if not mechanism.present or mechanism.relation != "provides":
                continue
            if mechanism_condition(mechanism) != condition:
                continue
            found_any = True
            if mechanism.activation != "move":
                best = max(best, 1.0)
                continue
            move_id = next(
                (
                    tag.removeprefix("move:")
                    for tag in mechanism.evidence
                    if tag.startswith("move:")
                ),
                None,
            )
            if move_id is None:
                best = max(best, 1.0)
                continue
            pct = _provider_move_commitment(
                context.resolved_build.species or "", move_id, regulation
            )
            reliability = 1.0 if pct is None else pct / 100.0
            best = max(best, reliability)
    return best if found_any else 1.0


def candidate_dependency_reliability(
    decision: object,
    locked: Sequence[LockedAnchorContext],
    *,
    regulation: str,
) -> float:
    """Worst-case reliability across every TRACKED_CONDITIONS dependency
    this candidate actually has satisfied by the locked team -- 1.0 if it
    has no such dependency, or if a dependency exists but is genuinely
    unmet (that's a different, existing concern -- see
    candidate_wastes_core_slot / candidate_has_unmet_needed_weather_
    dependency -- not something this function tries to also judge).

    Generalizes beyond weather specifically (the scope of the two
    functions above) to all six TRACKED_CONDITIONS, since Mawile-Mega's
    real dependency is Trick Room, not weather -- reuses
    mechanism_condition, which already covers the full set, rather than
    widening either of those weather-specific functions and risking
    their already-verified behavior.

    Deliberately includes BOTH "needed" and "wanted" importance tiers,
    unlike candidate_wastes_core_slot's stricter "needed"-only gate --
    confirmed directly that Trick Room/Tailwind benefits_from mechanisms
    are classified "wanted" everywhere in this codebase, never "needed"
    (weather-move dependencies like Electro Shot/Rain are the ones that
    get "needed", a real, deliberate distinction: a hindering-nature/
    slow-attacker TR preference is inherently softer and inferred, not
    tied to a specific locked move the way a real weather-move mechanic
    is). Also deliberately does not require mechanism.present -- "wanted"
    dependencies are typically present=False by design (inferred from
    role/nature, not concretely move-locked the way "needed" ones are);
    requiring it here would make this function unable to fire for
    exactly the case it exists to catch.
    """
    mechanisms = getattr(decision, "mechanisms", None)
    if not mechanisms:
        return 1.0
    provided = provided_conditions(locked)
    worst = 1.0
    for m in mechanisms:
        if m.relation != "benefits_from" or m.importance not in ("needed", "wanted"):
            continue
        condition = mechanism_condition(m)
        if condition is None or condition not in provided:
            continue
        worst = min(
            worst, condition_provider_reliability(condition, locked, regulation=regulation)
        )
    return worst


def has_reliable_screens_provider(
    locked: Sequence[LockedAnchorContext],
    *,
    exclude_slot: int | None = None,
    exclude_slots: frozenset[int] = frozenset(),
) -> bool:
    """Whether the locked team already has a genuinely committed screens
    setter -- not just anyone carrying a single screen move incidentally.

    Screens (Light Screen/Reflect/Aurora Veil) is deliberately NOT one of
    TRACKED_CONDITIONS (see ADR-028's original scoping) -- it doesn't fit
    the same 0/1/2+ provider-cardinality model weather/Trick Room/Tailwind
    do. This is a narrower, boolean check for a narrower purpose: the
    unconditional "screens" support need (query_support_needs fires it for
    every offense-primary anchor, trigger=None, with zero team-state
    awareness) has no equivalent of the already-provided filter tailwind/
    trick_room got, and confirmed live, that meant a genuine screens setter
    (Grimmsnarl, real Light Clay + both Light Screen and Reflect) didn't
    stop a second screens candidate (Sableye) from surfacing turn after
    turn the same way Whimsicott/Aerodactyl did for tailwind before that
    fix. This does not attempt to model screens' own provider-cardinality
    question (Light Clay + Item Clause exclusivity, confirmed real in
    conversation but out of scope here) -- it only answers "is there
    already a real, primary screens setter," using the same wanted/
    secondary distinction anchor_roles.py's screens mechanism already
    computes (Aurora Veil, or both Light Screen and Reflect, or Light Clay
    with at least one screen move present) -- someone running Reflect as
    a single incidental move does not count.
    """
    skip = _skipped_slots(exclude_slot=exclude_slot, exclude_slots=exclude_slots)
    for context in locked:
        if context.slot_index in skip:
            continue
        role_decision = getattr(context, "role_decision", None)
        if role_decision is None:
            continue
        for mechanism in role_decision.mechanisms:
            if (
                mechanism.present
                and mechanism.relation == "provides"
                and mechanism.kind == "screens"
                and mechanism.importance == "wanted"
            ):
                return True
    return False


def anchor_has_obvious_need(
    anchor_role_decision: object,
    support_needs: Sequence[SupportNeed] | None,
) -> bool:
    """Whether a single locked anchor has a genuine, externally-facing need
    -- something else on the team would actually need to fill -- as
    opposed to nothing obvious at all.

    Confirmed live (2026-08-21): discover_single_locked produces sharp,
    well-targeted candidates when the anchor has a real external
    dependency (e.g. Archaludon needs Rain for Electro Shot and can't
    provide it itself -- query_support_needs correctly identifies a real
    gap, driving real Rain-setter suggestions). It produces much weaker,
    near-arbitrary candidates when the anchor has nothing obvious to fill
    -- either because its own real "needed" dependency is self-satisfied
    (Charizard-Mega-Y needs Sun for Solar Beam, but provides Sun itself
    via Drought -- no outstanding gap for anything else to fill) or
    because it only ever generates the generic, unconditional
    "attacker-universal" fallback needs (healing_cleric/screens,
    trigger=None -- real but deliberately low-confidence, not a specific
    ask). This is the signal used to decide whether to keep
    discover_single_locked's own candidate generation (works well, proven
    live) or route to discover_multi_locked instead (better-tested
    machinery: field-aware threat coverage progressively fixed across
    ADR-028's amendments, real query_shared_teammates co-occurrence data,
    the select_diverse_candidates category architecture) rather than
    maintaining a second, weaker copy of the same problem.

    Returns True (an obvious need exists, keep single_locked's own path)
    if either:
    - Any support_needs entry has a real, specific trigger (not None --
      the generic attacker-universal fallback is deliberately excluded)
      AND isn't explicitly marked a weak "want" stance -- confirmed live:
      speed_tier:already_fast is a real, specifically-triggered Tailwind
      need ("further Speed still helps against faster threats") but is
      deliberately stance="want", the same deliberately-weak tier as a
      strategic Trick-Room-sweeper's own aspirational TR ask -- neither
      should count as "obvious" on their own, or Charizard-Mega-Y (fast,
      self-sufficient for its own real needed dependency) would have
      incorrectly kept single_locked's weaker path anyway. Every other
      need category never sets stance at all (stays None), so this only
      narrows the specific, already-identified weak tier -- it doesn't
      require every need to explicitly opt in.
    - The anchor has an unmet, needed-importance benefits_from mechanism
      for a condition it doesn't already provide itself.

    Does NOT attempt to judge whether a candidate would conflict with the
    anchor's own kit or locked weather -- that's a distinct, currently
    unimplemented check (see resolve_condition_beneficiaries/
    resolve_need_candidates), not something this routing decision can or
    should paper over.
    """
    if support_needs and any(
        need.trigger is not None and need.stance != "want" for need in support_needs
    ):
        return True
    mechanisms = getattr(anchor_role_decision, "mechanisms", None)
    if not mechanisms:
        return False
    provided = {
        mechanism_condition(m)
        for m in mechanisms
        if m.present and m.relation == "provides"
    }
    for m in mechanisms:
        if m.present and m.relation == "benefits_from" and m.importance == "needed":
            condition = mechanism_condition(m)
            if condition is None or condition not in provided:
                return True
    return False


def team_field_states(
    locked: Sequence[LockedAnchorContext],
    *,
    exclude_slot: int | None = None,
    exclude_slots: frozenset[int] = frozenset(),
) -> list["FieldSpec"]:
    """Real, achievable field states this locked team can produce -- one
    FieldSpec per distinct provided condition, not a single combined
    state (only one weather can be active at a time, and Trick Room can
    be toggled back off by re-setting it -- each condition is tested as
    its own independently achievable field, matching how
    compute_team_coverage's forced-field fallback already tries each
    field separately rather than combining them).

    Covers both ability- and move-based providers via mechanism_condition
    (the same detection condition_resilience.py already uses elsewhere)
    -- unlike the narrower, ability-only lookup this replaces, which
    could never have detected Tailwind at all, since there is no
    Tailwind-setting ability; Tailwind is always move-based.

    Confirmed with Vu directly: Trick Room is represented as a global
    field flag (not side-specific, unlike Tailwind) -- setting it again
    while active reverses it back to normal order, but that's a
    turn-sequencing nuance for live play, not something this static
    "can the team produce this condition at all" check needs to model;
    each field state here is tested independently by the caller, which
    already accommodates that. Tailwind and Trick Room only affect
    speed/turn order (unlike weather/terrain's direct damage
    interactions) -- that's handled correctly by the real calc engine
    once given the right FieldSpec input; this function's only job is
    constructing that input correctly, not modeling the mechanics itself.
    """
    out: list["FieldSpec"] = []
    seen: set[str] = set()
    skip = _skipped_slots(exclude_slot=exclude_slot, exclude_slots=exclude_slots)
    for context in locked:
        if context.slot_index in skip:
            continue
        role_decision = getattr(context, "role_decision", None)
        if role_decision is None:
            continue
        for mechanism in role_decision.mechanisms:
            if not mechanism.present or mechanism.relation != "provides":
                continue
            condition = mechanism_condition(mechanism)
            if condition is None or condition not in TRACKED_CONDITIONS or condition in seen:
                continue
            seen.add(condition)
            if condition in _WEATHER_LABEL:
                out.append({"weather": condition, "gameType": "Doubles"})  # type: ignore[typeddict-item]
            elif condition == "Trick Room":
                out.append({"isTrickRoom": True, "gameType": "Doubles"})  # type: ignore[typeddict-item]
            elif condition == "Tailwind":
                out.append(
                    {
                        "attackerSide": {"isTailwind": True},
                        "gameType": "Doubles",
                    }
                )
    return out


def _as_support_need(
    need: SupportNeed | AnchoredSupportNeed,
) -> SupportNeed:
    return need if isinstance(need, SupportNeed) else need.need


def _preferred_setter_direction(
    locked: Sequence[LockedAnchorContext], condition: str
) -> bool:
    setter_id = _SETTER_ROLE_FOR_CONDITION[condition]
    has_setter = False
    has_offense = False
    for context in locked:
        decision = context.role_decision
        roles = (decision.role_id, *decision.secondary_role_ids)
        if setter_id in roles:
            has_setter = True
        if (
            decision.primary_function == "offense"
            and decision.role_id != setter_id
        ):
            has_offense = True
    return has_setter and has_offense


_TR_SPE_GAP_MIN = 15


def _tr_spe_discount_floor(threat_speeds: list[int]) -> int | None:
    """High side of the largest interior Spe gap, else already_fast. None if no signal."""
    uniq = sorted(set(threat_speeds))
    pairs = list(zip(uniq, uniq[1:]))
    interior = pairs[1:-1] if len(pairs) > 2 else ()
    best_gap = 0
    best_hi: int | None = None
    for lo, hi in interior:
        gap = hi - lo
        if gap > best_gap:
            best_gap, best_hi = gap, hi
    if best_hi is not None and best_gap >= _TR_SPE_GAP_MIN:
        return best_hi
    if not threat_speeds:
        return None
    for spe in range(0, max(threat_speeds) + 2):
        if _spe_tier(spe, threat_speeds) == "already_fast":
            return spe
    return None


def _discount_tr_wanted(build: ResolvedAnchorBuild, floor: int | None) -> bool:
    """True when this locked member should not add a Trick Room wanted vote."""
    if int(build.spread.get("spe", 0) or 0) > 0:
        return True
    scarf = to_id(build.item or "") == "choicescarf"
    if scarf:
        return True
    nature = build.nature or "Hardy"
    if nature in _SPEED_PLUS:
        return True
    if floor is None or not build.species:
        return False
    return effective_spe(build.species, build.spread, nature, scarf=scarf) >= floor


def assess_condition_resilience(
    locked: Sequence[LockedAnchorContext],
) -> ConditionResilienceReport:
    rows: list[ConditionResilienceRow] = []
    tr_floor: int | None = None
    if locked:
        regulation = next(
            (c.resolved_build.regulation for c in locked),
            "champions-reg-mb",
        )
        tr_floor = _tr_spe_discount_floor(_threat_speeds(None, regulation))
    for condition in TRACKED_CONDITIONS:
        providers: list[ConditionProviderMember] = []
        dependents: list[ConditionDependentMember] = []
        seen_providers: set[int] = set()
        seen_dependents: set[int] = set()

        for context in locked:
            species = str(
                context.resolved_build.species or context.pokemon.get("species") or ""
            )
            best_dependent: Literal["needed", "wanted"] | None = None
            provider_mechanic: str | None = None
            for mechanism in context.role_decision.mechanisms:
                if mechanism_condition(mechanism) != condition:
                    continue
                if mechanism.present and mechanism.relation == "provides":
                    provider_mechanic = mechanism.mechanic
                if (
                    mechanism.relation == "benefits_from"
                    and mechanism.importance in ("needed", "wanted")
                    and (mechanism.present or mechanism.supply == "teammate_expected")
                ):
                    if mechanism.importance == "needed" or best_dependent is None:
                        best_dependent = mechanism.importance  # type: ignore[assignment]
            if provider_mechanic is not None and context.slot_index not in seen_providers:
                seen_providers.add(context.slot_index)
                providers.append(
                    ConditionProviderMember(
                        context.slot_index, species, provider_mechanic
                    )
                )
            if best_dependent is not None and context.slot_index not in seen_dependents:
                if (
                    condition == "Trick Room"
                    and best_dependent == "wanted"
                    and _discount_tr_wanted(context.resolved_build, tr_floor)
                ):
                    continue
                seen_dependents.add(context.slot_index)
                dependents.append(
                    ConditionDependentMember(
                        context.slot_index, species, best_dependent
                    )
                )

        provider_count = len(providers)
        needed = sum(1 for row in dependents if row.importance == "needed")
        wanted = sum(1 for row in dependents if row.importance == "wanted")

        if needed or wanted >= MIN_WANTED_DEPENDENTS_FOR_ESSENTIAL:
            classification: ConditionClass = "essential"
        elif wanted or _preferred_setter_direction(locked, condition):
            classification = "preferred"
        elif provider_count:
            classification = "optional"
        else:
            continue

        if classification in ("essential", "preferred"):
            if provider_count == 0:
                gap: ConditionGap = "missing_provider"
            elif provider_count == 1:
                gap = "single_provider_spof"
            else:
                gap = "none"
        else:
            gap = "none"

        secondary: tuple[ConditionProviderMember, ...] = ()
        if condition in ("Trick Room", "Tailwind"):
            hits: list[ConditionProviderMember] = []
            for context in locked:
                species = str(
                    context.resolved_build.species
                    or context.pokemon.get("species")
                    or ""
                )
                for mechanism in context.role_decision.mechanisms:
                    if (
                        mechanism.present
                        and mechanism.kind == "secondary_speed_control"
                        and mechanism.relation == "provides"
                    ):
                        hits.append(
                            ConditionProviderMember(
                                context.slot_index, species, mechanism.mechanic
                            )
                        )
            secondary = tuple(hits)

        rows.append(
            ConditionResilienceRow(
                condition=condition,
                classification=classification,
                provider_count=provider_count,
                providers=tuple(providers),
                dependents=tuple(dependents),
                gap=gap,
                secondary_speed_control=secondary,
            )
        )
    return ConditionResilienceReport(conditions=tuple(rows))


def _condition_already_covered(
    condition: str, existing_needs: Sequence[SupportNeed | AnchoredSupportNeed]
) -> bool:
    for raw in existing_needs:
        need = _as_support_need(raw)
        if condition == "Trick Room" and need.category == "trick_room":
            return True
        if condition == "Tailwind" and need.category == "tailwind":
            return True
        if condition in _WEATHER_LABEL and need.category == "condition_setter":
            labels = field_labels_from_trigger(need.trigger or "")
            if _WEATHER_LABEL[condition] in labels:
                return True
    return False


def gap_support_needs(
    report: ConditionResilienceReport,
    existing_needs: Sequence[SupportNeed] | Sequence[AnchoredSupportNeed],
) -> tuple[SupportNeed, ...]:
    """Emit gap needs only for conditions with zero providers.

    A ``single_provider_spof`` gap is deliberately excluded here, not just
    deduplicated: a real team never wants a second *primary* setter for a
    condition it already has one of -- the ``existing_needs`` dedup check
    below can't reliably distinguish "genuinely missing" from "already
    covered, backup would be nice" once the caller has already filtered
    already-satisfied needs out of ``existing_needs`` upstream (team_
    candidates.py's already-provided filter), which silently defeated this
    dedup for exactly the essential/preferred, single-provider case.
    Backup-provider value for an existing single provider is real but is a
    *different* candidate shape (a secondary provider found via divergence
    from the existing provider, not a primary-role Compendium search) and
    is handled exclusively by ``fills_spof_backup_gap`` /
    ``_candidate_fills_condition_gap``.
    """
    out: list[SupportNeed] = []
    for row in report.conditions:
        if row.gap != "missing_provider":
            continue
        if _condition_already_covered(row.condition, existing_needs):
            continue
        if row.condition in _WEATHER_LABEL:
            label = _WEATHER_LABEL[row.condition]
            out.append(
                SupportNeed(
                    category="condition_setter",
                    name=f"{row.condition} setter",
                    description=(
                        f"Team {row.classification} {row.condition} plan has "
                        f"provider gap ({row.gap})."
                    ),
                    trigger=f"field_condition:any:{label}",
                    notes=f"condition_resilience:{row.gap}",
                )
            )
        elif row.condition == "Trick Room":
            out.append(
                SupportNeed(
                    category="trick_room",
                    name="Trick Room",
                    description=(
                        f"Team {row.classification} Trick Room plan has "
                        f"provider gap ({row.gap})."
                    ),
                    trigger="condition_resilience:gap",
                    stance="need",
                )
            )
        elif row.condition == "Tailwind":
            out.append(
                SupportNeed(
                    category="tailwind",
                    name="Tailwind",
                    description=(
                        f"Team {row.classification} Tailwind plan has "
                        f"provider gap ({row.gap})."
                    ),
                    trigger="condition_resilience:gap",
                    stance="need",
                )
            )
    return tuple(out)
