"""apply_provisional_overrides + select overlap reject."""

from __future__ import annotations

from recommender.nodes import (
    _deterministic_build_option_ids,
    apply_provisional_option,
    classify_pending,
)
from recommender.slot_fill import apply_provisional_overrides
from recommender.state import (
    Attr,
    PendingPresentation,
    PendingSlotIntent,
    ProvisionalSlot,
    TargetRoleDecision,
    empty_slot,
)


def _decision() -> TargetRoleDecision:
    return TargetRoleDecision(role_id="fast_special_attacker", source="other")


def _provisional() -> ProvisionalSlot:
    return ProvisionalSlot(
        schema_version=1,
        slot_index=0,
        target_role_decision=_decision(),
        species="Gholdengo",
        ability="Good as Gold",
        item="Life Orb",
        moves=("Make It Rain", "Shadow Ball", "Protect", "Nasty Plot"),
        nature="Timid",
        spread=(
            ("hp", 4),
            ("atk", 0),
            ("def", 0),
            ("spa", 32),
            ("spd", 0),
            ("spe", 30),
        ),
        fingerprint="fp-old",
    )


def _intent() -> PendingSlotIntent:
    return PendingSlotIntent(
        schema_version=1,
        slot_index=0,
        species="Gholdengo",
        target_role_decision=_decision(),
        source="threat",
    )


def _state(provisional=None, pending=None, payload=None):
    return {
        "team_draft": [empty_slot()],
        "regulation_mod": "champions",
        "pending_slot_intent": _intent(),
        "provisional_slot": provisional or _provisional(),
        "pending_presentation": pending,
        "turn_payload": payload,
    }


def test_apply_provisional_overrides_multi_field():
    result = apply_provisional_overrides(
        _provisional(),
        overrides={"nature": "Modest", "item": "Choice Specs"},
        intent=_intent(),
        state=_state(),
    )
    assert isinstance(result, ProvisionalSlot)
    assert result.nature == "Modest"
    assert result.item == "Choice Specs"
    assert result.moves[0] == "Make It Rain"


def test_select_overlapping_override_keys_rejected():
    pending: PendingPresentation = {
        "schema_version": 1,
        "kind": "full_build_confirmation",
        "slot_index": 0,
        "provisional_fingerprint": "fp-old",
        "build_option_groups": (
            {
                "axis": "item",
                "prompt": "item",
                "options": (
                    {
                        "option_id": "item:1",
                        "label": "Sash",
                        "axis": "item",
                        "provenance": "usage_spread",
                        "overrides": {"item": "Focus Sash"},
                        "diff_summary": "item",
                        "tradeoff": "glass",
                    },
                ),
            },
            {
                "axis": "bundled",
                "prompt": "kit",
                "options": (
                    {
                        "option_id": "bundled:1",
                        "label": "Sitrus kit",
                        "axis": "bundled",
                        "provenance": "vgcpastes",
                        "overrides": {"item": "Sitrus Berry", "nature": "Bold"},
                        "diff_summary": "item, nature",
                        "tradeoff": "bulk",
                    },
                ),
            },
        ),
        "default_option_ids": (),
    }
    before = _provisional()
    out = apply_provisional_option(
        _state(
            provisional=before,
            pending=pending,
            payload={"option_ids": ("item:1", "bundled:1")},
        )
    )
    assert "overlapping override key" in str(out.get("slot_commit_error") or "")
    assert out.get("provisional_slot") is None or out.get("provisional_slot") is before


def test_deterministic_compose_across_axes():
    pending: PendingPresentation = {
        "schema_version": 1,
        "kind": "full_build_confirmation",
        "build_option_groups": (
            {
                "axis": "spread_nature",
                "prompt": "spread",
                "options": (
                    {
                        "option_id": "spread_nature:1",
                        "label": "Bulky",
                        "axis": "spread_nature",
                        "provenance": "usage_spread",
                        "overrides": {"nature": "Bold"},
                        "diff_summary": "nature",
                        "tradeoff": "bulk",
                    },
                ),
            },
            {
                "axis": "moveset",
                "prompt": "moves",
                "options": (
                    {
                        "option_id": "moveset:1",
                        "label": "Darkest Lariat",
                        "axis": "moveset",
                        "provenance": "usage_spread",
                        "overrides": {
                            "moves": (
                                "Fake Out",
                                "Parting Shot",
                                "Flare Blitz",
                                "Darkest Lariat",
                            )
                        },
                        "diff_summary": "moves",
                        "tradeoff": "coverage",
                    },
                ),
            },
        ),
    }
    ids = _deterministic_build_option_ids(
        "spread_nature:1 + moveset:1", pending
    )
    assert ids == ("spread_nature:1", "moveset:1")


def test_classify_pending_select_build_option():
    pending: PendingPresentation = {
        "schema_version": 1,
        "kind": "full_build_confirmation",
        "slot_index": 0,
        "provisional_fingerprint": "fp",
        "build_option_groups": (
            {
                "axis": "spread_nature",
                "prompt": "spread",
                "options": (
                    {
                        "option_id": "spread_nature:1",
                        "label": "Bulky Modest",
                        "axis": "spread_nature",
                        "provenance": "usage_spread",
                        "overrides": {"nature": "Modest"},
                        "diff_summary": "nature",
                        "tradeoff": "bulk",
                    },
                ),
            },
        ),
    }
    result = classify_pending("spread_nature:1", pending)
    assert result["turn_intent"] == "select_build_option"
    assert result["turn_payload"]["option_ids"] == ("spread_nature:1",)
