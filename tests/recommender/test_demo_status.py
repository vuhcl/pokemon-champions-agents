"""Hosted-demo status labels and the streaming message path."""

from __future__ import annotations

import os
import threading

os.environ["RECOMMENDER_TOOL_LOG"] = "/tmp/hosted_demo_status_tool_log.jsonl"

from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import MemorySaver

from recommender.demo_status import TurnStatus, run_message
from recommender.graph import build_graph, compile_graph
from recommender.session import DEFAULT_FORMAT_ID, thread_config
from recommender.stage_labels import LABELS, stage_label


def _graph(mode: str):
    def bootstrap(payload: dict) -> dict:
        if mode == "sleep":
            threading.Event().wait(0.4)
        if mode == "raise":
            raise RuntimeError("fake bootstrap parser failed")
        return {
            "direction_text": "Rain",
            "anchor_text": "Pelipper",
            "pool_entries": None,
            "delegated": False,
            "ownership_mode": None,
        }

    def turn(payload: dict) -> dict:
        return {"turn_intent": "pending_response", "message": "unused"}

    return compile_graph(
        checkpointer=MemorySaver(),
        bootstrap_intake_parser=RunnableLambda(bootstrap),
        turn_intent_parser=RunnableLambda(turn),
    )


def _open(graph):
    config = thread_config("status-test")
    graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config)
    return config


def test_every_compiled_node_has_a_label():
    missing = [name for name in build_graph().nodes if name not in LABELS]
    assert missing == []


def test_unknown_node_does_not_return_its_name():
    assert stage_label("not_a_node") == "Working…"
    assert "not_a_node" not in stage_label("not_a_node")
    assert all(label == "Working…" for label in LABELS.values())
    assert all(name not in label for name, label in LABELS.items())


def test_slow_parser_shows_working_then_idle():
    graph = _graph("sleep")
    config = _open(graph)
    status = TurnStatus()
    holder: dict = {}

    def work() -> None:
        holder["values"] = run_message(graph, config, "Rain with Pelipper", status)

    thread = threading.Thread(target=work)
    thread.start()
    seen = []
    for _ in range(50):
        if status.state == "working" and status.stage:
            seen.append((status.state, status.stage))
            break
        threading.Event().wait(0.02)
    thread.join()
    assert seen == [("working", "Working…")]
    assert status.state == "idle"
    assert status.stage is None
    assert status.turn == holder["values"]["turn"]


def test_failing_parser_ends_idle_and_matches_invoke():
    streamed = _graph("raise")
    invoked = _graph("raise")
    status = TurnStatus(state="working", turn=9, stage="Working…")
    stream_config = _open(streamed)
    invoke_config = _open(invoked)
    stream_values = run_message(streamed, stream_config, "Rain with Pelipper", status)
    invoke_values = invoked.invoke({"pending_input": "Rain with Pelipper"}, invoke_config)
    assert status.state == "idle"
    assert status.stage is None
    assert status.turn == stream_values["turn"] == invoke_values["turn"]
    assert stream_values["turn_intent"] == invoke_values["turn_intent"]
    assert (stream_values.get("pending_presentation") or {}).get("kind") == (
        invoke_values.get("pending_presentation") or {}
    ).get("kind")
