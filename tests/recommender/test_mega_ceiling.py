from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from recommender.format import resolve_format
from recommender.legality import load_snapshot
from recommender.nodes import discover_single_locked
from recommender.reconcile import _item_mega_forme
from recommender.slot_fill import (
    AnchoredSlotDiscovery,
    AnnotatedCandidate,
    PresentedCandidate,
    SlotFillContext,
    SlotFillPresentation,
    SlotFillTerminalResult,
    present_candidates,
    run_slot_fill_terminal,
)
from recommender.state import (
    Attr,
    RecommenderState,
    Slot,
    ThreatCandidate,
    ThreatCounterCandidate,
    empty_slot,
)
from recommender.support_needs import RoleShapeContext, SupportNeed

# See test_team_phase_routing.py's _OBVIOUS_NEED -- same reasoning: this
# orchestration test needs a realistic trigger to avoid discover_single_
# locked routing it to discover_multi_locked instead (2026-08-21).
_OBVIOUS_NEED = [
    SupportNeed(
        category="trick_room",
        name="Trick Room",
        description="Low Spe attacker with no priority.",
        trigger="speed_tier:low_no_priority",
        stance="need",
    )
]
from recommender.team_candidates import (
    mega_ceiling_notices,
    mega_useful_ceiling,
    merge_multi_locked_candidates,
)

VGC_MB = "[Gen 9 Champions] VGC 2026 Reg M-B"
SPREAD = {"hp": 32, "atk": 32, "def": 2, "spa": 0, "spd": 0, "spe": 0}


def _locked(species: str, item: str = "Leftovers") -> Slot:
    return Slot(
        role=Attr("bulky_attacker", locked=True),
        species=Attr(species, locked=True),
        ability=Attr("Pressure", locked=True),
        item=Attr(item, locked=True),
        moveset=Attr(["Protect", "Tackle", "Rest", "Sleep Talk"], locked=True),
        spread=Attr(dict(SPREAD), locked=True),
        nature=Attr("Adamant", locked=True),
    )


def _state(draft: list[Slot] | None = None) -> RecommenderState:
    return {
        "format_id": VGC_MB,
        "game_type": "doubles",
        "regulation_mod": "champions",
        "picked_team_size": 4,
        "available_pool": [],
        "team_draft": draft or [empty_slot() for _ in range(6)],
        "archetype": Attr(),
        "rejected": [],
        "constraints": [],
        "messages": [],
    }


def _counter(species: str) -> ThreatCounterCandidate:
    row = ThreatCandidate(
        ladder_species=species,
        usage_rank=1,
        form=species,
        showdown_usage_pct=None,
        showdown_formes=(),
        spec={"species": species},
        build_source="test",
    )
    return ThreatCounterCandidate(
        candidate=row,
        threats_countered=("target",),
        threats_countered_count=1,
        verified_score=1.0,
        verified_vs=(),
    )


def test_ceiling_uses_format_constants_not_a_bare_three():
    draft = [empty_slot() for _ in range(6)]
    pick = resolve_format(VGC_MB)["picked_team_size"]
    assert mega_useful_ceiling(len(draft), pick) == 1 + (len(draft) - pick)


def test_charizard_mega_x_locked_is_one_of_three():
    notices = mega_ceiling_notices(
        _state([_locked("Charizard-Mega-X"), *[empty_slot() for _ in range(5)]])
    )
    assert len(notices) == 1
    assert "1 of 3" in notices[0]
    assert "1 of 6" not in notices[0]


def test_zero_mega_locks_emits_no_notice():
    assert mega_ceiling_notices(_state([_locked("Kingambit"), *[empty_slot() for _ in range(5)]])) == ()


def test_missing_picked_team_size_emits_no_notice():
    state = _state([_locked("Charizard-Mega-X"), *[empty_slot() for _ in range(5)]])
    del state["picked_team_size"]
    assert mega_ceiling_notices(state) == ()


def test_partial_lock_does_not_count():
    draft = [Slot(species=Attr("Charizard-Mega-X", locked=True)), *[empty_slot() for _ in range(5)]]
    assert mega_ceiling_notices(_state(draft)) == ()


def test_base_charizard_with_charizardite_x_counts_once():
    notices = mega_ceiling_notices(
        _state(
            [
                _locked("Charizard", item="Charizardite X"),
                *[empty_slot() for _ in range(5)],
            ]
        )
    )
    assert len(notices) == 1
    assert "1 of 3" in notices[0]


def test_meowsticite_on_base_meowstic_counts_once():
    notices = mega_ceiling_notices(
        _state(
            [_locked("Meowstic", item="Meowsticite"), *[empty_slot() for _ in range(5)]]
        )
    )
    assert len(notices) == 1
    assert "1 of 3" in notices[0]


def test_item_mega_forme_meowstic_defaults_to_male():
    snap = load_snapshot()
    assert _item_mega_forme("meowsticite", "meowstic", snap) == "meowsticmmega"
    assert _item_mega_forme("meowsticite", "meowsticf", snap) == "meowsticfmega"
    assert _item_mega_forme("charizarditex", "charizard", snap) == "charizardmegax"
    assert _item_mega_forme("charizarditey", "charizard", snap) == "charizardmegay"
    assert _item_mega_forme("swampertite", "swampert", snap) == "swampertmega"


def test_locked_charizard_x_excludes_y_and_does_not_double_count():
    contexts = [
        SimpleNamespace(
            resolved_build=SimpleNamespace(species="Charizard-Mega-X"),
            support_needs=(),
        )
    ]
    state = _state([_locked("Charizard-Mega-X"), *[empty_slot() for _ in range(5)]])
    with patch(
        "recommender.team_candidates.resolve_all_support_needs",
        return_value=[],
    ):
        rows = merge_multi_locked_candidates(
            state,
            contexts,  # type: ignore[arg-type]
            (_counter("Charizard-Mega-Y"), _counter("Incineroar")),
            None,
            ownership_mode="off",
            owned_species=frozenset(),
        )
    assert "Charizard-Mega-Y" not in [row.species for row in rows]
    assert [row.species for row in rows] == ["Incineroar"]
    notices = mega_ceiling_notices(state)
    assert len(notices) == 1
    assert "1 of 3" in notices[0]


def test_present_candidates_and_terminal_copy_notices():
    notice = mega_ceiling_notices(
        _state([_locked("Charizard-Mega-X"), *[empty_slot() for _ in range(5)]])
    )[0]
    ctx = SlotFillContext(
        anchor=None,
        role_shape_context=None,
        annotated_candidates=[AnnotatedCandidate("Farigiraf", (), "need")],
        candidates_pre_ranked=True,
        notices=(notice,),
    )
    presentation = present_candidates(ctx, slot_index=1)
    assert presentation.notices == (notice,)
    assert "1 of 3" in presentation.notices[0]
    terminal = run_slot_fill_terminal(ctx, _state(), slot_index=1)
    pending = terminal.state_updates["pending_presentation"]
    assert pending["notices"] == (notice,)
    assert "1 of 3" in pending["notices"][0]


def test_discover_single_locked_sets_notice_on_first_mega_lock():
    state = _state([_locked("Charizard-Mega-X"), *[empty_slot() for _ in range(5)]])
    context = SlotFillContext(
        anchor={"species": "Charizard-Mega-X"},
        role_shape_context=RoleShapeContext(),
        threat_counter_results=[],
        support_needs=_OBVIOUS_NEED,
    )
    captured: dict = {}

    def merge(ctx):
        ctx.annotated_candidates = [AnnotatedCandidate("Farigiraf", (), "need")]
        return ctx.annotated_candidates

    def terminal(ctx, _state, *, slot_index):
        captured["notices"] = ctx.notices
        return SlotFillTerminalResult(
            presentation=SlotFillPresentation(
                1, (PresentedCandidate("Farigiraf", "need", ()),)
            ),
            state_updates={
                "pending_presentation": {
                    "schema_version": 1,
                    "kind": "candidate_selection",
                    "slot_index": slot_index,
                    "options": [{"species": "Farigiraf", "source": "need"}],
                }
            },
            deferred=False,
        )

    with (
        patch(
            "recommender.slot_fill.build_anchored_slot_fill_context",
            return_value=AnchoredSlotDiscovery(context, object(), object(), False),
        ),
        patch("recommender.slot_fill.annotate_overlap", return_value=[]),
        patch("recommender.slot_fill.resolve_all_support_needs", return_value=[]),
        patch(
            "recommender.slot_fill.resolve_condition_beneficiaries", return_value=[]
        ),
        patch("recommender.slot_fill.merge_need_resolved", side_effect=merge),
        patch("recommender.slot_fill.run_slot_fill_terminal", side_effect=terminal),
    ):
        discover_single_locked(state)

    assert captured["notices"]
    assert "1 of 3" in captured["notices"][0]
    assert "1 of 6" not in captured["notices"][0]
