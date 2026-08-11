"""Unit tests for plain-text turn rendering (no graph)."""

from __future__ import annotations

from recommender.present_text import (
    BOOTSTRAP_PARSER_FIX_HINT,
    BOOTSTRAP_PARSER_NOT_CONFIGURED,
    UNMATCHED_REPLY_PREFIX,
    format_evidence_summary,
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
    assert "rain_setter" in text


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
