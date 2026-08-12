"""Backup-redundancy divergence scoring for CompositionFit escapes.

Live kits are scored with binary presence (move/ability on the resolved set), not
usage-%% weights from the calibration artifact. Tag vocabulary is the validated
calibration set: move categories from ``flags.v1.json`` plus existing mechanism ids
(weather / TR / Tailwind / screens / redirect / disruption / protection / ally).

ponytail: DIVERGENCE_COMPLEMENTARY_THRESHOLD=0.6 is tournament n=8 mid-gap (empty
band 0.5–0.75); revisit when ladder team-composition data exists.
ponytail: MIN_SIDE_TAGS=2 fail-closed on non-category tags after exclude — Protect
alone yields category_status+support_protection which would defeat a raw len>=2
floor; categories still count in Jaccard but not the floor. Upgrade via richer
mechanism emission if a real sparse-but-diverging backup appears.
"""

from __future__ import annotations

from collections.abc import Sequence

from recommender.anchor_roles import AnchorRoleDecision
from recommender.counters import load_move_flags
from recommender.ids import to_id

# Mid empty gap between partial (≤0.5) and diverged (≥0.75) on usage-confirmed pairs.
DIVERGENCE_COMPLEMENTARY_THRESHOLD = 0.6

MIN_SIDE_TAGS = 2  # non-category tags after exclude; see fail-closed below

PROVIDER_TAG_BY_CONDITION = {
    "Rain": "provides_rain",
    "Sun": "provides_sun",
    "Sand": "provides_sand",
    "Snow": "provides_snow",
    "Trick Room": "provides_trick_room",
    "Tailwind": "provides_tailwind",
}

_MECH_TAGS: dict[str, str] = {
    "drizzle": "provides_rain",
    "raindance": "provides_rain",
    "drought": "provides_sun",
    "orichalcumpulse": "provides_sun",
    "sunnyday": "provides_sun",
    "sandstream": "provides_sand",
    "sandstorm": "provides_sand",
    "snowwarning": "provides_snow",
    "snowscape": "provides_snow",
    "trickroom": "provides_trick_room",
    "tailwind": "provides_tailwind",
    "followme": "provides_redirection",
    "ragepowder": "provides_redirection",
    "lightscreen": "provides_screens",
    "reflect": "provides_screens",
    "auroraveil": "provides_screens",
    "willowisp": "disruption_status",
    "encore": "disruption_status",
    "disable": "disruption_status",
    "taunt": "disruption_status",
    "quash": "disruption_speed",
    "fakeout": "disruption_priority",
    "wideguard": "support_protection",
    "quickguard": "support_protection",
    "protect": "support_protection",
    "helpinghand": "support_ally",
    "coaching": "support_ally",
    "lifedew": "support_ally",
    "painsplit": "support_ally",
}

_SECONDARY_ROLE_TAGS: dict[str, str] = {
    "rain_setter": "provides_rain",
    "sun_setter": "provides_sun",
    "sand_setter": "provides_sand",
    "snow_setter": "provides_snow",
    "trick_room_setter": "provides_trick_room",
    "tailwind_setter": "provides_tailwind",
    "redirection": "provides_redirection",
    "screens_support": "provides_screens",
    "support_speed_control": "provides_tailwind",
}

_CATEGORY_TAG = {
    "Physical": "category_physical",
    "Special": "category_special",
    "Status": "category_status",
}


def function_tags(
    decision: AnchorRoleDecision,
    *,
    moves: Sequence[str] = (),
    ability: str | None = None,
) -> frozenset[str]:
    """Binary kit tags from mechanisms, secondary roles, moves, and ability."""
    tags: set[str] = set()
    for mechanism in decision.mechanisms:
        if not mechanism.present:
            continue
        mid = to_id(mechanism.mechanic)
        if mid in _MECH_TAGS:
            tags.add(_MECH_TAGS[mid])
        if mechanism.role_id:
            tags.add(
                _SECONDARY_ROLE_TAGS.get(
                    mechanism.role_id, f"role:{mechanism.role_id}"
                )
            )
    for role_id in decision.secondary_role_ids:
        tags.add(_SECONDARY_ROLE_TAGS.get(role_id, f"role:{role_id}"))
    if decision.role_id:
        tags.add(
            _SECONDARY_ROLE_TAGS.get(decision.role_id, f"role:{decision.role_id}")
        )

    flags = load_move_flags()
    for move in moves:
        mid = to_id(move)
        if mid in _MECH_TAGS:
            tags.add(_MECH_TAGS[mid])
        cat = (flags.get(mid) or {}).get("category")
        tag = _CATEGORY_TAG.get(str(cat)) if cat else None
        if tag:
            tags.add(tag)

    if ability:
        aid = to_id(ability)
        if aid in _MECH_TAGS:
            tags.add(_MECH_TAGS[aid])
    return frozenset(tags)


def divergence_score(
    candidate_decision: AnchorRoleDecision,
    existing_decision: AnchorRoleDecision,
    *,
    candidate_moves: Sequence[str] = (),
    existing_moves: Sequence[str] = (),
    candidate_ability: str | None = None,
    existing_ability: str | None = None,
    shared_provider_tags: frozenset[str] | None = None,
) -> float:
    """1 − Jaccard on non-shared tags. Fail-closed to 0.0 when either side is thin."""
    cand = function_tags(
        candidate_decision, moves=candidate_moves, ability=candidate_ability
    )
    exist = function_tags(
        existing_decision, moves=existing_moves, ability=existing_ability
    )
    if shared_provider_tags is None:
        shared_provider_tags = frozenset(
            t
            for t in (cand & exist)
            if t.startswith("provides_")
        )
    cand = cand - shared_provider_tags
    exist = exist - shared_provider_tags
    # Categories alone must not clear the sparse-kit floor (Protect → status+protection).
    def _side_ok(tags: frozenset[str]) -> bool:
        return sum(1 for t in tags if not t.startswith("category_")) >= MIN_SIDE_TAGS

    if not _side_ok(cand) or not _side_ok(exist):
        return 0.0
    union = cand | exist
    if not union:
        return 0.0
    return 1.0 - (len(cand & exist) / len(union))
