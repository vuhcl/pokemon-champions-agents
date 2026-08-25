"""Load and interpret data/moves/stat_boosts.v1.json (self-boost helpers)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from recommender.ids import to_id

ROOT = Path(__file__).resolve().parents[1]
_STAT_BOOSTS_PATH = ROOT / "data" / "moves" / "stat_boosts.v1.json"


@lru_cache(maxsize=1)
def load_stat_boosts() -> dict[str, Any]:
    return json.loads(_STAT_BOOSTS_PATH.read_text())


def _self_boosts(entry: dict[str, Any]) -> dict[str, int]:
    """Stat changes the move always applies to its own user (chance-gated ones excluded)."""
    out: dict[str, int] = {}
    for eff in entry.get("boosts") or []:
        if eff.get("to") != "self" or eff.get("chance") != 100:
            continue
        for stat, stages in (eff.get("stats") or {}).items():
            out[stat] = out.get(stat, 0) + int(stages)
    return out


@lru_cache(maxsize=None)
def _self_defense_drops(mid: str) -> dict[str, int]:
    """Guaranteed self Def/SpD drops for a damaging move (empty if none)."""
    ent = (load_stat_boosts().get("moves") or {}).get(to_id(mid)) or {}
    if ent.get("category") == "Status":
        return {}
    drops = {
        s: st
        for s, st in _self_boosts(ent).items()
        if s in {"def", "spd"} and st < 0
    }
    return drops
