"""FU20 judge-lite unit tests (checks 1–4)."""

from __future__ import annotations

from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.judge_lite import (
    apply_unverified_labels,
    check_coverage,
    check_entity_number_provenance,
    check_mutation,
    check_state_claims,
)
from recommender.state import Attr


def test_coverage_missing_lookup():
    verdicts = check_coverage(
        [{"class": "LOOKUP"}],
        [],
        "Toxapex is Water/Poison.",
    )
    assert any(v["verdict"] == "unsupported" for v in verdicts)


def test_coverage_ok_with_tool():
    verdicts = check_coverage(
        [{"class": "LOOKUP"}],
        [{"name": "get_typing", "result": {"types": ["Water", "Poison"]}, "result_status": "ok"}],
        "Toxapex is Water/Poison.",
    )
    assert verdicts == []


def test_mutation_unauthorized_lock():
    verdicts = check_mutation(
        [{"name": "lock_fields", "args": {"slot": 1}, "result": {"ok": True}, "result_status": "ok"}],
        allowed={"read_team", "get_typing"},
        confirms_replacement=False,
        state_before=None,
        state_after=None,
        reply="Locked slot 1.",
    )
    assert any(v["claim_span"] == "lock_fields" for v in verdicts)


def test_mutation_stated_but_unperformed():
    st = empty_team()
    verdicts = check_mutation(
        [],
        allowed=set(),
        confirms_replacement=False,
        state_before=st,
        state_after=st,
        reply="I locked Pelipper in slot 1.",
    )
    assert any(v["verdict"] == "contradicted" and v["kind"] == "mutation" for v in verdicts)


def test_state_claims_contradicted_and_unsupported():
    st = empty_team()
    st["team_draft"][0].species = Attr("Pelipper", True)
    # Contradicted empty claim.
    v1, cov = check_state_claims("Slot 1 is empty.", st)
    assert any(v["verdict"] == "contradicted" for v in v1)
    assert cov["patterns_hit"] >= 1
    # Unsupported / wrong species.
    v2, _ = check_state_claims("Slot 1 holds Garchomp.", st)
    assert any(v["verdict"] in ("contradicted", "unsupported") for v in v2)


def test_provenance_unsupported_species_and_number():
    st = empty_team()
    verdicts = check_entity_number_provenance(
        "Zamazenta deals 312 damage.",
        user_text="What about bulk?",
        tool_calls=[],
        state=st,
    )
    assert any(v["kind"] == "provenance" and v["verdict"] == "unsupported" for v in verdicts)


def test_provenance_supported_from_tool():
    st = empty_team()
    verdicts = check_entity_number_provenance(
        "Toxapex is Water/Poison.",
        user_text="What type is Toxapex?",
        tool_calls=[
            {
                "name": "get_typing",
                "result": {"species": "Toxapex", "types": ["Water", "Poison"]},
            }
        ],
        state=st,
    )
    assert not any(v["claim_span"] == "Toxapex" for v in verdicts)


def test_apply_unverified_labels():
    text = apply_unverified_labels(
        "Zamazenta is great.",
        [{"claim_span": "Zamazenta", "verdict": "unsupported", "kind": "provenance"}],
    )
    assert "[unverified]" in text


def test_judge_retry_then_post_cap_labels_mutation_claim():
    """Stated but unperformed mutation → one retry call; post-cap labels if repeated."""
    from scripts.eval.part_g_arm.state.harness import run_turn
    from scripts.eval.part_g_arm.config import ArmConfig
    from scripts.eval.part_g_arm.state.tools import set_draft, set_guard, set_judge, set_tool_fields, set_wrapper

    class _AI:
        def __init__(self, content="", tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls or []
            self.response_metadata = {}

    class RetryLLM:
        def __init__(self):
            self.n = 0

        def invoke(self, messages):
            self.n += 1
            # 1st: final answer claiming a lock with no tools
            if self.n == 1:
                return _AI(content="I locked Pelipper in slot 1.")
            # 2nd: parser structured (if guard on) — return ASK-looking JSON-ish via content
            # Guard parser uses with_structured_output or JSON; may fail → ASK fallback.
            # 3rd would be retry after judge — repeat the bad claim.
            return _AI(content="I locked Pelipper in slot 1.")

        def bind_tools(self, _specs):
            return self

        def with_structured_output(self, _schema):
            class _S:
                def invoke(self_inner, _msgs):
                    return {
                        "uncertain": False,
                        "sub_requests": [
                            {
                                "class": "WRITE",
                                "action": "lock_fields",
                                "numeric_or_explain": False,
                                "confirms_replacement": False,
                            }
                        ],
                    }

            return _S()

    set_tool_fields(True)
    set_wrapper(True)
    set_draft(True)
    set_guard(True)
    set_judge(True)
    try:
        cfg = ArmConfig(prompt_file="state/prompt_guard.md", enforce_first_turn_tool=False)
        llm = RetryLLM()
        st = empty_team()
        # Pre-seed pending asked unused; run_turn will parse then answer.
        st2, rec = run_turn(cfg, llm, None, st, "Lock Pelipper in slot 1.", prior_messages=[])
        assert rec.get("judge")
        j = rec["judge"]
        assert j.get("retries") == 1
        assert j.get("retry_used") is True
        assert j.get("raw_answer")
        assert j.get("retried_answer") is not None
        assert j.get("post_judge_answer")
        # Retry repeated the claim → post-cap mutation line or contradicted verdict path.
        assert (
            "Actual state change" in (j["post_judge_answer"] or "")
            or any(v.get("kind") == "mutation" for v in (j.get("verdicts") or []))
            or "[unverified]" in (j["post_judge_answer"] or "")
        )
        assert llm.n >= 2  # at least answer + retry (parser may add one)
    finally:
        set_judge(False)
        set_guard(False)
        set_draft(False)
        set_wrapper(False)
        set_tool_fields(False)
