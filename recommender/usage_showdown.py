"""Showdown / MunchStats VGC Reg M-B per-species fetch (form-separated).

Same source as scripts/extract_usage/fetch_usage_mb.py. Returns None on failure.
"""

from __future__ import annotations

import urllib.parse
from typing import Any

from recommender.ids import to_id
from recommender.usage_cbd import fetch_json
from recommender.usage_data import SHOWDOWN_USAGE_RATING, showdown_species_map

SHOWDOWN_FORMAT = "gen9championsvgc2026regmb"
SHOWDOWN_MONTH = "2026-06"
MUNCH_BASE = (
    f"https://raw.githubusercontent.com/PizzaTimeJoshua/munchstats/main/"
    f"stats/{SHOWDOWN_MONTH}/{SHOWDOWN_FORMAT}/{SHOWDOWN_USAGE_RATING}"
)


def _munch_moves(detail: dict[str, Any]) -> list[dict[str, Any]]:
    raw = detail.get("Moves") or {}
    if not isinstance(raw, dict):
        return []
    items: list[tuple[str, float]] = []
    for name, w in raw.items():
        try:
            items.append((str(name), float(w)))
        except (TypeError, ValueError):
            continue
    items.sort(key=lambda x: -x[1])
    total = sum(w for _, w in items) or 1.0
    return [{"name": n, "pct": round(100.0 * w / total, 3)} for n, w in items[:12]]


def _munch_items(detail: dict[str, Any]) -> list[dict[str, Any]]:
    raw = detail.get("Items") or {}
    if not isinstance(raw, dict):
        return []
    items: list[tuple[str, float]] = []
    for name, w in raw.items():
        try:
            items.append((str(name), float(w)))
        except (TypeError, ValueError):
            continue
    items.sort(key=lambda x: -x[1])
    total = sum(w for _, w in items) or 1.0
    return [{"name": n, "pct": round(100.0 * w / total, 3)} for n, w in items[:12]]


def fetch_showdown_vgc_species(display_name: str) -> dict[str, Any] | None:
    """Offline showdown_vgc_mb exact id, else MunchStats live. None on miss/error."""
    if not display_name or not str(display_name).strip():
        return None
    sid = to_id(display_name)
    offline = showdown_species_map().get(sid)
    if isinstance(offline, dict):
        return offline
    try:
        index = fetch_json(f"{MUNCH_BASE}/_index.json")
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
        detail = fetch_json(f"{MUNCH_BASE}/{urllib.parse.quote(display)}.json")
    except Exception:
        return None
    if not isinstance(detail, dict):
        return {
            "name": display,
            "id": sid,
            "usage_pct": usage * 100.0,
            "common_moves": [],
            "common_abilities": [],
            "common_items": [],
            "featured_sets": [],
            "source": "munchstats-showdown",
        }
    return {
        "name": display,
        "id": sid,
        "usage_pct": usage * 100.0,
        "common_moves": _munch_moves(detail),
        "common_abilities": [],
        "common_items": _munch_items(detail),
        "featured_sets": [],
        "source": "munchstats-showdown",
    }
