"""Dependency-neutral teammate evidence contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TeammateStatus = Literal["available", "unavailable"]
DenominatorKind = Literal["ability_weight", "teammate_weight_div_6", "floor_1"]
AttributionStatus = Literal["exact", "ambiguous", "unresolved"]
TeammateSource = Literal["showdown-offline", "showdown-live", "cbd-offline"]


@dataclass(frozen=True)
class NormalizedTeammate:
    species_id: str
    name: str
    rank: int
    chaos_weight: float
    conditional_pct: float

    def snapshot_row(self) -> dict[str, object]:
        return {
            "id": self.species_id,
            "name": self.name,
            "rank": self.rank,
            "chaos_weight": self.chaos_weight,
            "conditional_pct": self.conditional_pct,
        }


@dataclass(frozen=True)
class NormalizedTeammates:
    status: TeammateStatus
    rows: tuple[NormalizedTeammate, ...] | None
    denominator_weight: float | None
    denominator_kind: DenominatorKind | None
    raw_count: int | None
    source_row_count: int
    limit: int
    truncated: bool

    def snapshot_rows(self) -> list[dict[str, object]] | None:
        if self.rows is None:
            return None
        return [row.snapshot_row() for row in self.rows]

    def snapshot_meta(self) -> dict[str, object]:
        return {
            "status": self.status,
            "denominator_weight": self.denominator_weight,
            "denominator_kind": self.denominator_kind,
            "raw_count": self.raw_count,
            "source_row_count": self.source_row_count,
            "retained_count": len(self.rows or ()),
            "limit": self.limit,
            "truncated": self.truncated,
        }


@dataclass(frozen=True)
class TeammateEvidence:
    species_id: str
    name: str
    rank: int
    conditional_pct: float | None
    chaos_weight: float | None
    attribution_status: AttributionStatus


@dataclass(frozen=True)
class TeammateQueryResult:
    anchor_id: str
    anchor_name: str
    status: TeammateStatus
    source: TeammateSource | None
    rows: tuple[TeammateEvidence, ...] | None
    raw_count: int | None
    truncated: bool | None
    caveats: tuple[str, ...]


@dataclass(frozen=True)
class SharedAnchorEvidence:
    anchor_id: str
    rank: int
    conditional_pct: float | None


@dataclass(frozen=True)
class SharedTeammate:
    species_id: str
    name: str
    per_anchor: tuple[SharedAnchorEvidence, ...]
    worst_rank: int
    min_conditional_pct: float | None
    attribution_status: AttributionStatus


@dataclass(frozen=True)
class SharedTeammateQueryResult:
    anchor_results: tuple[TeammateQueryResult, ...]
    status: TeammateStatus
    rows: tuple[SharedTeammate, ...] | None
    unavailable_anchors: tuple[str, ...]
    ordering: str
    caveats: tuple[str, ...]
