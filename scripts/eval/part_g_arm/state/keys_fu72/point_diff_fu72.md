# FU72 point diff (old acceptance ';'-split ↔ new structured points)

## DM2
- pass_criteria_changed: False
- old_point_count: 2
- new_point_count: 3

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: EXPAND: full numeric grid per Hatterene COMMON_JOINT cell in derived_keys.dm_outputs.dm2. Locked fixture attacker = Adamant Life Orb Atk-32 ability Intimidate (confirmed
- `p2`: not the DM1 pin top-item attacker).

### New t1 (rewrite=True)
- `p1` [tool-backed]: Use the locked attacker from read_team: Adamant Life Orb Atk-32 Intimidate (not the DM1 pin top-item attacker).
- `p2` [tool-backed]: Expand the full numeric damage grid for every Hatterene COMMON_JOINT cell in derived_keys.dm_outputs.dm2.
- `p3` [tool-backed]: Look up Hatterene item and ability (Incineroar usage calls optional). The Hatterene item stated or used must be Life Orb, or faithful to the get_usage_items result received.

### Mapping (old → new) — required when pass_criteria unchanged
- `p1` → `t1.p1`, `t1.p2`
- `p2` → `t1.p1`, `t1.p3`

## DM6
- pass_criteria_changed: False
- old_point_count: 6
- new_point_count: 7

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: ASSUME-STATE. Gallade-Mega Inner Focus + Galladite
- `p2`: nature/SP/item from top Showdown joint+item (Jolly SP {'hp': 2, 'atk': 32, 'def': 0, 'spa': 0, 'spd': 0, 'spe': 32} item Galladite
- `p3`: source=showdown_doubles Gallade-Mega top retained joint (COMMON_JOINT[0])). Close Combat (Fighting 2.0× vs Fire/Dark). Single case attacker Atk stage 0 (no Intimidate drop). Key: 270–318 (guaranteed OHKO). Arm must state attacker nature/SP/item matching key
- `p4`: mismatch → not SERVED
- `p5`: numbers with no stated attacker conditions → false claim
- `p6`: −1 or second case → false. Not a spread move. dm_outputs.dm6

### New t1 (rewrite=True)
- `p1` [tool-backed]: ASSUME-STATE: Gallade-Mega with Inner Focus and Galladite.
- `p2` [tool-backed]: Attacker nature/SP/item from the top Showdown joint (Jolly Spe-32 / Atk-32, Galladite, COMMON_JOINT[0]).
- `p3` [tool-backed]: Move is Close Combat (Fighting 2.0× into Fire/Dark Incineroar). Single case at Atk stage 0 (no Intimidate drop).
- `p4` [tool-backed]: Key damage range is 270–318 (guaranteed OHKO).
- `p5`: Arm must state attacker nature/SP/item matching the key; mismatch is not SERVED.
- `p6`: Numbers with no stated attacker conditions are a false claim.
- `p7`: A −1 range or a second (Intimidate) case is false. Not a spread move.

### Mapping (old → new) — required when pass_criteria unchanged
- `p1` → `t1.p1`
- `p2` → `t1.p2`
- `p3` → `t1.p2`, `t1.p3`, `t1.p4`, `t1.p5`
- `p4` → `t1.p5`
- `p5` → `t1.p6`
- `p6` → `t1.p7`

## GS1
- pass_criteria_changed: True
- old_point_count: 7
- new_point_count: 5

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: t1 SERVED modal (MIR/SB/Protect/Nasty Plot
- `p2`: Life Orb). t2 MUTATION-OK Scarf+read-back
- `p3`: LO released
- `p4`: name every status move in actual t1 draft (flags.v1 category==Status) as unusable under Scarf lock
- `p5`: offer attack swaps
- `p6`: no silent move change
- `p7`: no refusal. Part 0 choice-lock hand rule (no blob field). derived_keys.row_c_gholdengo_scarf

### New t1 (rewrite=True)
- `p1` [tool-backed]: Complete, legal Gholdengo build (item, ability, nature, SP spread, four moves), tool-backed: each field comes from a tool result in the turn (usage tools, check_learnset and legality checks, or the synthesis path through set_slot). Any such build passes. Stating a source is not a separate requirement of this point; if the reply cites a usage figure, the usual labeling rule applies (Showdown is never called in-game). If the reply pairs a nature with an in-game spread, it must not present that pairing as a measured joint (get_usage_spreads rank-pairs nature with spread).
- `p2` [tool-backed]: Draft via set_slot (or featured path); no lock_fields unless asked.

### New t2 (rewrite=True)
- `p1` [tool-backed]: MUTATION-OK: apply Choice Scarf; Life Orb released; read back.
- `p2` [tool-backed]: Name every Status move in the actual t1 draft as unusable for damage under Scarf; do not flag status moves that still do something under Scarf (e.g. Trick).
- `p3`: Offer attack swaps; no silent move change; no refusal.

## H15
- pass_criteria_changed: False
- old_point_count: 5
- new_point_count: 4

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: Modest top joint SP={'hp': 32, 'atk': 0, 'def': 0, 'spa': 32, 'spd': 2, 'spe': 0} chaos_weight pct≈8876.7
- `p2`: label chaos_weight as **weight** (not % — presenting as percent = false). Spe under stated SP: Modest 80, Timid hypothetical 88. Benchmark lists in derived_keys.h15_primarina.benchmarks. Verdict: Modest default SERVED when basis stated (only retained joint
- `p3`: Timid not retained) + speed tradeoff mentioned
- `p4`: conditional Timid OK with named key benchmark
- `p5`: 'Timid is better' with no benchmark / fabricated Timid joint = false.

### New t1 (rewrite=True)
- `p1` [tool-backed]: Modest top joint SP is hp32/atk0/def0/spa32/spd2/spe0 with chaos_weight ≈8876.7; label chaos_weight as weight, not percent (presenting it as % is false).
- `p2` [tool-backed]: Spe under the stated SP: Modest 80, Timid hypothetical 88 (benchmarks in derived_keys.h15_primarina.benchmarks).
- `p3`: Verdict: Modest default is SERVED when the basis is stated (only retained joint; Timid is not retained) and the speed tradeoff is mentioned.
- `p4`: Conditional Timid is OK only with a named key benchmark. 'Timid is better' with no benchmark or a fabricated Timid joint is false.

### Mapping (old → new) — required when pass_criteria unchanged
- `p1` → `t1.p1`
- `p2` → `t1.p1`, `t1.p2`
- `p3` → `t1.p3`
- `p4` → `t1.p4`
- `p5` → `t1.p4`

## H18b
- pass_criteria_changed: False
- old_point_count: 2
- new_point_count: 7

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: Binary checklist H18b: t1 establishes definition (no re-ask at t2)
- `p2`: t2 Sinistcha fails top-joint SP rule — supply passing set (lookup/synth), state differs from usual + exists to satisfy 32-SP rule, offer usual set (not a mutation), constraint kept. Incineroar top joint passes — not the fail case.

### New t1 (rewrite=True)
- `p1`: Establish the hyper-offense definition (every locked/drafted slot has 32 SP in Atk or SpA).
- `p2`: Do not re-ask for the definition on later turns.

### New t2 (rewrite=True)
- `p1` [tool-backed]: Sinistcha's top joint fails the 32-SP Atk/SpA rule.
- `p2` [tool-backed]: Supply a passing set (usage lookup or synthesis) that satisfies the 32-SP rule.
- `p3`: State that the passing set differs from the usual Sinistcha set and exists to satisfy the constraint.
- `p4`: Offer the usual set as well (offer only — not a mutation).
- `p5`: Keep the hyper-offense constraint. Incineroar's top joint passes and is not the fail case.

### Mapping (old → new) — required when pass_criteria unchanged
- `p1` → `t1.p1`, `t1.p2`
- `p2` → `t2.p1`, `t2.p2`, `t2.p3`, `t2.p4`, `t2.p5`

## H6
- pass_criteria_changed: True
- old_point_count: 3
- new_point_count: 2

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: unordered `{Incineroar,Garchomp,Sneasler,Gholdengo,Raichu}`
- `p2`: set-scoring
- `p3`: must label **in-game** source

### New t1 (rewrite=True)
- `p1` [tool-backed]: Unordered set {Incineroar, Sneasler, Garchomp, Raichu, Kingambit}; set-scoring.
- `p2`: Must label in-game source.

## H8
- pass_criteria_changed: True
- old_point_count: 2
- new_point_count: 3

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: **No** (Item Clause)
- `p2`: **no-mutation check**

### New t1 (rewrite=True)
- `p1`: Outcome: Item Clause → No.
- `p2`: No mutation.
- `p3` [tool-backed]: Required step: describe (or equivalent rules lookup). no_lookup_needed is NOT an alternative; a correct answer from memory can pass outcome and fail the required step.

## HC1
- pass_criteria_changed: True
- old_point_count: 5
- new_point_count: 3

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: Snapshot: no legal Water∧Fire species
- `p2`: state unsatisfiable as written
- `p3`: record nothing
- `p4`: must not apply either / silently pick one
- `p5`: option-offer OK only if nothing recorded until pick

### New t1 (rewrite=True)
- `p1` [tool-backed]: Recognise the two constraints (all Water and all Fire) leave an empty pool (verify with find_species types Water and Fire → count 0).
- `p2`: Either record both constraints, or record nothing — both accepted — as long as the empty-pool recognition is clear.
- `p3`: Must not silently apply only one constraint or pick a species from an empty pool.

## HC2
- pass_criteria_changed: True
- old_point_count: 4
- new_point_count: 4

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: Separate conflicting requests
- `p2`: ask resolve
- `p3`: no guess
- `p4`: no state change until user picks

### New t1 (rewrite=True)
- `p1`: Treat the turn as separate conflicting requests.
- `p2`: Ask the user to resolve which constraint wins.
- `p3`: Do not guess which constraint to keep.
- `p4`: No state change until the user picks.

## HN2b
- pass_criteria_changed: False
- old_point_count: 5
- new_point_count: 5

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: Full forward grid in derived_keys.hn2b_forward_grid (COMMON_SPEED distinct
- `p2`: Scarf = 2 lines only
- `p3`: TW extras)
- `p4`: control HN2 (156>149 at max)
- `p5`: pair not pooled

### New t1 (rewrite=True)
- `p1` [tool-backed]: Full forward grid from derived_keys.hn2b_forward_grid (COMMON_SPEED distinct cells).
- `p2`: Scarf lines: two only.
- `p3`: Tailwind extras are included in the grid.
- `p4` [tool-backed]: Control HN2: Annihilape outspeeds Gholdengo at max (156 > 149).
- `p5`: Pair is not pooled with HN2.

### Mapping (old → new) — required when pass_criteria unchanged
- `p1` → `t1.p1`
- `p2` → `t1.p2`
- `p3` → `t1.p3`
- `p4` → `t1.p4`
- `p5` → `t1.p5`

## HN3
- pass_criteria_changed: False
- old_point_count: 3
- new_point_count: 3

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: COMMON_ITEM (ingame): Life Orb 42.4, Glimmoranite 28.0, Focus Sash 26.9 (cum≥90% at 3, cum 97.3)
- `p2`: 'nothing' counts toward slots and 90% cutoff when present
- `p3`: label in-game

### New t1 (rewrite=True)
- `p1` [tool-backed]: COMMON_ITEM (ingame): Life Orb 42.4, Glimmoranite 28.0, Focus Sash 26.9 (cum≥90% at 3, cum 97.3).
- `p2`: 'nothing' counts toward slots and the 90% cutoff when present.
- `p3`: Label the source as in-game.

### Mapping (old → new) — required when pass_criteria unchanged
- `p1` → `t1.p1`
- `p2` → `t1.p2`
- `p3` → `t1.p3`

## HP3
- pass_criteria_changed: True
- old_point_count: 2
- new_point_count: 2

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: Refuse illegal mutation
- `p2`: state unchanged

### New t1 (rewrite=True)
- `p1` [tool-backed]: Rule B: either a lookup that supports the refusal, or a write attempt whose validator refusal the reply recognises and cites (illegal mutation).
- `p2`: Outcome by rubric: the illegal write does not land; team state matches the refusal outcome.

## HU2
- pass_criteria_changed: True
- old_point_count: 4
- new_point_count: 2

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: EXPLICIT CONTROL paired with HU2b
- `p2`: outspeeds set `{Incineroar,Kingambit,Golisopod}`
- `p3`: set-scoring
- `p4`: label in-game

### New t1 (rewrite=True)
- `p1` [tool-backed]: Outspeeds set {Kingambit, Incineroar} among in-game top-10 at Spe-32 + Spe-boosting nature; set-scoring.
- `p2`: Label in-game source.

## HU2b
- pass_criteria_changed: True
- old_point_count: 6
- new_point_count: 4

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: Paired with HU2 (in-game lineage top10
- `p2`: not pooled). ASSUME-STATE: threats = shared Showdown per-form set ≥4.52% (showdown_threats_ge_452
- `p3`: n=36
- `p4`: megas are separate ThreatCandidates — e.g. Salamence-Mega not base). max Spe=Timid Spe-32 (128)
- `p5`: max_speed role+share as HN2b
- `p6`: core_non_max for outspeeds_any

### New t1 (rewrite=True)
- `p1` [tool-backed]: The arm picks N for get_meta_threats and states it. Any N is accepted when the stated N matches the call.
- `p2` [tool-backed]: The threat set reasoned over is exactly the list that call returns for that N, labeled as the in-game list. Naming a threat not in the returned list fails.
- `p3` [tool-backed]: Pelipper's max Spe is Timid Spe-32 = 128 (from get_speed).
- `p4` [tool-backed]: List which threats in the returned list Pelipper outspeeds at max Spe (and which it does not), each against that threat's Spe from a tool. Megas are separate entries where the list has them. Keep the HN2b convention: mark max_speed role and share; use core_non_max for outspeeds_any.

## HU3
- pass_criteria_changed: False
- old_point_count: 4
- new_point_count: 4

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: Option list 3–5 Fire
- `p2`: per-option bulk reason
- `p3`: ask which
- `p4`: slot unchanged until selection

### New t1 (rewrite=True)
- `p1` [tool-backed]: Option list of 3–5 bulky Fire types for slot 3.
- `p2`: Each option has a bulk reason.
- `p3`: Ask which option to take.
- `p4`: Slot unchanged until selection.

### Mapping (old → new) — required when pass_criteria unchanged
- `p1` → `t1.p1`
- `p2` → `t1.p2`
- `p3` → `t1.p3`
- `p4` → `t1.p4`

## IC1
- pass_criteria_changed: False
- old_point_count: 2
- new_point_count: 2

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: t1 SERVED Leftovers (Psychic Seed+Rocky Helmet excluded by Item Clause). t2 MUTATION-OK Sitrus Berry with read-back
- `p2`: Leftovers released. Trap: suggesting Seed/Helmet. Moves not keyed. derived_keys.row_a_corviknight

### New t1 (rewrite=True)
- `p1` [tool-backed]: SERVED Corviknight with Leftovers (Psychic Seed + Rocky Helmet excluded by Item Clause).

### New t2 (rewrite=True)
- `p1` [tool-backed]: MUTATION-OK different item (e.g. Sitrus) with read-back; Leftovers released. Trap: Seed/Helmet.

### Mapping (old → new) — required when pass_criteria unchanged
- `p1` → `t1.p1`, `t2.p1`
- `p2` → `t2.p1`

## IS1
- pass_criteria_changed: True
- old_point_count: 4
- new_point_count: 8

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: See derived_keys.is1_min_spe: per Dragapult cell, bare + Scarf outcomes
- `p2`: N=0 → no investment needed
- `p3`: bare max 169 unreachable vs every Dragapult cell
- `p4`: Scarf+TW stack reachability-only

### New t1 (rewrite=True)
- `p1`: State which Dragapult COMMON_SPEED cell(s) are assumed, or state that max-speed investment is assumed for the opponent (that assumption is itself a scoring point).
- `p2` [tool-backed]: If no max-speed assumption is stated, call get_common_speeds (or equivalent) for Dragapult's common cells.
- `p3` [tool-backed]: For each assumed cell: state whether a bare (no Scarf) Spe investment can outspeed it, or that the cell is unreachable bare. Spe 0 counts as the minimum when it already outspeeds.
- `p4` [tool-backed]: Give a tool-backed Spe number (solve_spread, or get_speed on the stated spread) that outspeeds the cell under the stated assumption.
- `p5` [tool-backed]: State the outcome vs budget: fits, shortfall, or unreachable. Scarf and Scarf+Tailwind are reachability notes only.
- `p6`: Never say the investment is 'not recommended'.
- `p7` [conditional] [tool-backed]: CONDITIONAL (score only if the arm claims a stated SP is the minimum): for each assumed cell, neutral-nature minimum Spe SP is the offline minimum (cells [213, 194, 190]; see is_minima_fu72.json IS1).
- `p8` [conditional] [tool-backed]: CONDITIONAL: beneficial-nature (Jolly) minimum Spe SP per assumed cell matches the offline minimum.

## IS2
- pass_criteria_changed: True
- old_point_count: 4
- new_point_count: 6

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: PARTIAL+ASSUME-STATE. derived_keys.is2_min_spe: Dragapult COMMON_SPEED 213/194/190 at Scarf+1
- `p2`: Jolly Spe needs 32/21/19
- `p3`: R=24 → 194+190 fit, 213 short by 8 SP (budget-only
- `p4`: 213 reachable at Spe-32). max Spe at R=24 = 201. Arm must state assumed cells + unbeatable cell + shortfall.

### New t1 (rewrite=True)
- `p1`: State the assumed Dragapult cell(s), or state a max-speed assumption for Dragapult.
- `p2` [tool-backed]: If no assumption, call get_common_speeds for Dragapult.
- `p3` [tool-backed]: Read the locked Basculegion (Jolly + Choice Scarf, Spe budget R=24) via read_team.
- `p4` [tool-backed]: Per cell: state the Jolly+Scarf Spe investment that outspeeds (tool-backed), and whether it fits within R=24 or the shortfall.
- `p5`: Never say 'not recommended'.
- `p6` [conditional] [tool-backed]: CONDITIONAL (if a minimum is claimed): the stated Spe SP equals the offline Jolly+Scarf minimum for that cell (is_minima_fu72.json IS2).

## IS3
- pass_criteria_changed: True
- old_point_count: 6
- new_point_count: 7

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: 4-part min-SP
- `p2`: Slowbro max stack Spe=270 vs Dragapult Timid-32=213
- `p3`: vs max-speed Dragapult reachable only under Scarf+TW stack
- `p4`: Showdown Slowbro COMMON_ITEM has **no Choice Scarf** in retained list (0 recorded Scarf share)
- `p5`: state min required + recorded usage
- `p6`: never 'not recommended'

### New t1 (rewrite=True)
- `p1`: State the assumed Dragapult cell(s) or a max-speed assumption.
- `p2` [tool-backed]: Tool-backed Spe number that outspeeds under the stated assumption.
- `p3` [tool-backed]: Max-speed Dragapult cell is reachable only under Scarf + Tailwind; state that reachability.
- `p4` [tool-backed]: State recorded Scarf usage on Slowbro: none in the retained COMMON_ITEM list.
- `p5`: Never say 'not recommended'.
- `p6` [conditional] [tool-backed]: CONDITIONAL: claimed neutral-nature minimum matches offline Scarf+TW minimum for the max cell.
- `p7` [conditional] [tool-backed]: CONDITIONAL: claimed beneficial-nature minimum matches offline Scarf+TW minimum for the max cell.

## IS4
- pass_criteria_changed: True
- old_point_count: 7
- new_point_count: 6

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: Prompt requires Mega
- `p2`: 4-part min-SP
- `p3`: Pincurchin max stack=218 < Alakazam-Mega Timid-32=222 → **unreachable** vs max cell even under Scarf+TW
- `p4`: no Spe-boosting move
- `p5`: state min required / unreachable
- `p6`: no invented SP
- `p7`: never 'not recommended'

### New t1 (rewrite=True)
- `p1`: The prompt requires Mega Alakazam (not base).
- `p2`: State the Mega Alakazam target cell (Timid Spe-32) or a max-speed assumption.
- `p3` [tool-backed]: Pincurchin's max Spe under Scarf + Tailwind is 219, below Mega Alakazam Timid-32 (222); unreachable even under Scarf + Tailwind.
- `p4`: Pincurchin has no Spe-boosting move that changes this reachability.
- `p5`: State unreachable (no invented Spe SP that claims to outspeed the max cell).
- `p6`: Never say 'not recommended'.

## IX1
- pass_criteria_changed: False
- old_point_count: 4
- new_point_count: 4

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: Fake Out priority 3 > Follow Me 2 (and Rage Powder same class)
- `p2`: FAIL if recommends Follow Me/Rage Powder as counter
- `p3`: PASS = Fake Out outprioritizes redirect or valid non-redirect counters
- `p4`: assume counter=redirect|block

### New t1 (rewrite=False)
- (no intended pass-criteria change; structure-only or unchanged)
- `p1`: Fake Out priority 3 > Follow Me 2 (and Rage Powder same class)
- `p2`: FAIL if recommends Follow Me/Rage Powder as counter
- `p3`: PASS = Fake Out outprioritizes redirect or valid non-redirect counters
- `p4`: assume counter=redirect|block

### Mapping (old → new) — required when pass_criteria unchanged
- `p1` → `t1.p1`
- `p2` → `t1.p2`
- `p3` → `t1.p3`
- `p4` → `t1.p4`

## IX5
- pass_criteria_changed: False
- old_point_count: 5
- new_point_count: 5

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: Assume punish=blocked|reflected|boosted
- `p2`: set rule
- `p3`: separate buckets
- `p4`: verify holders vs legality
- `p5`: set-scoring

### New t1 (rewrite=False)
- (no intended pass-criteria change; structure-only or unchanged)
- `p1`: Assume punish=blocked|reflected|boosted
- `p2`: set rule
- `p3`: separate buckets
- `p4`: verify holders vs legality
- `p5`: set-scoring

### Mapping (old → new) — required when pass_criteria unchanged
- `p1` → `t1.p1`
- `p2` → `t1.p2`
- `p3` → `t1.p3`
- `p4` → `t1.p4`
- `p5` → `t1.p5`

## IX7
- pass_criteria_changed: False
- old_point_count: 4
- new_point_count: 4

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: safe=no damage: Flying / Levitate / Telepathy / Earth Eater
- `p2`: examples+counts with source label
- `p3`: resist≠safe unless definition says so
- `p4`: set matches stated definition

### New t1 (rewrite=False)
- (no intended pass-criteria change; structure-only or unchanged)
- `p1`: safe=no damage: Flying / Levitate / Telepathy / Earth Eater
- `p2`: examples+counts with source label
- `p3`: resist≠safe unless definition says so
- `p4`: set matches stated definition

### Mapping (old → new) — required when pass_criteria unchanged
- `p1` → `t1.p1`
- `p2` → `t1.p2`
- `p3` → `t1.p3`
- `p4` → `t1.p4`

## MM1
- pass_criteria_changed: True
- old_point_count: 3
- new_point_count: 3

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: Build with Salamencite
- `p2`: state mega cannot hold another item
- `p3`: offer keep stone or base form+Leftovers (form change = offer only). Stone map from Showdown items.ts (standalone). legality.py has no mega-stone check — open arm tool item. derived_keys.row_g_h_salamence_mega

### New t1 (rewrite=True)
- `p1` [tool-backed]: Build Salamence holding Salamencite.
- `p2`: State that a mega cannot hold another item.
- `p3`: Offer keep-stone or base form + Leftovers (form change is offer-only).

## MM2
- pass_criteria_changed: True
- old_point_count: 3
- new_point_count: 3

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: Refuse: stone is required mega item
- `p2`: draft unchanged
- `p3`: form change offer only. derived_keys.row_g_h_salamence_mega

### New t1 (rewrite=True)
- `p1`: Refuse: the mega stone is the required mega item.
- `p2`: Draft unchanged.
- `p3`: Form-change offer only.

## MR1
- pass_criteria_changed: True
- old_point_count: 2
- new_point_count: 2

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: Refuse illegal species
- `p2`: state unchanged

### New t1 (rewrite=True)
- `p1` [tool-backed]: Rule B: either a lookup that supports the refusal, or a write attempt whose validator refusal the reply recognises and cites (illegal species).
- `p2`: Outcome by rubric: the illegal write does not land; team state matches the refusal outcome.

## MR2
- pass_criteria_changed: True
- old_point_count: 2
- new_point_count: 2

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: Refuse illegal item
- `p2`: state unchanged

### New t1 (rewrite=True)
- `p1` [tool-backed]: Rule B: either a lookup that supports the refusal, or a write attempt whose validator refusal the reply recognises and cites (illegal item (Choice Specs on Hatterene)).
- `p2`: Outcome by rubric: the illegal write does not land; team state matches the refusal outcome.

## MR3
- pass_criteria_changed: True
- old_point_count: 2
- new_point_count: 2

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: Species Clause
- `p2`: state unchanged

### New t1 (rewrite=True)
- `p1` [tool-backed]: Species Clause applies (second Incineroar).
- `p2`: State unchanged after the refusal.

## MR4
- pass_criteria_changed: True
- old_point_count: 2
- new_point_count: 3

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: Item Clause
- `p2`: state unchanged

### New t1 (rewrite=True)
- `p1`: Apply Choice Scarf to the first mon as asked (item field is unlocked in the FU72 seed).
- `p2` [tool-backed]: Rule B / Item Clause: the second Scarf is refused; the reply recognises and cites the validator refusal (or a clause lookup).
- `p3`: No second Scarf applied and no other field touched (rewritten 'state unchanged').

## MR5
- pass_criteria_changed: False
- old_point_count: 2
- new_point_count: 2

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: refuse/ask
- `p2`: state unchanged

### New t1 (rewrite=True)
- `p1`: Refuse or ask (occupied slot).
- `p2`: State unchanged.

### Mapping (old → new) — required when pass_criteria unchanged
- `p1` → `t1.p1`
- `p2` → `t1.p2`

## MR6
- pass_criteria_changed: True
- old_point_count: 2
- new_point_count: 2

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: empty unlock refuse
- `p2`: state unchanged

### New t1 (rewrite=True)
- `p1`: Empty unlock: accept a no-op or an explicit refusal.
- `p2`: State unchanged.

## MR7
- pass_criteria_changed: True
- old_point_count: 2
- new_point_count: 2

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: nothing pending
- `p2`: state unchanged

### New t1 (rewrite=True)
- `p1`: Nothing is pending to commit.
- `p2`: State unchanged.

## MR8
- pass_criteria_changed: True
- old_point_count: 2
- new_point_count: 2

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: illegal
- `p2`: state unchanged

### New t1 (rewrite=True)
- `p1` [tool-backed]: Refuse the illegal species (Koraidon).
- `p2`: State unchanged.

## MS1
- pass_criteria_changed: False
- old_point_count: 1
- new_point_count: 1

### Old (mechanical ';'-split of request-set acceptance)
- `acceptance`: Read-back: slot2 species=Garchomp locked=true

### New t1 (rewrite=False)
- (no intended pass-criteria change; structure-only or unchanged)
- `acceptance`: Read-back: slot2 species=Garchomp locked=true

### Mapping (old → new) — required when pass_criteria unchanged
- `acceptance` → `t1.acceptance`

## MS2
- pass_criteria_changed: True
- old_point_count: 1
- new_point_count: 3

### Old (mechanical ';'-split of request-set acceptance)
- `acceptance`: Read-back: slot1 unlocked / empty

### New t1 (rewrite=True)
- `p1` [tool-backed]: Call unlock_slot (or equivalent) on slot 1.
- `p2`: Under unlock_keeps_values: attribute values remain; locks are cleared. The old 'empty slot' expectation does not apply.
- `p3`: Read-back states slot 1 unlocked with prior values kept.

## MS5
- pass_criteria_changed: True
- old_point_count: 5
- new_point_count: 4

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: MUTATION-OK with conflict audit: apply archetype + read-back, then audit locked slots
- `p2`: report each conflict with reason
- `p3`: do not edit locked (offers only). Conflicts: Drought (non-rain weather ability) + Solar Beam (rain-reduced)
- `p4`: control Pelipper not flagged. Both flags required. Locked unchanged
- `p5`: offered replacements legal. Fixture: Charizard-Mega-Y + Charizardite Y + Solar Beam + control.

### New t1 (rewrite=True)
- `p1` [tool-backed]: MUTATION-OK: apply the rain-offense archetype and read it back.
- `p2`: Audit locked slots and report each conflict with a reason. Required conflicts: Drought (non-rain weather ability) and Solar Beam (rain-reduced).
- `p3`: Control Pelipper is not flagged. 'Flagged' means an entry in the change_archetype conflicts field.
- `p4`: Both required conflict flags must appear. Locked slots stay unchanged; offered replacements must be legal.

## MS8
- pass_criteria_changed: False
- old_point_count: 1
- new_point_count: 1

### Old (mechanical ';'-split of request-set acceptance)
- `acceptance`: Read-back Pelipper s1 locked

### New t1 (rewrite=False)
- (no intended pass-criteria change; structure-only or unchanged)
- `acceptance`: Read-back Pelipper s1 locked

### Mapping (old → new) — required when pass_criteria unchanged
- `acceptance` → `t1.acceptance`

## MT1
- pass_criteria_changed: True
- old_point_count: 1
- new_point_count: 3

### Old (mechanical ';'-split of request-set acceptance)
- `acceptance`: Both constraints in t3 read-back

### New t1 (rewrite=True)
- `p1` [tool-backed]: Record a Water-only constraint on slot 1.

### New t2 (rewrite=True)
- `p1` [tool-backed]: Record the additional no-Intimidate constraint.

### New t3 (rewrite=True)
- `p1` [tool-backed]: Read-back shows both constraints active (Water-only on slot 1, and no Intimidate).

## MT2
- pass_criteria_changed: True
- old_point_count: 4
- new_point_count: 3

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: t2 unordered `{Charizard,Garchomp,Sneasler}`
- `p2`: set-scoring
- `p3`: label in-game
- `p4`: t3 Pelipper

### New t1 (rewrite=True)
- `p1` [tool-backed]: Lock Pelipper into a slot as asked; state reflects the lock.

### New t2 (rewrite=False)
- (no intended pass-criteria change; structure-only or unchanged)
- `p1` [tool-backed]: Unordered set ['Sneasler', 'Charizard', 'Garchomp']; set-scoring; label in-game source.

### New t3 (rewrite=True)
- `p1`: Confirm slot 1 is Pelipper.

## MT3
- pass_criteria_changed: True
- old_point_count: 2
- new_point_count: 6

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: Binary checklist MT3 (Fire required
- `p2`: Intimidate → flag)

### New t1 (rewrite=True)
- `p1` [tool-backed]: Record the No-Intimidate constraint (t1).

### New t2 (rewrite=True)
- `p1` [tool-backed]: Suggest a Fire-typed species for slot 2; tool-backed (find_species or usage path).
- `p2`: Asking instead of suggesting Fire is not an accepted path.

### New t3 (rewrite=True)
- `p1`: The t3 reply itself answers yes or no for the t2 pick (or picks one of several Fire types / asks which — both accepted).
- `p2` [tool-backed]: Ability lookup in this turn backs the answer even if t2 already mentioned Intimidate. 'Has Intimidate' = species can have it as a legal ability.
- `p3` [tool-backed]: If the pick can have Intimidate: flag against the t1 constraint and offer ≥1 tool-backed alternative (different Fire pick, or a non-Intimidate legal ability on the same species). Silent acceptance or flag-with-no-alternative fails.

## MT5
- pass_criteria_changed: True
- old_point_count: 1
- new_point_count: 3

### Old (mechanical ';'-split of request-set acceptance)
- `acceptance`: Archetype string in t3 read-back

### New t1 (rewrite=True)
- `p1` [tool-backed]: Apply the rain-offense archetype as asked.

### New t2 (rewrite=True)
- `p1` [tool-backed]: Offer a rain-setter candidate for the open slot (tool-backed species or build suggestion).

### New t3 (rewrite=True)
- `p1` [tool-backed]: Read-back includes the rain-offense archetype string.

## MT6
- pass_criteria_changed: True
- old_point_count: 4
- new_point_count: 5

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: t1 = HC1 behavior (unsatisfiable as written
- `p2`: record nothing)
- `p3`: t2 resolves to Water only
- `p4`: t3 Water-only read-back

### New t1 (rewrite=True)
- `p1` [tool-backed]: Same empty-pool recognition as HC1 (Water∧Fire).
- `p2`: Either record both constraints or record nothing; both accepted if empty-pool is recognised.

### New t2 (rewrite=True)
- `p1` [tool-backed]: Resolve to Water only: drop Fire (set_constraint_active / restore / add Water as applicable).
- `p2`: Do not stack another Fire constraint.

### New t3 (rewrite=True)
- `p1` [tool-backed]: Confirm constraints: Water-only read-back.

## MU1
- pass_criteria_changed: False
- old_point_count: 5
- new_point_count: 5

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: NO-MUTATION
- `p2`: claims scored
- `p3`: state unchanged
- `p4`: no lock/commit. Required claim: Item Clause blocks both holding Choice Scarf (Garchomp/Jolteon/Choice Scarf legal in pin). Other claims scored if made
- `p5`: variants must be legal.

### New t1 (rewrite=True)
- `p1`: NO-MUTATION class.
- `p2`: Claims are scored.
- `p3`: State unchanged; no lock or commit.
- `p4`: Required claim: Item Clause blocks both holding Choice Scarf (Garchomp / Jolteon / Choice Scarf legal in the pin).
- `p5`: Other claims scored if made; variants must be legal.

### Mapping (old → new) — required when pass_criteria unchanged
- `p1` → `t1.p1`
- `p2` → `t1.p2`
- `p3` → `t1.p3`
- `p4` → `t1.p3`, `t1.p4`
- `p5` → `t1.p5`

## MU2
- pass_criteria_changed: False
- old_point_count: 3
- new_point_count: 3

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: NO-MUTATION
- `p2`: claims scored. Any species named as Water must be Water and legal
- `p3`: mechanical statements match typing/calc. Fixture: slot 2 open + locked team/item for non-trivial clause checks.

### New t1 (rewrite=True)
- `p1`: No team mutation.
- `p2`: Any species the arm names as Water is Water and legal.
- `p3`: Mechanical statements match typing and calc.

### Mapping (old → new) — required when pass_criteria unchanged
- `p1` → `t1.p1`
- `p2` → `t1.p2`
- `p3` → `t1.p3`

## MU4
- pass_criteria_changed: True
- old_point_count: 4
- new_point_count: 4

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: NO-MUTATION
- `p2`: claims scored. Yes/no/conditional with ≥1 tool-backed reason (Drizzle + explicit ability, usage, legality/clauses, state)
- `p3`: each reason scored
- `p4`: bare yes/no = fail. Fixture: Pelipper unlocked + interacting locked slot.

### New t1 (rewrite=True)
- `p1`: NO-MUTATION class.
- `p2` [tool-backed]: Answer yes / no / conditional with at least one tool-backed reason (Drizzle + explicit ability, usage, legality/clauses, or state).
- `p3`: Each reason is scored.
- `p4`: Bare yes/no without a tool-backed reason fails.

## MU6
- pass_criteria_changed: True
- old_point_count: 2
- new_point_count: 3

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: No reset tool
- `p2`: state unchanged

### New t1 (rewrite=True)
- `p1`: Do not call reset_team (hypothetical).
- `p2`: Explain what reset_team would clear (counterpart MS3: what would be lost) without writing.
- `p3`: State unchanged.

## MU8
- pass_criteria_changed: True
- old_point_count: 2
- new_point_count: 2

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: No archetype/lock tools
- `p2`: state unchanged

### New t1 (rewrite=True)
- `p1`: No archetype or lock write tools are used.
- `p2`: State unchanged.

## MV3
- pass_criteria_changed: True
- old_point_count: 1
- new_point_count: 6

### Old (mechanical ';'-split of request-set acceptance)
- `acceptance`: Required: Rock Slide targets all adjacent foes (both opponents in doubles). Required caveat: accuracy 90% (gen9_accuracy 4eeb96ea…) so either/both can avoid. 'always hits both'/'can't miss' = false. Targeting correct with no accuracy = not SERVED. Optional: each target rolls accuracy separately (scored if made). 0.75 damage claim dropped (unverified). derived_keys.mv3_rock_slide

### New t1 (rewrite=True)
- `p1` [tool-backed]: Rock Slide targets all adjacent foes (both opponents in doubles).
- `p2` [tool-backed]: Required caveat: accuracy 90% (gen9_accuracy pin), so either or both can miss.
- `p3`: Claims that it always hits both, or cannot miss, are false.
- `p4`: Targeting correct with no accuracy caveat is not SERVED.
- `p5`: Optional (scored if made): each target rolls accuracy separately.
- `p6`: A 0.75 damage claim is dropped (unverified).

## MW3
- pass_criteria_changed: True
- old_point_count: 2
- new_point_count: 2

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: Ask slot
- `p2`: no state change

### New t1 (rewrite=True)
- `p1`: Ambiguity: which slot 'the slot I mentioned' refers to; ask. Off-topic questions fail.
- `p2`: No state change until the slot is resolved.

## OL4
- pass_criteria_changed: True
- old_point_count: 3
- new_point_count: 3

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: **not** deterministic bind
- `p2`: ask confirm
- `p3`: state unchanged until confirmation

### New t1 (rewrite=True)
- `p1`: Ambiguity to resolve: whether the user wants the pending option confirmed/set as draft vs locked in.
- `p2`: Accepted: confirm or set a draft. Locking it in is not accepted. Off-topic questions fail.
- `p3`: State unchanged until confirmation.

## OL5
- pass_criteria_changed: False
- old_point_count: 1
- new_point_count: 1

### Old (mechanical ';'-split of request-set acceptance)
- `acceptance`: Bound Garchomp

### New t1 (rewrite=False)
- (no intended pass-criteria change; structure-only or unchanged)
- `acceptance`: Bound Garchomp

### Mapping (old → new) — required when pass_criteria unchanged
- `acceptance` → `t1.acceptance`

## OL6
- pass_criteria_changed: True
- old_point_count: 2
- new_point_count: 2

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: Ask
- `p2`: unchanged

### New t1 (rewrite=True)
- `p1`: Ambiguity to resolve: which referent / action the user means; ask. Off-topic questions fail.
- `p2`: State unchanged.

## OL7a
- pass_criteria_changed: False
- old_point_count: 1
- new_point_count: 1

### Old (mechanical ';'-split of request-set acceptance)
- `acceptance`: Verifiably faster=Jolteon (Spe 200)

### New t1 (rewrite=False)
- (no intended pass-criteria change; structure-only or unchanged)
- `acceptance`: Verifiably faster=Jolteon (Spe 200)

### Mapping (old → new) — required when pass_criteria unchanged
- `acceptance` → `t1.acceptance`

## OL9
- pass_criteria_changed: True
- old_point_count: 2
- new_point_count: 2

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: Ask
- `p2`: not applied

### New t1 (rewrite=True)
- `p1`: Ambiguity: multi-select vs which single option. Off-topic questions fail.
- `p2`: Accepted: multi-select or ask which. Not applied until resolved.

## Q10
- pass_criteria_changed: True
- old_point_count: 2
- new_point_count: 2

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: Explains empty unlock
- `p2`: no mutation

### New t1 (rewrite=True)
- `p1`: Explains empty unlock.
- `p2`: No mutation.

## Q9
- pass_criteria_changed: True
- old_point_count: 2
- new_point_count: 3

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: **No** (Species Clause)
- `p2`: no mutation

### New t1 (rewrite=True)
- `p1`: Outcome: Species Clause → No.
- `p2`: No mutation.
- `p3` [tool-backed]: Required step: describe (or equivalent rules lookup). no_lookup_needed is NOT an alternative; a correct answer from memory can pass outcome and fail the required step.

## RB1
- pass_criteria_changed: True
- old_point_count: 6
- new_point_count: 3

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: MUTATION-OK with stated consequence: apply+read-back
- `p2`: state Calm Mind+Nasty Plot are Status self-boosters sharing SpA
- `p3`: Calm Mind also +SpD (kept only via CM)
- `p4`: offer swap one out
- `p5`: no silent remove. Key from stat_boosts.v1.json: CM +1 spa +1 spd
- `p6`: NP +2 spa. Damaging self-boosts do not count. derived_keys.row_j_calm_mind_nasty_plot

### New t1 (rewrite=True)
- `p1` [tool-backed]: read_team first (current moveset / room).
- `p2`: Under sticky_locks: the write is refused with atomic field_locked; Nasty Plot is not applied; existing values unchanged.
- `p3`: Calm Mind / Nasty Plot boost-overlap consequence is scored only if a write is allowed; under sticky refusal it is not required.

## TB1
- pass_criteria_changed: False
- old_point_count: 3
- new_point_count: 4

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: SERVED with stated correction: build as asked but state Charcoal has no effect (no legal damaging Fire move
- `p2`: Status like Will-O-Wisp does not count)
- `p3`: offer other items. Silent acceptance = fail. Type-boost table standalone from pinned items. derived_keys.row_e_charcoal_sinistcha

### New t1 (rewrite=True)
- `p1` [tool-backed]: SERVED: draft a Sinistcha build holding Charcoal as asked.
- `p2` [tool-backed]: State that Charcoal has no effect because Sinistcha has no legal damaging Fire move (Status moves such as Will-O-Wisp do not count).
- `p3`: Offer other items. Silent acceptance of Charcoal with no correction fails.
- `p4`: Type-boost table is standalone from pinned items (derived_keys.row_e_charcoal_sinistcha).

### Mapping (old → new) — required when pass_criteria unchanged
- `p1` → `t1.p1`, `t1.p2`
- `p2` → `t1.p2`
- `p3` → `t1.p3`, `t1.p4`

## TB2
- pass_criteria_changed: True
- old_point_count: 4
- new_point_count: 4

### Old (mechanical ';'-split of request-set acceptance)
- `p1`: MUTATION-OK with stated consequence: apply swap+read-back
- `p2`: state Charcoal no longer boosts
- `p3`: offer keep/swap item
- `p4`: no silent item change. Warn only if no remaining damaging move of item type on set. derived_keys.row_f_incineroar_charcoal

### New t1 (rewrite=True)
- `p1` [tool-backed]: read_team for the current moveset.
- `p2` [tool-backed]: Swap Flare Blitz for Darkest Lariat (legal per check_learnset); apply and read back.
- `p3`: State that Charcoal no longer boosts (consequence / type-boost vs remaining damaging moves).
- `p4`: Offer keep or swap item; no silent item change.

## Unchanged pass criteria with fewer new points than old
- H15: new=4 < old=5; map=p1→['t1.p1']; p2→['t1.p1', 't1.p2']; p3→['t1.p3']; p4→['t1.p4']; p5→['t1.p4']

