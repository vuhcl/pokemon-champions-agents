# single_locked condition-beneficiary partner discovery — discovery and design (2026-08-11)

**Status:** Discovery + design only. No beneficiary-discovery implementation in this pass.
Follow-up 2026-08-11b added source check + empirical ranking/target-role verification
(regression tests lock the sort/fallback claims; the resolver is still unbuilt).

**Trigger:** Manual CLI testing. Locking Pelipper (Rain Setter) and viewing partner-slot
candidates surfaces no rain-beneficiary logic — the first suggestion for a rain provider's
partner slot should plausibly include something that benefits from Rain (a Swift Swim user, a
rain-boosted attacker), and currently does not.

**Hypotheses under test (from the brief — verified below, not assumed):**

1. `single_locked` candidate discovery runs `query_support_needs` against the anchor's own
   kit — "what does Pelipper itself need from a partner," not "what does Pelipper's provided
   mechanism make a good partner for."
2. `condition_resilience` is the closest existing condition-aware mechanism, but is
   `multi_locked`-only and gap-driven (missing providers), not beneficiary-driven.
3. The Rain-need-resolution fix (move-derived `benefits_from` driving the *anchor's* own
   needs) is the mirror image; the reverse direction was never built.

**Explicitly out of scope (per brief):** any 1.0 reasoning-loop / steering work; ranking
changes beyond what's needed to surface beneficiary candidates at all; canonical name/form
resolution; `multi_locked` calc-unavailable labeled-degradation.

---

## Part 1 — verified current state

### 1. `single_locked`'s discovery chain has no path from anchor `provides` to beneficiary search

**Verdict: hypothesis 1 is correct.** Confirmed against source, then against a live Pelipper
probe.

#### The actual chain

`discover_single_locked` (`recommender/nodes.py:977-1041`) for a fully-locked single anchor
and a blank open slot:

1. `build_anchored_slot_fill_context(state, anchors[0])`
2. `annotate_overlap(context)`
3. `resolve_all_support_needs(context, state, ...)`
4. `merge_need_resolved(context)`
5. `run_slot_fill_terminal(...)`

That is the whole candidate-generation path. There is no other branch.

`build_anchored_slot_fill_context` (`recommender/slot_fill.py:170-232`) does classify the
anchor, including `provides`-tier mechanisms:

```196:209:recommender/slot_fill.py
    decision = classify_anchor_role(
        resolved,
        user_role=user_anchor_role,
        explicit_role=anchor_slot.role.value if anchor_slot.role.locked else None,
    )
    shape = derive_role_shape_context(decision)
    pokemon = resolved.as_pokemon()
    needs = query_support_needs(
        pokemon,
        shape,
        team_draft=state["team_draft"],
        state=state,
        regulation=regulation,
    )
```

Then it also runs `query_threat_counters(pokemon)` and returns
`AnchoredSlotDiscovery(context, resolved, decision, False)`.

**The decision is then thrown away.** `discover_single_locked` reads only
`discovery.context` (`nodes.py:1012-1016`). `SlotFillContext` has no field for
`AnchorRoleDecision` or its `mechanisms`. Downstream never sees Pelipper's Drizzle.

#### What the context actually carries

`derive_role_shape_context` (`anchor_roles.py:778-812`) is a one-way projection. The only
condition it copies onto `RoleShapeContext` is `needed_weathers`, and only from
`benefits_from` mechanisms (`needed`/`wanted`, present or `teammate_expected`):

```793:806:recommender/anchor_roles.py
    weathers: list[str] = []
    for m in decision.mechanisms:
        if m.relation != "benefits_from":
            continue
        if m.importance not in ("needed", "wanted"):
            continue
        if not (m.present or m.supply == "teammate_expected"):
            continue
        for item in m.evidence:
            if not item.startswith("condition:"):
                continue
            name = item.removeprefix("condition:")
            if name in _SHAPE_WEATHERS and name not in weathers:
                weathers.append(name)
```

`provides` is not read. Pelipper's `condition:Rain` tag never becomes a shape field.

`query_support_needs` (`support_needs.py:498-506`) is explicitly "named support-need
categories for an anchor; no ranking or candidate search." Every trigger is an ask *from*
the pokemon *to* a partner: attacker-universal cleric/screens, Contrary, defensive
asymmetry, tank-without-self-heal, Fake Out / Taunt, speed-axis Trick Room / Tailwind, and
`condition_setter` when the anchor itself depends on a field it does not already have
(`_speed_needs` + the `needed_weathers` pass at `:640-664`).

There is no "I provide Rain, find someone who wants it" category.

`resolve_all_support_needs` (`slot_fill.py:1170-1231`) only resolves `ctx.support_needs`
(or caller-supplied `anchored_needs`). `merge_need_resolved` unions those rows with
`query_threat_counters` output. `annotate_overlap` tags threat rows against the same
support-need list via `_NEED_SATISFIERS` — which for weather is `_NeedSatisfier(abilities=
ABILITY_TO_FIELD)`, i.e. **setters**, not beneficiaries (`slot_fill.py:77-94`).

#### Live Pelipper probe (2026-08-11, `resolve_anchor_build("Pelipper")`)

| Field | Value |
|---|---|
| `role_id` | `rain_setter` |
| `primary_function` | `support` |
| `secondary_role_ids` | `("tailwind_setter",)` |
| mechanisms | `provides`/`needed`/`present` Drizzle `condition:Rain`; `provides`/`wanted`/`present` Tailwind `condition:Tailwind` |
| `needed_weathers` | `()` |
| `query_support_needs` | **empty list** |

So for the reported CLI case, need-resolution has nothing to resolve. Every presented
partner comes from `query_threat_counters` (what answers the things that threaten
Pelipper). Rain-beneficiary logic is not "ranked too low"; it is **never generated**.

This matches the architecture, not a Pelipper-specific data miss. The same empty-need
shape showed up on Ninetales-Alola (Snow Warning) and Whimsicott (Tailwind). Torkoal and
Tyranitar do surface cleric / coverage needs — still zero beneficiary search.

Covered by existing tests, not inferred: `test_pelipper_primary_rain_secondary_tailwind_without_setup`
(`tests/recommender/test_anchor_roles.py:75-87`) already asserts Pelipper's Drizzle
`provides` Rain and that `derive_role_shape_context` does not treat it as setup. That test
never asks whether partner discovery *consumes* the provides row — because nothing does.

---

### 2. Existing query tools cannot express "find `benefits_from` matching condition X"

**Verdict: no public query tool does this. Two private slot-fill primitives can be
reused as the invert of the already-shipped emission tables. That is new discovery
*wiring*, not a new evidence source.**

| Tool | What it actually searches | Usable as beneficiary lookup? |
|---|---|---|
| `query_support_needs` | Named needs of **one** pokemon | No — it is the ask-suracer, and for a setter it often returns `[]` |
| `query_threat_counters` / `query_counters` | Type / matchup answers to the anchor's threats | No — orthogonal axis |
| `query_by_usage` | Rank a caller-supplied pool by usage, cut to `n` | **Yes, as a ranker of an already-filtered pool** — same role it already plays in `_resolve_condition_setter` / FO ability search (`slot_fill.py:895-921, 959-963, 1065-1069`). Cannot *find* Swift Swim users by itself |
| `query_teammates` | Usage co-occurrence with one species | Not in the `single_locked` chain (only `query_shared_teammates` on `multi_locked`, `nodes.py:1108, 1152`). Co-occurrence ≠ `benefits_from`. Rejected as the mechanism for this gap |
| `query_shared_teammates` | Intersection of N≥2 teammate lists | `multi_locked` only; needs two locked members |
| `role_category_evidence` / `role_candidates` | Shipped Role Compendium files under `data/roles/` | **Setter files only** for weather (`weather_setter_rain.v1.json`, sun/sand/snow) plus `trick_room_setter`, redirection, SD/NP. **No** `rain_attacker` / `trick_room_sweeper` / Tailwind-beneficiary file. `_compendium_roles_for_need` maps `condition_setter` → `weather_setter` (`slot_fill.py:966-977`) — again providers |
| `_species_with_abilities` | Legal species whose legality ∪ featured ability intersects a given id set | **Yes** — already used for FO-protection abilities and, via `_resolve_condition_setter`, for `ABILITY_TO_FIELD` setters |
| `narrow_candidates_for_move` | Legal species that learn a move | **Yes** — already used for TR/TW/Taunt/cleric/screens need resolution |

There is no `query_by_mechanism`, no reverse index of `MechanismEvidence` across the
species pool, and `classify_anchor_role` is per-build, not a dex scan.

`query_theme_refinement_candidates` does not exist in `recommender/` (historical ADR-022
name only).

---

### 3. The gap is not Rain-specific. Invertible evidence is.

**Verdict: the missing *branch* applies to every tracked condition. The *evidence that
branch can invert* does not.** Tracked set is already `("Rain", "Sun", "Sand", "Snow",
"Trick Room", "Tailwind")` (`recommender/condition_types.py:10`).

#### What `_mechanisms` actually emits today (`anchor_roles.py:430-609`)

**`provides` (present, `condition:{C}` tagged) — the input this new branch would read:**

| Condition | Automatic ability (`needed`) | Manual move (`wanted`, interruptible) |
|---|---|---|
| Rain / Sun / Sand / Snow | `ABILITY_TO_FIELD` weather abilities (Drizzle, Drought, Sand Stream, Snow Warning, …); Delta Stream excluded | `WEATHER_SETTING_MOVES` (Rain Dance etc.) |
| Tailwind | — | Tailwind move, `wanted` |
| Trick Room | — | Trick Room move, `needed` |

**`benefits_from` (the rows a beneficiary search would match) — not symmetric:**

| Condition | Kit-emitted, `present=True` | Strategic append, often `present=False` |
|---|---|---|
| Rain | Speed/utility abilities in `_NEEDED_CONDITION_ABILITIES` / `_WANTED_CONDITION_ABILITIES` ∩ `CONDITION_DEPENDENT_ABILITIES` (Swift Swim needed; Rain Dish / Hydration / Dry Skin / Forecast wanted); `CHARGE_INSTANT_WEATHER` move Electro Shot (`needed`) | `bulky_rain_attacker` when the kit has no present Rain benefit (`anchor_roles.py:723-740`) |
| Sun | Chlorophyll needed; Solar Power / Flower Gift / Leaf Guard / Protosynthesis / Forecast wanted; Solar Beam / Solar Blade | — |
| Sand | Sand Rush needed; Sand Force / Sand Veil wanted | — |
| Snow | Slush Rush needed; Snow Cloak / Ice Body wanted | — |
| Trick Room | **none** | `trick_room_sweeper` without Trick Room on the kit (`anchor_roles.py:704-721`) |
| Tailwind | **none** | **none** |

Live confirmation of the provider side (same probe): Torkoal `provides` Sun, Ninetales-Alola
`provides` Snow, Tyranitar `provides` Sand, Whimsicott `provides` Tailwind — all with
`needed_weathers == ()`. Archaludon is the mirror-image case that *does* work:
`benefits_from` Electro Shot / Rain → `needed_weathers == ("Rain",)` →
`condition_setter` need `field_condition:any:rain`. That is the earlier-this-session fix.
Nobody built the reverse.

#### Legal beneficiary pools via the existing invert primitive (Champions-legal, 2026-08-11)

`_species_with_abilities` against the current snapshot:

| Ability | Legal species (first names) |
|---|---|
| Swift Swim | 6: Qwilfish, Overqwil, Swampert-Mega, Basculegion, Basculegion-F, Beartic |
| Chlorophyll | 6: Venusaur, Vileplume, Victreebel, Leafeon, Whimsicott, Scovillain |
| Sand Rush | 3: Excadrill, Lycanroc, Houndstone |
| Slush Rush | 1: Beartic |
| Solar Power | 3: Charizard, Houndoom-Mega, Heliolisk |
| Sand Force | 4: Steelix-Mega, Garchomp-Mega, Hippowdon, Excadrill |
| Rain Dish | Blastoise, Pelipper |
| Hydration | Vaporeon, Goodra |
| Dry Skin | Toxicroak, Heliolisk |

Kingdra and Barraskewda have Swift Swim in the dex and are **not** Champions-legal
(`is_species_legal` False). A correct invert will not invent them. Swampert (base) is
legal with Torrent, not Swift Swim; Swampert-Mega is the Swift Swim form — the same
legality-vs-featured union `_species_with_abilities` already uses for setter search.

`CHARGE_INSTANT_WEATHER` (`matchup.py:278-282`) is exactly `{solarbeam, solarblade → Sun;
electroshot → Rain}`. Archaludon is the live Electro Shot user (`featured_moves` includes
it). There is no Sand/Snow charge-move equivalent.

#### What is *not* in the mechanism model (do not invent)

- Generic Rain-boosted Water STAB. Hurricane accuracy in Rain. Weather Ball type change.
  Those are real mechanics; they are not `benefits_from` rows. Pelipper's own Hurricane /
  Weather Ball are on the *provider*, not a partner ask.
- Tailwind dependents. There is no Tailwind-analog of Swift Swim and no strategic
  `benefits_from` append.
- Trick Room sweepers as a searchable kit table. The only TR `benefits_from` is a
  declared-role append on an already-classified build. There is no
  `data/roles/trick_room_sweeper.v1.json` to reverse-lookup.
- Terrains. `CONDITION_DEPENDENT_ABILITIES` includes Surge Surfer / Quark Drive / Grass
  Pelt / Mimicry, but those are not in `_NEEDED`/`_WANTED` emission (and terrains are not
  in `TRACKED_CONDITIONS`). Out of scope here.

**So:** an anchor providing any of the six tracked conditions *should* run the same
branch. Weather providers will actually surface names. A Tailwind-only or Trick-Room-only
provider will run the branch and correctly get an empty extra set, unless/until
`benefits_from` emission for those two is extended — that extension is a separate
evidence-producer task, not this one.

---

### 4. `condition_resilience` is not this feature, and would not paper over it

**Verdict: hypothesis 2 is correct.**

`assess_condition_resilience` (`condition_resilience.py:93-169`) walks locked
`AnchorRoleDecision.mechanisms`, using `mechanism_condition` (the `condition:{C}` tag) to
count **providers** (`present` + `provides`) and **dependents** (`benefits_from` +
`needed`/`wanted` + present-or-`teammate_expected`). It then classifies
essential/preferred/optional and emits a **gap** of `missing_provider` /
`single_provider_spof` / `none`.

Callers: `discover_multi_locked` and `refresh_team_signals` only (`nodes.py:1111, 1156`).
`discover_single_locked` never calls it. `gap_support_needs` (`:188-239`) turns gaps into
**setter** `SupportNeed`s (`condition_setter` / `trick_room` / `tailwind`) for
`resolve_need_candidates` — still "find a provider," the same direction as the anchor's
own `condition_setter` ask.

On a lone Pelipper it would not even try. With one provider and zero dependents, the Rain
row classifies **optional** (`provider_count` truthy, no needed/wanted dependents, and
`_preferred_setter_direction` requires setter **and** an offense partner —
`condition_resilience.py:74-90`). Optional rows get `gap="none"`. `gap_support_needs`
skips `gap==none`. The missing partner is the dependent, which this function is not
designed to hunt.

ADR-028 states this scope explicitly: generation-primary consumption is "a gapped
essential/preferred condition generates **backup-setter** candidates." Not beneficiaries.

---

## Part 2 — design proposal

### 1. Additional candidate-generation branch in `single_locked` only

**Proposal (not implemented):** after the existing need-resolution pass, run one extra
deterministic invert of the anchor's present `provides` mechanisms, and merge those
species through the path that already exists (`need_resolved_candidates` →
`merge_need_resolved`).

Hook, smallest possible:

`discover_single_locked` already holds `discovery.anchor_role_decision` and ignores it.
Keep the current `query_support_needs` → `resolve_all_support_needs` pass unchanged.
Between that and `merge_need_resolved`, append rows from a new private helper (name
bikeshed: `resolve_condition_beneficiaries`). Do not replace need search. Do not call
`assess_condition_resilience`. Do not add a public ADR-022 query tool — the invert is the
same kind of private resolver as `_resolve_condition_setter`.

Algorithm:

1. From `decision.mechanisms`, take `present` + `relation=="provides"` +
   `importance in {needed, wanted}`. Map each to a tracked condition via the existing
   `mechanism_condition` helper (`condition_resilience.py:52-65`) — same tag the emitter
   already stamped (`condition:Rain`, etc.). Deduplicate. Drop anything not in
   `TRACKED_CONDITIONS`.
2. For each provided condition `C`, collect candidate species by **inverting the same
   tables `_mechanisms` uses to emit `benefits_from`**, not by classifying the dex:
   - Ability ids in `_NEEDED_CONDITION_ABILITIES ∪ _WANTED_CONDITION_ABILITIES` whose
     `CONDITION_DEPENDENT_ABILITIES` weather canonicalizes to `C` → existing
     `_species_with_abilities`.
   - Move ids in `CHARGE_INSTANT_WEATHER` whose weather canonicalizes to `C` → existing
     `narrow_candidates_for_move` / `_narrow_need_candidates`.
3. Exclude **every currently-locked slot's lineage**, not a Pelipper name check. Reuse
   `lineage_ids` the same way `merge_multi_locked_candidates` already does
   (`team_candidates.py:224-237`): build `locked_lineages` from all locked members, drop
   any candidate whose `to_id` is in that set. Contract locked by
   `test_locked_anchor_lineage_exclusion_is_species_agnostic` (Pelipper, Torkoal,
   Tyranitar, Ninetales-Alola, Whimsicott, plus Mega/base pairs). Resolver is still
   unbuilt; implementation must call this primitive, not special-case Rain Dish.
4. `_rank_by_usage` the union after lineage exclusion. Needed-tier-before-wanted is not
   required. Unresolvable kit hits (Qwilfish) are **safe by 3c**, not by Rain usage-rank
   coincidence — see follow-up §C. Do not add a presentation-time resolvability filter.
5. Append onto `ctx.need_resolved_candidates`; `merge_need_resolved` already unions by
   species id (`source="need"` or `"both"`).

Reuse, not reinvent: `condition:{C}` tags, `mechanism_condition`,
`CONDITION_DEPENDENT_ABILITIES`, `_NEEDED`/`_WANTED` ability sets,
`CHARGE_INSTANT_WEATHER`, `_species_with_abilities`, `narrow_candidates_for_move`,
`query_by_usage` via `_rank_by_usage`, `merge_need_resolved`.

**Do not** scan every legal species through `classify_anchor_role`. That would re-derive
what the emission tables already know, and would still miss Tailwind/TR kit dependents
that those tables do not emit.

**Do not** map this onto `NeedCategory="condition_setter"` or
`_CONDITION_SETTER_TARGET_ROLES`. Those exist to request a *setter*. Routing beneficiaries
through them would label the open slot `rain_setter` — the exact wrong target role.
`target_role_from_needs` (`slot_fill.py:342-398`) has no rain-attacker mapping today
(`TargetRoleId` has `rain_setter`, not `rain_attacker`). Leave target-role derivation
untouched; kit fallback (`_kit_fallback_target_role`) already labels the candidate from
its own kit. Adding `*_attacker` target roles is a separate vocabulary task, out of
scope.

**NeedCategory:** add one literal, `condition_beneficiary`, so `matching_needs` stays
typed and `_NEED_TARGET_ROLES` can keep ignoring it. Put a `SupportNeed` on each
beneficiary row (`trigger` like `field_condition:provided:rain`, `notes` naming the
anchor mechanic). Do not add it to `_NEED_SATISFIERS` unless overlap-tagging threat rows
that happen to be beneficiaries is wanted later — not required to surface names that are
absent from the threat list.

#### Why this surfaces in the presented top-3 without a ranking redesign

**Empirically confirmed** (follow-up §B.1), not just sort-key reasoning. Injecting a
Swampert-Mega need-only row with `matching_needs` length 1 into a Pelipper-shaped empty
`support_needs` context, against eight threat rows with `verified_score` up to 99, makes
Swampert-Mega the presented **default**. Locked by
`test_unmapped_need_only_beneficiary_is_presented_default_over_high_score_threats`.

`present_candidates` → `pick_default_and_alternatives` keeps the sorted default plus two
alternatives (`move_narrowing.py:577-585`). `_sort_annotated` (`slot_fill.py:1255-1267`)
is `(compendium_rank, -len(matching_needs), -verified_score, usage_rank)`.

Consequence, not a bug: with ≥3 beneficiary-only rows, the entire presented trio can be
beneficiaries (threat-only rows have `matching_needs=()`). That matches the Pelipper CLI
gap. Do not add a mix-with-threats stage unless a later pass asks for it.

When the setter *does* have other needs (Torkoal's cleric / coverage), beneficiaries
interleave with those need rows on equal `matching_needs` length. Threat rows that also
satisfy a need keep their verified-score advantage. Alongside, not a replacement.

### 2. Evidence labeling

Reuse `CandidateEvidence` as-is. Match the closest shipped mechanism-driven resolver,
which is `_resolve_condition_setter` → `_mechanical_rows` (`slot_fill.py:924-933,
1018-1028`):

| Hit kind | `basis` | `confidence` | `producer_name` | `evidence` tokens (illustrative) |
|---|---|---|---|---|
| Ability invert (Swift Swim, Chlorophyll, …) | `mechanical_only` | `low` | `resolve_condition_beneficiaries` (or keep `_species_with_abilities` for the ability slice) | `need:condition_beneficiary`, `condition:Rain`, `ability:swiftswim`, `importance:needed`, `relation:benefits_from` |
| Charge-move invert (Electro Shot, Solar Beam) | same as `_narrow_need_candidates` already: `usage_backed`/`medium` when `commitment_pct` exists, else `mechanical_only`/`low` | (existing) | `narrow_candidates_for_move` | existing move tokens plus `condition:Rain` / `relation:benefits_from` |

Do **not** promote ability hits to `usage_backed` just because `_rank_by_usage` ordered
them. `_resolve_condition_setter` does not; usage is sort order, not basis. Do **not**
use `compendium_backed` — there is no beneficiary compendium file. Do **not** use
`synthesized`.

`branch="need"` is the existing `CandidateBranch` value (`state.py:162`). A new
`"beneficiary"` branch is unnecessary for v1; `producer_name` + `condition:` /
`relation:benefits_from` tokens already distinguish direction. `source` stays `"need"` or
`"both"` via `merge_need_resolved`.

### 3. Relation to `multi_locked` `condition_resilience`

These are opposite questions on the same mechanism object. They must not be collapsed.

| | `single_locked` beneficiary branch (this proposal) | `multi_locked` `condition_resilience` (ADR-028, shipped) |
|---|---|---|
| When | Exactly one locked member | Two or more locked members |
| Reads | Anchor `provides` | Whole locked set: `provides` **and** `benefits_from` |
| Asks | "This anchor provides C. Who wants C?" | "Is C essential/preferred, and is provision of C missing or SPOF?" |
| Generates | Species with kit-emitted `benefits_from` C | Backup **setters** for a provider gap |
| Empty case | Tailwind/TR provider → extra set `[]` (honest) | Lone Pelipper → Rain `optional`, `gap=none`, generates nothing |

No conflict: a later `multi_locked` turn with Pelipper + Mega Swampert would then see
Rain as essential/preferred with `provider_count=1` and could ask for a backup setter.
That is the intended sequel, not a duplicate of this branch.

**Known ceiling, not this task:** `multi_locked` with a setter plus partners that are
*not* beneficiaries still will not hunt dependents. Adding this invert there is a
follow-up if the same CLI gap shows up at two locks. YAGNI until it does.

### 4. Deterministic, tool-driven — not 1.0 reasoning-loop work

Every input is already on disk or already computed for this turn:

- `AnchorRoleDecision.mechanisms` from `classify_anchor_role` (already runs)
- Ability / move tables that emit `benefits_from`
- Legality snapshot + `is_species_legal`
- `narrow_candidates_for_move` / `_species_with_abilities` / `_rank_by_usage`

No LLM call, no free-form "who pairs with rain," no new live web search. Same epistemic
tier as every other 0.1.x slot-fill resolver. Consistent with ADR-014 (offline data) and
with "mechanical claims go through tools, never asserted text."

---

## Rejected alternatives

| Alternative | Why not |
|---|---|
| Teach `query_support_needs` to emit a fake "I need a Swift Swim user" need from `provides` | Wrong tool. ADR-022: it surfaces the *anchor's* support needs. Stuffing the inverse into it conflates the two directions the Rain-need fix just separated |
| Run `assess_condition_resilience` on one lock | Classifies Rain optional, generates no candidates (Part 1 §4) |
| `query_teammates(Pelipper)` | Not in this chain; usage correlation, not `benefits_from` |
| Classify every legal species, filter `benefits_from` | Dex-wide `classify_anchor_role`; slower; still empty for Tailwind/TR; re-implements the emission tables |
| Water-type / Hurricane-accuracy scan for "rain-boosted attackers" | New evidence source. The brief forbids that. Electro Shot is the rain-boosted attacker the model already knows |
| Invent Tailwind/TR beneficiaries from Spe-tier heuristics | That is `query_support_needs` Layer 3 *for the dependent*, inverted without a `benefits_from` row. Separate evidence-producer task |
| New public `query_condition_beneficiaries` ADR-022 tool | One caller. Private helper next to `_resolve_condition_setter` is enough |
| New `_sort_annotated` stage | `matching_needs` length already lifts these above Pelipper's threat-only list |
| Wire this into `multi_locked` in the same change | Brief is `single_locked` specifically |

---

## Acceptance checks for a later implementation pass

1. Lock Pelipper (usage Drizzle). Partner-slot presentation includes at least one
   Champions-legal kit-emitted Rain beneficiary (Basculegion / Archaludon / Swampert-Mega
   are the needed-tier live pool; do not hardcode the name — assert `benefits_from` /
   `condition:Rain` evidence on a presented option). Locked Pelipper is not a candidate.
   If an unresolvable kit hit is selected, 3c rediscovers — it is not a hard dead-end.
2. Existing need-resolution for non-providers unchanged (Archaludon still asks for a Rain
   setter; Kingambit TR-sweeper still asks for TR).
3. Whimsicott (Tailwind `provides`, no `benefits_from` invert) does not crash and does not
   fabricate Tailwind dependents.
4. Locked Pelipper is not nominated via its own Rain Dish.
5. Illegal Swift Swim users (Kingdra, Barraskewda) stay out.
6. Evidence on ability hits is `mechanical_only` / `low` unless a charge-move path already
   carries usage commitment.
7. `discover_multi_locked` / `assess_condition_resilience` behavior unchanged.
8. No LLM in the new path.

---

## Proposed log / ADR text (for the Claude Project — not written to the repo mirrors)

### Project log (2026-08-11)

`single_locked` partner discovery does not consider what the locked anchor *provides*,
only what it *needs*. Verified against source and a live Pelipper probe: `classify_anchor_role`
already emits present `provides`/`needed` Drizzle tagged `condition:Rain`, but
`derive_role_shape_context` only projects `benefits_from` into `needed_weathers`,
`query_support_needs(Pelipper)` returns `[]`, and `discover_single_locked` discards the
`AnchorRoleDecision` after building `SlotFillContext`. Presented partners are therefore
threat-counters only. `condition_resilience` cannot fill this — it is `multi_locked`-only
and hunts missing *providers*. The Rain-need-resolution fix was the opposite direction
(anchor dependence → setter search). Design in
`docs/single_locked_condition_beneficiary_discovery_and_design_2026-08-11.md`: an extra
`single_locked` invert of kit-emitted `benefits_from` tables, merged through existing
need-resolution, no new evidence source, no 1.0 reasoning loop. Not yet implemented.

### ADR draft (new, if implementing; letter-suffix amendment if folding into ADR-022/028)

**Decision:** In `single_locked` only, generate partner candidates that kit-emit
`benefits_from` for a condition the locked anchor already `provides` (present,
`needed`/`wanted`, `condition:{C}` tag). Invert the existing ability/charge-move emission
tables via `_species_with_abilities` and `narrow_candidates_for_move`; merge through
`need_resolved_candidates`. Label ability hits `mechanical_only`/`low`. Do not extend
`query_support_needs` or `assess_condition_resilience`. Tailwind/Trick Room providers may
legitimately yield an empty extra set until `benefits_from` emission exists for them.

**Why:** The mechanism model already encodes both directions. Consumption was one-way.
A lone weather setter's own support-need list is often empty, so the missing invert is
the entire partner story, not a ranking miss.

**Not:** generic Water-STAB rain boost; Tailwind/TR Spe-tier invention; dex-wide
reclassification; `multi_locked` wiring; a new ranking stage; a Role Compendium
`weather_beneficiary` category (ADR-015 Amendment 2026-07-28d already rejected that
membership type; no M-B VGC Role Compendium thread exists).

---

## Follow-up 2026-08-11b — Role Compendium source + empirical verification

### A. Role Compendium source check

#### A.1 Regulation mismatch — no M-B VGC Role Compendium thread

Cited URL is **Reg M-A**:
[VGC Regulation M-A Role Compendium](https://www.smogon.com/forums/threads/vgc-regulation-m-a-role-compendium.3782099/)
(thread 3782099, started 2026-05-07, last OP edit **2026-06-14**).

Searched for an M-B-specific VGC counterpart (exact phrase `"VGC Regulation M-B Role Compendium"`, Champions forum listing, M-B metagame / speed-tier resources). **None exists.** What does exist under M-B:

- [VGC Regulation M-B Speed Tiers](https://www.smogon.com/forums/threads/vgc-regulation-m-b-speed-tiers.3784081/) — speed table, not roles.
- [VGC Reg M-B Metagame Discussion](https://www.smogon.com/forums/threads/vgc-reg-m-b-metagame-discussion-thread.3784070/).
- [Champions OU Role Compendium [Updated for Reg M-B]](https://www.smogon.com/forums/forums/champions.1019/) — **singles OU**, wrong format.

The M-A OP itself treated the 2026-06-14 pass as terminal: "likely the final changes, as
M-B comes out super soon!" They did not continue the thread into M-B.

**Does the M-A *category* likely still hold for M-B?** The *name* of the bucket
(weather beneficiaries) is still a real doubles concept — M-B speed tiers still list
weather-speed users (Swampert-Mega 2×, Venusaur Chlorophyll, Excadrill Sand Rush). The
*membership and tiers* of the M-A thread must **not** be copied. Standing rule
(ADR-015 Amendment 2026-07-28d): the Smogon compendium is taxonomy seed only, never
membership or tier truth; the same amendment already names M-B relative-standing shifts
(Grimmsnarl vs Sableye screens) as a reason ranking must be recomputed per regulation.
Stated, not assumed: category concept likely still worth naming; M-A species lists are
not M-B-applicable membership.

#### A.2 Content — yes, Weather Beneficiaries exist on the M-A thread

Cited from the OP clarifications (not inferred):

> Weather Beneficiaries ARE NOT Pokemon benefits from that weather for a simple reason,
> such as Rain beating out Fire for Scizor (just an example). This also means that there
> will not be Volcarona under Sun Beneficiaries because Heat Wave gets boosted from the
> sun. There will be exceptions, however, like Archaludon and Mega Dragonite on Rain and
> Typhlosion-H on sun because they are staples of their respective archetype.

Section headers in the OP (sprites did not survive markdown conversion, so the **green/
yellow/red species under each header are not recovered from this fetch** — changelog
posts are the citable membership crumbs):

- Weather Beneficiaries → Rain / Sun / Snow / Sand
- Weather Setters → Rain / Sun / Snow / Sand (separate supportive section)
- Terrain Beneficiaries (direct boost only: Expanding Force, Quark Drive; not
  "Amoonguss safe from Extreme Speed")

Changelog crumbs (pengu, 2026-06-06 / 2026-06-14):

- Rain Beneficiaries: Meganium-Mega yellow→red, then **removed**; Politoed yellow→green
- Sand Beneficiaries: Tyranitar green→yellow
- Rain Setters separately: Sableye, Maushold, Vivillon, Froslass-Mega, Politoed

That is enough to confirm the category is real and distinct from setters. It is **not**
enough to import a membership list.

#### A.3 Do not build this as a Role Compendium category for this task

Feasibility of `construct_role_category` + critic: **not a small add.**
`construct_role_category` (`role_compendium.py:600-658`) only has kinds
`redirection`, `trick_room_setter`, `setup_attacker`, and default
`_construct_weather_setter`. No `weather_beneficiary` branch. Shipped `data/roles/`
files are setter / redirection / SD / NP only.

More important: **ADR-015 Amendment 2026-07-28d already decided this.** Quote:

> Weather/condition "Beneficiary" buckets are usage-discovered mechanical facts, not a
> separate third membership type, and exclude setters by convention.

Type (a) = catalogued table interactions (the amendment names **Swift Swim, Electro
Shot, Hurricane**). Type (b) = obscure-but-real interactions found via usage (Mega
Meganium ability+typing, Palafin Water-move density). The same amendment called out the
M-A source as unreliable *specifically on this bucket* (Mega Froslass, Alolan Ninetales,
Mega Gardevoir padded in as popular attackers on weather teams, not genuine
beneficiaries). Importing M-A membership would repeat that failure. Building a new
Compendium kind would relitigate that ADR.

**Design direction unchanged:** mechanical-table inversion is the interim *and* the
ADR-aligned type-(a) path. Compendium-first admission is **out of scope** unless the
user explicitly reopens ADR-015 2026-07-28d.

Concrete future upgrade (type b, not a new category file): usage-discovered obscure
Rain interactions the invert tables miss (Hurricane is already named as type a in that
ADR — optional add to the invert, not a Compendium build). No M-B thread to seed from.

---

### B. Empirical verification (both claims)

#### B.1 Ranking — no new stage needed, proven by test, with one order caveat

Injected post-merge shape (Pelipper `support_needs=[]`, eight threat rows with
`verified_score` 99→30, Swampert-Mega as need-only with an unmapped `SupportNeed`):
`present_candidates` default is **Swampert-Mega**. Locked by
`test_unmapped_need_only_beneficiary_is_presented_default_over_high_score_threats`
(`tests/recommender/test_slot_fill.py`).

The sort-key argument was correct for *surfacing*. It was incomplete for
*which* beneficiaries occupy the trio:

Live `_rank_by_usage` of the Rain invert pool (ability tables + Archaludon):

| # | Species | Kit fallback? |
|---|---------|----------------|
| 1 | Basculegion | yes (`fast_physical_attacker`) |
| 2 | Archaludon | yes (`bulky_special_attacker`) |
| 3 | Pelipper | yes — **must lineage-exclude** |
| 4 | Blastoise | yes |
| 5 | Vaporeon | **no** |
| 6 | Qwilfish | **no** |
| 8 | Swampert-Mega | yes |

Needed-tier-before-wanted (previous draft) would present Basculegion, Archaludon,
**Qwilfish**. Qwilfish has Swift Swim and `classify_anchor_role` → `kit_role=None`,
`role_id=unresolved`, `_kit_fallback_target_role` → `None`. Choosing it yields
`UnresolvedSlotRefinement(reason=unresolved_target_role)`
(`test_need_only_without_kit_role_still_unresolved_on_refine`) — then 3c rediscovers
(§C), so it is not a hard dead-end.

**Revised intra-beneficiary order:** usage-rank the union after lineage exclusion.
Do not needed-first. After dropping Pelipper, the natural top-3 are Basculegion,
Archaludon, Blastoise — all refine. Swampert-Mega is #8 in that mixed pool; Basculegion
still supplies the Swift Swim default.

#### B.2 Target role — kit fallback fires for the plausible picks, not for every table hit

`condition_beneficiary` is absent from `_NEED_TARGET_ROLES` and
`_CONDITION_SETTER_TARGET_ROLES` (`test_condition_beneficiary_is_not_a_target_role_mapping`).
Pelipper `support_needs=[]` → `derive_target_role` → `None`. A need-only row whose
category is also unmapped takes:

`_candidate_target_role` → `None` → `_resolved_candidate_target_role` →
`_kit_fallback_target_role` (the 3a path, `slot_fill.py:442-475, 467-475`).

Swampert-Mega: `TargetRoleDecision(fast_physical_attacker,
producer_name=slot_fill_kit_role_policy)`, **not** `rain_setter`. Choose +
`build_provisional_slot` → `ProvisionalSlot`, not unresolved. Locked by
`test_unmapped_need_only_swampert_mega_uses_kit_fallback_and_refines`.

Same fallback succeeds for Basculegion, Basculegion-F, Archaludon, Blastoise. It
**fails** for Qwilfish, Overqwil, Beartic, Vaporeon, Toxicroak, Castform forms,
Heliolisk, Goodra. That is not a new dead-end class — it is the pre-3a unresolved-kit
case. **Do not add a presentation filter.** Safety is 3c (`_route_after_refine`):
`refine_provisional_slot` sets `provisional_slot=None` for any `UnresolvedSlotRefinement`
reason, including `unresolved_target_role`; the graph then rediscovers. Proven with a
real (not mocked) Qwilfish refine:
`test_unresolved_target_role_refine_rediscovers_pending_presentation`. Rain usage-rank
keeping Qwilfish out of today's top-3 is UX coincidence, not the safety mechanism.
Do not add `condition_beneficiary` to `_NEED_TARGET_ROLES` later — that would
label the open slot a fake setter/attacker role and skip kit fallback.

---

### C. Safety mechanism chosen (2026-08-11c) — 3c, not a resolvability filter

**Question 1 — locked-anchor exclusion.** Design: general. Primitive: `lineage_ids` of
every currently-locked species, identical to `merge_multi_locked_candidates.eligible`.
Not a `"Pelipper"` string check. Not implemented in a beneficiary resolver (that
function does not exist yet); the contract is tested independently. Tyranitar also
excludes Tyranitar-Mega; Ninetales-Alola also excludes base Ninetales; locking Swampert
excludes Swampert-Mega.

**Question 2 — unresolvable beneficiaries on Sun/Sand/Snow.** Actual design: **(b)
safe by construction via 3c.** `_route_after_refine` (`graph.py:48-52`) branches only
on `provisional_slot is not None` → `END`, else `route_team_phase`. It does not read
`reason`. `refine_provisional_slot` (`nodes.py:458-466`) clears `provisional_slot` for
every `UnresolvedSlotRefinement`, including `unresolved_target_role`. Graph-path test
selects Qwilfish from a real Pelipper-locked `single_locked` pending, runs real
`build_provisional_slot`, and gets a new `candidate_selection` pending (Basculegion),
not `END`.

Rejected (a): a presentation-time kit-fallback filter. Extra code for a case 3c already
handles on every tracked condition. Add only if rediscovery *re-offering* the same
unresolvable default becomes a real UX loop — that is a prompt loop, not a hard
dead-end, and is not in scope until observed.
