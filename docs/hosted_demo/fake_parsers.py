"""Load fake_parser_fixture.json into the two Runnables compile_graph expects.

    uv run python docs/hosted_demo/fake_parsers.py
"""

from __future__ import annotations

import json
from pathlib import Path

from langchain_core.runnables import RunnableLambda

FIXTURE = Path(__file__).with_name("fake_parser_fixture.json")


def load(path: Path = FIXTURE) -> tuple[RunnableLambda, RunnableLambda]:
    data = json.loads(path.read_text())
    bootstrap_map = data["bootstrap"]
    turn_map = data["turn_intent"]
    raises = set(data["raises"])

    def bootstrap(payload: dict) -> dict:
        text = payload.get("user_text") or ""
        if text in bootstrap_map:
            return bootstrap_map[text]
        return bootstrap_map["Rain with Pelipper"]

    def turn(payload: dict) -> dict:
        text = payload.get("user_text") or ""
        if text in raises:
            raise RuntimeError("fake turn parser failed")
        if text in turn_map:
            return turn_map[text]
        return {"turn_intent": "pending_response", "message": "unmapped fixture text"}

    return RunnableLambda(bootstrap), RunnableLambda(turn)


if __name__ == "__main__":
    bootstrap, turn = load()
    rain = bootstrap.invoke({"user_text": "Rain with Pelipper"})
    assert rain["anchor_text"] == "Pelipper"
    lock = turn.invoke({"user_text": "Lock slot 1 Pelipper again."})
    assert lock["turn_intent"] == "lock" and lock["slot_index"] == 1
    try:
        turn.invoke({"user_text": "lock everything"})
    except RuntimeError:
        pass
    else:
        raise SystemExit("expected the fixture to raise")
    print("fake parsers ok")
