"""One place that reads the current UTC time, so a run can pin it.

``RECOMMENDER_FIXED_NOW_UTC`` (ISO 8601 with a ``Z`` or ``+00:00`` suffix, e.g. ``2026-11-05T12:00:00Z``)
makes ``utc_now()`` return that instant; unset, it returns the real time. A malformed value raises
immediately instead of falling back to the real clock.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

ENV_FIXED_NOW = "RECOMMENDER_FIXED_NOW_UTC"


def _parse_fixed(raw: str) -> datetime:
    text = raw.strip()
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    except ValueError as exc:
        raise ValueError(f"{ENV_FIXED_NOW}={raw!r} is not an ISO 8601 UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{ENV_FIXED_NOW}={raw!r} must carry a UTC offset (Z or +00:00)")
    return parsed.astimezone(timezone.utc)


def fixed_now() -> datetime | None:
    raw = os.environ.get(ENV_FIXED_NOW)
    return _parse_fixed(raw) if raw else None


def utc_now() -> datetime:
    fixed = fixed_now()
    return fixed if fixed is not None else datetime.now(timezone.utc)
