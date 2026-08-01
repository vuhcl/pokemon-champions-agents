from unittest.mock import MagicMock, patch

from langgraph.checkpoint.memory import MemorySaver

from recommender.graph import compile_graph
from recommender.reconcile import (
    check_archetype_fit,
    check_theme_fit,
    reconcile_on_archetype_change,
)
from recommender.state import Attr, ReasonRef, RecommenderState, Slot, VerificationEntry

VGC_MB = "[Gen 9 Champions] VGC 2026 Reg M-B"


def _base_state(**overrides) -> RecommenderState:
    state: RecommenderState = {
        "format_id": VGC_MB,
        "game_type": "doubles",
        "regulation_mod": "champions",
        "picked_team_size": 4,
        "available_pool": [],
        "team_draft": [Slot() for _ in range(6)],
        "archetype": Attr(),
        "rejected": [],
        "constraints": [],
        "messages": [],
        "turn": 1,
        "superseded": [],
        "pending_flags": [],
    }
    state.update(overrides)
    return state


def test_tier1_rain_reopens_fire_type():
    slot = Slot(
        species=Attr(value="Charizard", locked=True, reason=ReasonRef(kind="archetype"))
    )
    fit = check_theme_fit(slot, "Rain")
    assert fit is not None
    assert fit.satisfies is False
    assert fit.groundedness == "mechanically-checkable"
    assert fit.ambiguous is False

    state = _base_state(
        team_draft=[
            Slot(
                species=Attr(
                    value="Charizard",
                    locked=True,
                    reason=ReasonRef(kind="archetype"),
                )
            ),
            *[Slot() for _ in range(5)],
        ]
    )
    out = reconcile_on_archetype_change(state, ["Rain"])
    assert out["team_draft"][0].species.locked is False
    assert out["team_draft"][0].species.value is None
    assert len(out["superseded"]) == 1
    assert out["superseded"][0]["value"] == "Charizard"


def test_tier2_calc_severity_flags_not_reopen():
    slot = Slot(
        species=Attr(value="Snorlax", locked=True),
        moveset=Attr(value=["Body Slam"], locked=True),
        verification=[
            VerificationEntry(
                claim="Body Slam damage",
                tool_called="calc",
                result="damage max 200",
                turn=1,
            )
        ],
    )
    mock_client = MagicMock()
    mock_client.calculate.return_value = {"damageRange": [80, 96], "koChance": "3HKO"}

    fit = check_theme_fit(slot, "Rain", calc_client=mock_client)
    assert fit is not None
    assert fit.satisfies is False
    assert fit.severity in ("costly", "toss-up")

    state = _base_state(team_draft=[slot, *[Slot() for _ in range(5)]])
    with patch("recommender.reconcile.CalcClient", return_value=mock_client):
        out = reconcile_on_archetype_change(state, ["Rain"], calc_client=mock_client)
    draft = out.get("team_draft", state["team_draft"])
    assert draft[0].species.locked is True
    assert len(out.get("superseded", [])) == 0
    assert any(f["flag_kind"] == "severity_mismatch" for f in out["pending_flags"])


def test_composite_or_dropping_one_component_keeps_slot():
    slot = Slot(
        species=Attr(value="Tornadus", locked=True),
        moveset=Attr(value=["Tailwind", "Bleakwind Storm"], locked=True),
        item=Attr(value="Focus Sash", locked=True),
    )
    fit_tail = check_theme_fit(slot, "Tailwind")
    fit_tr = check_theme_fit(slot, "TrickRoom")
    assert fit_tail is not None and fit_tail.satisfies is True
    assert fit_tr is not None and fit_tr.satisfies is False

    composite = check_archetype_fit(slot, ["Tailwind", "TrickRoom"])
    assert composite.satisfies is True

    state = _base_state(
        team_draft=[slot, *[Slot() for _ in range(5)]],
        archetype=Attr(value=["Tailwind", "TrickRoom"], locked=True),
    )
    out = reconcile_on_archetype_change(state, ["Tailwind"])
    assert "team_draft" not in out or out["team_draft"][0].species.locked is True


def test_exempt_mechanical_conflict_flags_not_reopen():
    slot = Slot(
        species=Attr(
            value="Charizard",
            locked=True,
            exempt_from_theme=True,
            reason=ReasonRef(kind="user_stated"),
        )
    )
    state = _base_state(team_draft=[slot, *[Slot() for _ in range(5)]])
    out = reconcile_on_archetype_change(state, ["Rain"])
    draft = out.get("team_draft", state["team_draft"])
    assert draft[0].species.locked is True
    assert draft[0].species.value == "Charizard"
    assert len(out.get("superseded", [])) == 0
    assert len(out["pending_flags"]) == 1
    assert out["pending_flags"][0]["flag_kind"] == "flag_exempt_conflict"


def test_restore_reverses_auto_reopen():
    graph = compile_graph(checkpointer=MemorySaver())
    thread = {"configurable": {"thread_id": "restore-test"}}
    graph.invoke({"format_id": VGC_MB}, config=thread)

    draft = [
        Slot(
            species=Attr(
                value="Charizard",
                locked=True,
                reason=ReasonRef(kind="archetype"),
            )
        ),
        *[Slot() for _ in range(5)],
    ]
    graph.update_state(
        thread,
        {
            "team_draft": draft,
            "turn": 1,
            "superseded": [],
            "pending_flags": [],
        },
    )

    with patch(
        "recommender.nodes.classify_pending",
        return_value={
            "turn_intent": "archetype_change",
            "turn_payload": {"components": ["Rain"]},
        },
    ):
        after_change = graph.invoke({"pending_input": "switch to rain"}, config=thread)

    assert after_change["team_draft"][0].species.locked is False
    assert len(after_change["superseded"]) == 1

    with patch(
        "recommender.nodes.classify_pending",
        return_value={
            "turn_intent": "restore",
            "turn_payload": {"slot_index": 0, "attr": "species"},
        },
    ):
        restored = graph.invoke({"pending_input": "restore Charizard"}, config=thread)

    slot = restored["team_draft"][0]
    assert slot.species.locked is True
    assert slot.species.value == "Charizard"
    assert slot.species.reason is not None
    assert slot.species.reason.kind == "user_stated"
    assert len(restored["superseded"]) == 0
