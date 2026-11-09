"""In-process turn status for the hosted demo.

The message path is the only writer. POST /key and POST /round do not call it.
The record is not stored in the checkpointer, so a restart drops it.
"""

from __future__ import annotations

from dataclasses import dataclass

from recommender.stage_labels import stage_label


@dataclass
class TurnStatus:
    state: str = "idle"
    turn: int = 0
    stage: str | None = None


def _start_name(chunk: object) -> str | None:
    data = chunk
    if isinstance(chunk, dict) and chunk.get("type") == "task":
        data = chunk.get("payload")
    if isinstance(data, dict) and "triggers" in data and isinstance(data.get("name"), str):
        return data["name"]
    return None


def run_message(graph, config: dict, text: str, status: TurnStatus) -> dict:
    """Stream one user message. Sets working before the stream and idle in a finally."""
    status.state = "working"
    status.stage = None
    try:
        for chunk in graph.stream({"pending_input": text}, config, stream_mode="tasks"):
            name = _start_name(chunk)
            if name:
                status.stage = stage_label(name)
    finally:
        status.state = "idle"
        status.stage = None
        values = graph.get_state(config).values
        status.turn = int(values.get("turn") or 0)
    return values
