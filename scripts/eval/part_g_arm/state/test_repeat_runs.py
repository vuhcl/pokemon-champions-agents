"""Three-run runner support + compare_runs (no covered model)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.eval.part_g_arm.state.compare_runs import compare_entry, compare_runs
from scripts.eval.part_g_arm.state.request_set_runner import resolve_out_dir, run_role


def test_run_role_and_resolve_out_dir(tmp_path: Path):
    assert run_role(1) == "primary"
    assert run_role(2) == "determinism"
    d, rid, role = resolve_out_dir(out_dir=None, runs_root=tmp_path, run_id=1)
    assert d == tmp_path / "run_1" and rid == 1 and role == "primary"
    d2, rid2, role2 = resolve_out_dir(out_dir=tmp_path / "legacy", runs_root=None, run_id=3)
    assert d2 == tmp_path / "legacy" and rid2 == 3 and role2 == "determinism"


def test_compare_equal_and_differ(tmp_path: Path):
    def _row(rid: str, klass: str, text: str, tools: list) -> dict:
        return {
            "id": rid,
            "turns": [
                {
                    "mechanical_class": klass,
                    "final_text": text,
                    "tool_calls": tools,
                    "errors": [],
                }
            ],
        }

    tools = [{"name": "get_typing", "args": {"species": "Venusaur"}, "result": {}}]
    primary = {"r1": _row("r1", "lookup only", "Poison/Grass", tools)}
    same = {"r1": _row("r1", "lookup only", "Poison/Grass", tools)}
    diff = {"r1": _row("r1", "lookup only", "Grass/Poison", tools)}

    for name, data in (("run_1", primary), ("run_2", same), ("run_3", diff)):
        d = tmp_path / name
        d.mkdir()
        (d / "transcript.json").write_text(json.dumps(list(data.values())) + "\n")

    report = compare_runs(tmp_path / "run_1", tmp_path / "run_2", tmp_path / "run_3")
    assert report["vs_run_2"][0]["status"] == "equal"
    assert report["vs_run_3"][0]["status"] == "differ"
    assert report["differ_count"] == 1


def test_compare_error_mismatch():
    primary = {
        "id": "x",
        "turns": [{"mechanical_class": "lookup only", "final_text": "ok", "tool_calls": [], "errors": []}],
    }
    other = {
        "id": "x",
        "turns": [
            {
                "mechanical_class": "lookup only",
                "final_text": "no usable answer",
                "tool_calls": [],
                "errors": ["item_timeout"],
            }
        ],
    }
    got = compare_entry(primary, other, vs_run=2)
    assert got["status"] == "error_mismatch"


def test_stop_after_zero_stamps_run_id(tmp_path: Path):
    """--stop-after 0 writes empty transcript/progress with run_id (no model)."""
    from scripts.eval.part_g_arm.config import ArmConfig
    from scripts.eval.part_g_arm.state.request_set_runner import run_batch
    from scripts.eval.part_g_arm.state.stub_llm import StubLLM
    from recommender.arm_tools import ArmTools
    from recommender.calc_client import CalcClient

    out = tmp_path / "run_1"
    cfg = ArmConfig(prompt_file="state/prompt.md")
    arm = ArmTools(regulation=cfg.regulation, allow_live=False, calc=CalcClient(cfg.calc_base_url))
    rc = run_batch(
        out_dir=out,
        wanted=[],
        cfg=cfg,
        llm=StubLLM(),
        arm=arm,
        facts={"digest": "x", "stub": True},
        rows_by_id={},
        stop_after=0,
        run_id=1,
        role="primary",
    )
    assert rc == 0
    progress = json.loads((out / "progress.json").read_text())
    assert progress.get("run_id") == 1 and progress.get("role") == "primary"
    record = json.loads((out / "run_record.json").read_text())
    assert record.get("run_id") == 1 and record.get("role") == "primary"
    assert json.loads((out / "transcript.json").read_text()) == []
