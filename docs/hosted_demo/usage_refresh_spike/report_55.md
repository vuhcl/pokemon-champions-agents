# Follow-up 55: the 24 failures on `b49e27f`

Report only. No test edits. The assertion text is from the pytest run on `b49e27f` (24 failed, 4758 passed, 18 skipped). The actual values below were read from that same usage file. `gourgeistlarge` returning `battle_transform` is the form check working as designed when a forme has no independent ladder row. That case was not investigated further.

Wait for the re-pin before editing any of these. `species_n` can still move, and a test updated now has to be edited again if the value it pins moves.

## (a) Data-derived expected value

Updating the pinned literals to the M-8 values makes these pass, with no product code. Two tests need every pin in the test updated, not only the line that failed first.

| Test | What differs |
|---|---|
| `test_ability_usage_tier.py::test_sandaconda_non_modal_sand_spit_grant` | Grant is `None`, expected `sandspit`. The modal map is Sand Spit only, and the test also requires Sand Veil in that map. |
| `test_anchor_roles.py::test_writeup_kit_does_not_change_mechanism_roles[Arboliva-grassy_terrain_setter]` | Role is `bulky_special_attacker`, expected `grassy_terrain_setter`. |
| `test_arm_teammates.py::test_h6_rillaboom_top5_is_served_from_ingame_without_percentages` | Top 5 is Incineroar, Sneasler, Garchomp, Raichu, Kingambit. The pin has Gholdengo instead of Kingambit. |
| `test_arm_teammates.py::test_showdown_result_is_labeled_separately_from_ingame_for_the_same_species` | Same top-5 set as the row above (`H6_TOP5`). |
| `test_arm_teammates.py::test_mt2_pelipper_whimsicott_intersection_on_ingame` | Intersection adds Indeedee-F to the pinned Charizard, Garchomp, Sneasler. |
| `test_arm_teammates.py::test_ingame_age_counts_from_captured_on` | `('2026-11-06', 'M-8')`, expected `('2026-10-21', 'M-7')`. Age against the test's today of 2026-10-28 is -9, not 7. |
| `test_condition_resilience.py::test_plus_nature_only_discounts_kingambit_and_does_not_emit` | Kingambit spread `spe` is 32, expected 0. The later asserts in this test still hold. |
| `test_slot_fill.py::test_resolve_condition_beneficiaries_confidence_is_usage_aware` | Castform evidence is `mechanical_only` / `low`, expected `usage_backed` / `high`. |
| `test_slot_fill.py::test_annotate_composition_impact_sets_species_primary_role` | Ariados role is `standard_physical_attacker`, expected `redirection`. |
| `test_slot_fill.py::test_pending_presentation_wires_species_primary_role` | Same Ariados role, `standard_physical_attacker` versus `redirection`. |

1. Yes. Sandaconda also needs the Sand Veil pin changed. The age test also needs `age_days` or the frozen today changed. Both are still test expectations.
2. Wait. All ten pin a current ladder fact. The two Rillaboom tests share `H6_TOP5`, so that is one edit covering two tests. If the file moves that fact again, the edit happens twice.

## (b) Missing ladder row

| Test | What differs |
|---|---|
| `test_forme_identity.py::test_classify_mechanical_gourgeist_and_toxtricity` | `gourgeistlarge` is `battle_transform`, expected `mechanical_selectable`. |
| `test_forme_identity.py::test_pool_skips_cosmetics_and_blade_keeps_gourgeist` | `gourgeistlarge` is not in the legal pool. |

1. Yes. Point the first test's `gourgeistlarge` expectation at `battle_transform`, and drop or invert the pool membership assert. The failure in the classify test is the first assert; `gourgeistsuper` and `toxtricitylowkey` were not the failing lines.
2. Wait with the re-pin. If these are updated now and a later capture gives `gourgeistlarge` its own row, both tests are edited again. If the row stays absent, they are not.

## (c) Not a pinned value that can be regenerated

These do not pass by writing an M-8 literal into the failing assert. No product change is proposed.

| Test | What differs |
|---|---|
| `test_condition_resilience.py::test_kingambit_present_false_counts_as_dependent_in_assess` | `next()` raises `StopIteration`. The resilience report's condition list is empty, so there is no Trick Room row. |
| `test_condition_resilience.py::test_icy_wind_softens_tr_without_changing_classification_or_gap` | Same missing Trick Room row (`StopIteration`) on the Kingambit usage build. |
| `test_condition_resilience.py::test_milotic_usage_icy_wind_not_on_kit_does_not_soften` | Same missing Trick Room row. |
| `test_condition_resilience.py::test_rotom_wash_thunderbolt_does_not_soften` | Same missing Trick Room row. |
| `test_condition_resilience.py::test_goodra_sap_sipper_and_thunderbolt_do_not_soften` | Goodra's pinned M-B moves still match. The failure is the same missing Trick Room row. |
| `test_condition_resilience.py::test_ampharos_static_softens_tr` | Ampharos's pinned M-B moves still match. The failure is the same missing Trick Room row. |
| `test_condition_resilience.py::test_declared_garchomp_mega_plus_kingambit_is_preferred_not_essential` | `StopIteration`. The report's conditions are Sand only. Both builds have spread `spe` 32. |
| `test_condition_resilience.py::test_kingambit_declared_sweeper_counts_as_wanted_tr` | Spread `spe` is 32, expected 0. With that spread the wanted count is 0, and the test expects 1. |
| `test_condition_resilience.py::test_two_hindering_natures_without_declared_sweeper_make_tr_essential` | Trick Room classification is `preferred`, expected `essential`. Wanted dependents are 1, expected 2. Kingambit `spe` is 32 and Goodra `spe` is 0. |
| `test_condition_resilience.py::test_declared_kingambit_plus_kangaskhan_mega_is_essential` | Trick Room classification is `preferred`, expected `essential`. The only wanted dependent is Kangaskhan-Mega, so the count is 1, expected 2. |
| `test_condition_resilience.py::test_milotic_and_rotom_wash_do_not_emit_secondary_speed_control` | Rotom-Wash moves are Hydro Pump, Thunderbolt, Will-O-Wisp, Electroweb. The pin has Protect instead of Electroweb. The test also requires Electroweb to be absent, and the role emits `secondary_speed_control` for `move:electroweb`. |
| `test_slot_fill.py::test_real_ariados_redirection_refines_to_full_provisional_slot` | `assert None is not None`. Strategic evidence for `redirection` is missing. Asking for `standard_physical_attacker` is also `None`. Ariados's anchor role is `standard_physical_attacker`; its moves are Protect, Sucker Punch, Poison Jab, First Impression. |

1. No.
2. Do not update these as a data refresh. Rewriting them to today's behavior and then seeing the file move would edit them twice. That applies to all twelve: the Kingambit spread, the Rotom-Wash moves, and the Ariados kit are the ladder facts underneath.

Kingambit's usage spread on this file is `spe` 32, nature Adamant, item Chople Berry. `_discount_tr_wanted` returns true when `spe` is greater than 0. That is why the wanted counts above are short. The empty condition list on the `StopIteration` tests was measured; the branch that drops the row was not traced.

## CLI graph, not the demo backend; not used for decisions

A 10-session mixed cap-2 run had already finished (wall 189.3 s, worst message script A message 3 at 19.58 s, no invoke errors). A 12-session queue run had also finished (the process printed wall 230.0 s, 0 user-message refusals, 4 init refusals, max wait 0 s, max total 18.064 s, none over 120 s). Those prints were not checked further. Node attribution was not started. No cap, queue, timeout, or graph-path PR was changed.
