"""Provisional edit revise + apply_provisional_edit handler."""

from __future__ import annotations

from recommender.nodes import apply_provisional_edit
from recommender.slot_fill import revise_provisional_slot
from recommender.state import (
    PendingSlotIntent,
    ProvisionalSlot,
    TargetRoleDecision,
    empty_slot,
)


def _decision(role_id: str = "fast_special_attacker") -> TargetRoleDecision:
    return TargetRoleDecision(role_id=role_id, source="other")


def _provisional(
    *,
    nature: str = "Timid",
    item: str = "Life Orb",
    fingerprint: str = "fp-old",
) -> ProvisionalSlot:
    decision = _decision()
    return ProvisionalSlot(
        schema_version=1,
        slot_index=0,
        target_role_decision=decision,
        species="Gholdengo",
        ability="Good as Gold",
        item=item,
        moves=("Make It Rain", "Shadow Ball", "Protect", "Nasty Plot"),
        nature=nature,
        spread=(
            ("hp", 4),
            ("atk", 0),
            ("def", 0),
            ("spa", 32),
            ("spd", 0),
            ("spe", 30),
        ),
        base_slot_fingerprint="base",
        fingerprint=fingerprint,
    )


def _intent(provisional: ProvisionalSlot) -> PendingSlotIntent:
    return PendingSlotIntent(
        schema_version=1,
        slot_index=provisional.slot_index,
        species=provisional.species,
        target_role_decision=provisional.target_role_decision,
        source="threat",
        base_slot_fingerprint=provisional.base_slot_fingerprint,
    )


def test_revise_field_only_nature_leaves_other_fields():
    current = _provisional()
    result = revise_provisional_slot(
        current,
        field="nature",
        value="Modest",
        scope="field_only",
        intent=_intent(current),
        state={"regulation_mod": "champions", "team_draft": [empty_slot() for _ in range(6)]},
    )
    assert isinstance(result, ProvisionalSlot)
    assert result.nature == "Modest"
    assert result.item == current.item
    assert result.moves == current.moves
    assert result.spread_dict() == current.spread_dict()
    assert result.fingerprint != current.fingerprint


def test_apply_provisional_edit_success_replaces_fingerprint():
    current = _provisional()
    draft = [empty_slot() for _ in range(6)]
    state = {
        "pending_slot_intent": _intent(current),
        "provisional_slot": current,
        "turn_payload": {
            "field": "nature",
            "value": "Modest",
            "scope": "field_only",
        },
        "team_draft": draft,
        "regulation_mod": "champions",
        "constraints": [],
    }
    out = apply_provisional_edit(state)  # type: ignore[arg-type]
    assert out.get("slot_commit_error") is None
    assert isinstance(out["provisional_slot"], ProvisionalSlot)
    assert out["provisional_slot"].nature == "Modest"
    assert out["provisional_slot"].fingerprint != current.fingerprint
    assert out["pending_presentation"]["kind"] == "full_build_confirmation"
    assert out["pending_presentation"]["provisional_fingerprint"] == (
        out["provisional_slot"].fingerprint
    )
    assert out["pending_slot_intent"] is state["pending_slot_intent"]


def test_apply_provisional_edit_illegal_item_keeps_old():
    current = _provisional()
    state = {
        "pending_slot_intent": _intent(current),
        "provisional_slot": current,
        "turn_payload": {
            "field": "item",
            "value": "NotARealItemXYZ",
            "scope": "field_only",
        },
        "team_draft": [empty_slot() for _ in range(6)],
        "regulation_mod": "champions",
        "constraints": [],
    }
    out = apply_provisional_edit(state)  # type: ignore[arg-type]
    assert out.get("slot_commit_error")
    assert "provisional_slot" not in out
    assert "illegal" in str(out["slot_commit_error"]).casefold() or "edit" in str(
        out["slot_commit_error"]
    ).casefold()


def _pelipper_provisional() -> ProvisionalSlot:
    decision = TargetRoleDecision(role_id="rain_setter", source="other")
    return ProvisionalSlot(
        schema_version=1,
        slot_index=0,
        target_role_decision=decision,
        species="Pelipper",
        ability="Drizzle",
        item="Damp Rock",
        moves=("Hurricane", "Weather Ball", "Tailwind", "Protect"),
        nature="Modest",
        spread=(
            ("hp", 2),
            ("atk", 0),
            ("def", 0),
            ("spa", 32),
            ("spd", 0),
            ("spe", 32),
        ),
        base_slot_fingerprint="base",
        fingerprint="fp-peli",
    )


def test_revise_swap_protect_for_soak_from_partial_value():
    current = _pelipper_provisional()
    result = revise_provisional_slot(
        current,
        field="moves",
        value=["Soak"],
        scope="field_only",
        intent=_intent(current),
        state={
            "regulation_mod": "champions",
            "team_draft": [empty_slot() for _ in range(6)],
            "last_user_text": "swap protect for soak",
        },
    )
    assert isinstance(result, ProvisionalSlot)
    assert [m.casefold() for m in result.moves] == [
        "hurricane",
        "weather ball",
        "tailwind",
        "soak",
    ]


def test_revise_swap_two_name_value_without_user_text():
    current = _pelipper_provisional()
    result = revise_provisional_slot(
        current,
        field="moves",
        value=["Protect", "Soak"],
        scope="field_only",
        intent=_intent(current),
        state={
            "regulation_mod": "champions",
            "team_draft": [empty_slot() for _ in range(6)],
        },
    )
    assert isinstance(result, ProvisionalSlot)
    assert "Soak" in result.moves
    assert "Protect" not in result.moves


def test_apply_provisional_edit_move_swap_fail_message():
    from recommender.state import UnresolvedSlotRefinement

    current = _pelipper_provisional()
    state = {
        "pending_slot_intent": _intent(current),
        "provisional_slot": current,
        "turn_payload": {
            "field": "moves",
            "value": ["Hurricane", "Weather Ball"],
            "scope": "field_only",
        },
        "team_draft": [empty_slot() for _ in range(6)],
        "regulation_mod": "champions",
        "constraints": [],
        "last_user_text": "swap hurricane and weather ball",
    }
    out = apply_provisional_edit(state)  # type: ignore[arg-type]
    assert out.get("slot_commit_error")
    assert "could not apply move swap" in str(out["slot_commit_error"]).casefold()
    assert not isinstance(out.get("provisional_slot"), UnresolvedSlotRefinement)