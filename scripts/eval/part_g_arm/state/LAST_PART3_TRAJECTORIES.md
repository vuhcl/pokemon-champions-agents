# Part 3 — reference trajectories (no model)

Script: `reference_trajectories.py` → `part3_reference_trajectories.json`.

`class_scorer`: MUTATION-OK now accepts `recorded` (MS7 / OL8 reject paths).

## Mechanical covered (42)

| metric | n |
|---|---|
| pass | **36** |
| unexpected fail | **0** |
| capability gap | **6** |

### Capability gaps → needs tool X

| row | missing |
|---|---|
| MS6 | **add_constraint (4b)** |
| MR2 | **edit_slot_field (4a)** (item lock refuse Choice Specs) |
| MR4 | **edit_slot_field (4a)** (Item Clause on two Scarves) |
| OL1 | FBC provisional wire in pending loader (fixture has options, no `provisional_slot`) |
| OL2a | FBC provisional wire + suffix/label select (CLI `2` ≠ ordinal 2) |
| OL3 | label-select + FBC provisional wire |

OL1/OL2a/OL3 are **not** in the Part 4 build list; report only. Part 4a/4b close MS6/MR2/MR4. Re-run this check after Part 4; gaps that remain move to not-covered at freeze.

### Sample passing trajectories

| row | trajectory | observed | key |
|---|---|---|---|
| MS1 | lock_slot(2, Garchomp) | wrote | MUTATION-OK |
| MS4 | commit_slot() | wrote | MUTATION-OK |
| MS7 | reject_option(2) | recorded | MUTATION-OK |
| MS8 | lock_slot(1, Pelipper) | wrote | MUTATION-OK |
| MR1 | lock_slot(1, Flutter Mane) | refused | MUTATION-REFUSED |
| OL2b | select_option(2) | bound | MUTATION-OK |
| OL5 | select_option(1) | bound | MUTATION-OK |
| OL8 | reject_all() | recorded | MUTATION-OK |
| HC2 | no_lookup_needed (ask) | lookup only | ASK |
| MU1 | check_hypothetical two Scarves | lookup only | NO-MUTATION |

Full table in `part3_reference_trajectories.json`.

## Hand-audit covered — fact reachability

Rows where a needed fact is **not** reachable from current tools (11):

H11, H19, H20, MT1, MT5, MT6, HU1, HU3, MV1, IC1 (t2), TB1

Part 4 may close: MT1/MT6 (4b), MV1 (4h), IC1 t2 (4a), HU3/H20 (4c), MT5 (4f), TB1 (4a consequence). H11/H19/HU1 may stay hand-audit gaps.

One line each for the rest: see `hand_audit` array in the JSON (get_typing / get_speed / calc_damage / …).
