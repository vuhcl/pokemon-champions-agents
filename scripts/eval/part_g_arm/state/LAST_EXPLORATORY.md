# Exploratory mode (2026-10-28)

Declared in registration analysis_plan 3b. Unscored; separate root.

- Module: `exploratory_runner.py` (progress: `exploratory_progress.json`; README mark `exploratory, unscored`).
- Isolation: exploratory root must contain `exploratory`; refuses registered `run_1`/`run_2`/`run_3` layouts. Registered `run_batch` calls `assert_not_exploratory_dir`.
- Loader: same as `resolve_start_state`; H12 → `empty_team` from row text only (not in `seeds/` / SHA256SUMS). Load failures recorded, state not invented.
- Tests: `test_exploratory_runner.py` — stub + eev/dev only; **no model run on any not-covered request-set row**.
- Real not-covered run: wait for Vu after registered run 3 outputs are committed.
