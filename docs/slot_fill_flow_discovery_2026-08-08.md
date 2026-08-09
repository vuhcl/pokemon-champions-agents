# Slot-Fill Flow Discovery Report

**Date:** 2026-08-08  
**Audience:** Claude / next implementation-planning session  
**Status:** Discovery record. Every section labeled **Proposal** is for review, not an accepted architecture decision.

## Purpose and method

This session did not validate a predesigned flow. It attempted to discover the flow by role-playing four materially different team-building scenarios and calling the repository's real functions and data:

1. fill one slot beside an existing Kingambit anchor;
2. begin from an empty team with an optional owned pool;
3. build a complete team around Archaludon;
4. choose between mono-Steel and mono-Fairy, then build a mono-Fairy hybrid roster.

The session used the shipped proposal/refinement path, ADR-022 queries, ADR-023 terminal machinery, Role Compendium, usage and teammate records, legality checks, static counters, the calc service, and the current graph entry points. Manual reasoning was explicitly identified when no function produced the required input or conclusion.

## Executive findings

1. The repository has most individual capabilities, but the live graph still does not connect them into one slot-fill.
2. A single fixed slot-fill sequence is insufficient. The orchestrator must route by team phase:
   - empty-team bootstrap;
   - early anchor/core construction;
   - team-wide completion after multiple locks;
   - provisional-build refinement and confirmation.
3. Candidate selection and build commitment need distinct states. The safe sequence is:
   `candidate chosen -> provisional full build -> user confirmation -> atomic slot lock`.
4. Anchor evidence is useful for the first core, but harmful when applied indefinitely. After roughly three locked Pokémon, team-wide threats, role diversity, shared teammates, and user preference should dominate.
5. Every essential field condition needs either redundant setup or a demonstrated condition-independent mode.
6. Usage, mechanical legality, and damage verification answer different questions. “Legal and super-effective” is candidate-generation evidence, not enough to select a move.
7. Four-of-six formats require evaluating plausible selected-four groups. Roster legality alone cannot model mutually exclusive Mega choices or mode dependencies.
8. Tool output and agent reasoning must be separately attributed in every presentation.

## What was actually attempted

### Scenario 1: Kingambit anchor, one open partner slot

Actual sequence:

1. Loaded Kingambit's real usage build.
2. Called `query_counters`; Incineroar led the returned relevant threats.
3. Called `query_threat_counters`; it failed because the calc service was not running.
4. Manually constructed `RoleShapeContext` because no runtime producer exists.
5. The first guessed role shape was wrong and generated false Fake Out/Taunt needs.
6. Reconstructed the context from Kingambit's real usage kit.
7. Called `query_support_needs`; it surfaced healing, screens, and optional Trick Room.
8. Presented the support directions; the user selected Trick Room.
9. The phrase “Trick Room” had to be manually interpreted as the `trick_room_setter` need/category.
10. Called the support-need resolver. It searched legal move learners and returned a capped pool, but did not use the shipped Trick Room Setter compendium.
11. Applied overlap annotation/ranking. Generic need overlap elevated Delphox-Mega instead of privileging the user's selected Trick Room need.
12. The user chose Farigiraf.
13. Used the pending-presentation bridge to parse the choice and call `apply_lock`.
14. Handed the species to refinement.
15. Refinement produced an incomplete/incorrectly preserved build in at least one attribute, including a missing nature despite usage evidence.
16. The session corrected the order: future candidates must remain provisional until the complete refined build is shown and confirmed.

Observed gaps:

- `RoleShapeContext` is required but no live node derives it.
- A bad manual role-shape guess can create confidently wrong support needs.
- Natural-language need names and internal taxonomies do not resolve consistently.
- Need resolution bypasses relevant Role Compendium categories.
- Chosen-need intent is not strong enough in candidate ordering.
- The calc dependency fails hard rather than yielding a clearly labeled static fallback.
- Refinement can discard available nature/build evidence.
- The terminal path commits species before the required full-build confirmation.

### Scenario 2: Empty team with an available pool

The user required the opening to surface two choices at once:

- choose a team direction or anchor;
- provide an available pool.

The provided pool was Milotic, Swampert, Gholdengo, Staraptor, Whimsicott, Sinistcha, Mimikyu, Sneasler, Incineroar, and “Eternal Floette,” while still allowing outside recommendations.

Actual sequence:

1. Called `query_by_usage` against owned candidates.
2. Compared owned usage leaders with global options.
3. Intersected owned species with shipped Role Compendium categories.
4. Loaded representative usage builds to identify real role combinations.
5. “Eternal Floette” silently disappeared because the canonical identifier is `Floette-Eternal`.
6. Recommended owned Gholdengo setup offense with Whimsicott and Incineroar.
7. Clearly separated the recommendation from tool results:
   - usage and compendium membership were tool-produced;
   - choosing that combination as the preferred direction was agent reasoning.
8. Tested the graph's interpretation of an initial “Gholdengo” reply.
9. `classify_pending` could not classify a general first-turn choice without a pending presentation, so a manual `LockPayload` was needed.
10. Runtime `infer_role` reduced Gholdengo to `fast_attacker`, losing its Nasty Plot/setup identity.

Observed gaps:

- Empty-team bootstrap currently falls toward `_pick_role`'s generic `bulky_attacker` default instead of asking a useful opening question.
- If the user delegates after the opening, no explicit mechanism recommends an anchor/direction.
- Name resolution is absent at the input boundary.
- Unresolved pool entries are silently dropped.
- `query_by_usage` can restrict to owned species but cannot express the desired “owned first, outside allowed” bootstrap behavior.
- Ownership preference is not consistently available across query APIs.
- General first-turn intent classification and pending-presentation classification are conflated.
- Runtime roles cannot preserve setup-role identity from the compendium.

### Scenario 3: Build around Archaludon

Actual sequence:

1. Loaded Archaludon's representative Stamina/Leftovers/Electro Shot build.
2. Ran anchor support analysis. It surfaced SpD coverage, healing, screens, and preferably Tailwind.
3. The support tool did not surface Rain.
4. Manually inferred Rain from Electro Shot's one-turn behavior in Rain.
5. Queried the Rain Setter compendium; Pelipper and Politoed were the leading candidates.
6. Recommended Pelipper, initially without checking Archaludon's stored teammate data.
7. After user correction, read the teammate records directly:
   - Pelipper was first;
   - Swampert second;
   - Basculegion third;
   - Grimmsnarl fourth;
   - Sinistcha fifth;
   - Whimsicott was absent.
8. Confirmed Pelipper compresses Drizzle and Tailwind in one usage-backed slot.
9. Refined Pelipper to the requested bulkier spread and confirmed the full build.
10. Returned to Archaludon because its own complete build had never been confirmed; refined and confirmed a bulkier version.
11. Built an initial three-member core using Archaludon teammate evidence and surfaced role compression such as Grimmsnarl's screens.
12. Resolved the teammate label `Swampert` to `Swampert-Mega` after finding:
    - Swampertite on 95.5% of in-game Swampert;
    - a form-specific Mega record with Swift Swim;
    - a misleading merged base-form representative set.
13. Refined Mega Swampert and preserved Earthquake after the user rejected the manually substituted High Horsepower.
14. Continued using anchor teammate evidence too long and proposed Basculegion, duplicating Rain offense and weaknesses.
15. Rolled back that reasoning and changed phase from anchor-centric core construction to team-wide gap analysis.
16. Aggregated threats across the locked core. Shared Ground/Steel pressure, especially Excadrill, became the main selection signal.
17. Filled later slots by team-wide role and matchup needs rather than Archaludon's teammate list.
18. Completed the roster with Mega Swampert, Annihilape, and Modest Hydreigon after full-build confirmations.
19. Ran legality and item-uniqueness checks.
20. The user noted that the late-slot flow should explicitly ask whether the remaining roster should lean attacker or support.
21. The user also added shared-common-teammate intersection as a signal once multiple slots are locked.

Observed gaps:

- Move-dependent field requirements such as Electro Shot -> Rain have no detector.
- Teammate data is stored but has no query API.
- Stored teammate percentages are unavailable.
- Base-form teammate names can resolve to the wrong battle form/build.
- Ownership does not automatically propagate from a base species to its Mega form.
- `infer_role` misclassifies multifunction support sets, including Pelipper/Grimmsnarl/Sinistcha cases.
- No explicit transition changes candidate evidence after an initial core is formed.
- Anchor cooccurrence can overwhelm team-wide composition and create redundant attackers.
- Shared threat aggregation exists only as ad hoc orchestration.
- Shared common teammates across multiple locked members have no callable.
- Late-slot attacker/support preference is not solicited by the live flow.
- Nature can again be lost during refinement even when usage supplies it.

### Scenario 4: Mono-Steel or mono-Fairy

Actual sequence:

1. Enumerated legal Steel and Fairy species.
2. Called usage ranking within each type and compared owned representation.
3. Recommended mono-Fairy because it had more owned candidates and clearer initial role diversity.
4. Failed to surface Mawile as the natural Steel/Fairy bridge before forcing the direction choice.
5. After user correction, resolved Mawile's form attribution:
   - Mawilite appeared on 99.3% of the in-game record;
   - the effective anchor was Mega Mawile, not base Mawile.
6. Compared evidence-backed directions:
   - Mega Mawile Trick Room;
   - Whimsicott fast offense;
   - Ninetales-Alola Snow/Aurora Veil.
7. The user chose a hybrid Mega Mawile Trick Room plus Ninetales-Alola Snow direction.
8. Refined Mega Mawile, added Swords Dance by request, re-presented the complete revision, and confirmed it.
9. Refined a bulky-support Ninetales spread.
10. Checked Moonblast and Encore usage/legality.
11. Initially asked the user to choose Blizzard versus Freeze-Dry before evaluating whether Water was actually the larger team-wide gap.
12. After correction, aggregated current threats. Basculegion, Blastoise, and Swampert made Water coverage relevant.
13. Static `query_counters` returned identical results for Blizzard and Freeze-Dry because it does not model Freeze-Dry's special Water effectiveness.
14. Chose Freeze-Dry provisionally using mechanical reasoning and later confirmed it.
15. With two locks, intersected shared teammate records. Whimsicott was the only shared teammate satisfying mono-Fairy, but it was initially excluded as a Trick Room option because it lacked compendium/usage proof.
16. Corrected candidate generation to include legal mechanical options with lower confidence rather than hiding them.
17. Selected Hatterene.
18. Hatterene's no-usage refinement produced only Trick Room and Protect; item, spread, nature, and two moves remained empty.
19. Constructed a legal tier-3 build manually.
20. Iterated Hatterene's build against current shared threats:
    - considered Psychic, Dazzling Gleam, Giga Drain, Mystical Fire, and Protect;
    - retained Protect and Mystical Fire;
    - selected Dazzling Gleam as the STAB move;
    - switched Sitrus Berry to Life Orb by request;
    - required fresh confirmation after each material revision.
21. The user identified two missing gates for Giga Drain: usage support and damage benchmarks.
22. Asked whether the final three should lean attacker, support, or balanced; the user chose balanced.
23. A strict Fairy-only counter query returned no candidates, so the flow degraded to type, ability, and move-mechanics reasoning.
24. Identified Primarina as the best Fire/Ground answer because Liquid Voice turns Hyper Voice into Water damage.
25. `query_counters` had missed Primarina because it does not model Liquid Voice conversion.
26. Confirmed Primarina as the fourth slot.
27. Evaluated shared teammates and support roles for slot five.
28. Incorrectly excluded additional Mega forms from the six-member roster.
29. Corrected the rule:
    - multiple Mega-capable Pokémon may be rostered;
    - only selected-four/in-battle choices create incompatibility.
30. Compared Mega Clefable with base Clefable.
31. Chose base Clefable because Mega Clefable would prevent Mega Mawile from functioning in the same selected four and would therefore require a different redirected attacker.
32. Replaced Moonblast with Icy Wind for condition-independent speed control and confirmed the revised full build.
33. Chose owned Mimikyu for the final flexible attacker slot after team-wide threat and role analysis.
34. Synthesized and confirmed an Expert Belt coverage build.
35. Started the real calc service and ran exact damage plus calc-backed coverage/SPOF review.
36. Verified:
    - bulky Ninetales Freeze-Dry does 43.6-52.7% to Basculegion and 36-43.7% to Blastoise;
    - max-SpA Ninetales still only 2HKOs;
    - Life Orb Hatterene Giga Drain does 81.7-96.4% to Basculegion and 66.6-79.7% to Blastoise;
    - Liquid Voice Primarina has roughly coin-flip OHKOs on Charizard, Torkoal, and Excadrill;
    - Life Orb Hatterene Mystical Fire has a 75% OHKO chance on Excadrill;
    - Expert Belt Mimikyu Wood Hammer OHKOs Basculegion but only 2HKOs Blastoise;
    - the top-threat review found no clean answer to Mega Charizard X;
    - the review reported Mawile and Primarina as apparent single points of failure.
37. Checked the user's move-usage correction that Phantom Force is more popular than Shadow Claw.
38. The integrated snapshot contained no Mimikyu usage record, exposing a data-coverage gap.
39. Calc comparison still strongly favored Phantom Force against Ceruledge:
    - Shadow Claw: 75.6-88.9%, guaranteed 2HKO;
    - Phantom Force: 96.6-115.4%, 81.3% OHKO.
40. Recognized Phantom Force's semi-invulnerable first turn as positive doubles positioning value, not merely a two-turn drawback.
41. Added the general requirement that essential Rain/Trick Room/Snow conditions need a secondary setter or a demonstrated fallback mode.

Observed gaps:

- Theme comparison lacks bridge-candidate detection.
- Monotype is not enforced automatically as a hard candidate constraint.
- Form attribution fails for Mega-dominant base records.
- Candidate generation treats compendium membership too exclusively and can hide valid legal options.
- Tier-3 refinement cannot always produce a confirmable full build.
- Static counters miss special move rules and ability-driven type conversion.
- Strict matchup thresholds can empty constrained candidate pools without a degraded reasoning path.
- The six-member roster and selected-four composition are not modeled separately.
- Existing ADR text that describes a single-Mega roster constraint is stale for this format.
- `Slot` has no ability attribute, so synthesized abilities are lost in team review.
- Team review does not model Trick Room as a field/speed mode.
- Team review evaluates the roster more readily than plausible selected-four combinations.
- The usage snapshot has no Mimikyu record, so usage-backed move comparison silently becomes unavailable.
- The calc service is an external runtime dependency and initially failed to start inside the sandbox.
- Candidate descriptions can overclaim “answers Water” when damage only supports chip or a 2HKO.

## Consolidated gap inventory

### Orchestration and graph gaps

1. **ADR-022/023 is not on the live proposal path.** `propose_team_draft` calls `fill_team_draft`; it does not instantiate `SlotFillContext` or call the four query tools.
2. **ADR-023 terminal machinery is callable but not graph-connected.** `run_slot_fill_terminal` directly calls `apply_lock`, while the graph has no slot-fill discovery/presentation node.
3. **No bootstrap node exists.** `accept_available_pool` routes directly to `propose_team_draft`.
4. **No team-phase router exists.** Empty, early-anchor, and late-team slots enter the same proposal function.
5. **No provisional slot-build state exists.** The current terminal sequence commits species before refinement.
6. **`classify_pending` is presentation-bound.** It cannot serve general first-turn direction/anchor interpretation.
7. **No structural trigger asks attacker versus support for late slots.**
8. **No structural trigger checks shared teammates after multiple locks.**
9. **No structural trigger checks condition resilience.**
10. **No structural trigger performs bring-four compatibility analysis.**

### Data and identity gaps

1. No canonical name/form resolver at user-input boundaries.
2. No ambiguity prompt for shorthand such as “Floette.”
3. Unresolved names can disappear silently.
4. Base-form teammate labels can map to the wrong form-specific usage build.
5. Ownership does not propagate across base/Mega forms.
6. Teammate records lack a public query API.
7. Teammate percentages are discarded or unavailable.
8. No shared-common-teammate query exists.
9. Mimikyu is absent from the integrated usage snapshot.
10. Runtime role taxonomy loses setup and multifunction identities.

### Reasoning-input gaps

1. No producer derives `RoleShapeContext`.
2. No explicit distinction marks a condition as essential, preferred, or optional.
3. No detector maps move mechanics to conditions, such as Electro Shot -> Rain.
4. No robust representation maps ability plus move interactions, such as Liquid Voice + Hyper Voice.
5. No special-effect edge models Freeze-Dry -> Water.
6. No positioning-value edge models Phantom Force -> semi-invulnerable turn.
7. No phase rule limits anchor cooccurrence to early core construction.
8. Shared threats and role duplication are manually aggregated.

### Tool-composition gaps

1. Natural-language support needs do not reliably map to compendium categories.
2. Support-need resolution can use raw learnsets while bypassing a stronger compendium.
3. `query_by_usage` lacks owned-first bootstrap behavior.
4. Ownership modes differ across query APIs.
5. `_union_move_candidates` can be nondeterministic because it iterates a `frozenset`.
6. Static counters do not model several conditional mechanics.
7. Threat-counter queries require a running calc service and have no integrated static fallback.
8. Strict query thresholds can return an empty constrained pool without signaling the next fallback.
9. Tier-3 refinement may leave item, nature, spread, or moves unfilled.
10. Usage-provided nature can be lost during refinement.
11. `Slot` cannot retain ability for downstream review.

### Interaction and presentation gaps

1. Tool evidence and agent reasoning are not structurally separated.
2. Candidate confidence is not labeled as usage-backed, compendium-backed, mechanical-only, or synthesized.
3. Conditional recommendations can be presented before their condition is checked.
4. Full builds are not guaranteed to be shown before commitment.
5. A revised build is not structurally forced through fresh confirmation.
6. No atomic full-slot lock follows confirmation.
7. No explanation is required when a pool entry fails resolution.
8. No presentation rule explains whether a move is a clean answer, probable KO, 2HKO, or chip.

### Team-level modeling gaps

1. Six-member roster validity and selected-four compatibility are conflated.
2. Multiple Mega-capable roster members are incorrectly excluded by stale reasoning/documentation.
3. Trick Room and other speed modes are not modeled by team coverage.
4. Essential-condition redundancy is not checked.
5. A condition-independent fallback mode is not demonstrated.
6. SPOF output can be misleading when abilities or speed modes are absent from state.
7. Team review does not enumerate representative selected-four groups.

## Existing tools and the interaction edges they need

The following are available now, but several have no live caller or successor.

### Live graph and proposal path

- `initialize -> accept_available_pool -> propose_team_draft` exists.
- `propose_team_draft -> fill_team_draft` exists.
- `fill_team_draft -> _pick_role -> refinement hierarchy` exists.
- `classify_input -> apply_lock/constraint/rejection/archetype/reset/review` exists.
- Every mutating intent handler currently returns to `propose_team_draft`.

Missing interaction edges:

- `accept_available_pool -> bootstrap_direction`.
- `propose_team_draft -> team_phase_router`.
- `team_phase_router(empty) -> bootstrap_direction`.
- `team_phase_router(early_core) -> anchor_slot_discovery`.
- `team_phase_router(late_team) -> team_gap_slot_discovery`.
- `candidate_choice -> provisional_build_refinement`.
- `provisional_build_refinement -> full_build_presentation`.
- `full_build_acceptance -> atomic_full_slot_lock`.
- `atomic_full_slot_lock -> post_lock_team_checks`.

### ADR-022 query tools

- `query_by_usage` is available for bootstrap popularity.
- `query_counters` is available for static relevant threats.
- `query_threat_counters` is available for verified depth-one answers when calc is healthy.
- `query_support_needs` is available once `RoleShapeContext` exists.

Missing interaction edges:

- `anchor usage build -> RoleShapeContext producer`.
- `anchor -> query_counters` and `anchor -> query_support_needs` in parallel.
- `query_counters -> query_threat_counters`.
- `threat answers + support needs -> annotate_overlap`.
- `chosen support need -> resolver dispatcher`.
- `calc unavailable -> labeled static fallback`.

### ADR-023 terminal machinery

- `SlotFillContext`, `annotate_overlap`, `merge_need_resolved`, `present_candidates`, and `run_slot_fill_terminal` exist.
- The pending bridge can resolve a presented candidate and call `apply_lock`.

Missing interaction edges:

- `team_phase_router -> SlotFillContext construction`.
- `query outputs -> persisted/reconstructable context across user turns`.
- `present_candidates -> pending presentation -> classify_pending`.
- `candidate acceptance -> provisional build`, rather than immediate committed-species lock.

### Role Compendium and need resolution

- Weather setters, Redirection, Swords Dance, Nasty Plot, and Trick Room Setter categories exist.
- `role_candidates` and `load_role_category` are callable.

Missing interaction edges:

- `natural-language need -> canonical need/category`.
- `need resolver -> compendium first`.
- `compendium candidates + legal mechanical candidates -> confidence-labeled union`.
- `compendium role -> runtime role without losing setup identity`.

### Ownership, naming, usage, and teammate evidence

- `available_pool`, ranking ownership modes, species usage, representative sets, and raw teammate arrays exist.

Missing interaction edges:

- `raw user name -> canonical species/form`.
- `canonical base species -> battle form attribution`.
- `base ownership -> legal form ownership`.
- `empty-team bootstrap -> owned-first ranking with outside alternatives`.
- `anchor -> teammate query`.
- `two or more locked species -> shared teammate intersection`.
- `shared teammate signal -> early-core validation or late-team secondary evidence`.

### Refinement, legality, and calc

- Tier-1/2/3 spread sourcing, move narrowing, legality checking, calc client, coverage review, and SPOF detection exist.

Missing interaction edges:

- `candidate choice -> complete provisional build`.
- `usage miss -> guaranteed complete tier-3 constructor`.
- `provisional build -> legality`.
- `coverage claim -> exact benchmark calc`.
- `verified complete build -> user confirmation`.
- `confirmed build -> atomic lock`.
- `locked team -> selected-four/mode-aware review`.

## Potential domain dependency edges

These are not necessarily LangGraph edges. They are mechanics or evidence interactions that should be represented so tools can compose correctly:

- `Electro Shot -> Rain preferred/required for one-turn use`.
- `Drizzle -> Rain condition`.
- `Pelipper -> Drizzle + Tailwind role compression`.
- `Swift Swim -> Rain dependence`.
- `Snow Warning -> Aurora Veil availability`.
- `Freeze-Dry -> super-effective against Water`.
- `Liquid Voice + Hyper Voice -> Water-type spread damage`.
- `Disguise -> safer setup/execution`.
- `Phantom Force -> semi-invulnerable positioning turn`.
- `Trick Room setter -> slow attacker enablement`.
- `Icy Wind/Tailwind/priority -> condition-independent speed fallback`.
- `Follow Me -> setup protection`.
- `Helping Hand -> ally damage breakpoint`.
- `Life Dew/Hospitality -> sustain`.
- `multiple Mega-capable roster members -> selected-four incompatibility, not roster illegality`.
- `owned base species -> owned Mega form when the transformation item/form is legal`.
- `shared teammate of multiple locks -> cohesion evidence`.
- `same attacking role/typing across candidates -> duplication penalty`.
- `essential condition -> secondary setter OR fallback mode`.

## Proposal: natural end-to-end flow for review

This is a proposal, not a decision.

### 0. Normalize inputs and hard constraints

1. Resolve user names to canonical species/forms.
2. Preserve original input for explanations.
3. Ask on ambiguity; never silently discard.
4. Normalize ownership across legal forms.
5. Record hard constraints such as monotype.
6. Record format semantics, especially six-roster/four-selection rules.

### 1. Route by team phase

#### Empty team

1. Ask for team direction/anchor and available pool in the same prompt.
2. If the user supplies either, use it.
3. If the user delegates, propose one concrete direction plus real alternatives.
4. Bias toward owned species while still allowing outside candidates.
5. Attribute usage facts separately from the agent's recommendation.

#### Early anchor/core, usually one to three confirmed members

1. Attempt role/archetype membership first.
2. Load real usage builds and form attribution.
3. In parallel:
   - derive threats;
   - derive support needs;
   - query common teammates.
4. Merge overlap between verified threat answers and support needs.
5. Validate leading candidates against pair cooccurrence.
6. Prefer role compression when evidence supports it.

#### Team completion, usually three or more confirmed members

1. Stop treating the original anchor as the sole reference point.
2. Aggregate team-wide threats and uncovered matchups.
3. Evaluate role duplication and physical/special balance.
4. Intersect shared common teammates across locked members.
5. Ask whether remaining slots should favor attackers, support, or balance when that preference changes ranking.
6. Treat shared teammates as cohesion evidence, not a veto over team needs.
7. Evaluate plausible selected-four groups and mutually exclusive Mega choices.

### 2. Generate a tractable candidate pool

1. Apply hard legality/theme/ownership constraints.
2. Dispatch known role needs to the Role Compendium.
3. Add legal mechanical candidates omitted by the compendium, labeled lower confidence.
4. Add threat-answer candidates.
5. Add teammate/cohesion candidates.
6. Add owned candidates as a preference, not necessarily a restriction.
7. Deduplicate canonical forms and keep evidence provenance.

### 3. Deep-verify before presentation

For each tractable candidate:

1. resolve the correct form;
2. load representative usage;
3. verify ability/move interactions;
4. verify legality;
5. check role overlap and new weaknesses;
6. run calc breakpoints for claims that depend on damage;
7. check essential-condition resilience;
8. check selected-four compatibility;
9. demote or eject candidates that fail.

### 4. Present candidates

Present:

- one concrete default;
- one or two genuinely different alternatives;
- the role and team gap each fills;
- ownership status;
- usage/compendium/mechanical/calc provenance;
- important tradeoffs;
- any condition or selected-four dependency.

Do not present an unchecked conditional choice such as “use Freeze-Dry if Water is the bigger gap.” Check the gap first.

### 5. Treat the user's candidate choice as provisional

Do not commit the species to the team draft yet. Store a pending/provisional slot intent containing:

- chosen species/form;
- intended role;
- evidence and rationale;
- requested user modifications.

### 6. Build the complete provisional set

Use:

1. exact usage build;
2. usage-supported adaptation;
3. role templates and move narrowing;
4. minimal legal tier-3 synthesis.

The result must include species, form, ability, item, nature, spread, four moves, role, and evidence quality.

### 7. Verify the provisional set

1. legality and item clause;
2. exact usage support where claimed;
3. matchup/damage benchmarks where claimed;
4. team-wide redundancy and new weaknesses;
5. field-condition resilience;
6. selected-four compatibility.

### 8. Present the full build and require confirmation

1. Show every attribute and rationale.
2. Allow targeted revisions.
3. Re-run affected verification after revisions.
4. Require fresh confirmation for every material revision.

### 9. Atomically lock the full slot

After acceptance, lock all confirmed attributes together. Avoid a committed species with unconfirmed moves/item/spread.

### 10. Run post-lock checks and loop

1. update team phase;
2. recompute team-wide gaps;
3. recompute shared teammates;
4. check condition redundancy/fallback;
5. check representative selected-four modes;
6. continue to the next slot or final review.

## Proposal: graph integration sketch for review

This is a proposal, not a decision.

Prefer a small number of orchestration nodes rather than one graph node per low-level query:

1. `bootstrap_direction`
   - entered after pool acceptance when no anchor/theme exists;
   - presents direction and pool options.
2. `route_team_phase`
   - chooses bootstrap, early-core discovery, late-team discovery, provisional refinement, or final review.
3. `discover_slot_candidates`
   - constructs `SlotFillContext`;
   - calls the relevant ADR-022 tools;
   - merges role, threat, support, ownership, and teammate evidence;
   - emits a pending candidate presentation.
4. `refine_provisional_slot`
   - consumes candidate choice without committing;
   - creates and verifies a full build.
5. `confirm_full_build`
   - emits a pending full-build presentation.
6. `commit_full_slot`
   - atomically locks all confirmed attributes.
7. `post_lock_review`
   - updates team phase and condition/selected-four diagnostics.

### Proposed modular function boundaries

The graph nodes above should be thin orchestrators. Ranking, evidence composition, verification, and team diagnostics should remain reusable functions with narrow contracts, similar to `rank_and_cut`, rather than being embedded in node bodies.

These are conceptual contracts for review, not settled names or signatures:

1. `collect_candidate_evidence(state, ctx) -> CandidateEvidenceBundle`
   - calls only the sources enabled by the current team phase;
   - collects role/compendium, threat, support-need, usage, ownership, and teammate evidence without ranking it;
   - preserves source attribution and failures, including unavailable calc evidence.
2. `merge_candidate_evidence(bundle) -> list[AnnotatedCandidate]`
   - canonicalizes species/forms and deduplicates candidates;
   - reuses `annotate_overlap` and `merge_need_resolved`;
   - attaches every supporting and conflicting signal instead of allowing one branch to overwrite another.
3. `rank_and_cut_slot_candidates(candidates, ctx, *, stage) -> list[AnnotatedCandidate]`
   - centralizes ordering and cut policy instead of distributing sorting across resolvers and nodes;
   - should reuse or generalize the existing `rank_and_cut` machinery rather than create an unrelated ranking implementation;
   - supports at least a `tractable` stage before deep verification and a `presentable` stage afterward;
   - applies hard constraints before soft ownership, cohesion, and role-fit preferences.
4. `verify_candidate_pool(candidates, state, ctx) -> list[VerifiedCandidate]`
   - checks form attribution, legality, representative usage, conditional mechanics, matchup breakpoints, role duplication, and new shared weaknesses;
   - can promote, demote, or eject candidates;
   - returns explicit confidence/provenance instead of only a reordered species list.
5. `assess_condition_resilience(team) -> ConditionResilience`
   - classifies Rain, Snow, Trick Room, Tailwind, and similar conditions as essential, preferred, or optional;
   - reports a secondary setter, a condition-independent fallback mode, or an unresolved dependency;
   - is callable both during candidate verification and post-lock review.
6. `assess_selected_four_modes(team) -> list[SelectionModeAssessment]`
   - evaluates representative four-of-six groups;
   - detects incompatible Mega commitments, missing setters, and modes that only function when an omitted member is brought;
   - keeps roster legality separate from battle-selection viability.
7. `build_provisional_slot(candidate, state, user_edits) -> ProvisionalSlot`
   - runs the existing tier-1/tier-2/tier-3 refinement hierarchy;
   - guarantees a complete species/form, ability, item, nature, spread, and four-move result or returns a structured unresolved result;
   - does not mutate `team_draft`.

The central candidate-discovery orchestrator should therefore be approximately:

`collect -> merge -> rank/cut to tractable -> verify -> rank/cut to presentable -> present`

The provisional-build orchestrator should be:

`build provisional slot -> verify build/team interactions -> present full build -> await confirmation`

Likely graph edges:

- `accept_available_pool -> route_team_phase`
- `apply_lock/record_constraint/record_rejection/handle_archetype_change -> route_team_phase`
- `route_team_phase(empty) -> bootstrap_direction`
- `route_team_phase(open_slot) -> discover_slot_candidates`
- `discover_slot_candidates -> END` after presentation
- `classify_input(candidate_accept) -> refine_provisional_slot`
- `refine_provisional_slot -> confirm_full_build -> END`
- `classify_input(build_accept) -> commit_full_slot`
- `commit_full_slot -> post_lock_review`
- `post_lock_review -> route_team_phase` or `END`

The pending presentation must distinguish candidate selection from full-build confirmation so `classify_pending` can route each acceptance correctly.

## Proposed acceptance checks for a future implementation

1. Empty team presents direction and pool options together.
2. Delegation after the opening produces an owned-biased anchor recommendation.
3. “Eternal Floette” resolves to `Floette-Eternal`; ambiguous “Floette” asks.
4. “Trick Room” resolves to the Trick Room Setter category.
5. Kingambit slot-fill calls both threat and support branches and annotates overlap.
6. Archaludon detects Electro Shot's Rain interaction.
7. Pelipper is recognized as both Rain and Tailwind compression.
8. Swampert teammate evidence resolves to Mega Swampert where usage warrants it.
9. After three locks, candidate ranking switches from anchor-centric to team-wide.
10. Shared teammates are computed for two or more locked species.
11. Late-slot selection asks attacker/support/balance when materially relevant.
12. Mono-Fairy remains a hard filter.
13. Mawile is surfaced as a Steel/Fairy bridge.
14. Multiple Mega-capable roster members are allowed but conflicting selected-four modes are flagged.
15. Freeze-Dry and Liquid Voice interactions affect matchup analysis.
16. No-usage Hatterene still receives a complete, legal provisional build.
17. Mimikyu usage absence is reported rather than silently treated as evidence.
18. Essential Trick Room/Rain teams have a backup setter or validated fallback mode.
19. No slot attribute is locked before complete-build confirmation.
20. A confirmed build is atomically committed.

## Suggested implementation priority

### Highest priority

1. Add team-phase routing and connect ADR-022/023 to the live graph.
2. Add provisional full-build confirmation and atomic commit.
3. Add canonical name/form resolution with unresolved-input reporting.
4. Add form-aware ownership and teammate attribution.
5. Add teammate/shared-teammate query surfaces.
6. Add condition classification and redundancy/fallback checks.

### Next priority

1. Produce `RoleShapeContext` from real state.
2. Wire need categories to the Role Compendium before raw learnset search.
3. Preserve ability in committed slot state.
4. Fill all tier-3 build attributes deterministically.
5. Add move/ability conditional mechanics needed by counters and review.
6. Add a labeled static fallback when calc is unavailable.
7. Add selected-four review and correct stale Mega documentation.

### Lower priority

1. Expand usage coverage, including Mimikyu.
2. Preserve teammate percentages.
3. Make candidate union ordering deterministic.
4. Improve runtime role taxonomy for setup and multifunction supports.
5. Add richer provenance and confidence labels to presentation.

## Final handoff

The session's central result is not one universal sequence. It is a state-dependent loop with explicit phase changes and two human gates:

1. candidate/direction choice;
2. complete-build confirmation.

The smallest useful integration is a phase router plus one candidate-discovery orchestrator, one provisional-refinement step, and one atomic commit step. Existing query, compendium, pending-presentation, legality, refinement, and calc components should be reused behind those nodes rather than reimplemented.
