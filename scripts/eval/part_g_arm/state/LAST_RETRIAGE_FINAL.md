# Final re-triage of 35 not-covered rows (2026-10-28)

Against the final tool set (incl. `find_species`+ability, `check_learnset`, `show_candidates`, `edit_slot_field`, constraints, move priority, mega-stone). **No covered-list change.** Source: `part0_retriage_final.json`.

`coverable_now_ids`: H12, H19, H20, H21, H22, H27, IX5, IX7, OL7a.

| id | coverable_now | blocker (exact) | scorable | seed / fixture route (no OL/v4/H27 edits) |
|---|---|---|---|---|
| H12 | yes | nothing | hand audit | seed needed: `'attackers undefined'` → `empty_team`; `calc_damage` exists |
| H17 | no | `show_candidates` needs `all_locked` incl. role; `edit_slot_field` cannot set role; empty bootstrap | hand audit | `empty_team` loads |
| H18 | no | HO checklist needs progressing 32-SP slots; `show_candidates` blocked without `all_locked` | hand audit | `empty_team` loads |
| H19 | yes | nothing | hand audit | `find_species(learns_move='Trick Room')` (n=60); `empty_team` |
| H20 | yes | nothing | hand audit | `find_species(types=['Electric'])` + `add_constraint`; `empty_team` |
| H21 | yes | nothing | hand audit | ASSUME-STATE membership; **no frozen checklist**; `empty_team` |
| H22 | yes | nothing | hand audit | **frozen checklist H22** (4 items) in request set; ASSUME-STATE; `empty_team` |
| H25 | no | fixture not `all_locked` → `show_candidates` refuses | hand audit | v4 fixture loads; incomplete for candidates |
| H26 | no | same as H25 (Torkoal) | hand audit | v4 fixture loads; incomplete |
| H27 | yes | nothing | hand audit | `load_fixture('H27')` CS; top Ground = Garchomp via `get_typing` |
| MT4 | no | `show_candidates` exists; CS seed has **0** `all_locked` anchors (not “missing tool”) | mechanical | `seeds/cs_pending.json` loads |
| MT7 | no | permanent DEV | hand audit | `empty_team` |
| MT8 | no | permanent DEV | hand audit | `empty_team` |
| AR1 | no | keep out (MT7 t1 dup) | hand audit | `empty_team` |
| AR2 | no | keep out (Pareto-t2 dup) | hand audit | `empty_team` |
| AR3 | no | 6-turn Mega-X compound not built | hand audit | `empty_team` only |
| SC1 | no | `sc1_start.json` not in `_SLOT_BASE`; draft-condition unwired (`check_learnset` ok for Snarl) | mechanical | v4 fixture present; needs state `_SLOT_BASE` |
| SC3 | no | `sc3_two_slots.json` not in `_SLOT_BASE`; condition unwired | mechanical | v4 fixture present; needs `_SLOT_BASE` |
| TS1 | no | `ts1_sequence.json` unwired; no draft-retain across topic switch | mechanical | v4 file present; no seed |
| GT1 | no | no VGCPastes / usage-moves surface | hand audit | `empty_team` |
| LZ1 | no | no common_moves tool (mega-stone rule ≠ moveset frequencies) | hand audit | `empty_team` |
| IX2 | no | no Showdown interaction tool (Pain Split / Magic Guard) | hand audit | `empty_team` |
| IX3 | no | `flags.v1` slicing not on `get_move_static` (priority only) | hand audit | `empty_team` |
| IX4 | no | `check_learnset`/`find_species` exist; Good as Gold / Mold Breaker / Wandering Spirit multi-step interaction missing | hand audit | `empty_team` |
| IX5 | yes | nothing | hand audit | `find_species(ability=…)` per ASSUME-STATE punish buckets |
| IX6 | no | no Unburden×White Herb interaction tool | hand audit | `empty_team` |
| IX7 | yes | nothing | hand audit | `find_species` Flying / Levitate / Telepathy / Earth Eater |
| DM5 | no | `dm5_working_draft.json` not in `_SLOT_BASE` | hand audit | v4 fixture present; needs state `_SLOT_BASE` |
| OL7a | yes | nothing | mechanical | `OL7a.json` CS; `select_option(Jolteon)` → FBC with provisional |
| OL7b | no | FBC omits `provisional_slot` → `select_option` refuses (Oct-27 “coverable” stale) | mechanical | `OL7b.json` loads; needs provisional wire |
| OL10a | no | CS staleness undetectable (no presentation fingerprint) | not scorable | `OL10a.json` loads |
| OL10b | no | provisional null; select refuses; fp path incomplete | mechanical | `OL10b.json` loads |
| OL1 | no | FBC no `provisional_slot`; select cannot bind | mechanical | `OL1.json` loads |
| OL2a | no | same | mechanical | `OL2a.json` loads |
| OL3 | no | label bind + no provisional | mechanical | `OL3.json` loads |

## vs 2026-10-27
- Newly coverable: **H19, H20, IX5, IX7** (find_species).
- Still coverable: H12, H21, H22, H27, OL7a.
- Demoted: **OL7b** (provisional gap).
- Reason fixes: MT4 (anchor, not missing tool); IX4 (interaction, not missing learnset tool); DM5/SC1/SC3/TS1 (`_SLOT_BASE` / condition, not vague “not built”).
