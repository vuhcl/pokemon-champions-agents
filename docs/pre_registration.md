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

   Note: `git diff <A> <B> -L …` is **not** usable here — Git's `-L` walk
   accepts at most one positive revision (`git diff` two-commit form fails with
   `bad revision` / `invalid object name` on the `-L` argument). Use `git log
   -L` as above.
5. **Pin usage (and other mutable data) by blob SHA or tag.** Record the blob
   SHAs of the usage files used (or a pinned tag). The daily in-game refresh
   bot commits move usage ranks and change data under a fixed method; a method
   SHA alone is not enough to reproduce a data-dependent result.
6. **Amendments are append-only.** After a run, do not edit the original
   registration text. Append a dated amendment under that section (or a new
   section that supersedes by id + date). Changing metric, thresholds, oracle,
   or sample requires a new registration (new SHA) before any comparable
   remeasure.

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
| PRE-MD-CLAIM | not yet registered | — | Model-driven arm vs deterministic baseline — claim verification (false-claim rate, false-legal rate, unverifiable-share cap; ≤2% ceiling decided for those gated metrics) | — |
| PRE-MD-ROUTE | not yet registered | — | Routing correctness of the model-chosen tool vs the request (right facts, wrong question) | — |
| PRE-MD-THEME | not yet registered | — | Theme handling slice — claim correctness and honest labeling of model-interpreted sets only (no viability or win-rate metric) | — |
| PRE-EXCELLENT-FLOOR | not yet registered | — | Relative Excellent-damage-floor robustness (`recommender/role_compendium_setup.py` Excellent floor = 2nd-highest adjusted × 0.95); method class is Vu's choice | — |

No registration in this file is marked `registered`. Nothing is registered by
the commit that introduced this skeleton.
