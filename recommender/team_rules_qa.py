"""Deterministic gate for team-rules questions ("can I have two X / the same item twice?").

The answer is the validator's refusal message (ADR-081, ``team_validation``), never generated.
Same shape as ``item_holders.try_route_item_holders`` (ADR-077): a pending_response-shaped
dict, or None to fall through to the existing path. Reads nothing from state and writes nothing.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from recommender.legality import load_snapshot
from recommender.species_resolve import lookup_species_id
from recommender.state import Attr, empty_slot
from recommender.team_validation import validate_team_value

# shortcut: question-shaped duplicate-use phrasings only (two/both/twice/same); other rule
# questions (e.g. team size) fall through, add a pattern here when a row needs one.
_QUESTION_RE = re.compile(
    r"^\s*(?:can|could|may|am|is|are|would|will|does|do|what\s+if)\b|\?\s*$", re.IGNORECASE
)
_DUP_RE = re.compile(r"\b(?:both|two|2|twice|same)\b", re.IGNORECASE)
_TWO_SPECIES_RE = re.compile(
    r"\b(?:two|2|twice)\s+(?:of\s+)?([A-Za-z][\w'.\-]*(?:\s+[A-Za-z][\w'.\-]*)?)", re.IGNORECASE
)


def _reply(message: str) -> dict[str, Any]:
    return {"turn_intent": "pending_response", "turn_payload": {"message": message}}


def _duplicate_species(text: str, snap: dict[str, Any]) -> str | None:
    for m in _TWO_SPECIES_RE.finditer(text):
        words = m.group(1).split()
        for cand in (" ".join(words), words[0], words[0].rstrip("sS")):
            if lookup_species_id(cand, snap):
                return cand
    return None


def _duplicate_verdict(attr: str, value: str, snap: dict[str, Any]) -> str:
    """Hold `value` in slot 1, then try it in slot 2; return the validator's message."""
    draft = [empty_slot(), empty_slot()]
    first = validate_team_value(attr, value, slot_index=0, team_draft=draft, snap=snap)
    if first.refusal is not None:
        return first.refusal.message
    draft[0] = replace(draft[0], **{attr: Attr(first.canonical, locked=True)})
    second = validate_team_value(attr, value, slot_index=1, team_draft=draft, snap=snap)
    if second.refusal is None:
        return f"Yes: {first.canonical} twice does not break the Species or Item Clause."
    return f"No. {second.refusal.message}"


def try_route_team_rules(text: str) -> dict[str, Any] | None:
    """Never raises: any failure falls through to the existing classify path."""
    try:
        if not _QUESTION_RE.search(text) or not _DUP_RE.search(text):
            return None
        snap = load_snapshot()
        species = _duplicate_species(text, snap)
        if species is not None:
            return _reply(_duplicate_verdict("species", species, snap))
        from recommender.turn_intent import extract_item_name_target

        item = extract_item_name_target(text)
        if item is not None:
            return _reply(_duplicate_verdict("item", item, snap))
    except Exception:  # noqa: BLE001 - a gate must not break the turn
        return None
    return None
