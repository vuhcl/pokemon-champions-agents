"""CLI REPL behavior: landmine, meta, interrupts, E2E smoke."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from langchain_core.runnables import RunnableLambda

from recommender.cli import handle_line, invoke_user_text, main
from recommender.graph import compile_cli_graph, compile_graph
from recommender.present_text import NO_PENDING_MESSAGE
from recommender.session import DEFAULT_FORMAT_ID, thread_config
from recommender.state import CandidateDiscoveryError


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

    def wrapping(*, path=None, bootstrap_intake_parser=None):
        graph, saver = real_compile(
            path=path, bootstrap_intake_parser=bootstrap_intake_parser
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


def test_handle_line_pre_guard_skips_invoke_without_pending():
    graph = MagicMock()
    state = {"pending_presentation": None, "team_draft": []}
    config = thread_config("t")
    new_state, new_config, tid, output, should_exit = handle_line(
        graph, config, state, "hello", format_id=DEFAULT_FORMAT_ID, thread_id="t"
    )
    assert output == NO_PENDING_MESSAGE
    assert should_exit is False
    graph.invoke.assert_not_called()
    assert new_state is state
    assert tid == "t"


def test_handle_line_pre_guard_reports_fail_closed_discovery():
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
