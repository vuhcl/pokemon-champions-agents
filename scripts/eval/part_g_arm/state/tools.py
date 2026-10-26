"""State tools for the Part G arm. Each wrapper calls one existing node.

Slot arguments are the user's number. Conversion happens once, here, through
user_slot_to_index. A bad slot does not call the node and does not change state.
A node refusal is merged by copying only the keys the node returned.

check_hypothetical copies the draft, validates on the copy, and discards it.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import fields, replace
from typing import Any

from recommender.arm_tools import TOOL_SPECS, to_jsonable
from recommender.nodes import apply_lock, commit_full_slot, reset_team, unlock_locked_slot
from recommender.slot_index import SlotIndexError, display_slot, user_slot_to_index
from recommender.state import Attr, Slot
from recommender.team_validation import validate_team_value

STATE_TOOL_NAMES = frozenset({"lock_slot", "unlock_slot", "reset_team", "commit_slot", "read_team"})
LOOKUP_TOOL_NAMES = frozenset(spec["function"]["name"] for spec in TOOL_SPECS)
# Read-only against live state (hyp copies then discards).
READONLY_TOOL_NAMES = LOOKUP_TOOL_NAMES | {"check_hypothetical"}


def _spec(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required}}}


_INT = {"type": "integer"}
_STR = {"type": "string"}

STATE_TOOL_SPECS: list[dict[str, Any]] = [
    _spec("lock_slot", "Lock a species into a team slot. slot counts from 1.",
          {"slot": dict(_INT), "species": dict(_STR)}, ["slot", "species"]),
    _spec("unlock_slot", "Clear a fully locked team slot. slot counts from 1.",
          {"slot": dict(_INT)}, ["slot"]),
    _spec("reset_team", "Clear the whole team.", {}, []),
    _spec("commit_slot", "Confirm the pending build. Refuses when nothing is pending.", {}, []),
    _spec("read_team", "Read the current team. Slot numbers in the result count from 1.", {}, []),
]

_PLACEMENT = {
    "type": "object",
    "properties": {"species": dict(_STR), "item": dict(_STR)},
}
HYP_TOOL_SPECS: list[dict[str, Any]] = [
    _spec(
        "check_hypothetical",
        "Check a what-if placement on a copy of the team. Never writes the live team. "
        "Pass placements as species and/or item pairs. conflicts_with_slot counts from 1.",
        {"placements": {"type": "array", "items": _PLACEMENT}},
        ["placements"],
    ),
]


def combined_specs() -> list[dict[str, Any]]:
    """A new list. Does not append to TOOL_SPECS."""
    return [*TOOL_SPECS, *STATE_TOOL_SPECS, *HYP_TOOL_SPECS]


def _merge(state: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    return {**state, **patch}


def _refuse(message: str) -> dict[str, Any]:
    return {"slot_commit_error": message}


def slot_signature(slot: Slot) -> tuple[Any, ...]:
    """Every Slot field: Attr fields as (name, value, locked), other fields as (name, value)."""
    out: list[Any] = []
    for field in fields(Slot):
        value = getattr(slot, field.name)
        if isinstance(value, Attr):
            out.append((field.name, to_jsonable(value.value), value.locked))
        else:
            out.append((field.name, to_jsonable(value)))
    return tuple(out)


def read_team(state: dict[str, Any]) -> dict[str, Any]:
    slots = []
    for index, slot in enumerate(state["team_draft"]):
        slots.append({
            "slot": display_slot(index),
            "species": slot.species.value,
            "species_locked": slot.species.locked,
            "attrs": slot_signature(slot),
        })
    return {"slots": slots}


def lock_slot(state: dict[str, Any], user_slot: object, species: object) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(species, str) or not species:
        return state, _refuse("species is required")
    try:
        index = user_slot_to_index(user_slot, team_size=len(state["team_draft"]))
    except SlotIndexError as exc:
        return state, _refuse(str(exc))
    patch = apply_lock({**state, "turn_payload": {"slot_index": index, "attr": "species", "value": species}})
    return _merge(state, patch), patch


def unlock_slot(state: dict[str, Any], user_slot: object) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        index = user_slot_to_index(user_slot, team_size=len(state["team_draft"]))
    except SlotIndexError as exc:
        return state, _refuse(str(exc))
    patch = unlock_locked_slot({**state, "turn_payload": {"slot_index": index}})
    return _merge(state, patch), patch


def reset_team_state(state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    patch = reset_team({**state, "turn_payload": {}})
    return _merge(state, patch), patch


def commit_slot(state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    patch = commit_full_slot(state)
    return _merge(state, patch), patch


def _first_free(draft: list[Slot]) -> int | None:
    for index, slot in enumerate(draft):
        if not slot.species.value:
            return index
    return None


def _slot_for_species(draft: list[Slot], species: str) -> int | None:
    want = species.casefold()
    for index, slot in enumerate(draft):
        if slot.species.value and str(slot.species.value).casefold() == want:
            return index
    return None


def check_hypothetical(state: dict[str, Any], placements: object) -> dict[str, Any]:
    """Validate proposed species/item placements on a discarded copy of team_draft.

    Decision (C2): the validator assumes every species value on the draft is locked.
    Species named in a placement but absent from the live team are written onto the
    first free slot of the COPY (ascending index), locked=True, then discarded with
    the copy. Item-only placements use the first free slot. No free slot → refuse.
    Live team_draft and pending are never written.
    """
    if not isinstance(placements, list) or not placements:
        return {"verdict": "bad_value", "conflicts_with_slot": None,
                "message": "placements must be a non-empty list of species/item pairs"}
    draft = deepcopy(list(state["team_draft"]))
    last_ok: dict[str, Any] = {"verdict": "ok", "conflicts_with_slot": None, "message": None}
    for raw in placements:
        if not isinstance(raw, dict):
            return {"verdict": "bad_value", "conflicts_with_slot": None,
                    "message": "each placement must be an object with species and/or item"}
        species = raw.get("species")
        item = raw.get("item")
        if not species and not item:
            return {"verdict": "bad_value", "conflicts_with_slot": None,
                    "message": "each placement needs species and/or item"}
        index: int | None = None
        if isinstance(species, str) and species.strip():
            index = _slot_for_species(draft, species)
            if index is None:
                index = _first_free(draft)
                if index is None:
                    return {"verdict": "bad_slot_index", "conflicts_with_slot": None,
                            "message": "no free slot on the copy for a species not on the team"}
                verdict = validate_team_value("species", species, slot_index=index, team_draft=draft)
                if verdict.refusal is not None:
                    other = verdict.refusal.conflicts_with_slot
                    return {
                        "verdict": verdict.refusal.kind,
                        "conflicts_with_slot": None if other is None else int(display_slot(other)),
                        "message": verdict.refusal.message,
                    }
                draft[index] = replace(
                    draft[index], species=Attr(value=verdict.canonical, locked=True)
                )
        else:
            index = _first_free(draft)
            if index is None:
                return {"verdict": "bad_slot_index", "conflicts_with_slot": None,
                        "message": "no free slot on the copy for an item-only placement"}
        if isinstance(item, str) and item.strip():
            assert index is not None
            verdict = validate_team_value("item", item, slot_index=index, team_draft=draft)
            if verdict.refusal is not None:
                other = verdict.refusal.conflicts_with_slot
                return {
                    "verdict": verdict.refusal.kind,
                    "conflicts_with_slot": None if other is None else int(display_slot(other)),
                    "message": verdict.refusal.message,
                }
            draft[index] = replace(
                draft[index], item=Attr(value=verdict.canonical, locked=True)
            )
        last_ok = {"verdict": "ok", "conflicts_with_slot": None, "message": None}
    return last_ok


def draft_signature(state: dict[str, Any]) -> tuple[Any, ...]:
    """Whole-team write detector. Prefers team_draft; snapshots carry attrs from read_team."""
    if "team_draft" in state:
        return tuple(slot_signature(slot) for slot in state["team_draft"])
    return tuple(tuple(row["attrs"]) for row in state.get("slots") or ())


def mechanical_class(before: dict[str, Any], after: dict[str, Any], tool_calls: list[dict[str, Any]]) -> str:
    """wrote, then refused, then lookup only, then no change."""
    if draft_signature(before) != draft_signature(after):
        return "wrote"
    for call in tool_calls:
        if call["name"] in STATE_TOOL_NAMES and (call.get("result") or {}).get("slot_commit_error"):
            return "refused"
    if tool_calls and all(call["name"] in READONLY_TOOL_NAMES for call in tool_calls):
        return "lookup only"
    return "no change"
