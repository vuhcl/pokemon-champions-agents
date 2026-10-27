# Last full final-prompt dev rerun (Part 5 — spread solver round)

- Transcript (outside repo): `/Users/nowaki027/part-g-arm-state-out-final3/`
- Prompt sha256: `fdab0b6f60daf2e8dfb2f53e020bcdc2c734467d7bc7b24fd7a68def364ddc17` (FREEZE)
- Model: `qwen3.5:latest` digest `44a38603922e14f1e3ae68c5d900cc39f2a925a9749d12ab6d268d75a01a399f`
- Does not inherit the rev3 PASS. See `RUN_PARAMS` in `harness.py` / `run_record.json`.
- New capability: `solve_spread` (read-only). Stateful arm does not inherit prior PASS.

## Per-row (final prompt)

| row | class | pass | notes vs prior final (`bc6f8bb7…`) |
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
| dev-pick-named | bound | pass | **new** (replaces retired `dev-select-cs`); select_option only, no commit |
| dev-select-bad | refused | pass | same |
| dev-select-locked-target | recorded | **fail** | prior refused; this run rejected options after select_option refused on locked target |
| dev-confirm-fbc | wrote | pass | same |
| dev-confirm-stale-fp | refused | pass | same |
| dev-reject | recorded | pass | same |
| dev-toss-all | recorded | pass | **new** (rewrote `dev-reject-all` wording) |
| dev-show-rejected | recorded, lookup only | pass | **new** (rewrote `dev-read-rejected` wording) |
| dev-dismiss-later | recorded | **fail** | **new** (replaces retired `dev-reject-dismiss`); model called `reject_all` instead of dismiss |
| dev-reject-all-bad | refused | pass | same |
| dev-mt7 | lookup only / no change ×2 | hand pass (no silent write) | **new**; `solve_spread` called 8× on t1 all `status=unknown` (move nested under attacker; missing ability); t2–t3 did not re-solve |
| dev-mt8 | lookup only / no change / lookup ×2 | hand pass (no silent write) | **new**; same t1 unknown; t3 checked legality of Mega-Y; t4 `read_pending` only — **did not state Timid result before a way out** |

## Retired-row findings (kept)

- `dev-select-cs`: select then unrequested commit (wrote).
- `dev-reject-dismiss`: no tool call / `no_lookup_needed` on dismissal.

## MT7/MT8 hand audit fields

| field | MT7 | MT8 |
|---|---|---|
| tool calls / turn | t1: 8× solve_spread; t2: read_team; t3: check_species_legal, get_abilities, read_team | t1: 8× solve_spread; t2: read_team; t3: check_species_legal; t4: read_pending |
| Timid stated at t4 before way out | n/a | **no** |
| Silent apply | no | no |
| Sentence order (MT8) | n/a | failed (no Timid / infeasible Modest statement) |
