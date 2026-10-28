"""check_hypothetical stages species+item siblings (same as apply_lock batch)."""

from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.tools import check_hypothetical


def test_mega_without_item_refuses_mega_stone():
    r = check_hypothetical(empty_team(), [{"species": "Salamence-Mega"}])
    assert r["verdict"] == "mega_stone"
    assert "Salamencite" in (r.get("message") or "")


def test_mega_with_stone_in_same_placement_ok():
    r = check_hypothetical(
        empty_team(), [{"species": "Salamence-Mega", "item": "Salamencite"}]
    )
    assert r == {"verdict": "ok", "conflicts_with_slot": None, "message": None}


def test_mega_with_wrong_item_refuses():
    r = check_hypothetical(
        empty_team(), [{"species": "Salamence-Mega", "item": "Leftovers"}]
    )
    assert r["verdict"] == "mega_stone"
