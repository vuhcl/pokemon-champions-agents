from __future__ import annotations

from unittest.mock import patch

from recommender.graph import _route_team_phase, build_graph
from recommender.nodes import (
    bootstrap_direction,
    discover_multi_locked,
    discover_single_locked,
    generate_team_review,
    refresh_team_signals,
    team_phase,
)
from recommender.slot_fill import (
    AnchoredSlotDiscovery,
    AnnotatedCandidate,
    PresentedCandidate,
    SlotFillContext,
    SlotFillPresentation,
    SlotFillTerminalResult,
)
from recommender.state import (
    Attr,
    CandidateDiscoveryError,
    Constraint,
    RecommenderState,
    Slot,
    TeamReviewResult,
    TeamThreatDiscovery,
    ThreatCandidate,
    ThreatCounterCandidate,
    empty_slot,
)
from recommender.support_needs import RoleShapeContext

VGC_MB = "[Gen 9 Champions] VGC 2026 Reg M-B"
SPREAD = {"hp": 32, "atk": 32, "def": 2, "spa": 0, "spd": 0, "spe": 0}


def _locked(species: str) -> Slot:
    return Slot(
        role=Attr("bulky_attacker", locked=True),
        species=Attr(species, locked=True),
        ability=Attr("Pressure", locked=True),
        item=Attr("Leftovers", locked=True),
        moveset=Attr(["Protect", "Tackle", "Rest", "Sleep Talk"], locked=True),
        spread=Attr(dict(SPREAD), locked=True),
        nature=Attr("Adamant", locked=True),
    )


def _state(draft: list[Slot]) -> RecommenderState:
    return {
        "format_id": VGC_MB,
        "game_type": "doubles",
        "regulation_mod": "champions",
        "picked_team_size": 4,
        "available_pool": [],
        "team_draft": draft,
        "archetype": Attr(),
        "rejected": [],
        "constraints": [],
        "messages": [],
    }


def test_team_phase_boundaries_use_only_fully_confirmed_slots():
    empty = [empty_slot() for _ in range(6)]
    partial = [Slot(species=Attr("Kingambit", locked=True)), *empty[1:]]
    one = [_locked("Kingambit"), *[empty_slot() for _ in range(5)]]
    two = [_locked("Kingambit"), _locked("Pelipper"), *[empty_slot() for _ in range(4)]]
    five_partial = [
        *[_locked(f"Member{i}") for i in range(5)],
        Slot(species=Attr("Sixth", locked=True)),
    ]
    complete = [_locked(f"Member{i}") for i in range(6)]

    assert team_phase(_state(empty)) == "empty"
    assert team_phase(_state(partial)) == "empty"
    assert team_phase(_state(one)) == "single_locked"
    assert team_phase(_state(two)) == "multi_locked"
    assert team_phase(_state(five_partial)) == "multi_locked"
    assert team_phase(_state(complete)) == "complete"
    assert _route_team_phase(_state(complete)) == "complete"


def test_single_locked_runs_existing_helpers_in_required_order():
    state = _state([_locked("Kingambit"), *[empty_slot() for _ in range(5)]])
    context = SlotFillContext(
        anchor={"species": "Kingambit"},
        role_shape_context=RoleShapeContext(),
        threat_counter_results=[],
        support_needs=[],
    )
    order: list[str] = []

    def annotate(ctx):
        order.append("annotate")
        ctx.annotated_candidates = []
        return []

    def resolve(ctx, _state, **_kwargs):
        order.append("resolve")
        ctx.need_resolved_candidates = ["Farigiraf"]
        return ["Farigiraf"]

    def beneficiaries(ctx, _decision, _state, **_kwargs):
        order.append("beneficiaries")
        return ctx.need_resolved_candidates or []

    def merge(ctx):
        order.append("merge")
        ctx.annotated_candidates = [
            AnnotatedCandidate("Farigiraf", (), "need")
        ]
        return ctx.annotated_candidates

    def terminal(_ctx, _state, *, slot_index):
        order.append("terminal")
        assert slot_index == 1
        return SlotFillTerminalResult(
            presentation=SlotFillPresentation(
                1, (PresentedCandidate("Farigiraf", "need", ()),)
            ),
            state_updates={
                "pending_presentation": {
                    "schema_version": 1,
                    "kind": "candidate_selection",
                    "slot_index": 1,
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
        patch("recommender.slot_fill.annotate_overlap", side_effect=annotate),
        patch("recommender.slot_fill.resolve_all_support_needs", side_effect=resolve),
        patch(
            "recommender.slot_fill.resolve_condition_beneficiaries",
            side_effect=beneficiaries,
        ),
        patch("recommender.slot_fill.merge_need_resolved", side_effect=merge),
        patch("recommender.slot_fill.run_slot_fill_terminal", side_effect=terminal),
    ):
        result = discover_single_locked(state)

    assert order == ["annotate", "resolve", "beneficiaries", "merge", "terminal"]
    assert result["pending_presentation"]["options"][0]["species"] == "Farigiraf"
    assert result["coverage"] == []
    assert result["spofs"] == []
    assert result["shared_teammates"] is None


def test_single_locked_passes_ownership_mode_and_expanded_owned_ids():
    from recommender.team_candidates import owned_species_ids

    state = _state([_locked("Kingambit"), *[empty_slot() for _ in range(5)]])
    state["available_pool"] = [{"species": "Swampert"}]
    state["ownership_mode"] = "owned_only"
    context = SlotFillContext(
        anchor={"species": "Kingambit"},
        role_shape_context=RoleShapeContext(),
        threat_counter_results=[],
        support_needs=[],
    )
    captured: dict = {}
    captured_ben: dict = {}

    def resolve(ctx, _state, **kwargs):
        captured.update(kwargs)
        ctx.need_resolved_candidates = []
        return []

    def beneficiaries(ctx, _decision, _state, **kwargs):
        captured_ben.update(kwargs)
        return ctx.need_resolved_candidates or []

    with (
        patch(
            "recommender.slot_fill.build_anchored_slot_fill_context",
            return_value=AnchoredSlotDiscovery(context, object(), object(), False),
        ),
        patch("recommender.slot_fill.annotate_overlap", return_value=[]),
        patch("recommender.slot_fill.resolve_all_support_needs", side_effect=resolve),
        patch(
            "recommender.slot_fill.resolve_condition_beneficiaries",
            side_effect=beneficiaries,
        ),
        patch("recommender.slot_fill.merge_need_resolved", return_value=[]),
        patch("recommender.propose.fill_team_draft", return_value={}),
    ):
        discover_single_locked(state)

    assert captured.get("ownership_mode") == "owned_only"
    assert captured.get("available_species") == owned_species_ids(state)
    assert "swampertmega" in captured["available_species"]
    assert captured_ben.get("ownership_mode") == "owned_only"
    assert captured_ben.get("available_species") == owned_species_ids(state)
    assert "swampertmega" in captured_ben["available_species"]


def test_single_locked_owned_only_presents_expanded_mega_from_real_need_resolution():
    """End-to-end: real resolve_all_support_needs + merge + present.

    Threat counters are emptied so candidates must come from need resolution (threats
    are not ownership-filtered in single_locked). Slowbro→Slowbro-Mega is used because
    Mega Swampert does not learn any current need-satisfier move; Slowbro-Mega learns
    Trick Room and exercises the same base→Mega ownership expansion.
    """
    from recommender.ids import to_id

    archaludon = Slot(
        role=Attr("bulky_rain_attacker", locked=True),
        species=Attr("Archaludon", locked=True),
        ability=Attr("Stamina", locked=True),
        item=Attr("Assault Vest", locked=True),
        moveset=Attr(
            ["Dragon Pulse", "Electro Shot", "Body Press", "Flash Cannon"],
            locked=True,
        ),
        spread=Attr(dict(SPREAD), locked=True),
        nature=Attr("Modest", locked=True),
    )
    state = _state([archaludon, *[empty_slot() for _ in range(5)]])
    state["available_pool"] = [{"species": "Slowbro"}]
    state["ownership_mode"] = "owned_only"

    with patch(
        "recommender.threat_counters.query_threat_counters",
        return_value=TeamThreatDiscovery(status="available", candidates=()),
    ):
        result = discover_single_locked(state)

    pending = result["pending_presentation"]
    assert pending is not None
    assert pending["kind"] == "candidate_selection"
    options = [option["species"] for option in pending["options"]]
    option_ids = {to_id(name) for name in options}
    assert "slowbromega" in option_ids, options


def test_single_locked_pelipper_presents_rain_condition_beneficiary():
    pelipper = Slot(
        role=Attr("rain_setter", locked=True),
        species=Attr("Pelipper", locked=True),
        ability=Attr("Drizzle", locked=True),
        item=Attr("Focus Sash", locked=True),
        moveset=Attr(
            ["Hurricane", "Weather Ball", "Tailwind", "Protect"],
            locked=True,
        ),
        spread=Attr(dict(SPREAD), locked=True),
        nature=Attr("Modest", locked=True),
    )
    state = _state([pelipper, *[empty_slot() for _ in range(5)]])

    with patch(
        "recommender.threat_counters.query_threat_counters",
        return_value=TeamThreatDiscovery(status="available", candidates=()),
    ):
        result = discover_single_locked(state)

    pending = result["pending_presentation"]
    assert pending is not None
    tokens: list[str] = []
    for option in pending["options"]:
        for ev in option.get("evidence") or ():
            tokens.extend(getattr(ev, "evidence", ()) or ())
    assert "need:condition_beneficiary" in tokens
    assert "condition:Rain" in tokens


def test_single_locked_partial_open_slot_uses_legacy_fallback():
    state = _state(
        [
            _locked("Kingambit"),
            Slot(role=Attr("trick_room_setter")),
            *[empty_slot() for _ in range(4)],
        ]
    )
    with (
        patch(
            "recommender.propose.fill_team_draft",
            return_value={"team_draft": state["team_draft"]},
        ) as fill,
        patch("recommender.slot_fill.build_anchored_slot_fill_context") as build,
    ):
        result = discover_single_locked(state)

    fill.assert_called_once()
    build.assert_not_called()
    assert result["last_team_review"] is None


def test_single_locked_empty_candidate_set_uses_legacy_fallback():
    state = _state([_locked("Kingambit"), *[empty_slot() for _ in range(5)]])
    context = SlotFillContext(
        anchor={"species": "Kingambit"},
        role_shape_context=RoleShapeContext(),
        threat_counter_results=[],
        support_needs=[],
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
        patch("recommender.slot_fill.merge_need_resolved", return_value=[]),
        patch("recommender.propose.fill_team_draft", return_value={}) as fill,
        patch("recommender.slot_fill.run_slot_fill_terminal") as terminal,
    ):
        result = discover_single_locked(state)

    fill.assert_called_once()
    terminal.assert_not_called()
    assert result == {
        "coverage": [],
        "spofs": [],
        "shared_teammates": None,
        "last_team_review": None,
        "candidate_discovery_error": None,
    }


def test_single_locked_degraded_empty_does_not_call_fill_team_draft():
    state = _state([_locked("Kingambit"), *[empty_slot() for _ in range(5)]])
    error = CandidateDiscoveryError(
        kind="calc_unavailable",
        stage="candidate_verification",
        message="calc down",
        retryable=True,
        exception_type="CalcClientError",
    )
    context = SlotFillContext(
        anchor={"species": "Kingambit"},
        role_shape_context=RoleShapeContext(),
        threat_counter_results=[],
        support_needs=[],
        threat_discovery_status="degraded",
        threat_discovery_error=error,
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
        patch("recommender.slot_fill.merge_need_resolved", return_value=[]),
        patch("recommender.propose.fill_team_draft", return_value={}) as fill,
        patch("recommender.slot_fill.run_slot_fill_terminal") as terminal,
    ):
        result = discover_single_locked(state)

    fill.assert_not_called()
    terminal.assert_not_called()
    assert result["candidate_discovery_error"] is error
    assert result["pending_presentation"] is None


def test_single_locked_degraded_with_candidates_presents_without_fill_team_draft():
    state = _state([_locked("Kingambit"), *[empty_slot() for _ in range(5)]])
    error = CandidateDiscoveryError(
        kind="calc_unavailable",
        stage="candidate_verification",
        message="calc down",
        retryable=True,
        exception_type="CalcClientError",
    )
    static_row = ThreatCounterCandidate(
        candidate=ThreatCandidate(
            ladder_species="Incineroar",
            usage_rank=1,
            form="Incineroar",
            showdown_usage_pct=None,
            showdown_formes=(),
            spec={"species": "Incineroar"},
            build_source="ingame",
            threat_kinds=frozenset({"wall"}),
        ),
        threats_countered=("t1",),
        threats_countered_count=1,
        verified_score=0.0,
        verified_vs=(),
        estimate_kind="static",
    )
    context = SlotFillContext(
        anchor={"species": "Kingambit"},
        role_shape_context=RoleShapeContext(),
        threat_counter_results=[static_row],
        support_needs=[],
        threat_discovery_status="degraded",
        threat_discovery_error=error,
    )

    def fake_merge(ctx: SlotFillContext) -> list:
        ctx.annotated_candidates = [
            AnnotatedCandidate(
                species="Incineroar",
                matching_needs=(),
                source="threat",
                threat_row=static_row,
                evidence=(),
            )
        ]
        return ctx.annotated_candidates

    pending = {
        "schema_version": 1,
        "kind": "candidate_selection",
        "slot_index": 1,
        "options": [{"species": "Incineroar", "source": "threat", "evidence": ()}],
    }
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
        patch("recommender.slot_fill.merge_need_resolved", side_effect=fake_merge),
        patch("recommender.propose.fill_team_draft", return_value={}) as fill,
        patch(
            "recommender.slot_fill.run_slot_fill_terminal",
            return_value=SlotFillTerminalResult(
                presentation=SlotFillPresentation(
                    slot_index=1,
                    candidates=(
                        PresentedCandidate(
                            species="Incineroar", source="threat", evidence=()
                        ),
                    ),
                ),
                state_updates={"pending_presentation": pending},
                deferred=False,
            ),
        ) as terminal,
    ):
        result = discover_single_locked(state)

    fill.assert_not_called()
    terminal.assert_called_once()
    assert result["pending_presentation"] == pending
    assert result["candidate_discovery_error"] is error
    assert result["candidate_discovery_error"].kind == "calc_unavailable"


def test_single_locked_degraded_evidence_tokens():
    from recommender.slot_fill import _threat_evidence

    error = CandidateDiscoveryError(
        kind="calc_unavailable",
        stage="candidate_verification",
        message="calc down",
        retryable=True,
    )
    row = ThreatCounterCandidate(
        candidate=ThreatCandidate(
            ladder_species="Incineroar",
            usage_rank=1,
            form="Incineroar",
            showdown_usage_pct=None,
            showdown_formes=(),
            spec={"species": "Incineroar"},
            build_source="ingame",
            threat_kinds=frozenset({"wall", "ko_threshold"}),
        ),
        threats_countered=("t1",),
        threats_countered_count=1,
        verified_score=99.0,
        verified_vs=(),
        estimate_kind="static",
    )
    evidence = _threat_evidence(row, degradation_kind="calc_unavailable")
    assert len(evidence) == 1
    assert evidence[0].basis == "mechanical_only"
    assert evidence[0].confidence == "low"
    assert "static_type_estimate" in evidence[0].evidence
    assert "calc_unavailable" in evidence[0].evidence
    assert "wall_axis" in evidence[0].evidence
    assert "ko_threshold_proxy" in evidence[0].evidence
    assert not any(item.startswith("verified_score:") for item in evidence[0].evidence)

    state = _state([_locked("Kingambit"), *[empty_slot() for _ in range(5)]])
    context = SlotFillContext(
        anchor={"species": "Kingambit"},
        role_shape_context=RoleShapeContext(),
        threat_counter_results=[row],
        support_needs=[],
        need_resolved_candidates=[],
        threat_discovery_status="degraded",
        threat_discovery_error=error,
    )
    from recommender.slot_fill import annotate_overlap, merge_need_resolved

    annotate_overlap(context)
    merge_need_resolved(context)
    threat_ev = context.annotated_candidates[0].evidence[0]
    assert threat_ev.basis == "mechanical_only"
    assert threat_ev.confidence == "low"
    assert "static_type_estimate" in threat_ev.evidence
    assert not any(item.startswith("verified_score:") for item in threat_ev.evidence)


def test_empty_bootstrap_clears_stale_signals_and_prompts_for_intake():
    state = _state([empty_slot() for _ in range(6)])
    state.update(
        {
            "coverage": [object()],  # type: ignore[list-item]
            "spofs": [object()],  # type: ignore[list-item]
            "last_team_review": TeamReviewResult([], [], []),
        }
    )

    result = bootstrap_direction(state)

    assert result["coverage"] == []
    assert result["spofs"] == []
    assert result["shared_teammates"] is None
    assert result["last_team_review"] is None
    assert result["candidate_discovery_error"] is None
    assert result["pending_presentation"]["kind"] == "bootstrap_intake"


def test_only_multi_refresh_publishes_shared_signal_result():
    state = _state([_locked("A"), _locked("B"), *[empty_slot() for _ in range(4)]])
    review = TeamReviewResult(threats=[], coverage=[], spofs=[])
    shared = object()
    config = {"configurable": {"thread_id": "phase-signals"}}
    with (
        patch("recommender.nodes._compute_team_review", return_value=review) as compute,
        patch(
            "recommender.nodes.query_shared_teammates", return_value=shared
        ) as query_shared,
    ):
        refreshed = refresh_team_signals(state, config)  # type: ignore[arg-type]
        completed = generate_team_review(state, config)  # type: ignore[arg-type]

    assert compute.call_count == 2
    query_shared.assert_called_once()
    query_shared.assert_called_with(["A", "B"], "champions")
    assert refreshed["coverage"] == []
    assert refreshed["spofs"] == []
    assert refreshed["shared_teammates"] is shared
    assert refreshed["last_team_review"] is None
    assert refreshed["candidate_discovery_error"] is None
    assert "condition_resilience" in refreshed
    assert completed["last_team_review"] is review
    assert completed["coverage"] is review.coverage
    assert completed["spofs"] is review.spofs
    assert completed["shared_teammates"] is None
    assert completed["condition_resilience"] is None
    assert completed["candidate_discovery_error"] is None


def test_generate_team_review_surfaces_calc_unavailable_error():
    state = _state([_locked(f"Member{i}") for i in range(6)])
    error = CandidateDiscoveryError(
        kind="calc_unavailable",
        stage="coverage",
        message="calc down",
        retryable=True,
        exception_type="CalcClientError",
    )
    review = TeamReviewResult(
        [], [], [], status="unavailable", error=error
    )
    config = {"configurable": {"thread_id": "review-unavailable"}}
    with patch("recommender.nodes._compute_team_review", return_value=review):
        result = generate_team_review(state, config)  # type: ignore[arg-type]
    assert result["candidate_discovery_error"] is error
    assert result["candidate_discovery_error"].kind == "calc_unavailable"
    assert result["last_team_review"] is review
    assert result["coverage"] == []
    assert result["spofs"] == []


def test_generate_team_review_surfaces_calc_incomplete_error():
    state = _state([_locked(f"Member{i}") for i in range(6)])
    error = CandidateDiscoveryError(
        kind="calc_incomplete",
        stage="spof",
        message="bad batch",
        retryable=True,
        exception_type="MatchupEvidenceError",
    )
    review = TeamReviewResult(
        [], [], [], status="unavailable", error=error
    )
    config = {"configurable": {"thread_id": "review-incomplete"}}
    with patch("recommender.nodes._compute_team_review", return_value=review):
        result = generate_team_review(state, config)  # type: ignore[arg-type]
    assert result["candidate_discovery_error"] is error
    assert result["candidate_discovery_error"].kind == "calc_incomplete"


def test_multi_signal_refresh_binds_full_result_cache_to_graph_thread():
    state = _state([_locked("A"), _locked("B"), *[empty_slot() for _ in range(4)]])
    config = {"configurable": {"thread_id": "phase-signals"}}
    with (
        patch("recommender.matchup.bind_matchup_memo_thread") as bind,
        patch("recommender.nodes.get_relevant_threats", return_value=[]),
        patch("recommender.nodes.compute_team_coverage", return_value=[]),
        patch("recommender.nodes.detect_spof", return_value=[]),
        patch("recommender.nodes.query_shared_teammates", return_value=None),
    ):
        result = refresh_team_signals(state, config)  # type: ignore[arg-type]

    bind.assert_called_once_with("phase-signals")
    assert result["coverage"] == []
    assert result["spofs"] == []
    assert result["shared_teammates"] is None
    assert result["last_team_review"] is None
    assert result["candidate_discovery_error"] is None
    assert "condition_resilience" in result


def test_second_lock_routes_through_multi_discovery():
    before = _state([_locked("A"), *[empty_slot() for _ in range(5)]])
    after = [_locked("A"), _locked("B"), *[empty_slot() for _ in range(4)]]
    with (
        patch(
            "recommender.nodes.classify_pending",
            return_value={"turn_intent": "lock", "turn_payload": {}},
        ),
        patch("recommender.graph.nodes.apply_lock", return_value={"team_draft": after}),
        patch(
            "recommender.graph.nodes.discover_multi_locked",
            return_value={"coverage": [], "spofs": [], "last_team_review": None},
        ) as discover,
        patch("recommender.graph.nodes.propose_team_draft", return_value={}),
    ):
        graph = build_graph().compile()
        result = graph.invoke({**before, "pending_input": "lock it"})

    discover.assert_called_once()
    assert result["team_draft"] == after
    assert result["coverage"] == []


def test_multi_partial_slot_refreshes_signals_then_uses_legacy_fallback():
    partial = Slot(species=Attr("Farigiraf"))
    state = _state(
        [_locked("A"), _locked("B"), partial, *[empty_slot() for _ in range(3)]]
    )
    review = TeamReviewResult([], [], [])
    shared = object()
    with (
        patch("recommender.nodes._compute_team_review", return_value=review),
        patch("recommender.nodes.query_shared_teammates", return_value=shared),
        patch(
            "recommender.propose.fill_team_draft",
            return_value={"team_draft": state["team_draft"]},
        ) as fill,
    ):
        result = discover_multi_locked(state, {})  # type: ignore[arg-type]
    fill.assert_called_once()
    assert result["shared_teammates"] is shared
    assert result["candidate_discovery_error"] is None


def test_multi_unsupported_hard_constraint_fails_closed():
    state = _state(
        [_locked("A"), _locked("B"), *[empty_slot() for _ in range(4)]]
    )
    state["constraints"] = [
        Constraint("hard", "must be shiny", 1, True, "team_wide")
    ]
    review = TeamReviewResult([], [], [])
    with (
        patch("recommender.nodes._compute_team_review", return_value=review),
        patch("recommender.nodes.query_shared_teammates", return_value=None),
    ):
        result = discover_multi_locked(state, {})  # type: ignore[arg-type]
    error = result["candidate_discovery_error"]
    assert isinstance(error, CandidateDiscoveryError)
    assert error.kind == "unsupported_constraint"
    assert result["pending_presentation"] is None


def test_sixth_atomic_commit_routes_directly_to_complete_review():
    before = _state([*[_locked(f"Member{i}") for i in range(5)], empty_slot()])
    after = [_locked(f"Member{i}") for i in range(6)]
    review = TeamReviewResult(threats=[], coverage=[], spofs=[])
    with (
        patch(
            "recommender.nodes.classify_pending",
            return_value={"turn_intent": "full_slot_confirmed"},
        ),
        patch(
            "recommender.graph.nodes.commit_full_slot",
            return_value={"team_draft": after},
        ),
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
