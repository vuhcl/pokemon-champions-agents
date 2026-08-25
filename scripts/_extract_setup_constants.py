"""One-shot: extract setup constants into role_compendium_setup_constants.py."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
rc_path = ROOT / "recommender" / "role_compendium.py"
lines = rc_path.read_text().splitlines()

# 1-based 86:372 and 484:485 (_BODY_PRESS_EVS, _DEF_PAYOFF_DELTA_EPS)
body = "\n".join(lines[85:372] + lines[483:485]) + "\n"

header = '''"""Setup-attacker constants shared by role_compendium and role_compendium_setup."""

from __future__ import annotations

from pathlib import Path

from recommender.matchup import _CHARGE_MOVES, _RECHARGE_MOVES
from recommender.support_needs import _OFFENSIVE_PRIORITY_MOVES, _SELF_HEAL_MOVES

ROOT = Path(__file__).resolve().parents[1]

'''

(ROOT / "recommender" / "role_compendium_setup_constants.py").write_text(header + body)

# Remove from compendium (bottom-up)
new_rc = lines[:85] + lines[372:483] + lines[485:]
rc_path.write_text("\n".join(new_rc) + "\n")

# Re-export from compendium for importers that still use the façade
insert_at = 85  # after line 85 (0-index), before RAIN_SETTER_CRITERIA
reexport = """
from recommender.role_compendium_setup_constants import (  # noqa: E402
    _ALLY_HIT_DAMAGE_MOVE_IDS,
    _ALLY_HIT_TYPE_PROTECTIONS,
    _BODY_PRESS_EVS,
    _CALC_POKE_KEYS,
    _CONNECT_RECOIL_MOVES,
    _DD_SETUP_PRESENCE_FLOOR,
    _DEF_PAYOFF_DELTA_EPS,
    _DRAIN_MOVES,
    _PIKALYTICS_PAIRS_PATH,
    _SETUP_ACCEPTABLE_FLOOR_MULT,
    _SETUP_BANNED_PAYOFF,
    _SETUP_BITE_MOVES,
    _SETUP_BOTH_BRANCH_SCORE_DIV,
    _SETUP_BRANCH_A_PRIORITY,
    _SETUP_BULK_FLOOR,
    _SETUP_CHOICE_ITEMS,
    _SETUP_CONDITIONAL_PRIORITY,
    _SETUP_DAMAGE_FRAC_CAP,
    _SETUP_EXCELLENT_SECONDARY_ABILITIES,
    _SETUP_EXCELLENT_SECONDARY_MOVES,
    _SETUP_FLOOR_SECOND_MULT,
    _SETUP_LOCKIN_MOVES,
    _SETUP_NARROW_CONDITIONAL_PRIORITY,
    _SETUP_PRESENCE_SET_PCT_FLOOR,
    _SETUP_PRIORITY_FINISHER_MOVES,
    _SETUP_PULSE_MOVES,
    _SETUP_PUNCH_MOVES,
    _SETUP_SLICE_MOVES,
    _SETUP_SPE_FLOOR,
    _SETUP_SPEED_ABILITIES,
    _SETUP_SUSTAIN_DRAIN,
    _SETUP_SUSTAIN_HEALS,
    _SETUP_SUSTAIN_ITEMS,
    _SETUP_SURVIVE_ABILITIES,
    _SETUP_THREAT_ENCOUNTER_GAMES,
    _SETUP_THREAT_USAGE_PCT_FLOOR,
    _SOUND_ALLY_HIT_MOVE_IDS,
    _SPREAD_DAMAGE_MOVE_IDS,
)

"""
lines2 = rc_path.read_text().splitlines()
# Find RAIN_SETTER_CRITERIA
idx = next(i for i, ln in enumerate(lines2) if ln.startswith("RAIN_SETTER_CRITERIA"))
lines2 = lines2[:idx] + reexport.strip().splitlines() + [""] + lines2[idx:]
rc_path.write_text("\n".join(lines2) + "\n")
print("ok", len(lines2))
