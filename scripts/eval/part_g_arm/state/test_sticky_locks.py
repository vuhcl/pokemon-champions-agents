"""FU65 sticky_locks: draft set_slot refuses writes to locked fields (flag default off)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from recommender.state import Attr
from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.harness import dispatch
from scripts.eval.part_g_arm.state.tools import (
    set_draft,
    set_sticky_locks,
    set_tool_fields,
    set_wrapper,
)


@pytest.fixture(autouse=True)
def _flags_off():
    set_tool_fields(False)
    set_wrapper(False)
    set_draft(False)
    set_sticky_locks(False)
    yield
    set_tool_fields(False)
    set_wrapper(False)
    set_draft(False)
    set_sticky_locks(False)


def _enable_draft(*, sticky: bool) -> None:
    set_tool_fields(True)
    set_wrapper(True)
    set_draft(True)
    set_sticky_locks(sticky)


def _arm():
    from recommender.arm_tools import ArmTools
    from recommender.calc_client import CalcClient

    return ArmTools(regulation="champions", allow_live=False, calc=CalcClient())


def _seed_locked_species_item() -> dict:
    """Draft Venusaur + Sitrus, then lock both."""
    _enable_draft(sticky=True)
    arm = _arm()
    st, _ = dispatch(
        empty_team(),
        arm,
        "set_slot",
        {"species": "Venusaur", "item": "Sitrus Berry", "slot": 1},
    )
    st, _ = dispatch(st, arm, "lock_fields", {"slot": 1, "fields": ["species", "item"]})
    return st


def test_sticky_refuses_locked_field_value_and_lock_unchanged():
    st = _seed_locked_species_item()
    arm = _arm()
    before_item = st["team_draft"][0].item.value
    before_locked = st["team_draft"][0].item.locked
    st2, res = dispatch(st, arm, "set_slot", {"slot": 1, "item": "Leftovers"})
    assert res.get("ok") is False
    assert res.get("error_kind") == "field_locked"
    assert "field locked, value unchanged" in (res.get("slot_commit_error") or "")
    assert res.get("ok") is not True
    assert "applied" not in res
    locked_fields = res.get("locked_fields") or []
    assert any(r.get("field") == "item" and r.get("lock_unchanged") for r in locked_fields)
    assert st2["team_draft"][0].item.value == before_item
    assert st2["team_draft"][0].item.locked is before_locked is True
    after = res.get("state_after") or {}
    assert after.get("slots")
    assert after["slots"][0]["attributes"]["item"]["status"] == "locked"
    assert after["slots"][0]["attributes"]["item"]["value"] == before_item


def test_sticky_atomic_mixed_locked_and_unlocked():
    """Locked + unlocked fields in one call: nothing applied (atomic)."""
    st = _seed_locked_species_item()
    arm = _arm()
    # ability is unlocked/empty; item is locked.
    st2, res = dispatch(
        st, arm, "set_slot", {"slot": 1, "item": "Leftovers", "ability": "Chlorophyll"}
    )
    assert res.get("ok") is False
    assert res.get("error_kind") == "field_locked"
    causes = [el.get("cause") for el in (res.get("elements") or [])]
    assert "field locked, value unchanged" in causes
    assert "not applied: sibling field locked" in causes
    assert st2["team_draft"][0].item.value == "Sitrus Berry"
    assert st2["team_draft"][0].item.locked is True
    assert st2["team_draft"][0].ability.value is None


def test_sticky_unlocked_field_still_writes():
    _enable_draft(sticky=True)
    arm = _arm()
    st, _ = dispatch(empty_team(), arm, "set_slot", {"species": "Venusaur", "slot": 1})
    st, _ = dispatch(st, arm, "lock_fields", {"slot": 1, "fields": ["species"]})
    st2, res = dispatch(st, arm, "set_slot", {"slot": 1, "item": "Sitrus Berry"})
    assert res.get("ok") is True
    assert st2["team_draft"][0].item.value == "Sitrus Berry"
    assert st2["team_draft"][0].item.locked is False
    assert st2["team_draft"][0].species.locked is True
    assert "locked" not in (res.get("applied") or [{}])[0]
    assert (res.get("applied") or [{}])[0].get("field_locks", {}).get("species") is True


def test_sticky_unlock_fields_then_write_succeeds():
    st = _seed_locked_species_item()
    arm = _arm()
    st, res_u = dispatch(st, arm, "unlock_fields", {"slot": 1, "fields": ["item"]})
    assert res_u.get("ok") is True
    st2, res = dispatch(st, arm, "set_slot", {"slot": 1, "item": "Leftovers"})
    assert res.get("ok") is True
    assert st2["team_draft"][0].item.value == "Leftovers"
    assert st2["team_draft"][0].item.locked is False


def test_sticky_refusal_not_success_shaped():
    st = _seed_locked_species_item()
    arm = _arm()
    _, res = dispatch(st, arm, "set_slot", {"slot": 1, "item": "Leftovers"})
    assert res.get("ok") is False
    assert res.get("write_mode") is None
    assert res.get("error_kind") == "field_locked"
    text = str(res.get("slot_commit_error") or "")
    assert "unchanged" in text
    assert "applied" not in res


def test_flag_off_reproduces_a393ae91_clears_lock():
    """sticky_locks off: draft set_slot overwrites locked field and clears the lock."""
    _enable_draft(sticky=False)
    arm = _arm()
    st, _ = dispatch(
        empty_team(),
        arm,
        "set_slot",
        {"species": "Venusaur", "item": "Sitrus Berry", "slot": 1},
    )
    st, _ = dispatch(st, arm, "lock_fields", {"slot": 1, "fields": ["item"]})
    assert st["team_draft"][0].item.locked is True
    st2, res = dispatch(st, arm, "set_slot", {"slot": 1, "item": "Leftovers"})
    assert res.get("ok") is True
    assert res.get("write_mode") == "draft"
    assert (res.get("applied") or [{}])[0].get("locked") is False
    assert "field_locks" not in (res.get("applied") or [{}])[0]
    assert st2["team_draft"][0].item.value == "Leftovers"
    assert st2["team_draft"][0].item.locked is False
    assert res.get("error_kind") is None


def test_sticky_default_off_identity():
    """Module default is off; enabling draft alone does not sticky-refuse."""
    from scripts.eval.part_g_arm.state.tools import sticky_locks_enabled

    assert sticky_locks_enabled() is False
    _enable_draft(sticky=False)
    arm = _arm()
    from scripts.eval.part_g_arm.state.pending import build_fully_locked_slot

    st = build_fully_locked_slot("Mawile", user_slot=1)
    slot0 = st["team_draft"][0]
    st["team_draft"][0] = replace(slot0, item=Attr("Sitrus Berry", locked=True))
    st2, res = dispatch(st, arm, "set_slot", {"slot": 1, "item": "Leftovers"})
    assert res.get("ok") is True, res
    assert st2["team_draft"][0].item.locked is False
