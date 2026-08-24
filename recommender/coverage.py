"""Team-wide threat coverage and SPOF detection (ADR-015 gaps #7/#8)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from recommender.calc_client import CalcClient, FieldSpec, PokemonSpecOptional
from recommender.ids import to_id
from recommender.matchup import MatchupResult, Severity, classify_matchup

if TYPE_CHECKING:
    from recommender.slot_fill import LockedAnchorContext
from recommender.ranking import rank_and_cut
from recommender.state import (
    Attr,
    RecommenderState,
    Slot,
    SPOFFinding,
    ThreatCandidate,
    ThreatCoverageResult,
)
from recommender.usage_data import (
    TEAM_THREAT_N,
    SLOT_THREAT_N,
    featured_or_common_set,
    ingame_species_map,
    lineage_ids,
    set_from_ingame,
    set_from_showdown,
    showdown_species_map,
)

# Reuse WEATHER_SETTERS / TERRAIN_SETTERS keys; map ability → FieldSpec values.
ABILITY_TO_FIELD: dict[str, FieldSpec] = {
    "drizzle": {"weather": "Rain", "gameType": "Doubles"},
    "drought": {"weather": "Sun", "gameType": "Doubles"},
    "sandstream": {"weather": "Sand", "gameType": "Doubles"},
    "snowwarning": {"weather": "Snow", "gameType": "Doubles"},
    "orichalcumpulse": {"weather": "Sun", "gameType": "Doubles"},
    "desolateland": {"weather": "Harsh Sunshine", "gameType": "Doubles"},
    "primordialsea": {"weather": "Heavy Rain", "gameType": "Doubles"},
    "deltastream": {"weather": "Strong Winds", "gameType": "Doubles"},
    "electricsurge": {"terrain": "Electric", "gameType": "Doubles"},
    "grassysurge": {"terrain": "Grassy", "gameType": "Doubles"},
    "psychicsurge": {"terrain": "Psychic", "gameType": "Doubles"},
    "mistysurge": {"terrain": "Misty", "gameType": "Doubles"},
    "hadronengine": {"terrain": "Electric", "gameType": "Doubles"},
}

_NEUTRAL_COVER = frozenset({"clean_kill", "intentional_non_ko_answer"})
_OUTCOME_RANK = {"clean_kill": 2, "intentional_non_ko_answer": 1}


def _set_to_spec(s: dict[str, Any]) -> PokemonSpecOptional:
    out: PokemonSpecOptional = {"species": s["species"]}
    if s.get("item"):
        out["item"] = s["item"]
    if s.get("ability"):
        out["ability"] = s["ability"]
    if s.get("nature"):
        out["nature"] = s["nature"]
    if s.get("moves"):
        out["moves"] = list(s["moves"])
    if s.get("evs"):
        out["evs"] = dict(s["evs"])  # type: ignore[typeddict-item]
    if s.get("level") is not None:
        out["level"] = s["level"]
    return out


def _showdown_formes(
    lineage: list[str], sd: dict[str, Any]
) -> tuple[tuple[str, float], ...]:
    out: list[tuple[str, float]] = []
    for sid in lineage:
        ent = sd.get(sid)
        if not ent:
            continue
        pct = ent.get("usage_pct")
        name = ent.get("name") or sid
        out.append((name, float(pct) if pct is not None else 0.0))
    return tuple(out)


def _candidate_from_set(
    *,
    ladder_species: str,
    usage_rank: int | None,
    form: str,
    showdown_usage_pct: float | None,
    showdown_formes: tuple[tuple[str, float], ...],
    poke_set: dict[str, Any],
    build_source: str,
) -> ThreatCandidate:
    return ThreatCandidate(
        ladder_species=ladder_species,
        usage_rank=usage_rank,
        form=form,
        showdown_usage_pct=showdown_usage_pct,
        showdown_formes=showdown_formes,
        spec=_set_to_spec(poke_set),
        build_source=build_source,
    )


def _expand_ladder_species(
    sid: str,
    entry: dict[str, Any],
    *,
    regulation: str,
    sd: dict[str, Any],
) -> list[ThreatCandidate]:
    ladder_name = entry.get("name") or sid
    rank = entry.get("usage_rank")
    rank_i = int(rank) if rank is not None else None
    lineage = lineage_ids(sid)
    hits = [lid for lid in lineage if lid in sd]
    # Child usage keys already name a forme. Do not steal the base's Showdown
    # row (or emit siblings) under this ladder_species.
    if sid != lineage[0]:
        hits = [sid] if sid in sd else []
    formes = _showdown_formes(lineage, sd)

    if len(hits) >= 2:
        # Multi-form: Showdown builds only — never mix in-game.
        donor: dict[str, Any] | None = None
        for lid in hits:
            donor = set_from_showdown(lid, regulation=regulation)
            if donor:
                break
        out: list[ThreatCandidate] = []
        for lid in hits:
            sd_ent = sd[lid]
            form_name = sd_ent.get("name") or lid
            pct = sd_ent.get("usage_pct")
            pct_f = float(pct) if pct is not None else None
            poke = set_from_showdown(lid, regulation=regulation)
            if poke:
                out.append(
                    _candidate_from_set(
                        ladder_species=ladder_name,
                        usage_rank=rank_i,
                        form=form_name,
                        showdown_usage_pct=pct_f,
                        showdown_formes=formes,
                        poke_set=poke,
                        build_source="showdown_form",
                    )
                )
                continue
            if not donor:
                continue
            # Same sibling build, stamped as this forme name.
            patched = dict(donor)
            patched["species"] = form_name
            out.append(
                _candidate_from_set(
                    ladder_species=ladder_name,
                    usage_rank=rank_i,
                    form=form_name,
                    showdown_usage_pct=pct_f,
                    showdown_formes=formes,
                    poke_set=patched,
                    build_source="showdown_partial_fallback",
                )
            )
        return out

    if len(hits) == 1:
        lid = hits[0]
        sd_ent = sd[lid]
        form_name = sd_ent.get("name") or lid
        pct = sd_ent.get("usage_pct")
        pct_f = float(pct) if pct is not None else None
        sd_set = set_from_showdown(lid, regulation=regulation)
        if sd_set:
            return [
                _candidate_from_set(
                    ladder_species=ladder_name,
                    usage_rank=rank_i,
                    form=form_name,
                    showdown_usage_pct=pct_f,
                    showdown_formes=formes,
                    poke_set=sd_set,
                    build_source="showdown_form",
                )
            ]
        poke = set_from_ingame(sid, regulation=regulation)
        if not poke:
            return []
        return [
            _candidate_from_set(
                ladder_species=ladder_name,
                usage_rank=rank_i,
                form=ladder_name,
                showdown_usage_pct=pct_f,
                showdown_formes=formes,
                poke_set=poke,
                build_source="ingame",
            )
        ]

    poke = set_from_ingame(sid, regulation=regulation)
    if not poke:
        return []
    return [
        _candidate_from_set(
            ladder_species=ladder_name,
            usage_rank=rank_i,
            form=ladder_name,
            showdown_usage_pct=None,
            showdown_formes=formes,
            poke_set=poke,
            build_source="ingame",
        )
    ]


def _slot_to_spec(slot: Slot, *, regulation: str = "champions") -> PokemonSpecOptional | None:
    species = slot.species.value
    if not species:
        return None
    spec: PokemonSpecOptional = {"species": species}
    if slot.ability.value:
        spec["ability"] = slot.ability.value
    if slot.item.value:
        spec["item"] = slot.item.value
    if slot.moveset.value:
        spec["moves"] = list(slot.moveset.value)
    if slot.spread.value:
        spec["evs"] = dict(slot.spread.value)  # type: ignore[typeddict-item]

    need_ability = "ability" not in spec
    need_item = "item" not in spec
    need_moves = "moves" not in spec
    need_evs = "evs" not in spec
    if need_ability or need_item or need_moves or need_evs:
        filled = featured_or_common_set(species, regulation=regulation)
        if filled:
            if need_ability and filled.get("ability"):
                spec["ability"] = filled["ability"]
            if need_item and filled.get("item"):
                spec["item"] = filled["item"]
            if need_moves and filled.get("moves"):
                spec["moves"] = list(filled["moves"])
            if need_evs and filled.get("evs"):
                spec["evs"] = dict(filled["evs"])  # type: ignore[typeddict-item]
    return spec



def _better_outcome(a: MatchupResult, b: MatchupResult | None) -> MatchupResult:
    if b is None:
        return a
    ra = _OUTCOME_RANK.get(a.outcome, 0)
    rb = _OUTCOME_RANK.get(b.outcome, 0)
    return a if ra >= rb else b


def _threat_usage_rank_key(entry: dict[str, Any]) -> tuple:
    """Ordinal usage_rank: lower rank number = more popular (ascending)."""
    return (entry.get("usage_rank") is None, entry.get("usage_rank") or 10**9)


def get_relevant_threats(
    state: RecommenderState,
    n: int | None = None,
    relevance_filter: Callable[[PokemonSpecOptional], bool] | None = None,
) -> list[ThreatCandidate]:
    """Top-n in-game ladder species, expanded to Showdown formes when multi-form.

    ``n`` counts ladder species that survive expand+filter (return length may exceed
    ``n`` due to forme expand). Defaults: TEAM_THREAT_N (50) without filter;
    SLOT_THREAT_N (10) with filter.
    """
    regulation = state.get("regulation_mod") or "champions"
    if n is None:
        n = SLOT_THREAT_N if relevance_filter is not None else TEAM_THREAT_N

    ig = ingame_species_map(regulation)
    sd = showdown_species_map(regulation)
    # Expand+filter first so empty survivors do not consume n; rank ordinal ascending.
    survivors: list[tuple[str, dict[str, Any], list[ThreatCandidate]]] = []
    for sid, entry in ig.items():
        cands = _expand_ladder_species(sid, entry, regulation=regulation, sd=sd)
        if relevance_filter is not None:
            cands = [c for c in cands if relevance_filter(c.spec)]
        if cands:
            survivors.append((sid, entry, cands))

    ranked = rank_and_cut(
        survivors,
        key=lambda row: _threat_usage_rank_key(row[1]),
        n=n,
        tier=None,
        slack=-1,
        order="ascending",
    )
    return [c for _, _, cands in ranked for c in cands]


def compute_team_coverage(
    team_draft: list[Slot],
    threats: list[PokemonSpecOptional],
    client: CalcClient | None = None,
    *,
    exclude_slot: int | None = None,
    exclude_slots: frozenset[int] = frozenset(),
    regulation: str = "champions",
    locked_contexts: "Sequence[LockedAnchorContext]" = (),
) -> list[ThreatCoverageResult]:
    """`locked_contexts` (from collect_locked_anchor_contexts) supplies the
    team's real, achievable field states (weather/Tailwind/Trick Room,
    both ability- and move-based providers) via
    condition_resilience.team_field_states -- replaces the older,
    ability-only _forced_fields_from_draft this function used to call
    directly, which could never detect Tailwind at all (there is no
    Tailwind-setting ability). Defaults to empty (no known field
    providers) rather than silently falling back to the old, narrower
    behavior -- callers that care about field-awareness must supply real
    contexts explicitly.
    """
    if not threats:
        return []

    from recommender.condition_resilience import team_field_states

    skip = set(exclude_slots)
    if exclude_slot is not None:
        skip.add(exclude_slot)
    forced_fields = team_field_states(
        locked_contexts, exclude_slot=exclude_slot, exclude_slots=exclude_slots
    )
    results: list[ThreatCoverageResult] = []

    for threat in threats:
        covering: list[int] = []
        best: MatchupResult | None = None
        any_result: MatchupResult | None = None
        forced_field: FieldSpec | None = None


        for i, slot in enumerate(team_draft):
            if i in skip:
                continue
            spec = _slot_to_spec(slot, regulation=regulation)
            if not spec:
                continue
            r = classify_matchup(spec, threat, None, client=client)
            any_result = r
            if r.outcome in _NEUTRAL_COVER:
                covering.append(i)
                best = _better_outcome(r, best)

        if covering:
            assert best is not None
            results.append(
                ThreatCoverageResult(
                    threat=threat,
                    best_outcome=best,
                    covering_slot_indices=covering,
                    forced_field=None,
                    flagged=best.outcome == "conditionally_dependent_answer",
                )
            )
            continue

        for field in forced_fields:
            field_covering: list[int] = []
            field_best: MatchupResult | None = None
            for i, slot in enumerate(team_draft):
                if exclude_slot is not None and i == exclude_slot:
                    continue
                spec = _slot_to_spec(slot, regulation=regulation)
                if not spec:
                    continue
                r = classify_matchup(spec, threat, field, client=client)
                any_result = r
                if r.outcome != "no_answer":
                    field_covering.append(i)
                    field_best = _better_outcome(r, field_best)
            if field_covering and field_best is not None:
                covering = field_covering
                best = field_best
                forced_field = field
                break

        if covering and best is not None:
            results.append(
                ThreatCoverageResult(
                    threat=threat,
                    best_outcome=best,
                    covering_slot_indices=covering,
                    forced_field=forced_field,
                    flagged=best.outcome == "conditionally_dependent_answer",
                )
            )
            continue

        gap = any_result or MatchupResult(outcome="no_answer", severity="toss-up")
        results.append(
            ThreatCoverageResult(
                threat=threat,
                best_outcome=gap,
                covering_slot_indices=[],
                forced_field=None,
                flagged=False,
            )
        )

    return results


def detect_spof(
    team_draft: list[Slot],
    threats: list[PokemonSpecOptional],
    client: CalcClient | None = None,
    *,
    regulation: str = "champions",
    locked_contexts: "Sequence[LockedAnchorContext]" = (),
) -> list[SPOFFinding]:
    baseline = compute_team_coverage(
        team_draft, threats, client, regulation=regulation, locked_contexts=locked_contexts
    )
    by_slot: dict[int, tuple[list[PokemonSpecOptional], dict[str, Severity]]] = {}

    for i, slot in enumerate(team_draft):
        if not slot.species.value:
            continue
        minus = compute_team_coverage(
            team_draft,
            threats,
            client,
            exclude_slot=i,
            regulation=regulation,
            locked_contexts=locked_contexts,
        )
        for base, without in zip(baseline, minus):
            if base.best_outcome.outcome == "no_answer":
                continue
            if without.best_outcome.outcome != "no_answer":
                continue
            if base.covering_slot_indices != [i]:
                continue
            lost, severities = by_slot.setdefault(i, ([], {}))
            lost.append(base.threat)
            sid = to_id(base.threat["species"])
            severities[sid] = base.best_outcome.severity

    return [
        SPOFFinding(slot_index=i, threats_lost=lost, threat_severity=severities)
        for i, (lost, severities) in sorted(by_slot.items())
    ]


def spec_to_slot(spec: PokemonSpecOptional) -> Slot:
    """Inverse of _slot_to_spec -- builds a real Slot from a spec dict, for
    candidates that don't have one yet (they're not locked). Needed
    because compute_team_coverage/detect_spof take list[Slot], not specs,
    so evaluating a hypothetical hybrid subset (locked slots + a not-yet-
    locked candidate) requires a real Slot for the candidate too.
    """
    return Slot(
        species=Attr(value=spec.get("species")),
        ability=Attr(value=spec.get("ability")),
        item=Attr(value=spec.get("item")),
        moveset=Attr(value=list(spec["moves"]) if spec.get("moves") else None),
        spread=Attr(value=dict(spec["evs"]) if spec.get("evs") else None),
    )


def _reindexed_subset(
    team_draft: list[Slot],
    locked_contexts: Sequence["LockedAnchorContext"],
    subset_indices: Sequence[int],
) -> tuple[list[Slot], tuple["LockedAnchorContext", ...]]:
    """Builds a synthetic team_draft containing only subset_indices,
    re-indexed to their new positions -- compute_team_coverage/detect_spof
    report covering_slot_indices/slot_index against team_draft's own
    positions, so a filtered-but-not-reindexed list would misattribute
    coverage to the wrong (original) slot number.
    """
    ordered = list(subset_indices)
    draft = [team_draft[i] for i in ordered]
    old_to_new = {old: new for new, old in enumerate(ordered)}
    contexts = tuple(
        replace(ctx, slot_index=old_to_new[ctx.slot_index])
        for ctx in locked_contexts
        if ctx.slot_index in old_to_new
    )
    return draft, contexts


def subset_gap_counts(
    team_draft: list[Slot],
    locked_contexts: Sequence["LockedAnchorContext"],
    subset_indices: Sequence[int],
    threats: list[PokemonSpecOptional],
    client: CalcClient | None = None,
    *,
    regulation: str = "champions",
) -> tuple[int, int]:
    """(uncovered_count, spof_count) for exactly this subset of team_draft
    positions -- the real quality metric a specific 4-of-N bring would
    have against the given threats. Lower is better on both; callers
    compare subsets by this tuple, not a single combined score, since
    collapsing "uncovered" and "spof" into one number would obscure which
    kind of gap actually remains (a real product/design choice deferred
    to whoever consumes this, not resolved here).

    Deliberately does not weight by threat severity -- MatchupResult's
    severity field is always "toss-up" for a genuine no_answer outcome
    (a placeholder, not a real signal), so severity-weighting the
    "uncovered" bucket from coverage results alone would be spurious.
    A real severity-aware version would need the threat objective's own
    baseline severity classification (TeamThreatObjectiveRow), not
    something this function has access to -- left as a known,
    undertaken refinement, not attempted here.
    """
    draft, contexts = _reindexed_subset(team_draft, locked_contexts, subset_indices)
    coverage = compute_team_coverage(
        draft, threats, client, regulation=regulation, locked_contexts=contexts
    )
    spofs = detect_spof(
        draft, threats, client, regulation=regulation, locked_contexts=contexts
    )
    uncovered = sum(1 for row in coverage if row.best_outcome.outcome == "no_answer")
    return uncovered, len(spofs)


def best_achievable_gap_counts(
    team_draft: list[Slot],
    locked_contexts: Sequence["LockedAnchorContext"],
    available_indices: Sequence[int],
    pick_count: int,
    threats: list[PokemonSpecOptional],
    client: CalcClient | None = None,
    *,
    regulation: str = "champions",
) -> tuple[int, int]:
    """The best (fewest uncovered, then fewest spof) gap counts achievable
    from ANY pick_count-sized combination of available_indices -- e.g.
    "the best real bring-4 this roster can produce," not "does the full
    roster together cover everything." No plausibility filter on which
    combinations count -- confirmed directly in conversation: almost any
    coherent combination of real picks is somebody's legitimate answer to
    some real matchup, so there's no principled way to exclude one ahead
    of time. Cost is combinatorial (C(len(available_indices), pick_count))
    but cheap at the roster sizes this format actually has (N<=6); the
    real cost driver is calc calls, and classify_matchup's own per-pair
    memoization means the same pairwise matchup is reused across however
    many subsets happen to share it, not recomputed per-subset.
    """
    from itertools import combinations

    if len(available_indices) < pick_count:
        # Can't form a full bring yet -- e.g. only 2 locked and picking a
        # 3rd with pick_count=4. No real "best 4" exists; caller should
        # treat this as "no baseline to compare against" rather than a
        # real (0, 0) or worst-case answer.
        raise ValueError(
            f"need at least {pick_count} available_indices, got {len(available_indices)}"
        )
    best: tuple[int, int] | None = None
    for subset in combinations(available_indices, pick_count):
        counts = subset_gap_counts(
            team_draft, locked_contexts, subset, threats, client, regulation=regulation
        )
        if best is None or counts < best:
            best = counts
    assert best is not None
    return best


def candidate_improves_best_bring(
    team_draft: list[Slot],
    locked_contexts: Sequence["LockedAnchorContext"],
    candidate_slot_index: int,
    pick_count: int,
    threats: list[PokemonSpecOptional],
    client: CalcClient | None = None,
    *,
    regulation: str = "champions",
) -> bool:
    """Whether including this candidate allows some pick_count-sized
    combination to beat the best combination achievable from the locked
    roster alone -- the real "does this candidate have genuine bench/flex
    value" question for slots beyond the core (slot_index >= pick_count),
    as opposed to "does this candidate add more stackable coverage" (the
    wrong question once only pick_count of the roster will ever actually
    be brought together -- confirmed live, 2026-08-21).

    team_draft/locked_contexts must already include the candidate at
    candidate_slot_index (as a real, if hypothetical, Slot -- see
    spec_to_slot) -- this function only decides whether its presence
    changes the best achievable outcome, it doesn't construct the
    hypothetical team itself.
    """
    locked_indices = [ctx.slot_index for ctx in locked_contexts]
    if len(locked_indices) < pick_count:
        # No real baseline exists yet (e.g. only 3 locked, picking a
        # candidate 4th slot) -- every candidate that helps complete the
        # first real bring has value by definition, not something this
        # comparison is equipped to judge one way or the other.
        return False
    baseline = best_achievable_gap_counts(
        team_draft,
        locked_contexts,
        locked_indices,
        pick_count,
        threats,
        client,
        regulation=regulation,
    )
    with_candidate = best_achievable_gap_counts(
        team_draft,
        locked_contexts,
        [*locked_indices, candidate_slot_index],
        pick_count,
        threats,
        client,
        regulation=regulation,
    )
    return with_candidate < baseline
