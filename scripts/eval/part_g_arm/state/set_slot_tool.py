"""set_slot: aggregated all-or-nothing wrapper over lock_slot / edit_slot_field / unlock_slot.

Behind the run flag `wrapper`. Validates every element first; applies nothing on any failure.
No new write paths — only the existing state tools.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from recommender.legality import load_snapshot, resolve_learnset, species_can_have_ability
from recommender.slot_index import SlotIndexError, display_slot, user_slot_to_index
from recommender.ids import to_id
from recommender.state import Attr, Slot, all_locked
from recommender.team_validation import validate_team_value

from scripts.eval.part_g_arm.state.draft_lock import (
    draft_contents_summary,
    slot_is_blank,
)
from scripts.eval.part_g_arm.state.tools import (
    draft_enabled,
    edit_slot_field,
    lock_slot,
    read_team,
    unlock_slot,
)

_ATTR_FIELDS = ("item", "ability", "nature", "spread", "moves")
_SEVEN = ("role", "species", "ability", "item", "moveset", "spread", "nature")


def _slot_occupied_partial(slot: Slot) -> bool:
    """Partly locked: some attr set/locked but not all_locked."""
    if all_locked(slot):
        return False
    return any(
        getattr(slot, name).locked or getattr(slot, name).value is not None
        for name in _SEVEN
    )


def _slot_open_for_default(slot: Slot) -> bool:
    """Default-first-open-slot rule. Under draft, any valued slot is not open."""
    if draft_enabled():
        return slot_is_blank(slot)
    return not all_locked(slot) and slot.species.value is None


def _normalize_requests(args: dict[str, Any]) -> list[dict[str, Any]] | str:
    """Return a list of per-slot request dicts, or an error string."""
    if "slots" in args and args["slots"] is not None:
        raw = args["slots"]
        if not isinstance(raw, list) or not raw:
            return "slots must be a non-empty list of slot requests"
        out: list[dict[str, Any]] = []
        for i, item in enumerate(raw):
            if not isinstance(item, dict):
                return f"slots[{i}] must be an object"
            out.append(dict(item))
        return out
    single = {
        k: args.get(k)
        for k in ("slot", "species", "item", "ability", "nature", "spread", "moves", "replace")
        if k in args and args.get(k) is not None
    }
    if "species" not in single and not any(k in single for k in _ATTR_FIELDS):
        return "set_slot requires species and/or at least one of item|ability|nature|moves|spread"
    return [single]


def _project_species(draft: list[Slot], index: int, species: str) -> list[Slot]:
    slot = draft[index]
    new_slot = replace(slot, species=Attr(value=species, locked=True))
    out = list(draft)
    out[index] = new_slot
    return out


def _project_item(draft: list[Slot], index: int, item: str) -> list[Slot]:
    slot = draft[index]
    new_slot = replace(slot, item=Attr(value=item, locked=True))
    out = list(draft)
    out[index] = new_slot
    return out


def _element(
    *,
    slot: int,
    field: str,
    value: object,
    ok: bool,
    cause: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {"slot": slot, "field": field, "value": value, "ok": ok}
    if cause is not None:
        row["cause"] = cause
    return row


def set_slot(state: dict[str, Any], args: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate every element, then apply via lock/edit/unlock. State unchanged on any failure."""
    args = dict(args or {})
    replace_flag = bool(args.get("replace") or False)
    normalized = _normalize_requests(args)
    if isinstance(normalized, str):
        return state, {
            "ok": False,
            "slot_commit_error": normalized,
            "elements": [],
            "replace": replace_flag,
        }

    snap = load_snapshot()
    draft = list(state["team_draft"])
    elements: list[dict[str, Any]] = []
    resolved: list[dict[str, Any]] = []  # index + fields ready to apply
    reserved_opens: set[int] = set()

    for req in normalized:
        req_replace = bool(req.get("replace")) if "replace" in req else replace_flag
        user_slot = req.get("slot")
        if user_slot is None:
            open_i = None
            for i, slot in enumerate(draft):
                if i in reserved_opens:
                    continue
                if _slot_open_for_default(slot):
                    open_i = i
                    break
            if open_i is None:
                elements.append(
                    _element(
                        slot=0,
                        field="slot",
                        value=None,
                        ok=False,
                        cause="no open slot (every slot is occupied or reserved by this request)",
                    )
                )
                continue
            index = open_i
        else:
            try:
                index = user_slot_to_index(user_slot, team_size=len(draft))
            except SlotIndexError as exc:
                elements.append(
                    _element(
                        slot=user_slot if isinstance(user_slot, int) else 0,
                        field="slot",
                        value=user_slot,
                        ok=False,
                        cause=str(exc),
                    )
                )
                continue

        disp = display_slot(index)
        slot_obj = draft[index]
        species = req.get("species")
        held = slot_obj.species.value

        # Species swap on a held species (locked or draft) needs replace=true.
        species_swap = (
            species is not None
            and held is not None
            and to_id(str(species)) != to_id(str(held))
        )
        needs_replace = species_swap and (
            all_locked(slot_obj) or (draft_enabled() and held is not None)
        )
        if needs_replace and not req_replace:
            contents = (
                draft_contents_summary(slot_obj)
                if draft_enabled()
                else f"fully locked holding {held}"
            )
            elements.append(
                _element(
                    slot=disp,
                    field="slot",
                    value=held,
                    ok=False,
                    cause=(
                        f"slot {disp} holds {contents}; "
                        "swapping species needs replace=true only after the user confirms"
                    ),
                )
            )
            elements.append(
                _element(
                    slot=disp,
                    field="species",
                    value=species,
                    ok=False,
                    cause=f"not applied: slot {disp} needs replace after confirmation",
                )
            )
            for field in _ATTR_FIELDS:
                if req.get(field) is not None:
                    elements.append(
                        _element(
                            slot=disp,
                            field=field,
                            value=req.get(field),
                            ok=False,
                            cause=f"not applied: slot {disp} needs replace after confirmation",
                        )
                    )
            continue

        # Partly locked: keep today's apply_lock path (no invent).
        _ = _slot_occupied_partial(slot_obj)

        projected = list(draft)
        if req_replace and species_swap and (
            all_locked(slot_obj) or (draft_enabled() and held is not None)
        ):
            # Project empty slot for clause checks (unlock then rewrite).
            from recommender.state import empty_slot

            projected[index] = empty_slot()

        req_elements_before = len(elements)
        canonical_species: str | None = None
        if species is not None:
            verdict = validate_team_value(
                "species", species, slot_index=index, team_draft=projected, snap=snap
            )
            if verdict.refusal is not None:
                elements.append(
                    _element(
                        slot=disp,
                        field="species",
                        value=species,
                        ok=False,
                        cause=verdict.refusal.message,
                    )
                )
            else:
                canonical_species = verdict.canonical
                elements.append(
                    _element(slot=disp, field="species", value=canonical_species, ok=True)
                )
                projected = _project_species(projected, index, str(canonical_species))

        if req.get("item") is not None:
            verdict = validate_team_value(
                "item", req["item"], slot_index=index, team_draft=projected, snap=snap
            )
            if verdict.refusal is not None:
                elements.append(
                    _element(
                        slot=disp,
                        field="item",
                        value=req["item"],
                        ok=False,
                        cause=verdict.refusal.message,
                    )
                )
            else:
                elements.append(
                    _element(slot=disp, field="item", value=verdict.canonical, ok=True)
                )
                projected = _project_item(projected, index, str(verdict.canonical))

        if req.get("ability") is not None:
            ab = req["ability"]
            sp_for_ab = canonical_species or (
                projected[index].species.value if projected[index].species.value else None
            )
            if not isinstance(ab, str) or not ab.strip():
                elements.append(
                    _element(slot=disp, field="ability", value=ab, ok=False, cause="ability is required")
                )
            elif not sp_for_ab:
                elements.append(
                    _element(
                        slot=disp,
                        field="ability",
                        value=ab,
                        ok=False,
                        cause="species must be set before ability",
                    )
                )
            elif not species_can_have_ability(snap, sp_for_ab, ab):
                elements.append(
                    _element(
                        slot=disp,
                        field="ability",
                        value=ab,
                        ok=False,
                        cause=f"{ab!r} is not a legal ability for {sp_for_ab}",
                    )
                )
            else:
                elements.append(_element(slot=disp, field="ability", value=ab, ok=True))

        moves = req.get("moves")
        if moves is not None:
            sp_for_mv = canonical_species or (
                projected[index].species.value if projected[index].species.value else None
            )
            if not isinstance(moves, (list, tuple)) or not moves:
                elements.append(
                    _element(
                        slot=disp,
                        field="moves",
                        value=moves,
                        ok=False,
                        cause="moves must be a non-empty list of move names",
                    )
                )
            elif not sp_for_mv:
                elements.append(
                    _element(
                        slot=disp,
                        field="moves",
                        value=moves,
                        ok=False,
                        cause="species must be set before moves",
                    )
                )
            else:
                learnset = set(resolve_learnset(snap, str(sp_for_mv)) or [])

                all_ok = True
                for mv in moves:
                    mid = to_id(str(mv))
                    if mid not in learnset:
                        elements.append(
                            _element(
                                slot=disp,
                                field="move",
                                value=mv,
                                ok=False,
                                cause=f"{mv} is not in {sp_for_mv}'s Champions learnset",
                            )
                        )
                        all_ok = False
                    else:
                        elements.append(_element(slot=disp, field="move", value=mv, ok=True))
                if all_ok:
                    elements.append(
                        _element(slot=disp, field="moves", value=list(moves), ok=True)
                    )

        if req.get("nature") is not None:
            nat = req["nature"]
            if not isinstance(nat, str) or not nat.strip():
                elements.append(
                    _element(slot=disp, field="nature", value=nat, ok=False, cause="nature is required")
                )
            else:
                elements.append(_element(slot=disp, field="nature", value=nat, ok=True))

        if req.get("spread") is not None:
            spr = req["spread"]
            if not isinstance(spr, dict):
                elements.append(
                    _element(
                        slot=disp,
                        field="spread",
                        value=spr,
                        ok=False,
                        cause="spread must be an object of six SP ints",
                    )
                )
            else:
                elements.append(_element(slot=disp, field="spread", value=spr, ok=True))

        # If this request produced only failures on species-required empty request:
        if species is None and not any(req.get(f) is not None for f in _ATTR_FIELDS):
            elements.append(
                _element(
                    slot=disp,
                    field="species",
                    value=None,
                    ok=False,
                    cause="species is required when no other fields are set",
                )
            )

        batch_ok = all(el["ok"] for el in elements[req_elements_before:])
        if batch_ok:
            reserved_opens.add(index)
            # Commit projection for subsequent requests in this call (clause accounting).
            draft = projected
            resolved.append(
                {
                    "index": index,
                    "display": disp,
                    "species": canonical_species,
                    "item": next(
                        (el["value"] for el in elements[req_elements_before:] if el["field"] == "item" and el["ok"]),
                        None,
                    ),
                    "ability": req.get("ability") if isinstance(req.get("ability"), str) else None,
                    "nature": req.get("nature") if isinstance(req.get("nature"), str) else None,
                    "moves": list(moves) if isinstance(moves, (list, tuple)) else None,
                    "spread": req.get("spread") if isinstance(req.get("spread"), dict) else None,
                    "replace": (
                        req_replace
                        and species is not None
                        and (
                            all_locked(state["team_draft"][index])
                            or (
                                draft_enabled()
                                and state["team_draft"][index].species.value is not None
                            )
                        )
                    ),
                }
            )

    if not elements:
        return state, {
            "ok": False,
            "slot_commit_error": "set_slot received no actionable fields",
            "elements": [],
            "replace": replace_flag,
        }

    if any(not el["ok"] for el in elements):
        failed = [el for el in elements if not el["ok"]]
        summary = "; ".join(
            f"slot {el['slot']} {el['field']}: {el.get('cause') or 'failed'}" for el in failed
        )
        return state, {
            "ok": False,
            "slot_commit_error": summary,
            "elements": elements,
            "replace": replace_flag,
        }

    # Apply via underlying tools only. Surface edit_slot_field consequences unchanged.
    after = state
    applied_slots: list[int] = []
    consequences: list[dict[str, Any]] = []
    edits: list[dict[str, Any]] = []

    def _apply_edit(field: str, value: object) -> dict[str, Any] | None:
        nonlocal after
        after, patch = edit_slot_field(after, user_slot, field, value)
        if patch.get("slot_commit_error"):
            return {
                "ok": False,
                "slot_commit_error": str(patch["slot_commit_error"]),
                "elements": elements,
                "replace": replace_flag,
            }
        facts = list(patch.get("consequences") or [])
        consequences.extend(facts)
        edits.append(
            {
                "slot": user_slot,
                "field": patch.get("field") or field,
                "consequences": facts,
                "reconcile_pending_flags": list(patch.get("reconcile_pending_flags") or []),
                "superseded": list(patch.get("superseded") or []),
            }
        )
        return None

    for step in resolved:
        index = step["index"]
        user_slot = index + 1  # underlying tools require int, not display str
        disp = step["display"]
        if draft_enabled():
            # Write drafts only (locked=False). Never call lock_slot / edit_slot_field.
            from recommender.state import empty_slot as _empty

            draft_list = list(after["team_draft"])
            slot = draft_list[index]
            if step["replace"]:
                slot = _empty()
            if step["species"] is not None:
                slot = replace(slot, species=Attr(value=step["species"], locked=False))
            if step["item"] is not None:
                slot = replace(slot, item=Attr(value=step["item"], locked=False))
            if step["ability"] is not None:
                slot = replace(slot, ability=Attr(value=step["ability"], locked=False))
            if step["nature"] is not None:
                slot = replace(slot, nature=Attr(value=step["nature"], locked=False))
            if step["spread"] is not None:
                slot = replace(slot, spread=Attr(value=step["spread"], locked=False))
            if step["moves"] is not None:
                slot = replace(slot, moveset=Attr(value=list(step["moves"]), locked=False))
            draft_list[index] = slot
            after = {**after, "team_draft": draft_list, "slot_commit_error": None}
        else:
            if step["replace"]:
                after, patch = unlock_slot(after, user_slot)
                if patch.get("slot_commit_error"):
                    return state, {
                        "ok": False,
                        "slot_commit_error": str(patch["slot_commit_error"]),
                        "elements": elements,
                        "replace": replace_flag,
                    }
            if step["species"] is not None:
                after, patch = lock_slot(after, user_slot, step["species"])
                if patch.get("slot_commit_error"):
                    return state, {
                        "ok": False,
                        "slot_commit_error": str(patch["slot_commit_error"]),
                        "elements": elements,
                        "replace": replace_flag,
                    }
            for field, key in (
                ("item", "item"),
                ("ability", "ability"),
                ("moves", "moves"),
                ("nature", "nature"),
                ("spread", "spread"),
            ):
                if step[key] is not None:
                    err = _apply_edit(field, step[key])
                    if err is not None:
                        return state, err
        applied_slots.append(int(disp) if isinstance(disp, str) else disp)

    # Read-back from state, not echoed request.
    team = read_team(after)
    by_slot = {int(row["slot"]): row for row in team["slots"]}
    applied = []
    for disp in applied_slots:
        row = by_slot[int(disp)]
        applied.append(
            {
                "slot": int(disp),
                "species": row["species"],
                "item": next(
                    (a[1] for a in row["attrs"] if isinstance(a, (list, tuple)) and a[0] == "item"),
                    None,
                ),
                "ability": next(
                    (a[1] for a in row["attrs"] if isinstance(a, (list, tuple)) and a[0] == "ability"),
                    None,
                ),
                "nature": next(
                    (a[1] for a in row["attrs"] if isinstance(a, (list, tuple)) and a[0] == "nature"),
                    None,
                ),
                "moveset": next(
                    (a[1] for a in row["attrs"] if isinstance(a, (list, tuple)) and a[0] == "moveset"),
                    None,
                ),
                "spread": next(
                    (a[1] for a in row["attrs"] if isinstance(a, (list, tuple)) and a[0] == "spread"),
                    None,
                ),
            }
        )

    out: dict[str, Any] = {
        "ok": True,
        "applied": applied,
        "elements": elements,
        "replace": replace_flag,
        "slots_used": applied_slots,
        "consequences": consequences,
        "edits": edits,
    }
    if draft_enabled():
        out["write_mode"] = "draft"
        # Draft writes never lock.
        for row in applied:
            row["locked"] = False
    return after, out


SET_SLOT_SPEC = {
    "type": "function",
    "function": {
        "name": "set_slot",
        "description": (
            "Set one or more team slots in one call. Validates every element first and "
            "applies nothing unless all pass (all-or-nothing). "
            "slot is optional and defaults to the first open slot (1-based). "
            "Pass species and any of item, ability, nature, moves, spread. "
            "For several slots at once, pass slots=[{...}, {...}]. "
            "replace defaults false; set replace true only after the user has confirmed "
            "replacing the species in that fully locked slot — an earlier request that "
            "names the slot is not a confirmation. "
            "Attribute edits return the same consequences as edit_slot_field (type-boost, "
            "Choice-lock vs status, status self-boost overlap). "
            "When this tool is available, use it instead of lock_slot or edit_slot_field."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "slot": {"type": "integer"},
                "species": {"type": "string"},
                "item": {"type": "string"},
                "ability": {"type": "string"},
                "nature": {"type": "string"},
                "moves": {"type": "array", "items": {"type": "string"}},
                "spread": {"type": "object"},
                "replace": {"type": "boolean"},
                "slots": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "slot": {"type": "integer"},
                            "species": {"type": "string"},
                            "item": {"type": "string"},
                            "ability": {"type": "string"},
                            "nature": {"type": "string"},
                            "moves": {"type": "array", "items": {"type": "string"}},
                            "spread": {"type": "object"},
                            "replace": {"type": "boolean"},
                        },
                    },
                },
            },
            "required": [],
        },
    },
}

SET_SLOT_SPEC_DRAFT = {
    "type": "function",
    "function": {
        "name": "set_slot",
        "description": (
            "Write draft values into one or more team slots (locked=false). "
            "Validates every element first and applies nothing unless all pass. "
            "Never locks — call lock_fields when the user asks to lock or confirm. "
            "slot is optional and defaults to the first blank slot (a draft slot is not open). "
            "Swapping the species of a slot that already holds a draft or locked species "
            "needs replace=true only after the user confirms; attribute-only edits need no replace. "
            "For several slots at once, pass slots=[{...}, {...}]."
        ),
        "parameters": SET_SLOT_SPEC["function"]["parameters"],
    },
}
