"""A4: terminal fallback on empty answer and on tool-call cap hit."""

from __future__ import annotations

from scripts.eval.part_g_arm.state.guard_terminal import build_fallback_reply


def test_a4_empty_answer_fallback_nonempty():
    calls = [
        {
            "name": "get_typing",
            "result": {"species": "Toxapex", "types": ["Water", "Poison"]},
            "result_status": "ok",
        }
    ]
    text = build_fallback_reply(calls)
    assert text.strip()
    assert "Toxapex" in text or "types" in text
    assert "get_typing" in text


def test_a4_cap_hit_fallback():
    calls = [
        {
            "name": "read_team",
            "result": {"status": "refused", "guard_blocked": True, "message": "cap"},
            "result_status": "refused",
        }
    ]
    blocked = [{"name": "get_typing", "reason": "per-turn tool call cap (16)"}]
    text = build_fallback_reply(calls, blocked_calls=blocked, cap_hit=True)
    assert text.strip()
    assert "cap" in text.lower()
    assert "Refused" in text


def test_a4_refused_names_class_reason():
    calls = [
        {
            "name": "unlock_slot",
            "result": {
                "status": "refused",
                "guard_blocked": True,
                "message": "Refused unlock_slot: not allowed for request class ASK.",
                "class": "ASK",
            },
            "result_status": "refused",
        }
    ]
    text = build_fallback_reply(calls)
    assert "unlock_slot" in text
    assert "ASK" in text or "Refused" in text
