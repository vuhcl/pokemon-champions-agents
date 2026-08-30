from __future__ import annotations

from unittest.mock import patch

import pytest
from langgraph.checkpoint.memory import MemorySaver

from langchain_core.runnables import RunnableLambda

from recommender.constraint_enforcement import matches_species, MechanicalSpec
from recommender.graph import compile_graph
from recommender.legality import load_snapshot
from recommender.nodes import classify_input, handle_claim_correction
from recommender.present_text import format_turn
from recommender.state import (
    Attr,
    CandidateDiscoveryError,
    RecommenderState,
    Slot,
    SystemClaim,
    empty_slot,
)
from recommender.system_claims import (
    build_deterministic_claim_correction,
    claim_is_true_against_snapshot,
    negation_matches_claim,
    stamp_system_claim,
    try_extract_reattempt_constraint,
    try_parse_verifiable_claim_from_message,
)

VGC_MB = "[Gen 9 Champions] VGC 2026 Reg M-B"


def _locked_slot(
    species: str,
    *,
    role: str,
    ability: str,
    item: str,
    moves: list[str],
    nature: str,
    spread: dict[str, int],
) -> Slot:
    return Slot(
        role=Attr(role, locked=True),
        species=Attr(species, locked=True),
        ability=Attr(ability, locked=True),
        item=Attr(item, locked=True),
        moveset=Attr(moves, locked=True),
        spread=Attr(spread, locked=True),
        nature=Attr(nature, locked=True),
    )


def _four_lock_support_draft() -> list[Slot]:
    return [
        _locked_slot(
            "Archaludon",
            role="bulky_special_attacker",
            ability="Stamina",
            item="Leftovers",
            moves=["Electro Shot", "Flash Cannon", "Protect", "Dragon Pulse"],
            nature="Calm",
            spread={"hp": 32, "atk": 0, "def": 1, "spa": 5, "spd": 25, "spe": 3},
        ),
        _locked_slot(
            "Pelipper",
            role="support_speed_control",
            ability="Drizzle",
            item="Focus Sash",
            moves=["Hurricane", "Weather Ball", "Tailwind", "Wide Guard"],
            nature="Modest",
            spread={"hp": 32, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 2},
        ),
        _locked_slot(
            "Swampert-Mega",
            role="bulky_attacker",
            ability="Swift Swim",
            item="Swampertite",
            moves=["Protect", "Wave Crash", "Ice Punch", "Earthquake"],
            nature="Adamant",
            spread={"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
        ),
        _locked_slot(
            "Sinistcha",
            role="redirection",
            ability="Hospitality",
            item="Sitrus Berry",
            moves=["Matcha Gotcha", "Rage Powder", "Strength Sap", "Protect"],
            nature="Bold",
            spread={"hp": 252, "atk": 0, "def": 252, "spa": 0, "spd": 4, "spe": 0},
        ),
        empty_slot(),
        empty_slot(),
    ]


def _graph(*, parser=None):
    if parser is None:
        parser = RunnableLambda(lambda _: {"turn_intent": "continue"})
    return compile_graph(checkpointer=MemorySaver(), turn_intent_parser=parser)


def _thread(suffix: str):
    return {"configurable": {"thread_id": f"claim-correction-{suffix}"}}


def _base_state(**overrides) -> RecommenderState:
    state: RecommenderState = {
        "format_id": VGC_MB,
        "game_type": "doubles",
        "regulation_mod": "champions-reg-mb",
        "picked_team_size": 4,
        "available_pool": [],
        "team_draft": _four_lock_support_draft(),
        "archetype": Attr(),
        "rejected": [],
        "constraints": [],
        "messages": [],
        "turn": 1,
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


def _grass_claim(*, with_reattempt: bool = True) -> SystemClaim:
    claim: SystemClaim = {
        "turn": 1,
        "kind": "type",
        "subject_species": "Heliolisk",
        "asserted_value": "Grass",
        "source": "pending_response_message",
        "display_excerpt": "Heliolisk is a Grass-type option",
        "verifiable": True,
        "originating_user_text": "I want a grass type",
    }
    if with_reattempt:
        reattempt = try_extract_reattempt_constraint("I want a grass type")
        assert reattempt is not None
        claim["reattempt_constraint"] = reattempt
    return claim


def test_parse_type_claim_from_message():
    parsed = try_parse_verifiable_claim_from_message(
        "Heliolisk is a Grass-type option for that slot"
    )
    assert parsed is not None
    assert parsed["kind"] == "type"
    assert parsed["subject_species"] == "Heliolisk"
    assert parsed["asserted_value"] == "Grass"


def test_extract_reattempt_from_originating_text():
    payload = try_extract_reattempt_constraint("I want a grass type")
    assert payload is not None
    assert payload["mechanical_kind"] == "type"
    assert payload["mechanical_value"] == "Grass"
    assert payload["type"] == "hard"


def test_stamp_system_claim_attaches_reattempt():
    claim = stamp_system_claim(
        message="Heliolisk is a Grass-type option",
        originating_user_text="I want a grass type",
        turn=1,
    )
    assert claim is not None
    assert claim["originating_user_text"] == "I want a grass type"
    assert "reattempt_constraint" in claim


def test_classify_input_stamps_claim_on_pending_response():
    state = _base_state(pending_input="I want a grass type")
    with patch(
        "recommender.nodes.classify_pending",
        return_value={
            "turn_intent": "pending_response",
            "turn_payload": {
                "message": "Heliolisk is a Grass-type option for that slot"
            },
        },
    ):
        out = classify_input(state, turn_intent_parser=object())
    assert out["last_system_claim"] is not None
    assert out["last_system_claim"]["subject_species"] == "Heliolisk"
    assert out["last_system_claim"]["originating_user_text"] == "I want a grass type"


def test_negation_matches_claim():
    claim = _grass_claim(with_reattempt=False)
    assert negation_matches_claim("heliolisk is not grass type", claim)
    assert not negation_matches_claim("I don't want Heliolisk", claim)


def test_deterministic_prepass_skips_llm():
    from recommender.nodes_classify import _try_deterministic_claim_correction

    claim = _grass_claim(with_reattempt=False)
    result = _try_deterministic_claim_correction("heliolisk is not grass type", claim)
    assert result is not None
    assert result["turn_intent"] == "claim_correction"


def test_handle_claim_correction_false_claim_reruns_discovery():
    state = _base_state(
        last_system_claim=_grass_claim(),
        turn_payload={
            "subject_species": "Heliolisk",
            "disputed_kind": "type",
            "disputed_value": "Grass",
            "user_text": "heliolisk is not grass type",
        },
    )
    out = handle_claim_correction(state)
    assert out["claim_correction_rerun_discovery"] is True
    assert out["last_system_claim"] is None
    assert len(out["constraints"]) == 1
    assert "withdrew" in (out["correction_response"] or "").lower()


def test_verification_claim_was_true():
    claim: SystemClaim = {
        "turn": 1,
        "kind": "type",
        "subject_species": "Heliolisk",
        "asserted_value": "Electric",
        "source": "pending_response_message",
        "display_excerpt": "Heliolisk is Electric type",
        "verifiable": True,
        "originating_user_text": "needs electric coverage",
    }
    assert claim_is_true_against_snapshot(claim)
    state = _base_state(
        last_system_claim=claim,
        turn_payload={
            "subject_species": "Heliolisk",
            "disputed_kind": "type",
            "disputed_value": "Electric",
            "user_text": "Heliolisk is not electric type",
        },
    )
    out = handle_claim_correction(state)
    assert not out.get("claim_correction_rerun_discovery")
    assert "constraints" not in out
    assert "confirms" in (out["correction_response"] or "").lower()


def test_unverifiable_honest_retraction():
    claim: SystemClaim = {
        "turn": 1,
        "kind": "other",
        "subject_species": "Heliolisk",
        "asserted_value": "unknown",
        "source": "pending_response_message",
        "display_excerpt": "something vague",
        "verifiable": False,
        "originating_user_text": "help",
    }
    state = _base_state(
        last_system_claim=claim,
        turn_payload={"user_text": "that's wrong", "subject_species": None, "disputed_kind": None, "disputed_value": None},
    )
    out = handle_claim_correction(state)
    assert "can't verify" in (out["correction_response"] or "").lower()
    assert not out.get("claim_correction_rerun_discovery")


def test_heliolisk_e2e_not_rejection():
    calls: list[int] = []

    def _fail_parser(_input):
        calls.append(1)
        raise AssertionError("LLM should not run when pre-pass matches")

    graph = _graph(parser=_fail_parser)
    suffix = "e2e-not-rejection"
    cfg = _thread(suffix)
    graph.invoke({"format_id": VGC_MB, "team_draft": _four_lock_support_draft()}, config=cfg)
    graph.update_state(
        cfg,
        {
            "last_system_claim": _grass_claim(),
            "pending_presentation": None,
            "candidate_discovery_error": None,
        },
    )

    result = graph.invoke(
        {"pending_input": "heliolisk is not grass type"},
        config=cfg,
    )

    assert calls == []
    assert result["turn_intent"] == "claim_correction"
    assert not any(entry["species"] == "Heliolisk" for entry in result.get("rejected", []))
    rendered = format_turn(result)
    assert "withdrew" in rendered.lower() or "re-running" in rendered.lower()


def test_heliolisk_e2e_constraint_unsatisfiable():
    graph = _graph()
    suffix = "e2e-unsatisfiable"
    cfg = _thread(suffix)
    graph.invoke({"format_id": VGC_MB, "team_draft": _four_lock_support_draft()}, config=cfg)
    graph.update_state(
        cfg,
        {
            "last_system_claim": _grass_claim(),
            "pending_presentation": None,
            "candidate_discovery_error": None,
        },
    )

    with patch(
        "recommender.constraint_enforcement.apply_mechanical_constraints_to_discovery",
        return_value=(
            [],
            CandidateDiscoveryError(
                kind="constraint_unsatisfiable",
                stage="constraint_validation",
                message="No candidates match hard constraint(s): Grass type",
                retryable=False,
            ),
        ),
    ):
        result = graph.invoke(
            {"pending_input": "heliolisk is not grass type"},
            config=cfg,
        )

    err = result.get("candidate_discovery_error")
    assert err is not None
    assert err.kind == "constraint_unsatisfiable"


def test_rejection_not_misclassified_with_claim_present():
    from recommender.nodes_classify import _try_deterministic_claim_correction

    claim = _grass_claim(with_reattempt=False)
    assert _try_deterministic_claim_correction("I don't want Heliolisk", claim) is None


def test_rillaboom_is_grass_in_snapshot():
    snap = load_snapshot()
    spec = MechanicalSpec(kind="type", value="Grass", scope="per_slot", label="Grass type")
    assert matches_species("Rillaboom", spec, snap=snap, team_draft=[])


def test_build_deterministic_claim_correction_payload():
    claim = _grass_claim(with_reattempt=False)
    result = build_deterministic_claim_correction("heliolisk is not grass type", claim)
    assert result["turn_intent"] == "claim_correction"
    assert result["turn_payload"]["disputed_value"] == "Grass"
