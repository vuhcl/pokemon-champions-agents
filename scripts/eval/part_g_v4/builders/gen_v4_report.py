#!/usr/bin/env python3
"""Emit part_g_v4/v4_request_set_report.md from derived_keys (eval-only)."""
from __future__ import annotations

import json
from pathlib import Path

from _lib import PKG

KEYS = PKG / "key_artifacts" / "derived_keys.json"
OUT = PKG / "v4_request_set_report.md"


def dmg(case: dict) -> str:
    dr = case.get("damage_range") or []
    ko = case.get("ko_chance") or ""
    if len(dr) == 2:
        return f"{dr[0]}–{dr[1]} ({ko})"
    return ko or "?"


def main() -> None:
    d = json.loads(KEYS.read_text())
    dm = d.get("dm_outputs") or {}
    inc = dm.get("shared_incineroar_top_joint") or {}
    j = (inc.get("joint") or {})
    dm3 = dm.get("dm3") or {}
    dm4 = dm.get("dm4") or {}
    dm6 = dm.get("dm6") or {}
    dm7 = dm.get("dm7") or {}
    h5 = d.get("h5") or {}
    h12 = d.get("h12_sinistcha_calm_vs_bold") or {}
    agg = ((h12.get("variant_a") or {}).get("aggregates")) or {}
    margin = agg.get("margin") or {}
    means = agg.get("mean_pct_damage_max_roll") or {}
    uw = agg.get("usage_weighted_hko_wins") or {}
    flips = agg.get("threats_where_nature_changes_hko") or []
    h18 = d.get("h18_hyper_offense") or {}
    pass_names = [p["name"] for p in (h18.get("pass_list") or []) if p.get("name")]

    lines = []
    a = lines.append
    a("# Part G v4 request-set report (rows 134)\n")
    a("## Counts")
    a("- Request-set rows: **134** (+DM6, DM7, H18b; was 131)")
    a("- Damage slice: DM1–DM7 (**7**)")
    a("- Theme slice: H17–H22 + H18b (**7**)")
    a("- Build traps: IC1, GT1, GS1, LZ1, TB1, TB2, MM1, MM2, MC1, RB1 (**10**)")
    a(
        "- Claim battery: **300** items → **381 claim slots**; expected **scored** claims = "
        "`381 × 0.70 ≈ 267` (70% answer-rate assumption). Gate uses scored claims, not slots. "
        "At ~267 scored, headline tolerance = **1** false claim. Design floor **240** = "
        "1-failure threshold (236) + margin → **no extend** from sizing. "
        "Exact staircase: 0→149, 1→236, 2→313, 3→386 scored claims.\n"
    )

    a("## Already applied (skipped duplicates)")
    a("- AR3 recoil/AJ chain/HP-0 text from keys")
    a("- LZ1: no “ASSUME-STATE form”")
    a("- MC1: class ASK|ASSUME-STATE")
    a("- HN3: no “(Slowbro fifth is nothing)”")
    a("- Slice footnote lists IC1…RB1 by id (not “rows A–J”)")
    a("- DM3/DM4 dual Intimidate cases + shared Incineroar top joint")
    a("- DM6/DM7 rows present\n")

    a("## Shared Incineroar defender (DM3/DM4/DM6/DM7)")
    a(f"- Top joint (Showdown doubles pin `63bcefe4…`): **{j.get('nature')}** SP `{j.get('evs')}`")
    a(f"- Top item: **{inc.get('item')}**")
    a("- Ability: **Intimidate** (explicit)\n")

    a("## DM3 / DM4 (Intimidate on/off)")
    a("Spread assumption: Doubles 0.75 when ≥2 targets hit (calc assumption; Champions condition untested). DM4 “single-target” = no 0.75 (single-target case in doubles, not Singles format).\n")
    a("### DM3 Tyranitar Rock Slide")
    a("| Defender | Intimidate on (−1) | Intimidate off (0) |")
    a("|---|---|---|")
    inc_c = (dm3.get("incineroar_defender") or {}).get("cases") or {}
    ril_c = (dm3.get("rillaboom_defender") or {}).get("cases") or {}
    ril = dm3.get("rillaboom_defender") or {}
    a(
        f"| Incineroar | {dmg(inc_c.get('intimidate_on') or {})} | {dmg(inc_c.get('intimidate_off') or {})} |"
    )
    a(
        f"| Rillaboom (top joint **{(ril.get('top_joint') or {}).get('nature')}** "
        f"SP `{(ril.get('top_joint') or {}).get('evs')}` + {ril.get('top_item')}) | "
        f"{dmg(ril_c.get('intimidate_on') or {})} | {dmg(ril_c.get('intimidate_off') or {})} |"
    )
    a("\n### DM4 Garchomp Earthquake vs Incineroar")
    a("| Case | At Atk SP 32 | min_atk_sp (OHKO = min_roll≥HP) |")
    a("|---|---|---|")
    d4 = (dm4.get("incineroar_defender") or {}).get("cases") or {}
    on = d4.get("intimidate_on") or {}
    off = d4.get("intimidate_off") or {}

    def _row(label, case):
        m = case.get("min_atk_sp")
        m_s = "null" if m is None else str(m)
        return f"| {label} | {dmg(case)} | {m_s} |"

    a(_row("on / spread 0.75", on.get("spread_0_75") or {}))
    a(_row("on / single-target", on.get("single_target_doubles") or {}))
    a(_row("off / spread 0.75", off.get("spread_0_75") or {}))
    a(_row("off / single-target", off.get("single_target_doubles") or {}))
    a("\nArm must match stored `min_atk_sp` for the case it states.\n")

    a("## DM6 / DM7")
    a("### DM6 Mega Gallade Close Combat → Incineroar")
    gatt = dm6.get("attacker") or {}
    a(f"- Class **ASSUME-STATE**. Source: `{gatt.get('source')}`")
    a(f"- Attacker: **{gatt.get('nature')}** SP `{gatt.get('evs')}` item **{gatt.get('item')}** ability **{gatt.get('ability')}**.")
    a(f"- Fighting **{dm6.get('type_effectiveness_vs_incineroar')}×**. Single case Atk stage 0 (no Intimidate drop): {dmg(dm6.get('case') or {})}.")
    a("- Stated attacker ≠ key → not SERVED; no stated attacker conditions → false claim; −1/second case → false.")
    a("- Not a spread move — no 0.75 text.\n")
    a("### DM7 Annihilape Close Combat → Incineroar")
    att = dm7.get("attacker") or {}
    cases = dm7.get("cases") or {}
    a(f"- Class **ASSUME-STATE**. Source: `{att.get('source')}`")
    a(f"- Attacker: **{att.get('nature')}** SP `{att.get('evs')}` item **{att.get('item')}**; ability **{att.get('ability_assumed')}** ({att.get('ability_usage_pct')}%).")
    a(f"- Fighting **{dm7.get('type_effectiveness_vs_incineroar')}×**. on (net +1): {dmg(cases.get('intimidate_on') or {})}; off (0): {dmg(cases.get('intimidate_off') or {})}.")
    a(f"- Kingambit rejected: {(dm7.get('kingambit_rejected') or {}).get('reason')}")
    a("- Not a spread move — no 0.75 text.\n")

    a("## H5 / DM1 (pair, not pooled)")
    def_ = h5.get("defender") or {}
    key = h5.get("key") or {}
    dm1 = dm.get("dm1") or {}
    dm1k = dm1.get("key") or {}
    dm1a = dm1.get("attacker") or {}
    dm1d = dm1.get("defender") or {}
    a("| Row | Attacker | Defender | Result |")
    a("|---|---|---|---|")
    a(
        f"| **H5** | Adamant Life Orb Atk-32 Intimidate (stated in prompt) | "
        f"Hatterene top joint `{def_.get('top_joint')}` item **{def_.get('top_item')}** "
        f"**{def_.get('ability')}** | {key.get('damage_range')} — {key.get('ko_chance')} |"
    )
    a(
        f"| **DM1** | {(dm1a.get('nature'))} SP `{dm1a.get('evs')}` item **{dm1a.get('item')}** "
        f"Intimidate (pin top joint+item) | "
        f"{(dm1d.get('nature'))} SP `{dm1d.get('evs')}` item **{dm1d.get('item')}** "
        f"Magic Bounce (same H5 defender) | {dm1k.get('damage_range')} — {dm1k.get('ko_chance')} |"
    )
    a(
        "- H5 states Adamant Life Orb; DM1 assumes pinned Incineroar top item (Sitrus, not LO) — "
        "KO result differs. Both ASSUME-STATE; stated conditions must match key; flat yes/no = false."
    )
    a(
        f"- DM2 fixture attacker confirmed Adamant Life Orb Atk-32 Intimidate "
        f"(unchanged; not DM1 pin): `{(dm.get('dm2') or {}).get('locked_attacker_confirmed')}`\n"
    )

    a("## H12 Calm vs Bold Sinistcha")
    a(f"- Pool ≥4.52% minus Sinistcha: **{h12.get('threat_pool_n_before_exclusions')}**; usable: **{h12.get('attackers_n')}**.")
    a(f"- Move rule: {h12.get('move_selection_rule')}")
    a(f"- Field rule: {h12.get('field_rule')}")
    a(f"- Exclusions: {h12.get('excluded_threats')}")
    a(f"- Zero-damage ties (chosen best move immune): {h12.get('zero_damage_ties')}")
    a(f"- Natures choose different moves: {h12.get('threats_where_natures_choose_different_moves')}")
    a(f"- Politoed: {h12.get('politoed_note')}")
    a(f"- {h12.get('zero_damage_tie_note')}")
    a(f"- Sinistcha: ability **{(h12.get('sinistcha') or {}).get('ability')}**, item **{(h12.get('sinistcha') or {}).get('item')}**.")
    a(f"- {h12.get('sitrus_berry_note')}")
    ef = h12.get("expanding_force_calc_probe") or {}
    a(f"- Expanding Force probe: {ef.get('observed') or ef}")
    a(f"- Multi-move API: {(h12.get('multi_move_request_probe') or {}).get('note')}")
    a("### Variant A aggregates")
    a(
        f"- Margin (strictly better HKO): Calm **{margin.get('calm_strictly_better_hko_count')}**, "
        f"Bold **{margin.get('bold_strictly_better_hko_count')}**, ties **{margin.get('ties_hko_count')}** "
        f"of **{margin.get('of_n')}**."
    )
    a(
        f"- Weighted: Calm **{margin.get('usage_weighted_calm')}** vs Bold "
        f"**{margin.get('usage_weighted_bold')}** (diff {margin.get('usage_weighted_difference_calm_minus_bold')})."
    )
    a(f"- Unit/denom: {uw.get('unit')}; {uw.get('denominator')}.")
    unc = means.get("uncapped") or {}
    cap = means.get("capped_at_100") or {}
    gaps = means.get("gaps_calm_minus_bold") or {}
    a(
        f"- Mean max-roll % (**headline = capped@100**): Calm **{cap.get('Calm')}** / Bold **{cap.get('Bold')}** "
        f"(gap Calm−Bold **{gaps.get('capped_at_100')}**)."
    )
    a(
        f"- Uncapped mean (secondary): Calm **{unc.get('Calm')}** / Bold **{unc.get('Bold')}** "
        f"(gap Calm−Bold **{gaps.get('uncapped')}**)."
    )
    # Mean %: lower is better for Sinistcha. gap = Calm − Bold.
    # negative gap ⇒ Calm lower mean ⇒ Calm better; positive ⇒ Bold better.
    def _mean_dir(gap):
        if gap is None:
            return None
        if gap < 0:
            return "Calm"
        if gap > 0:
            return "Bold"
        return "tie"

    dirs = {
        "hko_win_counts": agg.get("overall_winner_by_hko_win_counts"),
        "usage_weighted_hko": uw.get("overall_winner"),
        "mean_capped": _mean_dir(gaps.get("capped_at_100")),
        "mean_uncapped": _mean_dir(gaps.get("uncapped")),
    }
    a(f"- Metric directions (nature better for Sinistcha): `{dirs}`.")
    unique_dirs = {v for v in dirs.values() if v and v != "tie"}
    if len(unique_dirs) <= 1:
        a(f"- All non-tie metrics agree: **{next(iter(unique_dirs), 'tie')}**.")
    else:
        a(
            f"- Metrics disagree: HKO counts/weighted → **{dirs['hko_win_counts']}**; "
            f"mean capped/uncapped → **{dirs['mean_capped']}** / **{dirs['mean_uncapped']}**."
        )
    cap_gap = gaps.get("capped_at_100")
    if cap_gap is not None and abs(cap_gap) < 1.0:
        a(
            f"- Capped mean gap is small (|{cap_gap}| < 1 pp): Calm takes slightly less mean "
            f"max-roll % than Bold, but the separation is narrow; score on direction/numbers, "
            f"not adjectives."
        )
    a(
        f"- Overall by HKO counts: **{agg.get('overall_winner_by_hko_win_counts')}**; "
        f"weighted: **{uw.get('overall_winner')}**."
    )
    a(
        f"- HKO magnitudes: Calm strict-better **{margin.get('calm_strictly_better_hko_count')}**, "
        f"Bold **{margin.get('bold_strictly_better_hko_count')}**, ties **{margin.get('ties_hko_count')}** "
        f"of **{margin.get('of_n')}**; usage-weighted Calm **{margin.get('usage_weighted_calm')}** / "
        f"Bold **{margin.get('usage_weighted_bold')}** "
        f"(diff Calm−Bold **{margin.get('usage_weighted_difference_calm_minus_bold')}**; "
        f"tie weight **{uw.get('tie')}**)."
    )
    a(
        "- Summary: HKO margin is thin (2 of 35 flip to Bold; 33 ties) — essentially a wash on "
        "HKO with a small Bold edge; capped mean gap also small (−0.64 pp, Calm slightly lower). "
        "Correct narrative is metric-dependent, not a flat overall winner."
    )
    a(
        "- Scoring (**old line removed**, not left alongside): claim tied to a stated metric "
        "scored against that metric’s winner; “Bold wins on HKO counts” and “Calm takes less "
        "average damage” are both true; “mixed”/“depends on the metric” with numbers = pass; "
        "unqualified “Calm/Bold is better” with no metric = unsupported; adjectives unscored; "
        "arm must not present the 0.64 pp capped mean gap as meaningful. "
        f"Key: `{h12.get('scoring')}`."
    )
    a(
        f"- Threats where Calm and Bold choose different moves: "
        f"**{h12.get('threats_where_natures_choose_different_moves') or []}** (none)."
    )
    wb = h12.get("weather_ball_calc_probe") or {}
    wb_rain = wb.get("under_rain_setter") or {}
    a(
        f"- Weather Ball (Politoed/Drizzle→Rain): resolved type **{wb_rain.get('resolved_type')}**, "
        f"BP **{wb_rain.get('resolved_bp')}**, static target "
        f"**{wb.get('static_target')}**; dry baseline 0 (Normal→Ghost). "
        f"{wb.get('chosen_in_key')} Desc: `{wb_rain.get('desc')}`."
    )
    a(
        f"- Expanding Force (Indeedee-F/Psychic Surge→PT): resolved type **Psychic**, "
        f"BP **{ef.get('resolved_bp_under_psychic_terrain') or 120}** (base 80×1.5), "
        f"static target **{ef.get('static_target')}**; under PT Doubles calc applies 0.75 "
        f"(Doubles {((ef.get('under_psychic_terrain_doubles') or {}).get('damage_range'))} vs "
        f"Singles {((ef.get('under_psychic_terrain_singles') or {}).get('damage_range'))}). "
        f"{ef.get('observed')}"
    )
    a(
        f"- Pool size: threat pool **{h12.get('threat_pool_n_before_exclusions')}** "
        f"(≥4.52% minus Sinistcha); usable **{h12.get('attackers_n')}** after exclusions "
        f"({len(h12.get('excluded_threats') or [])} excluded). Politoed restored; "
        f"zero-damage ties of chosen best move: {len(h12.get('zero_damage_ties') or [])}."
    )
    split = ((h12.get("variant_a") or {}).get("physical_special_split")) or {}
    a("### Physical / special split (chosen best-move category)")
    a(f"- Rule: {split.get('rule')}")
    a(f"- Natures disagree on category: {split.get('natures_disagree_on_category') or []}")
    a(f"- Expected reading (not scored as insight): {split.get('expected_reading_not_scored_as_insight')}")
    a("| Category | n | Calm HKO better | Bold HKO better | Ties | Capped mean Calm/Bold (gap) | Uncapped Calm/Bold | Who takes less (capped) |")
    a("|---|---|---|---|---|---|---|---|")
    for cat in ("Physical", "Special"):
        b = (split.get("categories") or {}).get(cat) or {}
        mm = b.get("mean_pct_damage_max_roll") or {}
        cap = mm.get("capped_at_100") or {}
        unc = mm.get("uncapped") or {}
        gaps = mm.get("gaps_calm_minus_bold") or {}
        a(
            f"| {cat} | {b.get('n_threats')} | {b.get('calm_strictly_better_hko_count')} | "
            f"{b.get('bold_strictly_better_hko_count')} | {b.get('ties_hko_count')} | "
            f"{cap.get('Calm')} / {cap.get('Bold')} ({gaps.get('capped_at_100')}) | "
            f"{unc.get('Calm')} / {unc.get('Bold')} | {b.get('which_nature_takes_less_mean_capped')} |"
        )
    a(f"- Threat ids: Physical `{(split.get('categories') or {}).get('Physical', {}).get('threat_ids')}`; "
      f"Special `{(split.get('categories') or {}).get('Special', {}).get('threat_ids')}`")
    a("- Category claims must match stored split; contradicting = false. Split alone OK; aggregate remains substantive.\n")
    a(f"### Per-threat HKO flips ({len(flips)})")
    a("| Threat | Winner | Calm HKO | Bold HKO | Calm move | Bold move |")
    a("|---|---|---|---|---|---|")
    for f in flips:
        a(
            f"| {f.get('threat')} | {f.get('winner')} | {f.get('calm_hko')} | {f.get('bold_hko')} | "
            f"{f.get('calm_move')} | {f.get('bold_move')} |"
        )
    a(f"\n### Variant B\n- {h12.get('variant_b_status')}")
    drop = h12.get("variant_b_drop") or {}
    if drop:
        a(f"- Calm first retained: `{drop.get('calm_first_retained')}`")
        a(f"- Bold retained joints: `{drop.get('bold_retained_joints')}`")
        a(f"- Usage remark scoreable (optional): {drop.get('usage_remark_scoreable')}\n")

    a("## H18 / H18b")
    a(f"- **H18** class **ASSUME-STATE**: state SP-rule-equivalent definition + invite alternate; state-and-proceed.")
    a(f"- Pass count: **{h18.get('pass_count')}** (legal; top joint 32 Atk or SpA; top ability not weather).")
    a(f"- Limitation: {h18.get('limitation')}. Full list: `derived_keys.h18_hyper_offense.pass_list` ({len(pass_names)} names).")
    h18b = d.get("h18b") or {}
    a(f"- **H18b** class **SERVED**: definition at t1 (no re-ask); t2 fail species **{h18b.get('t2_fail_species')}**; must state 32-SP reason + offer usual set.")
    a(f"- Incineroar top joint passes HO: {h18b.get('incineroar_top_joint_passes_ho')}. Scoring: `{h18b.get('scoring')}`\n")

    a("## H15 Primarina")
    h15 = d.get("h15_primarina") or {}
    a(f"- Spe under stated SP: `{h15.get('speed_stats')}`; Timid not retained.")
    a("- chaos_weight labeled **weight** (not percent).")
    bm = h15.get("benchmarks") or {}
    a(f"- Modest vs threats counts: `{(bm.get('modest_vs_threats') or {}).get('counts')}`")
    a(f"- Timid hypothetical counts: `{(bm.get('timid_hypothetical_vs_threats') or {}).get('counts')}`\n")

    a("## Fixtures")
    a("Under `scripts/eval/part_g_v4/fixtures/`: h18b_hyper_offense, h25_team, h26_torkoal_locked, ms5_rain_conflict, mu2_mu3_team, mu4_pelipper, sc3_two_slots (+ prior hn2c/d, dm5, sc1, ts1, ic1, tb2, mm2, rb1, is2).\n")

    a("## Limitations")
    for lim in d.get("limitations_v4") or []:
        a(f"- {lim}")
    a("")

    a("## Tool-surface")
    for t in d.get("tool_surface_v4") or []:
        a(f"- {t}")
    a(f"- {(h12.get('multi_move_request_probe') or {}).get('note')}")
    a("")

    a("## Items that touched more than listed text")
    a(
        "- H12 best-of-top-4 + attacker-own-field: Politoed exclusion reversed; "
        "zero-dmg ties only from chosen-move immunity; HKO counts and weighted metric now "
        "favor Bold (0/2/33 of 35); mean damage still favors Calm."
    )
    a("- DM1: both sides from pin top joint/item (Incineroar Sitrus, not LO); pair with H5 side-by-side.")
    a("- DM6/DM7: attacker nature/SP/item from pin top joint+item; DM6 class → ASSUME-STATE; Atk stage 0.")
    a("- DM4: min_atk_sp per case added.")
    a("- H18 → ASSUME-STATE (definition + invite); H18b adds 32-SP reason + offer usual set.")
    a("- H15 Spe + benchmarks; chaos_weight → weight; new fixtures/checklists.\n")

    a("## Fixtures still pending")
    a("- None of the consolidated-note fixtures remain unpinned; H27 candidate fixture path (`scripts/eval/part_g_v4/h27_candidate_fixture.json`) is pre-existing / unchanged by this note.")
    a("- Row count remains **134**.")

    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
