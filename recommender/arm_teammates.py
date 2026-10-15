"""Arm-facing explicit-source teammate tools (D7).

Named structured sources and labeled fallback per ADR-014 Amendments
2026-10-14a and 2026-10-14b. ``query_teammates`` / ``query_shared_teammates``
(D1, the Showdown-first graph path) are unchanged.

Contract:

* ``source`` is required and has no default: ``"ingame"`` or ``"showdown"``.
  Build-level names (vgcpastes, pikalytics, pokemon-zone, writeups) return
  ``deferred_build_surface`` and are served by a later PR.
* There is no phase argument. The phase gate lives in the graph callers
  (Amendment 2026-10-14b). Callers control live fetches with ``allow_live``;
  evaluation runs must pass ``allow_live=False`` (live data is not pinned).
* A missing row for the requested source triggers at most one cross-source hop,
  disclosed in ``fallback`` and ``attempts``. A hop is a full retrieval on the
  other source: Showdown tries offline then at most one live call; in-game is
  offline only. A miss on the second source is final.
* Mega formes are never served from in-game (the in-game blob has no Mega
  keys). A Mega request or any Mega anchor is served whole from Showdown.
* A malformed offline row is an explicit error: no live call and no hop.
* Showdown results carry ``denominator``: the weight that ``conditional_pct``
  is a fraction of, read from the record's own metadata with a label naming the
  quantity. When a record lacks it, ``denominator`` is None and a caveat says
  the base is unavailable; it is never back-computed.
* Nothing raises. Unexpected exceptions become a fixed-message error result
  and the exception class is logged through ``log_tool_call``.
* A live call goes through the existing ``fetch_live_showdown_detail``
  mechanism once and adds no retry here. That mechanism's worst case is about
  90.6 s. Production collapses every live failure to ``None``, so the logged
  subkind is ``miss_or_error``; ``http_4xx_miss``, ``transient_exhausted`` and
  ``json_decode`` appear only through an injected fetcher that raises
  ``ArmLiveFetchError``.
"""

from __future__ import annotations

import calendar
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from functools import lru_cache
from typing import Any, Literal

from recommender.ids import to_id
from recommender.item_conditions import mega_stones_by_item_id
from recommender.legality import is_species_legal, load_snapshot
from recommender.teammate_types import (
    ArmErrorKind,
    DenominatorKind,
    ArmFallbackReason,
    ArmLiveErrorKind,
    ArmMultiMode,
    ArmPieceSource,
    ArmStatus,
    ArmValueKind,
    AttributionStatus,
)
from recommender.teammates import (
    LiveShowdownFetch,
    _attribution_status,
    _number,
    _showdown_result,
    normalize_munch_teammates,
)
from recommender.tool_log import log_tool_call
from recommender.usage_data import (
    ingame_ladder_species_map,
    lineage_ids,
    load_usage,
    showdown_species_map,
)
from recommender.usage_live import (
    LiveFetchError,
    _live_format_for,
    fetch_live_showdown_detail,
)

ARM_UNEXPECTED_MSG = "An unexpected error occurred while querying teammates."
ARM_INVALID_SOURCE_MSG = "source must be 'ingame' or 'showdown'."
ARM_INVALID_MODE_MSG = (
    "mode must be 'intersection', 'reverse_lookup', or 'team_level'."
)
ARM_MALFORMED_MSG = "The stored teammate row for this species is unusable."
ARM_DEFERRED_MSG = "This source is a build-level surface and is not served by this tool yet."
ARM_MESSAGE_ALLOWLIST: frozenset[str] = frozenset(
    {
        ARM_UNEXPECTED_MSG,
        ARM_INVALID_SOURCE_MSG,
        ARM_INVALID_MODE_MSG,
        ARM_MALFORMED_MSG,
        ARM_DEFERRED_MSG,
    }
)

PIECE_SOURCES: tuple[str, ...] = ("ingame", "showdown")
BUILD_LEVEL_SOURCES: frozenset[str] = frozenset(
    {"vgcpastes", "pikalytics", "pokemon-zone", "writeups"}
)
_MULTI_MODES: tuple[str, ...] = ("intersection", "reverse_lookup", "team_level")


class ArmLiveFetchError(LiveFetchError):
    """Injectable live-fetch failure carrying one of the typed subkinds."""

    def __init__(self, kind: ArmLiveErrorKind) -> None:
        super().__init__(kind)
        self.kind: ArmLiveErrorKind = kind


@dataclass(frozen=True)
class ArmAsOf:
    """Freshness fields for one retrieval (ADR-014 2026-10-14b)."""

    source: ArmPieceSource
    captured_on: str | None  # ingame
    season: str | None  # ingame
    month: str | None  # showdown
    rating: int | None  # showdown
    period_end: str | None  # showdown: calendar last day of month
    extracted_at: str | None  # showdown offline extract, reference only; None for live
    fetched_at: str | None  # live only
    age_days: int | None  # from captured_on (ingame) or period_end (showdown)


@dataclass(frozen=True)
class ArmDenominator:
    """What a Showdown row's ``conditional_pct`` is a fraction of.

    Read from the record's own metadata (offline ``teammates_meta`` or the live
    normalization); never back-computed. ``conditional_pct`` equals
    ``round(100 * chaos_weight / weight, 3)``.
    """

    weight: float
    kind: DenominatorKind
    label: str


@dataclass(frozen=True)
class ArmFallback:
    """Disclosure that the served source differs from the requested one.

    ``error_kind`` equals ``reason`` (14b vocabulary). The live-failure subkind
    lives on the attempt, not here.
    """

    requested: ArmPieceSource
    used: ArmPieceSource
    reason: ArmFallbackReason
    error_kind: ArmFallbackReason


@dataclass(frozen=True)
class ArmAttempt:
    source: ArmPieceSource
    method: Literal["offline", "live"]
    reason: ArmFallbackReason | None  # None = this attempt served
    subkind: ArmLiveErrorKind | None = None  # live_unavailable only
    anchor_id: str | None = None  # set on multi-anchor results


@dataclass(frozen=True)
class ArmTeammateRow:
    species_id: str
    name: str
    rank: int
    conditional_pct: float | None
    chaos_weight: float | None
    attribution_status: AttributionStatus
    value_kind: ArmValueKind


@dataclass(frozen=True)
class ArmTeammateResult:
    status: ArmStatus
    anchor_id: str
    anchor_name: str
    requested_source: str | None
    used_source: ArmPieceSource | None
    method: Literal["offline", "live"] | None
    value_kind: ArmValueKind | None
    rows: tuple[ArmTeammateRow, ...] | None
    raw_count: int | None
    truncated: bool | None
    fallback: ArmFallback | None
    attempts: tuple[ArmAttempt, ...]
    as_of: ArmAsOf | None
    caveats: tuple[str, ...] = ()
    denominator: ArmDenominator | None = None  # showdown only
    message: str | None = None
    error_kind: str | None = None
    exception_type: str | None = None


@dataclass(frozen=True)
class ArmSharedAnchorEvidence:
    anchor_id: str
    rank: int
    conditional_pct: float | None
    value_kind: ArmValueKind


@dataclass(frozen=True)
class ArmSharedTeammate:
    species_id: str
    name: str
    per_anchor: tuple[ArmSharedAnchorEvidence, ...]
    worst_rank: int
    min_conditional_pct: float | None
    attribution_status: AttributionStatus
    value_kind: ArmValueKind


@dataclass(frozen=True)
class ArmMultiAsOf:
    per_anchor: tuple[ArmAsOf | None, ...]
    as_of_dates_differ: bool
    note: str | None


@dataclass(frozen=True)
class ArmMultiTeammateResult:
    status: ArmStatus
    mode: ArmMultiMode
    anchor_results: tuple[ArmTeammateResult, ...]
    rows: tuple[ArmSharedTeammate, ...] | None
    unavailable_anchors: tuple[str, ...]
    fallback: ArmFallback | None
    attempts: tuple[ArmAttempt, ...]
    as_of: ArmMultiAsOf | None
    caveats: tuple[str, ...] = ()
    message: str | None = None
    error_kind: str | None = None
    exception_type: str | None = None
    ordering: str | None = None


# --------------------------------------------------------------------------
# Mega detection and dates
# --------------------------------------------------------------------------


def period_end_for_month(month: str) -> str | None:
    """Calendar last day of YYYY-MM (Showdown ``age_days`` base); None if malformed."""
    try:
        y_s, m_s = str(month).split("-", 1)
        y, m = int(y_s), int(m_s)
        if not 1 <= m <= 12:
            return None
        return date(y, m, calendar.monthrange(y, m)[1]).isoformat()
    except (TypeError, ValueError):
        return None


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _age_days_from_iso(day: str | None) -> int | None:
    if not day:
        return None
    try:
        d = date.fromisoformat(str(day)[:10])
    except ValueError:
        return None
    return (_utc_today() - d).days


@lru_cache(maxsize=1)
def _mega_pairs() -> tuple[tuple[str, str], ...]:
    """(base id, mega forme id) for MEGA_STONES entries whose forme is a legal forme."""
    snap = load_snapshot()
    species = snap.get("species") or {}
    out: list[tuple[str, str]] = []
    for pairs in mega_stones_by_item_id().values():
        for base, mega in pairs:
            mid = to_id(mega)
            entry = species.get(mid) or {}
            if entry.get("base_species_id") and is_species_legal(snap, mid):
                out.append((to_id(base), mid))
    return tuple(out)


def legal_mega_forme_ids() -> frozenset[str]:
    return frozenset(mega for _base, mega in _mega_pairs())


def mega_capable_base_ids() -> frozenset[str]:
    return frozenset(base for base, _mega in _mega_pairs())


def is_mega_forme(species: str) -> bool:
    return to_id(species) in legal_mega_forme_ids()


# --------------------------------------------------------------------------
# Retrieval (one source, one anchor)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Retrieval:
    kind: Literal["ok", "miss", "malformed"]
    source: ArmPieceSource
    attempt: ArmAttempt
    method: Literal["offline", "live"] | None = None
    name: str | None = None
    rows: tuple[ArmTeammateRow, ...] | None = None
    raw_count: int | None = None
    truncated: bool | None = None
    as_of: ArmAsOf | None = None
    caveats: tuple[str, ...] = ()
    denominator: ArmDenominator | None = None
    exception_type: str | None = None


_DENOMINATOR_LABELS: dict[str, str] = {
    "ability_weight": (
        "conditional_pct = 100 x teammate chaos_weight / the anchor's summed "
        "Abilities weights (its total weighted usage in the source)"
    ),
    "teammate_weight_div_6": (
        "conditional_pct = 100 x teammate chaos_weight / (sum of all listed "
        "teammate weights / 6); an upstream display floor, not an independent "
        "sample count"
    ),
    "floor_1": (
        "conditional_pct = 100 x teammate chaos_weight / 1.0 (the source had "
        "no usable Abilities weights)"
    ),
}
_NO_DENOMINATOR_CAVEAT = (
    "conditional_pct is a share of the anchor's total weight, but this record "
    "does not carry that total, so the base is unavailable"
)


def _denominator(weight: object, kind: object) -> ArmDenominator | None:
    w = _number(weight)
    if w is None or w <= 0 or kind not in _DENOMINATOR_LABELS:
        return None
    return ArmDenominator(weight=w, kind=kind, label=_DENOMINATOR_LABELS[kind])  # type: ignore[arg-type]


def _miss(
    source: ArmPieceSource,
    method: Literal["offline", "live"],
    reason: ArmFallbackReason,
    subkind: ArmLiveErrorKind | None = None,
) -> _Retrieval:
    return _Retrieval("miss", source, ArmAttempt(source, method, reason, subkind))


def _malformed(source: ArmPieceSource, value: object) -> _Retrieval:
    return _Retrieval(
        "malformed",
        source,
        ArmAttempt(source, "offline", None),
        exception_type=type(value).__name__,
    )


def _ingame_as_of(regulation: str) -> ArmAsOf:
    meta = load_usage(regulation).get("meta") or {}
    captured = meta.get("munchstats_captured_on")
    captured_s = captured[:10] if isinstance(captured, str) else None
    season = meta.get("munchstats_default_season")
    return ArmAsOf(
        source="ingame",
        captured_on=captured_s,
        season=str(season) if season is not None else None,
        month=None,
        rating=None,
        period_end=None,
        extracted_at=None,
        fetched_at=None,
        age_days=_age_days_from_iso(captured_s),
    )


def _showdown_offline_as_of(regulation: str) -> ArmAsOf:
    meta = load_usage(regulation).get("meta") or {}
    month = meta.get("showdown_month")
    month_s = str(month) if month else None
    rating = meta.get("showdown_rating")
    period_end = period_end_for_month(month_s) if month_s else None
    extracted = meta.get("showdown_extracted_at") or meta.get(
        "showdown_teammates_extracted_at"
    )
    return ArmAsOf(
        source="showdown",
        captured_on=None,
        season=None,
        month=month_s,
        rating=rating if isinstance(rating, int) else None,
        period_end=period_end,
        extracted_at=str(extracted) if extracted else None,
        fetched_at=None,
        age_days=_age_days_from_iso(period_end),
    )


def _showdown_live_as_of(regulation: str) -> ArmAsOf:
    tup = _live_format_for(regulation)  # (month, showdown format id, rating)
    month_s = tup[0] if tup else None
    period_end = period_end_for_month(month_s) if month_s else None
    return ArmAsOf(
        source="showdown",
        captured_on=None,
        season=None,
        month=month_s,
        rating=int(tup[2]) if tup else None,
        period_end=period_end,
        extracted_at=None,
        fetched_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        age_days=_age_days_from_iso(period_end),
    )


def _date_caveats(as_of: ArmAsOf) -> tuple[str, ...]:
    if as_of.source == "ingame" and as_of.captured_on is None:
        return ("in-game capture date is unavailable, so the age is unknown",)
    if as_of.source == "showdown" and as_of.period_end is None:
        return ("Showdown month is missing or malformed, so the age is unknown",)
    return ()


def _retrieve_ingame(species: str, regulation: str) -> _Retrieval:
    """Offline only. Exact id on the raw ladder map; no base-species substitution."""
    sid = to_id(species)
    entry = ingame_ladder_species_map(regulation).get(sid)
    if entry is None:
        return _miss("ingame", "offline", "no_row")
    if not isinstance(entry, dict) or not isinstance(entry.get("teammates"), list):
        return _malformed("ingame", entry)
    excluded = set(lineage_ids(species))
    rows: list[ArmTeammateRow] = []
    for rank, raw in enumerate(entry["teammates"], start=1):
        name = str(raw).strip()
        tid = to_id(name)
        if not name or not tid or tid in excluded:
            continue
        rows.append(
            ArmTeammateRow(
                species_id=tid,
                name=name,
                rank=rank,
                conditional_pct=None,
                chaos_weight=None,
                attribution_status=_attribution_status(tid),
                value_kind="rank_only",
            )
        )
    caveats = [
        "in-game lists carry rank only; there are no percentages",
        "in-game teammate labels do not prove exact-form attribution",
    ]
    if sid in mega_capable_base_ids():
        caveats.append(
            "in-game usage for a Mega-capable base species mixes base-form "
            "and Mega-form usage"
        )
    as_of = _ingame_as_of(regulation)
    return _Retrieval(
        "ok",
        "ingame",
        ArmAttempt("ingame", "offline", None),
        method="offline",
        name=str(entry.get("name") or species),
        rows=tuple(rows),
        raw_count=None,
        truncated=None,
        as_of=as_of,
        caveats=tuple(caveats) + _date_caveats(as_of),
    )


def _showdown_ok(
    species: str,
    q: Any,
    method: Literal["offline", "live"],
    as_of: ArmAsOf,
    denominator: ArmDenominator | None,
    extra: tuple[str, ...] = (),
) -> _Retrieval:
    rows = tuple(
        ArmTeammateRow(
            species_id=r.species_id,
            name=r.name,
            rank=r.rank,
            conditional_pct=r.conditional_pct,
            chaos_weight=r.chaos_weight,
            attribution_status=r.attribution_status,
            value_kind="conditional_percent",
        )
        for r in (q.rows or ())
    )
    return _Retrieval(
        "ok",
        "showdown",
        ArmAttempt("showdown", method, None),
        method=method,
        name=q.anchor_name or species,
        rows=rows,
        raw_count=q.raw_count,
        truncated=q.truncated,
        as_of=as_of,
        caveats=(
            tuple(q.caveats)
            + extra
            + (() if denominator else (_NO_DENOMINATOR_CAVEAT,))
            + _date_caveats(as_of)
        ),
        denominator=denominator,
    )


def _retrieve_showdown(
    species: str,
    regulation: str,
    *,
    allow_live: bool,
    live_fetch: LiveShowdownFetch,
) -> _Retrieval:
    """Offline row first; one live call only when the offline row is absent."""
    entry = showdown_species_map(regulation).get(to_id(species))
    if entry is not None:
        if not isinstance(entry, dict):
            return _malformed("showdown", entry)
        q = _showdown_result(
            species,
            source="showdown-offline",
            rows=entry.get("teammates"),
            meta=entry.get("teammates_meta"),
        )
        if q is None:
            return _malformed("showdown", entry.get("teammates"))
        meta = entry.get("teammates_meta")
        meta = meta if isinstance(meta, dict) else {}
        return _showdown_ok(
            species,
            q,
            "offline",
            _showdown_offline_as_of(regulation),
            _denominator(meta.get("denominator_weight"), meta.get("denominator_kind")),
        )

    if not allow_live:
        return _miss("showdown", "offline", "live_disabled")
    if _live_format_for(regulation) is None:
        return _miss("showdown", "offline", "live_not_supported")

    subkind: ArmLiveErrorKind = "miss_or_error"
    q = None
    normalized = None
    try:
        detail = live_fetch(species, regulation)
    except ArmLiveFetchError as exc:
        detail, subkind = None, exc.kind
    except Exception:  # live failures are a miss, never an exception to the caller
        detail = None
    if detail is not None:
        normalized = normalize_munch_teammates(detail)
        if normalized.rows is not None:
            q = _showdown_result(
                species,
                source="showdown-live",
                rows=normalized.snapshot_rows(),
                meta=normalized.snapshot_meta(),
            )
    if q is None:
        return _miss("showdown", "live", "live_unavailable", subkind)
    return _showdown_ok(
        species,
        q,
        "live",
        _showdown_live_as_of(regulation),
        _denominator(normalized.denominator_weight, normalized.denominator_kind)
        if normalized is not None
        else None,
        ("live fetch: not pinned, so this result cannot be replayed",),
    )


def _retrieve(
    source: ArmPieceSource,
    species: str,
    regulation: str,
    *,
    allow_live: bool,
    live_fetch: LiveShowdownFetch,
) -> _Retrieval:
    if source == "ingame":
        return _retrieve_ingame(species, regulation)
    return _retrieve_showdown(
        species, regulation, allow_live=allow_live, live_fetch=live_fetch
    )


def _other(source: ArmPieceSource) -> ArmPieceSource:
    return "showdown" if source == "ingame" else "ingame"


def _synthetic_ingame_mega_miss() -> _Retrieval:
    """In-game was not queried: it carries no Mega formes."""
    return _miss("ingame", "offline", "form_not_in_source")


def _fallback(
    requested: ArmPieceSource, used: ArmPieceSource, reason: ArmFallbackReason
) -> ArmFallback:
    return ArmFallback(requested, used, reason, reason)


# --------------------------------------------------------------------------
# Single anchor
# --------------------------------------------------------------------------


def _error(
    species: str,
    requested: str | None,
    kind: ArmErrorKind,
    message: str,
    *,
    exception_type: str | None = None,
    attempts: tuple[ArmAttempt, ...] = (),
) -> ArmTeammateResult:
    return ArmTeammateResult(
        status="error",
        anchor_id=to_id(species),
        anchor_name=species,
        requested_source=requested,
        used_source=None,
        method=None,
        value_kind=None,
        rows=None,
        raw_count=None,
        truncated=None,
        fallback=None,
        attempts=attempts,
        as_of=None,
        message=message,
        error_kind=kind,
        exception_type=exception_type,
    )


def _unavailable(
    species: str, requested: str, attempts: tuple[ArmAttempt, ...]
) -> ArmTeammateResult:
    return ArmTeammateResult(
        status="unavailable",
        anchor_id=to_id(species),
        anchor_name=species,
        requested_source=requested,
        used_source=None,
        method=None,
        value_kind=None,
        rows=None,
        raw_count=None,
        truncated=None,
        fallback=None,
        attempts=attempts,
        as_of=None,
    )


def _served(
    species: str,
    requested: str,
    r: _Retrieval,
    fallback: ArmFallback | None,
    attempts: tuple[ArmAttempt, ...],
) -> ArmTeammateResult:
    return ArmTeammateResult(
        status="available",
        anchor_id=to_id(species),
        anchor_name=r.name or species,
        requested_source=requested,
        used_source=r.source,
        method=r.method,
        value_kind="rank_only" if r.source == "ingame" else "conditional_percent",
        rows=r.rows,
        raw_count=r.raw_count,
        truncated=r.truncated,
        fallback=fallback,
        attempts=attempts,
        as_of=r.as_of,
        caveats=r.caveats,
        denominator=r.denominator,
    )


def _malformed_error(
    species: str,
    requested: str,
    r: _Retrieval,
    attempts: tuple[ArmAttempt, ...],
    tool: str,
    args: dict[str, Any],
) -> ArmTeammateResult:
    log_tool_call(
        tool,
        args,
        latency_ms=0.0,
        ok=False,
        error=f"malformed_offline_row:{r.exception_type}",
    )
    return _error(
        species,
        requested,
        "malformed_offline_row",
        ARM_MALFORMED_MSG,
        exception_type=r.exception_type,
        attempts=attempts,
    )


def arm_query_teammates(
    species: str,
    *,
    source: str,
    regulation: str = "champions",
    allow_live: bool = True,
    live_showdown_fetch: LiveShowdownFetch = fetch_live_showdown_detail,
) -> ArmTeammateResult:
    """Explicit-source teammate query with disclosed fallback (ADR-014 14a/14b)."""
    if source in BUILD_LEVEL_SOURCES:
        return ArmTeammateResult(
            status="deferred_build_surface",
            anchor_id=to_id(species),
            anchor_name=species,
            requested_source=source,
            used_source=None,
            method=None,
            value_kind=None,
            rows=None,
            raw_count=None,
            truncated=None,
            fallback=None,
            attempts=(),
            as_of=None,
            message=ARM_DEFERRED_MSG,
            error_kind="deferred_build_surface",
        )
    if source not in PIECE_SOURCES:
        return _error(
            species,
            source if isinstance(source, str) else None,
            "invalid_source",
            ARM_INVALID_SOURCE_MSG,
        )
    args = {"species": species, "source": source, "regulation": regulation}
    try:
        return _single_inner(
            species,
            source,  # type: ignore[arg-type]
            regulation,
            allow_live=allow_live,
            live_fetch=live_showdown_fetch,
            args=args,
        )
    except Exception as exc:
        log_tool_call(
            "arm.query_teammates",
            args,
            latency_ms=0.0,
            ok=False,
            error=f"unexpected_failure:{type(exc).__name__}",
        )
        return _error(
            species,
            source,
            "unexpected_failure",
            ARM_UNEXPECTED_MSG,
            exception_type=type(exc).__name__,
        )


def _single_inner(
    species: str,
    source: ArmPieceSource,
    regulation: str,
    *,
    allow_live: bool,
    live_fetch: LiveShowdownFetch,
    args: dict[str, Any],
) -> ArmTeammateResult:
    mega = is_mega_forme(species)
    tool = "arm.query_teammates"

    # First leg. In-game is not queried for a Mega: it has no Mega formes.
    if source == "ingame" and mega:
        first = _synthetic_ingame_mega_miss()
    else:
        first = _retrieve(
            source, species, regulation, allow_live=allow_live, live_fetch=live_fetch
        )
    if first.kind == "ok":
        return _served(species, source, first, None, (first.attempt,))
    if first.kind == "malformed":
        return _malformed_error(species, source, first, (), tool, args)

    # Exactly one hop. The second leg's result is final, so no loop is possible.
    second_source = _other(source)
    if second_source == "ingame" and mega:
        return _unavailable(
            species, source, (first.attempt, _synthetic_ingame_mega_miss().attempt)
        )
    second = _retrieve(
        second_source, species, regulation, allow_live=allow_live, live_fetch=live_fetch
    )
    if second.kind == "malformed":
        return _malformed_error(species, source, second, (first.attempt,), tool, args)
    attempts = (first.attempt, second.attempt)
    if second.kind == "ok":
        assert first.attempt.reason is not None
        fb = _fallback(source, second_source, first.attempt.reason)
        return _served(species, source, second, fb, attempts)
    return _unavailable(species, source, attempts)


# --------------------------------------------------------------------------
# Multi anchor
# --------------------------------------------------------------------------


def _multi_error(
    mode: ArmMultiMode,
    kind: ArmErrorKind,
    message: str,
    *,
    exception_type: str | None = None,
    attempts: tuple[ArmAttempt, ...] = (),
) -> ArmMultiTeammateResult:
    return ArmMultiTeammateResult(
        status="error",
        mode=mode,
        anchor_results=(),
        rows=None,
        unavailable_anchors=(),
        fallback=None,
        attempts=attempts,
        as_of=None,
        message=message,
        error_kind=kind,
        exception_type=exception_type,
    )


def arm_query_teammates_multi(
    species: Sequence[str],
    *,
    source: str,
    mode: str = "intersection",
    regulation: str = "champions",
    allow_live: bool = True,
    live_showdown_fetch: LiveShowdownFetch = fetch_live_showdown_detail,
) -> ArmMultiTeammateResult:
    """Multi-anchor query. One source for the whole query; anchors are never dropped."""
    safe_mode: ArmMultiMode = mode if mode in _MULTI_MODES else "intersection"  # type: ignore[assignment]
    if source in BUILD_LEVEL_SOURCES:
        return ArmMultiTeammateResult(
            status="deferred_build_surface",
            mode=safe_mode,
            anchor_results=(),
            rows=None,
            unavailable_anchors=(),
            fallback=None,
            attempts=(),
            as_of=None,
            message=ARM_DEFERRED_MSG,
            error_kind="deferred_build_surface",
        )
    if source not in PIECE_SOURCES:
        return _multi_error(safe_mode, "invalid_source", ARM_INVALID_SOURCE_MSG)
    if mode not in _MULTI_MODES:
        return _multi_error("intersection", "invalid_mode", ARM_INVALID_MODE_MSG)
    names = tuple(species)
    args = {"species": list(names), "source": source, "mode": mode, "regulation": regulation}
    try:
        return _multi_inner(
            names,
            source,  # type: ignore[arg-type]
            safe_mode,
            regulation,
            allow_live=allow_live,
            live_fetch=live_showdown_fetch,
            args=args,
        )
    except Exception as exc:
        log_tool_call(
            "arm.query_teammates_multi",
            args,
            latency_ms=0.0,
            ok=False,
            error=f"unexpected_failure:{type(exc).__name__}",
        )
        return _multi_error(
            safe_mode,
            "unexpected_failure",
            ARM_UNEXPECTED_MSG,
            exception_type=type(exc).__name__,
        )


def _tag(attempt: ArmAttempt, anchor_id: str) -> ArmAttempt:
    return replace(attempt, anchor_id=anchor_id)


def _date_key(ao: ArmAsOf | None) -> tuple[str, str] | None:
    if ao is None:
        return None
    day = ao.captured_on if ao.source == "ingame" else ao.period_end
    return (ao.source, day) if day else None


def _multi_inner(
    names: tuple[str, ...],
    source: ArmPieceSource,
    mode: ArmMultiMode,
    regulation: str,
    *,
    allow_live: bool,
    live_fetch: LiveShowdownFetch,
    args: dict[str, Any],
) -> ArmMultiTeammateResult:
    if mode == "team_level":
        return ArmMultiTeammateResult(
            status="deferred_build_surface",
            mode=mode,
            anchor_results=(),
            rows=None,
            unavailable_anchors=(),
            fallback=None,
            attempts=(),
            as_of=None,
            message=ARM_DEFERRED_MSG,
            error_kind="deferred_build_surface",
        )
    if not names:
        return ArmMultiTeammateResult(
            status="unavailable",
            mode=mode,
            anchor_results=(),
            rows=None,
            unavailable_anchors=(),
            fallback=None,
            attempts=(),
            as_of=None,
        )

    tool = "arm.query_teammates_multi"
    ids = tuple(to_id(n) for n in names)
    megas = tuple(is_mega_forme(n) for n in names)
    any_mega = any(megas)

    def run(src: ArmPieceSource) -> list[_Retrieval]:
        return [
            _retrieve(src, n, regulation, allow_live=allow_live, live_fetch=live_fetch)
            for n in names
        ]

    def bad(rs: list[_Retrieval], prior: tuple[ArmAttempt, ...]) -> ArmMultiTeammateResult:
        r = next(r for r in rs if r.kind == "malformed")
        log_tool_call(
            tool,
            args,
            latency_ms=0.0,
            ok=False,
            error=f"malformed_offline_row:{r.exception_type}",
        )
        return _multi_error(
            mode,
            "malformed_offline_row",
            ARM_MALFORMED_MSG,
            exception_type=r.exception_type,
            attempts=prior,
        )

    fallback: ArmFallback | None = None
    first_attempts: tuple[ArmAttempt, ...]

    # First leg (whole query on the requested source).
    if source == "ingame" and any_mega:
        first_attempts = tuple(
            _tag(_synthetic_ingame_mega_miss().attempt, i)
            for i, is_m in zip(ids, megas, strict=True)
            if is_m
        )
        hop_reason: ArmFallbackReason = "form_not_in_source"
        served = None
    else:
        first = run(source)
        if any(r.kind == "malformed" for r in first):
            return bad(first, ())
        first_attempts = tuple(
            _tag(r.attempt, i) for r, i in zip(first, ids, strict=True)
        )
        if all(r.kind == "ok" for r in first):
            served = first
            hop_reason = "no_row"  # unused
        else:
            served = None
            miss = next(r for r in first if r.kind == "miss")
            assert miss.attempt.reason is not None
            hop_reason = miss.attempt.reason

    # Exactly one whole-query hop; the second leg is final.
    if served is None:
        second_source = _other(source)
        if second_source == "ingame" and any_mega:
            extra = tuple(
                _tag(_synthetic_ingame_mega_miss().attempt, i)
                for i, is_m in zip(ids, megas, strict=True)
                if is_m
            )
            return ArmMultiTeammateResult(
                status="unavailable",
                mode=mode,
                anchor_results=(),
                rows=None,
                unavailable_anchors=ids,
                fallback=None,
                attempts=first_attempts + extra,
                as_of=None,
            )
        second = run(second_source)
        if any(r.kind == "malformed" for r in second):
            return bad(second, first_attempts)
        attempts_all = first_attempts + tuple(
            _tag(r.attempt, i) for r, i in zip(second, ids, strict=True)
        )
        missed = tuple(
            i for r, i in zip(second, ids, strict=True) if r.kind != "ok"
        )
        if missed:
            return ArmMultiTeammateResult(
                status="unavailable",
                mode=mode,
                anchor_results=(),
                rows=None,
                unavailable_anchors=missed,
                fallback=None,
                attempts=attempts_all,
                as_of=None,
            )
        served = second
        fallback = _fallback(source, second_source, hop_reason)
    else:
        attempts_all = first_attempts

    used = served[0].source
    anchor_results = tuple(
        _served(n, source, r, fallback, (_tag(r.attempt, i),))
        for n, r, i in zip(names, served, ids, strict=True)
    )
    keys = [_date_key(r.as_of) for r in served]
    uniq = {k for k in keys if k is not None}
    differ = len(uniq) > 1
    multi_as_of = ArmMultiAsOf(
        per_anchor=tuple(r.as_of for r in served),
        as_of_dates_differ=differ,
        note="anchor as-of dates differ across anchors" if differ else None,
    )

    if mode == "reverse_lookup":
        shared = _reverse_rows(ids, used, regulation)
        caveats = (
            "reverse lookup scans stored teammate lists that are cut off at the "
            "top entries, so the result is a lower bound",
            "an anchor appearing in a species' list does not mean the anchors "
            "were on the same team",
        )
    else:
        shared = _intersection_rows(anchor_results, names)
        caveats = (
            "ranks are within each anchor's own list, not joint team frequency",
        )

    shared.sort(
        key=lambda row: (
            row.min_conditional_pct is None,
            -(row.min_conditional_pct or 0.0),
            row.worst_rank,
            sum(item.rank for item in row.per_anchor),
            row.species_id,
        )
    )
    return ArmMultiTeammateResult(
        status="available",
        mode=mode,
        anchor_results=anchor_results,
        rows=tuple(shared),
        unavailable_anchors=(),
        fallback=fallback,
        attempts=attempts_all,
        as_of=multi_as_of,
        caveats=caveats,
        ordering=(
            "highest minimum conditional_pct, then lowest worst rank; "
            "rank-only evidence uses lowest worst rank"
        ),
    )


def _shared_row(
    sid: str,
    name: str,
    evidence: Sequence[tuple[str, int, float | None, ArmValueKind]],
) -> ArmSharedTeammate:
    pcts = [pct for _a, _r, pct, _k in evidence]
    kinds = {k for _a, _r, _p, k in evidence}
    return ArmSharedTeammate(
        species_id=sid,
        name=name,
        per_anchor=tuple(
            ArmSharedAnchorEvidence(a, r, p, k) for a, r, p, k in evidence
        ),
        worst_rank=max(r for _a, r, _p, _k in evidence),
        min_conditional_pct=(
            min(p for p in pcts if p is not None)
            if all(p is not None for p in pcts)
            else None
        ),
        attribution_status=_attribution_status(sid),
        value_kind="conditional_percent" if "conditional_percent" in kinds else "rank_only",
    )


def _intersection_rows(
    anchors: tuple[ArmTeammateResult, ...], names: tuple[str, ...]
) -> list[ArmSharedTeammate]:
    by_anchor = [{r.species_id: r for r in (a.rows or ())} for a in anchors]
    shared_ids = set(by_anchor[0]).intersection(*(set(m) for m in by_anchor[1:]))
    shared_ids.difference_update({lid for n in names for lid in lineage_ids(n)})
    return [
        _shared_row(
            sid,
            by_anchor[0][sid].name,
            [
                (a.anchor_id, m[sid].rank, m[sid].conditional_pct, m[sid].value_kind)
                for a, m in zip(anchors, by_anchor, strict=True)
            ],
        )
        for sid in shared_ids
    ]


def _reverse_rows(
    anchor_ids: tuple[str, ...], used: ArmPieceSource, regulation: str
) -> list[ArmSharedTeammate]:
    """Species whose own stored teammate list contains every anchor."""
    if used == "ingame":
        source_map = ingame_ladder_species_map(regulation)
        kind: ArmValueKind = "rank_only"
    else:
        source_map = showdown_species_map(regulation)
        kind = "conditional_percent"
    excluded = {lid for a in anchor_ids for lid in lineage_ids(a)}
    out: list[ArmSharedTeammate] = []
    for sid, row in source_map.items():
        if sid in excluded or not isinstance(row, dict):
            continue
        tm = row.get("teammates")
        if not isinstance(tm, list):
            continue
        pos: dict[str, tuple[int, float | None]] = {}
        for i, t in enumerate(tm, start=1):
            if isinstance(t, dict):
                tid = to_id(str(t.get("id") or t.get("name") or ""))
                try:
                    rank = int(t.get("rank") or i)
                except (TypeError, ValueError):
                    rank = i
                pct = _number(t.get("conditional_pct"))
            else:
                tid, rank, pct = to_id(str(t)), i, None
            if tid:
                pos.setdefault(tid, (rank, pct))
        if all(a in pos for a in anchor_ids):
            out.append(
                _shared_row(
                    sid,
                    str(row.get("name") or sid),
                    [(a, pos[a][0], pos[a][1], kind) for a in anchor_ids],
                )
            )
    return out


__all__ = [
    "ARM_MESSAGE_ALLOWLIST",
    "ArmDenominator",
    "ArmLiveFetchError",
    "arm_query_teammates",
    "arm_query_teammates_multi",
    "is_mega_forme",
    "legal_mega_forme_ids",
    "mega_capable_base_ids",
    "period_end_for_month",
]
