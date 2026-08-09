# Team-Phase Routing Current-State Verification

**Date:** 2026-08-08  
**Audience:** Vu / implementation review  
**Status:** Direct-source discovery record. No routing implementation is claimed here.

## Purpose and scope

This report re-verifies the live graph after the anchor-role / target-role Tracks A-C work.
It uses the corrected phase boundary established by the scenario follow-up:

1. `empty` — zero fully confirmed members;
2. `single_locked` — one fully confirmed member;
3. `multi_locked` — two or more fully confirmed members while any slot remains open;
4. `complete` — every roster slot is fully confirmed.

`all_locked` is the confirmation boundary: role, species, ability, item, moveset, nature,
and spread must all be locked. Partial steering remains valid state, but is not promoted to
a confirmed member.

The deferred backlog is status-checked only. None of it belongs to this routing pass.

## Executive findings

1. **Verified:** no executable `route_team_phase`, `bootstrap_direction`, or
   `post_lock_review` exists.
2. **Verified:** `accept_available_pool` is a no-op and routes directly to
   `propose_team_draft`.
3. **Verified:** empty-team proposal can reach `_pick_role`'s low-confidence
   `bulky_attacker` coverage-gap fallback. No opening direction/pool interaction exists.
4. **Verified:** Track C added a production-quality anchored context constructor and the
   provisional-build / confirmation / atomic-commit lifecycle, but the graph never dispatches
   to anchored discovery.
5. **Verified:** `compute_team_coverage` and `detect_spof` are callable and tested. Their
   outputs are not persisted as team-wide working signals, and no phase trigger recomputes
   them after each lock.
6. **Verified:** no teammate query API or shared-teammate intersection exists.
7. **Verified:** `generate_team_review` computes threats, coverage, and SPOFs, but is reached
   only by explicit `team_review` intent—not roster completion.
8. **Verified:** successful ordinary and atomic locks route directly back to the legacy
   proposal node. Track C does not structurally trigger post-lock team-wide recomputation.

## Phase capability matrix

### `empty`

**Current dispatch:** `initialize -> accept_available_pool -> propose_team_draft`.

**Real existing capability:**

- initialization and available-pool persistence;
- legacy dependency-circle refinement;
- usage and role helpers callable below the graph.

**Missing/new interaction design:**

- one opening interaction that asks for direction/anchor and available pool together;
- delegated owned-first direction recommendation;
- a pending-state contract for that interaction.

**Routing-pass boundary:** add an explicit phase destination, but label it as a legacy
adapter. Do not imply that bootstrap behavior is implemented.

### `single_locked`

**Real existing capability:**

- `build_anchored_slot_fill_context` resolves the anchor build, classifies anchor role,
  derives `RoleShapeContext`, and runs support-needs plus threat-counter queries;
- `annotate_overlap`, `resolve_all_support_needs`, `merge_need_resolved`,
  `present_candidates`, and `run_slot_fill_terminal` provide the existing consumption chain;
- candidate acceptance, provisional refinement, full-build confirmation, and atomic commit
  are graph-connected.

**Still missing or partial:**

- no production graph caller composes the anchored chain;
- the constructor does not pass an owned-first policy;
- target-role Compendium candidates are not queried;
- only currently mapped support needs produce target-role decisions, so threat-only
  candidates can remain unresolved;
- no-candidate behavior has no dedicated interaction and must retain a labeled legacy
  fallback.

**Routing-pass boundary:** real dispatch to the existing chain, preserving unresolved
outcomes. Do not add ownership, Compendium expansion, or a new role heuristic.

### `multi_locked`

**Real existing capability:**

- `get_relevant_threats`;
- `compute_team_coverage(team_draft, threats, ...)`;
- `detect_spof(team_draft, threats, ...)`;
- thread-scoped full-result matchup caching;
- `team_need_flags` already reads `coverage` and `spofs`, although those keys are not typed
  or populated by the live graph.

**Still missing or partial:**

- no phase dispatcher or post-lock refresh;
- no full team-gap candidate-discovery/ranking orchestrator;
- no shared-teammate query/intersection;
- no condition-resilience, role-duplication, attacker/support/balance, or selected-four
  signal implementation.

**Routing-pass boundary:** recompute and persist the callable coverage/SPOF signals on every
entry after a lock, then use the existing proposal/refinement path. This is real signal
dispatch, not full behavioral parity with the role-play.

### `complete`

**Real existing capability:** `generate_team_review` obtains relevant threats and computes
coverage/SPOF into `TeamReviewResult`.

**Missing wiring:** completion does not route to review. A fully locked draft sent to
`propose_team_draft` simply produces no proposal update.

**Routing-pass boundary:** automatically dispatch a complete roster to the existing review.
Selected-four, condition resilience, and richer mechanics remain deferred.

## Post-lock verification

`apply_lock` and `commit_full_slot` both update `team_draft`, after which the graph routes to
`propose_team_draft`. The proposal function may perform a narrow local coverage check only
when no role/archetype signal exists; it does not persist team-wide diagnostics. There is no
cache invalidation or refresh edge tied to a successful lock.

Therefore, “recompute after every lock” remains structurally missing.

## Deferred backlog status

### Unchanged/open

- canonical name/form resolution and unresolved-input reporting;
- base/Mega ownership propagation;
- teammate query API and shared-teammate intersection;
- teammate percentages (ingestion retains names only);
- condition-resilience classification and fallback-mode detection;
- Liquid Voice conversion in static counters;
- Freeze-Dry's special Water interaction in static counters;
- Phantom Force's positive semi-invulnerable positioning value;
- labeled static fallback when the calc service is unavailable;
- selected-four/bring-four compatibility modeling;
- stale original single-Mega wording (a later amendment corrects it, but the stale text
  remains);
- Mimikyu in the integrated usage snapshot;
- deterministic `_union_move_candidates` ordering.

### Partial

- Electro Shot's Rain-shortened charge is modeled inside pairwise matchup timing, but
  Electro Shot does not produce a Rain support need;
- Track C rejects incomplete provisional builds structurally, but tier 3 still does not
  guarantee every build field;
- Tracks B/C add anchor-field and target-role provenance/confidence, but presented candidates
  still lack the richer usage/Compendium/mechanical/synthesized confidence model.

### Corrected older status

The six ADR-023 items from 2026-08-02 are not an untouched open list:

- Speed-axis bidirectionality and ability-flipped-threat framing were dissolved as separate
  design gaps;
- team-state scaling and representative verification-build selection were resolved;
- the two `rank_and_cut` passes remain deliberately accepted divergence risk;
- Mega count was reframed as deferred selected-four/quick-pick guidance, not roster
  illegality.

### Memoization distinction

Full-result, thread-scoped LRU memoization already shipped on 2026-07-31
(`MATCHUP_MEMO_MAX_ENTRIES=8192`). Its key includes the complete build fingerprint, including
nature and EVs.

Breakpoint memoization is different and remains deferred: infer and reuse calc-derived
KO/speed thresholds for a fixed matchup shape while EV, nature, or level varies. This routing
pass does not implement or claim that optimization.

## Proposed routing scope

Implement only:

1. derived four-way phase routing;
2. explicit empty legacy adapter;
3. real single-anchor Track C dispatch;
4. real multi-lock coverage/SPOF refresh;
5. automatic complete review;
6. stale-signal clearing and tests.

Do not implement any deferred item listed above.
