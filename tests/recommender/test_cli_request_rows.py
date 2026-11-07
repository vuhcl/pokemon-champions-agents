"""FU71: CLI request-set rows H8, Q9, MU1, MU5, MS1, MS2, Q10, MR6, MR7 through handle_line.

The turn-intent parser is stubbed with the extraction the prompt specifies for the row
(no live LLM). Gates (rules Q&A, idle commit) never reach the parser.
"""

from __future__ import annotations

import copy

import pytest
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import MemorySaver

from recommender import team_rules_qa
from recommender.cli import handle_line
from recommender.graph import compile_graph
from recommender.nodes_classify import NOTHING_TO_COMMIT_MSG
from recommender.session import DEFAULT_FORMAT_ID, thread_config
from recommender.state import Attr, Slot, empty_slot
from recommender.team_rules_qa import try_route_team_rules

PENDING_RESPONSE = {"turn_intent": "pending_response"}


def _locked(species: str) -> Slot:
    return Slot(
        role=Attr("bulky_attacker", locked=True),
        species=Attr(species, locked=True),
        ability=Attr("Pressure", locked=True),
        item=Attr("Leftovers", locked=True),
        moveset=Attr(["Protect", "Tackle", "Rest", "Sleep Talk"], locked=True),
        spread=Attr({"hp": 32, "atk": 32, "def": 2, "spa": 0, "spd": 0, "spe": 0}, locked=True),
        nature=Attr("Adamant", locked=True),
    )


def _turn(text: str, parser_out: dict, draft: list[Slot] | None = None):
    graph = compile_graph(
        checkpointer=MemorySaver(), turn_intent_parser=RunnableLambda(lambda _: parser_out)
    )
    config = thread_config("t")
    graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config)
    update = {"pending_presentation": None}
    if draft is not None:
        update["team_draft"] = draft
    graph.update_state(config, update)
    state = graph.get_state(config).values
    before = copy.deepcopy(state["team_draft"])
    new_state, _, _, output, _ = handle_line(
        graph, config, state, text, format_id=DEFAULT_FORMAT_ID, thread_id="t"
    )
    return before, new_state, output


def _unchanged(before, after) -> bool:
    return before == after["team_draft"]


@pytest.mark.parametrize(
    ("text", "clause"),
    [
        ("Can I put Choice Scarf on both Garchomp and Jolteon?", "Item Clause"),  # H8
        ("Can I have two Incineroar on one team?", "Species Clause"),  # Q9
        ("What if I gave Choice Scarf to both Garchomp and Jolteon on this team?", "Item Clause"),  # MU1
        ("Could I run two Life Orbs on this team?", "Item Clause"),  # MU5
    ],
)
def test_rules_question_answers_no_with_clause_and_changes_nothing(text, clause):
    before, after, output = _turn(text, PENDING_RESPONSE)  # parser would give a useless reply
    assert after["turn_intent"] == "pending_response"
    assert f"No. {clause}:" in output
    assert _unchanged(before, after)


@pytest.mark.parametrize(
    "text",
    [
        "Can Garchomp learn Earthquake?",
        "Can I have two weeks to decide?",
        "Lock two Incineroar",
        "I want both Garchomp and Jolteon",
    ],
)
def test_unrecognised_question_falls_through(text):
    assert try_route_team_rules(text) is None


def test_rules_gate_never_raises(monkeypatch):
    def boom():
        raise RuntimeError("snapshot gone")

    monkeypatch.setattr(team_rules_qa, "load_snapshot", boom)
    assert try_route_team_rules("Can I have two Incineroar on one team?") is None


def test_ms1_lock_garchomp_in_slot_2_reads_back_state():
    parser_out = {"turn_intent": "lock", "slot_index": 2, "attr": "species", "value": "Garchomp"}
    _, after, output = _turn("Lock Garchomp in slot 2", parser_out)
    assert after["team_draft"][1].species.value == "Garchomp"
    assert after["team_draft"][1].species.locked
    assert output.splitlines()[0] == "Slot 2: Garchomp (locked: species)."


def test_ms2_unlock_slot_1_reads_back_empty_slot():
    draft = [_locked("Kingambit")] + [empty_slot() for _ in range(5)]
    _, after, output = _turn("Unlock slot 1", {"turn_intent": "repick_locked_slot", "slot_index": 1}, draft)
    assert after["team_draft"][0] == empty_slot()
    assert output.splitlines()[0] == "Slot 1: empty (unlocked)."


@pytest.mark.parametrize("text", ["Can I unlock slot 2 when nothing is locked?", "Unlock slot 2"])  # Q10, MR6
def test_unlock_with_nothing_locked_explains_and_changes_nothing(text):
    before, after, output = _turn(text, {"turn_intent": "repick_locked_slot", "slot_index": 2})
    assert "Slot 2 has nothing locked, so there is nothing to unlock. Nothing was changed." in output
    assert _unchanged(before, after)


@pytest.mark.parametrize("parser_out", [PENDING_RESPONSE, {"turn_intent": "full_slot_confirmed"}])
def test_mr7_commit_with_nothing_pending_says_so_and_changes_nothing(parser_out):
    before, after, output = _turn("Commit this build", parser_out)
    assert NOTHING_TO_COMMIT_MSG in output
    assert _unchanged(before, after)
    assert after.get("pending_presentation") is None
