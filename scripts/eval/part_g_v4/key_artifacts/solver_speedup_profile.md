# Spread solver Step 0 profile (2026-10-11 / live run)

Live run: tmux `mt7mt8ar`, pid 27340, started `2026-10-11T20:15:52Z`.
**Not killed** for this profile. Calc pin: `@smogon/calc 0.11.0-champions.5d5bf43` via `http://127.0.0.1:4173`.

## Live progress (log + probes)

| Item | Value |
|------|------:|
| Elapsed (at profile) | ~5.1 h |
| CPU | ~97% of one core (single Python process, no children) |
| Logical cores available | 14 |
| Log stage | `MT8 t4 drop Spe gate...` (in progress; stages through `MT8 t4 Jolly+Weather Ball` done) |
| `probe_*.json` written since start | ~587k (~1.4 GB earlier sample at ~538k) |
| Overall probe write rate | ~30.4 /s |
| Last-10-min rate | ~21 /s |
| Est. remaining wall (slow path @ ~30/s) | ~12–14 h (nospe remainder + AR2; see below) |
| Full MT7/MT8/AR est. at slow rate | ~18–20 h |

Completed stages (from log): MT7 t1/t2/t3, MT8 t3 Modest (False), MT8 t3 Timid WB, MT7 t3 Timid FT, MT8 t4 Jolly WB.

## How calcs are made

- Path: Python `calc_store.calculate` → HTTP `POST /calculate` (one move per request).
- Not in-process for the live run.
- Disk-first: if `key_artifacts/calc/{id}.json` exists, return it (no HTTP).
- In-memory `_CACHE` keyed by full request JSON (includes nature name).
- **`persist=False` is ignored** — every miss still `write_text` of indented JSON (~2.5 KB/file). Search uses `artifact_id="probe"` → `probe_<sha16>`.

### HTTP latency (n=20 unique, while live run busy)

| | ms |
|--|---:|
| mean | 0.29 |
| p50 | 0.29 |
| min | 0.23 |
| max | 0.42 |

Disk JSON load of an existing probe: ~0.03 ms. HTTP is **not** the bottleneck; probe write volume + single-threaded Python search is.

## Search shape (`search_conditions`)

Per nature in `ALL_NATURES` (25):

1. Spe fixed at gate min (or 0 if ungated); budget `rem = 66 - spe`.
2. **Full grid** over `hp ∈ 0..32`, `def ∈ 0..32` with `hp+def ≤ rem` (not a Spe ladder).
3. Per cell: **binary search** min SpD in `0..min(32, rem-hp-def)` such that all conditions survive (`max(damage) < defender HP`).
4. `_ok` short-circuits on first failing condition (2-condition stages skip move 2 when move 1 fails).

| Grid | Cells |
|------|------:|
| Speed-gated (Spe≥110), all natures | 26,579 |
| Ungated (spe=0), per nature | 1,089 (×25 = 27,225) |

| Stage (est. binary SpD iters ≈ 5.19/cell × n_cond) | Est. calcs (upper) |
|--|--:|
| MT7 t1 / t2 (1 cond, gated) | ~138k each |
| Each 2-cond gated stage | ~276k |
| MT8 t4 drop Spe (2 cond, ungated) | ~300k |
| AR2 pareto (6 class natures, HP×Def + binary SpD) | ~33k |
| **Sum upper bound** | **~2.0M** |

Unique probes this run (~587k after ~5 h) are below the sum because of disk reuse across stages (shared Adamant CC cells), `_ok` short-circuit, and binary-search variance. Effective unique-write rate ≈ 30/s.

`ar3_derive.min_atk_for_ohko` still does a **linear** Atk SP scan `0..32` (separate from MT7 grid).

## Cache / identical effective stats

- First-run **request-hash** hit rate among a 5k sample of this run’s probes: **0** duplicate request keys (each probe file unique).
- Memory cache helps only within-process exact request repeats.
- Collapsing the five neutral natures (Hardy/Docile/Serious/Bashful/Quirky) on the same 5k sample: **20 / 5000** (~0.4%) would share identical effective stats; calc_store does **not** collapse neutrals, so those still miss.
- Neutral class can share identical (HP,Def,SpD,Spe) survival outcomes; the solver still enumerates all five natures (by design for class counts).

## Bottleneck ranking (for speedup)

1. Always-on probe JSON writes (~30 files/s × indent) on the search path.
2. Single-process nature loop (14 cores idle).
3. Full HP×Def enumeration where large infeasible regions exist (staircase helps hard stages more than MT7 t1).
4. Per-call HTTP/JSON (small vs 1–2; in-process still wins when probe I/O is off).

## Resume note (live slow run)

Do not kill pid 27340 / tmux `mt7mt8ar`. When it finishes, compare `solver_runs/mt7_mt8_ar_live.json` to the fast-path output (expect 0 differences on completed stages; full MT7/MT8 when both done).

## Fast-path resume (Step 4)

```bash
PART_G_V4_CALC_BACKEND=inprocess \
PART_G_V4_CALC_IGNORE_DISK=1 \
PART_G_V4_SOLVER_WORKERS=6 \
PART_G_V4_SOLVER_CHECKPOINT_DIR=scripts/eval/part_g_v4/key_artifacts/solver_runs/ckpt_fast \
python3 -u scripts/eval/part_g_v4/key_artifacts/solver_runs/run_mt7_mt8_ar_fast.py
```

Per-stage nature rows append to `{prefix}_cells.jsonl` under the checkpoint dir. Re-run the same command to resume. Delete `ckpt_fast/` for a clean start.

Linear baseline (old full HP×Def grid): `PART_G_V4_SOLVER_LINEAR=1`.

## Projected E2E (after Step 0–4)

| Path | MT7 t1 wall | Full MT7/MT8/AR (est.) |
|------|------------:|-----------------------:|
| Slow (live, HTTP + always-write probes, 1 core) | ~0.5–1 h (implied by ~5 h / ~7 stages) | ~18–20 h |
| Fast (in-process, persist=False on search, binary SpD, 4 workers) | **~4 s** (MT7 t1) | **48.9 s** full MT7/MT8/AR vs live **5.37 h** (`FINISH.json` / `FINISH_fast.json`) |

### Step 1 note — staircase caveat

Defender bulk is monotone when HP/Def/SpD are raised independently. Under a shared SP budget, `spd_hi = min(32, rem−hp−df)` falls as HP/Def rise, so “exists SpD ≤ spd_hi” is **not** monotone in HP for fixed Def (holes observed on MT7 t3 Bold). Default search therefore keeps the full HP×Def grid + binary SpD; `PART_G_V4_SOLVER_STAIRCASE=1` is opt-in only. Atk-SP OHKO binary search (AR3) is unaffected.

Validation: `solver_speedup_validation.json` — AR3 602 files / 30 key rows, in-process vs HTTP n=1000 seed=42, fast vs linear SpD cells n=200 seed=7 (0 diffs). Re-compare full live vs fast after default-grid regen.

## In-process vs hosted /calculate — pin refresh

The n=1000 (seed=42) in-process vs HTTP check is sufficient for the current pin
`@smogon/calc 0.11.0-champions.5d5bf43`. **Re-run that sample (and the AR3 / MT7
gates) against hosted `/calculate` after the Oct 19–20 pin refresh** (new calc
build under `vendor/smogon-calc`); do not treat the old sample as covering a new
pin.

`persist=False` on spread-solver search probes is intentional and matches the
probe persistence policy: `probe_*` files from the solver are regenerated live
and are not committed.
