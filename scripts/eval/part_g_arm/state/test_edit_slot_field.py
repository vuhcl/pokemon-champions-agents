"""4a edit_slot_field — validators, consequences, refusal preserves pending."""

from __future__ import annotations

from scripts.eval.part_g_arm.state.edit_consequences import consequences_after_edit
from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.pending import _lock_internal, build_fully_locked_slot
from scripts.eval.part_g_arm.state.tools import edit_slot_field, lock_slot, read_team
from recommender.state import Attr, all_locked


def _partial_garchomp() -> dict:
    st = empty_team()
    st = _lock_internal(st, 0, "species", "Garchomp")
    st = _lock_internal(st, 0, "ability", "Sand Veil")
    return st


def test_edit_item_on_partial_slot():
    st = _partial_garchomp()
    after, res = edit_slot_field(st, 1, "item", "Sitrus Berry")
    assert res.get("ok")
    assert after["team_draft"][0].item.value == "Sitrus Berry"
    assert after["team_draft"][0].item.locked


def test_refuse_illegal_item_writes_nothing():
    st = _partial_garchomp()
    before_item = st["team_draft"][0].item.value
    after, res = edit_slot_field(st, 1, "item", "Choice Specs")
    assert res.get("slot_commit_error") or "refuse" in str(res).lower() or res.get("ok") is not True
    assert after["team_draft"][0].item.value == before_item


def test_choice_lock_consequence_lists_status_moves():
    st = build_fully_locked_slot("Gholdengo", user_slot=1)
    # Ensure status moves on set
    slot = st["team_draft"][0]
    from dataclasses import replace
    from recommender.state import Attr

    st = {
        **st,
        "team_draft": [
            replace(
                slot,
                item=Attr("Life Orb", locked=True),
                moveset=Attr(
                    ["Make It Rain", "Shadow Ball", "Protect", "Nasty Plot"],
                    locked=True,
                ),
            ),
            *st["team_draft"][1:],
        ],
    }
    assert all_locked(st["team_draft"][0])
    after, res = edit_slot_field(st, 1, "item", "Choice Scarf")
    assert res.get("ok"), res
    kinds = {c["kind"] for c in res.get("consequences") or []}
    assert "choice_lock_status" in kinds
    choice = next(c for c in res["consequences"] if c["kind"] == "choice_lock_status")
    assert "Nasty Plot" in choice["unusable_status_moves"] or "Protect" in choice["unusable_status_moves"]
    assert after["team_draft"][0].item.value == "Choice Scarf"
    # moves unchanged
    assert after["team_draft"][0].moveset.value == [
        "Make It Rain",
        "Shadow Ball",
        "Protect",
        "Nasty Plot",
    ]


def test_status_self_boost_overlap_fact():
    from recommender.state import Slot

    slot = Slot(
        species=Attr("Lucario-Mega-Z", locked=True),
        moveset=Attr(["Aura Sphere", "Flash Cannon", "Calm Mind", "Nasty Plot"], locked=True),
        item=Attr("Lucarionite Z", locked=True),
    )
    facts = consequences_after_edit(slot, changed_field="moveset")
    overlap = [f for f in facts if f["kind"] == "status_self_boost_overlap"]
    assert overlap
    assert "spa" in overlap[0]["shared_stats"]


def test_type_boost_inactive_when_no_fire_move():
    from recommender.state import Slot

    slot = Slot(
        species=Attr("Incineroar", locked=True),
        item=Attr("Charcoal", locked=True),
        moveset=Attr(["Fake Out", "Parting Shot", "Fire Punch", "Knock Off"], locked=True),
    )
    # Fire Punch is Fire damaging — active. Swap to no Fire:
    slot2 = Slot(
        species=Attr("Incineroar", locked=True),
        item=Attr("Charcoal", locked=True),
        moveset=Attr(["Fake Out", "Parting Shot", "Darkest Lariat", "Throat Chop"], locked=True),
    )
    facts = consequences_after_edit(slot2, changed_field="moveset")
    inactive = [f for f in facts if f["kind"] == "type_boost_inactive"]
    assert inactive
    assert inactive[0]["type"] == "Fire"
