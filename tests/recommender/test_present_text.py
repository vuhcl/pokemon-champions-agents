"""Unit tests for plain-text turn rendering (no graph)."""

from __future__ import annotations

from recommender.present_text import (
    BOOTSTRAP_PARSER_FIX_HINT,
    BOOTSTRAP_PARSER_NOT_CONFIGURED,
    NO_PENDING_MESSAGE,
    UNMATCHED_REPLY_PREFIX,
    format_evidence_summary,
    format_no_pending,
    format_roster,
    format_turn,
)
from recommender.state import (
    Attr,
    CandidateDiscoveryError,
    CandidateEvidence,
    ProvisionalSlot,
    Slot,
    TargetRoleDecision,
    TeamReviewResult,
    UnresolvedTargetRoleDecision,
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


def test_complete_roster_and_review_status():
    draft = [_locked(f"Mon{i}") for i in range(6)]
    text = format_turn(
        {
            "pending_presentation": None,
            "team_draft": draft,
            "last_team_review": TeamReviewResult(
                threats=[], coverage=[], spofs=[], status="unavailable"
            ),
        }
    )
    assert "Mon0" in text
    assert "Team review status: unavailable" in text


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
