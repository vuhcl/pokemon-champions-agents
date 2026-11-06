"""Per-thread matchup memo: isolation, LRU, and the LangGraph executor."""

from __future__ import annotations

import importlib.util
import os
import sys
import threading

import pytest
from typing import Any
from unittest.mock import patch

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.pregel._executor import BackgroundExecutor

import recommender.matchup as matchup
from recommender.calc_client import CalcClient, CalcRequest
from recommender.matchup import (
    bind_matchup_memo_thread,
    classify_matchup,
    clear_matchup_memo,
    matchup_memo_stats,
    release_matchup_memo,
)

A = {
    "species": "Garchomp",
    "item": "Life Orb",
    "ability": "Rough Skin",
    "moves": ["Earthquake", "Dragon Claw"],
    "evs": {"hp": 0, "atk": 32, "spe": 32},
}
B = {
    "species": "Kingambit",
    "item": "Black Glasses",
    "ability": "Defiant",
    "moves": ["Sucker Punch", "Kowtow Cleave"],
    "evs": {"hp": 32, "atk": 32, "spe": 0},
}


def _calc() -> dict[str, Any]:
    dmg = [100, 100]
    return {
        "damageRange": dmg,
        "koChance": "100% OHKO",
        "raw": {
            "damage": dmg,
            "range": dmg,
            "kochance": {"chance": 1.0, "n": 1, "text": "100% OHKO"},
            "stats": {
                "attacker": {"spe": 100, "hp": 100},
                "defender": {"spe": 90, "hp": 100},
            },
        },
    }


class _Calc(CalcClient):
    def __init__(self) -> None:
        super().__init__("http://mock")
        self.calls = 0

    def calculate_batch(self, requests: list[CalcRequest]) -> list[dict[str, Any]]:
        self.calls += len(requests)
        return [_calc() for _ in requests]


def setup_function() -> None:
    clear_matchup_memo()


def teardown_function() -> None:
    clear_matchup_memo()


def _spec(species: str) -> dict[str, Any]:
    return {**A, "species": species}


def test_binding_one_thread_does_not_clear_the_other() -> None:
    bind_matchup_memo_thread("t1")
    classify_matchup(_spec("Alpha"), B, None, client=_Calc())
    bind_matchup_memo_thread("t2")
    assert matchup_memo_stats() == {"hits": 0, "misses": 0}
    other = _Calc()
    classify_matchup(_spec("Alpha"), B, None, client=other)
    assert other.calls > 0
    back = _Calc()
    bind_matchup_memo_thread("t1")
    classify_matchup(_spec("Alpha"), B, None, client=back)
    assert back.calls == 0
    assert matchup_memo_stats()["hits"] >= 1


def test_live_memo_lru_evicts_a_whole_thread_and_release_is_a_noop() -> None:
    with patch.object(matchup, "MATCHUP_MEMO_MAX_LIVE_THREADS", 2):
        bind_matchup_memo_thread("a")
        classify_matchup(_spec("Alpha"), B, None, client=_Calc())
        bind_matchup_memo_thread("b")
        classify_matchup(_spec("Beta"), B, None, client=_Calc())
        bind_matchup_memo_thread("c")
        classify_matchup(_spec("Gamma"), B, None, client=_Calc())
        rebound = _Calc()
        bind_matchup_memo_thread("a")
        classify_matchup(_spec("Alpha"), B, None, client=rebound)
        assert rebound.calls > 0

        bind_matchup_memo_thread("b")
        classify_matchup(_spec("Beta"), B, None, client=_Calc())
        release_matchup_memo("b")
        released = _Calc()
        bind_matchup_memo_thread("b")
        classify_matchup(_spec("Beta"), B, None, client=released)
        assert released.calls > 0
        release_matchup_memo("missing")
        assert "missing" not in matchup._memos


def test_concurrent_threads_do_not_read_each_others_memo() -> None:
    errors: list[BaseException] = []

    def work(tid: str) -> None:
        try:
            bind_matchup_memo_thread(tid)
            client = _Calc()
            classify_matchup(_spec(tid), B, None, client=client)
            again = _Calc()
            classify_matchup(_spec(tid), B, None, client=again)
            if again.calls != 0:
                raise AssertionError(f"{tid} missed its own memo")
            stranger = _Calc()
            classify_matchup(_spec(tid + "-other"), B, None, client=stranger)
            if stranger.calls == 0:
                raise AssertionError(f"{tid} saw another write without computing")
            if len(matchup._memos[tid]) > matchup.MATCHUP_MEMO_MAX_ENTRIES:
                raise AssertionError("cap exceeded")
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(f"s{i}",)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    bind_matchup_memo_thread("s0")
    cached = _Calc()
    classify_matchup(_spec("s0"), B, None, client=cached)
    assert cached.calls == 0
    foreign = _Calc()
    classify_matchup(_spec("s1"), B, None, client=foreign)
    assert foreign.calls > 0


def test_bind_is_visible_inside_classify_on_a_langgraph_executor_thread() -> None:
    seen: dict[str, Any] = {}

    def work() -> None:
        seen["ident"] = threading.get_ident()
        bind_matchup_memo_thread("lg-exec")
        classify_matchup(_spec("Exec"), B, None, client=_Calc())
        again = _Calc()
        classify_matchup(_spec("Exec"), B, None, client=again)
        seen["second_calls"] = again.calls
        seen["hits"] = matchup_memo_stats()["hits"]

    with BackgroundExecutor({}) as submit:
        submit(work).result()
    assert seen["ident"] != threading.get_ident()
    assert seen["second_calls"] == 0
    assert seen["hits"] >= 1

    def node(state: dict, config: RunnableConfig) -> dict:
        seen["node_ident"] = threading.get_ident()
        bind_matchup_memo_thread(config["configurable"]["thread_id"])
        classify_matchup(_spec("Node"), B, None, client=_Calc())
        again = _Calc()
        classify_matchup(_spec("Node"), B, None, client=again)
        seen["node_second_calls"] = again.calls
        return {"n": state["n"] + 1}

    graph = StateGraph(dict)
    graph.add_node("n", node)
    graph.add_edge(START, "n")
    graph.add_edge("n", END)
    graph.compile().invoke({"n": 0}, {"configurable": {"thread_id": "lg-node"}})
    # Visibility is the hit. This sync one-node invoke may stay on the caller
    # thread; BackgroundExecutor above is the pool path Pregel submits on.
    assert seen["node_second_calls"] == 0


@pytest.mark.skipif(os.environ.get("CALC_LIVE") != "1", reason="needs live calc service")
def test_alone_games_match_380_fingerprints() -> None:
    path = (
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        + "/docs/hosted_demo/matchup_memo_threads/remeasure.py"
    )
    spec = importlib.util.spec_from_file_location("matchup_memo_remeasure", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    mode, scripts, sem_n = module.PLANS["alone"]
    result = module.run_plan("alone-pytest", mode, scripts, sem_n)
    assert result["errors"] == []
    assert result["diffs"] == []
