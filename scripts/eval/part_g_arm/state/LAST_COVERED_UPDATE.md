# Covered-list update (Vu 2026-10-28) — item 1

H22: **keep out** (Vu default). No freeze.

## Counts

| | value |
|---|---|
| covered / not_covered | **103 / 31** |
| `covered_list.json` sha256 | `ebde0d0ad9acdd51d477b7aeab039e6494bf3081b96b22c666fedf313243c4c1` |
| mechanical only | **41** (was 40; +OL7a) |
| hand audit only | **59** (was 56; +H27, IX5, IX7; MT2/H6 already hand) |
| dual | **3** (MS5, RB1, TB2) |
| mechanical incl dual | 44 |
| hand incl dual | 62 |
| audit form sections / cells | **74 / 242** |
| OL7a on form? | **no** (scorable-mechanical only) |

Form math: freeze baseline 71/232 + H27 (1×1) + IX5 (1×5) + IX7 (1×4). Acceptance `;`-split + H11 errata point unchanged. Generator method same as `LAST_B1_REFRESH` / `LAST_FREEZE_CONFIRM`.

## Added

| row | bucket |
|---|---|
| OL7a | scorable-mechanical |
| H27 | hand audit |
| IX5 | hand audit |
| IX7 | hand audit |

## Kept out (Vu)

H12 (19-cell claim surface; vacuous `no_lookup_needed`), H19/H20 (bootstrap empty), H21 (no frozen checklist), H22 (default keep out), OL7b (no provisional_slot), IX4 (interaction gap).

## Errata

`stale_pin_rows`: **[]** (MT2/H6 removed). H25 substitution left. sha256 `905f66de16fdfa4c3062750e6f0851f1427c8e1888dc76903afc06423eb6ae02`.

## Changed-file shas

| file | sha256 |
|---|---|
| `covered_list.json` | `ebde0d0ad9acdd51d477b7aeab039e6494bf3081b96b22c666fedf313243c4c1` |
| `errata.json` | `905f66de16fdfa4c3062750e6f0851f1427c8e1888dc76903afc06423eb6ae02` |
| `b1_discovery.json` | `ea95a6cef2068450ba4bf3c59a60d48b2730d095cf7788407a515ce6f09db52f` |
| `part0_retriage_final.json` | (see git; H19/H20 restored) |

## Not-covered reasons (31)

One line each — see `LAST_NOT_COVERED_REASONS.md` (item 4). Summary in `LAST_RETRIAGE_FINAL.md`.

## H19/H20 retriage flip

Prior final retriage set `coverable_now: yes` because the trajectory script treated a nonempty `find_species` pool as a pass. Restored to **false** per `LAST_H19_H20_NOT_COVERED.md` (06db302). Vacuous trajectories marked for H12/H21/H22.
