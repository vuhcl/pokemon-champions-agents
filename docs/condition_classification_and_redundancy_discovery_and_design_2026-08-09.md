# Condition classification and redundancy/fallback checks — discovery and design (2026-08-09)

**Status:** Discovery + design only. No implementation in this pass.

**Deferred-from:** original Highest-priority tier item 6 in
[`docs/slot_fill_flow_discovery_2026-08-08.md`](slot_fill_flow_discovery_2026-08-08.md)
(§Suggested implementation priority; acceptance check 18; proposed
`assess_condition_resilience`). Confirmed still open in
[`docs/master_project_log.md`](master_project_log.md) (2026-08-09 ownership close-out:
item 6 untouched).

**Related but deliberately separate:** multi-locked `composition_fit` (candidate-level
duplication ranking). That design explicitly carved condition resilience out of scope
([`docs/multi_locked_candidate_discovery_and_ranking_design_2026-08-08.md`](multi_locked_candidate_discovery_and_ranking_design_2026-08-08.md)
§7: "This scope does not include condition resilience or selected-four mode viability").

**Out of scope here (per brief):** canonical name/form resolution; selected-four modeling;
calc-unavailable fallback; any new role taxonomy beyond what is already shipped.

---

## Part 1 — verified current state

### 1. Does `AnchorRoleDecision` mechanism evidence already capture team-condition dependency?

**Schema yes; production coverage almost no.**

`MechanismEvidence` already has the fields this task needs
(`recommender/anchor_roles.py:86-101`):

| Field | Relevant values already typed |
|-------|-------------------------------|
| `relation` | `provides`, `benefits_from`, `executes`, `mitigates` |
| `importance` | `needed` / `wanted` / `secondary` |
| `supply` | `self_supplied`, `teammate_expected`, `not_applicable` |
| `activation` / `interruptible` / `prerequisite` | used for setup-turn projection |

ADR-024 states the intended contract
(`docs/architecture_decisions.md` ADR-024): tiers per mechanic; interruptibility and
self-vs-teammate supply; `requires_setup_turn` must **never** derive from
"condition-dependence on a teammate-supplied effect."

**What `_mechanisms` actually emits today** (`anchor_roles.py:320-380`): only
self-supplied `provides` / `executes` / `mitigates` for a small hard-coded set —

- ability `Drizzle` → `provides` / `needed` / `rain_setter` / `automatic` / not prerequisite;
- setup moves (SD/NP/CM/Bulk Up) → `executes` / `needed` / prerequisite+interruptible move;
- `Tailwind` → `provides` / `wanted` / `tailwind_setter` / interruptible move / **not** prerequisite;
- `Trick Room` → `provides` / `needed` / `trick_room_setter` / prerequisite+interruptible move;
- Stamina / Sucker Punch / Leftovers → unrelated durability/offense/sustain.

No `benefits_from` rows for Swift Swim, Chlorophyll, Sand Rush, Electro Shot, Solar Power,
Protosynthesis, Rain-boosted Water STAB framing, etc.

**The only live `benefits_from` path** is not in `_mechanisms` at all. It is appended later in
`classify_anchor_role` when `role_id == "trick_room_sweeper"` and the kit lacks Trick Room
(`anchor_roles.py:465-482`): `relation="benefits_from"`, `kind="teammate_condition_benefit"`,
`importance="wanted"`, `supply="teammate_expected"`, `present=False`. Covered by
`tests/recommender/test_anchor_roles.py:34-47`.

**Smoking-gun negative:** Archaludon declared `bulky_rain_attacker` records Stamina durability
and explicitly has **no** Rain mechanism or rain role_id on mechanisms
(`test_anchor_roles.py:53-62`). So even a clean strategic Rain-attacker identity does **not**
currently encode "execution depends on Rain being active."

**Verdict for Q1:** the evidence *model* can represent team-condition dependence
(`benefits_from` + `teammate_expected` + `needed`/`wanted`). The *producer* almost never does.
Condition essentiality cannot be read off locked-member decisions without first extending
what `_mechanisms` / classification emit — still within the existing tier/relation vocabulary,
not a second evidence system.

#### `requires_setup_turn` — confirmed distinct

Projection (`anchor_roles.py:525-536` / ADR-024):

```text
present ∧ importance ∈ {needed, wanted} ∧ prerequisite ∧ activation == "move" ∧ interruptible
```

That is "the anchor must spend an interruptible turn on its own required setup action before
its payoff." It is **not** "the team's plan depends on field condition C."

Confirming examples already shipped:

| Case | `requires_setup_turn` | Team-condition dependence? |
|------|----------------------|----------------------------|
| Pelipper Drizzle primary + Tailwind wanted | `False` (auto setter; Tailwind not prerequisite) | Provides Rain; does not *depend* on a teammate condition |
| Kingambit `trick_room_sweeper` without Trick Room | `False` (benefit is teammate-expected, not self setup) | Depends on Trick Room — exactly the case ADR-024 excludes from this Boolean |
| Swords Dance / Nasty Plot needed | `True` when those moves are present | Self-setup, not field weather |

**Distinction holds.** Do not overload `requires_setup_turn` for condition essentiality.

---

### 2. Does `detect_spof` (or anything else) detect "only one provider of condition X"?

**`detect_spof` is threat-coverage leave-one-out only.**

```418:451:recommender/coverage.py
def detect_spof(...):
    baseline = compute_team_coverage(...)
    ...
    minus = compute_team_coverage(..., exclude_slot=i, ...)
    ...
    if without.best_outcome.outcome != "no_answer": continue
    if base.covering_slot_indices != [i]: continue
    # → SPOFFinding(slot_index, threats_lost, threat_severity)
```

A SPOF is: removing one slot turns at least one previously answered **meta threat** into
`no_answer`, and that slot was the sole covering index. Field enters only insofar as
`compute_team_coverage` may use ability-forced weather/terrain from remaining members
(`_forced_fields_from_draft`, `coverage.py:245-272`) when neutral answers fail. That is still
"does the team still answer threat T," not "how many members can set Rain / Trick Room /
Tailwind."

**Closest existing relatives (still not this check):**

| Mechanism | What it answers | Why it is not condition-provider SPOF |
|-----------|-----------------|----------------------------------------|
| `query_support_needs` `condition_setter` | This *one* Pokémon has a condition-dependent ability and no locked ability-setter currently secures it (`support_needs.py:75-105`, `_secured_fields` / `_condition_secured`) | Per-anchor partner ask; ability setters only; no team-wide essentiality; no provider cardinality 0/1/2+ |
| `_forced_fields_from_draft` / `_secured_fields` | Unique ability→field maps present on locked slots | Dedupes by field key; ignores move setters (Rain Dance, Trick Room, Tailwind); does not count redundancy |
| Role Compendium `role_candidates("weather_setter", "Rain")` etc. | Global admitted species for a role file | Species-pool lookup, not "locked team ∩ independently capable on *this* build" |
| ADR-018 team-level redundancy prose (`architecture_decisions.md` ~1425-1457) | Presentation ordering when *searching* for a second setter (competence before redundancy flag) | Policy for candidate presentation, not a runtime detector of current roster SPOF |

**Repository search:** no `assess_condition_resilience`, `condition_resilience`, or equivalent
producer exists under `recommender/`.

**Verdict for Q2:** nothing today detects "exactly one team member can provide condition X"
as a first-class structural finding. `detect_spof` must stay in its threat-coverage lane;
condition-provider SPOF is a distinct signal.

---

### 3. What does `composition_fit` actually mean?

**Candidate-level impact of *adding this candidate*, not team-level capability inventory.**

Producer: `annotate_composition_impact` (`team_candidates.py:364-435`).

**Locked side (inventory used as baseline):** for each locked `AnchorRoleDecision`, count
`primary_function`, `role_id`, and every `mechanism.present` mechanic string; also physical vs
special move counts among offense primaries.

**Candidate side:** resolve a representative build + `classify_anchor_role`, then assign:

| Fit | Predicate (as coded) |
|-----|----------------------|
| `complementary` | candidate has `anchored_needs`, **or** its `primary_function` is missing on the locked team, **or** it corrects a material physical/special skew |
| `severe_duplication` | no anchored needs, and it repeats a mechanic the team already has **≥2** of |
| `duplicative` | locked team already has this `role_id`, **or** it repeats any present mechanic (≥1), **or** it worsens phys/spec skew |
| `neutral` | unknown primary, or none of the above |

Used as ranking stage 4 in multi-locked lexicographic order
(`multi_locked_..._design` §9; `_FIT_RANK` in `team_candidates.py:438-443`):
`complementary > neutral > duplicative > severe_duplication`. Demotes; does not exclude.

**"Duplication" here:** "would this *candidate* repeat a function/mechanism the roster
already has?" It is **not** "does the roster already have redundant *capability* to provide
condition C, independent of evaluating any candidate?"

**Direct conflict with this task's desirable outcome:** a second Rain setter beside Pelipper
repeats `Drizzle`/`rain_setter`-adjacent mechanics and is therefore likely
`duplicative`/`severe_duplication` — exactly when an essential Rain plan with provider_count=1
*wants* a backup setter. Multi-locked design already noted the Basculegion failure mode was
role/offense duplication; it also explicitly deferred condition resilience (§7). ADR-018's
worked example (Politoed beside Pelipper) says redundant-but-competent setters should still be
presented with a redundancy *flag*, not pre-eliminated — `composition_fit` currently encodes
only the demotion half of that story, without the "resilience gap makes the second setter
valuable" half.

**Verdict for Q3:** related surface vocabulary ("duplication"), different question and
different aggregation axis (candidate delta vs team inventory). Do not treat
`composition_fit` as already answering condition redundancy.

---

### 4. Role Compendium weather/condition-setter categories — team provider counting?

**Shipped category files (species admission lists, not team analyzers):**

| File | Category / condition |
|------|----------------------|
| `data/roles/weather_setter_rain.v1.json` | `weather_setter` + Rain |
| `data/roles/weather_setter_sun.v1.json` | Sun |
| `data/roles/weather_setter_sand.v1.json` | Sand |
| `data/roles/weather_setter_snow.v1.json` | Snow |
| `data/roles/trick_room_setter.v1.json` | `trick_room_setter` |
| *(no dedicated Tailwind setter compendium file)* | Tailwind exists as need/role_id/`provides` mechanism and secondary allowlists, not a first-class role JSON |

APIs (`role_compendium.py:3126-3151`, `role_category_evidence` / `role_candidates`): load one
role entry and return admitted species ordered by tier. Construction distinguishes ability
delivery vs move delivery for weather setters; reverse lookup can mark exact-build vs
species-only membership.

**What does *not* exist:** an API that takes `team_draft` / locked contexts and returns
"N independently capable providers of C on the current builds." Intersecting
`role_candidates(...)` with locked species IDs would be a weak proxy and would violate
ADR-024's rule that compendium membership must not invent mechanisms the active build does
not use (e.g. a locked Pelipper running Keen Eye with no Drizzle must not count as a Rain
provider just because the species is Excellent in the Rain setter file — see
`test_anchor_roles.py:12-17` confirming ability can be non-Drizzle).

**Single-anchor classification** (`classify_anchor_role` + reverse compendium) is what exists
today. Team-level multi-provider counting does not.

---

### 5. What did ADR-023 Amendment 2026-08-02a actually dissolve?

**Dissolved gap 1 — Speed-axis "bidirectionality"**
(`docs/architecture_decisions.md` ADR-023 Amendment 2026-08-02a):

> Original finding assumed Trick Room and Tailwind must be presented as mutually exclusive
> answers to `query_support_needs`' Speed-axis trigger. Incorrect — TailRoom is a valid
> composite (ADR-020); `query_support_needs` already surfaces named need options rather than
> forcing a single pick. No tool change.

That closes only: "must the support-needs UI treat TR and TW as exclusive alternatives?"

It does **not** classify whether Trick Room or Tailwind is essential/preferred/optional to a
given roster; does **not** count providers; does **not** detect a condition-provider SPOF;
does **not** require a backup setter or fallback mode.

**Verdict for Q5:** the broader condition-essentiality / redundancy / fallback question
remains fully open. The amendment is adjacent only in that both mention speed-control
conditions; it does not partially implement this item.

---

### Part 1 synthesis

| Assumed cover | Actual |
|---------------|--------|
| Mechanism evidence already encodes condition dependence | Schema ready; only Trick Room sweeper emits `benefits_from`; Rain attackers etc. do not |
| `requires_setup_turn` ≈ condition dependence | Confirmed **false** by ADR-024 and projection predicate |
| `detect_spof` covers condition SPOF | Confirmed **false** — threat-coverage only |
| `composition_fit` ≈ condition redundancy | Confirmed **false** — candidate delta; can actively fight backup-setter value |
| Compendium setter categories ≈ team provider count | Confirmed **false** — global admission lists |
| ADR-023a dissolved this | Confirmed **false** — only TR↔TW exclusivity misdiagnosis |

Original flow-discovery finding stands: *"No structural trigger checks condition
resilience"* / *"Essential-condition redundancy is not checked"*
(`slot_fill_flow_discovery_2026-08-08.md` executive finding 5; gaps 270-271, 308-309;
proposed API 610-613).

---

## Part 2 — design proposal

### 0. Preconditions (reuse, don't invent a second evidence model)

Before essentiality math is trustworthy, extend the **existing** `MechanismEvidence`
producer so dependents and providers are actually present on locked members:

**Providers (`provides`, typically `self_supplied`, `present=True`):** keep current Drizzle /
Tailwind / Trick Room rows; add the already-known ability and move vocabulary already used
elsewhere (no new taxonomy) —

- weather abilities already in `WEATHER_SETTERS` / `ABILITY_TO_FIELD`
  (`contingent_value.py:15-23`, `coverage.py`);
- weather moves already keyed in `move_narrowing.py:46-49,65-68` (Rain Dance, Sunny Day,
  Sandstorm, Snowscape/Chilly Reception);
- Trick Room / Tailwind moves (already partially present).

**Dependents (`benefits_from`, `teammate_expected`):** emit from the same condition tables
`query_support_needs` already maintains (`_CONDITION_DEPENDENT_ABILITIES`) plus strategic
roles that are definitionally condition-mode (e.g. existing `trick_room_sweeper` path;
`bulky_rain_attacker` / sand-offense labels when declared or cleanly classified) with
`needed` vs `wanted` chosen by how hard execution fails without the field —

- speed-doubling / hard enable (Swift Swim, Chlorophyll, Sand Rush, Slush Rush, Surge Surfer,
  Electro Shot's Rain skip-charge when modeled) → prefer `needed`;
- damage/bulk soft boosts (Solar Power, Sand Force, Rain Dish, Ice Body, Dry Skin positive,
  Protosynthesis without Booster Energy, etc.) → prefer `wanted`;
- incidental / secondary → `secondary` (does not drive essentiality).

Move→condition tables already exist in calc/matchup for some charge moves
(`matchup.py` Electro Shot ↔ Rain); wire those into mechanism emission rather than inventing
parallel maps. Until those emissions exist, any essentiality classifier would silently under-
call Rain offense (Archaludon) and over-rely on the one Trick Room sweeper special case.

**Provider independence rule:** count only mechanisms that are `present` on the member's
**resolved active build** (same discipline as ADR-024). Compendium membership may *suggest*
a member could be rebuilt as a setter; it must not count as a live provider without kit
evidence. Optional later diagnostic: "species is a known setter but current kit does not
provide C."

---

### 1. Essential / preferred / optional classification

**Proposal:** for each tracked condition
`C ∈ {Rain, Sun, Sand, Snow, Trick Room, Tailwind}` (terrains deferred unless already
appearing as dependents; out of scope to invent new roles):

Let `Dependents(C)` = locked members other than pure providers whose mechanisms include
`benefits_from` on mechanic/kind mapped to `C` with `importance ∈ {needed, wanted}` and
either `present=True` **or** strategic `present=False` teammate-expected rows (Kingambit-style
declared mode).

| Class | Rule |
|-------|------|
| **essential** | ≥1 dependent with `needed`-tier `benefits_from` for `C`, **or** ≥2 distinct locked members with `wanted`-tier dependence on `C` (team clearly built around the mode even if no single hard lock) |
| **preferred** | not essential, but ≥1 `wanted`-tier dependent, **or** the team's primary direction/archetype/locked setter identity is a `*_setter` for `C` with at least one offense-primary teammate that is not itself only a setter (soft "we're on this plan" without hard dependents yet) |
| **optional** | team has a provider of `C` but no `needed`/`wanted` dependents (bonus control), **or** no providers and no dependents (irrelevant — omit from surfacing) |

**Why reuse tiers:** matches the user brief and ADR-024; avoids a parallel
"conditionImportance" enum. `needed` vs `wanted` already means "execution requires" vs
"materially wants."

**Why count *other* members' dependence, not the setter's `provides`:** a lone Pelipper
`provides` Rain as `needed` for *its* rain_setter identity; that does not by itself make Rain
essential to a six-slot plan until someone else's offense/speed depends on it. Setter-only
teams stay `preferred` at most until dependents appear.

**Explicit non-goal this pass:** proving a full "condition-independent fallback mode"
(e.g. Icy Wind replacing Trick Room). Flow discovery wanted that as an alternative to a
backup setter; treat it as a **later diagnostic** once provider redundancy exists. v1
surfaces provider cardinality gaps; fallback-mode demonstration can reuse speed-control /
priority move evidence later without blocking this design.

---

### 2. Redundancy / provider cardinality

**Proposal:** `Providers(C)` = locked members with a `present` `provides` mechanism for `C`
(ability or move), counted as independent if each can establish `C` without needing the
other's presence.

| `provider_count` | Meaning | Surface |
|------------------|---------|---------|
| **≥2** | Redundant capability | Informational; second setter is resilience, not a gap |
| **1** | Condition-dependency SPOF (distinct from `detect_spof`) | Real gap when class is essential or preferred |
| **0** | Unmet condition | Gap when class is essential or preferred (support_needs already asks this per-anchor for abilities; team signal makes it roster-wide including move setters) |

**Independence note:** two automatic weather abilities both "provide" Rain; still count as 2
for redundancy purposes. Domain mechanics about who wins a weather war (slower auto-setter,
Mega phase order — `master_project_log.md` deep technical notes) affect *reliability under
contest*, not the basic "do we have a second way to put Rain up if one member is dead/off
the field" count. Contest reliability can be a later severity tag; do not block v1 on it.

**Naming:** recommend `ConditionProviderFinding` / team signal field
`condition_resilience` (or `condition_signals`) — do **not** overload `SPOFFinding`, which is
threat-typed today (`state.py` / coverage types).

---

### 3. Where it surfaces — generation vs ranking (explicit decision)

Mirror the `shared_teammates` decision discipline
(`multi_locked_..._design` §6): publish in `refresh_team_signals`, then choose consumption
by what the signal uniquely enables.

**Proposal — dual use, generation-primary for gaps:**

1. **Publish** alongside `coverage` / `spofs` / `shared_teammates` from
   `refresh_team_signals` (`nodes.py:1071-1087`) and the parallel recompute inside
   `discover_multi_locked`. Add a `RecommenderState` field (same pattern as
   `shared_teammates`).

2. **Candidate generation (primary for `provider_count ≤ 1` when class ∈ {essential, preferred}):**
   admit backup-setter candidates via **existing** need-resolution paths —
   `condition_setter` / weather_setter + condition / `trick_room_setter` / Tailwind move
   satisfiers already in `slot_fill.py` — scoped to the gapped condition. Same reasoning as
   shared teammates: a ranking-only modifier cannot surface Politoed if no threat/support
   branch emitted it, yet acceptance check 18 requires backup setters for essential
   Rain/TR plans.

3. **Ranking (secondary, corrective):**
   - When `provider_count ≤ 1` and class is essential/preferred, a candidate that
     `provides` that condition must **not** be punished as mere `duplicative` for repeating
     the setter mechanic — treat as composition-positive for resilience (override or
     pre-empt the blind spot in §3). This is the load-bearing interaction with
     `composition_fit`.
   - Optionally add a late lexicographic stage "condition-SPOF backup" adjacent to existing
     "SPOF backup answers" (threat SPOF), **without** merging the two finding types.

**Why not ranking-only:** same failure mode `shared_teammates` rejected — demoting/boosting
rows that never entered the pool does nothing. Why not generation-only: without the
`composition_fit` interaction, generated backup setters would be systematically demoted for
"duplicating" the exact capability the gap says is missing.

**Why not fold into `detect_spof`:** different ontology (condition providers vs threat
answers); different consumers; keeps threat SPOF tests and semantics stable.

---

### 4. How this differs from `composition_fit` (non-duplication claim)

| | `composition_fit` | Condition resilience (this design) |
|--|-------------------|-------------------------------------|
| Axis | Candidate × locked roster | Locked roster alone (then informs candidates) |
| Question | Does adding *this* species repeat function? | Is condition C essential, and how many live providers exist? |
| Aggregation | Counts repeated role_ids / mechanism strings / phys-spec skew | Counts dependents by tier + providers by present `provides` |
| Desired second setter | Often `duplicative` | Often the *fix* for provider_count=1 |
| Scope statement | Explicitly excluded condition resilience | This item |

Overlap is real but one-way: both look at mechanisms on locked members. Resilience **feeds**
composition ranking (exception when duplication is actually resilience), rather than
re-implementing complementary/duplicative predicates. If implementation ever finds the
override is the only consumer, keep a single team signal and a narrow composition hook —
do not spawn a second parallel "fit" enum.

---

### 5. Minimal API shape (design only)

```text
assess_condition_resilience(locked_contexts | team_draft) -> ConditionResilienceReport
  conditions: list[ConditionResilienceRow]
    condition: Rain | Sun | Sand | Snow | Trick Room | Tailwind
    class: essential | preferred | optional
    provider_count: int
    providers: list[slot_index / species]
    dependents: list[{slot, importance}]
    gap: none | missing_provider | single_provider_spof
```

Callable from `refresh_team_signals` and reusable in post-lock review (flow-discovery
proposed both). Implementation should take `LockedAnchorContext` tuples already built by
`collect_locked_anchor_contexts` so mechanism evidence is not re-derived ad hoc with different
rules.

---

### 6. Residual risks / calibration notes

1. **Evidence sparsity until mechanism emission is widened** — shipping the classifier before
   dependent/provider emission expands will under-fire (Archaludon-shaped false "optional").
2. **`wanted`×2 → essential heuristic** may need real-team calibration; keep as an explicit
   policy with named tests so it can be tightened without silent drift.
3. **Tailwind has no dedicated compendium file** — provider detection must be move/mechanism
   based (already true for Tailwind in `_mechanisms`); do not block on new role JSON (out of
   scope).
4. **Weather-war reliability ≠ provider count** — document as known ceiling; optional later
   severity.
5. **Fallback mode** deferred as stated in §1; acceptance check 18's "or validated fallback"
   remains partially unmet until a follow-up.

---

## Final handoff

**Part 1:** condition essentiality/redundancy is **not** already covered by mechanism
projection, `detect_spof`, `composition_fit`, Role Compendium admission lists, or ADR-023
Amendment 2026-08-02a. The mechanism-evidence *schema* is the right reuse point; the
*producer* must grow within that schema first.

**Part 2:** classify essential/preferred/optional from locked members' `needed`/`wanted`
`benefits_from` rows; count present `provides` providers; publish as a team-wide signal next
to coverage/SPOF/shared teammates; consume primarily as **candidate generation** for
provider gaps, with a **ranking override** so `composition_fit` does not demote the backup
setter the gap asks for.

No implementation in this pass.
