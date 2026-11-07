# Follow-up 68 — re-pin refreshed in-game usage (a50b4dd4)

Read-only report. Branch `fu68-repin-ingame-usage` from main at `a50b4dd4`. Draft PR so `tests` runs (GITHUB_TOKEN push on the refresh commit did not).

## What changed on disk (pin)

| Pin | Old git blob | New git blob | content sha256 (new) |
|---|---|---|---|
| `data/usage/champions-reg-mc.ingame_doubles.v1.json` | `31af0801…` | `d60a06e0…` | `0c45c62a02b5997e428e5cdc16aecef8cbf138ab47471c4afaf5310064934796` |

Showdown (`63bcefe4…`), legality, and showdown_text pins untouched. `usage-showdown-rollover` not enabled.

Updated: `scripts/eval/part_g_v4/checks/check_pins.py` `EXPECTED_BLOB` + `pins_manifest.json` (ingame entry only).

## Regenerated

| Artifact | Result |
|---|---|
| `key_artifacts/derived_keys.json` | new sha `bba5787ce95f9e0b615ce679d8622ca6b1d7709e2cc8e73dc493cda7b88354b2` (was `e7067254…`) |
| `part3_request_set_v4.md` | new sha `98c3bd0249c0ac5626be7688d9767d20e08b2c5b2341f3ed9f6ada0ee68c3cae` (HN3 COMMON_ITEM percents only in the table) |
| `v4_request_set_report.md` | regenerated; byte-identical to HEAD — nothing to commit |
| `battery/claim_battery_v4.json` | new hash `e7492a6811f057f1e84ccac821c1249eb29a3fad1f25eec6f9a0e613b776f4b0` (was `6e6c6be4…`) |
| `battery/false_legal_battery_v4.json` | unchanged `3025138427391e57a92e1862a87b0074d44a51b290836077abf094af92c4bdec` |
| `battery/battery_manifest.json` | updated to match |
| `key_artifacts/full_chain_leaf_diff_v44.json` | **new version file** (supersedes v43); 36 leaves |
| `key_artifacts/showdown_items_ts.provenance.json` | `keys_sha_at_record` → new keys sha |
| `key_artifacts/calc_coverage.json` | recount `artifacts_saved` 627716 → 976 (file count; required set unchanged) |

Full chain: `run_full_chain_fast.py` with `PART_G_V4_CALC_IGNORE_DISK=1`, then hand-patch subtrees reapplied (same 21-subtree pattern as prior cuts).

## Not regenerated / left alone

- **Calc artifact bodies** under `key_artifacts/calc/`: live IGNORE_DISK rewrite added unrelated response schema fields (`ability_assert`, `recoil`, `abilityResolution`). Mechanical key leaves did not change (see leaf diff). Restored to HEAD so this PR stays usage-pin-scoped.
- **Arm v2 ladder artifacts at `a393ae91`**: untouched (no prompt / parser / sticky-lock edits).
- **MS2 / RB1 hand key cuts** and **`unlock_slot` prompt cut**: deferred per brief.

## Derived-key leaf diff (36 leaves, 4 row groups)

Grouped by row id. Count = leaf paths whose value changed.

### `ingame_top10_usage` (16)

| path | old | new |
|---|---|---|
| `[0]` name/id | Garchomp / garchomp | Sneasler / sneasler |
| `[1]` name/id | Sneasler / sneasler | Garchomp / garchomp |
| `[3]` name/id | Incineroar / incineroar | Kingambit / kingambit |
| `[5]` name/id | Archaludon / archaludon | Incineroar / incineroar |
| `[6]` name/id | Raichu / raichu | Indeedee-F / indeedeef |
| `[7]` name/id | Pelipper / pelipper | Basculegion / basculegion |
| `[8]` name/id | Kingambit / kingambit | Whimsicott / whimsicott |
| `[9]` name/id | Indeedee-F / indeedeef | Raichu / raichu |

### `hn3_common_item` (3)

| path | old | new |
|---|---|---|
| `cumulative_pct` | 94.6 | 97.3 |
| `items[0].pct` (Life Orb) | 37.0 | 42.4 |
| `items[1].pct` (Glimmoranite) | 30.7 | 28.0 |

(`items[2]` Focus Sash 26.9 unchanged.)

### `row_a_corviknight` (12)

| path | old | new |
|---|---|---|
| `after_item_clause[0].pct` | 32.0 | 38.5 |
| `after_item_clause[1].pct` | 9.2 | 14.9 |
| `after_item_clause[2].pct` | 4.8 | 11.8 |
| `corviknight_ingame_common_items[0]` | Psychic Seed 38.8 | Leftovers 38.5 |
| `corviknight_ingame_common_items[1]` | Leftovers 32.0 | Psychic Seed 25.5 |
| `corviknight_ingame_common_items[2].pct` | 9.2 | 14.9 |
| `corviknight_ingame_common_items[3]` | Rocky Helmet 7.7 | Occa Berry 11.8 |
| `corviknight_ingame_common_items[4]` | Occa Berry 4.8 | Rocky Helmet 3.3 |

### `row_c_gholdengo_scarf` (5)

| path | old | new |
|---|---|---|
| `t1_modal_item.pct` | 78.0 | 80.4 |
| `t1_modal_moves[0].pct` | 99.3 | 99.4 |
| `t1_modal_moves[1].pct` | 98.7 | 99.3 |
| `t1_modal_moves[2].pct` | 89.2 | 88.0 |
| `t1_modal_moves[3].pct` | 81.0 | 84.1 |

**Total:** 36 leaf changes, all usage-derived. No calc/damage/speed mechanical key leaves changed.

## Claim battery

Path stays `claim_battery_v4.json` (generator contract); content hash is the new version. Regenerating against the new ingame pin reshuffles **sampled** slots whose strata depend on usage (damage / speed / move_static pools), not only the 68 usage / 10 usage_showdown slots:

- claim items with content change: 183 of 415 (usage 34, usage_showdown 10, damage 53, speed 51, move_static 35)
- false_legal battery hash unchanged

## Test failures — before vs after

### Before (main `3117072` CI `tests`, against M-8 file from `b49e27f` / pin still M-7; 24 failed, 4762 passed, 18 skipped)

All 24 were usage-derived:

1. `test_ability_usage_tier.py::test_sandaconda_non_modal_sand_spit_grant`
2. `test_anchor_roles.py::test_writeup_kit_does_not_change_mechanism_roles[Arboliva-grassy_terrain_setter]`
3. `test_arm_teammates.py::test_h6_rillaboom_top5_is_served_from_ingame_without_percentages`
4. `test_arm_teammates.py::test_mt2_pelipper_whimsicott_intersection_on_ingame`
5. `test_arm_teammates.py::test_ingame_age_counts_from_captured_on`
6. `test_arm_teammates.py::test_showdown_result_is_labeled_separately_from_ingame_for_the_same_species`
7. `test_condition_resilience.py::test_kingambit_present_false_counts_as_dependent_in_assess`
8. `test_condition_resilience.py::test_milotic_and_rotom_wash_do_not_emit_secondary_speed_control`
9. `test_condition_resilience.py::test_icy_wind_softens_tr_without_changing_classification_or_gap`
10. `test_condition_resilience.py::test_milotic_usage_icy_wind_not_on_kit_does_not_soften`
11. `test_condition_resilience.py::test_rotom_wash_thunderbolt_does_not_soften`
12. `test_condition_resilience.py::test_goodra_sap_sipper_and_thunderbolt_do_not_soften`
13. `test_condition_resilience.py::test_ampharos_static_softens_tr`
14. `test_condition_resilience.py::test_kingambit_declared_sweeper_counts_as_wanted_tr`
15. `test_condition_resilience.py::test_plus_nature_only_discounts_kingambit_and_does_not_emit`
16. `test_condition_resilience.py::test_two_hindering_natures_without_declared_sweeper_make_tr_essential`
17. `test_condition_resilience.py::test_declared_garchomp_mega_plus_kingambit_is_preferred_not_essential`
18. `test_condition_resilience.py::test_declared_kingambit_plus_kangaskhan_mega_is_essential`
19. `test_forme_identity.py::test_classify_mechanical_gourgeist_and_toxtricity`
20. `test_forme_identity.py::test_pool_skips_cosmetics_and_blade_keeps_gourgeist`
21. `test_slot_fill.py::test_resolve_condition_beneficiaries_confidence_is_usage_aware`
22. `test_slot_fill.py::test_annotate_composition_impact_sets_species_primary_role`
23. `test_slot_fill.py::test_pending_presentation_wires_species_primary_role`
24. `test_slot_fill.py::test_real_ariados_redirection_refines_to_full_provisional_slot`

(`check_pins` also fails closed on main until this re-pin.)

### After re-pin to `a50b4dd4` (2026-11-07 M-8) + test rebaselines

Of the 24:

- **20 pass without test edits** under the Nov-7 capture (Sandaconda / Arboliva / condition_resilience / forme_identity / slot_fill including `standard_physical_attacker` vs redirection).
- **4 rebaselined** in `test_arm_teammates.py`: H6 top5 Gholdengo→Kingambit; MT2 adds Indeedee-F; `captured_on`/`season` → `2026-11-07` / `M-8` with age monkeypatch `2026-11-14`.

**Additional usage-derived failure exposed by the Nov-7 capture** (not in the 24):

- `test_ability_usage_tier.py::test_kingambit_swords_dance_stays_good` — tier Good→Excellent; renamed to `test_kingambit_swords_dance_is_excellent`.

### Non-usage-derived failures

None. After the rebaselines above: **0 failed**.

## Local suite counts

| Suite | Result |
|---|---|
| `run_all_checks.py` | exit 0; 12/12 PASS; keys_sha=`bba5787c…`; claim=`e7492a68…`; false_legal=`30251384…` (unchanged) |
| `uv run pytest` | **4800 passed, 15 skipped** |

Hashes (unbroken):

claim=`e7492a6811f057f1e84ccac821c1249eb29a3fad1f25eec6f9a0e613b776f4b0` false_legal=`3025138427391e57a92e1862a87b0074d44a51b290836077abf094af92c4bdec` keys_sha=`bba5787ce95f9e0b615ce679d8622ca6b1d7709e2cc8e73dc493cda7b88354b2`
