"""Exploratory mode: isolation + stub/dev only (no real not-covered model run)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.eval.part_g_arm.config import ArmConfig
from scripts.eval.part_g_arm.state.exploratory_runner import (
    README_MARK,
    assert_exploratory_root,
    assert_not_exploratory_dir,
    load_not_covered_ids,
    resolve_exploratory_start,
    run_exploratory_batch,
)
from scripts.eval.part_g_arm.state.request_set_rows import load_request_rows
from scripts.eval.part_g_arm.state.request_set_runner import run_batch
from scripts.eval.part_g_arm.state.stub_llm import StubLLM
from recommender.arm_tools import ArmTools
from recommender.calc_client import CalcClient


def test_not_covered_includes_mt7_mt8_h12():
    ids = load_not_covered_ids()
    assert len(ids) == 31
    for rid in ("MT7", "MT8", "H12", "SC1", "OL7b"):
        assert rid in ids


def test_h12_loader_empty_team_from_row_text():
    rows = {r["id"]: r for r in load_request_rows()}
    state, meta = resolve_exploratory_start(rows["H12"])
    assert state is not None and meta["loaded"] is True
    assert "empty_team" in (meta.get("source") or "")
    assert meta.get("error") is None


def test_load_failure_recorded_not_invented():
    """SC1 fixture refuses to guess — exploratory must surface load_failure, not invent state."""
    rows = {r["id"]: r for r in load_request_rows()}
    state, meta = resolve_exploratory_start(rows["SC1"])
    assert state is None
    assert meta.get("loaded") is False
    assert meta.get("error")


def test_assert_exploratory_root_rejects_registered_layout(tmp_path: Path):
    with pytest.raises(SystemExit, match="exploratory"):
        assert_exploratory_root(tmp_path / "plain_out")
    # Path has 'exploratory' but already hosts registered run_1..3
    root = tmp_path / "exploratory" / "stolen_runs"
    (root / "run_1").mkdir(parents=True)
    (root / "run_1" / "run_record.json").write_text("{}\n")
    with pytest.raises(SystemExit, match="registered"):
        assert_exploratory_root(root)


def test_registered_runner_refuses_exploratory_dir(tmp_path: Path):
    out = tmp_path / "exploratory" / "leak"
    out.mkdir(parents=True)
    (out / "README.md").write_text(f"{README_MARK}\n\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="exploratory"):
        assert_not_exploratory_dir(out)
    cfg = ArmConfig(prompt_file="state/prompt.md")
    arm = ArmTools(regulation=cfg.regulation, allow_live=False, calc=CalcClient(cfg.calc_base_url))
    with pytest.raises(SystemExit, match="exploratory"):
        run_batch(
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


def test_exploratory_stub_on_dev_row_only(tmp_path: Path):
    """Stub + one eev/dev row; never a request-set not-covered id."""
    out = tmp_path / "exploratory" / "stub_dev"
    cfg = ArmConfig(prompt_file="state/prompt.md")
    arm = ArmTools(regulation=cfg.regulation, allow_live=False, calc=CalcClient(cfg.calc_base_url))
    from scripts.eval.part_g_arm.state.harness import start_state as harness_start

    # Prefer fully_locked so start_state is defined (eev/dev only — not a request-set row).
    dev_row = {
        "id": "eev_exploratory_stub",
        "start": "fully_locked",
        "species": "Venusaur",
        "user_slot": 1,
        "turns": ["what types is Venusaur?"],
    }
    rows_by_id = {
        "eev_exploratory_stub": {
            "id": "eev_exploratory_stub",
            "prompt": "what types is Venusaur?",
            "state": "dev",
            "class": "DEV",
            "acceptance": "",
            "claim_types": "",
            "raw": "",
            "_dev_row": dev_row,
        }
    }

    def _resolve(row):
        st = harness_start(row["_dev_row"])
        return st, {"row": row["id"], "loaded": True, "complete": True, "source": "harness"}

    def _turns(row, _state):
        return list(row["_dev_row"]["turns"])

    rc = run_exploratory_batch(
        out_dir=out,
        wanted=["eev_exploratory_stub"],
        cfg=cfg,
        llm=StubLLM(),
        arm=arm,
        facts={"digest": "x", "stub": True},
        rows_by_id=rows_by_id,
        resolve_fn=_resolve,
        turns_fn=_turns,
    )
    assert rc == 0
    readme = (out / "README.md").read_text(encoding="utf-8")
    assert readme.startswith(README_MARK)
    progress = json.loads((out / "exploratory_progress.json").read_text())
    assert progress["mode"] == "exploratory"
    assert "eev_exploratory_stub" in progress["finished"]
    assert not (out / "progress.json").exists()  # never write registered progress name
    transcript = json.loads((out / "transcript.json").read_text())
    assert len(transcript) == 1
    entry = transcript[0]
    assert entry["mode"] == "exploratory"
    assert entry.get("load_failure") is False
    assert "mechanical_class" in (entry["turns"][0] if entry["turns"] else {}) or entry["turns"]
    # Unscored: no class_scorer fields / pass-fail
    assert "pass" not in entry
    assert "score" not in entry
    record = json.loads((out / "run_record.json").read_text())
    assert record["scoring"] == "none"
    assert record["mode"] == "exploratory"


def test_exploratory_records_load_failure_without_model(tmp_path: Path):
    """Synthetic load failure: no invented state; StubLLM never invoked for turns."""
    out = tmp_path / "exploratory" / "load_fail"
    cfg = ArmConfig(prompt_file="state/prompt.md")
    arm = ArmTools(regulation=cfg.regulation, allow_live=False, calc=CalcClient(cfg.calc_base_url))
    stub = StubLLM()
    rows_by_id = {
        "eev_load_fail": {
            "id": "eev_load_fail",
            "prompt": "x",
            "state": "dev",
            "class": "DEV",
            "acceptance": "",
            "claim_types": "",
            "raw": "",
        }
    }

    def _resolve(_row):
        return None, {
            "row": "eev_load_fail",
            "loaded": False,
            "complete": False,
            "source": None,
            "error": "FixtureLoadError: synthetic refuse",
        }

    rc = run_exploratory_batch(
        out_dir=out,
        wanted=["eev_load_fail"],
        cfg=cfg,
        llm=stub,
        arm=arm,
        facts={"digest": "x", "stub": True},
        rows_by_id=rows_by_id,
        resolve_fn=_resolve,
        stop_after=1,
    )
    assert rc == 0
    assert stub.calls == 0
    entry = json.loads((out / "transcript.json").read_text())[0]
    assert entry["load_failure"] is True
    assert entry["loaded"] is False
    assert entry["turns"] == []
    assert "synthetic refuse" in entry["error"]
