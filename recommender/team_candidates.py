"""Team-level candidate collection and ranking for multi-locked rosters."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from recommender.anchor_roles import (
    AnchorRoleDecision,
    ResolvedAnchorBuild,
    classify_anchor_role,
    derive_role_shape_context,
    resolve_anchor_build,
)
from recommender.condition_resilience import (
    ConditionResilienceReport,
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
    from recommender.condition_resilience import provided_conditions, team_field_states

    # Filter out already-satisfied provider needs (trick_room/tailwind)
    # before candidate resolution -- confirmed live: Pelipper already
    # provides Tailwind via its own move, but Archaludon's "tailwind"
    # support need (a real, speed-tier-triggered need, not a generic
    # placeholder) was still being surfaced as unmet, feeding candidate
    # discovery for a condition the team already has. Only trick_room and
    # tailwind map to a TRACKED_CONDITIONS provider check this way --
    # other need categories (healing_cleric, screens, etc.) aren't
    # binary "provided or not" the same way, so they're unaffected here.
    already_provided = provided_conditions(anchor_contexts)
    _PROVIDER_NEED_CONDITION = {"trick_room": "Trick Room", "tailwind": "Tailwind"}
    anchored_needs = tuple(
        need
        for need in anchored_needs
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

    pf_report = assess_primary_function_resilience(locked)
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
        fills_missing, fills_spof_backup = _candidate_fills_condition_gap(
            decision,
            condition_resilience,
            candidate_build=build,
            locked=locked,
        )
        fills_pf_spof = _candidate_fills_primary_function_spof(
            decision, build, pf_report, locked
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
        out.append(
            replace(
                candidate,
                composition_fit=fit,
                fills_essential_gap=fills_missing,
                fills_spof_backup_gap=fills_spof_backup,
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
) -> tuple[bool, bool]:
    """Returns (fills_missing_provider_gap, fills_spof_backup_gap) --
    split rather than a single bool, so the caller (and _rank_key) can
    give these two genuinely different situations different ranking
    priority. missing_provider is a real, currently-unmet need and
    should always win top priority in ranking. single_provider_spof is
    real backup value (per the condition's own essential/preferred
    classification) established via build divergence from the existing
    provider -- confirmed by an existing test as a meaningful, legitimate
    signal on its own -- but confirmed live it must NOT compete for the
    SAME top-priority rank slot as a genuinely missing need, since a
    weak, low-confidence backup-only candidate was outranking strong,
    high-confidence, unrelated candidates entirely because the two cases
    were previously collapsed into one boolean.
    """
    if report is None:
        return False, False
    by_slot = _locked_by_slot(locked)
    fills_missing = False
    fills_spof_backup = False
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
    return fills_missing, fills_spof_backup


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
    scored = [
        (
            c,
            c.threat_row.verified_score if c.threat_row else 0.0,
            defensive_synergy_score(
                _species_types(snap, c.species), locked_types_list
            ),
        )
        for c in candidates
    ]
    verified_rank = {
        to_id(item[0].species): i
        for i, item in enumerate(sorted(scored, key=lambda x: -x[1]))
    }
    synergy_rank = {
        to_id(item[0].species): i
        for i, item in enumerate(sorted(scored, key=lambda x: -x[2]))
    }

    def sort_key(item: tuple[AnnotatedCandidate, float, float]):
        sid = to_id(item[0].species)
        return (
            verified_rank[sid] + synergy_rank[sid],
            _shared_teammate_tiebreak(item[0]),
        )

    return [item[0] for item in sorted(scored, key=sort_key)]


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
    candidates: list[AnnotatedCandidate], *, condition_beneficiary: bool = False
) -> list[AnnotatedCandidate]:
    """Categories B (support-needs) and C (condition-benefit) share the
    same ranking approach: best evidence quality (reusing the same
    _BASIS_RANK/_CONFIDENCE_RANK convention _rank_key already uses),
    shared-teammate correlation as the secondary tie-break. Scoped to
    the relevant category's own evidence via _need_branch_evidence, not
    the candidate's full evidence tuple.
    """
    def sort_key(c: AnnotatedCandidate):
        relevant = _need_branch_evidence(c, condition_beneficiary=condition_beneficiary)
        best = (
            max(
                (_BASIS_RANK[item.basis], _CONFIDENCE_RANK[item.confidence])
                for item in relevant
            )
            if relevant
            else (0, 0)
        )
        return (-best[0], -best[1], _shared_teammate_tiebreak(c))

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
        if need_categories - {"condition_beneficiary"}:
            category_b.append(c)
    return category_a, category_b, category_c


def rank_multi_locked_by_category(
    candidates: Sequence[AnnotatedCandidate],
    locked_contexts: Sequence[LockedAnchorContext],
    *,
    n_per_category: int = 10,
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
    ranked_b = _rank_by_need_evidence(category_b, condition_beneficiary=False)[
        :n_per_category
    ]
    ranked_c = _rank_by_need_evidence(category_c, condition_beneficiary=True)[
        :n_per_category
    ]

    seen: set[str] = set()
    combined: list[AnnotatedCandidate] = []
    for c in (*ranked_a, *ranked_b, *ranked_c):
        sid = to_id(c.species)
        if sid not in seen:
            seen.add(sid)
            combined.append(c)
    return combined


def select_diverse_candidates(
    candidates: Sequence[AnnotatedCandidate],
    locked_contexts: Sequence[LockedAnchorContext],
    *,
    n_alternatives: int = 2,
) -> dict[str, Any]:
    """Default + N alternatives via a multi-signal, per-category
    approach, replacing a single combined ranking for this specific
    selection step. Confirmed with Vu directly, following live evidence
    that a single ranking (even after fixing several real bugs in it)
    kept surfacing narrow, redundant, or context-blind candidate sets --
    e.g. three Steel-type picks that all individually looked reasonable
    but collectively piled onto the same shared weakness, or real
    teammates (a screens setter, a Rain-boosted sweeper) that never
    entered the top ranks because their real value lives outside what
    any single score can see.

    Three categories, each scored independently:
    - A: type-synergy + threat-counter breadth (_rank_category_a)
    - B: support-needs (screens, trick_room, healing_cleric, etc.)
    - C: condition-benefit (Rain-beneficiary, etc.)
    Shared-teammate correlation is the secondary tie-break within every
    category, not a separate global signal.

    Default: a genuine multi-category candidate (confirmed strong -- top
    3 -- in more than one category) if one exists, since that represents
    real, multi-dimensional value; otherwise falls back to Category A's
    top pick. Alternatives: the top pick from each of the OTHER
    categories, skipping to the next-best within a category if its top
    pick was already used as the default or as another alternative.

    Returns a "tracks" mapping (species -> human-readable label) alongside
    default/alternatives, surfacing which track each pick actually came
    from -- confirmed live this matters for real debugging (candidates
    that "feel like" they should be one category can genuinely be
    multi-category, e.g. a strong threat-counter that also happens to
    satisfy a support-need), not just future steering (explicitly scoped
    out of this change -- surfacing the track is the only thing
    implemented here, not acting on a request for "a different track").
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

    # Categories B/C are filtered to strong evidence (confidence != low)
    # immediately after ranking -- confirmed live, a real, deliberate
    # design decision, not just a multi-signal-detection nuance: if the
    # BEST available candidate for a category is only low confidence, it
    # should not be suggested as that category's candidate at all, not
    # even as a weak fallback. A weak, trigger=None match (e.g. an
    # unconditionally-generated need like screens) can still rank "top"
    # within its own category purely because many candidates for that
    # need share the same low floor -- that's not the same as being a
    # genuinely reliable pick. Other signals (shared-teammate,
    # threat-coverage, additional matching_needs) are only meant to rank
    # candidates WITHIN a real confidence tier, never to substitute for
    # one. If nothing in a category clears this bar, that category
    # simply contributes nothing here -- existing fallback logic below
    # (default falls through A -> B -> C; alternatives skip empty
    # categories naturally) already handles an empty category correctly.
    ranked_b = [
        c
        for c in _rank_by_need_evidence(category_b, condition_beneficiary=False)
        if _has_strong_evidence(c, condition_beneficiary=False)
    ]
    ranked_c = [
        c
        for c in _rank_by_need_evidence(category_c, condition_beneficiary=True)
        if _has_strong_evidence(c, condition_beneficiary=True)
    ]
    ranked_by_category = {"A": ranked_a, "B": ranked_b, "C": ranked_c}

    # Multi-category default: a candidate confirmed in the top-3 of more
    # than one category's own ranking represents real, multi-dimensional
    # value -- not just "happened to be top in one narrow signal".
    # Grouped by lineage, not exact species id, for the same reason the
    # alternatives dedup below is -- a mega/regional form shouldn't be
    # treated as a separate candidate from its base species here either.
    # B/C are already strong-evidence-only at this point (filtered
    # above), so no additional filtering is needed here.
    top3_lineages: dict[str, set[frozenset[str]]] = {
        "A": {frozenset(lineage_ids(c.species)) for c in ranked_a[:3]},
        "B": {frozenset(lineage_ids(c.species)) for c in ranked_b[:3]},
        "C": {frozenset(lineage_ids(c.species)) for c in ranked_c[:3]},
    }
    multi_signal_lineages: dict[frozenset[str], int] = {}
    for key, lineages in top3_lineages.items():
        for lineage in lineages:
            multi_signal_lineages[lineage] = multi_signal_lineages.get(lineage, 0) + 1
    genuine_multi_signal_lineages = {
        lineage for lineage, count in multi_signal_lineages.items() if count > 1
    }

    default: AnnotatedCandidate | None = None
    default_categories: list[str] = []
    if genuine_multi_signal_lineages:
        # Among genuine multi-signal candidates, prefer whichever ranks
        # best in Category A (the closest existing analog to "strongest
        # overall"), falling back to its rank in whichever category it's
        # strongest in otherwise.
        best_rank = None
        for lineage in genuine_multi_signal_lineages:
            for key, ranked in ranked_by_category.items():
                for i, c in enumerate(ranked):
                    if frozenset(lineage_ids(c.species)) == lineage:
                        candidate_rank = (i, key != "A")
                        if best_rank is None or candidate_rank < best_rank[0]:
                            best_rank = (candidate_rank, c)
        if best_rank is not None:
            default = best_rank[1]
            default_lineage = frozenset(lineage_ids(default.species))
            default_categories = [
                key
                for key, lineages in top3_lineages.items()
                if default_lineage in lineages
            ]
    if default is None and ranked_a:
        default = ranked_a[0]
        default_categories = ["A"]
    elif default is None and ranked_b:
        default = ranked_b[0]
        default_categories = ["B"]
    elif default is None and ranked_c:
        default = ranked_c[0]
        default_categories = ["C"]

    # Dedup by lineage, not exact species id -- confirmed live necessary:
    # a plain to_id() comparison doesn't catch a mega/regional-form
    # duplicate of the same underlying species (e.g. Abomasnow and
    # Abomasnow-Mega both getting selected as if they were genuinely
    # different alternatives, when they're the same Pokemon).
    used_lineages: set[str] = (
        set(lineage_ids(default.species)) if default is not None else set()
    )
    alternatives: list[AnnotatedCandidate] = []
    alternative_categories: list[str] = []
    for key, ranked in (("B", ranked_b), ("C", ranked_c), ("A", ranked_a)):
        if len(alternatives) >= n_alternatives:
            break
        for c in ranked:
            c_lineage = set(lineage_ids(c.species))
            if not (c_lineage & used_lineages):
                alternatives.append(c)
                alternative_categories.append(key)
                used_lineages |= c_lineage
                break

    tracks: dict[str, str] = {}
    category_keys: dict[str, list[str]] = {}
    if default is not None:
        tracks[default.species] = " + ".join(
            _TRACK_LABELS[key] for key in default_categories
        )
        category_keys[default.species] = default_categories
    for c, key in zip(alternatives, alternative_categories):
        tracks[c.species] = _TRACK_LABELS[key]
        category_keys[c.species] = [key]

    return {
        "default": default.species if default is not None else None,
        "alternatives": [c.species for c in alternatives[:n_alternatives]],
        "tracks": tracks,
        "category_keys": category_keys,
    }


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
