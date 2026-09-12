"""Shared Reg M-* letter helpers for the legality extract gate."""

from __future__ import annotations

import re

_REG_LETTER = re.compile(r"\bReg M-([A-Z])\b", re.I)


def letter_from_format_name(name: str) -> str:
    m = _REG_LETTER.search(name or "")
    if not m:
        raise ValueError(f"could not parse Reg M-* letter from {name!r}")
    return m.group(1).upper()


def prior_letter(letter: str) -> str:
    letter = letter.upper()
    if letter == "A":
        raise ValueError("no prior letter before Reg M-A")
    return chr(ord(letter) - 1)


def next_letter(letter: str) -> str:
    letter = letter.upper()
    if letter == "Z":
        raise ValueError("no next letter after Reg M-Z")
    return chr(ord(letter) + 1)


def letters_adjacent(current: str, live: str) -> bool:
    return ord(live.upper()) == ord(current.upper()) + 1


def prior_mod_id(current_letter: str) -> str:
    """Showdown archive mod for the letter *before* current (championsregmb for C)."""
    return f"championsregm{prior_letter(current_letter).lower()}"


def archive_mod_for_letter(letter: str) -> str:
    """Showdown archive folder name for a retired letter (M-C → championsregmc)."""
    return f"championsregm{letter.lower()}"


def file_tag_for_letter(letter: str) -> str:
    return f"champions-reg-m{letter.lower()}"
