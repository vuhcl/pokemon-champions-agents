"""Team-level candidate collection and ranking for multi-locked rosters."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from recommender.anchor_roles import (
    AnchorRoleDecision,
    ResolvedAnchorBuild,
    classify_anchor_role,
    derive_role_shape_context,
    resolve_anchor_build,
)
from recommender.condition_resilience import (
    ConditionResilienceReport,
    candidate_dependency_reliability,
    gap_support_needs,
    mechanism_condition,
)
from recommender.divergence import (
    DIVERGENCE_COMPLEMENTARY_THRESHOLD,
    PROVIDER_TAG_BY_CONDITION,
    divergence_score,
)
from recommender.primary_function_resilience import assess_primary_function_resilience
from recommender.primary_function_types import PrimaryFunctionResilienceReport
from recommender.ids import to_id
from recommender.legality import is_species_legal, load_snapshot
from recommender.ranking import OwnershipMode, rank_and_cut
from recommender.reconcile import _item_mega_forme
from recommender.slot_fill import (
    AnnotatedCandidate,
    AnchoredSupportNeed,
    CoreSlotConflict,
    LockedAnchorContext,
    SlotFillContext,
    _kit_fallback_target_role,
    resolve_all_support_needs,
    resolve_condition_beneficiaries,
    resolve_need_candidates,
    target_role_from_anchored_needs,
)
from recommender.state import (
    Attr,
    CandidateBranch,
    CandidateEvidence,
    ReasonRef,
    RecommenderState,
    Slot,
    TargetRoleDecision,
    TeamCompletionPreference,
    TeamReviewResult,
    TeamThreatObjectiveRow,
    ThreatCandidate,
    ThreatCounterCandidate,
    all_locked,
)
from recommender.support_needs import SupportNeed, query_support_needs
from recommender.teammates import SharedTeammateQueryResult
from recommender.usage_data import featured_or_common_set, lineage_ids
from recommender.usage_spreads import move_category_counts

# Champions: only Eternal Flower Floette can Mega Evolve (not plain Floette).
_FLOETTE_DENY_SID = "floette"
_FLOETTE_ETERNAL_SID = "floetteeternal"
_FLOETTE_MEGA_SID = "floettemega"
# Pikalytics team-usage pairs label the lineage `floetteeternal`; Showdown panel
# primaries use `floettemega`. Co-occurrence lookup only — not a calc/legality alias.
_PAIR_LOOKUP_ALIASES = {_FLOETTE_MEGA_SID: _FLOETTE_ETERNAL_SID}


def pair_lookup_species_id(species_id: str) -> str:
    """Map panel species id → id used in team-composition pair files."""
    return _PAIR_LOOKUP_ALIASES.get(species_id, species_id)


def panel_species_id_from_pair_id(pair_id: str, panel_ids: set[str]) -> str | None:
    """Join a pair-file id onto a panel member id (Floette bridge both ways)."""
    if pair_id in panel_ids:
        return pair_id
    if pair_id == _FLOETTE_ETERNAL_SID and _FLOETTE_MEGA_SID in panel_ids:
        return _FLOETTE_MEGA_SID
    return None


def _is_mega_sid(species_id: str) -> bool:
    return species_id.endswith(("mega", "megax", "megay"))


def mega_useful_ceiling(team_size: int, pick_count: int) -> int:
    return 1 + (team_size - pick_count)


def mega_ceiling_notices(state: RecommenderState) -> tuple[str, ...]:
    pick_count = state.get("picked_team_size")
    if pick_count is None:
        return ()
    draft = state.get("team_draft") or []
    snap = load_snapshot()
    bases: set[str] = set()
    for slot in draft:
        if not all_locked(slot) or not slot.species.value:
            continue
        sid = to_id(slot.species.value)
        base = lineage_ids(sid)[0]
        item = to_id(slot.item.value or "")
        if _is_mega_sid(sid) or _item_mega_forme(item, base, snap):
            bases.add(base)
    n = len(bases)
    if n == 0:
        return ()
    ceiling = mega_useful_ceiling(len(draft), pick_count)
    return (
        f"{n} of {ceiling} Mega-Stone holders locked — "
        "only one can Mega Evolve per battle.",
    )


def _candidate_mega_base(build: ResolvedAnchorBuild, snap: dict) -> str | None:
    """Returns the lineage base id if this build is itself a mega-stone
    holder (mega form species, or a mega stone item on the matching base),
    else None. Shared by mega_ceiling_notices' locked-side detection and
    candidate_wastes_core_slot's candidate-side detection, so they can't
    silently drift into two different notions of "is this a mega."
    """
    sid = to_id(build.species or "")
    if not sid:
        return None
    base = lineage_ids(sid)[0]
    item = to_id(build.item or "")
    if _is_mega_sid(sid) or _item_mega_forme(item, base, snap):
        return base
    return None


_WEATHERS = frozenset({"Rain", "Sun", "Sand", "Snow"})


def candidate_core_slot_conflicts(
    decision: AnchorRoleDecision,
    build: ResolvedAnchorBuild,
    locked: Sequence[LockedAnchorContext],
    *,
    is_core_slot: bool,
) -> tuple[CoreSlotConflict, ...]:
    """Locked members this candidate conflicts with over weather or mega."""
    if not is_core_slot:
        return ()
    from recommender.condition_resilience import mechanism_condition, provided_conditions
    from recommender.legality import load_snapshot

    snap = load_snapshot()
    conflicts: list[CoreSlotConflict] = []
    candidate_mega_base = _candidate_mega_base(build, snap)
    if candidate_mega_base is not None:
        for context in locked:
            locked_mega_base = _candidate_mega_base(context.resolved_build, snap)
            if locked_mega_base is not None and locked_mega_base != candidate_mega_base:
                conflicts.append(
                    CoreSlotConflict(
                        kind="mega",
                        locked_slot_index=context.slot_index,
                        locked_species=context.resolved_build.species or "",
                        resource=locked_mega_base,
                    )
                )
    locked_weathers = provided_conditions(locked) & _WEATHERS
    if locked_weathers:
        needed: set[str] = set()
        for m in decision.mechanisms:
            if m.present and m.relation == "benefits_from" and m.importance == "needed":
                condition = mechanism_condition(m)
                if condition in _WEATHERS and condition not in locked_weathers:
                    needed.add(condition)
        if needed:
            for context in locked:
                role_decision = getattr(context, "role_decision", None)
                if role_decision is None:
                    continue
                for mechanism in role_decision.mechanisms:
                    if not mechanism.present or mechanism.relation != "provides":
                        continue
                    provided = mechanism_condition(mechanism)
                    if provided in locked_weathers:
                        conflicts.append(
                            CoreSlotConflict(
                                kind="weather",
                                locked_slot_index=context.slot_index,
                                locked_species=context.resolved_build.species or "",
                                resource=provided,
                            )
                        )
                        break
    return tuple(conflicts)


def candidate_wastes_core_slot(
    decision: AnchorRoleDecision,
    build: ResolvedAnchorBuild,
    locked: Sequence[LockedAnchorContext],
    *,
    is_core_slot: bool,
) -> bool:
    """Whether recommending this candidate for THIS slot would waste a
    core-team slot on a scarce, single-use resource that's already
    claimed in a conflicting way.

    Confirmed live (2026-08-21): Swampert-Mega (real Rain-abuse value)
    surfaced as a top-3 "threat coverage + type synergy" pick for slot 4
    on a team already committed to Sun via a locked Charizard-Mega-Y --
    Sun and Rain are mutually exclusive, so Swampert-Mega's actual
    distinguishing strength can never fire on this team as currently
    built. A second mega-stone holder is the same shape of problem: only
    one Pokemon can Mega Evolve per battle, so a second one occupying one
    of the first picked_team_size slots wastes that slot's real,
    always-available flexibility on a mechanic that's already spoken for.

    Deliberately scoped to is_core_slot only -- a second weather or mega
    is legitimate, real alternate-core bench value once the core is
    settled (confirmed: real teams build a Sun-core AND a Rain-core
    variant sharing the same locked anchors, swapped in per matchup),
    not something to discourage there. Callers are responsible for
    computing is_core_slot (slot_index < picked_team_size) -- this
    function only judges the resource-conflict question, not slot
    position, to keep the two concerns independently testable.
    """
    return bool(
        candidate_core_slot_conflicts(
            decision, build, locked, is_core_slot=is_core_slot
        )
    )


def candidate_has_unmet_needed_weather_dependency(
    decision: AnchorRoleDecision, locked: Sequence[LockedAnchorContext]
) -> bool:
    """Whether this candidate has a real, needed-importance benefits_from
    weather dependency that the locked team doesn't already provide.

    Used to gate candidate_improves_best_bring (bench-slot coverage-
    subset evaluation) to candidates with no hard dependency at all.
    Evaluating a dependent candidate (Mega-Swampert-shaped) alone would
    produce an honestly WRONG coverage number, not just an incomplete
    one -- team_field_states only forces a weather onto a subset's
    matchup calc if that subset actually contains a real provider, so a
    solo evaluation understates the candidate's real value rather than
    just failing to credit it. Correctly pairing a dependent candidate
    with a real provider (confirmed in design discussion: this is a
    two-slot-at-once decision, not a ranking tweak) is a separate,
    not-yet-built capability -- deliberately not approximated here.
    Reuses the exact same mechanism_condition/provided_conditions check
    as candidate_wastes_core_slot's weather half, since it's the same
    underlying question asked for a different purpose (is this
    dependency unmet at all, vs. does it specifically conflict).
    """
    from recommender.condition_resilience import mechanism_condition, provided_conditions

    _WEATHERS = frozenset({"Rain", "Sun", "Sand", "Snow"})
    provided = provided_conditions(locked) & _WEATHERS
    for m in decision.mechanisms:
        if m.present and m.relation == "benefits_from" and m.importance == "needed":
            condition = mechanism_condition(m)
            if condition in _WEATHERS and condition not in provided:
                return True
    return False


def _threat_id(threat: ThreatCandidate) -> str:
    return to_id(threat.spec.get("species") or threat.form or threat.ladder_species)


def _fallback_threat(spec: dict) -> ThreatCandidate:
    species = str(spec.get("species") or "")
    return ThreatCandidate(
        ladder_species=species,
        usage_rank=None,
        form=species,
        showdown_usage_pct=None,
        showdown_formes=(),
        spec=spec,
        build_source="team_review",
    )


def build_team_threat_objective(
    review: TeamReviewResult,
) -> tuple[TeamThreatObjectiveRow, ...]:
    """Merge uncovered coverage rows and SPOFs by exact normalized threat ID."""
    threats = {_threat_id(threat): threat for threat in review.threats}
    baseline = {
        to_id(row.threat.get("species") or ""): row.best_outcome
        for row in review.coverage
    }
    rows: dict[str, dict] = {}
    for coverage in review.coverage:
        threat_id = to_id(coverage.threat.get("species") or "")
        if threat_id and not coverage.covering_slot_indices:
            rows[threat_id] = {
                "threat": threats.get(threat_id) or _fallback_threat(coverage.threat),
                "kinds": {"uncovered"},
                "slots": set(),
                "baseline": coverage.best_outcome,
            }
    for finding in review.spofs:
        for spec in finding.threats_lost:
            threat_id = to_id(spec.get("species") or "")
            if not threat_id:
                continue
            row = rows.setdefault(
                threat_id,
                {
                    "threat": threats.get(threat_id) or _fallback_threat(spec),
                    "kinds": set(),
                    "slots": set(),
                    "baseline": baseline.get(threat_id),
                },
            )
            row["kinds"].add("spof")
            row["slots"].add(finding.slot_index)
    return tuple(
        TeamThreatObjectiveRow(
            threat=row["threat"],
            kinds=frozenset(row["kinds"]),
            spof_slot_indices=tuple(sorted(row["slots"])),
            baseline_outcome=row["baseline"],
        )
        for _, row in sorted(rows.items())
    )


def owned_species_ids(state: RecommenderState) -> frozenset[str]:
    """Exact pool species IDs plus base-form-only Mega ownership expansion."""
    snap = load_snapshot()
    owned: set[str] = set()
    for row in state.get("available_pool", []):
        sid = to_id(row.get("species") or "")
        if not sid:
            continue
        owned.add(sid)
        if sid == _FLOETTE_DENY_SID:
            continue
        if sid == _FLOETTE_ETERNAL_SID and is_species_legal(snap, _FLOETTE_MEGA_SID):
            owned.add(_FLOETTE_MEGA_SID)
            continue
        for kid in lineage_ids(sid):
            if not _is_mega_sid(kid) or not is_species_legal(snap, kid):
                continue
            if sid == lineage_ids(kid)[0]:
                owned.add(kid)
    return frozenset(owned)


def collect_locked_anchor_contexts(
    state: RecommenderState,
) -> tuple[LockedAnchorContext, ...]:
    regulation = state.get("regulation_mod") or "champions-reg-mb"
    masked = frozenset(state.get("masked_slot_indices") or ())
    contexts: list[LockedAnchorContext] = []
    for slot_index, slot in enumerate(state["team_draft"]):
        if slot_index in masked:
            continue
        if not all_locked(slot) or not slot.species.value:
            continue
        resolved = resolve_anchor_build(
            slot,
            role_hint=slot.role.value,
            regulation=regulation,
        )
        decision = classify_anchor_role(
            resolved,
            explicit_role=slot.role.value if slot.role.locked else None,
        )
        shape = derive_role_shape_context(decision)
        pokemon = resolved.as_pokemon()
        anchor_id = to_id(resolved.species or "")
        needs = tuple(
            AnchoredSupportNeed(slot_index, anchor_id, need)
            for need in query_support_needs(
                pokemon,
                shape,
                team_draft=state["team_draft"],
                state=state,
                regulation=regulation,
            )
        )
        contexts.append(
            LockedAnchorContext(
                slot_index=slot_index,
                anchor_id=anchor_id,
                pokemon=pokemon,
                resolved_build=resolved,
                role_decision=decision,
                role_shape_context=shape,
                support_needs=needs,
            )
        )
    return tuple(contexts)


def _candidate_species(candidate: ThreatCounterCandidate) -> str:
    row = candidate.candidate
    return str(row.spec.get("species") or row.form or row.ladder_species)


def _merge_evidence(
    left: tuple[CandidateEvidence, ...], right: tuple[CandidateEvidence, ...]
) -> tuple[CandidateEvidence, ...]:
    return tuple(dict.fromkeys((*left, *right)))


def _source(branches: frozenset[CandidateBranch]) -> str:
    if branches == {"threat"}:
        return "threat"
    if branches == {"need"}:
        return "need"
    if branches == {"teammate"}:
        return "teammate"
    if branches == {"threat", "need"}:
        return "both"
    return "mixed"


def merge_multi_locked_candidates(
    state: RecommenderState,
    anchor_contexts: Sequence[LockedAnchorContext],
    threat_candidates: Sequence[ThreatCounterCandidate],
    shared: SharedTeammateQueryResult | None,
    *,
    ownership_mode: OwnershipMode,
    owned_species: frozenset[str],
    condition_resilience: ConditionResilienceReport | None = None,
) -> list[AnnotatedCandidate]:
    """Merge threat, anchored-need, and exact shared evidence by species ID."""
    locked_lineages = {
        lineage
        for context in anchor_contexts
        for lineage in lineage_ids(context.resolved_build.species or "")
    }
    rejected_lineages = {
        lineage
        for row in state.get("rejected", [])
        for lineage in lineage_ids(row["species"])
    }

    def eligible(species: str) -> bool:
        species_id = to_id(species)
        return bool(
            species_id
            and species_id not in locked_lineages
            and not (set(lineage_ids(species)) & rejected_lineages)
            and (ownership_mode != "owned_only" or species_id in owned_species)
        )

    by_id: dict[str, AnnotatedCandidate] = {}
    for threat in threat_candidates:
        species = _candidate_species(threat)
        if not eligible(species):
            continue
        evidence = tuple(
            CandidateEvidence(
                basis=(
                    "usage_backed"
                    if threat.candidate.usage_rank is not None
                    else "mechanical_only"
                ),
                confidence="high" if threat.verified_vs else "medium",
                producer_name="query_candidates_for_threats",
                evidence=(f"verified_score:{threat.verified_score}",),
                branch="threat",
                subject_id=threat_id,
            )
            for threat_id in threat.threats_countered
        )
        species_id = to_id(species)
        by_id[species_id] = AnnotatedCandidate(
            species=species,
            matching_needs=(),
            source="threat",
            threat_row=threat,
            spec=threat.candidate.spec,
            evidence=evidence,
            branches=frozenset({"threat"}),
        )

    anchored_needs = tuple(
        need for context in anchor_contexts for need in context.support_needs
    )
    from recommender.condition_resilience import (
        has_reliable_screens_provider,
        provided_conditions,
        team_field_states,
    )

    # Filter out already-satisfied provider needs (trick_room/tailwind/
    # screens) before candidate resolution -- confirmed live: Pelipper
    # already provides Tailwind via its own move, but Archaludon's
    # "tailwind" support need (a real, speed-tier-triggered need, not a
    # generic placeholder) was still being surfaced as unmet, feeding
    # candidate discovery for a condition the team already has.
    # trick_room/tailwind map to a TRACKED_CONDITIONS provider check;
    # screens isn't one of TRACKED_CONDITIONS (doesn't fit the same
    # 0/1/2+ provider-cardinality model) but confirmed live to need the
    # same already-covered suppression regardless -- Sableye kept
    # surfacing as a fresh "screens" candidate even after Grimmsnarl (a
    # real, committed screens setter) was already locked, since the
    # unconditional "screens" need has zero team-state awareness on its
    # own. Other need categories (healing_cleric, etc.) still aren't
    # binary "provided or not" the same way and remain unaffected here.
    already_provided = provided_conditions(anchor_contexts)
    has_screens = has_reliable_screens_provider(anchor_contexts)
    _PROVIDER_NEED_CONDITION = {"trick_room": "Trick Room", "tailwind": "Tailwind"}
    anchored_needs = tuple(
        need
        for need in anchored_needs
        if need.need.category != "screens" or not has_screens
        if _PROVIDER_NEED_CONDITION.get(need.need.category) not in already_provided
    )
    support_context = SlotFillContext(anchor=None, role_shape_context=None)
    locked_weather = next(
        (
            field["weather"]
            for field in team_field_states(anchor_contexts)
            if "weather" in field
        ),
        None,
    )
    support_rows = resolve_all_support_needs(
        support_context,
        state,
        anchored_needs=anchored_needs,
        available_species=owned_species,
        ownership_mode=ownership_mode,
        locked_weather=locked_weather,
        locked_species=[
            context.resolved_build.species
            for context in anchor_contexts
            if context.resolved_build.species
        ],
    )
    # Condition-beneficiary candidates (e.g. a real Rain-beneficiary once
    # Rain is locked in via some anchor's Drizzle/Rain Dance) -- confirmed
    # gap, not previously wired into this multi-locked pipeline at all
    # (only discover_single_locked called this). That's the exact
    # scenario every live-observed candidate-quality issue in this
    # investigation actually occurred in (2+ locked members). Looped over
    # every locked anchor, not just the first, since any one of them
    # could be the actual condition provider -- provided_weather_conditions
    # only looks at the ONE decision passed in, and correctly returns
    # nothing for anchors that don't themselves provide a weather.
    #
    # Combines with support_rows explicitly via return values, not by
    # relying on ctx.need_resolved_candidates' mutation side-effect --
    # that side-effect only reflects support_rows when
    # resolve_all_support_needs actually runs for real. An existing test
    # mocks it to return a fixed value directly, which (correctly) never
    # touches the context's internal state, so relying on the mutation
    # would have silently dropped support_rows under that mock.
    locked_species_names = [
        str(context.resolved_build.species or "") for context in anchor_contexts
    ]
    beneficiary_rows: list[NeedResolvedCandidate] = []
    for context in anchor_contexts:
        beneficiary_rows = resolve_condition_beneficiaries(
            support_context,
            getattr(context, "role_decision", None),
            state,
            locked_species=locked_species_names,
            available_species=owned_species,
            ownership_mode=ownership_mode,
        )
    seen_species = {to_id(row.species) for row in support_rows}
    all_support_rows = list(support_rows) + [
        row for row in beneficiary_rows if to_id(row.species) not in seen_species
    ]
    for support in all_support_rows:
        if not eligible(support.species):
            continue
        species_id = to_id(support.species)
        existing = by_id.get(species_id)
        branches = frozenset((*((existing.branches) if existing else ()), "need"))
        anchored = tuple(
            dict.fromkeys(
                (*((existing.anchored_needs) if existing else ()), *support.anchored_needs)
            )
        )
        by_id[species_id] = AnnotatedCandidate(
            species=existing.species if existing else support.species,
            matching_needs=tuple(
                dict.fromkeys(
                    (*((existing.matching_needs) if existing else ()), *support.matching_needs)
                )
            ),
            source=_source(branches),
            target_role_decision=target_role_from_anchored_needs(anchored),
            threat_row=existing.threat_row if existing else None,
            spec=existing.spec if existing else {"species": support.species},
            evidence=_merge_evidence(
                existing.evidence if existing else (), support.evidence
            ),
            branches=branches,
            anchor_ids=frozenset(need.anchor_id for need in anchored),
            anchor_slot_indices=frozenset(
                need.anchor_slot_index for need in anchored
            ),
            anchored_needs=anchored,
        )

    if condition_resilience is not None:
        for gap_need in gap_support_needs(condition_resilience, anchored_needs):
            try:
                gap_rows = resolve_need_candidates(
                    gap_need,
                    state,
                    available_species=owned_species,
                    ownership_mode=ownership_mode,
                )
            except NotImplementedError:
                continue
            synthetic = AnchoredSupportNeed(
                anchor_slot_index=-1,
                anchor_id="condition_resilience",
                need=gap_need,
            )
            for row in gap_rows:
                if not eligible(row.species):
                    continue
                species_id = to_id(row.species)
                existing = by_id.get(species_id)
                branches = frozenset(
                    (*((existing.branches) if existing else ()), "need")
                )
                anchored = tuple(
                    dict.fromkeys(
                        (
                            *((existing.anchored_needs) if existing else ()),
                            synthetic,
                        )
                    )
                )
                evidence = tuple(
                    replace(
                        item,
                        branch="need",
                        producer_name="condition_resilience_gap",
                        subject_id=(
                            f"{gap_need.category}:{to_id(gap_need.trigger or '')}"
                        ),
                    )
                    for item in row.evidence
                )
                by_id[species_id] = AnnotatedCandidate(
                    species=existing.species if existing else row.species,
                    matching_needs=tuple(
                        dict.fromkeys(
                            (
                                *((existing.matching_needs) if existing else ()),
                                *row.matching_needs,
                            )
                        )
                    ),
                    source=_source(branches),
                    target_role_decision=target_role_from_anchored_needs(anchored),
                    threat_row=existing.threat_row if existing else None,
                    spec=existing.spec if existing else {"species": row.species},
                    evidence=_merge_evidence(
                        existing.evidence if existing else (), evidence
                    ),
                    branches=branches,
                    anchor_ids=frozenset(need.anchor_id for need in anchored),
                    anchor_slot_indices=frozenset(
                        need.anchor_slot_index for need in anchored
                    ),
                    anchored_needs=anchored,
                )

    if shared is not None and shared.status == "available":
        for teammate in shared.rows or ():
            if teammate.attribution_status != "exact" or not eligible(teammate.name):
                continue
            species_id = to_id(teammate.name)
            existing = by_id.get(species_id)
            branches = frozenset(
                (*((existing.branches) if existing else ()), "teammate")
            )
            details = (
                f"min_conditional_pct:{teammate.min_conditional_pct}",
                f"worst_rank:{teammate.worst_rank}",
                *(
                    f"anchor:{row.anchor_id}:rank:{row.rank}:pct:{row.conditional_pct}"
                    for row in teammate.per_anchor
                ),
            )
            evidence = CandidateEvidence(
                basis="teammate_backed",
                confidence="medium",
                producer_name="query_shared_teammates",
                evidence=details,
                branch="teammate",
                subject_id=species_id,
            )
            by_id[species_id] = AnnotatedCandidate(
                species=existing.species if existing else teammate.name,
                matching_needs=existing.matching_needs if existing else (),
                source=_source(branches),
                target_role_decision=(
                    existing.target_role_decision if existing else None
                ),
                threat_row=existing.threat_row if existing else None,
                spec=existing.spec if existing else {"species": teammate.name},
                evidence=_merge_evidence(
                    existing.evidence if existing else (), (evidence,)
                ),
                branches=branches,
                anchor_ids=existing.anchor_ids if existing else frozenset(),
                anchor_slot_indices=(
                    existing.anchor_slot_indices if existing else frozenset()
                ),
                composition_fit=(
                    existing.composition_fit if existing else "neutral"
                ),
                shared_min_pct=teammate.min_conditional_pct,
                shared_worst_rank=teammate.worst_rank,
                anchored_needs=existing.anchored_needs if existing else (),
            )
    rows: list[AnnotatedCandidate] = []
    for key in sorted(by_id):
        row = by_id[key]
        if row.target_role_decision is None:
            fallback = _kit_fallback_target_role(row.species)
            if fallback is not None:
                row = replace(row, target_role_decision=fallback)
        rows.append(row)
    return rows


def _ability_attr_for_candidate_spec(
    species: str, ability: object, *, regulation: str
) -> Attr[str]:
    """Elevate kit ability only when it matches usage-backed featured/common set.

    Production producers that put ability on candidate specs
    (``query_counters``, ``_set_to_spec`` / featured usage) are usage-backed.
    Tests and future callers may inject other values — those stay provisional so
    Task A's mechanism gate omits them instead of a false ``user_confirmed`` lock.
    """
    if not ability:
        return Attr()
    stated = str(ability)
    usage = featured_or_common_set(species, regulation=regulation)
    usage_ability = usage.get("ability") if usage else None
    if usage_ability and to_id(stated) == to_id(str(usage_ability)):
        return Attr(
            value=str(usage_ability),
            locked=False,
            reason=ReasonRef(kind="tier2_heuristic", ref="usage"),
        )
    return Attr(value=stated, locked=False)


def _role_decision(species: str, spec: dict, regulation: str):
    slot = Slot(
        species=Attr(value=species),
        ability=_ability_attr_for_candidate_spec(
            species, spec.get("ability"), regulation=regulation
        ),
    )
    provisional = {
        key: value
        for key, value in spec.items()
        if key not in {"species", "ability"} and value is not None
    }
    build = resolve_anchor_build(
        slot,
        provisional=provisional or None,
        regulation=regulation,
    )
    return build, classify_anchor_role(build)


def annotate_composition_impact(
    candidates: Sequence[AnnotatedCandidate],
    state: RecommenderState,
    *,
    locked_anchors: Sequence[LockedAnchorContext] | None = None,
    condition_resilience: ConditionResilienceReport | None = None,
    objective: Sequence[TeamThreatObjectiveRow] = (),
) -> list[AnnotatedCandidate]:
    regulation = state.get("regulation_mod") or "champions-reg-mb"
    locked = (
        tuple(locked_anchors)
        if locked_anchors is not None
        else collect_locked_anchor_contexts(state)
    )
    picked_team_size = state.get("picked_team_size")
    open_slot_index = next(
        (
            index
            for index, slot in enumerate(state.get("team_draft") or [])
            if not all_locked(slot)
        ),
        None,
    )
    is_core_slot = (
        picked_team_size is not None
        and open_slot_index is not None
        and open_slot_index < picked_team_size
    )
    # Only meaningful for bench slots with a real, complete core already
    # locked (candidate_improves_best_bring needs a real pick_count-sized
    # baseline to compare against -- see its own docstring). Threats
    # extracted once here, not per-candidate, since they don't vary by
    # candidate.
    bench_threats = (
        [row.threat.spec for row in objective]
        if (
            not is_core_slot
            and picked_team_size is not None
            and len(locked) >= picked_team_size
            and open_slot_index is not None
        )
        else None
    )
    primary_counts: dict[str, int] = {}
    role_counts: dict[str, int] = {}
    mechanism_counts: dict[str, int] = {}
    physical = special = attackers = 0
    for context in locked:
        decision = context.role_decision
        primary_counts[decision.primary_function] = (
            primary_counts.get(decision.primary_function, 0) + 1
        )
        role_counts[decision.role_id] = role_counts.get(decision.role_id, 0) + 1
        for mechanism in decision.mechanisms:
            if mechanism.present:
                mechanism_counts[mechanism.mechanic] = (
                    mechanism_counts.get(mechanism.mechanic, 0) + 1
                )
        if decision.primary_function == "offense":
            p_count, s_count = move_category_counts(context.resolved_build.moves)
            physical += p_count
            special += s_count
            attackers += 1

    pf_report = assess_primary_function_resilience(locked)
    if bench_threats is not None:
        from recommender.coverage import candidate_improves_best_bring, spec_to_slot
    out: list[AnnotatedCandidate] = []
    for candidate in candidates:
        build, decision = _role_decision(
            candidate.species, dict(candidate.spec), regulation
        )
        p_count, s_count = move_category_counts(build.moves)
        corrects_skew = attackers >= 2 and (
            (physical > 0 and special == 0 and s_count > 0)
            or (special > 0 and physical == 0 and p_count > 0)
        )
        worsens_skew = attackers >= 2 and (
            (physical > 0 and special == 0 and p_count > 0 and s_count == 0)
            or (special > 0 and physical == 0 and s_count > 0 and p_count == 0)
        )
        repeated_mechanisms = [
            mechanism
            for mechanism in decision.mechanisms
            if mechanism.present and mechanism_counts.get(mechanism.mechanic, 0)
        ]
        severe_repeat = any(
            mechanism_counts.get(mechanism.mechanic, 0) >= 2
            for mechanism in repeated_mechanisms
        )
        missing_primary = (
            decision.primary_function != "unknown"
            and primary_counts.get(decision.primary_function, 0) == 0
        )
        fills_missing, fills_spof_backup, backup_conditions = (
            _candidate_fills_condition_gap(
                decision,
                condition_resilience,
                candidate_build=build,
                locked=locked,
            )
        )
        fills_pf_spof = _candidate_fills_primary_function_spof(
            decision, build, pf_report, locked
        )
        core_slot_conflicts = candidate_core_slot_conflicts(
            decision, build, locked, is_core_slot=is_core_slot
        )
        wastes_core_slot = bool(core_slot_conflicts)
        dependency_reliability = candidate_dependency_reliability(
            decision, locked, regulation=regulation
        )
        improves_bench_subset = False
        if bench_threats is not None and not candidate_has_unmet_needed_weather_dependency(
            decision, locked
        ):
            candidate_spec = {
                "species": build.species,
                "ability": build.ability,
                "item": build.item,
                "moves": list(build.moves),
                "evs": dict(build.evs),
            }
            hypothetical_draft = list(state.get("team_draft") or [])
            hypothetical_draft[open_slot_index] = spec_to_slot(candidate_spec)
            improves_bench_subset = candidate_improves_best_bring(
                hypothetical_draft,
                locked,
                open_slot_index,
                picked_team_size,
                bench_threats,
                None,
                regulation=regulation,
            )
        if (
            candidate.anchored_needs
            or missing_primary
            or corrects_skew
            or fills_missing
            or fills_spof_backup
            or fills_pf_spof
        ):
            fit = "complementary"
        elif decision.primary_function == "unknown":
            fit = "neutral"
        elif severe_repeat and not candidate.anchored_needs:
            fit = "severe_duplication"
        elif role_counts.get(decision.role_id, 0) or repeated_mechanisms or worsens_skew:
            fit = "duplicative"
        else:
            fit = "neutral"
        evidence = candidate.evidence
        if fills_spof_backup and backup_conditions:
            # Without this, fills_spof_backup_gap is computed correctly but
            # is invisible to _categorize_candidates/select_diverse_candidates:
            # a genuine backup-provider candidate with no other matching_needs
            # had no "need"-branch evidence at all, so it couldn't pass
            # Category B's confidence gate even after being routed there.
            evidence = evidence + tuple(
                CandidateEvidence(
                    basis="synthesized",
                    confidence="medium",
                    producer_name="condition_gap_backup",
                    evidence=("need:spof_backup", f"condition:{condition}"),
                    branch="need",
                )
                for condition in backup_conditions
            )
        out.append(
            replace(
                candidate,
                composition_fit=fit,
                fills_essential_gap=fills_missing,
                fills_spof_backup_gap=fills_spof_backup,
                evidence=evidence,
                wastes_core_slot=wastes_core_slot,
                improves_bench_subset=improves_bench_subset,
                dependency_reliability=dependency_reliability,
                core_slot_conflicts=core_slot_conflicts,
            )
        )
    return out


def _locked_by_slot(
    locked: Sequence[LockedAnchorContext],
) -> dict[int, LockedAnchorContext]:
    return {context.slot_index: context for context in locked}


def _candidate_fills_condition_gap(
    decision: AnchorRoleDecision,
    report: ConditionResilienceReport | None,
    *,
    candidate_build: ResolvedAnchorBuild,
    locked: Sequence[LockedAnchorContext],
) -> tuple[bool, bool, tuple[str, ...]]:
    """Returns (fills_missing_provider_gap, fills_spof_backup_gap,
    backup_conditions) -- split rather than a single bool, so the caller
    (and _rank_key) can give these two genuinely different situations
    different ranking priority. missing_provider is a real, currently-unmet
    need and should always win top priority in ranking. single_provider_spof
    is real backup value (per the condition's own essential/preferred
    classification) established via build divergence from the existing
    provider -- confirmed by an existing test as a meaningful, legitimate
    signal on its own -- but confirmed live it must NOT compete for the
    SAME top-priority rank slot as a genuinely missing need, since a
    weak, low-confidence backup-only candidate was outranking strong,
    high-confidence, unrelated candidates entirely because the two cases
    were previously collapsed into one boolean.

    backup_conditions names which condition(s) actually earned
    fills_spof_backup_gap, so the caller can attach real, honest evidence
    (2026-08-21: this signal was computed correctly but was never wired
    into select_diverse_candidates' category membership or its confidence
    gate at all -- a backup-provider candidate with no other matching_needs
    was structurally invisible no matter how strong its divergence score).
    """
    if report is None:
        return False, False, ()
    by_slot = _locked_by_slot(locked)
    fills_missing = False
    fills_spof_backup = False
    backup_conditions: list[str] = []
    for row in report.conditions:
        if row.gap not in {"missing_provider", "single_provider_spof"}:
            continue
        if row.classification not in {"essential", "preferred"}:
            continue
        if not any(
            mechanism.present
            and mechanism.relation == "provides"
            and mechanism_condition(mechanism) == row.condition
            for mechanism in decision.mechanisms
        ):
            continue
        if row.gap == "missing_provider":
            fills_missing = True
            continue
        if len(row.providers) != 1:
            continue
        provider = by_slot.get(row.providers[0].slot_index)
        if provider is None:
            continue
        tag = PROVIDER_TAG_BY_CONDITION.get(row.condition)
        shared = frozenset({tag}) if tag else frozenset()
        score = divergence_score(
            decision,
            provider.role_decision,
            candidate_moves=candidate_build.moves,
            existing_moves=provider.resolved_build.moves,
            candidate_ability=candidate_build.ability,
            existing_ability=provider.resolved_build.ability,
            shared_provider_tags=shared,
        )
        if score >= DIVERGENCE_COMPLEMENTARY_THRESHOLD:
            fills_spof_backup = True
            backup_conditions.append(row.condition)
    return fills_missing, fills_spof_backup, tuple(backup_conditions)


def _candidate_fills_primary_function_spof(
    decision: AnchorRoleDecision,
    build: ResolvedAnchorBuild,
    report: PrimaryFunctionResilienceReport,
    locked: Sequence[LockedAnchorContext],
) -> bool:
    by_slot = _locked_by_slot(locked)
    for row in report.functions:
        if row.gap != "single_provider_spof":
            continue
        if decision.primary_function != row.primary_function:
            continue
        if len(row.providers) != 1:
            continue
        provider = by_slot.get(row.providers[0].slot_index)
        if provider is None:
            continue
        score = divergence_score(
            decision,
            provider.role_decision,
            candidate_moves=build.moves,
            existing_moves=provider.resolved_build.moves,
            candidate_ability=build.ability,
            existing_ability=provider.resolved_build.ability,
            shared_provider_tags=frozenset(),
        )
        if score >= DIVERGENCE_COMPLEMENTARY_THRESHOLD:
            return True
    return False


_FIT_RANK = {
    "severe_duplication": 0,
    "duplicative": 1,
    "neutral": 2,
    "complementary": 3,
}
_BASIS_RANK = {
    "synthesized": 0,
    "ownership_backed": 0,
    "teammate_backed": 1,
    "mechanical_only": 2,
    "usage_backed": 3,
    "compendium_backed": 4,
}
_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


def _pick_best_evidence_item(
    items: Sequence[CandidateEvidence],
) -> CandidateEvidence | None:
    """Max by (basis, confidence); override only when winner is
    compendium_backed and a usage_backed row with commitment_pct: has
    strictly higher confidence.

    Display (_best_evidence_row) and Category B/C ranking
    (_rank_by_need_evidence) share this so Fix A's downgraded
    Role Compendium row cannot understate a real commitment-backed
    usage entry (Grimmsnarl screens). Does not change _BASIS_RANK.
    """
    if not items:
        return None

    def quality(item: CandidateEvidence) -> tuple[int, int]:
        return (_BASIS_RANK[item.basis], _CONFIDENCE_RANK[item.confidence])

    winner = max(items, key=quality)
    if winner.basis != "compendium_backed":
        return winner
    winner_conf = _CONFIDENCE_RANK[winner.confidence]
    commitment = [
        item
        for item in items
        if item.basis == "usage_backed"
        and any(tag.startswith("commitment_pct:") for tag in item.evidence)
        and _CONFIDENCE_RANK[item.confidence] > winner_conf
    ]
    if not commitment:
        return winner
    return max(commitment, key=lambda item: _CONFIDENCE_RANK[item.confidence])


def _primary_function(candidate: AnnotatedCandidate, regulation: str) -> str:
    return _role_decision(candidate.species, dict(candidate.spec), regulation)[
        1
    ].primary_function


def _rank_key(
    candidate: AnnotatedCandidate,
    objective: Sequence[TeamThreatObjectiveRow],
    preference: TeamCompletionPreference | None,
    regulation: str,
) -> tuple:
    objective_by_id = {
        _threat_id(row.threat): row for row in objective if _threat_id(row.threat)
    }
    counts = {
        "uncovered_verified_decisive": 0,
        "uncovered_verified_costly": 0,
        "uncovered_verified_toss-up": 0,
        "uncovered_conditional_decisive": 0,
        "uncovered_conditional_costly": 0,
        "uncovered_conditional_toss-up": 0,
        "spof_verified_decisive": 0,
        "spof_verified_costly": 0,
        "spof_verified_toss-up": 0,
    }
    for threat_id, result in (
        candidate.threat_row.verified_vs if candidate.threat_row else ()
    ):
        row = objective_by_id.get(threat_id)
        if row is None or result.outcome == "no_answer":
            continue
        kind = "uncovered" if "uncovered" in row.kinds else "spof"
        outcome = (
            "conditional"
            if result.outcome == "conditionally_dependent_answer"
            else "verified"
        )
        key = f"{kind}_{outcome}_{result.severity}"
        if key in counts:
            counts[key] += 1
    best_evidence = max(
        (
            _BASIS_RANK[item.basis],
            _CONFIDENCE_RANK[item.confidence],
        )
        for item in candidate.evidence
    ) if candidate.evidence else (0, 0)
    primary = _primary_function(candidate, regulation)
    preference_fit = int(
        preference in {"attacker", "support"}
        and primary == ("offense" if preference == "attacker" else "support")
    )
    distinct_needs = {
        (need.need.category, need.need.trigger) for need in candidate.anchored_needs
    }
    return (
        int(not candidate.wastes_core_slot),
        int(candidate.fills_essential_gap),
        counts["uncovered_verified_decisive"],
        counts["uncovered_verified_costly"],
        _FIT_RANK[candidate.composition_fit],
        preference_fit,
        counts["uncovered_verified_toss-up"],
        counts["uncovered_conditional_decisive"],
        counts["uncovered_conditional_costly"],
        counts["uncovered_conditional_toss-up"],
        counts["spof_verified_decisive"],
        counts["spof_verified_costly"],
        counts["spof_verified_toss-up"],
        len(candidate.anchor_ids),
        len(distinct_needs),
        # Repositioned (2026-08-19), not just re-documented: previously
        # sat AFTER best_evidence, where it was effectively dead --
        # candidates rarely tie on evidence quality, so a field placed
        # after it in a tuple comparison is consulted only in the rare
        # case everything else including evidence also ties. Confirmed
        # with Vu directly: shared-teammate co-occurrence is a real proxy
        # for mechanism/threat-coverage synergy that Part 1's field-
        # awareness fix doesn't fully capture on its own (speed control,
        # ability interactions, move combos real players find but the
        # calc-based matchup model doesn't directly model) -- moved ahead
        # of best_evidence so it can decide between candidates that are
        # comparably valuable on every genuinely-computed team-value
        # field above (threat-coverage, fit, preference, needs) but
        # differ in individual evidence confidence, which is a far more
        # common tie than tying on evidence too. Still ranks below every
        # substantive field above it -- never overrides genuinely correct
        # threat-coverage superiority, per explicit design decision.
        (
            candidate.shared_min_pct
            if candidate.shared_min_pct is not None
            else float("-inf")
        ),
        (
            -candidate.shared_worst_rank
            if candidate.shared_worst_rank is not None
            else float("-inf")
        ),
        best_evidence[0],
        best_evidence[1],
        int(candidate.fills_spof_backup_gap),
    )


def _shared_teammate_tiebreak(candidate: AnnotatedCandidate) -> tuple[float, float]:
    """Lower is better. Reused as the within-category secondary signal
    for select_diverse_candidates -- same role shared-teammate evidence
    already has in _rank_key, just scoped locally to one category instead
    of globally across the whole pool."""
    return (
        -(candidate.shared_min_pct if candidate.shared_min_pct is not None else -1.0),
        (
            candidate.shared_worst_rank
            if candidate.shared_worst_rank is not None
            else float("inf")
        ),
    )


def _dense_rank(items: list, value_fn, *, descending: bool = True) -> dict[str, int]:
    """Rank items by value_fn's output, keyed by to_id(item.species) --
    exact ties share the identical rank (dense rank), not distinct
    sequential positions from a stable sort.

    Confirmed a real, pre-existing bug in this function's own callers
    during verification of an unrelated feature (dependency_reliability,
    2026-08-22): a naive `{to_id(item.species): i for i, item in
    enumerate(sorted(...))}` pattern silently assigns distinct sequential
    ranks even when every value is exactly tied, purely from whatever
    order the input list happened to be in -- not a theoretical concern,
    directly observed producing a wrong result (two mutually-cancelling
    arbitrary tie-breaks let a candidate with 8x worse verified_score win
    over one with identical, tied defensive_synergy_score). Reused here
    for verified_rank, synergy_rank, AND reliability_rank uniformly,
    rather than leaving the two pre-existing ones broken while only
    fixing the new one.
    """
    unique_values = sorted({value_fn(item) for item in items}, reverse=descending)
    value_rank = {value: i for i, value in enumerate(unique_values)}
    return {to_id(item.species): value_rank[value_fn(item)] for item in items}


def _rank_category_a(
    candidates: list[AnnotatedCandidate],
    locked_types_list: list[list[str]],
) -> list[AnnotatedCandidate]:
    """Type-synergy + threat-counter breadth, combined by RANK position
    rather than raw value -- confirmed necessary, not a stylistic choice:
    verified_score (calc-verified, can be 40+ across many threats) and
    defensive_synergy_score (typically single-digit) are on wildly
    different scales, and a naive sum let the larger-magnitude signal
    dominate the same way a prior, separately-discovered ranking bug did
    (fills_essential_gap completely overriding evidence quality). Rank-
    based combination is scale-invariant by construction, avoiding the
    need to guess at normalization weights between two very differently-
    behaved raw signals.
    """
    from recommender.counters import _species_types, defensive_synergy_score
    from recommender.legality import load_snapshot

    if not candidates:
        return []
    snap = load_snapshot()
    scored_verified = {
        to_id(c.species): c.threat_row.verified_score if c.threat_row else 0.0
        for c in candidates
    }
    scored_synergy = {
        to_id(c.species): defensive_synergy_score(
            _species_types(snap, c.species), locked_types_list
        )
        for c in candidates
    }
    verified_rank = _dense_rank(candidates, lambda c: scored_verified[to_id(c.species)])
    synergy_rank = _dense_rank(candidates, lambda c: scored_synergy[to_id(c.species)])
    # Confirmed live (2026-08-22): Mawile-Mega's real Trick Room
    # dependency, nominally satisfied by a locked Sinistcha whose real
    # aggregate TR commitment (57.2%) is barely more than a coinflip
    # against its actual defining move (Rage Powder, 95.6%), should rank
    # behind a candidate with the same real threat-coverage/type-synergy
    # profile but a genuinely reliable (or no) dependency -- a soft
    # ranking nudge, not a hard gate, so it joins the same rank-summed
    # combination as verified_score/defensive_synergy rather than
    # excluding or force-bottoming a candidate the way wastes_core_slot
    # does for a genuinely disqualifying conflict.
    reliability_rank = _dense_rank(candidates, lambda c: c.dependency_reliability)

    def sort_key(c: AnnotatedCandidate):
        sid = to_id(c.species)
        return (
            int(c.wastes_core_slot),
            int(not c.improves_bench_subset),
            verified_rank[sid] + synergy_rank[sid] + reliability_rank[sid],
            _shared_teammate_tiebreak(c),
        )

    return sorted(candidates, key=sort_key)


def _need_branch_evidence(
    c: AnnotatedCandidate, *, condition_beneficiary: bool
) -> tuple[CandidateEvidence, ...]:
    """Scopes a candidate's evidence to the specific category (B or C)
    being evaluated, not the candidate's full, unscoped evidence tuple.

    Confirmed live, a real bug: a candidate with strong, unrelated
    evidence (e.g. real threat-counter data) mixed into its overall
    evidence tuple was incorrectly ranking high within -- and passing
    the confidence gate for -- Category B/C based on that unrelated
    evidence, not its actual, genuinely weak support-need match. Same
    class of bug as the earlier evidence-display scoping fix, but here
    affecting the underlying ranking/gating logic itself, not just what
    gets shown afterward -- confirmed both needed the same fix, not
    just the display layer.
    """
    return tuple(
        item
        for item in c.evidence
        if item.branch == "need"
        and (
            any("need:condition_beneficiary" in tag for tag in item.evidence)
            == condition_beneficiary
        )
    )


def _rank_by_need_evidence(
    candidates: list[AnnotatedCandidate],
    locked: Sequence["LockedAnchorContext"] = (),
    *,
    condition_beneficiary: bool = False,
) -> list[AnnotatedCandidate]:
    """Categories B (support-needs) and C (condition-benefit) share the
    same ranking approach: best evidence quality (reusing the same
    _BASIS_RANK/_CONFIDENCE_RANK convention _rank_key already uses),
    shared-teammate correlation as the secondary tie-break. Scoped to
    the relevant category's own evidence via _need_branch_evidence, not
    the candidate's full evidence tuple.

    A candidate whose ONLY relevant evidence is a fills_spof_backup_gap
    annotation (tagged "need:spof_backup") ranks behind any candidate
    with at least one genuine, non-backup need match, regardless of raw
    basis/confidence numbers -- confirmed live (2026-08-21): a secondary/
    backup purpose (Sableye's incidental Rain value) should never
    out-rank or crowd out a candidate answering a genuinely open need,
    the same "backup shouldn't compete with genuinely missing" priority
    ADR-026 Amendment 2026-08-17a already established for
    fills_essential_gap vs. fills_spof_backup_gap directly -- this
    extends that same principle to evidence-based ranking now that
    fills_spof_backup_gap actually reaches this ranking step at all.

    Confirmed live (2026-08-22): Trick Room and Tailwind are NOT
    mutually exclusive -- a team can legitimately run both, so this is
    deliberately not a candidate_wastes_core_slot-style hard conflict.
    But a candidate whose ENTIRE real support-need value is trick_room
    or tailwind ALONE, and nothing else, is genuinely lower-value once
    the team already has some real speed control locked (Aromatisse,
    Armarouge -- single-purpose TR-only compendium entries, repeatedly
    resurfacing turn after turn ahead of genuinely multi-purpose real
    alternatives like Sableye [screens + backup rain] or Grimmsnarl
    [screens + disruption]) -- a soft demotion, same shape as
    _is_backup_only, not exclusion.
    """

    def _is_backup_only(relevant: tuple[CandidateEvidence, ...]) -> bool:
        return bool(relevant) and all(
            any("need:spof_backup" in tag for tag in item.evidence)
            for item in relevant
        )

    from recommender.condition_resilience import provided_conditions

    already_has_speed_control = bool(
        provided_conditions(locked) & {"Trick Room", "Tailwind"}
    )

    def _is_redundant_speed_control_only(c: AnnotatedCandidate) -> bool:
        if not already_has_speed_control:
            return False
        need_categories = {n.category for n in c.matching_needs}
        return bool(need_categories) and need_categories <= {"trick_room", "tailwind"}

    def sort_key(c: AnnotatedCandidate):
        relevant = _need_branch_evidence(c, condition_beneficiary=condition_beneficiary)
        picked = _pick_best_evidence_item(relevant)
        best = (
            (_BASIS_RANK[picked.basis], _CONFIDENCE_RANK[picked.confidence])
            if picked is not None
            else (0, 0)
        )
        return (
            int(c.wastes_core_slot),
            int(_is_redundant_speed_control_only(c)),
            int(_is_backup_only(relevant)),
            -best[0],
            -best[1],
            _shared_teammate_tiebreak(c),
        )

    return sorted(candidates, key=sort_key)


_TRACK_LABELS = {
    "A": "threat coverage + type synergy",
    "B": "support/utility",
    "C": "condition synergy",
}


def _categorize_candidates(
    candidates: Sequence[AnnotatedCandidate],
) -> tuple[list[AnnotatedCandidate], list[AnnotatedCandidate], list[AnnotatedCandidate]]:
    """Splits a candidate pool into the three categories (A: threat-
    coverage+type-synergy, B: support-needs, C: condition-benefit) --
    shared by select_diverse_candidates and rank_multi_locked_by_category
    so their categorization logic can't silently drift apart.
    """
    category_a: list[AnnotatedCandidate] = []
    category_b: list[AnnotatedCandidate] = []
    category_c: list[AnnotatedCandidate] = []
    for c in candidates:
        if c.threat_row is not None:
            category_a.append(c)
        need_categories = {n.category for n in c.matching_needs}
        if "condition_beneficiary" in need_categories:
            category_c.append(c)
        in_category_b = bool(need_categories - {"condition_beneficiary"})
        # fills_essential_gap/fills_spof_backup_gap (2026-08-21 fix): these
        # are computed correctly elsewhere but were never consulted here at
        # all -- a real backup-provider candidate (fills_spof_backup_gap)
        # typically has NO matching_needs of its own (that's precisely why
        # this signal exists as a separate annotation: the anchor's own
        # dependency is already satisfied, so query_support_needs never asks
        # for it), so it had no category to land in no matter how strong its
        # divergence score. fills_essential_gap is usually already covered
        # via a real matching_needs entry (gap_support_needs still fires
        # normally for missing_provider), but is included here too for
        # parity and to guard against that path being unavailable.
        if not in_category_b and (c.fills_essential_gap or c.fills_spof_backup_gap):
            in_category_b = True
        if in_category_b:
            category_b.append(c)
    return category_a, category_b, category_c


def rank_multi_locked_by_category(
    candidates: Sequence[AnnotatedCandidate],
    locked_contexts: Sequence[LockedAnchorContext],
    *,
    n_per_category: int = 10,
    category_b_n: int | None = None,
    category_b_uncapped: bool = False,
) -> list[AnnotatedCandidate]:
    """Gives each of the three categories its own top-N cut, instead of
    one shared, combined top-N ranking.

    Confirmed live, a real, significant bug: rank_multi_locked_candidates'
    single, combined top-10 cut (via the old _rank_key) was defeating the
    entire purpose of select_diverse_candidates' category-aware
    selection -- genuinely valuable Category B/C candidates (a real
    screens setter, a real Rain-beneficiary) got cut from the pool
    ENTIRELY whenever 10+ candidates ranked higher by threat-coverage/
    type-synergy criteria alone, which is the common case with real
    threat-counter data from live calc. select_diverse_candidates never
    even got a chance to consider them.

    Deliberately a separate function, not a change to
    rank_multi_locked_candidates itself -- that function has a second,
    different caller (material_completion_preferences) where the single-
    ranking, n=3 behavior is still the right tool for comparing
    preference-based orderings, not for feeding select_diverse_candidates.
    """
    category_a, category_b, category_c = _categorize_candidates(candidates)

    from recommender.counters import _species_types
    from recommender.legality import load_snapshot

    snap = load_snapshot()
    locked_types_list = [
        _species_types(snap, ctx.resolved_build.species) for ctx in locked_contexts
    ]
    ranked_a = _rank_category_a(category_a, locked_types_list)[:n_per_category]
    ranked_b_full = _rank_by_need_evidence(
        category_b, locked_contexts, condition_beneficiary=False
    )
    if category_b_uncapped:
        ranked_b = ranked_b_full
    else:
        b_n = n_per_category if category_b_n is None else category_b_n
        ranked_b = ranked_b_full[:b_n]
    ranked_c = _rank_by_need_evidence(
        category_c, locked_contexts, condition_beneficiary=True
    )[:n_per_category]

    seen: set[str] = set()
    combined: list[AnnotatedCandidate] = []
    for c in (*ranked_a, *ranked_b, *ranked_c):
        sid = to_id(c.species)
        if sid not in seen:
            seen.add(sid)
            combined.append(c)
    return combined


def _pick_first_new_lineage(
    ranked: Sequence[AnnotatedCandidate],
    used_lineages: set[str],
) -> AnnotatedCandidate | None:
    for c in ranked:
        lineage = set(lineage_ids(c.species))
        if not (lineage & used_lineages):
            return c
    return None


def _support_need_categories(c: AnnotatedCandidate) -> frozenset[str]:
    """Raw matching_needs categories (tests / callers that want unfiltered)."""
    return frozenset(
        n.category
        for n in c.matching_needs
        if n.category != "condition_beneficiary"
    )


_DIVERSITY_TIERS_COUNT = frozenset({"Excellent", "Good"})
_DIVERSITY_TIERS_DROP = frozenset({"Acceptable"})


def _diversity_need_categories_from_evidence(
    evidence: Sequence[CandidateEvidence],
    categories: Sequence[str],
) -> frozenset[str]:
    """Which need categories count toward support diversification.

    Commitment tags (in-game only via narrow_candidates) always count.
    Without commitment: Good/Excellent tier counts; Acceptable does not;
    missing tier tags count (neutral — unit fixtures / unknown).
    Never consults Showdown.
    """
    out: set[str] = set()
    for category in categories:
        if category == "condition_beneficiary":
            continue
        need_tag = f"need:{category}"
        relevant = [
            item
            for item in evidence
            if item.branch == "need" and need_tag in item.evidence
        ]
        if not relevant:
            # matching_needs listed it but no need-branch row — keep (neutral)
            out.add(category)
            continue
        if any(
            tag.startswith("commitment_pct:")
            for item in relevant
            for tag in item.evidence
        ):
            out.add(category)
            continue
        tiers = {
            tag.removeprefix("tier:")
            for item in relevant
            for tag in item.evidence
            if tag.startswith("tier:")
        }
        if not tiers:
            out.add(category)
            continue
        if tiers & _DIVERSITY_TIERS_COUNT:
            out.add(category)
            continue
        # Acceptable-only (or other non-Good/Excellent) without commitment
        if tiers <= _DIVERSITY_TIERS_DROP:
            continue
        out.add(category)
    return frozenset(out)


def _diversity_need_categories(c: AnnotatedCandidate) -> frozenset[str]:
    cats = [
        n.category
        for n in c.matching_needs
        if n.category != "condition_beneficiary"
    ]
    return _diversity_need_categories_from_evidence(c.evidence, cats)


def _diversify_by_need_category(
    ranked_b: Sequence[AnnotatedCandidate],
    n: int,
    *,
    banned_profiles: frozenset[frozenset[str]] = frozenset(),
) -> list[AnnotatedCandidate]:
    picked: list[AnnotatedCandidate] = []
    used_lineages: set[str] = set()
    covered: set[str] = set()
    picked_ids: set[str] = set()

    for c in ranked_b:
        if len(picked) >= n:
            break
        lineage = set(lineage_ids(c.species))
        if lineage & used_lineages:
            continue
        cats = _diversity_need_categories(c)
        if not cats or not (cats - covered):
            continue
        if cats in banned_profiles:
            continue
        picked.append(c)
        used_lineages |= lineage
        covered |= cats
        picked_ids.add(to_id(c.species))

    picked_profiles = {_diversity_need_categories(c) for c in picked}
    for c in ranked_b:
        if len(picked) >= n:
            break
        if to_id(c.species) in picked_ids:
            continue
        lineage = set(lineage_ids(c.species))
        if lineage & used_lineages:
            continue
        cats = _diversity_need_categories(c)
        if not cats or not (cats - covered):
            continue
        if any(cats <= profile for profile in picked_profiles):
            continue
        if cats in banned_profiles:
            continue
        picked.append(c)
        used_lineages |= lineage
        picked_profiles.add(cats)
        picked_ids.add(to_id(c.species))

    for c in ranked_b:
        if len(picked) >= n:
            break
        if to_id(c.species) in picked_ids:
            continue
        lineage = set(lineage_ids(c.species))
        if lineage & used_lineages:
            continue
        cats = _diversity_need_categories(c)
        if cats in banned_profiles:
            continue
        picked.append(c)
        used_lineages |= lineage
        picked_ids.add(to_id(c.species))

    return picked


def banned_profiles_from_rejected(
    rejected: Sequence[dict[str, Any]] | None,
) -> frozenset[frozenset[str]]:
    out: set[frozenset[str]] = set()
    for row in rejected or ():
        cats = row.get("need_categories")
        if cats:
            out.add(frozenset(cats))
    return frozenset(out)


def _select_attacker(
    ranked_a: Sequence[AnnotatedCandidate],
    ranked_c: Sequence[AnnotatedCandidate],
    *,
    n_alternatives: int,
) -> list[tuple[AnnotatedCandidate, str]]:
    total = n_alternatives + 1
    picks: list[tuple[AnnotatedCandidate, str]] = []
    used_lineages: set[str] = set()

    if ranked_a and ranked_c:
        default = ranked_a[0]
        picks.append((default, "A"))
        used_lineages |= set(lineage_ids(default.species))

        if len(picks) < total:
            alt_c = _pick_first_new_lineage(ranked_c, used_lineages)
            if alt_c is not None:
                picks.append((alt_c, "C"))
                used_lineages |= set(lineage_ids(alt_c.species))

        if len(picks) < total:
            alt_a = _pick_first_new_lineage(ranked_a[1:], used_lineages)
            if alt_a is not None:
                picks.append((alt_a, "A"))
            elif len(picks) < total:
                alt_c = _pick_first_new_lineage(ranked_c[1:], used_lineages)
                if alt_c is not None:
                    picks.append((alt_c, "C"))
    else:
        pool = [(c, "A") for c in ranked_a] + [(c, "C") for c in ranked_c]
        for c, key in pool:
            if len(picks) >= total:
                break
            lineage = set(lineage_ids(c.species))
            if lineage & used_lineages:
                continue
            picks.append((c, key))
            used_lineages |= lineage

    return picks


def _select_balanced(
    ranked_a: Sequence[AnnotatedCandidate],
    ranked_b: Sequence[AnnotatedCandidate],
    ranked_c: Sequence[AnnotatedCandidate],
    *,
    n_alternatives: int,
    banned_profiles: frozenset[frozenset[str]] = frozenset(),
) -> list[tuple[AnnotatedCandidate, str]]:
    total = n_alternatives + 1
    picks: list[tuple[AnnotatedCandidate, str]] = []
    used_lineages: set[str] = set()
    for key, ranked in (("A", ranked_a), ("B", ranked_b), ("C", ranked_c)):
        if len(picks) >= total:
            break
        pool: Sequence[AnnotatedCandidate] = ranked
        if key == "B" and banned_profiles:
            pool = [
                c
                for c in ranked
                if _diversity_need_categories(c) not in banned_profiles
            ]
        c = _pick_first_new_lineage(pool, used_lineages)
        if c is not None:
            picks.append((c, key))
            used_lineages |= set(lineage_ids(c.species))
    return picks


def _select_support(
    ranked_b: Sequence[AnnotatedCandidate],
    *,
    n_alternatives: int,
    banned_profiles: frozenset[frozenset[str]] = frozenset(),
) -> list[tuple[AnnotatedCandidate, str]]:
    picked = _diversify_by_need_category(
        ranked_b, n_alternatives + 1, banned_profiles=banned_profiles
    )
    return [(c, "B") for c in picked]


def _build_select_result(
    picks: Sequence[tuple[AnnotatedCandidate, str]],
    *,
    n_alternatives: int,
) -> dict[str, Any]:
    if not picks:
        return {
            "default": None,
            "alternatives": [],
            "tracks": {},
            "category_keys": {},
        }
    default_c, default_key = picks[0]
    tracks: dict[str, str] = {default_c.species: _TRACK_LABELS[default_key]}
    category_keys: dict[str, list[str]] = {default_c.species: [default_key]}
    alternatives: list[str] = []
    for c, key in picks[1 : n_alternatives + 1]:
        alternatives.append(c.species)
        tracks[c.species] = _TRACK_LABELS[key]
        category_keys[c.species] = [key]
    return {
        "default": default_c.species,
        "alternatives": alternatives,
        "tracks": tracks,
        "category_keys": category_keys,
    }


def select_diverse_candidates(
    candidates: Sequence[AnnotatedCandidate],
    locked_contexts: Sequence[LockedAnchorContext],
    *,
    n_alternatives: int = 2,
    preference: TeamCompletionPreference | None = None,
    banned_profiles: frozenset[frozenset[str]] = frozenset(),
) -> dict[str, Any]:
    """Default + N alternatives via per-preference selection shapes.

    Three categories, each scored independently:
    - A: type-synergy + threat-counter breadth (_rank_category_a)
    - B: support-needs (screens, trick_room, healing_cleric, etc.)
    - C: condition-benefit (Rain-beneficiary, etc.)

    Preference selects among distinct presentation shapes:
    - attacker: hard-excludes Category B as a selection source (A+C only)
    - balanced / unset: one pick per category A→B→C, lineage-deduped
    - support: B-only, diversified by NeedCategory within ranked_b

    Returns a "tracks" mapping (species -> human-readable label) alongside
    default/alternatives, surfacing which track each pick came from.
    """
    category_a, category_b, category_c = _categorize_candidates(candidates)

    from recommender.counters import _species_types
    from recommender.legality import load_snapshot

    snap = load_snapshot()
    locked_types_list = [
        _species_types(snap, ctx.resolved_build.species) for ctx in locked_contexts
    ]

    ranked_a = _rank_category_a(category_a, locked_types_list)

    def _has_strong_evidence(c: AnnotatedCandidate, *, condition_beneficiary: bool) -> bool:
        relevant = _need_branch_evidence(c, condition_beneficiary=condition_beneficiary)
        return any(item.confidence != "low" for item in relevant)

    ranked_b = [
        c
        for c in _rank_by_need_evidence(
            category_b, locked_contexts, condition_beneficiary=False
        )
        if _has_strong_evidence(c, condition_beneficiary=False)
    ]
    ranked_c = [
        c
        for c in _rank_by_need_evidence(
            category_c, locked_contexts, condition_beneficiary=True
        )
        if _has_strong_evidence(c, condition_beneficiary=True)
    ]

    effective = preference or "balanced"
    if effective == "attacker":
        picks = _select_attacker(ranked_a, ranked_c, n_alternatives=n_alternatives)
    elif effective == "support":
        picks = _select_support(
            ranked_b,
            n_alternatives=n_alternatives,
            banned_profiles=banned_profiles,
        )
    else:
        picks = _select_balanced(
            ranked_a,
            ranked_b,
            ranked_c,
            n_alternatives=n_alternatives,
            banned_profiles=banned_profiles,
        )

    return _build_select_result(picks, n_alternatives=n_alternatives)


def rank_multi_locked_candidates(
    candidates: Sequence[AnnotatedCandidate],
    *,
    objective: Sequence[TeamThreatObjectiveRow],
    preference: TeamCompletionPreference | None,
    ownership_mode: OwnershipMode,
    owned_species: frozenset[str],
    n: int = 10,
    regulation: str = "champions-reg-mb",
) -> list[AnnotatedCandidate]:
    rows = sorted(candidates, key=lambda candidate: to_id(candidate.species))
    if ownership_mode == "owned_only":
        rows = [row for row in rows if to_id(row.species) in owned_species]
    return rank_and_cut(
        rows,
        key=lambda candidate: _rank_key(
            candidate, objective, preference, regulation
        ),
        n=n,
        tier=None,
        order="descending",
        ownership_mode=ownership_mode,
        is_owned=lambda candidate: to_id(candidate.species) in owned_species,
    )


def material_completion_preferences(
    candidates: Sequence[AnnotatedCandidate],
    *,
    objective: Sequence[TeamThreatObjectiveRow],
    ownership_mode: OwnershipMode,
    owned_species: frozenset[str],
    regulation: str = "champions-reg-mb",
) -> tuple[TeamCompletionPreference, ...]:
    preferences: tuple[TeamCompletionPreference, ...] = (
        "attacker",
        "support",
        "balanced",
    )
    orders = {
        tuple(
            to_id(candidate.species)
            for candidate in rank_multi_locked_candidates(
                candidates,
                objective=objective,
                preference=preference,
                ownership_mode=ownership_mode,
                owned_species=owned_species,
                n=3,
                regulation=regulation,
            )
        )
        for preference in preferences
    }
    return preferences if len(orders) > 1 else ()



@dataclass(frozen=True)
class MaskedCorePackage:
    candidate: AnnotatedCandidate
    masked_slot_indices: tuple[int, ...]
    fill: AnnotatedCandidate
    label: str


def remaining_open_after_place(state: RecommenderState) -> int:
    draft = state.get("team_draft") or []
    open_count = sum(1 for slot in draft if not all_locked(slot))
    return max(0, open_count - 1)


def mask_slots_for(candidate: AnnotatedCandidate) -> tuple[int, ...]:
    return tuple(sorted({row.locked_slot_index for row in candidate.core_slot_conflicts}))


def _has_usage_backed(candidate: AnnotatedCandidate) -> bool:
    return any(getattr(item, "basis", None) == "usage_backed" for item in candidate.evidence)


def _has_verified_threat(candidate: AnnotatedCandidate) -> bool:
    row = candidate.threat_row
    if row is None:
        return False
    return bool(getattr(row, "verified_vs", None))


def independently_strong_category_a(
    candidate: AnnotatedCandidate,
    pool: Sequence[AnnotatedCandidate],
    locked: Sequence[LockedAnchorContext],
) -> bool:
    ignored = [replace(row, wastes_core_slot=False) for row in pool]
    category_a, _, _ = _categorize_candidates(ignored)
    from recommender.counters import _species_types
    from recommender.legality import load_snapshot

    snap = load_snapshot()
    locked_types: list[list[str]] = []
    for context in locked:
        species = context.resolved_build.species or ""
        try:
            locked_types.append(_species_types(snap, species))
        except Exception:
            locked_types.append([])
    ranked = _rank_category_a(list(category_a), locked_types)
    top = {to_id(row.species) for row in ranked[:3]}
    return to_id(candidate.species) in top


def should_try_masked_core(
    candidate: AnnotatedCandidate,
    pool: Sequence[AnnotatedCandidate],
    state: RecommenderState,
    locked: Sequence[LockedAnchorContext],
) -> bool:
    if not candidate.wastes_core_slot:
        return False
    if remaining_open_after_place(state) < 1:
        return False
    if not (_has_verified_threat(candidate) and _has_usage_backed(candidate)):
        return False
    pick = state.get("picked_team_size")
    if pick is None:
        return False
    mask = set(mask_slots_for(candidate))
    unmasked = sum(1 for row in locked if row.slot_index not in mask)
    if unmasked + 1 < pick:
        return False
    return independently_strong_category_a(candidate, pool, locked)


def _package_label(
    candidate: AnnotatedCandidate,
    locked: Sequence[LockedAnchorContext],
    mask: frozenset[int],
) -> str:
    by_slot = {context.slot_index: context for context in locked}
    names: list[str] = []
    for index in sorted(mask):
        context = by_slot.get(index)
        species = (
            (context.resolved_build.species or "") if context is not None else ""
        )
        names.append(species or f"slot {index}")
    benched = ", ".join(names)
    kinds = {row.kind for row in candidate.core_slot_conflicts}
    if "weather" in kinds:
        return f"Weather core — {benched} benched"
    return f"Mega core — {benched} benched"


def _synthetic_candidate_context(
    candidate: AnnotatedCandidate,
    slot_index: int,
    state: RecommenderState,
) -> LockedAnchorContext:
    from recommender.coverage import spec_to_slot

    spec = dict(candidate.spec) if candidate.spec else {"species": candidate.species}
    spec.setdefault("species", candidate.species)
    slot = spec_to_slot(spec)
    regulation = state.get("regulation_mod") or "champions-reg-mb"
    resolved = resolve_anchor_build(
        slot, role_hint=slot.role.value, regulation=regulation
    )
    decision = classify_anchor_role(resolved, explicit_role=None)
    shape = derive_role_shape_context(decision)
    pokemon = resolved.as_pokemon()
    anchor_id = to_id(resolved.species or candidate.species)
    needs = tuple(
        AnchoredSupportNeed(slot_index, anchor_id, need)
        for need in query_support_needs(
            pokemon,
            shape,
            team_draft=state["team_draft"],
            state=state,
            regulation=regulation,
        )
    )
    return LockedAnchorContext(
        slot_index=slot_index,
        anchor_id=anchor_id,
        pokemon=pokemon,
        resolved_build=resolved,
        role_decision=decision,
        role_shape_context=shape,
        support_needs=needs,
    )


def _is_sole_needed_provider(
    slot_index: int,
    locked: Sequence[LockedAnchorContext],
    mask: frozenset[int],
) -> bool:
    from recommender.condition_resilience import mechanism_condition

    target = next((row for row in locked if row.slot_index == slot_index), None)
    if target is None:
        return False
    provided: set[str] = set()
    for mechanism in target.role_decision.mechanisms:
        if mechanism.present and mechanism.relation == "provides":
            condition = mechanism_condition(mechanism)
            if condition:
                provided.add(condition)
    if not provided:
        return False
    others = [
        row
        for row in locked
        if row.slot_index != slot_index and row.slot_index not in mask
    ]
    other_provided: set[str] = set()
    for row in others:
        for mechanism in row.role_decision.mechanisms:
            if mechanism.present and mechanism.relation == "provides":
                condition = mechanism_condition(mechanism)
                if condition:
                    other_provided.add(condition)
    unique = provided - other_provided
    if not unique:
        return False
    for row in others:
        for mechanism in row.role_decision.mechanisms:
            if (
                mechanism.present
                and mechanism.relation == "benefits_from"
                and mechanism.importance == "needed"
                and mechanism_condition(mechanism) in unique
            ):
                return True
    return False


def _calc_agrees(
    candidate: AnnotatedCandidate,
    fill: AnnotatedCandidate,
    state: RecommenderState,
    working: Sequence[LockedAnchorContext],
    objective: Sequence[object],
    fill_index: int,
    candidate_index: int,
) -> bool:
    from recommender.coverage import candidate_improves_best_bring, spec_to_slot

    pick = state.get("picked_team_size")
    threat_specs = []
    for row in objective:
        threat = getattr(row, "threat", None)
        spec = getattr(threat, "spec", None) if threat is not None else None
        if spec:
            threat_specs.append(spec)
    if pick is None or not threat_specs or len(working) < pick:
        return False
    draft = list(state.get("team_draft") or [])
    cand_spec = dict(candidate.spec) if candidate.spec else {"species": candidate.species}
    cand_spec.setdefault("species", candidate.species)
    fill_spec = dict(fill.spec) if fill.spec else {"species": fill.species}
    fill_spec.setdefault("species", fill.species)
    draft[candidate_index] = spec_to_slot(cand_spec)
    draft[fill_index] = spec_to_slot(fill_spec)
    regulation = state.get("regulation_mod") or "champions-reg-mb"
    return candidate_improves_best_bring(
        draft,
        working,
        fill_index,
        pick,
        threat_specs,
        None,
        regulation=regulation,
    )


def _search_gap_fill(
    candidate: AnnotatedCandidate,
    state: RecommenderState,
    locked: Sequence[LockedAnchorContext],
    mask: frozenset[int],
    objective: Sequence[object],
    candidate_index: int,
) -> AnnotatedCandidate | None:
    from recommender.condition_resilience import assess_condition_resilience
    from recommender.teammates import pairwise_teammate_lift, query_shared_teammates
    from recommender.threat_counters import query_candidates_for_threats
    from recommender.usage_data import lineage_ids

    filtered = [row for row in locked if row.slot_index not in mask]
    synthetic = _synthetic_candidate_context(candidate, candidate_index, state)
    working = [*filtered, synthetic]
    regulation = state.get("regulation_mod") or "champions-reg-mb"
    ownership_mode = state.get("ownership_mode", "off")
    owned = owned_species_ids(state)
    names = [
        row.resolved_build.species
        for row in working
        if row.resolved_build.species
    ]
    shared = query_shared_teammates(names, regulation)
    resilience = assess_condition_resilience(working)
    locked_species = [str(name) for name in names]
    excluded = {
        lineage for species in locked_species for lineage in lineage_ids(species)
    }
    try:
        discovery = query_candidates_for_threats(
            objective,  # type: ignore[arg-type]
            available_pool=sorted(owned),
            ownership_mode=ownership_mode,
            excluded_species=excluded,
            locked_contexts=working,
            exclude_slots=mask,
        )
        threat_rows = (
            discovery.candidates if discovery.status != "unavailable" else ()
        )
    except Exception:
        threat_rows = ()
    merged = merge_multi_locked_candidates(
        state,
        working,
        threat_rows,
        shared,
        ownership_mode=ownership_mode,
        owned_species=owned,
        condition_resilience=resilience,
    )
    annotated = annotate_composition_impact(
        merged,
        state,
        locked_anchors=working,
        condition_resilience=resilience,
        objective=objective,  # type: ignore[arg-type]
    )
    ranked = rank_multi_locked_by_category(annotated, working)
    blocked = {to_id(candidate.species)}
    blocked.update(to_id(row.resolved_build.species or "") for row in working)
    ranked = [row for row in ranked if to_id(row.species) not in blocked]
    shared_ids: set[str] = set()
    if shared is not None and getattr(shared, "status", None) == "available":
        shared_ids = {to_id(getattr(row, "species_id", "")) for row in (shared.rows or ())}

    def sort_key(row: AnnotatedCandidate) -> tuple[int, float]:
        hit = to_id(row.species) in shared_ids
        lift = pairwise_teammate_lift(candidate.species, row.species, regulation)
        return (0 if hit else 1, -(lift if lift is not None else 0.0))

    ranked = sorted(ranked, key=sort_key)
    opens = [
        index
        for index, slot in enumerate(state.get("team_draft") or [])
        if not all_locked(slot)
    ]
    # discover_masked_core_package requires len(opens) >= 2, so fill_index is
    # always set on the only production call path.
    fill_index = opens[1] if len(opens) > 1 else None
    for row in ranked:
        if not _has_usage_backed(row):
            continue
        if fill_index is not None and not _calc_agrees(
            candidate, row, state, working, objective, fill_index, candidate_index
        ):
            continue
        return row
    return None


def discover_masked_core_package(
    candidate: AnnotatedCandidate,
    state: RecommenderState,
    locked: Sequence[LockedAnchorContext],
    *,
    objective: Sequence[object] = (),
) -> MaskedCorePackage | None:
    """Pure gap-fill against a masked exclusive-resource conflict. No graph."""
    mask = set(mask_slots_for(candidate))
    remaining = remaining_open_after_place(state)
    if not mask or remaining < 1 or len(mask) > remaining:
        return None
    opens = [
        index
        for index, slot in enumerate(state.get("team_draft") or [])
        if not all_locked(slot)
    ]
    if len(opens) < 2:
        return None
    used_fills = 0
    fill: AnnotatedCandidate | None = None
    while True:
        fill = _search_gap_fill(
            candidate, state, locked, frozenset(mask), objective, opens[0]
        )
        if fill is None:
            return None
        used_fills += 1
        extra = {
            row.locked_slot_index
            for row in fill.core_slot_conflicts
            if row.locked_slot_index not in mask
        }
        if remaining - used_fills <= 0:
            extra = {
                index
                for index in extra
                if not _is_sole_needed_provider(index, locked, frozenset(mask))
            }
        extra -= mask
        if not extra:
            break
        if used_fills >= remaining:
            return None
        mask |= extra
        if len(mask) > remaining:
            return None
    if fill is None:
        return None
    frozen = frozenset(mask)
    return MaskedCorePackage(
        candidate=candidate,
        masked_slot_indices=tuple(sorted(frozen)),
        fill=fill,
        label=_package_label(candidate, locked, frozen),
    )


def gather_masked_core_packages(
    candidates: Sequence[AnnotatedCandidate],
    state: RecommenderState,
    locked: Sequence[LockedAnchorContext],
    *,
    objective: Sequence[object] = (),
) -> tuple[MaskedCorePackage, ...]:
    packages: list[MaskedCorePackage] = []
    for candidate in candidates:
        if not should_try_masked_core(candidate, candidates, state, locked):
            continue
        package = discover_masked_core_package(
            candidate, state, locked, objective=objective
        )
        if package is not None:
            packages.append(package)
    return tuple(packages)
