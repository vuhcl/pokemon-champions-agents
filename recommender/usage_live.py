"""Shared, bounded live usage fetch for ADR-014 structured-source exceptions."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from functools import lru_cache
from typing import Any

from recommender.ids import regulation_file_tag, to_id

_UA = "pokemon-champions-agents/0.1"
_LIVE_FORMATS = {
    "champions-reg-mb": (
        "2026-06",
        "gen9championsvgc2026regmb",
        1500,
    )
}

JsonValue = dict[str, Any] | list[Any]
JsonFetch = Callable[[str], JsonValue | None]


def fetch_json(url: str) -> JsonValue | None:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode())
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
        OSError,
    ):
        return None


def supports_live_usage(regulation: str) -> bool:
    try:
        return regulation_file_tag(regulation) in _LIVE_FORMATS
    except ValueError:
        return False


@lru_cache(maxsize=128)
def fetch_live_cbd_battle(
    species: str, fetcher: JsonFetch = fetch_json
) -> dict[str, Any] | None:
    url = (
        "https://championsbattledata.com/api/battle/Doubles/"
        f"{urllib.parse.quote(species.strip())}?season=Current"
    )
    payload = fetcher(url)
    return payload if isinstance(payload, dict) else None


@lru_cache(maxsize=128)
def fetch_live_showdown_detail(
    species: str,
    regulation: str = "champions",
    fetcher: JsonFetch = fetch_json,
) -> dict[str, Any] | None:
    """Fetch one exact-form MunchStats record; misses and failures are cached."""
    if not supports_live_usage(regulation):
        return None
    tag = regulation_file_tag(regulation)
    live_format = _LIVE_FORMATS.get(tag)
    if live_format is None:
        return None
    month, format_id, rating = live_format
    base = (
        "https://raw.githubusercontent.com/PizzaTimeJoshua/munchstats/main/"
        f"stats/{month}/{format_id}/{rating}"
    )
    index = fetcher(f"{base}/_index.json")
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
        return None
    detail = fetcher(f"{base}/{urllib.parse.quote(display)}.json")
    return detail if isinstance(detail, dict) else None
