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


# --- #195 after-run reproductions (phrasing gaps + multi-claim) ---


def test_rewrite_slash_without_type_word_sinistcha():
    msg = (
        "Each option's typing is as follows: Sinistcha is Dark/Fairy, "
        "Clefable is Fairy, and Ariados is Bug/Poison."
    )
    out = rewrite_pending_response_message(msg)
    assert "Sinistcha is Grass/Ghost" in out
    assert "Dark/Fairy" not in out
    assert "Clefable is Fairy" in out
    assert "Ariados is Bug/Poison" in out


def test_rewrite_bare_is_type_without_type_word_heliolisk():
    msg = (
        "Each option's typing is as follows: Heliolisk is Grass, "
        "Abomasnow is Ice, and Whimsicott is Fairy."
    )
    out = rewrite_pending_response_message(msg)
    assert "Heliolisk is Electric/Normal" in out
    assert "Heliolisk is Grass" not in out
    assert "Abomasnow is Ice" in out
    assert "Whimsicott is Fairy" in out


def test_rewrite_dash_list_false_with_true_parenthetical_sibling():
    """#195 qwen3.5-style: must not no-op on parenthetical Electric/Normal type."""
    msg = (
        "1. Heliolisk - Electric/Grass (matches your Electric/Normal type request)\n"
        "2. Abomasnow - Ice/Grass type"
    )
    out = rewrite_pending_response_message(msg)
    assert "Heliolisk - Electric/Normal" in out
    assert "Electric/Grass" not in out
    assert "Abomasnow - Ice/Grass type" in out


def test_rewrite_skip_neither_separator():
    msg = "Heliolisk - option 1"
    assert rewrite_pending_response_message(msg) == msg


def test_rewrite_separator_true_unchanged():
    msg = "Heliolisk - Electric/Normal type"
    assert rewrite_pending_response_message(msg) == msg


def test_rewrite_separator_false_ariados():
    msg = "Ariados - Fire/Water"
    out = rewrite_pending_response_message(msg)
    assert "Bug/Poison" in out
    assert "Fire/Water" not in out


def test_rewrite_parenthetical_false_corviknight():
    msg = "Corviknight (Fire/Water)"
    out = rewrite_pending_response_message(msg)
    assert "Flying/Steel" in out
    assert "Fire/Water" not in out


def test_rewrite_parenthetical_true_unchanged():
    msg = "Corviknight (Flying/Steel)"
    assert rewrite_pending_response_message(msg) == msg


def test_rewrite_possessive_false():
    msg = "Ariados's typing is Fire"
    out = rewrite_pending_response_message(msg)
    assert "Bug/Poison" in out
    assert "typing is Fire" not in out


def test_rewrite_possessive_true_unchanged():
    msg = "Heliolisk's typing is Electric/Normal"
    assert rewrite_pending_response_message(msg) == msg


def test_rewrite_inverse_false():
    msg = "a Fire-type Ariados would help"
    out = rewrite_pending_response_message(msg)
    assert "Bug/Poison type" in out
    assert "Fire-type Ariados" not in out


def test_rewrite_inverse_true_unchanged():
    msg = "an Electric-type Heliolisk"
    assert rewrite_pending_response_message(msg) == msg


def test_rewrite_ability_separator_dry_skin():
    msg = "Heliolisk - Intimidate"
    out = rewrite_pending_response_message(msg)
    # Heliolisk abilities are Dry Skin / Sand Veil / Solar Power — not Intimidate
    assert "Intimidate" not in out
    assert "Dry Skin" in out or "Sand Veil" in out or "Solar Power" in out


def test_negation_slash_without_type_unchanged():
    msg = "Sinistcha is not Dark/Fairy"
    assert rewrite_pending_response_message(msg) == msg


def test_negation_bare_is_unchanged():
    msg = "Heliolisk is not Grass"
    assert rewrite_pending_response_message(msg) == msg


def test_negation_separator_unchanged():
    msg = "Heliolisk is not Electric/Grass type"
    assert rewrite_pending_response_message(msg) == msg


def test_negation_possessive_unchanged():
    msg = "Ariados is not a Fire type"
    assert rewrite_pending_response_message(msg) == msg


def test_negation_inverse_unchanged():
    msg = "not a Fire-type Ariados"
    assert rewrite_pending_response_message(msg) == msg


def test_stamp_still_single_claim_first_hit():
    from recommender.system_claims import stamp_system_claim, try_parse_verifiable_claim_from_message

    msg = (
        "Sinistcha is Grass/Ghost, Clefable is Fairy, and Ariados is Bug/Poison."
    )
    parsed = try_parse_verifiable_claim_from_message(msg)
    assert parsed is not None
    assert parsed["subject_species"] == "Sinistcha"
    stamped = stamp_system_claim(
        message=msg, originating_user_text="typing?", turn=1
    )
    assert stamped is not None
    assert stamped["subject_species"] == "Sinistcha"
