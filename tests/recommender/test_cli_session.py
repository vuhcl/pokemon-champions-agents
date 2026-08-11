"""Session helpers: mint, list, incomplete selection, empty-state guards."""

from __future__ import annotations

from pathlib import Path

from recommender.checkpointer import open_sqlite_checkpointer
from recommender.graph import compile_graph
from recommender.session import (
    DEFAULT_FORMAT_ID,
    is_incomplete,
    list_thread_summaries,
    mint_thread_id,
    pick_newest_incomplete,
    resolve_thread_id,
    thread_config,
    thread_exists,
)
from recommender.state import Attr, Slot

_SPREAD = {"hp": 32, "atk": 32, "def": 2, "spa": 0, "spd": 0, "spe": 0}


def _fully_locked(species: str) -> Slot:
    return Slot(
        role=Attr("bulky_attacker", locked=True),
        species=Attr(species, locked=True),
        ability=Attr("Pressure", locked=True),
        item=Attr("Leftovers", locked=True),
        moveset=Attr(["Protect", "Tackle", "Rest", "Sleep Talk"], locked=True),
        spread=Attr(dict(_SPREAD), locked=True),
        nature=Attr("Adamant", locked=True),
    )


def test_mint_thread_id_prefix():
    assert mint_thread_id().startswith("team-")


def test_is_incomplete_empty_state_no_keyerror():
    assert is_incomplete({}) is False


def test_thread_exists_unknown(tmp_path: Path):
    db = tmp_path / "s.db"
    saver = open_sqlite_checkpointer(db)
    try:
        assert thread_exists(saver, "missing") is False
        graph = compile_graph(checkpointer=saver)
        values = graph.get_state(thread_config("missing")).values
        assert values == {} or not values
    finally:
        saver.conn.close()


def test_pick_newest_incomplete_among_multiple(tmp_path: Path):
    db = tmp_path / "multi.db"
    saver = open_sqlite_checkpointer(db)
    try:
        graph = compile_graph(checkpointer=saver)
        older = thread_config("older")
        newer = thread_config("newer")
        graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config=older)
        graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config=newer)
        # Bump newer so it is the most recently updated incomplete thread.
        graph.update_state(newer, {"turn": 1})

        summaries = list_thread_summaries(graph, saver)
        assert {s.thread_id for s in summaries} >= {"older", "newer"}
        assert all(s.incomplete for s in summaries if s.thread_id in {"older", "newer"})
        assert pick_newest_incomplete(summaries) == "newer"
        thread_id, is_new = resolve_thread_id(
            mode="resume", explicit_id=None, summaries=summaries
        )
        assert is_new is False
        assert thread_id == "newer"
    finally:
        saver.conn.close()


def test_complete_excluded_from_default_but_reachable(tmp_path: Path):
    db = tmp_path / "complete.db"
    saver = open_sqlite_checkpointer(db)
    try:
        graph = compile_graph(checkpointer=saver)
        complete_cfg = thread_config("done")
        incomplete_cfg = thread_config("wip")
        graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config=complete_cfg)
        graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config=incomplete_cfg)

        draft = [_fully_locked(f"Mon{i}") for i in range(6)]
        graph.update_state(
            complete_cfg,
            {
                "team_draft": draft,
                "pending_presentation": None,
                "pending_slot_intent": None,
                "provisional_slot": None,
            },
        )
        # Touch complete last so it is newest overall — still must not be picked.
        graph.update_state(complete_cfg, {"turn": 99})

        summaries = list_thread_summaries(graph, saver)
        by_id = {s.thread_id: s for s in summaries}
        assert by_id["done"].incomplete is False
        assert by_id["wip"].incomplete is True
        assert pick_newest_incomplete(summaries) == "wip"

        assert thread_exists(saver, "done") is True
        loaded = graph.get_state(complete_cfg).values
        assert loaded["team_draft"][0].species.value == "Mon0"
    finally:
        saver.conn.close()
