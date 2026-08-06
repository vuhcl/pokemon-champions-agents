"""Contingent-value category diff (ADR-016 Amendment 2026-07-26b).

Regulation-change mechanism only — no live trigger wired here.
"""

from __future__ import annotations

from typing import Any

from recommender.ids import to_id
from recommender.legality import load_snapshot, resolve_learnset

Category = str

WEATHER_SETTERS = {
    "drizzle": "weather_setter",
    "drought": "weather_setter",
    "sandstream": "weather_setter",
    "snowwarning": "weather_setter",
    "orichalcumpulse": "weather_setter",
    "desolateland": "weather_setter",
    "primordialsea": "weather_setter",
    "deltastream": "weather_setter",
}
TERRAIN_SETTERS = {
    "psychicsurge": "terrain_setter",
    "electricsurge": "terrain_setter",
    "grassysurge": "terrain_setter",
    "mistysurge": "terrain_setter",
    "hadronengine": "terrain_setter",
}
REDIRECT_MOVES = {"followme", "ragepowder"}


def _ability_categories(ability_name: str) -> set[Category]:
    aid = to_id(ability_name)
    out: set[Category] = set()
    if aid in WEATHER_SETTERS:
        out.add(WEATHER_SETTERS[aid])
    if aid in TERRAIN_SETTERS:
        out.add(TERRAIN_SETTERS[aid])
    return out


def categorize_champions_pool(snap: dict[str, Any] | None = None) -> dict[Category, list[str]]:
    """Tag legal Champions species by enabling categories."""
    snap = snap or load_snapshot()
    cats: dict[Category, list[str]] = {
        "terrain_setter": [],
        "weather_setter": [],
        "redirection": [],
        "priority_control": [],
    }
    for sid, entry in snap["species"].items():
        if entry.get("is_nonstandard") is not None or entry.get("tier") == "Illegal":
            continue
        for ab in (entry.get("abilities") or {}).values():
            if not isinstance(ab, str):
                continue
            for c in _ability_categories(ab):
                if sid not in cats[c]:
                    cats[c].append(sid)
        ls = resolve_learnset(snap, sid) or []
        if REDIRECT_MOVES & set(ls):
            cats["redirection"].append(sid)
        if "tailwind" in ls or "trickroom" in ls:
            if sid not in cats["priority_control"]:
                cats["priority_control"].append(sid)
    return cats


def diff_categories(
    mainline: dict[Category, list[str]],
    champions: dict[Category, list[str]],
    *,
    rare_threshold: int = 2,
) -> list[dict[str, Any]]:
    """Categories common in mainline but rare/absent in Champions."""
    findings: list[dict[str, Any]] = []
    for cat, main_ids in mainline.items():
        champ_ids = champions.get(cat) or []
        if len(main_ids) >= rare_threshold and len(champ_ids) < rare_threshold:
            findings.append(
                {
                    "category": cat,
                    "mainline_count": len(main_ids),
                    "champions_count": len(champ_ids),
                    "champions_species": list(champ_ids),
                }
            )
    return findings


# Hand fixture for Expanding Force / Psychic Terrain (ADR example).
EXPANDING_FORCE_FIXTURE = {
    "move": "expandingforce",
    "depends_on": "terrain_setter",
    "enabler_ability": "Psychic Surge",
    "note": "Expanding Force value contingent on Psychic Terrain; rare in Champions",
}
