"""Champions Battle Data (CBD) Doubles fetch/parse — shared by snapshot extract + construct.

ADR-014 Amendment 2026-08-05a: structured source, known parser. Returns None on failure.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from recommender.ids import to_id

CBD_API = "https://championsbattledata.com"
UA = "pokemon-champions-agents/0.1"


def fetch_json(url: str) -> dict[str, Any] | list[Any] | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def pct_rows(rows: list[dict[str, Any]], category: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        if r.get("category") != category:
            continue
        name = (r.get("name") or "").strip()
        if not name:
            continue
        pv = r.get("percentage_value")
        if pv is None:
            raw = str(r.get("percentage") or "").rstrip("%")
            try:
                pv = float(raw) if raw else None
            except ValueError:
                pv = None
        entry: dict[str, Any] = {"name": name}
        if pv is not None:
            entry["pct"] = float(pv)
        out.append(entry)
    return out


def spreads_from_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        if r.get("category") != "stat_points":
            continue
        evs = {
            "hp": int(r.get("hp_points") or 0),
            "atk": int(r.get("attack_points") or 0),
            "def": int(r.get("defense_points") or 0),
            "spa": int(r.get("sp_atk_points") or 0),
            "spd": int(r.get("sp_def_points") or 0),
            "spe": int(r.get("speed_points") or 0),
        }
        entry: dict[str, Any] = {"evs": evs}
        pv = r.get("percentage_value")
        if pv is not None:
            entry["pct"] = float(pv)
        out.append(entry)
        if len(out) >= 8:
            break
    return out


def entry_from_battle(
    battle: dict[str, Any],
    *,
    display_name: str,
    usage_rank: int | None = None,
    sid_hint: str | None = None,
) -> dict[str, Any]:
    """Build a snapshot-shaped species entry from a CBD battle payload."""
    rows = battle.get("rows") or []
    if not isinstance(rows, list):
        rows = []
    disp = battle.get("pokemon") or display_name
    sid = to_id(str(battle.get("showdownId") or sid_hint or disp))
    out: dict[str, Any] = {
        "name": disp,
        "id": sid,
        "common_moves": pct_rows(rows, "move"),
        "common_abilities": pct_rows(rows, "ability"),
        "common_items": pct_rows(rows, "held_item"),
        "teammates": [r["name"] for r in pct_rows(rows, "teammate")],
        "top_spreads": spreads_from_rows(rows),
        "featured_sets": [],
        "source": "championsbattledata",
    }
    if usage_rank is not None:
        out["usage_rank"] = usage_rank
    return out


def fetch_ingame_doubles_species(display_name: str) -> dict[str, Any] | None:
    """Per-species CBD Doubles fetch. None on 404/network/parse failure (never raises)."""
    if not display_name or not str(display_name).strip():
        return None
    name = str(display_name).strip()
    url = f"{CBD_API}/api/battle/Doubles/{urllib.parse.quote(name)}?season=Current"
    try:
        battle = fetch_json(url)
    except Exception:
        return None
    if not isinstance(battle, dict):
        return None
    return entry_from_battle(battle, display_name=name)
