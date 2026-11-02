"""A1/A2: allowed_tools table + mapping §4 availability rules."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pytest

from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.guard_allowed import (
    WRITE_ACTION_TOOLS,
    allowed_tools,
    first_blank_slot_index,
    has_fully_locked_anchor,
    has_valued_attribute,
    pending_fingerprint_matches,
    stamp_pending_team_fingerprint,
    team_fingerprint,
)
from scripts.eval.part_g_arm.state.request_set_rows import load_request_rows, resolve_start_state
from recommender.state import Attr, Slot, all_locked

HERE = Path(__file__).resolve().parent
REV3 = HERE / "expected_tools_fu16" / "expected_tools_rev3_2026-11-02.csv"

# Tool name → parser action used by the A1 oracle.
_TOOL_TO_ACTION: dict[str, str] = {}
for action, tools in WRITE_ACTION_TOOLS.items():
    for t in tools:
        _TOOL_TO_ACTION.setdefault(t, action)


def _split_tools(cell: str) -> list[str]:
    out: list[str] = []
    for step in (cell or "").split(";"):
        step = step.strip()
        if not step:
            continue
        for alt in step.split("|"):
            t = alt.strip()
            if t:
                out.append(t)
    return out


def _effective_class(row: dict[str, str]) -> str:
    o = (row.get("guard_class_override") or "").strip()
    return o or row["proposed_guard_class"]


def _oracle_sub_requests(row: dict[str, str]) -> list[dict[str, Any]]:
    """Oracle parser: class from CSV; WRITE actions inferred from expected write tools."""
    cls = _effective_class(row)
    all_tools: list[str] = []
    for col in ("expected_tools_ordered", "optional_tools", "alternative_path"):
        all_tools.extend(_split_tools(row.get(col) or ""))
    numeric = {"calc_damage", "get_speed", "solve_spread", "describe", "no_lookup_needed"}
    need_numeric = any(t in numeric for t in all_tools)
    if cls in ("ASK", "READ_ONLY_REFUSE", "READ_STATE", "LOOKUP", "HYPOTHETICAL"):
        return [
            {
                "class": cls,
                "action": None,
                "numeric_or_explain": need_numeric and cls in ("LOOKUP", "HYPOTHETICAL"),
                "confirms_replacement": False,
            }
        ]
    # WRITE / PENDING_ANSWER: one sub-request per distinct write action needed.
    actions: list[str] = []
    for t in all_tools:
        if t.startswith("reject"):
            act = "reject"
        else:
            act = _TOOL_TO_ACTION.get(t)
        if act and act not in actions:
            actions.append(act)
    if not actions:
        actions = ["set_slot"]
    return [
        {
            "class": cls,
            "action": a,
            "numeric_or_explain": need_numeric,
            "confirms_replacement": False,
        }
        for a in actions
    ]


def _fixture_for_row(row_id: str, turn: str, request_rows: list[dict[str, Any]]) -> dict[str, Any]:
    match = next((r for r in request_rows if r.get("id") == row_id), None)
    if match is None:
        return empty_team()
    state, meta = resolve_start_state(match)
    if state is None:
        return empty_team()
    # PENDING_ANSWER / select rows: ensure CS pending has a fresh team fingerprint.
    if isinstance(state.get("pending_presentation"), dict):
        stamp_pending_team_fingerprint(state)
    return state


# Tools named in the approved mapping (draft-rung surface). Anything else is out of scope
# for A1 (e.g. get_featured_builds — FU19 out of scope / new_tool_needed).
_MAPPED_TOOLS: frozenset[str] = frozenset(
    {
        "get_typing",
        "get_abilities",
        "check_species_ability",
        "check_species_legal",
        "check_item_legal",
        "get_move_static",
        "check_learnset",
        "find_species",
        "get_usage_items",
        "get_usage_teammates",
        "get_usage_spreads",
        "get_usage_stats",
        "get_common_speeds",
        "get_meta_threats",
        "calc_damage",
        "get_speed",
        "solve_spread",
        "describe",
        "no_lookup_needed",
        "read_team",
        "read_pending",
        "read_constraints",
        "read_archetype",
        "read_rejected",
        "check_hypothetical",
        "show_candidates",
        "set_slot",
        "lock_fields",
        "unlock_fields",
        "unlock_slot",
        "select_option",
        "commit_slot",
        "confirm_build",
        "reject_pending",
        "reject_option",
        "reject_all",
        "add_constraint",
        "restore_constraint",
        "set_constraint_active",
        "change_archetype",
        "reset_team",
    }
)


def test_a1_oracle_allowed_covers_expected_tools():
    request_rows = load_request_rows()
    rows = list(csv.DictReader(REV3.open(newline="", encoding="utf-8")))
    assert len(rows) == 118
    failures: list[str] = []
    state_removed: list[str] = []
    csv_vs_mapping: list[str] = []
    out_of_scope: list[str] = []
    for row in rows:
        rid = f'{row["row_id"]} t{row["turn"]}'
        cls = _effective_class(row)
        state = _fixture_for_row(row["row_id"], row["turn"], request_rows)
        subs = _oracle_sub_requests(row)
        pending_asked = None
        if cls == "PENDING_ANSWER":
            for sub in subs:
                if sub.get("action"):
                    pending_asked = {
                        "action": sub["action"],
                        "missing_argument": None,
                        "slot_context": None,
                    }
                    break
        allowed = allowed_tools(subs, state, pending_asked=pending_asked)
        needed = set()
        for col in ("expected_tools_ordered", "optional_tools", "alternative_path"):
            needed.update(_split_tools(row.get(col) or ""))
        unmapped = sorted(t for t in needed if t not in _MAPPED_TOOLS and not t.startswith("reject"))
        if unmapped:
            out_of_scope.append(f"{rid}: {unmapped}")
        needed &= _MAPPED_TOOLS | {t for t in needed if t.startswith("reject")}
        missing = sorted(needed - allowed)
        if not missing:
            continue
        # FU22 §1: no_lookup_needed is not bound on WRITE / PENDING_ANSWER / READ_STATE.
        if cls in ("WRITE", "PENDING_ANSWER", "READ_STATE") and set(missing) <= {
            "no_lookup_needed"
        }:
            csv_vs_mapping.append(
                f"{rid} [{cls}]: CSV expects {missing}; FU22 excludes no_lookup_needed"
            )
            continue
        from scripts.eval.part_g_arm.state.guard_allowed import _bundle_for_class

        class_only: set[str] = set()
        rich = _rich_state_for_diagnosis()
        for sub in subs:
            class_only |= _bundle_for_class(
                sub["class"],
                action=sub.get("action"),
                numeric_or_explain=sub.get("numeric_or_explain", False),
                state=rich,
            )
        if set(missing) <= class_only:
            state_removed.append(f"{rid} [{cls}]: state removed {missing}")
        else:
            failures.append(f"{rid} [{cls}]: missing {missing}; allowed={sorted(allowed)}")
    print("A1 failures:", failures)
    print("A1 state-removed (not class):", state_removed)
    print("A1 CSV-vs-mapping (mapping wins):", csv_vs_mapping)
    print("A1 out-of-scope tools skipped:", out_of_scope)
    assert failures == []


def _rich_state_for_diagnosis() -> dict[str, Any]:
    """Fully locked anchor + blank slot + pending with matching fingerprint."""
    from recommender.state import Attr, Slot

    locked = Slot(
        role=Attr("sweeper", True),
        species=Attr("Pelipper", True),
        ability=Attr("Drizzle", True),
        item=Attr("Damp Rock", True),
        moveset=Attr(["Hurricane", "Weather Ball", "Protect", "Tailwind"], True),
        spread=Attr({"hp": 252, "atk": 0, "def": 4, "spa": 252, "spd": 0, "spe": 0}, True),
        nature=Attr("Modest", True),
    )
    blank = Slot()
    state: dict[str, Any] = empty_team()
    state["team_draft"] = [locked, blank, Slot(), Slot(), Slot(), Slot()]
    state["pending_presentation"] = {
        "kind": "candidate_selection",
        "slot_index": 1,
        "options": [{"species": "Toxapex"}, {"species": "Corviknight"}],
    }
    stamp_pending_team_fingerprint(state)
    return state


def _locked_anchor_team() -> dict[str, Any]:
    return _rich_state_for_diagnosis()


# --- A2: one unit test per §4 availability rule ---


@pytest.mark.parametrize("row_id", ["MS1", "MS8", "MT2"])
def test_a1_ms_rows_pass_after_in_turn_set_slot(row_id: str):
    """FU23 §2: empty fixture unbinds lock_fields; post-set_slot state binds it."""
    row = next(
        r
        for r in csv.DictReader(REV3.open(newline="", encoding="utf-8"))
        if r["row_id"] == row_id and r["turn"] == "1"
    )
    subs = _oracle_sub_requests(row)
    empty = empty_team()
    before = allowed_tools(subs, empty)
    assert "lock_fields" not in before
    # Simulate draft written by set_slot earlier in the turn (slot 2 for MS1).
    after_state = empty_team()
    after_state["team_draft"][1].species = Attr("Garchomp", False)
    after = allowed_tools(subs, after_state)
    needed = set()
    for col in ("expected_tools_ordered", "optional_tools", "alternative_path"):
        needed.update(_split_tools(row.get(col) or ""))
    needed &= _MAPPED_TOOLS | {t for t in needed if t.startswith("reject")}
    missing = sorted(needed - after)
    assert "lock_fields" in after
    assert missing == [], f"{row_id}: still missing {missing}"


def test_set_slot_bound_on_build_not_lock_fields():
    st = empty_team()
    # Put a draft value so lock_fields *could* bind if action were lock.
    st["team_draft"][0].species = Attr("Garchomp", False)
    allowed = allowed_tools(
        [{"class": "WRITE", "action": "set_slot", "numeric_or_explain": False}],
        st,
    )
    assert "set_slot" in allowed
    assert "lock_fields" not in allowed


def test_lock_fields_requires_valued_attribute():
    empty = empty_team()
    assert not has_valued_attribute(empty)
    assert "lock_fields" not in allowed_tools(
        [{"class": "WRITE", "action": "lock_fields"}], empty
    )
    valued = empty_team()
    valued["team_draft"][0].species = Attr("Garchomp", False)
    assert "lock_fields" in allowed_tools(
        [{"class": "WRITE", "action": "lock_fields"}], valued
    )


def test_unlock_slot_not_bound_on_lock_request():
    st = empty_team()
    st["team_draft"][0].species = Attr("Garchomp", False)
    allowed = allowed_tools([{"class": "WRITE", "action": "lock_fields"}], st)
    assert "unlock_slot" not in allowed
    assert "lock_fields" in allowed


def test_show_candidates_needs_locked_anchor_and_blank():
    empty = empty_team()
    assert "show_candidates" not in allowed_tools([{"class": "LOOKUP"}], empty)
    rich = _locked_anchor_team()
    assert has_fully_locked_anchor(rich)
    assert first_blank_slot_index(rich) == 1
    assert "show_candidates" in allowed_tools([{"class": "LOOKUP"}], rich)
    # Drafted (not blank) open slot alone does not open show_candidates without blank.
    drafted_only = empty_team()
    drafted_only["team_draft"][0] = Slot(
        species=Attr("Pelipper", False),
    )
    assert first_blank_slot_index(drafted_only) == 1  # slot 0 drafted, slot 1 blank
    assert not has_fully_locked_anchor(drafted_only)
    assert "show_candidates" not in allowed_tools([{"class": "LOOKUP"}], drafted_only)


def test_select_option_ol10a_stale_and_fresh():
    rich = _locked_anchor_team()
    assert pending_fingerprint_matches(rich)
    assert "select_option" in allowed_tools(
        [{"class": "WRITE", "action": "select_option"}], rich
    )
    # Stale: mutate team after stamp.
    rich["team_draft"][0].item = Attr("Life Orb", True)
    assert not pending_fingerprint_matches(rich)
    assert "select_option" not in allowed_tools(
        [{"class": "WRITE", "action": "select_option"}], rich
    )


def test_reject_tools_need_pending():
    empty = empty_team()
    assert "reject_all" not in allowed_tools(
        [{"class": "WRITE", "action": "reject"}], empty
    )
    rich = _locked_anchor_team()
    allowed = allowed_tools([{"class": "WRITE", "action": "reject"}], rich)
    assert {"reject_pending", "reject_option", "reject_all"} <= allowed


def test_commit_and_reset_only_on_explicit_action():
    st = empty_team()
    assert "commit_slot" not in allowed_tools(
        [{"class": "WRITE", "action": "set_slot"}], st
    )
    assert "reset_team" not in allowed_tools(
        [{"class": "HYPOTHETICAL"}], st
    )
    assert "reset_team" in allowed_tools(
        [{"class": "WRITE", "action": "reset"}], st
    )
    assert "commit_slot" in allowed_tools(
        [{"class": "WRITE", "action": "commit"}], st
    )


def test_uncertain_falls_to_ask_with_no_lookup_needed():
    allowed = allowed_tools(
        [{"class": "WRITE", "action": "set_slot", "uncertain": True}],
        empty_team(),
    )
    assert "no_lookup_needed" in allowed
    assert "read_team" in allowed
    assert "set_slot" not in allowed


def test_ask_and_refuse_bind_no_lookup_needed_read_state_does_not():
    """FU22: ASK / READ_ONLY_REFUSE = READ + no_lookup_needed; READ_STATE = READ only."""
    for cls in ("ASK", "READ_ONLY_REFUSE"):
        allowed = allowed_tools([{"class": cls}], empty_team())
        assert "no_lookup_needed" in allowed
        assert "get_typing" not in allowed
        assert "read_team" in allowed
    read_state = allowed_tools([{"class": "READ_STATE"}], empty_team())
    assert "no_lookup_needed" not in read_state
    assert "read_team" in read_state


def test_constraint_action_binds_set_constraint_active_only_when_live():
    """FU22 §7: bind by name; skip when no live schema."""
    st = empty_team()
    live_without = frozenset(
        {
            "add_constraint",
            "restore_constraint",
            "read_team",
            "read_constraints",
            "get_typing",
            "get_abilities",
            "check_species_ability",
            "check_species_legal",
            "check_item_legal",
            "get_move_static",
            "check_learnset",
            "find_species",
            "get_usage_items",
            "get_usage_teammates",
            "get_usage_spreads",
            "get_usage_stats",
            "get_common_speeds",
            "get_meta_threats",
            "read_pending",
            "read_archetype",
            "read_rejected",
        }
    )
    allowed = allowed_tools(
        [{"class": "WRITE", "action": "constraint"}],
        st,
        live=live_without,
    )
    assert "add_constraint" in allowed
    assert "restore_constraint" in allowed
    assert "set_constraint_active" not in allowed
    allowed2 = allowed_tools(
        [{"class": "WRITE", "action": "constraint"}],
        st,
        live=live_without | {"set_constraint_active"},
    )
    assert "set_constraint_active" in allowed2


def test_write_numeric_binds_numbers_not_no_lookup_needed():
    st = empty_team()
    without = allowed_tools(
        [{"class": "WRITE", "action": "set_slot", "numeric_or_explain": False}], st
    )
    with_n = allowed_tools(
        [{"class": "WRITE", "action": "set_slot", "numeric_or_explain": True}], st
    )
    assert "calc_damage" not in without
    assert "calc_damage" in with_n
    assert "describe" in with_n
    assert "no_lookup_needed" not in with_n
