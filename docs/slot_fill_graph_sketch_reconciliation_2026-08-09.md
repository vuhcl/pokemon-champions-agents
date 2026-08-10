# Slot-fill graph sketch vs live graph — reconciliation (2026-08-09)

**Status:** Discovery / documentation only. No implementation, no design proposals.

**Source sketch:** `docs/slot_fill_flow_discovery_2026-08-08.md` § “Proposal: graph
integration sketch for review” (nodes, likely edges, modular function boundaries).

**Live evidence:** current `recommender/graph.py` and the node functions it registers in
`recommender/nodes.py`, plus the helper modules those nodes call. Claims below cite that
source (or a dated ADR / master-log entry when classifying *why* a divergence happened).
Nothing here is reconstructed from conversation memory alone.

---

## 1. Topology snapshot (current)

### Registered graph nodes (`recommender/graph.py:49-73`)

| Node name | Function |
|-----------|----------|
| `initialize` | `nodes.initialize` |
| `accept_available_pool` | `nodes.accept_available_pool` |
| `classify_input` | `nodes.classify_input` (optional `bootstrap_intake_parser`) |
| `apply_lock` | `nodes.apply_lock` |
| `record_constraint` | `nodes.record_constraint` |
| `record_rejection` | `nodes.record_rejection` |
| `handle_archetype_change` | `nodes.handle_archetype_change` |
| `reset_team` | `nodes.reset_team` |
| `restore_superseded` | `nodes.restore_superseded` |
| `route_team_phase` | `nodes.route_team_phase` |
| `bootstrap_direction` | `nodes.bootstrap_direction` |
| `record_bootstrap_response` | `nodes.record_bootstrap_response` |
| `discover_single_locked` | `nodes.discover_single_locked` |
| `refresh_team_signals` | `nodes.refresh_team_signals` |
| `discover_multi_locked` | `nodes.discover_multi_locked` |
| `generate_team_review` | `nodes.generate_team_review` |
| `finish_pending_response` | `nodes.finish_pending_response` |
| `refine_provisional_slot` | `nodes.refine_provisional_slot` |
| `commit_full_slot` | `nodes.commit_full_slot` |

`propose_team_draft` is **not** a registered graph node. It remains a Python helper
(`nodes.py:862-866`) called only from partial-slot / empty-merge fallbacks inside
`discover_single_locked` / `discover_multi_locked`.

### Phase destinations (`graph.py:25-30`, routed via `nodes.team_phase`)

| Phase | Destination |
|-------|-------------|
| `empty` | `bootstrap_direction` |
| `single_locked` | `discover_single_locked` |
| `multi_locked` | `discover_multi_locked` |
| `complete` | `generate_team_review` |

### Intent destinations relevant to the sketch (`graph.py:10-23`)

| Intent | Destination |
|--------|-------------|
| `continue` | `route_team_phase` |
| `bootstrap_response` | `record_bootstrap_response` |
| `slot_candidate_selected` | `refine_provisional_slot` |
| `full_slot_confirmed` | `commit_full_slot` |
| `team_review` | `generate_team_review` |
| `pending_response` | `finish_pending_response` |

Mutation handlers (`apply_lock`, constraints, rejections, archetype, reset, restore,
`commit_full_slot`, `record_bootstrap_response`) edge back to `route_team_phase`
(`graph.py:81-91`). Discovery / presentation terminals edge to `END`
(`graph.py:93-98`). **`refine_provisional_slot` goes to `END`, not to another confirm node.**

---

## 2. Proposed orchestration nodes — classification

### 2.1 `bootstrap_direction`

**Classification: Built as proposed** (intent match; richer than the stub the sketch
described).

- **Live:** graph node `bootstrap_direction` → `nodes.bootstrap_direction`
  (`graph.py:65`, `nodes.py:893-965`).
- **Original intent:** entered after pool acceptance when no anchor/theme exists; presents
  direction and pool options (`slot_fill_flow_discovery_2026-08-08.md:567-569`).
- **Match:** phase `empty` routes here (`graph.py:26`). First pass emits
  `kind="bootstrap_intake"` (`nodes.py:912-918`); after intake completion it runs
  `discover_bootstrap_directions` and `run_slot_fill_terminal` (`nodes.py:920-965`).
- **Note (not a divergence of the *node*):** intake parsing and
  `record_bootstrap_response` are additional seams the sketch did not name (see §5).

### 2.2 `route_team_phase`

**Classification: Built differently.**

- **Live:** graph node `route_team_phase` → empty passthrough `nodes.route_team_phase`
  (`nodes.py:307-309`); real work is `nodes.team_phase` used as the conditional map
  (`graph.py:43-44`, `92`; `nodes.py:294-304`).
- **Original intent:** choose bootstrap, early-core discovery, late-team discovery,
  provisional refinement, **or** final review (`slot_fill_flow_discovery…:570-571`).
- **What actually exists:** phase routing covers only
  `empty` / `single_locked` / `multi_locked` / `complete` (`graph.py:25-30`). Provisional
  refinement and full-build confirmation are **intent** routes from `classify_input`, not
  phase destinations (`graph.py:21-22`). Final review is both a phase destination
  (`complete` → `generate_team_review`) and an explicit `team_review` intent.
- **Traceable decision:** ADR-025 / team-phase routing implementation — four phases from
  confirmed-lock count, with `complete` auto-dispatching to `generate_team_review`
  (`docs/architecture_decisions.md:3977-3992`; `docs/master_project_log.md:2244-2277`).
  The sketch’s “roughly three locked” early→late boundary was explicitly rejected in favor
  of a 2-lock `multi_locked` floor and per-entry recompute
  (`architecture_decisions.md:3994-4013`).

### 2.3 `discover_slot_candidates`

**Classification: Built differently** — split into two phase-specific discovery nodes.

- **Original intent:** one orchestrator that constructs `SlotFillContext`, calls ADR-022
  tools, merges evidence, emits pending candidate presentation
  (`slot_fill_flow_discovery…:572-576`). Proposed edge:
  `route_team_phase(open_slot) -> discover_slot_candidates`
  (`slot_fill_flow_discovery…:636-637`).
- **What actually exists:**
  - `discover_single_locked` (`nodes.py:968-1032`) — Track C chain:
    `build_anchored_slot_fill_context` → `annotate_overlap` → `resolve_all_support_needs`
    → `merge_need_resolved` → `run_slot_fill_terminal` (or `fill_team_draft` fallback).
  - `discover_multi_locked` (`nodes.py:1108-1276`) — team-portfolio path:
    `_compute_team_review`, `query_shared_teammates`, `assess_condition_resilience`,
    `query_candidates_for_threats`, `merge_multi_locked_candidates`,
    `rank_multi_locked_candidates`, optional `completion_preference` gate, then
    `run_slot_fill_terminal`.
- **Traceable decisions:**
  1. **Team-phase routing (ADR-025):** early vs late become `single_locked` vs
     `multi_locked`, not one `open_slot` bucket (`architecture_decisions.md:3980-3992`;
     initially `multi_locked -> refresh_team_signals` per
     `docs/team_phase_routing_implementation_2026-08-08.md:64-68`).
  2. **Anchor / target-role split (ADR-024):** single-anchor discovery is not “pick a role
     for the open slot alone”; it needs `classify_anchor_role` feeding
     `RoleShapeContext`, separate from `TargetRoleDecision`
     (`architecture_decisions.md:3912-3973`;
     `docs/master_project_log.md:2138-2159`).
  3. **Multi-locked real dispatch (ADR-026):** `multi_locked` is deliberately *not* a
     parameterized reuse of the single-anchor chain
     (`architecture_decisions.md:4027-4036`). That is why the sketch’s single
     `discover_slot_candidates` name never landed.

### 2.4 `refine_provisional_slot`

**Classification: Built as proposed.**

- **Live:** `refine_provisional_slot` (`graph.py:72`, `nodes.py:435-473`).
- **Original intent:** consume candidate choice without committing; create and verify a
  full build (`slot_fill_flow_discovery…:577-579`).
- **Match:** intent `slot_candidate_selected` → this node (`graph.py:21`). Builds via
  `build_provisional_slot` without mutating `team_draft`; on success emits
  `pending_presentation` with `kind="full_build_confirmation"` (`nodes.py:454-472`).
- **Side effect vs sketch:** this node also performs the presentation step the sketch
  assigned to a separate `confirm_full_build` node (see §2.5).

### 2.5 `confirm_full_build`

**Classification: Never built** as a graph node — **superseded / folded**.

- **Original intent:** emit a pending full-build presentation; edge
  `refine_provisional_slot -> confirm_full_build -> END`
  (`slot_fill_flow_discovery…:580-581`, `639`).
- **What actually exists:** `refine_provisional_slot` itself writes the
  `full_build_confirmation` pending presentation and edges to `END`
  (`nodes.py:467-472`; `graph.py:98`). The next user turn’s `classify_pending` maps
  affirm → `full_slot_confirmed` (`nodes.py:192-194`).
- **Relevance today:** the *human gate* the sketch wanted is live; a dedicated graph node
  for “emit confirmation presentation” is unnecessary given the fold into refine.

### 2.6 `commit_full_slot`

**Classification: Built as proposed.**

- **Live:** `commit_full_slot` (`graph.py:73`, `nodes.py:480-582`).
- **Original intent:** atomically lock all confirmed attributes
  (`slot_fill_flow_discovery…:582-583`).
- **Match:** intent `full_slot_confirmed` → this node (`graph.py:22`). Prevalidates
  fingerprints, spread, moves, legality, constraints; replaces one slot once or changes
  nothing (`nodes.py:480-582`). Then edges to `route_team_phase` (`graph.py:88-91`), not
  to a post-lock review node.

### 2.7 `post_lock_review`

**Classification: Never built** as a graph node — **superseded in part, still absent as a
dedicated step**.

- **Original intent:** update team phase and condition/selected-four diagnostics; edge
  `commit_full_slot -> post_lock_review` then back to `route_team_phase` or `END`
  (`slot_fill_flow_discovery…:584-585`, `641-642`).
- **What actually exists instead:**
  - Phase update is implicit: `commit_full_slot` clears coverage/SPOF/shared/review
    (`nodes.py:577-581`) and returns to `route_team_phase`, which re-derives phase from
    `all_locked` counts (`nodes.py:294-304`).
  - Condition resilience is computed **inside** `discover_multi_locked` (and also inside
    the orphaned `refresh_team_signals`) via `assess_condition_resilience`
    (`nodes.py:1146-1152`, `1084-1104`) — not as a post-commit node.
  - Selected-four / bring-four diagnostics: **no** `assess_selected_four_modes` (or
    equivalent) exists under `recommender/` (repository search returns no matches).
- **Relevance today:** phase refresh + multi-locked signal recompute cover much of the
  sketch’s “update team phase / recompute gaps” intent without a named node. Selected-four
  mode assessment from the sketch remains unimplemented (finding only; no design here).

---

## 3. Proposed likely edges — classification

| Proposed edge (`slot_fill_flow_discovery…:631-642`) | Classification | Live evidence |
|----------------------------------------------------|----------------|---------------|
| `accept_available_pool -> route_team_phase` | **Built as proposed** | `graph.py:77` |
| mutating handlers → `route_team_phase` | **Built as proposed** (extended to include `commit_full_slot` and `record_bootstrap_response`) | `graph.py:81-91` |
| `route_team_phase(empty) -> bootstrap_direction` | **Built as proposed** | `graph.py:26`, `92` |
| `route_team_phase(open_slot) -> discover_slot_candidates` | **Built differently** | split: `single_locked` / `multi_locked` (`graph.py:27-28`) |
| `discover_slot_candidates -> END` after presentation | **Built as proposed** (on both discovery nodes) | `graph.py:94-95` |
| `classify_input(candidate_accept) -> refine_provisional_slot` | **Built as proposed** | intent `slot_candidate_selected` (`graph.py:21`; `nodes.py:231-234`) |
| `refine_provisional_slot -> confirm_full_build -> END` | **Built differently** | refine → `END` with confirmation presentation already attached (`graph.py:98`; `nodes.py:467-472`) |
| `classify_input(build_accept) -> commit_full_slot` | **Built as proposed** | intent `full_slot_confirmed` (`graph.py:22`; `nodes.py:192-194`) |
| `commit_full_slot -> post_lock_review` | **Never built** | commit → `route_team_phase` (`graph.py:88-91`) |
| `post_lock_review -> route_team_phase` or `END` | **Never built** | N/A |

**Pending-kind distinction (sketch closing note):** the sketch required candidate selection
vs full-build confirmation to be distinguishable for `classify_pending`
(`slot_fill_flow_discovery…:644`). **Built as proposed:** `candidate_selection`
(`slot_fill.py:1264`), `full_build_confirmation` (`nodes.py:467-472`), plus later
`bootstrap_intake` and `completion_preference` kinds the sketch did not name
(`nodes.py:881`, `1237`).

---

## 4. Proposed modular function boundaries — classification

These were conceptual contracts in the sketch (`slot_fill_flow_discovery…:587-621`), not
required graph node names.

| Proposed contract | Classification | Live counterpart (if any) |
|-------------------|----------------|---------------------------|
| `collect_candidate_evidence` | **Never built** under that name; **built differently** as phase-local collectors | `build_anchored_slot_fill_context` (`slot_fill.py`); `collect_locked_anchor_contexts` / threat objective builders (`team_candidates.py:76+`, `144+`); `discover_bootstrap_directions` (`bootstrap.py:313+`) |
| `merge_candidate_evidence` | **Never built** under that name; **built differently** | `annotate_overlap` / `merge_need_resolved` (single); `merge_multi_locked_candidates` (`team_candidates.py:211+`) |
| `rank_and_cut_slot_candidates` | **Never built** under that name; **built differently** | existing `rank_and_cut` (`ranking.py:14`); `rank_multi_locked_candidates` (`team_candidates.py:681+`); single-locked uses terminal / internal sort after ADR-022 merge |
| `verify_candidate_pool` | **Never built** | no `verify_candidate_pool` / equivalent deep-verify orchestrator; verification is scattered (legality in commit, calc in threat/coverage paths, composition annotate in multi-locked) |
| `assess_condition_resilience` | **Built as proposed** (callable; wired into multi-locked) | `recommender/condition_resilience.py:93+`; called from `discover_multi_locked` / `refresh_team_signals` (`nodes.py:1147`, `1102`) |
| `assess_selected_four_modes` | **Never built** | no matches under `recommender/` |
| `build_provisional_slot` | **Built as proposed** | `slot_fill.py:1343+`; called from `refine_provisional_slot` (`nodes.py:454-456`) |

Central pipelines the sketch described:

- Candidate discovery ≈ `collect → merge → rank/cut → verify → present`
  (`slot_fill_flow_discovery…:623-625`): **partially realized**, differently per phase; the
  unified `verify_candidate_pool` stage before presentation is the clearest missing piece.
- Provisional build ≈ `build → verify → present → await confirmation`
  (`slot_fill_flow_discovery…:627-629`): **largely realized** via
  `refine_provisional_slot` + pending confirmation + `commit_full_slot`, with build-time
  completeness enforced by `build_provisional_slot` returning
  `UnresolvedSlotRefinement` when fields are missing.

---

## 5. Exists now, not in the original graph sketch

Items that are live orchestration or graph-adjacent seams the sketch’s seven-node list did
not anticipate (non-exhaustive of every ADR since, but of graph-visible / routing-visible
additions):

| Addition | Where | Why it wasn’t in the sketch |
|----------|-------|-----------------------------|
| Split discovery nodes `discover_single_locked` / `discover_multi_locked` | `graph.py:67-69` | Sketch assumed one `discover_slot_candidates`; ADR-025/026 made phases structurally different |
| `generate_team_review` as automatic `complete` destination | `graph.py:29`, `70` | Sketch mentioned “final review” as a phase choice inside `route_team_phase`, not a named node; ADR-025 made auto-review a real destination |
| `record_bootstrap_response` + injected `bootstrap_intake_parser` on `classify_input` | `graph.py:51-56`, `66`; `nodes.py:312-319`, `384-432` | ADR-027 empty-team bootstrap LLM intake seam |
| `finish_pending_response` | `graph.py:20`, `71` | Soft-exit for defer / unparseable pending replies |
| `completion_preference` pending kind + re-entry via `continue` | `nodes.py:1223-1241`, `145-175`; intent `continue` → `route_team_phase` | Late-slot attacker/support/balance ask from the discovery scenarios; implemented inside multi-locked, not as its own sketch node |
| Structured `candidate_discovery_error` / calc-unavailable degraded discovery | `discover_single_locked` degraded branch (`nodes.py:1016-1028`); multi-locked fail-closed (`nodes.py:1155-1160`, `1200-1205`) | ADR-029; sketch only listed the missing edge `calc unavailable -> labeled static fallback` as a tool-composition gap |
| `condition_resilience` state published on multi-locked entry | `nodes.py:1147-1152` | ADR-028; sketch named the *function* but not a graph-visible state field |
| `refresh_team_signals` node registration | `graph.py:68` | Introduced by ADR-025 as the original `multi_locked` destination; later bypassed when multi-locked discovery absorbed signal refresh (see §6) |
| Ownership expansion helper used by discovery | `owned_species_ids` (`team_candidates.py:122+`), wired into single- and multi-locked | Ownership/form propagation work after the sketch |
| Demotion of `propose_team_draft` off the live graph | callable only as fallback helper | Sketch’s *then-current* graph still centered on `propose_team_draft`; team-phase work replaced that as the primary open-slot path |

---

## 6. Dead / unreachable graph surface

### 6.1 `refresh_team_signals` — orphaned node (confirmed)

- **Registered:** `g.add_node("refresh_team_signals", …)` (`graph.py:68`).
- **Not in** `_PHASE_ROUTES`, `_INTENT_ROUTES`, or any `add_edge` /
  `add_conditional_edges` destination list in `graph.py`.
- **Still callable in unit tests** (`tests/recommender/test_team_phase_routing.py` imports
  and invokes it directly).
- **Historical role:** ADR-025 originally routed `multi_locked -> refresh_team_signals`
  (`docs/team_phase_routing_implementation_2026-08-08.md:64-68`). ADR-026 replaced that
  with direct `discover_multi_locked`, which recomputes the same review/shared/resilience
  signals inline (`nodes.py:1142-1154`).
- **Prior confirmation this session:** calc-unavailable discovery pass
  (`docs/calc_unavailable_static_fallback_discovery_and_design_2026-08-09.md:42-46`;
  `docs/master_project_log.md:3110-3112`).

**Finding:** the original sketch implied a live post-lock / team-signal refresh step; the
closest registered artifact (`refresh_team_signals`) is **not** reached by any current
route. Live multi-locked behavior does the refresh work inside `discover_multi_locked`
instead.

### 6.2 No other registered node is similarly orphaned

Every other `add_node` name appears as a START/intent/phase destination or as a mutation
handler that edges to `route_team_phase` / `END`. `propose_team_draft` is not orphaned — it
was removed from graph registration entirely and remains a helper.

### 6.3 Sketch-implied edges that never became live routes

- `commit_full_slot -> post_lock_review` — no `post_lock_review` node; commit returns to
  phase routing (`graph.py:88-91`).
- `refine_provisional_slot -> confirm_full_build` — no `confirm_full_build` node.
- Single `discover_slot_candidates` destination — never registered.

---

## 7. Plain findings (no scoping)

1. Of the sketch’s seven orchestration nodes, **four** exist under the same names with
   matching core intent (`bootstrap_direction`, `route_team_phase`,
   `refine_provisional_slot`, `commit_full_slot`); **one** was split
   (`discover_slot_candidates` → single/multi); **two** were never registered
   (`confirm_full_build`, `post_lock_review`) and are partially folded into refine /
   multi-locked recompute.
2. The largest structural divergence from the sketch is **not** missing wiring — it is the
   deliberate ADR-024/025/026 decision that early-core and late-team discovery are different
   operations, plus ADR-025’s rejection of a fixed “~3 locks” threshold.
3. The human double-gate the sketch centered on (candidate choice → full-build confirmation
   → atomic lock) **is** live on the graph via intents and pending kinds.
4. `refresh_team_signals` is the main **dead registered** surface corresponding to something
   the sketch expected to be live; selected-four assessment remains the main **never-built**
   sketch contract with no live substitute.
5. Several capabilities the sketch listed only as gaps or modular helpers
   (condition resilience, calc-unavailable degradation, bootstrap LLM intake, completion
   preference) later shipped as graph-adjacent behavior the seven-node sketch did not draw.

---

## Sources consulted

- `docs/slot_fill_flow_discovery_2026-08-08.md` (proposal sketch §§ nodes / edges /
  modular boundaries)
- `recommender/graph.py` (full file)
- `recommender/nodes.py` (phase/intent handlers and discovery/commit/bootstrap bodies cited
  above)
- `recommender/slot_fill.py`, `recommender/team_candidates.py`,
  `recommender/condition_resilience.py`, `recommender/bootstrap.py`,
  `recommender/ranking.py` (modular-boundary counterparts)
- `docs/architecture_decisions.md` ADR-024, ADR-025, ADR-026, ADR-027, ADR-028, ADR-029
- `docs/team_phase_routing_implementation_2026-08-08.md`
- `docs/calc_unavailable_static_fallback_discovery_and_design_2026-08-09.md`
- `docs/master_project_log.md` (dated entries for team-phase, multi-locked, calc-unavailable
  orphan confirmation)
