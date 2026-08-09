# RoleShapeContext Derivation Discovery Report

**Date:** 2026-08-08  
**Audience:** Vu / next design-review session  
**Status:** Discovery record. Every section labeled **Proposal** is for review, not an accepted architecture or implementation decision.

## Purpose and method

This report investigates the missing link in the proposed flow:

`role decision -> RoleShapeContext -> SlotFillContext -> ADR-022 query tools`

It does not implement that link. It:

1. reads the current `RoleShapeContext` contract directly from source;
2. inventories every repository construction site;
3. reconstructs the incorrect and corrected Kingambit executions from the role-play transcript;
4. checks the no-anchor path that was executed in the same transcript;
5. proposes source precedence and field derivation rules;
6. identifies where the current struct or the proposed chain is semantically wrong or incomplete.

Primary evidence:

- `recommender/support_needs.py`;
- `recommender/slot_fill.py`;
- all `RoleShapeContext(...)` constructions under `tests/`;
- the real slot-fill role-play transcript, especially Kingambit events 5-16 and empty-team events 17-18;
- the two latest `master_project_log.md` entries covering the paused `_pick_role` redesign and corrected phase routing.

## Executive findings

1. **There is no production construction site.** The repository contains 42 constructors: 30 in `test_query_support_needs.py` and 12 in `test_slot_fill.py`, all test-only.
2. **The Kingambit failure was narrower and more concrete than the prior report states.** The incorrect and corrected contexts differed in exactly one field:
   - incorrect: `setup_dependent=True`;
   - corrected: `setup_dependent=False`.
   `match_status="partial"`, `primary_function="offense"`, and `tankiness="tanky"` did not change.
3. **The correction came from the actual usage moveset, not the role label.** Black Glasses Kingambit used Sucker Punch / Kowtow Cleave / Protect / Iron Head, with no setup move. The role-play therefore removed Fake Out and Taunt needs while preserving healing, screens, and optional Trick Room.
4. **The transcript contradicts a literal reading of the proposed chain.** Current `_pick_role` decides the role for the open slot. `RoleShapeContext` describes the existing anchor passed as `pokemon` to `query_support_needs`. An open-slot role cannot by itself describe the anchor.
5. **The target role was decided after support discovery in Scenario 1.** The actual sequence was:
   `classify Kingambit -> derive support needs -> user chooses Trick Room -> resolve target role trick_room_setter`.
   The user's later `trick_room_sweeper` label for Kingambit did not produce the corrected context.
6. **Role identity alone is insufficient.** A strategic `trick_room_sweeper` can be condition-dependent without requiring its own setup turn. Mapping that name directly to `setup_dependent=True` recreates the observed bug.
7. **No-anchor state should not produce a RoleShapeContext.** The real empty-team execution passed `match_status="none"` with no species, and all anchor-dependent queries correctly returned empty. Bootstrap used `query_by_usage` instead.
8. **The current struct mixes three concerns:**
   - routing (`match_status`);
   - role-shape judgments (`primary_function`, `tankiness`, `setup_dependent`);
   - unused provenance (`archetype_id`, `partial_signals`).
9. **Two fields are currently inert.** `archetype_id` and `partial_signals` are never populated by any repository constructor and are never read by `query_support_needs`.
10. **`match_status="none"` and `"partial"` are behaviorally identical inside the function.** Only `"clean"` has special behavior, returning immediately.
11. **Build resolution should be separate from shape judgment.** `query_support_needs` already derives ability, moves, stats, priority, healing, field dependence, and speed internally. The orchestrator should provide one resolved anchor build plus only the genuinely interpretive role-shape judgments.

## Current source contract

`RoleShapeContext` is a frozen dataclass in `recommender/support_needs.py`:

```python
@dataclass(frozen=True)
class RoleShapeContext:
    match_status: MatchStatus
    primary_function: PrimaryFunction = "unknown"
    tankiness: Tankiness = "unknown"
    setup_dependent: bool = False
    archetype_id: str | None = None
    partial_signals: tuple[str, ...] = ()
```

Literal domains:

- `MatchStatus = Literal["clean", "partial", "none"]`
- `PrimaryFunction = Literal["offense", "support", "unknown"]`
- `Tankiness = Literal["tanky", "glass", "unknown"]`

### What `query_support_needs` actually reads

Only four fields affect behavior:

1. `match_status`
   - `"clean"` returns `[]` immediately;
   - `"partial"` and `"none"` continue through exactly the same logic.
2. `primary_function`
   - `"offense"` adds generic healing and screens;
   - it enables speed-axis needs;
   - `"support"` can still participate in defensive asymmetry;
   - `"unknown"` suppresses offense-specific needs.
3. `tankiness`
   - `"tanky"` enables defensive-asymmetry checks;
   - `"tanky"` plus no self-heal enriches/adds healing;
   - `"glass"` plus offense enables Fake Out/redirection protection.
4. `setup_dependent`
   - `True` adds Fake Out protection;
   - `True` adds Taunt disruption.

The function does not read:

- `archetype_id`;
- `partial_signals`.

### What comes from the anchor build instead

`query_support_needs` does not expect the context to contain all mechanics. It separately resolves:

- species;
- ability;
- moves;
- base stats;
- offensive priority;
- self-healing moves;
- ability-derived weather/terrain dependence;
- whether the team already provides that field condition;
- speed tier relative to relevant threats.

Current kit precedence inside `_resolve_kit` is:

1. an explicitly present `ability` or `moves` key, including explicit `None`/empty values;
2. `featured_or_common_set`;
3. the first legality ability for ability only;
4. empty moves if usage has none.

This distinction matters: role shape should not duplicate facts already available from the resolved build.

## Complete repository construction-site inventory

Repository search found no production call. Every constructor is in one of two test files.

### `tests/recommender/test_query_support_needs.py`: 30 constructors

Each entry below lists every non-default value. Omitted fields use:

- `primary_function="unknown"`;
- `tankiness="unknown"`;
- `setup_dependent=False`;
- `archetype_id=None`;
- `partial_signals=()`.

1. `test_clean_match_returns_empty`
   - `clean`, offense, tanky, setup `True`.
2. `test_archaludon_offense_tank_coverage_and_healing`
   - `partial`, offense, tanky.
3. `test_attacker_universal_screens_and_healing`
   - `partial`, offense, glass.
4. `test_tailwind_support_no_screens_or_healing`
   - `partial`, support, unknown tankiness.
5. `test_support_tank_asymmetry_no_screens`
   - `partial`, support, tanky.
6. `test_glass_gate_no_defensive_coverage`
   - `partial`, offense, glass.
7. `test_setup_dependent_fake_out_and_taunt`
   - `partial`, support, unknown tankiness, setup `True`.
8. `test_setup_offense_kingambit_still_fake_out`
   - `partial`, offense, tanky, setup `True`.
9. `test_glass_offense_fake_out_not_setup`
   - `partial`, offense, glass, explicit setup `False`.
10. `test_tanky_offense_no_fake_out_without_setup`
    - `partial`, offense, tanky, explicit setup `False`.
11. `test_contrary_stat_lowering_partner`
    - `partial`, offense, unknown tankiness.
12. `test_inconclusive_no_attacker_universals`
    - `partial`, unknown function and tankiness.
13. `test_speed_boost_layer1_no_speed_needs`
    - `partial`, offense, glass.
14. `test_unburden_layer1_no_speed_needs`
    - `partial`, offense, glass.
15. `test_quick_feet_layer1_no_speed_needs`
    - `partial`, offense, glass.
16. `test_swift_swim_no_rain_needs_condition_setter`
    - `partial`, offense, glass.
17. `test_swift_swim_rain_locked_no_speed_need`
    - `partial`, offense, glass.
18. `test_chlorophyll_desolate_land_clears_condition_setter`
    - `partial`, offense, glass.
19. `test_swift_swim_primordial_sea_clears_condition_setter`
    - `partial`, offense, glass.
20. `test_sand_force_needs_condition_setter`
    - `partial`, offense, glass.
21. `test_sand_force_sand_locked_clears_condition_setter`
    - `partial`, offense, glass.
22. `test_dry_skin_needs_rain_only`
    - `partial`, offense, glass.
23. `test_forecast_multi_condition_and_any_secures`, first call
    - `partial`, offense, glass.
24. `test_forecast_multi_condition_and_any_secures`, secured-team call
    - `partial`, offense, glass.
25. `test_mimicry_multi_terrain_emit_and_secure`, first call
    - `partial`, offense, glass.
26. `test_mimicry_multi_terrain_emit_and_secure`, secured-team call
    - `partial`, offense, glass.
27. `test_protosynthesis_needs_sun_setter`
    - `partial`, offense, glass.
28. `test_tank_with_only_life_dew_still_wants_healing_cleric`
    - `partial`, offense, tanky.
29. `test_layer3_smoke_slow_attacker_emits_speed_control`
    - `partial`, offense, tanky.
30. `test_no_ranking_or_resolution_fields`
    - `partial`, offense, tanky.

What these sites establish:

- `"clean"` is tested once.
- `"partial"` is used in every other test.
- `"none"` is never tested.
- `archetype_id` is never supplied.
- `partial_signals` is never supplied.
- Most tests hand-author values specifically to activate one branch; they do not demonstrate derivation.
- The repeated offense/glass context is fixture-like input for ability/field tests, not independent evidence that those Pokémon were classified correctly.

### `tests/recommender/test_slot_fill.py`: 12 constructors

1. `test_farigiraf_multi_branch_annotates_and_is_default`
   - `partial`, offense.
2. `test_single_branch_no_false_positive_overlap`
   - `partial` only.
3. `test_merge_need_resolved_surfaces_need_only_species`
   - `partial` only.
4. `test_terminal_e2e_lock_then_refinement_handoff`
   - `partial` only.
5. `test_deferral_discardable_reenterable`, original context
   - `partial` only.
6. `test_deferral_discardable_reenterable`, re-entered context
   - `partial` only.
7. `test_present_only_persists_ordered_options_with_sources`
   - `partial` only.
8. `test_present_only_rejects_empty_presentation`
   - `partial` only.
9. `test_accept_with_empty_pool_raises`
   - `partial` only.
10. `test_contrary_need_does_not_match_intimidate`
    - `partial` only.
11. `test_fake_out_need_matches_armor_tail_ability`
    - `partial` only.
12. `test_resolve_all_and_merge_without_chosen_need`
    - `partial` only.

What these sites establish:

- Eleven of twelve use only the required `match_status`.
- These contexts are plumbing placeholders. The tests exercise `SlotFillContext` annotation, merge, presentation, locking, and resolution rather than shape classification.
- They provide no evidence for how production values should be derived.

## Real-execution construction sites from the role-play

The transcript contains four materially distinct uses:

1. Incorrect Kingambit:
   - `partial`, offense, tanky, setup `True`.
2. Corrected Kingambit:
   - `partial`, offense, tanky, setup `False`.
3. Empty team:
   - `none`, all other fields defaulted.
4. Archaludon:
   - `partial`, offense, tanky, setup `False`.

Only the Kingambit pair isolates a causal field correction.

## Exact Kingambit reconstruction

### First execution: incorrect

The anchor passed to `query_support_needs` was only:

```python
{"species": "Kingambit"}
```

The manually guessed context was:

```python
RoleShapeContext(
    match_status="partial",
    primary_function="offense",
    tankiness="tanky",
    setup_dependent=True,
)
```

Because only species was passed, `_resolve_kit` internally loaded the representative usage build:

- Kingambit @ Black Glasses;
- Defiant;
- Adamant;
- 32 HP / 32 Atk / 2 SpD;
- Sucker Punch / Kowtow Cleave / Protect / Iron Head.

The real output was:

1. Fake Out protection — trigger `setup_dependent:fake_out`;
2. Taunt disruption — trigger `setup_dependent:taunt`;
3. Healing/cleric — trigger `tank_no_self_heal`;
4. Screens;
5. Trick Room — stance `want`, trigger `speed_tier:low_with_priority`.

### Evidence check between executions

The transcript then called `featured_or_common_set("Kingambit")` explicitly and inspected the build. It found no setup move.

Important distinctions:

- the usage build did support offense-primary;
- the 32 HP usage spread and durable species shape were treated as support for tanky;
- the actual kit contradicted `setup_dependent=True`;
- Sucker Punch remained evidence for offensive priority;
- low Speed remained evidence for Trick Room;
- no role classifier or function rebuilt the context automatically.

### Second execution: corrected

The corrected context was:

```python
RoleShapeContext(
    match_status="partial",
    primary_function="offense",
    tankiness="tanky",
    setup_dependent=False,
)
```

Again, `query_support_needs` received only `{"species": "Kingambit"}` and loaded usage internally.

The corrected output was:

1. Healing/cleric — `tank_no_self_heal`;
2. Screens;
3. Trick Room — `want`, `speed_tier:low_with_priority`.

Exactly two false options disappeared:

- Fake Out protection;
- Taunt disruption.

### What did not cause the correction

The user later supplied:

`anchor role = trick_room_sweeper`

That happened after the corrected support-needs call. It established the semantic mapping:

`trick_room_sweeper -> trick_room need -> trick_room_setter target`

It did not establish that Kingambit itself uses an interruptible setup move. Treating `trick_room_sweeper` as setup-dependent would conflate:

- dependence on a teammate-provided field/speed condition;
- dependence on the anchor spending its own turn setting up.

The transcript supports only the second meaning for the current `setup_dependent` gates.

### Additional contradiction exposed by current code

Running `infer_role` on the actual Black Glasses set returns `bulky_attacker`, not `trick_room_sweeper`.

Therefore three role concepts were simultaneously present:

1. usage-kit inference: `bulky_attacker`;
2. user strategic identity: `trick_room_sweeper`;
3. requested partner role: `trick_room_setter`.

They are not interchangeable, and a single unqualified “decided role” is insufficient input.

## Semantic mismatch in the proposed pipeline

### Current `_pick_role` semantics

Current `_pick_role` runs while filling an open slot. It chooses a role value to assign to that slot before species refinement.

Examples:

- `TrickRoom` archetype component -> open slot role `trick_room_sweeper`;
- `Tailwind` -> `support_speed_control`;
- unresolved coverage gap -> `bulky_attacker`.

### Current `RoleShapeContext` semantics

`query_support_needs(pokemon, role_shape_context, ...)` interprets the context as the role shape of `pokemon`, the existing anchor whose teammate needs are being surfaced.

`SlotFillContext` likewise stores:

- `anchor`;
- `role_shape_context`;
- the resulting threat/support candidate evidence.

### Consequence

If `_pick_role` returns the target role for an empty slot, that value cannot directly construct the existing anchor's RoleShapeContext.

The actual Kingambit sequence confirms the reverse dependency:

1. classify the anchor;
2. derive the anchor's residual support needs;
3. choose one need;
4. map that need to a target partner role;
5. find species for that target role.

### Proposal: resolve the overloaded term “role decision”

This is a proposal, not a decision.

Use two explicit concepts:

1. `AnchorRoleDecision`
   - describes the existing anchor's strategic function and classification quality;
   - can produce `RoleShapeContext`.
2. `TargetRoleDecision`
   - describes what the open slot should provide;
   - constrains candidate generation;
   - must be preserved through `SlotFillContext` and provisional refinement.

If the redesigned `_pick_role` produces `TargetRoleDecision`, the proposed chain should be:

`anchor classification -> RoleShapeContext -> support needs -> TargetRoleDecision -> SlotFillContext candidate resolution`

If it instead produces `AnchorRoleDecision`, its name and call site should make that semantic change explicit because that is not current `_pick_role` behavior.

## Proposal: derivation procedure

This is a proposal, not a decision.

The conceptual operation should be:

`derive_role_shape_context(anchor, anchor_role_decision, state)`

It should not accept only a target/open-slot role.

### Step 0: require a real anchor

1. Identify the anchor whose teammate needs are being queried.
2. If no anchor species exists:
   - do not fabricate `RoleShapeContext(match_status="none")`;
   - skip `query_counters`, `query_threat_counters`, and `query_support_needs`;
   - route empty-team bootstrap through direction/ownership input, Role Compendium, and/or `query_by_usage`.

This matches the real empty-team execution: all anchor-dependent tools returned nothing.

### Step 1: resolve one anchor build

Construct one explicit `PokemonSpecOptional` before deriving shape.

Source precedence:

1. user-confirmed or locked slot attributes;
2. complete provisional build for that anchor;
3. role-compatible usage build;
4. generic representative usage build;
5. synthesized complete build;
6. species-only evidence.

Rules:

- explicit user-confirmed fields override usage;
- usage fills only missing fields;
- do not merge unrelated top moves, item, and spread variants as though they co-occurred;
- record the source of each resolved field;
- do not silently choose the first legal ability when several are possible;
- if the build remains incomplete, preserve unknowns rather than inventing them.

Current state limitation:

- `Slot` cannot store ability, so a locked team member may still lose a user-selected ability before this step.

### Step 2: validate role semantics against the resolved build

Compare `AnchorRoleDecision` with the actual resolved kit.

Classify the relationship:

- `clean`: role and execution mechanism are directly supported by the build/compendium profile;
- `partial`: strategic role is decided, but the build only supports part of its execution/profile or raw residual needs remain useful;
- `none`: no reliable anchor-role classification exists.

Do not derive this only from the role string.

Examples:

- Kingambit strategic Trick Room sweeper + non-setup Black Glasses kit:
  - offense is supported;
  - setup-turn dependence is not supported;
  - condition dependence may be supported by strategy;
  - the overall match is partial.
- Usage-backed Swords Dance attacker with Swords Dance present:
  - setup-turn dependence is supported.
- Usage-backed automatic weather setter:
  - support role may be clean;
  - automatic weather does not imply setup-turn dependence.

### Step 3: derive `primary_function`

Source:

1. explicit primary-function metadata on `AnchorRoleDecision`;
2. role/archetype classifier judgment with evidence;
3. `unknown` if unresolved.

Do not infer it from attacking-move count. ADR-022 already records Farigiraf as the counterexample: several attacking moves can coexist with a support-primary role.

Expected role metadata examples:

- fast/bulky/setup attacker -> offense;
- Trick Room setter, weather setter, redirection -> support;
- pivot roles require explicit metadata because “pivot” does not determine whether offense or support is primary;
- hybrid roles need one declared primary or an expanded field domain.

### Step 4: derive `tankiness`

Source:

1. durability intent carried by the anchor-role classification;
2. resolved spread/nature/item and species stats as evidence;
3. matchup survivability evidence when already available;
4. `unknown` when only a role name or species is known.

Do not use base stats alone. ADR-022 records that fixed mechanical tankiness rules failed on ordinary counterexamples.

Do not map every attacker to glass or every pivot to tanky.

Kingambit evidence:

- top usage spread invests 32 HP;
- Speed investment is zero;
- its strategic role expects it to absorb pressure while attacking;
- `tanky` was retained across both transcript executions.

### Step 5: derive `setup_dependent`

Define the field narrowly:

> Does this anchor's assigned function require it to complete an exposed, interruptible setup action before its payoff?

Source:

1. actual moves in the resolved build;
2. ability/item sequencing if it creates an equivalent interruptible setup turn;
3. explicit mechanism metadata from a synthesized/compendium role;
4. otherwise `False`.

Positive examples:

- Swords Dance, Nasty Plot, Calm Mind, Bulk Up attacker;
- manual Trick Room setter;
- another role whose payoff requires first completing a status/setup action.

Negative examples:

- Kingambit merely benefiting from teammate-set Trick Room;
- Swift Swim attacker benefiting from teammate-set Rain;
- automatic Drizzle/Snow Warning setter;
- low-Speed attacker with priority;
- a role name containing “sweeper” without a setup move.

If the strategic role expects setup but the resolved build lacks the setup mechanism:

- keep `setup_dependent=False` for current-kit support-needs behavior;
- mark the role/build relationship `partial` or conflicting;
- preserve that conflict in provenance.

This rule directly prevents the observed false Fake Out/Taunt outputs.

### Step 6: handle `match_status`

Under the current struct:

- `clean` should mean the upstream role/archetype profile fully answers support-profile discovery, so the support tool returns no raw needs;
- `partial` should mean the context contains usable shape judgments but raw support-needs analysis is still required;
- `none` should mean no role classification exists, not “there is no anchor.”

However, the orchestrator should normally decide whether to call the raw tool before entering it. That makes `match_status` routing metadata rather than role shape.

### Step 7: handle `archetype_id` and `partial_signals`

If retained:

- `archetype_id` comes directly from the canonical anchor role/archetype decision;
- `partial_signals` comes from the classifier's evidence, not an independently reconstructed string list.

Possible Kingambit signals:

- `usage_primary:offense`;
- `usage_bulk:32_hp`;
- `usage_priority:sucker_punch`;
- `usage_setup:none`;
- `strategy_condition:trick_room`.

But these should be structured evidence with provenance, not untyped strings.

Because neither field is consumed today, the minimal safe choice is to keep this evidence on `AnchorRoleDecision` and pass only the active shape fields into `query_support_needs`.

### Step 8: call `query_support_needs` with both products

Pass:

1. the resolved anchor build as `pokemon`;
2. the derived interpretive context;
3. the current `team_draft`;
4. the current full state/regulation.

This keeps responsibilities separate:

- build mechanics come from the resolved build;
- role interpretation comes from `RoleShapeContext`;
- teammate satisfaction comes from team state.

### Step 9: preserve target-role provenance separately

When a support need becomes a target role:

- `trick_room` need -> `trick_room_setter` target role;
- that target role belongs in `SlotFillContext` or its successor;
- it must survive candidate presentation, provisional refinement, and atomic lock.

Do not attempt to store this target role in the anchor's `RoleShapeContext`.

## Missing-source behavior

### Anchor has a complete confirmed build

- Use it directly.
- Fill only attributes the state truly lacks.
- Derive execution-sensitive fields from that exact kit.

### Anchor has species plus representative usage

- Use the representative build provisionally.
- Record that it is usage-derived, not user-confirmed.
- If the decided strategic role conflicts with usage, use:
  - strategic role for intended primary function;
  - actual kit for setup/condition execution;
  - `partial` match plus explicit conflict evidence.

### Anchor has multiple role-distinct usage variants

- Select a role-compatible variant before deriving shape.
- Do not always use generic top-1 if it represents a different role.
- If no variant can be linked to the decided role, keep the ambiguity explicit.

### Anchor has no usage but has a synthesized full build

- Use the synthesized build.
- Mark every derived field as synthesized/mechanical rather than usage-backed.
- Setup dependence can be true only when the synthesized mechanism actually contains setup.

### Anchor has species and role only

- Derive only fields guaranteed by role metadata.
- Use `unknown` for tankiness or primary function when the role does not define them.
- Keep setup `False` unless the role contract guarantees an interruptible setup mechanism.
- Avoid letting a first-legal-ability fallback masquerade as the anchor's actual ability.
- Suppress needs that depend on unresolved kit facts, or label them provisional.

### No anchor / empty team

- Do not construct context.
- Do not call anchor-dependent ADR-022 tools.
- Use bootstrap direction/ownership/usage/role candidate mechanisms.

### Clean role/archetype match

- The orchestrator can skip raw `query_support_needs`.
- It may still construct a context for diagnostics, but the current tool returns no needs.
- Threat analysis is a separate branch and need not be skipped merely because support profile is clean.

## Struct review

### `match_status`: routing field, not shape field

Evidence:

- only `"clean"` changes behavior;
- `"partial"` and `"none"` are identical inside the tool;
- `"none"` has no repository test;
- no-anchor should skip construction entirely.

Proposal:

- move classification status to `AnchorRoleDecision`/orchestration;
- call `query_support_needs` only when raw reasoning is warranted;
- remove it from the eventual minimal shape struct, or define and test all three states.

### `primary_function`: useful but underspecified

Evidence:

- it controls broad offense-universal needs;
- ADR-022 explicitly rejects move-count inference;
- hybrid Pokémon still need a declared primary.

Proposal:

- retain it only if every redesigned role carries explicit primary-function metadata;
- otherwise add a deliberate hybrid/ambiguous representation rather than guessing.

### `tankiness`: useful but too coarse and source-ambiguous

Evidence:

- it controls defensive coverage, enriched healing, and glass-offense Fake Out protection;
- no production classifier exists;
- fixed mechanical derivation was already rejected in ADR-022.

Proposal:

- define it as role/build durability intent, not base-stat tier;
- consider adding a neutral/balanced value;
- preserve per-field evidence/confidence.

### `setup_dependent`: necessary trigger, misleading name

Evidence:

- one wrong Boolean created two false support needs;
- “Trick Room sweeper” condition dependence was easy to confuse with own-turn setup;
- tests use the field for both support setup and offensive setup.

Proposal:

- rename to `requires_setup_turn` or similarly execution-specific wording;
- derive from the actual role mechanism and resolved kit;
- model field-condition dependence separately.

### `archetype_id`: currently unnecessary in this struct

Evidence:

- zero repository constructors populate it;
- zero consumer reads it.

Proposal:

- move canonical role identity to `AnchorRoleDecision`;
- retain here only if a concrete consumer is designed.

### `partial_signals`: currently unnecessary and weakly typed

Evidence:

- zero constructors populate it;
- zero consumer reads it;
- free-form strings cannot safely drive behavior.

Proposal:

- replace with structured evidence/provenance on the role decision;
- do not add behavior that parses prose-like signal strings.

## Missing concepts exposed by transcript/source evidence

### Anchor role versus target role

The current structures do not cleanly preserve both. This is the primary missing concept.

Needed distinction:

- anchor role informs support-needs interpretation;
- target role constrains species search and must survive refinement.

### Condition dependence versus setup-turn dependence

Kingambit exposed the distinction:

- it may want Trick Room;
- it does not spend a turn setting Trick Room itself;
- therefore it is condition-dependent but not setup-turn-dependent.

A separate mechanic/profile value is needed if condition dependence must inform orchestration.

### Per-field provenance/confidence

The transcript manually retained three judgments and corrected one. The current dataclass cannot state:

- offense came from role semantics;
- tanky came from role judgment plus usage spread;
- setup false came from exact usage moves;
- strategic Trick Room identity came from the user.

Without provenance, a later caller cannot distinguish evidence from default.

### Resolved anchor build

The context alone is not enough. The derivation result should pair role shape with the exact build used to justify it.

### Real Speed inputs

Current speed analysis computes anchor Speed with zero Speed investment and Hardy nature rather than using the resolved usage spread/nature. That happened to be close for the top Kingambit set but is not generally correct.

Proposal:

- use the resolved anchor build's nature and spread in speed analysis;
- do not add duplicate speed fields to RoleShapeContext unless the build cannot be passed through.

### Ability persistence

`Slot` has no ability field. A user-confirmed ability can therefore be absent when the anchor build is reconstructed.

This is not a RoleShapeContext field, but it blocks reliable derivation.

### Move-derived field requirements

The Archaludon execution used the same context shape but missed Rain because field dependence is derived only from abilities. Electro Shot's Rain interaction had no representation.

Proposal:

- extend resolved-kit mechanics to include move-derived conditions;
- do not overload `setup_dependent` to represent them.

## Proposal: minimal conceptual module boundaries

This is a proposal, not a decision.

1. `resolve_anchor_build(anchor_slot, state) -> ResolvedAnchorBuild`
   - resolves exact fields and per-field sources.
2. `classify_anchor_role(anchor, decided_anchor_role, resolved_build) -> AnchorRoleDecision`
   - produces role identity, match quality, primary function, durability intent, mechanism evidence, and conflicts.
3. `derive_role_shape_context(role_decision, resolved_build) -> RoleShapeContext`
   - performs a narrow, auditable projection into the fields actually consumed by support-needs reasoning.
4. `derive_target_role(chosen_need, role_mapping) -> TargetRoleDecision`
   - maps a selected support need to the role the open slot must provide.

The orchestrator sequence for an anchored slot becomes:

`resolve anchor build -> classify anchor role -> derive shape -> query support needs -> choose/merge need -> derive target role -> discover species`

The empty-team sequence bypasses the first four anchor-specific operations.

## Proposed acceptance checks for a future implementation

1. Repository has one production construction path rather than ad hoc callers.
2. Black Glasses Kingambit produces:
   - partial;
   - offense;
   - tanky;
   - setup-turn dependence false.
3. The Kingambit result excludes Fake Out and Taunt needs.
4. Sucker Punch still produces optional, not required, Trick Room.
5. User-stated `trick_room_sweeper` does not automatically set setup-turn dependence true.
6. A usage-backed Swords Dance build does set setup-turn dependence true.
7. An automatic weather setter does not set setup-turn dependence true.
8. No-anchor state bypasses RoleShapeContext and returns to bootstrap.
9. Explicit locked build fields override usage.
10. Role-conflicting usage produces a partial match and recorded conflict.
11. No-usage species does not receive guessed tankiness or setup dependence.
12. Clean role match skips raw support-needs analysis.
13. `"none"` has a defined, tested meaning or is removed.
14. `archetype_id` and `partial_signals` gain consumers or are moved/removed.
15. Anchor and target roles remain distinct through candidate selection.
16. Speed analysis uses the resolved spread/nature.
17. Ambiguous ability does not silently become the first legal ability.
18. Move-derived requirements such as Electro Shot -> Rain survive kit analysis.
19. Every derived judgment exposes source/confidence.

## Suggested review decisions before implementation

1. Does redesigned `_pick_role` decide an anchor role or an open-slot target role?
2. Should `match_status` remain inside RoleShapeContext or become orchestrator routing state?
3. Should `setup_dependent` be renamed to `requires_setup_turn`?
4. Is `tankiness` allowed to remain open-ended judgment, and does it need a balanced value?
5. Should `archetype_id` and `partial_signals` move into a structured `RoleDecision`?
6. What object preserves `TargetRoleDecision` through `SlotFillContext` and refinement?
7. What is the canonical resolved-build source when usage has multiple role-distinct variants?

## Final handoff

The missing link is not a one-line role-to-context mapping.

The primary transcript shows that a strategic role label and the anchor's execution shape are separate:

- Kingambit can be designated a Trick Room sweeper;
- its real Black Glasses kit is offense-primary and tanky;
- it has priority and benefits from Trick Room;
- it does not require its own setup turn.

The safe design is therefore:

1. resolve the actual anchor build;
2. classify the anchor role against that build;
3. project only evidence-backed interpretive fields into RoleShapeContext;
4. keep the open-slot target role separate;
5. skip the entire anchor-context path when no anchor exists.

No derivation function should be implemented until the anchor-role versus target-role ambiguity is resolved.
