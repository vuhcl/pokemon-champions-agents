# PRE-RS-ARM results (stateful arm, request-set covered subset), 2026-10-28

Status: counts are final for this registration (row-level script reproduced them). Not yet appended to eval_results.md. No pass threshold and no verdict word (Vu, 2026-10-28). The covered rows are a pre-declared subset (103 of 134), not a sample.

## What ran
- Registration PR #319, merge commit b98568d126efc67b40a28f6e3cd94a15e32470e4; freeze commit 17f8fdd32247d67c09f325ab9c96512d7b6265ba (manifest file sha256 59cde484...a7d4, files-table sha 112e3b9d...e4d0).
- Arm: tool-calling loop (LangChain ChatOllama + the stateful tool set), prompt bd2b69cd, tools.py e5dd309e. Model qwen3.5:latest (Q4_K_M, digest 44a38603...), temperature 0, think false, num_ctx 16384, num_predict 2048, no seed. Not the Claude API model.
- Run 1 (primary): 103 rows, 113 turns, 1448 s. Runs 2 and 3: identical on every one of 113 turns (class, ordered tool calls, final-text hash); they show determinism for this configuration and nothing else.
- Rows that never ran (harness load failures, deterministic in all three runs): SC2 (no loader for state cell "Arch on team or ask-add path"), TB2 (no _SLOT_BASE entry for tb2_incineroar_charcoal.json).
- 6 turns had no usable answer (GS1 t1, H14 t1, HC2 t1, IC1 t1, MC1 t1, MT6 t2); counted as fails where mechanical, all cells fail where hand-audited.
- Exploratory run on the 31 kept-out rows: NOT run (Vu, 2026-10-28, decided after seeing run 1 counts). The 31 rows have no observation.

## Counts (95% Clopper-Pearson, two-sided; frozen clopper_pearson_two_sided)
Row level (row passes iff every judged turn passes; my calculation from the final CSV, to be reproduced by Cursor's post-run script):

| bucket | rows judged | passes | interval |
|---|---|---|---|
| mechanical only | 41 | 30 | 0.571 to 0.858 |
| hand audit only (audited) | 58 | 18 | 0.195 to 0.445 |
| hand audit only, SC2 counted as not passed | 59 | 18 | 0.192 to 0.439 |
| dual, class part (MS5, RB1) | 2 | 1 | 0.013 to 0.987 |
| dual, class part, TB2 counted as not passed | 3 | 1 | 0.008 to 0.906 |
| dual, hand part (MS5, RB1) | 2 | 0 | 0.000 to 0.842 |
| dual, hand part, TB2 counted as not passed | 3 | 0 | 0.000 to 0.708 |
| all 103 rows, SC2 and TB2 not passed (not a headline) | 103 | 48 | 0.367 to 0.567 |
| all rows that ran | 101 | 48 | 0.375 to 0.577 |

Section (turn) level, frozen script on the final audit CSV: hand-audit sections 20/65 (0.199 to 0.435); dual hand sections 0/2; all audited sections 20/67 (0.193 to 0.423); rubric points 66/177 (0.301 to 0.449). Mechanical per class (turn = row): ASK 7/9, FAIL-CLOSED 2/4, MUTATION-OK 7/12, MUTATION-REFUSED 8/10, NO-MUTATION 7/8.

Dual rows: MS5 class pass (wrote), hand fail; RB1 class fail (no change), hand fail. Reported separately; neither score overrides the other (registration).

## Rules decided after run 1 counts were seen (post-hoc, disclosed)
- SC2 and TB2 (never ran) are counted as not passed in the primary count, with the version that drops them shown beside it.
- Hand-audit conventions fixed before the audit started: counting unit is the rubric cell; a no-answer turn fails every cell; a point that describes a failure trigger passes when the trigger did not occur and fails when it did; fragments that are not scoring points are not applicable; a row with a flawed argument but all points passing passes, with the flaw in the note. Sections with every point not applicable have overall not applicable and are excluded (5: MT1 t1 and t2, MT2 t1, MT5 t1 and t2).
- A single auditor who knows the keys (Vu). The gemma judge (gemma4:12b, prompt 89b99005...) is a non-gating consistency check run after export: it agreed with Vu's overall verdict on 43 of 72 sections and disagreed on 29 (0 abstained); no verdict was changed. Direction: gemma pass / Vu fail in 24 sections (22 hand-only, 2 dual: MS5, RB1); gemma fail / Vu pass in 0; the other 5 are Vu not_applicable (MT1 t1/t2, MT2 t1, MT5 t1/t2). On the 67 sections with a Vu pass/fail, agreement is 43/67. The judge was only ever more lenient than the audit. Calibration was 20/22 on the Part 5 planted/correct set (12 planted, 10 correct; false_pass 2, false_fail 0), a different set; it is not independent corroboration of the audit.

## Harness and key defects found during the audit (counted beside the results, not removed from them)
- DM2: start state built by build_fully_locked_slot("Incineroar") (Blaze, Sitrus Berry, Modest, generic spread, first four legal moves, no Flare Blitz); the key's grid is for Adamant Life Orb Atk-32 Intimidate. The key could not be matched by construction; the arm also ignored the locked slot.
- H18b: the fixture's two locked slots lack role and moveset, so show_candidates found no fully-locked anchor and returned "empty team: ... needs a locked anchor".
- RB1: resolve_start_state checks for the words idle/empty/bootstrap/mid-build before it looks for a fixture path; the state cell contains "4th empty", so the fixture was never loaded and the arm saw an empty team.
- SC2, TB2: load failures (above).
- MV2 (PP) and MV3 (target, accuracy): get_move_static returns type, category, base power and priority only; PP, target, accuracy and flags exist in the move data but no tool returns them. Displayed PP in static.v1.json already follows the Champions formula, so mainline PP (10, 15) is wrong.
- Start-state vs key sweep over the 103 covered rows (Cursor): MATCH 7, MISMATCH 7, KEY SILENT 89. MISMATCH rows: DM2, RB1, TB2 (above) and MR3, MS2, MS3, MW2. For the latter four the key's state cell requires locked slots, but resolve_start_state maps those states to empty_team, so all four ran from an empty team (not sweep false positives). MR3: key "one locked", prompt "Lock a second Incineroar", expected refusal (Species Clause); arm locked on an empty team, so the row failed, and the failure depends on the mismatch. MS2: key "slot1 locked", prompt "Unlock slot 1", expected a write; the tool refused on an empty team, so the row failed, and the failure depends on the mismatch. MS3: key "2 locked", prompt "Reset the team"; reset_team wrote, row passed, and the result does not depend on the mismatch. MW2: key ">=1 locked", prompt "Unlock the other one"; arm made no change (read_team), row passed, and whether it would still ASK with a locked slot is undetermined. Results are identical across runs 1-3. Mechanical-only sensitivity (not a replacement for the primary 30/41): 30/39 [0.607, 0.889] excluding MR3 and MS2; 28/37 [0.588, 0.882] excluding all four; 32/41 [0.624, 0.894] if MR3 and MS2 were passes; 28/41 [0.519, 0.819] if MS3 and MW2 were fails. build_fully_locked_slot feeds DM2 only; build_fully_locked_mega feeds no covered row.
- DM2 transcript: the arm never called read_team; its calc attackers were Intimidate / Jolly / 32 Spe (Black Sludge recorded as empty); final numbers 99-117 (75-88.6%), 2HKO. The numbers match neither the loaded fixture nor the key.
- Tool capability: of the covered rows, only MV2 (PP) and MV3 (target) were found to need a field no tool returns. The arm said Wish has 10 PP (key 8).
- show_candidates: 9 calls in run 1, 0 successful; 8 refused for no fully-locked anchor, 1 for a wrong slot. HU3's reference calls for show_candidates and the arm skipped it. H18b's slots are partly locked (role, moveset unlocked), so they are not all_locked.

## Failure patterns seen (Vu's audit notes; tallies in the section above)
- Unrequested state changes: of 113 turns, 13 were allowed to change state and 100 were not; 15 of those 100 changed state anyway (e.g. MT1 t1 locked Blastoise for "Slot 1 Water"; MT3 t1 locked Arcanine; GS1 locked species only in all slots; MC1 locked a base form with no item; H14, HC2, IC1, MM1; Q10 attempted a mutation on a question). The other 85 turns did not change state.
- Mechanical or factual claims made without a tool (H15, HU4, IX1, IX5, IX7, MT6, MV3, DM2 item remark); legality or usage not checked (H3, HU2b, H18b).
- Answers faithful to the calculator but with an unstated or non-pinned assumed set (DM1, DM3, DM6, DM7, H5).
- Misreading of tool output: MS5 listed Pelipper as a conflict from blanket judgment_mismatch pending_flags (the conflicts list had only Charizard-Mega-Y).
- Multi-turn rows: 1 of 8 passes (MT5).

## Caveats
- Dev was in-sample (three prompt revisions after A5, all on dev rows; dev 42 of 44 on final tools); damage and assumption rows had no dev counterpart as far as the plan shows.
- Configuration: local 4-bit model, thinking off. This says nothing about the same arm on another model.
- Hand-audit results come from one auditor who knows the keys; the second rater under-flags (20/22 agreement, 2 of 12 planted errors passed).
- Passes with noted flaws: HU1, HU3 (claims not tool-checked).

## Reproducibility
- Final audit CSV hand_audit_export_1.csv sha256 3bdbc2b6bbc1afef8134be0755170d8a2c1ad6f0695042cf6a802789acca8f07 (72 sections, 232 lines, 60 rows). First export (HF2 t1 and H18b t1 had blank overalls; superseded): sha256 bdf5a2605335db17397e109c1ce2ad1937b8840dbcea56eb459d7f42ac86a7f0 (copy held outside the repo).
- Row-level script row_level_verdicts.py sha256 fe29de7d1720c2592549e2a29a5a62bcca4c79ecfb858f7a8426ab528195cc64, written after the run, not in the frozen manifest; its counts equal the hand calculation (hand-only 18/58, mechanical only 30/41, dual 1/2 class and 0/2 hand, 48/103 and 48/101).
- Run artifacts, audit CSVs, gemma merge and row verdicts: branch run/pre-rs-arm-b98568d, commit bd8e568efa8ede61cfd82c277e9cbb7ac35c582c (not pushed, not merged to main). Frozen manifest verify PASS, tree clean, calc health ok, check_pins PASS (14) after the runs. Only run 1 has class scorer and interval output; runs 2 and 3 are compared by compare_runs.py (differ_count 0).
- Exploratory runner (exploratory_runner.py) was frozen but not used.
