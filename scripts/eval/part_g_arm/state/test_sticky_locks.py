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
    set_tool_fixes_v2,
    set_unlock_keeps_values,
    set_wrapper,
)


@pytest.fixture(autouse=True)
def _flags_off():
    set_tool_fields(False)
    set_wrapper(False)
    set_draft(False)
    set_sticky_locks(False)
    set_unlock_keeps_values(False)
    set_tool_fixes_v2(False)
    yield
    set_tool_fields(False)
    set_wrapper(False)
    set_draft(False)
    set_sticky_locks(False)
    set_unlock_keeps_values(False)
    set_tool_fixes_v2(False)


def _enable_draft(*, sticky: bool = False, keep: bool = False) -> None:
    set_tool_fields(True)
    set_wrapper(True)
    set_draft(True)
    set_sticky_locks(sticky)
    set_unlock_keeps_values(keep)


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


# --- FU66: unlock tools need an explicit user unlock request under sticky_locks ---


def test_sticky_unprompted_unlock_fields_refused():
    """Model-initiated unlock_fields on a set_slot turn is guard-blocked."""
    from scripts.eval.part_g_arm.state.guard_exec import check_call, init_turn_ctx

    st = _seed_locked_species_item()
    user = "Switch its item to Leftovers."
    ctx = init_turn_ctx(
        [{"class": "WRITE", "action": "set_slot", "confirms_replacement": False}],
        st,
        user_text=user,
    )
    assert "unlock_fields" not in ctx["allowed"]
    refusal = check_call(
        "unlock_fields",
        {"slot": 1, "fields": ["item"]},
        allowed=ctx["allowed"] | {"unlock_fields"},  # even if bound, sticky blocks
        guard_class="WRITE",
        confirms_replacement=False,
        pending_asked=None,
        state=st,
        user_text=user,
    )
    assert refusal is not None
    assert refusal.get("guard_blocked") is True
    assert refusal.get("reason") == "unlock without user request"
    msg = refusal.get("message") or ""
    assert "unlock_fields" in msg and "unlock_slot" in msg
    assert "request class" not in msg  # names tools, not only class (entry 38)
    assert st["team_draft"][0].item.locked is True


def test_sticky_explicit_unlock_request_allows_unlock_fields():
    from scripts.eval.part_g_arm.state.guard_exec import guarded_dispatch, init_turn_ctx
    from scripts.eval.part_g_arm.state.harness import dispatch as real_dispatch

    st = _seed_locked_species_item()
    user = "Unlock the item on slot 1"
    ctx = init_turn_ctx(
        [{"class": "WRITE", "action": "unlock_fields", "confirms_replacement": False}],
        st,
        user_text=user,
    )
    assert "unlock_fields" in ctx["allowed"]

    def _dispatch(state, arm, name, args):  # noqa: ANN001
        return real_dispatch(state, arm, name, args)

    st2, res = guarded_dispatch(
        st,
        _arm(),
        "unlock_fields",
        {"slot": 1, "fields": ["item"]},
        turn_ctx=ctx,
        dispatch_fn=_dispatch,
    )
    assert res.get("guard_blocked") is not True
    assert res.get("ok") is True
    assert st2["team_draft"][0].item.locked is False
    assert st2["team_draft"][0].item.value == "Sitrus Berry"


def test_sticky_explicit_unlock_then_write_succeeds():
    from scripts.eval.part_g_arm.state.guard_exec import guarded_dispatch, init_turn_ctx
    from scripts.eval.part_g_arm.state.harness import dispatch as real_dispatch

    st = _seed_locked_species_item()
    arm = _arm()

    def _dispatch(state, _arm, name, args):  # noqa: ANN001
        return real_dispatch(state, arm, name, args)

    ctx_u = init_turn_ctx(
        [{"class": "WRITE", "action": "unlock_fields"}],
        st,
        user_text="Unlock slot 1 item",
    )
    st, res_u = guarded_dispatch(
        st,
        arm,
        "unlock_fields",
        {"slot": 1, "fields": ["item"]},
        turn_ctx=ctx_u,
        dispatch_fn=_dispatch,
    )
    assert res_u.get("ok") is True
    st2, res = dispatch(st, arm, "set_slot", {"slot": 1, "item": "Leftovers"})
    assert res.get("ok") is True
    assert st2["team_draft"][0].item.value == "Leftovers"
    assert st2["team_draft"][0].item.locked is False


def test_sticky_unlock_slot_replace_rule_unchanged_when_keep_off():
    """Flag off: explicit unlock passes FU66; unlock_slot replace=true still needs confirm."""
    from scripts.eval.part_g_arm.state.guard_exec import check_call, init_turn_ctx

    st = _seed_locked_species_item()  # sticky on, keep off
    user = "Unlock slot 1"
    ctx = init_turn_ctx(
        [{"class": "WRITE", "action": "unlock_slot", "confirms_replacement": False}],
        st,
        user_text=user,
    )
    assert "unlock_slot" in ctx["allowed"]
    mid = check_call(
        "unlock_slot",
        {"slot": 1},
        allowed=ctx["allowed"],
        guard_class="WRITE",
        confirms_replacement=False,
        pending_asked=None,
        state=st,
        user_text=user,
    )
    assert mid is None
    refusal = check_call(
        "unlock_slot",
        {"slot": 1, "replace": True},
        allowed=ctx["allowed"],
        guard_class="WRITE",
        confirms_replacement=False,
        pending_asked=None,
        state=st,
        user_text=user,
    )
    assert refusal is not None
    assert refusal.get("reason") == "replace=true without confirmation"


def test_flag_off_unlock_fields_unprompted_still_runs():
    """sticky_locks off: unlock_fields needs no user unlock text (a393ae91)."""
    from scripts.eval.part_g_arm.state.guard_exec import check_call, init_turn_ctx

    _enable_draft(sticky=False)
    arm = _arm()
    st, _ = dispatch(
        empty_team(),
        arm,
        "set_slot",
        {"species": "Venusaur", "item": "Sitrus Berry", "slot": 1},
    )
    st, _ = dispatch(st, arm, "lock_fields", {"slot": 1, "fields": ["item"]})
    ctx = init_turn_ctx(
        [{"class": "WRITE", "action": "unlock_fields"}],
        st,
        user_text="Switch its item to Leftovers.",
    )
    assert "unlock_fields" in ctx["allowed"]
    refusal = check_call(
        "unlock_fields",
        {"slot": 1, "fields": ["item"]},
        allowed=ctx["allowed"],
        guard_class="WRITE",
        confirms_replacement=False,
        pending_asked=None,
        state=st,
        user_text="Switch its item to Leftovers.",
    )
    assert refusal is None
    st2, res = dispatch(st, arm, "unlock_fields", {"slot": 1, "fields": ["item"]})
    assert res.get("ok") is True
    assert st2["team_draft"][0].item.locked is False


# --- FU67 / entry 58: unlock_keeps_values ---


def test_unlock_slot_keeps_values_clears_locks():
    _enable_draft(sticky=True, keep=True)
    arm = _arm()
    st, _ = dispatch(
        empty_team(),
        arm,
        "set_slot",
        {"species": "Venusaur", "item": "Sitrus Berry", "slot": 1},
    )
    st, _ = dispatch(st, arm, "lock_fields", {"slot": 1})
    assert st["team_draft"][0].species.locked is True
    st2, res = dispatch(st, arm, "unlock_slot", {"slot": 1, "replace": True})
    assert res.get("ok") is True, res
    assert res.get("wiped") is not True
    assert st2["team_draft"][0].species.value == "Venusaur"
    assert st2["team_draft"][0].item.value == "Sitrus Berry"
    assert st2["team_draft"][0].species.locked is False
    assert st2["team_draft"][0].item.locked is False


def test_unlock_slot_then_set_slot_under_both_flags():
    from scripts.eval.part_g_arm.state.guard_exec import guarded_dispatch, init_turn_ctx
    from scripts.eval.part_g_arm.state.harness import dispatch as real_dispatch

    _enable_draft(sticky=True, keep=True)
    arm = _arm()
    st, _ = dispatch(
        empty_team(),
        arm,
        "set_slot",
        {"species": "Venusaur", "item": "Sitrus Berry", "slot": 1},
    )
    st, _ = dispatch(st, arm, "lock_fields", {"slot": 1, "fields": ["item"]})

    def _dispatch(state, _a, name, args):  # noqa: ANN001
        return real_dispatch(state, arm, name, args)

    ctx = init_turn_ctx(
        [{"class": "WRITE", "action": "unlock_slot"}],
        st,
        user_text="Unlock slot 1",
    )
    assert "unlock_slot" in ctx["allowed"]
    assert "clear_slot" not in ctx["allowed"]
    st, res_u = guarded_dispatch(
        st, arm, "unlock_slot", {"slot": 1}, turn_ctx=ctx, dispatch_fn=_dispatch
    )
    assert res_u.get("ok") is True
    assert st["team_draft"][0].item.locked is False
    st2, res = dispatch(st, arm, "set_slot", {"slot": 1, "item": "Leftovers"})
    assert res.get("ok") is True
    assert st2["team_draft"][0].item.value == "Leftovers"


def test_clear_slot_needs_replace_confirmation():
    from scripts.eval.part_g_arm.state.guard_exec import check_call, init_turn_ctx

    _enable_draft(sticky=True, keep=True)
    arm = _arm()
    st, _ = dispatch(
        empty_team(),
        arm,
        "set_slot",
        {"species": "Venusaur", "slot": 1},
    )
    user = "Clear slot 1"
    ctx = init_turn_ctx(
        [{"class": "WRITE", "action": "clear", "confirms_replacement": False}],
        st,
        user_text=user,
    )
    assert "clear_slot" in ctx["allowed"]
    refusal = check_call(
        "clear_slot",
        {"slot": 1, "replace": True},
        allowed=ctx["allowed"],
        guard_class="WRITE",
        confirms_replacement=False,
        pending_asked=None,
        state=st,
        user_text=user,
    )
    assert refusal is not None
    assert refusal.get("reason") == "replace=true without confirmation"
    # With confirms: wipe allowed at guard; tool still needs replace=true.
    ok = check_call(
        "clear_slot",
        {"slot": 1, "replace": True},
        allowed=ctx["allowed"],
        guard_class="WRITE",
        confirms_replacement=True,
        pending_asked=None,
        state=st,
        user_text=user,
    )
    assert ok is None
    st2, res = dispatch(st, arm, "clear_slot", {"slot": 1, "replace": True})
    assert res.get("ok") is True
    assert res.get("wiped") is True
    assert st2["team_draft"][0].species.value is None


def test_unlock_negation_does_not_bind_unlock_tools():
    from scripts.eval.part_g_arm.state.guard_allowed import user_requests_unlock
    from scripts.eval.part_g_arm.state.guard_exec import init_turn_ctx

    _enable_draft(sticky=True, keep=True)
    st = empty_team()
    text = "Keep it locked, don't unlock slot 1"
    assert user_requests_unlock(text) is False
    ctx = init_turn_ctx(
        [{"class": "WRITE", "action": "set_slot"}],
        st,
        user_text=text,
    )
    assert "unlock_slot" not in ctx["allowed"]
    assert "unlock_fields" not in ctx["allowed"]


def test_keep_flag_off_unlock_slot_still_wipes_with_replace():
    """unlock_keeps_values off: draft unlock_slot remains a393ae91 wipe path."""
    _enable_draft(sticky=False, keep=False)
    arm = _arm()
    st, _ = dispatch(
        empty_team(),
        arm,
        "set_slot",
        {"species": "Venusaur", "slot": 1},
    )
    st2, res = dispatch(st, arm, "unlock_slot", {"slot": 1, "replace": True})
    assert res.get("ok") is True
    assert res.get("wiped") is True
    assert st2["team_draft"][0].species.value is None


def test_both_flags_off_equals_a393ae91_unlock_and_set_slot():
    _enable_draft(sticky=False, keep=False)
    arm = _arm()
    st, _ = dispatch(
        empty_team(),
        arm,
        "set_slot",
        {"species": "Venusaur", "item": "Sitrus Berry", "slot": 1},
    )
    st, _ = dispatch(st, arm, "lock_fields", {"slot": 1, "fields": ["item"]})
    st2, res = dispatch(st, arm, "set_slot", {"slot": 1, "item": "Leftovers"})
    assert res.get("ok") is True
    assert st2["team_draft"][0].item.locked is False
    assert (res.get("applied") or [{}])[0].get("locked") is False
