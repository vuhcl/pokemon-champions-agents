from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from recommender.matchup import MatchupEvidenceError, MatchupResult
from recommender.nodes import classify_pending, commit_full_slot, discover_multi_locked
from recommender.slot_fill import (
    AnnotatedCandidate,
    AnchoredSupportNeed,
    NeedResolvedCandidate,
    SlotFillContext,
    SlotFillResponse,
    build_provisional_slot,
    run_slot_fill_terminal,
)
from recommender.state import (
    Attr,
    CandidateDiscoveryError,
    CandidateEvidence,
    RecommenderState,
    SPOFFinding,
    Slot,
    TeamReviewResult,
    TeamThreatDiscovery,
    TeamThreatObjectiveRow,
    TargetRoleDecision,
    ThreatCandidate,
    ThreatCounterCandidate,
    ThreatCoverageResult,
    UnresolvedTargetRoleDecision,
    empty_slot,
)
from recommender.support_needs import SupportNeed
from recommender.team_candidates import (
    _rank_category_a,
    _rank_key,
    annotate_composition_impact,
    build_team_threat_objective,
    candidate_core_slot_conflicts,
    collect_locked_anchor_contexts,
    material_completion_preferences,
    merge_multi_locked_candidates,
    rank_multi_locked_by_category,
    rank_multi_locked_candidates,
    select_diverse_candidates,
    SUPPORT_CATEGORY_B_POOL_N,
)
from recommender.teammate_types import (
    SharedAnchorEvidence,
    SharedTeammate,
    SharedTeammateQueryResult,
)
from recommender.threat_counters import aggregate_verified


def _threat(species: str, usage_rank: int | None = 1) -> ThreatCandidate:
    return ThreatCandidate(
        ladder_species=species,
        usage_rank=usage_rank,
        form=species,
        showdown_usage_pct=None,
        showdown_formes=(),
        spec={"species": species},
        build_source="test",
    )


def _counter(
    species: str,
    *,
    threat_id: str = "target",
    outcome: str = "clean_kill",
    severity: str = "costly",
    usage_rank: int | None = 1,
    matchups: tuple[tuple[str, str, str], ...] | None = None,
) -> ThreatCounterCandidate:
    rows = matchups or ((threat_id, outcome, severity),)
    verified = tuple(
        (
            row_threat_id,
            MatchupResult(outcome=row_outcome, severity=row_severity),  # type: ignore[arg-type]
        )
        for row_threat_id, row_outcome, row_severity in rows
    )
    return ThreatCounterCandidate(
        candidate=_threat(species, usage_rank=usage_rank),
        threats_countered=tuple(row[0] for row in rows),
        threats_countered_count=len(rows),
        verified_score=aggregate_verified([result for _, result in verified]),
        verified_vs=verified,
    )


def _objective(
    *,
    threat_id: str = "target",
    kinds: frozenset[str] = frozenset({"uncovered"}),
) -> TeamThreatObjectiveRow:
    return TeamThreatObjectiveRow(_threat(threat_id), kinds)  # type: ignore[arg-type]


def _need(category: str, trigger: str | None = None) -> SupportNeed:
    return SupportNeed(
        category=category,  # type: ignore[arg-type]
        name=category,
        description=category,
        trigger=trigger,
    )


def _evidence(
    basis: str = "mechanical_only",
    *,
    branch: str = "need",
    anchor_id: str | None = None,
) -> CandidateEvidence:
    return CandidateEvidence(
        basis=basis,  # type: ignore[arg-type]
        confidence="medium",
        producer_name="test",
        branch=branch,  # type: ignore[arg-type]
        origin_anchor_id=anchor_id,
    )


def _candidate(
    species: str,
    *,
    fit: str = "neutral",
    fills_essential_gap: bool = False,
    threat: ThreatCounterCandidate | None = None,
    anchors: frozenset[str] = frozenset(),
    needs: tuple[AnchoredSupportNeed, ...] = (),
    evidence: tuple[CandidateEvidence, ...] = (),
    spec: dict | None = None,
) -> AnnotatedCandidate:
    return AnnotatedCandidate(
        species=species,
        matching_needs=tuple(row.need for row in needs),
        source="threat" if threat else "need",
        threat_row=threat,
        spec=spec or {"species": species},
        evidence=evidence or (_evidence(),),
        branches=frozenset({"threat" if threat else "need"}),
        anchor_ids=anchors,
        composition_fit=fit,  # type: ignore[arg-type]
        fills_essential_gap=fills_essential_gap,
        anchored_needs=needs,
    )


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
        moveset=Attr(moves or ["Tackle", "Protect", "Rest", "Sleep Talk"], locked=True),
        spread=Attr(
            {"hp": 32, "atk": 32, "def": 2, "spa": 0, "spd": 0, "spe": 0},
            locked=True,
        ),
        nature=Attr("Adamant", locked=True),
    )


def _state(draft: list[Slot] | None = None) -> RecommenderState:
    return {
        "format_id": "[Gen 9 Champions] VGC 2026 Reg M-B",
        "game_type": "doubles",
        "regulation_mod": "champions-reg-mb",
        "picked_team_size": 4,
        "available_pool": [],
        "team_draft": draft or [empty_slot() for _ in range(6)],
        "archetype": Attr(),
        "rejected": [],
        "constraints": [],
        "messages": [],
    }


def _shared(*rows: SharedTeammate, status: str = "available"):
    return SharedTeammateQueryResult(
        anchor_results=(),
        status=status,  # type: ignore[arg-type]
        rows=rows if status == "available" else None,
        unavailable_anchors=(),
        ordering="test",
        caveats=(),
    )


def _shared_row(species: str, attribution: str = "exact") -> SharedTeammate:
    return SharedTeammate(
        species_id=species.lower(),
        name=species,
        per_anchor=(SharedAnchorEvidence("a", 2, 20.0),),
        worst_rank=2,
        min_conditional_pct=20.0,
        attribution_status=attribution,  # type: ignore[arg-type]
    )


def test_locked_slot_order_does_not_change_multi_rank():
    need = _need("screens")
    first = _candidate(
        "Alpha",
        anchors=frozenset({"a"}),
        needs=(AnchoredSupportNeed(0, "a", need),),
    )
    permuted = replace(
        first,
        anchor_slot_indices=frozenset({4}),
        anchored_needs=(AnchoredSupportNeed(4, "a", need),),
    )
    beta = _candidate("Beta")
    kwargs = dict(
        objective=(),
        preference=None,
        ownership_mode="off",
        owned_species=frozenset(),
    )
    assert [row.species for row in rank_multi_locked_candidates([first, beta], **kwargs)] == [
        row.species for row in rank_multi_locked_candidates([permuted, beta], **kwargs)
    ]


def test_all_anchors_contribute_before_global_cut():
    late = AnchoredSupportNeed(5, "late", _need("screens"))
    resolved = NeedResolvedCandidate(
        "Farigiraf", (late.need,), (_evidence(anchor_id="late"),), (late,)
    )
    contexts = [
        SimpleNamespace(resolved_build=SimpleNamespace(species="A"), support_needs=()),
        SimpleNamespace(resolved_build=SimpleNamespace(species="B"), support_needs=(late,)),
    ]
    with patch(
        "recommender.team_candidates.resolve_all_support_needs",
        return_value=[resolved],
    ):
        rows = merge_multi_locked_candidates(
            _state(),
            contexts,  # type: ignore[arg-type]
            (),
            None,
            ownership_mode="off",
            owned_species=frozenset(),
        )
    assert [row.species for row in rows] == ["Farigiraf"]
    assert rows[0].anchor_ids == frozenset({"late"})


def test_duplicate_need_rows_do_not_inflate_anchor_breadth():
    need = _need("screens")
    duplicate = _candidate(
        "Alpha",
        anchors=frozenset({"a"}),
        needs=(
            AnchoredSupportNeed(0, "a", need),
            AnchoredSupportNeed(0, "a", need),
        ),
    )
    broad = _candidate(
        "Beta",
        anchors=frozenset({"a", "b"}),
        needs=(
            AnchoredSupportNeed(0, "a", need),
            AnchoredSupportNeed(1, "b", need),
        ),
    )
    ranked = rank_multi_locked_candidates(
        [duplicate, broad],
        objective=(),
        preference=None,
        ownership_mode="off",
        owned_species=frozenset(),
    )
    assert ranked[0].species == "Beta"


def test_team_wide_threat_objective_ignores_anchor_local_false_gap():
    covered = ThreatCoverageResult(
        {"species": "Covered"},
        MatchupResult("clean_kill", "costly"),
        [1],
        None,
        False,
    )
    uncovered = ThreatCoverageResult(
        {"species": "Gap"},
        MatchupResult("no_answer", "toss-up"),
        [],
        None,
        True,
    )
    objective = build_team_threat_objective(
        TeamReviewResult([_threat("Covered"), _threat("Gap")], [covered, uncovered], [])
    )
    assert [row.threat.form for row in objective] == ["Gap"]


def test_spof_improvement_rewards_second_verified_answer():
    baseline = ThreatCoverageResult(
        {"species": "Target"},
        MatchupResult("clean_kill", "costly"),
        [0],
        None,
        False,
    )
    objective = build_team_threat_objective(
        TeamReviewResult(
            [_threat("Target")],
            [baseline],
            [SPOFFinding(0, [{"species": "Target"}], {"target": "costly"})],
        )
    )
    ranked = rank_multi_locked_candidates(
        [_candidate("Answer", threat=_counter("Answer")), _candidate("Other")],
        objective=objective,
        preference=None,
        ownership_mode="off",
        owned_species=frozenset(),
    )
    assert objective[0].kinds == frozenset({"spof"})
    assert ranked[0].species == "Answer"


def test_candidate_local_provenance_survives_merge_and_selection():
    need = AnchoredSupportNeed(0, "anchor", _need("trick_room"))
    support = NeedResolvedCandidate(
        "Farigiraf",
        (need.need,),
        (_evidence("compendium_backed", anchor_id="anchor"),),
        (need,),
    )
    shared = _shared(_shared_row("Farigiraf"))
    with patch(
        "recommender.team_candidates.resolve_all_support_needs",
        return_value=[support],
    ):
        rows = merge_multi_locked_candidates(
            _state(),
            [SimpleNamespace(resolved_build=SimpleNamespace(species="A"), support_needs=(need,))],  # type: ignore[list-item]
            (_counter("Farigiraf"),),
            shared,
            ownership_mode="off",
            owned_species=frozenset(),
        )
    ctx = SlotFillContext(None, None, annotated_candidates=rows, candidates_pre_ranked=True)
    terminal = run_slot_fill_terminal(
        ctx, _state(), slot_index=0, response=SlotFillResponse("choose", "Farigiraf")
    )
    intent = terminal.state_updates["pending_slot_intent"]
    assert {item.branch for item in intent.evidence} == {"threat", "need", "teammate"}
    assert intent.source == "mixed"


def test_target_role_is_candidate_local():
    trick = AnchoredSupportNeed(0, "a", _need("trick_room"))
    support = NeedResolvedCandidate(
        "Farigiraf", (trick.need,), (_evidence(anchor_id="a"),), (trick,)
    )
    with patch(
        "recommender.team_candidates.resolve_all_support_needs",
        return_value=[support],
    ):
        rows = merge_multi_locked_candidates(
            _state(),
            [SimpleNamespace(resolved_build=SimpleNamespace(species="A"), support_needs=(trick,))],  # type: ignore[list-item]
            (_counter("Incineroar"),),
            _shared(_shared_row("Rillaboom")),
            ownership_mode="off",
            owned_species=frozenset(),
        )
    by_species = {row.species: row for row in rows}
    assert by_species["Farigiraf"].target_role_decision is not None
    # Threat/teammate-only rows may receive kit identity fallback (not open-slot inherit).
    assert isinstance(
        by_species["Incineroar"].target_role_decision, TargetRoleDecision
    )
    assert (
        by_species["Incineroar"].target_role_decision.producer_name
        == "slot_fill_kit_role_policy"
    )
    assert by_species["Rillaboom"].target_role_decision is None or isinstance(
        by_species["Rillaboom"].target_role_decision, TargetRoleDecision
    )


def test_incompatible_candidate_support_roles_remain_unresolved():
    needs = (
        AnchoredSupportNeed(0, "a", _need("trick_room")),
        AnchoredSupportNeed(1, "b", _need("tailwind")),
    )
    support = NeedResolvedCandidate(
        "Farigiraf",
        tuple(row.need for row in needs),
        (_evidence(),),
        needs,
    )
    with patch(
        "recommender.team_candidates.resolve_all_support_needs",
        return_value=[support],
    ):
        row = merge_multi_locked_candidates(
            _state(),
            [SimpleNamespace(resolved_build=SimpleNamespace(species="A"), support_needs=needs)],  # type: ignore[list-item]
            (),
            None,
            ownership_mode="off",
            owned_species=frozenset(),
        )[0]
    assert isinstance(row.target_role_decision, UnresolvedTargetRoleDecision)
    assert row.target_role_decision.reason == "incompatible_support_roles"


def test_compendium_stays_first_and_rejections_still_apply():
    from recommender.slot_fill import resolve_need_candidates

    rows = resolve_need_candidates(_need("trick_room"), _state())
    assert rows
    assert rows[0].evidence[0].basis == "compendium_backed"


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("off", {"Owned", "Unowned"}),
        ("owned_first", {"Owned", "Unowned"}),
        ("owned_last", {"Owned", "Unowned"}),
        ("owned_only", {"Owned"}),
    ],
)
def test_ownership_mode_applies_uniformly_to_every_candidate_branch(mode, expected):
    shared = _shared(_shared_row("Owned"), _shared_row("Unowned"))
    rows = merge_multi_locked_candidates(
        _state(),
        [],
        (_counter("Owned"), _counter("Unowned")),
        shared,
        ownership_mode=mode,
        owned_species=frozenset({"owned"}),
    )
    assert {row.species for row in rows} == expected


@pytest.mark.parametrize(
    "shared",
    [
        _shared(status="unavailable"),
        _shared(),
        _shared(_shared_row("Ambiguous", "ambiguous")),
    ],
)
def test_shared_teammate_unavailable_empty_and_nonexact_are_neutral(shared):
    rows = merge_multi_locked_candidates(
        _state(),
        [],
        (),
        shared,
        ownership_mode="off",
        owned_species=frozenset(),
    )
    assert rows == []


def test_shared_only_candidate_cannot_win_without_team_fit():
    ranked = rank_multi_locked_candidates(
        [
            _candidate("Shared", fit="neutral", evidence=(_evidence("teammate_backed"),)),
            _candidate("Fit", fit="complementary"),
        ],
        objective=(),
        preference=None,
        ownership_mode="off",
        owned_species=frozenset(),
    )
    assert ranked[0].species == "Fit"


def test_basculegion_regression_does_not_rank_redundant_rain_attacker_first():
    draft = [
        _locked("Archaludon", role="bulky_rain_attacker", ability="Stamina", moves=["Dragon Pulse", "Electro Shot", "Protect", "Body Press"]),
        _locked("Pelipper", role="rain_support", ability="Drizzle", moves=["Hurricane", "Tailwind", "Wide Guard", "Protect"]),
        _locked("Mega Swampert", role="physical_rain_attacker", ability="Swift Swim", item="Swampertite", moves=["Wave Crash", "Earthquake", "Ice Punch", "Protect"]),
        *[empty_slot() for _ in range(3)],
    ]
    screens = AnchoredSupportNeed(0, "archaludon", _need("screens"))
    support = NeedResolvedCandidate(
        "Grimmsnarl",
        (screens.need,),
        (_evidence(anchor_id="archaludon"),),
        (screens,),
    )
    contexts = [
        SimpleNamespace(
            resolved_build=SimpleNamespace(species=species),
            support_needs=(screens,) if species == "Archaludon" else (),
        )
        for species in ("Archaludon", "Pelipper", "Mega Swampert")
    ]
    shared = _shared(_shared_row("Basculegion"), _shared_row("Grimmsnarl"))
    with patch(
        "recommender.team_candidates.resolve_all_support_needs",
        return_value=[support],
    ):
        candidates = merge_multi_locked_candidates(
            _state(draft),
            contexts,  # type: ignore[arg-type]
            (),
            shared,
            ownership_mode="off",
            owned_species=frozenset(),
        )
    specs = {
        "Basculegion": {"species": "Basculegion", "ability": "Swift Swim", "moves": ["Wave Crash", "Last Respects", "Aqua Jet", "Protect"]},
        "Grimmsnarl": {"species": "Grimmsnarl", "ability": "Prankster", "item": "Light Clay", "moves": ["Reflect", "Light Screen", "Parting Shot", "Fake Out"]},
    }
    candidates = [replace(row, spec=specs[row.species]) for row in candidates]
    annotated = annotate_composition_impact(candidates, _state(draft))
    ranked = rank_multi_locked_candidates(
        annotated,
        objective=(),
        preference=None,
        ownership_mode="off",
        owned_species=frozenset(),
    )
    assert ranked[0].species == "Grimmsnarl"
    basculegion = next(row for row in ranked if row.species == "Basculegion")
    assert any(item.branch == "teammate" for item in basculegion.evidence)


def test_unknown_candidate_composition_is_neutral_not_guessed():
    row = annotate_composition_impact(
        [_candidate("Missingmon", spec={"species": "Missingmon"})],
        _state([_locked("Kingambit"), _locked("Pelipper"), *[empty_slot() for _ in range(4)]]),
    )[0]
    assert row.composition_fit == "neutral"


def test_completion_preference_only_prompts_when_rank_would_change():
    candidates = [_candidate("Attacker"), _candidate("Support")]
    with patch(
        "recommender.team_candidates._primary_function",
        side_effect=lambda row, _reg: "offense" if row.species == "Attacker" else "support",
    ):
        assert material_completion_preferences(
            candidates,
            objective=(),
            ownership_mode="off",
            owned_species=frozenset(),
        ) == ("attacker", "support", "balanced")
    result = classify_pending(
        "support",
        {
            "schema_version": 2,
            "kind": "completion_preference",
            "preference_options": ("attacker", "support", "balanced"),
        },
    )
    assert result["turn_intent"] == "continue"
    assert result["team_completion_preference"] == "support"


def test_multi_selection_reuses_existing_atomic_commit_lifecycle():
    decision = TargetRoleDecision(
        role_id="trick_room_setter",
        source="support_need",
        evidence=("trick_room",),
    )
    candidate = replace(
        _candidate("Farigiraf"), target_role_decision=decision  # type: ignore[arg-type]
    )
    compendium = _candidate(
        "Amoonguss", evidence=(_evidence("compendium_backed"),)
    )
    ctx = SlotFillContext(
        None,
        None,
        annotated_candidates=[candidate, compendium],
        candidates_pre_ranked=True,
    )
    terminal = run_slot_fill_terminal(ctx, _state(), slot_index=0)
    assert terminal.presentation.default == "Farigiraf"
    assert terminal.state_updates["pending_presentation"]["options"][0]["species"] == "Farigiraf"
    selected = run_slot_fill_terminal(
        ctx,
        _state(),
        slot_index=0,
        response=SlotFillResponse("choose", "Farigiraf"),
    )
    intent = selected.state_updates["pending_slot_intent"]
    moves = ["Psychic", "Hyper Voice", "Trick Room", "Protect"]
    spread = {"hp": 32, "atk": 0, "def": 0, "spa": 32, "spd": 2, "spe": 0}
    with (
        patch(
            "recommender.propose.featured_or_common_set",
            return_value={
                "species": "Farigiraf",
                "ability": "Armor Tail",
                "moves": moves,
                "item": "Sitrus Berry",
                "nature": "Modest",
            },
        ),
        patch(
            "recommender.propose.get_resolved_build",
            return_value={
                "spread": spread,
                "source_tier": "champions-native",
                "verified": True,
            },
        ),
    ):
        provisional = build_provisional_slot(intent, _state())
    state = {
        **_state(),
        "pending_slot_intent": intent,
        "provisional_slot": provisional,
        "pending_presentation": {
            "schema_version": 1,
            "kind": "full_build_confirmation",
            "slot_index": 0,
            "provisional_fingerprint": provisional.fingerprint,
        },
    }
    committed = commit_full_slot(state)
    assert committed["team_draft"][0].species.value == "Farigiraf"
    assert committed["team_draft"][0].species.locked


@pytest.mark.parametrize(
    "error",
    [
        MatchupEvidenceError("bad row"),
        MatchupEvidenceError("count mismatch"),
    ],
)
def test_calc_evidence_failure_aborts_multi_discovery_without_partial_ranking(error):
    """ADR-029: multi_locked stays fail-closed on calc-unavailable team review."""
    state = _state([_locked("A"), _locked("B"), *[empty_slot() for _ in range(4)]])
    discovery_error = CandidateDiscoveryError(
        "calc_incomplete",
        "coverage",
        str(error),
        True,
        type(error).__name__,
    )
    review = TeamReviewResult(
        [], [], [], status="unavailable", error=discovery_error
    )
    with (
        patch("recommender.nodes._compute_team_review", return_value=review),
        patch("recommender.nodes.query_shared_teammates", return_value=_shared()),
    ):
        result = discover_multi_locked(state, {})  # type: ignore[arg-type]
    assert result["pending_presentation"] is None
    assert result["candidate_discovery_error"] is discovery_error


def test_multi_locked_threat_branch_receives_expanded_owned_ids():
    state = _state([_locked("A"), _locked("B"), *[empty_slot() for _ in range(4)]])
    state["available_pool"] = [{"species": "Swampert"}]
    state["ownership_mode"] = "owned_only"
    review = TeamReviewResult([_threat("Target")], [], [])
    captured: dict = {}

    def capture_threats(objective, **kwargs):
        captured.update(kwargs)
        return TeamThreatDiscovery(status="available", candidates=(), error=None)

    with (
        patch("recommender.nodes._compute_team_review", return_value=review),
        patch("recommender.nodes.query_shared_teammates", return_value=_shared()),
        patch(
            "recommender.threat_counters.query_candidates_for_threats",
            side_effect=capture_threats,
        ),
        patch(
            "recommender.team_candidates.collect_locked_anchor_contexts",
            return_value=(),
        ),
        patch(
            "recommender.team_candidates.merge_multi_locked_candidates",
            return_value=[],
        ),
    ):
        discover_multi_locked(state, {})  # type: ignore[arg-type]

    pool = set(captured.get("available_pool") or ())
    assert "swampert" in pool
    assert "swampertmega" in pool
    assert captured.get("ownership_mode") == "owned_only"


def test_severe_composition_repair_outranks_minor_threat_gain():
    ranked = rank_multi_locked_candidates(
        [
            _candidate("Repair", fit="complementary"),
            _candidate(
                "Minor",
                fit="severe_duplication",
                threat=_counter("Minor", outcome="clean_kill", severity="toss-up"),
            ),
        ],
        objective=(_objective(),),
        preference=None,
        ownership_mode="off",
        owned_species=frozenset(),
    )
    assert ranked[0].species == "Repair"


def test_equal_impact_band_prefers_verified_threat_gain():
    ranked = rank_multi_locked_candidates(
        [
            _candidate("Answer", threat=_counter("Answer", severity="costly")),
            _candidate("Equal"),
        ],
        objective=(_objective(),),
        preference=None,
        ownership_mode="off",
        owned_species=frozenset(),
    )
    assert ranked[0].species == "Answer"


def test_composition_beats_toss_up_or_spof_gain():
    test_severe_composition_repair_outranks_minor_threat_gain()


def test_essential_gap_fill_outranks_high_volume_threat_coverage():
    """Regression for the rain-suggestion degradation bug (2026-08-16/17).

    A candidate that fills an essential/missing-provider condition gap (e.g.
    the only real Rain setter available for a team whose anchor's kit
    genuinely depends on Rain) must not be structurally excluded just
    because unrelated candidates have far more verified threat-coverage
    hits. Before this fix, fills_essential_gap wasn't a distinct ranking
    signal at all, so a need-only candidate with zero threat_row entries
    lost to literally any threat-branch candidate, no matter how essential
    the need — confirmed live: an essential Rain setter with 0 verified
    threat hits was outranked by ordinary attackers with 76 each and never
    appeared in the ranked pool at all.
    """
    ranked = rank_multi_locked_candidates(
        [
            _candidate("RainSetter", fills_essential_gap=True),
            _candidate(
                "OrdinaryAttacker",
                threat=_counter("OrdinaryAttacker", outcome="clean_kill", severity="decisive"),
            ),
        ],
        objective=(_objective(),),
        preference=None,
        ownership_mode="off",
        owned_species=frozenset(),
    )
    assert ranked[0].species == "RainSetter"


def test_essential_gap_fill_does_not_help_when_absent():
    """Sanity check: fills_essential_gap=False (the default) must not change
    existing ranking behavior — a plain complementary-fit candidate still
    loses to a decisive verified-threat answer, same as before this fix."""
    ranked = rank_multi_locked_candidates(
        [
            _candidate("Composition", fit="complementary"),
            _candidate(
                "Answer",
                fit="severe_duplication",
                threat=_counter("Answer", severity="decisive"),
            ),
        ],
        objective=(_objective(),),
        preference=None,
        ownership_mode="off",
        owned_species=frozenset(),
    )
    assert ranked[0].species == "Answer"


def test_decisive_or_costly_uncovered_closure_precedes_composition():
    ranked = rank_multi_locked_candidates(
        [
            _candidate("Composition", fit="complementary"),
            _candidate(
                "Answer",
                fit="severe_duplication",
                threat=_counter("Answer", severity="decisive"),
            ),
        ],
        objective=(_objective(),),
        preference=None,
        ownership_mode="off",
        owned_species=frozenset(),
    )
    assert ranked[0].species == "Answer"


@pytest.mark.parametrize("severity", ["decisive", "costly", "toss-up"])
def test_clean_kill_and_intentional_non_ko_answer_share_severity_precedence(
    severity,
):
    rows = [
        _candidate(
            "Alpha",
            threat=_counter("Alpha", outcome="clean_kill", severity=severity),
        ),
        _candidate(
            "Beta",
            threat=_counter(
                "Beta",
                outcome="intentional_non_ko_answer",
                severity=severity,
            ),
        ),
    ]
    ranked = rank_multi_locked_candidates(
        rows,
        objective=(_objective(),),
        preference=None,
        ownership_mode="off",
        owned_species=frozenset(),
    )
    assert [row.species for row in ranked] == ["Alpha", "Beta"]


def test_multi_threat_portfolio_counts_unconditional_answer_types_equally():
    objective = (
        _objective(threat_id="targeta"),
        _objective(threat_id="targetb"),
    )
    mixed = _candidate(
        "Alpha",
        threat=_counter(
            "Alpha",
            matchups=(
                ("targeta", "clean_kill", "costly"),
                ("targetb", "intentional_non_ko_answer", "costly"),
            ),
        ),
    )
    clean = _candidate(
        "Beta",
        threat=_counter(
            "Beta",
            matchups=(
                ("targeta", "clean_kill", "costly"),
                ("targetb", "clean_kill", "costly"),
            ),
        ),
    )
    ranked = rank_multi_locked_candidates(
        [clean, mixed],
        objective=objective,
        preference=None,
        ownership_mode="off",
        owned_species=frozenset(),
    )
    assert [row.species for row in ranked] == ["Alpha", "Beta"]


def test_usage_does_not_break_equal_candidate_ties():
    merged = merge_multi_locked_candidates(
        _state(),
        [],
        (
            _counter("Alpha", usage_rank=100),
            _counter("Beta", usage_rank=1),
        ),
        None,
        ownership_mode="off",
        owned_species=frozenset(),
    )
    assert {
        evidence.basis for row in merged for evidence in row.evidence
    } == {"usage_backed"}
    without_usage = merge_multi_locked_candidates(
        _state(),
        [],
        (_counter("No Usage", usage_rank=None),),
        None,
        ownership_mode="off",
        owned_species=frozenset(),
    )
    assert without_usage[0].evidence[0].basis == "mechanical_only"
    assert [
        row.species
        for row in rank_multi_locked_candidates(
            list(reversed(merged)),
            objective=(),
            preference=None,
            ownership_mode="off",
            owned_species=frozenset(),
        )
    ] == ["Alpha", "Beta"]


def test_empty_team_threat_objective_allows_support_and_shared_ranking():
    result = TeamThreatDiscovery("available", ())
    assert result.status == "available"
    assert rank_multi_locked_candidates(
        [_candidate("Support")],
        objective=(),
        preference=None,
        ownership_mode="off",
        owned_species=frozenset(),
    )


def test_backup_setter_protect_only_demoted_when_sparse_vs_rain_spof():
    """Protect-only second Drizzle setter no longer gets an ungated complementary pass.

    ``single_provider_spof`` still detects the Rain gap, but divergence fail-closed
    (``MIN_SIDE_TAGS``) demotes a near-empty kit that previously cleared via
    ``_candidate_fills_condition_gap`` alone.
    """
    from recommender.condition_resilience import assess_condition_resilience
    from recommender.team_candidates import collect_locked_anchor_contexts

    draft = [
        _locked("Pelipper", role="rain_setter", ability="Drizzle", moves=["Hurricane", "Protect", "Tailwind", "U-turn"]),
        _locked(
            "Archaludon",
            role="bulky_rain_attacker",
            ability="Stamina",
            moves=["Electro Shot", "Flash Cannon", "Protect", "Dragon Pulse"],
        ),
        *[empty_slot() for _ in range(4)],
    ]
    state = _state(draft)
    contexts = collect_locked_anchor_contexts(state)
    report = assess_condition_resilience(contexts)
    rain = next(row for row in report.conditions if row.condition == "Rain")
    assert rain.classification == "essential"
    assert rain.provider_count == 1
    assert rain.gap == "single_provider_spof"

    candidates = [
        _candidate(
            "Politoed",
            spec={"species": "Politoed", "ability": "Drizzle", "moves": ["Protect"]},
        )
    ]
    annotated = annotate_composition_impact(
        candidates, state, locked_anchors=contexts, condition_resilience=report
    )
    assert annotated[0].species == "Politoed"
    assert annotated[0].composition_fit in {"duplicative", "severe_duplication"}


def test_candidate_kit_ability_keeps_present_rain_provider_for_composition_gap():
    """Regression for the post-Task-A `_role_decision` follow-on.

    Threat/composition candidates carry ability on their kit ``spec`` (same shape as
    usage-backed ``_set_to_spec`` / ``query_counters``). After Task A's gate, feeding
    that ability only via ``resolve_anchor_build(..., provisional=spec)`` labeled it
    ``provisional`` and omitted Drizzle from mechanisms — so a real backup Rain setter
    scored ``duplicative`` instead of filling ``single_provider_spof``.

    ``_role_decision`` must admit the ability as ``usage_derived`` when it matches
    featured/common usage (not a false ``user_confirmed`` lock), so Task A's gate
    keeps it mechanism-visible for the correct reason.

    CompositionFit for this Protect-only kit is demoted under divergence fail-closed;
    complementary coverage for a diverging backup lives on the rich-kit discover test
    and ``test_sableye_backup_rain_setter_complementary_when_diverged``.
    """
    from recommender.anchor_roles import classify_anchor_role, resolve_anchor_build
    from recommender.condition_resilience import (
        assess_condition_resilience,
        mechanism_condition,
    )
    from recommender.team_candidates import _role_decision, collect_locked_anchor_contexts

    draft = [
        _locked(
            "Pelipper",
            role="rain_setter",
            ability="Drizzle",
            moves=["Hurricane", "Protect", "Tailwind", "U-turn"],
        ),
        _locked(
            "Archaludon",
            role="bulky_rain_attacker",
            ability="Stamina",
            moves=["Electro Shot", "Flash Cannon", "Protect", "Dragon Pulse"],
        ),
        *[empty_slot() for _ in range(4)],
    ]
    state = _state(draft)
    contexts = collect_locked_anchor_contexts(state)
    report = assess_condition_resilience(contexts)
    rain = next(row for row in report.conditions if row.condition == "Rain")
    assert rain.gap == "single_provider_spof"

    spec = {"species": "Politoed", "ability": "Drizzle", "moves": ["Protect"]}

    # Contrast: provisional-only resolve still omits (Task A unchanged).
    provisional_build = resolve_anchor_build("Politoed", provisional=spec)
    assert provisional_build.source_for("ability") == "provisional"
    provisional_decision = classify_anchor_role(provisional_build)
    assert not any(
        m.present
        and m.relation == "provides"
        and mechanism_condition(m) == "Rain"
        for m in provisional_decision.mechanisms
    )

    # Candidate path: usage-matched kit ability is usage_derived, not user lock.
    build, decision = _role_decision("Politoed", spec, "champions-reg-mb")
    assert build.ability == "Drizzle"
    assert build.source_for("ability") == "usage_derived"
    assert build.confirmed("ability") is False
    assert any(
        m.mechanic == "Drizzle"
        and m.present
        and m.relation == "provides"
        and mechanism_condition(m) == "Rain"
        for m in decision.mechanisms
    )

    # Non-usage ability on the same species stays provisional (no mechanism claim).
    damp_build, damp_decision = _role_decision(
        "Politoed",
        {"species": "Politoed", "ability": "Damp", "moves": ["Protect"]},
        "champions-reg-mb",
    )
    assert damp_build.ability == "Damp"
    assert damp_build.source_for("ability") == "provisional"
    assert not any(
        m.present
        and m.relation == "provides"
        and mechanism_condition(m) == "Rain"
        for m in damp_decision.mechanisms
    )

    annotated = annotate_composition_impact(
        [_candidate("Politoed", spec=spec)],
        state,
        locked_anchors=contexts,
        condition_resilience=report,
    )
    assert annotated[0].composition_fit in {"duplicative", "severe_duplication"}


def test_discover_multi_locked_publishes_resilience_and_keeps_backup_rain_setter_complementary():
    """Override must fire on the wired discover path with the published report."""
    from recommender.team_candidates import annotate_composition_impact as real_annotate

    draft = [
        _locked(
            "Pelipper",
            role="rain_setter",
            ability="Drizzle",
            moves=["Hurricane", "Protect", "Tailwind", "U-turn"],
        ),
        _locked(
            "Archaludon",
            role="bulky_rain_attacker",
            ability="Stamina",
            moves=["Electro Shot", "Flash Cannon", "Protect", "Dragon Pulse"],
        ),
        *[empty_slot() for _ in range(4)],
    ]
    state = _state(draft)
    # Skip the completion-preference fork so we reach candidate_selection.
    state["team_completion_preference"] = "balanced"

    politoed = replace(
        _counter("Politoed"),
        candidate=replace(
            _counter("Politoed").candidate,
            spec={
                "species": "Politoed",
                "ability": "Drizzle",
                # Usage-attested perish-support kit (ingame common_moves), not
                # Weather Ball offense that clones Pelipper's secondary tags.
                "moves": ["Protect", "Perish Song", "Encore", "Helping Hand"],
            },
        ),
    )
    review = TeamReviewResult(threats=[_threat("Target")], coverage=[], spofs=[])
    discovery = TeamThreatDiscovery(
        status="available", candidates=(politoed,), error=None
    )
    annotated_by_discover: list[AnnotatedCandidate] = []
    annotate_report = None

    def capture_annotate(*args, **kwargs):
        nonlocal annotate_report
        annotate_report = kwargs.get("condition_resilience")
        annotated = real_annotate(*args, **kwargs)
        annotated_by_discover[:] = list(annotated)
        return annotated

    with (
        patch("recommender.nodes._compute_team_review", return_value=review),
        patch("recommender.nodes.query_shared_teammates", return_value=_shared()),
        patch(
            "recommender.threat_counters.query_candidates_for_threats",
            return_value=discovery,
        ),
        # Keep assess/annotate/merge real; only quiet Spe/ability need floods so
        # the injected Rain provider is not cut before presentation.
        patch(
            "recommender.team_candidates.resolve_all_support_needs",
            return_value=[],
        ),
        patch(
            "recommender.team_candidates.resolve_need_candidates",
            return_value=[],
        ),
        patch(
            "recommender.team_candidates.annotate_composition_impact",
            side_effect=capture_annotate,
        ),
    ):
        result = discover_multi_locked(state, {})  # type: ignore[arg-type]

    report = result["condition_resilience"]
    assert report is not None
    assert annotate_report is report
    rain = next(row for row in report.conditions if row.condition == "Rain")
    assert rain.classification == "essential"
    assert rain.provider_count == 1
    assert rain.gap == "single_provider_spof"

    politoed_row = next(row for row in annotated_by_discover if row.species == "Politoed")
    assert politoed_row.composition_fit == "complementary"
    # Split from a single fills_essential_gap bool (2026-08-19): Politoed
    # here is a single_provider_spof backup with real build-divergent
    # value, not a genuinely missing provider -- fills_essential_gap is
    # now reserved for missing_provider specifically (always top ranking
    # priority), while this SPOF-backup case is tracked separately with
    # deliberately lower ranking priority (see _rank_key), since a weak
    # backup-only candidate was previously outranking strong, unrelated
    # candidates by sharing the same top-priority boolean.
    assert politoed_row.fills_essential_gap is False
    assert politoed_row.fills_spof_backup_gap is True
    # Live divergence vs locked Pelipper must clear the provisional threshold.
    from recommender.divergence import (
        DIVERGENCE_COMPLEMENTARY_THRESHOLD,
        PROVIDER_TAG_BY_CONDITION,
        divergence_score,
    )
    from recommender.team_candidates import _role_decision, collect_locked_anchor_contexts

    contexts = collect_locked_anchor_contexts(state)
    pelipper = next(c for c in contexts if c.resolved_build.species == "Pelipper")
    build, decision = _role_decision(
        "Politoed",
        {
            "species": "Politoed",
            "ability": "Drizzle",
            "moves": ["Protect", "Perish Song", "Encore", "Helping Hand"],
        },
        "champions-reg-mb",
    )
    score = divergence_score(
        decision,
        pelipper.role_decision,
        candidate_moves=build.moves,
        existing_moves=pelipper.resolved_build.moves,
        candidate_ability=build.ability,
        existing_ability=pelipper.resolved_build.ability,
        shared_provider_tags=frozenset({PROVIDER_TAG_BY_CONDITION["Rain"]}),
    )
    assert score >= DIVERGENCE_COMPLEMENTARY_THRESHOLD

    presentation = result["pending_presentation"]
    assert presentation is not None
    assert presentation["kind"] == "candidate_selection"
    assert any(opt["species"] == "Politoed" for opt in presentation["options"])


def test_fills_spof_backup_gap_alone_reaches_select_diverse_candidates():
    """Regression, confirmed live (2026-08-21): fills_spof_backup_gap was
    computed correctly by _candidate_fills_condition_gap but was never read
    by _categorize_candidates, _rank_category_a, or select_diverse_candidates
    at all -- a candidate whose ONLY qualifying signal was a real backup-
    provider value (no threat_row, no other matching_needs, which is the
    normal shape for this case since the anchor's own dependency is already
    satisfied and query_support_needs never asks for a backup) was
    structurally invisible no matter how strong its divergence score. Live
    symptom: no 2nd Rain-setter ever got suggested even when that was the
    real, open need. This isolates the exact signal with no other category
    membership available, so it can only pass via the fills_spof_backup_gap
    wiring in _categorize_candidates.
    """
    from recommender.team_candidates import _categorize_candidates

    backup_only = AnnotatedCandidate(
        species="Politoed",
        matching_needs=(),
        source="need",
        threat_row=None,
        branches=frozenset({"need"}),
        composition_fit="complementary",
        fills_essential_gap=False,
        fills_spof_backup_gap=True,
        evidence=(
            CandidateEvidence(
                basis="synthesized",
                confidence="medium",
                producer_name="condition_gap_backup",
                evidence=("need:spof_backup", "condition:Rain"),
                branch="need",
            ),
        ),
    )
    # A handful of unrelated filler candidates so this isn't a pool of one.
    filler = [
        AnnotatedCandidate(
            species=f"Filler{i}",
            matching_needs=(),
            source="threat",
            threat_row=_counter(f"Filler{i}"),
            branches=frozenset({"threat"}),
        )
        for i in range(3)
    ]
    candidates = [backup_only, *filler]
    cat_a, cat_b, cat_c = _categorize_candidates(candidates)
    assert backup_only in cat_b
    assert backup_only not in cat_a

    ranked = rank_multi_locked_by_category(candidates, ())
    picked = select_diverse_candidates(ranked, ())
    all_shown = {picked["default"], *picked["alternatives"]}
    assert "Politoed" in all_shown
    assert picked["tracks"]["Politoed"] == "support/utility"


def test_backup_only_candidate_ranks_behind_genuine_need_match():
    """Regression, confirmed live (2026-08-21): Sableye kept surfacing
    prominently even once its dominant purpose (screens) was already
    covered, riding on its real but secondary backup-Rain value alone.
    A candidate whose only relevant evidence is a fills_spof_backup_gap
    annotation must rank behind any candidate with a genuine, non-backup
    need match within the same category -- same "backup shouldn't compete
    with a real need" priority ADR-026 Amendment 2026-08-17a already
    established for fills_essential_gap vs. fills_spof_backup_gap, now
    extended to evidence-based Category B/C ranking.

    Deliberately constructed as a tie on the pre-existing basis/confidence
    numbers alone (not just a case the existing ranking already handles):
    "synthesized" (the backup evidence's basis) and "ownership_backed"
    share the same, lowest _BASIS_RANK tier, so a genuine-need candidate
    stuck at "ownership_backed"/low confidence would previously have LOST
    a tie-break to a backup-only candidate's higher "medium" confidence --
    confirmed this exact setup fails without the new tier check (verified
    against pre-fix code before finalizing this test), not just a case
    that already happened to work via basis rank alone.
    """
    from recommender.support_needs import SupportNeed
    from recommender.team_candidates import _rank_by_need_evidence

    backup_only = AnnotatedCandidate(
        species="Sableye",
        matching_needs=(),
        source="need",
        threat_row=None,
        branches=frozenset({"need"}),
        fills_spof_backup_gap=True,
        evidence=(
            CandidateEvidence(
                basis="synthesized",
                confidence="medium",
                producer_name="condition_gap_backup",
                evidence=("need:spof_backup", "condition:Rain"),
                branch="need",
            ),
        ),
    )
    genuine_need = AnnotatedCandidate(
        species="Farigiraf",
        matching_needs=(
            SupportNeed(
                category="trick_room",
                name="Trick Room",
                description="x",
                trigger="speed_tier:middling",
            ),
        ),
        source="need",
        threat_row=None,
        branches=frozenset({"need"}),
        # Tied with "synthesized" on _BASIS_RANK (both rank 0) and
        # deliberately lower confidence -- without the tier check, this
        # loses the tie-break to the backup candidate's higher confidence.
        evidence=(
            CandidateEvidence(
                basis="ownership_backed",
                confidence="low",
                producer_name="ownership_match",
                evidence=("need:trick_room",),
                branch="need",
            ),
        ),
    )
    ranked = _rank_by_need_evidence([backup_only, genuine_need])
    assert [c.species for c in ranked] == ["Farigiraf", "Sableye"]


def test_single_purpose_speed_control_demoted_when_team_already_has_some():
    """Regression, confirmed live (2026-08-22): Trick Room and Tailwind
    are NOT mutually exclusive (a team can legitimately run both), so
    this is deliberately not a candidate_wastes_core_slot-style hard
    conflict -- but a candidate whose ENTIRE real support-need value is
    trick_room or tailwind alone, and nothing else, is genuinely lower
    value once the team already has some real speed control. Live
    symptom: Aromatisse (single-purpose, compendium-backed medium
    confidence trick_room match) kept outranking genuinely multi-purpose
    real alternatives (Sableye: screens + backup rain) with a locked
    Pelipper already providing Tailwind.
    """
    from recommender.team_candidates import _rank_by_need_evidence

    from recommender.condition_resilience import assess_condition_resilience

    draft = [
        _locked(
            "Pelipper",
            role="support_speed_control",
            ability="Drizzle",
            item="Focus Sash",
            moves=["Hurricane", "Weather Ball", "Tailwind", "Wide Guard"],
        ),
        *[empty_slot() for _ in range(5)],
    ]
    state = _state(draft)
    contexts = collect_locked_anchor_contexts(state)

    tr_only = AnnotatedCandidate(
        species="Aromatisse",
        matching_needs=(
            SupportNeed(
                category="trick_room", name="Trick Room", description="x", trigger=None
            ),
        ),
        source="need",
        branches=frozenset({"need"}),
        evidence=(
            CandidateEvidence(
                basis="compendium_backed",
                confidence="medium",
                producer_name="role_category_evidence",
                evidence=("need:trick_room",),
                branch="need",
            ),
        ),
    )
    screens_only = AnnotatedCandidate(
        species="Sableye",
        matching_needs=(
            SupportNeed(
                category="screens", name="Screens", description="x", trigger=None
            ),
        ),
        source="need",
        branches=frozenset({"need"}),
        # Deliberately LOWER raw confidence than the TR-only candidate --
        # the demotion must win regardless of raw evidence quality, the
        # same "soft nudge, not just a tiebreak" shape as wastes_core_slot
        # and _is_backup_only.
        evidence=(
            CandidateEvidence(
                basis="compendium_backed",
                confidence="low",
                producer_name="role_category_evidence",
                evidence=("need:screens",),
                branch="need",
            ),
        ),
    )
    ranked = _rank_by_need_evidence(
        [tr_only, screens_only], contexts, condition_beneficiary=False
    )
    assert [c.species for c in ranked] == ["Sableye", "Aromatisse"]
    assert "Aromatisse" in [c.species for c in ranked]


def test_single_purpose_speed_control_not_demoted_when_team_has_none():
    """Sibling of the test above: when the team has NO real speed control
    locked at all, a genuinely-needed trick_room-only candidate must NOT
    be demoted -- this check is specifically about redundancy, not a
    blanket penalty on single-purpose speed-control candidates.
    """
    from recommender.team_candidates import _rank_by_need_evidence

    tr_only = AnnotatedCandidate(
        species="Aromatisse",
        matching_needs=(
            SupportNeed(
                category="trick_room", name="Trick Room", description="x", trigger=None
            ),
        ),
        source="need",
        branches=frozenset({"need"}),
        evidence=(
            CandidateEvidence(
                basis="compendium_backed",
                confidence="medium",
                producer_name="role_category_evidence",
                evidence=("need:trick_room",),
                branch="need",
            ),
        ),
    )
    screens_only = AnnotatedCandidate(
        species="Sableye",
        matching_needs=(
            SupportNeed(
                category="screens", name="Screens", description="x", trigger=None
            ),
        ),
        source="need",
        branches=frozenset({"need"}),
        evidence=(
            CandidateEvidence(
                basis="compendium_backed",
                confidence="low",
                producer_name="role_category_evidence",
                evidence=("need:screens",),
                branch="need",
            ),
        ),
    )
    ranked = _rank_by_need_evidence(
        [tr_only, screens_only], (), condition_beneficiary=False
    )
    assert [c.species for c in ranked] == ["Aromatisse", "Sableye"]


def test_multi_purpose_speed_control_candidate_not_demoted():
    """A candidate whose real support-need value includes speed control
    AND something else (e.g. a real screens match alongside a trick_room
    match) must not be demoted -- the check is specifically "is this
    candidate's ENTIRE value redundant speed control," not "does it
    provide any speed control at all."
    """
    from recommender.team_candidates import _rank_by_need_evidence

    draft = [
        _locked(
            "Pelipper",
            role="support_speed_control",
            ability="Drizzle",
            item="Focus Sash",
            moves=["Hurricane", "Weather Ball", "Tailwind", "Wide Guard"],
        ),
        *[empty_slot() for _ in range(5)],
    ]
    state = _state(draft)
    contexts = collect_locked_anchor_contexts(state)

    multi_purpose = AnnotatedCandidate(
        species="Grimmsnarl",
        matching_needs=(
            SupportNeed(
                category="trick_room", name="Trick Room", description="x", trigger=None
            ),
            SupportNeed(
                category="screens", name="Screens", description="x", trigger=None
            ),
        ),
        source="need",
        branches=frozenset({"need"}),
        evidence=(
            CandidateEvidence(
                basis="compendium_backed",
                confidence="medium",
                producer_name="role_category_evidence",
                evidence=("need:trick_room",),
                branch="need",
            ),
        ),
    )
    tr_only = AnnotatedCandidate(
        species="Aromatisse",
        matching_needs=(
            SupportNeed(
                category="trick_room", name="Trick Room", description="x", trigger=None
            ),
        ),
        source="need",
        branches=frozenset({"need"}),
        evidence=(
            CandidateEvidence(
                basis="compendium_backed",
                confidence="medium",
                producer_name="role_category_evidence",
                evidence=("need:trick_room",),
                branch="need",
            ),
        ),
    )
    ranked = _rank_by_need_evidence(
        [tr_only, multi_purpose], contexts, condition_beneficiary=False
    )
    assert ranked[0].species == "Grimmsnarl"


def test_candidate_wastes_core_slot_weather_conflict():
    """Regression, confirmed live (2026-08-21): Swampert-Mega (real
    Rain-abuse value via Swift Swim) surfaced as a top-3 threat-coverage
    pick for slot 4 on a team already committed to Sun via a locked
    Charizard-Mega-Y. Sun and Rain are mutually exclusive, so Swampert-
    Mega's actual distinguishing strength can never fire on this team as
    built. Must only apply during core-slot construction -- a second
    weather is legitimate real alternate-core bench value once the core
    is settled (confirmed: real teams build a Sun-core and a Rain-core
    variant sharing the same anchors, swapped in per matchup).
    """
    from recommender.anchor_roles import classify_anchor_role, resolve_anchor_build
    from recommender.team_candidates import candidate_wastes_core_slot

    draft = [
        _locked(
            "Charizard-Mega-Y",
            role="sun_setter",
            ability="Drought",
            item="Charizardite Y",
            moves=["Heat Wave", "Protect", "Weather Ball", "Solar Beam"],
        ),
        *[empty_slot() for _ in range(5)],
    ]
    state = _state(draft)
    contexts = collect_locked_anchor_contexts(state)

    build = resolve_anchor_build("Swampert-Mega")
    decision = classify_anchor_role(build)
    assert (
        candidate_wastes_core_slot(decision, build, contexts, is_core_slot=True)
        is True
    )
    assert (
        candidate_wastes_core_slot(decision, build, contexts, is_core_slot=False)
        is False
    )


def test_candidate_wastes_core_slot_second_mega():
    """Regression, confirmed live (2026-08-21): only one Pokemon can Mega
    Evolve per battle -- a second mega-stone holder occupying one of the
    first picked_team_size slots wastes that slot's real flexibility on
    a mechanic that's already spoken for. Same is_core_slot-only scoping
    as the weather case: a second mega is legitimate bench flexibility
    once the core is settled, not something to discourage there.
    """
    from recommender.anchor_roles import classify_anchor_role, resolve_anchor_build
    from recommender.team_candidates import candidate_wastes_core_slot

    draft = [
        _locked(
            "Charizard-Mega-Y",
            role="sun_setter",
            ability="Drought",
            item="Charizardite Y",
            moves=["Heat Wave", "Protect", "Weather Ball", "Solar Beam"],
        ),
        *[empty_slot() for _ in range(5)],
    ]
    state = _state(draft)
    contexts = collect_locked_anchor_contexts(state)

    build = resolve_anchor_build("Metagross-Mega")
    decision = classify_anchor_role(build)
    assert (
        candidate_wastes_core_slot(decision, build, contexts, is_core_slot=True)
        is True
    )
    assert (
        candidate_wastes_core_slot(decision, build, contexts, is_core_slot=False)
        is False
    )


def test_candidate_wastes_core_slot_no_conflict():
    """A candidate with no mega-stone requirement and no needed-importance
    weather dependency must never be flagged, regardless of slot -- this
    check is specifically about scarce-resource conflicts, not a general
    penalty on every candidate during core construction.
    """
    from recommender.anchor_roles import classify_anchor_role, resolve_anchor_build
    from recommender.team_candidates import candidate_wastes_core_slot

    draft = [
        _locked(
            "Charizard-Mega-Y",
            role="sun_setter",
            ability="Drought",
            item="Charizardite Y",
            moves=["Heat Wave", "Protect", "Weather Ball", "Solar Beam"],
        ),
        *[empty_slot() for _ in range(5)],
    ]
    state = _state(draft)
    contexts = collect_locked_anchor_contexts(state)

    build = resolve_anchor_build("Garchomp")
    decision = classify_anchor_role(build)
    assert (
        candidate_wastes_core_slot(decision, build, contexts, is_core_slot=True)
        is False
    )



def test_candidate_core_slot_conflicts_weather_names_charizard_slot():
    from recommender.anchor_roles import classify_anchor_role, resolve_anchor_build

    draft = [
        _locked(
            "Charizard-Mega-Y",
            role="sun_setter",
            ability="Drought",
            item="Charizardite Y",
            moves=["Heat Wave", "Protect", "Weather Ball", "Solar Beam"],
        ),
        *[empty_slot() for _ in range(5)],
    ]
    contexts = collect_locked_anchor_contexts(_state(draft))
    build = resolve_anchor_build("Swampert-Mega")
    decision = classify_anchor_role(build)
    conflicts = candidate_core_slot_conflicts(
        decision, build, contexts, is_core_slot=True
    )
    weather = [c for c in conflicts if c.kind == "weather"]
    assert weather
    assert {c.locked_slot_index for c in weather} == {0}
    assert all(c.locked_species == "Charizard-Mega-Y" for c in weather)
    assert all(c.resource == "Sun" for c in weather)
    assert candidate_core_slot_conflicts(
        decision, build, contexts, is_core_slot=False
    ) == ()


def test_candidate_core_slot_conflicts_mega_names_locked_mega():
    from recommender.anchor_roles import classify_anchor_role, resolve_anchor_build

    draft = [
        _locked(
            "Charizard-Mega-Y",
            role="sun_setter",
            ability="Drought",
            item="Charizardite Y",
            moves=["Heat Wave", "Protect", "Weather Ball", "Solar Beam"],
        ),
        *[empty_slot() for _ in range(5)],
    ]
    contexts = collect_locked_anchor_contexts(_state(draft))
    build = resolve_anchor_build("Metagross-Mega")
    decision = classify_anchor_role(build)
    conflicts = candidate_core_slot_conflicts(
        decision, build, contexts, is_core_slot=True
    )
    mega = [c for c in conflicts if c.kind == "mega"]
    assert mega
    assert {c.locked_slot_index for c in mega} == {0}
    assert all(c.locked_species == "Charizard-Mega-Y" for c in mega)


def test_candidate_core_slot_conflicts_swampert_vs_charizard_is_one_slot():
    from recommender.anchor_roles import classify_anchor_role, resolve_anchor_build

    draft = [
        _locked(
            "Charizard-Mega-Y",
            role="sun_setter",
            ability="Drought",
            item="Charizardite Y",
            moves=["Heat Wave", "Protect", "Weather Ball", "Solar Beam"],
        ),
        *[empty_slot() for _ in range(5)],
    ]
    contexts = collect_locked_anchor_contexts(_state(draft))
    build = resolve_anchor_build("Swampert-Mega")
    decision = classify_anchor_role(build)
    conflicts = candidate_core_slot_conflicts(
        decision, build, contexts, is_core_slot=True
    )
    assert {c.locked_slot_index for c in conflicts} == {0}
    kinds = {c.kind for c in conflicts}
    assert "weather" in kinds
    assert "mega" in kinds


def test_candidate_core_slot_conflicts_two_sun_providers_both_listed():
    from recommender.anchor_roles import classify_anchor_role, resolve_anchor_build

    draft = [
        _locked(
            "Charizard-Mega-Y",
            role="sun_setter",
            ability="Drought",
            item="Charizardite Y",
            moves=["Heat Wave", "Protect", "Weather Ball", "Solar Beam"],
        ),
        _locked(
            "Torkoal",
            role="sun_setter",
            ability="Drought",
            item="Heat Rock",
            moves=["Eruption", "Protect", "Earth Power", "Solar Beam"],
        ),
        *[empty_slot() for _ in range(4)],
    ]
    contexts = collect_locked_anchor_contexts(_state(draft))
    build = resolve_anchor_build("Swampert-Mega")
    decision = classify_anchor_role(build)
    conflicts = candidate_core_slot_conflicts(
        decision, build, contexts, is_core_slot=True
    )
    weather_slots = {c.locked_slot_index for c in conflicts if c.kind == "weather"}
    assert weather_slots == {0, 1}


def _bench_state(*, n_locked=4):
    """4 real locked slots (a complete core, picked_team_size=4 per this
    file's _state) + open bench slots -- the exact precondition
    candidate_improves_best_bring needs to have a real baseline to
    compare against.
    """
    locked = [
        _locked(
            f"Garchomp{i}" if i else "Garchomp",
            moves=["Dragon Claw", "Rock Slide", "Earthquake", "Protect"],
        )
        for i in range(n_locked)
    ]
    draft = [*locked, *[empty_slot() for _ in range(6 - n_locked)]]
    return _state(draft)


def test_annotate_composition_impact_wires_bench_subset_for_bench_slot():
    """Confirms annotate_composition_impact actually calls
    candidate_improves_best_bring for a bench slot with no dependency,
    and correctly threads its result onto improves_bench_subset --
    candidate_improves_best_bring's own correctness (real
    compute_team_coverage/detect_spof behavior) is already verified
    separately with real MockCalcClient scenarios (test_coverage.py);
    this only tests that THIS wiring calls it and uses the result.
    """
    from recommender.condition_resilience import assess_condition_resilience
    from recommender.state import TeamThreatObjectiveRow, ThreatCandidate

    state = _bench_state()
    contexts = collect_locked_anchor_contexts(state)
    resilience = assess_condition_resilience(contexts)
    objective = [
        TeamThreatObjectiveRow(
            threat=ThreatCandidate(
                ladder_species="Kingambit",
                usage_rank=1,
                form="Kingambit",
                showdown_usage_pct=None,
                showdown_formes=(),
                spec={"species": "Kingambit"},
                build_source="ingame",
            ),
            kinds=frozenset({"uncovered"}),
        )
    ]
    candidates = [_candidate("Whimsicott", spec={"species": "Whimsicott"})]

    with patch(
        "recommender.coverage.candidate_improves_best_bring",
        return_value=True,
    ) as mocked:
        annotated = annotate_composition_impact(
            candidates,
            state,
            locked_anchors=contexts,
            condition_resilience=resilience,
            objective=objective,
        )
    mocked.assert_called_once()
    assert annotated[0].improves_bench_subset is True


def test_annotate_composition_impact_does_not_evaluate_bench_subset_for_core_slot():
    """Sibling: with fewer than picked_team_size locked (still building
    the core), candidate_improves_best_bring must never be called at
    all -- there's no real baseline yet, and this is core-slot territory
    handled by candidate_wastes_core_slot instead.
    """
    from recommender.condition_resilience import assess_condition_resilience

    state = _bench_state(n_locked=2)  # Still building the core.
    contexts = collect_locked_anchor_contexts(state)
    resilience = assess_condition_resilience(contexts)
    candidates = [_candidate("Whimsicott", spec={"species": "Whimsicott"})]

    with patch(
        "recommender.coverage.candidate_improves_best_bring"
    ) as mocked:
        annotated = annotate_composition_impact(
            candidates, state, locked_anchors=contexts, condition_resilience=resilience
        )
    mocked.assert_not_called()
    assert annotated[0].improves_bench_subset is False


def test_annotate_composition_impact_does_not_evaluate_dependent_candidate():
    """A candidate with an unmet needed weather dependency (Swampert-Mega
    wanting Rain) must never reach candidate_improves_best_bring --
    evaluating it alone would produce an honestly wrong, unamplified
    coverage number (team_field_states only forces Rain when a real
    provider is also in the subset). Pairing it correctly is a separate,
    not-yet-built capability, deliberately not approximated here.
    """
    from recommender.anchor_roles import classify_anchor_role, resolve_anchor_build
    from recommender.condition_resilience import assess_condition_resilience
    from recommender.state import TeamThreatObjectiveRow, ThreatCandidate

    state = _bench_state()
    contexts = collect_locked_anchor_contexts(state)
    resilience = assess_condition_resilience(contexts)
    objective = [
        TeamThreatObjectiveRow(
            threat=ThreatCandidate(
                ladder_species="Kingambit",
                usage_rank=1,
                form="Kingambit",
                showdown_usage_pct=None,
                showdown_formes=(),
                spec={"species": "Kingambit"},
                build_source="ingame",
            ),
            kinds=frozenset({"uncovered"}),
        )
    ]
    swampert_build = resolve_anchor_build("Swampert-Mega")
    candidates = [
        _candidate(
            "Swampert-Mega",
            spec={
                "species": "Swampert-Mega",
                "ability": swampert_build.ability,
                "item": swampert_build.item,
                "moves": list(swampert_build.moves),
            },
        )
    ]

    with patch(
        "recommender.coverage.candidate_improves_best_bring"
    ) as mocked:
        annotated = annotate_composition_impact(
            candidates,
            state,
            locked_anchors=contexts,
            condition_resilience=resilience,
            objective=objective,
        )
    mocked.assert_not_called()
    assert annotated[0].improves_bench_subset is False


def test_rank_category_a_demotes_wastes_core_slot_candidate():
    """Confirms the discount actually reaches Category A ranking, not
    just the underlying candidate_wastes_core_slot check in isolation --
    Swampert-Mega surfaced specifically as a "threat coverage + type
    synergy" pick live, so this is the ranking function that must respect
    the flag.
    """
    from recommender.team_candidates import _rank_category_a

    strong_but_wastes = AnnotatedCandidate(
        species="Swampert-Mega",
        matching_needs=(),
        source="threat",
        threat_row=_counter("Swampert-Mega", usage_rank=1),
        branches=frozenset({"threat"}),
        wastes_core_slot=True,
    )
    weaker_but_usable = AnnotatedCandidate(
        species="Garchomp",
        matching_needs=(),
        source="threat",
        threat_row=_counter("Garchomp", usage_rank=50),
        branches=frozenset({"threat"}),
        wastes_core_slot=False,
    )
    ranked = _rank_category_a([strong_but_wastes, weaker_but_usable], [[]])
    assert [c.species for c in ranked] == ["Garchomp", "Swampert-Mega"]


def test_rank_category_a_demotes_unreliable_dependency_at_equal_strength():
    """Confirms dependency_reliability actually reaches Category A
    ranking as a soft nudge, not a hard gate -- two candidates with
    IDENTICAL raw verified_score/defensive_synergy inputs must be
    ordered by reliability alone, and the less-reliable one must still
    appear in the ranked output (not excluded), unlike wastes_core_slot's
    behavior for a genuinely disqualifying conflict.

    Uses fake species names (not real ones) specifically so
    defensive_synergy_score is genuinely tied at its neutral default --
    confirmed real species have real, differing types even against an
    empty locked_types_list (e.g. Mawile-Mega -1.0 vs Excadrill -2.0),
    which would confound this test's intended isolation of reliability
    as the only differentiating signal.
    """
    from recommender.team_candidates import _rank_category_a

    unreliable = AnnotatedCandidate(
        species="Unreliable",
        matching_needs=(),
        source="threat",
        threat_row=_counter("Unreliable", usage_rank=5),
        branches=frozenset({"threat"}),
        dependency_reliability=0.572,
    )
    reliable = AnnotatedCandidate(
        species="Reliable",
        matching_needs=(),
        source="threat",
        threat_row=_counter("Reliable", usage_rank=5),
        branches=frozenset({"threat"}),
        dependency_reliability=1.0,
    )
    ranked = _rank_category_a([unreliable, reliable], [[]])
    assert [c.species for c in ranked] == ["Reliable", "Unreliable"]
    assert "Unreliable" in [c.species for c in ranked]


def test_rank_category_a_reliability_ties_do_not_inject_spurious_ordering():
    """Regression, confirmed during implementation (2026-08-22): a real
    bug in this feature's own first draft -- when every candidate shares
    the same dependency_reliability (the common case, nobody has a real
    dependency), a naive stable-sort-based rank still assigned distinct
    sequential positions purely from list order, silently corrupting
    otherwise-unrelated verified_score/defensive_synergy ordering. Caught
    by an existing test (test_rank_category_a_balances_verified_score_
    against_synergy) breaking once this field was added, not shipped
    uncorrected. This test locks in the fix directly: candidates tied on
    dependency_reliability (all at the 1.0 default) must rank purely by
    their other real signals, regardless of input list order.
    """
    from recommender.team_candidates import _rank_category_a

    weaker = AnnotatedCandidate(
        species="Weaker",
        matching_needs=(),
        source="threat",
        threat_row=_counter("Weaker", outcome="intentional_non_ko_answer", severity="toss-up"),
        branches=frozenset({"threat"}),
    )
    stronger = AnnotatedCandidate(
        species="Stronger",
        matching_needs=(),
        source="threat",
        threat_row=_counter("Stronger", outcome="clean_kill", severity="decisive"),
        branches=frozenset({"threat"}),
    )
    # Deliberately list the weaker candidate FIRST -- if reliability_rank
    # were still list-order-sensitive, this input order could flip the
    # otherwise-correct result.
    ranked = _rank_category_a([weaker, stronger], [[]])
    assert [c.species for c in ranked] == ["Stronger", "Weaker"]


def test_unrelated_mechanic_duplication_still_demoted():
    from recommender.condition_resilience import assess_condition_resilience
    from recommender.team_candidates import (
        _candidate_fills_condition_gap,
        _role_decision,
        collect_locked_anchor_contexts,
    )

    draft = [
        _locked("Pelipper", role="rain_setter", ability="Drizzle"),
        _locked(
            "Archaludon",
            role="bulky_rain_attacker",
            ability="Stamina",
            moves=["Electro Shot", "Flash Cannon", "Protect", "Dragon Pulse"],
        ),
        # Second offense so Blissey cannot clear via primary_function SPOF hatch.
        _locked(
            "Kingambit",
            role="fast_physical_attacker",
            ability="Supreme Overlord",
            moves=["Kowtow Cleave", "Sucker Punch", "Iron Head", "Protect"],
        ),
        *[empty_slot() for _ in range(3)],
    ]
    state = _state(draft)
    contexts = collect_locked_anchor_contexts(state)
    report = assess_condition_resilience(contexts)
    rain = next(row for row in report.conditions if row.condition == "Rain")
    assert rain.gap == "single_provider_spof"

    spec = {
        "species": "Blissey",
        "ability": "Natural Cure",
        "item": "Leftovers",
        "moves": ["Soft-Boiled", "Seismic Toss", "Toxic", "Protect"],
    }
    build, decision = _role_decision("Blissey", spec, "champions-reg-mb")
    # Split from a single bool into (fills_missing_provider_gap,
    # fills_spof_backup_gap, backup_conditions) (2026-08-19, extended
    # 2026-08-21) -- Blissey doesn't provide Rain at all here, so none of
    # the three should fire.
    assert (
        _candidate_fills_condition_gap(
            decision,
            report,
            candidate_build=build,
            locked=contexts,
        )
        == (False, False, ())
    )

    candidates = [_candidate("Blissey", spec=spec)]
    annotated = annotate_composition_impact(
        candidates, state, locked_anchors=contexts, condition_resilience=report
    )
    assert annotated[0].composition_fit in {"duplicative", "severe_duplication"}
    assert annotated[0].fills_essential_gap is False


def test_sableye_backup_rain_setter_complementary_when_diverged():
    from recommender.condition_resilience import assess_condition_resilience
    from recommender.team_candidates import collect_locked_anchor_contexts

    draft = [
        _locked(
            "Pelipper",
            role="rain_setter",
            ability="Drizzle",
            moves=["Hurricane", "Protect", "Tailwind", "U-turn"],
        ),
        _locked(
            "Archaludon",
            role="bulky_rain_attacker",
            ability="Stamina",
            moves=["Electro Shot", "Flash Cannon", "Protect", "Dragon Pulse"],
        ),
        *[empty_slot() for _ in range(4)],
    ]
    state = _state(draft)
    contexts = collect_locked_anchor_contexts(state)
    report = assess_condition_resilience(contexts)
    rain = next(row for row in report.conditions if row.condition == "Rain")
    assert rain.gap == "single_provider_spof"

    candidates = [
        _candidate(
            "Sableye",
            spec={
                "species": "Sableye",
                "ability": "Prankster",
                "moves": [
                    "Rain Dance",
                    "Encore",
                    "Will-O-Wisp",
                    "Light Screen",
                ],
            },
        )
    ]
    annotated = annotate_composition_impact(
        candidates, state, locked_anchors=contexts, condition_resilience=report
    )
    assert annotated[0].species == "Sableye"
    assert annotated[0].composition_fit == "complementary"


def test_near_clone_rain_setter_not_complementary_despite_spof():
    from recommender.condition_resilience import assess_condition_resilience
    from recommender.team_candidates import collect_locked_anchor_contexts

    draft = [
        _locked(
            "Pelipper",
            role="rain_setter",
            ability="Drizzle",
            moves=["Hurricane", "Protect", "Tailwind", "U-turn"],
        ),
        _locked(
            "Archaludon",
            role="bulky_rain_attacker",
            ability="Stamina",
            moves=["Electro Shot", "Flash Cannon", "Protect", "Dragon Pulse"],
        ),
        *[empty_slot() for _ in range(4)],
    ]
    state = _state(draft)
    contexts = collect_locked_anchor_contexts(state)
    report = assess_condition_resilience(contexts)
    assert next(r for r in report.conditions if r.condition == "Rain").gap == (
        "single_provider_spof"
    )

    candidates = [
        _candidate(
            "Politoed",
            spec={
                "species": "Politoed",
                "ability": "Drizzle",
                "moves": ["Hurricane", "Weather Ball", "Tailwind", "Protect"],
            },
        )
    ]
    annotated = annotate_composition_impact(
        candidates, state, locked_anchors=contexts, condition_resilience=report
    )
    assert annotated[0].composition_fit in {"duplicative", "severe_duplication"}


def test_second_offense_spof_complementary_when_same_category_diverged():
    """One locked physical attacker; second physical with diverging secondaries.

    ``corrects_skew`` cannot fire (attackers on locked side is 1). Complementary must
    come from the primary_function SPOF hatch gated on divergence.
    """
    from recommender.team_candidates import collect_locked_anchor_contexts

    draft = [
        _locked(
            "Kingambit",
            role="fast_physical_attacker",
            ability="Supreme Overlord",
            item="Life Orb",
            moves=["Kowtow Cleave", "Sucker Punch", "Iron Head", "Protect"],
        ),
        *[empty_slot() for _ in range(5)],
    ]
    state = _state(draft)
    contexts = collect_locked_anchor_contexts(state)
    assert contexts[0].role_decision.primary_function == "offense"

    candidates = [
        _candidate(
            "Incineroar",
            spec={
                "species": "Incineroar",
                "ability": "Intimidate",
                "item": "Safety Goggles",
                "moves": ["Fake Out", "Flare Blitz", "Parting Shot", "Will-O-Wisp"],
            },
        )
    ]
    annotated = annotate_composition_impact(
        candidates, state, locked_anchors=contexts, condition_resilience=None
    )
    assert annotated[0].species == "Incineroar"
    assert annotated[0].composition_fit == "complementary"


def test_gap_need_deduped_when_anchored_trick_room_already_present():
    from recommender.condition_resilience import assess_condition_resilience, gap_support_needs
    from recommender.team_candidates import collect_locked_anchor_contexts

    draft = [
        _locked("Kingambit", role="trick_room_sweeper"),
        *[empty_slot() for _ in range(5)],
    ]
    state = _state(draft)
    contexts = collect_locked_anchor_contexts(state)
    report = assess_condition_resilience(contexts)
    anchored = tuple(need for ctx in contexts for need in ctx.support_needs)
    tr_anchored = next(n for n in anchored if n.need.category == "trick_room")
    assert tr_anchored.need.trigger is not None
    assert tr_anchored.need.trigger.startswith("speed_tier:")

    residual = gap_support_needs(report, anchored)
    assert not any(n.category == "trick_room" for n in residual)
    # Without dedupe, a gap need would use this trigger and double-count in ranking.
    assert ("trick_room", "condition_resilience:gap") not in {
        (n.category, n.trigger) for n in residual
    }

    with patch(
        "recommender.team_candidates.resolve_all_support_needs",
        return_value=[
            NeedResolvedCandidate(
                "Farigiraf",
                matching_needs=(tr_anchored.need,),
                evidence=(_evidence("compendium_backed"),),
                anchored_needs=(tr_anchored,),
            )
        ],
    ), patch(
        "recommender.team_candidates.resolve_need_candidates",
        return_value=[],
    ):
        merged = merge_multi_locked_candidates(
            state,
            contexts,
            (),
            None,
            ownership_mode="off",
            owned_species=frozenset(),
            condition_resilience=report,
        )
    farig = next(row for row in merged if row.species == "Farigiraf")
    distinct_needs = {
        (n.need.category, n.need.trigger) for n in farig.anchored_needs
    }
    assert ("trick_room", tr_anchored.need.trigger) in distinct_needs
    assert ("trick_room", "condition_resilience:gap") not in distinct_needs
    assert len({k for k in distinct_needs if k[0] == "trick_room"}) == 1


def test_gap_need_deduped_when_anchored_rain_already_present():
    """Anchored move-derived Rain need must suppress gap Rain (trigger-parity invariant)."""
    from recommender.condition_resilience import assess_condition_resilience, gap_support_needs
    from recommender.team_candidates import collect_locked_anchor_contexts

    draft = [
        _locked(
            "Archaludon",
            role="bulky_special_attacker",
            ability="Stamina",
            moves=["Electro Shot", "Dragon Pulse", "Flash Cannon", "Aura Sphere"],
        ),
        *[empty_slot() for _ in range(5)],
    ]
    state = _state(draft)
    contexts = collect_locked_anchor_contexts(state)
    report = assess_condition_resilience(contexts)
    anchored = tuple(need for ctx in contexts for need in ctx.support_needs)
    rain_anchored = next(
        n
        for n in anchored
        if n.need.category == "condition_setter"
        and n.need.trigger == "field_condition:any:rain"
    )
    assert rain_anchored.need.trigger == "field_condition:any:rain"

    residual = gap_support_needs(report, anchored)
    assert not any(
        n.category == "condition_setter" and n.trigger == "field_condition:any:rain"
        for n in residual
    )
    assert ("condition_setter", "field_condition:any:rain") not in {
        (n.category, n.trigger) for n in residual
    }


def test_residual_gap_attaches_single_synthetic_anchored_need():
    from recommender.condition_resilience import (
        ConditionResilienceReport,
        ConditionResilienceRow,
    )

    report = ConditionResilienceReport(
        conditions=(
            ConditionResilienceRow(
                condition="Trick Room",
                classification="essential",
                provider_count=0,
                providers=(),
                dependents=(),
                gap="missing_provider",
            ),
        )
    )
    gap_need = SupportNeed(
        category="trick_room",
        name="Trick Room",
        description="gap",
        trigger="condition_resilience:gap",
        stance="need",
    )
    with patch(
        "recommender.team_candidates.gap_support_needs", return_value=(gap_need,)
    ), patch(
        "recommender.team_candidates.resolve_all_support_needs", return_value=[]
    ), patch(
        "recommender.team_candidates.resolve_need_candidates",
        return_value=[
            NeedResolvedCandidate(
                "Farigiraf",
                matching_needs=(gap_need,),
                evidence=(_evidence("compendium_backed"),),
            )
        ],
    ):
        merged = merge_multi_locked_candidates(
            _state([_locked("Kingambit"), *[empty_slot() for _ in range(5)]]),
            [],
            (),
            None,
            ownership_mode="off",
            owned_species=frozenset(),
            condition_resilience=report,
        )
    farig = next(row for row in merged if row.species == "Farigiraf")
    assert any(n.anchor_id == "condition_resilience" for n in farig.anchored_needs)
    assert len(farig.anchored_needs) == 1
    assert farig.target_role_decision is not None
    assert farig.target_role_decision.role_id == "trick_room_setter"  # type: ignore[union-attr]


def test_rank_key_weak_spof_backup_does_not_outrank_strong_unrelated_candidate():
    """Regression, confirmed live (2026-08-19): after a Tailwind setter
    was locked, a weak, low-confidence, mechanical_only Tailwind-backup
    candidate (Altaria) ranked #1 -- ahead of strong, usage_backed/high-
    confidence candidates entirely unrelated to any tracked condition
    (Garchomp, Delphox) -- purely because fills_essential_gap treated a
    genuinely missing need and a mere single_provider_spof backup
    opportunity identically, and that single boolean was the FIRST,
    highest-priority field in the rank key, ahead of evidence quality.

    This is the real, deeper root cause behind the "Altaria/Staraptor
    both tailwind_setter" alternatives-selection bug -- fixed separately
    by _redundancy_tier_for_candidates, but that fix only ever reorders
    candidates[1:] (the alternatives), never candidates[0] (the default),
    so a weak SPOF-backup-only candidate could still win the default slot
    outright. This test confirms the actual ranking order is now correct,
    not just the alternatives display.
    """
    def evidence(basis, confidence):
        return CandidateEvidence(basis=basis, confidence=confidence, producer_name="x")

    # SPOF-backup-only (no missing_provider gap), weak evidence -- exactly
    # the observed Altaria shape.
    weak_spof_backup = AnnotatedCandidate(
        species="Altaria",
        matching_needs=(),
        source="mechanical",
        target_role_decision=TargetRoleDecision(
            role_id="tailwind_setter", source="mechanical_only"
        ),
        fills_essential_gap=False,
        fills_spof_backup_gap=True,
        evidence=(evidence("mechanical_only", "low"),),
        composition_fit="complementary",
    )
    # No gap involvement of any kind, but strong, real evidence -- exactly
    # the observed Garchomp shape.
    strong_unrelated = AnnotatedCandidate(
        species="Garchomp",
        matching_needs=(),
        source="usage",
        target_role_decision=TargetRoleDecision(
            role_id="fast_physical_attacker", source="usage_backed"
        ),
        fills_essential_gap=False,
        fills_spof_backup_gap=False,
        evidence=(evidence("usage_backed", "high"),),
        composition_fit="complementary",
    )

    key_weak = _rank_key(
        weak_spof_backup, objective=(), preference=None, regulation="champions-reg-mb"
    )
    key_strong = _rank_key(
        strong_unrelated, objective=(), preference=None, regulation="champions-reg-mb"
    )
    assert key_strong > key_weak, "strong unrelated evidence must outrank a weak SPOF-backup-only candidate"


def test_rank_key_still_prioritizes_genuinely_missing_provider():
    """A genuinely missing need (fills_essential_gap=True) must still
    unconditionally outrank a strong, unrelated candidate -- confirms the
    split didn't weaken the ORIGINAL, correct priority for missing_provider,
    only separated it from the different single_provider_spof case."""
    def evidence(basis, confidence):
        return CandidateEvidence(basis=basis, confidence=confidence, producer_name="x")

    genuinely_missing = AnnotatedCandidate(
        species="Pelipper",
        matching_needs=(),
        source="mechanical",
        target_role_decision=TargetRoleDecision(
            role_id="tailwind_setter", source="mechanical_only"
        ),
        fills_essential_gap=True,
        fills_spof_backup_gap=False,
        evidence=(evidence("mechanical_only", "low"),),
        composition_fit="complementary",
    )
    strong_unrelated = AnnotatedCandidate(
        species="Garchomp",
        matching_needs=(),
        source="usage",
        target_role_decision=TargetRoleDecision(
            role_id="fast_physical_attacker", source="usage_backed"
        ),
        fills_essential_gap=False,
        fills_spof_backup_gap=False,
        evidence=(evidence("usage_backed", "high"),),
        composition_fit="complementary",
    )
    key_missing = _rank_key(
        genuinely_missing, objective=(), preference=None, regulation="champions-reg-mb"
    )
    key_strong = _rank_key(
        strong_unrelated, objective=(), preference=None, regulation="champions-reg-mb"
    )
    assert key_missing > key_strong, "a genuinely missing provider must still win top priority"


def test_rank_key_shared_teammate_decides_over_raw_evidence_when_otherwise_tied():
    """Real design decision, confirmed with Vu directly: shared-teammate
    co-occurrence (a proxy for real mechanism/threat-coverage synergy the
    calc-based matchup model doesn't fully capture on its own) should have
    meaningful ranking influence, not be an effectively-dead last-resort
    tie-break. Previously positioned immediately after best_evidence,
    where candidates almost never actually tie (evidence quality varies
    constantly), making it structurally unable to matter in practice.
    Repositioned ahead of best_evidence: confirms a candidate with a real,
    strong shared-teammate signal now correctly outranks one with only
    stronger raw evidence confidence, when every genuinely-computed
    team-value field (threat-coverage, fit, preference, needs) ties.
    """
    def evidence(basis, confidence):
        return CandidateEvidence(basis=basis, confidence=confidence, producer_name="x")

    strong_shared_teammate = AnnotatedCandidate(
        species="Swampert-Mega",
        matching_needs=(),
        source="teammate_backed",
        target_role_decision=TargetRoleDecision(
            role_id="rain_attacker", source="teammate_backed"
        ),
        fills_essential_gap=False,
        fills_spof_backup_gap=False,
        evidence=(evidence("mechanical_only", "low"),),
        composition_fit="complementary",
        shared_min_pct=48.5,
        shared_worst_rank=2,
    )
    strong_evidence_no_shared = AnnotatedCandidate(
        species="Delphox",
        matching_needs=(),
        source="usage",
        target_role_decision=TargetRoleDecision(
            role_id="fast_special_attacker", source="usage_backed"
        ),
        fills_essential_gap=False,
        fills_spof_backup_gap=False,
        evidence=(evidence("usage_backed", "high"),),
        composition_fit="complementary",
        shared_min_pct=None,
        shared_worst_rank=None,
    )
    key_shared = _rank_key(
        strong_shared_teammate, objective=(), preference=None, regulation="champions-reg-mb"
    )
    key_evidence = _rank_key(
        strong_evidence_no_shared, objective=(), preference=None, regulation="champions-reg-mb"
    )
    assert key_shared > key_evidence


def test_rank_key_real_threat_coverage_still_beats_shared_teammate_correlation():
    """Confirms the design boundary holds: shared-teammate evidence must
    NOT override genuinely-computed, real threat-coverage superiority --
    it only matters as a tie-breaker among comparably-valuable candidates,
    per the explicit design decision this repositioning was scoped to."""
    def evidence(basis, confidence):
        return CandidateEvidence(basis=basis, confidence=confidence, producer_name="x")

    objective = (_objective(threat_id="target", kinds=frozenset({"uncovered"})),)
    real_coverage = AnnotatedCandidate(
        species="Garchomp",
        matching_needs=(),
        source="usage",
        target_role_decision=TargetRoleDecision(
            role_id="fast_physical_attacker", source="usage_backed"
        ),
        fills_essential_gap=False,
        fills_spof_backup_gap=False,
        evidence=(evidence("usage_backed", "high"),),
        composition_fit="complementary",
        shared_min_pct=None,
        shared_worst_rank=None,
        threat_row=_counter("Garchomp", outcome="clean_kill", severity="decisive"),
    )
    weak_but_strongly_shared = AnnotatedCandidate(
        species="Sinistcha",
        matching_needs=(),
        source="teammate_backed",
        target_role_decision=TargetRoleDecision(
            role_id="cleric", source="teammate_backed"
        ),
        fills_essential_gap=False,
        fills_spof_backup_gap=False,
        evidence=(evidence("mechanical_only", "low"),),
        composition_fit="complementary",
        shared_min_pct=99.0,
        shared_worst_rank=1,
    )
    key_coverage = _rank_key(
        real_coverage, objective=objective, preference=None, regulation="champions-reg-mb"
    )
    key_shared = _rank_key(
        weak_but_strongly_shared,
        objective=objective,
        preference=None,
        regulation="champions-reg-mb",
    )
    assert key_coverage > key_shared


def test_condition_beneficiaries_discovered_in_multi_locked_pipeline():
    """Regression for a real, confirmed gap: resolve_condition_beneficiaries
    (real Rain-beneficiary discovery, e.g. Basculegion) had exactly one
    caller in the whole codebase -- discover_single_locked -- and was
    never wired into the multi-locked pipeline at all. This is the exact
    scenario every live-observed candidate-quality issue in this whole
    investigation actually occurred in (2+ locked members). Confirmed
    directly against the real Archaludon+Pelipper(Drizzle) scenario:
    Basculegion (real Swift Swim Rain-beneficiary) now gets discovered
    with correctly-attributed evidence, not silently missing.
    """
    draft = [
        _locked(
            "Archaludon",
            role="bulky_special_attacker",
            ability="Stamina",
            moves=["Electro Shot", "Flash Cannon", "Protect", "Dragon Pulse"],
        ),
        _locked(
            "Pelipper",
            role="support_speed_control",
            ability="Drizzle",
            item="Focus Sash",
            moves=["Hurricane", "Weather Ball", "Tailwind", "Wide Guard"],
        ),
        *[empty_slot() for _ in range(4)],
    ]
    state = _state(draft)
    contexts = collect_locked_anchor_contexts(state)
    merged = merge_multi_locked_candidates(
        state, contexts, (), None, ownership_mode="off", owned_species=frozenset()
    )
    basculegion = next(
        (row for row in merged if row.species == "Basculegion"), None
    )
    assert basculegion is not None
    categories = {need.category for need in basculegion.matching_needs}
    assert "condition_beneficiary" in categories
    assert any(
        "condition:Rain" in e.evidence for e in basculegion.evidence
    )


def test_condition_beneficiary_checks_every_locked_anchor_not_just_first():
    """Confirms the condition-provider check loops over every locked
    anchor -- Rain here comes from the SECOND locked member (Pelipper),
    not the first (Archaludon), and must still be found."""
    draft = [
        _locked(
            "Archaludon",
            role="bulky_special_attacker",
            ability="Stamina",
            moves=["Electro Shot", "Flash Cannon", "Protect", "Dragon Pulse"],
        ),
        _locked(
            "Pelipper",
            role="support_speed_control",
            ability="Drizzle",
            item="Focus Sash",
            moves=["Hurricane", "Weather Ball", "Tailwind", "Wide Guard"],
        ),
        *[empty_slot() for _ in range(4)],
    ]
    state = _state(draft)
    contexts = collect_locked_anchor_contexts(state)
    # confirm Archaludon (first locked) does NOT itself provide Rain --
    # this test is only meaningful if the provider is genuinely the
    # second anchor, not the first.
    archaludon_ctx = next(c for c in contexts if c.resolved_build.species == "Archaludon")
    from recommender.condition_resilience import mechanism_condition
    archaludon_provides = {
        mechanism_condition(m)
        for m in archaludon_ctx.role_decision.mechanisms
        if m.present and m.relation == "provides"
    }
    assert "Rain" not in archaludon_provides

    merged = merge_multi_locked_candidates(
        state, contexts, (), None, ownership_mode="off", owned_species=frozenset()
    )
    assert any(row.species == "Basculegion" for row in merged)


def _synth_category_a(species: str, matchups) -> AnnotatedCandidate:
    row = _counter(species, matchups=matchups, usage_rank=None)
    return AnnotatedCandidate(
        species=species,
        matching_needs=(),
        source="threat",
        threat_row=row,
        spec={"species": species},
        evidence=(),
        branches=frozenset({"threat"}),
    )


_ARCHALUDON_PELIPPER_LOCKED_TYPES = [["Steel", "Dragon"], ["Water", "Flying"]]


def test_rank_category_a_balances_verified_score_against_synergy():
    """Regression, confirmed live: a prior naive-sum combination of
    threat-counter breadth and type-synergy let the higher-magnitude
    signal (verified_score, can be 8+ across multiple threats) dominate
    the much smaller-magnitude signal (defensive_synergy_score,
    typically single-digit) completely, the same failure mode already
    found once in this investigation for a different pair of signals.
    Rank-based combination (this test) must NOT let raw magnitude decide
    -- Kingambit has the highest raw verified_score of anyone here, but
    its severe negative synergy (compounds Archaludon's own weaknesses)
    must pull it out of the top spot, and Swampert-Mega's weak raw
    verified_score must not prevent it from beating several stronger-
    verified but synergy-poor candidates.
    """
    pool = [
        _synth_category_a(
            "Kingambit",
            (("t1", "clean_kill", "decisive"), ("t2", "clean_kill", "decisive"), ("t3", "intentional_non_ko_answer", "costly")),
        ),
        _synth_category_a(
            "Excadrill",
            (("t1", "clean_kill", "decisive"), ("t2", "clean_kill", "costly")),
        ),
        _synth_category_a(
            "Gholdengo",
            (("t1", "clean_kill", "decisive"), ("t2", "intentional_non_ko_answer", "decisive"), ("t3", "clean_kill", "toss-up")),
        ),
        _synth_category_a(
            "Garchomp",
            (("t1", "clean_kill", "decisive"), ("t2", "clean_kill", "decisive")),
        ),
        _synth_category_a("Delphox", (("t1", "intentional_non_ko_answer", "costly"),)),
        _synth_category_a(
            "Swampert-Mega",
            (("t1", "clean_kill", "costly"), ("t2", "intentional_non_ko_answer", "toss-up")),
        ),
    ]
    ranked = _rank_category_a(pool, _ARCHALUDON_PELIPPER_LOCKED_TYPES)
    order = [c.species for c in ranked]
    kingambit_rank = order.index("Kingambit")
    swampert_rank = order.index("Swampert-Mega")
    # Kingambit has the single highest raw verified_score in the pool
    # (9.0) but must not win outright given its terrible synergy.
    assert order[0] != "Kingambit"
    # Swampert-Mega has the second-LOWEST raw verified_score (2.5) but
    # its strong synergy must still let it beat Kingambit specifically.
    assert swampert_rank < kingambit_rank


def test_select_diverse_candidates_dedupes_by_lineage_not_exact_species_id():
    """Regression for a real bug found live: the dedup logic only checked
    exact species-id match, which doesn't catch a mega/regional-form
    duplicate of the same underlying species (Abomasnow and
    Abomasnow-Mega both selected as if genuinely different candidates).
    Fixed via lineage_ids grouping -- confirms it holds across both the
    multi-signal-detection step and the final alternatives dedup.
    """
    base = _synth_category_a(
        "Abomasnow", (("t1", "clean_kill", "decisive"),)
    )
    mega = _synth_category_a(
        "Abomasnow-Mega", (("t1", "clean_kill", "decisive"),)
    )
    other = _synth_category_a(
        "Garchomp", (("t1", "intentional_non_ko_answer", "costly"),)
    )
    result = select_diverse_candidates(
        [base, mega, other], (), n_alternatives=2
    )
    all_selected = [result["default"], *result["alternatives"]]
    all_selected = [s for s in all_selected if s is not None]
    from recommender.usage_data import lineage_ids

    seen_lineages: list[set] = []
    for species in all_selected:
        lineage = set(lineage_ids(species))
        assert not any(lineage & seen for seen in seen_lineages), (
            f"{species} shares a lineage with an already-selected candidate"
        )
        seen_lineages.append(lineage)


def _condition_beneficiary_evidence(
    basis: str = "mechanical_only", confidence: str = "high"
) -> CandidateEvidence:
    """Matches real production evidence shape from
    resolve_condition_beneficiaries -- includes the 'need:
    condition_beneficiary' tag the scoping logic in
    _need_branch_evidence requires to correctly distinguish Category C
    from Category B evidence, unlike the generic _evidence() helper,
    which doesn't set any evidence tags at all."""
    return CandidateEvidence(
        basis=basis,  # type: ignore[arg-type]
        confidence=confidence,  # type: ignore[arg-type]
        producer_name="test",
        branch="need",
        evidence=("need:condition_beneficiary", "condition:Rain"),
    )


def test_select_diverse_candidates_picks_from_each_nonempty_category():
    """End-to-end: with real candidates present in all three categories,
    confirms the selection draws from more than just one category rather
    than collapsing back to a single ranking."""
    category_a = _synth_category_a(
        "Garchomp", (("t1", "clean_kill", "decisive"),)
    )
    category_b = AnnotatedCandidate(
        species="Grimmsnarl",
        matching_needs=(_need("screens"),),
        source="need",
        threat_row=None,
        spec={"species": "Grimmsnarl"},
        evidence=(_evidence("compendium_backed"),),
        branches=frozenset({"need"}),
    )
    category_c = AnnotatedCandidate(
        species="Basculegion",
        matching_needs=(_need("condition_beneficiary"),),
        source="need",
        threat_row=None,
        spec={"species": "Basculegion"},
        evidence=(_condition_beneficiary_evidence(),),
        branches=frozenset({"need"}),
    )
    result = select_diverse_candidates(
        [category_a, category_b, category_c], (), n_alternatives=2
    )
    selected = {result["default"], *result["alternatives"]}
    assert "Grimmsnarl" in selected
    assert "Basculegion" in selected


def test_select_diverse_candidates_attacker_hard_excludes_category_b():
    """Attacker preference hard-excludes Category B as a selection source.
    B-only species never appear; dual-branch A+B species may appear via A."""
    category_a = _synth_category_a(
        "Garchomp", (("t1", "clean_kill", "decisive"),)
    )
    dual_branch = AnnotatedCandidate(
        species="Sylveon",
        matching_needs=(_need("screens"),),
        source="both",
        threat_row=_counter(
            "Sylveon", outcome="clean_kill", severity="decisive", usage_rank=1
        ),
        spec={"species": "Sylveon"},
        evidence=(_evidence("compendium_backed"),),
        branches=frozenset({"threat", "need"}),
    )
    b_only = AnnotatedCandidate(
        species="Grimmsnarl",
        matching_needs=(_need("screens"),),
        source="need",
        threat_row=None,
        spec={"species": "Grimmsnarl"},
        evidence=(_evidence("compendium_backed"),),
        branches=frozenset({"need"}),
    )
    category_c = AnnotatedCandidate(
        species="Basculegion",
        matching_needs=(_need("condition_beneficiary"),),
        source="need",
        threat_row=None,
        spec={"species": "Basculegion"},
        evidence=(_condition_beneficiary_evidence(),),
        branches=frozenset({"need"}),
    )
    pool = [category_a, dual_branch, b_only, category_c]
    result = select_diverse_candidates(
        pool, (), n_alternatives=2, preference="attacker"
    )
    selected = {result["default"], *result["alternatives"]}
    assert "Grimmsnarl" not in selected
    assert result["default"] == "Garchomp"
    assert "Basculegion" in selected


def test_select_diverse_candidates_balanced_dedupes_dual_branch_lineage():
    """Balanced picks one per category; a dual-branch species counts once."""
    dual_branch = AnnotatedCandidate(
        species="Sylveon",
        matching_needs=(_need("screens"),),
        source="both",
        threat_row=_counter(
            "Sylveon", outcome="clean_kill", severity="decisive", usage_rank=1
        ),
        spec={"species": "Sylveon"},
        evidence=(_evidence("compendium_backed"),),
        branches=frozenset({"threat", "need"}),
    )
    category_b = AnnotatedCandidate(
        species="Grimmsnarl",
        matching_needs=(_need("trick_room"),),
        source="need",
        threat_row=None,
        spec={"species": "Grimmsnarl"},
        evidence=(_evidence("compendium_backed"),),
        branches=frozenset({"need"}),
    )
    category_c = AnnotatedCandidate(
        species="Basculegion",
        matching_needs=(_need("condition_beneficiary"),),
        source="need",
        threat_row=None,
        spec={"species": "Basculegion"},
        evidence=(_condition_beneficiary_evidence(),),
        branches=frozenset({"need"}),
    )
    result = select_diverse_candidates(
        [dual_branch, category_b, category_c], (), n_alternatives=2
    )
    selected = [result["default"], *result["alternatives"]]
    assert len(selected) == 3
    assert len(set(selected)) == 3
    assert "Sylveon" in selected
    assert result["tracks"]["Sylveon"] == "threat coverage + type synergy"


def test_select_diverse_candidates_support_diversifies_by_need_category():
    """Support preference diversifies within Category B by NeedCategory."""
    trick_room_1 = AnnotatedCandidate(
        species="Hatterene",
        matching_needs=(_need("trick_room"),),
        source="need",
        threat_row=None,
        spec={"species": "Hatterene"},
        evidence=(_evidence("compendium_backed"),),
        branches=frozenset({"need"}),
    )
    trick_room_2 = AnnotatedCandidate(
        species="Gothitelle",
        matching_needs=(_need("trick_room"),),
        source="need",
        threat_row=None,
        spec={"species": "Gothitelle"},
        evidence=(_evidence("compendium_backed"),),
        branches=frozenset({"need"}),
    )
    trick_room_3 = AnnotatedCandidate(
        species="Oranguru",
        matching_needs=(_need("trick_room"),),
        source="need",
        threat_row=None,
        spec={"species": "Oranguru"},
        evidence=(_evidence("compendium_backed"),),
        branches=frozenset({"need"}),
    )
    screens = AnnotatedCandidate(
        species="Grimmsnarl",
        matching_needs=(_need("screens"),),
        source="need",
        threat_row=None,
        spec={"species": "Grimmsnarl"},
        evidence=(_evidence("compendium_backed"),),
        branches=frozenset({"need"}),
    )
    fake_out = AnnotatedCandidate(
        species="Incineroar",
        matching_needs=(_need("fake_out_protection"),),
        source="need",
        threat_row=None,
        spec={"species": "Incineroar"},
        evidence=(_evidence("compendium_backed"),),
        branches=frozenset({"need"}),
    )
    pool = [trick_room_1, trick_room_2, trick_room_3, screens, fake_out]
    result = select_diverse_candidates(
        pool, (), n_alternatives=2, preference="support"
    )
    selected = [result["default"], *result["alternatives"]]
    categories = set()
    by_species = {c.species: c for c in pool}
    for species in selected:
        for need in by_species[species].matching_needs:
            if need.category != "condition_beneficiary":
                categories.add(need.category)
    assert len(categories) >= 2
    assert all(result["tracks"][s] == "support/utility" for s in selected)


def test_select_diverse_candidates_support_preference_is_b_only():
    """Support puts Category B in the default slot with B-only picks."""
    category_a = _synth_category_a(
        "Garchomp", (("t1", "clean_kill", "decisive"),)
    )
    category_b = AnnotatedCandidate(
        species="Grimmsnarl",
        matching_needs=(_need("screens"),),
        source="need",
        threat_row=None,
        spec={"species": "Grimmsnarl"},
        evidence=(_evidence("compendium_backed"),),
        branches=frozenset({"need"}),
    )
    category_c = AnnotatedCandidate(
        species="Basculegion",
        matching_needs=(_need("condition_beneficiary"),),
        source="need",
        threat_row=None,
        spec={"species": "Basculegion"},
        evidence=(_condition_beneficiary_evidence(),),
        branches=frozenset({"need"}),
    )
    pool = [category_a, category_b, category_c]
    support = select_diverse_candidates(
        pool, (), n_alternatives=2, preference="support"
    )
    assert support["default"] == "Grimmsnarl"
    assert all(
        support["tracks"][s] == "support/utility"
        for s in [support["default"], *support["alternatives"]]
        if s
    )


def test_merge_multi_locked_filters_already_provided_tailwind_need():
    """Regression, confirmed live: Archaludon's real, speed-tier-triggered
    'tailwind' support need was still being surfaced as unmet even though
    Pelipper (also locked) already provides Tailwind via its own move --
    query_support_needs generates needs per-anchor with zero awareness of
    what the rest of the locked team already has. Confirms trick_room (a
    provider-type need the team genuinely does NOT yet have) is
    unaffected -- this is a targeted filter, not a blanket removal of
    speed-control needs.
    """
    draft = [
        _locked(
            "Archaludon",
            role="bulky_special_attacker",
            ability="Stamina",
            moves=["Electro Shot", "Flash Cannon", "Protect", "Dragon Pulse"],
        ),
        _locked(
            "Pelipper",
            role="support_speed_control",
            ability="Drizzle",
            item="Focus Sash",
            moves=["Hurricane", "Weather Ball", "Tailwind", "Wide Guard"],
        ),
        *[empty_slot() for _ in range(4)],
    ]
    state = _state(draft)
    contexts = collect_locked_anchor_contexts(state)
    merged = merge_multi_locked_candidates(
        state, contexts, (), None, ownership_mode="off", owned_species=frozenset()
    )
    tailwind_matches = [
        row for row in merged if any(n.category == "tailwind" for n in row.matching_needs)
    ]
    assert tailwind_matches == []
    trick_room_matches = [
        row for row in merged if any(n.category == "trick_room" for n in row.matching_needs)
    ]
    assert len(trick_room_matches) > 0


def test_merge_multi_locked_filters_already_provided_tailwind_need_with_resilience_wired():
    """Regression, confirmed live (2026-08-21): the sibling test above
    (test_merge_multi_locked_filters_already_provided_tailwind_need) passes
    condition_resilience=None, which skips gap_support_needs entirely --
    so it could never have caught this. discover_multi_locked always wires
    a real condition_resilience through, and once it's present,
    gap_support_needs re-derived a 'tailwind' need for the exact
    single_provider_spof case the first filter had just removed, because it
    checked coverage against the same already-filtered anchored_needs tuple.
    Live symptom: Whimsicott and Aerodactyl kept appearing as
    compendium-backed 'tailwind_setter' support/utility picks turn after
    turn despite Pelipper already providing Tailwind. This test wires
    condition_resilience the same way discover_multi_locked does, so a
    regression here can't hide behind an under-specified test call again.
    """
    from recommender.condition_resilience import assess_condition_resilience

    draft = [
        _locked(
            "Archaludon",
            role="bulky_special_attacker",
            ability="Stamina",
            moves=["Electro Shot", "Flash Cannon", "Protect", "Dragon Pulse"],
        ),
        _locked(
            "Pelipper",
            role="support_speed_control",
            ability="Drizzle",
            item="Focus Sash",
            moves=["Hurricane", "Weather Ball", "Tailwind", "Wide Guard"],
        ),
        *[empty_slot() for _ in range(4)],
    ]
    state = _state(draft)
    contexts = collect_locked_anchor_contexts(state)
    resilience = assess_condition_resilience(contexts)
    merged = merge_multi_locked_candidates(
        state,
        contexts,
        (),
        None,
        ownership_mode="off",
        owned_species=frozenset(),
        condition_resilience=resilience,
    )
    tailwind_matches = [
        row for row in merged if any(n.category == "tailwind" for n in row.matching_needs)
    ]
    assert tailwind_matches == []
    whimsicott = [row for row in merged if row.species == "Whimsicott"]
    if whimsicott:
        assert all(n.category != "tailwind" for n in whimsicott[0].matching_needs)
    aerodactyl = [row for row in merged if row.species == "Aerodactyl"]
    if aerodactyl:
        assert all(n.category != "tailwind" for n in aerodactyl[0].matching_needs)


def test_merge_multi_locked_filters_already_covered_screens_need():
    """Regression, confirmed live (2026-08-21): Sableye kept surfacing as a
    fresh 'screens_support' candidate turn after turn even after Grimmsnarl
    -- a real, committed screens setter (Light Clay + both Light Screen and
    Reflect) -- was already locked. Unlike tailwind/trick_room/weather,
    screens is deliberately NOT one of TRACKED_CONDITIONS (ADR-028's
    original scoping -- it doesn't fit the same 0/1/2+ provider-cardinality
    model), so it never got an already-provided filter at all: the
    unconditional 'screens' need (query_support_needs, trigger=None, fires
    for every offense-primary anchor) has zero team-state awareness on its
    own. has_reliable_screens_provider adds a narrower, boolean-only check
    (not a full provider-cardinality model) reusing anchor_roles.py's
    existing wanted/secondary distinction for screens mechanisms.
    """
    draft = [
        _locked(
            "Archaludon",
            role="bulky_special_attacker",
            ability="Stamina",
            moves=["Electro Shot", "Flash Cannon", "Protect", "Dragon Pulse"],
        ),
        _locked(
            "Grimmsnarl",
            role="screens_support",
            ability="Prankster",
            item="Light Clay",
            moves=["Parting Shot", "Reflect", "Light Screen", "Spirit Break"],
        ),
        *[empty_slot() for _ in range(4)],
    ]
    state = _state(draft)
    contexts = collect_locked_anchor_contexts(state)
    merged = merge_multi_locked_candidates(
        state, contexts, (), None, ownership_mode="off", owned_species=frozenset()
    )
    screens_matches = [
        row for row in merged if any(n.category == "screens" for n in row.matching_needs)
    ]
    assert screens_matches == []
    sableye = [row for row in merged if row.species == "Sableye"]
    if sableye:
        assert all(n.category != "screens" for n in sableye[0].matching_needs)


def test_has_reliable_screens_provider_requires_genuine_commitment():
    """A single incidental screen move (secondary importance) must not
    count -- only Aurora Veil, both Light Screen and Reflect, or Light
    Clay plus at least one screen move (anchor_roles.py's existing
    'wanted' bar) should suppress the generic screens need. Confirms the
    boolean check isn't accidentally looser than the real mechanism
    evidence it's built on.
    """
    from recommender.condition_resilience import has_reliable_screens_provider

    committed = [
        _locked(
            "Grimmsnarl",
            role="screens_support",
            ability="Prankster",
            item="Light Clay",
            moves=["Parting Shot", "Reflect", "Light Screen", "Spirit Break"],
        ),
    ]
    incidental = [
        _locked(
            "Archaludon",
            role="bulky_special_attacker",
            ability="Stamina",
            # Single, incidental Reflect -- not a real screens commitment.
            moves=["Reflect", "Flash Cannon", "Protect", "Dragon Pulse"],
        ),
    ]
    assert has_reliable_screens_provider(collect_locked_anchor_contexts(_state(committed)))
    assert not has_reliable_screens_provider(
        collect_locked_anchor_contexts(_state(incidental))
    )


def test_provided_conditions_reflects_real_locked_mechanisms():
    """Direct unit test for the new helper: confirms it correctly
    identifies Tailwind as team-provided (via Pelipper's move) and
    Trick Room as NOT provided, using the real anchor-resolution
    pipeline, not a hand-constructed mock."""
    from recommender.condition_resilience import provided_conditions

    draft = [
        _locked(
            "Archaludon",
            role="bulky_special_attacker",
            ability="Stamina",
            moves=["Electro Shot", "Flash Cannon", "Protect", "Dragon Pulse"],
        ),
        _locked(
            "Pelipper",
            role="support_speed_control",
            ability="Drizzle",
            item="Focus Sash",
            moves=["Hurricane", "Weather Ball", "Tailwind", "Wide Guard"],
        ),
    ]
    state = _state(draft)
    contexts = collect_locked_anchor_contexts(state)
    conditions = provided_conditions(contexts)
    assert "Tailwind" in conditions
    assert "Rain" in conditions
    assert "Trick Room" not in conditions


def test_select_diverse_candidates_returns_track_labels():
    """Confirms select_diverse_candidates surfaces which track each pick
    came from -- default and each alternative -- using the exact labels
    requested directly, not an inferred format."""
    category_a = _synth_category_a(
        "Garchomp", (("t1", "clean_kill", "decisive"),)
    )
    category_b = AnnotatedCandidate(
        species="Grimmsnarl",
        matching_needs=(_need("screens"),),
        source="need",
        threat_row=None,
        spec={"species": "Grimmsnarl"},
        evidence=(_evidence("compendium_backed"),),
        branches=frozenset({"need"}),
    )
    category_c = AnnotatedCandidate(
        species="Basculegion",
        matching_needs=(_need("condition_beneficiary"),),
        source="need",
        threat_row=None,
        spec={"species": "Basculegion"},
        evidence=(_condition_beneficiary_evidence(),),
        branches=frozenset({"need"}),
    )
    result = select_diverse_candidates(
        [category_a, category_b, category_c], (), n_alternatives=2
    )
    tracks = result["tracks"]
    assert tracks["Garchomp"] == "threat coverage + type synergy"
    assert tracks["Grimmsnarl"] == "support/utility"
    assert tracks["Basculegion"] == "condition synergy"


def test_select_diverse_candidates_excludes_low_confidence_only_from_category_b_c():
    """Regression, confirmed live: a candidate whose ONLY evidence for a
    category is low confidence must not be selected as that category's
    representative at all, even as its top-ranked candidate within a
    weak pool -- confirmed as a deliberate design decision, not assumed:
    other signals (shared-teammate, additional matching_needs) are only
    meant to rank candidates within a genuine confidence tier, never to
    substitute for one. A category with no strong-evidence candidate at
    all correctly contributes nothing, falling through to whatever
    other categories have available (existing fallback logic, unchanged
    by this fix).
    """
    weak_only = AnnotatedCandidate(
        species="Sylveon",
        matching_needs=(_need("healing_cleric"),),
        source="need",
        threat_row=None,
        spec={"species": "Sylveon"},
        evidence=(
            CandidateEvidence(
                basis="mechanical_only",
                confidence="low",
                producer_name="test",
                branch="need",
            ),
        ),
        branches=frozenset({"need"}),
    )
    strong_a = _synth_category_a(
        "Garchomp", (("t1", "clean_kill", "decisive"),)
    )
    result = select_diverse_candidates([weak_only, strong_a], (), n_alternatives=2)
    assert "Sylveon" not in {result["default"], *result["alternatives"]}


def test_select_diverse_candidates_still_includes_genuinely_strong_category_b():
    """Confirms the fix is targeted, not a blanket exclusion of Category
    B/C -- a candidate with genuine, non-low evidence for the category
    must still be selectable."""
    strong_b = AnnotatedCandidate(
        species="Grimmsnarl",
        matching_needs=(_need("screens"),),
        source="need",
        threat_row=None,
        spec={"species": "Grimmsnarl"},
        evidence=(
            CandidateEvidence(
                basis="compendium_backed",
                confidence="medium",
                producer_name="test",
                branch="need",
            ),
        ),
        branches=frozenset({"need"}),
    )
    result = select_diverse_candidates([strong_b], (), n_alternatives=2)
    assert result["default"] == "Grimmsnarl"


def test_rank_by_need_evidence_scoped_to_relevant_category_not_full_evidence():
    """Regression, confirmed live: a candidate's strong, unrelated
    evidence (e.g. real threat-counter data) mixed into its overall
    evidence tuple was incorrectly letting it pass Category B's
    confidence gate and rank highly within it, even though its actual,
    genuinely weak support-need evidence never should have qualified on
    its own. Same class of bug as the earlier evidence-display scoping
    fix, but here affecting the underlying selection logic itself, not
    just what gets displayed afterward.
    """
    strong_threat_evidence = CandidateEvidence(
        basis="usage_backed",
        confidence="high",
        producer_name="query_counters",
        branch="threat",
        evidence=("usage:sylveon",),
    )
    weak_need_evidence = CandidateEvidence(
        basis="mechanical_only",
        confidence="low",
        producer_name="test",
        branch="need",
        evidence=("need:healing_cleric", "trigger:tank_no_self_heal", "move:wish"),
    )
    sylveon_shaped = AnnotatedCandidate(
        species="Sylveon",
        matching_needs=(_need("healing_cleric"),),
        source="need",
        threat_row=None,
        spec={"species": "Sylveon"},
        evidence=(strong_threat_evidence, weak_need_evidence),
        branches=frozenset({"need"}),
    )
    result = select_diverse_candidates([sylveon_shaped], (), n_alternatives=2)
    assert result["default"] is None
    assert result["alternatives"] == []


def test_rank_by_need_evidence_correctly_distinguishes_b_and_c_scoping():
    """Confirms _need_branch_evidence's condition_beneficiary parameter
    actually changes which evidence counts -- a candidate whose only
    strong evidence is condition_beneficiary-tagged should qualify for
    Category C but not Category B, and vice versa."""
    condition_evidence = CandidateEvidence(
        basis="mechanical_only",
        confidence="high",
        producer_name="test",
        branch="need",
        evidence=("need:condition_beneficiary", "condition:Rain"),
    )
    rain_only = AnnotatedCandidate(
        species="Basculegion",
        matching_needs=(_need("condition_beneficiary"),),
        source="need",
        threat_row=None,
        spec={"species": "Basculegion"},
        evidence=(condition_evidence,),
        branches=frozenset({"need"}),
    )
    result = select_diverse_candidates([rain_only], (), n_alternatives=2)
    assert result["default"] == "Basculegion"
    assert result["tracks"]["Basculegion"] == "condition synergy"


def test_rank_multi_locked_by_category_gives_each_category_its_own_cut():
    """Regression, confirmed live: rank_multi_locked_candidates' single,
    combined top-10 cut (via the old _rank_key) was defeating
    select_diverse_candidates' entire purpose -- genuinely valuable
    Category B/C candidates got cut from the pool entirely whenever
    10+ candidates ranked higher by threat-coverage/type-synergy
    criteria alone, the common case with real threat-counter data.
    Confirms each category now gets its own top-N cut: 15 strong
    Category A candidates and 1 real Category B candidate must both
    survive, not just the 10 A-category candidates a shared cut would
    have kept.
    """
    category_a_candidates = [
        _synth_category_a(f"Attacker{i}", (("t1", "clean_kill", "decisive"),))
        for i in range(15)
    ]
    category_b_candidate = AnnotatedCandidate(
        species="Grimmsnarl",
        matching_needs=(_need("screens"),),
        source="need",
        threat_row=None,
        spec={"species": "Grimmsnarl"},
        evidence=(_evidence("compendium_backed"),),
        branches=frozenset({"need"}),
    )
    pool = [*category_a_candidates, category_b_candidate]
    result = rank_multi_locked_by_category(pool, (), n_per_category=10)
    result_species = {c.species for c in result}
    assert "Grimmsnarl" in result_species, (
        "Category B candidate must survive its own cut, not be squeezed "
        "out by 15 Category A candidates in a shared ranking"
    )
    assert len(result_species) == 11  # 10 from category A + 1 from B


def _category_b_need_candidate(
    species: str,
    categories: tuple[str, ...],
    *,
    confidence: str = "medium",
    basis: str = "compendium_backed",
) -> AnnotatedCandidate:
    needs = tuple(_need(category) for category in categories)
    evidence = tuple(
        CandidateEvidence(
            basis=basis,  # type: ignore[arg-type]
            confidence=confidence,  # type: ignore[arg-type]
            producer_name="test",
            evidence=tuple(f"need:{category}" for category in categories),
            branch="need",
        )
        for category in categories
    )
    return AnnotatedCandidate(
        species=species,
        matching_needs=needs,
        source="need",
        threat_row=None,
        spec={"species": species},
        evidence=evidence,
        branches=frozenset({"need"}),
    )


def test_diversify_fallback_prefers_new_category_over_redundant():
    from recommender.team_candidates import _diversify_by_need_category

    pool = [
        _category_b_need_candidate("SinistchaLike", ("healing_cleric", "trick_room")),
        _category_b_need_candidate("AromatisseLike", ("healing_cleric", "trick_room")),
        _category_b_need_candidate("GrimmsnarlLike", ("screens",)),
        _category_b_need_candidate("AudinoLike", ("healing_cleric", "trick_room")),
        _category_b_need_candidate("IncineroarLike", ("fake_out_protection",)),
    ]
    picked = _diversify_by_need_category(pool, n=3)
    assert [c.species for c in picked] == [
        "SinistchaLike",
        "GrimmsnarlLike",
        "IncineroarLike",
    ]


def test_diversify_fallback_skips_duplicate_need_profile():
    from recommender.team_candidates import _diversify_by_need_category

    pool = [
        _category_b_need_candidate("SinistchaLike", ("healing_cleric", "trick_room")),
        _category_b_need_candidate("AromatisseLike", ("healing_cleric", "trick_room")),
        _category_b_need_candidate("KlefkiLike", ("screens", "trick_room")),
        _category_b_need_candidate("AudinoLike", ("healing_cleric", "trick_room")),
        _category_b_need_candidate("SableyeLike", ("screens",)),
    ]
    picked = _diversify_by_need_category(pool, n=3)
    assert [c.species for c in picked] == [
        "SinistchaLike",
        "KlefkiLike",
        "SableyeLike",
    ]


def test_support_widens_category_b_cut_for_support_only():
    pool = [
        _category_b_need_candidate(
            f"Rank{i}",
            ("healing_cleric", "trick_room"),
            confidence="high",
        )
        for i in range(10)
    ]
    pool.append(_category_b_need_candidate("Sableye", ("screens",), confidence="medium"))
    ranked_default = rank_multi_locked_by_category(pool, (), n_per_category=10)
    ranked_wide = rank_multi_locked_by_category(
        pool, (), category_b_n=SUPPORT_CATEGORY_B_POOL_N
    )
    ranked_none = rank_multi_locked_by_category(pool, (), category_b_n=None)
    default_species = {c.species for c in ranked_default}
    wide_species = {c.species for c in ranked_wide}
    assert "Sableye" not in default_species
    assert "Sableye" in wide_species
    assert default_species == {c.species for c in ranked_none}


def test_discover_multi_locked_passes_widened_b_cut_for_support():
    from recommender.nodes import discover_multi_locked
    from recommender.slot_fill import SlotFillPresentation, SlotFillTerminalResult
    from recommender.team_candidates import SUPPORT_CATEGORY_B_POOL_N

    terminal = SlotFillTerminalResult(
        presentation=SlotFillPresentation(slot_index=2, candidates=(), notices=()),
        state_updates={},
        deferred=False,
    )

    draft = [
        _locked(
            "Archaludon",
            role="bulky_special_attacker",
            ability="Stamina",
            moves=["Electro Shot", "Flash Cannon", "Protect", "Dragon Pulse"],
        ),
        _locked(
            "Pelipper",
            role="support_speed_control",
            ability="Drizzle",
            item="Focus Sash",
            moves=["Hurricane", "Weather Ball", "Tailwind", "Wide Guard"],
        ),
        *[empty_slot() for _ in range(4)],
    ]
    stub = _category_b_need_candidate("Stub", ("screens",))
    review = TeamReviewResult(threats=[], coverage=[], spofs=[])
    threat = TeamThreatDiscovery(status="available", candidates=(), error=None)

    with (
        patch("recommender.nodes._compute_team_review", return_value=review),
        patch("recommender.nodes.query_shared_teammates", return_value=None),
        patch(
            "recommender.threat_counters.query_candidates_for_threats",
            return_value=threat,
        ),
        patch(
            "recommender.team_candidates.merge_multi_locked_candidates",
            return_value=[stub],
        ),
        patch(
            "recommender.team_candidates.annotate_composition_impact",
            side_effect=lambda rows, *args, **kwargs: list(rows),
        ),
        patch(
            "recommender.team_candidates.gather_masked_core_packages",
            return_value=[],
        ),
        patch(
            "recommender.team_candidates.rank_multi_locked_by_category",
        ) as mocked_cut,
        patch("recommender.slot_fill.run_slot_fill_terminal", return_value=terminal),
    ):
        mocked_cut.return_value = [stub]
        support_state = {
            **_state(draft),
            "team_completion_preference": "support",
        }
        discover_multi_locked(support_state, {})  # type: ignore[arg-type]
        assert (
            mocked_cut.call_args.kwargs.get("category_b_n")
            == SUPPORT_CATEGORY_B_POOL_N
        )

        mocked_cut.reset_mock()
        attacker_state = {
            **_state(draft),
            "team_completion_preference": "attacker",
        }
        discover_multi_locked(attacker_state, {})  # type: ignore[arg-type]
        assert mocked_cut.call_args.kwargs.get("category_b_n") is None
