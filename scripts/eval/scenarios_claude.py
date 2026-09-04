"""~17 Claude API validation scenarios (Task C). Parser-only; no full graph.

Ground-truth intents/payloads reuse shapes from unit tests / prompt rules.
claim_correction cases are chosen so negation_matches_claim does NOT fire.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from recommender.state import SystemClaim
from recommender.system_claims import (
    negation_matches_claim,
    serialize_last_system_claim,
)

Component = str  # turn_intent_parser | claim_correction | full_build_confirmation


@dataclass(frozen=True)
class ClaudeScenario:
    scenario_id: str
    component: Component
    doc: str
    user_text: str
    pending_kind: str = "none"
    pending_context: str = ""
    roster_summary: str = ""
    last_system_claim: str = ""
    # Ground truth for agreement (intent required; payload keys optional soft checks).
    expected_intent: str = ""
    expected_payload: dict[str, Any] = field(default_factory=dict)
    # Keys in expected_payload that must match when present on both sides.
    payload_keys: tuple[str, ...] = ()
    # If True, divergence is known deferred (ADR-031 multi-axis bare number) — report,
    # do not treat as a new bug in this PR.
    known_deferred: bool = False
    # claim used only to assert deterministic pre-pass does not fire (claim_correction).
    claim_for_deterministic_guard: SystemClaim | None = None


def _grass_claim() -> SystemClaim:
    return {
        "turn": 1,
        "kind": "type",
        "subject_species": "Heliolisk",
        "asserted_value": "Grass",
        "source": "pending_response_message",
        "display_excerpt": "Heliolisk is a Grass-type option",
        "verifiable": True,
        "originating_user_text": "I want a grass type",
    }


def _ability_claim() -> SystemClaim:
    return {
        "turn": 1,
        "kind": "ability",
        "subject_species": "Incineroar",
        "asserted_value": "Intimidate",
        "source": "pending_response_message",
        "display_excerpt": "Incineroar has Intimidate",
        "verifiable": True,
        "originating_user_text": "need intimidate",
    }


def _item_claim() -> SystemClaim:
    return {
        "turn": 1,
        "kind": "item",
        "subject_species": "Pelipper",
        "asserted_value": "Choice Specs",
        "source": "pending_response_message",
        "display_excerpt": "Pelipper holds Choice Specs",
        "verifiable": True,
        "originating_user_text": "specs pelipper",
    }


_FULL_BUILD_CTX = (
    "full build confirmation for Pelipper; options: "
    "spread_nature:default[spread_nature]=Modest 4/252/252; "
    "spread_nature:1[spread_nature]=Modest bulky; "
    "spread_nature:2[spread_nature]=Timid max Spe; "
    "moveset:1[moveset]=Hurricane / Weather Ball / Tailwind / Protect; "
    "moveset:2[moveset]=Hurricane / Weather Ball / U-turn / Protect; "
    "item:1[item]=Damp Rock; "
    "item:2[item]=Focus Sash; "
    "item:3[item]=Life Orb"
)

_MULTI_AXIS_BARE_CTX = _FULL_BUILD_CTX  # multiple axis groups → bare "1" is deferred


def build_scenarios() -> list[ClaudeScenario]:
    grass = _grass_claim()
    ability = _ability_claim()
    item = _item_claim()

    turn_intent: list[ClaudeScenario] = [
        ClaudeScenario(
            scenario_id="ti_lock",
            component="turn_intent_parser",
            doc="lock species on idle (test_parse_turn_intent_lock_payload shape)",
            user_text="lock Pelipper as the rain setter in slot 1",
            pending_kind="none",
            roster_summary="slot0 empty; slot1 empty",
            expected_intent="lock",
            expected_payload={"attr": "species", "value": "Pelipper"},
            payload_keys=("attr", "value"),
        ),
        ClaudeScenario(
            scenario_id="ti_constraint",
            component="turn_intent_parser",
            doc="hard Grass-type mechanical constraint (prompt example)",
            user_text="must be Grass type",
            pending_kind="none",
            expected_intent="constraint",
            expected_payload={
                "type": "hard",
                "mechanical_kind": "type",
                "mechanical_value": "Grass",
                "scope": "per_slot",
                "groundedness": "mechanically-checkable",
            },
            payload_keys=(
                "type",
                "mechanical_kind",
                "mechanical_value",
                "scope",
                "groundedness",
            ),
        ),
        ClaudeScenario(
            scenario_id="ti_rejection",
            component="turn_intent_parser",
            doc="species ban is rejection, not claim_correction",
            user_text="I don't want Heliolisk",
            pending_kind="none",
            expected_intent="rejection",
            expected_payload={"species": "Heliolisk"},
            payload_keys=("species",),
        ),
        ClaudeScenario(
            scenario_id="ti_archetype_change",
            component="turn_intent_parser",
            doc="strategy pivot → archetype_change (prompt: switch to trick room)",
            user_text="switch to trick room",
            pending_kind="none",
            expected_intent="archetype_change",
            expected_payload={"components": ["TrickRoom"]},
            # components labels vary (TrickRoom / trick room / TR); check intent only
            payload_keys=(),
        ),
        ClaudeScenario(
            scenario_id="ti_revise_locked_slot",
            component="turn_intent_parser",
            doc="idle field edit on locked roster slot",
            user_text="change slot 1's item to Focus Sash only",
            pending_kind="none",
            roster_summary=(
                "slot1 Pelipper locked item=Damp Rock nature=Modest"
            ),
            expected_intent="revise_locked_slot",
            expected_payload={
                "slot_index": 1,
                "field": "item",
                "value": "Focus Sash",
                "scope": "field_only",
            },
            payload_keys=("slot_index", "field", "value", "scope"),
        ),
        ClaudeScenario(
            scenario_id="ti_repick_locked_slot",
            component="turn_intent_parser",
            doc="species swap on locked slot (no field)",
            user_text="swap out Sinistcha in slot 5 for something else",
            pending_kind="none",
            roster_summary="slot5 Sinistcha locked",
            expected_intent="repick_locked_slot",
            expected_payload={"slot_index": 5},
            payload_keys=("slot_index",),
        ),
        ClaudeScenario(
            scenario_id="ti_bare_number_multiaxis",
            component="turn_intent_parser",
            doc=(
                "bare-number across multiple axis groups — known deferred "
                "(ADR-031); mock/deterministic declines; report API divergence"
            ),
            user_text="1",
            pending_kind="full_build_confirmation",
            pending_context=_MULTI_AXIS_BARE_CTX,
            # Preferred fail-closed: pending_response. select_build_option with
            # bare "1" is the known deferred LLM failure mode.
            expected_intent="pending_response",
            expected_payload={},
            payload_keys=(),
            known_deferred=True,
        ),
        ClaudeScenario(
            scenario_id="ti_ambiguous",
            component="turn_intent_parser",
            doc="under-specified → pending_response (prompt: bare no)",
            user_text="no",
            pending_kind="none",
            expected_intent="pending_response",
            expected_payload={},
            payload_keys=(),
        ),
    ]

    claim_correction: list[ClaudeScenario] = [
        ClaudeScenario(
            scenario_id="cc_thats_wrong",
            component="claim_correction",
            doc="soft dispute; negation_matches_claim must not fire",
            user_text="that's wrong",
            pending_kind="none",
            last_system_claim=serialize_last_system_claim(grass),
            expected_intent="claim_correction",
            expected_payload={},
            payload_keys=(),
            claim_for_deterministic_guard=grass,
        ),
        ClaudeScenario(
            scenario_id="cc_claim_incorrect",
            component="claim_correction",
            doc="explicit incorrect-claim phrasing without type-negation regex",
            user_text="that claim is incorrect",
            pending_kind="none",
            last_system_claim=serialize_last_system_claim(grass),
            expected_intent="claim_correction",
            expected_payload={},
            payload_keys=(),
            claim_for_deterministic_guard=grass,
        ),
        ClaudeScenario(
            scenario_id="cc_isnt_grass",
            component="claim_correction",
            doc="isn't (not 'is not') — skips TYPE_NEGATION_RES; still claim_correction",
            user_text="Heliolisk isn't a Grass type",
            pending_kind="none",
            last_system_claim=serialize_last_system_claim(grass),
            expected_intent="claim_correction",
            expected_payload={
                "disputed_kind": "type",
                "disputed_value": "Grass",
                "subject_species": "Heliolisk",
            },
            payload_keys=("disputed_kind", "disputed_value", "subject_species"),
            claim_for_deterministic_guard=grass,
        ),
        ClaudeScenario(
            scenario_id="cc_ability_soft",
            component="claim_correction",
            doc="ability dispute without negation_matches_claim trigger phrasing",
            user_text="you got Incineroar's ability wrong",
            pending_kind="none",
            last_system_claim=serialize_last_system_claim(ability),
            expected_intent="claim_correction",
            expected_payload={
                "disputed_kind": "ability",
                "subject_species": "Incineroar",
            },
            payload_keys=("disputed_kind", "subject_species"),
            claim_for_deterministic_guard=ability,
        ),
    ]

    # Keep unused item claim reachable for future expansion / self-check variety.
    _ = item

    full_build: list[ClaudeScenario] = [
        ClaudeScenario(
            scenario_id="fbc_spread_nature",
            component="full_build_confirmation",
            doc="pick spread_nature:1",
            user_text="spread_nature:1",
            pending_kind="full_build_confirmation",
            pending_context=_FULL_BUILD_CTX,
            expected_intent="select_build_option",
            expected_payload={"option_ids": ("spread_nature:1",)},
            payload_keys=("option_ids",),
        ),
        ClaudeScenario(
            scenario_id="fbc_moveset",
            component="full_build_confirmation",
            doc="pick moveset:2",
            user_text="moveset:2",
            pending_kind="full_build_confirmation",
            pending_context=_FULL_BUILD_CTX,
            expected_intent="select_build_option",
            expected_payload={"option_ids": ("moveset:2",)},
            payload_keys=("option_ids",),
        ),
        ClaudeScenario(
            scenario_id="fbc_item",
            component="full_build_confirmation",
            doc="pick item:2 (Focus Sash)",
            user_text="item:2",
            pending_kind="full_build_confirmation",
            pending_context=_FULL_BUILD_CTX,
            expected_intent="select_build_option",
            expected_payload={"option_ids": ("item:2",)},
            payload_keys=("option_ids",),
        ),
        ClaudeScenario(
            scenario_id="fbc_bundled_axes",
            component="full_build_confirmation",
            doc="compose independent axes in one turn",
            user_text="spread_nature:1 and item:1",
            pending_kind="full_build_confirmation",
            pending_context=_FULL_BUILD_CTX,
            expected_intent="select_build_option",
            expected_payload={
                "option_ids": ("spread_nature:1", "item:1"),
            },
            payload_keys=("option_ids",),
        ),
        ClaudeScenario(
            scenario_id="fbc_compare",
            component="full_build_confirmation",
            doc="compare two item options before deciding",
            user_text="compare item:1 and item:2",
            pending_kind="full_build_confirmation",
            pending_context=_FULL_BUILD_CTX,
            expected_intent="compare",
            expected_payload={"option_ids": ("item:1", "item:2")},
            payload_keys=("option_ids",),
        ),
    ]

    scenarios = turn_intent + claim_correction + full_build
    assert len(scenarios) == 17, len(scenarios)

    for sc in scenarios:
        if sc.claim_for_deterministic_guard is not None:
            assert not negation_matches_claim(
                sc.user_text, sc.claim_for_deterministic_guard
            ), f"{sc.scenario_id}: deterministic pre-pass would fire"

    return scenarios
