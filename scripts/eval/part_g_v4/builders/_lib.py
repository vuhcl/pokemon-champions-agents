"""ADR-060-clean helpers: pinned JSON + standalone formulas only. No recommender.*."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

# builders/ → part_g_v4 → eval → scripts → repo root
PKG = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[4]
LEGALITY = ROOT / "data" / "legality" / "champions.v1.json"
INGAME = ROOT / "data" / "usage" / "champions-reg-mc.ingame_doubles.v1.json"
SHOWDOWN = ROOT / "data" / "usage" / "champions-reg-mc.showdown_doubles.v1.json"

SPEED_PLUS = {"Timid", "Jolly", "Hasty", "Naive"}
SPEED_MINUS = {"Brave", "Relaxed", "Quiet", "Sassy"}


def to_id(name: str) -> str:
    s = name.strip().lower()
    s = s.replace("♀", "f").replace("♂", "m")
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def load_legality() -> dict:
    return load_json(LEGALITY)


def load_ingame() -> dict:
    return load_json(INGAME)


def load_showdown() -> dict:
    return load_json(SHOWDOWN)


def is_legal_species(sp: dict) -> bool:
    return sp.get("is_nonstandard") is None


def champions_spe(base_spe: int, spe_sp: int, nature: str, scarf: bool = False) -> int:
    n = 1.1 if nature in SPEED_PLUS else (0.9 if nature in SPEED_MINUS else 1.0)
    speed = math.floor(n * (base_spe + spe_sp + 20))
    return int(speed * 1.5) if scarf else speed


def champions_hp(base_hp: int, hp_sp: int) -> int:
    """Champions L50 HP for this project: base + SP + 75 (Hatterene 57→132; Primarina 80+32→187)."""
    return base_hp + int(hp_sp) + 75


def base_stats(snap: dict, species: str) -> dict:
    return snap["species"][to_id(species)]["base_stats"]


def common_joint(sd: dict, species: str, n: int = 3) -> list:
    sid = to_id(species)
    spreads = (sd["showdown_doubles"]["species"].get(sid) or {}).get("top_spreads") or []
    return spreads[:n]


def common_item_showdown(sd: dict, species: str) -> list:
    sid = to_id(species)
    return (sd["showdown_doubles"]["species"].get(sid) or {}).get("common_items") or []


# Showdown doubles usage floor for per-form ThreatCandidates (1 - 0.5^(1/15))
SHOWDOWN_THREAT_USAGE_CUTOFF = 1 - 0.5 ** (1 / 15)  # ≈ 0.045158


def showdown_threats_ge_cutoff(
    sd: dict | None = None,
    cutoff: float = SHOWDOWN_THREAT_USAGE_CUTOFF,
) -> list[dict]:
    """Every Showdown-listed form (mega included) with usage_pct ≥ cutoff.

    Shared by HU2b / AR3 / any Speed-cell key that expands threats by form.
    usage_pct in the blob is percent (may be <1); always divide by 100.
    """
    if sd is None:
        sd = load_showdown()
    out = []
    for sid, sp in (sd.get("showdown_doubles") or {}).get("species", {}).items():
        usage = sp.get("usage_pct")
        if usage is None:
            continue
        u_pct = float(usage)
        u_frac = u_pct / 100.0
        if u_frac + 1e-12 >= cutoff:
            out.append(
                {
                    "id": sid,
                    "name": sp.get("name") or sid,
                    "usage": u_frac,
                    "usage_pct": u_pct,
                }
            )
    out.sort(key=lambda r: (-r["usage"], r["id"]))
    return out
