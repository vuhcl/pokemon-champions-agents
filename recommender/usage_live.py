"""Shared, bounded live usage fetch for ADR-014 structured-source exceptions."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import Any, NamedTuple

from recommender.ids import regulation_file_tag, to_id
from recommender.regulation_registry import REGULATIONS
from recommender.tool_log import log_tool_call, timed_tool_call
from recommender.usage_data import load_usage, showdown_species_map

_UA = "pokemon-champions-agents/0.1"
_LIVE_FETCH_ATTEMPTS = 3
_LIVE_FETCH_BACKOFF_S = (0.2, 0.4)
_CACHE_MAX = 128

JsonValue = dict[str, Any] | list[Any]
JsonFetch = Callable[[str], JsonValue | None]


class LiveFetchError(Exception):
    """Transport / malformed-body failure — not a cacheable miss."""


class LiveTuple(NamedTuple):
    """Live fetch tuple; slot order is the contract of ``_live_format_for``."""

    month: str
    format_id: str
    rating: int


@dataclass(frozen=True)
class LiveDeferral:
    """A regulation with no live tuple, and why (never a silent None)."""

    tag: str
    reason: str
    decided_in: str  # "computed" or the amendment/PR that recorded the deferral


# Deliberate, owner-decided deferrals only. Computed failures never belong here.
RECORDED_DEFERRALS: dict[str, LiveDeferral] = {}

_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def live_tuple_for(tag: str) -> LiveTuple | LiveDeferral:
    """Derive a regulation's live tuple (ADR-014 Amendment 2026-10-14b).

    Format from the registry; month and rating from the offline Showdown
    snapshot's own meta. Exact tag only: no other regulation's tuple is used.
    """
    recorded = RECORDED_DEFERRALS.get(tag)
    if recorded is not None:
        return recorded
    expected = (REGULATIONS.get(tag) or {}).get("showdown_format")
    if not expected:
        return LiveDeferral(tag, "no_registered_showdown_format", "computed")
    if not showdown_species_map(tag):
        return LiveDeferral(tag, "no_showdown_snapshot", "computed")
    meta = load_usage(tag).get("meta") or {}
    if meta.get("showdown_format") != expected:
        return LiveDeferral(tag, "format_mismatch", "computed")
    month = meta.get("showdown_month")
    if not isinstance(month, str) or not _MONTH.match(month):
        return LiveDeferral(tag, "meta_month_invalid", "computed")
    rating = meta.get("showdown_rating")
    if isinstance(rating, bool) or not isinstance(rating, int) or rating <= 0:
        return LiveDeferral(tag, "meta_rating_invalid", "computed")
    return LiveTuple(month, str(expected), rating)


def _live_format_for(regulation: str) -> tuple[str, str, int] | None:
    """Exact tag only — no archive walk (M-C must not resolve to M-B live).

    Bare ``champions`` (the product mod name the graph passes as
    ``regulation_mod``) is unsupported: it never resolves to a tuple.
    """
    if regulation.strip().lower() == "champions":
        return None
    try:
        result = live_tuple_for(regulation_file_tag(regulation))
    except ValueError:
        return None
    return tuple(result) if isinstance(result, LiveTuple) else None


def fetch_json(
    url: str,
    *,
    turn: int | None = None,
    thread_id: str | None = None,
) -> JsonValue | None:
    """Fetch JSON. HTTP 4xx → None; transient fails retry then raise LiveFetchError."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    last_exc: BaseException | None = None
    retries_used = 0
    t0 = time.perf_counter()
    for attempt in range(_LIVE_FETCH_ATTEMPTS):
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read().decode()
            try:
                result: JsonValue = json.loads(raw)
            except json.JSONDecodeError as exc:
                log_tool_call(
                    "fetch_json",
                    {"url": url},
                    latency_ms=(time.perf_counter() - t0) * 1000,
                    ok=False,
                    retries=retries_used,
                    error="JSONDecodeError",
                    turn=turn,
                    thread_id=thread_id,
                )
                raise LiveFetchError(f"invalid JSON from {url}") from exc
            log_tool_call(
                "fetch_json",
                {"url": url},
                latency_ms=(time.perf_counter() - t0) * 1000,
                ok=True,
                retries=retries_used,
                turn=turn,
                thread_id=thread_id,
            )
            return result
        except urllib.error.HTTPError as exc:
            # HTTPError is a URLError subclass — handle before URLError.
            code = exc.code
            try:
                exc.read()
            except Exception:
                pass
            if 400 <= code < 500:
                log_tool_call(
                    "fetch_json",
                    {"url": url, "http_status": code},
                    latency_ms=(time.perf_counter() - t0) * 1000,
                    ok=True,
                    retries=retries_used,
                    turn=turn,
                    thread_id=thread_id,
                )
                return None
            last_exc = exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_exc = exc
        if attempt + 1 >= _LIVE_FETCH_ATTEMPTS:
            break
        time.sleep(_LIVE_FETCH_BACKOFF_S[min(attempt, len(_LIVE_FETCH_BACKOFF_S) - 1)])
        retries_used += 1
    log_tool_call(
        "fetch_json",
        {"url": url},
        latency_ms=(time.perf_counter() - t0) * 1000,
        ok=False,
        retries=retries_used,
        error=type(last_exc).__name__ if last_exc else "LiveFetchError",
        turn=turn,
        thread_id=thread_id,
    )
    raise LiveFetchError(f"live fetch failed for {url}") from last_exc


def supports_live_usage(regulation: str) -> bool:
    return _live_format_for(regulation) is not None


def _cache_get(cache: OrderedDict[Hashable, Any], key: Hashable) -> Any | None:
    if key not in cache:
        return None
    cache.move_to_end(key)
    return cache[key]


def _cache_put(cache: OrderedDict[Hashable, Any], key: Hashable, value: Any) -> None:
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > _CACHE_MAX:
        cache.popitem(last=False)


_CBD_CACHE: OrderedDict[Hashable, dict[str, Any] | None] = OrderedDict()
_SHOWDOWN_CACHE: OrderedDict[Hashable, dict[str, Any] | None] = OrderedDict()


def fetch_live_cbd_battle(
    species: str,
    fetcher: JsonFetch = fetch_json,
    *,
    turn: int | None = None,
    thread_id: str | None = None,
) -> dict[str, Any] | None:
    use_cache = fetcher is fetch_json
    key: Hashable = (species,)
    if use_cache and key in _CBD_CACHE:
        return _cache_get(_CBD_CACHE, key)

    def _run() -> dict[str, Any] | None:
        url = (
            "https://championsbattledata.com/api/battle/Doubles/"
            f"{urllib.parse.quote(species.strip())}?season=Current"
        )
        try:
            payload = fetcher(url)
        except LiveFetchError:
            return None
        result = payload if isinstance(payload, dict) else None
        if use_cache:
            _cache_put(_CBD_CACHE, key, result)
        return result

    return timed_tool_call(
        "fetch_live_cbd_battle",
        {"species": species},
        _run,
        turn=turn,
        thread_id=thread_id,
    )


def fetch_live_cbd_battle_cache_clear() -> None:
    _CBD_CACHE.clear()


fetch_live_cbd_battle.cache_clear = fetch_live_cbd_battle_cache_clear  # type: ignore[attr-defined]


def fetch_live_showdown_detail(
    species: str,
    regulation: str = "champions",
    fetcher: JsonFetch = fetch_json,
    *,
    turn: int | None = None,
    thread_id: str | None = None,
) -> dict[str, Any] | None:
    """Fetch one exact-form MunchStats record; legitimate misses are cached."""
    use_cache = fetcher is fetch_json
    key: Hashable = (species, regulation)
    if use_cache and key in _SHOWDOWN_CACHE:
        return _cache_get(_SHOWDOWN_CACHE, key)

    def _run() -> dict[str, Any] | None:
        live_format = _live_format_for(regulation)
        if live_format is None:
            result = None
            if use_cache:
                _cache_put(_SHOWDOWN_CACHE, key, result)
            return result
        month, format_id, rating = live_format
        base = (
            "https://raw.githubusercontent.com/PizzaTimeJoshua/munchstats/main/"
            f"stats/{month}/{format_id}/{rating}"
        )
        try:
            index = fetcher(f"{base}/_index.json")
        except LiveFetchError:
            return None
        pokemon = index.get("pokemon") if isinstance(index, dict) else None
        display = next(
            (
                str(name)
                for name in (pokemon or {})
                if to_id(str(name)) == to_id(species)
            ),
            None,
        )
        if not display:
            result = None
            if use_cache:
                _cache_put(_SHOWDOWN_CACHE, key, result)
            return result
        try:
            detail = fetcher(f"{base}/{urllib.parse.quote(display)}.json")
        except LiveFetchError:
            return None
        result = detail if isinstance(detail, dict) else None
        if use_cache:
            _cache_put(_SHOWDOWN_CACHE, key, result)
        return result

    return timed_tool_call(
        "fetch_live_showdown_detail",
        {"species": species, "regulation": regulation},
        _run,
        turn=turn,
        thread_id=thread_id,
    )


def fetch_live_showdown_detail_cache_clear() -> None:
    _SHOWDOWN_CACHE.clear()


fetch_live_showdown_detail.cache_clear = (  # type: ignore[attr-defined]
    fetch_live_showdown_detail_cache_clear
)
