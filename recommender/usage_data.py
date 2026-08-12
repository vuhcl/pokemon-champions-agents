"""Load offline usage snapshots (in-game ladder + Showdown@1500)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from recommender.ids import regulation_file_tag, to_id
from recommender.state import PokemonSet, StatsTable

REPO_ROOT = Path(__file__).resolve().parents[1]
USAGE_DIR = REPO_ROOT / "data" / "usage"

# Doubles coverage pool (no relevance_filter). Not Role Compendium's 20-30 scale.
TEAM_THREAT_N = 50

# Slot-level when relevance_filter set. Practical update from ADR-015a "handful" (3-5);
# architecture_decisions.md remains read-only — note in task summary only.
SLOT_THREAT_N = 10  # allowed range 5-10; default top of range

# Smogon convention: 1500+ = high-level ladder filter (casual play stripped).
# Confirmed 2026-06 gen9championsvgc2026regmb: 1_163_315 battles at 1500 — adequate.
SHOWDOWN_USAGE_RATING = 1500


@lru_cache(maxsize=4)
def load_usage(regulation: str = "champions-reg-mb") -> dict[str, Any]:
    tag = regulation_file_tag(regulation)
    path = USAGE_DIR / f"{tag}.v1.json"
    if not path.exists():
        return {"meta": {}, "species": {}, "ingame_doubles": {"species": {}}, "showdown_vgc_mb": {"species": {}}}
    return json.loads(path.read_text())


def species_usage(species: str, *, regulation: str = "champions-reg-mb") -> dict[str, Any] | None:
    snap = load_usage(regulation)
    return snap.get("species", {}).get(to_id(species))


def ingame_species_map(regulation: str = "champions-reg-mb") -> dict[str, Any]:
    snap = load_usage(regulation)
    return (snap.get("ingame_doubles") or {}).get("species") or {}


def showdown_species_map(regulation: str = "champions-reg-mb") -> dict[str, Any]:
    snap = load_usage(regulation)
    return (snap.get("showdown_vgc_mb") or {}).get("species") or {}


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


def _species_for_spec(entry: dict[str, Any], fallback: str) -> str:
    """Calc-compatible species label: display name only when it to_id-matches the stored id."""
    name = entry.get("name") or fallback
    sid = to_id(entry.get("id") or fallback)
    if to_id(name) == sid:
        return name
    legal = (_legality_species().get(sid) or {}).get("name")
    if legal:
        return str(legal)
    return sid


def _nonempty_moves(names: Any) -> list[str]:
    """Skip blank chaos keys, then display-map, cap at 4."""
    out: list[str] = []
    for n in names:
        if n is None or not str(n).strip():
            continue
        out.append(_display_move(str(n)))
        if len(out) >= 4:
            break
    return out


def _set_from_entry(entry: dict[str, Any], species: str) -> PokemonSet | None:
    for fs in entry.get("featured_sets") or []:
        real = _nonempty_moves(fs.get("moves") or [])
        if len(real) >= 4 and fs.get("item") and fs.get("item") != "Nothing":
            out: PokemonSet = {
                "species": _species_for_spec(entry, species),
                "item": _display_item(fs["item"]),
                "moves": real,
            }
            if fs.get("ability"):
                out["ability"] = _display_ability(fs["ability"])
            if fs.get("nature"):
                out["nature"] = fs["nature"]
            spread = _spread_from_usage(entry)
            if spread:
                out["evs"] = spread
            return out
    moves = _nonempty_moves(m["name"] for m in (entry.get("common_moves") or []))
    items = entry.get("common_items") or []
    abilities = entry.get("common_abilities") or []
    if not moves or not items:
        return None
    out = {
        "species": _species_for_spec(entry, species),
        "item": _display_item(items[0]["name"]),
        "moves": moves,
    }
    if abilities:
        out["ability"] = _display_ability(abilities[0]["name"])
    spread = _spread_from_usage(entry)
    if spread:
        out["evs"] = spread
    return out  # type: ignore[return-value]


def featured_or_common_set(species: str, *, regulation: str = "champions-reg-mb") -> PokemonSet | None:
    """Most representative set: first featured with 4 moves, else top common moves+item."""
    entry = species_usage(species, regulation=regulation)
    if not entry:
        return None
    return _set_from_entry(entry, species)


def set_from_showdown(species: str, *, regulation: str = "champions-reg-mb") -> PokemonSet | None:
    entry = showdown_species_map(regulation).get(to_id(species))
    if not entry:
        return None
    return _set_from_entry(entry, species)


def set_from_ingame(species: str, *, regulation: str = "champions-reg-mb") -> PokemonSet | None:
    entry = ingame_species_map(regulation).get(to_id(species))
    if not entry:
        return None
    return _set_from_entry(entry, species)


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
                "species": _species_for_spec(entry, species),
                "item": _display_item(fs.get("item") or item),
                "moves": _nonempty_moves(fs.get("moves") or moves),
            }
            if fs.get("ability"):
                out["ability"] = _display_ability(fs["ability"])
            spread = _spread_from_usage(entry)
            if spread:
                out["evs"] = spread
            return out
    return None


@lru_cache(maxsize=1)
def _legality_species() -> dict[str, Any]:
    path = REPO_ROOT / "data" / "legality" / "champions.v1.json"
    if not path.exists():
        return {}
    return (json.loads(path.read_text()).get("species")) or {}


@lru_cache(maxsize=1)
def _legality_blob() -> dict[str, Any]:
    path = REPO_ROOT / "data" / "legality" / "champions.v1.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


@lru_cache(maxsize=1)
def _ability_display() -> dict[str, str]:
    out: dict[str, str] = {}
    for ent in _legality_species().values():
        for name in (ent.get("abilities") or {}).values():
            if isinstance(name, str) and name:
                out[to_id(name)] = name
    return out


def _display_item(raw: str) -> str:
    ent = (_legality_blob().get("items") or {}).get(to_id(raw))
    return (ent or {}).get("name") or raw


def _display_move(raw: str) -> str:
    ent = (_legality_blob().get("moves") or {}).get(to_id(raw))
    return (ent or {}).get("name") or raw


def _display_ability(raw: str) -> str:
    return _ability_display().get(to_id(raw), raw)


def lineage_ids(ladder_species: str) -> list[str]:
    """Base id plus legality children, even when called with an exact child form."""
    requested = to_id(ladder_species)
    base = (_legality_species().get(requested) or {}).get("base_species_id") or requested
    kids = [base]
    for sid, ent in _legality_species().items():
        if ent.get("base_species_id") == base and sid not in kids:
            kids.append(sid)
    return kids
