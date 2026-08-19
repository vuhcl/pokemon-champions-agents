"""query_threat_counters — depth-one counter-of-counters (ADR-022).

Orchestrates query_counters + classify_matchup; does not modify either.

# Docs flag (read-only): ADR-022 still says query_counter_of_counters and
# popularity-filter-to-3-5 before recurse; this tool uses full query_counters
# discovery then a separate usage-only top-N only for calc verification.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from recommender.calc_client import FieldSpec
    from recommender.slot_fill import LockedAnchorContext

from recommender.calc_client import CalcClient, CalcClientError, PokemonSpecOptional
from recommender.counters import query_counters
from recommender.ids import to_id
from recommender.matchup import MatchupEvidenceError, MatchupResult, classify_matchup
from recommender.ranking import OwnershipMode, rank_and_cut
from recommender.resolved_builds import get_resolved_build
from recommender.state import (
    CandidateDiscoveryError,
    TeamThreatDiscovery,
    TeamThreatObjectiveRow,
    ThreatCandidate,
    ThreatCounterCandidate,
)
from recommender.usage_data import featured_or_common_set

# Caller-local scalar: outcome and severity multipliers trade off; this is not a
# repository-wide lexicographic precedence policy.
_OUTCOME_POINTS: dict[str, float] = {
    "clean_kill": 4.0,
    "intentional_non_ko_answer": 2.0,
    "conditionally_dependent_answer": 1.0,
    "no_answer": 0.0,
}
_SEVERITY_POINTS: dict[str, float] = {
    "decisive": 1.0,
    "costly": 0.5,
    "toss-up": 0.25,
}

_DEFAULT_REGULATION = "champions-reg-mb"


@dataclass
class _Merged:
    candidate: ThreatCandidate
    threat_ids: set[str] = field(default_factory=set)

    @property
    def count(self) -> int:
        return len(self.threat_ids)


def pair_score(result: MatchupResult) -> float:
    """Severity-weighted outcome points for one classify_matchup result."""
    return _OUTCOME_POINTS.get(result.outcome, 0.0) * _SEVERITY_POINTS.get(
        result.severity, 0.0
    )


def aggregate_verified(results: list[MatchupResult]) -> float:
    return sum(pair_score(r) for r in results)


def _species_id(tc: ThreatCandidate) -> str:
    return to_id(tc.spec.get("species") or tc.form or tc.ladder_species)


def _usage_popularity(tc: ThreatCandidate) -> float:
    if tc.usage_rank is not None:
        return -float(tc.usage_rank)
    return float("-inf")


def _better_usage(a: ThreatCandidate, b: ThreatCandidate) -> ThreatCandidate:
    """Prefer lower ordinal usage_rank; None loses."""
    if a.usage_rank is None:
        return b
    if b.usage_rank is None:
        return a
    return a if a.usage_rank <= b.usage_rank else b


def _set_to_spec(s: dict[str, Any], species: str) -> PokemonSpecOptional:
    out: PokemonSpecOptional = {"species": s.get("species") or species}
    if s.get("item"):
        out["item"] = str(s["item"])
    if s.get("ability"):
        out["ability"] = str(s["ability"])
    if s.get("nature"):
        out["nature"] = str(s["nature"])
    if s.get("moves"):
        out["moves"] = list(s["moves"])
    if s.get("evs"):
        out["evs"] = dict(s["evs"])  # type: ignore[typeddict-item]
    if s.get("level") is not None:
        out["level"] = int(s["level"])
    return out


def _most_common_verify_spec(
    species: str, *, regulation: str = _DEFAULT_REGULATION
) -> PokemonSpecOptional:
    """Single most-common build for classify_matchup (ADR-023a gap 6).

    Usage set first; tier-1 resolved-build cache for spread when present;
    cache miss falls through to usage-sourced spec (propose's tier-1→tier-2 pattern).
    One build per species — never every cached variant.
    """
    usage = featured_or_common_set(species, regulation=regulation)
    if not usage:
        return {"species": species}
    spec = _set_to_spec(usage, species)
    moves = list(usage.get("moves") or [])
    item = usage.get("item")
    if moves and item:
        cached = get_resolved_build(species, moves, str(item), regulation)
        if cached and cached.get("spread"):
            spec["evs"] = dict(cached["spread"])  # type: ignore[typeddict-item]
    return spec


def _collect_candidates(
    threats: Sequence[ThreatCandidate],
    *,
    candidate_pool: list[PokemonSpecOptional] | None,
    available_pool: list[str] | None,
    ownership_mode: OwnershipMode,
    excluded_species: Collection[str],
) -> tuple[dict[str, _Merged], dict[str, ThreatCandidate]]:
    excluded = {to_id(species) for species in excluded_species}
    threats_by_id: dict[str, ThreatCandidate] = {}
    merged: dict[str, _Merged] = {}
    for threat in threats:
        tid = _species_id(threat)
        if not tid:
            continue
        threats_by_id.setdefault(tid, threat)
        kwargs: dict[str, Any] = {}
        if candidate_pool is not None:
            kwargs["candidate_pool"] = candidate_pool
        if ownership_mode != "off":
            kwargs["available_pool"] = available_pool
            kwargs["ownership_mode"] = ownership_mode
        for candidate in query_counters(threat.spec, **kwargs):
            cid = _species_id(candidate)
            if not cid or cid in excluded:
                continue
            row = merged.get(cid)
            if row is None:
                merged[cid] = _Merged(candidate=candidate, threat_ids={tid})
            else:
                row.candidate = _better_usage(row.candidate, candidate)
                row.threat_ids.add(tid)
    return merged, threats_by_id


def _static_cut(
    merged: dict[str, _Merged],
    *,
    n: int,
    available_pool: list[str] | None,
    ownership_mode: OwnershipMode,
) -> list[_Merged]:
    owned = {sid for species in available_pool or [] if (sid := to_id(species))}
    return rank_and_cut(
        list(merged.values()),
        key=lambda row: (row.count, _usage_popularity(row.candidate)),
        n=n,
        tier=None,
        order="descending",
        ownership_mode=ownership_mode,
        is_owned=lambda row: _species_id(row.candidate) in owned,
    )


def _static_threat_rows(static: list[_Merged]) -> tuple[ThreatCounterCandidate, ...]:
    return tuple(
        ThreatCounterCandidate(
            candidate=row.candidate,
            threats_countered=tuple(sorted(row.threat_ids)),
            threats_countered_count=row.count,
            verified_score=0.0,
            verified_vs=(),
            estimate_kind="static",
        )
        for row in static
    )


def query_threat_counters(
    anchor: PokemonSpecOptional,
    *,
    n: int = 10,
    verify_threats_n: int = 5,
    client: CalcClient | None = None,
    candidate_pool: list[PokemonSpecOptional] | None = None,
    available_pool: list[str] | None = None,
    ownership_mode: OwnershipMode = "off",
) -> TeamThreatDiscovery:
    """Candidates that counter the anchor's threats; final order from verified matchups.

    ``candidate_pool`` restricts teammate/candidate search (step 2+) only — never
    threat identification (step 1), which always uses the full unrestricted meta.
    Ownership follows the same candidate-side-only boundary.

    On calc failure returns ``status="degraded"`` with static type-effectiveness
    discovery rows (from ``query_counters`` / ``_static_cut``), not verified
    matchups. Weather/terrain are not passed into static type rewrites today —
    Weather Ball / Terrain Pulse stay base-typed under that ceiling.
    """
    if not anchor.get("species"):
        return TeamThreatDiscovery(status="available", candidates=())

    # --- 1. Full threat list (query_counters default n) — never pass candidate_pool ---
    threats = query_counters(anchor)
    if not threats:
        return TeamThreatDiscovery(status="available", candidates=())

    # --- 2–3. Depth-one expand + merge (pool restricts candidates only) ---
    merged, threats_by_id = _collect_candidates(
        threats,
        candidate_pool=candidate_pool,
        available_pool=available_pool,
        ownership_mode=ownership_mode,
        excluded_species=(str(anchor["species"]),),
    )
    if not merged:
        return TeamThreatDiscovery(status="available", candidates=())

    # --- 4. Static cut: count primary, usage tiebreak ---
    static = _static_cut(
        merged,
        n=n,
        available_pool=available_pool,
        ownership_mode=ownership_mode,
    )

    # --- 5. Usage-only re-select of verification threats (independent ranking) ---
    verify_threats = rank_and_cut(
        threats,
        key=_usage_popularity,
        n=verify_threats_n,
        tier=None,
        order="descending",
    )
    verify_ids = {_species_id(t) for t in verify_threats}

    # --- 6. classify_matchup on credited ∩ verify set; verified score is real rank ---
    try:
        out_rows: list[ThreatCounterCandidate] = []
        for m in static:
            verified: list[tuple[str, MatchupResult]] = []
            cand_species = (
                m.candidate.spec.get("species")
                or m.candidate.form
                or m.candidate.ladder_species
            )
            cand_spec = _most_common_verify_spec(cand_species)
            for tid in sorted(m.threat_ids):
                if tid not in verify_ids:
                    continue
                threat = threats_by_id.get(tid)
                if threat is None:
                    continue
                threat_species = (
                    threat.spec.get("species") or threat.form or threat.ladder_species
                )
                threat_spec = _most_common_verify_spec(threat_species)
                result = classify_matchup(cand_spec, threat_spec, None, client=client)
                verified.append((tid, result))
            score = aggregate_verified([r for _, r in verified])
            out_rows.append(
                ThreatCounterCandidate(
                    candidate=m.candidate,
                    threats_countered=tuple(sorted(m.threat_ids)),
                    threats_countered_count=m.count,
                    verified_score=score,
                    verified_vs=tuple(verified),
                    estimate_kind="verified",
                )
            )

        owned = {sid for species in available_pool or [] if (sid := to_id(species))}
        ranked = rank_and_cut(
            out_rows,
            key=lambda c: (c.verified_score, _usage_popularity(c.candidate)),
            n=len(out_rows),
            tier=None,
            order="descending",
            ownership_mode=ownership_mode,
            is_owned=lambda c: _species_id(c.candidate) in owned,
        )
        return TeamThreatDiscovery(status="available", candidates=tuple(ranked))
    except (CalcClientError, MatchupEvidenceError) as exc:
        return TeamThreatDiscovery(
            status="degraded",
            candidates=_static_threat_rows(static),
            error=CandidateDiscoveryError(
                kind=(
                    "calc_unavailable"
                    if isinstance(exc, CalcClientError)
                    else "calc_incomplete"
                ),
                stage="candidate_verification",
                message=str(exc),
                retryable=True,
                exception_type=type(exc).__name__,
                status_code=exc.status if isinstance(exc, CalcClientError) else None,
            ),
        )


def _best_matchup_with_forced_fields(
    candidate_spec: PokemonSpecOptional,
    threat_spec: PokemonSpecOptional,
    forced_fields: Sequence["FieldSpec"],
    *,
    client: CalcClient | None,
) -> MatchupResult:
    """Always checks every real, achievable field state and returns
    whichever produces the best result -- not just as a fallback when
    neutral fails outright. Same underlying question as
    coverage.compute_team_coverage's forced-field fallback (does X
    answer threat Y, accounting for the team's real locked conditions),
    but that pattern alone isn't sufficient here: it only short-circuits
    "unanswered -> answered" transitions, not "already answered, but the
    real field state makes it meaningfully safer" ones.

    Real, confirmed gap found live, not hypothetical: a Steel-type
    candidate that already "answers" a Fire-type threat neutrally (e.g.
    surviving via bulk despite Steel's real 2x Fire weakness) but only
    at "costly" severity would never have been re-evaluated under Rain,
    even though Rain halving Fire's power would clearly make that
    matchup safer -- severity, not just outcome type, feeds directly
    into the actual ranking score via pair_score/aggregate_verified, so
    this is a real ranking-correctness gap, not just cosmetic. Compares
    by pair_score (weighs both outcome and severity) rather than
    coverage.py's _better_outcome (outcome only, blind to severity
    differences within the same outcome) -- that comparison is correct
    for compute_team_coverage's different question (which of several
    TEAM MEMBERS best answers a threat) but not precise enough for this
    one (which of several FIELD STATES for the SAME candidate is best).

    Skips the forced-field check only when neutral is already the
    absolute ceiling (clean_kill + decisive, pair_score 4.0) -- nothing
    can improve on that, confirmed directly against the real point
    tables (_OUTCOME_POINTS/_SEVERITY_POINTS) before relying on it.

    Root-cause fix for the original confirmed live bug too: this
    function's calls to classify_matchup previously always passed
    field=None, meaning every threat-coverage evaluation was blind to
    the team's actual locked weather/Tailwind/Trick Room -- a Fire-type
    candidate on a Rain team got evaluated as if it weren't raining, and
    a Water-type candidate's real Rain-boosted offense was never
    credited.
    """
    neutral = classify_matchup(candidate_spec, threat_spec, None, client=client)
    if not forced_fields or (
        neutral.outcome == "clean_kill" and neutral.severity == "decisive"
    ):
        return neutral
    best = neutral
    best_score = pair_score(neutral)
    for forced_field in forced_fields:
        r = classify_matchup(candidate_spec, threat_spec, forced_field, client=client)
        score = pair_score(r)
        if score > best_score:
            best = r
            best_score = score
    return best


def query_candidates_for_threats(
    objective: Sequence[TeamThreatObjectiveRow],
    *,
    n: int = 20,
    client: CalcClient | None = None,
    candidate_pool: list[PokemonSpecOptional] | None = None,
    available_pool: list[str] | None = None,
    ownership_mode: OwnershipMode = "off",
    excluded_species: Collection[str] = (),
    locked_contexts: Sequence["LockedAnchorContext"] = (),
    exclude_slot: int | None = None,
) -> TeamThreatDiscovery:
    """Discover once per team objective, then verify every admitted candidate."""
    if not objective:
        return TeamThreatDiscovery(status="available", candidates=())

    threats = tuple(row.threat for row in objective)
    merged, threats_by_id = _collect_candidates(
        threats,
        candidate_pool=candidate_pool,
        available_pool=available_pool,
        ownership_mode=ownership_mode,
        excluded_species=excluded_species,
    )
    if not merged:
        return TeamThreatDiscovery(status="available", candidates=())

    static = _static_cut(
        merged,
        n=n,
        available_pool=available_pool,
        ownership_mode=ownership_mode,
    )
    objective_ids = sorted(threats_by_id)
    from recommender.condition_resilience import team_field_states

    forced_fields = team_field_states(locked_contexts, exclude_slot=exclude_slot)
    try:
        rows: list[ThreatCounterCandidate] = []
        for merged_row in static:
            species = (
                merged_row.candidate.spec.get("species")
                or merged_row.candidate.form
                or merged_row.candidate.ladder_species
            )
            candidate_spec = _most_common_verify_spec(species)
            verified: list[tuple[str, MatchupResult]] = []
            for threat_id in objective_ids:
                threat = threats_by_id[threat_id]
                threat_species = (
                    threat.spec.get("species")
                    or threat.form
                    or threat.ladder_species
                )
                verified.append(
                    (
                        threat_id,
                        _best_matchup_with_forced_fields(
                            candidate_spec,
                            _most_common_verify_spec(threat_species),
                            forced_fields,
                            client=client,
                        ),
                    )
                )
            rows.append(
                ThreatCounterCandidate(
                    candidate=merged_row.candidate,
                    threats_countered=tuple(sorted(merged_row.threat_ids)),
                    threats_countered_count=merged_row.count,
                    verified_score=aggregate_verified(
                        [result for _, result in verified]
                    ),
                    verified_vs=tuple(verified),
                    estimate_kind="verified",
                )
            )
        return TeamThreatDiscovery(status="available", candidates=tuple(rows))
    except (CalcClientError, MatchupEvidenceError) as exc:
        return TeamThreatDiscovery(
            status="unavailable",
            candidates=(),
            error=CandidateDiscoveryError(
                kind=(
                    "calc_unavailable"
                    if isinstance(exc, CalcClientError)
                    else "calc_incomplete"
                ),
                stage="candidate_verification",
                message=str(exc),
                retryable=True,
                exception_type=type(exc).__name__,
                status_code=exc.status if isinstance(exc, CalcClientError) else None,
            ),
        )
