"""After a refused commit_full_slot the confirmation screen stays live and every exit it
offers still works as a normal turn (no refusal replayed, no dead end).

Needs the calc service for the edit exit (edits re-verify the build), like other live tests.
"""

from __future__ import annotations

import pytest

from recommender.nodes_classify import CONTINUE_ABANDON_MSG
from recommender.present_text import format_turn

from pending_harness import (
    REFUSAL_ALLOWED,
    Harness,
    anchor_draft,
    changed_keys,
    commit_seed,
)
from recommender.state import Attr, Slot, empty_slot


def _clash_draft():
    d = [empty_slot() for _ in range(6)]
    d[0] = Slot(species=Attr("Charizard", locked=True))
    return d


# (id, seed factory, expected refusal fragment, fixing edit or None)
SCENARIOS = [
    (
        "species-clause",
        lambda: commit_seed(_clash_draft(), "Charizard-Mega-X"),
        "Species Clause",
        None,  # no field edit can fix a species clash; exits are defer/continue/reject
    ),
    (
        "illegal-build",
        lambda: commit_seed(
            anchor_draft(), "Farigiraf", ability="Drizzle",
            moves=("Psychic", "Hyper Voice", "Trick Room", "Protect"),
        ),
        "illegal provisional slot",
        {"turn_intent": "edit", "field": "ability", "value_text": "Armor Tail"},
    ),
]


def _refused(intent: dict, scenario) -> tuple[Harness, dict, dict]:
    h = Harness(intent)
    before = h.seed(**scenario[1]())
    after = h.turn("yes")  # deterministic full_slot_confirmed -> commit_full_slot
    return h, before, after


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s[0] for s in SCENARIOS])
def test_refused_commit_keeps_the_confirmation_screen_exactly(scenario):
    h, before, after = _refused({"turn_intent": "pending_response"}, scenario)
    assert scenario[2] in after["slot_commit_error"]
    assert changed_keys(before, after) <= REFUSAL_ALLOWED
    assert after["team_draft"] == before["team_draft"]
    assert h.discovery_calls() == 0
    text = format_turn(after)
    assert text.index("Slot commit error:") < text.index("Accept this build?")


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s[0] for s in SCENARIOS])
def test_exit_defer_abandons_the_build(scenario):
    h, before, _ = _refused({"turn_intent": "pending_response"}, scenario)
    out = h.turn("defer")
    assert out["turn_intent"] == "build_abandoned"
    assert not out.get("slot_commit_error")
    assert out["pending_presentation"] is None and out["provisional_slot"] is None
    assert out["team_draft"] == before["team_draft"]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s[0] for s in SCENARIOS])
def test_exit_continue_then_confirm_abandons_the_build(scenario):
    h, before, _ = _refused({"turn_intent": "continue"}, scenario)
    asked = h.turn("what's next")
    assert asked["pending_presentation"]["kind"] == "confirm_abandon_build"
    assert not asked.get("slot_commit_error")
    done = h.turn("yes")
    assert done["turn_intent"] == "continue" and not done.get("slot_commit_error")
    assert done["pending_presentation"] is None and done["provisional_slot"] is None
    assert h.discovery_calls() == 1
    assert done["team_draft"] == before["team_draft"]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s[0] for s in SCENARIOS])
def test_exit_rejection_is_a_normal_turn(scenario):
    species = scenario[1]()["provisional_slot"].species
    intent = {"turn_intent": "rejection", "species": species, "slot_index": 1, "reason": "no"}
    h, before, _ = _refused(intent, scenario)
    out = h.turn("no thanks")
    assert out["turn_intent"] == "rejection" and not out.get("slot_commit_error")
    assert out["pending_presentation"] is None and out["provisional_slot"] is None
    assert any(r["species"] == species for r in out["rejected"])
    assert h.discovery_calls() == 1


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s[0] for s in SCENARIOS])
def test_exit_team_review_shows_the_roster_and_keeps_the_screen(scenario):
    h, before, _ = _refused({"turn_intent": "team_review"}, scenario)
    out = h.turn("show my team")
    assert not out.get("slot_commit_error")
    assert out["pending_presentation"]["kind"] == "full_build_confirmation"
    assert out["provisional_slot"] == before["provisional_slot"]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s[0] for s in SCENARIOS])
def test_exit_edit_is_a_normal_turn_and_can_fix_a_fixable_refusal(scenario):
    edit = scenario[3] or {"turn_intent": "edit", "field": "item", "value_text": "Leftovers"}
    h, before, _ = _refused(edit, scenario)
    out = h.turn("change it")
    assert out["turn_intent"] == "edit" and not out.get("slot_commit_error")
    assert out["pending_presentation"]["kind"] == "full_build_confirmation"
    if scenario[3] is None:
        return
    done = h.turn("yes")
    assert not done.get("slot_commit_error")
    assert done["team_draft"][1].species.value == "Farigiraf" and done["team_draft"][1].species.locked
    assert done["pending_presentation"] is None and done["provisional_slot"] is None


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s[0] for s in SCENARIOS])
def test_confirming_again_repeats_the_refusal_but_exits_stay_available(scenario):
    h, before, first = _refused({"turn_intent": "pending_response"}, scenario)
    again = h.turn("yes")
    assert again["slot_commit_error"] == first["slot_commit_error"]
    assert again["pending_presentation"] == before["pending_presentation"]
    out = h.turn("defer")
    assert out["turn_intent"] == "build_abandoned" and not out.get("slot_commit_error")
