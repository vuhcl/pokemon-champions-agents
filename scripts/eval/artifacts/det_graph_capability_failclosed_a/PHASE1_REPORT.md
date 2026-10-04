# Phase 1 report — fail-closed unmatched clarify (Approach A)

**Status:** STOP after Phase 1. No recommender/ or tests/ code changes. No commit/push. Awaiting Vu for Phase 2.

**Control HEAD:** `9621b772ee5edd26b223c2ed70546a8079fb3a87` (merge #229)  
**Baseline HEAD:** `88df2d7bda5e0f357e98631b7fd821aba6c328af`

---

## 1. Snapshot

- Copied `/tmp/det_graph_capability` → `scripts/eval/artifacts/det_graph_capability_baseline_88df2d7/`
- Verified `meta.json` `head` starts with `88df2d7`
- **Size:** 4.1M total (206 files); `runs/` 1.8M
- **Proposal:** commit the snapshot (small enough; eval_results / v2 pre-registration can cite it). No gitignore/manifest needed at this size. **Not committed yet** (per instructions).

---

## 2. Gate 0

Artifacts:

- `ux_cost_gate0.json`
- `ux_cost_gate0.md`

**Sampling caveat:** CAP25 is mostly idle / shallow seeds and barely exercises mid-flow `PendingPresentation` kinds. `unique_UX_count == 0` on this corpus is weak evidence for mid-flow clarify quality.

| Model | canned | llm_authored |
|---|---:|---:|
| qwen2.5_7b | 11 | 7 |
| qwen3.5_latest | 1 | 12 |

**unique_UX_count:** 0 → did not stop for Vu on unique_UX.

### Full llm_authored table (Vu reviews buckets)

| request_id | model | bucket | reason | message (truncated) |
|---|---|---|---|---|
| S4 | qwen2.5_7b | state_rebuildable | Slot/option ask recoverable | Which of your picks do you want to swap for something that threatens Kingambit? |
| S6 | qwen2.5_7b | echo_soft_refuse | Restates user Q | Why did you pick Farigiraf over Hatterene? |
| S8 | qwen2.5_7b | echo_soft_refuse | Restates user Q | What do you consider the best criteria for evaluating a team in Reg M-C? |
| i7 | qwen2.5_7b | echo_soft_refuse | Restates user Q | Which Pokémon pairs with both Torkoal and Scovillain? |
| i8L | qwen2.5_7b | echo_soft_refuse | Restates user Q | What support does Hatterene need? |
| C2 | qwen2.5_7b | echo_soft_refuse | Restates user Q | Does Jolly vs Adamant change which threats your Garchomp outspeeds? |
| C3 | qwen2.5_7b | echo_soft_refuse | Restates user Q | Does max Attack on Kingambit change what it OHKOs? |
| S2 | qwen3.5_latest | state_rebuildable | Soft help / visibility | I'd be happy to help you find a bulky Fire-type… |
| S4 | qwen3.5_latest | state_rebuildable | Asks for slot | I don't have visibility into your current roster… |
| S7 | qwen3.5_latest | echo_soft_refuse | False Item Clause; idle refuse recovers | Yes, you can run two Choice Scarf users… no restriction against duplicate items… |
| S8 | qwen3.5_latest | echo_soft_refuse | Soft help | I can help you find strong Reg M-C teams!… |
| i6L | qwen3.5_latest | state_rebuildable | Slot/build ask | Could you clarify which roster slot… Garchomp with Scarf… |
| i7 | qwen3.5_latest | echo_soft_refuse | Soft help | I'd be happy to help with pairing suggestions!… |
| C1 | qwen3.5_latest | state_rebuildable | Asks for threats | I can help you analyze that!… which opponents… |
| C4 | qwen3.5_latest | state_rebuildable | Asks team/strategy | To help you decide between Modest and Timid… |
| D1 | qwen3.5_latest | state_rebuildable | Spread preference ask | Which spread would you prefer? Max Defense… |
| P1 | qwen3.5_latest | echo_soft_refuse | Illegal-entity prose; refuse recovers | Specs Chi-Yu … could potentially OHKO Kingambit… |
| P2 | qwen3.5_latest | echo_soft_refuse | Illegal-entity prose | Which slot… Miraidon with Scarf… |
| P3 | qwen3.5_latest | echo_soft_refuse | Illegal-entity prose | add Walking Wake… |

### Passthrough-test inventory (re-checked)

Repo search for `_clarify_parser(`, `Which field should change?`, `What should change about the build?` under `tests/`:

1. `tests/recommender/test_turn_intent.py:88-102` `test_gap_fill_bare_no_on_full_build_keeps_pending` — direct gap-fill model-message passthrough.
2. `tests/recommender/test_present_text.py:850-862` `test_unmatched_custom_message_replaces_prefix` — format_turn fixture with that string.
3. Helper only: `test_turn_intent.py:51-57` `_clarify_parser` default (no assert of passthrough by itself).
4. Related but not model-passthrough: `test_cli_repl.py:759-772` empty → `UNMATCHED_REPLY_PREFIX`.

**No additional passthrough assert sites found.**

**Accepted UX note for draft log:** full_build template under A is generic `CLASSIFY_FAIL_USER_MSG` (“name the field, value, scope”), not the model’s tailored “Which field should change?” — small accepted UX loss.

---

## 3. Control run (current HEAD, no A)

Harness copy: `run_discovery_control.py` with `OUT=…/failclosed_a/control`.  
Command: `uv run python …/run_discovery_control.py P1 P2 P3 S7`  
Log: `control/control_run.log`

Required `uv sync --extra ollama` (missing `langchain_ollama` in env); restored `--extra dev` afterward.

### Control visible messages (payload.message)

| ID | qwen2.5:7b | qwen3.5:latest |
|---|---|---|
| P1 | That action isn't available here. | Specs Chi-Yu OHKO / Choice Specs discussable (same as baseline) |
| P2 | That action isn't available here. | Miraidon + Scarf slot offer (same as baseline) |
| P3 | CLASSIFY_FAIL_USER_MSG (field/value/scope) | Walking Wake add/support offer (same as baseline) |
| S7 | CLASSIFY_FAIL_USER_MSG | “no restriction against duplicate items…” (same as baseline) |

All eight outcomes: `FAIL-CLOSED` (no state change). Full texts: `baseline_vs_control.json`.

---

## 4. Baseline vs control (data/HEAD drift only)

| | Baseline | Control |
|---|---|---|
| HEAD | `88df2d7…` | `9621b77…` (#229) |

**Result:** all 8 probe `payload.message` strings are **byte-equal** baseline ↔ control (`message_equal: true` for every row).

So on P1–P3/S7, HEAD/data drift from 88df2d7 → 9621b77 did **not** change the unmatched free-text defect surface. Attribution of a future after-run change to A remains clean for these probes (control still required by protocol).

---

## 5. Baseline verifier scores (`score_transcript`)

Artifact: `v2_verifier_scores.json` (`calc_ok=false` for offline calc; structural/legality/species still scored).

| ID | model | false_legal | false_illegal | species FALSE | mech FALSE | item_clause | note |
|---|---|---:|---:|---:|---:|---|---|
| P1–P3,S7 | qwen2.5_7b | 0 | 0 | 0 | 0 | null | canned mismatch/CLASSIFY_FAIL only |
| P1 | qwen3.5_latest | 0 | 0 | 0 | 0 | null | **1 mech unverifiable_shape**; false OHKO prose not FALSE |
| P2,P3 | qwen3.5_latest | 0 | 0 | 0 | 0 | null | illegal entities discussable; **not flagged** |
| S7 | qwen3.5_latest | 0 | 0 | 0 | 0 | null | false “no duplicate item restriction”; **not flagged** (Item Clause only on completed teams) |

**Finding:** despite visible false-legal / false-rules prose on qwen3.5 P1–P3/S7, `score_transcript` returns zeros on false_legal / false_illegal / species FALSE / item_clause. **The v2 false-legal gate cannot see this defect class** and would need an additional verifier. Not fixed in this task.

---

## 6. Three investigations (not widening A)

### a. `bootstrap_intake_error` / model text — **YES**

Code path:

1. `parse_bootstrap_intake` ([recommender/bootstrap.py](recommender/bootstrap.py) 125–128, 142–147) wraps `parsing_error` / `ValidationError` / `Exception` as `BootstrapIntakeParseError(f"…{exc}")` with **no redaction**.
2. `classify_pending` sets `bootstrap_intake_error=str(exc)` ([nodes_classify.py](recommender/nodes_classify.py) 1575–1578).
3. `format_turn` displays `Bootstrap intake error: {bootstrap_err}` ([present_text.py](recommender/present_text.py) 689–690).

Contrast: turn-intent path maps parse failures to `CLASSIFY_FAIL_USER_MSG` and strips `OUTPUT_PARSING_FAILURE` ([test_turn_intent.py](tests/recommender/test_turn_intent.py) 845–858). Bootstrap does not.

Probe artifact: `bootstrap_exc_probe.json`.  
**Separate backlog item** — do not fold into A.

### b. ADR-048 `format_no_pending` / `team_phase` — **never existed in code**

- `git log -S team_phase -- recommender/present_text.py` → **no commits** (empty).
- `format_no_pending` introduced in `df8a024` (“fix: clarify idle and ambiguous candidate presentation”) already as discovery-error vs `NO_PENDING_MESSAGE` only — **no** `team_phase == "complete"` branch (verified at that commit).
- Complete-team roster + `last_team_review` rendering was added to **`format_turn`’s pending-None branch** in `26c991e` (“Surface locked builds and team review findings…”), not to `format_no_pending`.

**Conclusion for Vu:** ADR-048 text that says `format_no_pending` gained a `team_phase == "complete"` branch appears **wrong from the start** (conflated with `format_turn` work), not a later regression that removed the branch.

### c. Passthrough re-check

No third test file asserts model-authored gap-fill message passthrough beyond the two inventoried sites (+ helper / empty-prefix related test). Inventory above is complete for current `tests/`.

---

## Draft ADR / log text (report only — do not paste into mirror docs yet)

**New ADR (recommended title):** Fail-closed unmatched clarify — discard model-authored `pending_response.message` on the deterministic `_gap_fill` path.

**Context:** Capability discovery (2026-10-04, baseline HEAD 88df2d7) showed qwen3.5 free-text unmatched replies treating illegal entities as usable and asserting no Item Clause; the type/ability guard (ADR-051 Amendment 2026-09-05a) extracted zero claims. Legality must never be an LLM assertion (ADR-002).

**Decision:** On `_gap_fill` after `parse_turn_intent`, if `turn_intent == pending_response` and message is not in the deterministic allowlist (`NON_CLAIM_MESSAGES` + gate constants), replace with `clarify_message_from_pending` (idle → `Didn't catch that.`; full_build → `CLASSIFY_FAIL_USER_MSG`). Keep `rewrite_pending_response_message` at `_payload_for` for model-driven backstop. Do not route complete unmatched through `format_no_pending`.

**UX note:** full_build unmatched uses generic field/value/scope ask, not a model-tailored “Which field should change?” — accepted small UX loss.

**Cross-links:** ADR-002, ADR-051 (guard retained), ADR-048 (complete rendering stays on `format_turn`).

**Open / separate:** bootstrap_intake_error may surface model text via `str(exc)`; v2 `score_transcript` blind to this defect class.

---

## Phase 1 stop

Ready for Vu to review Gate 0 buckets and green-light Phase 2 (feature branch + implementation + after-run).
