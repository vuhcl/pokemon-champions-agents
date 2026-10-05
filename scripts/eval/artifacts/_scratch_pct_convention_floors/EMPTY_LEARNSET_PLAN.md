# Plan-first: empty learnset keys block forme inheritance

**Status:** confirmed at runtime (2026-10-05). **Do not implement in #245 / pct-convention PR.** Separate follow-up after merge.

## Symptom

Five Champions formes have a **present empty** learnset key in the legality snapshot:

`gourgeistsuper`, `vivillonfancy`, `vivillonpokeball`, `polteageistantique`, `sinistchamasterpiece`

`resolve_learnset` returns `[]` immediately when `sid in learnsets`, so it never walks `base_species_id`. Contrast: `gourgeistlarge` has a **missing** key → inherits base Gourgeist (60 moves) → `check_set(..., Trick Room)` OK. Gourgeist-Super + Trick Room / Protect fails with `learnset: not in Champions learnset`. Super is absent from the B6 Trick Room draft despite usage.

Probe: `probe_empty_learnset.py` in this directory.

## Root cause (two layers)

1. **Extract** (`scripts/extract_legality/learnsets.ts`): when Showdown’s forme entry has `learnset === undefined`, extract writes `out[id] = []` instead of omitting the key (megas correctly omit).
2. **Resolve** (`recommender/legality.py` `resolve_learnset`): treats any present key — including `[]` — as authoritative and stops the base walk.

## Fix-site options (pick in follow-up; recommend both)

| Option | Change | Pros | Cons |
| --- | --- | --- | --- |
| A. Resolve only | Treat `[]` as missing; continue `base_species_id` walk | Small Python diff; fixes all consumers of `resolve_learnset` | Leaves lying empty keys in snapshot |
| B. Extract only | Omit key when `learnset` undefined (same as megas) | Honest snapshot; matches Large / Mega pattern | Needs snapshot regen; anyone reading `learnsets[sid]` raw still needs care |
| **C. Both (recommended)** | Extract omits; resolve treats `[]` as missing as belt-and-suspenders | Correct data + defensive runtime | Two sites + regen |

Do **not** invent forme-specific move lists by hand.

## Other consumers of `learnsets[sid]` (bypass `resolve_learnset`)

Production recommender paths already go through `resolve_learnset` (setup, support, weather, slot_fill, move_narrowing, prior_standin, bootstrap_role_nn, contingent_value, role_aware_synthesis, nodes_classify).

**Direct `learnsets[...]` reads found:**

- `recommender/legality.py` — only inside `resolve_learnset` itself
- Scratch/probes: `probe_empty_learnset.py`, `_scratch_b2c_retarget_pins/legality_flips.py`
- Tests: `tests/recommender/test_recommend.py` (asserts mega key **absent** — same invariant we want for these five)

No second production bypass to patch beyond resolve + extract.

## Tests (all five formes)

1. Snapshot / extract: each of the five either **absent** from `learnsets` or non-empty after fix; never `[]`.
2. `resolve_learnset(snap, sid)` returns the base pool (non-empty) for each.
3. `check_set` with **Trick Room** on **Gourgeist-Super** succeeds (and Protect if already in base).
4. Parallel smoke for the other four formes with at least one base-legal move each.
5. Regression: megas still omit learnset keys; `swampertmega` stays absent.

## After the fix lands

Regenerate B6 scratch drafts (dry-run only — no critic / persist / archive). Super should appear in the Trick Room draft if usage + floors admit it. Roles/marker hashes must still be guarded unchanged until Vu signs off on persist.

## Out of scope here

- Part C ability-usage audit
- Forme-resolution follow-up (cosmetic / battle_transform / mechanical_selectable)
- Floor constant edits
