"""A refused lock, restore, repick or commit leaves team_draft and all pending state as it was.

Whole-state diff: only the keys in REFUSAL_ALLOWED (classify_input bookkeeping, the
refusal message, per-turn resets) may differ; ``last_system_claim`` is also allowed when
classification itself blocked the request (intent pending_response). Discovery is
stubbed and must not run on a refusal.
"""

from __future__ import annotations

import pytest

from recommender.legality import is_item_legal, load_snapshot
from recommender.nodes import (
    LOCK_BAD_SLOT_MSG,
    LOCK_FULLY_LOCKED_SLOT_MSG,
    REPICK_REQUIRES_LOCKED_MSG,
    RESTORE_NOTHING_MSG,
)
from recommender.state import Attr, Slot, empty_slot

from pending_harness import (
    ALL_KINDS as _ALL_KINDS,
    LOCK_REACHABLE,
    REFUSAL_ALLOWED,
    RESTORE_REACHABLE,
    Harness,
    anchor_draft,
    changed_keys,
    commit_seed,
    pending,
    provisional,
    slot_intent,
)

# The three question kinds consume any reply themselves (they re-ask with an updated
# question), before and independently of the lock/restore/repick handlers. Their pending
# rewrite is pre-existing closed-set behavior, not a refusal; the characterization tests
# pin that a lock/restore never reaches a handler from them.
ALL_KINDS = tuple(k for k in _ALL_KINDS if not k.endswith("_question"))

SNAP = load_snapshot()
ILLEGAL_ITEM = next(e["name"] for i, e in sorted(SNAP["items"].items()) if not is_item_legal(SNAP, i))


def _draft_with(**slot0) -> list[Slot]:
    d = [empty_slot() for _ in range(6)]
    d[0] = Slot(**{k: Attr(v, locked=True) for k, v in slot0.items()})
    return d


def _full_slot_draft() -> list[Slot]:
    full = Slot(
        role=Attr("r", locked=True), species=Attr("Garchomp", locked=True), ability=Attr("Rough Skin", locked=True),
        item=Attr("Life Orb", locked=True), moveset=Attr(["Earthquake"] * 4, locked=True),
        spread=Attr({"hp": 32}, locked=True), nature=Attr("Jolly", locked=True),
    )
    d = [empty_slot() for _ in range(6)]
    d[1] = full
    return d


def _lock(attr: str, value: str, slot_index: int = 2) -> dict:
    return {"turn_intent": "lock", "slot_index": slot_index, "attr": attr, "value": value}


# (id, intent, draft factory, expected message fragment)
LOCK_REFUSALS = [
    ("second-incineroar", _lock("species", "Incineroar"), lambda: _draft_with(species="Incineroar"), "Species Clause"),
    ("same-dex-pair", _lock("species", "Charizard-Mega-X"), lambda: _draft_with(species="Charizard"), "Species Clause"),
    ("illegal-species", _lock("species", "Flutter Mane"), anchor_draft, "not legal"),
    ("illegal-item", _lock("item", ILLEGAL_ITEM), anchor_draft, "not legal"),
    ("second-item", _lock("item", "Choice Scarf"), lambda: _draft_with(item="Choice Scarf"), "Item Clause"),
    ("bad-slot-index", _lock("species", "Garchomp", slot_index=9), anchor_draft, LOCK_BAD_SLOT_MSG),
    ("fully-locked-slot", _lock("species", "Rillaboom"), _full_slot_draft, LOCK_FULLY_LOCKED_SLOT_MSG),
]


def _seed(h: Harness, kind: str, draft: list[Slot], **extra) -> dict:
    values = {"team_draft": draft, "pending_presentation": pending(kind), **extra}
    if kind in ("full_build_confirmation", "confirm_abandon_build"):
        values["provisional_slot"] = provisional()
        values["pending_slot_intent"] = slot_intent(draft)
    return h.seed(**values)


def _assert_untouched(before: dict, after: dict) -> None:
    allowed = REFUSAL_ALLOWED | ({"last_system_claim"} if after.get("turn_intent") == "pending_response" else set())
    extra = changed_keys(before, after) - allowed
    assert extra == set(), extra
    assert after["team_draft"] == before["team_draft"]


@pytest.mark.parametrize("kind", ALL_KINDS)
@pytest.mark.parametrize("case", LOCK_REFUSALS, ids=[c[0] for c in LOCK_REFUSALS])
def test_refused_lock_changes_nothing_but_the_listed_keys(case, kind):
    _, intent, draft_fn, message = case
    h = Harness(intent)
    before = _seed(h, kind, draft_fn())
    after = h.turn()
    _assert_untouched(before, after)
    assert h.discovery_calls() == 0
    if kind in LOCK_REACHABLE:
        assert message in after["slot_commit_error"]
    else:
        assert not after.get("slot_commit_error")  # stopped before the handler


REPICK = {"turn_intent": "repick_locked_slot", "slot_index": 2}  # user slot 2 → internal 1


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_refused_repick_with_nothing_locked_changes_nothing(kind):
    h = Harness(REPICK)
    before = _seed(h, kind, anchor_draft())
    after = h.turn()
    _assert_untouched(before, after)
    assert h.discovery_calls() == 0
    if kind == "none":
        assert after["slot_commit_error"] == REPICK_REQUIRES_LOCKED_MSG


RESTORE = {"turn_intent": "restore", "slot_index": 2, "attr": "species"}  # user slot 2 → internal 1


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_refused_restore_with_no_match_changes_nothing(kind):
    h = Harness(RESTORE)
    before = _seed(h, kind, anchor_draft(), superseded=[])
    after = h.turn()
    _assert_untouched(before, after)
    assert h.discovery_calls() == 0
    if kind in RESTORE_REACHABLE:
        assert after["slot_commit_error"] == RESTORE_NOTHING_MSG


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_refused_restore_that_clashes_after_a_later_lock_changes_nothing(kind):
    entry = {"slot_index": 1, "attr": "species", "value": "Charizard", "reason": "x", "turn_removed": 1}
    h = Harness(RESTORE)
    before = _seed(h, kind, _draft_with(species="Charizard-Mega-X"), superseded=[entry])
    after = h.turn()
    _assert_untouched(before, after)
    assert after["superseded"] == [entry]
    assert h.discovery_calls() == 0
    if kind in RESTORE_REACHABLE:
        assert "Species Clause" in after["slot_commit_error"]


# ---- the router: success continues, refusal ends --------------------------------------

def test_accepted_lock_and_restore_still_continue_to_route_team_phase():
    h = Harness(_lock("species", "Garchomp"))
    _seed(h, "candidate_selection", anchor_draft())
    h.turn()
    assert h.discovery_calls() == 1
    h = Harness(RESTORE)
    _seed(h, "candidate_selection", anchor_draft(), superseded=[
        {"slot_index": 1, "attr": "species", "value": "Rillaboom", "reason": "x", "turn_removed": 1}])
    out = h.turn()
    assert h.discovery_calls() == 1 and not out.get("slot_commit_error")


def test_idle_refusal_ends_at_the_error_and_the_roster():
    from recommender.present_text import format_turn

    h = Harness(_lock("species", "Incineroar"))
    _seed(h, "none", _draft_with(species="Incineroar"))
    out = h.turn()
    assert out["pending_presentation"] is None and h.discovery_calls() == 0
    text = format_turn(out)
    assert text.index("Slot commit error:") < text.index("Incineroar", text.index("Slot commit error:") + 40)


# ---- CLI: the error, then the still-live pending block ---------------------------------

@pytest.mark.parametrize("kind", LOCK_REACHABLE[1:])
def test_rendered_refusal_shows_error_then_the_pending_block(kind):
    from recommender.present_text import format_turn

    h = Harness(_lock("species", "Incineroar"))
    _seed(h, kind, _draft_with(species="Incineroar"))
    out = h.turn()
    text = format_turn(out)
    err = text.index("Slot commit error: Species Clause")
    body = {"candidate_selection": "Farigiraf", "completion_preference": "Prefer next slot orientation"}[kind]
    assert err < text.index(body)
    assert text.rstrip().endswith(
        {"candidate_selection": "'defer'.", "completion_preference": "'defer'."}[kind]
    )


# ---- the refusal signal is reliable ---------------------------------------------------

def test_handler_successes_never_return_a_truthy_slot_commit_error():
    from recommender.nodes import unlock_locked_slot

    out = unlock_locked_slot({"team_draft": _full_slot_draft(), "turn_payload": {"slot_index": 1}})
    assert not out.get("slot_commit_error") and "team_draft" in out
    h = Harness(_lock("species", "Garchomp"))
    _seed(h, "none", anchor_draft())
    assert not h.turn().get("slot_commit_error")  # lock success (commit success: test_commit_refusal_escape)


def test_restore_refusal_text_has_no_regulation_id():
    assert RESTORE_NOTHING_MSG == "There is nothing to restore for that slot."
