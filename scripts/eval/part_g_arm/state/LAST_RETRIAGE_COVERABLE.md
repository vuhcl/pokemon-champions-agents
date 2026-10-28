# Coverable-now reference trajectories (2026-10-28)

No model. No covered_list change. Scorer marks these `excluded: not_covered` (expected).

| row | trajectory (summary) | pass/fail | sections | cells | seed needed |
|---|---|---|---|---|---|
| H12 | no_lookup_needed | PASS | 1 | 19 | H12 seed: state cell 'attackers undefined' → empty_team (... |
| H19 | find_species | PASS | 1 | 2 | — |
| H20 | find_species; add_constraint | PASS | 1 | 1 | — |
| H21 | no_lookup_needed | PASS | 1 | 3 | — |
| H22 | no_lookup_needed | PASS | 1 | 1 | — |
| H27 | read_pending; get_typing; get_typing; get_typing | PASS | 1 | 1 | — |
| IX5 | find_species; find_species; find_species; find_species | PASS | 1 | 5 | — |
| IX7 | find_species; find_species; find_species; find_species | PASS | 1 | 4 | — |
| OL7a | read_pending; select_option | PASS | 1 | 1 | — |

## Notes

- **H21:** no frozen checklist (acceptance says so).
- **H22:** frozen checklist H22 exists (4 items); form cells use acceptance `;`-split → 1.
- **H12:** claim surface = 19 acceptance points × 1 turn; needs empty_team seed for loader.
- **OL7a:** mechanical select Jolteon; scorer exclusion `not_covered` until Vu adds.
- Form cost if all 9 added (`;`-split): **9 sections / 37 cells**.

- H12: H12 acceptance ';'-splits to 19 points × 1 turn(s)
- H21: acceptance explicitly: No frozen checklist
- H22: form generator uses acceptance ';'-split (1 point); frozen checklist H22 has 4 rubric items in part3_request_set_v4.md
