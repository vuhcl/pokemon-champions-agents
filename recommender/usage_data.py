"""Load offline usage snapshots (in-game ladder + Showdown@1500)."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict

from recommender.ids import regulation_file_tag, to_id
from recommender.legality import load_snapshot as load_legality_snapshot
from recommender.species_forms import ingame_excluded_species_ids, item_mega_forme
from recommender.sp_convert import evs_to_sp
from recommender.state import PokemonSet, StatsTable

REPO_ROOT = Path(__file__).resolve().parents[1]
USAGE_DIR = REPO_ROOT / "data" / "usage"
TEAM_COMP_DIR = REPO_ROOT / "data" / "team-composition"

# Doubles coverage pool (no relevance_filter). Not Role Compendium's 20-30 scale.
TEAM_THREAT_N = 50

# Slot-level when relevance_filter set. Practical update from ADR-015a "handful" (3-5);
# architecture_decisions.md remains read-only — note in task summary only.
SLOT_THREAT_N = 10  # allowed range 5-10; default top of range

# Smogon convention: 1500+ = high-level ladder filter (casual play stripped).
# Confirmed 2026-06 gen9championsvgc2026regmb: 1_163_315 battles at 1500 — adequate.
SHOWDOWN_USAGE_RATING = 1500

_STAT_KEYS = ("hp", "atk", "def", "spa", "spd", "spe")

SetMatchSource = Literal["vgcpastes", "featured"]
SetMatchProvenance = Literal["vgcpastes", "featured"]


class SetMatchEntry(TypedDict):
    set: PokemonSet
    source: SetMatchSource
    provenance: SetMatchProvenance
    occurrence_count: NotRequired[int]
    date_shared_earliest: NotRequired[str]


SetMatchResult = list[SetMatchEntry]


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


@lru_cache(maxsize=1)
def ingame_excluded_ids() -> frozenset[str]:
    return ingame_excluded_species_ids(load_legality_snapshot())


def ingame_ladder_species_map(regulation: str = "champions-reg-mb") -> dict[str, Any]:
    """Raw in-game doubles ladder rows (rank/membership only — not build-safe).

    Includes mega-capable bases for popularity rank and threat-ladder membership.
    Do not use for move/item/spread build construction; use ingame_species_map()
    or Showdown for builds.
    """
    return (load_usage(regulation).get("ingame_doubles") or {}).get("species") or {}


def ingame_species_map(regulation: str = "champions-reg-mb") -> dict[str, Any]:
    raw = ingame_ladder_species_map(regulation)
    excluded = ingame_excluded_ids()
    if not excluded:
        return raw
    return {sid: row for sid, row in raw.items() if sid not in excluded}


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


def _nature_from_usage(entry: dict[str, Any]) -> str | None:
    spreads = entry.get("top_spreads") or []
    if spreads and spreads[0].get("nature"):
        return str(spreads[0]["nature"])
    return None


def calc_species_label(species: str, spec: dict[str, Any] | None = None) -> str:
    """Calc-service species label for a build (e.g. Aegislash → Aegislash-Shield)."""
    sid = to_id(species)
    entry = {"id": sid, "name": (spec or {}).get("species") or species}
    return _species_for_spec(entry, species)


def _species_for_spec(entry: dict[str, Any], fallback: str) -> str:
    """Calc-compatible species label: display name only when it to_id-matches the stored id."""
    sid = to_id(entry.get("id") or fallback)
    if sid == "aegislash":
        return "Aegislash-Shield"
    name = entry.get("name") or fallback
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
            elif nat := _nature_from_usage(entry):
                out["nature"] = nat
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
    if nat := _nature_from_usage(entry):
        out["nature"] = nat
    spread = _spread_from_usage(entry)
    if spread:
        out["evs"] = spread
    return out  # type: ignore[return-value]


def _iter_usage_ranked_items(entry: dict[str, Any]):
    """Usage-ranked item ids: featured_sets (4-move rows) then common_items."""
    seen: set[str] = set()
    for fs in entry.get("featured_sets") or []:
        real = _nonempty_moves(fs.get("moves") or [])
        if len(real) >= 4 and fs.get("item") and fs.get("item") != "Nothing":
            iid = to_id(fs["item"])
            if iid not in seen:
                seen.add(iid)
                yield _display_item(fs["item"])
    for row in entry.get("common_items") or []:
        iid = to_id(row["name"])
        if iid not in seen:
            seen.add(iid)
            yield _display_item(row["name"])


def pick_team_aware_usage_item(
    species: str,
    *,
    regulation: str = "champions-reg-mb",
    used: set[str],
    entry: dict[str, Any] | None = None,
    snap: dict[str, Any] | None = None,
) -> str | None:
    """First legal usage-ranked item not already on team_draft (Item Clause)."""
    from recommender.legality import is_item_legal, load_snapshot

    row = entry if entry is not None else species_usage(species, regulation=regulation)
    if not row:
        return None
    snap = snap or load_snapshot()
    for item in _iter_usage_ranked_items(row):
        if to_id(item) in used:
            continue
        if is_item_legal(snap, item):
            return item
    return None


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
    item: str | None,
    *,
    regulation: str = "champions-reg-mb",
) -> SetMatchResult:
    """Exact moves+item match: VGCPastes first, then synthetic featured_sets.

    ``item is None`` means unspecified (no exact match attempted).
    ``item == ""`` means explicitly no held item.
    Returns a ranked list (empty = miss; [0] = primary; [1:] = alternatives).
    """
    if item is None:
        return []
    want_moves = sorted(to_id(m) for m in moves)
    want_item = to_id(item)

    vgcpastes_hits = _match_vgcpastes(
        species, want_moves, want_item, item=item, regulation=regulation
    )
    if vgcpastes_hits:
        return vgcpastes_hits

    entry = species_usage(species, regulation=regulation)
    if not entry:
        return []
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
            return [
                {
                    "set": out,
                    "source": "featured",
                    "provenance": "featured",
                }
            ]
    return []


@lru_cache(maxsize=4)
def load_vgcpastes_builds(regulation: str = "champions-reg-mb") -> dict[str, Any]:
    tag = regulation_file_tag(regulation)
    path = TEAM_COMP_DIR / f"{tag}.vgcpastes-builds.v1.json"
    if not path.exists():
        return {"meta": {}, "teams": [], "cores": []}
    return json.loads(path.read_text())


def normalize_member_evs(raw: dict[str, Any] | None) -> dict[str, int] | None:
    """Normalize paste EVs to Champions SP (0–32, sum 66). None if unusable."""
    if not isinstance(raw, dict):
        return None
    try:
        spread = {stat: int(raw.get(stat, 0)) for stat in _STAT_KEYS}
    except (TypeError, ValueError):
        return None
    if any(v > 32 for v in spread.values()):
        spread = evs_to_sp(spread)
    if sum(spread.values()) != 66 or any(v < 0 or v > 32 for v in spread.values()):
        return None
    return spread


def parse_date_shared(raw: str | None) -> date | None:
    """Parse VGCPastes ``date_shared`` strings like ``12 Aug 2026``."""
    if not raw or not str(raw).strip():
        return None
    try:
        return datetime.strptime(str(raw).strip(), "%d %b %Y").date()
    except ValueError:
        return None


def vgcpastes_lookup_species_ids(species: str, item: str | None) -> tuple[str, ...]:
    """Species ids to scan in VGCPastes (base + mega label when holding a stone)."""
    requested = to_id(species)
    snap = {"species": _legality_species()}
    ent = snap["species"].get(requested) or {}
    base = ent.get("base_species_id") or requested
    ids: list[str] = []
    for candidate in (requested, base):
        if candidate and candidate not in ids:
            ids.append(candidate)
    item_id = to_id(item) if item else ""
    if item_id:
        mega = item_mega_forme(item_id, base, snap)
        if mega and mega not in ids:
            ids.append(mega)
    return tuple(ids)


def _match_vgcpastes(
    species: str,
    want_moves: list[str],
    want_item: str,
    *,
    item: str,
    regulation: str,
) -> SetMatchResult:
    data = load_vgcpastes_builds(regulation)
    lookup_ids = set(vgcpastes_lookup_species_ids(species, item))
    # bucket_key -> list of (parsed_date_or_max, member, team)
    buckets: dict[
        tuple[str, tuple[int, ...] | None],
        list[tuple[date | None, dict[str, Any]]],
    ] = defaultdict(list)

    for team in data.get("teams") or []:
        team_date = parse_date_shared(team.get("date_shared"))
        for member in team.get("members") or []:
            sid = to_id(str(member.get("species") or ""))
            if sid not in lookup_ids:
                continue
            moves = member.get("moves") or []
            if len(moves) != 4 or not all(moves):
                continue
            mem_moves = sorted(to_id(m) for m in moves)
            mem_item = to_id(member.get("item") or "")
            if mem_moves != want_moves or mem_item != want_item:
                continue
            spread = normalize_member_evs(member.get("evs"))
            nature = str(member.get("nature") or "")
            spread_key: tuple[int, ...] | None = (
                tuple(spread[s] for s in _STAT_KEYS) if spread is not None else None
            )
            buckets[(nature, spread_key)].append((team_date, member))

    if not buckets:
        return []

    ranked: list[tuple[int, date, tuple[str, tuple[int, ...] | None], dict[str, Any]]] = []
    far_future = date(9999, 12, 31)
    for key, rows in buckets.items():
        count = len(rows)
        dates = [d for d, _ in rows if d is not None]
        earliest = min(dates) if dates else far_future
        member = rows[0][1]
        ranked.append((count, earliest, key, member))

    # occurrence desc, then earliest date asc
    ranked.sort(key=lambda r: (-r[0], r[1]))

    out: SetMatchResult = []
    for count, earliest, key, member in ranked:
        nature, spread_key = key
        built: PokemonSet = {
            "species": str(member.get("species_display") or member.get("species") or species),
            "moves": [str(m) for m in (member.get("moves") or [])][:4],
        }
        raw_item = member.get("item")
        if raw_item:
            built["item"] = _display_item(str(raw_item))
        else:
            built["item"] = ""
        if member.get("ability"):
            built["ability"] = _display_ability(str(member["ability"]))
        if nature:
            built["nature"] = nature
        if spread_key is not None:
            built["evs"] = {s: spread_key[i] for i, s in enumerate(_STAT_KEYS)}
        entry: SetMatchEntry = {
            "set": built,
            "source": "vgcpastes",
            "provenance": "vgcpastes",
            "occurrence_count": count,
        }
        if earliest != far_future:
            entry["date_shared_earliest"] = earliest.isoformat()
        out.append(entry)
    return out


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
    if not raw:
        return ""
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
