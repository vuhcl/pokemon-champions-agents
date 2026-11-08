"""Collect graded request-set turn texts (original + fu74 overrides) for overlap checks."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
V4 = HERE.parents[1] / "part_g_v4"
REV3 = HERE / "expected_tools_fu16" / "expected_tools_rev3_2026-11-02.csv"
OVERRIDES = HERE / "keys_fu72" / "request_text_overrides_fu72.json"
REQUEST_SET = V4 / "part3_request_set_v4.md"

_WORD = re.compile(r"[A-Za-z0-9']+")


def tokenize(text: str) -> list[str]:
    return [w.casefold() for w in _WORD.findall(text or "")]


def ngrams(tokens: list[str], n: int = 4) -> set[tuple[str, ...]]:
    if len(tokens) < n:
        return set()
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def graded_turn_texts() -> list[str]:
    """Every graded user-turn string: CSV user_turn_text + part3 prompts + overrides."""
    out: list[str] = []
    with REV3.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            t = (row.get("user_turn_text") or "").strip()
            if t:
                out.append(t)
    # Multi-turn prompts in the request set (pipe-joined in loader); also raw lines.
    raw = REQUEST_SET.read_text(encoding="utf-8")
    out.append(raw)
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    out.extend(str(v) for v in overrides.values())
    return out


def graded_4grams() -> set[tuple[str, ...]]:
    grams: set[tuple[str, ...]] = set()
    for text in graded_turn_texts():
        grams |= ngrams(tokenize(text), 4)
    return grams


def overlapping_4grams(candidate: str, *, graded: set[tuple[str, ...]] | None = None) -> set[tuple[str, ...]]:
    g = graded if graded is not None else graded_4grams()
    return ngrams(tokenize(candidate), 4) & g
