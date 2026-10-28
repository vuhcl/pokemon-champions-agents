# Three-run rehearsal (dev mega eev only; stub LLM; 2026-10-28)

## Layout
`--runs-root /Users/nowaki027/part-g-arm-state-out-rehearse` with `--run-id` 1|2|3.
Rows: `dev-mega-bare-hyp`, `dev-mega-edit-refuse`, `dev-mega-lock-ok` via `--dev --dev-rows-file state/dev_rows.json --stub`.
No covered request-set row; no Ollama.

## Resume after kill
- Run 1 `--stop-after 1` → `progress.finished=["dev-mega-bare-hyp"]` only.
- Re-invoke same command without `--stop-after` → transcript has all 3 rows (resume from progress).

## Timings (`time -p` real)
| step | real (s) |
|------|----------|
| run1 partial (stop-after 1) | 0.35 |
| run1 resume (2 remaining) | 0.38 |
| run2 full | 0.33 |
| run3 full | 0.36 |

## Disk
| path | size |
|------|------|
| runs-root total | 428K |
| run_1 / run_2 / run_3 each | 136K |

Each run dir: `progress.json`, `run_record.json`, `transcript.json`.

## compare_runs.py
`differ_count=0`, `row_count=3`; all three rows `equal` vs run_2 and vs run_3 (mechanical_class, tool_calls, sha256(final_text)).
