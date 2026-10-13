# Task C — per-stat SP≤32 cap sweep (v4.2)

## Cap-less `spd_hi = rem - hp - df` (bug class)

| Location | Status | Affects committed key leaf? |
|---|---|---|
| `builders/spread_solver.py` `search_conditions` | **Fixed** (current code uses `spd_hi = min(32, rem - hp - df)` at L109 on main / equivalent on #265). Historical cap-less code produced committed v4.1 Jolly `+Def:20` / `+Spe:2` (SpD=34 cells). | Yes — was the root cause of those two leaves; corrected in v4.2 keys |
| Other builders (`ar3_*`, `dm_*`, `h12_*`, `derive_outputs`, `v4_consolidated_keys`, `speed_grid`) | No `spd_hi = rem - hp - df` pattern. Loops use `range(33)` or `min(32, …)` when clamping pin spreads. | No |

## Stale narrative (keys / notes / request set)

| Location | Text | Action in v4.2 |
|---|---|---|
| `derived_keys` `jolly_sneasler.note` (v4.1) | “works under +SpD / +Def / +Spe” | Rewritten to +SpD-only legal result |
| `derived_keys` / request-set MT8 | `+SpD 294/+Def 20/+Spe 2` | Keys fixed; **request-set text kept** (sha `fc6b150d…`); R9 errata |
| `drop_speed_gate.note` / `prior_illegal_spd34_note` | Documents SpD=34 as **prior illegal** | Kept (correct historical warning) |
| `gen_request_set_v4.py` / `part3_request_set_v4.md` L472 | cites 20/2 | Unchanged (hash discipline); fold at Oct 19–20 pin refresh |
| `unverified_descriptive.jolly_class_counts_note` | called 20/2 “UNVERIFIED” | Removed; replaced with FALSE scoring note |

## Flag (no code change needed)

- `speed_grid.py` `n_suffices > 32` compares a **count**, not an SP investment.
- Pin-spread clamps `min(32, ev)` are defensive and already correct.
