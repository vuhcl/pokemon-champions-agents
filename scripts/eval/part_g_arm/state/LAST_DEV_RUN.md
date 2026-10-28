# Full eev rerun (pre-freeze round 3 item 3)

After H11 errata + MM1/MM2 covered + MM2 fixture. **No prompt change.**

| | |
|---|---|
| tools.py sha256 | `e5dd309e0a6ce4afb9eeddc0b2bb2172ea79086feda8e7ff07a3158ae4dd5d42` |
| prompt.md sha256 | `bd2b69cde151fdb4dd2431c294ca46f4fbc251f54cebd82a13844d4eba0aaf86` |
| tool_schema_sha256 | `f0c97ad3b88cb3f118e241111bd454a4e86f7937cd4342f0969cadbe5049b845` |
| model | `qwen3.5:latest` digest `44a38603922e14f1e3ae68c5d900cc39f2a925a9749d12ab6d268d75a01a399f` |
| temperature | 0.0 |
| think | false |
| num_ctx | 16384 |
| num_predict | 2048 |
| allow_live | false |
| transcript | `/Users/nowaki027/part-g-arm-state-out-pre-freeze-r3/` |
| result | **40/41** eev pass |
| vs prior find-species full run | same 40/41; **no regressions** |

## Per-row

| row | mechanical_class (per turn) | pass | prior | change |
|---|---|---|---|---|
| dev-lock | wrote/refused | pass | pass | same |
| dev-unlock | refused | pass | pass | same |
| dev-commit | refused | pass | pass | same |
| dev-lookup | lookup only | pass | pass | same |
| dev-unlock-ok | wrote | pass | pass | same |
| dev-commit-ok | wrote | pass | pass | same |
| dev-hyp-item-clause | lookup only | pass | pass | same |
| dev-hyp-species-clause | lookup only | pass | pass | same |
| dev-hyp-unknown-species | lookup only | pass | pass | same |
| dev-hyp-legal | lookup only | pass | pass | same |
| dev-hyp-item-only | lookup only | pass | pass | same |
| dev-pick-named | bound | pass | pass | same |
| dev-select-bad | refused | pass | pass | same |
| dev-select-locked-target | refused | pass | pass | same |
| dev-confirm-fbc | wrote | pass | pass | same |
| dev-confirm-stale-fp | refused | pass | pass | same |
| dev-reject | recorded | pass | pass | same |
| dev-toss-all | recorded | pass | pass | same |
| dev-show-rejected | recorded/lookup only | pass | pass | same |
| dev-dismiss-later | dismissed | pass | pass | same |
| dev-reject-all-bad | refused | pass | pass | same |
| dev-edit-item-ok | wrote | pass | pass | same |
| dev-edit-item-refuse | refused | pass | pass | same |
| dev-edit-choice-consequence | wrote | pass | pass | same |
| dev-ms6-water | recorded | pass | pass | same |
| dev-mt3-intimidate | recorded | pass | pass | same |
| dev-restore-type | recorded/recorded/recorded | pass | pass | same |
| dev-show-open | bound | pass | pass | same |
| dev-show-reject | bound/recorded/bound | pass | pass | same |
| dev-show-empty | refused | pass | pass | same |
| dev-show-locked | refused | pass | pass | same |
| dev-learnset-yes | lookup only | pass | pass | same |
| dev-learnset-no | lookup only | pass | pass | same |
| dev-archetype-rain | wrote | pass | pass | same |
| dev-move-priority | lookup only | pass | pass | same |
| dev-fs-types-move | lookup only | pass | pass | same |
| dev-fs-stat-bulk | lookup only | pass | pass | same |
| dev-fs-formes | lookup only | pass | pass | same |
| dev-fs-prankster-weather | lookup only | fail | fail | same |
| dev-mt7 | lookup only/no change/recorded | pass | pass | same |
| dev-mt8 | lookup only/no change/recorded/no change | pass | pass | same |

## Failures (unchanged finding)

- `dev-fs-prankster-weather: set ['Banette', 'Banette-Mega', 'Grimmsnarl', 'Klefki', 'Liepard', 'Meowstic', 'Sableye', 'Whimsicott'] != key ['Banette-Mega', 'Klefki', 'Liepard', 'Meowstic', 'Sableye', 'Whimsicott']`
- `dev-fs-prankster-weather: 'Banette' named without find_species hit`
- `dev-fs-prankster-weather: 25 tool calls exceeds 16`

No prompt.md edit. Prankster weather remains the known set/tool-budget finding.
