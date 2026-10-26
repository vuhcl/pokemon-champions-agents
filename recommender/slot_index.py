"""User-facing slot numbers count from 1. Nodes index team_draft from 0.

Convert once, at the extraction boundary (recommender/turn_intent.py). Do not
convert inside the nodes, and do not convert a number that is already an
internal index (pending screens, superseded entries, direct node calls).
"""

from __future__ import annotations

ROSTER_SLOTS = 6


class SlotIndexError(ValueError):
    """The user slot is not an in-range integer. Callers must write nothing."""


def user_slot_to_index(user_slot: object, *, team_size: int = ROSTER_SLOTS) -> int:
    """1-based user slot to a 0-based team_draft index."""
    if isinstance(user_slot, bool) or not isinstance(user_slot, int):
        raise SlotIndexError(f"slot must be an integer, got {user_slot!r}")
    if not 1 <= user_slot <= team_size:
        raise SlotIndexError(f"slot {user_slot} is outside 1..{team_size}")
    return user_slot - 1


def display_slot(index: int) -> str:
    """Internal index to the 1-based number shown to the user."""
    return str(index + 1)
