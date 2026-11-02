"""draft rung: lock_fields / unlock_fields / draft-aware unlock_slot helpers."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from recommender.slot_index import SlotIndexError, display_slot, user_slot_to_index
from recommender.state import Attr, Slot, all_locked, empty_slot

_ATTR_NAMES = ("role", "species", "ability", "item", "moveset", "spread", "nature")
_LOCKABLE = ("species", "ability", "item", "moveset", "spread", "nature", "role")


def attr_status(attr: Attr) -> str:
    if attr.value is None and not attr.locked:
        return "empty"
    if attr.locked:
        return "locked"
    return "draft"


def slot_has_values(slot: Slot) -> bool:
    return any(getattr(slot, n).value is not None for n in _ATTR_NAMES)


def slot_is_blank(slot: Slot) -> bool:
    return not slot_has_values(slot) and not any(getattr(slot, n).locked for n in _ATTR_NAMES)


def draft_contents_summary(slot: Slot) -> str:
    parts: list[str] = []
    for name in _ATTR_NAMES:
        attr = getattr(slot, name)
        if attr.value is None:
            continue
        parts.append(f"{name}={attr.value!r}({attr_status(attr)})")
    return ", ".join(parts) if parts else "(empty)"


def _refuse(message: str) -> dict[str, Any]:
    return {"ok": False, "slot_commit_error": message}


def lock_fields(
    state: dict[str, Any],
    user_slot: object,
    fields: object = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Lock named attributes that already have values (omit fields → all valued)."""
    try:
        index = user_slot_to_index(user_slot, team_size=len(state["team_draft"]))
    except SlotIndexError as exc:
        return state, _refuse(str(exc))
    slot = state["team_draft"][index]
    if fields is None:
        names = [n for n in _LOCKABLE if getattr(slot, n).value is not None]
    else:
        if not isinstance(fields, list) or not fields:
            return state, _refuse("fields must be a non-empty list of attribute names, or omitted")
        names = []
        for f in fields:
            if not isinstance(f, str):
                return state, _refuse("fields must be strings")
            name = "moveset" if f == "moves" else f
            if name not in _LOCKABLE:
                return state, _refuse(f"unknown field {f!r}")
            names.append(name)
    if not names:
        return state, _refuse(
            f"slot {display_slot(index)} has no valued attributes to lock"
        )
    updates: dict[str, Attr] = {}
    locked_names: list[str] = []
    for name in names:
        attr = getattr(slot, name)
        if attr.value is None:
            return state, _refuse(
                f"cannot lock empty attribute {name} on slot {display_slot(index)}"
            )
        updates[name] = replace(attr, locked=True)
        locked_names.append(name)
    new_slot = replace(slot, **updates)
    draft = list(state["team_draft"])
    draft[index] = new_slot
    after = {**state, "team_draft": draft, "slot_commit_error": None}
    return after, {
        "ok": True,
        "slot": display_slot(index),
        "locked": locked_names,
        "status": {n: attr_status(getattr(new_slot, n)) for n in _LOCKABLE},
    }


def unlock_fields(
    state: dict[str, Any],
    user_slot: object,
    fields: object = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Set locked=False on named attrs; keep values."""
    try:
        index = user_slot_to_index(user_slot, team_size=len(state["team_draft"]))
    except SlotIndexError as exc:
        return state, _refuse(str(exc))
    slot = state["team_draft"][index]
    if fields is None:
        names = [n for n in _LOCKABLE if getattr(slot, n).locked]
    else:
        if not isinstance(fields, list) or not fields:
            return state, _refuse("fields must be a non-empty list of attribute names, or omitted")
        names = []
        for f in fields:
            if not isinstance(f, str):
                return state, _refuse("fields must be strings")
            name = "moveset" if f == "moves" else f
            if name not in _LOCKABLE:
                return state, _refuse(f"unknown field {f!r}")
            names.append(name)
    if not names:
        return state, _refuse(
            f"slot {display_slot(index)} has no locked attributes to unlock"
        )
    updates: dict[str, Attr] = {}
    unlocked: list[str] = []
    for name in names:
        attr = getattr(slot, name)
        updates[name] = replace(attr, locked=False)
        unlocked.append(name)
    new_slot = replace(slot, **updates)
    draft = list(state["team_draft"])
    draft[index] = new_slot
    after = {**state, "team_draft": draft, "slot_commit_error": None}
    return after, {
        "ok": True,
        "slot": display_slot(index),
        "unlocked": unlocked,
        "status": {n: attr_status(getattr(new_slot, n)) for n in _LOCKABLE},
    }


def unlock_slot_draft(
    state: dict[str, Any],
    user_slot: object,
    *,
    replace: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Wipe an occupied slot. Under draft, require replace=true when values present."""
    try:
        index = user_slot_to_index(user_slot, team_size=len(state["team_draft"]))
    except SlotIndexError as exc:
        return state, _refuse(str(exc))
    slot = state["team_draft"][index]
    if slot_is_blank(slot):
        return state, _refuse(f"slot {display_slot(index)} is already empty")
    if not replace:
        return state, {
            "ok": False,
            "slot_commit_error": (
                f"slot {display_slot(index)} holds {draft_contents_summary(slot)}; "
                "clearing it needs replace=true only after the user confirms"
            ),
            "draft_contents": draft_contents_summary(slot),
            "replace": False,
        }
    draft = list(state["team_draft"])
    draft[index] = empty_slot()
    after = {**state, "team_draft": draft, "slot_commit_error": None}
    return after, {
        "ok": True,
        "slot": display_slot(index),
        "wiped": True,
        "replace": True,
    }


LOCK_FIELDS_SPEC = {
    "type": "function",
    "function": {
        "name": "lock_fields",
        "description": (
            "Lock attributes on a slot that already have values. "
            "Omit fields to lock every valued attribute. Refuses empty attributes. "
            "Does not write new values — use set_slot to draft values first. "
            "slot counts from 1."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "slot": {"type": "integer"},
                "fields": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["slot"],
        },
    },
}

UNLOCK_FIELDS_SPEC = {
    "type": "function",
    "function": {
        "name": "unlock_fields",
        "description": (
            "Set locked=false on attributes while keeping their values (draft again). "
            "Omit fields to unlock every currently locked attribute. slot counts from 1."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "slot": {"type": "integer"},
                "fields": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["slot"],
        },
    },
}
