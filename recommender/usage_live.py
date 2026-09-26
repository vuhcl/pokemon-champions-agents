"""Shared, bounded live usage fetch for ADR-014 structured-source exceptions."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Any

from recommender.ids import regulation_lookup_chain, to_id
from recommender.tool_log import log_tool_call, timed_tool_call

_UA = "pokemon-champions-agents/0.1"
_LIVE_FORMATS = {
    "champions-reg-mb": (
        "2026-06",
        "gen9championsvgc2026regmb",
        1500,
    )
}
_LIVE_FETCH_ATTEMPTS = 3
_LIVE_FETCH_BACKOFF_S = (0.2, 0.4)
_CACHE_MAX = 128

JsonValue = dict[str, Any] | list[Any]
JsonFetch = Callable[[str], JsonValue | None]


class LiveFetchError(Exception):
    """Transport / malformed-body failure — not a cacheable miss."""


def _live_format_for(regulation: str) -> tuple[str, str, int] | None:
    """Newest→older walk until a tag has a live MunchStats tuple (usage lag)."""
    try:
        for tag in regulation_lookup_chain(regulation):
            hit = _LIVE_FORMATS.get(tag)
            if hit is not None:
                return hit
    except ValueError:
        return None
    return None


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
