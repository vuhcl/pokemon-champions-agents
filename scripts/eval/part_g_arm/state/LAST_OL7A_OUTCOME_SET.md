# OL7a outcome_sets fix (2026-10-28)

Removed `class_cells.OL7a → MUTATION-OK`. Added `outcome_sets.OL7a`:

```json
{"accepted": [{"kind": "bind", "species": "Jolteon"}, {"kind": "ask"}], "other_bind": "fail"}
```

`class_scorer.score_outcome_set` + `errata_read.outcome_set`. Spe 200 = bind-target identity, **not** a dual hand point → stays mechanical-only (41/59/3; form 74/242 unchanged).

## After fix

| outcome | observed | pass/fail |
|---|---|---|
| (a) select Jolteon | bound | **PASS** (outcome=bind) |
| (b) ask, no mutate | lookup only | **PASS** (outcome=ask) |
| (c) select other | bound | **FAIL** (other_bind) |

Reference trajectories: **41/41**. Tests: `test_ol7a_outcome_set.py` (3).
