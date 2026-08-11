"""Static roster role-structure grouping (contested vs uncontested functions).

On-demand summary from AnchorRoleDecision fields only — not wired into the live graph.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from recommender.slot_fill import LockedAnchorContext

GroupStatus = Literal["contested", "uncontested"]

_LABELS: dict[str, str] = {
    "rain_setter": "rain setter",
    "sun_setter": "sun setter",
    "sand_setter": "sand setter",
    "snow_setter": "snow setter",
    "trick_room_setter": "trick room setter",
    "tailwind_setter": "tailwind setter",
    "attacker": "attacker",
    "redirection": "redirection",
    "screens_support": "screens",
    "support_speed_control": "speed control",
    "bulky_pivot": "bulky pivot",
    "fast_pivot": "fast pivot",
}

__all__ = [
    "GroupStatus",
    "MemberRef",
    "MemberRoleMembership",
    "RoleFunctionGroup",
    "RosterRoleStructureReport",
    "summarize_roster_role_structure",
]


@dataclass(frozen=True)
class MemberRef:
    slot_index: int
    species: str


@dataclass(frozen=True)
class RoleFunctionGroup:
    function_key: str
    label: str
    members: tuple[MemberRef, ...]
    cardinality: int
    status: GroupStatus
    notes: str | None = None


@dataclass(frozen=True)
class MemberRoleMembership:
    slot_index: int
    species: str
    groups: tuple[tuple[str, GroupStatus], ...]


@dataclass(frozen=True)
class RosterRoleStructureReport:
    groups: tuple[RoleFunctionGroup, ...]
    members: tuple[MemberRoleMembership, ...]


def _label_for(function_key: str) -> str:
    return _LABELS.get(function_key, function_key.replace("_", " "))


def _member_ref(context: LockedAnchorContext) -> MemberRef:
    species = context.resolved_build.species or context.anchor_id
    return MemberRef(slot_index=context.slot_index, species=species)


def _function_keys(context: LockedAnchorContext) -> tuple[str, ...]:
    decision = context.role_decision
    keys: list[str] = []
    if decision.role_id and decision.role_id != "unresolved":
        keys.append(decision.role_id)
    keys.extend(decision.secondary_role_ids)
    if decision.primary_function == "offense":
        keys.append("attacker")
    for m in decision.mechanisms:
        if (
            m.present
            and m.relation == "provides"
            and m.importance in {"needed", "wanted"}
            and m.role_id
        ):
            keys.append(m.role_id)
    return tuple(dict.fromkeys(keys))


def summarize_roster_role_structure(
    locked: Sequence[LockedAnchorContext],
) -> RosterRoleStructureReport:
    if not locked:
        return RosterRoleStructureReport(groups=(), members=())

    by_key: dict[str, list[MemberRef]] = defaultdict(list)
    member_keys: list[tuple[MemberRef, tuple[str, ...]]] = []
    for context in locked:
        ref = _member_ref(context)
        keys = _function_keys(context)
        member_keys.append((ref, keys))
        for key in keys:
            by_key[key].append(ref)

    # Deduplicate members per key (stable by first appearance / slot_index).
    for key, refs in list(by_key.items()):
        by_key[key] = list({r.slot_index: r for r in refs}.values())
        by_key[key].sort(key=lambda r: r.slot_index)

    status_by_key: dict[str, GroupStatus] = {
        key: ("contested" if len(refs) >= 2 else "uncontested")
        for key, refs in by_key.items()
    }

    groups: list[RoleFunctionGroup] = []
    for key, refs in by_key.items():
        status = status_by_key[key]
        notes = f"{len(refs)} candidates" if status == "contested" else None
        groups.append(
            RoleFunctionGroup(
                function_key=key,
                label=_label_for(key),
                members=tuple(refs),
                cardinality=len(refs),
                status=status,
                notes=notes,
            )
        )

    groups.sort(
        key=lambda g: (
            0 if g.status == "contested" else 1,
            -g.cardinality if g.status == "contested" else 0,
            g.members[0].slot_index if g.members else 0,
            g.function_key,
        )
    )

    memberships: list[MemberRoleMembership] = []
    for ref, keys in member_keys:
        memberships.append(
            MemberRoleMembership(
                slot_index=ref.slot_index,
                species=ref.species,
                groups=tuple((k, status_by_key[k]) for k in keys),
            )
        )
    memberships.sort(key=lambda m: m.slot_index)

    return RosterRoleStructureReport(
        groups=tuple(groups),
        members=tuple(memberships),
    )
