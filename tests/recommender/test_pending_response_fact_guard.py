"""Runtime guard: rewrite false parseable type/ability claims in pending_response."""

from __future__ import annotations

from recommender.state import SystemClaim
from recommender.system_claims import (
    claim_is_true_against_snapshot,
    rewrite_pending_response_message,
)
from recommender.turn_intent import TurnIntentExtraction, _payload_for


_HELIOLISK_FALSE = (
    "Heliolisk is Electric/Water type, not Grass type. "
    "Would you like me to filter for grass-type Pokémon from the candidates?"
)


def test_rewrite_heliolisk_false_dual_type():
    out = rewrite_pending_response_message(_HELIOLISK_FALSE)
    assert "Electric/Normal" in out
    assert "Electric/Water" not in out
    assert "filter for grass-type" in out


def test_rewrite_true_type_unchanged():
    msg = "Heliolisk is Electric type. Which candidate?"
    assert rewrite_pending_response_message(msg) == msg


def test_rewrite_unparseable_unchanged():
    msg = "Which candidate fits that role best?"
    assert rewrite_pending_response_message(msg) == msg


def test_rewrite_false_item_left_unchanged():
    # Ability Shield is in the Champions item table but nonstandard → claim false;
    # policy leaves item claims alone (no species-canonical item in snapshot).
    msg = "Pelipper's item is Ability Shield"
    assert claim_is_true_against_snapshot(
        {
            "turn": 0,
            "kind": "item",
            "subject_species": "Pelipper",
            "asserted_value": "Ability Shield",
            "source": "pending_response_message",
            "display_excerpt": msg,
            "verifiable": True,
            "originating_user_text": "",
        }
    ) is False
    assert rewrite_pending_response_message(msg) == msg


def test_payload_for_pending_response_rewrites():
    extraction = TurnIntentExtraction(
        turn_intent="pending_response",
        message=_HELIOLISK_FALSE,
    )
    payload = _payload_for(extraction)
    assert payload is not None
    assert "Electric/Normal" in payload["message"]
    assert "Electric/Water" not in payload["message"]
    assert "filter for grass-type" in payload["message"]


def test_claim_correction_still_confirms_true_stamped_claim():
    """Second line of defense: dispute of a true claim still yields snapshot confirms."""
    from recommender.nodes import handle_claim_correction

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
    out = handle_claim_correction(
        {
            "format_id": "[Gen 9 Champions] VGC 2026 Reg M-B",
            "team_draft": [],
            "constraints": [],
            "rejected": [],
            "last_system_claim": claim,
            "turn_payload": {
                "subject_species": "Heliolisk",
                "disputed_kind": "type",
                "disputed_value": "Electric",
                "user_text": "Heliolisk is not electric type",
            },
        }
    )
    assert not out.get("claim_correction_rerun_discovery")
    assert "confirms" in (out["correction_response"] or "").lower()
