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
    parse_user_turns,
    resolve_start_state,
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


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pin_hashes() -> dict[str, str]:
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
    return out


def assert_frozen_prompt(cfg: ArmConfig, *, allow_dev: bool) -> None:
    got = cfg.prompt_hash()
    if got == FROZEN_PROMPT_SHA256:
        return
    if allow_dev:
        print(f"dev override: prompt {got} != frozen {FROZEN_PROMPT_SHA256}", file=sys.stderr)
        return
    raise SystemExit(
        f"refusing to start: prompt sha256 {got} != frozen {FROZEN_PROMPT_SHA256} "
        "(pass --dev to override)"
    )


def assert_row_allowed(row_id: str, *, allow_dev: bool, covered: set[str]) -> None:
    if row_id in covered:
        return
    if allow_dev:
        print(f"dev override: running non-covered row {row_id}", file=sys.stderr)
        return
    raise SystemExit(f"refusing row {row_id!r}: not in covered_list.json (pass --dev to override)")


def run_row(
    row: dict[str, Any],
    *,
    cfg: ArmConfig,
    llm: Any,
    arm: ArmTools,
) -> dict[str, Any]:
    state, meta = resolve_start_state(row)
    if state is None:
        return {
            "id": row["id"],
            "loaded": False,
            "error": meta.get("error"),
            "turns": [],
        }
    turns_out: list[dict[str, Any]] = []
    for user_text in parse_user_turns(row["prompt"]):
        state, record = run_turn(cfg, llm, arm, state, user_text)
        turns_out.append(record)
    return {
        "id": row["id"],
        "loaded": True,
        "start_meta": meta,
        "turns": turns_out,
    }


def build_run_parameters(cfg: ArmConfig, facts: dict[str, Any]) -> dict[str, Any]:
    specs = combined_specs()
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
        "pin_hashes": pin_hashes(),
        "arm_side_adaptations": {
            "select_option_source_default": RUN_PARAMS["select_option_source_default"],
            "primitive_pending_tools": RUN_PARAMS["primitive_tools"],
            "partial_cs_stale_gate": RUN_PARAMS["partial_cs_stale_gate"],
            "solve_spread": "read-only solve_spread tool (L1-to-joint)",
        },
        "allow_live": cfg.allow_live,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out_dir", type=Path, help="transcript directory (outside the repo)")
    parser.add_argument("--row", action="append", default=[], help="row id to run (repeatable)")
    parser.add_argument("--dev", action="store_true", help="allow non-frozen prompt / non-covered rows")
    parser.add_argument("--list-covered", action="store_true", help="print covered ids and exit")
    args = parser.parse_args(argv)

    covered = load_covered_ids()
    if args.list_covered:
        print("\n".join(sorted(covered)))
        return 0

    cfg = ArmConfig(prompt_file="state/prompt.md")
    assert_frozen_prompt(cfg, allow_dev=args.dev)

    rows_by_id = {r["id"]: r for r in load_request_rows()}
    wanted = args.row or sorted(covered)
    for rid in wanted:
        assert_row_allowed(rid, allow_dev=args.dev, covered=covered)
        if rid not in rows_by_id:
            raise SystemExit(f"unknown row id {rid!r}")

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    from scripts.eval.part_g_arm.run_battery import model_facts
    from langchain_ollama import ChatOllama

    try:
        facts = model_facts(cfg)
    except (Exception, SystemExit) as exc:  # noqa: BLE001
        (out_dir / "run_record.json").write_text(
            json.dumps({"error": f"{type(exc).__name__}: {exc}"}, indent=2) + "\n"
        )
        return 1

    arm = ArmTools(
        regulation=cfg.regulation,
        allow_live=False,
        calc=CalcClient(cfg.calc_base_url),
        include_damage_rolls=cfg.damage_rolls_in_result,
    )
    llm = ChatOllama(
        model=cfg.model,
        temperature=cfg.temperature,
        reasoning=cfg.think,
        num_ctx=cfg.num_ctx,
        num_predict=cfg.num_predict,
        client_kwargs={"timeout": cfg.call_timeout_s},
    ).bind_tools(combined_specs())

    transcript = []
    for rid in wanted:
        print(f"running {rid}", file=sys.stderr)
        transcript.append(run_row(rows_by_id[rid], cfg=cfg, llm=llm, arm=arm))

    record = build_run_parameters(cfg, facts)
    (out_dir / "transcript.json").write_text(json.dumps(transcript, indent=2) + "\n", encoding="utf-8")
    (out_dir / "run_record.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
