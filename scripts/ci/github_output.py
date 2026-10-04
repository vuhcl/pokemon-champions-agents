"""Sanitize values written to GitHub Actions GITHUB_OUTPUT files."""

from __future__ import annotations

import re

_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def sanitize_github_output_value(value: str, *, max_len: int = 200) -> str:
    """Collapse to one line, strip controls, cap length (for GITHUB_OUTPUT safety)."""
    text = _CTRL.sub(" ", str(value))
    text = " ".join(text.split())
    if len(text) > max_len:
        text = text[:max_len]
    return text
