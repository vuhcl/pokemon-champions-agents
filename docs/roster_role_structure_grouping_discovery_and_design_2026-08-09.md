# Roster role-structure grouping — discovery and design (2026-08-09)

**Status:** Design landed; on-demand summary implemented in
`recommender/roster_role_structure.py` (not graph-wired).

**Scope (confirmed narrow):** identify which locked roster members share a role/function
(implicitly competing for the same bring-4 slot) and which provide something no other locked
member does (effectively mandatory regardless of matchup). Static structural grouping only.

**Explicitly out of scope:** any "default 4" / "best 4"; opponent-aware reasoning;
execution-reliability / timing scoring; redundancy scoring within a candidate subset;
Mega-count guidance; selected-four / Team Preview beyond this static structure summary.

**Worked example (acceptance fixture):** Rain roster —
Pelipper (Drizzle + Tailwind), Archaludon (special Electro Shot kit), Mega-Swampert (Swift
Swim attacker), Sableye (Will-O-Wisp / Light Screen / Rain Dance / Encore), Sinistcha (Matcha
Gotcha / Trick Room / Protect / Rage Powder), Maushold (**Technician**; Population Bomb /
Tidy Up / Encore / Bite — fast-physical profile, not Friend Guard). Expected structural
reading: rain-setter contested (Pelipper, Sableye); attacker contested (Archaludon,
Mega-Swampert, Maushold); Sableye also uncontested unique utility (screens/status/
disruption); Sinistcha uncontested support unique to the roster.

**Amendment 2026-08-09b:** corrected Maushold ability + build-level confirmation + Matcha
Gotcha function-key decision — see §Part 1.4–1.7 below.

**Amendment 2026-08-09c:** original-probe independence audit — the first Maushold call did
**not** pass Friend Guard (ability omitted → resolved `None`); `bulky_attacker` came from
`infer_role` default with **zero** `MechanismEvidence` rows. See §1.4a.

**Amendment 2026-08-10:** re-probe on current source — Technician-Maushold now classifies
`role_id=fast_physical_attacker` (Technician × multi-hit), still `primary_function=offense`,
so it still joins the coarse contested `attacker` group. Implementation ships available
fields only; Step A utility/Hospitality emission remains deferred.

**Related but separate:**
[`docs/condition_classification_and_redundancy_discovery_and_design_2026-08-09.md`](condition_classification_and_redundancy_discovery_and_design_2026-08-09.md)
(condition essentiality / provider SPOF for six tracked field conditions);
[`docs/multi_locked_candidate_discovery_and_ranking_design_2026-08-08.md`](multi_locked_candidate_discovery_and_ranking_design_2026-08-08.md)
(`composition_fit` candidate-vs-roster duplication ranking — not a roster self-summary).

---

## Part 1 — verified current state

### 1. Is `assess_condition_resilience` only about the six tracked conditions?

**Yes. Precisely scoped; not a general role-grouping engine.**

`TRACKED_CONDITIONS` is the closed set
(`recommender/condition_types.py:10`):

```text
("Rain", "Sun", "Sand", "Snow", "Trick Room", "Tailwind")
```

`assess_condition_resilience` iterates **only** that tuple
(`recommender/condition_resilience.py:93-97`):

```93:97:recommender/condition_resilience.py
def assess_condition_resilience(
    locked: Sequence[LockedAnchorContext],
) -> ConditionResilienceReport:
    rows: list[ConditionResilienceRow] = []
    for condition in TRACKED_CONDITIONS:
```

Provider detection requires a present `provides` mechanism whose
`mechanism_condition(...)` resolves to one of those six
(`condition_resilience.py:109-127`, `mechanism_condition` at `:52-65`). That helper returns
`None` for anything outside the tracked set / setter-role map / Trick Room|Tailwind mechanic
names.

What it answers: per tracked condition — classification (essential/preferred/optional),
`provider_count`, dependents, and gap (`missing_provider` / `single_provider_spof` /
`none`). What it does **not** answer: general attacker vs support contested slots, screens,
status disruption, redirection, healing, or any non-tracked function.

**Closest false friend:** `annotate_composition_impact` in
`recommender/team_candidates.py:480-555` counts locked `primary_function`, exact `role_id`,
and present mechanism **names** to label *incoming candidates* as complementary /
duplicative. That is candidate-ranking impact, not a readable roster-structure summary, and
it still collapses support too coarsely when it uses `primary_function` alone.

**Verdict for Q1:** condition-resilience provider-count logic is reusable as a *pattern*
(invert providers → cardinality → contested vs sole), but not as the *function vocabulary*
for general roster role structure.

---

### 2. Does `AnchorRoleDecision` already carry enough information for general functions?

**Structure yes for roles/mechanisms it already emits; coverage incomplete for the worked
example's unique-utility half.**

`AnchorRoleDecision` (`recommender/anchor_roles.py:118-129`):

| Field | What it encodes today |
|-------|------------------------|
| `role_id` | Single primary strategic label |
| `secondary_role_ids` | Distinct role ids from present `needed`/`wanted` mechanisms with a `role_id` ≠ primary (`:746-754`; ADR-024) |
| `primary_function` | Coarse bucket: `offense` / `support` / `unknown` (`:40`, `:622-635`) |
| `mechanisms` | Per-mechanic evidence rows (`MechanismEvidence`, `:92-107`) |
| `kit_role` | Separate `infer_role` fallback label — diagnostic, not the strategic primary |

**Live probe of the worked-example kits** (locked moves/abilities via
`resolve_anchor_build` + `classify_anchor_role`, 2026-08-09):

| Member | `role_id` | `secondary_role_ids` | `primary_function` | Present / relevant mechanisms |
|--------|-----------|----------------------|--------------------|-------------------------------|
| Pelipper | `rain_setter` | `tailwind_setter` | `support` | Drizzle `provides` Rain; Tailwind `provides` |
| Sableye | `rain_setter` | `()` | `support` | Rain Dance `provides` Rain **only** |
| Archaludon (`user_role=bulky_rain_attacker`) | `bulky_rain_attacker` | `()` | `offense` | Stamina; Electro Shot `benefits_from` Rain |
| Mega-Swampert (`user_role=physical_rain_attacker`) | `physical_rain_attacker` | `()` | `offense` | Swift Swim `benefits_from` Rain |
| Sinistcha | `redirection` | `trick_room_setter` | `support` | Trick Room `provides` (Rage Powder / Hospitality **not** mechanism rows) |
| Maushold (**Technician** locked) | `fast_physical_attacker` | `()` | `offense` | *(none)* — Encore / Bite / Tidy Up / Technician emit nothing |

Implications for "what function does this member provide?":

1. **Rain-setter competition is already readable** from `role_id` / setter mechanisms:
   Pelipper and Sableye both classify as `rain_setter` (Sableye via exact rain-setter
   compendium + Rain Dance mechanism; Pelipper via Drizzle). This overlaps condition-
   resilience's Rain provider list, by design.
2. **Attacker competition is *not* readable from exact `role_id`.** The three attackers have
   three different ids (`bulky_rain_attacker`, `physical_rain_attacker`, `fast_physical_attacker`).
   They **do** share `primary_function == "offense"`. Grouping attackers therefore needs the
   coarse function bucket (or an explicit alias of it), not exact-id equality.
3. **Support must *not* coarsen the same way.** Collapsing all `primary_function == "support"`
   members would falsely group Pelipper + Sableye + Sinistcha into one contested "support"
   slot — contradicting the worked example (rain-setter contested separately; Sinistcha
   uncontested redirection/utility). Fine-grained `role_id` / mechanism-backed functions are
   required on the support side.
4. **Sableye's unique utility is not in the decision today.** Will-O-Wisp, Light Screen, and
   Encore produce no `MechanismEvidence` and no `secondary_role_ids`. Screens *are* known
   elsewhere as a support-need satisfier (`slot_fill.py:85-87` `_NEED_SATISFIERS["screens"]`),
   but that vocabulary is used for *open-slot need matching*, not projected onto locked
   anchors' role decisions. **Same gap category on fixture Maushold:** Encore (disruption)
   and Bite (flinch chance) also emit nothing — see §1.4.
5. **Sinistcha's uncontested identity is partially present.** Primary `redirection` comes from
   exact compendium (`redirection.v1.json`), not from a Rage Powder mechanism row. Secondary
   `trick_room_setter` comes from the Trick Room move mechanism. Hospitality (resolved ability)
   is **not** emitted as a mechanism / role id. Matcha Gotcha self-drain is deliberately
   **not** proposed as its own function key (see §1.7) — ally-directed Hospitality remains
   the only healing/ally-reinforce gap worth a producer extension if that uncontested line
   is desired.

**Verdict for Q2:** enough to determine functions **the classifier already names**. Not yet
enough, without a small producer extension, to surface the worked example's Sableye (and
Maushold Encore) unique-utility lines, or Sinistcha Hospitality ally-heal. Do **not** invent
a parallel taxonomy; extend emission into the existing evidence model (same conclusion
pattern as the condition-resilience design's preconditions).

---

### 1.4 Corrected Maushold fixture probe (Technician)

#### 1.4a Original probe — exact inputs (independence audit)

The **first** session probe (before any Technician correction) was **not** a Friend Guard
build. Ability was omitted entirely. Exact call shape:

```python
# Original roster loop entry — only species + moves; no ability, item, or role hint
("Maushold", dict(moves=["Population Bomb", "Tidy Up", "Encore", "Bite"]))

# Constructed as:
slot = Slot(
    species=Attr(value="Maushold", locked=True),
    # ability: Attr() default — NOT Friend Guard, NOT Technician
    # item: Attr() default
    moveset=Attr(
        value=["Population Bomb", "Tidy Up", "Encore", "Bite"],
        locked=True,
    ),
)
build = resolve_anchor_build(slot)
decision = classify_anchor_role(build)  # user_role=None, explicit_role=None
```

Nothing beyond resolved kit data was available to that call: no `user_role`, no
`explicit_role`, no "attacker" hint, no conversational prose. Re-invocation of those same
inputs (2026-08-09c) resolves:

| Field | Value | Provenance |
|-------|-------|------------|
| ability | `None` | `unknown` |
| item | `None` | `unknown` |
| moves | fixture four | `user_confirmed` |
| `role_id` | `bulky_attacker` | evidence: `("primary_role", "user_confirmed", "infer_role fallback")` |
| `MechanismEvidence` | **empty tuple** | `_mechanisms(build)` length 0 |
| `compendium.exact` | `[]` | no exact role hit |

So the original `bulky_attacker` label was **not** produced under a Friend Guard ability, and
was **not** influenced by conversational framing of Maushold as an attacker. It was the
classifier's own fallback on moves-only kit data.

#### 1.4b Fresh corrected kit (Technician) — independent invocation

Separate call (not adjusted from prior result):

```python
slot = Slot(
    species=Attr(value="Maushold", locked=True),
    ability=Attr(value="Technician", locked=True),
    moveset=Attr(
        value=["Population Bomb", "Tidy Up", "Encore", "Bite"],
        locked=True,
    ),
)
build = resolve_anchor_build(slot)
decision = classify_anchor_role(build)  # still no role hints
```

| Field | Value |
|-------|-------|
| ability | Technician (`user_confirmed`) |
| `role_id` | `bulky_attacker` |
| `secondary_role_ids` | `()` |
| `primary_function` | `offense` |
| `kit_role` | `bulky_attacker` |
| evidence | `("primary_role", "user_confirmed", "infer_role fallback")` |
| `MechanismEvidence` | **empty** — still length 0 |
| `compendium.exact` | `[]` |
| `infer_role(moves, item)` | `bulky_attacker` |

#### 1.4c Why — from actual mechanism evidence (there is none)

Classification path in `classify_anchor_role` (`anchor_roles.py:650-691`), applied to both
A and B:

1. `_mechanisms(build)` → **`[]`**. Population Bomb multi-hit, Technician low-BP boost,
   Tidy Up (+Atk/+Spe / clears hazards), Encore, and Bite flinch are **not** in the
   producer. `_SETUP_MOVES` only lists Swords Dance / Nasty Plot / Calm Mind / Bulk Up
   (`anchor_roles.py:376-381`) — **Tidy Up is not among them**, so no
   `swords_dance_attacker`-style setup role_id is emitted. No weather/condition/Tailwind/
   Trick Room / Stamina / Leftovers rows either.
2. `user_role` / `explicit_role` empty → no declared branch.
3. `compendium.exact` empty → no usage-derived strategic role.
4. `next((m for m in mechanisms if m.role_id), None)` → `None` (no mechanism roles).
5. Falls through to `infer_role(list(build.moves), build.item or "")`
   (`recommend.py:46-57`): no Trick Room, no Tailwind, item empty (not sash/scarf/band/
   specs/berry/helmet) → **default return `bulky_attacker`**.
6. `_primary_function("bulky_attacker")` → `offense` because `role_id` is in the hard-coded
   offense set (`anchor_roles.py:622-628`).

**There is no present `MechanismEvidence` row that "explains" Technician × Population Bomb
or Tidy Up.** The label is entirely the `infer_role` catch-all default.

#### 1.4d Coincidence with conversation / Friend Guard

**Correction to the premise that "the original probe used Friend Guard":** it did not
(§1.4a). Ability was absent (`None`).

**Friend Guard + the same four moves** (no Follow Me), as a separate check:

| Build | `role_id` | mechanisms | exact compendium |
|-------|-----------|------------|------------------|
| ability omitted (original) | `bulky_attacker` | `[]` | `[]` |
| Technician + fixture moves | `bulky_attacker` | `[]` | `[]` |
| Friend Guard + fixture moves | `bulky_attacker` | `[]` | `[]` |
| Friend Guard + Follow Me (earlier contrast) | `redirection` | `[]` | exact `redirection` |

Friend Guard alone does **not** change the label: ability is unused by `_mechanisms` and by
`infer_role`, and Friend Guard without Follow Me / Rage Powder does not hit
`compendium.exact` redirection. So `bulky_attacker` is **not** a defensible differentiated
output for "Friend-Guard Maushold specifically" — it is the same under-differentiated
fallback for any Maushold kit that (a) has moves, (b) has no exact compendium hit, (c)
emits no mechanism `role_id`, and (d) fails `infer_role`'s few item/move special cases.

**Coincidence verdict:** conversational description of Maushold as an attacker matching
`bulky_attacker` is real but **harmless regarding bias** — the probe had no role hint.
The matching label is explained by a **real classifier weakness**: Maushold builds are
under-differentiated whenever ability-defining identity (Technician vs Friend Guard) is not
accompanied by a move that triggers exact redirection compendium (Follow Me / Rage Powder)
or by an `infer_role`-recognized item. The original result was not wrong *because of*
conversational framing; it was the classifier's coarse default, now surfaced by the
Technician correction (which still yields the same default, for the same reason).

**Grouping impact (unchanged):** `primary_function == "offense"` still places fixture
Maushold in the shared `attacker` contest. Exact `role_id` remaining `bulky_attacker`
under Technician is a fidelity quirk of `infer_role`, not evidence that the probe was
steered by chat.

---

### 1.5 Build-level vs species-level grouping (confirmed)

**Contrast probe — same species, different resolved kit:**

| Build | `role_id` | `primary_function` | Would join (proposed algorithm) |
|-------|-----------|--------------------|----------------------------------|
| Technician + Pop Bomb / Tidy Up / Encore / Bite | `bulky_attacker` | `offense` | contested `attacker` |
| Friend Guard + Follow Me / Pop Bomb / Protect / Encore | `redirection` | `support` | uncontested (or contested-with-Sinistcha) `redirection` — **not** `attacker` |
| Species only (no locked ability/moves) | `unresolved` | `unknown` | no function keys (skipped) |

Friend Guard + Follow Me classifies via exact redirection compendium
(`redirection.v1.json`, Excellent) with empty mechanisms — same pattern as Sinistcha's
redirection primary. Result is meaningfully different from the Technician attacker build.

**Architectural confirmation:** the proposed algorithm must key exclusively off each
member's `LockedAnchorContext.role_decision` (derived from that slot's real
`ResolvedAnchorBuild`), never species-level defaults or compendium membership without the
active kit. If it ever operated coarser than the resolved kit, Technician-Maushold and
Friend-Guard-Maushold would be misclassified identically. Species-only probe (`unresolved` /
`unknown`) shows there is no safe species default to fall back on anyway.

---

### 1.6 Archaludon special attacker / phys–special (deliberately out of scope)

Archaludon with the fixture special kit + `user_role=bulky_rain_attacker` classifies
`primary_function == "offense"` / `role_id == bulky_rain_attacker`. `PrimaryFunction` is
only `offense | support | unknown` (`anchor_roles.py:40`) — it does **not** distinguish
physical vs special.

**That is correct for this task.** Archaludon still counts toward the shared `attacker`
contest with Mega-Swampert and Technician-Maushold. Physical/special/type interactions
(e.g. Maushold's Fighting weakness compounding with Archaludon's profile) are
damage-profile / matchup reasoning, not function-group structure, and remain **explicitly
out of scope** per the original brief — not an emission gap to close here.

---

### 1.7 Matcha Gotcha self-heal — no separate function key

**Decision: do not add a tracked function key for Matcha Gotcha.** Fold it into Sinistcha's
existing offense-on-a-support-primary representation (STAB damage that happens to drain);
do not surface an uncontested "self-heal" group from this move.

**Reasoning:**

1. **Bring-4 function test fails.** Contested/uncontested groups answer "who else on the
   locked roster supplies this *roster function*?" Self-drain on Sinistcha's own attacking
   turn is self-sustain for that member's longevity, not a team function peers compete to
   cover (unlike rain-setting, redirection, or screens). Calling it uncontested "mandatory
   self-heal" would misframe personal sustain as a slot-competition axis.
2. **Other-directed vs self.** The fixture's interesting Sinistcha heal/ally signal is
   **Hospitality** (and Friend Guard on other builds) — already named in redirection
   secondary allowlists (`role_compendium.py`). That is the candidate for a future
   ally-heal / ally-reinforce key if producer emission is extended. Matcha Gotcha is not
   that.
3. **Existing vocab already treats self-heal differently from cleric support.**
   `_SELF_HEAL_MOVES` in `support_needs.py:53-65` is recover-style moves for *suppressing
   a tank's healing need*; `_NEED_SATISFIERS["healing_cleric"]` is Wish / Heal Pulse / etc.
   Matcha Gotcha appears in neither — and has `heal: 1` on a damaging move in
   `data/moves/flags.v1.json`, i.e. drain offense, not a dedicated support role.
4. **YAGNI for this scope.** Adding a Matcha-specific (or drain-move) function key invents
   taxonomy the grouping task does not need to explain the Rain roster's bring-4-shaped
   structure.

---

### 3. Can a member appear in more than one role-group? Does the model support it?

**Yes, membership must be many-to-many. The data model already supports multi-function
membership; nothing forces one-classification-per-member.**

Evidence:

- ADR-024 explicitly sources `secondary_role_ids` from distinct needed/wanted mechanisms
  (`docs/architecture_decisions.md` ADR-024; `anchor_roles.py:746-754`). Pelipper live:
  primary `rain_setter` + secondary `tailwind_setter`.
- Sinistcha live: primary `redirection` + secondary `trick_room_setter`.
- Compendium / membership docs already treat multi-role as a first-class quality signal
  (e.g. architecture notes on Pelipper / Politoed / Sableye multi-role structure around
  ADR support-membership criteria).
- `condition_resilience` already allows the same slot to be both a Rain **provider** and a
  Rain **dependent** in theory (separate lists); provider detection is independent per
  condition. That is multi-label by condition, not by general role — but the pattern is
  multi-membership.

What is **not** supported today for the Sableye fixture:

- Primary is singular (`role_id: str`) — fine.
- Unique screens/status/disruption never enter `secondary_role_ids` because no mechanism
  carries those role ids — so multi-membership *capacity* exists, but the second label is
  missing for Sableye.

**Verdict for Q3:** grouping must be explicitly many-to-many (member → set of function keys →
invert). Do not collapse a member into a single exclusive bucket. Sableye must be allowed to
appear in both `rain_setter` (contested) and a unique-utility group (uncontested) once that
utility is evidence-backed.

---

### Part 1 synthesis

| Question | Verified answer |
|----------|-----------------|
| Reuse `assess_condition_resilience` as-is for general roles? | **No** — six tracked conditions only |
| Reuse `AnchorRoleDecision` as the labeling source? | **Yes, structurally** — with known emission gaps for utility kits |
| One classification per member? | **No** — many-to-many; model already has secondary roles + mechanisms |
| Exact `role_id` equality for attackers? | **No** — use `primary_function == "offense"` (or alias) |
| Exact `primary_function == "support"` for support contested slots? | **No** — too coarse; keep setter / redirection / utility keys fine-grained |
| Technician-Maushold → `fast_attacker`? | **No today** — `infer_role` ignores ability → `bulky_attacker`; still `offense` |
| Encore/Bite on Maushold emit mechanisms? | **No** — same utility-emission gap category as Sableye |
| Grouping must be build-level? | **Yes** — FG+Follow Me Maushold → `redirection`/`support`, not `attacker` |
| Phys/special inside `attacker`? | **Deliberately out of scope** — not a gap |
| Matcha Gotcha as own function key? | **No** — self-drain, not a roster bring-4 function |

---

## Part 2 — design proposal

### 1. Grouping algorithm (proposed)

**Input:** locked roster members as `LockedAnchorContext` (already carries
`role_decision: AnchorRoleDecision` from that slot's resolved kit) — same collection path
as condition resilience (`collect_locked_anchor_contexts`). **Never** species-level defaults
(§1.5).

**Step A — extract function keys per member** (union, order-preserving):

1. **Primary strategic role:** `decision.role_id` (skip `"unresolved"`).
2. **Secondary strategic roles:** each of `decision.secondary_role_ids`.
3. **Offense bucket (coarse):** if `decision.primary_function == "offense"`, also emit a
   stable function key `attacker` (display label "attacker"). This is the only intentional
   coarsening — required so Archaludon / Mega-Swampert / Technician-Maushold share a
   contested slot despite divergent exact role ids. Physical vs special is **not**
   subdivided here (§1.6).
4. **Significant provide-mechanisms:** for each present mechanism with
   `relation == "provides"` and `importance in {"needed", "wanted"}` and a non-null
   `role_id`, ensure that `role_id` is in the set (usually already covered by 1–2).
5. **Do not** emit keys from `benefits_from` dependents (Swift Swim / Electro Shot) as
   "functions provided to the roster" — those are consumption, not supply. Condition
   resilience already owns that axis.
6. **Do not** emit a blanket `support` bucket from `primary_function` (see Part 1 §2).
7. **Do not** emit a Matcha Gotcha / self-drain function key (§1.7).

**Step B — invert:** `function_key → [members…]`.

**Step C — classify groups:**

- `len(members) >= 2` → **contested** (implicit bring-4 competition for that function).
- `len(members) == 1` → **uncontested** (that member's contribution of this function is
  effectively mandatory for covering it among the locked six — still **not** a bring-4
  recommendation).

**Step D — member-centric index (derived, not a second classification):** for each member,
list every group they belong to with contested/uncontested flags. This is how Sableye
surfaces as both rain-setter competitor and unique-utility provider without collapsing.

**Preconditions before the worked example fully passes (labeled — not this pass's
implementation):**

| Gap | Why it blocks the fixture | Proposed fix (reuse, don't invent) |
|-----|---------------------------|------------------------------------|
| Sableye screens / WoW / Encore absent from mechanisms | Unique-utility group empty | Extend `_mechanisms` (or a thin projection used only by this summary) to tag present kit moves already known in `_NEED_SATISFIERS` / compendium secondary allowlists — e.g. screens → function key aligned with need category `screens`; status/disruption moves already named in redirection secondary allowlists (`encore`, `willowisp` in `role_compendium.py`) → a single `disruption_utility` or split keys. Prefer attaching as `MechanismEvidence` with `role_id` so `secondary_role_ids` stays the single secondary channel (ADR-024). |
| Maushold Encore (and Bite flinch) absent | Same utility gap on an offense primary | **Same fix category as Sableye** — not a separate workstream; Encore already in the disruption allowlist above. Bite flinch stays optional/secondary unless a flinch vocabulary already exists (it does not in need satisfiers today — leave out unless needed). |
| Sinistcha Rage Powder not a mechanism | Redirection primary depends on compendium exact hit | Acceptable for grouping today (primary `redirection` is present). Optionally later emit `provides` / `redirection` from Follow Me / Rage Powder moves for kit-proofing when compendium miss. |
| Hospitality / Friend Guard not on decision | Optional ally-heal / ally-reinforce uncontested line | Emit from `_REDIRECTION_SECONDARY_ABILITIES` (`hospitality`, `friendguard`) as mechanisms with role ids if that display line is wanted. **Not** Matcha Gotcha (§1.7). |

Until those producer gaps close, a pure-decision run still yields a **useful partial**
structure for the fixture (rain contested; attackers contested via `attacker` bucket
including Technician-Maushold; Sinistcha `redirection` + `trick_room_setter` uncontested;
Pelipper also `tailwind_setter` uncontested) but **misses** Sableye's (and Maushold
Encore's) unique utility and optional Sinistcha Hospitality ally-reinforce.

---

### 2. Output shape (proposed)

Readable roster-structure summary — not a recommendation. Suggested types (names flexible):

```text
RosterRoleStructureReport
  groups: tuple[RoleFunctionGroup, ...]
  members: tuple[MemberRoleMembership, ...]   # optional derived view

RoleFunctionGroup
  function_key: str          # e.g. rain_setter | attacker | redirection | screens
  label: str                 # human: "rain setter", "attacker", "screens", …
  members: tuple[MemberRef, ...]  # slot_index, species
  cardinality: int
  status: "contested" | "uncontested"
  notes: str | None          # e.g. "3 candidates" when contested offense

MemberRef
  slot_index: int
  species: str

MemberRoleMembership
  slot_index: int
  species: str
  groups: tuple[(function_key, status), ...]
```

**Display sketch for the worked example (target after producer gaps):**

```text
rain setter: Pelipper, Sableye (contested)
attacker: Archaludon, Mega-Swampert, Maushold (contested, 3 candidates)
tailwind setter: Pelipper (uncontested)
redirection: Sinistcha (uncontested)
trick room setter: Sinistcha (uncontested)
screens: Sableye (uncontested)
status / disruption: Sableye[, Maushold] (contested if both emit Encore; else Sableye alone)
ally heal (Hospitality): Sinistcha (uncontested)  # optional; once emitted — not Matcha Gotcha
```

Ordering suggestion: contested groups first (by cardinality desc), then uncontested; within
a group, stable by slot index. No ranking of *which* contested member is "better."

**Partial output available today (no producer changes):** rain setter contested; attacker
contested (via proposed `attacker` key, including Technician-Maushold despite
`role_id=bulky_attacker`); Pelipper tailwind uncontested; Sinistcha redirection + trick
room uncontested. Sableye/Maushold disruption and Sinistcha Hospitality lines absent until
Step A preconditions land.

---

### 3. Evidence model reuse (confirmed)

**Proposal reuses `AnchorRoleDecision` as the sole labeling source for providers** —
`role_id`, `secondary_role_ids`, `primary_function` (offense bucket only), and
`mechanisms` — not a new classification system parallel to ADR-024 / the role
compendium.

Any missing labels are **producer completeness** inside `_mechanisms` /
`classify_anchor_role` (or a documented projection that writes the same mechanism/role_id
shapes), using vocabularies already present in:

- setter / speed-control mechanisms already emitted;
- `_NEED_SATISFIERS` move sets (`slot_fill.py`);
- redirection secondary move/ability allowlists (`role_compendium.py`);
- `PrimaryFunction` offense bucket (`anchor_roles.py`).

This mirrors the condition-resilience design stance: extend emission into the existing
evidence model before trusting team-level cardinality math.

**Non-goals for labeling:** do not score Prankster vs natural speed; do not prefer Drizzle
over Rain Dance; do not fold execution reliability into contested/uncontested.

---

### 4. Where should this surface?

**Recommendation: new on-demand query/summary function — not automatic live-graph wiring
in this scope.**

| Option | Pros | Cons |
|--------|------|------|
| **A. Callable summary** e.g. `summarize_roster_role_structure(locked) -> Report`, invoked when asked or when UI/review requests it (gate hint: useful once ≥4 locks, but callable anytime) | Matches confirmed scope; zero risk of driving slot-fill / candidate ranking; easy to test against the Rain fixture; parallel to how condition resilience *can* be assessed from contexts without owning bring-4 | Requires an explicit call site (chat tool, review panel, or future graph opt-in) |
| B. Always attach in `refresh_team_signals` / `discover_multi_locked` | Always fresh next to coverage / resilience | Couples a static descriptive summary into every multi-lock turn; easy to be misread as selection guidance; graph already busy with candidate discovery |
| C. Fold into `assess_condition_resilience` | One report | Wrong abstraction — tracked conditions ≠ general roles (Part 1 §1) |

**Choose A.** Reasoning: the brief asks for structure identification, not live routing
pressure. Condition resilience already occupies the automatic multi-lock signal niche for
*field conditions*. Role-structure grouping answers a different question ("who shares a
bring-4-shaped function among locked members?") and should stay pull-based until a later
product decision wants it on the default review pane. Suggested call cues (non-binding):
user asks "how does this roster structure?", team-review mode, or lock-count ≥ 4 — still
the same pure function underneath.

Do **not** feed this report into `composition_fit` or selected-four assessment in this
design — that would smuggle ranking / bring-4 selection back into scope.

---

## Acceptance checks (for a later implementation pass)

1. Rain fixture: Pelipper + Sableye in the same contested `rain_setter` group.
2. Rain fixture: Archaludon + Mega-Swampert + Technician-Maushold in the same contested
   `attacker` group (despite distinct exact role ids; despite Archaludon being special and
   Maushold physical — no phys/special split).
3. Rain fixture: Sableye appears in ≥1 uncontested utility group **and** the contested rain
   group (many-to-many) — blocked on mechanism emission for screens/status/disruption until
   precondition lands; document partial vs full.
4. Rain fixture: Sinistcha appears in uncontested `redirection` (and `trick_room_setter`);
   not merged into a generic support bucket with Pelipper/Sableye; no Matcha Gotcha
   self-heal function key.
5. Build-level: Friend Guard + Follow Me Maushold must **not** join the `attacker` group;
   must join `redirection` (proves kit-keyed, not species-keyed).
6. No output field named or framed as "recommended four," "default bring," or opponent-
   relative ranking.
7. Implementation consumes `AnchorRoleDecision` fields only (plus the explicit `attacker`
   alias of `primary_function == "offense"`); no second role taxonomy module.

---

## Scratchpad

- **Goal:** discovery + design for static roster role-structure grouping.
- **Plan:** verify condition_resilience scope → probe AnchorRoleDecision on Rain fixture →
  design many-to-many grouping + output + surface recommendation.
- [X] Part 1 verified with source citations + live classification probe
- [X] Part 2 algorithm / output / reuse / surface written
- [X] Amendment 2026-08-09b: Technician-Maushold probe, build-level contrast, phys/special
  OOS, Matcha Gotcha no-key decision
- [X] Implementation (on-demand `summarize_roster_role_structure`; Step A emission deferred)
