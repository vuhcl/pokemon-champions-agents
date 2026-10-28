# Repeat-run design (proposal — no covered model run)

Declared before any covered three-run: **run 1 = primary**; **runs 2 and 3 = determinism checks**. Comparison lists per-row differences beside the primary; never averaged; never replacing run 1.

## Runner support

- CLI: `--runs-root DIR --run-id {1|2|3}` → `DIR/run_N/` (isolated `progress.json`; no resume across runs).
- Legacy: plain `out_dir` still works; optional `--run-id` stamps that directory.
- Every `run_record.json`, transcript entry, and `progress.json` carries `run_id` + `role` (`primary` | `determinism`).
- Same covered row order, same `ArmConfig` / `FAILURE_POLICY` / digest gate.

## Comparison fields ([compare_runs.py](compare_runs.py))

| field | rule |
|---|---|
| mechanical class | per-turn sequence must match |
| tool calls | ordered `(name, args)` must match |
| final text | `sha256(final_text)` per turn must match |
| errors / timeout | one-sided → `status: error_mismatch` (both sides’ error strings); listed in `differ`, not a pass |

## Wall time and disk (planned)

| | estimate |
|---|---|
| Per run | **~16–20 min** at **8.4 s/turn** (Vu) |
| Three sequential local Ollama | **~48–60 min** |
| Disk | ~1 MB observed on recent out dirs; covered estimate **~2–4 MB/run → ~6–12 MB** for three |

## Schedule

- Freeze target: **2026-10-29 / 2026-10-30** (once open items closed).
- Covered three-run: **2026-11-02**.
- `usage-refresh-mc`: decide at **2026-11-01** check; untouched until then.
