# Team-Phase Routing Implementation Report

**Date:** 2026-08-08  
**Audience:** Vu / post-implementation review  
**Status:** Implemented and verified locally. Proposed ADR/project-log wording is intentionally
not included; draft those only after this report is reviewed.

## Scope delivered

Implemented the bounded routing pass from
`docs/team_phase_routing_discovery_2026-08-08.md`:

1. derived `empty` / `single_locked` / `multi_locked` / `complete` phases;
2. explicit graph decision point after pool acceptance and mutating handlers;
3. real Track C anchored discovery dispatch for a clean single-anchor/open-slot state;
4. real team-wide coverage/SPOF refresh for `multi_locked`;
5. automatic existing team review for `complete`;
6. stale signal clearing, tests, and documentation.

No deferred backlog capability was implemented.

## Files changed by this pass

- `recommender/state.py`
  - adds optional typed `coverage` and `spofs` working-signal fields.
- `recommender/nodes.py`
  - adds phase derivation and thin phase handlers;
  - composes existing single-anchor discovery helpers;
  - shares one thread-bound team-review computation between multi refresh and final review;
  - clears stale signals on empty/single/reset and after atomic commit before rerouting.
- `recommender/graph.py`
  - adds the explicit `route_team_phase` node and four conditional destinations;
  - routes pool acceptance, continue, ordinary mutations, reset/restore, and atomic commit
    through that decision point.
- `tests/recommender/test_team_phase_routing.py`
  - adds focused phase, helper-order, fallback, signal, cache-binding, and graph-transition
    coverage.
- `docs/team_phase_routing_discovery_2026-08-08.md`
  - records the pre-implementation direct-source check and corrected deferred status.
- `docs/team_phase_routing_implementation_2026-08-08.md`
  - this report.

This pass did not edit `docs/architecture_decisions.md`,
`docs/master_project_log.md`, or the attached plan file.

## Implemented behavior

### Phase derivation

`team_phase` counts only `all_locked` slots:

- zero confirmed -> `empty`;
- one confirmed -> `single_locked`;
- two or more with an open slot -> `multi_locked`;
- every slot confirmed -> `complete`.

A species-only or otherwise partial slot does not count as a confirmed member. A
five-confirmed-plus-one-partial roster remains `multi_locked`.

Source: `recommender/nodes.py:206-221`.

### Graph routing

`route_team_phase` now follows:

- `empty -> bootstrap_direction`;
- `single_locked -> discover_single_locked`;
- `multi_locked -> refresh_team_signals`;
- `complete -> generate_team_review`.

Pool acceptance and all ordinary mutation/commit handlers enter the router. Candidate
selection still ends in provisional refinement, and provisional refinement still ends after
presenting the full build; Track C's cross-turn lifecycle is unchanged.

Source: `recommender/graph.py:8-88`.

### Empty

`bootstrap_direction` explicitly clears stale coverage/SPOF/final-review state, then the graph
uses the legacy proposal path.

This is intentionally a routing stub. It does not implement the combined direction/pool
interaction and does not close the generic `_pick_role` fallback gap.

Source: `recommender/nodes.py:687-689`.

### Single locked

For exactly one fully confirmed anchor and a completely open next slot, the node executes:

`build_anchored_slot_fill_context`
`-> annotate_overlap`
`-> resolve_all_support_needs`
`-> merge_need_resolved`
`-> run_slot_fill_terminal`

The resulting candidate presentation is persisted for the existing Track C response path.

If the open slot already contains partial steering, the anchor constructor bypasses, or no
candidate survives merging, the node clears stale team signals and uses the labeled legacy
proposal fallback. It does not manufacture a target role.

Source: `recommender/nodes.py:692-731`.

Still intentionally absent:

- owned-first argument propagation;
- target-role Compendium dispatch;
- complete target-role resolution for threat-only candidates;
- dedicated no-candidate UX.

### Multi locked

`refresh_team_signals` uses the same `_compute_team_review` path as complete review:

1. bind the full-result matchup LRU to `RunnableConfig.thread_id`;
2. load relevant threats;
3. compute team coverage;
4. detect SPOFs;
5. persist `coverage` and `spofs`;
6. clear stale `last_team_review`;
7. continue to legacy proposal/refinement.

Source: `recommender/nodes.py:734-761`.

This is real recomputation after a lock, not a full multi-member candidate ranker. Shared
teammates, condition resilience, role duplication, attacker/support preference, and
selected-four evidence remain unavailable.

### Complete

A fully confirmed roster routes automatically to `generate_team_review`. The review and the
working `coverage`/`spofs` fields are all populated from the same computation.

The explicit `team_review` intent remains supported.

Source: `recommender/nodes.py:764-770`;
`recommender/graph.py:16,22-27,81-86`.

## Signal freshness

- Empty and single handlers clear coverage, SPOFs, and final review before producing their
  next output.
- Multi recomputes coverage/SPOFs and clears final review.
- Complete recomputes all three.
- Reset clears all three.
- Atomic commit clears stale values before the phase router publishes the new phase's values.

No phase exposes a previous phase's review as current.

## Memoization distinction

The implementation reuses the existing full-result, thread-scoped LRU and binds it in the
shared review computation. This cache remains keyed by the complete matchup fingerprint;
existing tests confirm an EV change is a cache miss.

Breakpoint memoization was not implemented. Learning reusable KO/speed thresholds across
different EV, nature, or level variants remains a separate deferred task.

## Verification

Focused routing/slot-flow command:

`uv run pytest tests/recommender/test_team_phase_routing.py tests/recommender/test_slot_fill.py tests/recommender/test_coverage.py tests/recommender/test_steering.py`

Result: **60 passed**.

Routing/cache-focused command:

`uv run pytest tests/recommender/test_team_phase_routing.py tests/recommender/test_threats.py`

Result: **24 passed**.

Full suite:

`uv run pytest`

Result: **440 passed, 5 skipped**.

Patch hygiene:

`git diff --check`

Result: **passed**.

## Test coverage added

`tests/recommender/test_team_phase_routing.py` verifies:

- 0/1/2/5/6-confirmed phase boundaries;
- partial slots do not count as confirmed;
- deterministic sole-anchor / first-open-slot selection;
- required Track C helper order;
- partial-open and empty-candidate legacy fallbacks;
- empty-phase stale-signal clearing;
- shared multi/complete signal publication;
- thread binding for the full-result LRU;
- second-lock routing to multi refresh;
- sixth atomic commit routing to complete review.

## Accepted residual risks

1. Coverage/SPOF still fails hard when the calc service is unavailable. The separately
   deferred labeled static fallback remains necessary.
2. Single-anchor discovery can still produce unresolved target roles. The implementation
   preserves that result instead of guessing.
3. Empty bootstrap remains behaviorally legacy until its interaction contract is designed.
4. Multi-lock routing publishes only currently callable coverage/SPOF signals; it does not
   imply parity with the full role-play evidence set.

## Review gate

Review this report and the diff before drafting any ADR or master-project-log entry. Any
proposed entries should be derived from the verified behavior above and pasted only through
the established review path.
