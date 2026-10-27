# A4 — test-report reconciliation

## Trio with calc UP (confirmed)

Confirmation: `GET http://127.0.0.1:4173/health` returned `{"status":"ok"}` immediately before and after each trio run.

| tree | result |
|---|---|
| `eval/part-g-arm-state` @ `fcb46c6` | **3 passed** in ~13s |
| `main` @ `11e2322` (same calc process) | **3 passed** in ~13s |

Prior “calc UP but trio failed” on this branch was a dead/stale calc mid-suite (health empty / `calc_unavailable`), not new product failures. When calc stayed alive, the trio passes on both trees.

One-line failures when calc is actually DOWN (same signature as the known calc-dependent suite; not new failures):

1. `test_kingambit_swords_dance_stays_good` — `KeyError: 'Kingambit'` / usage path under calc-unavailable fallout (or equivalent when the client cannot complete).
2. `test_three_locked_core_slot_stays_demote_only` — `CandidateDiscoveryError(kind='calc_unavailable', ...)` asserted away (`assert 'unavailable' != 'unavailable'`).
3. `test_bench_subset_eval_on_sequential_slot_five` — same `calc_unavailable` assertion failure.

These are the calc-down / calc-unavailable dependent failures (same shape as the prior #315-era calc-down suite notes), not new arm-state regressions. With calc healthy they pass.

## Collection counts (4795 both arm-state rounds)

Default `uv run pytest` uses `pyproject.toml` `testpaths`: `tests/recommender` + `tests/ci` only.

| collect | count |
|---|---|
| branch default | **4795** |
| main default | **4773** |
| delta | **+22** = entire `tests/recommender/test_arm_state_tools.py` on the branch (0 on main) |

Solver / reproduction / forced-repair tests are **not** in the default collect:

| file (under `scripts/eval/part_g_arm/state/`) | tests | collected by default? |
|---|---|---|
| `test_solve_spread.py` | 14 | **no** — path-invoke |
| `test_forced_repair.py` | 2 | **no** |
| `test_reproduce_mt7_mt8.py` | 1 (+ nested) | **no** |

So “~30 tests added” and “4795 unchanged across rounds” are consistent: the ~16 solver-family tests live outside `testpaths`, and `test_arm_state_tools` was already present at 22 for both recent arm-state rounds. Default collected total does not move when only `state/` tests are added.
