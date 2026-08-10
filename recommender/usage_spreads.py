"""Contextual tier-2 spread selection from structured usage evidence."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from recommender.ids import to_id
from recommender.legality import load_snapshot
from recommender.state import StatsTable
from recommender.usage_data import species_usage
from recommender.usage_live import (
    JsonFetch,
    fetch_json,
    fetch_live_cbd_battle,
    fetch_live_showdown_detail,
    supports_live_usage,
)

_STAT_KEYS = ("hp", "atk", "def", "spa", "spd", "spe")
_SPEED_PLUS = frozenset({"Hasty", "Jolly", "Naive", "Timid"})
_SPEED_MINUS = frozenset({"Brave", "Relaxed", "Quiet", "Sassy"})
@dataclass(frozen=True)
class SpreadEvidence:
    spread: StatsTable
    nature: str | None
    source: str
    weight: float | None
    weight_kind: str
    rank: int


@dataclass(frozen=True)
class SpreadChoice:
    spread: StatsTable
    nature: str | None
    source: str
    rationale: str


def _normalize_spread(raw: Any) -> StatsTable | None:
    if not isinstance(raw, dict) or any(key not in raw for key in _STAT_KEYS):
        return None
    try:
        spread: StatsTable = {key: int(raw[key]) for key in _STAT_KEYS}  # type: ignore[misc]
    except (TypeError, ValueError):
        return None
    if sum(spread.values()) != 66 or any(value < 0 or value > 32 for value in spread.values()):
        return None
    return spread


def _weight(raw: Any) -> float | None:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _evidence_from_rows(
    rows: Sequence[dict[str, Any]], *, source: str, weight_kind: str
) -> tuple[SpreadEvidence, ...]:
    out: list[SpreadEvidence] = []
    for rank, row in enumerate(rows):
        spread = _normalize_spread(row.get("evs"))
        if spread is None:
            continue
        nature = row.get("nature")
        out.append(
            SpreadEvidence(
                spread=spread,
                nature=str(nature) if nature else None,
                source=source,
                weight=_weight(row.get("pct")),
                weight_kind=weight_kind,
                rank=rank,
            )
        )
    return tuple(out)


def _showdown_rows(detail: dict[str, Any]) -> list[dict[str, Any]]:
    raw = detail.get("Spreads") or {}
    if not isinstance(raw, dict):
        return []
    try:
        ranked = sorted(raw.items(), key=lambda pair: -float(pair[1]))
    except (TypeError, ValueError):
        return []
    out: list[dict[str, Any]] = []
    for label, chaos_weight in ranked:
        if len(out) >= 8 or not isinstance(label, str) or ":" not in label:
            continue
        nature, values = label.split(":", 1)
        parts = values.split("/")
        if len(parts) != 6:
            continue
        try:
            hp, atk, defense, spa, spd, spe = (int(float(value)) for value in parts)
        except (TypeError, ValueError):
            continue
        out.append(
            {
                "nature": nature,
                "evs": {
                    "hp": hp,
                    "atk": atk,
                    "def": defense,
                    "spa": spa,
                    "spd": spd,
                    "spe": spe,
                },
                "pct": chaos_weight,
            }
        )
    return out


def _cbd_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("rows") or []
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if len(out) >= 8 or not isinstance(row, dict) or row.get("category") != "stat_points":
            continue
        try:
            evs = {
                "hp": int(row.get("hp_points") or 0),
                "atk": int(row.get("attack_points") or 0),
                "def": int(row.get("defense_points") or 0),
                "spa": int(row.get("sp_atk_points") or 0),
                "spd": int(row.get("sp_def_points") or 0),
                "spe": int(row.get("speed_points") or 0),
            }
        except (TypeError, ValueError):
            continue
        out.append(
            {
                "evs": evs,
                "pct": row.get("percentage_value"),
            }
        )
    return out


@lru_cache(maxsize=128)
def fetch_live_spreads(
    species: str,
    regulation: str = "champions",
    fetch_json: JsonFetch = fetch_json,
) -> tuple[SpreadEvidence, ...]:
    """Fetch one species' structured spreads; misses and failures are cached."""
    if not supports_live_usage(regulation):
        return ()
    detail = fetch_live_showdown_detail(species, regulation, fetch_json)
    if detail is not None:
        evidence = _evidence_from_rows(
            _showdown_rows(detail),
            source="showdown-live",
            weight_kind="chaos_weight",
        )
        if evidence:
            return evidence

    cbd = fetch_live_cbd_battle(species, fetch_json)
    if cbd is None:
        return ()
    return _evidence_from_rows(
        _cbd_rows(cbd),
        source="cbd-live",
        weight_kind="percentage",
    )


def effective_spe(
    species: str,
    spread: dict[str, int],
    nature: str,
    *,
    scarf: bool = False,
    level: int = 50,
    snap: dict[str, Any] | None = None,
) -> int:
    """Approximate Champions Speed for deterministic breakpoint comparisons."""
    snapshot = snap or load_snapshot()
    entry = (snapshot.get("species") or {}).get(to_id(species)) or {}
    base = int((entry.get("base_stats") or {}).get("spe") or 0)
    ev_like = min(252, int(spread.get("spe", 0)) * 4)
    speed = ((2 * base + 31 + ev_like // 4) * level) // 100 + 5
    if nature in _SPEED_PLUS:
        speed = int(speed * 1.1)
    elif nature in _SPEED_MINUS:
        speed = int(speed * 0.9)
    return int(speed * 1.5) if scarf else speed


def _move_categories(moves: Sequence[str], snap: dict[str, Any]) -> tuple[int, int]:
    physical = special = 0
    move_table = snap.get("moves") or {}
    for move in moves:
        category = (move_table.get(to_id(move)) or {}).get("category")
        physical += category == "Physical"
        special += category == "Special"
    return physical, special


def move_category_counts(
    moves: Sequence[str], snap: dict[str, Any] | None = None
) -> tuple[int, int]:
    return _move_categories(moves, snap or load_snapshot())


def _threat_specs(threats: Sequence[Any]) -> list[dict[str, Any]]:
    return [
        spec
        for threat in threats
        if isinstance((spec := getattr(threat, "spec", threat)), dict)
    ]


def _bulk_score(
    spread: StatsTable, threats: Sequence[dict[str, Any]], snap: dict[str, Any]
) -> int:
    physical = special = 0
    for threat in threats:
        p_count, s_count = _move_categories(threat.get("moves") or [], snap)
        physical += p_count
        special += s_count
    if physical > special:
        return spread["hp"] + spread["def"]
    if special > physical:
        return spread["hp"] + spread["spd"]
    return 2 * spread["hp"] + spread["def"] + spread["spd"]


def _offense_score(
    spread: StatsTable, physical: int, special: int
) -> int:
    if physical > special:
        return spread["atk"]
    if special > physical:
        return spread["spa"]
    return max(spread["atk"], spread["spa"])


def _speed_score(
    species: str,
    evidence: SpreadEvidence,
    threats: Sequence[dict[str, Any]],
    snap: dict[str, Any],
) -> tuple[int, int]:
    speed = effective_spe(
        species, evidence.spread, evidence.nature or "Hardy", snap=snap
    )
    cleared = 0
    for threat in threats:
        opponent = str(threat.get("species") or "")
        if not opponent:
            continue
        opponent_spread = threat.get("evs") or {
            "hp": 0,
            "atk": 0,
            "def": 0,
            "spa": 0,
            "spd": 0,
            "spe": 32,
        }
        if speed > effective_spe(
            opponent,
            opponent_spread,
            str(threat.get("nature") or "Jolly"),
            snap=snap,
        ):
            cleared += 1
    return cleared, speed


def _choice_score(
    evidence: SpreadEvidence,
    *,
    species: str,
    role: str,
    physical: int,
    special: int,
    threats: Sequence[dict[str, Any]],
    snap: dict[str, Any],
) -> tuple[Any, ...]:
    spread = evidence.spread
    offense = _offense_score(spread, physical, special)
    bulk = _bulk_score(spread, threats, snap)
    speed = _speed_score(species, evidence, threats, snap)
    rank = -evidence.rank
    if role == "fast_attacker" or role.startswith("fast_"):
        return speed, offense, bulk, rank
    if role == "trick_room_sweeper":
        return -speed[1], offense, bulk, rank
    if role == "support_speed_control":
        return speed, bulk, offense, rank
    if (
        role == "bulky_attacker"
        or role.startswith("bulky_")
        or role == "screens_support"
    ):
        return bulk, spread["hp"], offense, rank
    return offense, bulk, speed, rank


def select_usage_spread(
    species: str,
    role: str,
    moves: Sequence[str],
    *,
    regulation: str = "champions",
    threats: Sequence[Any] = (),
    snap: dict[str, Any] | None = None,
    live_fetch: Callable[[str, str], tuple[SpreadEvidence, ...]] | None = None,
) -> SpreadChoice | None:
    """Choose a real usage spread for the current role and threat context."""
    snapshot = snap or load_snapshot()
    entry = species_usage(species, regulation=regulation)
    if entry is None:
        fetch = live_fetch or fetch_live_spreads
        candidates = fetch(species, regulation)
        source_tier = "tier2_usage_live"
    else:
        rows = entry.get("top_spreads") or []
        source = "showdown-offline" if any(row.get("nature") for row in rows) else "cbd-offline"
        weight_kind = "chaos_weight" if source.startswith("showdown") else "percentage"
        candidates = _evidence_from_rows(rows, source=source, weight_kind=weight_kind)
        source_tier = "tier2_usage_offline"
    if not candidates:
        return None

    threat_specs = _threat_specs(threats)
    physical, special = _move_categories(moves, snapshot)
    selected = max(
        candidates,
        key=lambda candidate: _choice_score(
            candidate,
            species=species,
            role=role,
            physical=physical,
            special=special,
            threats=threat_specs,
            snap=snapshot,
        ),
    )
    rationale = (
        f"{source_tier} role={role} selected rank={selected.rank + 1} "
        f"from {len(candidates)} {selected.source} variants"
    )
    return SpreadChoice(
        spread=dict(selected.spread),  # type: ignore[arg-type]
        nature=selected.nature,
        source=source_tier,
        rationale=rationale,
    )
