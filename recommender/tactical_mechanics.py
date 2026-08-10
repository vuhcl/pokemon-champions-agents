"""Doubles-tactical caveat helpers (screen-clear / protect-contact bypass)."""

from __future__ import annotations

from dataclasses import replace

from recommender.calc_client import FieldSpec
from recommender.ids import to_id
from recommender.matchup import MatchupCaveats, _makes_contact

SCREEN_CLEAR_MOVES = frozenset({"brickbreak", "psychicfangs", "ragingbull"})
PROTECT_BYPASS_CONTACT_ABILITIES = frozenset({"unseenfist", "piercingdrill"})


def apply_tactical_caveats(
    *,
    move_id: str,
    attacker_ability: str | None,
    field: FieldSpec | None,
    caveats: MatchupCaveats,
) -> MatchupCaveats:
    """Set screen_clear_applied / protect_bypass_applied only."""
    mid = to_id(move_id)
    side = (field or {}).get("defenderSide") or {}
    out = caveats
    if mid in SCREEN_CLEAR_MOVES and (
        side.get("isReflect") or side.get("isLightScreen") or side.get("isAuroraVeil")
    ):
        out = replace(out, screen_clear_applied=True)
    if (
        side.get("isProtected")
        and to_id(attacker_ability or "") in PROTECT_BYPASS_CONTACT_ABILITIES
        and _makes_contact(mid)
    ):
        out = replace(out, protect_bypass_applied=True)
    return out
