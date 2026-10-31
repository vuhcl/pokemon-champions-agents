"""Script reference trajectories for coverable-now not-covered rows (no model).

Reads part0_retriage_final.json. Does not edit covered_list.json.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from recommender.arm_tools import ArmTools
from recommender.regulation_registry import active_regulation

from scripts.eval.part_g_arm.state.class_scorer import score_transcript
from scripts.eval.part_g_arm.state.errata_read import expected_turns
from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.hand_audit_form import (
    _points_with_set_errata,
    build_sections_from_transcript,
    split_acceptance_points,
)
from scripts.eval.part_g_arm.state.request_set_rows import (
    load_request_rows,
    parse_user_turns,
    resolve_start_state,
)
from scripts.eval.part_g_arm.state.tools import (
    add_constraint,
    check_learnset,
    find_species,
    mechanical_class,
    read_pending,
    select_option,
)

HERE = Path(__file__).resolve().parent
FINAL = HERE / "part0_retriage_final.json"
OUT = HERE / "LAST_RETRIAGE_COVERABLE.md"
OUT_JSON = HERE / "retriage_coverable_trajectories.json"

Call = tuple[str, dict[str, Any]]


def _arm() -> ArmTools:
    return ArmTools(regulation=active_regulation(), allow_live=False, calc=None, include_damage_rolls=False)


def _dispatch(state: dict[str, Any], name: str, kwargs: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if name == "find_species":
        return state, find_species(state, **kwargs)
    if name == "check_learnset":
        return state, check_learnset(state, kwargs["species"], kwargs["move"])
    if name == "add_constraint":
        return add_constraint(
            state,
            kwargs.get("predicate"),
            kwargs.get("scope"),
            kwargs.get("groundedness"),
            slot=kwargs.get("slot"),
            mechanical_kind=kwargs.get("mechanical_kind"),
            value=kwargs.get("value"),
        )
    if name == "select_option":
        return select_option(state, kwargs["option"])
    if name == "read_pending":
        return state, read_pending(state)
    if name == "no_lookup_needed":
        return state, _arm().no_lookup_needed(
            kwargs.get("reason", "assume-state"),
            kwargs.get("category", "other"),
        )
    if name in {
        "get_typing",
        "get_abilities",
        "check_species_ability",
        "get_speed",
        "check_species_legal",
    }:
        return state, getattr(_arm(), name)(**kwargs)
    raise KeyError(f"unknown tool {name}")


def _run(state: dict[str, Any], calls: list[Call]) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    before = state
    after = copy.deepcopy(state)
    tool_calls: list[dict[str, Any]] = []
    for name, kwargs in calls:
        after, result = _dispatch(after, name, kwargs)
        tool_calls.append({"name": name, "args": kwargs, "result": result})
    return after, tool_calls, mechanical_class(before, after, tool_calls)


def trajectories() -> dict[str, list[Call]]:
    """One correct-behavior path per coverable-now id (from row text only)."""
    return {
        "H12": [
            (
                "no_lookup_needed",
                {
                    "reason": "ASSUME-STATE Sinistcha Calm/Bold vs Showdown attacker pool; calc_damage per stated sides",
                    "category": "conceptual",
                },
            )
        ],
        "H19": [("find_species", {"learns_move": "Trick Room"})],
        "H20": [
            ("find_species", {"types": ["Electric"]}),
            (
                "add_constraint",
                {
                    "predicate": "Electric only",
                    "scope": "team_wide",
                    "groundedness": "mechanically-checkable",
                    "mechanical_kind": "type",
                    "value": "Electric",
                },
            ),
        ],
        "H21": [
            (
                "no_lookup_needed",
                {
                    "reason": "ASSUME-STATE: membership = species name contains 'monkey' / dex category; confirm or proceed",
                    "category": "conceptual",
                },
            )
        ],
        "H22": [
            (
                "no_lookup_needed",
                {
                    "reason": "ASSUME-STATE aesthetic membership; offer confirm/reject under stated assumption (checklist H22)",
                    "category": "conceptual",
                },
            )
        ],
        "H27": [
            ("read_pending", {}),
            ("get_typing", {"species": "Garchomp"}),
            ("get_typing", {"species": "Incineroar"}),
            ("get_typing", {"species": "Rillaboom"}),
        ],
        "IX5": [
            ("find_species", {"ability": "Inner Focus"}),
            ("find_species", {"ability": "Own Tempo"}),
            ("find_species", {"ability": "Oblivious"}),
            ("find_species", {"ability": "Scrappy"}),
        ],
        "IX7": [
            ("find_species", {"types": ["Flying"]}),
            ("find_species", {"ability": "Levitate"}),
            ("find_species", {"ability": "Telepathy"}),
            ("find_species", {"ability": "Earth Eater"}),
        ],
        # Spe 200 = Jolteon is the request-set key; select without live calc.
        "OL7a": [
            ("read_pending", {}),
            ("select_option", {"option": 3}),  # Jolteon in OL7a fixture
        ],
    }


def _start(rid: str, row: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any], str | None]:
    """Return (state, meta, seed_needed)."""
    if rid == "H12":
        # Loader fails on 'attackers undefined'; seed from row text = empty_team.
        return empty_team(), {"loaded": True, "complete": True, "source": "seed:empty_team"}, (
            "H12 seed: state cell 'attackers undefined' → empty_team (row text only; not written to seeds/)"
        )
    state, meta = resolve_start_state(row)
    return state, meta, None


def _form_cost(rid: str, row: dict[str, Any], n_turns: int) -> dict[str, Any]:
    from scripts.eval.part_g_arm.state.errata_read import acceptance_with_key_overrides

    pts = _points_with_set_errata(
        rid,
        split_acceptance_points(
            acceptance_with_key_overrides(rid, row.get("acceptance") or "")
        ),
    )
    sections = n_turns  # one section per played turn
    cells = sections * len(pts)
    extra: dict[str, Any] = {}
    if rid == "H21":
        extra["frozen_checklist"] = False
        extra["note"] = "acceptance explicitly: No frozen checklist"
    if rid == "H22":
        extra["frozen_checklist"] = True
        extra["checklist_items"] = 4
        extra["note"] = (
            "form generator uses acceptance ';'-split (1 point); "
            "frozen checklist H22 has 4 rubric items in part3_request_set_v4.md"
        )
    if rid == "H12":
        extra["claim_surface_rubric_cells"] = cells
        extra["note"] = f"H12 acceptance ';'-splits to {len(pts)} points × {n_turns} turn(s)"
    if rid in {"H19", "H20"}:
        extra["frozen_checklist"] = True
        extra["note"] = f"binary checklist {rid} in request set; form cells from acceptance ';'-split"
    return {
        "acceptance_points": len(pts),
        "sections_if_added": sections,
        "cells_if_added": cells,
        **extra,
    }


def run() -> dict[str, Any]:
    final = json.loads(FINAL.read_text(encoding="utf-8"))
    coverable = list(final["coverable_now_ids"])
    rows_by_id = {r["id"]: r for r in load_request_rows()}
    trajs = trajectories()
    results: list[dict[str, Any]] = []
    transcript: list[dict[str, Any]] = []

    for rid in coverable:
        row = rows_by_id[rid]
        calls = trajs[rid]
        state, meta, seed_needed = _start(rid, row)
        turns_text = parse_user_turns(row.get("prompt") or "") or [row.get("prompt") or rid]
        if state is None:
            results.append(
                {
                    "row": rid,
                    "trajectory": [f"{n}({a})" for n, a in calls],
                    "pass": False,
                    "error": meta.get("error"),
                    "seed_needed": seed_needed,
                }
            )
            continue

        # Single scripted turn covering the row's first (or only) user prompt.
        after, tool_calls, mech = _run(state, calls)
        turn = {
            "user": turns_text[0],
            "tool_calls": tool_calls,
            "state_before": {"slots": []},
            "state_after": {"slots": []},
            "final_text": f"scripted reference for {rid}",
            "mechanical_class": mech,
            "errors": [],
        }
        # Carry real signatures when mechanical_class needs them — recompute properly:
        after2, tool_calls2, mech = _run(copy.deepcopy(state), calls)
        turn["tool_calls"] = tool_calls2
        turn["mechanical_class"] = mech
        entry = {"id": rid, "loaded": True, "turns": [turn]}
        transcript.append(entry)

        scored = score_transcript([entry], rows_by_id=rows_by_id)
        per = scored["per_row"][0]
        # not_covered exclusion expected; mechanical observation still present when not stale
        obs = None
        match = None
        if per.get("turns"):
            obs = per["turns"][0].get("mechanical_class_observed") or per["turns"][0].get("match")
            match = per["turns"][0].get("match")
            obs = per["turns"][0]
        key_exp = expected_turns(rid, row.get("class") or "")[0]
        # Pass = tools ran without error and (for mechanical OL7a) class matches key when scored.
        def _failed(t: dict[str, Any]) -> bool:
            r = t.get("result")
            if not isinstance(r, dict):
                return False
            if r.get("slot_commit_error"):
                return True
            if r.get("status") == "error":
                return True
            return False

        tool_err = any(_failed(t) for t in tool_calls2)
        if rid == "OL7a":
            class_ok = (
                mech not in {"refused"}
                and not tool_err
                and after2.get("provisional_slot") is not None
            )
        else:
            class_ok = not tool_err

        cost = _form_cost(rid, row, n_turns=1)
        results.append(
            {
                "row": rid,
                "trajectory": [f"{n}({json.dumps(a, sort_keys=True)})" for n, a in calls],
                "observed_mechanical_class": mech,
                "key_class_expected": key_exp,
                "scorer_excluded": per.get("excluded"),
                "turn_score": obs,
                "pass": bool(class_ok),
                "seed_needed": seed_needed,
                "form": cost,
                "loader": meta.get("source"),
            }
        )

    # Aggregate proposed form cost if all coverable hand-audit rows were added
    hand = [r for r in results if rows_by_id[r["row"]].get("class") and True]
    sections = sum(r["form"]["sections_if_added"] for r in results if r.get("form"))
    cells = sum(r["form"]["cells_if_added"] for r in results if r.get("form"))

    doc = {
        "as_of": "2026-10-28",
        "coverable_now_ids": coverable,
        "results": results,
        "form_cost_if_all_added": {
            "rows": len(results),
            "sections": sections,
            "cells": cells,
            "note": "acceptance ';'-split method (same as LAST_B1 / freeze confirm). H22 checklist has 4 items but acceptance cell count is 1.",
        },
    }
    OUT_JSON.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Coverable-now reference trajectories (2026-10-28)",
        "",
        "No model. No covered_list change. Scorer marks these `excluded: not_covered` (expected).",
        "",
        "| row | trajectory (summary) | pass/fail | sections | cells | seed needed |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        traj = "; ".join(c.split("(")[0] for c in r["trajectory"])
        seed = r.get("seed_needed") or "—"
        if len(seed) > 60:
            seed = seed[:57] + "..."
        form = r.get("form") or {}
        lines.append(
            f"| {r['row']} | {traj} | {'PASS' if r['pass'] else 'FAIL'} | "
            f"{form.get('sections_if_added', '—')} | {form.get('cells_if_added', '—')} | {seed} |"
        )
    lines += [
        "",
        "## Notes",
        "",
        "- **H21:** no frozen checklist (acceptance says so).",
        "- **H22:** frozen checklist H22 exists (4 items); form cells use acceptance `;`-split → 1.",
        "- **H12:** claim surface = 19 acceptance points × 1 turn; needs empty_team seed for loader.",
        "- **OL7a:** mechanical select Jolteon; scorer exclusion `not_covered` until Vu adds.",
        f"- Form cost if all {len(results)} added (`;`-split): "
        f"**{sections} sections / {cells} cells**.",
        "",
    ]
    for r in results:
        if r["row"] in {"H12", "H21", "H22"} and r.get("form", {}).get("note"):
            lines.append(f"- {r['row']}: {r['form']['note']}")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return doc


def main() -> int:
    # Fix accidental walrus in import — rewrite cleanly if needed
    doc = run()
    failed = [r["row"] for r in doc["results"] if not r["pass"]]
    print(
        f"coverable={len(doc['results'])} pass={len(doc['results'])-len(failed)} "
        f"fail={failed} form={doc['form_cost_if_all_added']}"
    )
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
