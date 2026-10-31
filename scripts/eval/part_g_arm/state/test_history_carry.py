"""History after turn 0: user+assistant text only; turn 0 seed unchanged."""

from __future__ import annotations

from scripts.eval.part_g_arm.config import ArmConfig
from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.request_set_runner import run_row
from scripts.eval.part_g_arm.state.request_set_rows import load_request_rows, resolve_start_state
from recommender.arm_tools import ArmTools
from recommender.calc_client import CalcClient


def _arm() -> ArmTools:
    from recommender.regulation_registry import active_regulation

    return ArmTools(
        regulation=active_regulation(),
        allow_live=False,
        calc=CalcClient("http://127.0.0.1:9"),
    )


class _AI:
    def __init__(self, content: str = "") -> None:
        self.content = content
        self.tool_calls: list = []


class TextOnlyLLM:
    """Always ends the turn with text (no tools)."""

    def __init__(self) -> None:
        self.n = 0
        self.seen: list[list] = []

    def invoke(self, messages: object) -> _AI:
        self.seen.append(list(messages))  # type: ignore[arg-type]
        self.n += 1
        return _AI(content=f"answer-{self.n}")


def test_mt3_t2_receives_seed_t1_text_no_tool_message():
    """Runner turn 0 for MT3 is request-set t2; seed history is t1 user+assistant."""
    rows = {r["id"]: r for r in load_request_rows()}
    st, meta = resolve_start_state(rows["MT3"])
    assert st and meta["loaded"]
    hist = st.get("_message_history") or []
    assert hist[0]["role"] == "user" and "Intimidate" in hist[0]["content"]
    assert hist[1]["role"] == "assistant"

    cfg = ArmConfig(prompt_file="state/prompt.md", enforce_first_turn_tool=False)
    llm = TextOnlyLLM()
    entry = run_row(
        rows["MT3"],
        cfg=cfg,
        llm=llm,
        arm=_arm(),
        turns_fn=lambda _row, _state: ["Suggest a teammate for slot 2."],
    )
    assert entry["loaded"]
    assert llm.seen, "llm was not invoked"
    msgs = llm.seen[0]
    assert not any(type(m).__name__ == "ToolMessage" for m in msgs)
    texts = [getattr(m, "content", "") for m in msgs]
    assert any("Intimidate" in (t or "") for t in texts)
    assert any("Noted" in (t or "") for t in texts)


def test_turn0_seed_unchanged_when_second_turn_runs():
    """Turn 0 still gets seed only; turn 1 gets prior row turns' text (not tools)."""
    cfg = ArmConfig(prompt_file="state/prompt.md", enforce_first_turn_tool=False)
    llm = TextOnlyLLM()
    row = {
        "id": "dev-hist-synth",
        "prompt": "(t1) First ask. (t2) Second ask.",
        "state": "idle",
        "class": "DEV",
        "acceptance": "",
        "claim_types": "",
        "raw": "",
    }
    seed_state = empty_team()
    seed_state["_message_history"] = [
        {"role": "user", "content": "seed-user"},
        {"role": "assistant", "content": "seed-assistant"},
    ]

    def resolve(_row):
        return seed_state, {"loaded": True, "complete": True, "source": "test"}

    entry = run_row(
        row,
        cfg=cfg,
        llm=llm,
        arm=_arm(),
        resolve_fn=resolve,
        turns_fn=lambda _r, _s: ["First ask.", "Second ask."],
    )
    assert len(entry["turns"]) == 2
    assert len(llm.seen) == 2
    t0_texts = [getattr(m, "content", "") for m in llm.seen[0]]
    assert "seed-user" in t0_texts and "seed-assistant" in t0_texts
    assert "First ask." in t0_texts
    assert "Second ask." not in t0_texts
    t1_texts = [getattr(m, "content", "") for m in llm.seen[1]]
    assert "seed-user" not in t1_texts
    assert "First ask." in t1_texts and "answer-1" in t1_texts
    assert "Second ask." in t1_texts
    assert not any(type(m).__name__ == "ToolMessage" for m in llm.seen[1])
