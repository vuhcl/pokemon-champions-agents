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

## Amendments to registrations
