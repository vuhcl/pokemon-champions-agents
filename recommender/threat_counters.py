"""query_threat_counters — depth-one counter-of-counters (ADR-022).

Orchestrates query_counters + classify_matchup; does not modify either.

# Docs flag (read-only): ADR-022 still says query_counter_of_counters and
# popularity-filter-to-3-5 before recurse; this tool uses full query_counters
# discovery then a separate usage-only top-N only for calc verification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from recommender.calc_client import CalcClient, PokemonSpecOptional
from recommender.counters import query_counters
from recommender.ids import to_id
from recommender.matchup import MatchupResult, classify_matchup
from recommender.ranking import rank_and_cut
from recommender.resolved_builds import get_resolved_build
from recommender.state import ThreatCandidate, ThreatCounterCandidate
from recommender.usage_data import featured_or_common_set

# Outcome dominates; severity scales within an outcome (existing MatchupResult fields).
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


def query_threat_counters(
    anchor: PokemonSpecOptional,
    *,
    n: int = 10,
    verify_threats_n: int = 5,
    client: CalcClient | None = None,
    candidate_pool: list[PokemonSpecOptional] | None = None,
) -> list[ThreatCounterCandidate]:
    """Candidates that counter the anchor's threats; final order from verified matchups.

    ``candidate_pool`` restricts teammate/candidate search (step 2+) only — never
    threat identification (step 1), which always uses the full unrestricted meta.
    """
    if not anchor.get("species"):
        return []

    anchor_id = to_id(anchor["species"])

    # --- 1. Full threat list (query_counters default n) — never pass candidate_pool ---
    threats = query_counters(anchor)
    if not threats:
        return []

    threats_by_id: dict[str, ThreatCandidate] = {}
    for t in threats:
        tid = _species_id(t)
        if tid and tid not in threats_by_id:
            threats_by_id[tid] = t

    # --- 2–3. Depth-one expand + merge (pool restricts candidates only) ---
    merged: dict[str, _Merged] = {}
    for threat in threats:
        tid = _species_id(threat)
        # Pass candidate_pool only when set so existing (pokemon, n=20) mocks stay valid.
        if candidate_pool is not None:
            cands = query_counters(threat.spec, candidate_pool=candidate_pool)
        else:
            cands = query_counters(threat.spec)
        for cand in cands:
            cid = _species_id(cand)
            if not cid or cid == anchor_id:
                continue
            row = merged.get(cid)
            if row is None:
                merged[cid] = _Merged(candidate=cand, threat_ids={tid})
            else:
                row.candidate = _better_usage(row.candidate, cand)
                row.threat_ids.add(tid)

    if not merged:
        return []

    pool = list(merged.values())

    # --- 4. Static cut: count primary, usage tiebreak ---
    static = rank_and_cut(
        pool,
        key=lambda m: (m.count, _usage_popularity(m.candidate)),
        n=n,
        tier=None,
        order="descending",
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
            )
        )

    return rank_and_cut(
        out_rows,
        key=lambda c: (c.verified_score, _usage_popularity(c.candidate)),
        n=len(out_rows),
        tier=None,
        order="descending",
    )
