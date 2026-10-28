"""Exploratory (unscored) runner for not-covered request-set rows.

Declared in the registration analysis_plan 3b. Same model/prompt/failure policy
as the registered runner, but writes only under an exploratory root and never
into a registered three-run layout. Registered ``request_set_runner`` refuses
directories marked exploratory (see ``assert_not_exploratory_dir``).

No class scoring, no judge, no pass/fail. Do not run on real not-covered rows
until Vu says go — tests use stub + eev/dev only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from recommender.arm_tools import ArmTools
from recommender.calc_client import CalcClient

from scripts.eval.part_g_arm.config import ArmConfig
from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.request_set_rows import (
    load_covered_ids,
    load_request_rows,
    resolve_start_state,
    turns_for_row,
)
from scripts.eval.part_g_arm.state.request_set_runner import (
    FAILURE_POLICY,
    FIXED_RUN_SETTINGS,
    assert_frozen_prompt,
    build_run_parameters,
    run_row,
)
from scripts.eval.part_g_arm.state.tools import combined_specs

HERE = Path(__file__).resolve().parent
README_MARK = "exploratory, unscored"
README_BODY = (
    f"{README_MARK}\n\n"
    "Exploratory arm transcripts for not-covered request-set rows.\n"
    "Not part of the registered three-run design. No class scoring, no judge, no pass/fail.\n"
)
PROGRESS_NAME = "exploratory_progress.json"


def load_not_covered_ids() -> list[str]:
    doc = json.loads((HERE / "covered_list.json").read_text(encoding="utf-8"))
    return list(doc["not_covered"])


def assert_exploratory_root(root: Path) -> Path:
    """Refuse registered three-run layouts and paths without an exploratory segment."""
    root = root.resolve()
    parts_l = {p.lower() for p in root.parts}
    if "exploratory" not in parts_l and not root.name.lower().startswith("exploratory"):
        raise SystemExit(
            f"exploratory root must include path segment 'exploratory' or a name "
            f"starting with exploratory; got {root}"
        )
    for n in (1, 2, 3):
        run_dir = root / f"run_{n}"
        if run_dir.is_dir() and (run_dir / "run_record.json").is_file():
            raise SystemExit(
                f"refusing exploratory write into registered three-run layout ({run_dir})"
            )
    # Writing as ROOT/run_N beside an existing registered tree
    if root.name.startswith("run_") and (root.parent / "run_1" / "run_record.json").is_file():
        raise SystemExit(f"refusing exploratory write beside registered runs ({root.parent})")
    # Directly targeting a registered run_N directory
    if root.name in {"run_1", "run_2", "run_3"} and (root / "run_record.json").is_file():
        raise SystemExit(f"refusing exploratory write into registered run dir {root}")
    return root


def assert_not_exploratory_dir(out_dir: Path) -> None:
    """Registered runner calls this so it never writes into an exploratory tree."""
    out_dir = out_dir.resolve()
    if "exploratory" in {p.lower() for p in out_dir.parts}:
        raise SystemExit(
            f"refusing registered runner write into path with 'exploratory' segment: {out_dir}"
        )
    readme = out_dir / "README.md"
    if readme.is_file():
        head = readme.read_text(encoding="utf-8")[:120].lower()
        if head.startswith(README_MARK) or "exploratory, unscored" in head:
            raise SystemExit(
                f"refusing registered runner write into exploratory dir {out_dir} "
                f"(README marks {README_MARK!r})"
            )
    if (out_dir / PROGRESS_NAME).is_file():
        raise SystemExit(
            f"refusing registered runner write into dir with {PROGRESS_NAME}: {out_dir}"
        )


def resolve_exploratory_start(row: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Like resolve_start_state, but H12 gets empty_team from row text (not in seeds/)."""
    rid = row["id"]
    if rid == "H12":
        # Retriage: state cell 'attackers undefined' → empty_team (row text only).
        return empty_team(), {
            "row": rid,
            "loaded": True,
            "complete": True,
            "source": "exploratory:empty_team (attackers undefined)",
            "error": None,
        }
    return resolve_start_state(row)


def _jsonable_sig(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_jsonable_sig(v) for v in value]
    if isinstance(value, list):
        return [_jsonable_sig(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable_sig(v) for k, v in value.items()}
    return value


def _entry_state_signature(entry: dict[str, Any]) -> Any:
    """Compact signature from the last turn's state_after snapshot, if any."""
    turns = entry.get("turns") or []
    if not turns:
        return None
    after = turns[-1].get("state_after")
    return _jsonable_sig(after) if after is not None else None


def run_exploratory_batch(
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
) -> int:
    out_dir = assert_exploratory_root(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "README.md").write_text(README_BODY, encoding="utf-8")

    progress_path = out_dir / PROGRESS_NAME
    # Never read registered progress.json
    if (out_dir / "progress.json").is_file() and not progress_path.is_file():
        raise SystemExit(
            f"refusing to treat registered progress.json as exploratory at {out_dir}"
        )

    if progress_path.is_file():
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
    else:
        progress = {"finished": [], "transcript_by_id": {}, "mode": "exploratory"}

    finished = list(progress.get("finished") or [])
    by_id: dict[str, Any] = dict(progress.get("transcript_by_id") or {})
    newly = 0
    resolve = resolve_fn or resolve_exploratory_start

    for rid in wanted:
        if rid in by_id and rid in finished:
            print(f"skip finished {rid}", file=sys.stderr)
            continue
        print(f"exploratory {rid}", file=sys.stderr)
        row = rows_by_id[rid]
        state, meta = resolve(row)
        if state is None or not meta.get("loaded"):
            entry: dict[str, Any] = {
                "id": rid,
                "loaded": False,
                "load_failure": True,
                "error": meta.get("error") or "loader returned no state",
                "start_meta": meta,
                "turns": [],
                "state_signature": None,
                "mode": "exploratory",
            }
        else:
            entry = run_row(
                row,
                cfg=cfg,
                llm=llm,
                arm=arm,
                resolve_fn=resolve,
                turns_fn=turns_fn,
            )
            entry["mode"] = "exploratory"
            entry["load_failure"] = False
            entry["state_signature"] = _entry_state_signature(entry)

        if rid in finished and rid in by_id:
            raise SystemExit(f"refusing to rewrite finished exploratory row {rid}")
        by_id[rid] = entry
        finished.append(rid)
        progress = {
            "finished": finished,
            "transcript_by_id": by_id,
            "mode": "exploratory",
            "mark": README_MARK,
            "failure_policy": FAILURE_POLICY,
        }
        progress_path.write_text(json.dumps(progress, indent=2) + "\n", encoding="utf-8")
        newly += 1
        if stop_after is not None and newly >= stop_after:
            print(f"stop_after={stop_after} hit", file=sys.stderr)
            break

    transcript = [by_id[rid] for rid in wanted if rid in by_id]
    record = build_run_parameters(cfg, facts)
    record["mode"] = "exploratory"
    record["mark"] = README_MARK
    record["scoring"] = "none"
    (out_dir / "transcript.json").write_text(json.dumps(transcript, indent=2) + "\n", encoding="utf-8")
    (out_dir / "run_record.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"wrote exploratory {out_dir} ({len(transcript)} rows)", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--exploratory-root",
        type=Path,
        default=None,
        help="output root (must include 'exploratory' in the path); separate from registered runs",
    )
    parser.add_argument("--row", action="append", default=[], help="subset of not-covered ids (repeatable)")
    parser.add_argument("--stub", action="store_true", help="StubLLM (no Ollama)")
    parser.add_argument("--stop-after", type=int, default=None)
    parser.add_argument(
        "--dev-rows-file",
        type=Path,
        default=None,
        help="test-only: harness-style eev/dev rows (never a covered/not-covered request-set row)",
    )
    parser.add_argument(
        "--list-not-covered",
        action="store_true",
        help="print not_covered ids and exit",
    )
    args = parser.parse_args(argv)

    not_covered = load_not_covered_ids()
    if args.list_not_covered:
        print("\n".join(not_covered))
        return 0
    if args.exploratory_root is None:
        raise SystemExit("--exploratory-root is required (unless --list-not-covered)")

    cfg = ArmConfig(prompt_file="state/prompt.md")
    assert_frozen_prompt(cfg, allow_dev=bool(args.dev_rows_file))

    rows_by_id = {r["id"]: r for r in load_request_rows()}
    resolve_fn: Any = None
    turns_fn: Any = None

    if args.dev_rows_file:
        from scripts.eval.part_g_arm.state.harness import start_state as harness_start

        dev_doc = json.loads(args.dev_rows_file.read_text(encoding="utf-8"))
        wanted = args.row or [r["id"] for r in dev_doc["rows"]]
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

        def _resolve_dev(row: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
            if row.get("_dev_row"):
                return harness_start(row["_dev_row"]), {
                    "row": row["id"],
                    "loaded": True,
                    "complete": True,
                    "source": "harness.start_state",
                }
            return resolve_exploratory_start(row)

        def _turns_dev(row: dict[str, Any], state: dict[str, Any] | None) -> list[str]:
            if row.get("_dev_row"):
                return list(row["_dev_row"]["turns"])
            return turns_for_row(row, state)

        resolve_fn = _resolve_dev
        turns_fn = _turns_dev
    else:
        covered = load_covered_ids()
        wanted = args.row or list(not_covered)
        for rid in wanted:
            if rid in covered:
                raise SystemExit(f"exploratory refuses covered row {rid!r}")
            if rid not in not_covered:
                raise SystemExit(f"exploratory refuses unknown/not-listed row {rid!r}")
            if rid not in rows_by_id:
                raise SystemExit(f"unknown row id {rid!r}")

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

        facts = model_facts(cfg)
        llm = ChatOllama(
            model=cfg.model,
            temperature=cfg.temperature,
            reasoning=cfg.think,
            num_ctx=cfg.num_ctx,
            num_predict=cfg.num_predict,
            client_kwargs={"timeout": cfg.call_timeout_s},
        ).bind_tools(combined_specs())

    return run_exploratory_batch(
        out_dir=args.exploratory_root,
        wanted=wanted,
        cfg=cfg,
        llm=llm,
        arm=arm,
        facts=facts,
        rows_by_id=rows_by_id,
        stop_after=args.stop_after,
        resolve_fn=resolve_fn,
        turns_fn=turns_fn,
    )


if __name__ == "__main__":
    raise SystemExit(main())
