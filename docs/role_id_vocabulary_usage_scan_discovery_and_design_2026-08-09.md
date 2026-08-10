# Role_id vocabulary expansion via usage scan — discovery and design (2026-08-09)

**Status:** Discovery + design only. No implementation in this pass.

**Motivation:** Roster role-structure grouping found that a Technician, fast-physical +
disruption Maushold build lands on generic `bulky_attacker` via `infer_role`'s
ability-blind fallback, because no classification tier recognizes anything more specific
([`docs/roster_role_structure_grouping_discovery_and_design_2026-08-09.md`](roster_role_structure_grouping_discovery_and_design_2026-08-09.md)
§1.4). ADR-015 Amendment 2026-07-28d already named the same real case as missing from
community source lists: *"Maushold's real attacker case (Technician + Population Bomb +
Tidy Up) absent entirely"* (`docs/architecture_decisions.md`).

**Critical scoping (do not default to new Compendium files):** the Role Compendium is the
heaviest `role_id` tier — constructor/critic-verified categories with admitted/rejected
membership. Many scan-surfaced patterns belong only at a lighter tier (`infer_role`
refinement or mechanism emission), without member lists or reverse-lookup evidence.

**Explicitly out of scope:** implementing any new Compendium file or classification rule;
roster role-structure grouping implementation; canonical name/form resolution;
selected-four / quick-pick.

---

## Part 1 — verified current state

### 1. Every current source of `role_id` (precise)

`classify_anchor_role` assigns **primary** `role_id` in a fixed priority cascade
(`recommender/anchor_roles.py:650-691`). Separately, `secondary_role_ids` are derived from
present needed/wanted mechanisms with a distinct `role_id` (`:746-754`). Those are related
but not the same producer.

#### Source A — Declared role (`user_role` / `explicit_role`)

| Property | Fact |
|----------|------|
| When | Non-empty after `_role_id(...)` normalize |
| Evidence | `AnchorRoleEvidence("primary_role", "user_confirmed", role_id)` |
| Vocabulary | **Opaque string** — not constrained to `RoleArchetype` or Compendium ids (ADR-024: `role_id` remains opaque). Live examples in tests: `bulky_rain_attacker`, `physical_rain_attacker` |
| To add a new value | Nothing in code — callers may pass any label. No membership verification. Does not expand automatic classification |

#### Source B — Role Compendium exact hit

| Property | Fact |
|----------|------|
| When | No declared role; `reverse_compendium_evidence(...).exact` non-empty; primary = `exact[0].role_id` |
| Exact rule | Species admitted in a shipped `data/roles/*.v1.json` **and** the candidate's named `mechanism` id is present in the build's moves **or** ability (`role_compendium.py:3233-3272`) |
| Also produced (not primary alone) | `species` (admitted but mechanism absent) and `rejected` tiers — used elsewhere; **do not** set primary `role_id` |
| Shipped files (8) | `weather_setter_{rain,sun,sand,snow}`, `redirection`, `trick_room_setter`, `swords_dance_attacker`, `nasty_plot_attacker` under `data/roles/` |
| Role ids emitted | `rain_setter` / `sun_setter` / `sand_setter` / `snow_setter` via `_strategic_role_id`; else category stem (`redirection`, `trick_room_setter`, …) (`:3175-3178`) |
| To add a new value | Full Compendium build: define `sub_criteria` + `construct_role_category` kind branch → admitted/rejected candidates with delivery `mechanism` → tiers → `critique_role_ranking` approval → `persist_approved` (`rebuild_role_category`, `:3303-3342`). Heaviest path |

#### Source C — Mechanism-based match

| Property | Fact |
|----------|------|
| When | No declared role; no exact Compendium; first present mechanism with non-null `role_id` wins (`:680-684`) |
| Producer | `_mechanisms(build)` (`:430-609`) |
| Role ids emitted today | Weather ability → `*_setter`; weather moves → `*_setter`; SD/NP/CM/Bulk Up → `swords_dance_attacker` / `nasty_plot_attacker` / `setup_attacker`; Tailwind → `tailwind_setter`; Trick Room → `trick_room_setter` |
| What is **not** emitted | Technician, Tidy Up, Encore, Bite, screens, Will-O-Wisp, Rage Powder / Follow Me (as mechanism rows), Hospitality / Friend Guard, Intimidate, Fake Out, etc. |
| To add a new value | Add a `MechanismEvidence` row with `role_id=...`, usually `relation="provides"` or `executes`, `importance` in `{needed, wanted}` so it can also feed `secondary_role_ids`. No admitted/rejected lists. Optionally mirror an existing need-satisfier / allowlist vocabulary — still not a Compendium file |

#### Source D — `infer_role` fallback

| Property | Fact |
|----------|------|
| When | No declared / exact / mechanism-role; and build has moves or item (`:686-689`) |
| Evidence | `("primary_role", <moves source>, "infer_role fallback")` |
| Vocabulary | Closed `RoleArchetype` Literal (`recommend.py:21-27`): `fast_attacker`, `bulky_attacker`, `bulky_pivot`, `trick_room_sweeper`, `support_speed_control` |
| Full decision logic | See §1.3 |
| To add a new value | Extend `infer_role`'s decision tree (and usually the `RoleArchetype` Literal + `role_spread` if spreads matter). Still ability-blind unless the function signature is widened. Lightest path for coarse kit archetypes |

#### Source E — Unresolved

Empty kit → `role_id="unresolved"`, `primary_function="unknown"`.

**Cascade summary:**

```text
declared → exact Compendium → first mechanism.role_id → infer_role → unresolved
```

---

### 2. What makes a category Compendium-worthy vs lighter-tier?

**Authoritative purpose** (ADR-015 Amendment 2026-07-28d): the Compendium exists to serve
*"I need something that fulfills a specific functional role"* — role-specific search —
**not** taxonomic completeness, and **not** "I just need something strong" (already covered
by usage/stats search). Explicit non-example: *"generalist attacker" isn't a doubles
category*.

**Properties shared by the eight shipped categories:**

| Shipped category | Delivery gate (enumerable) | Role-search question |
|------------------|----------------------------|----------------------|
| Weather setters ×4 | Ability (Drizzle, Drought, …) and/or weather move | "Who sets Rain/Sun/Sand/Snow?" |
| Redirection | Follow Me / Rage Powder | "Who redirects?" |
| Trick Room Setter | Trick Room | "Who sets Trick Room?" |
| Swords Dance / Nasty Plot Attacker | Named +2 setup move + offense exploit test | "Who is a real SD/NP attacker?" |

Common property: **widely differentiating, strategically named function** with a **clear
delivery mechanism**, where membership is contested enough to need **admitted vs rejected**
verification and tiering (constructor + critic). Modifier-only abilities (Prankster,
Regenerator) were explicitly rejected as primary categories — they attach to whatever role
the build already has (same amendment).

**Therefore lighter tier is appropriate when:**

- The pattern is a **coarse kit archetype** for spread/fallback only (Life Orb → fast,
  Leftovers → bulky pivot) → `infer_role`.
- The pattern is a **mechanical fact on the active kit** that should label primary or
  secondary function without a searchable membership list (Technician×multi-hit, Tidy Up
  setup, screens present, Encore present) → `_mechanisms` (± `infer_role` if it should
  change the coarse primary when no heavier hit exists).
- The pattern is **self-sustain or damage-profile detail** (Matcha drain, phys vs special)
  → usually neither Compendium nor new primary `role_id` (see roster-structure §1.6–1.7).

**Compendium is appropriate when:** someone would ask the recommender for candidates *by
that role name*, and wrong membership would be costly enough to justify constructor/critic
gates — not merely to escape `bulky_attacker`.

---

### 3. `infer_role` full decision logic (what it reads / ignores)

```46:57:recommender/recommend.py
def infer_role(moves: list[str], item: str) -> RoleArchetype:
    mids = {to_id(m) for m in moves}
    iid = to_id(item)
    if "trickroom" in mids:
        return "trick_room_sweeper"
    if "tailwind" in mids or iid == "choicescarf":
        return "support_speed_control" if "tailwind" in mids else "fast_attacker"
    if iid in {"sitrusberry", "leftovers", "rockyhelmet"}:
        return "bulky_pivot"
    if iid in {"lifeorb", "choiceband", "choicespecs"}:
        return "fast_attacker"
    return "bulky_attacker"
```

| Reads | Does not read |
|-------|----------------|
| Move ids (only Trick Room, Tailwind as special cases) | Ability (Technician, Friend Guard, Swift Swim, Prankster, …) |
| Item id (scarf / bulky berries+Leftovers+Helmet / LO+Choice attacking items) | Species, base stats, Speed tier, EVs, nature |
| | Multi-hit / priority / flinch / screens / status / setup beyond those two moves |
| | Compendium membership |

**Maushold-shaped gap at this tier alone:** fixable **in part** by teaching `infer_role` (or
a pre-fallback mechanism) to treat Technician + multi-hit and/or Tidy Up as non-default
offense — that does **not** require a Compendium file. It cannot express secondary
disruption (Encore) as a second function; that remains mechanism/`secondary_role_ids`
territory. Ability-blindness is also why Friend Guard vs Technician under-differentiate
when moves/items match (verified below).

---

### 1.4 Live usage probe (evidence for Part 2)

**Data reality for Reg M-B offline usage** (`recommender/usage_data.py`):

- `ingame_species_map`: **exactly 50** species with `usage_rank` (same N as `TEAM_THREAT_N`).
  Has `common_abilities` / `common_moves` / `common_items`; **`featured_sets` are empty**.
- `showdown_species_map`: **77** species with concrete `featured_sets` (typically one set).
- Representative kit for the probe: ability₀ + item₀ + moves₀₋₃ by usage pct.

**Cascade outcomes on all 50 ingame representatives** (2026-08-09 probe):

| Source that set primary `role_id` | Count |
|-----------------------------------|------:|
| `infer_role` fallback | **34** |
| Exact Compendium | 7 |
| Mechanism `role_id` | 9 |

So the coarse fallback is not a Maushold corner case — it is the **majority path** for
current top-usage kits.

**Motivating under-differentiation, present in top 50:** species display name
`Maushold Family of Four` (rank 25). Top ability in usage is Friend Guard; second is
Technician (≥5%). Same top moves/item → **both** classify `bulky_attacker` (`UNDERDIFF`).
That matches the roster-structure audit: ability is unused by `_mechanisms` and
`infer_role`.

**Other high-signal fallback / mislabel examples from the same probe** (illustrative, not
exhaustive implementation backlog):

| Kit (usage-shaped) | Landed `role_id` | Why interesting |
|--------------------|------------------|-----------------|
| Grimmsnarl / Prankster / Light Clay + screens-shaped moves | `bulky_attacker` | Support/screens identity collapsed to offense fallback |
| Archaludon / Stamina / Leftovers + Electro Shot kit | `bulky_pivot` | Item branch of `infer_role`; not rain-offense without declared role |
| Excadrill / Sand Rush / Focus Sash | `bulky_attacker` | Condition-dependent offense; ability ignored for primary |
| Incineroar / Intimidate / Sitrus + Fake Out / Parting Shot | `bulky_pivot` | Coarse item-driven label; Fake Out support not named |
| Whimsicott / Prankster + Tailwind | `tailwind_setter` (mechanism) | Works via Tailwind mechanism; Encore still unemitted secondary |

Ability-sensitivity scan (≥5% ability share, same moves/item): **every** multi-ability
species in the top 50 either under-differentiated or only "differed" when a non-ability
signal already fixed the label (e.g. Nasty Plot / Calm Mind / Tailwind mechanism). No case
where ability alone flipped primary `role_id`.

---

## Part 2 — design proposal

### 1. Scan methodology (proposed)

**Goal:** discover recurring functional patterns on real Reg M-B builds that no current
cascade tier names specifically — then triage each to Compendium / mechanism / `infer_role`,
not invent labels for completeness.

**Corpus (first pass):**

1. **Primary:** all 50 `ingame_doubles` species by `usage_rank` (already the offline top-N).
2. **Concrete sets:** all `showdown_vgc_mb` `featured_sets` (77 species) as a second pass
   over fully specified builds.
3. **Synthetic variants (required):** for each ingame species, also classify
   - ability₀ + item₀ + top-4 moves (baseline);
   - each ability with pct ≥ 5% holding moves/item fixed (under-differentiation detector);
   - optional: replace top-4 with alternate high-pct move clusters when move₄ and move₅ are
     both ≥ ~40% (captures dual sets like Sinistcha TR vs Life Dew without inventing sets).

**Per build, record:**

- Cascade winner (declared/exact/mech/`infer_role`/unresolved);
- `role_id`, `secondary_role_ids`, `primary_function`;
- Present mechanism kinds / role_ids (or empty);
- Flags: `infer_role_fallback`, `ability_ignored_underdiff`, `support_moves_present_but_offense_label`
  (heuristic: ≥2 of screens / Encore / Fake Out / redirection / Tailwind / Trick Room /
  Will-O-Wisp while `primary_function=="offense"` and fallback).

**Pattern extraction:** cluster flagged builds by shared mechanical signature (ability id,
setup move, support move set, item class) — not by species name. A pattern must appear on
**≥2 species** or on **≥1 top-20 species with clear mechanical gate** to enter the triage
list (avoids one-off lore).

**Outputs of the scan (artifacts, not code in this pass):** a gap table with proposed tier
per pattern. No auto-writing of Compendium JSON.

---

### 2. Tier triage for real gaps (from probe + known fixtures)

| Pattern | Evidence | Proposed tier | Why not heavier/lighter |
|---------|----------|---------------|-------------------------|
| Technician (+ multi-hit / Pop Bomb) offense | Maushold Family of Four underdiff; ADR-028d named absence | **Mechanism** (primary or strong secondary) **and/or `infer_role` refinement** | Role-search "give me a Technician attacker" is niche; membership list adds little vs detecting the ability×move gate on the active kit. **Not** default Compendium |
| Tidy Up as setup | Same Maushold attacker case; not in `_SETUP_MOVES` | **Mechanism** — extend setup map like Bulk Up → `setup_attacker` (or dedicated tidy_up role_id only if needed) | Same shape as existing CM/Bulk Up handling; Compendium setup attackers already cover SD/NP with membership contests |
| Friend Guard vs Technician underdiff | Top-50 probe | Fixed as **byproduct** of ability-aware mechanism/`infer_role` above; FG+Follow Me already Compendium `redirection` when redirect move present | Do not add `friend_guard_support` Compendium — Friend Guard is a modifier/secondary on redirection (shipped allowlist) |
| Screens / Light Clay / Grimmsnarl-shaped | Top-50 Grimmsnarl → `bulky_attacker`; roster Sableye gap | **Mechanism emission** of screens (± disruption) for `secondary_role_ids` / grouping — **not** automatic new Compendium | "Screens" can be role-search-worthy *later*; first need kit-proof emission. Full screens Compendium is optional Phase 2 if role-search demand is proven |
| Encore / WoW disruption on offense kits | Maushold + Sableye fixtures; Whimsicott Encore unemitted | **Mechanism** secondary (`disruption_utility` or reuse need vocabulary) | Incidental on many primaries; Compendium membership wrong shape |
| Condition speed abilities (Sand Rush, Chlorophyll, Swift Swim) primary still fallback | Excadrill / Venusaur / Basculegion-shaped | **Mechanism** already partially emits `benefits_from` for needed abilities when ability provenance allows — primary label may need **declared/strategic** or light **infer_role** only if we want `sand_attacker`-class primaries without user role | Beneficiary buckets are usage-discovered facts per ADR-028d, **not** a third Compendium membership type |
| Leftovers/Sitrus → `bulky_pivot` on non-pivots (Archaludon) | Top-50 Archaludon | **`infer_role` refinement** (e.g. require pivot move for `bulky_pivot`) and/or prefer mechanism Stamina durability without forcing pivot | Do not Compendium "Leftovers tank" |
| Fake Out / Intimidate support (Incineroar) | Top-50 | Defer: possible future Compendium **if** role-search "Fake Out support" is a product need; else mechanism tags only | Widely differentiating **candidate** for Compendium — but out of first cut unless scan shows systematic miss hurting slot-fill |
| Rain/special strategic labels (`bulky_rain_attacker`) | Only via declared today | Keep **declared** + existing benefits_from append path; usage scan may suggest auto-hints later — not Compendium-first | Already special-cased in classifier for declared rain attacker |

**Default rule for triage:** start at the lightest tier that makes the active kit's
function readable to `classify_anchor_role` and to roster grouping's function keys. Promote
to Compendium only when the scan shows a stable role-search category with contested
membership.

---

### 3. Connection to roster role-structure "Step A preconditions"

Roster grouping Step A preconditions
([`roster_role_structure_grouping_discovery_and_design_2026-08-09.md`](roster_role_structure_grouping_discovery_and_design_2026-08-09.md)):

- Sableye screens / WoW / Encore emission;
- Maushold Encore (same gap category);
- Optional Sinistcha Hospitality / Friend Guard ally-reinforce;
- Explicitly **not** Matcha Gotcha self-heal as a function key.

**Relation to this scan:**

| | Role_id vocabulary scan | Roster Step A emission |
|--|-------------------------|-------------------------|
| Primary question | Is the **primary** label too coarse / wrong tier? | Are **secondary functions** missing for contested/uncontested groups? |
| Typical fix | `infer_role` and/or mechanism `role_id` for primary | Mechanism rows (often secondary importance) feeding `secondary_role_ids` |
| Maushold Technician | In scope here (escape `bulky_attacker`) | Encore secondary still Step A |
| Sableye screens | May appear as a scan pattern (Grimmsnarl) | Closing emission is Step A / shared `_mechanisms` work |

**Verdict:** related producers (`_mechanisms`), **different enough in kind to stay separately
scoped**. Closing screens/Encore/Hospitality gaps is **not** an automatic byproduct of
"expand role_id vocabulary via usage scan," though the scan **feeds** that backlog with
frequency evidence (e.g. Grimmsnarl screens collapsed to `bulky_attacker`). Implementers
may batch shared `_mechanisms` edits carefully, but tracking/acceptance stay on two tickets:
(1) primary vocabulary / cascade fidelity, (2) roster-structure function emission.

---

### 4. First-pass sequencing / scope cut

**First cut (recommended):** Reg M-B viability of **primary classification fidelity** for
top-usage kits — not exhaustive coverage of every build.

1. **Run the scan artifact** (Part 2 §1) on ingame top-50 + showdown featured sets; publish
   the gap table with tier tags only (still no Compendium files).
2. **Implement lightest wins first** (separate implementation tasks, after this design):
   - `infer_role` fixes that remove clear false pivots / false bulky defaults (pivot-move
     gate; optional ability hooks for Technician / speed weather if kept in this tier);
   - `_SETUP_MOVES` / mechanism additions for Tidy Up and other high-frequency setup moves
     already analogous to Bulk Up;
   - Technician×multi-hit mechanism (or infer_role) so Maushold Family of Four underdiff
     closes without a Compendium category.
3. **Do not** open new Compendium categories in the first implementation wave unless the
   scan table marks a pattern `compendium-candidate` with an explicit role-search question
   and ≥N competing species — Fake Out support is the most plausible future candidate,
   still deferred pending product need.
4. **Keep** screens / Encore / Hospitality emission on the **roster role-structure**
   precondition track (may share `_mechanisms` PRs, different acceptance).
5. **Sequence vs roster grouping implementation:** this vocabulary/scan work may land
   *before or in parallel with* grouping implementation for the Technician primary label,
   but grouping's contested `attacker` bucket already works via `primary_function==offense`
   today — grouping is not blocked on a finer Maushold `role_id`. Finer labels improve
   human-readable structure summaries and future composition signals; they are not a hard
   gate for the first grouping summary.

**Explicit non-goals for first cut:** singles categories; terrain roles; beneficiary
Compendium files; phys/special splits; selected-four; inventing `role_id`s for every
Smogon forum tag.

---

## Acceptance checks (later implementation / scan execution)

1. Scan produces a gap table covering all 50 ingame species + showdown featured sets, each
   row tagged `compendium` | `mechanism` | `infer_role` | `defer` with one-line reasoning.
2. Maushold Family of Four Technician vs Friend Guard no longer share an identical primary
   when kits differ only by ability **or** the remaining equality is explicitly justified
   (e.g. both still offense but Technician gains a mechanism role_id / secondary).
3. No new `data/roles/*.v1.json` ships in the first implementation wave unless a gap row was
   tagged `compendium` with role-search justification.
4. Roster Step A items (screens/Encore/Hospitality) remain separately tracked even if
   `_mechanisms` PRs overlap.

---

## Scratchpad

- **Goal:** discovery + design for usage-driven `role_id` vocabulary expansion with correct
  tiering (not Compendium-default).
- [X] Enumerate role_id sources A–E with add-cost
- [X] Compendium-worthy criteria from ADR-028d + shipped 8
- [X] Full `infer_role` logic + ability blindness
- [X] Live top-50 probe (34/50 fallback; Maushold underdiff)
- [X] Scan methodology, triage, Step A relation, first-cut sequencing
- [X] Full corpus scan executed — results + coherent `infer_role` proposal in
  [`role_id_gap_scan_results_and_infer_role_proposal_2026-08-09.md`](role_id_gap_scan_results_and_infer_role_proposal_2026-08-09.md)
  (raw JSON: [`artifacts/role_id_gap_scan_2026-08-09.json`](artifacts/role_id_gap_scan_2026-08-09.json))
- [ ] Implementation (deferred)
