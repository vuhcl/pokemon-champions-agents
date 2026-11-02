"""Calc preflight + halt-and-resume harness tests (follow-up 13 Part H).

Does not touch tool schemas, prompts, or tool result shapes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from recommender.calc_client import CalcClient, CalcClientError
from scripts.eval.part_g_arm.state.calc_infra import (
    cheap_health,
    classify_calc_failure,
    run_preflight,
)


def test_a_preflight_passes_against_pinned_service():
    """(a) Live preflight against the pinned calc on :4173."""
    client = CalcClient()
    try:
        client.health(timeout=1.0)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"calc service down: {exc}")
    pf = run_preflight(client)
    assert pf["ok"] is True, pf.get("errors")
    assert pf["probes"]["speed_stage_scarf_tw"]["got"] == 651
    assert pf["probes"]["speed_paralyzed_scarf"]["got"] == 108
    assert pf["probes"]["damage_mega_ability"]["got"] == [270, 318]
    assert pf["probes"]["damage_recoil"]["got"] == [76, 90]


def test_b_preflight_fails_when_service_down():
    """(b) Preflight fails when nothing answers on the URL."""
    client = CalcClient("http://127.0.0.1:1")
    pf = run_preflight(client)
    assert pf["ok"] is False
    assert pf["errors"]
    assert classify_calc_failure(pf.get("classification") or pf["errors"][0]) in {
        "infrastructure",
        "input_refusal",
    }
    # Health failure is infrastructure.
    assert pf.get("classification") == "infrastructure" or any(
        "health" in e.lower() or "refused" in e.lower() or "errno" in e.lower()
        for e in pf["errors"]
    )


def test_c_preflight_fails_on_injected_wrong_value(monkeypatch):
    """(c) Wrong Spe probe value → preflight not ok."""
    from scripts.eval.part_g_arm.state import calc_infra as mod

    real = CalcClient()
    try:
        real.health(timeout=1.0)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"calc service down: {exc}")

    monkeypatch.setattr(mod, "_apply_stage_scarf_tw_para", lambda *a, **k: 999)
    pf = run_preflight(real)
    assert pf["ok"] is False
    assert any("651" in e or "probe a" in e for e in pf["errors"])


def test_d_classify_infra_vs_input_refusal():
    """(d) Transport death vs unknown-species / bad args."""
    assert (
        classify_calc_failure(
            CalcClientError(0, {"error": "[Errno 61] Connection refused"})
        )
        == "infrastructure"
    )
    assert (
        classify_calc_failure(
            CalcClientError(500, {"error": "worker died"})
        )
        == "infrastructure"
    )
    assert (
        classify_calc_failure(
            CalcClientError(400, {"error": "unknown Champions species: FakeMon"})
        )
        == "input_refusal"
    )
    assert (
        classify_calc_failure(
            {
                "status": "error",
                "error_kind": "calc_error",
                "message": "{'error': '[Errno 61] Connection refused'}",
            }
        )
        == "infrastructure"
    )
    assert (
        classify_calc_failure(
            {
                "status": "error",
                "error_kind": "bad_arguments",
                "message": "stage must be an integer",
            }
        )
        == "input_refusal"
    )
    assert (
        classify_calc_failure(
            {
                "status": "error",
                "error_kind": "calc_error",
                "message": "unknown Champions species: Foo",
            }
        )
        == "input_refusal"
    )


def _stub_row(rid: str) -> dict[str, Any]:
    return {
        "id": rid,
        "prompt": "ping",
        "state": "dev",
        "class": "DEV",
        "acceptance": "",
        "claim_types": "",
        "raw": "",
        "_dev_row": {
            "id": rid,
            "start": "empty",
            "turns": ["hello"],
        },
    }


def test_e_mid_row_infra_reruns_once_clean_score(tmp_path: Path, monkeypatch):
    """(e) Stubbed mid-row infra → one restart+rerun; clean attempt is finished."""
    from scripts.eval.part_g_arm.config import ArmConfig
    from scripts.eval.part_g_arm.state import request_set_runner as rsr
    from scripts.eval.part_g_arm.state.stub_llm import StubLLM
    from recommender.arm_tools import ArmTools

    calls = {"n": 0}

    def fake_run_row(row, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "id": row["id"],
                "loaded": True,
                "turns": [
                    {
                        "tool_calls": [
                            {
                                "name": "calc_damage",
                                "result": {
                                    "status": "error",
                                    "error_kind": "calc_error",
                                    "message": "[Errno 61] Connection refused",
                                },
                            }
                        ],
                        "final_text": "no usable answer",
                        "no_usable_answer": True,
                    }
                ],
            }
        return {
            "id": row["id"],
            "loaded": True,
            "turns": [
                {
                    "tool_calls": [],
                    "final_text": "ok",
                    "replace_true_calls": 0,
                }
            ],
            "replace_true_turns": [],
        }

    monkeypatch.setattr(rsr, "run_row", fake_run_row)
    monkeypatch.setattr(
        rsr,
        "run_preflight",
        lambda *_a, **_k: {"ok": True, "probes": {}, "errors": []},
    )
    monkeypatch.setattr(rsr, "cheap_health", lambda *_a, **_k: {"ok": True})

    restarts: list[str] = []

    class FakeSup:
        def ensure_running(self):
            return None

        def restart(self, *, reason: str = ""):
            restarts.append(reason)

        def snapshot(self):
            return {"restart_count": len(restarts), "restart_timestamps": list(restarts)}

    out = tmp_path / "run"
    cfg = ArmConfig(prompt_file="state/prompt.md")
    arm = ArmTools(regulation=cfg.regulation, allow_live=False, calc=CalcClient())
    rc = rsr.run_batch(
        out_dir=out,
        wanted=["R1"],
        cfg=cfg,
        llm=StubLLM(),
        arm=arm,
        facts={"digest": "x", "stub": True},
        rows_by_id={"R1": _stub_row("R1")},
        supervisor=FakeSup(),
        skip_calc_preflight=False,
        calc_client=CalcClient(),
    )
    assert rc == 0
    assert calls["n"] == 2
    assert len(restarts) == 1
    progress = json.loads((out / "progress.json").read_text())
    assert "R1" in progress["finished"]
    entry = progress["transcript_by_id"]["R1"]
    assert entry.get("infra_rerun") is True
    assert entry["turns"][0]["final_text"] == "ok"
    record = json.loads((out / "run_record.json").read_text())
    assert record["interrupted_rows"]
    assert "preflight" in record
    assert "calc_supervisor" in record


def test_f_second_infra_on_row_halts(tmp_path: Path, monkeypatch):
    """(f) Two infra failures on one row → halt; row not finished."""
    from scripts.eval.part_g_arm.config import ArmConfig
    from scripts.eval.part_g_arm.state import request_set_runner as rsr
    from scripts.eval.part_g_arm.state.stub_llm import StubLLM
    from recommender.arm_tools import ArmTools

    def always_infra(row, **kwargs):
        return {
            "id": row["id"],
            "loaded": True,
            "turns": [
                {
                    "tool_calls": [
                        {
                            "name": "get_speed",
                            "result": {
                                "status": "error",
                                "error_kind": "calc_error",
                                "message": "URLError: timed out",
                            },
                        }
                    ],
                    "final_text": "no usable answer",
                }
            ],
        }

    monkeypatch.setattr(rsr, "run_row", always_infra)
    monkeypatch.setattr(
        rsr, "run_preflight", lambda *_a, **_k: {"ok": True, "probes": {}, "errors": []}
    )
    monkeypatch.setattr(rsr, "cheap_health", lambda *_a, **_k: {"ok": True})

    class FakeSup:
        def ensure_running(self):
            return None

        def restart(self, *, reason: str = ""):
            return None

        def snapshot(self):
            return {"restart_count": 1, "restart_timestamps": ["t"]}

    out = tmp_path / "run"
    cfg = ArmConfig(prompt_file="state/prompt.md")
    arm = ArmTools(regulation=cfg.regulation, allow_live=False, calc=CalcClient())
    rc = rsr.run_batch(
        out_dir=out,
        wanted=["R1", "R2"],
        cfg=cfg,
        llm=StubLLM(),
        arm=arm,
        facts={"digest": "x", "stub": True},
        rows_by_id={"R1": _stub_row("R1"), "R2": _stub_row("R2")},
        supervisor=FakeSup(),
        calc_client=CalcClient(),
    )
    assert rc == 1
    progress = json.loads((out / "progress.json").read_text())
    assert "R1" not in progress["finished"]
    record = json.loads((out / "run_record.json").read_text())
    assert record["halt"]["reason"] == "second_infra_on_row"
    assert record["halt"]["at_row"] == "R1"


def test_g_resume_keeps_completed_rows(tmp_path: Path, monkeypatch):
    """(g) After a halt, resume skips finished rows and continues at the failed one."""
    from scripts.eval.part_g_arm.config import ArmConfig
    from scripts.eval.part_g_arm.state import request_set_runner as rsr
    from scripts.eval.part_g_arm.state.stub_llm import StubLLM
    from recommender.arm_tools import ArmTools

    out = tmp_path / "run"
    # Seed progress: A already finished.
    out.mkdir(parents=True)
    (out / "progress.json").write_text(
        json.dumps(
            {
                "finished": ["A"],
                "transcript_by_id": {
                    "A": {
                        "id": "A",
                        "loaded": True,
                        "turns": [{"final_text": "done", "tool_calls": []}],
                    }
                },
            }
        )
        + "\n"
    )

    seen: list[str] = []

    def fake_run_row(row, **kwargs):
        seen.append(row["id"])
        return {
            "id": row["id"],
            "loaded": True,
            "turns": [{"final_text": "ok", "tool_calls": [], "replace_true_calls": 0}],
            "replace_true_turns": [],
        }

    monkeypatch.setattr(rsr, "run_row", fake_run_row)
    monkeypatch.setattr(
        rsr, "run_preflight", lambda *_a, **_k: {"ok": True, "probes": {}, "errors": []}
    )
    monkeypatch.setattr(rsr, "cheap_health", lambda *_a, **_k: {"ok": True})

    class FakeSup:
        def ensure_running(self):
            return None

        def restart(self, *, reason: str = ""):
            return None

        def snapshot(self):
            return {"restart_count": 0, "restart_timestamps": []}

    cfg = ArmConfig(prompt_file="state/prompt.md")
    arm = ArmTools(regulation=cfg.regulation, allow_live=False, calc=CalcClient())
    rc = rsr.run_batch(
        out_dir=out,
        wanted=["A", "B"],
        cfg=cfg,
        llm=StubLLM(),
        arm=arm,
        facts={"digest": "x", "stub": True},
        rows_by_id={"A": _stub_row("A"), "B": _stub_row("B")},
        supervisor=FakeSup(),
        calc_client=CalcClient(),
    )
    assert rc == 0
    assert seen == ["B"]
    progress = json.loads((out / "progress.json").read_text())
    assert progress["finished"] == ["A", "B"]
    assert progress["transcript_by_id"]["A"]["turns"][0]["final_text"] == "done"


def test_h_run_record_fields_present(tmp_path: Path, monkeypatch):
    """(h) run_record carries preflight, supervisor, interrupted_rows."""
    from scripts.eval.part_g_arm.config import ArmConfig
    from scripts.eval.part_g_arm.state import request_set_runner as rsr
    from scripts.eval.part_g_arm.state.stub_llm import StubLLM
    from recommender.arm_tools import ArmTools

    monkeypatch.setattr(
        rsr,
        "run_row",
        lambda row, **k: {
            "id": row["id"],
            "loaded": True,
            "turns": [{"final_text": "ok", "tool_calls": [], "replace_true_calls": 0}],
            "replace_true_turns": [],
        },
    )
    monkeypatch.setattr(
        rsr,
        "run_preflight",
        lambda *_a, **_k: {
            "ok": True,
            "probes": {"speed_stage_scarf_tw": {"ok": True}},
            "errors": [],
            "probe_sources": {"speed_stage_scarf_tw": "x"},
        },
    )
    monkeypatch.setattr(rsr, "cheap_health", lambda *_a, **_k: {"ok": True})

    class FakeSup:
        def ensure_running(self):
            return None

        def restart(self, *, reason: str = ""):
            return None

        def snapshot(self):
            return {
                "restart_count": 0,
                "restart_timestamps": [],
                "events": [],
                "port": 4173,
            }

    out = tmp_path / "run"
    cfg = ArmConfig(prompt_file="state/prompt.md")
    arm = ArmTools(regulation=cfg.regulation, allow_live=False, calc=CalcClient())
    rsr.run_batch(
        out_dir=out,
        wanted=["R1"],
        cfg=cfg,
        llm=StubLLM(),
        arm=arm,
        facts={"digest": "x", "stub": True},
        rows_by_id={"R1": _stub_row("R1")},
        supervisor=FakeSup(),
        calc_client=CalcClient(),
    )
    record = json.loads((out / "run_record.json").read_text())
    assert "preflight" in record
    assert record["preflight"]["ok"] is True
    assert "calc_supervisor" in record
    assert "restart_count" in record["calc_supervisor"]
    assert "interrupted_rows" in record
    assert "failure_policy" in record
    assert "calc_infra" in record["failure_policy"]


def test_cheap_health_ok_or_skip():
    client = CalcClient()
    try:
        client.health(timeout=1.0)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"calc service down: {exc}")
    assert cheap_health(client)["ok"] is True
    dead = cheap_health(CalcClient("http://127.0.0.1:1"))
    assert dead["ok"] is False
    assert dead["classification"] == "infrastructure"
