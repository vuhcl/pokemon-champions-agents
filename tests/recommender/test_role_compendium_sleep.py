"""Sleep status spreader construct smoke test (no prior coverage)."""

from __future__ import annotations

from recommender.legality import load_snapshot
from recommender.role_compendium import (
    SLEEP_STATUS_SPREADER_CRITERIA,
    construct_role_category,
    legal_species_pool,
)


def test_sleep_construct_runs_offline_and_emits_candidates():
    snap = load_snapshot()
    draft = construct_role_category(
        "sleep_status_spreader",
        SLEEP_STATUS_SPREADER_CRITERIA,
        legal_species_pool(snap),
        snap=snap,
        live_fetch=None,
        showdown_fetch=None,
    )
    assert draft.category == "sleep_status_spreader"
    assert draft.candidates or draft.considered_rejected
    assert any("pathway" in n.lower() or "sleep" in n.lower() for n in draft.notes)
