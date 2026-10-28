# Final re-triage of not-covered rows (corrected 2026-10-28)

Against the final tool set. **Vu 2026-10-28** added OL7a, H27, IX5, IX7 to covered; H22 keep-out (default). Source: `part0_retriage_final.json`.

## Correction — H19 / H20

`coverable_now` was wrongly flipped to **yes** because a scripted trajectory treated a nonempty `find_species` pool as a pass. That contradicts `LAST_H19_H20_NOT_COVERED.md` (06db302): a nonempty pool is **not** a pass; `show_candidates` refuses an empty team; checklist item 1 has no route from bootstrap empty. Tools unchanged since that decision. **Restored `coverable_now: false`** with the bootstrap-empty blocker.

## Vacuous trajectories (find_species / no_lookup_needed)

| row | trajectory | proves | does not prove | vacuous for class scorer? |
|---|---|---|---|---|
| H12 | `no_lookup_needed` | abstention recorded | Calm/Bold claim content (19 cells) | **yes** |
| H21 | `no_lookup_needed` | ASSUME-STATE abstention | membership correctness (no frozen checklist) | **yes** |
| H22 | `no_lookup_needed` | ASSUME-STATE abstention | aesthetic checklist items | **yes** |
| H19 | `find_species(Trick Room)` | learnset pool (n=60) | checklist item 1 candidates/locks | yes (and not coverable) |
| H20 | `find_species(Electric)` (+constraint) | Electric pool / constraint record | checklist item 1 presented slots | yes (and not coverable) |
| IX5 | `find_species(ability=…)` ×4 | holders enumerable | ASSUME-STATE definition + set-scoring | no* (hand audit; Vu covered) |
| IX7 | `find_species` type/ability | EQ-safe pools | stated safe-definition | no* (hand audit; Vu covered) |
| H27 | `read_pending` + `get_typing` | CS fixture + Ground typing | explanation quality | no* (hand audit; Vu covered) |
| OL7a | `select_option(Jolteon)` | CS→FBC bind | — | no (mechanical; Vu covered) |

\*Hand-audit rows: class scorer only checks mechanical class; auditor checks content. Vu accepted tool-backed hand routes for IX5/IX7/H27.

## Current not-covered (31) — one line each

See also `LAST_NOT_COVERED_REASONS.md` (registration). Table of all rows (incl. now-covered) remains in `part0_retriage_final.json`.

| id | coverable_now | blocker (exact) | scorable |
|---|---|---|---|
| H12 | no | Vu keep-out: 19-cell claim surface; `no_lookup_needed` vacuous for class scorer | hand audit |
| H17 | no | `show_candidates` needs `all_locked` incl. role; empty bootstrap | hand audit |
| H18 | no | HO checklist needs 32-SP slots; `show_candidates` blocked without `all_locked` | hand audit |
| H19 | no | bootstrap empty — checklist item 1 no route; `find_species` pool ≠ pass | hand audit |
| H20 | no | bootstrap empty — checklist item 1 no route; `find_species` pool ≠ pass | hand audit |
| H21 | no | Vu keep-out: no frozen checklist; `no_lookup_needed` vacuous | hand audit |
| H22 | no | Vu keep-out (default): aesthetic ASSUME-STATE; `no_lookup_needed` vacuous | hand audit |
| H25 | no | fixture not `all_locked` → `show_candidates` refuses | hand audit |
| H26 | no | same as H25 | hand audit |
| MT4 | no | `show_candidates` exists; CS seed has 0 `all_locked` anchors | mechanical |
| MT7 | no | permanent DEV | hand audit |
| MT8 | no | permanent DEV | hand audit |
| AR1 | no | keep out (MT7 t1 dup) | hand audit |
| AR2 | no | keep out (Pareto-t2 dup) | hand audit |
| AR3 | no | 6-turn Mega-X compound not built | hand audit |
| SC1 | no | `sc1_start.json` not in `_SLOT_BASE`; draft-condition unwired | mechanical |
| SC3 | no | `sc3_two_slots.json` not in `_SLOT_BASE` | mechanical |
| TS1 | no | `ts1_sequence.json` unwired; no draft-retain | mechanical |
| GT1 | no | no VGCPastes / usage-moves surface | hand audit |
| LZ1 | no | no common_moves tool | hand audit |
| IX2 | no | no Showdown interaction tool (Pain Split / Magic Guard) | hand audit |
| IX3 | no | `flags.v1` slicing not on `get_move_static` | hand audit |
| IX4 | no | Good as Gold / Mold Breaker multi-step interaction not in arm tools | hand audit |
| IX6 | no | no Unburden×White Herb interaction tool | hand audit |
| DM5 | no | `dm5_working_draft.json` not in `_SLOT_BASE` | hand audit |
| OL7b | no | FBC omits `provisional_slot` → `select_option` refuses | mechanical |
| OL10a | no | CS staleness undetectable | not scorable |
| OL10b | no | provisional null; select refuses | mechanical |
| OL1 | no | FBC no `provisional_slot` | mechanical |
| OL2a | no | FBC no `provisional_slot` | mechanical |
| OL3 | no | label bind + no provisional | mechanical |

## Now covered (Vu add)

| id | bucket |
|---|---|
| OL7a | scorable-mechanical |
| H27 | hand audit |
| IX5 | hand audit |
| IX7 | hand audit |
