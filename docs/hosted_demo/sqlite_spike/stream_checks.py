"""Throwaway streaming check. Fake parsers through compile_graph. Not product code.

    uv run python docs/hosted_demo/sqlite_spike/stream_checks.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import typing
from dataclasses import is_dataclass
from pathlib import Path

from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import MemorySaver

ROOT = Path(__file__).resolve().parents[3]
MODES = ["values", "updates", "checkpoints", "tasks", "debug", "messages", "custom"]


def _summary(chunk):
    if isinstance(chunk, dict):
        keys = sorted(chunk)[:8]
        kind = chunk.get("type") or chunk.get("name")
        return {"dict_keys": keys, "type": kind, "name": chunk.get("name")}
    if isinstance(chunk, (list, tuple)) and chunk:
        return {"tuple_len": len(chunk), "first": type(chunk[0]).__name__}
    return {"type": type(chunk).__name__}


def _task_kind(chunk) -> tuple[str | None, str | None]:
    data = chunk
    if isinstance(chunk, dict) and "payload" in chunk and "type" in chunk:
        data = chunk["payload"]
        outer = chunk.get("type")
    else:
        outer = None
    if not isinstance(data, dict):
        return outer, None
    name = data.get("name")
    if "triggers" in data:
        return "start", name
    if "result" in data or "error" in data:
        return "result", name
    return outer, name


def _fingerprint(values: dict) -> dict:
    def norm(value):
        if is_dataclass(value):
            return {"__type__": type(value).__name__, **norm(value.__dict__)}
        if isinstance(value, dict):
            return {str(k): norm(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [norm(v) for v in value]
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return {"__repr__": repr(value)}

    draft = []
    for slot in values.get("team_draft") or []:
        species = getattr(getattr(slot, "species", None), "value", None)
        locked = bool(getattr(slot, "locked", False)) if not is_dataclass(slot) else None
        if is_dataclass(slot):
            locked = all(getattr(slot, name).locked for name in ("role", "species", "ability", "item", "moveset", "spread", "nature"))
            species = slot.species.value
        draft.append({"species": species, "locked": locked})
    prov = values.get("provisional_slot")
    return {
        "turn": values.get("turn"),
        "pending_kind": (values.get("pending_presentation") or {}).get("kind"),
        "turn_intent": values.get("turn_intent"),
        "draft": draft,
        "provisional": norm(prov),
        "team_draft": norm(values.get("team_draft")),
    }


class Box:
    def __init__(self) -> None:
        self.mode = "rain"
        self.events: list[tuple[str, float]] = []

    def bootstrap(self, payload: dict) -> dict:
        self.events.append(("bootstrap-start", time.perf_counter()))
        if self.mode == "sleep":
            time.sleep(0.6)
        elif self.mode == "raise":
            raise RuntimeError("fake bootstrap parser failed")
        self.events.append(("bootstrap-end", time.perf_counter()))
        if self.mode == "six":
            return {
                "direction_text": None,
                "anchor_text": "Pelipper",
                "pool_entries": ["Incineroar", "Rillaboom", "Amoonguss", "Kingambit", "Flutter Mane"],
                "delegated": False,
                "ownership_mode": None,
            }
        return {
            "direction_text": "Rain",
            "anchor_text": "Pelipper",
            "pool_entries": None,
            "delegated": False,
            "ownership_mode": None,
        }

    def turn(self, payload: dict) -> dict:
        self.events.append(("turn-start", time.perf_counter()))
        if self.mode == "raise":
            raise RuntimeError("fake turn parser failed")
        self.events.append(("turn-end", time.perf_counter()))
        return {"turn_intent": "pending_response", "message": "unused"}


def _graph(box: Box):
    from recommender.graph import compile_graph

    return compile_graph(
        checkpointer=MemorySaver(),
        bootstrap_intake_parser=RunnableLambda(box.bootstrap),
        turn_intent_parser=RunnableLambda(box.turn),
    )


def _run_invoke(box: Box, steps: list[tuple[str, str]]):
    from recommender.session import DEFAULT_FORMAT_ID, thread_config

    graph = _graph(box)
    config = thread_config("invoke")
    graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config)
    nodes: list[list[str]] = []
    for mode, text in steps:
        box.mode = mode
        graph.invoke({"pending_input": text}, config)
    values = graph.get_state(config).values
    return _fingerprint(values), nodes


def _run_stream(box: Box, steps: list[tuple[str, str]], mode: str = "tasks"):
    from recommender.session import DEFAULT_FORMAT_ID, thread_config

    graph = _graph(box)
    config = thread_config("stream")
    seen: list[str] = []
    for chunk in graph.stream({"format_id": DEFAULT_FORMAT_ID}, config, stream_mode=mode):
        kind, name = _task_kind(chunk)
        if kind == "start" and name:
            seen.append(name)
    user_steps = []
    for step_mode, text in steps:
        box.mode = step_mode
        names = []
        for chunk in graph.stream({"pending_input": text}, config, stream_mode=mode):
            kind, name = _task_kind(chunk)
            if kind == "start" and name:
                names.append(name)
        user_steps.append(names)
    values = graph.get_state(config).values
    return _fingerprint(values), {"opening": seen, "user_steps": user_steps}


def equivalence() -> dict:
    def drive(kind: str, steps: list[tuple[str, str]]):
        box = Box()
        if kind == "invoke":
            fp, _ = _run_invoke(box, steps)
            return fp
        fp, _ = _run_stream(box, steps)
        return fp

    baseline = [("rain", "Rain with Pelipper"), ("rain", "yes"), ("rain", "yes")]
    six = (
        "Pelipper @ Damp Rock; Incineroar @ Safety Goggles; Rillaboom @ Assault Vest; "
        "Amoonguss @ Sitrus Berry; Kingambit @ Black Glasses; Flutter Mane @ Choice Specs"
    )
    out = {}
    for name, steps in (
        ("baseline", baseline),
        ("six_paste", [("six", six)]),
    ):
        left = drive("invoke", steps)
        right = drive("stream", steps)
        out[name] = {"equal": left == right, "invoke_turn": left["turn"], "stream_turn": right["turn"]}
        if left != right:
            out[name]["invoke_pending"] = left["pending_kind"]
            out[name]["stream_pending"] = right["pending_kind"]
            out[name]["draft_equal"] = left["draft"] == right["draft"]
    # accept-defaults: same reply rule, compare the trace of turns
    out["accept_defaults"] = _compare_walks()
    return out


def _compare_walks() -> dict:
    from recommender.session import DEFAULT_FORMAT_ID, thread_config
    from recommender.state import all_locked

    def trace(use_stream: bool) -> list[dict]:
        box = Box()
        graph = _graph(box)
        config = thread_config("walk")
        if use_stream:
            list(graph.stream({"format_id": DEFAULT_FORMAT_ID}, config, stream_mode="tasks"))
        else:
            graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config)
        rows = []
        replies = {
            "bootstrap_intake": "Rain with Pelipper",
            "candidate_selection": "yes",
            "full_build_confirmation": "yes",
            "completion_preference": "1",
        }
        for _ in range(24):
            values = graph.get_state(config).values
            locked = sum(bool(all_locked(slot)) for slot in values.get("team_draft") or [])
            kind = (values.get("pending_presentation") or {}).get("kind")
            if locked == 6:
                rows.append({"turn": values.get("turn"), "locked": locked, "pending": kind})
                break
            text = replies.get(kind or "")
            if text is None:
                rows.append({"turn": values.get("turn"), "locked": locked, "pending": kind, "stopped": True})
                break
            box.mode = "rain"
            if use_stream:
                list(graph.stream({"pending_input": text}, config, stream_mode="tasks"))
            else:
                graph.invoke({"pending_input": text}, config)
            values = graph.get_state(config).values
            rows.append(
                {
                    "user": text,
                    "turn": values.get("turn"),
                    "locked": sum(bool(all_locked(slot)) for slot in values.get("team_draft") or []),
                    "pending": (values.get("pending_presentation") or {}).get("kind"),
                    "provisional": getattr(values.get("provisional_slot"), "species", None),
                }
            )
        final = graph.get_state(config).values
        return rows, _fingerprint(final)

    left_rows, left_fp = trace(False)
    right_rows, right_fp = trace(True)
    return {
        "equal": left_rows == right_rows and left_fp == right_fp,
        "invoke_steps": len(left_rows),
        "stream_steps": len(right_rows),
        "invoke_final_turn": left_fp["turn"],
        "stream_final_turn": right_fp["turn"],
    }


def start_signal() -> dict:
    from recommender.session import DEFAULT_FORMAT_ID, thread_config

    box = Box()
    box.mode = "sleep"
    graph = _graph(box)
    config = thread_config("signal")
    graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config)
    received = []
    for chunk in graph.stream({"pending_input": "Rain with Pelipper"}, config, stream_mode="tasks"):
        kind, name = _task_kind(chunk)
        received.append((kind, name, time.perf_counter()))
    start = next(t for ev, t in box.events if ev == "bootstrap-start")
    end = next(t for ev, t in box.events if ev == "bootstrap-end")
    early = [
        {"kind": kind, "name": name, "before_parser_return": ts < end}
        for kind, name, ts in received
        if ts < end
    ]
    return {
        "events": [{"kind": k, "name": n} for k, n, _ in received],
        "visible_before_parser_returned": early,
        "parser_slept_s": round(end - start, 3),
    }


def node_lists() -> dict:
    _, baseline = _run_stream(Box(), [("rain", "Rain with Pelipper"), ("rain", "yes"), ("rain", "yes")])
    six = (
        "Pelipper @ Damp Rock; Incineroar @ Safety Goggles; Rillaboom @ Assault Vest; "
        "Amoonguss @ Sitrus Berry; Kingambit @ Black Glasses; Flutter Mane @ Choice Specs"
    )
    box = Box()
    _, six_nodes = _run_stream(box, [("rain", six)])
    return {"baseline_user_steps": baseline["user_steps"], "six_paste_user_steps": six_nodes["user_steps"]}


def _drive(graph, config, use_stream: bool, text: str) -> str | None:
    try:
        if use_stream:
            list(graph.stream({"pending_input": text}, config, stream_mode="tasks"))
        else:
            graph.invoke({"pending_input": text}, config)
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    return None


def failure_paths() -> dict:
    import threading

    from recommender.session import DEFAULT_FORMAT_ID, thread_config

    def once(use_stream: bool, mode: str) -> dict:
        box = Box()
        box.mode = mode
        graph = _graph(box)
        config = thread_config("fail")
        graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config)
        err = _drive(graph, config, use_stream, "Rain with Pelipper")
        values = graph.get_state(config).values
        return {
            "turn": values.get("turn"),
            "pending": (values.get("pending_presentation") or {}).get("kind"),
            "error": err,
        }

    def timed(use_stream: bool) -> dict:
        box = Box()
        box.mode = "sleep"
        graph = _graph(box)
        config = thread_config("slow")
        graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config)
        holder: dict = {}

        def work() -> None:
            holder["error"] = _drive(graph, config, use_stream, "Rain with Pelipper")

        thread = threading.Thread(target=work)
        t0 = time.perf_counter()
        thread.start()
        time.sleep(0.2)
        poll_t0 = time.perf_counter()
        mid = graph.get_state(config).values
        poll_s = time.perf_counter() - poll_t0
        alive_at_deadline = thread.is_alive() and (time.perf_counter() - t0) < 0.5
        thread.join()
        final = graph.get_state(config).values
        return {
            "mid_turn": mid.get("turn"),
            "poll_blocked_s": round(poll_s, 3),
            "still_running_at_0_5s": alive_at_deadline,
            "final_turn": final.get("turn"),
            "error": holder.get("error"),
        }

    raised = {"invoke": once(False, "raise"), "stream": once(True, "raise")}
    slow = {"invoke": timed(False), "stream": timed(True)}
    return {
        "parser_raise": raised,
        "raise_equal": raised["invoke"] == raised["stream"],
        "sleep": slow,
        "sleep_equal": slow["invoke"] == slow["stream"],
    }


def mode_probe() -> dict:
    from langgraph.graph import END, START, StateGraph
    from typing_extensions import TypedDict

    class S(TypedDict):
        n: int

    def node(state: S) -> dict:
        time.sleep(0.2)
        return {"n": state["n"] + 1}

    g = StateGraph(S)
    g.add_node("slow", node)
    g.add_edge(START, "slow")
    g.add_edge("slow", END)
    app = g.compile()
    found = []
    try:
        from langgraph.types import StreamMode

        found = list(typing.get_args(StreamMode))
    except Exception as exc:
        found = [f"error {exc}"]
    emitted = {}
    for mode in MODES:
        t0 = time.perf_counter()
        rows = []
        try:
            for chunk in app.stream({"n": 0}, stream_mode=mode):
                rows.append({"at_s": round(time.perf_counter() - t0, 3), "summary": _summary(chunk), "kind": _task_kind(chunk)[0]})
        except Exception as exc:
            rows.append({"error": f"{type(exc).__name__}: {exc}"})
        emitted[mode] = rows
    return {"stream_mode_args": found, "tiny_graph": emitted}


def mode_probe_1214() -> dict:
    code = r"""
import typing, time
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import StreamMode
class S(TypedDict):
    n: int
def node(state):
    time.sleep(0.2)
    return {"n": state["n"] + 1}
g = StateGraph(S)
g.add_node("slow", node)
g.add_edge(START, "slow")
g.add_edge("slow", END)
app = g.compile()
out = {"stream_mode_args": list(typing.get_args(StreamMode)), "tiny_graph": {}}
for mode in ["values", "updates", "checkpoints", "tasks", "debug", "messages", "custom"]:
    t0 = time.perf_counter()
    rows = []
    try:
        for chunk in app.stream({"n": 0}, stream_mode=mode):
            kind = None
            if isinstance(chunk, dict) and "triggers" in chunk:
                kind = "start"
            elif isinstance(chunk, dict) and ("result" in chunk or "error" in chunk):
                kind = "result"
            elif isinstance(chunk, dict) and chunk.get("type") in ("task", "task_result", "checkpoint"):
                kind = chunk.get("type")
            rows.append({"at_s": round(time.perf_counter() - t0, 3), "kind": kind, "type": type(chunk).__name__})
    except Exception as exc:
        rows.append({"error": f"{type(exc).__name__}: {exc}"})
    out["tiny_graph"][mode] = rows
import importlib.metadata as m
out["langgraph"] = m.version("langgraph")
print(__import__("json").dumps(out))
"""
    proc = subprocess.run(
        ["uv", "run", "--with", "langgraph==1.2.14", "python", "-c", code],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return {"error": proc.stderr[-2000:], "returncode": proc.returncode}
    return json.loads(proc.stdout)


def main() -> None:
    os.environ["RECOMMENDER_TOOL_LOG"] = "/tmp/hosted_demo_stream_spike_tool_log.jsonl"
    os.chdir(ROOT)
    report = {
        "modes_installed": mode_probe(),
        "modes_1_2_14": mode_probe_1214(),
        "start_signal": start_signal(),
        "failure_paths": failure_paths(),
        "node_lists": node_lists(),
        "equivalence": equivalence(),
    }
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
