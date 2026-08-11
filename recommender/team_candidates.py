"""Team-level candidate collection and ranking for multi-locked rosters."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from recommender.anchor_roles import (
    classify_anchor_role,
    derive_role_shape_context,
    resolve_anchor_build,
)
from recommender.condition_resilience import (
    ConditionResilienceReport,
    gap_support_needs,
    mechanism_condition,
)
from recommender.ids import to_id
from recommender.legality import is_species_legal, load_snapshot
from recommender.ranking import OwnershipMode, rank_and_cut
from recommender.slot_fill import (
    AnnotatedCandidate,
    AnchoredSupportNeed,
    LockedAnchorContext,
    SlotFillContext,
    _kit_fallback_target_role,
    resolve_all_support_needs,
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
from recommender.support_needs import query_support_needs
from recommender.teammates import SharedTeammateQueryResult
from recommender.usage_data import featured_or_common_set, lineage_ids
from recommender.usage_spreads import move_category_counts

# Champions: only Eternal Flower Floette can Mega Evolve (not plain Floette).
_FLOETTE_DENY_SID = "floette"
_FLOETTE_ETERNAL_SID = "floetteeternal"
_FLOETTE_MEGA_SID = "floettemega"


def _is_mega_sid(species_id: str) -> bool:
    return species_id.endswith(("mega", "megax", "megay"))


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
    contexts: list[LockedAnchorContext] = []
    for slot_index, slot in enumerate(state["team_draft"]):
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
    rejected = {to_id(row["species"]) for row in state.get("rejected", [])}

    def eligible(species: str) -> bool:
        species_id = to_id(species)
        return bool(
            species_id
            and species_id not in locked_lineages
            and species_id not in rejected
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
    support_context = SlotFillContext(anchor=None, role_shape_context=None)
    support_rows = resolve_all_support_needs(
        support_context,
        state,
        anchored_needs=anchored_needs,
        available_species=owned_species,
        ownership_mode=ownership_mode,
    )
    for support in support_rows:
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
) -> list[AnnotatedCandidate]:
    regulation = state.get("regulation_mod") or "champions-reg-mb"
    locked = (
        tuple(locked_anchors)
        if locked_anchors is not None
        else collect_locked_anchor_contexts(state)
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
        fills_gap = _candidate_fills_condition_gap(decision, condition_resilience)
        if (
            candidate.anchored_needs
            or missing_primary
            or corrects_skew
            or fills_gap
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
        out.append(replace(candidate, composition_fit=fit))
    return out


def _candidate_fills_condition_gap(
    decision,
    report: ConditionResilienceReport | None,
) -> bool:
    if report is None:
        return False
    for row in report.conditions:
        if row.gap not in {"missing_provider", "single_provider_spof"}:
            continue
        if row.classification not in {"essential", "preferred"}:
            continue
        if any(
            mechanism.present
            and mechanism.relation == "provides"
            and mechanism_condition(mechanism) == row.condition
            for mechanism in decision.mechanisms
        ):
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
        best_evidence[0],
        best_evidence[1],
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
    )


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
