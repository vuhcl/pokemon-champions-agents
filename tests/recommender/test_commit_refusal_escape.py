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
        # Charizardite X so Mega Stone validation passes and Species Clause is the refusal.
        lambda: commit_seed(_clash_draft(), "Charizard-Mega-X", item="Charizardite X"),
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
    intent = {"turn_intent": "rejection", "species": species, "slot_index": 2, "reason": "no"}
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


# ---- the two exits that need build options: pick by id, and compare -----------------------

OPTION_SCENARIOS = [
    (
        "species-clause",
        lambda: commit_seed(
            _clash_draft(), "Charizard-Mega-X", item="Charizardite X", with_options=True
        ),
        "Species Clause",
    ),
    (
        "illegal-build",
        lambda: commit_seed(
            anchor_draft(), "Farigiraf", ability="Drizzle",
            moves=("Psychic", "Hyper Voice", "Trick Room", "Protect"), with_options=True,
        ),
        "illegal provisional slot",
    ),
]
_IDS = ("spread_nature:1", "spread_nature:2")


def _refused_with_options(intent: dict, scenario) -> tuple[Harness, dict, dict]:
    h = Harness(intent)
    before = h.seed(**scenario[1]())
    assert before["pending_presentation"]["build_option_groups"]
    after = h.turn("yes")
    assert scenario[2] in after["slot_commit_error"]
    assert h.discovery_calls() == 0  # the refusal ended the turn; nothing re-presented the screen
    return h, before, after


@pytest.mark.parametrize("scenario", OPTION_SCENARIOS, ids=[s[0] for s in OPTION_SCENARIOS])
def test_refused_commit_keeps_the_option_list_and_fingerprint_identical(scenario):
    h, before, after = _refused_with_options({"turn_intent": "pending_response"}, scenario)
    assert after["pending_presentation"] == before["pending_presentation"]
    assert after["pending_presentation"]["build_option_groups"] == before["pending_presentation"]["build_option_groups"]
    assert after["pending_presentation"]["provisional_fingerprint"] == before["provisional_slot"].fingerprint
    assert after["provisional_slot"] == before["provisional_slot"]
    assert after["pending_slot_intent"] == before["pending_slot_intent"]
    assert changed_keys(before, after) <= REFUSAL_ALLOWED
    text = format_turn(after)
    assert text.index("Slot commit error:") < text.index("spread_nature:1")


def test_exit_pick_option_by_id_works_after_a_species_clause_refusal():
    scenario = OPTION_SCENARIOS[0]
    h, before, first = _refused_with_options({"turn_intent": "pending_response"}, scenario)
    out = h.turn("spread_nature:1")
    assert out["turn_intent"] == "select_build_option"
    assert out["turn_payload"]["option_ids"] == ("spread_nature:1",)
    assert not out.get("slot_commit_error")
    assert out["pending_presentation"]["kind"] == "full_build_confirmation"
    assert out["provisional_slot"].nature == "Timid"
    assert dict(out["provisional_slot"].spread)["spe"] == 32
    assert out["team_draft"] == before["team_draft"]
    gone = h.turn("defer")  # and the screen still offers a way out
    assert gone["turn_intent"] == "build_abandoned" and not gone.get("slot_commit_error")


# Pre-existing, not caused by the router: an option pick re-validates the whole provisional
# slot, so on a build with an illegal field it is refused ("illegal edited slot: <field>").
# The guarantee here is preservation, not a success path. commit_first=False is the control:
# the identical refusal and preserved state arise with no commit attempt at all.
@pytest.mark.parametrize("commit_first", [True, False], ids=["after-refused-commit", "control-no-commit"])
def test_pick_option_on_an_illegal_build_is_refused_and_changes_nothing(commit_first):
    scenario = OPTION_SCENARIOS[1]
    h = Harness({"turn_intent": "pending_response"})
    seeded = h.seed(**scenario[1]())
    if commit_first:
        h.turn("yes")
        assert scenario[2] in h.state()["slot_commit_error"]
    before = h.state()
    out = h.turn("spread_nature:1")
    assert out["turn_intent"] == "select_build_option"
    assert "ability:Drizzle" in out["slot_commit_error"]
    for key in ("pending_presentation", "provisional_slot", "pending_slot_intent"):
        assert out[key] == before[key] == seeded[key], key
    pend = out["pending_presentation"]
    assert pend["build_option_groups"] == seeded["pending_presentation"]["build_option_groups"]
    assert pend["provisional_fingerprint"] == seeded["provisional_slot"].fingerprint
    assert out["team_draft"] == seeded["team_draft"]
    assert h.discovery_calls() == 0
    # the exits the user needs stay available: defer, and an ability edit that keeps the options
    assert h.turn("defer")["turn_intent"] == "build_abandoned"


@pytest.mark.parametrize("commit_first", [True, False], ids=["after-refused-commit", "control-no-commit"])
def test_ability_edit_repairs_an_illegal_build_and_keeps_the_option_list(commit_first):
    scenario = OPTION_SCENARIOS[1]
    h = Harness({"turn_intent": "edit", "field": "ability", "value_text": "Armor Tail"})
    seeded = h.seed(**scenario[1]())
    if commit_first:
        h.turn("yes")
    out = h.turn("fix the ability")
    assert out["turn_intent"] == "edit" and not out.get("slot_commit_error")
    assert out["provisional_slot"].ability == "Armor Tail"
    # the edit re-presents the screen with its own regenerated options, so check presence
    groups = out["pending_presentation"]["build_option_groups"]
    assert groups and any(o["option_id"] == "spread_nature:default" for g in groups for o in g["options"])
    assert h.discovery_calls() == 0


@pytest.mark.parametrize("scenario", OPTION_SCENARIOS, ids=[s[0] for s in OPTION_SCENARIOS])
def test_exit_compare_produces_its_result_in_the_same_turn(scenario):
    h, before, first = _refused_with_options(
        {"turn_intent": "compare", "option_ids": list(_IDS)}, scenario
    )
    assert before.get("compare_analysis") is None
    out = h.turn("compare 1 and 2")
    assert out["turn_intent"] == "compare"
    assert not out.get("slot_commit_error")
    # classify_input wipes compare_analysis at the start of the turn; the handler sets it after
    assert out["compare_analysis"] and out["compare_analysis"] != "Nothing to compare."
    assert "Name two or more valid build option ids" not in out["compare_analysis"]
    assert out["pending_presentation"] == before["pending_presentation"]
    assert out["provisional_slot"] == before["provisional_slot"]
