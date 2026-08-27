"""Map role_id strings to offense / support / unknown primary_function."""

from __future__ import annotations

from typing import Literal

from recommender.recommend import _DEPRECATED_ROLE_ALIASES

PrimaryFunction = Literal["offense", "support", "unknown"]

# Exceptions that suffix rules alone do not cover — see tests/recommender/test_anchor_roles.py.
_EXPLICIT_OFFENSE = frozenset(
    {
        "bulky_pivot",
        "fast_pivot",
        "trick_room_sweeper",
        "iron_defense_body_press",
        "setup_attacker",
    }
)
_EXPLICIT_SUPPORT = frozenset(
    {
        "support",
        "support_speed_control",
        "screens_support",
        "redirection",
        "sleep_status_spreader",
    }
)


def normalize_role_id(role_id: str) -> str:
    rid = role_id.strip().lower().replace("-", "_").replace(" ", "_")
    return _DEPRECATED_ROLE_ALIASES.get(rid, rid)


def primary_function_for_role_id(role_id: str) -> PrimaryFunction:
    rid = normalize_role_id(role_id)
    if rid == "unresolved":
        return "unknown"
    if rid.endswith("_attacker") or rid.endswith("_sweeper") or rid in _EXPLICIT_OFFENSE:
        return "offense"
    if rid.endswith("_setter") or rid in _EXPLICIT_SUPPORT:
        return "support"
    return "unknown"
