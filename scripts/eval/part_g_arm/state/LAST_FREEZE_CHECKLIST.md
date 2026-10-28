# Freeze checklist (report — not frozen)

Head at checklist commit (see git). Freeze target **2026-10-29 / 2026-10-30**. Covered three-run **2026-11-02**. No `FROZEN_MANIFEST.json` write.

## a. Mega-stone PR #318

**Status: OPEN, not merged** (`gh pr view 318`). MM1/MM2 remain **not_covered**. Cursor did not merge `main` into the arm branch. When Vu merges #318: merge main → arm, rerun MM1/MM2 reference trajectories only, report.

## b. H11 / H19 / H20 / HU1

| row | scripted trajectory | covered | notes |
|---|---|---|---|
| H11 | **pass** (core set + Mega present) | covered | **Drift:** tool also returns `Castform-Rainy` not in acceptance `{Gyarados,Pelipper,Quaquaval}`. Report-first for Vu; do not edit frozen keys. |
| H19 | **pass** (Trick Room learners nonempty) | covered | Learnset tool-reachable; **compendium-role TR setters that are not learnset-equivalent stay hand/checklist**. |
| H20 | **pass** (Water pool nonempty, include_formes=false) | covered | `find_species(types=…)` = legal **pool**; ranked offers still need `show_candidates`. |
| HU1 | **pass** (Fire bulk ≥350 membership) | covered | `stat_formula` + `include_formes=false`. |

Tests: `test_enumeration_trajectories.py`.

## c. Covered counts + B1 + Part 6

| | count |
|---|---|
| covered | **99** |
| not_covered | **35** |
| B1∩covered mechanical | **39** |
| B1∩covered hand audit | **54** |
| B1∩covered total | **93** |

**Covered but absent from B1** (assign for freeze honesty; propose B1 refresh, do not silently invent rates):

| row | request-set class | proposed bucket |
|---|---|---|
| GS1 | SERVED | hand audit |
| IX1 | ASSUME-STATE | hand audit |
| SC2 | SERVED | hand audit |
| MS5 | MUTATION-OK | scorable-mechanical |
| RB1 | MUTATION-OK | scorable-mechanical |
| TB2 | MUTATION-OK | scorable-mechanical |

After refresh: mechanical **42**, hand audit **57**, total **99**. See `LAST_PART6_PROPOSAL.md`.

## d. Prankster key independence

Rebuilt `build_prankster_weather_key.py` from legality + `WEATHER_SETTING_MOVES` only (**no** `find_species` import).

| | |
|---|---|
| artifact | `dev_keys_prankster_weather.json` |
| sha256 | `6dba1caac2d45135779779f7867f6f442163bdb3fef35ca6270d7c76329fb543` |
| prior (circular) | `cbef455d7ff1610152f64fc17ad5e33796e82fd05669a8fca93d8b0fa47652d3` |
| species set | Banette-Mega, Klefki, Liepard, Meowstic, Sableye, Whimsicott (count 6) |

Test: key == five-call `find_species` union; AST check builder does not import `find_species`.

## e. Diff attribution (correcting “all in f1aa0ec”)

| path | commit | change |
|---|---|---|
| `harness.py` | **f1aa0ec** (+110/−1) | find_species dispatch + Prankster set-grade; **state/dev-only** |
| `fixtures.py` | **a718495** (1 line) | `CHECKPOINT_PROMPT_SHA256` → bd2b69cd; state-only |
| `request_set_rows.py` | **a718495** (1 line) | `FROZEN_PROMPT_SHA256` proposal; state-only |

None of these are product CLI runtime paths beyond the arm eval harness.

## f. Manifest proposal

`STATE_MANIFEST_PROPOSAL.json`: `frozen: false`; prompt `bd2b69cd…`; `repeat_runs`; `hand_audit_form`; Prankster key sha above; covered_list sha `25b6a1cf…`; judge prompt sha `89b99005…`; seeds `SHA256SUMS` `9e8cc64f…`; **`clean_tree_commit_sha`: `""`** until Vu freezes.

## g. Prompt history for registration

`b7176485` → `c58e3ce8` (rejected) → `08a0917a` → **`bd2b69cd`**.

`bd2b69cd` added exactly:
1. The `find_species(...)` bullet under state tools in `prompt.md`.
2. One reply-rule sentence: report `species` from `find_species`.
