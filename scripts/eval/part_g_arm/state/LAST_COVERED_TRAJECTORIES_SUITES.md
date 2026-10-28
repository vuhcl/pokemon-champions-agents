# Item 2 — trajectories + suites (2026-10-28)

No model run on covered rows.

## Reference trajectories

`uv run python -m scripts.eval.part_g_arm.state.reference_trajectories`

| | result |
|---|---|
| mechanical | **41/41** PASS (was 40; +OL7a with errata MUTATION-OK) |
| capability gaps | 0 |
| hand_unreachable | 0 |
| hand map | includes H27, IX5, IX7, MT2/H6 (no longer stale) |

## Suites

| step | result |
|---|---|
| calc health before | ok |
| `uv run pytest` | **4785 passed**, 14 skipped |
| `npm test` | **119 passed** |
| `run_all_checks.py` | **PASS** |
| keys sha | `e70672541b5215e7bfff7eccb34dc321b2bde3a4b9cf08d1f5a6419be1d2309a` |
| battery claim / false_legal | `6e6c6be4351240629416f1e279bbf495bbf4670d79aaaa7d083a2c62c6d67443` / `3025138427391e57a92e1862a87b0074d44a51b290836077abf094af92c4bdec` |
| calc health after | ok, then stopped |
