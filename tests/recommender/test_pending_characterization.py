"""Characterization of today's pending-state behavior for lock and restore.

Written against main before the PR B change and kept green across it: accepted lock
and restore clear the four pending keys, a lock on full_build_confirmation is blocked
at classification, kinds that never reach a lock handler never do. Discovery is
stubbed (see pending_harness) so the end state is the handler's own output.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pending_harness import (
    ALL_KINDS,
    LOCK_GARCHOMP,
    LOCK_REACHABLE,
    PENDING_KEYS,
    RESTORE_REACHABLE,
    Harness,
    anchor_draft,
    changed_keys,
    pending,
    provisional,
    slot_intent,
)

RESTORE = {"turn_intent": "restore", "slot_index": 1, "attr": "species"}
SUPERSEDED = [{"slot_index": 1, "attr": "species", "value": "Rillaboom", "reason": "x", "turn_removed": 1}]


def _seed_live(h: Harness, kind: str, draft) -> dict:
    values = {"team_draft": draft, "pending_presentation": pending(kind)}
    if kind in ("full_build_confirmation", "confirm_abandon_build"):
        values["provisional_slot"] = provisional()
        values["pending_slot_intent"] = slot_intent(draft)
    return h.seed(**values)


@pytest.mark.parametrize("kind", LOCK_REACHABLE)
def test_accepted_lock_clears_all_pending_keys(kind):
    h = Harness(LOCK_GARCHOMP)
    _seed_live(h, kind, anchor_draft())
    out = h.turn()
    assert out["team_draft"][1].species.value == "Garchomp"
    assert out["team_draft"][1].species.locked
    for key in PENDING_KEYS:
        assert out.get(key) is None, key


@pytest.mark.parametrize("kind", RESTORE_REACHABLE)
def test_accepted_restore_clears_all_pending_keys(kind):
    h = Harness(RESTORE)
    draft = anchor_draft()
    _seed_live(h, kind, draft)
    h.seed(superseded=list(SUPERSEDED))
    out = h.turn()
    assert out["team_draft"][1].species.value == "Rillaboom"
    assert out["superseded"] == []
    for key in PENDING_KEYS:
        assert out.get(key) is None, key


def test_pick_by_lock_clears_candidate_selection():
    h = Harness({"turn_intent": "lock", "slot_index": 1, "attr": "species", "value": "Farigiraf"})
    _seed_live(h, "candidate_selection", anchor_draft())
    out = h.turn()
    assert out["team_draft"][1].species.value == "Farigiraf" and out["team_draft"][1].species.locked
    assert out["pending_presentation"] is None


def test_stale_slot_state_without_a_pending_screen_survives_an_accepted_lock():
    """had_pending is False when pending_presentation is None, so nothing is cleared."""
    h = Harness(LOCK_GARCHOMP)
    draft = anchor_draft()
    h.seed(team_draft=draft, pending_presentation=None,
           provisional_slot=provisional(), pending_slot_intent=slot_intent(draft))
    out = h.turn()
    assert out["team_draft"][1].species.value == "Garchomp"
    assert out["provisional_slot"] is not None and out["pending_slot_intent"] is not None


def test_lock_on_full_build_confirmation_is_blocked_at_classification():
    h = Harness(LOCK_GARCHOMP)
    draft = anchor_draft()
    before = _seed_live(h, "full_build_confirmation", draft)
    out = h.turn()
    assert out["turn_intent"] == "pending_response"
    assert out["team_draft"] == before["team_draft"]
    for key in PENDING_KEYS:
        assert repr(out.get(key)) == repr(before.get(key)), key
    assert changed_keys(before, out) <= {
        "turn", "turn_intent", "turn_payload", "last_user_text", "obs_thread_id", "last_system_claim",
    }


@pytest.mark.parametrize("kind", [k for k in ALL_KINDS if k not in LOCK_REACHABLE])
def test_kinds_that_cannot_reach_a_lock_handler_never_do(kind):
    lock_spy, restore_spy = MagicMock(return_value={}), MagicMock(return_value={})
    h = Harness(LOCK_GARCHOMP, replace={"apply_lock": lock_spy})
    _seed_live(h, kind, anchor_draft())
    h.turn()
    assert lock_spy.call_count == 0


@pytest.mark.parametrize("kind", [k for k in ALL_KINDS if k not in RESTORE_REACHABLE])
def test_kinds_that_cannot_reach_restore_never_do(kind):
    spy = MagicMock(return_value={})
    h = Harness(RESTORE, replace={"restore_superseded": spy})
    _seed_live(h, kind, anchor_draft())
    h.turn()
    assert spy.call_count == 0
