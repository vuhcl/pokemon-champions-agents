"""Part G arm runner: seed-0 gate, config assertions, and the loop's record shape with a scripted model."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from recommender.arm_tools import ArmTools  # noqa: E402
from scripts.eval.part_g_arm import run_battery  # noqa: E402
from scripts.eval.part_g_arm.config import ArmConfig, system_prompt_hash  # noqa: E402
from scripts.eval.part_g_arm.loop import ArmLoop  # noqa: E402


def test_config_pins_offline_and_explicit_think():
    with pytest.raises(AssertionError):
        ArmConfig(allow_live=True)
    with pytest.raises(AssertionError):
        ArmConfig(think=None)  # type: ignore[arg-type]
    assert ArmConfig().temperature == 0.0 and ArmConfig().think is False
    assert len(system_prompt_hash()) == 64


def _repo(tmp_path, *, section=True, dirty=False):
    r = tmp_path / "repo"
    (r / "docs").mkdir(parents=True)
    (r / "docs/pre_registration.md").write_text("# x\n" + ("## PRE-MD-CLAIM\ntext\n" if section else "## other\n"))
    for cmd in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "c"]):
        subprocess.run(["git", "-C", str(r), *cmd], check=True, capture_output=True)
    if dirty:
        (r / "stray.txt").write_text("x")
    head = subprocess.run(["git", "-C", str(r), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    return r, head


def _seed0(tmp_path):
    p = tmp_path / "s0.json"
    p.write_text(json.dumps({"seed": 0, "items": []}))
    rec = tmp_path / "rec.json"
    rec.write_text("{}")
    return p, rec


def test_seed0_gate_refuses_frozen_path_and_seed0_file_without_flags(tmp_path):
    frozen = ROOT / "scripts/eval/part_g_v4/battery/claim_battery_v4.json"
    with pytest.raises(SystemExit, match="held out"):
        run_battery.seed0_gate(frozen, None, None)
    seed0, _ = _seed0(tmp_path)
    with pytest.raises(SystemExit, match="held out"):
        run_battery.seed0_gate(seed0, None, None)
    seed1 = tmp_path / "s1.json"
    seed1.write_text(json.dumps({"seed": 1, "items": []}))
    run_battery.seed0_gate(seed1, None, None)  # dev batteries pass


def test_seed0_gate_each_refusal_and_the_pass(tmp_path):
    seed0, rec = _seed0(tmp_path)
    ok = lambda *a, **k: []  # noqa: E731
    repo, head = _repo(tmp_path)
    run_battery.seed0_gate(seed0, rec, head, root=repo, verify=ok)  # all conditions met
    with pytest.raises(SystemExit, match="not a commit"):
        run_battery.seed0_gate(seed0, rec, "deadbeef", root=repo, verify=ok)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "n"], check=True)
    with pytest.raises(SystemExit, match="HEAD is not the registration commit"):
        run_battery.seed0_gate(seed0, rec, head, root=repo, verify=ok)
    d_repo, d_head = _repo(tmp_path / "d", dirty=True)
    with pytest.raises(SystemExit, match="not clean"):
        run_battery.seed0_gate(seed0, rec, d_head, root=d_repo, verify=ok)
    n_repo, n_head = _repo(tmp_path / "n", section=False)
    with pytest.raises(SystemExit, match="PRE-MD-CLAIM"):
        run_battery.seed0_gate(seed0, rec, n_head, root=n_repo, verify=ok)
    c_repo, c_head = _repo(tmp_path / "c")
    with pytest.raises(SystemExit, match="run_params verification failed"):
        run_battery.seed0_gate(seed0, rec, c_head, root=c_repo, verify=lambda *a, **k: ["worktree.clean: x"])


class _Scripted:
    """Stands in for ChatOllama: replays AIMessages, one per invoke."""

    def __init__(self, msgs):
        self.msgs, self.calls = list(msgs), 0

    def bind_tools(self, _tools):
        return self

    def invoke(self, _messages):
        self.calls += 1
        return self.msgs.pop(0)


def _call(name, args, i="1"):
    return {"name": name, "args": args, "id": i, "type": "tool_call"}


def test_loop_records_tool_calls_and_final_text_verbatim():
    llm = _Scripted([AIMessage("", tool_calls=[_call("get_typing", {"species": "Glalie-Mega"})]),
                     AIMessage("Glalie-Mega is Ice type.")])
    arm = ArmLoop(ArmConfig(), llm=llm, tools=ArmTools(regulation="champions", allow_live=False))
    r = arm.run_item("Is Glalie-Mega Ice?")
    assert r["final_text"] == "Glalie-Mega is Ice type." and r["stop_reason"] == "final" and r["turns"] == 2
    assert [c["name"] for c in r["tool_calls"]] == ["get_typing"] and r["tool_calls"][0]["result"]["types"] == ["Ice"]


def test_loop_max_turns_has_no_answer_and_bad_tool_is_recorded():
    llm = _Scripted([AIMessage("", tool_calls=[_call("nope", {}, str(i))]) for i in range(3)])
    arm = ArmLoop(ArmConfig(max_turns=2), llm=llm, tools=ArmTools(regulation="champions", allow_live=False))
    r = arm.run_item("x")
    assert r["stop_reason"] == "max_turns" and r["final_text"] == "" and r["turns"] == 2
    assert r["tool_calls"][0]["ok"] is False and r["tool_calls"][0]["result"]["error_kind"] == "unknown_tool"


def test_served_teammate_result_counts_as_ok():
    llm = _Scripted([AIMessage("", tool_calls=[_call("get_usage_teammates", {"species": "Hydreigon", "source": "ingame"})]),
                     AIMessage("done")])
    r = ArmLoop(ArmConfig(), llm=llm, tools=ArmTools(regulation="champions", allow_live=False)).run_item("x")
    assert r["tool_calls"][0]["ok"] is True
