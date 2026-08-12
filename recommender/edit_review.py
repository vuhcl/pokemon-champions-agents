"""Deterministic soft review flags for provisional-slot edits."""

from __future__ import annotations

from recommender.state import ProvisionalSlot, RecommenderState, ReviewFlag


def collect_provisional_review_flags(
    provisional: ProvisionalSlot,
    state: RecommenderState,
    *,
    edited_fields: frozenset[str] = frozenset(),
) -> tuple[ReviewFlag, ...]:
    """Soft, non-blocking. Never raises. Empty tuple is valid."""
    return ()
