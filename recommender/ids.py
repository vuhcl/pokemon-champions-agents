"""Showdown-compatible id normalize + regulation file tags."""

from __future__ import annotations

import re

_MOD_TO_TAG = {
    "champions": "champions-reg-mb",
    "championsregma": "champions-reg-ma",
    "champions-reg-mb": "champions-reg-mb",
    "champions-reg-ma": "champions-reg-ma",
}


def to_id(text: str) -> str:
    """Match scripts/extract_legality/to_id.ts: lowercase, strip non-alphanumeric."""
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def regulation_file_tag(regulation: str) -> str:
    """Showdown mod or file tag → resolved-builds / usage file tag."""
    key = regulation.strip().lower().replace(" ", "")
    # Accept bare "champions-reg-mb" already
    if key in _MOD_TO_TAG:
        return _MOD_TO_TAG[key]
    # Soft: champions-reg-mb style already
    if key.startswith("champions-reg-"):
        return key
    raise ValueError(f"unknown regulation: {regulation!r}")
