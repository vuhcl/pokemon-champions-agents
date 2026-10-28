# H19 / H20 → not_covered (bootstrap empty)

Decision rule: nonempty `find_species` pool is **not** a pass. Same bootstrap-empty gate as H17/H18. `show_candidates` refuses an empty team.

## H19 — Trick Room setters only

| # | checklist item | tool route from empty team? |
|---|---|---|
| 1 | Presents TR-setter-focused candidates or locks | **No.** `show_candidates` refuses empty; `lock_slot` alone is not “presents candidates.” `find_species(learns_move=Trick Room)` returns a pool, not a candidate_selection screen or locks. |
| 2 | Non-setters absent or labeled out-of-scope | **No route** without a presentation path (depends on item 1). |
| 3 | No invented TR learnsets (learnset or compendium role; key records which) | **Partial.** `find_species` / `check_learnset` cover learnset. Key is learnset-only today; compendium-role TR setters without the move have **no** learnset tool route. |
| 4 | Legality checked for named species | **Yes.** `check_species_legal` / legality snapshot. |

**Decision: not_covered** — item 1 has no route from empty team.

## H20 — Mono-Electric doubles

| # | checklist item | tool route from empty team? |
|---|---|---|
| 1 | Every presented/locked slot species is Electric | **No.** Needs presented/locked slots. `show_candidates` refuses empty. `find_species(types=[Electric])` is a pool only. |
| 2 | Constraint acknowledged in read-back or presentation | **Partial.** `add_constraint` can record a type must-have from empty; presentation still blocked. |
| 3 | No non-Electric slipped in unlabeled | **No route** without presentation (depends on item 1). |
| 4 | Legality checked | **Yes.** Legality tools. |

**Decision: not_covered** — item 1 has no route from empty team.

## Covered list

Moved `H19`, `H20` from `covered` → `not_covered` in `covered_list.json`. Did not decide by a model run.
