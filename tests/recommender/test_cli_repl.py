"""CLI REPL behavior: landmine, meta, interrupts, E2E smoke."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import MemorySaver

from recommender.cli import handle_line, invoke_user_text, main
from recommender.graph import compile_cli_graph, compile_graph
from recommender.nodes import team_phase
from recommender.nodes_classify import _MISMATCH_MSG
from recommender.present_text import NO_PENDING_MESSAGE, UNMATCHED_REPLY_PREFIX
from recommender.session import DEFAULT_FORMAT_ID, thread_config
from recommender.state import (
    Attr,
    CandidateDiscoveryError,
    Slot,
    TeamReviewResult,
    empty_slot,
)


def _rain_parser():
    return RunnableLambda(
        lambda _: {
            "direction_text": "Rain",
            "anchor_text": "Pelipper",
            "pool_entries": None,
            "delegated": False,
            "ownership_mode": None,
        }
    )


def test_first_turn_invoke_is_format_id_only(tmp_path: Path, monkeypatch):
    payloads: list[dict] = []
    db = tmp_path / "landmine.db"
    real_compile = compile_cli_graph

    def wrapping(*, path=None, bootstrap_intake_parser=None, turn_intent_parser=None):
        graph, saver = real_compile(
            path=path,
            bootstrap_intake_parser=bootstrap_intake_parser,
            turn_intent_parser=turn_intent_parser,
        )
        real_invoke = graph.invoke

        def spy(payload, config=None, **kwargs):
            payloads.append(dict(payload))
            return real_invoke(payload, config=config, **kwargs)

        graph.invoke = spy  # type: ignore[method-assign]
        return graph, saver

    monkeypatch.setattr("recommender.cli.compile_cli_graph", wrapping)
    monkeypatch.setattr(
        "builtins.input", lambda *_a, **_k: (_ for _ in ()).throw(EOFError())
    )
    code = main(["--new", "--db", str(db), "--provider", "none"])
    assert code == 0
    assert payloads
    assert payloads[0] == {"format_id": DEFAULT_FORMAT_ID}
    assert "pending_input" not in payloads[0]


def test_main_prints_calc_startup_warning_to_stderr(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "calc-warn.db"
    monkeypatch.setattr(
        "recommender.cli.calc_startup_warning",
        lambda: "Calc service not reachable at http://127.0.0.1:4173 — test",
    )
    monkeypatch.setattr(
        "builtins.input", lambda *_a, **_k: (_ for _ in ()).throw(EOFError())
    )
    code = main(["--new", "--db", str(db), "--provider", "none"])
    assert code == 0
    err = capsys.readouterr().err
    assert "Calc service not reachable at http://127.0.0.1:4173" in err


def test_main_no_calc_warning_when_reachable(tmp_path: Path, monkeypatch, capsys):
    db = tmp_path / "calc-ok.db"
    monkeypatch.setattr("recommender.cli.calc_startup_warning", lambda: None)
    monkeypatch.setattr(
        "builtins.input", lambda *_a, **_k: (_ for _ in ()).throw(EOFError())
    )
    code = main(["--new", "--db", str(db), "--provider", "none"])
    assert code == 0
    err = capsys.readouterr().err
    assert "Calc service not reachable" not in err


def _locked_archaludon() -> Slot:
    return Slot(
        role=Attr("bulky_attacker", locked=True),
        species=Attr("Archaludon", locked=True),
        ability=Attr("Stamina", locked=True),
        item=Attr("Assault Vest", locked=True),
        moveset=Attr(["Electro Shot"], locked=True),
        spread=Attr({"hp": 32, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 0}, locked=True),
        nature=Attr("Modest", locked=True),
    )


_CANDIDATE_PENDING = {
    "schema_version": 1,
    "kind": "candidate_selection",
    "slot_index": 1,
    "options": [
        {"species": "Meowstic", "source": "need"},
        {"species": "Gardevoir-Mega", "source": "need"},
        {"species": "Sinistcha", "source": "usage"},
    ],
}


def _locked_species(species: str) -> Slot:
    return Slot(
        role=Attr("bulky_attacker", locked=True),
        species=Attr(species, locked=True),
        ability=Attr("Stamina", locked=True),
        item=Attr("Leftovers", locked=True),
        moveset=Attr(["Protect", "Iron Head", "Body Press", "Rock Slide"], locked=True),
        spread=Attr({"hp": 32, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 0}, locked=True),
        nature=Attr("Adamant", locked=True),
    )


def _complete_draft() -> list[Slot]:
    return [
        _locked_species(name)
        for name in (
            "Archaludon",
            "Pelipper",
            "Incineroar",
            "Sinistcha",
            "Meowstic",
            "Farigiraf",
        )
    ]


def _partial_draft() -> list[Slot]:
    return [_locked_species("Archaludon"), _locked_species("Pelipper"), *[empty_slot() for _ in range(4)]]


def _stub_team_review() -> TeamReviewResult:
    return TeamReviewResult(threats=[], coverage=[{"species": "X"}], spofs=[])


def test_handle_line_idle_without_parser_invokes_and_catches_not_implemented():
    graph = MagicMock()
    graph.invoke.side_effect = NotImplementedError(
        "classify_pending is not wired; monkeypatch in tests or configure ADR-013 LLM"
    )
    state = {"pending_presentation": None, "team_draft": []}
    config = thread_config("t")
    new_state, new_config, tid, output, should_exit = handle_line(
        graph, config, state, "hello", format_id=DEFAULT_FORMAT_ID, thread_id="t"
    )
    graph.invoke.assert_called_once_with({"pending_input": "hello"}, config)
    assert output == NO_PENDING_MESSAGE
    assert should_exit is False
    assert new_state is state
    assert new_config is config
    assert tid == "t"


def test_handle_line_discovery_error_skips_invoke():
    graph = MagicMock()
    state = {
        "pending_presentation": None,
        "team_draft": [],
        "candidate_discovery_error": CandidateDiscoveryError(
            kind="calc_unavailable",
            stage="coverage",
            message="calc service down",
            retryable=True,
        ),
    }
    _, _, _, output, should_exit = handle_line(
        graph, thread_config("t"), state, "hello", format_id=DEFAULT_FORMAT_ID, thread_id="t"
    )
    assert output is not None
    assert "calc_unavailable" in output
    assert "won't resolve on its own" in output
    assert "wait for a prompt" not in output
    assert should_exit is False
    graph.invoke.assert_not_called()


def test_handle_line_degraded_candidate_with_error_still_invokes():
    graph = MagicMock()
    graph.invoke.return_value = {
        "turn_intent": "deferred",
        "pending_presentation": None,
        "team_draft": [_locked_archaludon()],
    }
    error = CandidateDiscoveryError(
        kind="calc_incomplete",
        stage="threat_coverage",
        message="batch damage verification incomplete",
        retryable=True,
    )
    state = {
        "pending_presentation": _CANDIDATE_PENDING,
        "candidate_discovery_error": error,
        "team_draft": [_locked_archaludon()],
    }
    handle_line(
        graph,
        thread_config("t"),
        state,
        "defer",
        format_id=DEFAULT_FORMAT_ID,
        thread_id="t",
    )
    graph.invoke.assert_called_once()


def test_handle_line_idle_continue_empty_team():
    parser = RunnableLambda(lambda _: {"turn_intent": "continue"})
    graph = compile_graph(checkpointer=MemorySaver(), turn_intent_parser=parser)
    thread_id = "idle-empty-continue"
    config = thread_config(thread_id)
    state = graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config)
    graph.update_state(config, {"pending_presentation": None})
    state = graph.get_state(config).values
    new_state, _, _, output, should_exit = handle_line(
        graph,
        config,
        state,
        "what next",
        format_id=DEFAULT_FORMAT_ID,
        thread_id=thread_id,
    )
    assert should_exit is False
    assert output is not None
    assert new_state.get("pending_presentation", {}).get("kind") == "bootstrap_intake"


def test_handle_line_idle_continue_complete_team():
    parser = RunnableLambda(lambda _: {"turn_intent": "continue"})
    graph = compile_graph(checkpointer=MemorySaver(), turn_intent_parser=parser)
    thread_id = "idle-complete-continue"
    config = thread_config(thread_id)
    graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config)
    graph.update_state(
        config,
        {
            "pending_presentation": None,
            "team_draft": _complete_draft(),
            "bootstrap_intake_complete": True,
        },
    )
    state = graph.get_state(config).values
    with patch("recommender.nodes._compute_team_review", return_value=_stub_team_review()):
        new_state, _, _, _, should_exit = handle_line(
            graph,
            config,
            state,
            "what next",
            format_id=DEFAULT_FORMAT_ID,
            thread_id=thread_id,
        )
    assert should_exit is False
    assert team_phase(new_state) == "complete"
    assert new_state.get("pending_presentation") is None
    assert new_state.get("last_team_review") is not None


def test_handle_line_idle_team_review_complete_team():
    parser = RunnableLambda(lambda _: {"turn_intent": "team_review"})
    graph = compile_graph(checkpointer=MemorySaver(), turn_intent_parser=parser)
    thread_id = "idle-complete-review"
    config = thread_config(thread_id)
    graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config)
    graph.update_state(
        config,
        {
            "pending_presentation": None,
            "team_draft": _complete_draft(),
            "bootstrap_intake_complete": True,
        },
    )
    state = graph.get_state(config).values
    with patch("recommender.nodes._compute_team_review", return_value=_stub_team_review()):
        new_state, _, _, _, should_exit = handle_line(
            graph,
            config,
            state,
            "show me the team",
            format_id=DEFAULT_FORMAT_ID,
            thread_id=thread_id,
        )
    assert should_exit is False
    assert new_state.get("turn_intent") == "team_review"
    assert team_phase(new_state) == "complete"
    assert new_state.get("last_team_review") is not None


def test_handle_line_idle_team_review_partial_team():
    parser = RunnableLambda(lambda _: {"turn_intent": "team_review"})
    graph = compile_graph(checkpointer=MemorySaver(), turn_intent_parser=parser)
    thread_id = "idle-partial-review"
    config = thread_config(thread_id)
    graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config)
    graph.update_state(
        config,
        {
            "pending_presentation": None,
            "team_draft": _partial_draft(),
            "bootstrap_intake_complete": True,
        },
    )
    state = graph.get_state(config).values
    with patch("recommender.nodes._compute_team_review", return_value=_stub_team_review()):
        new_state, _, _, _, should_exit = handle_line(
            graph,
            config,
            state,
            "show me the team",
            format_id=DEFAULT_FORMAT_ID,
            thread_id=thread_id,
        )
    assert should_exit is False
    assert new_state.get("turn_intent") == "team_review"
    assert team_phase(new_state) == "multi_locked"
    assert new_state.get("last_team_review") is not None


@pytest.mark.parametrize(
    ("intent", "payload"),
    [
        (
            "edit",
            {
                "turn_intent": "edit",
                "field": "nature",
                "value_text": "Modest",
                "edit_scope": "field_only",
            },
        ),
        ("select_build_option", {"turn_intent": "select_build_option", "option_ids": ["1"]}),
        ("compare", {"turn_intent": "compare", "option_ids": ["1", "2"]}),
    ],
)
def test_handle_line_idle_blocked_intents(intent, payload):
    parser = RunnableLambda(lambda _: payload)
    graph = compile_graph(checkpointer=MemorySaver(), turn_intent_parser=parser)
    thread_id = f"idle-blocked-{intent}"
    config = thread_config(thread_id)
    graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config)
    graph.update_state(config, {"pending_presentation": None})
    state = graph.get_state(config).values
    new_state, _, _, output, should_exit = handle_line(
        graph,
        config,
        state,
        "ambiguous request",
        format_id=DEFAULT_FORMAT_ID,
        thread_id=thread_id,
    )
    assert should_exit is False
    assert output is not None
    assert new_state.get("turn_intent") == "pending_response"
    assert output.startswith(_MISMATCH_MSG)


def test_handle_line_unexpected_error_with_pending_is_friendly():
    from recommender.turn_intent import CLASSIFY_FAIL_USER_MSG

    graph = MagicMock()
    graph.invoke.side_effect = RuntimeError("OUTPUT_PARSING_FAILURE boom")
    state = {"pending_presentation": _CANDIDATE_PENDING, "team_draft": []}
    _, _, _, output, should_exit = handle_line(
        graph, thread_config("t"), state, "hello", format_id=DEFAULT_FORMAT_ID, thread_id="t"
    )
    assert output == CLASSIFY_FAIL_USER_MSG
    assert "OUTPUT_PARSING_FAILURE" not in output
    assert "RuntimeError" not in output
    assert should_exit is False


def _handle_deferred(incoming_pending, returned_state, reply="defer"):
    graph = MagicMock()
    graph.invoke.return_value = returned_state
    incoming = {"pending_presentation": incoming_pending, "team_draft": []}
    _, _, _, output, should_exit = handle_line(
        graph,
        thread_config("t"),
        incoming,
        reply,
        format_id=DEFAULT_FORMAT_ID,
        thread_id="t",
    )
    graph.invoke.assert_called_once()
    assert should_exit is False
    return output


def test_handle_line_degraded_candidate_defer_omits_unmatched_prefix():
    error = CandidateDiscoveryError(
        kind="calc_incomplete",
        stage="threat_coverage",
        message="batch damage verification incomplete",
        retryable=True,
    )
    output = _handle_deferred(
        _CANDIDATE_PENDING,
        {
            "turn_intent": "deferred",
            "pending_presentation": None,
            "candidate_discovery_error": error,
            "team_draft": [_locked_archaludon()],
        },
    )
    assert output is not None
    assert UNMATCHED_REPLY_PREFIX not in output
    assert "calc_incomplete" in output
    assert "Team:" in output
    assert "Archaludon" in output


def test_handle_line_healthy_candidate_defer_omits_unmatched_prefix():
    output = _handle_deferred(
        _CANDIDATE_PENDING,
        {
            "turn_intent": "deferred",
            "pending_presentation": None,
            "team_draft": [_locked_archaludon()],
        },
    )
    assert output is not None
    assert UNMATCHED_REPLY_PREFIX not in output
    assert "Team:" in output
    assert "Archaludon" in output


def test_handle_line_completion_preference_defer_omits_unmatched_prefix():
    output = _handle_deferred(
        {
            "schema_version": 2,
            "kind": "completion_preference",
            "preference_options": ("attacker", "support", "balanced"),
        },
        {
            "turn_intent": "deferred",
            "pending_presentation": None,
            "team_draft": [_locked_archaludon()],
        },
    )
    assert output is not None
    assert UNMATCHED_REPLY_PREFIX not in output


def test_handle_line_full_build_confirmation_defer_omits_unmatched_prefix():
    output = _handle_deferred(
        {"schema_version": 1, "kind": "full_build_confirmation"},
        {
            "turn_intent": "deferred",
            "pending_presentation": None,
            "pending_slot_intent": None,
            "provisional_slot": None,
            "provisional_refinement": None,
            "team_draft": [_locked_archaludon()],
        },
    )
    assert output is not None
    assert UNMATCHED_REPLY_PREFIX not in output


def test_handle_line_unmatched_keeps_pending_and_prefixes():
    output = _handle_deferred(
        _CANDIDATE_PENDING,
        {
            "turn_intent": "pending_response",
            "pending_presentation": _CANDIDATE_PENDING,
            "team_draft": [_locked_archaludon()],
        },
        reply="xyzzy",
    )
    assert output is not None
    assert output.startswith(UNMATCHED_REPLY_PREFIX)
    assert "Meowstic" in output
    assert "defer" in output


def test_invoke_user_text_raises_without_pending(tmp_path: Path):
    db = tmp_path / "nopending.db"
    graph, saver = compile_cli_graph(path=db, bootstrap_intake_parser=None)
    try:
        config = thread_config("t1")
        graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config)
        graph.update_state(
            config,
            {
                "pending_presentation": None,
                "bootstrap_intake_complete": True,
            },
        )
        try:
            invoke_user_text(graph, config, "anything")
            raised = False
        except NotImplementedError:
            raised = True
        assert raised
        # handle_line still surfaces the friendly message if invoke raises
        state = graph.get_state(config).values
        # Force path that calls invoke: temporarily give a pending then clear mid-flight
        # via testing the except branch with a raising graph mock:
        g2 = MagicMock()
        g2.invoke.side_effect = NotImplementedError("classify_pending is not wired")
        st = {"pending_presentation": {"kind": "bootstrap_intake", "prompt_text": "x"}}
        _, _, _, output, _ = handle_line(
            g2, config, st, "hi", format_id=DEFAULT_FORMAT_ID, thread_id="t1"
        )
        assert output == NO_PENDING_MESSAGE
    finally:
        saver.conn.close()


def test_meta_new_and_reset_mint_without_graph_reset_intent(tmp_path: Path):
    db = tmp_path / "meta.db"
    graph, saver = compile_cli_graph(path=db, bootstrap_intake_parser=None)
    try:
        thread_id, config, state = "old", thread_config("old"), {}
        state = graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config=thread_config("old"))
        thread_id = "old"
        config = thread_config("old")

        payloads: list[dict] = []
        real_invoke = graph.invoke

        def spy(payload, config=None, **kwargs):
            payloads.append(dict(payload))
            return real_invoke(payload, config=config, **kwargs)

        graph.invoke = spy  # type: ignore[method-assign]

        state, config, thread_id, output, should_exit = handle_line(
            graph,
            config,
            state,
            ":reset",
            format_id=DEFAULT_FORMAT_ID,
            thread_id=thread_id,
        )
        assert should_exit is False
        assert thread_id != "old"
        assert thread_id.startswith("team-")
        assert payloads
        assert payloads[-1] == {"format_id": DEFAULT_FORMAT_ID}
        assert "pending_input" not in payloads[-1]
        assert output is not None

        state2, config2, tid2, _, _ = handle_line(
            graph,
            config,
            state,
            ":new",
            format_id=DEFAULT_FORMAT_ID,
            thread_id=thread_id,
        )
        assert tid2 != thread_id
        assert tid2.startswith("team-")
    finally:
        saver.conn.close()


def test_keyboard_interrupt_on_input_returns_130(tmp_path: Path, monkeypatch):
    db = tmp_path / "ki.db"
    monkeypatch.setattr(
        "builtins.input",
        lambda *_a, **_k: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    code = main(["--new", "--db", str(db), "--provider", "none"])
    assert code == 130


def test_e2e_bootstrap_pick_confirm_restart(tmp_path: Path):
    db = tmp_path / "e2e.db"
    parser = _rain_parser()
    moves = ["Hurricane", "U-turn", "Weather Ball", "Protect"]
    spread = {"hp": 4, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 30}

    def _noop_single(_state):
        return {
            "coverage": [],
            "spofs": [],
            "shared_teammates": None,
            "last_team_review": None,
            "candidate_discovery_error": None,
            "pending_presentation": None,
        }

    with patch("recommender.nodes.discover_single_locked", side_effect=_noop_single):
        graph, saver = compile_cli_graph(path=db, bootstrap_intake_parser=parser)
        try:
            config = thread_config("e2e-smoke")
            first = graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config)
            assert first["pending_presentation"]["kind"] == "bootstrap_intake"

            second = graph.invoke({"pending_input": "Rain with Pelipper"}, config)
            assert second["bootstrap_intake_complete"] is True
            assert second["pending_presentation"]["kind"] == "candidate_selection"
            species = second["pending_presentation"]["options"][0]["species"]

            with (
                patch(
                    "recommender.propose.featured_or_common_set",
                    return_value={
                        "species": species,
                        "ability": "Drizzle",
                        "moves": moves,
                        "item": "Damp Rock",
                        "nature": "Modest",
                    },
                ),
                patch(
                    "recommender.propose.get_resolved_build",
                    return_value={
                        "spread": spread,
                        "source_tier": "test",
                        "verified": True,
                    },
                ),
            ):
                selected = graph.invoke({"pending_input": "yes"}, config)
            assert selected["pending_presentation"]["kind"] == "full_build_confirmation"
            assert selected["provisional_slot"] is not None

            confirmed = graph.invoke({"pending_input": "yes"}, config)
            slot0 = confirmed["team_draft"][0]
            assert slot0.species.value == species
            assert slot0.species.locked is True
        finally:
            saver.conn.close()

    from recommender.checkpointer import open_sqlite_checkpointer

    saver2 = open_sqlite_checkpointer(db)
    try:
        graph2 = compile_graph(checkpointer=saver2, bootstrap_intake_parser=parser)
        snap = graph2.get_state(thread_config("e2e-smoke")).values
        assert snap["team_draft"][0].species.locked is True
        assert snap["team_draft"][0].species.value == species
    finally:
        saver2.conn.close()
