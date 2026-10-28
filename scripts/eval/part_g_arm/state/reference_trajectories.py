"""Part 3 — scripted reference trajectories for mechanical covered rows (no model).

Each trajectory is the tool calls a correct arm would make. CAPABILITY_GAP rows
name the missing tool. Re-run after Part 4 builds to close gaps.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable

from scripts.eval.part_g_arm.state.class_scorer import score_turn
from scripts.eval.part_g_arm.state.errata_read import expected_turns
from scripts.eval.part_g_arm.state.request_set_rows import (
    load_covered_ids,
    load_request_rows,
    resolve_start_state,
)
from scripts.eval.part_g_arm.state.tools import (
    commit_slot,
    confirm_build,
    draft_signature,
    lock_slot,
    mechanical_class,
    read_pending,
    read_rejected,
    read_team,
    reject_all,
    reject_option,
    reject_pending,
    reset_team_state,
    select_option,
    steering_signature,
    unlock_slot,
    check_hypothetical,
)

HERE = Path(__file__).resolve().parent
DISCOVERY = HERE / "b1_discovery.json"

# (tool_name, kwargs) — kwargs use user-facing 1-based slots where applicable.
Call = tuple[str, dict[str, Any]]
Gap = dict[str, str]  # {"gap": "...", "needs": "tool X"}


def _mech_ids() -> list[str]:
    doc = json.loads(DISCOVERY.read_text(encoding="utf-8"))
    covered = load_covered_ids()
    out = []
    for row in doc["covered"]:
        if row["row"] in covered and row["bucket"] == "scorable-mechanical":
            out.append(row["row"])
    return out


def _hand_ids() -> list[str]:
    doc = json.loads(DISCOVERY.read_text(encoding="utf-8"))
    covered = load_covered_ids()
    out = []
    for row in doc["covered"]:
        if row["row"] in covered and row["bucket"] == "hand audit":
            out.append(row["row"])
        if row["row"] in covered and row["row"] == "MC1":
            out.append(row["row"])
    return out


def _snap(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "slots": draft_signature(state),
        "steering": steering_signature(state),
    }


def _dispatch(state: dict[str, Any], name: str, kwargs: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run one state/hyp tool. Lookups go through ArmTools when needed."""
    if name == "lock_slot":
        return lock_slot(state, kwargs["slot"], kwargs["species"])
    if name == "unlock_slot":
        return unlock_slot(state, kwargs["slot"])
    if name == "reset_team":
        return reset_team_state(state)
    if name == "commit_slot":
        return commit_slot(state)
    if name == "confirm_build":
        return confirm_build(state)
    if name == "select_option":
        return select_option(state, kwargs["option"])
    if name == "reject_option":
        return reject_option(state, kwargs["option"])
    if name == "reject_pending":
        return reject_pending(state)
    if name == "reject_all":
        return reject_all(state)
    if name == "read_team":
        return state, read_team(state)
    if name == "read_pending":
        return state, read_pending(state)
    if name == "read_rejected":
        return state, read_rejected(state)
    if name == "check_hypothetical":
        return state, check_hypothetical(state, kwargs["placements"])
    if name == "no_lookup_needed":
        from recommender.arm_tools import ArmTools
        from recommender.regulation_registry import active_regulation

        arm = ArmTools(regulation=active_regulation(), allow_live=False)
        return state, arm.no_lookup_needed(
            kwargs.get("reason", "no tool needed for this turn"),
            kwargs.get("category", "other"),
        )
    if name in {
        "get_typing",
        "get_abilities",
        "check_species_legal",
        "check_item_legal",
        "check_species_ability",
        "get_move_static",
    }:
        from recommender.arm_tools import ArmTools
        from recommender.regulation_registry import active_regulation

        arm = ArmTools(regulation=active_regulation(), allow_live=False)
        fn = getattr(arm, name)
        return state, fn(**kwargs)
    raise KeyError(f"unknown tool {name}")


def run_calls(
    state: dict[str, Any], calls: list[Call]
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    before = state
    after = copy.deepcopy(state)
    tool_calls: list[dict[str, Any]] = []
    for name, kwargs in calls:
        after, result = _dispatch(after, name, kwargs)
        tool_calls.append({"name": name, "arguments": kwargs, "result": result})
    cls = mechanical_class(before, after, tool_calls)
    return after, tool_calls, cls


# --- trajectory definitions -------------------------------------------------

def _traj_lock(slot: int, species: str) -> list[Call]:
    return [("lock_slot", {"slot": slot, "species": species})]


def _traj_refuse_lock(slot: int, species: str) -> list[Call]:
    return [("lock_slot", {"slot": slot, "species": species})]


def _ol_select(option: int) -> list[Call]:
    return [("select_option", {"option": option})]


def trajectories() -> dict[str, list[Call] | Gap]:
    """Mechanical covered rows → calls or capability gap."""
    return {
        # Fail-closed / ask / no-mutation: no write
        "H13": [("no_lookup_needed", {"reason": "no per-team win-rate data", "category": "unavailable"})],
        "H14": [("no_lookup_needed", {"reason": "out of format scope", "category": "unavailable"})],
        "H16": [("no_lookup_needed", {"reason": "no prior pick history", "category": "unavailable"})],
        "HC1": [("no_lookup_needed", {"reason": "unsatisfiable Water∧Fire", "category": "unavailable"})],
        "HC2": [("no_lookup_needed", {"reason": "ask which request to honor", "category": "other"})],
        "HP3": _traj_refuse_lock(1, "Koraidon"),
        "MU1": [
            (
                "check_hypothetical",
                {
                    "placements": [
                        {"species": "Garchomp", "item": "Choice Scarf"},
                        {"species": "Jolteon", "item": "Choice Scarf"},
                    ]
                },
            )
        ],
        "MU2": [("check_hypothetical", {"placements": [{"species": "Pelipper"}]})],
        "MU3": [("check_hypothetical", {"placements": [{"species": "Garchomp"}]})],
        "MU4": [("read_team", {})],
        "MU5": [("check_hypothetical", {"placements": [
            {"species": "Garchomp", "item": "Life Orb"},
            {"species": "Jolteon", "item": "Life Orb"},
        ]})],
        "MU6": [("read_team", {})],  # must NOT call reset_team
        "MU7": [("read_pending", {})],  # must NOT commit
        "MU8": [("read_team", {})],  # must NOT change archetype
        "MW1": [("read_pending", {})],
        "MW2": [("read_team", {})],
        "MW3": [("read_team", {})],
        "MW4": [("read_pending", {})],
        # Mutations
        "MS1": _traj_lock(2, "Garchomp"),
        "MS2": [("unlock_slot", {"slot": 1})],
        "MS3": [("reset_team", {})],
        "MS4": [("commit_slot", {})],
        "MS6": {"gap": "cannot record constraint", "needs": "add_constraint (4b)"},
        "MS7": [("reject_option", {"option": 2})],
        "MS8": _traj_lock(1, "Pelipper"),
        # Refusals
        "MR1": _traj_refuse_lock(1, "Flutter Mane"),
        "MR2": {
            "gap": "cannot lock item Choice Specs",
            "needs": "edit_slot_field (4a)",
        },
        "MR3": _traj_refuse_lock(2, "Incineroar"),  # after one Incineroar locked
        "MR4": {
            "gap": "cannot lock Choice Scarf on two slots",
            "needs": "edit_slot_field (4a)",
        },
        "MR5": _traj_refuse_lock(2, "Garchomp"),  # occupied — start must have slot2 locked
        "MR6": [("unlock_slot", {"slot": 2})],
        "MR7": [("commit_slot", {})],
        "MR8": _traj_refuse_lock(1, "Koraidon"),
        # OL — FBC fixtures ship pending options without provisional_slot; select_option refuses.
        "OL1": {
            "gap": "OL FBC fixture has options but no provisional_slot; select_option cannot bind",
            "needs": "FBC provisional wire in pending loader (or product apply path)",
        },
        "OL2a": {
            "gap": "OL FBC fixture lacks provisional_slot; also CLI maps bare '2' to id suffix not ordinal",
            "needs": "FBC provisional wire + suffix/label select",
        },
        "OL2b": [("select_option", {"option": 2})],  # Incineroar
        "OL3": {
            "gap": "label bind; FBC lacks provisional_slot",
            "needs": "label-select + FBC provisional wire",
        },
        "OL4": [("read_pending", {})],  # ASK — do not select
        "OL5": [("select_option", {"option": 1})],
        "OL6": [("read_pending", {})],  # ASK
        "OL8": [("reject_all", {})],  # neither → reject every option, no lock
        "OL9": [("read_pending", {})],  # ASK
    }


def _prepare_start(rid: str, state: dict[str, Any]) -> dict[str, Any]:
    """Fill starts that the request-set labels but loader leaves empty."""
    from scripts.eval.part_g_arm.state.fixtures import empty_team
    from scripts.eval.part_g_arm.state.pending import build_fully_locked_slot, _lock_internal

    if rid == "MS2":
        # slot1 locked
        return build_fully_locked_slot("Garchomp", user_slot=1)
    if rid == "MS3":
        st = build_fully_locked_slot("Garchomp", user_slot=1)
        return {**st, **lock_slot(st, 2, "Pelipper")[0]} if False else _two_locked()
    if rid == "MR3":
        return build_fully_locked_slot("Incineroar", user_slot=1)
    if rid == "MR5":
        return build_fully_locked_slot("Pelipper", user_slot=2)
    if rid == "MU6":
        return build_fully_locked_slot("Garchomp", user_slot=1)
    if rid == "MW2":
        return build_fully_locked_slot("Garchomp", user_slot=1)
    return state


def _two_locked() -> dict[str, Any]:
    from scripts.eval.part_g_arm.state.pending import build_fully_locked_slot

    st = build_fully_locked_slot("Garchomp", user_slot=1)
    st2, _ = lock_slot(st, 2, "Pelipper")
    # Pelipper may not be fully locked (species only) — enough for reset
    return st2


def run_all_mechanical() -> dict[str, Any]:
    rows_by_id = {r["id"]: r for r in load_request_rows()}
    trajs = trajectories()
    results: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []

    for rid in _mech_ids():
        row = rows_by_id[rid]
        key_class = expected_turns(rid, row.get("class") or "")[0]

        spec = trajs.get(rid)
        if spec is None:
            gaps.append({"row": rid, "needs": "trajectory not defined", "gap": "missing traj"})
            results.append({
                "row": rid,
                "trajectory": None,
                "observed_class": None,
                "key_class": key_class,
                "pass": False,
                "capability_gap": True,
                "needs": "trajectory not defined",
            })
            continue
        if isinstance(spec, dict) and "gap" in spec:
            gaps.append({"row": rid, **spec})
            results.append({
                "row": rid,
                "trajectory": None,
                "observed_class": None,
                "key_class": key_class,
                "pass": False,
                "capability_gap": True,
                "needs": spec["needs"],
                "gap": spec["gap"],
            })
            continue

        state, meta = resolve_start_state(row)
        if state is None:
            results.append({
                "row": rid,
                "trajectory": [f"{n}({a})" for n, a in spec],
                "observed_class": None,
                "key_class": key_class,
                "pass": False,
                "error": meta.get("error"),
            })
            continue
        state = _prepare_start(rid, state)
        before_snap = _snap(state)
        try:
            after, tool_calls, obs = run_calls(state, spec)
        except Exception as exc:  # noqa: BLE001
            results.append({
                "row": rid,
                "trajectory": [f"{n}({a})" for n, a in spec],
                "observed_class": None,
                "key_class": key_class,
                "pass": False,
                "error": f"{type(exc).__name__}: {exc}",
            })
            continue
        after_snap = _snap(after)
        turn = {
            "mechanical_class": obs,
            "state_before": before_snap,
            "state_after": after_snap,
            "tool_calls": [{"name": c["name"]} for c in tool_calls],
        }
        scored = score_turn(observed_mech=obs, expected_key_class=key_class, turn=turn)
        ok = bool(scored["match"] and scored["state_expectation_met"])
        results.append({
            "row": rid,
            "trajectory": [f"{c['name']}({c['arguments']})" for c in tool_calls],
            "observed_class": obs,
            "key_class": key_class,
            "pass": ok,
            "score": scored,
        })

    return {
        "mechanical_n": len(results),
        "passed": sum(1 for r in results if r.get("pass")),
        "failed": sum(1 for r in results if r.get("pass") is False and not r.get("capability_gap")),
        "capability_gaps": gaps,
        "rows": results,
    }


def hand_audit_tool_map() -> list[dict[str, Any]]:
    """One line per hand-audit covered row: which tools supply rubric facts."""
    # Compact map from request-set claim types — readiness only, no model.
    MAP: dict[str, str] = {
        "H1": "get_typing → Poison/Water",
        "H2": "check_species_ability / get_abilities → Unaware",
        "H3": "check_item_legal → Life Orb on Dragonite",
        "H4": "get_speed ×2 → Spe compare",
        "H5": "calc_damage under stated sides (ASSUME-STATE)",
        "H6": "get_usage_teammates (ingame) → partner set",
        "H7": "get_move_static → category + base_power",
        "H8": "check_hypothetical Item Clause / check_item_legal",
        "Q9": "check_species_legal + Species Clause via lock refuse or hyp",
        "Q10": "unlock_slot on empty → refuse message / read_team",
        "H11": "GAP: no legal-learners-by-type+move search tool (get_typing/get_move_static insufficient for set)",
        "H15": "usage joint via get_usage_* + get_speed (ASSUME-STATE)",
        "H18b": "fixture + solve_spread / usage; HO constraint judgment-only in fixture",
        "H19": "GAP: no Trick-Room learnset scan tool (check_learnset 4e helps per-species only)",
        "H20": "GAP: no monotype candidate producer without show_candidates+type filter",
        "MT1": "GAP until 4b: constraints not readable; t3 read-back needs read_constraints",
        "MT2": "stale pin — excluded",
        "MT3": "seed+history; t2 suggest needs show_candidates(4c); t3 get_abilities",
        "MT5": "GAP: no change_archetype / read_archetype (4f)",
        "MT6": "GAP: add_constraint (4b) for Water-only resolve",
        "HF1": "get_typing",
        "HF2": "get_abilities / check_species_ability",
        "HD1": "get_typing + history",
        "HU1": "GAP: bulk formula scan over legal Fire types — no set enumeration tool",
        "HU2": "get_speed + get_usage_teammates/threats (ingame)",
        "HU3": "GAP: show_candidates(4c) for Fire options",
        "HU4": "get_speed + usage (ASSUME-STATE)",
        "HN1": "get_abilities",
        "HN2": "get_speed ×2",
        "HN3": "get_usage_items (ingame)",
        "HN4": "get_move_static",
        "HP1": "check_species_legal / check_item_legal + calc_damage labeled hyp",
        "HP2": "check_species_legal + check_item_legal (question, no lock)",
        "MRB1": "read_team",
        "HU2b": "get_speed + usage ASSUME-STATE",
        "HN2b": "get_speed ASSUME-STATE grid",
        "HN2c": "get_speed + locked Spe from read_team",
        "HN2d": "get_speed (+1 stage claim narrative; tool gives bare Spe)",
        "IS1": "get_speed / solve_spread outspeed",
        "IS2": "solve_spread / get_speed + fixture",
        "IS3": "get_speed + get_usage_items (no Scarf in list)",
        "IS4": "get_speed unreachable",
        "DM1": "calc_damage ASSUME-STATE",
        "DM2": "calc_damage grid + locked Incineroar",
        "DM3": "calc_damage doubles",
        "DM4": "calc_damage min Atk search",
        "DM6": "calc_damage Mega Gallade",
        "DM7": "calc_damage Annihilape Defiant",
        "MV1": "GAP: get_move_static omits priority (4h)",
        "MV2": "get_move_static pp",
        "MV3": "get_move_static target; accuracy from pin/data",
        "IC1": "get_usage_items + Item Clause; t2 GAP edit_slot_field(4a) for Sitrus",
        "TB1": "GAP: type-boost consequence needs edit/build path + TYPE_BOOST data",
        "MC1": "ASK form or ASSUME-STATE Y — get_usage_*; no lock required for ASK",
        "H6_dup": "",
    }
    out = []
    for rid in _hand_ids():
        line = MAP.get(rid, "unmapped — inspect request-set claim types")
        gap = "GAP" in line or "gap" in line.lower()
        out.append({"row": rid, "tools": line, "fact_unreachable": gap})
    return out


def main() -> None:
    mech = run_all_mechanical()
    hand = hand_audit_tool_map()
    out = {
        "mechanical": mech,
        "hand_audit": hand,
        "needs_tool": mech["capability_gaps"],
        "hand_unreachable": [h for h in hand if h["fact_unreachable"]],
    }
    path = HERE / "part3_reference_trajectories.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(
        f"mechanical pass={mech['passed']}/{mech['mechanical_n']} "
        f"gaps={len(mech['capability_gaps'])} "
        f"hand_unreachable={len(out['hand_unreachable'])} → {path}"
    )


if __name__ == "__main__":
    main()
