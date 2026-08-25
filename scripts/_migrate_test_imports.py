"""One-shot: point compendium construct tests at canonical modules."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests" / "recommender"

SETUP = {
    "_AEGISLASH_FORMES", "_KO_BIN_RANK", "_ally_damage_risk_note", "_attach_top1_partners",
    "_attacker_kit", "_best_payoff_move", "_calc_pokemon_spec", "_calc_species_name",
    "_candidate_defender_spec", "_common_move_names", "_crossing_k", "_damage_score",
    "_drop_setup_choice_item", "_hit_frac_from_result", "_incoming_ohko_by_defender",
    "_is_bulk_crossing", "_is_spread_damage_mid", "_kit_damaging_mids", "_ko_frac_bin",
    "_move_override_extra", "_pair_entry_label", "_partition_by_admission_floor",
    "_payoff_coverage_note", "_payoff_sort_bp", "_pikalytics_panel_pair_counts",
    "_present_usage_payoff_ids", "_priority_finisher_combined_ko", "_ranked_payoff_moves",
    "_select_setup_payoff", "_setup_ability_for_payoff", "_setup_adjusted_score",
    "_setup_banned_payoffs", "_setup_branch_a", "_setup_branch_a_via_priority",
    "_setup_branches", "_setup_bulk_crossings", "_setup_bulk_ok", "_setup_defender_species",
    "_setup_excellent_floor", "_setup_kit_matrix_score", "_setup_mech_tier",
    "_setup_panel_build", "_setup_payoff_candidates", "_setup_payoff_notes",
    "_setup_priority_for_branch", "_setup_priority_kind", "_setup_self_drop_moves",
    "_setup_spe_crossings", "_setup_speed_path_a", "_setup_sustain_ok",
    "_setup_threat_defenders", "_setup_turn_order_weight", "_sort_members_by_crossings",
    "_sort_members_by_sweep", "_sweep_note_fields", "_threat_panel_label",
    "_usage_payoff_move_ids",
}
CONSTANTS = {
    "_ALLY_HIT_DAMAGE_MOVE_IDS", "_ALLY_HIT_TYPE_PROTECTIONS", "_BODY_PRESS_EVS",
    "_CONNECT_RECOIL_MOVES", "_DD_SETUP_PRESENCE_FLOOR", "_DEF_PAYOFF_DELTA_EPS",
    "_DRAIN_MOVES", "_SETUP_ACCEPTABLE_FLOOR_MULT", "_SETUP_BOTH_BRANCH_SCORE_DIV",
    "_SETUP_DAMAGE_FRAC_CAP", "_SETUP_PRIORITY_FINISHER_MOVES", "_SETUP_SPE_FLOOR",
    "_SETUP_THREAT_ENCOUNTER_GAMES", "_SETUP_THREAT_USAGE_PCT_FLOOR", "_SPREAD_DAMAGE_MOVE_IDS",
}
USAGE = {
    "_cbd_base_move_implausible_vs_mega", "_delivery_usage_hits", "_hits_clear_set_pct_floor",
    "_mega_usage_attribution", "_same_row_both_moves", "_usage_has_item",
}
SUPPORT = {"_screens_mech_dual", "_screens_dual_usage"}
STAT_BOOSTS = {"_self_boosts", "load_stat_boosts", "exact_self_boost_move", "exclusive_self_boost_move"}


def module_for(name: str) -> str | None:
    if name in SETUP:
        return "recommender.role_compendium_setup"
    if name in CONSTANTS:
        return "recommender.role_compendium_setup_constants"
    if name in USAGE:
        return "recommender.role_compendium_usage"
    if name in SUPPORT:
        return "recommender.role_compendium_support"
    if name in STAT_BOOSTS:
        return "recommender.stat_boosts"
    return None


def rewrite_inline(content: str) -> str:
    pat = re.compile(
        r"from recommender\.role_compendium import (\([^)]+\)|[\w_,\s]+)",
        re.MULTILINE,
    )

    def repl(m: re.Match[str]) -> str:
        blob = m.group(1).strip()
        if blob.startswith("("):
            inner = blob[1:-1]
        else:
            inner = blob
        names = [n.strip() for n in inner.split(",") if n.strip()]
        by_mod: dict[str, list[str]] = {}
        keep: list[str] = []
        for n in names:
            mod = module_for(n)
            if mod:
                by_mod.setdefault(mod, []).append(n)
            else:
                keep.append(n)
        out: list[str] = []
        for mod in sorted(by_mod):
            items = ", ".join(by_mod[mod])
            out.append(f"from {mod} import {items}")
        if keep:
            out.append(f"from recommender.role_compendium import {', '.join(keep)}")
        return "\n    ".join(out)

    return pat.sub(repl, content)


def rewrite_top_imports(path: Path, content: str) -> str:
    if path.name == "test_usage_cbd_or_showdown.py":
        return content.replace(
            "from recommender.role_compendium import (\n"
            "    _TRICK_ROOM_SET_PCT_FLOOR,\n"
            "    _USAGE_SET_PCT_FLOOR,\n"
            "    _UsageCtx,\n"
            "    _delivery_usage_hits,\n"
            "    _hits_clear_set_pct_floor,\n"
            "    _same_row_both_moves,\n"
            "    _usage_has_item,\n"
            ")",
            "from recommender.role_compendium import (\n"
            "    _TRICK_ROOM_SET_PCT_FLOOR,\n"
            "    _USAGE_SET_PCT_FLOOR,\n"
            "    _UsageCtx,\n"
            ")\n"
            "from recommender.role_compendium_usage import (\n"
            "    _delivery_usage_hits,\n"
            "    _hits_clear_set_pct_floor,\n"
            "    _same_row_both_moves,\n"
            "    _usage_has_item,\n"
            ")",
        )
    if path.name == "test_role_compendium_screens.py":
        return content.replace(
            "    _screens_mech_dual,\n",
            "",
        ).replace(
            "from recommender.role_compendium import (\n",
            "from recommender.role_compendium_support import _screens_mech_dual\n"
            "from recommender.role_compendium import (\n",
        )
    if path.name == "test_role_compendium_ally_risk.py":
        return content.replace(
            "from recommender.role_compendium import (\n"
            "    _ALLY_HIT_DAMAGE_MOVE_IDS,\n"
            "    _ally_damage_risk_note,\n"
            ")",
            "from recommender.role_compendium_setup_constants import _ALLY_HIT_DAMAGE_MOVE_IDS\n"
            "from recommender.role_compendium_setup import _ally_damage_risk_note",
        )
    if path.name == "test_role_compendium_pair_panel.py":
        return content.replace(
            "from recommender.role_compendium import (\n"
            "    _is_spread_damage_mid,\n"
            "    _pair_entry_label,\n"
            "    _setup_kit_matrix_score,\n"
            "    _setup_payoff_notes,\n"
            "    _setup_threat_defenders,\n"
            ")",
            "from recommender.role_compendium_setup import (\n"
            "    _is_spread_damage_mid,\n"
            "    _pair_entry_label,\n"
            "    _setup_kit_matrix_score,\n"
            "    _setup_payoff_notes,\n"
            "    _setup_threat_defenders,\n"
            ")",
        )
    return content


for path in TESTS.glob("test_role_compendium*.py"):
    text = path.read_text()
    text = rewrite_top_imports(path, text)
    text = rewrite_inline(text)
    path.write_text(text)

# trick_room attribution import at top
tr = TESTS / "test_role_compendium_trick_room.py"
text = tr.read_text()
text = text.replace(
    "    _mega_usage_attribution,\n",
    "",
)
if "from recommender.role_compendium_usage import _mega_usage_attribution" not in text:
    text = text.replace(
        "from recommender.role_compendium import (",
        "from recommender.role_compendium_usage import _mega_usage_attribution\n"
        "from recommender.role_compendium import (",
        1,
    )
text = text.replace(
    "    from recommender.role_compendium import _delivery_usage_hits",
    "    from recommender.role_compendium_usage import _delivery_usage_hits",
)
tr.write_text(text)

# usage test file
usage = TESTS / "test_usage_cbd_or_showdown.py"
usage.write_text(rewrite_top_imports(usage, usage.read_text()))

print("ok")
