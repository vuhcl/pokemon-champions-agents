"""Judge plumbing without a model: the request carries only the question and the answer text; the runner refuses when a model is loaded."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/eval/part_g_arm/judge"))
import extract as ex  # noqa: E402
import run_judge as rj  # noqa: E402


def test_request_has_only_prompt_and_answer_and_the_pinned_settings():
    req = ex.build_request("Does X have Y?", "No, X does not have Y.")
    assert req["model"] == "gemma4:12b" and req["think"] is False and req["stream"] is False and req["format"] is ex.SCHEMA
    assert req["options"] == {"temperature": 0, "num_ctx": 8192, "num_predict": 2000}
    system, user = req["messages"]
    assert system["content"] == ex.prompt_text() and user["content"] == "Question:\nDoes X have Y?\n\nAnswer:\nNo, X does not have Y."
    assert len(ex.prompt_sha256()) == 64 and ex.SCHEMA["properties"]["claims"]["items"]["properties"]["polarity"]["enum"] == ["T", "F"]


def test_runner_refuses_when_a_model_is_loaded_or_the_digest_differs(tmp_path, monkeypatch):
    items = tmp_path / "i.jsonl"
    items.write_text('{"id":"a","prompt":"q","final_text":"t"}\n')
    monkeypatch.setattr(sys, "argv", ["run_judge", "--items", str(items), "--out", str(tmp_path / "o.jsonl")])
    monkeypatch.setattr(ex, "loaded_models", lambda: ["qwen3.5:latest"])
    with pytest.raises(SystemExit, match="shows .*loaded"):
        rj.main()
    monkeypatch.setattr(ex, "loaded_models", lambda: [])
    monkeypatch.setattr(ex, "local_digest", lambda: "0" * 64)
    with pytest.raises(SystemExit, match="digest"):
        rj.main()


def test_unparseable_or_off_schema_output_is_a_failure_without_repair(monkeypatch):
    monkeypatch.setattr(ex, "_call", lambda *a, **k: {"message": {"content": '{"claims": [{"subject": "a"}]}'}})
    assert ex.extract("q", "t") == {"claims": [], "raw": '{"claims": [{"subject": "a"}]}', "parsed": False}
    monkeypatch.setattr(ex, "_call", lambda *a, **k: {"message": {"content": "not json"}})
    assert ex.extract("q", "t")["parsed"] is False
    good = '{"claims": [{"subject": "a", "predicate": "p", "value": "v", "polarity": "T"}]}'
    monkeypatch.setattr(ex, "_call", lambda *a, **k: {"message": {"content": good}})
    assert ex.extract("q", "t")["parsed"] is True
