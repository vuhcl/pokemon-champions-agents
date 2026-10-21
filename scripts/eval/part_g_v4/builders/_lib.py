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


# Flare Blitz / damage-fraction recoil — ADR-079: round-half-up of damage dealt x 33/100 (min 1); calc exposes % of attacker HP only
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


# AR3 OHKO into Primarina HP 187: unrounded 0.33×damage and the ADR-079 recoil HP (62)
AR3_RECOIL_CALC_UNROUNDED_HP = 61.71  # 187 * 0.33
AR3_RECOIL_VALUE_HP = 62  # ADR-079 operator at damage dealt 187: floor((33*187 + 50)/100)
CX_MEGA_X_BASE_HP = 78


def champions_cx_megax_hp(hp_sp: int) -> int:
    """Charizard-Mega-X max HP at level 50: base + SP + 75."""
    return CX_MEGA_X_BASE_HP + int(hp_sp) + 75


def recoil_share_pct_range_for_attacker_hp(attacker_max_hp: int) -> list[float]:
    """Accepted calc-attributed recoil % of attacker HP H for AR3 (damage capped at 187).

    Range = [61.71/H, 62/H] as percent, to 0.1:
    - lower (calc-display bound): floor to 0.1 — matches hosted calc one-decimal display
      at the AR3 fixtures (33.3% @ 185, 40.3% @ 153); plain round(61.71/185*100,1)=33.4
    - upper (true-share bound): round half to 0.1 (33.5% @ 185, 40.5% @ 153)
    """
    h = int(attacker_max_hp)
    if h <= 0:
        raise ValueError(f"attacker_max_hp must be positive, got {attacker_max_hp!r}")
    lo = math.floor(AR3_RECOIL_CALC_UNROUNDED_HP / h * 1000) / 10
    hi = round(AR3_RECOIL_VALUE_HP / h * 100, 1)
    return [lo, hi]


def recoil_hp_adr079(dealt: int, n: int = 33, den: int = 100) -> int:
    """ADR-079: max(1, floor((2*d*n + den) / (2*den))) for d > 0, else 0 (integer arithmetic)."""
    return max(1, (2 * dealt * n + den) // (2 * den)) if dealt > 0 else 0


def flare_blitz_recoil_basis(
    *,
    def_hp: int | None,
    atk_hp: int | None,
    damage: list | None,
    calc_display_pct: list | None = None,
) -> dict:
    """Flare Blitz recoil HP per ADR-079 (observed in-game: round-half-up of damage_dealt x 33/100); calc exposes % of atk HP only."""
    dealt_lo, dealt_hi = _dealt_cap(damage, def_hp)
    value_hp = recoil_hp_adr079(dealt_lo) if dealt_lo is not None else None
    value_hi = recoil_hp_adr079(dealt_hi) if dealt_hi is not None else None
    # OHKO into full Primarina: dealt == def_hp → single HP figure
    if value_hp is not None and value_hi is not None and value_hp != value_hi:
        # non-OHKO / non-cap range — keep lo; callers for AR3 OHKO expect a single value
        pass
    sim_hp = round(dealt_lo * 33 / 100) if dealt_lo is not None else None
    unrounded_33 = (
        round(dealt_lo * 33 / 100, 2) if dealt_lo is not None else None
    )

    # Worked examples only (fixture HP SP 32 / 0) — not the accepted set
    worked = {}
    for hp_sp, label in ((32, "hp_185"), (0, "hp_153")):
        h = champions_cx_megax_hp(hp_sp)
        band = recoil_share_pct_range_for_attacker_hp(h)
        worked[label] = {
            "hp_sp": hp_sp,
            "attacker_max_hp": h,
            "hp_formula": f"{CX_MEGA_X_BASE_HP} + {hp_sp} + 75 = {h}",
            "accepted_share_pct_range": band,
            "true_share_pct": round(100.0 * AR3_RECOIL_VALUE_HP / h, 1),
            "note": "worked example from AR3 fixture; not an exclusive accepted HP",
        }

    pct_lo = pct_hi = None
    if calc_display_pct and len(calc_display_pct) >= 2 and calc_display_pct[0] is not None:
        pct_lo, pct_hi = float(calc_display_pct[0]), float(calc_display_pct[1])
    calc_display = {
        "kind": "percent_of_attacker_hp_only",
        "exposes_hp_points": False,
        "move_data_factor": 0.33,
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

    share_formula = {
        "attacker_max_hp_from_sp": (
            f"H = {CX_MEGA_X_BASE_HP} + HP_SP + 75 (Charizard-Mega-X Champions HP)"
        ),
        "numerators": {
            "calc_unrounded_hp": AR3_RECOIL_CALC_UNROUNDED_HP,
            "calc_unrounded_note": (
                "187 × 0.33 for AR3 OHKO (damage capped at Primarina remaining HP 187); "
                f"this_call unrounded product={unrounded_33}"
            ),
            "true_value_hp": AR3_RECOIL_VALUE_HP,
        },
        "accepted_share_pct_range_for_H": (
            "lo = floor((61.71/H)*1000)/10 ; hi = round((62/H)*100, 1)  "
            "# percent points; lo truncated to 0.1 to match calc one-decimal display "
            "at fixtures; hi is true-share 62/H rounded to 0.1"
        ),
        "in_range_attributed_to_calc_display": "TRUE",
        "out_of_range": "FALSE",
        "no_stated_attacker_hp_or_spread": "FALSE (no stated conditions)",
    }

    return {
        "scope": RECOIL_DAMAGE_FRACTION_SCOPE,
        "recoil_basis": {
            "rule": "ADR-079: round-half-up of damage dealt x 33/100 (min 1), damage capped at defender remaining HP",
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
            "percent_of_attacker_hp_range_formula": share_formula,
            "worked_examples_attacker_hp": worked,
            "calc_display": calc_display,
            "showdown_sim_cross_check_hp": sim_hp,
        },
        "scoring": {
            "hp_point_62": "TRUE",
            "hp_point_61": "FALSE",
            "hp_point_61_sub_label": "derived_from_calc_percent",
            "hp_point_other": "FALSE",
            "percent_of_attacker_hp_attributed_to_calc_display": {
                "check": (
                    "Against the claim's stated attacker max HP H (or HP SP → "
                    f"H = {CX_MEGA_X_BASE_HP} + SP + 75): accepted share pct range "
                    "[floor(61.71/H*1000)/10, round(62/H*100, 1)]. "
                    "In range + attributed to calc display → TRUE; out of range → FALSE; "
                    "no stated attacker HP/spread → FALSE (no stated conditions)."
                ),
                "range_formula": share_formula,
                "worked_examples_not_accepted_set": {
                    "185": {
                        "hp_sp": 32,
                        "accepted_share_pct_range": recoil_share_pct_range_for_attacker_hp(185),
                        "verdict_if_claim_in_range": "TRUE",
                    },
                    "153": {
                        "hp_sp": 0,
                        "accepted_share_pct_range": recoil_share_pct_range_for_attacker_hp(153),
                        "verdict_if_claim_in_range": "TRUE",
                    },
                },
            },
            "unlabeled_or_33pct_of_max_hp_framing": "FALSE",
            "counts_in_gate": True,
            "sub_label_reported_as_own_sub_line": True,
            "note": (
                "HP-point 62 only is TRUE. 61 is FALSE with sub_label derived_from_calc_percent "
                "(own sub-line). Percent-of-attacker-HP claims use the H-formula above "
                "(worked examples 33.3–33.5% @ 185 and 40.3–40.5% @ 153). Unlabeled / "
                "'33% of max HP' framing is FALSE. Primarina HP 187 is damage dealt, not H."
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
