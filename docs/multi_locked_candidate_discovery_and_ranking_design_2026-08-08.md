# Multi-Locked Candidate Discovery and Ranking: Verification and Design Proposal

**Date:** 2026-08-08  
**Audience:** Vu / design review  
**Status:** Discovery and design proposal only. No implementation plan or runtime change is
included. Every substantive conclusion is labeled **Verified finding**, **Proposal**, or
**Explicit scope decision**.

## Purpose and method

This report investigates the deferred capability named by ADR-025: real candidate discovery
and ranking after two or more members are fully locked. It distinguishes that capability from
the already-shipped `multi_locked` signal refresh.

The source check covered:

1. phase derivation and graph routing;
2. the legacy proposal/refinement path reached by `multi_locked`;
3. Track C's live single-anchor discovery and terminal lifecycle;
4. ADR-022 query call sites;
5. compendium-first need resolution and `CandidateEvidence`;
6. ownership-aware query/ranking interfaces;
7. team coverage, SPOF, and shared-teammate signals;
8. `TargetRoleDecision` production and persistence;
9. focused tests for routing, slot fill, ownership, and teammate intersection.

Primary sources are:

- `recommender/graph.py`;
- `recommender/nodes.py`;
- `recommender/propose.py`;
- `recommender/slot_fill.py`;
- `recommender/coverage.py`;
- `recommender/counters.py`;
- `recommender/threat_counters.py`;
- `recommender/teammates.py`;
- `recommender/state.py`;
- `recommender/ranking.py`;
- `docs/architecture_decisions.md`;
- `docs/team_phase_routing_implementation_2026-08-08.md`;
- `docs/teammate_query_implementation_2026-08-08.md`;
- `docs/slot_fill_flow_discovery_2026-08-08.md`.

## Executive conclusions

1. **Verified finding:** `multi_locked` currently executes
   `refresh_team_signals -> propose_team_draft`. It does not enter Track C and does not produce
   a species candidate presentation.
2. **Verified finding:** the legacy path calls none of `query_counters`,
   `query_threat_counters`, `query_support_needs`, or `query_by_usage`.
3. **Verified finding:** compendium-first need resolution and candidate provenance are bypassed
   completely. Reuse of usage/build utilities during legacy refinement is not partial reuse of
   those candidate-discovery contracts.
4. **Verified finding:** ownership modes are not applied. The lower counter/ranking layers have
   support, but no mode is supplied by the production path.
5. **Verified finding:** current team-wide threat work computes coverage and leave-one-slot-out
   SPOFs against one global meta threat list. It does not aggregate candidate answers or rank a
   next member.
6. **Verified finding:** `shared_teammates` is now computed and published for `multi_locked`,
   superseding older statements that the signal was unavailable, but no candidate-generation or
   ranking code consumes it.
7. **Verified finding:** the legacy path partially touches `TargetRoleDecision`: `_pick_role`
   can produce one, but `fill_team_draft` flattens a resolved decision to a role `Attr`, ignores
   unresolved decisions, and discards the typed decision's constraints, confidence, ambiguity,
   and provenance.
8. **Proposal:** replace the legacy handoff with one all-members evidence collection. Support
   needs remain per-anchor; threat objectives become team-wide coverage gaps; shared teammates
   become a bounded candidate source; all evidence merges before the first global cut.
9. **Resolved proposal:** rank candidates by a documented severity-aware vector rather than
   opaque weighted sums. Decisive/costly verified uncovered closures precede composition;
   composition precedes toss-up, conditional, and SPOF gains; cross-anchor breadth, evidence
   quality, shared cohesion, then stable identity follow. Usage remains discovery/build-selection
   evidence and is not a ranking stage.
10. **Explicit scope decision:** role duplication, physical/special balance, and a material
    attacker/support/balance preference belong in this capability. Condition resilience,
    selected-four modeling, canonical name/form resolution, and calc-unavailable fallback do not.

## Part 1 — verified current state

### 1. The exact `multi_locked` handoff

**Verified finding — `recommender/nodes.py:207-217`:** `team_phase` counts only slots satisfying
`all_locked`. Two or more confirmed slots with an incomplete roster produce `multi_locked`.
`all_locked` requires role, species, ability, item, moveset, spread, and nature
(`recommender/state.py:388-392`).

**Verified finding — `recommender/graph.py:22-27,81-85`:** the graph route is:

`route_team_phase -> refresh_team_signals -> propose_team_draft -> END`

It does not route to `discover_single_locked`.

**Verified finding — `recommender/nodes.py:745-780`:** `refresh_team_signals`:

1. binds the matchup memo to the graph thread;
2. loads globally relevant threats;
3. computes team coverage;
4. computes SPOFs;
5. queries shared teammates for all fully locked species;
6. publishes `coverage`, `spofs`, and `shared_teammates`;
7. clears `last_team_review`.

**Verified finding — `recommender/nodes.py:682-685`:** `propose_team_draft` is only a wrapper
around `fill_team_draft`.

**Verified finding — `recommender/propose.py:42-103`:** `fill_team_draft` iterates incomplete
slots, may choose a role, and then calls `_propagate_and_refine`. It does not construct a
`SlotFillContext`, collect candidates, or persist a candidate presentation.

**Verified finding — `recommender/propose.py:201-206`:** when a slot has a role but no species,
the path stops. The source explicitly records role-to-species resolution as requiring the Role
Compendium. Existing-species slots can receive build defaults, but empty species slots do not
receive a candidate.

**Conclusion:** the current handoff is not a weaker multi-anchor version of Track C. It is a
structurally different attribute propagation/refinement path with no species discovery.

### 2. ADR-022 query invocation

**Verified finding:** the normal `multi_locked` route calls none of the four query surfaces:

- `query_counters`: not called;
- `query_threat_counters`: not called;
- `query_support_needs`: not called;
- `query_by_usage`: not called.

**Verified finding — `recommender/slot_fill.py:124-180`:** Track C's
`build_anchored_slot_fill_context` calls `query_support_needs` and
`query_threat_counters` for one resolved anchor.

**Verified finding — `recommender/threat_counters.py:119-241`:**
`query_threat_counters` calls `query_counters(anchor)` to identify threats, then calls
`query_counters(threat)` for candidate answers, cuts the merged static pool, verifies a bounded
threat set, and performs final ranking.

**Verified finding — `recommender/slot_fill.py:648-663`:** support resolution can use
`query_by_usage` to order a bounded mechanical species set. This is not reached by the legacy
multi path.

### 3. Compendium-first resolution and candidate provenance

**Verified finding:** both are bypassed entirely by `multi_locked`.

**Verified finding — `recommender/slot_fill.py:698-733,818-858`:** Track C maps supported need
categories to compendium roles, inserts compendium rows before raw mechanical additions, retains
useful usage evidence for overlapping rows, and respects role-specific rejection evidence.

**Verified finding — `recommender/slot_fill.py:895-919`:** current Track C presentation ranking
places exact/high-confidence compendium evidence first, then other compendium evidence, before
non-compendium rows. Compendium evidence must correspond to an active matching need.

**Verified finding — `recommender/state.py:136-164`:** `CandidateEvidence` stores:

- evidence basis;
- confidence;
- producer name;
- source-specific details.

**Verified finding — `recommender/slot_fill.py:382-447,484-554`:** threat and need producers
create evidence, and merge preserves the union when a species appears in multiple branches.
`recommender/slot_fill.py:922-971` persists that evidence into pending presentation options.

**Conclusion:** legacy use of `featured_or_common_set`, move narrowing, or cached builds during
refinement does not constitute partial reuse. Those utilities populate a build only after a
species already exists; they do not create or preserve candidate evidence.

### 4. Ownership modes

**Verified finding — `recommender/ranking.py:9-41,79-125`:** `rank_and_cut` supports:

- `owned_first`;
- `owned_last`;
- `off`;
- `owned_only`, with caller-side filtering required.

**Verified finding — `recommender/counters.py:315-350,438-447`:** `query_counters` supports
candidate-pool restriction and ownership ranking.

**Verified finding — `recommender/threat_counters.py:119-188,233-241`:**
`query_threat_counters` applies ownership only to the candidate side; anchor threat
identification remains against the unrestricted meta. This is the correct boundary.

**Verified finding:** neither current production path uses that support:

- `multi_locked` calls no candidate query;
- Track C calls `query_threat_counters(pokemon)` without ownership arguments
  (`recommender/slot_fill.py:164-168`);
- `SlotFillContext` has no ownership mode;
- `query_by_usage` has no ownership parameter (`recommender/by_usage.py:25-86`);
- support-need resolution has no ownership input;
- `RecommenderState.available_pool` is `list[PokemonSet]`, while the counter APIs expect a list
  of species names (`recommender/state.py:357-365`);
- `RecommenderState` has no field carrying the chosen ownership mode.

**Conclusion:** ownership is not partially applied in the legacy route. Lower-layer capability
exists but orchestration, input normalization, and non-counter branch propagation are absent.

### 5. What “team-wide threat aggregation” does today

**Verified finding — `recommender/coverage.py:288-322`:** `get_relevant_threats` builds one
global, usage-ranked meta threat list, expanding relevant forms. It is not a union of threats
returned by querying each locked member.

**Verified finding — `recommender/coverage.py:325-415`:** `compute_team_coverage` evaluates every
usable team slot against every threat. For each threat it records:

- the best team outcome;
- all covering slot indices;
- whether coverage requires a team-forced field;
- whether the answer is conditionally dependent;
- an empty covering list when the roster has no answer.

**Verified finding — `recommender/coverage.py:418-451`:** `detect_spof` recomputes coverage with
each slot omitted. A slot is a SPOF only when baseline coverage depends exclusively on it and
removing it changes the threat to `no_answer`.

**Verified finding:** no current function:

- unions `query_counters` or `query_threat_counters` results across locked members;
- turns uncovered `ThreatCoverageResult` rows into species candidates;
- computes a candidate's marginal improvement to team coverage;
- ranks candidates by threats addressed across the roster.

**Verified finding:** coverage and SPOF have a limited downstream use in move narrowing
(`recommender/move_narrowing.py:164-214,532-571`). That can influence a moveset fallback for a
species already selected; it is not multi-member species discovery.

**Conclusion:** team-wide diagnostics are real. Candidate-oriented threat aggregation remains
aspirational.

### 6. `TargetRoleDecision` in the legacy path

**Verified finding — `recommender/propose.py:106-149`:** `_pick_role` returns either:

- a resolved `TargetRoleDecision`;
- an `UnresolvedTargetRoleDecision`;
- no decision.

**Verified finding — `recommender/propose.py:81-96`:** `fill_team_draft` handles only a resolved
`TargetRoleDecision`, extracts its `role_id` and one provenance string, and stores an unlocked
role `Attr`. An unresolved result does not advance the slot.

The full decision object is not retained. Its evidence, needed/wanted constraints, confidence,
ambiguity, producer, and provenance do not travel into refinement.

**Verified finding — `recommender/state.py:167-254`; `recommender/slot_fill.py:223-302,948-1122`;
`recommender/nodes.py:243-254,308-402`:** Track C does preserve candidate-specific decisions
through:

1. `SlotFillContext`;
2. `AnnotatedCandidate`;
3. pending presentation option;
4. `PendingSlotIntent`;
5. provisional refinement;
6. atomic full-slot validation and commit.

Threat-only alternatives do not inherit a support-derived target role, and ambiguous speed
control remains structured rather than silently defaulting.

**Conclusion:** the legacy path partially reuses the producer but bypasses Track C's threading
contract.

### 7. Shared teammates and documentation freshness

**Verified finding — `recommender/teammates.py:395-484`:** `query_shared_teammates`:

- queries every locked species;
- returns unavailable if any anchor's evidence is unavailable;
- otherwise computes a strict all-N intersection of retained teammate rows;
- excludes every locked member's legality lineage;
- preserves per-anchor ranks/percentages;
- sorts percentage-complete rows by highest bottleneck percentage, then minimax worst rank;
- distinguishes an available empty intersection from unavailable evidence.

**Verified finding — `recommender/nodes.py:765-780`:** `refresh_team_signals` publishes this
result for `multi_locked`.

**Verified finding:** repository source has no runtime reader of
`state["shared_teammates"]`. The field is declared, published, cleared, and tested, but not
consumed by proposal or ranking.

**Verified finding — documentation chronology:** ADR-025
(`docs/architecture_decisions.md:3903-3949`) and the team-phase implementation report
(`docs/team_phase_routing_implementation_2026-08-08.md:112-128`) correctly described the
original routing pass, when shared teammates were unavailable. The later teammate report
(`docs/teammate_query_implementation_2026-08-08.md:20-36`) and current source supersede that
specific availability statement. Candidate-ranking consumption is still absent.

**Verified finding — `recommender/graph.py:18-19,87-88`:** candidate selection routes to
provisional refinement and ends. Signal freshness is triggered by lock/commit mutations, not by
merely selecting a provisional candidate.

## Part 2 — design proposal

### Design objective

**Proposal:** `multi_locked` should produce one candidate pool from the current roster, not one
pool per favored anchor. The pool must preserve why each candidate entered, which locked members
its evidence relates to, what team gap it improves, and what target role—if any—it can
defensibly carry.

The conceptual chain is:

`refresh team signals`
`-> collect every locked member's support evidence`
`-> derive one explicit team threat objective`
`-> resolve needs compendium-first`
`-> add shared-teammate candidates`
`-> merge all evidence`
`-> annotate target role and composition fit`
`-> rank once`
`-> run the existing Track C terminal`

This is a generalization beneath the phase node. It is not a second presentation, refinement, or
commit system.

### 1. Aggregation without anchor privilege

#### Per-anchor support collection

**Proposal:** for every fully locked slot:

1. call `resolve_anchor_build`;
2. call `classify_anchor_role`;
3. call `derive_role_shape_context`;
4. call `query_support_needs`;
5. retain the slot index and anchor identity on every surfaced need.

All locked members run through the same sequence. No “primary,” “original,” first-listed, or
first-successful anchor exists.

**Reasoning:** support needs are inherently relative to one member's resolved build and role
shape. Flattening builds first would lose the relation between a need and the member that
created it. Conversely, choosing one member recreates the same stale-anchor failure class that
ADR-025 fixed for signals.

#### Team-wide threat objective

**Proposal:** do not call `query_threat_counters` independently for each anchor and concatenate
its top-N output. Each invocation performs local cuts before the team can observe cross-anchor
value, so equal invocation count would still preserve local anchor privilege.

Instead:

1. take every coverage row with no covering slot;
2. add threats appearing in current SPOF findings;
3. deduplicate that explicit team threat set;
4. reuse ADR-022's `query_counters(threat)` candidate search, representative-build verification,
   and `rank_and_cut` semantics against the full set;
5. perform the tractable cut only after each candidate has been evaluated against the same team
   threat objective.

This generalizes the internal semantics of `query_threat_counters` while replacing only its
single-anchor threat-discovery input.

**Reasoning:** coverage answers “what the roster cannot currently answer”; SPOF answers “what
the roster answers through only one member.” Those are the relevant multi-member objectives.
An independent anchor's weakness that another locked teammate already covers should not receive
the same priority as an uncovered team threat.

#### Merge and normalization

**Proposal:** merge after all source branches complete. The candidate key remains the existing
normalized tool-emitted species/form identity; this task does not add a user-input name resolver.

Each evidence item must retain:

- producer;
- source branch;
- originating locked-slot index or `team` origin;
- originating need or threat;
- confidence and source-specific details.

For multi-anchor ranking, compare:

1. distinct locked members supported;
2. then distinct need/threat identities;
3. never raw evidence-row count.

**Reasoning:** a verbose anchor can emit several correlated needs. Counting rows would let that
anchor dominate even though every member was queried once. Distinct-anchor breadth makes the
unit of aggregation explicit.

**Proposal:** stable normalized candidate ID is the final tie-break. Reordering locked slots
must not change the candidate set or order, apart from source slot indices displayed in
provenance.

### 2. Evidence and branch representation

**Proposal:** retain `CandidateEvidence` as the one provenance object carried through merge,
presentation, pending intent, and refinement. Extend its envelope additively for anchor/team
origin and teammate-backed evidence; do not create a second multi-member evidence type.

The current three-value presentation source (`threat`, `need`, `both`) cannot accurately express
teammate-only or three-way evidence. The multi-member design should represent branch provenance
as a set derived from `CandidateEvidence`, while preserving the current labels as compatibility
rendering where possible.

**Reasoning:** enumerating every combination—such as
`threat_need_teammate`—would make provenance brittle. Candidate evidence already provides the
correct additive model.

### 3. Compendium-first need resolution

**Proposal:** resolve every per-anchor support need through the existing
`resolve_need_candidates` behavior:

1. mapped Compendium evidence first;
2. raw mechanical/usage-backed additions second;
3. role-specific rejections respected;
4. evidence merged when both paths support the same candidate.

`resolve_all_support_needs` should be generalized to accept needs carrying anchor origin, but
its resolver and evidence semantics remain the same.

**Reasoning:** the multi-anchor problem changes how results are collected and ranked, not how a
Trick Room, weather, redirection, or mechanical need is resolved. Reimplementing resolution
would create two definitions of compendium priority.

### 4. `TargetRoleDecision` preservation

**Proposal:** target role remains candidate-specific.

For each merged candidate:

1. consider only support needs the candidate actually satisfies;
2. if those needs imply one compatible role, create one `TargetRoleDecision` containing all
   relevant anchor/need provenance;
3. if they imply incompatible roles, retain an `UnresolvedTargetRoleDecision`;
4. if the candidate is threat-only or shared-teammate-only, leave target role unresolved;
5. do not infer target role from attacker/support/balance preference.

The resulting object continues through the existing pending presentation, `PendingSlotIntent`,
provisional build, and atomic commit lifecycle.

**Reasoning:** a global target role would let one anchor's need leak onto candidates that do not
satisfy it. This is the same failure Track C already prevents for threat-only alternatives.

**Accepted limitation:** current role mapping is incomplete beyond the shipped support-derived
cases. This design preserves unresolved results rather than silently filling that separate gap.

### 5. Ownership policy

**Proposal:** one explicit ownership mode applies to every candidate-producing branch.

- `owned_only`: normalize species from `available_pool` and restrict threat, support, shared, and
  usage pools before admission.
- `owned_first`: preserve both owned and unowned candidates, but apply the owned signal during
  bounded branch admission and as the leading ownership component in the final merged rank.
- `owned_last`: preserve both, using ownership only after the branch's substantive evidence and
  again after substantive evidence in final ranking.
- `off`: do not inspect ownership.

Threat identification always remains unrestricted. Ownership constrains whom the recommender
can propose, not which opposing threats exist.

**Proposal:** the orchestrator must receive the mode explicitly, defaulting to `off` only when no
preference was supplied. It must normalize `available_pool`'s `PokemonSet` entries to species IDs
once and pass the same policy to every branch.

**Reasoning:** applying ownership only after branch-local caps can permanently discard the
owned candidates that `owned_first` is intended to surface. Applying it only to counters would
make support and teammate branches behave differently. Current lower-level support is reusable,
but the missing orchestration and non-counter interfaces must be acknowledged rather than
treated as already wired.

### 6. `shared_teammates` integration

**Proposal:** use `shared_teammates` as a bounded candidate-generation source, not merely a
ranking modifier.

**Reasoning:**

1. modifier-only use cannot surface a shared teammate absent from threat/support branches;
2. the original flow discovery explicitly calls for teammate/cohesion candidates
   (`docs/slot_fill_flow_discovery_2026-08-08.md:474-482`);
3. strict all-N intersection already prevents one stale anchor list from unilaterally admitting
   Basculegion;
4. retained top-10 rows naturally bound the branch.

This is admission evidence, not proof that a candidate fits the roster. A shared-only candidate
receives no automatic global rank boost and cannot bypass threat improvement, composition fit,
legality/theme constraints, ownership, or unresolved target-role handling.

**Proposal — edge semantics:**

- unavailable shared evidence: add no candidates and apply no penalty;
- available empty intersection: add no candidates and apply no penalty, while preserving the
  factual distinction in diagnostics;
- exact-attribution row: may admit the species;
- ambiguous/unresolved row: may remain diagnostic evidence but cannot admit a species, because
  canonical form resolution is outside scope;
- absence from the retained intersection: never a veto, because each source list is truncated.

### 7. Role duplication and physical/special balance

**Explicit scope decision:** both belong in this task as multi-member ranking signals.

**Reasoning:** the Basculegion failure was not merely stale data. It was failure to recognize that
Mega Swampert already occupied Rain offense and that another Rain attacker repeated function and
weaknesses. A multi-member ranker that omits composition fit would preserve the observed failure
even with perfectly fresh signals.

**Proposal:** derive locked-member composition evidence from existing resolved builds and
`AnchorRoleDecision`. Derive candidate evidence from a concrete representative or provisional
build. Unknown evidence is neutral.

Role duplication means repeating an already-satisfied strategic function or required mechanism,
not merely sharing a coarse role string. Role compression that fills an unmet function remains
positive.

Physical/special balance is a soft correction only when the current offense is materially
one-sided and the candidate would worsen that asymmetry. It is not a hard 50/50 quota and does
not outrank an urgent uncovered matchup.

This scope does not include condition resilience or selected-four mode viability.

### 8. Attacker/support/balance user preference

**Explicit scope decision:** include the preference as an optional ranking input and a
conditional interaction gate.

**Proposal:** ask only when:

1. the viable leading pool contains materially different offense-primary and support-primary
   directions; and
2. choosing attacker, support, or balanced would change the presented order.

`balanced` means no category bias; it does not force equal role counts. The preference cannot
override hard constraints, an urgent team threat gap, or candidate-specific target-role
evidence. It cannot invent a target role.

**Reasoning:** always asking adds friction when the answer cannot change the result. Never asking
repeats the late-team interaction gap observed in the flow-discovery scenarios.

### 9. Resolved ranking stages

**Resolution:** reject an unconditional `team threat improvement -> composition fit` order.
A marginal matchup improvement must not automatically outrank an urgent composition repair.
Use staged/lexicographic comparison rather than opaque summed weights:

1. **Eligibility**
   - legality and existing hard team constraints;
   - `owned_only`, when selected;
   - exclude already locked species/lineages using existing exact identities.
2. **Decisive verified uncovered closures**
3. **Costly verified uncovered closures**
   - `clean_kill` and `intentional_non_ko_answer` count equally at the same severity.
   - genuinely uncovered team matchups only; an objective that is also a SPOF is not double-counted.
4. **Composition fit**
   - `complementary > neutral/unknown > duplicative > severe duplication`;
   - avoid duplicating satisfied roles/mechanisms;
   - correct material physical/special asymmetry;
   - apply material attacker/support preference after base composition fit.
5. **Toss-up verified uncovered closures**
6. **Conditional uncovered answers**
   - decisive, then costly, then toss-up severity.
7. **SPOF backup answers**
   - decisive, then costly, then toss-up severity.
8. **Cross-anchor support breadth**
   - distinct anchors supported;
   - then distinct needs satisfied.
9. **Evidence quality**
   - exact compendium/build support;
   - other compendium support;
   - usage-backed evidence;
   - mechanical-only evidence.
10. **Shared cohesion**
    - bottleneck percentage, then minimax worst rank, for admitted shared rows.
11. **Determinism**
    - stable normalized candidate ID.

Therefore severe composition repair outranks toss-up, conditional, or SPOF improvement, while a
decisive/costly verified answer to a genuinely uncovered matchup still outranks a composition
concern. Redundancy demotes but does not exclude a competent candidate.

Usage/real-team data remains legitimate for discovery, legality confirmation, and selecting a
representative build to verify. It cannot break otherwise-equal final candidate ties, matching
ADR-015's popularity-independent ranking rule.

The legacy `query_threat_counters` `verified_score` remains a caller-local multiplicative
heuristic, not a global outcome-first precedence rule. Its outcome and severity multipliers trade
off (`clean_kill × toss-up` scores below `intentional_non_ko_answer × decisive`, while
`clean_kill × costly` ties `intentional_non_ko_answer × decisive`). Multi-locked instead asks
which team objectives receive unconditional answers: clean kills and intentional non-KO answers
both close such an objective, consistent with ADR-015 describing the latter as legitimate and not
lesser. Their shared HP-based severity then determines the closure bucket; condition-dependent
answers remain later because they require team context. This portfolio policy does not change the
legacy scalar or require the two callers to share a ranking shape.

**Reasoning:** team-completion ranking must lead with marginal roster value. Compendium-first
still governs need resolution and evidence confidence, but a compendium-backed support candidate
must not automatically outrank the only decisive/costly verified answer to an uncovered threat.

Soft ownership composes at its documented position:

- `owned_first` precedes the substantive key at bounded admission/final ordering;
- `owned_last` follows it;
- neither changes threat identification.

### 10. Reuse boundaries

**Proposal:** carry forward unchanged in purpose:

- `resolve_anchor_build`;
- `classify_anchor_role`;
- `derive_role_shape_context`;
- `query_support_needs`;
- compendium-first `resolve_need_candidates`;
- `CandidateEvidence`;
- candidate-specific target-role decisions;
- pending presentation and `PendingSlotIntent`;
- provisional full-build refinement;
- atomic commit;
- `run_slot_fill_terminal`;
- `rank_and_cut`.

Generalize only the orchestration envelopes that are currently singular:

- one anchor/context becomes all per-anchor contexts plus one team objective;
- evidence gains anchor/team origin;
- branch provenance can include teammates;
- ownership input becomes explicit and uniform;
- threat discovery accepts an explicit team threat set rather than discovering from one anchor.

**Reasoning:** candidate collection and ranking are the missing layer. Track C's cross-turn
selection, refinement, confirmation, and commit semantics are already the correct terminal
lifecycle.

## Explicit out-of-scope dependencies

### Condition resilience

**Explicit scope decision:** excluded. Role/mechanism duplication may identify repeated Rain
offense, but this task does not decide whether Rain, Trick Room, Snow, or another condition has a
backup setter or condition-independent fallback.

### Selected-four / bring-four modeling

**Explicit scope decision:** excluded. Ranking evaluates six-member roster completion only. It
does not model mutually exclusive Mega choices or representative selected-four groups.

### Canonical name/form resolution

**Explicit scope decision:** excluded. Locked members are already fully confirmed, and candidate
merging uses exact identities emitted by current query surfaces. Ambiguous teammate labels cannot
admit candidates. User-entered aliases and base/form attribution remain a separate boundary task.

### Calc-unavailable static fallback

**Explicit scope decision and hard dependency:** excluded. Current coverage and verified threat
ranking can fail when the calc service is unavailable. The multi-member chain must report its
team-threat ranking as incomplete/unavailable in that state; it must not silently invent a static
fallback or present support/shared candidates as if authoritative matchup ranking succeeded.

## Design invariants and review scenarios

These are proposal checks for design review, not implementation tests.

1. **Permutation invariance:** reordering locked slots does not change candidate membership or
   order, except displayed source slot indices.
2. **No privileged-anchor cut:** no candidate is removed from the combined pool before all
   anchors and the team threat objective contribute.
3. **Volume normalization:** duplicating correlated needs from one anchor does not increase its
   distinct-anchor score.
4. **Team-threat precedence:** an anchor weakness already covered by another lock does not outrank
   a truly uncovered team threat.
5. **SPOF improvement:** a candidate that adds a second verified answer receives credit even when
   baseline coverage is non-empty.
6. **Provenance survival:** compendium, usage, mechanical, teammate, anchor, need, and threat
   origins survive merge, presentation, and pending intent.
7. **Target-role locality:** a threat-only or shared-only candidate does not inherit another
   candidate's support-derived role.
8. **Target-role conflict:** incompatible needs remain an `UnresolvedTargetRoleDecision`.
9. **Compendium reuse:** mapped support needs still resolve compendium-first and retain rejection
   semantics.
10. **Ownership consistency:** every branch observes the same mode; threat identification remains
    unrestricted.
11. **Shared evidence availability:** unavailable and empty add no candidates or penalty; only
    exact rows can admit.
12. **Shared-only restraint:** a candidate may enter through shared evidence but cannot lead
    without independent team-fit value.
13. **Basculegion regression:** with Mega Swampert already supplying Rain offense, stale
    Archaludon cooccurrence cannot make redundant Basculegion lead over a candidate closing a real
    team gap.
14. **Unknown composition evidence:** missing representative role/category evidence is neutral,
    not guessed.
15. **Preference materiality:** the attacker/support/balance question appears only when it changes
    viable ordering.
16. **Track C terminal preservation:** selection still creates a pending intent, then a complete
    provisional build, confirmation, and atomic commit.
17. **Calc failure honesty:** no authoritative team-threat ranking is claimed without the current
    calc-backed evidence or a separately designed fallback.

Resolved ordering acceptance scenarios:

- `test_severe_composition_repair_outranks_minor_threat_gain`;
- `test_equal_impact_band_prefers_verified_threat_gain`;
- `test_composition_beats_toss_up_or_spof_gain`;
- `test_decisive_or_costly_uncovered_closure_precedes_composition`;
- `test_usage_does_not_break_equal_candidate_ties`.

## Residual risks

1. **Composition predicates may need calibration.** The ordering boundary is resolved, but real
   team examples may refine which repeated functions qualify as duplicative or severe
   duplication. Named boundary tests must make such policy changes explicit.
2. **Shared teammate recall is bounded by retained top-10 lists.** Treating absence as non-evidence
   and never as a veto prevents false exclusion, but long-tail cohesion remains invisible.
3. **Current target-role vocabulary is incomplete.** The design preserves unresolved outcomes;
   it does not complete the separately deferred role taxonomy/dispatch.
4. **Calc availability remains operationally significant.** This report exposes the dependency
   rather than absorbing static fallback work.

## Review gate

Review the verified findings and design decisions in this document before creating an
implementation plan. In particular, approve or revise:

1. explicit team-coverage/SPOF threats instead of concatenated per-anchor
   `query_threat_counters` output;
2. shared teammates as a bounded candidate source;
3. role duplication, physical/special balance, and material user preference as in-scope ranking
   signals;
4. the resolved severity-aware ranking precedence;
5. explicit incomplete behavior when calc-backed team-threat evidence is unavailable.

No ADR, project-log entry, implementation plan, source change, or runtime test belongs in this
pass.
