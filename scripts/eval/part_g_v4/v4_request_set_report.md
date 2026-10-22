# Part G v4 request-set report (rows 134)

## Counts
- Request-set rows: **134** (+DM6, DM7, H18b; was 131)
- Damage slice: DM1–DM7 (**7**)
- Theme slice: H17–H22 + H18b (**7**)
- Build traps: IC1, GT1, GS1, LZ1, TB1, TB2, MM1, MM2, MC1, RB1 (**10**)
- Claim battery: **300** items → **379 claim slots**; expected **scored** claims = `379 × 0.70 ≈ 265` (70% answer-rate assumption). Gate uses scored claims, not slots. At ~265 scored, headline tolerance = **1** false claim. Design floor **240** = 1-failure threshold (236) + margin → **no extend** from sizing. Exact staircase: 0→149, 1→236, 2→313, 3→386 scored claims.

## Already applied (skipped duplicates)
- AR3 recoil/AJ chain/HP-0 text from keys
- LZ1: no “ASSUME-STATE form”
- MC1: class ASK|ASSUME-STATE
- HN3: no “(Slowbro fifth is nothing)”
- Slice footnote lists IC1…RB1 by id (not “rows A–J”)
- DM3/DM4 dual Intimidate cases + shared Incineroar top joint
- DM6/DM7 rows present

## Shared Incineroar defender (DM3/DM4/DM6/DM7)
- Top joint (Showdown doubles pin `63bcefe4…`): **Adamant** SP `{'hp': 32, 'atk': 32, 'def': 0, 'spa': 0, 'spd': 2, 'spe': 0}`
- Top item: **Sitrus Berry**
- Ability: **Intimidate** (explicit)

## DM3 / DM4 (Intimidate on/off)
Spread assumption: Doubles 0.75 when ≥2 targets hit (calc assumption; Champions condition untested). DM4 “single-target” = no 0.75 (single-target case in doubles, not Singles format).

### DM3 Tyranitar Rock Slide
| Defender | Intimidate on (−1) | Intimidate off (0) |
|---|---|---|
| Incineroar | 78–92 (guaranteed 3HKO) | 116–140 (guaranteed 2HKO) |
| Rillaboom (top joint **Jolly** SP `{'hp': 2, 'atk': 32, 'def': 0, 'spa': 0, 'spd': 0, 'spe': 32}` + Miracle Seed) | 39–46 (3.7% chance to 4HKO) | 58–70 (99.8% chance to 3HKO) |

### DM4 Garchomp Earthquake vs Incineroar
| Case | At Atk SP 32 | min_atk_sp (OHKO = min_roll≥HP) |
|---|---|---|
| on / spread 0.75 | 102–122 (guaranteed 2HKO) | null |
| on / single-target | 138–164 (guaranteed 2HKO) | null |
| off / spread 0.75 | 152–182 (guaranteed 2HKO) | null |
| off / single-target | 206–246 (guaranteed OHKO) | 28 |

Arm must match stored `min_atk_sp` for the case it states.

## DM6 / DM7
### DM6 Mega Gallade Close Combat → Incineroar
- Class **ASSUME-STATE**. Source: `{'nature_sp': 'showdown_doubles Gallade-Mega top retained joint (COMMON_JOINT[0])', 'item': 'showdown_doubles Gallade-Mega top item (Galladite / mega stone)', 'ability': 'mega form sole ability Inner Focus (also top Showdown ability 100%)', 'joint_chaos_weight': 1115.0763868554704}`
- Attacker: **Jolly** SP `{'hp': 2, 'atk': 32, 'def': 0, 'spa': 0, 'spd': 0, 'spe': 32}` item **Galladite** ability **Inner Focus**.
- Fighting **2.0×**. Single case Atk stage 0 (no Intimidate drop): 270–318 (guaranteed OHKO).
- Stated attacker ≠ key → not SERVED; no stated attacker conditions → false claim; −1/second case → false.
- Not a spread move — no 0.75 text.

### DM7 Annihilape Close Combat → Incineroar
- Class **ASSUME-STATE**. Source: `{'nature_sp': 'showdown_doubles Annihilape top retained joint (COMMON_JOINT[0])', 'item': 'showdown_doubles Annihilape top item', 'ability': 'top Showdown ability Defiant (assumed; must be stated)', 'joint_chaos_weight': 13607.750963984106}`
- Attacker: **Jolly** SP `{'hp': 2, 'atk': 32, 'def': 0, 'spa': 0, 'spd': 0, 'spe': 32}` item **Choice Scarf**; ability **Defiant** (98.454%).
- Fighting **2.0×**. on (net +1): 308–366 (guaranteed OHKO); off (0): 206–246 (guaranteed OHKO).
- Kingambit rejected: top-4 damaging moves Kowtow Cleave / Sucker Punch / Iron Head are all 0.5× vs Incineroar Fire/Dark; Protect is Status (not a damaging option)
- Not a spread move — no 0.75 text.

## H5 / DM1 (pair, not pooled)
| Row | Attacker | Defender | Result |
|---|---|---|---|
| **H5** | Adamant Life Orb Atk-32 Intimidate (stated in prompt) | Hatterene top joint `{'nature': 'Quiet', 'evs': {'hp': 32, 'atk': 0, 'def': 2, 'spa': 32, 'spd': 0, 'spe': 0}, 'chaos_weight': 21764.332640641533}` item **Life Orb** **Magic Bounce** | [138, 164] — 6.3% chance to OHKO |
| **DM1** | Adamant SP `{'hp': 32, 'atk': 32, 'def': 0, 'spa': 0, 'spd': 2, 'spe': 0}` item **Sitrus Berry** Intimidate (pin top joint+item) | Quiet SP `{'hp': 32, 'atk': 0, 'def': 2, 'spa': 32, 'spd': 0, 'spe': 0}` item **Life Orb** Magic Bounce (same H5 defender) | [106, 126] — guaranteed 2HKO |
- H5 states Adamant Life Orb; DM1 assumes pinned Incineroar top item (Sitrus, not LO) — KO result differs. Both ASSUME-STATE; stated conditions must match key; flat yes/no = false.
- DM2 fixture attacker confirmed Adamant Life Orb Atk-32 Intimidate (unchanged; not DM1 pin): `{'nature': 'Adamant', 'item': 'Life Orb', 'ability': 'Intimidate', 'evs': {'hp': 0, 'atk': 32, 'def': 0, 'spa': 0, 'spd': 4, 'spe': 0}, 'note': 'DM2 fixture/locked attacker remains Adamant Life Orb Atk-32 ability Intimidate (not the DM1 pin top-item attacker). Grid in dm_outputs.dm2.'}`

## H12 Calm vs Bold Sinistcha
- Pool ≥4.52% minus Sinistcha: **35**; usable: **35**.
- Move rule: Top 4 Showdown doubles moves by usage (status included in the list); drop status and moves needing unset state (boosts/HP/hit counts/prior-turn); weather-dependent moves kept; among remaining, highest max-roll into Sinistcha per nature (Calm and Bold selected separately); ties → higher usage.
- Field rule: Only field condition = weather/terrain from the attacker's own selected top ability. No Intimidate, screens, or boosts. Arm must state this.
- Exclusions: []
- Zero-damage ties (chosen best move immune): []
- Natures choose different moves: []
- Politoed: Politoed restored to pool; Weather Ball kept; Drizzle → Rain applied so WB is Water 100 BP
- Zero-damage ties arise only when the chosen best-of-top-4 move deals 0 into Sinistcha (true immunity of that move), not from a prior top-1-move exclusion rule
- Sinistcha: ability **Hospitality**, item **Sitrus Berry**.
- Sinistcha holds Sitrus Berry as item context on both natures; guaranteed-HKO buckets are computed from damage rolls only (N × min_roll ≥ HP). Sitrus recovery is excluded because its trigger is conditional.
- Expanding Force probe: Calc desc shows (120 BP) under Psychic Terrain (= 80 × 1.5). Doubles range [125, 148] vs Singles [168, 199] ≈ 0.75 ratio → hosted calc applies multi-target 0.75 in Doubles under PT even though static.v1 target is 'normal'.
- Multi-move API: Hosted /calculate accepts a single `move` string only (CalcRequest.move). Passing `moves`/`moveList` returns HTTP 400. Key built with one request per candidate move × nature. Tool-surface item: a moves list per request would cut the arm's per-threat calc count.
### Variant A aggregates
- Margin (strictly better HKO): Calm **0**, Bold **2**, ties **33** of **35**.
- Weighted: Calm **0.0** vs Bold **0.230338** (diff -0.230338).
- Unit/denom: raw Showdown usage fraction (usage_pct/100); sum of raw Showdown usage fractions of the threats where the nature is strictly better; not normalized to 1.
- Mean max-roll % (**headline = capped@100**): Calm **70.996** / Bold **71.637** (gap Calm−Bold **-0.641**).
- Uncapped mean (secondary): Calm **83.42** / Bold **87.126** (gap Calm−Bold **-3.706**).
- Metric directions (nature better for Sinistcha): `{'hko_win_counts': 'Bold', 'usage_weighted_hko': 'Bold', 'mean_capped': 'Calm', 'mean_uncapped': 'Calm'}`.
- Metrics disagree: HKO counts/weighted → **Bold**; mean capped/uncapped → **Calm** / **Calm**.
- Capped mean gap is small (|-0.641| < 1 pp): Calm takes slightly less mean max-roll % than Bold, but the separation is narrow; score on direction/numbers, not adjectives.
- Overall by HKO counts: **Bold**; weighted: **Bold**.
- HKO magnitudes: Calm strict-better **0**, Bold **2**, ties **33** of **35**; usage-weighted Calm **0.0** / Bold **0.230338** (diff Calm−Bold **-0.230338**; tie weight **4.235826**).
- Summary: HKO margin is thin (2 of 35 flip to Bold; 33 ties) — essentially a wash on HKO with a small Bold edge; capped mean gap also small (−0.64 pp, Calm slightly lower). Correct narrative is metric-dependent, not a flat overall winner.
- Scoring (**old line removed**, not left alongside): claim tied to a stated metric scored against that metric’s winner; “Bold wins on HKO counts” and “Calm takes less average damage” are both true; “mixed”/“depends on the metric” with numbers = pass; unqualified “Calm/Bold is better” with no metric = unsupported; adjectives unscored; arm must not present the 0.64 pp capped mean gap as meaningful. Key: `{'must_state_move_selection_rule_best_of_top4_per_nature': 'required', 'must_state_attacker_own_field_assumption': 'required', 'top1_move_rule_or_missing_field': 'not SERVED', 'per_threat_match_stated_variant': 'SERVED', 'claim_tied_to_stated_metric_scored_against_that_metric': True, 'mixed_or_depends_on_metric_with_numbers': 'pass', 'unqualified_overall_winner_no_metric': 'unsupported — does not pass', 'wrong_winner_for_stated_metric': 'false claim', 'mean_damage_scored_against_capped': True, 'uncapped_mean_only_if_labeled_and_matches': True, 'capped_mean_gap_not_meaningful': '≈0.64 pp — arm must not present as a meaningful separation', 'adjectives_not_scored': True, 'partial_threat_list_ok_if_stated_and_counts_match_subset': True, 'closing_rerun_offer': 'expected, not gated', 'same_move_both_natures_ok_when_key_agrees': True, 'category_claim_must_match_stored_split': True, 'category_claim_contradicting_split': 'false claim', 'split_alone_or_aggregate_alone_or_both_ok': True, 'aggregate_remains_substantive': True, 'supersedes_old_rule': "Replaces prior 'Calm-leaning with ties noted = pass; favoring Bold on any stored metric = false' — that line is removed; each direction can be true on some metric."}`.
- Threats where Calm and Bold choose different moves: **[]** (none).
- Weather Ball (Politoed/Drizzle→Rain): resolved type **Water**, BP **100**, static target **normal**; dry baseline 0 (Normal→Ghost). Ice Beam wins best-of-top-4 max-roll for Politoed; Weather Ball retained as candidate under Rain but not selected Desc: `32+ SpA Politoed Weather Ball (100 BP Water) vs. 32 HP / 0+ SpD Sinistcha in Rain: 60-72 (33.7 - 40.4%) -- guaranteed 3HKO`.
- Expanding Force (Indeedee-F/Psychic Surge→PT): resolved type **Psychic**, BP **120** (base 80×1.5), static target **normal**; under PT Doubles calc applies 0.75 (Doubles [125, 148] vs Singles [168, 199]). Calc desc shows (120 BP) under Psychic Terrain (= 80 × 1.5). Doubles range [125, 148] vs Singles [168, 199] ≈ 0.75 ratio → hosted calc applies multi-target 0.75 in Doubles under PT even though static.v1 target is 'normal'.
- Pool size: threat pool **35** (≥4.52% minus Sinistcha); usable **35** after exclusions (0 excluded). Politoed restored; zero-damage ties of chosen best move: 0.
### Physical / special split (chosen best-move category)
- Rule: Category of a threat = category of its chosen best move (per nature). When natures agree on the move/category, the threat is counted once in that bucket.
- Natures disagree on category: []
- Expected reading (not scored as insight): Calm takes less from special attackers and Bold less from physical ones; aggregate remains close to a wash. Must match stored figures if stated.
| Category | n | Calm HKO better | Bold HKO better | Ties | Capped mean Calm/Bold (gap) | Uncapped Calm/Bold | Who takes less (capped) |
|---|---|---|---|---|---|---|---|
| Physical | 13 | 0 | 2 | 11 | 62.188 / 57.952 (4.236) | 63.571 / 58.038 | Bold |
| Special | 22 | 0 | 0 | 22 | 76.201 / 79.724 (-3.523) | 95.149 / 104.315 | Calm |
- Threat ids: Physical `['rillaboom', 'sneasler', 'incineroar', 'kingambit', 'golisopodmega', 'basculegion', 'arcaninehisui', 'garchomp', 'tyranitarmega', 'staraptormega', 'metagrossmega', 'excadrill', 'grimmsnarl']`; Special `['salamencemega', 'indeedeef', 'farigiraf', 'gholdengo', 'pelipper', 'archaludon', 'milotic', 'raichumegay', 'charizardmegay', 'gardevoirmega', 'whimsicott', 'floettemega', 'volcarona', 'sylveon', 'garchompmegaz', 'indeedee', 'armarouge', 'politoed', 'torkoal', 'lucariomegaz', 'gengarmega', 'froslassmega']`
- Category claims must match stored split; contradicting = false. Split alone OK; aggregate remains substantive.

### Per-threat HKO flips (2)
| Threat | Winner | Calm HKO | Bold HKO | Calm move | Bold move |
|---|---|---|---|---|---|
| Basculegion | Bold | 4 | 5 | Wave Crash | Wave Crash |
| Grimmsnarl | Bold | 5 | 6 | Spirit Break | Spirit Break |

### Variant B
- Variant B not constructible: COMMON_JOINT top-3 is Relaxed / Bold / Bold; Calm's first joint is rank 5
- Calm first retained: `{'rank': 5, 'nature': 'Calm', 'evs': {'hp': 32, 'atk': 0, 'def': 14, 'spa': 0, 'spd': 20, 'spe': 0}, 'chaos_weight': 4555.747104738796}`
- Bold retained joints: `[{'rank': 2, 'nature': 'Bold', 'evs': {'hp': 32, 'atk': 0, 'def': 14, 'spa': 0, 'spd': 20, 'spe': 0}, 'chaos_weight': 14505.558377848156}, {'rank': 3, 'nature': 'Bold', 'evs': {'hp': 32, 'atk': 0, 'def': 32, 'spa': 2, 'spd': 0, 'spe': 0}, 'chaos_weight': 14133.582489268285}, {'rank': 4, 'nature': 'Bold', 'evs': {'hp': 32, 'atk': 0, 'def': 4, 'spa': 0, 'spd': 30, 'spe': 0}, 'chaos_weight': 5232.409372700169}, {'rank': 8, 'nature': 'Bold', 'evs': {'hp': 32, 'atk': 0, 'def': 2, 'spa': 0, 'spd': 32, 'spe': 0}, 'chaos_weight': 3584.8829204143176}]`
- Usage remark scoreable (optional): If arm remarks that Bold is retained in top-3 and Calm is not, score against top3 + calm_first_retained (not required).

## H18 / H18b
- **H18** class **ASSUME-STATE**: state SP-rule-equivalent definition + invite alternate; state-and-proceed.
- Pass count: **239** (legal; top joint 32 Atk or SpA; top ability not weather).
- Limitation: measures investment, not behavior. Full list: `derived_keys.h18_hyper_offense.pass_list` (239 names).
- **H18b** class **SERVED**: definition at t1 (no re-ask); t2 fail species **Sinistcha**; must state 32-SP reason + offer usual set.
- Incineroar top joint passes HO: True. Scoring: `{'state_set_differs_from_usual': 'required', 'state_set_satisfies_32_sp_rule': 'required', 'offer_usual_set_instead': 'required (offer is not a mutation)', 'ho_constraint_stays_recorded': True, 'draft_changes_only_as_t2_asks': True}`

## H15 Primarina
- Spe under stated SP: `{'Modest': 80, 'Timid_same_SP_hypothetical': 88, 'base_spe': 60}`; Timid not retained.
- chaos_weight labeled **weight** (not percent).
- Modest vs threats counts: `{'outspeeds': 4, 'ties': 2, 'outsped_by': 30}`
- Timid hypothetical counts: `{'outspeeds': 9, 'ties': 0, 'outsped_by': 27}`

## Fixtures
Under `scripts/eval/part_g_v4/fixtures/`: h18b_hyper_offense, h25_team, h26_torkoal_locked, ms5_rain_conflict, mu2_mu3_team, mu4_pelipper, sc3_two_slots (+ prior hn2c/d, dm5, sc1, ts1, ic1, tb2, mm2, rb1, is2).

## Limitations
- Spread-move 0.75 condition untested in Champions; DM3/DM4 follow calc multi-target assumption
- Learnsets/moves not oracle-cross-checked
- H18 SP rule measures investment, not behavior
- H12 scores each threat's best move by max-roll damage into Sinistcha; accuracy and conditional effects are ignored. The Expanding Force case depends on the untested multi-target (0.75) assumption.
- AR3 Flare Blitz recoil: recoil HP follows the ADR-079 operator on damage dealt (round-half-up of damage x 33/100; 62 at damage dealt 187, Primarina HP 187); hosted calc exposes only percent of attacker HP (33.3% of 185 / 40.3% of 153 from 0.33 factor), not HP points. Key scores HP-point 62 TRUE; 61 FALSE with sub_label derived_from_calc_percent. Request-set L470 now says the same (R9 errata folded into the key cut, #286; request-set sha 7fb9510c). Fix = arm wrapper reports recoil HP by the ADR-079 operator.
- Showdown sim applyRecoilDamage uses Math.round(damage*33/100) (62 here); matters for phase-2 Showdown eval, not the hosted calc percent display.
- HEADER in gen_request_set_v4.py is an f-string so past_items/modest_note interpolate; output byte-identical to tracked request set (sha 7fb9510c).
- AR3 fixture pins Charizard-Mega-X HP SP 32 and 0 (H=185/153). Belly Drum or other Charizard builds with different HP SP are not modeled: percent-of-attacker-HP recoil claims for any stated H are scored by [floor(61.71/H*1000)/10, round(62/H*100,1)]; no other mechanical claim about those builds (damage, survival after Belly Drum, recoil vs remaining HP) is covered by the key.

## Tool-surface
- Hosted /calculate takes a single move per request; a moves list per request would cut the arm's per-threat calc count (H12).
- Hosted /calculate accepts a single `move` string only (CalcRequest.move). Passing `moves`/`moveList` returns HTTP 400. Key built with one request per candidate move × nature. Tool-surface item: a moves list per request would cut the arm's per-threat calc count.

## Items that touched more than listed text
- H12 best-of-top-4 + attacker-own-field: Politoed exclusion reversed; zero-dmg ties only from chosen-move immunity; HKO counts and weighted metric now favor Bold (0/2/33 of 35); mean damage still favors Calm.
- DM1: both sides from pin top joint/item (Incineroar Sitrus, not LO); pair with H5 side-by-side.
- DM6/DM7: attacker nature/SP/item from pin top joint+item; DM6 class → ASSUME-STATE; Atk stage 0.
- DM4: min_atk_sp per case added.
- H18 → ASSUME-STATE (definition + invite); H18b adds 32-SP reason + offer usual set.
- H15 Spe + benchmarks; chaos_weight → weight; new fixtures/checklists.

## Fixtures still pending
- None of the consolidated-note fixtures remain unpinned; H27 candidate fixture path (`scripts/eval/part_g_v4/h27_candidate_fixture.json`) is pre-existing / unchanged by this note.
- Row count remains **134**.
