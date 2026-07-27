"""Load offline Pikalytics usage snapshot."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from recommender.ids import regulation_file_tag, to_id
from recommender.state import PokemonSet, StatsTable

REPO_ROOT = Path(__file__).resolve().parents[1]
USAGE_DIR = REPO_ROOT / "data" / "usage"


@lru_cache(maxsize=4)
def load_usage(regulation: str = "champions-reg-mb") -> dict[str, Any]:
    tag = regulation_file_tag(regulation)
    path = USAGE_DIR / f"{tag}.v1.json"
    if not path.exists():
        return {"meta": {}, "species": {}}
    return json.loads(path.read_text())


def species_usage(species: str, *, regulation: str = "champions-reg-mb") -> dict[str, Any] | None:
    snap = load_usage(regulation)
    return snap.get("species", {}).get(to_id(species))


def _spread_from_usage(entry: dict[str, Any]) -> StatsTable | None:
    spreads = entry.get("top_spreads") or []
    if not spreads:
        return None
    evs = spreads[0].get("evs") or {}
    return {
        "hp": int(evs.get("hp", 0)),
        "atk": int(evs.get("atk", 0)),
        "def": int(evs.get("def", 0)),
        "spa": int(evs.get("spa", 0)),
        "spd": int(evs.get("spd", 0)),
        "spe": int(evs.get("spe", 0)),
    }


def featured_or_common_set(species: str, *, regulation: str = "champions-reg-mb") -> PokemonSet | None:
    """Most representative set: first featured with 4 moves, else top common moves+item."""
    entry = species_usage(species, regulation=regulation)
    if not entry:
        return None
    for fs in entry.get("featured_sets") or []:
        moves = fs.get("moves") or []
        if len(moves) >= 4 and fs.get("item") and fs.get("item") != "Nothing":
            out: PokemonSet = {
                "species": entry.get("name") or species,
                "item": fs["item"],
                "moves": moves[:4],
            }
            if fs.get("ability"):
                out["ability"] = fs["ability"]
            spread = _spread_from_usage(entry)
            if spread:
                out["evs"] = spread
            return out
    moves = [m["name"] for m in (entry.get("common_moves") or [])[:4]]
    items = entry.get("common_items") or []
    abilities = entry.get("common_abilities") or []
    if not moves or not items:
        return None
    out = {
        "species": entry.get("name") or species,
        "item": items[0]["name"],
        "moves": moves,
    }
    if abilities:
        out["ability"] = abilities[0]["name"]
    spread = _spread_from_usage(entry)
    if spread:
        out["evs"] = spread
    return out  # type: ignore[return-value]


def find_set_matching(
    species: str,
    moves: list[str],
    item: str,
    *,
    regulation: str = "champions-reg-mb",
) -> PokemonSet | None:
    """Exact moves+item match against featured sets."""
    entry = species_usage(species, regulation=regulation)
    if not entry:
        return None
    want_moves = sorted(to_id(m) for m in moves)
    want_item = to_id(item)
    for fs in entry.get("featured_sets") or []:
        fs_moves = sorted(to_id(m) for m in (fs.get("moves") or []))
        fs_item = to_id(fs.get("item") or "")
        if fs_moves == want_moves and fs_item == want_item:
            out: PokemonSet = {
                "species": entry.get("name") or species,
                "item": fs.get("item") or item,
                "moves": list(fs.get("moves") or moves),
            }
            if fs.get("ability"):
                out["ability"] = fs["ability"]
            spread = _spread_from_usage(entry)
            if spread:
                out["evs"] = spread
            return out
    return None
