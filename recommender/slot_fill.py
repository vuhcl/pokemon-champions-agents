"""ADR-023 orchestrator consumption: hold, annotate, select, refine."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from recommender.anchor_roles import AnchorRoleDecision, ResolvedAnchorBuild
from recommender.by_usage import query_by_usage
from recommender.calc_client import PokemonSpecOptional
from recommender.contingent_value import REDIRECT_MOVES
from recommender.coverage import ABILITY_TO_FIELD
from recommender.ids import to_id
from recommender.legality import is_species_legal, load_snapshot, resolve_learnset
from recommender.move_narrowing import narrow_candidates_for_move, pick_default_and_alternatives
from recommender.propose import _propagate_and_refine
from recommender.ranking import OwnershipMode
from recommender.role_compendium import (
    CompendiumRoleEvidence,
    ReverseCompendiumEvidence,
    role_category_evidence,
    reverse_compendium_evidence,
)
from recommender.state import (
    Attr,
    CandidateBranch,
    CandidateDiscoveryError,
    CandidateEvidence,
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
from recommender.usage_data import featured_or_common_set

Source = PresentationSource
SlotFillAction = Literal["accept_default", "choose", "defer"]

_FO_PROTECTION_ABILITIES = frozenset(
    {"armortail", "queenlymajesty", "dazzling"}
)


@dataclass(frozen=True)
class _NeedSatisfier:
    moves: frozenset[str] = frozenset()
    abilities: frozenset[str] = frozenset()


# Annotate: learnset ∩ moves OR abilities ∩ ability ids. No defensive_coverage /
# stat_lowering_partner entry — no cheap teammate signal → never matches.
_NEED_SATISFIERS: dict[NeedCategory, _NeedSatisfier] = {
    "trick_room": _NeedSatisfier(moves=frozenset({"trickroom"})),
    "tailwind": _NeedSatisfier(moves=frozenset({"tailwind"})),
    "fake_out_protection": _NeedSatisfier(
        moves=frozenset({"fakeout"}) | frozenset(REDIRECT_MOVES),
        abilities=_FO_PROTECTION_ABILITIES,
    ),
    "taunt_disruption": _NeedSatisfier(moves=frozenset({"taunt"})),
    "healing_cleric": _NeedSatisfier(
        moves=frozenset(
            {"wish", "healpulse", "lifedew", "aromatherapy", "healbell"}
        )
    ),
    "screens": _NeedSatisfier(
        moves=frozenset({"lightscreen", "reflect", "auroraveil"})
    ),
    "condition_setter": _NeedSatisfier(abilities=frozenset(ABILITY_TO_FIELD)),
}


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
    shared_min_pct: float | None = None
    shared_worst_rank: int | None = None
    anchored_needs: tuple[AnchoredSupportNeed, ...] = ()
    direction_label: str | None = None
    strategic_role_id: str | None = None
    primary_function: Literal["offense", "support", "unknown"] | None = None
    mechanism_ids: tuple[str, ...] | None = None


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
        discovery = query_threat_counters(pokemon)
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


@dataclass(frozen=True)
class SlotFillPresentation:
    """Ordered candidate choices; acceptance creates a pending intent, not a lock."""

    slot_index: int
    candidates: tuple[PresentedCandidate, ...]

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


_NEED_TARGET_ROLES: dict[NeedCategory, tuple[TargetRoleId, str]] = {
    "trick_room": ("trick_room_setter", "move:trickroom"),
    "tailwind": ("tailwind_setter", "move:tailwind"),
}
REVIEWED_STRATEGIC_TARGET_ROLES: dict[str, TargetRoleId] = {
    "rainsetter": "rain_setter",
    "sunsetter": "sun_setter",
    "sandsetter": "sand_setter",
    "snowsetter": "snow_setter",
    "redirection": "redirection",
    "trickroomsetter": "trick_room_setter",
    "tailwindsetter": "tailwind_setter",
    "swordsdanceattacker": "swords_dance_attacker",
    "nastyplotattacker": "nasty_plot_attacker",
}


def target_role_from_strategic_evidence(
    role_id: str,
    *,
    anchor_role: AnchorRoleDecision | None = None,
    compendium: ReverseCompendiumEvidence | None = None,
) -> TargetRoleDecision | None:
    """Map reviewed exact strategic evidence to an open-slot role intent."""
    normalized = to_id(role_id)
    mapped = REVIEWED_STRATEGIC_TARGET_ROLES.get(normalized)
    if mapped is None:
        return None

    evidence: list[str] = []
    provenance: list[str] = []
    for mechanism in anchor_role.mechanisms if anchor_role is not None else ():
        if (
            mechanism.present
            and mechanism.importance in ("needed", "wanted")
            and to_id(mechanism.role_id or "") == normalized
        ):
            evidence.append(f"mechanism:{to_id(mechanism.mechanic)}")
            provenance.append(f"anchor_role:{mechanism.source}")

    for row in compendium.exact if compendium is not None else ():
        if row.tier is not None and to_id(row.role_id) == normalized:
            detail = f"compendium:{row.tier}:{row.source_file}"
            if row.mechanism:
                detail += f":{to_id(row.mechanism)}"
            evidence.append(detail)
            provenance.append(f"role_compendium:{row.source_file}")

    if not evidence:
        return None
    return TargetRoleDecision(
        role_id=mapped,
        source="other",
        evidence=tuple(dict.fromkeys(evidence)),
        needed_constraints=(f"role:{mapped}",),
        confidence="high",
        provenance=tuple(dict.fromkeys(provenance)),
        producer_name="target_role_from_strategic_evidence",
    )


def target_role_from_needs(
    needs: tuple[SupportNeed, ...] | list[SupportNeed],
) -> TargetRoleResult | None:
    """Resolve actionable need roles while preserving speed-control ambiguity."""
    relevant = [
        (need, _NEED_TARGET_ROLES[need.category])
        for need in needs
        if need.category in _NEED_TARGET_ROLES
    ]
    if not relevant:
        return None

    role_ids = tuple(dict.fromkeys(role_id for _, (role_id, _) in relevant))
    needed = tuple(
        constraint
        for need, (_, constraint) in relevant
        if need.stance != "want"
    )
    wanted = tuple(
        constraint
        for need, (_, constraint) in relevant
        if need.stance == "want"
    )
    evidence = tuple(
        f"{need.category}:{need.trigger}" if need.trigger else need.category
        for need, _ in relevant
    )
    provenance = tuple(f"support_need:{need.category}" for need, _ in relevant)
    if len(role_ids) > 1:
        return UnresolvedTargetRoleDecision(
            reason="ambiguous_speed_control",
            ambiguity=role_ids,
            source="support_need",
            evidence=evidence,
            needed_constraints=needed,
            wanted_constraints=wanted,
            provenance=provenance,
        )
    return TargetRoleDecision(
        role_id=role_ids[0],
        source="support_need",
        evidence=evidence,
        needed_constraints=needed,
        wanted_constraints=wanted,
        confidence="high",
        provenance=provenance,
    )


def target_role_from_anchored_needs(
    anchored_needs: tuple[AnchoredSupportNeed, ...],
) -> TargetRoleResult | None:
    decision = target_role_from_needs([row.need for row in anchored_needs])
    if decision is None:
        return None
    origins = tuple(
        f"anchor:{row.anchor_id}:slot:{row.anchor_slot_index}"
        for row in anchored_needs
    )
    if isinstance(decision, UnresolvedTargetRoleDecision):
        return replace(
            decision,
            reason="incompatible_support_roles",
            provenance=tuple(dict.fromkeys((*decision.provenance, *origins))),
        )
    return replace(
        decision,
        provenance=tuple(dict.fromkeys((*decision.provenance, *origins))),
    )


def _candidate_target_role(
    ctx: SlotFillContext, matching_needs: tuple[SupportNeed, ...]
) -> TargetRoleResult | None:
    matched = target_role_from_needs(matching_needs)
    decision = ctx.target_role_decision
    if decision is None:
        return matched
    if decision.source != "support_need":
        return decision
    if isinstance(decision, UnresolvedTargetRoleDecision):
        return matched
    return (
        decision
        if isinstance(matched, TargetRoleDecision)
        and matched.role_id == decision.role_id
        else None
    )


def derive_target_role(ctx: SlotFillContext) -> TargetRoleResult | None:
    """Populate the context's open-slot decision from selected support evidence."""
    if ctx.target_role_decision is None:
        needs = [ctx.chosen_need] if ctx.chosen_need is not None else ctx.support_needs or []
        ctx.target_role_decision = target_role_from_needs(needs)
    return ctx.target_role_decision


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
    if sat.moves and ls & sat.moves:
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
                target_role_decision=_candidate_target_role(ctx, matched),
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
            target_role_decision=_candidate_target_role(ctx, matched),
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
                target_role_decision=_candidate_target_role(ctx, matched),
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
            target_role_decision=_candidate_target_role(ctx, matched),
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
    out: list[NeedResolvedCandidate] = []
    for species in result.candidates:
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
    if need.category == "fake_out_protection":
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
    if cat == "stat_lowering_partner":
        return []
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

    if cat in ("trick_room", "tailwind", "taunt_disruption"):
        mid = next(iter(sat.moves))
        return _narrow_need_candidates(
            need,
            mid,
            state,
            available_species=available_species,
            ownership_mode=ownership_mode,
        )

    rows = _union_move_resolved(
        need,
        sat.moves,
        state,
        available_species=available_species,
        ownership_mode=ownership_mode,
    )
    if cat == "fake_out_protection" and sat.abilities:
        snap = load_snapshot()
        regulation = _regulation(state)
        seen = {to_id(row.species) for row in rows}
        names = [row.species for row in rows]
        for n in _species_with_abilities(
            sat.abilities, snap=snap, regulation=regulation
        ):
            sid = to_id(n)
            if sid not in seen:
                seen.add(sid)
                names.append(n)
        ranked = _rank_by_usage(
            names,
            available_species=available_species,
            ownership_mode=ownership_mode,
        )
        by_id = {to_id(row.species): row for row in rows}
        return [
            by_id.get(to_id(name))
            or _mechanical_rows(need, [name], "_species_with_abilities")[0]
            for name in ranked
        ]
    return rows


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
    learnset = set(resolve_learnset(snap, species) or [])
    abilities = _species_abilities(species, snap=snap, regulation=regulation)
    if need.category == "fake_out_protection":
        return "fakeout" in learnset or bool(abilities & _FO_PROTECTION_ABILITIES)
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
        if not _raw_claim_survives_rejection(
            need, row.species, tuple(rejected), state=state
        ):
            continue
        by_id[sid] = row
    rows = list(by_id.values())
    if ownership_mode == "owned_only":
        rows = [row for row in rows if to_id(row.species) in available_species]
    elif ownership_mode == "owned_first":
        rows.sort(key=lambda row: to_id(row.species) not in available_species)
    return rows


def resolve_all_support_needs(
    ctx: SlotFillContext,
    state: RecommenderState,
    *,
    anchored_needs: tuple[AnchoredSupportNeed, ...] = (),
    available_species: frozenset[str] = frozenset(),
    ownership_mode: OwnershipMode = "off",
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
            )
        except NotImplementedError:
            continue
        for row in names:
            sid = to_id(row.species)
            subject_id = f"{need.category}:{to_id(need.trigger or '')}"
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


def _sort_annotated(rows: list[AnnotatedCandidate]) -> list[AnnotatedCandidate]:
    return sorted(
        rows,
        key=lambda r: (
            _compendium_rank(r),
            -len(r.matching_needs),
            -(
                r.threat_row.verified_score
                if r.threat_row is not None and r.threat_row.estimate_kind == "verified"
                else 0.0
            ),
            _usage_rank_key(r),
        ),
    )


def _ordered_annotated(ctx: SlotFillContext) -> list[AnnotatedCandidate]:
    rows = list(ctx.annotated_candidates or [])
    return rows if ctx.candidates_pre_ranked else _sort_annotated(rows)


def present_candidates(
    ctx: SlotFillContext, *, slot_index: int
) -> SlotFillPresentation:
    rows = _ordered_annotated(ctx)
    names = [r.species for r in rows]
    picked = pick_default_and_alternatives(names)
    default = picked.get("default")
    alts = list(picked.get("alternatives") or [])
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
                evidence=by_species[to_id(species)].evidence,
            )
            for species in options
        ),
    )


def _pending_presentation(
    ctx: SlotFillContext, presentation: SlotFillPresentation
) -> PendingPresentation:
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
        options.append(option)
    return {
        "schema_version": 1,
        "kind": "candidate_selection",
        "slot_index": presentation.slot_index,
        "options": options,
    }


def run_slot_fill_terminal(
    ctx: SlotFillContext,
    state: RecommenderState,
    *,
    slot_index: int,
    response: SlotFillResponse | None = None,
) -> SlotFillTerminalResult:
    presentation = present_candidates(ctx, slot_index=slot_index)
    pending = _pending_presentation(ctx, presentation)

    if response is None:
        if not pending["options"]:
            raise ValueError("cannot persist: no species resolved from presentation")
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


def build_provisional_slot(
    intent: PendingSlotIntent, state: RecommenderState
) -> ProvisionalSlot | UnresolvedSlotRefinement:
    """Refine a selected candidate without mutating the persisted team draft."""
    decision = intent.target_role_decision
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
        regulation=state.get("regulation_mod") or "champions",
    )
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
