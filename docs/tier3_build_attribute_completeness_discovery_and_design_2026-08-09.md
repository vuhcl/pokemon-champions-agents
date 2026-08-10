# Tier-3 build attribute completeness — discovery and design (2026-08-09)

**Status:** Discovery + design only. No implementation in this pass.
**Design revision:** `_mechanisms` provenance gate + unique-only ability fill (2026-08-09
follow-up); non-hidden multi-ability guess withdrawn — see Part 2 §0–§1.

**Deferred-from:** slot-fill flow (Next-priority item 4: “Fill all tier-3 build attributes
deterministically”), ADR-023 Amendment 2026-08-08a residual (Track C rejects incomplete
provisional builds structurally, but does not guarantee every field), anchor-role /
target-role discovery (Case 4 synthesized-build finding: Hatterene manual completion),
ownership-propagation and calc-unavailable reports (listed as separately deferred). Always
correctly deferred; never previously traced end-to-end against current source for *both*
live paths (`recommend_build` and slot-fill `_refine_defaults`).

**Naming note (verified before design):** ADR-015’s written “tier 3” is **calc-driven
breakpoint verification**. Current code also labels `role_spread(...)` fallthrough as
`tier3_role` / `ref="tier3_role"`. Backlog item “tier-3 build attribute completeness” means
**last-resort completion of a confirmable provisional build when usage/cache miss**, not
“make `_tier3_verify_spread` fill attributes.” This report keeps both meanings explicit.

**Explicitly out of scope (per brief):** canonical name/form resolution; general usage
ingestion expansion as a product program (discussed only where Part 1 shows it is or is not
the fix); quick-pick / selected-four modeling.

---

## Part 1 — verified current state

### 1. What ADR-015 says vs what the code does

ADR-015’s three-tier strategy (`docs/architecture_decisions.md` ADR-015):

| Tier | ADR intent | Attribute target |
|------|------------|------------------|
| 1 | Known-build lookup (Champions-native → analogous → scoped live) | Full set: item, moves, SP spread, nature (ability implied by sources) |
| 2 | Role-pattern heuristic draft | Spread archetype from role; rationale; leftover-point allocation |
| 3 | Calc-driven breakpoint search | **Verify** tier-2 (and incomplete top-ups) against a small, role-relevant threat set — not invent identity fields |

Two live consumers implement different subsets:

#### A. `recommend_build` (`recommender/recommend.py`)

Assumes the caller already supplies **species + moves + item**.

Step order today:

1. Resolved-build cache hit → return cached spread (`source_tier: cache:…`).
2. Tier-1 exact usage match (`find_set_matching`); strip correlated EVs; else `lookup_live_build` (**stub, always `None`**); else assemble `{species, moves, item}` and optionally ability from `species_usage.common_abilities[0]`.
3. Legality + `diagnose_and_substitute` (item/move swaps only when the set is **illegal**, not when fields are missing).
4. Spread completeness:
   - full budget already → keep;
   - empty → `select_usage_spread` (tier-2 usage / live spreads) else `role_spread(infer_role(...))` labeled `tier3_role`;
   - partial → `_allocate_remainder` toward `role_spread` targets, labeled `tier1_partial`.
5. Optional `_tier3_verify_spread` **only if** `calculate_batch` is passed — KO smoke notes vs a **hardcoded** opponent list (`Kingambit`, `Garchomp`, `Incineroar`, …), not role-selected threats. Writes cache with `verified=True/False`.

**What this path fills:** spread (always, given moves+item); nature only when `select_usage_spread` returns one; ability only when usage lists one. It does **not** synthesize missing moves or items.

#### B. Slot-fill provisional path (the path that failed Hatterene)

`build_provisional_slot` → `_propagate_and_refine` → `_refine_defaults`
(`recommender/slot_fill.py:1343+`, `recommender/propose.py:221+`).

Attribute attempt order inside `_refine_defaults`:

1. **Ability / moves / item** via `featured_or_common_set` when any of those are needed.
2. On usage miss: **`assemble_moveset_fallback` for moves only** (`move_narrowing.py:562+`). Item and ability stay empty.
3. Soft Choice-item moveset bias (status moves stripped) when item is already Choice.
4. **Spread/nature path gated on `moves and item` both present.** Then:
   - cache spread (`get_resolved_build`);
   - else `select_usage_spread` (offline row or `fetch_live_spreads`);
   - else `role_spread(role | infer_role(...))` with `ReasonRef(kind="tier2_heuristic", ref="tier3_role")`.
5. Scarf Spe overshoot → nature correction only when Choice Scarf is **locked** and spread exists.

Dependency-circle pins **before** refine (Choice spreads, Trick Room → `role_spread("trick_room_sweeper")`, `infer_role` from locked moves) can fill role/spread without usage, but only from **already-locked** pins — not from a species-only + target-role seed.

**What this path attempts vs leaves empty:**

| Attribute | Filled from usage? | Last-resort synthesizer today? |
|-----------|--------------------|--------------------------------|
| Species | Seeded by intent | N/A |
| Role | Seeded by `TargetRoleDecision` | N/A (unresolved target role → separate `UnresolvedSlotRefinement`) |
| Ability | `featured_or_common_set` only | **No** |
| Item | usage only | **No** |
| Moves | usage, else `assemble_moveset_fallback` | Partial only (see §1.1) |
| Spread | cache / `select_usage_spread` / `role_spread` | **Yes, but only after moves+item exist** |
| Nature | usage featured nature or `select_usage_spread` | **No** under pure `tier3_role` |

##### 1.1 `assemble_moveset_fallback` ceiling

`preferred_move_ids` only has role prefs for `support_speed_control` and `trick_room_sweeper`, plus archetype components (`TrickRoom` → `trickroom`, etc.) and team-need flags. Most `TargetRoleId` values (including `trick_room_setter`, `fast_attacker`, `redirection`, setup attackers) contribute **no** preferred damaging moves. Fallback then appends Protect if legal and truncates to four — often **1–2 moves**.

Direct probe (this session):

- Hatterene + `trick_room_setter` + archetype `TrickRoom` → assembled `['trickroom', 'protect']`.
- Mimikyu + `fast_attacker` / `bulky_attacker` → assembled `['protect']` only.

`recommend_build`’s `_tier3_verify_spread` is **not** called from this path. Slot-fill “tier 3” in practice means the `tier3_role` spread table, not ADR-015 calc verification.

---

### 2. Failure mode when completion fails

`build_provisional_slot` post-checks seven fields and, on any miss, returns:

```317:322:recommender/state.py
@dataclass(frozen=True)
class UnresolvedSlotRefinement:
    schema_version: int
    intent: PendingSlotIntent
    unresolved_fields: tuple[str, ...]
    reason: Literal["incomplete_build", "unresolved_target_role"] = "incomplete_build"
```

Direct probe (this session), Hatterene + resolved `trick_room_setter`:

- Result type: `UnresolvedSlotRefinement`
- `reason`: `"incomplete_build"`
- `unresolved_fields`: `('ability', 'item', 'moves', 'nature', 'spread')`
- Partial progress retained on the working slot: moves `['trickroom', 'protect']`; item/ability/nature/spread `None`

`refine_provisional_slot` stores that object in `provisional_refinement` and clears `provisional_slot` (`nodes.py:435-465`). It does **not** crash, invent fake fields, or commit a partial lock.

**Verdict:** graceful structured failure is already correctly implemented (ADR-023 Amendment
2026-08-08a). The gap is **not** a correctness bug in failure handling. It is a
**coverage + last-resort synthesizer backlog**: the system correctly refuses to present an
incomplete build, but often cannot produce a complete one for out-of-snapshot species.

---

### 3. Real cases already surfaced (not hypothetical)

| Case | Source | What happened | Failure shape |
|------|--------|---------------|---------------|
| **Hatterene** | Slot-fill role-play (`docs/slot_fill_flow_discovery_2026-08-08.md` steps 17–19); restated in anchor-role Case 4 | No-usage refinement → only Trick Room + Protect; item, spread, nature, two moves empty; **manual** legal build constructed | Usage miss + incomplete moveset prefs + no item/ability/nature synthesizer → `incomplete_build` |
| **Mimikyu** | Same role-play steps 33–38, 214–235; team-phase routing discovery | Owned Mimikyu chosen; Expert Belt build synthesized **manually** in conversation; integrated snapshot has **no** Mimikyu row, so usage-backed move comparison silently unavailable | Same snapshot absence; **additional** symptom: usage evidence missing for ranking/comparison, not only provisional fill |
| **Clefable** | ADR-014 Amendment 2026-08-05a | Top-50 ladder snapshot excluded Clefable despite real Follow Me usage on site | Same **offline coverage cap** family; surfaced during Redirection construction, not provisional Hatterene path |

Re-checked against current offline snapshot (`data/usage` via `species_usage`):

- Snapshot still capped at ladder **rank ≤ 50** plus Mega/lineage rows (~80 merged species).
- `Hatterene`, `Mimikyu`, `Clefable` all still `usage=False` / `featured=False`.
- Control species from the same role-play with coverage (`Sinistcha`, `Farigiraf`, `Primarina`, `Ninetales`, …) still refine fully from usage.

**Are these one failure mode or several?**

One **shared trigger**: offline usage miss under the top-50 (+lineage) cap.

**Distinct consequences** once that trigger fires:

1. **Identity-assembly failure** (Hatterene provisional): cannot invent item/ability/full moves/nature → structured unresolved.
2. **Evidence-absence failure** (Mimikyu move comparison): consumers treat missing usage as “no signal” rather than “unknown / out of snapshot.”
3. **Discovery invisibility** (historical Clefable): species absent from construction-time usage queries until live CBD exception existed.

Hatterene and Mimikyu share (1) when run through `build_provisional_slot` today (direct Mimikyu probe also returns `incomplete_build` with the same five unresolved fields). Mimikyu’s backlog write-up additionally tracks (2).

---

### 4. Same as “Mimikyu / usage-coverage expansion” or separate?

**Separate issues that share a trigger.**

| | Mimikyu / usage-coverage expansion | Tier-3 attribute completeness |
|--|-----------------------------------|-------------------------------|
| Primary symptom | No usage row → usage-backed ranking/comparison/teammate evidence unavailable | Provisional refinement cannot emit `ProvisionalSlot` |
| Fix if only ingestion expands | Helps **if** Mimikyu/Hatterene enter the snapshot with usable featured/common sets | Reduces how often synthesis fires; **does not** define behavior when usage remains thin or live fetch fails |
| Fix if only algorithm improves | Does not restore usage percentages for comparison | Can still emit a **labeled synthesized** complete build |

Evidence that coverage alone is insufficient even for spreads/nature:

- With **manual** Hatterene moves+item, `_refine_defaults` can fill spread+nature via `select_usage_spread` / live spreads (`tier2_usage_live` observed this session).
- Ability remains `None` (no featured set).
- With live/offline spreads **mocked away**, pure `tier3_role` fills spread from `role_spread` but **still leaves nature and ability empty**.

So: expanding ingestion is the right fix for Mimikyu’s **usage-evidence** backlog. Completeness needs a **guaranteed last-resort constructor** regardless, because thin competitive usage and live-fetch failure are permanent edge cases ADR-015 already anticipated (“tier 2 is a rare edge case, not a coequal path” — ADR-016).

---

### 5. Existing fallbacks elsewhere (not reused for full-build synthesis)

| Mechanism | Location | What it does | Reused for missing identity today? |
|-----------|----------|--------------|-------------------------------------|
| `assemble_moveset_fallback` | `move_narrowing.py` | Role/archetype/need prefs + Protect | Yes for moves only; prefs too thin for most roles |
| `role_spread` / `infer_role` | `recommend.py` | Five hardcoded SP tables | Yes for spread after moves+item |
| `select_usage_spread` / `fetch_live_spreads` | `usage_spreads.py` | Real variants offline or live | Spreads/nature only; not moves/item/ability |
| `diagnose_and_substitute` | `recommend.py` | Life Orb / Sitrus / Focus Sash when item **illegal** | **Not** for missing item |
| Choice / TR dependency pins | `propose.py` | Spread from locked item/moves | Requires locks already present |
| `lookup_live_build` | `recommend.py` | ADR-014a exception | Stub `None` |
| Smogon writeup seed (incl. Hatterene) | `scripts/extract_usage/fetch_smogon_writeups.py` | Offline cache population | `data/resolved-builds/` currently **empty** (0 JSON); unused at runtime |
| Bootstrap `CandidateEvidence(basis="synthesized")` | `bootstrap.py` | Labels policy choices | Candidate presentation only, not build fields |
| Anchor `FieldProvenance(..., "synthesized")` | `anchor_roles.py` | Per-field provenance on resolved anchors | Parallel model; not wired into `_refine_defaults` |
| Role-adjacent species borrow | — | — | **Does not exist** |

**Verdict:** there is no hidden “borrow a representative build from a role-adjacent species”
path. The closest reusable pieces are item-substitution candidates, moveset prefs, and
`role_spread` — all partial.

---

## Part 2 — design proposal

**Design revision (2026-08-09, post–ability-provenance probe):** ability synthesis no longer
guesses among multiple legal options; `_mechanisms` must gate ability-derived claims on
provenance (prerequisite — see §0). Earlier draft text that allowed “pick a non-hidden
ability at low confidence” is **withdrawn**.

### Verdict

This is **primarily an algorithm limitation that is usually triggered by thin/absent offline
usage**, not a bug in unresolved handling and not solely an ingestion ticket.

- Prefer a **deterministic last-resort full-build synthesizer** on the slot-fill refine path
  (and align `recommend_build` only where it already assumes moves+item).
- Treat usage-coverage expansion as **complementary** (especially for Mimikyu evidence), not
  as the completeness guarantee.
- Do **not** invent role-adjacent species borrowing in v1 — no existing pattern, high
  contamination risk, and ADR-015 already prefers role-pattern + calc verification over
  cross-species copy.

### 0. Prerequisite — `_mechanisms` provenance gate (not the tier-3 feature itself)

**Confirmed gap (direct probe):** `_mechanisms` (`recommender/anchor_roles.py`) treats
`build.ability` as a flat fact. A `synthesized` Drizzle still emits Rain as
`needed` / `present=True` / `confidence="high"`, and `classify_anchor_role` can return
`rain_setter` with `match_quality="clean"`. Downstream consumers
(`derive_role_shape_context`, `target_role_from_strategic_evidence`, `condition_resilience`,
`team_candidates` duplication) branch on `present` / importance, **not** on
`MechanismEvidence.source`. Recording `source=synthesized` alone does not protect them.

**Required fix (smallest, central):** in `_mechanisms`, for ability-derived mechanisms only:

- Emit `present=True` with non-low confidence **only** when ability provenance is
  `user_confirmed`, `usage_derived`, or `legality_only` (unique-legal-ability case already
  used by `resolve_anchor_build`, e.g. Mimikyu → Disguise).
- For `synthesized` (and any other non-authoritative source): **omit** the ability mechanism,
  **or** emit `present=False` + `confidence="low"` so every present-gated consumer ignores it
  without per-consumer patches.
- Stop hardcoding `confidence="high"` on ability mechanisms — derive confidence from
  provenance (authoritative → high/medium; synthesized → low or omitted).

ADR-024’s “present `needed`/`wanted` mechanism” means the `MechanismEvidence.present` flag,
not “field is user-confirmed.” This gate is what makes that model safe under synthesis.

**Sequencing:** this is a **prerequisite fix**, not part of tier-3 attribute completeness.
**Prefer its own small task before tier-3 implementation** (one focused change + regression
test from the probe below). Bundling it as step 0 of the same implementation plan is
acceptable only if that plan cannot ship a synthesizer that writes `synthesized` abilities
without the gate landing in the same merge — do not land multi-option or role-constraint
ability fills first.

### 1. Proposed last-resort synthesizer (slot-fill `_refine_defaults` / shared helper)

Fire only after existing tier-1/2 attempts fail for a field. Order is identity → kit →
investment (mirrors what blocked Hatterene: spread never ran because item was empty).

1. **Ability** (revised — reuse `_unique_legal_ability` discipline; no non-hidden guess)
   - Reuse `resolve_anchor_build`’s `_unique_legal_ability`: fill **only** when exactly one
     legal ability exists in the Champions snapshot. Provenance `legality_only` (not
     `synthesized`) — same as today’s unique-ability path.
   - If the target role’s needed constraints uniquely select one legal ability (e.g.
     `rain_setter` → Drizzle among Pelipper’s options), that fill is allowed and labeled
     `synthesized` — but §0’s gate means it must **not** produce `present=True` Rain /
     `match_quality="clean"` from ability alone until the ability is confirmed or
     usage-derived. Prefer this over inventing a new provenance tier.
   - **Dropped:** picking a non-hidden legal ability (`0`/`1` vs `H`) when multiple options
     exist and no role constraint selects one. Snapshot slot order is game-data ordering,
     not a competitive signal; guessing creates exactly the false-mechanism risk §0 closes.
   - When multiple legal abilities exist and no role constraint selects one → **ability
     stays unresolved** (structured `incomplete_build` if other fields fill). Same ambiguity
     discipline as elsewhere in the project.
2. **Item**
   - Reuse the universal candidates already listed in `diagnose_and_substitute`: Life Orb,
     Sitrus Berry, Focus Sash — filtered by legality + Item Clause on the draft.
   - Bias by coarse role: offensive / setup → Life Orb; support / pivot / setter → Sitrus;
     frail sash archetypes → Focus Sash when base HP/Spe suggest it (keep rule tiny;
     document ceiling).
   - Provenance `synthesized`, confidence `low`–`medium`.
3. **Moves (pad to exactly four)**
   - Keep current `assemble_moveset_fallback` output as the seed.
   - Extend prefs: map each `TargetRoleId` to a small preferred-id list (TR setter includes
     `trickroom`; redirection includes Follow Me/Rage Powder; setup attackers include the
     setup move id; offensive roles include STAB/coverage via existing learnset + type
     heuristics **or** reuse move-narrowing’s team-need / mechanical-fit steps already built
     for usage-miss — prefer reuse over a new STAB inventer).
   - Always retain Protect when legal unless the role forbids it.
   - Still run `validate_moveset_redundancy`.
   - If still `< 4` after exhaustive legal narrowing → **remain** `incomplete_build` with
     `moves` listed (honest ceiling), rather than padding with arbitrary learnset noise.
4. **Spread**
   - Existing gate can run once item+moves exist: cache → `select_usage_spread` →
     `role_spread` via `infer_role` / archetype bridge for non-`RoleArchetype` target roles
     (today’s `trick_room_setter` → `infer_role` once Trick Room is in the moveset).
5. **Nature**
   - Missing today under pure `tier3_role`. Add a tiny companion table or derivation from the
     chosen spread (e.g. Spe 0 + SpA high → Quiet; Spe max + Atk → Jolly/Adamant) — same
     spirit as `_scarf_nature_correction`, not a new subsystem.
6. **Calc verification (ADR-015 tier 3 proper)**
   - Remains **post-complete verification**, optional when calc is up. Must not be required
     to emit `ProvisionalSlot`. On verify failure, keep the synthesized build but mark
     `verified=false` / lower confidence — do not wipe fields back to unresolved solely
     because calc is down (consistent with calc-unavailable design’s labeled degradation).

Success → `ProvisionalSlot` with per-field `ReasonRef` (and, if presentation carries evidence,
`CandidateEvidence(basis="synthesized", confidence="low"|"medium")`) when all seven fields
resolve. Multi-ability species without usage/role-selected ability correctly stay
`UnresolvedSlotRefinement` with `ability` in `unresolved_fields` even if kit/spread synthesize.

### 2. Interaction with confidence / provenance

Reuse models already in-repo; do not invent a third:

| Layer | Existing hook | Rule for synthesized / ability fields |
|-------|---------------|----------------------------------------|
| Slot attrs | `ReasonRef(kind=..., ref=...)` | Use `kind="tier2_heuristic"` with `ref` distinguishing `tier3_role` (spread table), `tier3_item_default`, `move_narrowing`, vs usage/cache refs. Unique ability fill should mirror resolve-path `legality_only` semantics (ReasonRef or FieldProvenance), not a generic “guessed ability” ref. |
| Candidates | `CandidateEvidence.basis` includes `"synthesized"`; confidence `high\|medium\|low` | Any provisional build that used ≥1 synthesized identity field (item/moves, or role-constraint ability) should attach evidence with `basis="synthesized"` and confidence **≤ medium** (default **low** if item or majority of moves were synthesized). Unique `legality_only` ability alone does not require `synthesized` basis. |
| Anchors | `FieldProvenance.source` | Preserve `legality_only` / `synthesized` / `usage_derived` / `user_confirmed` per field — never promote synthesized → usage_derived. |
| Mechanisms | `_mechanisms` + §0 gate | Ability-derived `present=True` only for `user_confirmed` / `usage_derived` / `legality_only`. Synthesized ability must not drive clean mechanism claims. |

Presentation must not imply parity with tier-1/2 usage-backed builds: same species can be
`usage_backed` at discovery and `synthesized` at refinement; both labels stay visible.

### 3. What not to do

- Do not treat Mimikyu snapshot expansion as closing this ticket.
- Do not silently dump leftover SP or invent natures without provenance (ADR-015 incomplete-
  spread guardrail).
- Do not call full recursive `recommend_build` per threat for opponent builds (ADR-015a).
- Do not borrow sets from “similar” species in v1.
- Do not weaken `UnresolvedSlotRefinement` / atomic commit gates — synthesis must produce a
  **complete legal** seven-field build or leave the structured unresolved result.
- Do **not** pick a non-hidden ability among multiple legal options to force completeness.
- Do **not** ship ability synthesis that can write `synthesized` abilities without §0’s
  `_mechanisms` gate already in place (or in the same merge as step 0).

### 4. Acceptance checks (for a later implementation pass)

**Prerequisite (§0) — land first or as plan step 0:**

0. Synthesized Drizzle on Pelipper (usage mocked away; same probe that found the bug) must
   **not** produce a Rain mechanism with `present=True`, must **not** yield
   `match_quality="clean"` from that ability claim, and must not hardcode
   `confidence="high"` on the ability mechanism. Unique Mimikyu → Disguise via
   `legality_only` may still emit a present mechanism if Disguise is modeled; that path is
   intentional and distinct from synthesis.

**Tier-3 synthesizer:**

1. No-usage Hatterene + `trick_room_setter`: synthesizer fills item / four moves / nature /
   full 66 SP where possible; **ability stays unresolved** (multiple legal abilities, no
   role constraint selects one) → `UnresolvedSlotRefinement` with `ability` listed (and
   only those fields still missing). Not a forced complete provisional via ability guess.
2. No-usage Mimikyu + offensive target role → `ProvisionalSlot` possible: unique Disguise via
   `legality_only`, plus synthesized item/moves/nature/spread as needed; usage comparison
   still reports absence separately (Mimikyu coverage ticket).
3. Usage-hit Sinistcha path unchanged (still `usage` / `tier2_usage_offline` provenance).
4. Pure `tier3_role` spread path sets nature (closes today’s nature hole even when moves+item
   were user-supplied).
5. Ability-defining target role with multiple legal abilities and no matching constraint →
   ability unresolved; no false `present=True` mechanism claim if a synthesized ability were
   somehow present (§0). Role-constraint-selected ability (if implemented) remains
   `synthesized` and non-authoritative for `present=True` until confirmed/usage-derived.
6. Existing `UnresolvedSlotRefinement` tests for unresolved target role remain green.

### Residual risks

- Prefs expansion for every `TargetRoleId` can rot; prefer wiring move-narrowing’s existing
  steps over a growing static table where possible.
- Multi-ability no-usage species (Hatterene-shaped) correctly cannot auto-complete ability —
  users or usage coverage must supply it; presentation should make that unresolved field
  obvious rather than looking like a general refine failure.
- Hardcoded opponent list inside `_tier3_verify_spread` remains an ADR-015 fidelity gap,
  orthogonal to attribute completeness.

---

## Scratchpad

- Goal: end-to-end discovery + design for tier-3 attribute completeness; no code.
- Plan: ADR-015 vs code → failure path → real cases → Mimikyu comparison → fallbacks → design.
- [x] Trace `recommend_build` and `_refine_defaults`
- [x] Reproduce Hatterene / Mimikyu `UnresolvedSlotRefinement`
- [x] Confirm snapshot cap + graceful failure
- [x] Design synthesizer + provenance rules
- [x] Fold `_mechanisms` gate + unique-only ability revision; Hatterene acceptance corrected
