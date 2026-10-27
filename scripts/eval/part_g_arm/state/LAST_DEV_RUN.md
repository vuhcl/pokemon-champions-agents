# Last full final-prompt dev rerun (Part A5 — freeze)

- Transcript (outside repo): `/Users/nowaki027/part-g-arm-state-out-final4/`
- **FROZEN prompt sha256:** `b71764852eb66f87f17375ff3226a7e4be7517b09eb8961fb56e779fe32badd8`
- Candidate not chosen: `fdab0b6f60daf2e8dfb2f53e020bcdc2c734467d7bc7b24fd7a68def364ddc17` (out-final3)
- Model: `qwen3.5:latest` digest `44a38603922e14f1e3ae68c5d900cc39f2a925a9749d12ab6d268d75a01a399f`
- Why frozen: revised prompt (A1 invalid_arguments + A2 reject consequences) fixed both graded fails from fdab0b6f with **no previously-passing graded row flipped to fail**. Last prompt revision; no further tuning.
- Does not inherit the rev3 PASS. See `RUN_PARAMS` in `harness.py` / `run_record.json`.

## Per-row (final prompt vs fdab0b6f)

| row | class | pass | vs fdab0b6f |
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
| dev-pick-named | bound | pass | same |
| dev-select-bad | refused | pass | same |
| dev-select-locked-target | refused | **pass** | was fail (recorded after refused select) |
| dev-confirm-fbc | wrote | pass | same |
| dev-confirm-stale-fp | refused | pass | same |
| dev-reject | recorded | pass | same |
| dev-toss-all | recorded | pass | same |
| dev-show-rejected | recorded, lookup only | pass | same |
| dev-dismiss-later | dismissed | **pass** | was fail (reject_all); now reject_pending |
| dev-reject-all-bad | refused | pass | same |
| dev-mt7 | lookup only / lookup only / no change | hand pass (no silent write) | same grade; t1–t2 now reach `optimal` after `invalid_arguments` repairs (was all `unknown`) |
| dev-mt8 | lookup only ×4 | hand pass (no silent write) | same grade; still **did not state Timid / infeasible Modest before a way out** on t4 |

## Findings kept (not tuned further)

- MT8 sentence-order / Timid-before-way-out still fails the hand field.
- MT7/MT8 still omit ability on first calls; A1 surfaces `invalid_arguments` with legal abilities instead of `unknown`.
