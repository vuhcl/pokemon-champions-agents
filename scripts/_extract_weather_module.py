"""One-shot: extract weather setter into role_compendium_weather.py."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
rc_path = ROOT / "recommender" / "role_compendium.py"
lines = rc_path.read_text().splitlines()

# 1-based 1082:1395 inclusive
body = "\n".join(lines[1081:1395]) + "\n"

header = '''"""Weather setter Role Compendium construction (ADR-019)."""

from __future__ import annotations

from typing import Any

from recommender.ids import to_id
from recommender.legality import resolve_learnset
from recommender.role_compendium import (
    CandidateEval,
    ClaimedTrait,
    LiveFetch,
    RejectedCandidate,
    RoleConstructionDraft,
    _REDIRECTION_SECONDARY_MOVES,
    _SHOWDOWN_BASE_USAGE_RATIO,
    _USAGE_SET_PCT_FLOOR,
    _UsageCtx,
    _admit_move_delivery,
    _condition_label,
    _criteria_sets,
    _discount_outcome,
    _draft_with_tiers,
    _excellent_secondary,
    _guard_pool,
    _pool_index,
    _ref_members,
    _secondary_support_notes,
    _species_abilities,
)
from recommender.role_compendium_usage import (
    _hits_clear_set_pct_floor,
    _mega_pair_ids,
    _move_display,
    _showdown_entry,
    _stone_fallback_ability,
)

'''

(ROOT / "recommender" / "role_compendium_weather.py").write_text(header + body)
new_rc = lines[:1081] + lines[1395:]
rc_path.write_text("\n".join(new_rc) + "\n")
print("ok", len(new_rc))
