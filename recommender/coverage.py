"""Team-wide threat coverage and SPOF detection (ADR-015 gaps #7/#8)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from recommender.calc_client import CalcClient, FieldSpec, PokemonSpecOptional
from recommender.contingent_value import TERRAIN_SETTERS, WEATHER_SETTERS
from recommender.ids import to_id
from recommender.matchup import MatchupResult, Severity, classify_matchup
from recommender.ranking import rank_and_cut
from recommender.state import (
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


def _forced_fields_from_draft(
    team_draft: list[Slot],
    *,
    regulation: str,
    exclude_slot: int | None = None,
) -> list[FieldSpec]:
    seen: set[tuple[str | None, str | None]] = set()
    out: list[FieldSpec] = []
    for i, slot in enumerate(team_draft):
        if exclude_slot is not None and i == exclude_slot:
            continue
        if not slot.species.value or not slot.species.locked:
            continue
        spec = _slot_to_spec(slot, regulation=regulation)
        if not spec:
            continue
        aid = to_id(spec.get("ability") or "")
        if aid not in WEATHER_SETTERS and aid not in TERRAIN_SETTERS:
            continue
        field = ABILITY_TO_FIELD.get(aid)
        if not field:
            continue
        key = (field.get("weather"), field.get("terrain"))
        if key in seen:
            continue
        seen.add(key)
        out.append(field)
    return out


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
    regulation: str = "champions",
) -> list[ThreatCoverageResult]:
    if not threats:
        return []

    forced_fields = _forced_fields_from_draft(
        team_draft, regulation=regulation, exclude_slot=exclude_slot
    )
    results: list[ThreatCoverageResult] = []

    for threat in threats:
        covering: list[int] = []
        best: MatchupResult | None = None
        any_result: MatchupResult | None = None
        forced_field: FieldSpec | None = None

        for i, slot in enumerate(team_draft):
            if exclude_slot is not None and i == exclude_slot:
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
) -> list[SPOFFinding]:
    baseline = compute_team_coverage(
        team_draft, threats, client, regulation=regulation
    )
    by_slot: dict[int, tuple[list[PokemonSpecOptional], dict[str, Severity]]] = {}

    for i, slot in enumerate(team_draft):
        if not slot.species.value:
            continue
        minus = compute_team_coverage(
            team_draft, threats, client, exclude_slot=i, regulation=regulation
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
