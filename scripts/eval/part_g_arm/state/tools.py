"""State tools for the Part G arm. Each wrapper calls one existing node.

Slot arguments are the user's number. Conversion happens once, here, through
user_slot_to_index. A bad slot does not call the node and does not change state.
A node refusal is merged by copying only the keys the node returned.

check_hypothetical copies the draft, validates on the copy, and discards it.
"""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import fields, replace
from pathlib import Path
from typing import Any

from recommender.arm_tools import TOOL_SPECS, to_jsonable
from recommender.nodes import (
    apply_lock,
    apply_provisional_option,
    commit_full_slot,
    handle_archetype_change,
    record_constraint,
    record_rejection,
    refine_provisional_slot,
    reset_team,
    restore_constraint,
    unlock_locked_slot,
)
from recommender.slot_index import SlotIndexError, display_slot, user_slot_to_index
from recommender.state import Attr, PendingSlotIntent, Slot, all_locked, slot_fingerprint
from recommender.team_validation import validate_team_value
from recommender.turn_intent import _clear_pending_keys

STATE_TOOL_NAMES = frozenset({
    "lock_slot", "unlock_slot", "reset_team", "commit_slot", "read_team",
    "select_option", "confirm_build", "reject_pending", "reject_option",
    "reject_all", "read_rejected", "edit_slot_field",
    "add_constraint", "read_constraints", "restore_constraint",
    "show_candidates", "change_archetype", "read_archetype",
})
LOOKUP_TOOL_NAMES = frozenset(spec["function"]["name"] for spec in TOOL_SPECS)
# Read-only against live state (hyp copies then discards; read_* do not write).
READONLY_TOOL_NAMES = LOOKUP_TOOL_NAMES | {
    "check_hypothetical", "read_pending", "read_rejected", "read_constraints",
    "read_archetype", "solve_spread", "check_learnset", "find_species",
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
        "Close the pending screen and record nothing. The same options can be offered again. "
        "Does not add species to the rejected list.",
        {},
        [],
    ),
    _spec(
        "reject_option",
        "Reject one candidate_selection option by its 1-based option number. "
        "The species is recorded as rejected, stays filtered out for the rest of the "
        "session and after a reset, and there is no undo.",
        {"option": dict(_INT)},
        ["option"],
    ),
    _spec(
        "reject_all",
        "Reject every candidate_selection option, then clear the pending screen once. "
        "Each species is recorded as rejected, stays filtered out for the rest of the "
        "session and after a reset, and there is no undo. "
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
    _spec(
        "edit_slot_field",
        "Change one locked field on a team slot (item, ability, nature, spread, or "
        "moveset). slot counts from 1. Uses the same validators as apply_lock / "
        "provisional edit; refusal writes nothing and keeps the pending screen. "
        "Does not silently edit other fields. Result includes consequences computed "
        "from data (type-boost vs remaining damaging moves of that type; Choice-lock "
        "vs status moves except Trick/Switcheroo; Status self-boosters sharing a stat).",
        {
            "slot": dict(_INT),
            "field": {
                "type": "string",
                "description": "item | ability | nature | spread | moveset",
            },
            "value": {
                "description": (
                    "New value: string for item/ability/nature; object of six SP ints "
                    "for spread; array of four move names for moveset."
                )
            },
        },
        ["slot", "field", "value"],
    ),
    _spec(
        "add_constraint",
        "Record a team constraint via build_constraint + record_constraint. "
        "predicate and scope are required. groundedness is "
        "mechanically-checkable | enumerable-but-uncoded | judgment-only. "
        "For type/ability/item must-haves pass mechanical_kind and value "
        "(maps to mechanical_value). mechanical_kind=type exists for MS6 Water. "
        "Ban-ability / ban-weather have no mechanical kind — use judgment-only "
        "(e.g. No Intimidate / No weather). Optional slot (1-based) is echoed in "
        "the predicate and read-back; product Constraint has no slot_index field. "
        "Does not build a draft-condition store.",
        {
            "predicate": dict(_STR),
            "scope": {
                "type": "string",
                "description": "per_slot | team_wide",
            },
            "groundedness": {
                "type": "string",
                "description": (
                    "mechanically-checkable | enumerable-but-uncoded | judgment-only"
                ),
            },
            "slot": dict(_INT),
            "mechanical_kind": {
                "type": "string",
                "description": "type | ability | item | no_duplicate_items",
            },
            "value": dict(_STR),
        },
        ["predicate", "scope", "groundedness"],
    ),
    _spec(
        "read_constraints",
        "Read active and inactive constraints (predicate, scope, groundedness, "
        "mechanical kind/value, still_active, optional slot echo). Does not change state.",
        {},
        [],
    ),
    _spec(
        "restore_constraint",
        "True-swap restore of the most recent constraints_superseded entry "
        "(newest-wins undo). Writes nothing when the log is empty.",
        {},
        [],
    ),
    _spec(
        "show_candidates",
        "Run the CLI candidate producer for an open slot (discover_single_locked "
        "or discover_multi_locked → present_candidates) and write a "
        "candidate_selection pending screen. slot counts from 1 and must be "
        "the next open blank slot. Optional n caps how many options are kept. "
        "Options carry producer source and evidence only. Honors rejected "
        "species (lineage filter). Does not write the team. Empty team "
        "(no locked anchor) refuses — bootstrap is out of scope. allow_live=False.",
        {"slot": dict(_INT), "n": dict(_INT)},
        ["slot"],
    ),
    _spec(
        "check_learnset",
        "Read-only: whether a species learns a move in the Champions learnset "
        "(legal_moves_for / resolve_learnset). Not a new rule. Returns "
        "learns=true|false and the species/move canonical ids used.",
        {"species": dict(_STR), "move": dict(_STR)},
        ["species", "move"],
    ),
    _spec(
        "change_archetype",
        "Set the team archetype from component strings (e.g. rain, offense) via "
        "handle_archetype_change. Does not clear locked slots; returns conflict "
        "audit for rain themes (non-rain weather abilities; sun charge moves like "
        "Solar Beam). Calc may be used by reconcile for fit checks (localhost).",
        {"components": {"type": "array", "items": dict(_STR)}},
        ["components"],
    ),
    _spec(
        "read_archetype",
        "Read the current archetype Attr (components, locked). Does not change state.",
        {},
        [],
    ),
    _spec(
        "find_species",
        "Read-only search over legal Champions species. Optional AND filters: "
        "types (species must have every listed type), learns_move, ability, "
        "stat_formula ({expr, op, value} over base_stats hp|atk|def|spa|spd|spe, "
        "e.g. expr 2*hp+def+spd op >= value 350), include_formes (default true; "
        "false drops Mega formes), optional n cap after name sort. Returns "
        "canonical species names. Does not write state.",
        {
            "types": {"type": "array", "items": dict(_STR)},
            "learns_move": dict(_STR),
            "ability": dict(_STR),
            "stat_formula": {
                "type": "object",
                "properties": {
                    "expr": dict(_STR),
                    "op": dict(_STR),
                    "value": {"type": "number"},
                },
            },
            "include_formes": {"type": "boolean"},
            "n": dict(_INT),
        },
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

_CONSTRAINT = {
    "type": "object",
    "description": (
        "Monotone only: type=survive|outspeed|ko. "
        "survive: attacker{species,nature,ability?,item?,sp|evs?} AND top-level move "
        "(move is a sibling of attacker, never nested inside it), field?. "
        "outspeed: target_spe (int Spe stat) or species+nature+spe_sp. "
        "ko: defender{...} AND top-level move, field?. "
        "Ability may be omitted only when the species has exactly one legal ability. "
        "Refuses underspeed, Trick Room, exact stats."
    ),
}
SPREAD_TOOL_SPECS: list[dict[str, Any]] = [
    _spec(
        "solve_spread",
        "Find one 66-SP spread for monotone survive/outspeed/ko constraints, "
        "closest in L1 to a 66-SP Showdown joint reference. Read-only: does not "
        "lock or write team/pending. Returns status "
        "(optimal | feasible | infeasible | unknown | invalid_arguments), "
        "spread, matched rank/distance, and calc-verified constraint results. "
        "invalid_arguments means bad input (wrong field or shape); unknown means "
        "the search hit its budget or time limit. Say 'no solution' only when "
        "status is infeasible. Example (dev species): "
        '{"species":"Venusaur-Mega","constraints":['
        '{"type":"survive","attacker":{"species":"Beedrill-Mega","nature":"Jolly",'
        '"sp":{"hp":0,"atk":32,"def":0,"spa":0,"spd":0,"spe":32}},'
        '"move":"U-turn","field":{"gameType":"Doubles"}},'
        '{"type":"outspeed","target_spe":100}]} '
        "(Thick Fat / Adaptability filled from data when omitted — single legal ability).",
        {
            "species": dict(_STR),
            "constraints": {"type": "array", "items": _CONSTRAINT},
            "ability": dict(_STR),
            "item": dict(_STR),
        },
        ["species", "constraints"],
    ),
]


def combined_specs() -> list[dict[str, Any]]:
    """A new list. Does not append to TOOL_SPECS.

    State-side: get_move_static description notes priority (4h enrichment); arm_tools
    schema text is otherwise unchanged.
    """
    lookups: list[dict[str, Any]] = []
    for spec in TOOL_SPECS:
        if spec["function"]["name"] == "get_move_static":
            fn = dict(spec["function"])
            fn["description"] = (
                "Type, category, base power and priority of a move "
                "(priority from data/moves/static.v1.json)."
            )
            lookups.append({**spec, "function": fn})
        else:
            lookups.append(spec)
    return [*lookups, *STATE_TOOL_SPECS, *HYP_TOOL_SPECS, *SPREAD_TOOL_SPECS]


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


_EDIT_FIELDS = frozenset({"item", "ability", "nature", "spread", "moveset", "moves"})


def edit_slot_field(
    state: dict[str, Any], user_slot: object, field: object, value: object
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Replace one field using the same validators as apply_lock; no silent sibling edits.

    Incomplete slots go through apply_lock. Fully locked slots cannot use apply_lock
    (product refuses revise-via-lock); they take the same Attr write +
    reconcile_on_sibling_change path apply_lock_single uses after validation.
    """
    from recommender.legality import check_set, load_snapshot, species_can_have_ability
    from recommender.reconcile import reconcile_on_sibling_change
    from scripts.eval.part_g_arm.state.edit_consequences import consequences_after_edit

    if not isinstance(field, str) or field not in _EDIT_FIELDS:
        return state, _refuse("field must be item|ability|nature|spread|moveset")
    attr = "moveset" if field == "moves" else field
    try:
        index = user_slot_to_index(user_slot, team_size=len(state["team_draft"]))
    except SlotIndexError as exc:
        return state, _refuse(str(exc))

    slot = state["team_draft"][index]
    pending_kept = state.get("pending_presentation")

    if not all_locked(slot):
        patch = apply_lock(
            {
                **state,
                "turn_payload": {"slot_index": index, "attr": attr, "value": value},
            }
        )
        if patch.get("slot_commit_error"):
            return state, _refuse(str(patch["slot_commit_error"]))
        after = _merge(state, patch)
    else:
        # Validate then write one Attr (lock_attr semantics without the all_locked gate).
        snap = load_snapshot()
        write_value: object = value
        if attr in {"species", "item"}:
            verdict = validate_team_value(
                attr, value, slot_index=index, team_draft=state["team_draft"], snap=snap
            )
            if verdict.refusal is not None:
                return state, _refuse(verdict.refusal.message)
            write_value = verdict.canonical
        elif attr == "ability":
            if not isinstance(value, str) or not value.strip():
                return state, _refuse("ability is required")
            sp = slot.species.value
            if not sp or not species_can_have_ability(snap, sp, value):
                return state, _refuse(f"{value!r} is not a legal ability for {sp}")
            write_value = value
        elif attr == "moveset":
            if not isinstance(value, (list, tuple)) or len(value) != 4:
                return state, _refuse("moveset requires exactly four moves")
            sp = slot.species.value
            if not sp:
                return state, _refuse("species must be locked before editing moveset")
            legality = check_set(
                sp,
                list(value),
                slot.item.value,
                ability=slot.ability.value,
                team_draft=state["team_draft"],
                exclude_slot=index,
            )
            if not legality.ok:
                detail = "; ".join(
                    f"{f.kind}:{f.element}" for f in legality.failures
                )
                return state, _refuse(f"illegal moveset: {detail}")
            write_value = list(value)
        elif attr == "nature":
            if not isinstance(value, str) or not value.strip():
                return state, _refuse("nature is required")
            write_value = value
        elif attr == "spread":
            if not isinstance(value, dict):
                return state, _refuse("spread must be an object of six SP ints")
            write_value = value
        else:
            return state, _refuse(f"unsupported field {attr}")

        new_attr = Attr(
            value=write_value,
            locked=True,
            reason=getattr(getattr(slot, attr), "reason", None),
            exempt_from_theme=getattr(getattr(slot, attr), "exempt_from_theme", False),
        )
        # Write only the edited field (no silent sibling clears — GS1/TB2/RB1).
        new_slot = replace(slot, **{attr: new_attr})
        components = (state.get("archetype") or Attr()).value
        # Reconcile for reporting only; discard slot mutations that would clear siblings.
        _probed, superseded, pending_flags = reconcile_on_sibling_change(
            new_slot,
            attr,
            slot_index=index,
            turn=state.get("turn", 0),
            components=components,
        )
        draft = list(state["team_draft"])
        draft[index] = new_slot
        after = {
            **state,
            "team_draft": draft,
            "slot_commit_error": None,
            "pending_presentation": pending_kept,
        }
        if superseded:
            after["superseded"] = [*state.get("superseded", []), *superseded]
        if pending_flags:
            after["pending_flags"] = [*state.get("pending_flags", []), *pending_flags]

    facts = consequences_after_edit(after["team_draft"][index], changed_field=attr)
    result = {
        "ok": True,
        "slot": display_slot(index),
        "field": attr,
        "consequences": facts,
        "reconcile_pending_flags": list(after.get("pending_flags") or []),
        "superseded": list(after.get("superseded") or []),
    }
    return after, result


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


_SLOT_PRED_RE = re.compile(r"^slot\s+(\d+)\b", re.I)
_GROUND = frozenset(
    {"mechanically-checkable", "enumerable-but-uncoded", "judgment-only"}
)
_SCOPES = frozenset({"per_slot", "team_wide"})
_MECH_KINDS = frozenset({"type", "ability", "item", "no_duplicate_items"})


def _constraint_row(c: Any) -> dict[str, Any]:
    """JSON row for one Constraint (dataclass or already-dict)."""
    if hasattr(c, "predicate"):
        pred = str(c.predicate or "")
        mech = getattr(c, "mechanical", None)
        row: dict[str, Any] = {
            "predicate": pred,
            "type": getattr(c, "type", None),
            "scope": getattr(c, "scope", None),
            "groundedness": getattr(c, "groundedness", None),
            "still_active": getattr(c, "still_active", True),
            "source_turn": getattr(c, "source_turn", None),
            "mechanical_kind": getattr(mech, "kind", None) if mech else None,
            "mechanical_value": getattr(mech, "value", None) if mech else None,
        }
    else:
        mech = (c or {}).get("mechanical") or {}
        pred = str((c or {}).get("predicate") or "")
        row = {
            "predicate": pred,
            "type": (c or {}).get("type"),
            "scope": (c or {}).get("scope"),
            "groundedness": (c or {}).get("groundedness"),
            "still_active": (c or {}).get("still_active", True),
            "source_turn": (c or {}).get("source_turn"),
            "mechanical_kind": mech.get("kind") if isinstance(mech, dict) else None,
            "mechanical_value": mech.get("value") if isinstance(mech, dict) else None,
        }
    m = _SLOT_PRED_RE.match(pred)
    if m:
        row["slot"] = int(m.group(1))
    return row


def read_constraints(state: dict[str, Any]) -> dict[str, Any]:
    """Read-only constraint list. Slot echo comes from predicate prefix when present."""
    return {"constraints": [_constraint_row(c) for c in state.get("constraints") or []]}


def add_constraint(
    state: dict[str, Any],
    predicate: object,
    scope: object,
    groundedness: object,
    *,
    slot: object = None,
    mechanical_kind: object = None,
    value: object = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Wrap record_constraint with structured args. No draft-condition store."""
    if not isinstance(predicate, str) or not predicate.strip():
        return state, _refuse("predicate is required")
    if scope not in _SCOPES:
        return state, _refuse("scope must be per_slot | team_wide")
    if groundedness not in _GROUND:
        return state, _refuse(
            "groundedness must be mechanically-checkable | "
            "enumerable-but-uncoded | judgment-only"
        )
    pred = predicate.strip()
    slot_echo: int | None = None
    if slot is not None:
        try:
            index = user_slot_to_index(slot, team_size=len(state["team_draft"]))
        except SlotIndexError as exc:
            return state, _refuse(str(exc))
        slot_echo = index + 1  # 1-based int (display_slot is str; options use ints)
        if not _SLOT_PRED_RE.match(pred):
            pred = f"slot {slot_echo} {pred}"

    payload: dict[str, Any] = {
        "type": "hard",
        "predicate": pred,
        "scope": scope,
        "groundedness": groundedness,
    }
    if groundedness == "judgment-only":
        if mechanical_kind is not None or (isinstance(value, str) and value.strip()):
            return state, _refuse(
                "judgment-only constraints must omit mechanical_kind/value"
            )
    else:
        if mechanical_kind is not None:
            if mechanical_kind not in _MECH_KINDS:
                return state, _refuse(
                    "mechanical_kind must be type | ability | item | no_duplicate_items"
                )
            payload["mechanical_kind"] = mechanical_kind
            if mechanical_kind != "no_duplicate_items":
                if not isinstance(value, str) or not value.strip():
                    return state, _refuse(
                        "mechanical_kind requires nonempty value"
                    )
                payload["mechanical_value"] = value.strip()

    patch = record_constraint(
        {**state, "turn_payload": payload, "turn": state.get("turn", 0)}
    )
    if patch.get("slot_commit_error"):
        return state, _refuse(str(patch["slot_commit_error"]))
    after = _merge(state, patch)
    latest = (after.get("constraints") or [])[-1]
    result = {
        "ok": True,
        "constraint": _constraint_row(latest),
        "constraints": [_constraint_row(c) for c in after.get("constraints") or []],
    }
    if slot_echo is not None:
        result["slot"] = slot_echo
    return after, result


def restore_constraint_tool(
    state: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Pop newest constraints_superseded entry (true-swap). Empty log → refuse."""
    if not state.get("constraints_superseded"):
        return state, _refuse("no superseded constraint to restore")
    before_sig = _constraints_signature(state.get("constraints"))
    patch = restore_constraint(state)
    after = _merge(state, patch)
    if _constraints_signature(after.get("constraints")) == before_sig and not patch:
        return state, _refuse("restore_constraint could not apply (stale log entry)")
    return after, {
        "ok": True,
        "constraints": [_constraint_row(c) for c in after.get("constraints") or []],
    }


def _evidence_strings(evidence: object) -> list[str]:
    """Flatten producer evidence to strings only — no arm-added fields."""
    out: list[str] = []
    for item in evidence or ():
        if hasattr(item, "evidence"):
            out.extend(str(x) for x in (getattr(item, "evidence") or ()))
        elif isinstance(item, dict):
            for x in item.get("evidence") or ():
                out.append(str(x))
        elif isinstance(item, str):
            out.append(item)
    return out


def _rejected_lineages(rejected: object) -> set[str]:
    from recommender.usage_data import lineage_ids

    out: set[str] = set()
    for row in rejected or ():
        if not isinstance(row, dict):
            continue
        species = row.get("species")
        if isinstance(species, str) and species.strip():
            out.update(lineage_ids(species))
    return out


def _filter_pending_rejected(
    pending: dict[str, Any], rejected: object
) -> dict[str, Any]:
    """Drop options whose lineage is on the rejected list (MT4)."""
    banned = _rejected_lineages(rejected)
    if not banned:
        return pending
    from recommender.usage_data import lineage_ids

    kept = []
    for opt in pending.get("options") or []:
        species = opt.get("species")
        if not isinstance(species, str) or not species:
            continue
        if set(lineage_ids(species)) & banned:
            continue
        kept.append(opt)
    return {**pending, "options": kept}


def _option_rows(pending: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i, opt in enumerate(pending.get("options") or []):
        rows.append(
            {
                "number": i + 1,
                "species": opt.get("species"),
                "source": opt.get("source"),
                "evidence": _evidence_strings(opt.get("evidence")),
            }
        )
    return rows


def check_learnset(state: dict[str, Any], species: object, move: object) -> dict[str, Any]:
    """Read-only learnset check via legality.legal_moves_for. Never writes state."""
    from recommender.ids import to_id
    from recommender.legality import legal_moves_for, load_snapshot
    from recommender.species_resolve import lookup_species_id

    _ = state
    if not isinstance(species, str) or not species.strip():
        return {"status": "error", "message": "species is required", "learns": None}
    if not isinstance(move, str) or not move.strip():
        return {"status": "error", "message": "move is required", "learns": None}
    snap = load_snapshot()
    sid = lookup_species_id(species, snap)
    if sid is None:
        return {
            "status": "not_found",
            "species": species,
            "move": move,
            "learns": False,
            "message": f"unknown species {species!r}",
        }
    name = str(snap["species"][sid].get("name") or species)
    legal = {to_id(m) for m in legal_moves_for(name, snap)}
    mid = to_id(move)
    learns = mid in legal
    return {
        "status": "ok",
        "species": name,
        "move": move.strip(),
        "move_id": mid,
        "learns": learns,
    }


_STATIC_MOVES_PATH = Path(__file__).resolve().parents[4] / "data" / "moves" / "static.v1.json"
_static_moves_cache: dict[str, Any] | None = None


def _static_moves() -> dict[str, Any]:
    global _static_moves_cache
    if _static_moves_cache is None:
        import json

        doc = json.loads(_STATIC_MOVES_PATH.read_text(encoding="utf-8"))
        _static_moves_cache = doc.get("moves") or {}
    return _static_moves_cache


def with_move_priority(result: dict[str, Any]) -> dict[str, Any]:
    """Attach priority from data/moves/static.v1.json onto a get_move_static result.

    ArmTools.get_move_static omits priority; the static blob has it. State-side
    enrichment only — does not edit recommender/arm_tools.py.
    """
    from recommender.ids import to_id

    if result.get("status") != "ok":
        return result
    move = result.get("move")
    if not isinstance(move, str):
        return result
    entry = _static_moves().get(to_id(move))
    if not isinstance(entry, dict) or "priority" not in entry:
        return result
    return {**result, "priority": entry["priority"]}


_STAT_NAMES = frozenset({"hp", "atk", "def", "spa", "spd", "spe"})
_STAT_OPS = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: a == b,
}


def _eval_stat_expr(expr: str, stats: dict[str, int]) -> int | None:
    """Evaluate a closed expr over hp|atk|def|spa|spd|spe with + * and integers.

    ``def`` is a Python keyword, so it is rewritten to STAT_DEF before ast.parse.
    """
    import ast

    rewritten = re.sub(r"\bdef\b", "STAT_DEF", expr.strip(), flags=re.IGNORECASE)

    def walk(node: ast.AST) -> int:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Name):
            key = "def" if node.id.casefold() == "stat_def" else node.id.casefold()
            if key not in _STAT_NAMES:
                raise ValueError(f"unknown stat {node.id!r}")
            return int(stats[key])
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return int(node.value)
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mult)):
            left, right = walk(node.left), walk(node.right)
            return left + right if isinstance(node.op, ast.Add) else left * right
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -walk(node.operand)
        raise ValueError("stat_formula expr allows only hp|atk|def|spa|spd|spe, +, *, integers")

    try:
        return walk(ast.parse(rewritten, mode="eval"))
    except (ValueError, SyntaxError, KeyError, TypeError):
        return None


def find_species(
    state: dict[str, Any],
    *,
    types: object = None,
    learns_move: object = None,
    ability: object = None,
    stat_formula: object = None,
    include_formes: object = True,
    n: object = None,
) -> dict[str, Any]:
    """Read-only legal-species search. AND filters. Never writes state."""
    from recommender.arm_teammates import is_mega_forme
    from recommender.ids import to_id
    from recommender.legality import (
        is_species_legal,
        legal_moves_for,
        load_snapshot,
        species_can_have_ability,
        species_types,
    )

    _ = state
    snap = load_snapshot()
    type_need: list[str] = []
    if types is not None:
        if not isinstance(types, list) or not all(isinstance(t, str) and t.strip() for t in types):
            return {"status": "error", "message": "types must be a list of strings", "species": [], "count": 0}
        type_need = [t.strip() for t in types]
    move_id: str | None = None
    if learns_move is not None:
        if not isinstance(learns_move, str) or not learns_move.strip():
            return {"status": "error", "message": "learns_move must be a nonempty string", "species": [], "count": 0}
        move_id = to_id(learns_move)
    ability_s: str | None = None
    if ability is not None:
        if not isinstance(ability, str) or not ability.strip():
            return {"status": "error", "message": "ability must be a nonempty string", "species": [], "count": 0}
        ability_s = ability.strip()
    formula: dict[str, Any] | None = None
    if stat_formula is not None:
        if not isinstance(stat_formula, dict):
            return {"status": "error", "message": "stat_formula must be an object", "species": [], "count": 0}
        expr, op, value = stat_formula.get("expr"), stat_formula.get("op"), stat_formula.get("value")
        if not isinstance(expr, str) or not isinstance(op, str) or not isinstance(value, (int, float)):
            return {
                "status": "error",
                "message": "stat_formula needs expr (str), op (>=|<=|>|<|==), value (number)",
                "species": [],
                "count": 0,
            }
        if op not in _STAT_OPS:
            return {"status": "error", "message": f"unsupported op {op!r}", "species": [], "count": 0}
        formula = {"expr": expr, "op": op, "value": float(value)}
    keep_formes = True if include_formes is None else bool(include_formes)
    cap: int | None = None
    if n is not None:
        if not isinstance(n, int) or n < 1:
            return {"status": "error", "message": "n must be a positive integer", "species": [], "count": 0}
        cap = n

    if not type_need and move_id is None and ability_s is None and formula is None:
        return {
            "status": "error",
            "message": "at least one of types, learns_move, ability, stat_formula is required",
            "species": [],
            "count": 0,
        }

    names: list[str] = []
    for sid, entry in (snap.get("species") or {}).items():
        name = str(entry.get("name") or sid)
        if not is_species_legal(snap, name):
            continue
        if not keep_formes and is_mega_forme(name):
            continue
        if type_need:
            got = {t.casefold() for t in (species_types(snap, name) or [])}
            if not all(t.casefold() in got for t in type_need):
                continue
        if ability_s is not None and not species_can_have_ability(snap, name, ability_s):
            continue
        if move_id is not None:
            legal = {to_id(m) for m in legal_moves_for(name, snap)}
            if move_id not in legal:
                continue
        if formula is not None:
            raw = entry.get("base_stats") or entry.get("baseStats") or {}
            stats = {k: int(raw.get(k) or 0) for k in _STAT_NAMES}
            scored = _eval_stat_expr(formula["expr"], stats)
            if scored is None:
                return {
                    "status": "error",
                    "message": f"invalid stat_formula.expr {formula['expr']!r}",
                    "species": [],
                    "count": 0,
                }
            if not _STAT_OPS[formula["op"]](scored, formula["value"]):
                continue
        names.append(name)

    names = sorted(set(names), key=lambda s: s.casefold())
    if cap is not None:
        names = names[:cap]
    filters: dict[str, Any] = {}
    if type_need:
        filters["types"] = type_need
    if learns_move is not None:
        filters["learns_move"] = learns_move
    if ability_s is not None:
        filters["ability"] = ability_s
    if formula is not None:
        filters["stat_formula"] = formula
    filters["include_formes"] = keep_formes
    if cap is not None:
        filters["n"] = cap
    return {
        "status": "ok",
        "species": names,
        "count": len(names),
        "filters_applied": filters,
        "source": "legality snapshot (Showdown Champions mod extract)",
    }


def read_archetype(state: dict[str, Any]) -> dict[str, Any]:
    arch = state.get("archetype") or Attr()
    return {
        "components": list(arch.value or []) if arch.value is not None else [],
        "locked": bool(arch.locked),
    }


def _rain_conflict_audit(state: dict[str, Any], components: list[str]) -> list[dict[str, Any]]:
    """MS5 surface: non-rain weather abilities + sun charge moves on locked slots.

    Uses ABILITY_TO_FIELD and CHARGE_INSTANT_WEATHER. Pelipper/Drizzle (Rain) not flagged.
    """
    from recommender.coverage import ABILITY_TO_FIELD
    from recommender.ids import to_id
    from recommender.matchup import CHARGE_INSTANT_WEATHER

    lowered = {c.casefold() for c in components}
    if "rain" not in lowered:
        return []
    rain_labels = frozenset({"Rain", "Heavy Rain"})
    sun_labels = frozenset({"Sun", "Harsh Sunshine"})
    conflicts: list[dict[str, Any]] = []
    for index, slot in enumerate(state["team_draft"]):
        if not slot.species.value:
            continue
        ability = slot.ability.value
        if isinstance(ability, str) and ability.strip():
            field = ABILITY_TO_FIELD.get(to_id(ability)) or {}
            weather = field.get("weather")
            if weather and weather not in rain_labels:
                conflicts.append(
                    {
                        "slot": display_slot(index),
                        "species": slot.species.value,
                        "kind": "non_rain_weather_ability",
                        "ability": ability,
                        "weather": weather,
                        "reason": f"{ability} sets {weather}, not Rain",
                    }
                )
        moves = slot.moveset.value or []
        for move in moves:
            mid = to_id(str(move))
            weathers = CHARGE_INSTANT_WEATHER.get(mid)
            if weathers and (weathers & sun_labels) and not (weathers & rain_labels):
                conflicts.append(
                    {
                        "slot": display_slot(index),
                        "species": slot.species.value,
                        "kind": "rain_reduced_move",
                        "move": move,
                        "reason": f"{move} is sun-charged / rain-penalized on a rain team",
                    }
                )
    return conflicts


def change_archetype(
    state: dict[str, Any], components: object
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Wrap handle_archetype_change; surface rain conflict audit; keep locked slots."""
    if not isinstance(components, list) or not components:
        return state, _refuse("components must be a non-empty list of strings")
    if not all(isinstance(c, str) and c.strip() for c in components):
        return state, _refuse("each component must be a nonempty string")
    comps = [c.strip() for c in components]
    before_draft = draft_signature(state)
    patch = handle_archetype_change(
        {**state, "turn_payload": {"components": comps}}
    )
    after = _merge(state, patch)
    # Spec: locked slots untouched — if reconcile mutated draft, refuse and revert.
    if draft_signature(after) != before_draft:
        return state, _refuse(
            "archetype reconcile would edit locked slots; refusing to keep locks intact"
        )
    conflicts = _rain_conflict_audit(after, comps)
    return after, {
        "ok": True,
        "archetype": read_archetype(after),
        "conflicts": conflicts,
        "pending_flags": to_jsonable(after.get("pending_flags") or []),
    }


def show_candidates(
    state: dict[str, Any],
    user_slot: object,
    n: object = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """CLI producer → candidate_selection pending. Does not write team_draft."""
    from recommender.nodes import discover_multi_locked, discover_single_locked

    try:
        index = user_slot_to_index(user_slot, team_size=len(state["team_draft"]))
    except SlotIndexError as exc:
        return state, _refuse(str(exc))
    draft = state["team_draft"]
    if all_locked(draft[index]):
        return state, _refuse(f"slot {display_slot(index)} is already fully locked")
    # CLI fills the first blank open slot; refuse a different open index.
    open_blank = [
        i
        for i, slot in enumerate(draft)
        if not all_locked(slot)
        and not any(
            getattr(slot, name).locked or getattr(slot, name).value is not None
            for name in ("role", "species", "ability", "item", "moveset", "spread", "nature")
        )
    ]
    if not open_blank:
        return state, _refuse("no blank open slot for candidate discovery")
    if index != open_blank[0]:
        return state, _refuse(
            f"slot {display_slot(index)} is not the next open blank slot "
            f"(next is {display_slot(open_blank[0])})"
        )

    anchors = [slot for slot in draft if all_locked(slot)]
    if not anchors:
        return state, _refuse(
            "empty team: show_candidates needs a locked anchor; "
            "bootstrap intake is out of scope for the arm"
        )

    # Pinned usage only — discover_* reads offline blobs; calc may degrade.
    if len(anchors) == 1:
        patch = discover_single_locked(state, {})
    else:
        patch = discover_multi_locked(state, {})

    # Discovery must not mutate the draft via this tool.
    if "team_draft" in patch:
        patch = {k: v for k, v in patch.items() if k != "team_draft"}

    pending = patch.get("pending_presentation")
    if not isinstance(pending, dict) or pending.get("kind") != "candidate_selection":
        err = patch.get("candidate_discovery_error")
        msg = (
            getattr(err, "message", None)
            or (err.get("message") if isinstance(err, dict) else None)
            or "no candidate_selection screen produced"
        )
        return state, _refuse(str(msg))

    pending = {**pending, "slot_index": index}
    pending = _filter_pending_rejected(pending, state.get("rejected"))
    if isinstance(n, int) and not isinstance(n, bool) and n >= 1:
        pending = {**pending, "options": list(pending.get("options") or [])[:n]}
    elif n is not None:
        return state, _refuse("n must be a positive integer when provided")

    options = _option_rows(pending)
    if not options:
        # Empty after reject filter / producer — write teachable pending like CLI.
        pending = {
            **pending,
            "options": [],
            "prompt_text": pending.get("prompt_text")
            or "No more candidates for this slot.",
        }
        after = _merge(state, {**patch, "pending_presentation": pending, "slot_commit_error": None})
        return after, {
            "ok": True,
            "slot": index + 1,
            "options": [],
            "message": "no candidates",
            "candidate_discovery_error": to_jsonable(patch.get("candidate_discovery_error")),
        }

    after = _merge(
        state,
        {**patch, "pending_presentation": pending, "slot_commit_error": None},
    )
    return after, {
        "ok": True,
        "slot": index + 1,
        "options": options,
        "candidate_discovery_error": to_jsonable(patch.get("candidate_discovery_error")),
    }


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


def solve_spread_tool(
    state: dict[str, Any],
    species: object,
    constraints: object,
    ability: object = None,
    item: object = None,
) -> dict[str, Any]:
    """Read-only spread solve. Never writes team_draft or pending."""
    from scripts.eval.part_g_arm.state.spread_solve import solve_spread

    if not isinstance(species, str) or not species.strip():
        return {"status": "unknown", "error": "species is required", "no_reference": False}
    if not isinstance(constraints, list):
        return {"status": "unknown", "error": "constraints must be a list", "no_reference": False}
    kwargs: dict[str, Any] = {}
    if isinstance(ability, str) and ability.strip():
        kwargs["ability"] = ability
    if isinstance(item, str):
        kwargs["item"] = item
    # state is unused on purpose — keeps the tool read-only against live state.
    _ = state
    return solve_spread(species.strip(), constraints, **kwargs)


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


def archetype_signature(state: dict[str, Any]) -> tuple[Any, ...] | None:
    """Components + locked for Attr or snapshot dict. None when unset."""
    # Snapshots carry archetype_sig (may be None); live state carries archetype Attr.
    if "team_draft" not in state and "archetype" not in state and "archetype_sig" in state:
        emb = state["archetype_sig"]
        return tuple(emb) if emb is not None else None
    arch = state.get("archetype")
    if arch is None:
        return None
    if isinstance(arch, Attr):
        comps = arch.value or []
        return (tuple(comps), bool(arch.locked))
    if isinstance(arch, dict):
        comps = arch.get("components") or arch.get("value") or []
        return (tuple(comps), bool(arch.get("locked")))
    return (to_jsonable(arch),)


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
    if archetype_signature(before) != archetype_signature(after):
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
    if rejected_grew or a_cons != b_cons:
        # recorded: reject list grew OR constraints list changed (add/restore).
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
