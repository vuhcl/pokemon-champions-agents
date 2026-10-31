"""Request-set runner for the stateful arm (Part B2).

Loads a row's start state, plays its turns in ONE session, writes transcripts
outside the repo. Refuses to start unless the prompt sha equals the frozen
sha from A5, and refuses row ids outside the pre-declared covered list unless
--dev is set.

No request-set row is run by default from this module's tests; this is the
runner only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from recommender.arm_tools import ArmTools
from recommender.calc_client import CalcClient

from scripts.eval.part_g_arm.config import ArmConfig
from scripts.eval.part_g_arm.state.harness import RUN_PARAMS, NON_INHERITANCE, run_turn
from scripts.eval.part_g_arm.state.request_set_rows import (
    FROZEN_PROMPT_SHA256,
    load_covered_ids,
    load_request_rows,
    resolve_start_state,
    turns_for_row,
)
from scripts.eval.part_g_arm.state.tools import combined_specs

HERE = Path(__file__).resolve().parent
V4 = HERE.parents[1] / "part_g_v4"

# Fixed run-model identity (Part 2). Same as Part G gate / out-final4. Do not vary per row.
FIXED_RUN_SETTINGS: dict[str, Any] = {
    "model_id": "qwen3.5:latest",
    "model_digest": "44a38603922e14f1e3ae68c5d900cc39f2a925a9749d12ab6d268d75a01a399f",
    "quantization": "Q4_K_M",
    "parameter_size": "9.7B",
    "temperature": 0.0,
    "think": False,
    "num_ctx": 16384,
    "num_predict": 2048,
    "seed": None,  # not pinned; Ollama default
    "prompt_sha256": FROZEN_PROMPT_SHA256,
}

# Arm v2 ladder flags (Vu 2026-10-30). All default off for PRE-RS-ARM-equivalent configs.
DEFAULT_RUN_FLAGS: dict[str, bool] = {
    "tool_fields": False,
    "wrapper": False,
    "guard": False,
    "judge": False,
}

# Fixed BEFORE any covered run (Part 4). No silent retry.
FAILURE_POLICY: dict[str, Any] = {
    "per_turn_timeout_s": 300.0,
    "max_tool_calls_per_turn": 16,
    "on_no_answer_or_error": "record as 'no usable answer'; no silent retry",
    "resume": (
        "progress.json lists finished row ids; resume skips them and must not rewrite "
        "their transcript entries"
    ),
}


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pin_hashes(*, additions_file: Path | None = None) -> dict[str, str]:
    """Content hashes for pins the run record must name."""
    out: dict[str, str] = {
        "prompt_sha256": FROZEN_PROMPT_SHA256,
        "request_set_sha256": _sha256_file(V4 / "part3_request_set_v4.md"),
        "derived_keys_sha256": _sha256_file(V4 / "key_artifacts" / "derived_keys.json"),
        "covered_list_sha256": _sha256_file(HERE / "covered_list.json"),
        "errata_sha256": _sha256_file(HERE / "errata.json"),
    }
    joint = HERE / "LAST_JOINT_COVERAGE.md"
    if joint.is_file():
        out["joint_coverage_note_sha256"] = _sha256_file(joint)
    if additions_file is not None:
        out["additions_file_sha256"] = _sha256_file(additions_file)
        out["additions_file"] = str(additions_file)
    return out


# Prompt variant when --tool-fields is on (own sha; not the PRE-RS-ARM freeze).
TOOL_FIELDS_PROMPT_FILE = "state/prompt_tool_fields.md"
# Prompt variant when --wrapper is on (tool_fields text + one set_slot sentence).
WRAPPER_PROMPT_FILE = "state/prompt_wrapper.md"


def assert_frozen_prompt(
    cfg: ArmConfig,
    *,
    allow_dev: bool,
    allow_tool_fields_prompt: bool = False,
    allow_wrapper_prompt: bool = False,
) -> None:
    got = cfg.prompt_hash()
    if got == FROZEN_PROMPT_SHA256:
        return
    if allow_wrapper_prompt and cfg.prompt_file == WRAPPER_PROMPT_FILE:
        print(
            f"wrapper prompt: {got} (frozen PRE-RS-ARM remains {FROZEN_PROMPT_SHA256})",
            file=sys.stderr,
        )
        return
    if allow_tool_fields_prompt and cfg.prompt_file == TOOL_FIELDS_PROMPT_FILE:
        print(
            f"tool_fields prompt: {got} (frozen PRE-RS-ARM remains {FROZEN_PROMPT_SHA256})",
            file=sys.stderr,
        )
        return
    if allow_dev:
        print(f"dev override: prompt {got} != frozen {FROZEN_PROMPT_SHA256}", file=sys.stderr)
        return
    raise SystemExit(
        f"refusing to start: prompt sha256 {got} != frozen {FROZEN_PROMPT_SHA256} "
        "(pass --dev to override)"
    )


def assert_row_allowed(
    row_id: str,
    *,
    allow_dev: bool,
    covered: set[str],
    additions_ids: set[str] | None = None,
) -> None:
    if row_id in covered:
        return
    if additions_ids and row_id in additions_ids:
        return
    if allow_dev:
        print(f"dev override: running non-covered row {row_id}", file=sys.stderr)
        return
    raise SystemExit(f"refusing row {row_id!r}: not in covered_list.json (pass --dev to override)")


def _usable_assistant_text(record: dict[str, Any]) -> str:
    text = (record.get("final_text") or "").strip()
    if not text or record.get("no_usable_answer"):
        return ""
    if text == "no usable answer":
        return ""
    return text


def run_row(
    row: dict[str, Any],
    *,
    cfg: ArmConfig,
    llm: Any,
    arm: ArmTools,
    resolve_fn: Any = None,
    turns_fn: Any = None,
    run_flags: dict[str, bool] | None = None,
) -> dict[str, Any]:
    resolve = resolve_fn or resolve_start_state
    turns_fn = turns_fn or turns_for_row
    flags = {**DEFAULT_RUN_FLAGS, **(run_flags or {})}
    state, meta = resolve(row)
    if state is None:
        return {
            "id": row["id"],
            "loaded": False,
            "error": meta.get("error"),
            "turns": [],
            "run_flags": dict(flags),
        }
    turns_out: list[dict[str, Any]] = []
    seed_prior = list(state.get("_message_history") or [])
    # User+assistant text from completed runner turns of this row (no tool messages).
    row_chat: list[dict[str, str]] = []
    # Apply failure-policy timeouts onto a shallow cfg copy when possible.
    turn_timeout = float(FAILURE_POLICY["per_turn_timeout_s"])
    max_tools = int(FAILURE_POLICY["max_tool_calls_per_turn"])
    for i, user_text in enumerate(turns_fn(row, state)):
        # Turn 0: seed history only (unchanged). Later turns: earlier row turns' text.
        use_prior = seed_prior if i == 0 else list(row_chat)
        # Cap model invocations via item_timeout / max_turns without mutating frozen ArmConfig.
        capped = cfg
        if hasattr(cfg, "item_timeout_s") and cfg.item_timeout_s != turn_timeout:
            from dataclasses import replace

            capped = replace(
                cfg,
                item_timeout_s=turn_timeout,
                max_turns=min(cfg.max_turns, max_tools),
            )
        state, record = run_turn(capped, llm, arm, state, user_text, prior_messages=use_prior)
        n_tools = len(record.get("tool_calls") or [])
        if n_tools > max_tools:
            record["errors"] = list(record.get("errors") or []) + ["max_tool_calls"]
        if not (record.get("final_text") or "").strip() or record.get("errors"):
            # No silent retry — stamp the policy outcome.
            if not (record.get("final_text") or "").strip():
                record["final_text"] = "no usable answer"
            record["no_usable_answer"] = True
        record["run_flags"] = dict(flags)
        # Prompt-token logging: char proxy always; HF token count when available.
        record["prompt_chars"] = sum(len(m.get("content") or "") for m in use_prior) + len(
            user_text
        ) + len(cfg.prompt_text())
        turns_out.append(record)
        row_chat.append({"role": "user", "content": user_text})
        assistant = _usable_assistant_text(record)
        if assistant:
            row_chat.append({"role": "assistant", "content": assistant})
    replace_true_turns = [
        i + 1 for i, t in enumerate(turns_out) if int(t.get("replace_true_calls") or 0) > 0
    ]
    return {
        "id": row["id"],
        "loaded": True,
        "start_meta": meta,
        "turns": turns_out,
        "run_flags": dict(flags),
        "replace_true_turns": replace_true_turns,
    }


def build_run_parameters(
    cfg: ArmConfig,
    facts: dict[str, Any],
    *,
    run_flags: dict[str, bool] | None = None,
    additions_file: Path | None = None,
) -> dict[str, Any]:
    flags = {**DEFAULT_RUN_FLAGS, **(run_flags or {})}
    specs = combined_specs(
        tool_fields=bool(flags.get("tool_fields")),
        wrapper=bool(flags.get("wrapper")),
    )
    digest = facts.get("digest") or FIXED_RUN_SETTINGS["model_digest"]
    return {
        "non_inheritance": NON_INHERITANCE,
        "run_params": RUN_PARAMS,
        "fixed_run_settings": FIXED_RUN_SETTINGS,
        "model_id": FIXED_RUN_SETTINGS["model_id"],
        "model_digest": digest,
        "temperature": FIXED_RUN_SETTINGS["temperature"],
        "think": FIXED_RUN_SETTINGS["think"],
        "num_ctx": FIXED_RUN_SETTINGS["num_ctx"],
        "num_predict": FIXED_RUN_SETTINGS["num_predict"],
        "seed": FIXED_RUN_SETTINGS["seed"],
        "prompt_sha256": cfg.prompt_hash(),
        "frozen_prompt_sha256": FROZEN_PROMPT_SHA256,
        "tool_set": [s["function"]["name"] for s in specs],
        "tool_schema_sha256": hashlib.sha256(
            json.dumps(specs, sort_keys=True).encode()
        ).hexdigest(),
        "pin_hashes": pin_hashes(additions_file=additions_file),
        "arm_side_adaptations": {
            "select_option_source_default": RUN_PARAMS["select_option_source_default"],
            "primitive_pending_tools": RUN_PARAMS["primitive_tools"],
            "partial_cs_stale_gate": RUN_PARAMS["partial_cs_stale_gate"],
            "solve_spread": "read-only solve_spread tool (L1-to-joint)",
        },
        "allow_live": cfg.allow_live,
        "failure_policy": FAILURE_POLICY,
        "run_flags": flags,
    }


def run_role(run_id: int) -> str:
    """run 1 = primary result; runs 2 and 3 = determinism checks (never averaged)."""
    if run_id == 1:
        return "primary"
    if run_id in (2, 3):
        return "determinism"
    raise ValueError(f"run_id must be 1, 2, or 3; got {run_id}")


def resolve_out_dir(*, out_dir: Path | None, runs_root: Path | None, run_id: int | None) -> tuple[Path, int | None, str | None]:
    """Map CLI out_dir / --runs-root + --run-id to a single run directory.

    --runs-root DIR with --run-id N → DIR/run_N/ (isolated progress; no resume across runs).
    Plain out_dir alone leaves run_id unset (legacy single-run).
    """
    if runs_root is not None:
        if run_id is None:
            raise SystemExit("--runs-root requires --run-id {1|2|3}")
        role = run_role(run_id)
        return runs_root / f"run_{run_id}", run_id, role
    if out_dir is None:
        raise SystemExit("out_dir or --runs-root is required")
    if run_id is not None:
        return out_dir, run_id, run_role(run_id)
    return out_dir, None, None


def _load_progress(out_dir: Path) -> dict[str, Any]:
    path = out_dir / "progress.json"
    if not path.is_file():
        return {"finished": [], "transcript_by_id": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_progress(out_dir: Path, progress: dict[str, Any]) -> None:
    (out_dir / "progress.json").write_text(json.dumps(progress, indent=2) + "\n", encoding="utf-8")


def run_batch(
    *,
    out_dir: Path,
    wanted: list[str],
    cfg: ArmConfig,
    llm: Any,
    arm: ArmTools,
    facts: dict[str, Any],
    rows_by_id: dict[str, dict[str, Any]],
    stop_after: int | None = None,
    resolve_fn: Any = None,
    turns_fn: Any = None,
    run_id: int | None = None,
    role: str | None = None,
    run_flags: dict[str, bool] | None = None,
    additions_file: Path | None = None,
) -> int:
    """Run rows with resume. stop_after limits newly completed rows (kill-resume tests)."""
    from scripts.eval.part_g_arm.state.exploratory_runner import assert_not_exploratory_dir
    from scripts.eval.part_g_arm.state.tools import set_tool_fields, set_wrapper

    assert_not_exploratory_dir(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    flags = {**DEFAULT_RUN_FLAGS, **(run_flags or {})}
    set_tool_fields(bool(flags.get("tool_fields")))
    set_wrapper(bool(flags.get("wrapper")))
    progress = _load_progress(out_dir)
    if run_id is not None:
        progress["run_id"] = run_id
        progress["role"] = role or run_role(run_id)
    finished = list(progress.get("finished") or [])
    by_id: dict[str, Any] = dict(progress.get("transcript_by_id") or {})
    newly = 0
    for rid in wanted:
        if rid in by_id and rid in finished:
            print(f"skip finished {rid}", file=sys.stderr)
            continue
        print(f"running {rid}", file=sys.stderr)
        entry = run_row(
            rows_by_id[rid],
            cfg=cfg,
            llm=llm,
            arm=arm,
            resolve_fn=resolve_fn,
            turns_fn=turns_fn,
            run_flags=flags,
        )
        if run_id is not None:
            entry["run_id"] = run_id
            entry["role"] = role or run_role(run_id)
        # Freeze finished results: never overwrite an existing finished entry.
        if rid in finished and rid in by_id:
            raise SystemExit(f"refusing to rewrite finished row {rid}")
        by_id[rid] = entry
        finished.append(rid)
        progress = {"finished": finished, "transcript_by_id": by_id}
        if run_id is not None:
            progress["run_id"] = run_id
            progress["role"] = role or run_role(run_id)
        _save_progress(out_dir, progress)
        newly += 1
        if stop_after is not None and newly >= stop_after:
            print(f"stop_after={stop_after} hit", file=sys.stderr)
            break

    transcript = [by_id[rid] for rid in wanted if rid in by_id]
    record = build_run_parameters(
        cfg, facts, run_flags=flags, additions_file=additions_file
    )
    if run_id is not None:
        record["run_id"] = run_id
        record["role"] = role or run_role(run_id)
    progress = {"finished": finished, "transcript_by_id": by_id}
    if run_id is not None:
        progress["run_id"] = run_id
        progress["role"] = role or run_role(run_id)
    _save_progress(out_dir, progress)
    (out_dir / "transcript.json").write_text(json.dumps(transcript, indent=2) + "\n", encoding="utf-8")
    # Per-row list of turns with replace=true set_slot calls (audit finds calls; verdict by hand).
    record["replace_true_turns_by_row"] = {
        e["id"]: e.get("replace_true_turns") or [] for e in transcript if e.get("loaded")
    }
    (out_dir / "run_record.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    _write_tool_calls_csv(out_dir, transcript)
    print(f"wrote {out_dir} ({len(transcript)} rows)", file=sys.stderr)
    return 0


def _write_tool_calls_csv(out_dir: Path, transcript: list[dict[str, Any]]) -> None:
    """One row per tool call; includes top-level replace for set_slot audit."""
    import csv

    path = out_dir / "tool_calls.csv"
    fields = [
        "row_id",
        "turn",
        "call_index",
        "name",
        "replace",
        "replace_true_calls",
        "args_json",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for entry in transcript:
            rid = entry.get("id")
            for ti, turn in enumerate(entry.get("turns") or []):
                rtc = turn.get("replace_true_calls")
                for ci, call in enumerate(turn.get("tool_calls") or []):
                    rep = call.get("replace")
                    if rep is None and call.get("name") == "set_slot":
                        rep = bool((call.get("args") or {}).get("replace") or False)
                    w.writerow(
                        {
                            "row_id": rid,
                            "turn": ti + 1,
                            "call_index": ci,
                            "name": call.get("name"),
                            "replace": "" if rep is None else str(bool(rep)).lower(),
                            "replace_true_calls": rtc if rtc is not None else "",
                            "args_json": json.dumps(call.get("args") or {}, sort_keys=True),
                        }
                    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "out_dir",
        type=Path,
        nargs="?",
        default=None,
        help="transcript directory (outside the repo); omit when using --runs-root",
    )
    parser.add_argument(
        "--runs-root",
        type=Path,
        default=None,
        help="parent dir for three-run layout; with --run-id N writes to ROOT/run_N/",
    )
    parser.add_argument(
        "--run-id",
        type=int,
        choices=(1, 2, 3),
        default=None,
        help="1=primary, 2|3=determinism checks; stamps run_id/role on every record",
    )
    parser.add_argument("--row", action="append", default=[], help="row id to run (repeatable)")
    parser.add_argument("--dev", action="store_true", help="allow non-frozen prompt / non-covered rows")
    parser.add_argument("--list-covered", action="store_true", help="print covered ids and exit")
    parser.add_argument("--stub", action="store_true", help="use StubLLM (no Ollama)")
    parser.add_argument("--stop-after", type=int, default=None, help="stop after N new rows (resume test)")
    parser.add_argument("--dev-rows-file", type=Path, default=None, help="run harness-style dev_rows.json via --dev")
    parser.add_argument(
        "--additions-file",
        type=Path,
        default=None,
        help="extra rows JSON (usable in a covered run); sha256 recorded in pin_hashes",
    )
    parser.add_argument(
        "--tool-fields",
        action="store_true",
        help="arm v2: enable tool_fields rung (default off)",
    )
    parser.add_argument(
        "--wrapper", action="store_true", help="arm v2: enable set-slot wrapper (default off)"
    )
    parser.add_argument(
        "--guard", action="store_true", help="arm v2: enable class tool guard (default off)"
    )
    parser.add_argument(
        "--judge", action="store_true", help="arm v2: enable judge-lite (default off)"
    )
    args = parser.parse_args(argv)
    run_flags = {
        "tool_fields": bool(args.tool_fields),
        "wrapper": bool(args.wrapper),
        "guard": bool(args.guard),
        "judge": bool(args.judge),
    }

    covered = load_covered_ids()
    if args.list_covered:
        print("\n".join(sorted(covered)))
        return 0

    from scripts.eval.part_g_arm.state.tools import set_tool_fields, set_wrapper

    set_tool_fields(bool(run_flags["tool_fields"]))
    set_wrapper(bool(run_flags["wrapper"]))
    if run_flags["wrapper"]:
        prompt_file = WRAPPER_PROMPT_FILE
    elif run_flags["tool_fields"]:
        prompt_file = TOOL_FIELDS_PROMPT_FILE
    else:
        prompt_file = "state/prompt.md"
    cfg = ArmConfig(prompt_file=prompt_file)
    assert_frozen_prompt(
        cfg,
        allow_dev=args.dev or bool(args.dev_rows_file),
        allow_tool_fields_prompt=bool(run_flags["tool_fields"]) and not run_flags["wrapper"],
        allow_wrapper_prompt=bool(run_flags["wrapper"]),
    )

    rows_by_id = {r["id"]: r for r in load_request_rows()}
    additions_ids: set[str] = set()
    additions_file: Path | None = args.additions_file
    if additions_file is not None:
        add_doc = json.loads(additions_file.read_text(encoding="utf-8"))
        add_rows = add_doc.get("rows") or []
        for r in add_rows:
            rid = r["id"]
            additions_ids.add(rid)
            rows_by_id[rid] = {
                "id": rid,
                "prompt": " | ".join(r.get("turns") or [r.get("prompt") or ""]),
                "state": r.get("state") or "idle",
                "class": r.get("class") or "ADDITION",
                "acceptance": r.get("acceptance") or "",
                "claim_types": r.get("claim_types") or "",
                "raw": "",
                "_addition_row": r,
            }

    if args.dev_rows_file:
        dev_doc = json.loads(args.dev_rows_file.read_text(encoding="utf-8"))
        all_dev = [r["id"] for r in dev_doc["rows"]]
        wanted = args.row if args.row else all_dev
        for r in dev_doc["rows"]:
            rows_by_id[r["id"]] = {
                "id": r["id"],
                "prompt": " | ".join(r["turns"]),
                "state": "dev",
                "class": "DEV",
                "acceptance": "",
                "claim_types": "",
                "raw": "",
                "_dev_row": r,
            }
    else:
        wanted = args.row or sorted(covered)
        if additions_ids and not args.row:
            wanted = [*wanted, *sorted(additions_ids)]
    for rid in wanted:
        assert_row_allowed(
            rid,
            allow_dev=args.dev or bool(args.dev_rows_file),
            covered=covered,
            additions_ids=additions_ids,
        )
        if rid not in rows_by_id:
            raise SystemExit(f"unknown row id {rid!r}")

    out_dir, run_id, role = resolve_out_dir(
        out_dir=args.out_dir, runs_root=args.runs_root, run_id=args.run_id
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    arm = ArmTools(
        regulation=cfg.regulation,
        allow_live=False,
        calc=CalcClient(cfg.calc_base_url),
        include_damage_rolls=cfg.damage_rolls_in_result,
    )

    if args.stub:
        from scripts.eval.part_g_arm.state.stub_llm import StubLLM

        llm: Any = StubLLM()
        facts: dict[str, Any] = {"digest": FIXED_RUN_SETTINGS["model_digest"], "stub": True}
    else:
        from scripts.eval.part_g_arm.run_battery import model_facts
        from langchain_ollama import ChatOllama

        try:
            facts = model_facts(cfg)
        except (Exception, SystemExit) as exc:  # noqa: BLE001
            err_rec: dict[str, Any] = {"error": f"{type(exc).__name__}: {exc}"}
            if run_id is not None:
                err_rec["run_id"] = run_id
                err_rec["role"] = role
            (out_dir / "run_record.json").write_text(json.dumps(err_rec, indent=2) + "\n")
            return 1
        llm = ChatOllama(
            model=cfg.model,
            temperature=cfg.temperature,
            reasoning=cfg.think,
            num_ctx=cfg.num_ctx,
            num_predict=cfg.num_predict,
            client_kwargs={"timeout": cfg.call_timeout_s},
        ).bind_tools(
            combined_specs(
                tool_fields=bool(run_flags["tool_fields"]),
                wrapper=bool(run_flags["wrapper"]),
            )
        )

    resolve_fn = None
    turns_fn = None
    if args.dev_rows_file or additions_ids:
        from scripts.eval.part_g_arm.state.harness import start_state as harness_start

        def _resolve_dev(row: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
            if row.get("_dev_row"):
                st = harness_start(row["_dev_row"])
                return st, {
                    "row": row["id"],
                    "loaded": True,
                    "complete": True,
                    "source": "harness.start_state",
                }
            if row.get("_addition_row"):
                # Later briefs may attach start descriptors; default empty until then.
                add = row["_addition_row"]
                if add.get("start"):
                    st = harness_start(add)
                    return st, {
                        "row": row["id"],
                        "loaded": True,
                        "complete": True,
                        "source": "additions harness.start_state",
                    }
                return resolve_start_state(row)
            return resolve_start_state(row)

        def _turns_dev(row: dict[str, Any], state: dict[str, Any] | None) -> list[str]:
            if row.get("_dev_row"):
                return list(row["_dev_row"]["turns"])
            if row.get("_addition_row") and row["_addition_row"].get("turns"):
                return list(row["_addition_row"]["turns"])
            return turns_for_row(row, state)

        resolve_fn = _resolve_dev
        turns_fn = _turns_dev

    return run_batch(
        out_dir=out_dir,
        wanted=wanted,
        cfg=cfg,
        llm=llm,
        arm=arm,
        facts=facts,
        rows_by_id=rows_by_id,
        stop_after=args.stop_after,
        resolve_fn=resolve_fn,
        turns_fn=turns_fn,
        run_id=run_id,
        role=role,
        run_flags=run_flags,
        additions_file=additions_file,
    )


if __name__ == "__main__":
    raise SystemExit(main())
