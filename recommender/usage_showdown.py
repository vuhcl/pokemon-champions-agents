"""Showdown / MunchStats VGC per-species fetch (form-separated).

Offline snapshot first. Live miss uses MunchStats with the snapshot's
month/format/rating and no move/item cap. Returns None on failure.
"""

from __future__ import annotations

import urllib.parse
from typing import Any

from recommender.ids import to_id
from recommender.usage_cbd import fetch_json
from recommender.usage_chaos import (
    chaos_weights_to_common,
    detail_raw_count,
    showdown_source_params,
    usage_pct_from_chaos,
)
from recommender.usage_data import showdown_species_map


def _munch_moves(detail: dict[str, Any]) -> list[dict[str, Any]]:
    return chaos_weights_to_common(
        detail.get("Moves"), raw_count=detail_raw_count(detail)
    )


def _munch_items(detail: dict[str, Any]) -> list[dict[str, Any]]:
    return chaos_weights_to_common(
        detail.get("Items"), raw_count=detail_raw_count(detail)
    )


def fetch_showdown_vgc_species(display_name: str) -> dict[str, Any] | None:
    """Offline showdown_vgc_mb exact id, else MunchStats live. None on miss/error."""
    if not display_name or not str(display_name).strip():
        return None
    sid = to_id(display_name)
    offline = showdown_species_map().get(sid)
    if isinstance(offline, dict):
        return offline
    params = showdown_source_params()
    base = (
        "https://raw.githubusercontent.com/PizzaTimeJoshua/munchstats/main/"
        f"stats/{params['month']}/{params['format_id']}/{params['rating']}"
    )
    try:
        index = fetch_json(f"{base}/_index.json")
    except Exception:
        return None
    if not isinstance(index, dict):
        return None
    poke = index.get("pokemon") or {}
    display: str | None = None
    usage = 0.0
    for name, meta in poke.items():
        if to_id(name) == sid:
            display = str(name)
            usage = float((meta or {}).get("usage") or 0.0)
            break
    if not display:
        return None
    try:
        detail = fetch_json(f"{base}/{urllib.parse.quote(display)}.json")
    except Exception:
        return None
    if not isinstance(detail, dict):
        return {
            "name": display,
            "id": sid,
            "usage_pct": usage * 100.0 if usage <= 1.0 else usage,
            "common_moves": [],
            "common_abilities": [],
            "common_items": [],
            "featured_sets": [],
            "source": "munchstats-showdown",
        }
    return {
        "name": display,
        "id": sid,
        "usage_pct": usage_pct_from_chaos({"usage": usage}),
        "common_moves": _munch_moves(detail),
        "common_abilities": [],
        "common_items": _munch_items(detail),
        "featured_sets": [],
        "source": "munchstats-showdown",
    }
