"""repick_locked_slot: full species re-pick on a fully locked team_draft slot."""

from __future__ import annotations

from unittest.mock import patch

from langgraph.checkpoint.memory import MemorySaver

from recommender.graph import build_graph, compile_graph
from recommender.nodes import (
    REPICK_REQUIRES_LOCKED_MSG,
    REVISE_REQUIRES_LOCKED_MSG,
    _compute_composition_gaps,
    apply_lock,
    begin_locked_slot_revision,
    team_phase,
    unlock_locked_slot,
)
from recommender.present_text import format_team_review
from recommender.state import (
    Attr,
    Slot,
    TeamReviewResult,
    all_locked,
    empty_slot,
)
from recommender.team_candidates import collect_locked_anchor_contexts

VGC_MB = "[Gen 9 Champions] VGC 2026 Reg M-B"
SPREAD = {"hp": 32, "atk": 32, "def": 2, "spa": 0, "spd": 0, "spe": 0}


def _locked(
    species: str,
    *,
    role: str = "bulky_attacker",
    ability: str = "Pressure",
    item: str = "Leftovers",
    moves: list[str] | None = None,
) -> Slot:
    return Slot(
        role=Attr(role, locked=True),
        species=Attr(species, locked=True),
        ability=Attr(ability, locked=True),
        item=Attr(item, locked=True),
        moveset=Attr(
            moves or ["Protect", "Tackle", "Rest", "Sleep Talk"], locked=True
        ),
        nature=Attr("Adamant", locked=True),
        spread=Attr(dict(SPREAD), locked=True),
    )


def _locked_sinistcha() -> Slot:
    return _locked(
        "Sinistcha",
        role="redirection",
        ability="Hospitality",
        item="Sitrus Berry",
        moves=["Rage Powder", "Matcha Gotcha", "Trick Room", "Shadow Ball"],
    )


def _base_state(*, team_draft: list[Slot], **extra) -> dict:
    base = {
        "format_id": VGC_MB,
        "game_type": "doubles",
        "regulation_mod": "champions-reg-mb",
        "picked_team_size": 4,
        "available_pool": [],
        "team_draft": team_draft,
        "archetype": Attr(),
        "rejected": [],
        "constraints": [],
        "messages": [],
    }
    base.update(extra)
    return base


def _graph():
    return compile_graph(checkpointer=MemorySaver())


def _thread(suffix: str):
    return {"configurable": {"thread_id": f"repick-locked-{suffix}"}}


def test_unlock_locked_slot_rejects_unlocked_slot():
    partial = Slot(species=Attr("Gholdengo", locked=True))
    state = {
        **_base_state(team_draft=[partial, *[empty_slot() for _ in range(5)]]),
        "turn_payload": {"slot_index": 0},
    }
    out = unlock_locked_slot(state)  # type: ignore[arg-type]
    assert out == {"slot_commit_error": REPICK_REQUIRES_LOCKED_MSG}
    assert "team_draft" not in out


def test_unlock_locked_slot_clears_slot_and_signals():
    draft = [_locked(f"Member{i}") for i in range(6)]
    state = _base_state(
        team_draft=draft,
        coverage=["stale"],
        spofs=["stale"],
        last_team_review={"x": 1},
        masked_slot_indices=(5,),
    )
    state["turn_payload"] = {"slot_index": 5}
    out = unlock_locked_slot(state)  # type: ignore[arg-type]
    assert out.get("slot_commit_error") is None
    assert not all_locked(out["team_draft"][5])
    assert out["team_draft"][5].species.value is None
    assert out["coverage"] == []
    assert out["spofs"] == []
    assert out["last_team_review"] is None
    assert out["masked_slot_indices"] == ()


def test_unlock_drops_team_phase_to_multi_locked():
    draft = [_locked(f"Member{i}") for i in range(6)]
    state = _base_state(team_draft=draft)
    state["turn_payload"] = {"slot_index": 5}
    out = unlock_locked_slot(state)  # type: ignore[arg-type]
    merged = {**state, **out}
    assert team_phase(merged) == "multi_locked"


def test_repick_routes_to_discovery_on_complete_team():
    suffix = "e2e-repick"
    draft = [_locked(f"Member{i}") for i in range(6)]
    discovery_out = {
        "pending_presentation": {
            "schema_version": 1,
            "kind": "candidate_selection",
            "slot_index": 5,
            "options": [{"species": "Pelipper", "source": "need"}],
        },
        "coverage": [],
        "spofs": [],
        "last_team_review": None,
    }
    with (
        patch(
            "recommender.nodes.classify_pending",
            return_value={
                "turn_intent": "repick_locked_slot",
                "turn_payload": {"slot_index": 5},
            },
        ),
        patch(
            "recommender.graph.nodes.discover_multi_locked",
            return_value=discovery_out,
        ) as discover,
    ):
        graph = compile_graph(checkpointer=MemorySaver())
        graph.invoke({"format_id": VGC_MB}, config=_thread(suffix))
        graph.update_state(_thread(suffix), _base_state(team_draft=draft))
        result = graph.invoke({"pending_input": "repick slot 5"}, config=_thread(suffix))

    discover.assert_called_once()
    assert result["pending_presentation"]["kind"] == "candidate_selection"
    assert result["pending_presentation"]["slot_index"] == 5
    assert not all_locked(result["team_draft"][5])


def test_repick_recompletion_runs_team_review():
    before = _base_state(
        team_draft=[_locked(f"Member{i}") for i in range(5)] + [empty_slot()]
    )
    after = [_locked(f"Member{i}") for i in range(6)]
    review = TeamReviewResult(threats=[], coverage=[], spofs=[], composition_gaps=())
    with (
        patch(
            "recommender.nodes.classify_pending",
            return_value={"turn_intent": "full_slot_confirmed"},
        ),
        patch("recommender.graph.nodes.commit_full_slot", return_value={"team_draft": after}),
        patch(
            "recommender.graph.nodes.generate_team_review",
            return_value={
                "coverage": [],
                "spofs": [],
                "last_team_review": review,
            },
        ) as generate,
    ):
        graph = build_graph().compile()
        result = graph.invoke({**before, "pending_input": "yes"})

    generate.assert_called_once()
    assert result["last_team_review"] is review
    assert result["team_draft"] == after


def test_sinistcha_redirection_composition_gap_after_swap():
    sinistcha = _locked_sinistcha()
    fillers = [_locked(f"Filler{i}") for i in range(5)]
    state = _base_state(team_draft=[*fillers, sinistcha])
    contexts_before = collect_locked_anchor_contexts(state)
    gaps_before = _compute_composition_gaps(contexts_before)
    assert not any("redirection" in g for g in gaps_before)

    swapped = _locked("Gholdengo", role="fast_special_attacker", ability="Good as Gold")
    after_draft = [*fillers, swapped]
    contexts_after = collect_locked_anchor_contexts(
        _base_state(team_draft=after_draft)
    )
    gaps_after = _compute_composition_gaps(contexts_after)
    assert any("redirection" in g for g in gaps_after)

    review = TeamReviewResult(
        threats=[],
        coverage=[],
        spofs=[],
        composition_gaps=gaps_after,
    )
    text = format_team_review(review, team_draft=after_draft)
    assert "Composition gaps:" in text
    assert "redirection" in text


def test_revise_path_does_not_call_unlock():
    locked = _locked("Gholdengo")
    state = {
        **_base_state(team_draft=[locked, *[empty_slot() for _ in range(5)]]),
        "turn_payload": {
            "slot_index": 0,
            "field": "item",
            "value": "Focus Sash",
            "scope": "field_only",
        },
    }
    with patch("recommender.nodes.unlock_locked_slot") as unlock_mock:
        out = begin_locked_slot_revision(state)  # type: ignore[arg-type]
        unlock_mock.assert_not_called()
    assert out.get("slot_commit_error") is None
    assert "provisional_slot" in out


def test_repick_does_not_fire_for_open_slot_lock():
    state = _base_state(team_draft=[empty_slot(), *[empty_slot() for _ in range(5)]])
    state["turn_payload"] = {
        "slot_index": 0,
        "attr": "species",
        "value": "Pelipper",
    }
    with patch("recommender.nodes.unlock_locked_slot") as unlock_mock:
        apply_lock(state)  # type: ignore[arg-type]
        unlock_mock.assert_not_called()


def test_begin_locked_slot_revision_still_rejects_unlocked():
    partial = Slot(species=Attr("Gholdengo", locked=True))
    state = {
        **_base_state(team_draft=[partial, *[empty_slot() for _ in range(5)]]),
        "turn_payload": {
            "slot_index": 0,
            "field": "item",
            "value": "Focus Sash",
            "scope": "field_only",
        },
    }
    out = begin_locked_slot_revision(state)  # type: ignore[arg-type]
    assert out == {"slot_commit_error": REVISE_REQUIRES_LOCKED_MSG}
