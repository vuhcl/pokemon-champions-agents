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
from recommender.nodes import (
    apply_lock,
    apply_provisional_option,
    commit_full_slot,
    record_rejection,
    refine_provisional_slot,
    reset_team,
    unlock_locked_slot,
)
from recommender.slot_index import SlotIndexError, display_slot, user_slot_to_index
from recommender.state import Attr, PendingSlotIntent, Slot, all_locked, slot_fingerprint
from recommender.team_validation import validate_team_value
from recommender.turn_intent import _clear_pending_keys

STATE_TOOL_NAMES = frozenset({
    "lock_slot", "unlock_slot", "reset_team", "commit_slot", "read_team",
    "select_option", "confirm_build", "reject_pending", "reject_option",
    "reject_all", "read_rejected",
})
LOOKUP_TOOL_NAMES = frozenset(spec["function"]["name"] for spec in TOOL_SPECS)
# Read-only against live state (hyp copies then discards; read_* do not write).
READONLY_TOOL_NAMES = LOOKUP_TOOL_NAMES | {
    "check_hypothetical", "read_pending", "read_rejected",
}

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
    _spec(
        "read_pending",
        "Read the pending screen. Option numbers count from 1 and are not slot numbers.",
        {},
        [],
    ),
    _spec(
        "select_option",
        "Select a pending option by its 1-based option number from read_pending. "
        "Option numbers are not slot numbers. Partial stale gate: refuses if the target "
        "slot is fully locked or the option fails team validation; does not detect a "
        "candidate list built for an earlier team.",
        {"option": dict(_INT)},
        ["option"],
    ),
    _spec(
        "confirm_build",
        "Confirm the pending full build (same commit path as commit_slot). "
        "Partial stale gate plus commit_full_slot fingerprint check.",
        {},
        [],
    ),
    _spec(
        "reject_pending",
        "Dismiss the pending screen without recording any rejection.",
        {},
        [],
    ),
    _spec(
        "reject_option",
        "Reject one candidate_selection option by its 1-based option number.",
        {"option": dict(_INT)},
        ["option"],
    ),
    _spec(
        "reject_all",
        "Reject every candidate_selection option, then clear the pending screen once. "
        "Atomic: if any record fails, writes nothing. Refuses without a candidate_selection screen.",
        {},
        [],
    ),
    _spec(
        "read_rejected",
        "Read the rejected list (species, reason, turn). Does not change state.",
        {},
        [],
    ),
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


def confirm_build(state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """FBC affirm. Same node as commit_slot (commit_full_slot); commit_slot unchanged."""
    return commit_slot(state)


def _pending_options(pending: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten pending options with 1-based display numbers (not slot numbers)."""
    kind = pending.get("kind")
    rows: list[dict[str, Any]] = []
    if kind == "candidate_selection":
        for i, opt in enumerate(pending.get("options") or []):
            rows.append({
                "number": i + 1,
                "id": opt.get("species"),
                "label": opt.get("species"),
                "species": opt.get("species"),
                "_raw": opt,
            })
    elif kind == "full_build_confirmation":
        n = 0
        for group in pending.get("build_option_groups") or []:
            for opt in group.get("options") or []:
                n += 1
                oid = opt.get("option_id") or opt.get("id")
                rows.append({
                    "number": n,
                    "id": oid,
                    "label": opt.get("label"),
                    "species": None,
                    "_raw": opt,
                })
    return rows


def read_pending(state: dict[str, Any]) -> dict[str, Any]:
    pending = state.get("pending_presentation")
    if not isinstance(pending, dict):
        return {"kind": None, "options": []}
    options = [
        {"number": row["number"], "id": row["id"], "label": row["label"], "species": row["species"]}
        for row in _pending_options(pending)
    ]
    return {"kind": pending.get("kind"), "options": options}


def _option_number_ok(option: object, count: int) -> str | None:
    if isinstance(option, bool) or not isinstance(option, int):
        return f"option must be an integer, got {option!r}"
    if not 1 <= option <= count:
        return f"option {option} is outside 1..{count}"
    return None


def select_option(state: dict[str, Any], option: object) -> tuple[dict[str, Any], dict[str, Any]]:
    """Select by read_pending's 1-based option number. Partial stale gate (see docstring).

    Partial stale gate: no pending / bad number / target slot fully locked / chosen
    species fails validate_team_value. Does NOT detect a CS list built for an earlier
    team (OL10a). FBC also relies on apply_provisional_option / later commit fingerprint.
    """
    pending = state.get("pending_presentation")
    if not isinstance(pending, dict):
        return state, _refuse("no pending screen")
    rows = _pending_options(pending)
    err = _option_number_ok(option, len(rows))
    if err:
        return state, _refuse(err)
    assert isinstance(option, int)
    chosen = rows[option - 1]
    slot_index = int(pending.get("slot_index", 0))
    draft = state["team_draft"]
    if not 0 <= slot_index < len(draft):
        return state, _refuse("pending slot_index is out of range")
    if all_locked(draft[slot_index]):
        return state, _refuse("target slot is already fully locked")

    kind = pending.get("kind")
    if kind == "candidate_selection":
        species = chosen.get("species")
        if not isinstance(species, str) or not species:
            return state, _refuse("selected option has no species")
        verdict = validate_team_value("species", species, slot_index=slot_index, team_draft=draft)
        if verdict.refusal is not None:
            return state, _refuse(verdict.refusal.message)
        raw = chosen["_raw"]
        intent = PendingSlotIntent(
            schema_version=1,
            slot_index=slot_index,
            species=str(verdict.canonical or species),
            target_role_decision=raw.get("target_role_decision"),
            source=raw.get("source") or "threat",
            evidence=tuple(raw.get("evidence") or ()),
            base_slot_fingerprint=slot_fingerprint(draft[slot_index]),
        )
        # Refine's returned dict replaces CS with FBC (clear via node return, ADR-031).
        patch = refine_provisional_slot({**state, "pending_slot_intent": intent})
        return _merge(state, patch), patch

    if kind == "full_build_confirmation":
        oid = chosen.get("id")
        if not oid:
            return state, _refuse("selected build option has no option_id")
        patch = apply_provisional_option({
            **state,
            "turn_payload": {"option_ids": (str(oid),)},
        })
        return _merge(state, patch), patch

    return state, _refuse(f"select_option does not support pending kind {kind!r}")


def reject_pending(state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pending = state.get("pending_presentation")
    if not isinstance(pending, dict):
        return state, _refuse("no pending screen")
    # Shared helper used by nodes; clears the four pending keys (gate 2).
    patch = _clear_pending_keys()
    return _merge(state, patch), patch


def reject_option(state: dict[str, Any], option: object) -> tuple[dict[str, Any], dict[str, Any]]:
    pending = state.get("pending_presentation")
    if not isinstance(pending, dict) or pending.get("kind") != "candidate_selection":
        return state, _refuse("reject_option requires a candidate_selection screen")
    rows = _pending_options(pending)
    err = _option_number_ok(option, len(rows))
    if err:
        return state, _refuse(err)
    assert isinstance(option, int)
    species = rows[option - 1].get("species")
    if not isinstance(species, str) or not species:
        return state, _refuse("selected option has no species")
    slot_index = int(pending.get("slot_index", 0))
    patch = record_rejection({
        **state,
        "turn_payload": {"species": species, "reason": "user_reject", "slot_index": slot_index},
    })
    if patch.get("slot_commit_error"):
        return state, patch
    # record_rejection does not clear pending; shared helper does (gate 2).
    # Clears after the first option — cannot reject the rest; use reject_all.
    patch = {**patch, **_clear_pending_keys()}
    return _merge(state, patch), patch


def read_rejected(state: dict[str, Any]) -> dict[str, Any]:
    """Read-only rejected list. Same fields the snapshot grades."""
    rows = []
    for entry in state.get("rejected") or []:
        if isinstance(entry, dict):
            rows.append(
                {
                    "species": entry.get("species"),
                    "reason": entry.get("reason"),
                    "turn": entry.get("turn"),
                }
            )
    return {"rejected": rows}


def reject_all(state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Record every CS option, then clear pending once. Atomic on any refusal.

    reject_option cannot do this: it clears the screen after the first call.
    """
    pending = state.get("pending_presentation")
    if not isinstance(pending, dict):
        return state, _refuse("no pending screen")
    if pending.get("kind") != "candidate_selection":
        return state, _refuse("reject_all requires a candidate_selection screen")
    rows = _pending_options(pending)
    if not rows:
        return state, _refuse("candidate_selection screen has no options")
    slot_index = int(pending.get("slot_index", 0))
    working = state
    for row in rows:
        species = row.get("species")
        if not isinstance(species, str) or not species:
            return state, _refuse("an option has no species")
        patch = record_rejection({
            **working,
            "turn_payload": {
                "species": species,
                "reason": "user_reject",
                "slot_index": slot_index,
            },
        })
        if patch.get("slot_commit_error"):
            return state, patch
        working = {**working, **patch}
    final = {"rejected": working.get("rejected") or [], **_clear_pending_keys()}
    return _merge(state, final), final


def _first_species_free(draft: list[Slot]) -> int | None:
    for index, slot in enumerate(draft):
        if not slot.species.value:
            return index
    return None


def _first_item_only_free(draft: list[Slot]) -> int | None:
    """Item-only placements need a slot with neither species nor item (used-index tracking)."""
    for index, slot in enumerate(draft):
        if not slot.species.value and not slot.item.value:
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
    first species-free slot of the COPY (ascending index), locked=True, then discarded
    with the copy. Item-only placements use the first slot with neither species nor
    item (so two identical items hit Item Clause instead of overwriting one slot).
    No free slot → refuse. Live team_draft and pending are never written.
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
                index = _first_species_free(draft)
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
            index = _first_item_only_free(draft)
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


def _pending_signature(pending: object) -> tuple[Any, ...] | None:
    if not isinstance(pending, dict):
        return None
    options: list[Any] = []
    kind = pending.get("kind")
    if kind == "candidate_selection":
        for opt in pending.get("options") or []:
            options.append(opt.get("species") or opt.get("id"))
    elif kind == "full_build_confirmation":
        for group in pending.get("build_option_groups") or []:
            for opt in group.get("options") or []:
                options.append(opt.get("option_id") or opt.get("id") or opt.get("label"))
    return (
        pending.get("kind"),
        pending.get("slot_index"),
        tuple(options),
        pending.get("provisional_fingerprint"),
    )


def _intent_signature(intent: object) -> tuple[Any, ...] | None:
    if intent is None:
        return None
    if isinstance(intent, dict):
        return (intent.get("species"), intent.get("slot_index"))
    return (getattr(intent, "species", None), getattr(intent, "slot_index", None))


def _provisional_signature(prov: object) -> tuple[Any, ...] | None:
    if prov is None:
        return None
    if isinstance(prov, dict):
        return (
            prov.get("species"),
            prov.get("fingerprint") or prov.get("option_id"),
            to_jsonable(prov.get("overrides")),
        )
    return (
        getattr(prov, "species", None),
        getattr(prov, "fingerprint", None),
        None,
    )


def _rejected_signature(rejected: object) -> tuple[Any, ...]:
    rows = rejected or ()
    out: list[tuple[Any, ...]] = []
    for entry in rows:
        if isinstance(entry, dict):
            out.append((entry.get("species"), entry.get("reason"), entry.get("turn")))
        else:
            out.append((to_jsonable(entry),))
    return tuple(out)


def _constraints_signature(constraints: object) -> tuple[Any, ...]:
    return tuple(to_jsonable(c) for c in (constraints or ()))


def steering_signature(state: dict[str, Any]) -> tuple[Any, ...]:
    """Pending / intent / provisional / rejected / constraints. Snapshots embed this under steering."""
    embedded = state.get("steering")
    if embedded is not None and "team_draft" not in state:
        return tuple(embedded)
    return (
        _pending_signature(state.get("pending_presentation")),
        _intent_signature(state.get("pending_slot_intent")),
        _provisional_signature(state.get("provisional_slot")),
        _rejected_signature(state.get("rejected")),
        _constraints_signature(state.get("constraints")),
    )


def mechanical_class(before: dict[str, Any], after: dict[str, Any], tool_calls: list[dict[str, Any]]) -> str:
    """wrote > bound > recorded > dismissed > refused > lookup only > no change."""
    if draft_signature(before) != draft_signature(after):
        return "wrote"
    b_pending, b_intent, b_prov, b_rej, b_cons = steering_signature(before)
    a_pending, a_intent, a_prov, a_rej, a_cons = steering_signature(after)
    rejected_grew = len(a_rej) > len(b_rej)
    pending_cleared = b_pending is not None and a_pending is None
    # Bound: screen replaced/advanced (still present with a new sig), or intent/provisional set.
    bound = (
        (b_pending != a_pending and a_pending is not None)
        or (b_intent != a_intent and a_intent is not None)
        or (b_prov != a_prov and a_prov is not None)
    )
    if bound:
        return "bound"
    if rejected_grew:
        return "recorded"
    if (
        pending_cleared
        and a_intent is None
        and a_prov is None
        and a_rej == b_rej
        and a_cons == b_cons
    ):
        return "dismissed"
    for call in tool_calls:
        if call["name"] in STATE_TOOL_NAMES and (call.get("result") or {}).get("slot_commit_error"):
            return "refused"
    if tool_calls and all(call["name"] in READONLY_TOOL_NAMES for call in tool_calls):
        return "lookup only"
    return "no change"
