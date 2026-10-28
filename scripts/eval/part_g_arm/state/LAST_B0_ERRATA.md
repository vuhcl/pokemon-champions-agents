# B0 — errata inputs (report)

Draft path `claude/request_set_errata_draft_2026-10-26.md` was **not present** in the worktree. Cells below are from `part3_request_set_v4.md` acceptance text + the Vu brief; recorded in `state/errata.json` (request set and `derived_keys.json` untouched).

## Per-turn class the key assigns

| row | turns | source |
|---|---|---|
| H15 | t1 **ASSUME-STATE** | class cell; acceptance SERVED is outcome under stated Modest joint, not a second class |
| DM1 | t1 **ASSUME-STATE** | class cell |
| DM3 | t1 **ASSUME-STATE** | class cell |
| IC1 | t1 **SERVED**, t2 **MUTATION-OK** | acceptance (overrides single-cell SERVED) |
| IS2 | t1 **PARTIAL+ASSUME-STATE** | acceptance (overrides cell ASSUME-STATE) |

## Loader substitutions

| row | status |
|---|---|
| MRB1 | **Applied by loader** `build_mrb1_start`: user slot 3 → Torkoal + Drought + Charcoal. Expected read-back exactly those three strings. No fixture file. |
| H25 | **Applied by loader** `_substitute_h25_doc` on load: user slot 2 Barraskewda → Basculegion / Swift Swim / Life Orb. `h25_team.json` on disk still says Barraskewda. |

Verified: `load_fixture("H25")` → Basculegion; file unchanged; MRB1 read-back Torkoal/Drought/Charcoal.
