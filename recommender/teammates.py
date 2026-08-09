"""Exact-form teammate co-occurrence evidence."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any, Literal

from recommender.ids import to_id
from recommender.legality import load_snapshot
from recommender.teammate_types import (
    AttributionStatus,
    DenominatorKind,
    NormalizedTeammate,
    NormalizedTeammates,
    SharedAnchorEvidence,
    SharedTeammate,
    SharedTeammateQueryResult,
    TeammateEvidence,
    TeammateQueryResult,
)
from recommender.usage_data import (
    ingame_species_map,
    lineage_ids,
    showdown_species_map,
)
from recommender.usage_live import fetch_live_showdown_detail

TEAMMATE_LIMIT = 10
_SNAPSHOT_KEYS = frozenset({"teammates", "teammates_meta"})


def _weights(raw: object) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for name, value in raw.items():
        label = str(name).strip()
        try:
            weight = float(value)
        except (TypeError, ValueError):
            continue
        if not label or not math.isfinite(weight) or weight < 0:
            continue
        out[label] = weight
    return out


def _raw_count(detail: dict[str, Any]) -> int | None:
    try:
        value = int(detail.get("Raw count"))
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def without_snapshot_teammates(entry: dict[str, Any]) -> dict[str, Any]:
    """Remove source-specific teammate fields from the compatibility flat map."""
    return {key: value for key, value in entry.items() if key not in _SNAPSHOT_KEYS}


def normalize_munch_teammates(
    detail: dict[str, Any] | None, *, limit: int = TEAMMATE_LIMIT
) -> NormalizedTeammates:
    """Convert MunchStats chaos weights to P(teammate | exact anchor form).

    This deliberately follows MunchStats' unconditional denominator selection:

      max(sum(valid Abilities), sum(valid Teammates) / 6, 1)

    The ``/ 6`` branch is an upstream display hotfix, not an independent sample
    count. Teammate percentages describe separate inclusion events and therefore
    must not be renormalized to sum to 100%.
    """
    if not isinstance(detail, dict) or not isinstance(detail.get("Teammates"), dict):
        return NormalizedTeammates(
            status="unavailable",
            rows=None,
            denominator_weight=None,
            denominator_kind=None,
            raw_count=_raw_count(detail or {}),
            source_row_count=0,
            limit=limit,
            truncated=False,
        )

    abilities = _weights(detail.get("Abilities"))
    teammates = _weights(detail["Teammates"])
    ability_weight = sum(abilities.values())
    teammate_weight_div_6 = sum(teammates.values()) / 6

    denominator = max(ability_weight, 1.0)
    denominator_kind: DenominatorKind = (
        "ability_weight" if ability_weight >= 1.0 else "floor_1"
    )
    if denominator < teammate_weight_div_6:
        denominator = teammate_weight_div_6
        denominator_kind = "teammate_weight_div_6"

    ranked = sorted(teammates.items(), key=lambda pair: (-pair[1], to_id(pair[0])))
    rows = tuple(
        NormalizedTeammate(
            species_id=to_id(name),
            name=name,
            rank=rank,
            chaos_weight=weight,
            conditional_pct=round(100.0 * weight / denominator, 3),
        )
        for rank, (name, weight) in enumerate(ranked[:limit], start=1)
    )
    return NormalizedTeammates(
        status="available",
        rows=rows,
        denominator_weight=denominator,
        denominator_kind=denominator_kind,
        raw_count=_raw_count(detail),
        source_row_count=len(ranked),
        limit=limit,
        truncated=len(ranked) > limit,
    )


def _number(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _showdown_result(
    species: str,
    *,
    source: Literal["showdown-offline", "showdown-live"],
    rows: object,
    meta: object,
) -> TeammateQueryResult | None:
    if rows is None or not isinstance(rows, list):
        return None
    metadata = meta if isinstance(meta, dict) else {}
    parsed: list[TeammateEvidence] = []
    for fallback_rank, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        species_id = to_id(str(row.get("id") or name))
        if not name or not species_id:
            continue
        try:
            rank = int(row.get("rank") or fallback_rank)
        except (TypeError, ValueError):
            rank = fallback_rank
        parsed.append(
            TeammateEvidence(
                species_id=species_id,
                name=name,
                rank=rank,
                conditional_pct=_number(row.get("conditional_pct")),
                chaos_weight=_number(row.get("chaos_weight")),
                attribution_status="exact",
            )
        )
    excluded = set(lineage_ids(species))
    parsed = [row for row in parsed if row.species_id not in excluded]
    return TeammateQueryResult(
        anchor_id=to_id(species),
        anchor_name=species,
        status="available",
        source=source,
        rows=tuple(parsed),
        raw_count=(
            int(metadata["raw_count"])
            if isinstance(metadata.get("raw_count"), int)
            else None
        ),
        truncated=(
            bool(metadata["truncated"])
            if "truncated" in metadata
            else source == "showdown-live"
            and len(rows) > TEAMMATE_LIMIT
        ),
        caveats=(
            "weighted ladder estimate, not an independent sample count",
            "long-tail and low-usage forms are less reliable",
            "not curated tournament data",
            f"only the top {TEAMMATE_LIMIT} source rows are retained",
        ),
    )


def _attribution_status(species_id: str) -> AttributionStatus:
    if species_id not in (load_snapshot().get("species") or {}):
        return "unresolved"
    lineage = lineage_ids(species_id)
    return "ambiguous" if species_id == lineage[0] and len(lineage) > 1 else "exact"


def _cbd_result(
    species: str,
    entry: dict[str, Any],
) -> TeammateQueryResult:
    rows = entry.get("teammates")
    rows = rows if isinstance(rows, list) else []
    excluded = set(lineage_ids(species))
    evidence: list[TeammateEvidence] = []
    for rank, raw in enumerate(rows, start=1):
        name = str(raw).strip()
        species_id = to_id(name)
        if not name or not species_id or species_id in excluded:
            continue
        evidence.append(
            TeammateEvidence(
                species_id=species_id,
                name=name,
                rank=rank,
                conditional_pct=None,
                chaos_weight=None,
                attribution_status=_attribution_status(species_id),
            )
        )
    return TeammateQueryResult(
        anchor_id=to_id(species),
        anchor_name=str(entry.get("name") or species),
        status="available",
        source="cbd-offline",
        rows=tuple(evidence),
        raw_count=None,
        truncated=None,
        caveats=(
            "CBD teammate labels do not prove exact-form attribution",
            "CBD percentages are unavailable in the stored snapshot",
        ),
    )


LiveShowdownFetch = Callable[[str, str], dict[str, Any] | None]


def _unavailable_result(species: str, caveat: str) -> TeammateQueryResult:
    return TeammateQueryResult(
        anchor_id=to_id(species),
        anchor_name=species,
        status="unavailable",
        source=None,
        rows=None,
        raw_count=None,
        truncated=None,
        caveats=(caveat,),
    )


def query_teammates(
    species: str,
    regulation: str = "champions",
    *,
    live_showdown_fetch: LiveShowdownFetch = fetch_live_showdown_detail,
) -> TeammateQueryResult:
    """Query exact-form evidence offline-first; fetch live only on snapshot miss."""
    species_id = to_id(species)
    showdown_entry = showdown_species_map(regulation).get(species_id)
    if showdown_entry is None:
        live_detail = live_showdown_fetch(species, regulation)
        normalized = normalize_munch_teammates(live_detail)
        if normalized.rows is not None:
            live = _showdown_result(
                species,
                source="showdown-live",
                rows=normalized.snapshot_rows(),
                meta=normalized.snapshot_meta(),
            )
            if live is not None:
                return live
    elif isinstance(showdown_entry, dict):
        offline = _showdown_result(
            str(showdown_entry.get("name") or species),
            source="showdown-offline",
            rows=showdown_entry.get("teammates"),
            meta=showdown_entry.get("teammates_meta"),
        )
        if offline is not None:
            return offline
        return _unavailable_result(
            species, "offline exact-form teammate record is malformed"
        )
    else:
        return _unavailable_result(
            species, "offline exact-form usage record is malformed"
        )

    ingame = ingame_species_map(regulation)
    base_id = lineage_ids(species)[0]
    cbd_entry = ingame.get(species_id) or ingame.get(base_id)
    if isinstance(cbd_entry, dict):
        return _cbd_result(species, cbd_entry)
    return _unavailable_result(
        species, "no offline or authorized live teammate evidence was available"
    )


TeammateQuery = Callable[[str, str], TeammateQueryResult]


def query_shared_teammates(
    species: Sequence[str],
    regulation: str = "champions",
    *,
    query: TeammateQuery = query_teammates,
) -> SharedTeammateQueryResult:
    """Return the strict all-N intersection of individually available rows."""
    anchors = tuple(query(name, regulation) for name in species)
    unavailable = tuple(
        result.anchor_id for result in anchors if result.status == "unavailable"
    )
    ordering = (
        "highest minimum conditional_pct, then lowest worst rank; "
        "rank-only evidence uses lowest worst rank"
    )
    caveats = tuple(dict.fromkeys(caveat for result in anchors for caveat in result.caveats))
    if not anchors or unavailable:
        return SharedTeammateQueryResult(
            anchor_results=anchors,
            status="unavailable",
            rows=None,
            unavailable_anchors=unavailable or tuple(to_id(name) for name in species),
            ordering=ordering,
            caveats=caveats,
        )

    by_anchor = [
        {row.species_id: row for row in result.rows or ()} for result in anchors
    ]
    shared_ids = set(by_anchor[0]).intersection(*(set(rows) for rows in by_anchor[1:]))
    excluded = {
        lineage_id
        for name in species
        for lineage_id in lineage_ids(name)
    }
    shared_ids.difference_update(excluded)

    shared: list[SharedTeammate] = []
    for species_id in shared_ids:
        evidence = tuple(rows[species_id] for rows in by_anchor)
        percentages = tuple(row.conditional_pct for row in evidence)
        all_percentages = all(value is not None for value in percentages)
        statuses = {row.attribution_status for row in evidence}
        attribution: AttributionStatus = (
            "unresolved"
            if "unresolved" in statuses
            else "ambiguous"
            if "ambiguous" in statuses
            else "exact"
        )
        shared.append(
            SharedTeammate(
                species_id=species_id,
                name=evidence[0].name,
                per_anchor=tuple(
                    SharedAnchorEvidence(
                        anchor_id=anchor.anchor_id,
                        rank=row.rank,
                        conditional_pct=row.conditional_pct,
                    )
                    for anchor, row in zip(anchors, evidence, strict=True)
                ),
                worst_rank=max(row.rank for row in evidence),
                min_conditional_pct=(
                    min(value for value in percentages if value is not None)
                    if all_percentages
                    else None
                ),
                attribution_status=attribution,
            )
        )

    shared.sort(
        key=lambda row: (
            row.min_conditional_pct is None,
            -(row.min_conditional_pct or 0),
            row.worst_rank,
            sum(item.rank for item in row.per_anchor),
            row.species_id,
        )
    )
    return SharedTeammateQueryResult(
        anchor_results=anchors,
        status="available",
        rows=tuple(shared),
        unavailable_anchors=(),
        ordering=ordering,
        caveats=caveats
        + ("empty means no teammate appeared in every retained top-10 list",),
    )
