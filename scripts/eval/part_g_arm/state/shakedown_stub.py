"""Part 4.1 — stub LLM end-to-end over all covered rows + class scorer."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from recommender.arm_tools import ArmTools
from recommender.calc_client import CalcClient

from scripts.eval.part_g_arm.config import ArmConfig
from scripts.eval.part_g_arm.state.class_scorer import score_transcript
from scripts.eval.part_g_arm.state.request_set_rows import load_covered_ids, load_request_rows
from scripts.eval.part_g_arm.state.request_set_runner import FIXED_RUN_SETTINGS, run_batch
from scripts.eval.part_g_arm.state.stub_llm import StubLLM

HERE = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    out = Path(argv[0]) if argv else Path("/Users/nowaki027/part-g-arm-state-out-stub")
    if out.exists():
        # Fresh stub run directory each time unless resume is intentional.
        for p in ("progress.json", "transcript.json", "run_record.json", "scorer.json"):
            (out / p).unlink(missing_ok=True)

    cfg = ArmConfig(prompt_file="state/prompt.md")
    covered = sorted(load_covered_ids())
    # MT4 stays not-covered for eval but is still in covered_list for load; include it.
    rows_by_id = {r["id"]: r for r in load_request_rows()}
    arm = ArmTools(
        regulation=cfg.regulation,
        allow_live=False,
        calc=CalcClient(cfg.calc_base_url),
        include_damage_rolls=False,
    )
    run_batch(
        out_dir=out,
        wanted=covered,
        cfg=cfg,
        llm=StubLLM(),
        arm=arm,
        facts={"digest": FIXED_RUN_SETTINGS["model_digest"], "stub": True},
        rows_by_id=rows_by_id,
    )
    transcript = json.loads((out / "transcript.json").read_text(encoding="utf-8"))
    assert len(transcript) == len(covered), (len(transcript), len(covered))
    for entry in transcript:
        assert "id" in entry
        for turn in entry.get("turns") or []:
            assert "state_before" in turn and "state_after" in turn
            assert "mechanical_class" in turn
            assert "user" in turn
    scored = score_transcript(transcript)
    (out / "scorer.json").write_text(json.dumps(scored, indent=2) + "\n", encoding="utf-8")
    by = {r["row"]: r for r in scored["per_row"]}
    assert by["MT2"].get("excluded") == "stale_pin"
    assert by["H6"].get("excluded") == "stale_pin"
    hand = [r for r in scored["per_row"] if r.get("excluded") == "hand audit"]
    assert hand, "expected hand-audit exclusions"
    print(
        f"stub ok rows={len(transcript)} hand_audit={len(hand)} "
        f"stale=MT2,H6 out={out}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
