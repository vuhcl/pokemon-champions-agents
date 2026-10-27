# Last full final-prompt dev rerun (Part 5)

- Transcript (outside repo): `/Users/nowaki027/part-g-arm-state-out-final2/`
- Prompt sha256: `bc6f8bb7a37292beec849ca39c25da9e79e26eae60485d32ec20769c3d5499a4`
- Model: `qwen3.5:latest` digest `44a38603922e14f1e3ae68c5d900cc39f2a925a9749d12ab6d268d75a01a399f`
- Does not inherit the rev3 PASS. See `RUN_PARAMS` in `harness.py` / `run_record.json`.

## Per-row (final prompt)

| row | class | pass | notes vs prior final (`d02dc4f3…`, class could not see binds) |
|---|---|---|---|
| dev-lock | wrote, refused | pass | same |
| dev-unlock | refused | pass | same |
| dev-commit | refused | pass | same |
| dev-lookup | lookup only | pass | same |
| dev-unlock-ok | wrote | pass | same |
| dev-commit-ok | wrote | pass | same |
| dev-hyp-item-clause | lookup only | pass | same |
| dev-hyp-species-clause | lookup only | pass | same |
| dev-hyp-unknown-species | lookup only | pass | same |
| dev-hyp-legal | lookup only | pass | same |
| dev-hyp-item-only | lookup only | pass | same |
| dev-select-cs | wrote | **fail** | prior "pass" was `no change` under a blind class after `select_option` only; this run called `select_option` then `commit_slot` → wrote |
| dev-select-bad | refused | pass | same |
| dev-select-locked-target | refused | pass | same |
| dev-confirm-fbc | wrote | pass | same |
| dev-confirm-stale-fp | refused | pass | same |
| dev-reject | recorded | pass | prior "pass" was `no change` after `reject_pending` (dismiss, not reject); this run used `reject_option` → recorded |
| dev-reject-all | recorded | pass | new |
| dev-read-rejected | recorded, lookup only | pass | new |
| dev-reject-dismiss | lookup only | **fail** | new; model called `no_lookup_needed`, pending uncleared |
| dev-reject-all-bad | refused | pass | new |

Earlier "pass" for `dev-select-cs` / `dev-reject` under the pre-Part-1 class is superseded by this rerun.
