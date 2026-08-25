"""One-shot: split test_role_compendium_swords_dance.py by concern."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "tests" / "recommender" / "test_role_compendium_swords_dance.py"
OUT = ROOT / "tests" / "recommender"

CONSTRUCT = {
    "test_exclusive_self_boost_atk",
    "test_stat_boosts_attributes_drops_to_the_right_side",
    "test_setup_adjusted_score_composition",
    "test_setup_excellent_floor_second_times_095",
    "test_setup_mech_tier_boundaries",
    "test_setup_mech_tier_degenerate_floor_stays_good",
    "test_setup_mech_tier_acceptable_mult_override",
    "test_partition_by_admission_floor_noop_and_boundary",
    "test_sd_criteria_locks_admission_and_acceptable_mult",
    "test_acceptable_basis_distinct_from_good",
    "test_acceptable_floor_note_emitted",
    "test_cbd_move_implausible_vs_mega_helper",
    "test_cbd_inflated_vs_mega_rejects_without_showdown_base_delivery",
    "test_discounted_base_in_acceptable_band_is_rejected",
    "test_setup_does_not_discount_when_mega_lacks_setup_move",
    "test_branch_a_via_priority_sole_path",
    "test_fakeout_does_not_clear_branch_a",
    "test_fakeout_banned_from_setup_payoff",
    "test_branch_a_priority_category_must_match_boost_stat",
    "test_blaziken_mega_branch_a_excellent",
    "test_priority_boost_only_when_payoff_is_priority",
    "test_setup_ability_for_payoff_gates",
    "test_disguise_clears_branch_b_without_bulk",
    "test_disguise_turn_order_credits_when_slower",
    "test_speed_boost_turn_order_rescues_slower",
    "test_soft_cap_limits_overkill",
    "test_weak_damage_priority_not_excellent",
    "test_neither_branch_rejected",
    "test_critique_approves",
    "test_rebuild_tmp",
    "test_sd_construct_structured_payoff_mawile_shaped",
}

PAYOFF = {
    "test_best_payoff_skips_self_spa_drop",
    "test_best_payoff_skips_focus_punch_and_recharge",
    "test_best_payoff_skips_lockin_moves",
    "test_select_setup_payoff_priority_wins_when_incoming_ohko",
    "test_turn_order_fictional_ko_zeroed",
    "test_turn_order_outsped_survives",
    "test_dd_spe_stages_rescues_outspeed",
    "test_turn_order_priority_full_credit",
    "test_turn_order_spe_tie_half_credit",
    "test_turn_order_missing_spe_fail_open",
    "test_present_usage_payoff_ids_drops_sub_floor_leftovers",
    "test_present_usage_payoff_ids_keeps_high_pct_regression",
    "test_present_usage_empty_bag_select_returns_none",
    "test_per_defender_kit_pick_beats_panel_average_theft",
    "test_combined_ko_competes_per_mid_not_global_payoff",
    "test_debuff_surv_denominator_is_drop_move_winners_only",
    "test_select_setup_payoff_aegislash_combined_ko_via_matrix",
    "test_kit_matrix_calc_count_scales_with_kit_not_usage_bag",
}

COMMON_HELPERS = {
    "_mock_calc",
    "_panel_result",
    "_sd_criteria_for_mock",
    "_sd_draft",
    "_members",
}


def bucket_for_test(name: str) -> str:
    if name in CONSTRUCT:
        return "construct"
    if name in PAYOFF:
        return "payoff"
    return "damage"


def node_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.FunctionDef):
        return node.name
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name):
                return t.id
    return None


def is_skippable(node: ast.AST) -> bool:
    if isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None), ast.Constant):
        return isinstance(node.value.value, str)
    return isinstance(node, (ast.Import, ast.ImportFrom))


def main() -> None:
    text = SRC.read_text()
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)

    assignments: list[tuple[str, ast.AST]] = []
    pending: list[ast.AST] = []
    for node in tree.body:
        if is_skippable(node):
            continue
        name = node_name(node)
        if isinstance(node, ast.FunctionDef) and name and name.startswith("test_"):
            b = bucket_for_test(name)
            for p in pending:
                assignments.append((b, p))
            pending = []
            assignments.append((b, node))
        elif name in COMMON_HELPERS:
            assignments.append(("common", node))
        else:
            pending.append(node)
    for p in pending:
        assignments.append(("damage", p))

    chunks: dict[str, list[str]] = {k: [] for k in ("common", "construct", "payoff", "damage")}
    for b, node in assignments:
        chunks[b].append("".join(lines[node.lineno - 1 : node.end_lineno]))

    rel = "from role_compendium_sd_common import (\n    _members,\n    _mock_calc,\n    _panel_result,\n    _sd_criteria_for_mock,\n    _sd_draft,\n)\n"

    (OUT / "role_compendium_sd_common.py").write_text(
        '"""Swords Dance setup-attacker tests — shared helpers."""\n\n'
        "from __future__ import annotations\n\n"
        "from pathlib import Path\n"
        "from typing import Any\n\n"
        "from recommender.ids import to_id\n"
        "from recommender.legality import load_snapshot\n"
        "from recommender.role_compendium import (\n"
        "    SWORDS_DANCE_ATTACKER_CRITERIA,\n"
        "    construct_role_category,\n"
        "    legal_species_pool,\n"
        ")\n\n"
        + "\n".join(chunks["common"])
        + "\n"
    )

    (OUT / "test_role_compendium_sd_construct.py").write_text(
        '"""Swords Dance setup-attacker tests — construct pipeline / tiering."""\n\n'
        "from __future__ import annotations\n\n"
        "from pathlib import Path\n"
        "from typing import Any\n\n"
        "from recommender.ids import to_id\n"
        "from recommender.legality import load_snapshot\n"
        + rel
        + "from recommender.role_compendium_setup import (\n"
        "    _partition_by_admission_floor,\n"
        "    _setup_adjusted_score,\n"
        "    _setup_branch_a,\n"
        "    _setup_branch_a_via_priority,\n"
        "    _setup_excellent_floor,\n"
        "    _setup_mech_tier,\n"
        "    _setup_payoff_candidates,\n"
        "    _setup_priority_kind,\n"
        "    _setup_self_drop_moves,\n"
        ")\n"
        "from recommender.role_compendium_setup_constants import (\n"
        "    _SETUP_ACCEPTABLE_FLOOR_MULT,\n"
        "    _SETUP_BOTH_BRANCH_SCORE_DIV,\n"
        "    _SETUP_DAMAGE_FRAC_CAP,\n"
        "    _SETUP_SPE_FLOOR,\n"
        "    _SETUP_SPEED_ABILITIES,\n"
        "    _SETUP_SURVIVE_ABILITIES,\n"
        ")\n"
        "from recommender.stat_boosts import _self_boosts, load_stat_boosts\n"
        "from recommender.role_compendium import (\n"
        "    SWORDS_DANCE_ATTACKER_CRITERIA,\n"
        "    RejectedCandidate,\n"
        "    construct_role_category,\n"
        "    critique_role_ranking,\n"
        "    exclusive_self_boost_move,\n"
        "    legal_species_pool,\n"
        "    rebuild_role_category,\n"
        ")\n\n"
        + "\n".join(chunks["construct"])
        + "\n"
    )

    (OUT / "test_role_compendium_sd_payoff_select.py").write_text(
        '"""Swords Dance setup-attacker tests — payoff selection / turn order / usage bag."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any\n\n"
        "from recommender.ids import to_id\n"
        "from recommender.legality import load_snapshot\n"
        + rel.replace(
            "(\n    _members,\n    _mock_calc,\n    _panel_result,\n    _sd_criteria_for_mock,\n    _sd_draft,\n)",
            "(_panel_result,)",
        )
        + "\n".join(chunks["payoff"])
        + "\n"
    )

    (OUT / "test_role_compendium_sd_damage_score.py").write_text(
        '"""Swords Dance setup-attacker tests — _damage_score and calc scoring paths."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any\n\n"
        "from recommender.ids import to_id\n\n"
        + rel.replace(
            "(\n    _members,\n    _mock_calc,\n    _panel_result,\n    _sd_criteria_for_mock,\n    _sd_draft,\n)",
            "(_panel_result,)",
        )
        + "\n".join(chunks["damage"])
        + "\n"
    )

    SRC.unlink()
    print("ok", {k: len(v) for k, v in chunks.items()})


if __name__ == "__main__":
    main()
