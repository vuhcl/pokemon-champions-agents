"""A3: blocked calls after refused unconfirmed replace (2026-10-30 finding)."""

from __future__ import annotations

from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.guard_allowed import has_valued_attribute
from scripts.eval.part_g_arm.state.guard_exec import check_call, guarded_dispatch, init_turn_ctx
from recommender.state import Attr


def test_a3_unlock_then_set_blocked_after_unconfirmed_replace():
    """After a refused replace, model tries unlock_slot then set_slot — neither runs."""
    st = empty_team()
    st["team_draft"][0].species = Attr("Garchomp", False)
    # ASK turn: user has not confirmed replace; only READ tools allowed.
    ctx = init_turn_ctx(
        [{"class": "ASK", "action": "set_slot", "confirms_replacement": False}],
        st,
    )
    assert "unlock_slot" not in ctx["allowed"]
    assert "set_slot" not in ctx["allowed"]

    def _boom(*_a, **_k):  # noqa: ANN001
        raise AssertionError("dispatch must not run for blocked calls")

    st2, r1 = guarded_dispatch(
        st,
        None,
        "unlock_slot",
        {"slot": 1, "replace": True},
        turn_ctx=ctx,
        dispatch_fn=_boom,
    )
    assert st2 is st
    assert r1.get("guard_blocked") is True
    assert "unlock_slot" in (r1.get("message") or "")

    st3, r2 = guarded_dispatch(
        st2,
        None,
        "set_slot",
        {"slot": 1, "species": "Landorus-Therian", "replace": True},
        turn_ctx=ctx,
        dispatch_fn=_boom,
    )
    assert st3 is st
    assert r2.get("guard_blocked") is True
    assert len(ctx["blocked_calls"]) == 2
    assert [b["name"] for b in ctx["blocked_calls"]] == ["unlock_slot", "set_slot"]


def test_replace_true_allowed_when_confirmed():
    st = empty_team()
    st["team_draft"][0].species = Attr("Garchomp", False)
    ctx = init_turn_ctx(
        [
            {
                "class": "WRITE",
                "action": "set_slot",
                "confirms_replacement": True,
            }
        ],
        st,
    )
    refusal = check_call(
        "set_slot",
        {"slot": 1, "species": "Landorus-Therian", "replace": True},
        allowed=ctx["allowed"],
        guard_class="WRITE",
        confirms_replacement=True,
        pending_asked=None,
        state=st,
    )
    assert refusal is None


def test_allowed_recomputed_after_set_slot_enables_lock_fields():
    """MS1/MS8/MT2: lock_fields unbound on empty; bound after a draft set_slot in-turn."""
    st = empty_team()
    subs = [
        {"class": "WRITE", "action": "set_slot"},
        {"class": "WRITE", "action": "lock_fields"},
    ]
    ctx = init_turn_ctx(subs, st)
    assert "lock_fields" not in ctx["allowed"]

    def _fake_set_slot(state, arm, name, args):  # noqa: ANN001
        assert name == "set_slot"
        state = dict(state)
        draft = list(state["team_draft"])
        draft[1] = draft[1]  # slot index 1 = user slot 2
        from recommender.state import Attr
        from dataclasses import replace

        draft[1] = replace(draft[1], species=Attr("Garchomp", False))
        state["team_draft"] = draft
        return state, {"ok": True, "species": "Garchomp"}

    st2, _ = guarded_dispatch(
        st, None, "set_slot", {"slot": 2, "species": "Garchomp"}, turn_ctx=ctx, dispatch_fn=_fake_set_slot
    )
    # Recomputed after the call for the *next* check:
    assert "lock_fields" in ctx["allowed"]
    assert has_valued_attribute(st2)

    def _fake_lock(state, arm, name, args):  # noqa: ANN001
        assert name == "lock_fields"
        return state, {"ok": True}

    _, r = guarded_dispatch(
        st2, None, "lock_fields", {"slot": 2}, turn_ctx=ctx, dispatch_fn=_fake_lock
    )
    assert not r.get("guard_blocked")


def test_cap_blocks_after_16():
    st = empty_team()
    ctx = init_turn_ctx([{"class": "LOOKUP"}], st)
    ctx["tool_call_count"] = 16
    ran = {"n": 0}

    def _dispatch(state, arm, name, args):  # noqa: ANN001
        ran["n"] += 1
        return state, {"ok": True}

    _, refusal = guarded_dispatch(
        st, None, "get_typing", {"species": "Toxapex"}, turn_ctx=ctx, dispatch_fn=_dispatch
    )
    assert refusal.get("guard_blocked")
    assert "cap" in (refusal.get("reason") or "")
    assert ran["n"] == 0
    assert ctx["cap_hit"] is True
