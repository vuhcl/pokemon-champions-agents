"""draft rung: set_slot drafts only; lock_fields; replace on draft wipe/swap."""

from __future__ import annotations

import hashlib
import json

import pytest

from scripts.eval.part_g_arm.config import ArmConfig
from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.harness import dispatch
from scripts.eval.part_g_arm.state.request_set_runner import (
    DRAFT_PROMPT_FILE,
    WRAPPER_PROMPT_FILE,
)
from scripts.eval.part_g_arm.state.tools import (
    combined_specs,
    read_team,
    set_draft,
    set_tool_fields,
    set_wrapper,
)


@pytest.fixture(autouse=True)
def _flags_off():
    set_tool_fields(False)
    set_wrapper(False)
    set_draft(False)
    yield
    set_tool_fields(False)
    set_wrapper(False)
    set_draft(False)


def _enable_draft() -> None:
    set_tool_fields(True)
    set_wrapper(True)
    set_draft(True)


def test_flags_off_and_wrapper_only_identity():
    """draft off: flags-off and wrapper-only schemas unchanged vs prior rungs."""
    off = hashlib.sha256(
        json.dumps(combined_specs(tool_fields=False, wrapper=False, draft=False), sort_keys=True).encode()
    ).hexdigest()
    assert off == "f0c97ad3b88cb3f118e241111bd454a4e86f7937cd4342f0969cadbe5049b845"
    wrap = combined_specs(tool_fields=True, wrapper=True, draft=False)
    names = [s["function"]["name"] for s in wrap]
    assert "set_slot" in names
    assert "lock_fields" not in names
    assert "lock_slot" not in names


def test_draft_prompt_sha_distinct():
    from pathlib import Path

    h = ArmConfig(prompt_file=DRAFT_PROMPT_FILE).prompt_hash()
    wrap = ArmConfig(prompt_file=WRAPPER_PROMPT_FILE).prompt_hash()
    assert h != wrap
    assert h == hashlib.sha256(
        Path("scripts/eval/part_g_arm/state/prompt_draft.md").read_bytes()
    ).hexdigest()


def test_set_slot_draft_never_locks():
    _enable_draft()
    from recommender.arm_tools import ArmTools
    from recommender.calc_client import CalcClient

    arm = ArmTools(regulation="champions", allow_live=False, calc=CalcClient())
    st, res = dispatch(
        empty_team(),
        arm,
        "set_slot",
        {"species": "Venusaur", "item": "Sitrus Berry", "slot": 1},
    )
    assert res.get("ok") is True
    assert res.get("write_mode") == "draft"
    team = read_team(st)
    attrs = team["slots"][0]["attributes"]
    assert attrs["species"]["value"] == "Venusaur"
    assert attrs["species"]["status"] == "draft"
    assert attrs["item"]["status"] == "draft"
    assert attrs["species"]["status"] != "locked"


def test_lock_fields_and_unlock_fields():
    _enable_draft()
    from recommender.arm_tools import ArmTools
    from recommender.calc_client import CalcClient

    arm = ArmTools(regulation="champions", allow_live=False, calc=CalcClient())
    st, _ = dispatch(empty_team(), arm, "set_slot", {"species": "Venusaur", "slot": 1})
    st, res = dispatch(st, arm, "lock_fields", {"slot": 1, "fields": ["species"]})
    assert res.get("ok") is True
    assert "species" in (res.get("locked") or [])
    assert read_team(st)["slots"][0]["attributes"]["species"]["status"] == "locked"
    st, res2 = dispatch(st, arm, "unlock_fields", {"slot": 1, "fields": ["species"]})
    assert res2.get("ok") is True
    assert read_team(st)["slots"][0]["attributes"]["species"]["status"] == "draft"
    assert read_team(st)["slots"][0]["attributes"]["species"]["value"] == "Venusaur"


def test_species_swap_draft_needs_replace():
    _enable_draft()
    from recommender.arm_tools import ArmTools
    from recommender.calc_client import CalcClient

    arm = ArmTools(regulation="champions", allow_live=False, calc=CalcClient())
    st, _ = dispatch(empty_team(), arm, "set_slot", {"species": "Venusaur", "slot": 1})
    st2, res = dispatch(st, arm, "set_slot", {"species": "Clefable", "slot": 1})
    assert res.get("ok") is False
    assert "Venusaur" in (res.get("slot_commit_error") or "")
    assert st2["team_draft"][0].species.value == "Venusaur"
    st3, res2 = dispatch(
        st, arm, "set_slot", {"species": "Clefable", "slot": 1, "replace": True}
    )
    assert res2.get("ok") is True
    assert st3["team_draft"][0].species.value == "Clefable"
    assert st3["team_draft"][0].species.locked is False


def test_attr_edit_draft_no_replace():
    _enable_draft()
    from recommender.arm_tools import ArmTools
    from recommender.calc_client import CalcClient

    arm = ArmTools(regulation="champions", allow_live=False, calc=CalcClient())
    st, _ = dispatch(empty_team(), arm, "set_slot", {"species": "Venusaur", "slot": 1})
    st, res = dispatch(st, arm, "set_slot", {"slot": 1, "item": "Sitrus Berry"})
    assert res.get("ok") is True
    assert st["team_draft"][0].item.value == "Sitrus Berry"
    assert st["team_draft"][0].item.locked is False


def test_unlock_slot_draft_needs_replace():
    _enable_draft()
    from recommender.arm_tools import ArmTools
    from recommender.calc_client import CalcClient

    arm = ArmTools(regulation="champions", allow_live=False, calc=CalcClient())
    st, _ = dispatch(empty_team(), arm, "set_slot", {"species": "Venusaur", "slot": 1})
    st2, res = dispatch(st, arm, "unlock_slot", {"slot": 1})
    assert res.get("ok") is False
    assert "Venusaur" in (res.get("slot_commit_error") or "")
    st3, res2 = dispatch(st, arm, "unlock_slot", {"slot": 1, "replace": True})
    assert res2.get("ok") is True
    assert st3["team_draft"][0].species.value is None


def test_item_clause_on_draft():
    _enable_draft()
    from recommender.arm_tools import ArmTools
    from recommender.calc_client import CalcClient
    from scripts.eval.part_g_arm.state.pending import build_fully_locked_slot

    arm = ArmTools(regulation="champions", allow_live=False, calc=CalcClient())
    # Slot 1 locked Sitrus; draft slot 2 same item → Item Clause.
    st = build_fully_locked_slot("Mawile", user_slot=1)
    # Ensure item is Sitrus on locked slot
    from dataclasses import replace
    from recommender.state import Attr

    slot0 = st["team_draft"][0]
    st["team_draft"][0] = replace(slot0, item=Attr("Sitrus Berry", locked=True))
    st2, res = dispatch(
        st, arm, "set_slot", {"slot": 2, "species": "Hydreigon", "item": "Sitrus Berry"}
    )
    assert res.get("ok") is False
    assert "Item Clause" in (res.get("slot_commit_error") or "") or "item" in (
        res.get("slot_commit_error") or ""
    ).lower()


def test_default_slot_skips_draft():
    _enable_draft()
    from recommender.arm_tools import ArmTools
    from recommender.calc_client import CalcClient

    arm = ArmTools(regulation="champions", allow_live=False, calc=CalcClient())
    st, _ = dispatch(empty_team(), arm, "set_slot", {"species": "Venusaur"})
    assert st["team_draft"][0].species.value == "Venusaur"
    st, res = dispatch(st, arm, "set_slot", {"species": "Clefable"})
    assert res.get("ok") is True, res
    assert st["team_draft"][0].species.value == "Venusaur"
    assert st["team_draft"][1].species.value == "Clefable"
