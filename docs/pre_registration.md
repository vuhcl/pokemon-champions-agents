# Pre-registration registry

Dated: 2026-10-08. Standing registry of pre-registered experiments for the
model-driven arm (product v2, shipping as 1.x). This file is meant to outlive
any single product version label.

## 1. Purpose and meaning of "pre-registered"

A measurement is **pre-registered** only when both hold:

1. A registration section for that experiment exists in this file and was
   committed **before** the run that produces the result.
2. That commit is an **ancestor** of the commit that produces the result
   (`pre_registration_sha` ≤ run HEAD in git history).

There is **no CI** for this. The check is manual; the procedure below is the
check. Precedents that motivated the discipline (read, do not restate):

- Laya turn_intent spike gates —
  [docs/eval_results.md § Laya turn_intent spike](eval_results.md#laya-turn_intent-spike-label-only-first-pass--2026-09-28)
  (Gates subsection).
- ADR-073 pre-registered floors method —
  [architecture_decisions.md § ADR-073](architecture_decisions.md#adr-073-set-floors-are-policy-constants-from-a-pre-registered-method-setup-presence-is-count-based).
- ADR-060 oracle independence —
  [architecture_decisions.md § ADR-060](architecture_decisions.md#adr-060-verification-evals-require-an-oracle-independent-of-the-code-under-test).
- ADR-071 Gate 0 and the 88df2d7 / 9621b77 control run —
  [architecture_decisions.md § ADR-071](architecture_decisions.md#adr-071-fail-closed-unmatched-clarify--discard-model-authored-pending_responsemessage-on-the-deterministic-gap-fill-path)
  (Why / Evidence: baseline HEAD `88df2d7`, control / main@`9621b77`).

**Out of scope for this file:** Showdown-simulated win-rate eval and RL work
(deferred; see `eval_results.md` Phase 2 / Phase 3 sections). Do not add
win-rate or RL registrations here until that sequencing question is settled
elsewhere.

## 2. Procedure

Exactly:

1. **Register before the run.** A registration is a `##` section in this file
   (id in the heading), filled from the template below, and committed **before**
   any run that will be treated as a result for that experiment.
2. **Record `pre_registration_sha` on the result.** The result artifact's
   `meta` (or equivalent) must record `pre_registration_sha`: the commit that
   introduced or last changed that registration section.
3. **Ancestor check.** Verification must succeed:

   ```bash
   git merge-base --is-ancestor <pre_registration_sha> <run_HEAD>
   ```

   Exit code 0 means the registration commit is an ancestor of the run HEAD.
   Exit code 1 means it is not (reject the run as pre-registered under that SHA).
4. **Section unchanged between registration and run.** The registration's
   method section must be unchanged between `pre_registration_sha` and the run
   HEAD. Verify with a line-range history walk on this file (adjust the regex
   to the registration's heading and the next `##` heading). Empty output means
   no commit in the range touched those lines:

   ```bash
   git log --oneline \
     -L '/^## <REG-ID>/,/^## /:docs/pre_registration.md' \
     <pre_registration_sha>..<run_HEAD>
   ```

   Empty log = section unchanged. Non-empty log = not the same registration;
   do not treat the run as pre-registered under that SHA (amend and re-register
   instead).

   **Empty is not self-proving.** A bad heading regex or range that matches no
   lines also prints nothing. Before trusting an empty result for a new
   registration id, confirm the same `-L` form produces **non-empty** output on
   a known change of that section (e.g. the commit that introduced it:
   `<intro>^..<intro>`).

   Note: `git diff <A> <B> -L …` is **not** usable here — Git's `-L` walk
   accepts at most one positive revision (`git diff` two-commit form fails with
   `bad revision` / `invalid object name` on the `-L` argument). Use `git log
   -L` as above.
5. **Pin usage (and other mutable data) by blob SHA or tag.** Record the blob
   SHAs of the usage files used (or a pinned tag). The daily in-game refresh
   bot commits move usage ranks and change data under a fixed method; a method
   SHA alone is not enough to reproduce a data-dependent result.
6. **Amendments are append-only.** After a run, do not edit the original
   registration text, and do not insert, move or delete any line inside a
   registered `##` section or between it and the next `##` heading. Record each
   amendment as a `### <REG-ID> Amendment YYYY-MM-DDa` subsection (then `b`, `c`,
   ...) under a single `## Amendments to registrations` heading, appended below
   any earlier amendments, and say which earlier amendment it supersedes. That
   heading must follow the registered section and exist in the registering
   commit, so the line-range walk in step 4 always ends at a `##` heading that
   does not move. A registered section with no following `##` heading makes the
   step-4 command error instead of printing nothing, which the step-4 sanity run
   does not catch. Register each new experiment directly above the most recent
   registration, never between a registered section and the Amendments heading.
   Changing metric, thresholds, oracle, or sample still requires a new
   registration (new SHA) before any comparable remeasure.

### Sample dataset rule

The 25-request deterministic-graph capability baseline
(`scripts/eval/artifacts/det_graph_capability_baseline_88df2d7/`) has been run
against the deterministic graph and is a **development** set. A registration's
`sample_dataset` must be a **held-out** set committed **before any arm code
exists**. The held-out set is drafted separately; it is not created by the
skeleton that introduced this file.

## 3. Registration template

Copy into a new `## <REG-ID>: <short title>` section when registering. Leave
`thresholds` for Vu to fill — never invent defaults.

```
hypothesis:
metric:
thresholds:                 # Vu fills; never defaulted by agents
sample_dataset:             # path + commit or blob SHA (held-out; see Procedure)
oracle_source:              # ground truth; independence from SUT per ADR-060
analysis_plan:
stop_rule:
before_run_evidence:        # pre_registration_sha after the registering commit
confounders_controls:       # HEAD/data drift → control run; label QA; oracle blind spots
verdict_costs_accepted:     # what a failed or null result will be reported as
```

Status values for rows that have (or will have) a section: `draft` |
`registered` | `run` | `amended`. Index rows below that are only placeholders
use `not yet registered` and must not claim a section exists.

## 4. Index

Decided context for the claim-verification candidate only (not a registration):
a **≤2% ceiling** is already decided for the gated metrics (false-claim rate,
false-legal rate, unverifiable-share cap). Every other threshold remains for Vu.

| id | status | date | owning experiment | result artifact |
|----|--------|------|-------------------|-----------------|
| PRE-MD-CLAIM | registered | 2026-10-24 | Model-driven arm, claim-level false-claim rate on the held-out claim battery (gated: adjusted claim-level false-claim rate, 95% CP upper bound ≤ 2%; false-legal and unverifiable share are reported, not gated) | — |
| PRE-RS-ARM | registered | 2026-10-28 | Stateful arm, class-scored request-set subset (descriptive; 103 covered rows; no pass threshold) | — |
| PRE-MD-ROUTE | not yet registered | — | Routing correctness of the model-chosen tool vs the request (right facts, wrong question) | — |
| PRE-MD-THEME | not yet registered | — | Theme handling slice — claim correctness and honest labeling of model-interpreted sets only (no viability or win-rate metric) | — |
| PRE-EXCELLENT-FLOOR | not yet registered | — | Relative Excellent-damage-floor robustness (`recommender/role_compendium_setup.py` Excellent floor = 2nd-highest adjusted × 0.95); method class is Vu's choice | — |

No registration in this file is marked `registered`. Nothing is registered by
the commit that introduced this skeleton.
## PRE-MD-CLAIM: Model-driven arm, claim-level false-claim rate on the held-out claim battery

### hypothesis

On the held-out 350-item claim battery (seed 0), the headless tool-calling arm (qwen3.5:latest via Ollama, temperature 0, think off, system prompt rev3, tools offline-pinned) answers in prose such that the one-sided 95% Clopper-Pearson upper bound on the claim-level false-claim rate, after audit adjustment, is at most 2%. FALSE means the claim contradicts the frozen key. This is a test of a specific configuration on one battery, not of the arm in general.

### metric

Claim-level false-claim rate, audit-adjusted.

- A claim is a statement extracted from the arm's final answer text by the frozen per-template extractors and scored by the frozen scorer (R6 enum: TRUE, FALSE, UNVERIFIABLE). Code: scripts/eval/part_g_v4/ at the freeze commit 92c03cbc5db551ffcd9f4579646a0dce9c227dca with FROZEN_MANIFEST.json sha256 0972060c0d0b208c6a9669b079ab483bc82e855fcc8956d92fac63c0c780458a. Where this text and scorer.py disagree, scorer.py at that commit governs.
- Gate unit: every scored (TRUE or FALSE) claim on the gated lines: speed, typing, ability, held-item, legality, move-static, damage (including the KO-count/KO-chance line, which is part of the same unit and not a separate pass requirement), and the other claim kinds the scorer gates. Per scorer.py at the freeze commit, the gated lines are `gate` and `ko_chance`. On `gate`: has_ability, guaranteed_ko, ko_threshold, hp_arithmetic, labelled_value, ko_needed, speed_stat, speed_margin, damage_range, percent_of_hp, nhko (TRUE/FALSE returns only), plus the kinds scored through the set and equality scorers (extractor kinds has_type, item_legal, species_legal, outspeed, faster, common_items, teammates, category, base_power, move_type; set-valued kinds common_items, teammates, ability_list_member, type_list_member, whose rank claims are also on `gate`). On `ko_chance`: ko_chance, ko_count. Usage set membership and rank are therefore gated; usage percentages are not (below). UNVERIFIABLE is excluded from the denominator (R8).
- Counting: each member of a stated list is a claim; logically equivalent claims about one fact count once per item (dedupe, be71d8a); negation is scored as the proposition; hedged statements get no verdict; a missing key member gets no verdict. Counting is per claim, not per underlying error: one wrong belief can produce several FALSE claims.
- Decided scoring rules (details in scorer.py): KO counts exact against rolls_ko_of_16; KO percentages within 3.125 points of 100*k/16 (arbitrary); a labelled value that differs from the key is FALSE (unit slips); "damage needed to KO" must equal the defender HP; "N out of d rolls" with d not 16 is compared as a percent; roll-descriptor statements ("the maximum roll is N, which would KO") use the roll-list comparison; percent of HP within 0.1 point; guaranteed/possible nHKO from min/max roll against defender HP.
- Non-gating lines, always reported: usage percentages (tolerance 0.05, every mismatch listed); chance-based nHKO (UNVERIFIABLE, line `chance_nhko_unverifiable`); UNVERIFIABLE returns of the numeric gate kinds (line `threshold_arith_unverifiable`); implied-plural ability statements for single-ability Mega forms (ability_plural); list-as-one variant (a set answer is one claim, FALSE if any member is FALSE); item-level line; claims-copied-unchanged sensitivity (the answer contains the entire text line from the tool, per-tool operationalisation at 935080f); UNVERIFIABLE share with a sensitivity line counting UNVERIFIABLE as FALSE; Vu's manual verdicts on scorer-UNVERIFIABLE claims (recorded as `other` exceptions with a note starting MANUAL TRUE: or MANUAL FALSE:, reported as "manually adjudicated UNVERIFIABLE: x TRUE, y FALSE of N", never counted in the gate); items with no usable answer (below); per-type rates.
- Items with no usable answer: an item is answered when a record exists in answers.jsonl, whatever its content. Items with a timeout, tool error, turn cap or empty final text produce no claims, stay out of the claim denominator, are reported by cause on their own line, and are not retried. A non-gating sensitivity line counts each such item as one FALSE claim and recomputes the bound.
- Audit adjustment (verdict rule): the verdict uses scripts/eval/part_g_v4/audit_adjusted.py at the freeze commit. Adjusted false = scorer FALSE, plus audit-found missed claims judged FALSE, plus wrong_verdict/wrong_extraction rows corrected to FALSE, minus those corrected to TRUE. Adjusted n = scored claims plus audit-found missed claims judged TRUE or FALSE. Canary-matched rows are excluded first. Any unprefixed, unmatched or ambiguous exception row blocks the verdict. The scorer-only numbers are reported beside the adjusted ones.

### damage_item_scoring (v5 cut; called "R11" in working notes, not a requirement in gate_scorer_requirements.md, which stays frozen at R1-R10; R9 applies, so each damage key's ground_truth.scoring governs)

Question. Each damage item names an attacker, a move and a defender and asks whether the move guarantees a KO, assuming the move hits. The prompt states level, nature and stat points for both sides (attacker: its stated SP in its offensive stat and 0 elsewhere; defender: 32 HP SP and 0 elsewhere), no items, full HP, no stat changes or status, no weather, terrain, screens or other field effects, a single target and no critical hit. Non-Mega species state their ability. Mega forms are named by form id and use their own single ability from the legality blob; the prompt says so.

Key. guaranteed_ko is true iff the minimum of the 16 damage rolls is at least the defender's HP. The rolls, min_roll, max_roll, hp and rolls_ko_of_16 (the number of rolls that KO) are stored in the key. The rolls come from the pinned @smogon/calc build recorded in the pool metadata, through the committed pool (key_artifacts/battery_damage_pool.json). Evidence for the keys is calc output and the pinned Showdown source; no in-game observation is claimed.

Scoring.
1. The yes/no answer is one claim, scored against guaranteed_ko: TRUE if it matches, FALSE if it contradicts.
2. A stated chance of KO is a separate claim, scored against rolls_ko_of_16 in steps of 6.25 points. A single number is TRUE iff it is within 3.125 points (half a step) of 100*k/16. Only single stated percentages are scored: the extractors do not extract "X-Y% chance" ranges as ranges, so a stated range falls to the single-percent pattern or to nothing (the audit-adjusted count is the check). The 3.125 tolerance is arbitrary, not derived.
3. The yes/no and chance claims are scored separately, except that logically equivalent restatements of one fact count once per item (dedupe: "guaranteed 1HKO" and "16 of 16" fold onto guaranteed_ko yes). A hedge with no number ("probably", "likely") gets no verdict.
4. A claim that states conditions differing from the prompt's (item, nature, SP, field, crit) is UNVERIFIABLE and counts in the unverifiable share.
5. If an answer states a different ability for a Mega form, the ability claim is scored FALSE against the legality blob's single ability for that form, and the damage claim is UNVERIFIABLE. The phrasing "A is one of X-Mega's abilities" is not this case: it is ability_plural, non-gating, and not scored.
6. UNVERIFIABLE is outside the R8 denominator. The sensitivity line counts it as FALSE and does not gate.
7. Other numeric damage statements are separate claims scored by the rules under "metric" (damage range, defender HP, percent of HP, nHKO counts, KO-needed thresholds, KO counts, roll statements, labelled-value unit slips). This subsection lists the question, key and the yes/no and chance rules only.

Pool and exclusions (recorded in the pool metadata).
- 53 damage items per battery (26 True and 27 False), drawn without replacement from a 212-entry pool (key_artifacts/battery_damage_pool.json) under quotas_per_battery: T1 8, T2 1, T3 8, T4 4, T4e 1, T4r 1, T5fd 1, T5fp 1, M1 1; F1 5, F2 5, F2b 4, F3n 2, F3r_high 1, F3r_mid 1, F3r_low 1, F4 3, F5 4, M2 1. The generator enforces the quotas; the realised seed-0 counts were not read. Cutoffs come from quartiles of the usable-move and base-stat distributions; the 1.25 comfortable-margin cutoff for T2 is a stated constant, not derived.
- Each defensive-equivalence group (identical types and base stats) appears in at most 2 damage items per battery.
- Excluded: defenders with Sturdy or Disguise (the calc rolls do not model them); species missing from the calc dex (Aegislash); 14 multi-hit moves; moves whose success or damage depends on state the stated conditions do not define (list derived from pinned Showdown move data); attacker ability pairs that assert_abilities rejects.
- Stat-override moves (for example Foul Play) and transient formes (Aegislash-Blade) stay in the pool on purpose; the prompt states every stat, so their keys are determined.

What this subsection does not cover. Twin items cover the Pixilate, Scrappy, Aerilate and Dragonize families only. Raging Bull passed the filters but was not tried; Refrigerate, Liquid Voice and Mega Sol were dropped by the base-power filter. A rule using only move effectiveness and base power can answer part of these items without the calculator, so the damage claims test chart and power knowledge as well as calculation. No frozen script quantifies this and no figure is claimed.

### thresholds

- PASS: adjusted one-sided 95% CP upper bound on the false-claim rate ≤ 2% (decided). Reference table: n ≥ 149/236/313/386 for 0/1/2/3 false.
- INCONCLUSIVE (does not pass, blocks "v1 done"): extractor recall < 90% (arbitrary), or fewer than 240 scored claims (design floor). Recall on held-out is measured as extracted claims / (extracted claims + audit-found missed claims judged TRUE or FALSE) (Vu, 2026-10-24).
- FAIL: the bound exceeds 2% with at least 240 scored claims and recall ≥ 90%.
- INCONCLUSIVE also if more than 5% of items (17 or more of 350) have no usable answer (arbitrary). Dev reference: all 350 items in dev2, dev3a and dev3b ended with stop_reason final, no errors, no empty answers, slowest 45 s against the 300 s item timeout.
- Flag, non-gating: UNVERIFIABLE share above 10% of scorable claims (arbitrary).
- Tripwire (Vu, 2026-10-24): if the sensitivity bound (UNVERIFIABLE counted FALSE) exceeds 2% while the primary bound is ≤ 2%, the PASS is reported with that caveat in the same sentence, and the manual UNVERIFIABLE line is published beside it.
- Audit size: the full battery. Rule fixed before the run: time the 50-answer sample, mean ≤ 72 s/answer means audit the full battery, else 100 plus targeted. The 72 s figure was set for a 300-item battery (6 h budget); the held-out battery has 350 items, where the same 6 h gives 61.7 s. Measured 2026-10-24: 14.2 s/answer, which clears both, so the full-battery audit (350 answers, about 83 minutes at that pace) applies.
- Canaries: 20 seeded errors (7 wrong_verdict, 7 wrong_extraction, 6 missed_claim), display-only; list hidden; N = 20 is registered here; the list is generated after the run and only its sha256 is committed, before the audit. Reported: detected, type-matched, one-sided 95% lower bounds. Not gating. Canary miss rate = undetected canaries / all 20 canaries, also shown per type (7/7/6) and as type-matched. Report-only (Vu, 2026-10-24): no trigger; a high miss rate is disclosed as audit sensitivity below target and the adjusted false count is read as a lower bound. For reference, the one-sided 95% lower bound on detection is 86% for 20/20, 78% for 19/20, 72% for 18/20, 66% for 17/20, 60% for 16/20.
- Arbitrary values, stated as such: 3.125, 0.1, 0.05, 90%, 72 s (61.7 s at 350 items), 10%, 5%, 20 canaries.

### sample_dataset

Held-out claim battery, seed 0, 350 items (battery/claim_battery_v4.json), sha256 6e6c6be4351240629416f1e279bbf495bbf4670d79aaaa7d083a2c62c6d67443. Its current hash dates from the v5 cut (the earlier 300-item hash 13d082440e62... is superseded). The file was last changed by cc70d1cc41b3fc09282a03fe70b746f3d20f4e72 ("Part G v5 key cut 2", 2026-10-22T23:11:10-07:00). The first arm-code commit is 9f71d0df7887daabd99f6bfdd28ba7d4c14e2d02 (recommender/arm_tools.py, 2026-10-23T11:54:03-07:00). `git merge-base --is-ancestor cc70d1c 9f71d0d` succeeds and the reverse fails, so the battery was committed before any arm code in git history and no arm output existed when it last changed. The ordering claim rests on commit ancestry; the arm commits share one committer timestamp (probably rebased), so their dates are not evidence of when the code was written. False-legal battery (non-gating) sha256 3025138427391e57a92e1862a87b0074d44a51b290836077abf094af92c4bdec. Keys: derived_keys sha256 e70672541b5215e7bfff7eccb34dc321b2bde3a4b9cf08d1f5a6419be1d2309a (key cut #286; confirmed current on the branch 2026-10-24). Request-set sha256 7fb9510cb50e8f1f320ac1cf6bced41e8dcd12f4245ed2abb03a42254a60afdb. Request-set rows (134) are not part of this registration. The dev battery (seed 1, 350 items, sha256 ea6308a7a975680219b653a297eab429e0c4237f6361736b1e768fe91036fe31, split dev_split.json sha256 a1c8bb7f16d7a451cf838b192d6e3e690cccdf3b3a3d918f5c2345a4bc92dba6) was used for all development and is not a result.

Expected size, an extrapolation from dev, not a measurement: dev3b gave 1,236 scored claims over 350 items with the same slot structure; at about 1,200 the 2% line tolerates 15 false claims (16 at 1,236). Item-level, about 350 scored items tolerate 2 false items.

### oracle_source

Frozen keys derived from the pinned calc (@smogon/calc 0.11.0-champions.5d5bf43) and pinned Showdown data (commit 942cda71d14bf0618bd57991708a2e2734b6daba), per ADR-078; usage keys are snapshot-faithful to the pinned blobs. Independence per ADR-060 is partial and stated plainly: ability, held-item and speed keys were externally checked by Vu on the 13 and 7 items of a 50-item timing sample (13/13 and 7/7, public base stats and formula); damage keys were checked by an independent hand computation and a second calculator (engine not identified) on 8 items (8/8 identical ranges; percentages differ only by rounding); usage keys, typing, legality and move_static keys were not externally checked; keys and tool read the same pinned blob for several kinds (circular). FALSE means contradicts the frozen key, not contradicts the game.

### analysis_plan

1. Create the worktree at the registration commit; record run_params there (clean tree, commit equal to HEAD, offline tools, calc build, lockfiles, model digest 44a38603922e14f1e3ae68c5d900cc39f2a925a9749d12ab6d268d75a01a399f, prompt hash 4087d7db7c366eb91be41a22d19cabc096b691022613c48835f988320e628c99, think false, num_ctx 16384, num_predict 2048, temperature 0, max_turns 8, timeouts 120/300/14400 s, damage_rolls_in_result false). Run the seed-0 battery once through the seed-0 gate (--registration-commit), with RECOMMENDER_FIXED_NOW_UTC set at run time (the value is recorded in run_params) and --out outside the repository. Then run_params verify (without --allow-pending) while HEAD is still the registration commit and the tree is clean; only after that are the outputs copied in and committed.
2. Score with the frozen scorer; commit the scorer output.
3. Vu audits all 350 answers in audit.html and exports the exception CSV. Note conventions: missed_claim notes start FALSE: or TRUE:; wrong_verdict and wrong_extraction notes start NOW FALSE: or NOW TRUE: (the correct verdict of that claim); MANUAL TRUE:/MANUAL FALSE: on an `other` row records a manual verdict on a scorer-UNVERIFIABLE claim. The log is committed and hashed; the canary check runs; then audit_adjusted.py produces the verdict. The headline is withheld until the log is committed.
4. After the log is committed, unseal the gemma4:12b extraction cross-check (non-gating; prompt sha256 3c510e80a9480457badc3487ffe8f8b32d0985a892f9eeadc2a191c6a9688bcd, model digest c7597fc90b86aff6965317f37dd5465402284e26382d9b4bf2dfe3ef1491f4b6).
5. Report: adjusted and scorer-only headline; every FALSE claim with its rule; per-type, item-level, list-as-one, copied-unchanged, usage, UNVERIFIABLE, ability_plural lines; audit exceptions by type; canary results; extractor recall; items with no usable answer by cause; the manual UNVERIFIABLE line.

### stop_rule

One run. No re-run, resizing or re-scoring with changed rules after answers exist. Items that time out or error are reported as such and are not retried (see "items with no usable answer" under metric and thresholds). Infrastructure failure rule (Vu, 2026-10-24): if the run process dies for a non-model reason (power, Ollama crash) before the scorer output exists, resume only the unanswered items (those with no record) from the same worktree and params and disclose it; an item that has a record is never regenerated. If scored claims are below 240 the result is INCONCLUSIVE and is not extended in place; a new battery needs a new registration.

### before_run_evidence

pre_registration_sha (the commit that introduces this section) and the registration commit used for --registration-commit (the merge commit) cannot appear in the text they identify; both are recorded in the result artifact and in the push report. The merge commit descends from origin/main 18a3e62 (merge of PR #309, 2026-10-22T23:34:59-07:00; no squash). Between cc70d1c (last battery change) and 18a3e62 the only change under scripts/eval/part_g_v4 and data is a 23-line addition to part3_claim_battery_design_v4.md; no battery, key or data file changed. Freeze commit 92c03cbc5db551ffcd9f4579646a0dce9c227dca and manifest sha256 0972060c0d0b208c6a9669b079ab483bc82e855fcc8956d92fac63c0c780458a; freeze_manifest.py verify passes at the branch tip 838a775, and the diff of scripts/eval/part_g_v4, scripts/eval/run_params.py and scripts/eval/part_g_arm/run_battery.py since the freeze commit is empty (the later commits, the rehearsal driver 4485730 and the .gitignore change 838a775, touch no frozen file). The branch was pushed to origin at 838a775bb10c0bffd5c47ab50e98ad6377f55d40 before registration. RECOMMENDER_FIXED_NOW_UTC is set at run time and recorded in run_params. Procedure checks 3 and 4 (ancestor check; `git log -L` empty on the registered section, with the non-empty sanity run on the introducing commit) recorded in the result.

### confounders_controls

- Dev results are in-sample: every prompt, tool and rule change was made after reading dev answers. Dev numbers are not a forecast. Dev3b, in-sample: 1,236 scored claims, 5 false, bound 0.85%; item-level 4 of 350 items, bound 2.6%; all false claims are damage claims (4 of 202 before the last pattern).
- Rules set after reading dev answers and before any held-out run: gating choices, unit-slip and threshold rules, numeric rules, dedupe, ability_plural, roll-descriptor patterns, audit conventions.
- Claude Code read all 350 dev answers before the split; Claude annotated 40 items for blind recall; half T is not unseen. Annotator and extractor author are both Claude, in separate contexts.
- Extractor recall on dev: 98.9% strict on a fresh 20-item round (round 1 before fixes: 92.9%). Known unextracted families: bullet-label echo lines, negated roll-count prose, "does not guarantee" restatements; chance ranges are not extracted as ranges; a second, contradictory guaranteed_ko yes/no statement in one answer is not extracted (one polarity claim per answer); roll-descriptor min/lowest/top/bottom, "rolls above N", "can/could" modals and "n't" negation have synthetic tests only. The audit-adjusted count is the check on these.
- The audit checks extraction and verdicts against keys and tool output; it does not verify keys. Audit-adjusted counting is symmetric (corrections in both directions).
- Decoding: temperature 0 with seed unset and Modelfile defaults left as is (presence_penalty 1.5, top_k 20, top_p 0.95). Run-to-run determinism was not measured; this registration claims one run, not reproducibility of the output.
- damage_rolls are omitted from the default tool output (product-config choice made partly for the gate); it removed surface, not fabrication.
- Calendar drift: usage data are pinned by blob; usage-showdown-rollover.yml is disabled; usage-refresh-mc stays enabled (Vu, 2026-10-24); usage-showdown-rollover.yml did not trigger on 2026-10-24. The bot commits to main, not to the run worktree, so the pinned blobs and the run_params check are not affected; any pin or hash change before the registration commit is handled as a new freeze check.

### verdict_costs_accepted

- PASS permits exactly this statement: on this battery, model, temperature, tools and system prompt (rev3, hash 4087d7db7c366eb91be41a22d19cabc096b691022613c48835f988320e628c99), the 95% upper bound on the claim-level false rate is ≤ 2%, where FALSE means contradicts the frozen key. The word "reliable" is not used. If the tripwire above applies, the caveat is in the same sentence. A PASS does not carry over to a changed prompt.
- Published beside any result: scorer-only and adjusted numbers, item-level and per-type results, the non-gating lines, the unextracted families, and the does-not-cover list.
- FAIL blocks calling v1 done. INCONCLUSIVE also blocks. A second attempt needs a fresh battery and a new registration, limited to fixes the false list supports (tool, prompt or scorer rule), capped at one further attempt.
- Follow-up, not part of this registration: damage answers paraphrase tool output (dev3b median 45 words, max 115, against a 24.5-word median overall), and all gated FALSE claims on dev3b came from the arm's own paraphrase or arithmetic, not copied lines. A damage prompt that states the verdict and the key numbers without restating tool output is the first thing to try after the gate; it would need its own dev pass and a new registration to carry the claim.
- Expected, stated before the run: the item-level line (about 2 false items tolerated at about 350 items) is likely to fail even if the claim-level line passes; both are reported and only the claim-level line gates.

### does not cover

Right-by-luck answers through wrong reasoning or the wrong tool; process correctness; from-memory extras not in the keys; implied plural abilities for Mega forms and the follow-up risk; mutation handling and the validator path; the deferred request set; implicit use of illegal entities (false-legal battery, non-gating); Sturdy/Disguise handling in the calc tool; Mega-form usage beyond the Showdown items; usage percentage fidelity; chance-based nHKO statements; fabricated arithmetic no scorer rule can check; key correctness beyond the checks listed under oracle_source; multi-run determinism; answer clarity and verbosity (not measured; damage answers are the longest outside list-type answers, and some echo tool field names or restate tool output in tool-internal terms).

## PRE-RS-ARM: Stateful arm, class-scored request-set subset (descriptive)

REGISTRATION TEXT v6, 2026-10-28. Freeze commit 17f8fdd32247d67c09f325ab9c96512d7b6265ba is recorded below. This file's own commit is the registration commit (recorded in the registration PR merge); no covered row has been run to a model.

### hypothesis

This is a descriptive evaluation, not a test with a pass threshold. It records, for a pre-declared subset of the 134 request-set rows, whether one configuration of the stateful arm (qwen3.5:latest via Ollama, temperature 0, think off, the state tools and prompt listed under sample_dataset) produces the answer-key class for each turn, and for hand-audit rows whether the answer states the facts the key requires. Per ADR-078 the request-set rows are class-scored, not pooled. No headline rate over the 134 rows is claimed; the subset is a pre-declared upper bound of 103 rows chosen by tool readiness and scorability, never by how a row performed. There is no pass/fail threshold and no verdict word (Vu, 2026-10-28); the result is the reported counts and intervals below.

This configuration is not the Part G gate configuration. The Part G PASS (rev3 prompt, lookup tools, seed-0 claim battery; audit-adjusted 10 false of 1,273 scored claims, upper bound 0.013288) does not carry over: the tool set and the prompt differ. This evaluation also does not measure the shipped v1.0.0 CLI.

### metric

Per turn, by row bucket (never pooled across buckets):

- Mechanical buckets: the observed mechanical class of the turn (state change and pending-screen outcome, from the tool results and the state signature) against the key's per-turn class. Class vocabulary and precedence: wrote > bound > recorded > dismissed > refused > lookup only > no change. Result per turn: pass or fail. The class scorer is state/class_scorer.py at the freeze commit; where this text and the scorer disagree, the scorer at the freeze commit governs.
- Hand-audit rows: Vu audits the final text, tool calls and results against the key's rubric points (pass / fail / not applicable per point, plus an overall pass/fail), in the HTML form exported to CSV. A second model rater (gemma4:12b) gives a consistency check only and is never counted as scoring.
- Dual rows (MS5, RB1, TB2): the class is scored mechanically and the stated-fact points are hand-audited. Both results are reported.
- Counts reported: covered rows 103 (mechanical only 41, hand audit only 59, dual 3: MS5, RB1, TB2) (confirmed at the freeze commit); audit form sections 74 and rubric cells 242 for run 1 (OL7a and the other mechanical-only rows are not on the form) (confirmed at the freeze commit); pass and fail counts per bucket, per class, and per row. Exact (Clopper-Pearson) two-sided 95% binomial intervals are shown beside every reported pass count (Vu, 2026-10-28): per bucket (mechanical only, hand audit only, dual), per answer-key class, and overall for the 103 rows, at two units, row level (a row passes iff every scored turn and rubric point passes) and turn level. They are descriptive. The covered rows are a pre-declared subset, not a random sample; rows share fixtures and sibling structure and multi-turn rows are not independent; so an interval describes how much a count of this size can move, not a rate for the 134 rows or for the arm in general. No interval is compared with a threshold. Counts and intervals for run 1 are the result; runs 2 and 3 are shown beside them as differences, with their own intervals only if requested after the fact and labeled as such.
- Class rule: the key's per-turn classes govern; the request-set class cell is a summary. Errata (below) are recorded before the run; the request set file is not edited.
- No usable answer (timeout, tool error, turn cap, empty final text) is recorded as such, counts as a fail for that turn in the mechanical bucket, is never retried, and is reported by cause.

### errata and loader facts (recorded before the run; state/errata.json at the freeze commit)

- IC1: turn 1 SERVED, turn 2 MUTATION-OK (the cell says SERVED). IS2: PARTIAL + ASSUME-STATE. H15, DM1 and DM3 need no correction (single class ASSUME-STATE, "SERVED when basis stated" is the pass outcome inside it).
- MRB1: the loader locks Torkoal at user slot 3 with Drought and Charcoal (test assertion updated to match).
- H11: the frozen key reads each species' raw learnset (all 98 Mega entries have an empty raw learnset in the snapshot), so it counts Gyarados-Mega as a deliberate false positive. The product resolver (legal_moves_for, find_species, check_learnset) gives a Mega its base species' moves, and the key was written assuming the tool output would not include Gyarados-Mega, which no longer holds. Errata (Vu, 2026-10-27): Gyarados-Mega is "allowed, not required"; naming it is not a false claim and omitting it is not a miss; required members stay {Gyarados, Pelipper, Quaquaval}. derived_keys.json and the keys sha are unchanged.
- MT2 and H6: scored and audited normally. Their keys were pinned to in-game teammate data that goes stale on the next in-game refresh (about Nov 4); at the run pins they are not content-stale. A run after that refresh would need new keys. stale_pin_rows is empty (Vu, 2026-10-28).
- OL7a: the request-set cell says PARTIAL and the key is {bind Jolteon, ask}, other bind = fail. The cell is not wrong; it encodes an accepted set. Errata outcome_sets.OL7a: binding Jolteon passes, asking without mutation passes, binding the other option fails. Scored mechanically (the Spe 200 fact identifies the correct bind target and is not a separate hand point). Before this errata the scorer failed a correct "ask" and passed a bind of the other option; both were fixed before any covered run.
- Seeds are hand-written loader state (below). MT3 and HC2 constraints (no_intimidate, no_weather_ability) are hand-written judgment-only constraints, not produced by build_constraint from the user text; the history shows the scripted acknowledgement. The candidate-selection seed's option source "threat" is an arm-side default and its evidence is empty. The full-build-confirmation seed uses a hand-written fingerprint; commit_full_slot compares the stored strings and does not recompute it.

### sample_dataset

Request set: scripts/eval/part_g_v4/part3_request_set_v4.md, sha256 7fb9510cb50e8f1f320ac1cf6bced41e8dcd12f4245ed2abb03a42254a60afdb. Keys: derived_keys.json sha256 e70672541b5215e7bfff7eccb34dc321b2bde3a4b9cf08d1f5a6419be1d2309a (unchanged). Claim battery and false-legal battery shas unchanged (6e6c6be4..., 3025138427...).

Covered list (103 rows), state/covered_list.json sha256 007ee2e91c2d87c689fab1e364bcb9dd0f4e1dd61c03b853db5003bb50943316 at the freeze commit (frozen: true; before the freeze flag the file was ebde0d0ad9acdd51d477b7aeab039e6494bf3081b96b22c666fedf313243c4c1, ids unchanged): H1 H2 H3 H4 H5 H6 H7 H8 H11 H13 H14 H15 H16 H18b HF1 HF2 HN1 HN2 HN2b HN2c HN2d HN3 HN4 HP1 HP2 HP3 HU1 HU2 HU2b HU3 HU4 HC1 HC2 HD1 DM1 DM2 DM3 DM4 DM6 DM7 IS1 IS2 IS3 IS4 MV1 MV2 MV3 MS1 MS2 MS3 MS4 MS5 MS6 MS7 MS8 MR1 MR2 MR3 MR4 MR5 MR6 MR7 MR8 MRB1 MU1 MU2 MU3 MU4 MU5 MU6 MU7 MU8 MW1 MW2 MW3 MW4 Q9 Q10 OL2b OL4 OL5 OL6 OL7a OL8 OL9 MT1 MT2 MT3 MT5 MT6 IC1 TB1 TB2 MC1 SC2 GS1 RB1 IX1 IX5 IX7 MM1 MM2 H27.

The covered list is chosen by tool readiness and scorability, never by how a row performed. Rows that were coverable but left out are listed with the reason below; no row was added or removed after seeing model output on it, because no covered row has been run to a model.

Not covered (31), reasons as of the final tool set (state/LAST_NOT_COVERED_REASONS.md):
- H12: claim surface of 19 rubric cells; the reference trajectory is "no lookup needed", which is vacuous for the class scorer; needs an empty-team seed. H21: no frozen checklist; vacuous trajectory. H22: assumption-labeled aesthetic, vacuous trajectory (a frozen 4-item checklist exists; kept out by Vu's default).
- H17, H18, H19, H20: start from an empty team; show_candidates needs an all-locked anchor (including role) and refuses an empty team; a non-empty find_species pool is not a pass for H19/H20. edit_slot_field cannot set a role.
- H25, H26, MT4: the fixtures and seed lock species/ability/item only (not all-locked), so show_candidates refuses; the tool exists.
- OL1, OL2a, OL3, OL7b, OL10b: the frozen build-confirmation fixtures omit provisional_slot, so select_option cannot bind; OL10a: no presentation fingerprint, staleness undetectable.
- MT7, MT8: permanent dev rows. AR1, AR2: near-duplicates of MT7 turns 1 and 2, kept out. AR3: six-turn compound not built.
- SC1, SC3, DM5, TS1: fixtures not in the loader's slot base; the draft-condition store and draft retention across a topic switch are not built.
- GT1, LZ1: no pastes or usage-moves surface. IX2: no Showdown interaction tool. IX3: flags not exposed by get_move_static. IX4: the Good as Gold / Mold Breaker / Wandering Spirit multi-step interaction is not in any arm tool. IX6: no Unburden and White Herb interaction tool.

Arm configuration: branch eval/part-g-arm-state, freeze commit 17f8fdd32247d67c09f325ab9c96512d7b6265ba (clean tree), state/FROZEN_MANIFEST_ARM_STATE.json (status frozen, 28 files): manifest_sha256 of the files table 112e3b9de30c980bac315b8c6dcdd081486ad6e6d7f4756d9be041a3c1bbe4d0, sha256 of the committed file 59cde4846fbf5a1c546fb20383df75722fc6dd2a031838c5884ce26779e9a7d4. Prompt state/prompt.md sha256 bd2b69cde151fdb4dd2431c294ca46f4fbc251f54cebd82a13844d4eba0aaf86. tools.py sha256 e5dd309e0a6ce4afb9eeddc0b2bb2172ea79086feda8e7ff07a3158ae4dd5d42. Seeds: SHA256SUMS file sha256 e7537618c1105aeeeb9273d8ed0045370bd8eecabcea5586f78f14a46f47b2ba (cs_pending 34495be395c0f53e38319fd438c9bbbfc0e5174691d6d13bcb3be02e1999b6eb, fbc_pending 4337ddd0dc15d319bbef0bc1ea8cbc9f978c45fa9de1768534b291df3de50af6, mt3_after_t1 0f6d61eb95dd6678301bdc91a3a746af2c8096f196e85b813f381e7d3f7720b2, hc2_after_t1 9d67bd3b7cc38cc7ad5c41fde9be130cdafdaceeb85bcb2f3dff8b34bbfab4f9, hd1_history 331da9c022897b7294549b01643ee7f6201cc82ad2ba4a8c74cde670606dd7c7). errata.json sha256 2d8133d8e67b86e20b8f490e3f4a54b6f2840104667a9709c10f4cb0b9ca1d5a; request_set_runner.py eca6dd7498c39dfc0fa6d974d4d875393e0d45cf34ed4362ee981d0b347ca70a; class_scorer.py 8f97b299a5392eef8237df7fda757af2dedfb04067e25eeec367554f0e31a8f4; compare_runs.py 2ae62010fd6aee73cfa122d691cc49ada2657d0de14d429a507c3caf6a2df6e4; hand_audit_form.py 9cce632b311d5fb6a5d34bb5ced781668c10335d55d69fd76e39d68b454b4010; clopper_pearson.py ceae2c5efd5f3b9b552d438b9916bdfc35c6dd51943193b3c58d654195a3d1e4; exploratory_runner.py 24d5f2f2ba0287c8f94cf1277dd709de712e1c0b9696a6efa3c9c8a07ef545c0; judge_prompt.md 89b9900570368074fd45a1ce44981e57fcd6e3da8f3c46f4dbcbb0fc437e5d87; dev_keys.json aa0e9169b45a20ece32376ac67a826b0d4898442c698c9860d87a0866b4a8e06; dev_keys_prankster_weather.json 6dba1caac2d45135779779f7867f6f442163bdb3fef35ca6270d7c76329fb543; dev_rows.json b7e31f60ae2af645d6275774a518c1abc0a93990663c4603de571dc9e827a311 (values at branch head 6543a0b; the freeze commit's FROZEN_MANIFEST_ARM_STATE.json is authoritative; the values above matched it at the freeze). Runner, class scorer, errata, judge prompt (sha256 89b9900570368074fd45a1ce44981e57fcd6e3da8f3c46f4dbcbb0fc437e5d87) and hand-audit form generator at the freeze commit.

Tools (state tools wrap the existing validated nodes; no new legality code): lock_slot (species only), unlock_slot, reset_team, commit_slot/confirm_build, read_team, read_pending, select_option, reject_pending/reject_option/reject_all, read_rejected, edit_slot_field (with computed consequences), add_constraint/read_constraints/restore_constraint, show_candidates (the CLI candidate producer, no LLM), change_archetype/read_archetype, check_learnset, check_hypothetical, solve_spread, find_species, get_move_static (with priority), and the lookup tools. The candidate list and its order are tool-determined; the model decides when to call and how to narrate. The mega-stone rule (ADR-002 Amendment 2026-10-27a, PR #318) is in the validator the tools call.

Model: qwen3.5:latest, digest 44a38603922e14f1e3ae68c5d900cc39f2a925a9749d12ab6d268d75a01a399f, Q4_K_M, temperature 0, think false, num_ctx 16384, num_predict 2048 (equals the Part G gate value, confirmed in the freeze-prep verify), no seed. Failure policy (fixed before the run): 300 s per turn, at most 16 tool calls per turn, no usable answer recorded with no retry, resume via progress.json after interruption.

Data: pinned legality snapshot, in-game and Showdown blobs as pinned (usage-showdown-rollover disabled; usage-refresh-mc is scheduled daily and not paused at the freeze; any pause is decided at the 2026-11-01 check and recorded). The spread solver references the Showdown ladder joint spreads (blob 63bcefe4512a202d75b62e79f2ccc5436527b46e; top 8 per species kept by the pin; entries filtered to a 66-SP total; 88 of 2,528 dropped; 39 of 355 legal species have no joint data). Showdown data is ladder data, not in-game data. Opponent natures are user-stated inputs.

Dev set: 44 dev rows (species and fixtures not among the 134, keys written before any model run), including MT7 and MT8 as permanent dev rows graded by hand. Prompt history after the A5 freeze: b7176485 -> c58e3ce8 (rejected: MT7/MT8 wrote the team) -> 08a0917a -> bd2b69cd (adds the find_species description and one reply-rule sentence); all tuned on dev rows only. Dev results on the final tools: 42 of 44 pass.

Run design: three sequential runs on identical settings. Run 1 is the primary result, declared here before it starts. Runs 2 and 3 are determinism checks; per-row differences in class, ordered tool calls (name and arguments) and the sha256 of the final text are listed beside run 1, never averaged and never replacing it.

### oracle_source

The keys are the frozen keys (ADR-078) derived from the pinned calc and pinned Showdown data; independence is partial as stated in PRE-MD-CLAIM. The H11 key's scope is the raw learnset (see errata). The Prankster dev key and the weather-move list (product constant WEATHER_SETTING_MOVES, a hand-written list, conditional setters excluded) are dev material and not part of the scored rows. FALSE means contradicts the frozen key (after errata), not contradicts the game.

### analysis_plan

1. Freeze: Vu approves the covered list, prompt sha, tools sha, seeds and manifest; Cursor commits the freeze on a clean tree; this section is registered with the freeze commit and manifest shas filled; pre_registration_sha and the registration commit are recorded in the result artifact (they cannot appear in this text).
2. Run 1, then runs 2 and 3, from a clean worktree at the registration commit, with the pin check before each run. Outputs outside the repo until post-run verification.
3. Score: mechanical class scorer on all mechanical and dual rows; compare_runs.py across runs.
3b. Exploratory observation (declared here, before any run): after run 3 has finished and its outputs are committed, the arm is run once, on the same configuration, on the 31 not-covered rows (including the dev rows MT7 and MT8) in a separate output directory. Rows whose fixture will not load are recorded as load failures. These transcripts are not scored, are not audited for pass or fail, are in no count or interval, and are used for no change to the prompt, tools, keys, covered list or errata of this registration. They are published as raw transcripts beside the result, labelled exploratory. Any change prompted by them requires a new registration.
4. Vu audits run 1 in the hand-audit form (74 sections, 242 rubric cells, plus any rows that differ in runs 2 and 3); the form shows no scorer or model verdict; the gemma judge output is merged after Vu exports. Audit conventions are fixed before any result is seen: the counting unit is the rubric cell (the Part G unit was the extracted claim), and no row or cell is relabeled or dropped after results are seen, as in Part G, where a spurious extractor claim stayed in the count.
5. Report: per-bucket and per-class counts with exact 95% intervals (row and turn level), every failed turn with its transcript reference, dev findings, run 2/3 differences, no-usable-answer cases by cause, judge agreement with Vu, errata applied.

### stop_rule

One registered attempt per run. No row is re-run or re-scored with changed rules after answers exist; no prompt, tool or key change after the freeze. Infrastructure failure (power, Ollama crash) before scorer output: resume only unanswered turns from the same worktree and parameters and disclose it. If any covered row is used to debug, that run is a development run and no class count from it is a result. If the run slips so that usage-refresh-mc re-pins (about Nov 4), the keys are invalidated and the run is void. Whether to pause usage-refresh-mc is decided at the 2026-11-01 check if the run will not have finished by Nov 3, and the decision is recorded.

### before_run_evidence

Freeze evidence (2026-10-28): freeze commit 17f8fdd32247d67c09f325ab9c96512d7b6265ba, containing only FROZEN_MANIFEST_ARM_STATE.json and covered_list.json (frozen: true). Verify: PASS frozen manifest on a clean tree. Counts re-confirmed at the freeze: 103 covered (41/59/3), form 74 sections / 242 cells. Keys sha e70672541b5215e7bfff7eccb34dc321b2bde3a4b9cf08d1f5a6419be1d2309a and request set sha 7fb9510cb50e8f1f320ac1cf6bced41e8dcd12f4245ed2abb03a42254a60afdb unchanged; errata sha 2d8133d8e67b86e20b8f490e3f4a54b6f2840104667a9709c10f4cb0b9ca1d5a. Suites: pytest 4785 passed, 14 skipped; npm test 119 passed; run_all_checks PASS (ar3 replay 602/602); check_pins PASS, 14 pins match, calc @smogon/calc 0.11.0-champions.5d5bf43 (vendor/smogon-calc), calc health ok before and after. Batteries: claim 6e6c6be4351240629416f1e279bbf495bbf4670d79aaaa7d083a2c62c6d67443, false_legal 3025138427391e57a92e1862a87b0074d44a51b290836077abf094af92c4bdec. origin/main base 707642bbadb481711356bb1ffeba959d9b0053f4 (merge-base the same). Ancestry: keys last cut at 96b87e7 (2026-10-20, #286); covered list content (103 ids) at 5804500 (2026-10-28); both precede the freeze commit and any covered run. No covered row has been run to a model: no run directory and no run commits exist. The only model runs are dev rows.

### confounders_controls

- Dev is in-sample: every prompt and tool change was made after reading dev answers. Dev numbers are not a forecast.
- Tuning touched the prompt three times after the A5 freeze (history above), on dev rows. The dev Mega rows were added after the last prompt revision and were run once without tuning.
- Hand-audit rows are judged by one person (Vu), who knows the keys; the second rater under-flags (calibration: agreement 20 of 22, 2 false passes of 12 planted errors, untuned).
- Run-to-run determinism: temperature 0 with no seed; runs 2 and 3 measure it for this configuration only.
- The 46 hand-rolled rows were reviewed for dev counterparts at planning (request_set_eval_plan_2026-10-25, disclosures). Dev rows use species and fixture ids different from the request-set rows and were frozen before any covered row ran.
- Showdown joint-spread references come from ladder data; the solver claim wording is "within d SP of rank r of the 66-SP joint spreads in the pinned Showdown data", never "best", never a share of players.

### verdict_costs_accepted

- The result is described as a subset of 103 pre-declared rows, never as the request-set rate. Buckets are reported separately; the overall count with its interval is shown but is not a headline rate and has no threshold.
- A pass on a row means this configuration produced the key's class (and facts) on one run. It does not establish reliability, and it does not carry over to a changed prompt or tool set.
- Known dev findings published beside the result: multi-call enumeration and union is unreliable on this model (the Prankster weather dev row); on a bare "could I put <Mega> on my team" question the arm can answer from a legality lookup without the stone requirement (dev-mega-bare-hyp; no covered row sends that turn type); MT7/MT8 turn 3 calls add_constraint without being asked (not a class failure); the judge under-flags.
- A failed row is a finding about the arm, not a reason to change it before the report.

### does not cover

Behavior on the 31 not-covered rows is observed once, exploratorily, after the registered runs (analysis_plan 3b) and is neither scored nor inferred from. Scored behavior on the 31 not-covered rows; the shipped CLI; a web UI; multi-run stability beyond three runs on one machine; right-by-luck answers through the wrong tool; key correctness beyond ADR-078 and the checks listed in PRE-MD-CLAIM; in-game accuracy of Showdown ladder spreads; model-API (Claude) behavior (blocked on a key; not measured); the species+ability concatenation tool-call pattern seen in Part G (unmeasured here).

## Amendments to registrations
