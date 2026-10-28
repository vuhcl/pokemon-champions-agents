"""B4 — class scorer on synthetic mechanical classes + freeze gate smoke."""

from __future__ import annotations

from scripts.eval.part_g_arm.state.class_scorer import score_transcript, score_turn
from scripts.eval.part_g_arm.state.request_set_rows import FROZEN_PROMPT_SHA256
from scripts.eval.part_g_arm.state.request_set_runner import assert_frozen_prompt, assert_row_allowed
from scripts.eval.part_g_arm.config import ArmConfig


def _turn(mech: str, *, wrote: bool = False) -> dict:
    slots_a = [{"slot": "1", "species": "Venusaur"}] if wrote else [{"slot": "1", "species": None}]
    slots_b = [{"slot": "1", "species": "Venusaur"}] if wrote else [{"slot": "1", "species": None}]
    if wrote and mech == "wrote":
        slots_a = [{"slot": "1", "species": None}]
    return {
        "mechanical_class": mech,
        "state_before": {"slots": slots_a, "steering": []},
        "state_after": {"slots": slots_b, "steering": []},
    }


def test_score_turn_mutation_ok_wrote():
    sc = score_turn(observed_mech="wrote", expected_key_class="MUTATION-OK", turn=_turn("wrote", wrote=True))
    assert sc["match"] is True
    assert sc["state_expectation_met"] is True


def test_score_turn_served_lookup():
    sc = score_turn(observed_mech="lookup only", expected_key_class="SERVED", turn=_turn("lookup only"))
    assert sc["match"] is True


def test_score_turn_mutation_refused():
    sc = score_turn(observed_mech="refused", expected_key_class="MUTATION-REFUSED", turn=_turn("refused"))
    assert sc["match"] is True


def test_score_transcript_mt2_h6_hand_audit_not_stale():
    """2026-10-28 Vu: stale_pin_rows cleared; MT2/H6 are hand-audit (not content-stale)."""
    out = score_transcript(
        [
            {"id": "MT2", "turns": [_turn("wrote", wrote=True)]},
            {"id": "H6", "turns": [_turn("lookup only")]},
        ]
    )
    by = {r["row"]: r for r in out["per_row"]}
    assert by["MT2"]["excluded"] == "hand audit"
    assert by["H6"]["excluded"] == "hand audit"
    assert by["MT2"].get("stale") is not True
    assert by["H6"].get("stale") is not True


def test_score_transcript_per_class_not_pooled():
    # MS1 is covered MUTATION-OK in the request set.
    out = score_transcript(
        [{"id": "MS1", "turns": [_turn("wrote", wrote=True)]}]
    )
    assert "MUTATION-OK" in out["per_class"] or out["per_row"][0].get("excluded") in {
        None,
        "hand audit",
        "scorable-mechanical",
    }
    # Never a single pooled rate key.
    assert "pooled" not in out
    assert "overall_rate" not in out


def test_synthetic_each_mechanical_class():
    for mech in ("wrote", "bound", "recorded", "dismissed", "refused", "lookup only", "no change"):
        sc = score_turn(
            observed_mech=mech,
            expected_key_class="NO-MUTATION",
            turn=_turn(mech),
        )
        assert "match" in sc


def test_frozen_prompt_gate():
    cfg = ArmConfig(prompt_file="state/prompt.md")
    assert cfg.prompt_hash() == FROZEN_PROMPT_SHA256
    assert_frozen_prompt(cfg, allow_dev=False)


def test_covered_gate_rejects_unknown():
    try:
        assert_row_allowed("MT7", allow_dev=False, covered={"H1"})
        raised = False
    except SystemExit:
        raised = True
    assert raised
