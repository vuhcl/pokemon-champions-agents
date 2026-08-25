"""One-shot: extract support constructs into role_compendium_support.py."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
rc_path = ROOT / "recommender" / "role_compendium.py"
lines = rc_path.read_text().splitlines()

body = "\n".join(lines[1171:2864]) + "\n"

header = '''"""Support-role Role Compendium constructs (redirect/TR/TW/screens/sleep)."""

from __future__ import annotations

from typing import Any

from recommender.ability_classification import execution_reinforce_abilities
from recommender.ids import to_id
from recommender.legality import resolve_learnset
from recommender.move_narrowing import move_priority
from recommender.role_compendium import (
    CandidateEval,
    ClaimedTrait,
    LiveFetch,
    RejectedCandidate,
    RoleConstructionDraft,
    _COMPETING_IDENTITY_MOVES,
    _FAKE_OUT_IMMUNE_TYPE,
    _REDIRECTION_SECONDARY_MOVES,
    _SCREENS_DELIVERY_NOTE,
    _SCREENS_EXCELLENT_SECONDARY_MOVES,
    _SCREENS_MOVE_IDS,
    _SCREENS_SECONDARY_MOVES,
    _SCREENS_SNOW_ABILITIES,
    _SCREENS_SPE_FLOOR,
    _SLEEP_ACCURACY,
    _SLEEP_ACCURACY_ABILITIES,
    _SLEEP_CORE_MOVES,
    _SLEEP_DELAYED,
    _SLEEP_EXCELLENT_SECONDARY_MOVES,
    _SLEEP_IMMEDIATE,
    _SLEEP_SECONDARY_MOVES,
    _SLEEP_SPE_FLOOR,
    _SLEEP_SPEED_ABILITIES,
    _SLEEP_STATUS_MOVES,
    _SLEEP_TRAP_ABILITIES,
    _TAILWIND_DELIVERY_NOTE,
    _TAILWIND_EXCELLENT_SECONDARY_MOVES,
    _TAILWIND_SECONDARY_MOVES,
    _TAILWIND_SPE_FLOOR,
    _TRICK_ROOM_BULK_FLOOR,
    _TRICK_ROOM_DELIVERY_NOTE,
    _TRICK_ROOM_EXCELLENT_SECONDARY_MOVES,
    _TRICK_ROOM_SECONDARY_MOVES,
    _TRICK_ROOM_SET_PCT_FLOOR,
    _USAGE_SET_PCT_FLOOR,
    _UsageCtx,
    _admit_move_delivery,
    _base_stats,
    _discount_outcome,
    _draft_with_tiers,
    _excellent_secondary,
    _guard_pool,
    _pool_index,
    _ref_members,
    _secondary_support_notes,
    _species_abilities,
    _species_id_is_mega,
)
from recommender.role_compendium_usage import (
    _delivery_usage_hits,
    _hits_clear_set_pct_floor,
    _mega_usage_attribution,
    _move_display,
    _move_pct,
    _same_row_both_moves,
    _species_types,
    _usage_has_item,
)

'''

(ROOT / "recommender" / "role_compendium_support.py").write_text(header + body)
new_rc = lines[:1171] + lines[2864:]
rc_path.write_text("\n".join(new_rc) + "\n")
print("ok", len(new_rc))
