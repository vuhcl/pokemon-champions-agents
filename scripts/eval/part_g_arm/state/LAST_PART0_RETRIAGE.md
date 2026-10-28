# Part 0 — re-triage of 38 not-covered rows (report only)

As of 2026-10-27. Prior “not built” (2026-10-25) predated state tools, pending loader, solve_spread, seeds.

`cursor_seed_fixes_manifest.md`: **not found** (see `LAST_SEED_FIXES.md`). No seed code changed.

**Coverable-now (listed only — not added to covered):** H12, H21, H22, H27, OL7a, OL7b.

Source: `part0_retriage.json`. Regenerate table: `uv run python -m scripts.eval.part_g_arm.state.retriage_not_covered`.

| id | coverable_now | needs | scorable | reason (exact missing) |
|---|---|---|---|---|
| H12 | yes | nothing | hand audit | calc_damage + ASSUME-STATE sides already; large claim surface |
| H17 | no | tool (T4+T6) | hand audit | rain bootstrap/candidates; no arm archetype or show-candidates |
| H18 | no | tool (T4+T2/T6) | hand audit | HO definition + candidates; no archetype/candidate arm tool |
| H21 | yes | nothing | hand audit | ASSUME-STATE membership; no specialized tool |
| H22 | yes | nothing | hand audit | ASSUME-STATE aesthetic; checklist is assumption-labeled |
| H25 | no | tool (T6) | hand audit | fixture loads; needs recommender candidates + Kingambit calc |
| H26 | no | tool (T6) | hand audit | fixture loads; needs Hatterene-support candidates |
| H27 | yes | nothing | hand audit | **pending loader exists**; CS options; top Ground via get_typing |
| AR1 | no | keep out (dev dup) | hand audit | **= mt7_t1_jolly_cc** keys; recommend stay out |
| AR2 | no | keep out (dev dup) | hand audit | **ar2_pareto** sibling of MT7 t2; recommend stay out |
| AR3 | no | tool + multi-turn fixtures | hand audit | 6-turn Mega-X Belly Drum compound |
| MS5 | no | tool (T4) | mechanical | fixture loads; need archetype + conflict audit |
| SC1 | no | tool (T2) + fixture route | mechanical | draft Snarl condition; sc1_* not in `_SLOT_BASE` |
| SC2 | no | learnset/legality tool | mechanical | **Soak refuse via legality**; no learnset arm tool |
| SC3 | no | tool (T2) + fixture route | mechanical | slot-2-only condition; sc3 unwired |
| TS1 | no | draft/topic tool + fixture | mechanical | ts1_sequence unwired; no draft-retain tool |
| GS1 | no | tool (T5) | hand audit | Scarf consequence vs status moves; species-only lock_slot |
| GT1 | no | VGCPastes moves surface | hand audit | Trick+Scarf from n=2 pastes; open gap |
| LZ1 | no | usage-moves + mega lock | hand audit | no common_moves tool |
| TB2 | no | tool (T5) + fixture route | mechanical | four moves survive `read_team`; no moveset edit; Charcoal consequence |
| MM1 | no | validator (T1) + ADR | hand audit | validate_team_value allows Leftovers; no mega-stone rule |
| MM2 | no | validator (T1) | mechanical | must refuse stone→Leftovers on Mega |
| RB1 | no | tool (T5) | mechanical | add Nasty Plot; CM+NP from stat_boosts.v1.json |
| IX1 | no | expose priority | hand audit | **not** from current lookups; static has priority, tool omits |
| IX2 | no | Showdown interaction source | hand audit | key in moves.ts/abilities.ts; not in arm tools |
| IX3 | no | expose flags.v1 | hand audit | Dire Claw slicing in flags; tool omits |
| IX4 | no | learnset tool | hand audit | Good as Gold / Mold Breaker path |
| IX5 | no | ability-holder search | hand audit | **not** from check_species_ability alone |
| IX6 | no | ability+item interaction data | hand audit | conditional Unburden |
| IX7 | no | ability-holder + typing search | hand audit | Flying via get_typing only; Levitate etc. missing |
| DM5 | no | fixture route | hand audit | dm5_working_draft not in `_SLOT_BASE` |
| OL7a | yes | nothing | mechanical | **pending loader**; faster=Jolteon via get_speed |
| OL7b | yes | nothing | mechanical | **pending loader**; synthetic Spe plumbing |
| OL10a | no | **cannot** (frozen fixture) | not scorable | pending+current team only; no presentation fingerprint; CS gate cannot detect |
| OL10b | no | fixture route (provisional wire) | mechanical | fp check in commit_full_slot exists; loader leaves provisional null → “missing” not stale |
| MT4 | no | tool (T6) | mechanical | no show-candidates tool |
| MT7 | no | permanent DEV | hand audit | stay DEV |
| MT8 | no | permanent DEV | hand audit | stay DEV |

## Special checks (summary)

| check | finding |
|---|---|
| H27 / OL7a | pending loader covers both; coverable_now **yes** |
| OL10b | fingerprint check exists in `commit_full_slot`; loader does not populate `provisional_slot` from fixture fps |
| SC2 | refusal must go through legality; no learnset tool → not coverable now |
| IX1 / IX5 / IX7 | **not** answerable from existing lookup tools as shipped |
| AR1 / AR2 | near-duplicates of MT7 t1 / Pareto-t2; **recommend stay out** |
