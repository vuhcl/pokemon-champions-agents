# Phase 2 report — fail-closed unmatched clarify (Approach A)

## Control validity
- Control HEAD: `9621b772ee5edd26b223c2ed70546a8079fb3a87`
- `origin/main` tip after fetch: same SHA (no recommender/ drift). Control valid; branch cut from that tip.

## Snapshot integrity
- Source `/tmp/det_graph_capability` ↔ `det_graph_capability_baseline_88df2d7/` (103 files, excluding `SNAPSHOT_META.md`)
- Tree SHA-256: `9deb1237df202cb9a4762477d5f1f25e916b44705f9920c11dbe4d33ec227500` (match before/after copy)
- `meta.json` head: `88df2d7bda5e0f357e98631b7fd821aba6c328af`

## Gate 0 relabel (Step0 addendum A–D)
- Buckets: echo_soft_refuse (7), unactionable_offer (8), defect_prose (4), unique_UX (0)
- **pending_kind_counts:** `{None: 19}` — all llm_authored rows idle
- Sampling caveat: **no mid-flow evidence in this corpus**
- S2 qwen2.5: `MISROUTED` (not in llm_authored table); S2/S8 qwen3.5 and S8 qwen2.5: `FAIL-CLOSED`
- D1: idle; under A idle → "Didn't catch that."; under full_build → CLASSIFY_FAIL + build body/footer. Idle UX loss logged; not unique_UX. Plan unchanged.
- Hostile scope: idle + every `PendingPresentation.kind` (not narrowed)

## Control vs after (P1–P3, S7)

| id | model | changed | control message | after message |
|---|---|---|---|---|
| P1 | qwen2.5 | no | That action isn't available here. | same |
| P2 | qwen2.5 | no | That action isn't available here. | same |
| P3 | qwen2.5 | no | CLASSIFY_FAIL_USER_MSG | same |
| S7 | qwen2.5 | no | CLASSIFY_FAIL_USER_MSG | same |
| P1 | qwen3.5 | **yes** | Specs Chi-Yu OHKO prose… | Didn't catch that. |
| P2 | qwen3.5 | **yes** | Miraidon+Scarf slot ask… | Didn't catch that. |
| P3 | qwen3.5 | **yes** | Walking Wake add/support… | Didn't catch that. |
| S7 | qwen3.5 | **yes** | two Choice Scarf / no Item Clause… | Didn't catch that. |

Full visible strings (with roster line) are in `control_vs_after.json`.

## v2 verifier scores
See `v2_verifier_scores.json`. Baseline scores were already zero on defect probes despite false prose — v2 false-legal gate is blind to this defect class (not fixed here). After scores remain zero on the replaced templates.

## Hostile / complete-phase tests
- `tests/recommender/test_failclosed_pending_clarify.py`: idle + every kind parametrized; stamp check; complete-phase roster regression.
- Targeted run: 68 passed (failclosed + present_text + turn_intent slices).

## bootstrap_exc_probe.json (not fixed in this PR)
YES — raw model text can appear under `Bootstrap intake error: …`. Separate backlog item.

## Follow-ups (not in PR)
- Idle unmatched shows no pointer to supported actions (`UNMATCHED_REPLY_PREFIX` unchanged)
- bootstrap_intake_error redaction
- v2 verifier coverage for free-text legality claims
