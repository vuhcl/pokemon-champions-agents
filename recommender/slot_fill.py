"""ADR-023 orchestrator consumption: hold, annotate, select, refine."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Any, Literal, Sequence, get_args

from recommender.anchor_roles import (
    AnchorRoleDecision,
    ResolvedAnchorBuild,
    _canonical_weather,
    classify_anchor_role,
    provided_weather_conditions,
    resolve_anchor_build,
    weather_beneficiary_ability_ids,
)
from recommender.by_usage import query_by_usage
from recommender.calc_client import PokemonSpecOptional
from recommender.condition_types import ConditionResilienceReport
from recommender.contingent_value import REDIRECT_MOVES
from recommender.coverage import ABILITY_TO_FIELD
from recommender.ids import to_id
from recommender.matchup import CHARGE_INSTANT_WEATHER
from recommender.legality import is_species_legal, load_snapshot, resolve_learnset
from recommender.move_narrowing import (
    MIN_USAGE_PCT,
    _HARD_REQUIRE_WEATHER,
    move_appears_in_usage,
    narrow_candidates_for_move,
    pick_default_and_alternatives,
)
from recommender.propose import _propagate_and_refine
from recommender.ranking import OwnershipMode
from recommender.role_compendium_read import (
    CompendiumRoleEvidence,
    ReverseCompendiumEvidence,
    role_category_evidence,
    reverse_compendium_evidence,
)
from recommender.state import (
    Attr,
    CandidateBranch,
    CandidateConfidence,
    CandidateDiscoveryError,
    CandidateEvidence,
    CandidateEvidenceBasis,
    CompositionFit,
    PendingPresentation,
    PendingPresentationOption,
    PendingSlotIntent,
    PresentationSource,
    ProvisionalSlot,
    RecommenderState,
    Slot,
    TargetRoleDecision,
    TargetRoleId,
    TargetRoleResult,
    TeamCompletionPreference,
    ThreatCounterCandidate,
    UnresolvedSlotRefinement,
    UnresolvedTargetRoleDecision,
    slot_fingerprint,
)
from recommender.support_needs import (
    NeedCategory,
    RoleShapeContext,
    SupportNeed,
    _weather_category_match,
    field_labels_from_trigger,
)
from recommender.usage_data import (
    featured_or_common_set,
    ingame_species_map,
    ingame_ladder_species_map,
    lineage_ids,
    showdown_species_map,
)

Source = PresentationSource
SlotFillAction = Literal["accept_default", "choose", "defer"]

@dataclass(frozen=True)
class _NeedSatisfier:
    moves: frozenset[str] = frozenset()
    abilities: frozenset[str] = frozenset()


# Annotate: learnset ∩ moves OR abilities ∩ ability ids. No defensive_coverage
# entry — no cheap teammate signal → never matches.
_NEED_SATISFIERS: dict[NeedCategory, _NeedSatisfier] = {
    "trick_room": _NeedSatisfier(moves=frozenset({"trickroom"})),
    "tailwind": _NeedSatisfier(moves=frozenset({"tailwind"})),
    "redirection": _NeedSatisfier(moves=frozenset(REDIRECT_MOVES)),
    # Wish is delayed-delivery in doubles (switch-in cost) — not a healing_cleric
    # satisfier. Immediate heals only.
    "healing_cleric": _NeedSatisfier(
        moves=frozenset({"healpulse", "lifedew", "aromatherapy", "healbell"})
    ),
    "screens": _NeedSatisfier(
        moves=frozenset({"lightscreen", "reflect", "auroraveil"})
    ),
    "condition_setter": _NeedSatisfier(abilities=frozenset(ABILITY_TO_FIELD)),
}


@dataclass(frozen=True)
class CoreSlotConflict:
    """Which locked member a candidate conflicts with over weather or mega."""

    kind: Literal["weather", "mega"]
    locked_slot_index: int
    locked_species: str
    resource: str


@dataclass(frozen=True)
class AnnotatedCandidate:
    species: str
    matching_needs: tuple[SupportNeed, ...]
    source: Source
    target_role_decision: TargetRoleResult | None = None
    threat_row: ThreatCounterCandidate | None = None
    spec: PokemonSpecOptional = field(default_factory=dict)  # type: ignore[assignment]
    evidence: tuple[CandidateEvidence, ...] = ()
    branches: frozenset[CandidateBranch] = frozenset()
    anchor_ids: frozenset[str] = frozenset()
    anchor_slot_indices: frozenset[int] = frozenset()
    composition_fit: CompositionFit = "neutral"
    fills_essential_gap: bool = False
    # Split from fills_essential_gap: a genuinely missing provider
    # (gap=="missing_provider") always ranks in fills_essential_gap
    # (unconditional top priority). A single_provider_spof backup
    # opportunity with real complementary value (build divergence from
    # the existing provider) is tracked separately here -- confirmed
    # live, collapsing both into one boolean let a weak, low-confidence
    # backup-only candidate outrank strong, high-confidence, unrelated
    # candidates entirely, since fills_essential_gap was the FIRST,
    # highest-priority field in ranking. See _rank_key/_sort_annotated
    # for where this is now given a deliberately lower priority than
    # evidence quality, rather than removed from ranking entirely.
    fills_spof_backup_gap: bool = False
    shared_min_pct: float | None = None
    shared_worst_rank: int | None = None
    anchored_needs: tuple[AnchoredSupportNeed, ...] = ()
    direction_label: str | None = None
    strategic_role_id: str | None = None
    species_primary_role: str | None = None
    primary_function: Literal["offense", "support", "unknown"] | None = None
    mechanism_ids: tuple[str, ...] | None = None
    # Confirmed live (2026-08-21): during core-slot construction (slot_index
    # < picked_team_size), a candidate whose real distinguishing value
    # depends on a scarce, single-use team resource (weather, mega
    # evolution) that's already claimed -- in a CONFLICTING way -- by
    # something locked in wastes a core slot on a mechanic that can't
    # actually fire this battle (Swampert-Mega's real Rain-abuse value on
    # a team already committed to Sun via a locked Charizard-Mega-Y; a
    # second mega-stone holder when only one can Mega Evolve per battle).
    # Index-based rank demotion only -- bench slots (slot_index >=
    # picked_team_size) keep wastes_core_slot=False even when
    # core_slot_conflicts is populated for masked-core discovery.
    # See team_candidates.candidate_wastes_core_slot.
    wastes_core_slot: bool = False
    # Confirmed live (2026-08-21/22, design discussion): for bench slots
    # (slot_index >= picked_team_size), "does this add more stackable
    # coverage" is the wrong question -- only picked_team_size of the
    # roster ever plays together in a given game. True when
    # candidate_improves_best_bring confirms some real, coherent bring-N
    # combination including this candidate beats every combination
    # achievable from the locked roster alone. Deliberately scoped to
    # candidates with NO unmet needed-importance weather dependency --
    # a dependent candidate (Mega-Swampert-shaped) evaluated alone
    # would get an honestly wrong (unamplified) coverage number, since
    # team_field_states only forces a weather when a real provider is
    # also in the subset; correctly pairing it with one is a separate,
    # not-yet-built capability (masked alternate-core discovery),
    # deliberately not approximated here. False for core slots and for
    # dependent candidates -- not evaluated, not "confirmed doesn't
    # improve."
    improves_bench_subset: bool = False
    # Confirmed live (2026-08-22): Mawile-Mega's real Trick Room
    # dependency can be nominally "satisfied" by a locked Sinistcha whose
    # real, aggregate Trick Room commitment (57.2%) is barely more than
    # a coinflip against its actual defining move, Rage Powder (95.6%)
    # -- Sinistcha's real primary job is redirection, not a genuine
    # Trick-Room-specialist build the way Farigiraf is. 1.0 = no
    # dependency, or a fully reliable one (ability-based, or a real
    # dedicated specialist's move commitment); lower = the team's
    # provision of a real, benefits_from dependency is less trustworthy.
    # A ranking signal, not a hard gate -- unlike wastes_core_slot, this
    # never excludes or forces a candidate to the bottom on its own; it
    # only nudges rank-sum ordering, since an unreliable enabler is a
    # real but soft downside, not a disqualifying one. See
    # condition_resilience.candidate_dependency_reliability.
    dependency_reliability: float = 1.0
    # Populated once len(state_locked) >= picked_team_size (core complete),
    # independent of wastes_core_slot / index-based rank demotion. Drives
    # masked alternate-core discovery (should_try_masked_core, mask indices).
    core_slot_conflicts: tuple[CoreSlotConflict, ...] = ()


@dataclass(frozen=True)
class AnchoredSupportNeed:
    anchor_slot_index: int
    anchor_id: str
    need: SupportNeed


@dataclass(frozen=True)
class LockedAnchorContext:
    slot_index: int
    anchor_id: str
    pokemon: PokemonSpecOptional
    resolved_build: ResolvedAnchorBuild
    role_decision: AnchorRoleDecision
    role_shape_context: RoleShapeContext
    support_needs: tuple[AnchoredSupportNeed, ...]


@dataclass(frozen=True)
class NeedResolvedCandidate:
    species: str
    matching_needs: tuple[SupportNeed, ...]
    evidence: tuple[CandidateEvidence, ...]
    anchored_needs: tuple[AnchoredSupportNeed, ...] = ()


@dataclass
class SlotFillContext:
    anchor: PokemonSpecOptional | None
    role_shape_context: RoleShapeContext | None
    target_role_decision: TargetRoleResult | None = None
    threat_counter_results: list[ThreatCounterCandidate] | None = None
    support_needs: list[SupportNeed] | None = None
    chosen_need: SupportNeed | None = None
    need_resolved_candidates: list[NeedResolvedCandidate] | None = None
    annotated_candidates: list[AnnotatedCandidate] | None = None
    candidates_pre_ranked: bool = False
    threat_discovery_status: Literal["available", "unavailable", "degraded"] = (
        "available"
    )
    threat_discovery_error: CandidateDiscoveryError | None = None
    notices: tuple[str, ...] = ()
    condition_resilience: ConditionResilienceReport | None = None
    locked_contexts: tuple[LockedAnchorContext, ...] = ()
    team_completion_preference: TeamCompletionPreference | None = None
    banned_profiles: frozenset[frozenset[str]] = frozenset()
    soft_mechanical: tuple = field(default_factory=tuple)
    constraint_slot_index: int | None = None
    constraint_team_draft: list | None = None


@dataclass(frozen=True)
class AnchoredSlotDiscovery:
    context: SlotFillContext | None
    resolved_build: Any | None
    anchor_role_decision: Any | None
    bypassed: bool


def build_anchored_slot_fill_context(
    state: RecommenderState,
    anchor_slot: Slot | None,
    *,
    user_anchor_role: str | None = None,
    target_role_decision: TargetRoleResult | None = None,
    threat_counter_results: list[ThreatCounterCandidate] | None = None,
) -> AnchoredSlotDiscovery:
    """Construct the one production anchor→shape→raw-query context."""
    if anchor_slot is None or not anchor_slot.species.value:
        return AnchoredSlotDiscovery(None, None, None, True)

    from recommender.anchor_roles import (
        classify_anchor_role,
        derive_role_shape_context,
        resolve_anchor_build,
    )
    from recommender.support_needs import query_support_needs
    from recommender.team_candidates import collect_locked_anchor_contexts
    from recommender.threat_counters import query_threat_counters

    regulation = _regulation(state)
    resolved = resolve_anchor_build(
        anchor_slot,
        role_hint=user_anchor_role or anchor_slot.role.value,
        regulation=regulation,
    )
    decision = classify_anchor_role(
        resolved,
        user_role=user_anchor_role,
        explicit_role=anchor_slot.role.value if anchor_slot.role.locked else None,
    )
    shape = derive_role_shape_context(decision)
    pokemon = resolved.as_pokemon()
    needs = query_support_needs(
        pokemon,
        shape,
        team_draft=state["team_draft"],
        state=state,
        regulation=regulation,
    )
    if threat_counter_results is not None:
        threats = list(threat_counter_results)
        discovery_status: Literal["available", "unavailable", "degraded"] = "available"
        discovery_error: CandidateDiscoveryError | None = None
    else:
        locked = collect_locked_anchor_contexts(state)
        discovery = query_threat_counters(pokemon, locked_contexts=locked)
        threats = list(discovery.candidates)
        discovery_status = discovery.status
        discovery_error = discovery.error
    return AnchoredSlotDiscovery(
        SlotFillContext(
            anchor=pokemon,
            role_shape_context=shape,
            target_role_decision=target_role_decision,
            threat_counter_results=threats,
            support_needs=needs,
            threat_discovery_status=discovery_status,
            threat_discovery_error=discovery_error,
        ),
        resolved,
        decision,
        False,
    )


@dataclass(frozen=True)
class PresentedCandidate:
    species: str
    source: Source
    evidence: tuple[CandidateEvidence, ...]
    track: str | None = None


@dataclass(frozen=True)
class SlotFillPresentation:
    """Ordered candidate choices; acceptance creates a pending intent, not a lock."""

    slot_index: int
    candidates: tuple[PresentedCandidate, ...]
    notices: tuple[str, ...] = ()

    @property
    def default(self) -> str | None:
        return self.candidates[0].species if self.candidates else None

    @property
    def alternatives(self) -> list[str]:
        return [candidate.species for candidate in self.candidates[1:]]

    @property
    def options(self) -> tuple[str, ...]:
        return tuple(candidate.species for candidate in self.candidates)


@dataclass(frozen=True)
class SlotFillResponse:
    action: SlotFillAction
    species: str | None = None  # required for choose


@dataclass
class SlotFillTerminalResult:
    presentation: SlotFillPresentation
    state_updates: dict[str, Any]
    deferred: bool


from recommender.slot_fill_target_role import (  # noqa: E402
    REVIEWED_STRATEGIC_TARGET_ROLES,
    _CONDITION_SETTER_TARGET_ROLES,
    _NEED_TARGET_ROLES,
    _kit_fallback_target_role,
    _resolved_candidate_target_role,
    derive_target_role,
    target_role_from_anchored_needs,
    target_role_from_needs,
    target_role_from_strategic_evidence,
)


def _regulation(state: RecommenderState | None = None) -> str:
    reg = (state or {}).get("regulation_mod") or "champions-reg-mb"
    return "champions-reg-mb" if reg == "champions" else str(reg)


def _legality_abilities(snap: dict[str, Any], species: str) -> set[str]:
    entry = (snap.get("species") or {}).get(to_id(species)) or {}
    return {
        to_id(v) for v in (entry.get("abilities") or {}).values() if isinstance(v, str)
    }


def _species_abilities(species: str, *, snap: dict[str, Any], regulation: str) -> set[str]:
    out = _legality_abilities(snap, species)
    featured = featured_or_common_set(species, regulation=regulation)
    if featured and featured.get("ability"):
        out.add(to_id(str(featured["ability"])))
    return out


def _field_label_matches(aid: str, label: str) -> bool:
    field = ABILITY_TO_FIELD.get(aid)
    if not field:
        return False
    w, t = field.get("weather"), field.get("terrain")
    if w and _weather_category_match(str(w), label):
        return True
    if t and to_id(str(t)) == to_id(label):
        return True
    return False


def _ability_matches_field_labels(aid: str, labels: list[str]) -> bool:
    return any(_field_label_matches(aid, lab) for lab in labels)


def _candidate_satisfies_need(
    species: str,
    need: SupportNeed,
    *,
    snap: dict[str, Any],
    regulation: str = "champions-reg-mb",
) -> bool:
    sat = _NEED_SATISFIERS.get(need.category)
    if sat is None:
        return False
    ls = set(resolve_learnset(snap, species) or [])
    if sat.moves:
        matching = ls & sat.moves
        if matching and any(
            move_appears_in_usage(species, mid, regulation=regulation)
            for mid in matching
        ):
            return True
    if sat.abilities:
        abs_ = _species_abilities(species, snap=snap, regulation=regulation)
        if need.category == "condition_setter" and need.trigger:
            labels = field_labels_from_trigger(need.trigger)
            if labels:
                return any(
                    aid in abs_ and _ability_matches_field_labels(aid, labels)
                    for aid in ABILITY_TO_FIELD
                )
        if abs_ & sat.abilities:
            return True
    return False


def _matching_needs_for(
    species: str,
    needs: list[SupportNeed],
    *,
    snap: dict[str, Any],
    regulation: str = "champions-reg-mb",
) -> tuple[SupportNeed, ...]:
    return tuple(
        n
        for n in needs
        if _candidate_satisfies_need(species, n, snap=snap, regulation=regulation)
    )


def _merge_evidence(
    *groups: tuple[CandidateEvidence, ...],
) -> tuple[CandidateEvidence, ...]:
    return tuple(dict.fromkeys(row for group in groups for row in group))


def _threat_evidence(
    row: ThreatCounterCandidate,
    *,
    degradation_kind: Literal["calc_unavailable", "calc_incomplete"] | None = None,
) -> tuple[CandidateEvidence, ...]:
    candidate = row.candidate
    if row.estimate_kind == "static":
        axis_tags = []
        if "wall" in candidate.threat_kinds:
            axis_tags.append("wall_axis")
        if "ko_threshold" in candidate.threat_kinds:
            axis_tags.append("ko_threshold_proxy")
        return (
            CandidateEvidence(
                basis="mechanical_only",
                confidence="low",
                producer_name="query_threat_counters",
                evidence=(
                    "static_type_estimate",
                    degradation_kind or "calc_unavailable",
                    *axis_tags,
                    f"threats_countered:{','.join(row.threats_countered)}",
                    f"build_source:{candidate.build_source}",
                ),
            ),
        )
    details = (
        f"verified_score:{row.verified_score}",
        f"threats_countered:{','.join(row.threats_countered)}",
        f"build_source:{candidate.build_source}",
    )
    if candidate.usage_rank is not None or candidate.showdown_usage_pct is not None:
        return (
            CandidateEvidence(
                basis="usage_backed",
                confidence="high",
                producer_name="query_threat_counters",
                evidence=details
                + (
                    f"usage_rank:{candidate.usage_rank}",
                    f"showdown_usage_pct:{candidate.showdown_usage_pct}",
                ),
            ),
        )
    return (
        CandidateEvidence(
            basis="mechanical_only",
            confidence="medium",
            producer_name="query_threat_counters",
            evidence=details,
        ),
    )


def _degradation_kind(
    ctx: SlotFillContext,
) -> Literal["calc_unavailable", "calc_incomplete"] | None:
    error = ctx.threat_discovery_error
    if (
        ctx.threat_discovery_status == "degraded"
        and error is not None
        and error.kind in ("calc_unavailable", "calc_incomplete")
    ):
        return error.kind  # type: ignore[return-value]
    return None


def _promote_exact_compendium(
    evidence: tuple[CandidateEvidence, ...], spec: PokemonSpecOptional
) -> tuple[CandidateEvidence, ...]:
    species = str(spec.get("species") or "")
    if not species or not any(row.basis == "compendium_backed" for row in evidence):
        return evidence
    reverse = reverse_compendium_evidence(
        species,
        moves=tuple(str(move) for move in spec.get("moves", []) or []),
        ability=str(spec.get("ability") or "") or None,
    )
    exact_roles = {row.role_id for row in reverse.exact}
    return tuple(
        CandidateEvidence(
            basis=row.basis,
            confidence=(
                "high"
                if row.basis == "compendium_backed"
                and any(
                    detail == f"role:{role}"
                    for role in exact_roles
                    for detail in row.evidence
                )
                else row.confidence
            ),
            producer_name=row.producer_name,
            evidence=row.evidence,
        )
        for row in evidence
    )


def annotate_overlap(ctx: SlotFillContext) -> list[AnnotatedCandidate]:
    """Cheap cross-branch annotation once both branch outputs exist."""
    if ctx.threat_counter_results is None or ctx.support_needs is None:
        raise ValueError(
            "annotate_overlap requires threat_counter_results and support_needs"
        )
    derive_target_role(ctx)
    snap = load_snapshot()
    regulation = "champions-reg-mb"
    degradation_kind = _degradation_kind(ctx)
    out: list[AnnotatedCandidate] = []
    for row in ctx.threat_counter_results:
        species = (
            row.candidate.spec.get("species")
            or row.candidate.form
            or row.candidate.ladder_species
        )
        matched = _matching_needs_for(
            species, ctx.support_needs, snap=snap, regulation=regulation
        )
        out.append(
            AnnotatedCandidate(
                species=species,
                matching_needs=matched,
                source="both" if matched else "threat",
                target_role_decision=_resolved_candidate_target_role(
                    ctx, species, matched
                ),
                threat_row=row,
                spec=dict(row.candidate.spec) or {"species": species},
                evidence=_threat_evidence(row, degradation_kind=degradation_kind),
            )
        )
    ctx.annotated_candidates = out
    return out


def merge_need_resolved(ctx: SlotFillContext) -> list[AnnotatedCandidate]:
    """Merge threat rows with need-resolved species; chosen_need optional (resolve-all)."""
    if ctx.need_resolved_candidates is None or ctx.threat_counter_results is None:
        raise ValueError(
            "merge_need_resolved requires need_resolved_candidates "
            "and threat_counter_results"
        )
    derive_target_role(ctx)
    needs = list(ctx.support_needs or [])
    if ctx.chosen_need is not None and ctx.chosen_need not in needs:
        needs = [*needs, ctx.chosen_need]
    snap = load_snapshot()
    regulation = "champions-reg-mb"
    degradation_kind = _degradation_kind(ctx)

    by_id: dict[str, AnnotatedCandidate] = {}
    for row in ctx.threat_counter_results:
        species = (
            row.candidate.spec.get("species")
            or row.candidate.form
            or row.candidate.ladder_species
        )
        sid = to_id(species)
        matched = _matching_needs_for(species, needs, snap=snap, regulation=regulation)
        by_id[sid] = AnnotatedCandidate(
            species=species,
            matching_needs=matched,
            source="both" if matched else "threat",
            target_role_decision=_resolved_candidate_target_role(
                ctx, species, matched
            ),
            threat_row=row,
            spec=dict(row.candidate.spec) or {"species": species},
            evidence=_threat_evidence(row, degradation_kind=degradation_kind),
        )

    for resolved in ctx.need_resolved_candidates:
        sid = to_id(resolved.species)
        existing = by_id.get(sid)
        if existing is not None:
            matched = tuple(
                dict.fromkeys((*existing.matching_needs, *resolved.matching_needs))
            )
            if ctx.chosen_need is not None and ctx.chosen_need not in matched:
                matched = (*matched, ctx.chosen_need)
            evidence = _promote_exact_compendium(
                _merge_evidence(existing.evidence, resolved.evidence), existing.spec
            )
            by_id[sid] = AnnotatedCandidate(
                species=existing.species,
                matching_needs=matched,
                source="both",
                target_role_decision=_resolved_candidate_target_role(
                    ctx, existing.species, matched
                ),
                threat_row=existing.threat_row,
                spec=existing.spec,
                evidence=evidence,
            )
            continue
        matched = resolved.matching_needs
        if ctx.chosen_need is not None and ctx.chosen_need not in matched:
            matched = (*matched, ctx.chosen_need)
        by_id[sid] = AnnotatedCandidate(
            species=resolved.species,
            matching_needs=matched,
            source="need",
            target_role_decision=_resolved_candidate_target_role(
                ctx, resolved.species, matched
            ),
            threat_row=None,
            spec={"species": resolved.species},
            evidence=resolved.evidence,
        )

    out = list(by_id.values())
    ctx.annotated_candidates = out
    return out


def _union_move_candidates(
    move_ids: frozenset[str], state: RecommenderState
) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for mid in sorted(move_ids):
        for name in narrow_candidates_for_move(mid, state).candidates:
            sid = to_id(name)
            if sid in seen:
                continue
            seen.add(sid)
            out.append(name)
    return out


def _need_evidence_details(need: SupportNeed) -> tuple[str, ...]:
    return (
        f"need:{need.category}",
        f"trigger:{need.trigger or 'none'}",
    )


def _narrow_need_candidates(
    need: SupportNeed,
    move_id: str,
    state: RecommenderState,
    *,
    available_species: frozenset[str],
    ownership_mode: OwnershipMode,
) -> list[NeedResolvedCandidate]:
    result = narrow_candidates_for_move(
        move_id,
        state,
        available_species=available_species,
        ownership_mode=ownership_mode,
    )
    regulation = _regulation(state)
    out: list[NeedResolvedCandidate] = []
    for species in result.candidates:
        if not move_appears_in_usage(species, move_id, regulation=regulation):
            continue
        meta = result.candidate_meta.get(to_id(species))
        if meta is not None and meta.commitment_pct is not None:
            evidence = CandidateEvidence(
                basis="usage_backed",
                confidence="medium",
                producer_name="narrow_candidates_for_move",
                evidence=_need_evidence_details(need)
                + (
                    f"move:{move_id}",
                    f"commitment_pct:{meta.commitment_pct}",
                    f"usage_pct:{meta.usage_pct}",
                    f"delivery:{meta.delivery}",
                ),
            )
        else:
            evidence = CandidateEvidence(
                basis="mechanical_only",
                confidence="low",
                producer_name="narrow_candidates_for_move",
                evidence=_need_evidence_details(need) + (f"move:{move_id}",),
            )
        out.append(NeedResolvedCandidate(species, (need,), (evidence,)))
    return out


def _union_move_resolved(
    need: SupportNeed,
    move_ids: frozenset[str],
    state: RecommenderState,
    *,
    available_species: frozenset[str],
    ownership_mode: OwnershipMode,
) -> list[NeedResolvedCandidate]:
    by_id: dict[str, NeedResolvedCandidate] = {}
    for move_id in sorted(move_ids):
        for row in _narrow_need_candidates(
            need,
            move_id,
            state,
            available_species=available_species,
            ownership_mode=ownership_mode,
        ):
            sid = to_id(row.species)
            existing = by_id.get(sid)
            by_id[sid] = (
                NeedResolvedCandidate(
                    existing.species,
                    existing.matching_needs,
                    _merge_evidence(existing.evidence, row.evidence),
                )
                if existing is not None
                else row
            )
    return list(by_id.values())


def _is_battle_only_transient_forme(sid: str, entry: dict[str, Any], regulation: str) -> bool:
    """Whether sid is a forme that only ever appears automatically during
    battle (weather/terastal/etc.-triggered) rather than something a
    player independently picks and boxes -- Castform's weather formes,
    not Rotom's appliance formes.

    Confirmed live (2026-08-22): resolve_condition_beneficiaries surfaced
    Castform/Castform-Sunny/Castform-Rainy/Castform-Snowy as four
    independent candidates, when a player only ever picks base "Castform"
    -- the weather-triggered formes aren't a real, separate team-building
    choice. Verified directly, not assumed: every battle-only automatic
    forme checked (Castform's three weather formes, Terapagos-Stellar,
    Zygarde-Complete) has zero rows in BOTH ingame_species_map and
    showdown_species_map -- they can never appear in a real team export,
    because they can't exist outside of live battle state. Genuinely
    separate, player-chosen formes (Rotom-Wash/Heat/Fan/Frost/Mow) all
    have real Showdown rows, since players do independently pick and
    report them. Some other battle-only formes (Mimikyu-Busted, Cramorant-
    Gulping/Gorging, Eiscue-Noice, Minior's core forme) aren't even
    independently is_species_legal entries at all -- _species_with_
    abilities's own legal-species filter already excludes those before
    this check would ever run, confirmed directly; this function only
    needs to handle the ones that DO pass that filter despite being
    battle-only.

    Deliberately requires base_species_id to be set (a real forme
    relationship), not just "zero usage rows alone" -- a genuinely new,
    independently-legal, real species that simply has low usage must
    never be excluded here; this collapses formes, it doesn't gate on
    popularity (that's Amendment 2026-08-22a's job, elsewhere).
    """
    base = entry.get("base_species_id")
    if not base or base == sid:
        return False
    return sid not in ingame_species_map(regulation) and sid not in showdown_species_map(
        regulation
    )


def _species_with_abilities(
    ability_ids: frozenset[str],
    *,
    snap: dict[str, Any],
    regulation: str,
) -> list[str]:
    out: list[str] = []
    for sid, entry in (snap.get("species") or {}).items():
        if not is_species_legal(snap, sid):
            continue
        if _is_battle_only_transient_forme(sid, entry, regulation):
            continue
        name = str(entry.get("name") or sid)
        if _species_abilities(name, snap=snap, regulation=regulation) & ability_ids:
            out.append(name)
    return out


def _rank_by_usage(
    names: list[str],
    *,
    n: int = 20,
    available_species: frozenset[str],
    ownership_mode: OwnershipMode,
) -> list[str]:
    if not names:
        return []
    ranked = query_by_usage(
        [{"species": name} for name in names],
        n=n,
        available_species=available_species,
        ownership_mode=ownership_mode,
    )
    out: list[str] = []
    seen: set[str] = set()
    for c in ranked:
        sp = c.spec.get("species") or c.form or c.ladder_species
        if not sp:
            continue
        sid = to_id(sp)
        if sid in seen:
            continue
        seen.add(sid)
        out.append(str(sp))
    return out


def _mechanical_rows(
    need: SupportNeed, names: list[str], producer_name: str
) -> list[NeedResolvedCandidate]:
    evidence = CandidateEvidence(
        basis="mechanical_only",
        confidence="low",
        producer_name=producer_name,
        evidence=_need_evidence_details(need),
    )
    return [NeedResolvedCandidate(name, (need,), (evidence,)) for name in names]


def _resolve_condition_setter(
    need: SupportNeed,
    state: RecommenderState,
    *,
    available_species: frozenset[str],
    ownership_mode: OwnershipMode,
) -> list[str]:
    snap = load_snapshot()
    regulation = _regulation(state)
    labels = field_labels_from_trigger(need.trigger) if need.trigger else []
    names: list[str] = []
    for sid, entry in (snap.get("species") or {}).items():
        if not is_species_legal(snap, sid):
            continue
        name = str(entry.get("name") or sid)
        abs_ = _species_abilities(name, snap=snap, regulation=regulation)
        if labels:
            if any(
                aid in abs_ and _ability_matches_field_labels(aid, labels) for aid in abs_
            ):
                names.append(name)
        elif abs_ & frozenset(ABILITY_TO_FIELD):
            names.append(name)
    return _rank_by_usage(
        names,
        available_species=available_species,
        ownership_mode=ownership_mode,
    )


def _compendium_roles_for_need(need: SupportNeed) -> list[tuple[str, str]]:
    if need.category == "trick_room":
        return [("trick_room_setter", "")]
    if need.category == "screens":
        return [("screens_support", "")]
    if need.category == "tailwind":
        return [("tailwind_setter", "")]
    if need.category == "redirection":
        return [("redirection", "")]
    if need.category == "condition_setter" and need.trigger:
        weather = {"rain": "Rain", "sun": "Sun", "sand": "Sand", "snow": "Snow"}
        return [
            ("weather_setter", weather[label])
            for label in field_labels_from_trigger(need.trigger)
            if label in weather
        ]
    return []


def _compendium_row(
    need: SupportNeed, row: CompendiumRoleEvidence
) -> NeedResolvedCandidate:
    details = _need_evidence_details(need) + (
        f"role:{row.role_id}",
        f"tier:{row.tier}",
        f"mechanism:{row.mechanism or 'unknown'}",
        f"source_file:{row.source_file}",
    )
    return NeedResolvedCandidate(
        row.species,
        (need,),
        (
            CandidateEvidence(
                basis="compendium_backed",
                confidence="medium",
                producer_name="role_category_evidence",
                evidence=details,
            ),
        ),
    )


def _raw_need_candidates(
    need: SupportNeed,
    state: RecommenderState,
    *,
    available_species: frozenset[str],
    ownership_mode: OwnershipMode,
) -> list[NeedResolvedCandidate]:
    cat = need.category
    if cat == "defensive_coverage":
        raise NotImplementedError(
            f"need {need.category}: compendium/ability-search deferred"
        )
    if cat == "condition_setter":
        return _mechanical_rows(
            need,
            _resolve_condition_setter(
                need,
                state,
                available_species=available_species,
                ownership_mode=ownership_mode,
            ),
            "_resolve_condition_setter",
        )

    sat = _NEED_SATISFIERS.get(cat)
    if sat is None or not sat.moves:
        raise NotImplementedError(
            f"need {need.category}: compendium/ability-search deferred"
        )

    if cat in ("trick_room", "tailwind"):
        mid = next(iter(sat.moves))
        return _narrow_need_candidates(
            need,
            mid,
            state,
            available_species=available_species,
            ownership_mode=ownership_mode,
        )

    return _union_move_resolved(
        need,
        sat.moves,
        state,
        available_species=available_species,
        ownership_mode=ownership_mode,
    )


def _raw_claim_survives_rejection(
    need: SupportNeed,
    species: str,
    rejected: tuple[CompendiumRoleEvidence, ...],
    *,
    state: RecommenderState,
) -> bool:
    rejected_roles = {
        row.role_id for row in rejected if to_id(row.species) == to_id(species)
    }
    if not rejected_roles:
        return True
    if need.category == "trick_room":
        return False
    snap = load_snapshot()
    regulation = _regulation(state)
    abilities = _species_abilities(species, snap=snap, regulation=regulation)
    if need.category == "condition_setter" and need.trigger:
        labels = field_labels_from_trigger(need.trigger)
        matching = {
            label
            for label in labels
            if any(
                aid in abilities and _field_label_matches(aid, label)
                for aid in ABILITY_TO_FIELD
            )
        }
        return any(f"{label}_setter" not in rejected_roles for label in matching)
    return True


def resolve_need_candidates(
    need: SupportNeed,
    state: RecommenderState,
    *,
    available_species: frozenset[str] = frozenset(),
    ownership_mode: OwnershipMode = "off",
    locked_weather: str | None = None,
    locked_species: Sequence[str] = (),
) -> list[NeedResolvedCandidate]:
    compendium: list[NeedResolvedCandidate] = []
    rejected: list[CompendiumRoleEvidence] = []
    for category, condition in _compendium_roles_for_need(need):
        evidence = role_category_evidence(category, condition)
        compendium.extend(_compendium_row(need, row) for row in evidence.species)
        rejected.extend(evidence.rejected)

    by_id: dict[str, NeedResolvedCandidate] = {}
    for row in compendium:
        sid = to_id(row.species)
        existing = by_id.get(sid)
        by_id[sid] = (
            NeedResolvedCandidate(
                existing.species,
                existing.matching_needs,
                _merge_evidence(existing.evidence, row.evidence),
            )
            if existing is not None
            else row
        )
    has_real_compendium = bool(_compendium_roles_for_need(need))
    for row in _raw_need_candidates(
        need,
        state,
        available_species=available_species,
        ownership_mode=ownership_mode,
    ):
        sid = to_id(row.species)
        existing = by_id.get(sid)
        if existing is not None:
            usage = tuple(item for item in row.evidence if item.basis == "usage_backed")
            if usage:
                by_id[sid] = NeedResolvedCandidate(
                    existing.species,
                    existing.matching_needs,
                    _merge_evidence(existing.evidence, usage),
                )
            continue
        # A need with a real compendium category (screens, tailwind,
        # trick_room, redirection) only matches candidates the
        # compendium actually recognizes -- confirmed live: Gholdengo
        # genuinely isn't a recognized screens user despite mechanically
        # learning Light Screen/Reflect, so it must not match at all, not
        # even at low confidence, when a real compendium exists to check
        # against. Needs without a real compendium (healing_cleric) are
        # unaffected -- there's nothing to restrict against for those.
        if has_real_compendium:
            continue
        if not _raw_claim_survives_rejection(
            need, row.species, tuple(rejected), state=state
        ):
            continue
        by_id[sid] = row
    rows = list(by_id.values())
    if locked_species:
        # Exclude already-locked lineage members -- confirmed live
        # (2026-08-21): this function had no already-locked exclusion at
        # all, unlike resolve_condition_beneficiaries's locked_lineages
        # check right next to it in the same module. Not yet observed as
        # a triggered live bug here specifically, but a structurally
        # identical gap sitting right next to one that's already
        # protected -- e.g. a base Charizard could in principle surface
        # via a real support-need match even with Charizard-Mega-Y
        # already locked. Mirrors resolve_condition_beneficiaries's
        # pattern exactly rather than inventing a second convention.
        locked_lineages = {
            lid for name in locked_species for lid in lineage_ids(name)
        }
        rows = [row for row in rows if to_id(row.species) not in locked_lineages]
    if locked_weather is not None:
        # A candidate matched only via a move that HARD-requires a
        # different weather than what the team already has locked in
        # isn't actually usable right now -- confirmed live: Abomasnow's
        # only screens move is Aurora Veil, which requires Snow/Hail to
        # be usable at all, and only one weather can be active. Rather
        # than excluding the candidate outright, its matching evidence
        # is downgraded to low confidence with an explicit conflict tag
        # -- deprioritizes it (via the same evidence-quality ranking
        # this codebase already uses elsewhere) without discarding real
        # information the candidate might still be worth surfacing as a
        # low-priority option, e.g. if the team's weather later changes.
        # A candidate that also learns an unconditionally-usable
        # satisfying move (e.g. Light Screen/Reflect) is untouched even
        # if it ALSO happens to know a hard-gated one -- only downgraded
        # when EVERY move-based match for this need is hard-blocked.
        # Candidates matched via ability evidence (no move-shaped tag at
        # all) are left untouched -- this check is specifically about
        # move-based satisfaction, not a general weather-relevance
        # judgment this function isn't equipped to make.
        #
        # Checks both evidence tag formats real data actually produces:
        # the raw-move path's "move:auroraveil" and the compendium
        # path's "mechanism:Aurora Veil" -- confirmed live these differ,
        # not assumed. Both normalized via to_id() so they consistently
        # match _HARD_REQUIRE_WEATHER's keys regardless of which path
        # produced the match.
        adjusted_rows: list[NeedResolvedCandidate] = []
        for row in rows:
            move_ids = [
                to_id(tag.removeprefix("move:"))
                for item in row.evidence
                for tag in item.evidence
                if tag.startswith("move:")
            ] + [
                to_id(tag.removeprefix("mechanism:"))
                for item in row.evidence
                for tag in item.evidence
                if tag.startswith("mechanism:")
            ]
            if not move_ids:
                adjusted_rows.append(row)
                continue
            required_weathers = {
                _HARD_REQUIRE_WEATHER[mid]
                for mid in move_ids
                if mid in _HARD_REQUIRE_WEATHER
            }
            usable = not required_weathers or locked_weather in required_weathers
            if usable:
                adjusted_rows.append(row)
                continue
            required = next(iter(required_weathers))
            # Downgrades BOTH basis and confidence, not confidence alone
            # -- _BASIS_RANK ranks compendium_backed highest (4) and is
            # compared before confidence in every ranking that uses this
            # evidence, so a confidence-only downgrade wouldn't actually
            # deprioritize this below genuinely-usable candidates with a
            # lower basis rank. mechanical_only/low matches this
            # signal's real semantic meaning here -- a weak, currently-
            # inapplicable match, not a strong compendium-backed one.
            downgraded_evidence = tuple(
                replace(
                    item,
                    basis="mechanical_only",
                    confidence="low",
                    evidence=item.evidence
                    + (f"weather_conflict:requires_{required}_have_{locked_weather}",),
                )
                for item in row.evidence
            )
            adjusted_rows.append(
                NeedResolvedCandidate(
                    row.species, row.matching_needs, downgraded_evidence, row.anchored_needs
                )
            )
        rows = adjusted_rows

    if ownership_mode == "owned_only":
        rows = [row for row in rows if to_id(row.species) in available_species]
    elif ownership_mode == "owned_first":
        rows.sort(key=lambda row: to_id(row.species) not in available_species)
    return rows


def _confidence_for_need_evidence(
    need: SupportNeed, item: CandidateEvidence
) -> Literal["high", "medium", "low"]:
    """Unconditional needs default low; keep real in-game commitment confidence."""
    if need.trigger is not None:
        return item.confidence
    if item.basis == "usage_backed" and any(
        tag.startswith("commitment_pct:") for tag in item.evidence
    ):
        return item.confidence
    return "low"


def resolve_all_support_needs(
    ctx: SlotFillContext,
    state: RecommenderState,
    *,
    anchored_needs: tuple[AnchoredSupportNeed, ...] = (),
    available_species: frozenset[str] = frozenset(),
    ownership_mode: OwnershipMode = "off",
    locked_weather: str | None = None,
    locked_species: Sequence[str] = (),
) -> list[NeedResolvedCandidate]:
    """Resolve every surfaced need; skip deferred/empty; set need_resolved_candidates."""
    by_id: dict[str, NeedResolvedCandidate] = {}
    inputs: tuple[tuple[SupportNeed, AnchoredSupportNeed | None], ...] = (
        tuple((anchored.need, anchored) for anchored in anchored_needs)
        if anchored_needs
        else tuple((need, None) for need in ctx.support_needs or [])
    )
    for need, anchored in inputs:
        try:
            names = resolve_need_candidates(
                need,
                state,
                available_species=available_species,
                ownership_mode=ownership_mode,
                locked_weather=locked_weather,
                locked_species=locked_species,
            )
        except NotImplementedError:
            continue
        for row in names:
            sid = to_id(row.species)
            subject_id = f"{need.category}:{to_id(need.trigger or '')}"
            # Unconditional needs (trigger=None: screens/healing_cleric
            # attacker-universal fallbacks) are weakly specific as a
            # *category*, but a candidate's real in-game commitment to
            # filling them is a separate signal -- already attached as
            # usage_backed + commitment_pct by _narrow_need_candidates
            # (ingame_species_map only). Blanket "low" was filtering
            # Excellent/high-commitment screens users (Grimmsnarl) before
            # ranked_b. Keep item.confidence when commitment is present;
            # otherwise keep the low override. Never invent Showdown here.
            evidence = tuple(
                replace(
                    item,
                    branch="need",
                    origin_slot_index=(
                        anchored.anchor_slot_index if anchored is not None else None
                    ),
                    origin_anchor_id=(
                        anchored.anchor_id if anchored is not None else None
                    ),
                    subject_id=subject_id,
                    confidence=_confidence_for_need_evidence(need, item),
                )
                for item in row.evidence
            )
            row_anchored = (anchored,) if anchored is not None else ()
            existing = by_id.get(sid)
            if existing is None:
                by_id[sid] = replace(
                    row, evidence=evidence, anchored_needs=row_anchored
                )
                continue
            by_id[sid] = NeedResolvedCandidate(
                species=existing.species,
                matching_needs=tuple(
                    dict.fromkeys((*existing.matching_needs, *row.matching_needs))
                ),
                evidence=_merge_evidence(existing.evidence, evidence),
                anchored_needs=tuple(
                    dict.fromkeys((*existing.anchored_needs, *row_anchored))
                ),
            )
    out = list(by_id.values())
    ctx.need_resolved_candidates = out
    return out


def resolve_condition_beneficiaries(
    ctx: SlotFillContext,
    decision: AnchorRoleDecision | None,
    state: RecommenderState,
    *,
    locked_species: Sequence[str],
    available_species: frozenset[str] = frozenset(),
    ownership_mode: OwnershipMode = "off",
) -> list[NeedResolvedCandidate]:
    """Invert present weather provides into kit-emitted benefits_from candidates.

    NOT ADDRESSED HERE, logged explicitly rather than silently dropped
    (2026-08-21): this function inverts what the ANCHOR provides into
    candidates who BENEFIT from it -- it has no corresponding check in
    the other direction, whether a CANDIDATE's own kit conflicts with
    what's already locked. Confirmed live: Archaludon (needs Rain for
    Electro Shot) and Sinistcha (Grass, real Fire-weakness gets worse
    under boosted Sun) both surfaced on a team already committed to Sun.
    Neither is a condition_beneficiary bug specifically -- Archaludon came
    through the real threat-coverage branch (query_threat_counters,
    already flagged 2026-08-20 as not field-aware), and the type-weakness-
    amplification case (Sinistcha) has no existing mechanism to extend at
    all, in this function or anywhere else in the codebase. This is a
    distinct, currently unimplemented capability -- a real
    benefits_from/type-matchup-vs-locked-condition conflict check -- not
    something the discover_single_locked -> discover_multi_locked routing
    fix (same investigation) was ever going to solve, since neither
    pipeline has this check.
    """
    existing = list(ctx.need_resolved_candidates or [])
    if decision is None or not hasattr(decision, "mechanisms"):
        ctx.need_resolved_candidates = existing
        return existing

    weathers = provided_weather_conditions(decision)
    if not weathers:
        ctx.need_resolved_candidates = existing
        return existing

    locked_lineages = {lid for name in locked_species for lid in lineage_ids(name)}
    snap = load_snapshot()
    regulation = _regulation(state)
    by_id: dict[str, NeedResolvedCandidate] = {
        to_id(row.species): row for row in existing
    }

    for condition in weathers:
        need = SupportNeed(
            category="condition_beneficiary",
            name=f"{condition} beneficiary",
            description=(
                f"Anchor provides {condition}; candidate kit-emits "
                f"benefits_from {condition}."
            ),
            trigger=f"field_condition:provided:{to_id(condition)}",
        )
        subject_id = f"condition_beneficiary:{to_id(condition)}"
        ability_ids = weather_beneficiary_ability_ids(condition)
        ability_names: dict[str, str] = {}
        ability_hits: dict[str, frozenset[str]] = {}
        for name in _species_with_abilities(
            ability_ids, snap=snap, regulation=regulation
        ):
            sid = to_id(name)
            if sid in locked_lineages:
                continue
            matched = (
                _species_abilities(name, snap=snap, regulation=regulation)
                & ability_ids
            )
            if not matched:
                continue
            ability_names[sid] = name
            ability_hits[sid] = frozenset(matched)

        move_rows: dict[str, NeedResolvedCandidate] = {}
        for move_id, labels in CHARGE_INSTANT_WEATHER.items():
            if not any(_canonical_weather(label) == condition for label in labels):
                continue
            for row in _narrow_need_candidates(
                need,
                move_id,
                state,
                available_species=available_species,
                ownership_mode=ownership_mode,
            ):
                sid = to_id(row.species)
                if sid in locked_lineages:
                    continue
                prior = move_rows.get(sid)
                move_rows[sid] = (
                    NeedResolvedCandidate(
                        prior.species,
                        prior.matching_needs,
                        _merge_evidence(prior.evidence, row.evidence),
                    )
                    if prior is not None
                    else row
                )

        union = list(
            dict.fromkeys(
                [*ability_names.values(), *(row.species for row in move_rows.values())]
            )
        )
        ranked = _rank_by_usage(
            union,
            n=20,
            available_species=available_species,
            ownership_mode=ownership_mode,
        )
        ladder_map = ingame_ladder_species_map(regulation)
        showdown_map = showdown_species_map(regulation)
        for name in ranked:
            sid = to_id(name)
            parts: list[CandidateEvidence] = []
            if sid in ability_hits:
                # Confidence now reflects real usage where it's actually
                # confirmed, rather than a hardcoded "high" regardless --
                # confirmed live (2026-08-21): Castform (0.037% Showdown
                # usage, absent from the in-game top-50) got the same
                # "high confidence" as a genuinely strong pick purely from
                # matching a beneficiary ability.
                #
                # Deliberately does NOT simply invert to "low unless
                # proven popular" -- query_by_usage (used for ordering
                # above) always returns usage_rank=None/showdown_usage_pct
                # =None regardless of real data (confirmed directly; it
                # never actually populates that field), and mega forms are
                # entirely absent from the in-game top-50 snapshot as a
                # known, separate data gap -- confirmed directly:
                # Swampert-Mega is absent from ingame_species_map but has
                # a real, substantial 8.19% Showdown usage. Absence from a
                # known-incomplete dataset is not evidence of poor
                # quality, so it must not be penalized the same way as a
                # species that IS present in real data but negligible
                # there (Castform). The existing, deliberate "ability-
                # based match = high confidence" convention (an ability is
                # mechanically certain/always-active, unlike a move that
                # might not be run) is preserved as the default and only
                # overridden by confirmed negative evidence, not by a data
                # gap. Reuses move_narrowing.MIN_USAGE_PCT (1.0), the same
                # negligible-usage floor already established elsewhere in
                # this codebase.
                # Resolved to the lineage base (lineage_ids[0] is always
                # the base species regardless of which member is queried,
                # confirmed directly) before the usage lookup -- Castform-
                # Sunny/Rainy/Snowy each have their own species id with no
                # usage entry of their own; only base "castform" carries
                # the real Showdown data. This does NOT fix the separate,
                # still-open forme-duplication bug (they still surface as
                # 3 independent candidate rows) -- it only makes sure
                # whichever row does get generated reads the correct real
                # usage data instead of silently missing it by id mismatch.
                in_ingame = lineage_ids(sid)[0] in ladder_map
                sw_entry = showdown_map.get(sid) or showdown_map.get(lineage_ids(sid)[0])
                sw_pct = sw_entry.get("usage_pct") if sw_entry else None
                if in_ingame or (sw_pct is not None and sw_pct >= MIN_USAGE_PCT):
                    basis: CandidateEvidenceBasis = "usage_backed"
                    confidence: CandidateConfidence = "high"
                elif sw_pct is not None and sw_pct < MIN_USAGE_PCT:
                    basis = "mechanical_only"
                    confidence = "low"
                else:
                    basis = "mechanical_only"
                    confidence = "high"
                parts.append(
                    CandidateEvidence(
                        basis=basis,
                        confidence=confidence,
                        producer_name="resolve_condition_beneficiaries",
                        evidence=(
                            "need:condition_beneficiary",
                            f"condition:{condition}",
                            *(f"ability:{aid}" for aid in sorted(ability_hits[sid])),
                            "relation:benefits_from",
                        ),
                        branch="need",
                        subject_id=subject_id,
                    )
                )
            if sid in move_rows:
                parts.extend(
                    replace(item, branch="need", subject_id=subject_id)
                    for item in move_rows[sid].evidence
                )
            if not parts:
                continue
            row = NeedResolvedCandidate(
                name, (need,), _merge_evidence(tuple(parts))
            )
            prior = by_id.get(sid)
            if prior is None:
                by_id[sid] = row
                continue
            by_id[sid] = NeedResolvedCandidate(
                species=prior.species,
                matching_needs=tuple(
                    dict.fromkeys((*prior.matching_needs, *row.matching_needs))
                ),
                evidence=_merge_evidence(prior.evidence, row.evidence),
                anchored_needs=prior.anchored_needs,
            )

    out = list(by_id.values())
    ctx.need_resolved_candidates = out
    return out


def _usage_rank_key(row: AnnotatedCandidate) -> float:
    if row.threat_row is not None and row.threat_row.candidate.usage_rank is not None:
        return float(row.threat_row.candidate.usage_rank)
    return float("inf")


def _compendium_rank(row: AnnotatedCandidate) -> int:
    confidence = {
        evidence.confidence
        for evidence in row.evidence
        if evidence.basis == "compendium_backed"
    }
    if confidence and not row.matching_needs:
        raise AssertionError("compendium-backed candidate must match an active need")
    if "high" in confidence:
        return 0
    if confidence:
        return 1
    return 2


def _sort_annotated(
    rows: list[AnnotatedCandidate],
    *,
    soft_mechanical: tuple = (),
    team_draft: list | None = None,
    open_slot_index: int | None = None,
) -> list[AnnotatedCandidate]:
    from recommender.constraint_enforcement import soft_rank_bonus

    def _soft_bonus(row: AnnotatedCandidate) -> int:
        if not soft_mechanical:
            return 0
        return soft_rank_bonus(
            row.species,
            soft_mechanical,
            team_draft=team_draft or [],
            open_slot_index=open_slot_index,
        )

    return sorted(
        rows,
        key=lambda r: (
            -int(r.fills_essential_gap),
            _compendium_rank(r),
            -int(r.fills_spof_backup_gap),
            -len(r.matching_needs),
            -(
                r.threat_row.verified_score
                if r.threat_row is not None and r.threat_row.estimate_kind == "verified"
                else 0.0
            ),
            _usage_rank_key(r),
            _soft_bonus(r),
        ),
    )


def _ordered_annotated(ctx: SlotFillContext) -> list[AnnotatedCandidate]:
    rows = list(ctx.annotated_candidates or [])
    if ctx.candidates_pre_ranked:
        return rows
    return _sort_annotated(
        rows,
        soft_mechanical=ctx.soft_mechanical,
        team_draft=ctx.constraint_team_draft,
        open_slot_index=ctx.constraint_slot_index,
    )


def _redundancy_tier_for_candidates(
    rows: list[AnnotatedCandidate],
    resilience: ConditionResilienceReport | None,
) -> dict[str, int]:
    """species -> 0 (prefer)/1/2 (deprioritize), used only for which
    alternatives to show alongside the default -- never affects ranking
    or which species is the default itself.

    Confirmed live: two of three "strategically different alternatives"
    were both tailwind_setter after a Tailwind setter was already locked
    -- fills_essential_gap (the ranking boost) treats "missing_provider"
    and "single_provider_spof" identically, so ranking alone doesn't
    distinguish a genuinely unmet need from a role that's merely eligible
    for backup redundancy, and either can independently rank highly
    enough to fill multiple alternative slots.

    Tier 0: role doesn't correspond to a tracked condition, or the
    condition still has gap=="missing_provider" -- a genuinely unmet
    need, always preferred.
    Tier 1: gap=="single_provider_spof" (the condition's own
    classification -- essential/preferred -- already means a backup
    provider has real strategic value, not merely optional) AND the
    candidate also matches another, distinct support-need category --
    e.g. Sableye as both a rain_setter and a screens provider. Backup
    value is real, but must come bundled with something else to compete
    with tier 0.
    Tier 2: gap=="none" (fully resolved, no backup value at all), or a
    SPOF-eligible role with no other contributing need -- purely
    redundant, shown only if there aren't enough tier 0/1 candidates to
    fill the alternative slots.
    """
    if resilience is None:
        return {}
    from recommender.condition_resilience import _SETTER_ROLE_FOR_CONDITION

    condition_for_role = {v: k for k, v in _SETTER_ROLE_FOR_CONDITION.items()}
    gap_by_condition = {row.condition: row.gap for row in resilience.conditions}

    tiers: dict[str, int] = {}
    for row in rows:
        role_id = getattr(row.target_role_decision, "role_id", None)
        condition = condition_for_role.get(role_id) if role_id else None
        if condition is None:
            tiers[row.species] = 0
            continue
        gap = gap_by_condition.get(condition, "none")
        if gap == "missing_provider":
            tiers[row.species] = 0
        elif gap == "single_provider_spof":
            distinct_categories = {need.category for need in row.matching_needs}
            tiers[row.species] = 1 if len(distinct_categories) > 1 else 2
        else:
            tiers[row.species] = 2
    return tiers


def _scoped_evidence(
    evidence: tuple[CandidateEvidence, ...], category_keys: list[str]
) -> tuple[CandidateEvidence, ...]:
    """Filters a candidate's full evidence tuple down to only the
    item(s) relevant to the track(s) it actually won, so the displayed
    evidence corresponds to why the candidate is being shown -- not the
    single highest-quality item across every need it happens to satisfy
    regardless of relevance.

    Confirmed live, a real bug: a candidate labeled "support/utility"
    displayed "usage_backed, high confidence" -- evidence that turned
    out to belong to its (unrelated, unlabeled) threat-counter data, not
    its actual support-need match, which was really mechanical_only/low.
    The label and the evidence told two different, inconsistent stories.

    Category A evidence has branch="threat"; categories B and C both
    have branch="need" (support-needs and condition-benefit are both
    resolved through the same need-resolution machinery) -- C is
    distinguished from B via the "need:condition_beneficiary" evidence
    tag specifically, confirmed against real evidence data before
    relying on it.
    """
    if not category_keys or not evidence:
        return evidence
    wants_a = "A" in category_keys
    wants_b = "B" in category_keys
    wants_c = "C" in category_keys
    scoped = tuple(
        item
        for item in evidence
        if (wants_a and item.branch == "threat")
        or (
            item.branch == "need"
            and (
                (wants_c and any("need:condition_beneficiary" in tag for tag in item.evidence))
                or (wants_b and not any("need:condition_beneficiary" in tag for tag in item.evidence))
            )
        )
    )
    return scoped or evidence


def present_candidates(
    ctx: SlotFillContext, *, slot_index: int
) -> SlotFillPresentation:
    rows = _ordered_annotated(ctx)
    names = [r.species for r in rows]
    if ctx.locked_contexts:
        # Multi-signal, per-category selection (select_diverse_candidates)
        # replaces the single-ranking + redundancy-tier approach here --
        # confirmed with Vu directly, following extensive live evidence
        # that a single ranking kept surfacing narrow or context-blind
        # candidate sets even after several real ranking bugs were fixed.
        # Deliberately scoped to the multi-locked path only (non-empty
        # locked_contexts): its three categories (type-synergy+threat-
        # counter, support-needs, condition-benefit) are built around
        # signals that are only meaningful once multiple team members
        # already exist to create real type/condition interactions --
        # single-locked keeps the older approach unchanged.
        from recommender.team_candidates import select_diverse_candidates

        picked = select_diverse_candidates(
            rows,
            ctx.locked_contexts,
            preference=ctx.team_completion_preference,
            banned_profiles=ctx.banned_profiles,
        )
    else:
        tier_for = _redundancy_tier_for_candidates(rows, ctx.condition_resilience)
        picked = pick_default_and_alternatives(names, redundancy_tier=tier_for)
    default = picked.get("default")
    alts = list(picked.get("alternatives") or [])
    tracks: dict[str, str] = picked.get("tracks") or {}
    category_keys: dict[str, list[str]] = picked.get("category_keys") or {}
    options: list[str] = []
    if default:
        options.append(default)
    options.extend(a for a in alts if a and a not in options)
    by_species = {to_id(row.species): row for row in rows}
    return SlotFillPresentation(
        slot_index=slot_index,
        candidates=tuple(
            PresentedCandidate(
                species=species,
                source=by_species[to_id(species)].source,
                evidence=_scoped_evidence(
                    by_species[to_id(species)].evidence,
                    category_keys.get(species, []),
                ),
                track=tracks.get(species),
            )
            for species in options
        ),
        notices=ctx.notices,
    )


def _pending_presentation(
    ctx: SlotFillContext,
    presentation: SlotFillPresentation,
    *,
    regulation: str,
) -> PendingPresentation:
    from recommender.team_candidates import species_primary_role_for_candidate
    rows = _ordered_annotated(ctx)
    by_species: dict[str, AnnotatedCandidate] = {}
    for row in rows:
        by_species.setdefault(to_id(row.species), row)
    options: list[PendingPresentationOption] = []
    for candidate in presentation.candidates:
        row = by_species[to_id(candidate.species)]
        option: PendingPresentationOption = {
            "species": candidate.species,
            "source": row.source,
            "evidence": candidate.evidence,
        }
        if row.target_role_decision is not None:
            option["target_role_decision"] = row.target_role_decision
        if row.direction_label is not None:
            option["direction_label"] = row.direction_label
        if row.strategic_role_id is not None:
            option["strategic_role_id"] = row.strategic_role_id
        if row.primary_function is not None:
            option["primary_function"] = row.primary_function
        if row.mechanism_ids is not None:
            option["mechanism_ids"] = row.mechanism_ids
        primary_role = row.species_primary_role
        if primary_role is None:
            primary_role = species_primary_role_for_candidate(
                row.species, dict(row.spec or {}), regulation
            )
        if primary_role:
            option["species_primary_role"] = primary_role
        need_cats = sorted(
            {
                n.category
                for n in row.matching_needs
                if n.category != "condition_beneficiary"
            }
        )
        if need_cats:
            option["need_categories"] = need_cats
            if "trick_room" in need_cats and len(need_cats) > 1:
                option["secondary_trick_room"] = True
        if candidate.track is not None:
            option["track"] = candidate.track
        options.append(option)
    pending: PendingPresentation = {
        "schema_version": 1,
        "kind": "candidate_selection",
        "slot_index": presentation.slot_index,
        "options": options,
        "notices": presentation.notices,
    }
    return pending


_EMPTY_CANDIDATE_POOL_PROMPT = (
    "No more candidates for this slot. Reply 'different focus', "
    "pick a remaining option if any, or 'defer'."
)


def run_slot_fill_terminal(
    ctx: SlotFillContext,
    state: RecommenderState,
    *,
    slot_index: int,
    response: SlotFillResponse | None = None,
) -> SlotFillTerminalResult:
    presentation = present_candidates(ctx, slot_index=slot_index)
    pending = _pending_presentation(ctx, presentation, regulation=_regulation(state))

    if response is None:
        if not pending["options"]:
            # Exhausted pool after reject / ban — teachable pending, not raise.
            pending = {
                **pending,
                "prompt_text": _EMPTY_CANDIDATE_POOL_PROMPT,
            }
            return SlotFillTerminalResult(
                presentation=presentation,
                state_updates={"pending_presentation": pending},
                deferred=False,
            )
        return SlotFillTerminalResult(
            presentation=presentation,
            state_updates={"pending_presentation": pending},
            deferred=False,
        )

    if response.action == "defer":
        return SlotFillTerminalResult(
            presentation=presentation,
            state_updates={
                "pending_presentation": None,
                "pending_slot_intent": None,
                "provisional_slot": None,
            },
            deferred=True,
        )

    if response.action == "accept_default":
        species = presentation.default
    elif response.action == "choose":
        species = response.species
    else:
        raise ValueError(f"unknown SlotFillResponse.action: {response.action!r}")

    if not species:
        raise ValueError("cannot select: no species resolved from presentation/response")

    selected = next(
        (
            row
            for row in ctx.annotated_candidates or []
            if to_id(row.species) == to_id(species)
        ),
        None,
    )
    if selected is None or all(
        to_id(species) != to_id(option) for option in presentation.options
    ):
        raise ValueError(f"cannot select: species {species!r} is not a presented option")
    decision = selected.target_role_decision
    intent = PendingSlotIntent(
        schema_version=1,
        slot_index=slot_index,
        species=selected.species,
        target_role_decision=decision,
        source=selected.source,
        evidence=selected.evidence,
        base_slot_fingerprint=slot_fingerprint(state["team_draft"][slot_index]),
    )
    return SlotFillTerminalResult(
        presentation=presentation,
        state_updates={
            "pending_presentation": None,
            "pending_slot_intent": intent,
            "provisional_slot": None,
        },
        deferred=False,
    )


def _provisional_from_refined(
    *,
    intent: PendingSlotIntent,
    decision: TargetRoleDecision,
    refined: Slot,
) -> ProvisionalSlot | UnresolvedSlotRefinement:
    moves = refined.moveset.value or []
    spread = refined.spread.value or {}
    unresolved = tuple(
        name
        for name, complete in (
            ("species", bool(refined.species.value)),
            ("ability", bool(refined.ability.value)),
            ("item", bool(refined.item.value)),
            ("moves", len(moves) == 4 and all(bool(move) for move in moves)),
            ("nature", bool(refined.nature.value)),
            (
                "spread",
                all(stat in spread for stat in ("hp", "atk", "def", "spa", "spd", "spe")),
            ),
        )
        if not complete
    )
    if unresolved:
        return UnresolvedSlotRefinement(
            schema_version=1,
            intent=intent,
            unresolved_fields=unresolved,
        )

    payload = {
        "slot_index": intent.slot_index,
        "role": decision.role_id,
        "species": str(refined.species.value),
        "ability": str(refined.ability.value),
        "item": str(refined.item.value),
        "moves": list(moves),
        "nature": str(refined.nature.value),
        "spread": {stat: int(spread[stat]) for stat in ("hp", "atk", "def", "spa", "spd", "spe")},
        "base": intent.base_slot_fingerprint,
    }
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return ProvisionalSlot(
        schema_version=1,
        slot_index=intent.slot_index,
        target_role_decision=decision,
        species=str(refined.species.value),
        ability=str(refined.ability.value),
        item=str(refined.item.value),
        moves=(str(moves[0]), str(moves[1]), str(moves[2]), str(moves[3])),
        nature=str(refined.nature.value),
        spread=tuple(
            (stat, int(spread[stat]))
            for stat in ("hp", "atk", "def", "spa", "spd", "spe")
        ),
        base_slot_fingerprint=intent.base_slot_fingerprint,
        fingerprint=fingerprint,
    )


def build_provisional_slot(
    intent: PendingSlotIntent, state: RecommenderState
) -> ProvisionalSlot | UnresolvedSlotRefinement:
    """Refine a selected candidate without mutating the persisted team draft."""
    decision = intent.target_role_decision
    if not isinstance(decision, TargetRoleDecision):
        decision = _kit_fallback_target_role(intent.species)
    if not isinstance(decision, TargetRoleDecision):
        return UnresolvedSlotRefinement(
            schema_version=1,
            intent=intent,
            unresolved_fields=("target_role",),
            reason="unresolved_target_role",
        )

    seed = Slot(
        role=Attr(value=decision.role_id),
        species=Attr(value=intent.species),
    )
    refined, _ = _propagate_and_refine(
        seed,
        state,
        regulation=_regulation(state),
    )
    return _provisional_from_refined(intent=intent, decision=decision, refined=refined)


_EDIT_SLOT_ATTR = {
    "ability": "ability",
    "item": "item",
    "moves": "moveset",
    "nature": "nature",
    "spread": "spread",
}

_SPREAD_STATS = ("hp", "atk", "def", "spa", "spd", "spe")


def _normalize_stat_key(key: object) -> str | None:
    """Normalize a stat key to canonical lowercase form ('Spe' -> 'spe').

    Model output uses conventional capitalized abbreviations (HP, Atk, Def,
    SpA, SpD, Spe) -- confirmed live, consistently, across real extractions
    -- while this module's internal representation is always lowercase.
    Returns None for anything that doesn't normalize to a known stat, so
    callers can reject rather than silently drop or misapply a value.
    """
    if not isinstance(key, str):
        return None
    normalized = key.strip().lower()
    return normalized if normalized in _SPREAD_STATS else None


_STAT_FULL_NAMES = {
    "hp": "hp",
    "health": "hp",
    "atk": "atk",
    "attack": "atk",
    "def": "def",
    "defense": "def",
    "defence": "def",
    "spa": "spa",
    "spatk": "spa",
    "specialattack": "spa",
    "spd": "spd",
    "spdef": "spd",
    "specialdefense": "spd",
    "specialdefence": "spd",
    "spe": "spe",
    "speed": "spe",
}


def parse_stat_reply(reply: str) -> str | None:
    """Normalize a free-text stat name to a canonical lowercase key, or
    None if it doesn't match a known stat. Accepts standard abbreviations
    (case-insensitive, matching this module's spread convention) and a
    handful of common full names/spellings. Shared by nodes.py (parsing a
    reallocation-question reply) and turn_intent.py (deterministic
    single-stat-target extraction from free text) -- moved here rather
    than one importing from the other, to avoid an awkward cross-layer
    dependency direction.
    """
    normalized = _normalize_stat_key(reply)
    if normalized is not None:
        return normalized
    collapsed = "".join(reply.split()).lower()
    return _STAT_FULL_NAMES.get(collapsed)


def stat_label(stat: str) -> str:
    return "HP" if stat == "hp" else stat.capitalize()


def _normalize_spread_dict(value: object) -> dict[str, int] | None:
    """Normalize an arbitrary stat-keyed dict to canonical lowercase keys.

    Returns None (never raises) if any key doesn't normalize to a known
    stat, any value isn't numeric, or two keys normalize to the same stat
    (e.g. both 'spe' and 'Spe' present) -- same fail-closed contract as
    every other spread-value guard in this module.
    """
    if not isinstance(value, dict):
        return None
    result: dict[str, int] = {}
    try:
        for key, val in value.items():
            stat = _normalize_stat_key(key)
            if stat is None or stat in result:
                return None
            result[stat] = int(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return result


def _coerce_full_spread(value: object) -> dict[str, int] | None:
    """Full six-stat spread dict from a full-replace edit value.

    Returns None (never raises) on anything malformed -- missing stat keys,
    wrong type, non-numeric values. Previously this coercion used a bare
    dict comprehension (`value[stat]` for each stat) with no guard, which
    raised an uncaught KeyError on a partial/malformed dict rather than
    degrading gracefully to UnresolvedSlotRefinement the way every other
    edit-value failure in this module does. Also previously didn't
    normalize stat-key casing at all -- confirmed live, this silently
    rejected every real model extraction, since the model consistently
    emits capitalized abbreviations, not this module's lowercase
    convention.
    """
    normalized = _normalize_spread_dict(value)
    if normalized is None or set(normalized) != set(_SPREAD_STATS):
        return None
    return normalized


def apply_partial_spread(
    base: dict[str, int],
    *,
    set_stats: dict[str, int] | None = None,
    delta_stats: dict[str, int] | None = None,
) -> dict[str, int] | None:
    """Apply a partial set and/or delta onto a full base spread.

    set_stats: named stats become exactly this value.
    delta_stats: named stats get this signed amount added to whatever
    they end up being after set_stats is applied (set then delta, in that
    order, so "set Spe to 5, then add 3 more" composes predictably if both
    were ever populated -- though _edit_value_slot_ok currently only ever
    allows one form at a time per edit).

    set_stats/delta_stats keys are normalized case-insensitively (model
    output uses conventional capitalized abbreviations); `base` is always
    this module's own internal representation and is never normalized.

    Returns None (never raises) on an unknown stat name or non-numeric
    value, so callers can degrade to UnresolvedSlotRefinement/
    slot_commit_error instead of crashing on a malformed model output.
    """
    normalized_set = _normalize_spread_dict(set_stats) if set_stats else {}
    if set_stats and normalized_set is None:
        return None
    normalized_delta = _normalize_spread_dict(delta_stats) if delta_stats else {}
    if delta_stats and normalized_delta is None:
        return None

    result = dict(base)
    try:
        for stat, val in normalized_set.items():
            result[stat] = val
        for stat, val in normalized_delta.items():
            result[stat] = int(result[stat]) + val
    except (TypeError, ValueError):
        return None
    return result


def _display_nature(value: object) -> str:
    from recommender.turn_intent import _REAL_NATURES

    raw = str(value)
    return _REAL_NATURES.get(to_id(raw), raw)


def _display_move(name: str, snap: dict[str, Any]) -> str:
    mid = to_id(name)
    meta = (snap.get("moves") or {}).get(mid) or {}
    display = meta.get("name") if isinstance(meta, dict) else None
    return str(display) if display else name


def _reconstruct_partial_moveset(
    current_moves: Sequence[str],
    value: object,
    *,
    user_text: str,
    species: str,
    snap: dict[str, Any],
) -> list[str] | None:
    """Rebuild a 4-move set from a 1–2 name swap/replace edit."""
    if not isinstance(value, (list, tuple)):
        return None
    names = [str(v) for v in value if v]
    if len(names) == 4:
        return [_display_move(n, snap) for n in names]
    current = [str(m) for m in current_moves]
    if len(current) != 4:
        return None
    current_by_id = {to_id(m): m for m in current}
    learnset = set(resolve_learnset(snap, species) or [])

    extracted: list[str] = []
    seen: set[str] = set()
    for name in names:
        mid = to_id(name)
        if not mid or mid in seen:
            continue
        seen.add(mid)
        extracted.append(name)

    on_set = [n for n in extracted if to_id(n) in current_by_id]
    off_set = [n for n in extracted if to_id(n) not in current_by_id]
    outgoing: str | None = None
    incoming: str | None = None

    from recommender.turn_intent import _find_known_value_in_text

    if len(extracted) == 2 and len(on_set) == 1 and len(off_set) == 1:
        outgoing, incoming = on_set[0], off_set[0]
    elif len(extracted) == 1 and len(off_set) == 1:
        incoming = off_set[0]
        hit = _find_known_value_in_text(user_text, dict(current_by_id))
        if hit is None:
            return None
        outgoing = hit
    elif len(extracted) == 1 and len(on_set) == 1:
        outgoing = on_set[0]
        moves_meta = snap.get("moves") or {}
        candidates: dict[str, str] = {}
        for mid in learnset:
            if mid in current_by_id:
                continue
            meta = moves_meta.get(mid) or {}
            display = meta.get("name") if isinstance(meta, dict) else None
            candidates[mid] = str(display) if display else mid
        hit = _find_known_value_in_text(user_text, candidates)
        if hit is None:
            return None
        incoming = hit
    else:
        return None

    if to_id(incoming) not in learnset:
        return None
    incoming = _display_move(incoming, snap)

    out: list[str] = []
    replaced = False
    for move in current:
        if to_id(move) == to_id(outgoing) and not replaced:
            out.append(incoming)
            replaced = True
        else:
            out.append(move)
    if not replaced or len(out) != 4:
        return None
    if len({to_id(m) for m in out}) != 4:
        return None
    return out


def _coerce_moves_edit_value(
    current: ProvisionalSlot,
    value: object,
    state: RecommenderState,
) -> list[str] | None:
    snap = load_snapshot()
    if isinstance(value, (list, tuple)) and len(value) == 4:
        return [_display_move(str(m), snap) for m in value]
    return _reconstruct_partial_moveset(
        current.moves,
        value,
        user_text=str(state.get("last_user_text") or ""),
        species=current.species,
        snap=snap,
    )


def apply_provisional_overrides(
    current: ProvisionalSlot,
    *,
    overrides: dict[str, object],
    intent: PendingSlotIntent,
    state: RecommenderState,
) -> ProvisionalSlot | UnresolvedSlotRefinement:
    """Pin all provided override fields (locked=True); keep others from current; refine."""
    decision = current.target_role_decision
    if not isinstance(decision, TargetRoleDecision):
        return UnresolvedSlotRefinement(
            schema_version=1,
            intent=intent,
            unresolved_fields=("target_role",),
            reason="unresolved_target_role",
        )
    if not overrides:
        return current

    seed = current.to_slot(locked=False, reason=None)
    for field, value in overrides.items():
        slot_attr = _EDIT_SLOT_ATTR.get(field)
        if slot_attr is None:
            return UnresolvedSlotRefinement(
                schema_version=1,
                intent=intent,
                unresolved_fields=(str(field),),
            )
        if field == "moves":
            coerced = _coerce_moves_edit_value(current, value, state)
            if coerced is None:
                return UnresolvedSlotRefinement(
                    schema_version=1,
                    intent=intent,
                    unresolved_fields=("moves",),
                )
            attr_value: Any = coerced
        elif field == "spread":
            attr_value = _coerce_full_spread(value)
            if attr_value is None:
                return UnresolvedSlotRefinement(
                    schema_version=1,
                    intent=intent,
                    unresolved_fields=("spread",),
                )
        elif field == "nature":
            attr_value = _display_nature(value)
        else:
            attr_value = value
        seed = replace(seed, **{slot_attr: Attr(value=attr_value, locked=True)})

    working_intent = replace(
        intent,
        slot_index=current.slot_index,
        species=current.species,
        target_role_decision=decision,
        base_slot_fingerprint=current.base_slot_fingerprint or intent.base_slot_fingerprint,
    )
    refined, _ = _propagate_and_refine(
        seed,
        state,
        regulation=state.get("regulation_mod") or "champions",
    )
    return _provisional_from_refined(
        intent=working_intent, decision=decision, refined=refined
    )


def revise_provisional_slot(
    current: ProvisionalSlot,
    *,
    field: str,
    value: object,
    scope: Literal["field_only", "regenerate"],
    intent: PendingSlotIntent,
    state: RecommenderState,
) -> ProvisionalSlot | UnresolvedSlotRefinement:
    """Apply a field edit or regenerate around a pinned value; never mutates team_draft."""
    decision = current.target_role_decision
    if not isinstance(decision, TargetRoleDecision):
        return UnresolvedSlotRefinement(
            schema_version=1,
            intent=intent,
            unresolved_fields=("target_role",),
            reason="unresolved_target_role",
        )
    slot_attr = _EDIT_SLOT_ATTR.get(field)
    if slot_attr is None:
        return UnresolvedSlotRefinement(
            schema_version=1,
            intent=intent,
            unresolved_fields=(field,),
        )

    if field == "moves":
        coerced = _coerce_moves_edit_value(current, value, state)
        if coerced is None:
            return UnresolvedSlotRefinement(
                schema_version=1,
                intent=intent,
                unresolved_fields=("moves",),
            )
        attr_value: Any = coerced
    elif field == "spread":
        attr_value = _coerce_full_spread(value)
        if attr_value is None:
            return UnresolvedSlotRefinement(
                schema_version=1,
                intent=intent,
                unresolved_fields=("spread",),
            )
    elif field == "nature":
        attr_value = _display_nature(value)
    else:
        attr_value = value

    pinned = Attr(value=attr_value, locked=True)
    if scope == "field_only":
        seed = replace(
            current.to_slot(locked=False, reason=None),
            **{slot_attr: pinned},
        )
    else:
        seed = Slot(
            role=Attr(value=decision.role_id),
            species=Attr(value=current.species),
            **{slot_attr: pinned},
        )

    working_intent = replace(
        intent,
        slot_index=current.slot_index,
        species=current.species,
        target_role_decision=decision,
        base_slot_fingerprint=current.base_slot_fingerprint or intent.base_slot_fingerprint,
    )
    refined, _ = _propagate_and_refine(
        seed,
        state,
        regulation=state.get("regulation_mod") or "champions",
    )
    return _provisional_from_refined(
        intent=working_intent, decision=decision, refined=refined
    )
