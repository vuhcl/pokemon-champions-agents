"""4c show_candidates — producer path, rejected filter, determinism, no team write."""

from __future__ import annotations

from copy import deepcopy

from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.pending import build_fully_locked_slot
from scripts.eval.part_g_arm.state.tools import (
    draft_signature,
    reject_option,
    show_candidates,
)
from recommender.state import all_locked


def test_shows_candidates_for_open_slot():
    st = build_fully_locked_slot("Venusaur", user_slot=1)
    assert all_locked(st["team_draft"][0])
    before_draft = draft_signature(st)
    after, res = show_candidates(st, 2)
    assert res.get("ok"), res
    assert len(res["options"]) >= 1
    assert res["options"][0]["number"] == 1
    assert res["options"][0]["species"]
    assert res["options"][0]["source"]
    assert isinstance(res["options"][0]["evidence"], list)
    pending = after["pending_presentation"]
    assert pending["kind"] == "candidate_selection"
    assert pending["slot_index"] == 1
    assert draft_signature(after) == before_draft


def test_honors_prior_rejection():
    st = build_fully_locked_slot("Venusaur", user_slot=1)
    after, res = show_candidates(st, 2)
    assert res.get("ok") and res["options"]
    banned = res["options"][0]["species"]
    after, _ = reject_option(after, 1)
    after2, res2 = show_candidates(after, 2)
    assert res2.get("ok"), res2
    names = [o["species"] for o in res2["options"]]
    assert banned not in names, (banned, names)


def test_empty_team_refuses():
    st = empty_team()
    after, res = show_candidates(st, 1)
    assert res.get("slot_commit_error")
    assert "empty team" in str(res["slot_commit_error"]).lower() or "anchor" in str(
        res["slot_commit_error"]
    ).lower()
    assert after.get("pending_presentation") is None


def test_determinism_same_options_twice():
    st = build_fully_locked_slot("Venusaur", user_slot=1)
    _, a = show_candidates(deepcopy(st), 2)
    _, b = show_candidates(deepcopy(st), 2)
    assert a.get("ok") and b.get("ok")
    assert [(o["species"], o["source"], o["evidence"]) for o in a["options"]] == [
        (o["species"], o["source"], o["evidence"]) for o in b["options"]
    ]


def test_locked_slot_refuses_without_draft_write():
    st = build_fully_locked_slot("Venusaur", user_slot=1)
    before = draft_signature(st)
    after, res = show_candidates(st, 1)
    assert res.get("slot_commit_error")
    assert draft_signature(after) == before
