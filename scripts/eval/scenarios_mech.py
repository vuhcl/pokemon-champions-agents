"""Extra mech-claim scenarios: compare turns + charge/recharge structural."""

from __future__ import annotations

from typing import Any

from recommender.matchup import MatchupResult, clear_matchup_memo, classify_matchup
from recommender.state import (
    BuildConfirmationOption,
    BuildOptionGroup,
    PendingSlotIntent,
    ProvisionalSlot,
    TargetRoleDecision,
    ThreatCoverageResult,
    empty_slot,
)
from scripts.eval.harness import ScenarioResult, seed_state, turn

SPREAD = (
    ("hp", 4),
    ("atk", 0),
    ("def", 0),
    ("spa", 32),
    ("spd", 0),
    ("spe", 30),
)


def _provisional_gholdengo(*, item: str = "Life Orb") -> ProvisionalSlot:
    return ProvisionalSlot(
        schema_version=1,
        slot_index=0,
        target_role_decision=TargetRoleDecision(
            role_id="fast_special_attacker", source="other"
        ),
        species="Gholdengo",
        ability="Good as Gold",
        item=item,
        moves=("Make It Rain", "Shadow Ball", "Protect", "Nasty Plot"),
        nature="Timid",
        spread=SPREAD,
        fingerprint="eval-compare-fp",
        base_slot_fingerprint="eval-base-fp",
    )


def _groups() -> tuple[BuildOptionGroup, ...]:
    opts = (
        BuildConfirmationOption(
            option_id="spread_nature:default",
            label="Default",
            axis="spread_nature",
            provenance="featured",
            overrides={},
            diff_summary="recommended default",
            tradeoff="keep",
        ),
        BuildConfirmationOption(
            option_id="spread_nature:1",
            label="Bulk",
            axis="spread_nature",
            provenance="usage_spread",
            overrides={
                "nature": "Modest",
                "spread": {
                    "hp": 32,
                    "atk": 0,
                    "def": 0,
                    "spa": 32,
                    "spd": 2,
                    "spe": 0,
                },
            },
            diff_summary="spread",
            tradeoff="more HP",
        ),
        BuildConfirmationOption(
            option_id="item:1",
            label="Life Orb",
            axis="item",
            provenance="featured",
            overrides={"item": "Life Orb"},
            diff_summary="item",
            tradeoff="more damage",
        ),
        BuildConfirmationOption(
            option_id="item:2",
            label="Choice Scarf",
            axis="item",
            provenance="featured",
            overrides={"item": "Choice Scarf"},
            diff_summary="item",
            tradeoff="more Spe",
        ),
    )
    return (
        BuildOptionGroup(axis="spread_nature", prompt="spread", options=opts[:2]),
        BuildOptionGroup(axis="item", prompt="item", options=opts[2:]),
    )


def _coverage_row(species: str, moves: list[str]) -> ThreatCoverageResult:
    return ThreatCoverageResult(
        threat={"species": species, "moves": moves},
        best_outcome=MatchupResult(outcome="no_answer", severity="toss-up"),
        covering_slot_indices=[],
        forced_field=None,
        flagged=False,
    )


def _run_compare(
    scenario_id: str,
    option_ids: tuple[str, ...],
) -> Any:
    def run(graph, config, state) -> ScenarioResult:
        provisional = _provisional_gholdengo()
        groups = _groups()
        intent = PendingSlotIntent(
            schema_version=1,
            slot_index=0,
            species=provisional.species,
            target_role_decision=provisional.target_role_decision,
            source="need",
            base_slot_fingerprint=provisional.base_slot_fingerprint,
        )
        pending = {
            "schema_version": 1,
            "kind": "full_build_confirmation",
            "slot_index": 0,
            "provisional_fingerprint": provisional.fingerprint,
            "build_option_groups": groups,
        }
        draft = [empty_slot() for _ in range(6)]
        seed_state(
            graph,
            config,
            team_draft=draft,
            bootstrap_intake_complete=True,
            provisional_slot=provisional,
            pending_slot_intent=intent,
            pending_presentation=pending,
            coverage=[
                _coverage_row("Incineroar", ["Knock Off", "Flare Blitz", "Fake Out"]),
                _coverage_row("Rillaboom", ["Grassy Glide", "Wood Hammer", "U-turn"]),
            ],
        )
        state = turn(
            graph,
            config,
            {
                "turn_intent": "compare",
                "turn_payload": {"option_ids": list(option_ids)},
            },
        )
        analysis = state.get("compare_analysis") or ""
        return ScenarioResult(
            scenario_id=scenario_id,
            path="compare",
            terminal="compare_done" if analysis else "compare_empty",
            pairs=[],
            state=state,
            compare_analysis=str(analysis),
        )

    return run


def run_charge_recharge_structural() -> dict[str, Any]:
    """Direct classify_matchup — not a graph scenario."""
    clear_matchup_memo()
    foe = {
        "species": "Incineroar",
        "ability": "Intimidate",
        "item": "Sitrus Berry",
        "nature": "Careful",
        "evs": {"hp": 32, "atk": 0, "def": 0, "spa": 0, "spd": 32, "spe": 2},
        "moves": ["Knock Off", "Flare Blitz", "Fake Out", "Parting Shot"],
    }
    # Only Solar Beam as damaging move so it is a_best → charge_delayed.
    solar = {
        "species": "Venusaur",
        "ability": "Overgrow",
        "item": "Life Orb",
        "nature": "Modest",
        "evs": {"hp": 4, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 30},
        "moves": ["Solar Beam", "Protect", "Sleep Powder", "Leech Seed"],
    }
    r1 = classify_matchup(solar, foe, None)
    clear_matchup_memo()
    # Only Hyper Beam as damaging move → recharge_vulnerable_*.
    hyper = {
        "species": "Gyarados",
        "ability": "Intimidate",
        "item": "Life Orb",
        "nature": "Adamant",
        "evs": {"hp": 4, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 30},
        "moves": ["Hyper Beam", "Protect", "Splash", "Tail Whip"],
    }
    r2 = classify_matchup(hyper, foe, None)
    notes = {
        "solar_beam_note": r1.turn_economy_note,
        "solar_beam_outcome": r1.outcome,
        "hyper_beam_note": r2.turn_economy_note,
        "hyper_beam_outcome": r2.outcome,
    }
    populated = [
        n
        for n in (r1.turn_economy_note, r2.turn_economy_note)
        if n is not None
    ]
    notes["populated"] = populated
    notes["ok"] = len(populated) >= 1
    return notes


COMPARE_SCENARIOS = [
    ("compare_spread", ("spread_nature:default", "spread_nature:1")),
    ("compare_item_scarf", ("item:1", "item:2")),
]
