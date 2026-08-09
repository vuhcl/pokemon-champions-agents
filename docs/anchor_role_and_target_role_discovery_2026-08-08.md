# Anchor-Role Classification, RoleShapeContext Projection, and Target-Role Preservation

**Date:** 2026-08-08  
**Audience:** Vu / next design-review session  
**Status:** Discovery/proposal record only. No derivation function was implemented. Every statement is labeled **Verified finding**, **Proposal**, or **Vu decision required**.

## Purpose and method

This report resolves the five design questions left open by:

- `docs/slot_fill_flow_discovery_2026-08-08.md`;
- `docs/role_shape_context_derivation_discovery_2026-08-08.md`;
- the paused `_pick_role` redesign and corrected phase-routing entries in `docs/master_project_log.md`;
- the original role-play transcript.

The settled scope was not reconsidered:

- `_pick_role` or its redesigned successor produces a `TargetRoleDecision` for the open slot.
- `classify_anchor_role` is a new producer of `AnchorRoleDecision` for an existing anchor.
- The verified Kingambit correction changed only `setup_dependent=True` to `False`.

Direct checks performed for this report:

1. Re-read both prior reports.
2. Re-read the current tail of `master_project_log.md`.
3. Read the current source contracts and all consumers for:
   - `RoleShapeContext`;
   - `SlotFillContext`;
   - `PendingPresentation`;
   - `Slot`;
   - `LockPayload`;
   - `infer_role`;
   - usage and resolved-build lookup.
4. Re-ran current usage/build and `infer_role` calls for Kingambit, Archaludon, and Pelipper.
5. Re-checked Role Compendium records for those species.
6. Re-ran `query_support_needs` with comparable Archaludon and Pelipper contexts.
7. Re-read the relevant Kingambit, Archaludon, and Pelipper transcript events.

### Source-state note

**Verified finding — `docs/master_project_log.md:1968-2136`:** the current file contains the paused `_pick_role` entry and corrected phase-routing entry. It does not yet contain a third entry recording the later confirmation that `RoleShapeContext` describes the anchor while `_pick_role` describes the target. That confirmation is present in the current RoleShapeContext report and the role-play transcript, but not in the project log at the time of this read.

## Executive findings

1. **Verified finding:** `infer_role` is a five-value kit heuristic driven only by Trick Room, Tailwind, Choice Scarf, and a few item groups (`recommender/recommend.py:21-57`). **Proposal:** treat it as evidence for a build's coarse shape, not as a strategic anchor-role classifier.
2. **Verified finding:** Kingambit is an Excellent Swords Dance Attacker in the compendium, but its representative Black Glasses build contains no Swords Dance (`data/roles/swords_dance_attacker.v1.json:674-712` plus direct `featured_or_common_set` execution). **Proposal:** species-level membership is not proof that the resolved build performs that role.
3. **Proposal:** `AnchorRoleDecision` should preserve one strategic role identity while retaining kit inference, compendium matches, mechanisms, conflicts, and provenance as separate evidence.
4. **Proposal, validated against direct Archaludon query output:** classification quality and support-query routing are not the same field. A build can cleanly support the proposed bulky Rain attacker identity while raw support analysis still returns useful needs.
5. **Proposal:** move role/build match quality to `AnchorRoleDecision`. Remove `match_status` from the eventual minimal `RoleShapeContext`; until migration, pass `"partial"` whenever raw support analysis is intentionally being run.
6. **Proposal:** rename `setup_dependent` to `requires_setup_turn` and derive it only from required execution mechanisms, not from role names, condition dependence, alternate compendium membership, or any setup-like move anywhere in the set.
7. **Verified finding:** `Slot` and `LockPayload` have no ability field. Existing code can silently refill ability from usage, but it cannot prove that this is the user's confirmed ability (`recommender/state.py:93-100,163-170`; `recommender/coverage.py:213-240`).
8. **Proposal:** ability persistence is a hard dependency for an authoritative complete-build path. Classification may degrade gracefully when ability is unknown, but it must not make ability-dependent role claims.
9. **Verified finding:** target-role intent is currently lost before refinement. `SlotFillContext` stores a chosen support need, pending options store only species/source, `classify_pending` emits a species-only lock, and the Kingambit/Farigiraf execution left the target slot's role `None`.
10. **Proposal:** the same immutable `TargetRoleDecision` should travel through candidate evidence, a cross-turn pending slot intent, provisional build, confirmation, and the atomic role+build lock.

## Sub-task 1: `classify_anchor_role` and `AnchorRoleDecision`

### What exists today

**Verified finding — `recommender/recommend.py:21-57`:**

- `infer_role` can return only:
  - `fast_attacker`;
  - `bulky_attacker`;
  - `bulky_pivot`;
  - `trick_room_sweeper`;
  - `support_speed_control`.
- A Trick Room move wins first.
- Tailwind becomes `support_speed_control`.
- Leftovers, Sitrus Berry, or Rocky Helmet becomes `bulky_pivot`.
- Life Orb, Choice Band, or Choice Specs becomes `fast_attacker`.
- Everything else becomes `bulky_attacker`.

**Verified finding:** it does not inspect ability, spread, attacking category, pivot moves, setup moves other than Trick Room, field-condition dependence, user strategy, or compendium evidence.

**Verified finding — direct execution:**

- Black Glasses Kingambit -> `bulky_attacker`.
- Leftovers Archaludon -> `bulky_pivot`, despite no pivot move.
- Tailwind Pelipper -> `support_speed_control`.

### Proposed inputs

**Proposal:** the conceptual signature should be:

`classify_anchor_role(resolved_build, *, user_role, inferred_kit_role, compendium_profiles, team_context) -> AnchorRoleDecision`

Required inputs:

1. `resolved_build: ResolvedAnchorBuild`
   - Exact species/form, ability, item, nature, spread, and moves where known.
   - Per-field provenance and unresolved fields.
2. `user_role: StrategicRoleStatement | None`
   - The user's explicit strategic identity.
   - A locked slot role with `ReasonRef(kind="user_stated")` is equivalent evidence.
3. `inferred_kit_role: RoleArchetype | None`
   - Current `infer_role` output.
   - Preserved as coarse kit evidence, never silently promoted to strategic truth.
4. `compendium_profiles: tuple[CompendiumRoleMatch, ...]`
   - Positive profiles and relevant rejection/conflict evidence.
   - Must distinguish species membership from exact-build mechanism support.
5. `team_context`
   - Only facts required to interpret mechanisms, such as a user-declared Rain or Trick Room mode.
   - It must not contain the open slot's `TargetRoleDecision`.

### Proposed output

**Proposal:** `AnchorRoleDecision` should contain at least:

1. `role_id`
   - Canonical strategic role identity for the anchor.
   - Example: `trick_room_sweeper`, `bulky_rain_attacker`, `rain_setter`.
2. `secondary_role_ids`
   - Additional strategic functions that must not be flattened into the primary identity.
   - Example: Pelipper primary Rain setter plus secondary Tailwind speed control.
3. `match_quality`
   - `clean`, `partial`, or `none` for role-to-resolved-build agreement.
   - This is diagnostic classification quality, not permission to skip support analysis.
4. `primary_function`
   - `offense`, `support`, or `unknown`.
5. `durability_intent`
   - At least `tanky`, `glass`, `balanced`, or `unknown`.
   - The later RoleShapeContext projection may remain narrower.
6. `mechanisms`
   - Structured execution evidence.
7. `kit_role`
   - The current `infer_role` result and its provenance.
8. `compendium_matches`
   - Profiles linked to the exact build separately from species-only alternatives.
9. `conflicts`
   - Examples: strategic setup role but no setup move; inferred pivot but no pivot mechanism.
10. `evidence`
   - Per-claim source and confidence, not free-form strings.

### Proposed mechanism evidence

**Proposal:** each mechanism should state:

- the mechanic, such as `Sucker Punch`, `Drizzle`, `Tailwind`, `Electro Shot`, or `Swords Dance`;
- its kind, such as offense, self-setup, automatic condition setting, manual condition setting, teammate-condition benefit, reactive durability, or pivot;
- its directional relation: `provides`, `benefits_from`, `executes`, or `mitigates`;
- whether it is required for the chosen strategic role or merely secondary;
- activation mode: automatic, passive/reactive, or move;
- whether an opponent can interrupt the activation turn;
- whether the anchor supplies the condition itself or expects a teammate;
- whether it is present in the resolved build;
- evidence source and confidence.

This is the minimum structure needed to derive an execution-specific setup Boolean without guessing from a role name.

### Proposed classification procedure

**Proposal:**

1. Normalize the explicit strategic role, if one exists.
2. Extract mechanisms from the resolved build.
3. Run `infer_role` and retain its output as kit evidence.
4. Load compendium profiles, but split them into:
   - exact-build-supported matches;
   - species-level alternate-role evidence;
   - rejected/conflicting profiles.
5. Choose role identity in this precedence:
   - explicit user/confirmed strategic role;
   - exact-build-supported compendium role;
   - mechanic-backed classifier result;
   - coarse `infer_role` fallback;
   - unresolved.
6. Derive primary function from the chosen role plus required mechanisms.
7. Derive durability intent from strategic intent and resolved build evidence together.
8. Compare the chosen role with the exact build:
   - `clean`: required mechanisms and function are supported;
   - `partial`: identity is usable, but a required/expected mechanism is missing, ambiguous, or only weakly supported;
   - `none`: no defensible identity can be established.
9. Preserve disagreements instead of forcing all evidence into one role string.

### Kingambit validation

**Verified finding — transcript lines/events 5-16 and direct source/data execution:**

- Resolved representative build:
  - Kingambit @ Black Glasses;
  - Defiant;
  - Adamant;
  - 32 HP / 32 Atk / 2 SpD;
  - Sucker Punch / Kowtow Cleave / Protect / Iron Head.
- `infer_role` returns `bulky_attacker`.
- The user later supplied strategic role `trick_room_sweeper`.
- The selected need produced open-slot target role `trick_room_setter`.
- The active build has no self-setup move.
- The Swords Dance Attacker compendium lists Kingambit as Excellent, but that is an alternate role profile for this species, not the active resolved set.

**Proposal — resulting `AnchorRoleDecision`:**

- `role_id = "trick_room_sweeper"`;
- `match_quality = "partial"` because the user strategy is usable and low-Speed offense fits it, but the representative kit alone does not establish the strategic label;
- `primary_function = "offense"`;
- `durability_intent = "tanky"`;
- `kit_role = "bulky_attacker"`;
- required/active mechanisms:
  - low-Speed offense;
  - Sucker Punch priority;
  - benefits from teammate-provided Trick Room;
  - no required self-setup turn;
- alternate species profile:
  - Swords Dance Attacker, not active for this build;
- conflict/evidence note:
  - strategic condition dependence must not become own-turn setup dependence.

**Verified finding:** `trick_room_setter` does not belong anywhere in this decision. It is the partner's `TargetRoleDecision`.

### Archaludon validation

**Verified finding — direct execution and transcript events 33-48:**

Initial representative build:

- Archaludon @ Leftovers;
- Stamina;
- Timid;
- 2 HP / 32 SpA / 32 Spe;
- Electro Shot / Flash Cannon / Protect / Dragon Pulse.

Confirmed revised build:

- Archaludon @ Leftovers;
- Stamina;
- Modest;
- 32 HP / 1 Def / 5 SpA / 25 SpD / 3 Spe;
- the same four moves;
- user-confirmed strategic role: bulky Rain special attacker.

Other direct findings:

- `infer_role` returns `bulky_pivot` solely because of Leftovers.
- The build contains no pivot move.
- Archaludon has no positive membership among the eight shipped role categories.
- It appears only as a rejected Swords Dance Attacker candidate because it clears neither delivery branch (`data/roles/swords_dance_attacker.v1.json:1071-1075`).
- Electro Shot benefits from Rain, while Archaludon does not set Rain.
- Stamina is reactive physical-durability evidence, not a setup turn.

**Proposal — resulting decision for the confirmed build:**

- `role_id = "bulky_rain_attacker"`;
- `match_quality = "clean"` because the user-confirmed build directly supports offense, Rain benefit, and durability intent;
- `primary_function = "offense"`;
- `durability_intent = "tanky"`;
- `kit_role = "bulky_pivot"` retained as conflicting coarse evidence;
- mechanisms:
  - special offense;
  - teammate-provided Rain accelerates Electro Shot;
  - Stamina supplies reactive physical durability;
  - Leftovers supplies passive sustain;
  - no pivot mechanism;
  - no required setup turn.

### What did not generalize symmetrically

**Proposal, validated against direct query output:** treating a proposed `match_quality="clean"` as “return no support needs” would be wrong for Archaludon. Direct `query_support_needs` execution with offense/tanky/no-setup surfaced:

- weak-SpD defensive coverage;
- healing/cleric;
- screens;
- optional Trick Room;
- Tailwind.

The role can be cleanly classified while residual teammate needs remain useful.

**Proposal, based on the verified Kingambit mismatch:** species-level compendium membership cannot be an active-role shortcut. Doing so would incorrectly mark the Black Glasses build as setup-dependent because another Kingambit profile uses Swords Dance.

**Verified finding:** the item rule labels Archaludon a pivot without a pivot move. **Proposal:** do not treat that output as strategic identity.

### Pelipper stress check

Pelipper is an additional symmetry check, not the required second anchor.

**Verified finding — direct execution and transcript events 33-40:**

- Representative build: Focus Sash, Drizzle, Modest, 2 HP / 32 SpA / 32 Spe, Hurricane / Weather Ball / Tailwind / Wide Guard.
- Confirmed revised spread: Modest, 32 HP / 1 Def / 5 SpA / 17 SpD / 11 Spe.
- `infer_role` returns `support_speed_control`.
- Rain Setter compendium ranks Pelipper first and records:
  - Drizzle as automatic primary delivery;
  - Tailwind and Helping Hand as secondary support.

**Proposal — resulting decision:**

- `role_id = "rain_setter"`;
- `match_quality = "clean"`;
- `primary_function = "support"`;
- durability intent depends on which resolved spread is active;
- Drizzle is automatic and not interruptible;
- Tailwind is a manual, interruptible secondary mechanism;
- `requires_setup_turn=False` for the primary Rain-setter identity.

**Proposal:** if the assigned strategic role is explicitly “Rain + Tailwind dual setter” and both halves are required, the required Tailwind mechanism would make `requires_setup_turn=True`. This cannot be decided by scanning for any setup-like move; required versus secondary contribution must be represented.

## Sub-task 2: `derive_role_shape_context`

### Current active contract

**Verified finding — `recommender/support_needs.py:472-617`:** only four fields affect `query_support_needs`:

- `match_status`;
- `primary_function`;
- `tankiness`;
- `setup_dependent`.

**Verified finding:** build mechanics are read separately from `pokemon`:

- ability and moves;
- species base stats;
- priority and self-heal;
- ability-derived field dependence;
- teammate field satisfaction;
- Speed comparison.

**Verified finding — `recommender/support_needs.py:463-465`:** current Speed analysis still ignores the resolved nature/spread and computes zero Speed investment with Hardy nature.

### Current-compatible narrow projection

**Proposal:** while the existing struct remains, project as follows.

#### `match_status`

1. No anchor:
   - do not construct a context;
   - do not call anchor-dependent queries.
2. Raw support analysis should run:
   - pass `"partial"`.
3. Upstream logic has already produced a complete support profile:
   - skip `query_support_needs`;
   - do not rely on `"clean"` as a role-classification synonym.
4. Do not produce `"none"` for a real anchor merely because classification is uncertain:
   - use unknown values for unresolved shape fields;
   - preserve `match_quality="none"` on `AnchorRoleDecision`.

This makes `"partial"` a compatibility routing token, not a derivation from role match quality.

#### `primary_function`

1. Use `AnchorRoleDecision.primary_function`.
2. Do not recompute from move count, item, or `infer_role`.
3. Use `"unknown"` when the decision has no defensible primary.

#### `tankiness`

1. `durability_intent="tanky"` -> `"tanky"`.
2. `durability_intent="glass"` -> `"glass"`.
3. `balanced` or unresolved -> `"unknown"` under the current narrow consumer.
4. Do not derive it from base stats alone.

#### `setup_dependent` / proposed `requires_setup_turn`

Set true only when a required mechanism for the assigned anchor role:

1. is activated by the anchor taking an action;
2. must happen before the role's payoff;
3. is interruptible by turn denial or Taunt-like disruption.

Set false when:

- no such required mechanism is evidenced;
- the role only benefits from teammate-provided Trick Room/Rain;
- the relevant condition is automatic;
- the only matching setup profile is an alternate species-level compendium role;
- an interruptible move is secondary rather than required.

When the build is incomplete, false means “not evidenced,” not “proven absent”; unresolved provenance remains on `AnchorRoleDecision`.

### Kingambit projection

**Verified finding:** the required current result is:

- `match_status="partial"`;
- `primary_function="offense"`;
- `tankiness="tanky"`;
- `setup_dependent=False`.

**Verified finding:** changing only setup from true to false removed Fake Out and Taunt while retaining healing, screens, and optional Trick Room.

### Archaludon projection

**Proposal, verified against the confirmed build:**

- compatibility `match_status="partial"`;
- `primary_function="offense"`;
- `tankiness="tanky"`;
- `setup_dependent=False`.

**Verified finding:** direct execution produced weak-SpD coverage, healing, screens, optional Trick Room, and Tailwind.

**Verified limitation:** Rain was not produced because `query_support_needs` derives condition requirements from abilities, not Electro Shot. This is a resolved-kit mechanics gap, not a reason to set setup dependence true.

### Pelipper projection

**Proposal, using the confirmed bulky build and primary Rain-setter identity:**

- compatibility `match_status="partial"` if raw analysis is intentionally run;
- `primary_function="support"`;
- `tankiness="tanky"` if the user's confirmed bulky intent is retained, otherwise use the resolved representative build's evidence;
- `setup_dependent=False` because primary Rain delivery is automatic.

**Verified finding:** direct execution with support/tanky/no-setup produces only healing/cleric. With support/glass/no-setup it produces no needs. With current `"clean"` it always returns no needs before examining the build.

### Projection conclusion

**Proposal:** `derive_role_shape_context` should remain a narrow, auditable projection. It must not:

- choose the anchor build;
- choose strategic role identity;
- inspect target/open-slot role;
- parse free-form evidence strings;
- infer field dependence that belongs in resolved-kit mechanics.

## Sub-task 3: `resolve_anchor_build`

### Proposed output contract

**Proposal:** `ResolvedAnchorBuild` should contain:

- one value or explicit unknown for species/form, ability, item, nature, spread, and moves;
- per-field source;
- whether fields are user-confirmed, provisional, usage-derived, cached, synthesized, legality-only, or unknown;
- a co-occurrence/provenance group where the source proves fields came from one set;
- unresolved ambiguities and conflicts;
- a stable build fingerprint/version so role classification is recomputed after a material revision.

### Verified current source limitations

1. **Verified finding — `recommender/state.py:163-170`:** `Slot` stores role, species, item, moveset, spread, and nature, but not ability.
2. **Verified finding — `recommender/state.py:263-266`:** `all_locked()` does not require nature and cannot require ability, so current state can call a slot complete without a complete confirmed build.
3. **Verified finding — `recommender/usage_data.py:67-107`:** `featured_or_common_set` selects the first complete featured moves/item set, then independently attaches the first top spread.
4. **Verified finding:** the current M-B featured set is itself assembled from top marginal fields, not observed joint-set evidence; the attached top spread is also not proven to co-occur with the featured moves/item/ability.
5. **Verified finding — `recommender/usage_data.py:124-152`:** `find_set_matching` can verify exact moves+item against featured sets, but still attaches the generic first top spread and omits nature.
6. **Verified finding — `recommender/resolved_builds.py:22-40`:** resolved-build cache rows store species, moves, item, spread, provenance, and verification metadata, but not ability or nature; the cache key likewise omits ability, so ability-distinct builds collide.
7. **Verified finding:** the cache's `verified` flag does not encode user confirmation or full-build completeness.
8. **Verified finding — `recommender/coverage.py:213-240`:** a slot conversion silently fills missing ability and other fields from representative usage.

### Proposed source precedence

**Proposal:**

1. User-confirmed locked fields.
2. Complete confirmed provisional build for the same anchor.
3. Exact moves+item matched usage build.
4. Role-compatible usage evidence or variant, when the source actually provides one.
5. Generic representative usage build.
6. Synthesized complete build.
7. Species-only evidence.

Higher-priority fields win individually, but fields may be grouped only when their source proves co-occurrence.

### Case 1: complete confirmed build

**Proposal:**

1. Use every confirmed value exactly.
2. Do not overwrite a confirmed field with usage.
3. Fill only fields the confirmed object explicitly marks missing.
4. Preserve a user-confirmed role separately from the build.
5. Recompute `AnchorRoleDecision` whenever the build fingerprint changes.

**Verified blocker:** current `Slot` cannot represent a complete confirmed build because it cannot retain ability, and `all_locked()` can report completion without nature.

### Case 2: usage-only

**Proposal:**

1. Prefer an exact featured set over independent common-move/item lists.
2. Mark the result `usage_derived`, not confirmed.
3. Group moves/item/ability/nature only when the source semantics prove a joint set. The current aggregate featured set does not.
4. Record top spread as separate evidence unless co-occurrence is proven.
5. Preserve missing fields as unknown.

Kingambit, initial Archaludon, and representative Pelipper all exercised this path.

### Case 3: multiple role-distinct variants

**Verified finding:** current shipped usage APIs do not expose role-correlated complete variants. `select_usage_spread()` can choose among spread/nature variants, but moves, item, and ability remain tied to one generic featured/representative set. Cache `variants` are spread dictionaries, not complete builds.

**Proposal:**

1. Do not pretend that the current data contains complete role-distinct variants.
2. Use role-aware spread/nature selection only for the fields it actually covers.
3. If a future source supplies complete variants, filter them by the decided strategic role's required mechanisms.
4. If one future complete variant matches, use it provisionally.
5. If several match, retain the ambiguity or ask the user; do not choose top-1 silently.
6. Do not claim a selected spread co-occurred with a featured moveset unless the source proves that.
7. Treat compendium membership as evidence that a variant may exist, not permission to inject its mechanism into another build.

**Verified example:** Kingambit has Excellent Swords Dance Attacker membership while its representative Black Glasses build lacks Swords Dance.

### Case 4: synthesized build

**Proposal:**

1. Require a complete explicit build or return a structured unresolved result.
2. Mark every synthesized field separately.
3. Validate legality.
4. Derive setup-turn dependence only from the synthesized mechanism actually present.
5. Do not promote a first-legal-ability fallback to confirmed fact.

**Verified finding:** current tier-3 refinement can leave fields incomplete; the role-play had to complete Hatterene manually.

### Case 5: species-only

**Proposal:**

1. Resolve only species/form and legality facts.
2. Do not claim an ability when more than one legal ability is possible.
3. Do not claim setup, condition setting, pivoting, or durability intent from species alone.
4. A user strategic role may establish intended primary function, but mechanism support remains unresolved.
5. Return `match_quality="partial"` or `"none"` with unknown shape fields.
6. Suppress or label needs that depend on unknown kit facts.

### Ability blocker

**Verified finding:** ability is role-defining for examples already used:

- Pelipper's Rain-setter identity depends on Drizzle.
- Archaludon's reactive durability evidence depends on Stamina.
- Kingambit's Defiant is relevant compendium secondary-role evidence.

**Proposal:** the missing `Slot.ability` field is a hard dependency for the authoritative confirmed-build and atomic-lock design. It does not prevent writing a classifier that degrades gracefully:

- if usage supplies an ability, classify it as provisional usage evidence;
- if ability is unresolved, omit ability-dependent mechanisms;
- reduce match quality where the role depends on that ability;
- never present the result as a confirmed anchor role.

**Proposal:** implementation should not be considered complete or production-safe until ability can be confirmed, persisted, revised, and atomically locked.

## Sub-task 4: struct-level open questions

### `match_status`

**Verified finding:** only `query_support_needs` reads this field. `"clean"` immediately returns `[]`; `"partial"` and `"none"` are behaviorally identical (`recommender/support_needs.py:481-486`).

**Verified finding:** no-anchor already returns `[]` from the missing-species guard, and the correct orchestrator behavior is to skip construction entirely.

**Proposal, validated against the comparable anchor:** a clean role classification should not imply that residual support needs are already known. The confirmed Archaludon build supports the proposed strategic identity while direct raw analysis still returns useful needs.

**Proposal:** remove `match_status` from the eventual `RoleShapeContext`.

- Keep `match_quality` on `AnchorRoleDecision`.
- Let orchestration separately decide `run_raw_support_analysis`.
- Until migration, pass `"partial"` when calling the raw tool.
- Do not use role-match quality as the routing condition.

### `setup_dependent`

**Verified finding:** repository search found no consumer outside `recommender/support_needs.py`; all other references are tests.

**Proposal:** rename it to `requires_setup_turn`.

Definition:

> The anchor's assigned role cannot reach its required payoff without first completing an exposed, interruptible action.

This excludes teammate-provided conditions and automatic abilities. Required versus secondary mechanisms must be considered, as shown by Pelipper's automatic Drizzle plus secondary Tailwind.

### `tankiness`

**Verified finding:** the current consumer has only two active gates:

- `tanky` enables defensive asymmetry and enhanced healing;
- `glass` plus offense enables Fake Out/redirection protection.

**Verified finding:** the real anchors exercised so far do not establish a distinct support-need behavior for `balanced`:

- Kingambit was treated as tanky.
- Confirmed Archaludon was explicitly bulky/tanky.
- representative Pelipper was Sash/max-offense; confirmed Pelipper was explicitly revised toward bulk.

**Proposal:** do not add `balanced` to the narrow `RoleShapeContext` yet. It would behave exactly like `unknown`.

**Proposal:** `AnchorRoleDecision.durability_intent` may preserve `balanced` for semantic accuracy, while the current projection maps `balanced` to `"unknown"`. Add a RoleShapeContext value only when a real consumer needs different behavior.

### `archetype_id`

**Verified finding:** repository search still finds zero consumers and zero construction sites that populate it.

**Proposal:** remove it from `RoleShapeContext`. Canonical anchor role identity belongs on `AnchorRoleDecision`.

### `partial_signals`

**Verified finding:** repository search still finds zero consumers and zero construction sites that populate it.

**Proposal:** remove it from `RoleShapeContext`. Replace it with typed mechanism evidence, conflicts, and per-field provenance on `AnchorRoleDecision`.

### Struct recommendation

**Proposal:** the eventual minimal shape passed to support reasoning is:

- `primary_function`;
- `tankiness`;
- `requires_setup_turn`.

Build mechanics stay in `ResolvedAnchorBuild`/`pokemon`; classification quality and evidence stay in `AnchorRoleDecision`; call routing stays in orchestration.

## Sub-task 5: preserving `TargetRoleDecision`

### Current lifecycle

**Verified finding — `recommender/slot_fill.py:77-85`:** `SlotFillContext` has:

- anchor;
- anchor `role_shape_context`;
- support/threat results;
- `chosen_need`;
- resolved species;
- annotated candidates.

It has no target-role field.

**Verified finding — `recommender/slot_fill.py:390-408`:** the existing resolve-all path iterates every support need and normally leaves `chosen_need=None`. Therefore the production-oriented helper has no “chosen need -> target role” step even before presentation.

**Verified finding — `recommender/slot_fill.py:68-74,223-280`:**

- `AnnotatedCandidate` stores species, matching needs, source, threat row, and spec.
- It does not store the intended target role.
- Its `matching_needs` is the last point where need evidence remains attached to each species.

**Verified finding — `recommender/state.py:135-142`:**

- pending presentation options store only species and source.

**Verified finding — `recommender/nodes.py:85-137`:**

- selecting a pending option produces a species-only `LockPayload`.

**Verified finding — `recommender/slot_fill.py:464-513`:**

- terminal acceptance immediately calls `apply_lock` on species.

**Verified finding — Kingambit/Farigiraf transcript event 16-17:**

- chosen need `trick_room`;
- intended target role `trick_room_setter`;
- Farigiraf species lock;
- refinement completed;
- final slot role remained `None`.

### Proposed `TargetRoleDecision`

**Proposal:** one immutable object should represent the open slot's role intent:

- canonical `role_id`;
- source: `_pick_role`, chosen support need, explicit user choice, or another named producer;
- originating need/evidence;
- required mechanisms or constraints;
- confidence/ambiguity;
- provenance.

This object is not part of `AnchorRoleDecision` or `RoleShapeContext`.

### Where it belongs

**Proposal:** add `target_role_decision` to `SlotFillContext`. This is its natural home during candidate discovery, but it is not sufficient by itself because `SlotFillContext` is not persisted across user turns.

**Proposal:** preserve the same decision through:

1. `SlotFillContext`
   - discovery-level target role.
2. `AnnotatedCandidate`
   - candidate-specific target role when merged branches can imply different roles.
3. Pending candidate presentation
   - each selectable option must retain the role decision selected with it.
4. `PendingSlotIntent`
   - cross-turn state after candidate choice; contains slot index, species, target role, evidence, and stage.
5. `ProvisionalSlot`
   - complete uncommitted build plus the same target role.
6. Full-build confirmation presentation
   - references the provisional slot and role.
7. Atomic batch lock
   - uses a new prevalidated all-or-nothing commit for role and every confirmed build field.

### Why a context-level field alone is insufficient

**Verified finding:** merged candidate pools can contain threat-only, need-only, and overlap candidates. A single `chosen_need` may be attached to need-resolved candidates while threat-only candidates have different justification (`recommender/slot_fill.py:223-280`).

**Proposal:** if every option truly shares one target role, the presentation may store it once. If options can imply different roles, the decision must be candidate-specific. The implementation must not silently apply a Trick Room Setter role to a threat-only alternative that does not provide Trick Room.

### Atomic lock support and blocker

**Verified finding — `recommender/state.py:96-100`; `recommender/nodes.py:257-351`:** current `LockPayload` can submit a batch of representable slot attributes, but `_apply_locks_batch` is not transactionally atomic. It skips conflicting attributes, commits the conflict-free remainder, and emits pending flags.

**Verified blocker:** ability cannot be included because `SlotAttrName` excludes it and `Slot` has no field.

**Proposal:** candidate acceptance must stop producing a lock payload. It should produce `PendingSlotIntent`, run provisional refinement, request confirmation, prevalidate the entire role/build update, and only then use a new all-or-nothing commit. Reusing `_apply_locks_batch` unchanged would still permit a partially committed slot.

## Proposed end-to-end anchored flow

This is a proposal, not an accepted implementation plan.

1. Resolve the anchor build with per-field provenance.
2. Classify the existing anchor into `AnchorRoleDecision`.
3. Decide whether raw support analysis should run.
4. If it runs, project the minimal RoleShapeContext.
5. Query and merge support/threat evidence.
6. Produce or refine `TargetRoleDecision` for the open slot.
7. Preserve that decision on candidate evidence and presentation.
8. Convert the user's candidate choice into `PendingSlotIntent`, not a lock.
9. Build and verify a complete `ProvisionalSlot`.
10. Present the complete build and role.
11. After confirmation, prevalidate and atomically commit role plus the complete build; do not reuse the current partial-commit batch semantics unchanged.
12. Recompute team-wide signals and any affected anchor classification after material changes.

## Vu decisions required before implementation

1. **Vu decision required:** canonical strategic role vocabulary.
   - Should identities be single values such as `bulky_rain_attacker`, or a primary role plus composable condition/mechanism tags?
   - This report does not choose a permanent taxonomy.
2. **Vu decision required:** representation of genuinely dual required roles.
   - Pelipper can be Rain setter primary with Tailwind secondary, or an explicitly required dual setter.
   - `requires_setup_turn` differs between those assignments.
3. **Vu decision required:** whether `AnchorRoleDecision.match_quality` keeps `clean/partial/none` or uses a less routing-like vocabulary.
   - The report recommends separating it from routing but does not require these exact labels.
4. **Vu decision required:** persistence envelope name and state shape.
   - `PendingSlotIntent` is proposed, not settled.
5. **Vu decision required:** whether ability persistence is fixed before or in the same implementation as this flow.
   - The report recommends treating it as a prerequisite for calling the path complete.
6. **Vu decision required:** source for role-correlated complete usage variants.
   - Current data supports role-aware spread/nature selection only; it cannot select correlated moves, item, ability, and spread variants.

## Proposed future acceptance checks

1. Black Glasses Kingambit preserves:
   - strategic `trick_room_sweeper`;
   - inferred `bulky_attacker`;
   - alternate Swords Dance profile;
   - target `trick_room_setter` separately.
2. Kingambit projects setup-turn false and does not emit Fake Out/Taunt setup needs.
3. Confirmed Archaludon classifies as offense-primary bulky Rain attacker despite `infer_role="bulky_pivot"`.
4. Archaludon records Electro Shot -> teammate-provided Rain and Stamina -> reactive durability.
5. A clean Archaludon classification does not suppress raw support-needs analysis.
6. Pelipper records Drizzle as automatic primary delivery and Tailwind as an interruptible secondary mechanism.
7. Species-only Swords Dance compendium membership does not change a non-Swords-Dance build's setup Boolean.
8. No-anchor state bypasses anchor classification and RoleShapeContext.
9. Unknown ability suppresses ability-dependent role claims.
10. A user-confirmed ability survives state persistence and atomic lock.
11. Multiple usage variants are not merged into a fictional co-occurring set.
12. `archetype_id` and `partial_signals` are removed from RoleShapeContext or gain an explicit consumer before being retained.
13. Candidate acceptance creates a pending intent, not a species lock.
14. Farigiraf chosen for Trick Room carries `trick_room_setter` through refinement.
15. Full confirmation atomically locks role, species, ability, item, moves, nature, and spread.

## Final handoff

**Verified finding:** the original failure was caused by conflating strategic condition dependence with an anchor's own interruptible setup turn.

**Proposal:** the smallest design that prevents that class of failure is:

1. one provenance-aware resolved anchor build;
2. one `AnchorRoleDecision` that keeps strategic identity separate from kit and compendium evidence;
3. one narrow shape projection;
4. one separately persisted `TargetRoleDecision`;
5. one provisional-build state before atomic lock.

No derivation function was implemented. The unresolved decisions above should be reviewed by Vu before implementation begins.
