"""Unit tests for plain-text turn rendering (no graph)."""

from __future__ import annotations

from recommender.matchup import MatchupResult
from recommender.present_text import (
    BOOTSTRAP_PARSER_FIX_HINT,
    BOOTSTRAP_PARSER_NOT_CONFIGURED,
    NO_PENDING_MESSAGE,
    TEAM_REVIEW_DETAIL_HINT,
    UNMATCHED_REPLY_PREFIX,
    _best_evidence_row,
    format_builds,
    format_evidence_summary,
    format_no_pending,
    format_roster,
    format_team_review,
    format_turn,
)
from recommender.state import (
    Attr,
    CandidateDiscoveryError,
    CandidateEvidence,
    ProvisionalSlot,
    Slot,
    SPOFFinding,
    TargetRoleDecision,
    TeamReviewResult,
    ThreatCandidate,
    ThreatCoverageResult,
    UnresolvedTargetRoleDecision,
    empty_slot,
)


def _locked(species: str, role: str = "bulky_attacker") -> Slot:
    return Slot(
        role=Attr(role, locked=True),
        species=Attr(species, locked=True),
        ability=Attr("Pressure", locked=True),
        item=Attr("Leftovers", locked=True),
        moveset=Attr(["Protect", "Tackle", "Rest", "Sleep Talk"], locked=True),
        spread=Attr(
            {"hp": 32, "atk": 32, "def": 2, "spa": 0, "spd": 0, "spe": 0},
            locked=True,
        ),
        nature=Attr("Adamant", locked=True),
    )


def test_format_evidence_summary_basic():
    evidence = CandidateEvidence(
        basis="usage_backed",
        confidence="high",
        producer_name="query_by_usage",
        evidence=("usage:pelipper",),
    )
    assert format_evidence_summary(evidence) == "usage_backed, high confidence"


def test_format_evidence_summary_degradation_tokens():
    evidence = CandidateEvidence(
        basis="mechanical_only",
        confidence="low",
        producer_name="query_threat_counters",
        evidence=("static_type_estimate", "calc_unavailable", "wall_axis"),
    )
    line = format_evidence_summary(evidence)
    assert "mechanical_only, low confidence" in line
    assert "calc_unavailable" in line
    assert "static_type_estimate" in line


def test_best_evidence_row_prefers_commitment_over_lower_compendium():
    """Grimmsnarl-shaped: Fix A downgrades Excellent screens to low, but
    real commitment_pct usage_backed/medium must win display."""
    rows = (
        CandidateEvidence(
            basis="compendium_backed",
            confidence="low",
            producer_name="role_compendium",
            evidence=("need:screens", "tier:Excellent", "role:screens_support"),
            branch="need",
        ),
        CandidateEvidence(
            basis="usage_backed",
            confidence="medium",
            producer_name="narrow_candidates_for_move",
            evidence=(
                "need:screens",
                "commitment_pct:86.1",
                "move:lightscreen",
            ),
            branch="need",
        ),
    )
    assert (
        format_evidence_summary(_best_evidence_row(rows))
        == "usage_backed, medium confidence"
    )


def test_best_evidence_row_keeps_compendium_when_confidence_tied():
    rows = (
        CandidateEvidence(
            basis="compendium_backed",
            confidence="medium",
            producer_name="role_compendium",
            evidence=("need:screens", "tier:Excellent"),
            branch="need",
        ),
        CandidateEvidence(
            basis="usage_backed",
            confidence="medium",
            producer_name="narrow_candidates_for_move",
            evidence=("need:screens", "commitment_pct:86.1"),
            branch="need",
        ),
    )
    assert (
        format_evidence_summary(_best_evidence_row(rows))
        == "compendium_backed, medium confidence"
    )


def test_bootstrap_intake_renders_prompt_and_notices():
    text = format_turn(
        {
            "pending_presentation": {
                "kind": "bootstrap_intake",
                "prompt_text": "What direction or anchor would you like?",
                "notices": ("Couldn't identify: Missing One",),
            }
        }
    )
    assert "What direction or anchor would you like?" in text
    assert "Couldn't identify: Missing One" in text
    assert "you pick" in text.lower() or "Reply with a direction" in text


def test_candidate_selection_evidence_line():
    text = format_turn(
        {
            "pending_presentation": {
                "kind": "candidate_selection",
                "slot_index": 0,
                "options": [
                    {
                        "species": "Pelipper",
                        "source": "bootstrap",
                        "direction_label": "Rain setter",
                        "primary_function": "support",
                        "target_role_decision": TargetRoleDecision(
                            role_id="rain_setter",
                            source="user_choice",
                        ),
                        "evidence": (
                            CandidateEvidence(
                                "usage_backed",
                                "high",
                                "query_by_usage",
                                ("usage:pelipper",),
                            ),
                        ),
                    }
                ],
            }
        }
    )
    assert "1. Pelipper" in text
    assert "usage_backed, high confidence" in text
    assert "reject N drops only that species" in text


def test_candidate_selection_shows_slash_need_categories():
    text = format_turn(
        {
            "pending_presentation": {
                "kind": "candidate_selection",
                "slot_index": 0,
                "options": [
                    {
                        "species": "Aromatisse",
                        "source": "need",
                        "need_categories": ["healing_cleric", "trick_room"],
                        "secondary_trick_room": True,
                        "target_role_decision": {
                            "role_id": "trick_room_setter",
                            "source": "support_need",
                            "evidence": (),
                            "needed_constraints": (),
                            "confidence": "high",
                            "provenance": (),
                            "producer_name": "test",
                        },
                        "evidence": (
                            CandidateEvidence(
                                "usage_backed",
                                "medium",
                                "test",
                                ("need:healing_cleric",),
                            ),
                        ),
                    }
                ],
            }
        }
    )
    assert "healing_cleric / trick_room" in text
    assert "trick_room_setter" not in text
    assert "base build includes Trick Room" in text


def test_candidate_selection_shows_primary_role_when_differs_from_need_role():
    text = format_turn(
        {
            "pending_presentation": {
                "kind": "candidate_selection",
                "slot_index": 0,
                "options": [
                    {
                        "species": "Sinistcha",
                        "source": "need",
                        "need_categories": ["trick_room"],
                        "target_role_decision": TargetRoleDecision(
                            role_id="trick_room_setter",
                            source="support_need",
                        ),
                        "species_primary_role": "redirection",
                        "evidence": (
                            CandidateEvidence(
                                "usage_backed",
                                "high",
                                "test",
                                ("need:trick_room",),
                            ),
                        ),
                    }
                ],
            }
        }
    )
    assert "trick_room" in text
    assert "trick_room_setter" in text
    assert "primary: redirection" in text


def test_candidate_selection_hides_primary_role_when_agrees():
    text = format_turn(
        {
            "pending_presentation": {
                "kind": "candidate_selection",
                "slot_index": 0,
                "options": [
                    {
                        "species": "Grimmsnarl",
                        "source": "need",
                        "need_categories": ["screens"],
                        "target_role_decision": TargetRoleDecision(
                            role_id="screens_support",
                            source="support_need",
                        ),
                        "species_primary_role": "screens_support",
                        "evidence": (
                            CandidateEvidence(
                                "usage_backed",
                                "medium",
                                "test",
                                ("need:screens",),
                            ),
                        ),
                    }
                ],
            }
        }
    )
    assert "screens" in text
    assert "primary:" not in text


def test_candidate_selection_shows_primary_when_tr_role_bit_suppressed():
    text = format_turn(
        {
            "pending_presentation": {
                "kind": "candidate_selection",
                "slot_index": 0,
                "options": [
                    {
                        "species": "Sinistcha",
                        "source": "need",
                        "need_categories": ["healing_cleric", "trick_room"],
                        "secondary_trick_room": True,
                        "target_role_decision": TargetRoleDecision(
                            role_id="trick_room_setter",
                            source="support_need",
                        ),
                        "species_primary_role": "redirection",
                        "evidence": (
                            CandidateEvidence(
                                "usage_backed",
                                "medium",
                                "test",
                                ("need:trick_room",),
                            ),
                        ),
                    }
                ],
            }
        }
    )
    assert "trick_room_setter" not in text
    assert "primary: redirection" in text


def test_candidate_selection_uses_best_evidence_not_first():
    """Regression for the rain-suggestion display bug (2026-08-16/17).

    A candidate's evidence tuple is merged across every support need it
    satisfies, not just the one it's being presented for. When a low-quality
    entry (e.g. from an unrelated, compendium-uncovered need) arrives before
    a high-quality one (e.g. real compendium-backed evidence for the role
    actually being offered), the displayed confidence text must reflect the
    best evidence, not whichever happened to be merged in first. Confirmed
    live: Meowstic displayed 'mechanical_only, low confidence' for a
    rain_setter suggestion backed by real compendium_backed/medium Rain
    evidence, because an unrelated screens-need mechanical entry landed
    first in its merged evidence tuple.
    """
    text = format_turn(
        {
            "pending_presentation": {
                "kind": "candidate_selection",
                "slot_index": 0,
                "options": [
                    {
                        "species": "Meowstic",
                        "source": "need",
                        "target_role_decision": TargetRoleDecision(
                            role_id="rain_setter",
                            source="usage_backed",
                        ),
                        "evidence": (
                            # Unrelated (screens), low-quality, arrives first.
                            CandidateEvidence(
                                "mechanical_only",
                                "low",
                                "narrow_candidates_for_move",
                                (),
                            ),
                            # Real evidence for the role actually offered.
                            CandidateEvidence(
                                "compendium_backed",
                                "medium",
                                "role_category_evidence",
                                (),
                            ),
                        ),
                    }
                ],
            }
        }
    )
    assert "1. Meowstic" in text
    assert "compendium_backed, medium confidence" in text
    assert "mechanical_only, low confidence" not in text
    assert "rain_setter" in text


def test_candidate_selection_renders_unresolved_role_ambiguity():
    """Meowstic-shaped unresolved rain|TR must show both roles, not a blank label."""
    text = format_turn(
        {
            "pending_presentation": {
                "kind": "candidate_selection",
                "slot_index": 0,
                "options": [
                    {
                        "species": "Meowstic",
                        "source": "need",
                        "target_role_decision": UnresolvedTargetRoleDecision(
                            reason="ambiguous_speed_control",
                            ambiguity=("rain_setter", "trick_room_setter"),
                            source="support_need",
                        ),
                        "evidence": (
                            CandidateEvidence(
                                "compendium_backed",
                                "medium",
                                "role_category_evidence",
                                ("role:trick_room_setter",),
                            ),
                        ),
                    },
                    {
                        "species": "Gardevoir-Mega",
                        "source": "need",
                        "target_role_decision": TargetRoleDecision(
                            role_id="trick_room_setter",
                            source="support_need",
                        ),
                        "evidence": (
                            CandidateEvidence(
                                "compendium_backed",
                                "medium",
                                "role_category_evidence",
                                ("role:trick_room_setter",),
                            ),
                        ),
                    },
                ],
            }
        }
    )
    assert "1. Meowstic" in text
    assert "rain_setter or trick_room_setter (unresolved)" in text
    assert "2. Gardevoir-Mega — trick_room_setter" in text


def test_candidate_selection_surfaces_degradation_tokens():
    text = format_turn(
        {
            "pending_presentation": {
                "kind": "candidate_selection",
                "options": [
                    {
                        "species": "Incineroar",
                        "source": "threat",
                        "evidence": (
                            CandidateEvidence(
                                "mechanical_only",
                                "low",
                                "query_threat_counters",
                                ("static_type_estimate", "calc_unavailable"),
                            ),
                        ),
                    }
                ],
            }
        }
    )
    assert "calc_unavailable" in text
    assert "static_type_estimate" in text


def test_full_build_confirmation_from_provisional_slot():
    provisional = ProvisionalSlot(
        schema_version=1,
        slot_index=0,
        target_role_decision=TargetRoleDecision(
            role_id="rain_setter", source="user_choice"
        ),
        species="Pelipper",
        ability="Drizzle",
        item="Damp Rock",
        moves=("Hurricane", "U-turn", "Weather Ball", "Protect"),
        nature="Modest",
        spread=(("hp", 4), ("spa", 252), ("spe", 252)),
    )
    text = format_turn(
        {
            "provisional_slot": provisional,
            "pending_presentation": {
                "kind": "full_build_confirmation",
                "slot_index": 0,
                "provisional_fingerprint": "fp",
            },
        }
    )
    assert "Pelipper" in text
    assert "Drizzle" in text
    assert "Damp Rock" in text
    assert "Accept this build?" in text
    assert "yes" in text.lower()


def test_full_build_confirmation_renders_review_flags():
    provisional = ProvisionalSlot(
        schema_version=1,
        slot_index=0,
        target_role_decision=TargetRoleDecision(
            role_id="rain_setter", source="user_choice"
        ),
        species="Pelipper",
        ability="Drizzle",
        item="Damp Rock",
        moves=("Hurricane", "U-turn", "Weather Ball", "Protect"),
        nature="Modest",
        spread=(("hp", 4), ("spa", 32), ("spe", 30)),
    )
    text = format_turn(
        {
            "provisional_slot": provisional,
            "pending_presentation": {
                "kind": "full_build_confirmation",
                "slot_index": 0,
                "provisional_fingerprint": "fp",
                "review_flags": (
                    {
                        "claim": "EVs invested in ATK, which Timid hinders",
                        "check": "ev_into_nature_hindered",
                        "basis": "deterministic",
                    },
                ),
            },
        }
    )
    assert "Note: EVs invested in ATK, which Timid hinders" in text


def test_calc_unavailable_error_only_no_fake_options():
    error = CandidateDiscoveryError(
        kind="calc_unavailable",
        stage="coverage",
        message="calc service down",
        retryable=True,
    )
    text = format_turn(
        {
            "pending_presentation": None,
            "candidate_discovery_error": error,
            "team_draft": [_locked("Garchomp")],
        }
    )
    assert "calc_unavailable" in text
    assert "calc service down" in text
    assert "1. " not in text or "Garchomp" in text
    assert "Incineroar" not in text


def test_format_builds_locked_slots():
    text = format_builds({"team_draft": [_locked("Incineroar")]})
    assert "Incineroar" in text
    assert "Pressure" in text
    assert "Leftovers" in text
    assert "Adamant" in text
    assert "Protect" in text
    assert "Tackle" in text


def test_format_builds_empty():
    assert "no locked members" in format_builds({"team_draft": []})


def test_format_builds_skips_partial():
    partial = empty_slot()
    partial.species = Attr("Pelipper", locked=True)
    text = format_builds({"team_draft": [partial, _locked("Incineroar")]})
    assert "Incineroar" in text
    assert "Pelipper" not in text


def _sample_threat() -> ThreatCandidate:
    return ThreatCandidate(
        ladder_species="Kingambit",
        usage_rank=3,
        form="Kingambit",
        showdown_usage_pct=None,
        showdown_formes=(),
        spec={"species": "Kingambit"},
        build_source="ingame",
    )


def test_format_team_review_gaps_and_spofs():
    draft = [_locked("Incineroar")]
    review = TeamReviewResult(
        threats=[_sample_threat()],
        coverage=[
            ThreatCoverageResult(
                {"species": "Gapmon"},
                MatchupResult("no_answer", "toss-up"),
                [],
                None,
                False,
            )
        ],
        spofs=[SPOFFinding(0, [{"species": "Gapmon"}], {"gapmon": "costly"})],
    )
    text = format_team_review(review, team_draft=draft)
    assert "Kingambit" not in text
    assert "Gapmon" in text
    assert "no_answer" in text
    assert "1. Incineroar loses Gapmon" in text
    assert TEAM_REVIEW_DETAIL_HINT in text


def test_format_team_review_threats_section():
    review = TeamReviewResult(threats=[_sample_threat()], coverage=[], spofs=[])
    text = format_team_review(
        review,
        sections=frozenset({"threats"}),
        show_detail_hint=False,
    )
    assert "Kingambit" in text
    assert "Threats:" in text
    assert "Coverage gaps:" not in text
    assert "SPOFs:" not in text
    assert TEAM_REVIEW_DETAIL_HINT not in text


def test_format_team_review_covered_section():
    review = TeamReviewResult(
        threats=[],
        coverage=[
            ThreatCoverageResult(
                {"species": "Coveredmon"},
                MatchupResult("clean_answer", "favorable"),
                [0],
                None,
                False,
            )
        ],
        spofs=[],
    )
    text = format_team_review(
        review,
        team_draft=[_locked("Incineroar")],
        sections=frozenset({"covered"}),
        show_detail_hint=False,
    )
    assert "Covered:" in text
    assert "covered by" in text
    assert "Coverage gaps:" not in text
    assert "Threats:" not in text


def test_format_team_review_default_hint():
    review = TeamReviewResult(threats=[_sample_threat()], coverage=[], spofs=[])
    text = format_team_review(review)
    assert TEAM_REVIEW_DETAIL_HINT in text
    assert "Threats:\n" not in text
    assert "Covered:\n" not in text


def test_format_team_review_composition_gaps():
    draft = [_locked("Incineroar")]
    review = TeamReviewResult(
        threats=[],
        coverage=[],
        spofs=[],
        composition_gaps=["redirection: no primary provider on locked team"],
    )
    text = format_team_review(review, team_draft=draft)
    assert "Composition gaps:" in text
    assert "redirection: no primary provider on locked team" in text


def test_format_team_review_flagged_separate():
    review = TeamReviewResult(
        threats=[],
        coverage=[
            ThreatCoverageResult(
                {"species": "Conditional"},
                MatchupResult("conditionally_dependent_answer", "costly"),
                [0],
                None,
                True,
            )
        ],
        spofs=[],
    )
    text = format_team_review(review, team_draft=[_locked("Incineroar")])
    assert "Conditional coverage:" in text
    assert "Conditional:" in text
    assert "Coverage gaps:\n  (none)" in text


def test_format_team_review_unavailable():
    error = CandidateDiscoveryError(
        kind="calc_unavailable",
        stage="coverage",
        message="calc down",
        retryable=True,
    )
    review = TeamReviewResult([], [], [], status="unavailable", error=error)
    with_error = format_team_review(review, include_error=True)
    without_error = format_team_review(review, include_error=False)
    assert "calc_unavailable" in with_error
    assert "calc down" in with_error
    assert "calc_unavailable" not in without_error


def test_format_turn_review_dedupes_error():
    error = CandidateDiscoveryError(
        kind="calc_unavailable",
        stage="coverage",
        message="calc down",
        retryable=True,
    )
    text = format_turn(
        {
            "pending_presentation": None,
            "team_draft": [_locked("Mon0")],
            "candidate_discovery_error": error,
            "last_team_review": TeamReviewResult(
                [], [], [], status="unavailable", error=error
            ),
        }
    )
    assert text.count("calc_unavailable") == 1
    assert "Team review:" in text


def test_complete_roster_and_review_status():
    draft = [_locked(f"Mon{i}") for i in range(6)]
    review = TeamReviewResult(
        threats=[_sample_threat()],
        coverage=[
            ThreatCoverageResult(
                {"species": "Gapmon"},
                MatchupResult("no_answer", "toss-up"),
                [],
                None,
                False,
            )
        ],
        spofs=[],
        status="available",
    )
    text = format_turn(
        {
            "pending_presentation": None,
            "team_draft": draft,
            "last_team_review": review,
        }
    )
    assert "Mon0" in text
    assert "Kingambit" not in text
    assert "Gapmon" in text
    assert "Team review status:" not in text
    assert TEAM_REVIEW_DETAIL_HINT in text


def test_format_turn_idle_review_terse():
    review = TeamReviewResult(
        threats=[_sample_threat()],
        coverage=[
            ThreatCoverageResult(
                {"species": "Gapmon"},
                MatchupResult("no_answer", "toss-up"),
                [],
                None,
                False,
            )
        ],
        spofs=[],
    )
    text = format_turn(
        {
            "pending_presentation": None,
            "team_draft": [_locked("Mon0")],
            "last_team_review": review,
        }
    )
    assert "Gapmon" in text
    assert "Threats:\n  -" not in text
    assert TEAM_REVIEW_DETAIL_HINT in text


def test_unmatched_prefix():
    text = format_turn(
        {
            "pending_presentation": {
                "kind": "bootstrap_intake",
                "prompt_text": "Start?",
            }
        },
        unmatched=True,
    )
    assert text.startswith(UNMATCHED_REPLY_PREFIX)


def test_unmatched_custom_message_replaces_prefix():
    text = format_turn(
        {
            "turn_payload": {"message": "Which field should change?"},
            "pending_presentation": {
                "kind": "full_build_confirmation",
                "slot_index": 0,
            },
        },
        unmatched=True,
    )
    assert text.startswith("Which field should change?")
    assert UNMATCHED_REPLY_PREFIX not in text


def test_team_review_roster_overlays_full_build_confirmation():
    from recommender.present_text import _FOOTERS

    draft = [_locked("Incineroar")]
    roster = format_roster({"team_draft": draft})
    provisional = ProvisionalSlot(
        schema_version=1,
        slot_index=0,
        target_role_decision=TargetRoleDecision(
            role_id="rain_setter", source="user_choice"
        ),
        species="Pelipper",
        ability="Drizzle",
        item="Damp Rock",
        moves=("Hurricane", "U-turn", "Weather Ball", "Protect"),
        nature="Modest",
        spread=(("hp", 4), ("spa", 252), ("spe", 252)),
    )
    text = format_turn(
        {
            "team_draft": draft,
            "turn_payload": {"message": roster},
            "provisional_slot": provisional,
            "pending_presentation": {
                "kind": "full_build_confirmation",
                "slot_index": 0,
                "provisional_fingerprint": "fp",
            },
        },
        unmatched=True,
    )
    footer = _FOOTERS["full_build_confirmation"]
    assert text.startswith(roster)
    assert "Incineroar" in text
    assert "Pelipper" in text
    assert "Accept this build?" in text
    assert text.count(footer) == 1
    assert UNMATCHED_REPLY_PREFIX not in text


def test_confirm_abandon_build_renders_without_fallback():
    from recommender.nodes import CONTINUE_ABANDON_MSG
    from recommender.present_text import _FOOTERS

    provisional = ProvisionalSlot(
        schema_version=1,
        slot_index=0,
        target_role_decision=TargetRoleDecision(
            role_id="rain_setter", source="user_choice"
        ),
        species="Pelipper",
        ability="Drizzle",
        item="Damp Rock",
        moves=("Hurricane", "U-turn", "Weather Ball", "Protect"),
        nature="Modest",
        spread=(("hp", 4), ("spa", 252), ("spe", 252)),
    )
    text = format_turn(
        {
            "turn_payload": {"message": CONTINUE_ABANDON_MSG},
            "provisional_slot": provisional,
            "pending_presentation": {
                "schema_version": 1,
                "kind": "confirm_abandon_build",
            },
        },
        unmatched=True,
    )
    footer = _FOOTERS["confirm_abandon_build"]
    assert text.startswith(CONTINUE_ABANDON_MSG)
    assert text.count(footer) == 1
    assert "Pending build: Pelipper." in text
    assert "(pending kind:" not in text


def test_no_parser_omits_unmatched_prefix_and_shows_fix_hint():
    text = format_turn(
        {
            "bootstrap_intake_error": BOOTSTRAP_PARSER_NOT_CONFIGURED,
            "pending_presentation": {
                "kind": "bootstrap_intake",
                "prompt_text": "Start?",
            },
        },
        unmatched=True,
    )
    assert UNMATCHED_REPLY_PREFIX not in text
    assert BOOTSTRAP_PARSER_FIX_HINT in text
    assert "Start?" in text


def test_format_roster_empty():
    assert "no locked members" in format_roster({"team_draft": []})


def test_no_pending_message_reports_discovery_error():
    error = CandidateDiscoveryError(
        kind="calc_unavailable",
        stage="coverage",
        message="calc service down",
        retryable=True,
    )
    text = format_no_pending(
        {"pending_presentation": None, "candidate_discovery_error": error}
    )
    assert "calc_unavailable" in text
    assert "won't resolve on its own" in text
    assert "check the calc service" in text
    assert NO_PENDING_MESSAGE not in text
    assert "wait for a prompt" not in text


def test_no_pending_message_idle_unchanged():
    assert (
        format_no_pending({"pending_presentation": None}) == NO_PENDING_MESSAGE
    )


def test_candidate_selection_renders_track_before_species():
    """Confirms the track label renders first, before the species name --
    explicit design requirement, not incidental formatting ('state the
    track they come from first, so the user can say "give me a different
    threat coverage"'). Surfacing only, steering itself is explicitly
    scoped out."""
    text = format_turn(
        {
            "pending_presentation": {
                "kind": "candidate_selection",
                "slot_index": 0,
                "options": [
                    {
                        "species": "Grimmsnarl",
                        "source": "need",
                        "track": "support/utility",
                        "evidence": (
                            CandidateEvidence(
                                "compendium_backed",
                                "high",
                                "resolve_need_candidates",
                                (),
                            ),
                        ),
                    }
                ],
            }
        }
    )
    assert "1. support/utility: Grimmsnarl" in text


def test_candidate_selection_omits_track_segment_when_absent():
    """Confirms the older (single/zero-locked) path, which never sets
    track, renders exactly as before -- no stray empty segment."""
    text = format_turn(
        {
            "pending_presentation": {
                "kind": "candidate_selection",
                "slot_index": 0,
                "options": [
                    {
                        "species": "Incineroar",
                        "source": "threat",
                        "evidence": (
                            CandidateEvidence(
                                "usage_backed", "high", "query_counters", ()
                            ),
                        ),
                    }
                ],
            }
        }
    )
    assert "1. Incineroar" in text
    assert "1. None: Incineroar" not in text
    assert ": Incineroar" not in text
