"""Build wrapper/draft prompts as tool_fields text + documented rung deltas.

Keeps rungs 3–6 from drifting when tool_fields gains reporting sentences.
"""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL_FIELDS = HERE / "prompt_tool_fields.md"
WRAPPER = HERE / "prompt_wrapper.md"
DRAFT = HERE / "prompt_draft.md"
GUARD = HERE / "prompt_guard.md"

# Guard = draft + refusal / ask guidance (mapping brief FU19).
_GUARD_DELTA = (
    "A tool call can be refused with a message naming the class of the request; "
    "do not retry it. Answer from what the tools returned, or ask for the missing detail."
)

# Wrapper replaces lock_slot + edit_slot_field with set_slot; unlock_slot unchanged.
_WRAPPER_SET_SLOT = (
    "- set_slot for locking a species and/or setting item, ability, nature, moves, or "
    "spread (optional slot defaults to the first open slot; all-or-nothing — every named "
    "element is checked before any write; set replace true only after the user confirms "
    "replacing a fully locked slot). Report consequences from the result; do not invent "
    "others."
)

_LOCK_SLOT_PREFIX = "- lock_slot(slot, species)"
_EDIT_SLOT_PREFIX = "- edit_slot_field(slot, field, value)"

# Draft replaces wrapper set_slot + unlock_slot with draft/lock_fields surface.
_DRAFT_SET_SLOT = (
    "- set_slot writes a draft only (locked=false): species and/or item, ability, nature, "
    "moves, spread. Optional slot defaults to the first blank slot (a draft slot is not "
    "open). All-or-nothing validation. Never locks — call lock_fields when the user asks "
    "to lock or confirm. Before clearing or overwriting a draft, tell the user what the "
    "draft holds and ask; use replace=true only after they confirm (same for unlocking a "
    "valued slot). Attribute-only edits on a draft need no replace."
)
_DRAFT_LOCK_FIELDS = (
    "- lock_fields(slot, fields?) locks valued attributes (omit fields to lock all valued "
    "attrs). unlock_fields(slot, fields?) sets locked=false and keeps values."
)
_DRAFT_UNLOCK_SLOT = (
    "- unlock_slot(slot, replace?) wipes an occupied slot; needs replace=true when the "
    "slot holds draft or locked values, only after the user confirms."
)


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def build_wrapper_from_tool_fields(tool_fields_text: str | None = None) -> str:
    """tool_fields body with lock/edit removed and set_slot wrapper sentence inserted."""
    lines = (
        tool_fields_text.splitlines()
        if tool_fields_text is not None
        else _lines(TOOL_FIELDS)
    )
    out: list[str] = []
    inserted = False
    for line in lines:
        if line.startswith(_LOCK_SLOT_PREFIX):
            out.append(_WRAPPER_SET_SLOT)
            inserted = True
            continue
        if line.startswith(_EDIT_SLOT_PREFIX):
            continue
        # solve_spread: hide names that are unbound on the wrapper rung
        if "do not call edit_slot_field, lock_slot, add_constraint" in line:
            line = line.replace(
                "do not call edit_slot_field, lock_slot, add_constraint",
                "do not call set_slot, add_constraint",
            )
        out.append(line)
    if not inserted:
        raise ValueError("tool_fields text missing lock_slot line for wrapper transform")
    return "\n".join(out) + "\n"


def build_draft_from_wrapper(wrapper_text: str | None = None) -> str:
    """wrapper body with draft set_slot / lock_fields / unlock_slot replace semantics."""
    lines = (
        wrapper_text.splitlines()
        if wrapper_text is not None
        else build_wrapper_from_tool_fields().splitlines()
    )
    out: list[str] = []
    for line in lines:
        if line.startswith("- set_slot "):
            out.append(_DRAFT_SET_SLOT)
            out.append(_DRAFT_LOCK_FIELDS)
            continue
        if line.startswith("- unlock_slot("):
            out.append(_DRAFT_UNLOCK_SLOT)
            continue
        out.append(line)
    return "\n".join(out) + "\n"


def build_guard_from_draft(draft_text: str | None = None) -> str:
    """draft body plus the guard refusal/ask sentences."""
    body = (
        draft_text
        if draft_text is not None
        else build_draft_from_wrapper()
    )
    text = body.rstrip() + "\n\n" + _GUARD_DELTA + "\n"
    return text


def write_ladder_prompts() -> None:
    wrapper = build_wrapper_from_tool_fields()
    WRAPPER.write_text(wrapper, encoding="utf-8")
    draft = build_draft_from_wrapper(wrapper)
    DRAFT.write_text(draft, encoding="utf-8")
    GUARD.write_text(build_guard_from_draft(draft), encoding="utf-8")
