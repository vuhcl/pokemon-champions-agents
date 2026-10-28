"""Multi-turn harness for the stateful arm. This file owns the model loop.

It does not edit ArmLoop or TOOL_SPECS. Lookups go through ArmTools.call.
Transcripts and the run record are written to the directory passed on the CLI,
which is outside the repo.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

from recommender.arm_tools import dumps, to_jsonable
from recommender.calc_client import CalcClient

from scripts.eval.part_g_arm.config import ArmConfig
from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.pending import build_cs_pending, build_fbc_pending, build_fully_locked_slot
from scripts.eval.part_g_arm.state.tools import (
    STATE_TOOL_NAMES,
    add_constraint,
    check_hypothetical,
    combined_specs,
    commit_slot,
    confirm_build,
    edit_slot_field,
    lock_slot,
    mechanical_class,
    read_constraints,
    read_pending,
    read_rejected,
    read_team,
    reject_all,
    reject_option,
    reject_pending,
    reset_team_state,
    restore_constraint_tool,
    select_option,
    show_candidates,
    solve_spread_tool,
    steering_signature,
    unlock_slot,
)

HERE = Path(__file__).resolve().parent
NON_INHERITANCE = "This configuration does not inherit the rev3 PASS."
# Standing disclosures for every stateful-arm run record (not a scoring claim).
RUN_PARAMS = {
    "primitive_tools": (
        "State tools call apply_lock / refine / commit / record_rejection nodes "
        "directly; they do not wrap the CLI binder path."
    ),
    "partial_cs_stale_gate": (
        "select_option refuses a fully locked target slot and validate_team_value "
        "failures; it does not detect a candidate list built for an earlier team "
        "(D8 / OL10a open)."
    ),
    "select_option_source_default": (
        "select_option uses raw.get('source') or 'threat'. classify_input reads "
        "option['source'] and KeyErrors when OL fixtures omit source (OL8 options "
        "are species-only). Arm-side default; CLI would not process those fixtures."
    ),
}
REASK = ("Call a tool before answering. Use a state tool when the user asks to lock, unlock, reset, or commit. "
         "Use a lookup tool for a factual question.")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _jsonable_result(patch: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in patch.items():
        if key == "team_draft":
            out[key] = read_team({"team_draft": value})["slots"]
        else:
            out[key] = to_jsonable(value)
    return out


def snapshot(state: dict[str, Any]) -> dict[str, Any]:
    pending = state.get("pending_presentation")
    intent = state.get("pending_slot_intent")
    prov = state.get("provisional_slot")
    rejected = state.get("rejected") or []
    return {
        "slots": read_team(state)["slots"],
        "pending_presentation": pending is not None,
        "pending_kind": pending.get("kind") if isinstance(pending, dict) else None,
        "pending_slot_intent_species": (
            intent.get("species") if isinstance(intent, dict) else getattr(intent, "species", None)
        ),
        "provisional_species": (
            prov.get("species") if isinstance(prov, dict) else getattr(prov, "species", None)
        ),
        "rejected": [
            {"species": e.get("species"), "reason": e.get("reason"), "turn": e.get("turn")}
            if isinstance(e, dict) else e
            for e in rejected
        ],
        "steering": list(steering_signature(state)),
        "slot_commit_error": state.get("slot_commit_error"),
    }


def dispatch(state: dict[str, Any], arm: Any, name: str, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if name == "lock_slot":
        return lock_slot(state, args.get("slot"), args.get("species"))
    if name == "edit_slot_field":
        return edit_slot_field(
            state, args.get("slot"), args.get("field"), args.get("value")
        )
    if name == "unlock_slot":
        return unlock_slot(state, args.get("slot"))
    if name == "reset_team":
        return reset_team_state(state)
    if name == "commit_slot":
        return commit_slot(state)
    if name == "confirm_build":
        return confirm_build(state)
    if name == "read_team":
        return state, read_team(state)
    if name == "read_pending":
        return state, read_pending(state)
    if name == "select_option":
        return select_option(state, args.get("option"))
    if name == "reject_pending":
        return reject_pending(state)
    if name == "reject_option":
        return reject_option(state, args.get("option"))
    if name == "reject_all":
        return reject_all(state)
    if name == "read_rejected":
        return state, read_rejected(state)
    if name == "add_constraint":
        return add_constraint(
            state,
            args.get("predicate"),
            args.get("scope"),
            args.get("groundedness"),
            slot=args.get("slot"),
            mechanical_kind=args.get("mechanical_kind"),
            value=args.get("value"),
        )
    if name == "read_constraints":
        return state, read_constraints(state)
    if name == "restore_constraint":
        return restore_constraint_tool(state)
    if name == "show_candidates":
        return show_candidates(state, args.get("slot"), n=args.get("n"))
    if name == "check_hypothetical":
        return state, check_hypothetical(state, args.get("placements"))
    if name == "solve_spread":
        return state, solve_spread_tool(
            state,
            args.get("species"),
            args.get("constraints"),
            ability=args.get("ability"),
            item=args.get("item"),
        )
    return state, arm.call(name, args or {})


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(str(part.get("text") or ""))
        return "".join(parts)
    return "" if content is None else str(content)


def run_turn(
    cfg: ArmConfig,
    llm: Any,
    arm: Any,
    state: dict[str, Any],
    user_text: str,
    *,
    prior_messages: list[dict[str, str]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

    messages: list[Any] = [SystemMessage(cfg.prompt_text())]
    # Optional prior turns (HD1 seed): same roles as a normal multi-turn chat.
    # prior_messages=None → fall back to state; prior_messages=[] → none.
    history = (
        prior_messages
        if prior_messages is not None
        else (state.get("_message_history") or [])
    )
    for prior in history:
        role = prior.get("role")
        content = prior.get("content") or ""
        if role == "user":
            messages.append(HumanMessage(content))
        elif role == "assistant":
            messages.append(AIMessage(content))
    messages.append(HumanMessage(user_text))
    calls: list[dict[str, Any]] = []
    before = snapshot(state)
    deadline = time.monotonic() + cfg.item_timeout_s
    final_text = ""
    errors: list[str] = []
    reasked = False
    for turn_index in range(cfg.max_turns):
        if time.monotonic() > deadline:
            errors.append("item_timeout")
            break
        try:
            ai = llm.invoke(messages)
        except Exception as exc:  # noqa: BLE001 - recorded, not raised
            errors.append(f"{type(exc).__name__}: {exc}")
            break
        if cfg.enforce_first_turn_tool and turn_index == 0 and not ai.tool_calls and not reasked:
            reasked = True
            messages.append(HumanMessage(REASK))
            continue
        messages.append(ai)
        if not ai.tool_calls:
            final_text = _text(ai.content)
            break
        for call in ai.tool_calls:
            state, patch = dispatch(state, arm, call["name"], call.get("args") or {})
            recorded = _jsonable_result(patch)
            calls.append({"name": call["name"], "args": call.get("args") or {}, "result": recorded})
            messages.append(ToolMessage(dumps(recorded), tool_call_id=call["id"]))
        if turn_index + 1 >= cfg.max_turns:
            errors.append("max_turns")
    after = snapshot(state)
    record = {
        "user": user_text,
        "tool_calls": calls,
        "state_before": before,
        "state_after": after,
        "final_text": final_text,
        "mechanical_class": mechanical_class(before, after, calls),
        "errors": errors,
        "reasked": reasked,
    }
    return state, record


def start_state(row: dict[str, Any]) -> dict[str, Any]:
    kind = row.get("start")
    if kind == "fully_locked":
        return build_fully_locked_slot(row["species"], user_slot=int(row["user_slot"]))
    if kind == "fbc":
        return build_fbc_pending(row["species"], slot_index=int(row["slot_index"]))
    if kind == "cs":
        return build_cs_pending(tuple(row["species_options"]), slot_index=int(row.get("slot_index", 0)))
    if kind == "cs_locked_target":
        # Fully lock user slot 1 (internal 0), then overlay a CS screen aimed at that slot.
        locked = build_fully_locked_slot(row["locked_species"], user_slot=1)
        cs = build_cs_pending(tuple(row["species_options"]), slot_index=0)
        return {**locked, "pending_presentation": cs["pending_presentation"]}
    if kind == "fbc_stale_fp":
        state = build_fbc_pending(row["species"], slot_index=int(row["slot_index"]))
        pending = dict(state["pending_presentation"] or {})
        pending["provisional_fingerprint"] = "stale-wrong-fp"
        return {**state, "pending_presentation": pending}
    return empty_team()

def grade_row(row_id: str, turns: list[dict[str, Any]], keys: dict[str, Any]) -> list[str]:
    spec = keys["rows"][row_id]
    failures: list[str] = []
    if spec.get("hand_grade"):
        # Hand audit only (MT7/MT8). Still enforce: never write team_draft.
        for i, turn in enumerate(turns):
            if turn["state_before"]["slots"] != turn["state_after"]["slots"]:
                failures.append(f"{row_id}: t{i+1} wrote team_draft (silent apply)")
        return failures
    if [turn["mechanical_class"] for turn in turns] != spec["classes"]:
        failures.append(f"{row_id}: classes {[t['mechanical_class'] for t in turns]} != {spec['classes']}")
    if row_id == "dev-lock":
        slot = str(spec["user_slot"])
        for turn, species in zip(turns, spec["species_after"], strict=True):
            got = next(row["species"] for row in turn["state_after"]["slots"] if row["slot"] == slot)
            if got != species:
                failures.append(f"{row_id}: slot {slot} species {got!r} != {species!r}")
        if turns[1]["state_after"]["slots"] != turns[0]["state_after"]["slots"]:
            failures.append(f"{row_id}: second turn changed the draft")
    if row_id in ("dev-unlock", "dev-commit"):
        if any(row["species"] for row in turns[0]["state_after"]["slots"]):
            failures.append(f"{row_id}: draft was written")
    if row_id == "dev-unlock-ok":
        slot = str(spec["user_slot"])
        after = next(row for row in turns[0]["state_after"]["slots"] if row["slot"] == slot)
        if after["species"] is not None or after["species_locked"]:
            failures.append(f"{row_id}: slot {slot} was not cleared")
        if turns[0]["state_after"]["pending_presentation"]:
            failures.append(f"{row_id}: pending screen was not cleared by the node dict")
    if row_id == "dev-commit-ok":
        slot = str(spec["user_slot"])
        after = next(row for row in turns[0]["state_after"]["slots"] if row["slot"] == slot)
        if after["species"] != spec["species"] or not after["species_locked"]:
            failures.append(f"{row_id}: slot {slot} species {after['species']!r} not locked as {spec['species']}")
        attrs = {
            entry[0]: (entry[1], entry[2])
            for entry in after["attrs"]
            if len(entry) == 3 and entry[0] in spec["fields"]
        }
        for field in spec["fields"]:
            value, locked = attrs[field]
            if not locked or value in (None, [], {}):
                failures.append(f"{row_id}: field {field} not committed ({value!r}, locked={locked})")
        if turns[0]["state_after"]["pending_presentation"]:
            failures.append(f"{row_id}: pending screen was not cleared by the node dict")
    if row_id == "dev-lookup":
        names = [call["name"] for call in turns[0]["tool_calls"]]
        if any(name in STATE_TOOL_NAMES for name in names):
            failures.append(f"{row_id}: a state tool ran")
        typing = [call for call in turns[0]["tool_calls"] if call["name"] == spec["tool"]]
        if not typing:
            failures.append(f"{row_id}: {spec['tool']} was not called")
        else:
            result = typing[-1]["result"]
            expect = keys["species"][spec["species"]]["types"]
            if result.get("types") != expect:
                failures.append(f"{row_id}: types {result.get('types')!r} != {expect!r}")
    if row_id.startswith("dev-hyp-"):
        before, after = turns[0]["state_before"], turns[0]["state_after"]
        if before["slots"] != after["slots"]:
            failures.append(f"{row_id}: team_draft changed")
        if before.get("pending_presentation") != after.get("pending_presentation"):
            failures.append(f"{row_id}: pending changed")
    if row_id == "dev-pick-named":
        before, after = turns[0]["state_before"], turns[0]["state_after"]
        if before["slots"] != after["slots"]:
            failures.append(f"{row_id}: team_draft changed")
        if after.get("pending_kind") != spec.get("expect_pending_kind"):
            failures.append(
                f"{row_id}: pending_kind {after.get('pending_kind')!r} != {spec.get('expect_pending_kind')!r}"
            )
        species = spec.get("expect_species")
        if after.get("provisional_species") != species:
            failures.append(f"{row_id}: provisional_species {after.get('provisional_species')!r} != {species!r}")
        if after.get("pending_slot_intent_species") != species:
            failures.append(
                f"{row_id}: pending_slot_intent_species {after.get('pending_slot_intent_species')!r} != {species!r}"
            )
        if spec.get("must_not_commit"):
            names = [c["name"] for c in turns[0]["tool_calls"]]
            if "commit_slot" in names or "confirm_build" in names:
                failures.append(f"{row_id}: commit/confirm ran (must not commit on pick)")
    if row_id in ("dev-select-bad", "dev-select-locked-target", "dev-confirm-stale-fp"):
        if not turns[0]["state_after"].get("pending_presentation"):
            failures.append(f"{row_id}: pending was cleared on refusal")
        if turns[0]["state_before"]["slots"] != turns[0]["state_after"]["slots"]:
            failures.append(f"{row_id}: draft changed on refusal")
    if row_id == "dev-confirm-fbc":
        slot = str(spec["user_slot"])
        after = next(row for row in turns[0]["state_after"]["slots"] if row["slot"] == slot)
        if after["species"] != spec["species"] or not after["species_locked"]:
            failures.append(f"{row_id}: slot {slot} not locked as {spec['species']}")
        if turns[0]["state_after"]["pending_presentation"]:
            failures.append(f"{row_id}: pending screen was not cleared")
    if row_id == "dev-reject":
        after = turns[0]["state_after"]
        if after.get("pending_presentation"):
            failures.append(f"{row_id}: pending was not cleared")
        want = spec.get("expect_rejected_species")
        names = [e.get("species") for e in after.get("rejected") or [] if isinstance(e, dict)]
        if want and want not in names:
            failures.append(f"{row_id}: rejected {names!r} missing {want!r}")
    if row_id == "dev-toss-all":
        after = turns[0]["state_after"]
        if after.get("pending_presentation"):
            failures.append(f"{row_id}: pending was not cleared")
        if any(row["species"] for row in after["slots"]):
            failures.append(f"{row_id}: draft was written")
        names = [e.get("species") for e in after.get("rejected") or [] if isinstance(e, dict)]
        for want in spec.get("expect_rejected_species") or []:
            if want not in names:
                failures.append(f"{row_id}: rejected {names!r} missing {want!r}")
        if len(names) < len(spec.get("expect_rejected_species") or []):
            failures.append(f"{row_id}: rejected grew by {len(names)}, expected more")
    if row_id == "dev-show-rejected":
        after = turns[-1]["state_after"]
        want = spec.get("expect_rejected_species")
        names = [e.get("species") for e in after.get("rejected") or [] if isinstance(e, dict)]
        if want and want not in names:
            failures.append(f"{row_id}: rejected {names!r} missing {want!r}")
        read_calls = [
            call for call in turns[-1]["tool_calls"] if call["name"] == "read_rejected"
        ]
        if not read_calls:
            failures.append(f"{row_id}: read_rejected was not called")
        else:
            got = [
                e.get("species")
                for e in (read_calls[-1]["result"] or {}).get("rejected") or []
            ]
            if want and want not in got:
                failures.append(f"{row_id}: read_rejected {got!r} missing {want!r}")
    if row_id == "dev-dismiss-later":
        before, after = turns[0]["state_before"], turns[0]["state_after"]
        if after.get("pending_presentation"):
            failures.append(f"{row_id}: pending was not cleared")
        if before.get("rejected") != after.get("rejected"):
            failures.append(f"{row_id}: rejected list changed on dismiss")
    if row_id == "dev-reject-all-bad":
        if turns[0]["state_after"].get("pending_presentation"):
            failures.append(f"{row_id}: pending appeared on refusal")
        if turns[0]["state_before"]["slots"] != turns[0]["state_after"]["slots"]:
            failures.append(f"{row_id}: draft changed on refusal")
        if turns[0]["state_before"].get("rejected") != turns[0]["state_after"].get("rejected"):
            failures.append(f"{row_id}: rejected changed on refusal")
    return failures


def run_record(cfg: ArmConfig, facts: dict[str, Any]) -> dict[str, Any]:
    specs = combined_specs()
    return {
        "non_inheritance": NON_INHERITANCE,
        "run_params": RUN_PARAMS,
        "prompt_file": cfg.prompt_file,
        "prompt_sha256": cfg.prompt_hash(),
        "tool_schema_sha256": _sha256_bytes(json.dumps(specs, sort_keys=True).encode()),
        "fixture_manifest_sha256": _sha256_bytes((HERE / "fixtures.py").read_bytes()),
        "model": cfg.model,
        "model_digest": facts.get("digest"),
        "allow_live": cfg.allow_live,
    }


def run_dev(out_dir: Path, cfg: ArmConfig | None = None) -> int:
    from recommender.arm_tools import ArmTools
    from langchain_ollama import ChatOllama
    from scripts.eval.part_g_arm.run_battery import model_facts

    cfg = cfg or ArmConfig(prompt_file="state/prompt.md")
    rows = json.loads((HERE / "dev_rows.json").read_text(encoding="utf-8"))["rows"]
    keys = json.loads((HERE / "dev_keys.json").read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        facts = model_facts(cfg)
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - the checkpoint records the failure and stops
        (out_dir / "run_record.json").write_text(json.dumps({"non_inheritance": NON_INHERITANCE, "error": f"{type(exc).__name__}: {exc}"}, indent=2) + "\n")
        print(f"checkpoint failed before the rows: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    arm = ArmTools(regulation=cfg.regulation, allow_live=False, calc=CalcClient(cfg.calc_base_url),
                   include_damage_rolls=cfg.damage_rolls_in_result)
    llm = ChatOllama(
        model=cfg.model, temperature=cfg.temperature, reasoning=cfg.think, num_ctx=cfg.num_ctx,
        num_predict=cfg.num_predict, client_kwargs={"timeout": cfg.call_timeout_s},
    ).bind_tools(combined_specs())
    transcript = []
    failures: list[str] = []
    for row in rows:
        state = start_state(row)
        turns = []
        for user_text in row["turns"]:
            state, record = run_turn(cfg, llm, arm, state, user_text)
            turns.append(record)
        failures.extend(grade_row(row["id"], turns, keys))
        transcript.append({"id": row["id"], "turns": turns, "pass": not any(item.startswith(row["id"] + ":") for item in failures)})
    record = run_record(cfg, facts)
    record["failures"] = failures
    (out_dir / "transcript.json").write_text(json.dumps(transcript, indent=2) + "\n", encoding="utf-8")
    (out_dir / "run_record.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m scripts.eval.part_g_arm.state.harness OUT_DIR", file=sys.stderr)
        return 2
    return run_dev(Path(argv[1]))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
