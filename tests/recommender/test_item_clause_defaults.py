"""Tier-1 default item selection respects Item Clause on team_draft."""

from __future__ import annotations

from unittest.mock import patch

from recommender.anchor_roles import resolve_anchor_build
from recommender.ids import to_id
from recommender.legality import check_set
from recommender.nodes import commit_full_slot
from recommender.propose import fill_team_draft
from recommender.slot_fill import build_provisional_slot
from recommender.state import (
    Attr,
    PendingSlotIntent,
    ProvisionalSlot,
    RecommenderState,
    Slot,
    TargetRoleDecision,
    empty_slot,
    slot_fingerprint,
)
from recommender.usage_data import featured_or_common_set


def _base_state(**overrides) -> RecommenderState:
    state: RecommenderState = {
        "format_id": "[Gen 9 Champions] VGC 2026 Reg M-B",
        "game_type": "doubles",
        "regulation_mod": "champions",
        "picked_team_size": 4,
        "available_pool": [],
        "team_draft": [empty_slot() for _ in range(6)],
        "archetype": Attr(),
        "rejected": [],
        "constraints": [],
        "messages": [],
        "turn": 1,
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


def _redirection_decision() -> TargetRoleDecision:
    return TargetRoleDecision(role_id="redirection", source="other")


def test_sinistcha_sitrus_locked_ariados_walks_to_focus_sash():
    """Live-transcript: tier-1 walks usage-ranked items when #1 collides."""
    sinistcha = Slot(
        species=Attr(value="Sinistcha", locked=True),
        item=Attr(value="Sitrus Berry", locked=True),
    )
    draft = [sinistcha, empty_slot(), *[empty_slot() for _ in range(4)]]
    state = _base_state(team_draft=draft)
    intent = PendingSlotIntent(
        schema_version=1,
        slot_index=1,
        species="Ariados",
        source="need",
        target_role_decision=_redirection_decision(),
        base_slot_fingerprint=slot_fingerprint(draft[1]),
    )
    provisional = build_provisional_slot(intent, state)
    assert isinstance(provisional, ProvisionalSlot)
    assert provisional.item == "Focus Sash"
    assert to_id(provisional.item) != "sitrusberry"
    legal = check_set(
        provisional.species,
        list(provisional.moves),
        provisional.item,
        ability=provisional.ability,
        team_draft=draft,
        exclude_slot=1,
    )
    assert legal.ok


def test_no_collision_sinistcha_keeps_kasib_berry():
    slot = Slot(
        species=Attr(value="Sinistcha", locked=True),
        role=Attr(value="redirection"),
    )
    filler = Slot(role=Attr(value="bulky_attacker"))
    state = _base_state(team_draft=[slot, filler, *[empty_slot() for _ in range(4)]])
    out = fill_team_draft(state)
    s = out["team_draft"][0]
    assert s.item.value == "Kasib Berry"
    assert s.item.reason is not None
    assert s.item.reason.ref != "tier3_item_default"


def test_usage_exhausted_falls_through_to_tier3_default():
    slot = Slot(
        species=Attr(value="Ariados", locked=True),
        role=Attr(value="redirection", locked=True),
    )
    sinistcha = Slot(
        species=Attr(value="Sinistcha", locked=True),
        item=Attr(value="Sitrus Berry", locked=True),
    )
    state = _base_state(
        team_draft=[sinistcha, slot, *[empty_slot() for _ in range(4)]]
    )
    with patch("recommender.usage_data.pick_team_aware_usage_item", return_value=None):
        out = fill_team_draft(state)
    s = out["team_draft"][1]
    assert s.item.value in {"Life Orb", "Focus Sash"}
    assert s.item.reason is not None
    assert s.item.reason.ref == "tier3_item_default"


def test_fill_team_draft_draft_sync_sees_sibling_provisional_item():
    """Slot 1 avoids Sitrus when slot 0 got provisional Sitrus in the same pass."""
    slot0 = Slot(species=Attr(value="Ariados", locked=True), role=Attr(value="redirection"))
    slot1 = Slot(species=Attr(value="Ariados", locked=True), role=Attr(value="redirection"))
    state = _base_state(team_draft=[slot0, slot1, *[empty_slot() for _ in range(4)]])
    out = fill_team_draft(state)
    assert out["team_draft"][0].item.value == "Sitrus Berry"
    assert out["team_draft"][1].item.value == "Focus Sash"


def test_commit_full_slot_passes_after_item_clause_avoidance():
    sinistcha = Slot(
        species=Attr(value="Sinistcha", locked=True),
        item=Attr(value="Sitrus Berry", locked=True),
    )
    draft = [sinistcha, empty_slot(), *[empty_slot() for _ in range(4)]]
    state = _base_state(team_draft=draft)
    intent = PendingSlotIntent(
        schema_version=1,
        slot_index=1,
        species="Ariados",
        source="need",
        target_role_decision=_redirection_decision(),
        base_slot_fingerprint=slot_fingerprint(draft[1]),
    )
    provisional = build_provisional_slot(intent, state)
    assert isinstance(provisional, ProvisionalSlot)
    committed = commit_full_slot(
        {
            **state,
            "team_draft": draft,
            "pending_slot_intent": intent,
            "provisional_slot": provisional,
            "pending_presentation": {
                "schema_version": 1,
                "kind": "full_build_confirmation",
                "slot_index": 1,
                "provisional_fingerprint": provisional.fingerprint,
            },
        }
    )
    assert committed.get("slot_commit_error") is None


def test_resolve_anchor_build_opt_in_avoids_collision_default_off_unchanged():
    sinistcha = Slot(
        species=Attr(value="Sinistcha", locked=True),
        item=Attr(value="Sitrus Berry", locked=True),
    )
    draft = [sinistcha, empty_slot(), *[empty_slot() for _ in range(4)]]
    blind = resolve_anchor_build("Ariados", regulation="champions")
    assert blind.item == featured_or_common_set("Ariados", regulation="champions")["item"]
    aware = resolve_anchor_build(
        "Ariados",
        regulation="champions",
        team_draft=draft,
        exclude_slot=1,
    )
    assert aware.item == "Focus Sash"
