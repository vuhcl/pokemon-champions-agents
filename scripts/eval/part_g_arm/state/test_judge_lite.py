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


def _judge_retry_llm(*, retry_ai):
    """Shared fake LLM: first answer claims a lock; later invokes return retry_ai."""

    class _AI:
        def __init__(self, content="", tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls or []
            self.response_metadata = {}

    class LLM:
        def __init__(self):
            self.n = 0
            self.retry_invoke_on = None

        def invoke(self, messages):
            self.n += 1
            if self.n == 1:
                return _AI(content="I locked Pelipper in slot 1.")
            self.retry_invoke_on = self
            return retry_ai if not callable(retry_ai) else retry_ai(self, messages)

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

    return LLM()


def test_judge_empty_retry_keeps_raw_with_labels():
    """FU24 §3: empty retry content → keep raw + apply labels (not final_text '')."""
    from scripts.eval.part_g_arm.config import ArmConfig
    from scripts.eval.part_g_arm.state.harness import run_turn
    from scripts.eval.part_g_arm.state.tools import (
        set_draft,
        set_guard,
        set_judge,
        set_tool_fields,
        set_wrapper,
    )

    class _AI:
        def __init__(self, content="", tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls or []
            self.response_metadata = {}

    llm = _judge_retry_llm(retry_ai=_AI(content=""))
    set_tool_fields(True)
    set_wrapper(True)
    set_draft(True)
    set_guard(True)
    set_judge(True)
    try:
        cfg = ArmConfig(prompt_file="state/prompt_guard.md", enforce_first_turn_tool=False)
        st2, rec = run_turn(
            cfg, llm, None, empty_team(), "Lock Pelipper in slot 1.", prior_messages=[]
        )
        j = rec["judge"]
        assert j.get("retry_used") is True
        assert j.get("retried_answer") == ""
        assert j.get("raw_answer")
        assert (rec.get("final_text") or "").strip()
        assert rec["final_text"] != ""
        assert j["post_judge_answer"] == rec["final_text"]
        # Labels applied to raw (mutation line or unverified), not blank.
        assert "locked" in (j["raw_answer"] or "").casefold()
    finally:
        set_judge(False)
        set_guard(False)
        set_draft(False)
        set_wrapper(False)
        set_tool_fields(False)


def test_judge_tool_call_retry_uses_unbound_and_keeps_raw_if_empty():
    """FU24 §3: retry unwraps bind_tools; tool-call-only empty content keeps raw."""
    from scripts.eval.part_g_arm.config import ArmConfig
    from scripts.eval.part_g_arm.state.harness import _llm_without_tools, run_turn
    from scripts.eval.part_g_arm.state.tools import (
        set_draft,
        set_guard,
        set_judge,
        set_tool_fields,
        set_wrapper,
    )

    class _AI:
        def __init__(self, content="", tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls or []
            self.response_metadata = {}

    class Bare:
        def __init__(self):
            self.invokes = 0

        def invoke(self, messages):
            self.invokes += 1
            # Unbound path: still empty text (no tools to call).
            return _AI(content="")

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

    class Bound:
        """Simulates llm.bind_tools(...): outer would emit tool_calls."""

        def __init__(self, bare: Bare):
            self.bound = bare
            self.outer_invokes = 0
            self.n = 0

        def invoke(self, messages):
            self.n += 1
            self.outer_invokes += 1
            if self.n == 1:
                return _AI(content="I locked Pelipper in slot 1.")
            # If retry incorrectly uses the bound llm:
            return _AI(
                content="",
                tool_calls=[{"id": "1", "name": "lock_fields", "args": {"slot": 1}}],
            )

        def bind_tools(self, _specs):
            return self

        def with_structured_output(self, _schema):
            return self.bound.with_structured_output(_schema)

    bare = Bare()
    llm = Bound(bare)
    assert _llm_without_tools(llm) is bare

    set_tool_fields(True)
    set_wrapper(True)
    set_draft(True)
    set_guard(True)
    set_judge(True)
    try:
        cfg = ArmConfig(prompt_file="state/prompt_guard.md", enforce_first_turn_tool=False)
        _st, rec = run_turn(
            cfg, llm, None, empty_team(), "Lock Pelipper in slot 1.", prior_messages=[]
        )
        j = rec["judge"]
        assert j.get("retry_used") is True
        assert bare.invokes >= 1  # retry hit unbound
        assert (rec.get("final_text") or "").strip()
        assert j.get("retried_answer") == ""
        assert "locked" in (j.get("raw_answer") or "").casefold()
    finally:
        set_judge(False)
        set_guard(False)
        set_draft(False)
        set_wrapper(False)
        set_tool_fields(False)
