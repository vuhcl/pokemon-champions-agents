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


# Flare Blitz / damage-fraction recoil — in-game 1/3 floor; calc exposes % of attacker HP only
RECOIL_DAMAGE_FRACTION_SCOPE = (
    "moves whose recoil is a fraction of damage dealt; "
    "Struggle and Steel Beam (fixed fraction of max HP) are excluded"
)


def _dealt_cap(damage: list | None, def_hp: int | None) -> tuple[int | None, int | None]:
    dmg = list(damage or [])
    if def_hp is None:
        return None, None
    if not dmg:
        return def_hp, def_hp
    return min(min(dmg), def_hp), min(max(dmg), def_hp)


def flare_blitz_recoil_basis(
    *,
    def_hp: int | None,
    atk_hp: int | None,
    damage: list | None,
    calc_display_pct: list | None = None,
) -> dict:
    """In-game Flare Blitz recoil = floor(damage_dealt/3); calc exposes % of atk HP only."""
    dealt_lo, dealt_hi = _dealt_cap(damage, def_hp)
    value_hp = math.floor(dealt_lo / 3) if dealt_lo is not None else None
    value_hi = math.floor(dealt_hi / 3) if dealt_hi is not None else None
    # OHKO into full Primarina: dealt == def_hp → single HP figure
    if value_hp is not None and value_hi is not None and value_hp != value_hi:
        # non-OHKO / non-cap range — keep lo; callers for AR3 OHKO expect a single value
        pass
    sim_hp = round(dealt_lo * 33 / 100) if dealt_lo is not None else None

    true_shares = {}
    for label, hp in (("hp_185", 185), ("hp_153", 153)):
        if value_hp is None:
            continue
        true_shares[label] = {
            "attacker_max_hp": hp,
            "recoil_hp": value_hp,
            "share": round(value_hp / hp, 4),
            "approx_pct": round(100.0 * value_hp / hp, 1),
            "note": "true share of attacker max HP (from value_hp); not the calc display",
        }
    if atk_hp is not None and value_hp is not None and atk_hp not in (185, 153):
        true_shares[f"hp_{atk_hp}"] = {
            "attacker_max_hp": atk_hp,
            "recoil_hp": value_hp,
            "share": round(value_hp / atk_hp, 4),
            "approx_pct": round(100.0 * value_hp / atk_hp, 1),
            "note": "true share of attacker max HP (from value_hp); not the calc display",
        }

    # Hosted /calculate exposes only percent-of-attacker-HP (raw.recoil), never HP points.
    # Document both AR3 attacker HP contexts; pct from this call when present.
    pct_lo = pct_hi = None
    if calc_display_pct and len(calc_display_pct) >= 2 and calc_display_pct[0] is not None:
        pct_lo, pct_hi = float(calc_display_pct[0]), float(calc_display_pct[1])
    calc_display = {
        "kind": "percent_of_attacker_hp_only",
        "exposes_hp_points": False,
        "move_data_factor": 0.33,
        "by_attacker_max_hp": {
            "185": {
                "calc_display_pct": 33.3,
                "note": "hosted calc raw.recoil for HP-32 CX; slightly below true share ~33.5%",
            },
            "153": {
                "calc_display_pct": 40.3,
                "note": "hosted calc raw.recoil for HP-0 CX; slightly below true share ~40.5%",
            },
        },
        "this_call": {
            "attacker_max_hp": atk_hp,
            "calc_display_pct_range": [pct_lo, pct_hi] if pct_lo is not None else None,
            "text_example": (
                f"{pct_lo} - {pct_hi}% recoil damage" if pct_lo is not None else None
            ),
        },
        "source": (
            "@smogon/calc 0.11.0-champions.5d5bf43 hosted /calculate raw.recoil "
            "(percent of attacker max HP from 0.33 factor); desc/fullDesc name damage only — "
            "no HP-point recoil field"
        ),
        "note": (
            "NOT an HP-point value. Flooring display%×atk_HP (or 0.33×damage) can yield 61; "
            "that is an arm conversion artifact, not a calc-exposed HP figure."
        ),
    }

    return {
        "scope": RECOIL_DAMAGE_FRACTION_SCOPE,
        "recoil_basis": {
            "rule": "true 1/3 of damage dealt, floor, capped at defender remaining HP",
            "value_hp": value_hp,
            "value_hp_source": (
                "owner-stated in-game text "
                "('The user also takes 1/3 of the damage dealt by this move.'); "
                f"sim cross-check Math.round({dealt_lo}*33/100)={sim_hp} "
                "(.cache/pokemon-showdown/sim/battle-actions.ts applyRecoilDamage L1376–1377)"
            ),
            "in_game_text": (
                "The user also takes 1/3 of the damage dealt by this move."
            ),
            "damage_dealt_after_defender_hp_cap_range": [dealt_lo, dealt_hi],
            "true_share_of_attacker_hp": true_shares,
            "calc_display": calc_display,
            "showdown_sim_cross_check_hp": sim_hp,
        },
        "scoring": {
            "hp_point_62": "TRUE",
            "hp_point_61": "FALSE",
            "hp_point_61_sub_label": "derived_from_calc_percent",
            "hp_point_other": "FALSE",
            "percent_of_attacker_hp_33_3_to_33_5_attributed_to_calc_display": "TRUE",
            "unlabeled_or_33pct_of_max_hp_framing": "FALSE",
            "counts_in_gate": True,
            "sub_label_reported_as_own_sub_line": True,
            "note": (
                "HP-point 62 only is TRUE. 61 is FALSE with sub_label derived_from_calc_percent "
                "(reported as its own sub-line). Calc-attributed 33.3–33.5% of stated attacker HP "
                "is TRUE; unlabeled / '33% of max HP' framing is FALSE."
            ),
        },
        # survival-margin aliases — true in-game HP only (not 61)
        "recoil_hp": value_hp,
        "recoil_hp_range": [value_hp, value_hp] if value_hp is not None else [None, None],
        "calc_recoil_text_is_display_pct_of_attacker_max_hp": True,
    }


def base_stats(snap: dict, species: str) -> dict:
    return snap["species"][to_id(species)]["base_stats"]


def common_joint(sd: dict, species: str, n: int = 3) -> list:
    sid = to_id(species)
    spreads = (sd["showdown_doubles"]["species"].get(sid) or {}).get("top_spreads") or []
    return spreads[:n]


def as_chaos_weight_joint(row: dict | None) -> dict | None:
    """Copy a Showdown top_spreads row; rename pin ``pct`` → ``chaos_weight`` (drop pct_kind)."""
    if not row:
        return None
    out = {k: v for k, v in row.items() if k not in ("pct", "pct_kind", "chaos_weight")}
    w = row.get("chaos_weight", row.get("pct"))
    if w is not None:
        out["chaos_weight"] = w
    return out


def as_chaos_weight_joints(rows: list | None) -> list:
    return [as_chaos_weight_joint(r) for r in (rows or []) if r is not None]


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
