"""revise_locked_slot: attribute edit on a fully locked team_draft slot."""

from __future__ import annotations

from unittest.mock import patch

from langgraph.checkpoint.memory import MemorySaver

from recommender.condition_resilience import provider_need_category_open
from recommender.graph import compile_graph
from recommender.nodes import (
    REVISE_REQUIRES_LOCKED_MSG,
    apply_lock,
    begin_locked_slot_revision,
)
from recommender.state import (
    Attr,
    Slot,
    all_locked,
    empty_slot,
)
from recommender.team_candidates import collect_locked_anchor_contexts, mega_ceiling_notices

VGC_MB = "[Gen 9 Champions] VGC 2026 Reg M-B"
SPREAD = {"hp": 32, "atk": 32, "def": 2, "spa": 0, "spd": 0, "spe": 0}


def _locked_gholdengo(*, item: str = "Life Orb") -> Slot:
    return Slot(
        role=Attr("fast_special_attacker", locked=True),
        species=Attr("Gholdengo", locked=True),
        ability=Attr("Good as Gold", locked=True),
        item=Attr(item, locked=True),
        moveset=Attr(
            ["Make It Rain", "Shadow Ball", "Protect", "Nasty Plot"], locked=True
        ),
        nature=Attr("Timid", locked=True),
        spread=Attr(
            {"hp": 4, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 30}, locked=True
        ),
    )


def _base_state(*, team_draft: list[Slot]) -> dict:
    return {
        "format_id": VGC_MB,
        "game_type": "doubles",
        "regulation_mod": "champions-reg-mb",
        "picked_team_size": 4,
        "available_pool": [],
        "team_draft": team_draft,
        "archetype": Attr(),
        "rejected": [],
        "constraints": [],
        "messages": [],
    }


def _graph():
    return compile_graph(checkpointer=MemorySaver())


def _thread(suffix: str):
    return {"configurable": {"thread_id": f"revise-locked-{suffix}"}}


def test_begin_locked_slot_revision_rejects_unlocked_slot():
    partial = Slot(species=Attr("Gholdengo", locked=True))
    state = {
        **_base_state(team_draft=[partial, *[empty_slot() for _ in range(5)]]),
        "turn_payload": {
            "slot_index": 0,
            "field": "item",
            "value": "Focus Sash",
            "scope": "field_only",
        },
    }
    out = begin_locked_slot_revision(state)  # type: ignore[arg-type]
    assert out == {"slot_commit_error": REVISE_REQUIRES_LOCKED_MSG}
    assert "team_draft" not in out


def test_revise_locked_slot_item_edit_commits():
    graph = _graph()
    suffix = "item-edit-commit"
    graph.invoke({"format_id": VGC_MB}, config=_thread(suffix))
    locked = _locked_gholdengo()
    graph.update_state(
        _thread(suffix),
        _base_state(team_draft=[locked, *[empty_slot() for _ in range(5)]]),
    )
    with patch(
        "recommender.nodes.classify_pending",
        return_value={
            "turn_intent": "revise_locked_slot",
            "turn_payload": {
                "slot_index": 0,
                "field": "item",
                "value": "Focus Sash",
                "scope": "field_only",
            },
        },
    ):
        edited = graph.invoke({"pending_input": "change item to Focus Sash"}, config=_thread(suffix))
    assert edited.get("slot_commit_error") is None
    assert edited["pending_presentation"]["kind"] == "full_build_confirmation"
    assert edited["provisional_slot"].item == "Focus Sash"

    with patch(
        "recommender.nodes.classify_pending",
        return_value={"turn_intent": "full_slot_confirmed"},
    ):
        with patch("recommender.slot_fill.build_anchored_slot_fill_context") as discovery:
            discovery.return_value.context = None
            committed = graph.invoke({"pending_input": "yes"}, config=_thread(suffix))
    assert committed["team_draft"][0].item.value == "Focus Sash"
    assert all_locked(committed["team_draft"][0])


def test_revise_locked_slot_does_not_use_apply_lock():
    locked = _locked_gholdengo()
    state = {
        **_base_state(team_draft=[locked, *[empty_slot() for _ in range(5)]]),
        "turn_payload": {
            "slot_index": 0,
            "field": "item",
            "value": "Focus Sash",
            "scope": "field_only",
        },
    }
    with patch("recommender.nodes.apply_lock") as apply_lock_mock:
        begin_locked_slot_revision(state)  # type: ignore[arg-type]
        apply_lock_mock.assert_not_called()


def test_revise_item_into_mega_stone_updates_ceiling_notices():
    charizard = Slot(
        role=Attr("special_attacker", locked=True),
        species=Attr("Charizard", locked=True),
        ability=Attr("Solar Power", locked=True),
        item=Attr("Choice Specs", locked=True),
        moveset=Attr(["Heat Wave", "Solar Beam", "Protect", "Air Slash"], locked=True),
        nature=Attr("Modest", locked=True),
        spread=Attr(dict(SPREAD), locked=True),
    )
    state = _base_state(team_draft=[charizard, *[empty_slot() for _ in range(5)]])
    assert mega_ceiling_notices(state) == ()

    edited = Slot(
        **{
            **charizard.__dict__,
            "item": Attr("Charizardite Y", locked=True),
        }
    )
    after = {**state, "team_draft": [edited, *[empty_slot() for _ in range(5)]]}
    notices = mega_ceiling_notices(after)
    assert notices
    assert "Mega-Stone" in notices[0]


def test_revise_moves_removes_redirection_coverage():
    sinistcha = Slot(
        role=Attr("redirection", locked=True),
        species=Attr("Sinistcha", locked=True),
        ability=Attr("Hospitality", locked=True),
        item=Attr("Sitrus Berry", locked=True),
        moveset=Attr(
            ["Rage Powder", "Matcha Gotcha", "Trick Room", "Shadow Ball"], locked=True
        ),
        nature=Attr("Bold", locked=True),
        spread=Attr(dict(SPREAD), locked=True),
    )
    gholdengo = _locked_gholdengo()
    state = _base_state(team_draft=[sinistcha, gholdengo, *[empty_slot() for _ in range(4)]])
    locked_before = collect_locked_anchor_contexts(state)
    assert provider_need_category_open("redirection", locked_before) is False

    edited = Slot(
        **{
            **sinistcha.__dict__,
            "moveset": Attr(
                ["Matcha Gotcha", "Shadow Ball", "Trick Room", "Protect"], locked=True
            ),
        }
    )
    after = {
        **state,
        "team_draft": [edited, gholdengo, *[empty_slot() for _ in range(4)]],
    }
    locked_after = collect_locked_anchor_contexts(after)
    assert provider_need_category_open("redirection", locked_after) is True


def test_apply_lock_still_rejects_fully_locked_slot():
    locked = _locked_gholdengo()
    state = {
        **_base_state(team_draft=[locked, *[empty_slot() for _ in range(5)]]),
        "turn_payload": {
            "slot_index": 0,
            "attr": "item",
            "value": "Focus Sash",
        },
    }
    out = apply_lock(state)  # type: ignore[arg-type]
    assert "team_draft" not in out
    assert out.get("slot_commit_error")
