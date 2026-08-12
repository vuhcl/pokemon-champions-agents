# Trick Room `benefits_from` unconsumed in `single_locked` — discovery and design (2026-08-11)

**Status:** Discovery + design only. No implementation in this pass.

**Trigger:** Mechanism-relation symmetry audit. A synthesized Trick Room `benefits_from`
row is written on a locked `trick_room_sweeper` whose kit has no Trick Room move, but
`derive_role_shape_context` only projects `{Rain, Sun, Sand, Snow}` into
`needed_weathers`, so `query_support_needs` never sees it. The only `single_locked` TR-setter
ask today is Layer 3’s Spe-tier heuristic.

**Framing (verified):** this is **not** the condition-beneficiary invert (provision → who
wants this). It is the dependence-side gap — same shape as the Archaludon Electro Shot fix
(`benefits_from` → an already-mapped need). Existing `NeedCategory="trick_room"` already
maps to `trick_room_setter` in `_NEED_TARGET_ROLES`. Second producer for an existing
category, not a new one.

**Out of scope:** Tailwind (no `benefits_from` writer); `condition_resilience` / gap-need
edits; Role Compendium.

---

## Part 1 — verified current state

### 1. When the synthesized TR-sweeper `benefits_from` row is written

**Not in `_mechanisms`.** `_mechanisms` never emits Trick Room `benefits_from`. It emits
Trick Room only as `provides` when the move is on the kit (`anchor_roles.py:524–531`).

The dependent row is appended later in `classify_anchor_role`, after `role_id` is resolved:

```735:753:recommender/anchor_roles.py
    if role_id == "trick_room_sweeper" and "trickroom" not in move_ids:
        mechanisms.append(
            MechanismEvidence(
                mechanic="Trick Room",
                kind="teammate_condition_benefit",
                relation="benefits_from",
                importance="wanted",
                role_id=None,
                present=False,
                prerequisite=False,
                activation="passive_reactive",
                interruptible=False,
                source="user_confirmed" if declared else "unknown",
                supply="teammate_expected",
                evidence=("condition:Trick Room", "strategy:trick_room_sweeper"),
                confidence="medium",
            )
        )
        conflicts.append("strategic Trick Room role is not established by the active kit")
```

**Exact gate:** `role_id == "trick_room_sweeper"` **and** `"trickroom" not in move_ids`.

That is a strategic-identity row, not a kit-derived one: `present=False`,
`supply="teammate_expected"`, `importance="wanted"`. It exists specifically because the
sweeper identity was chosen and the kit does not self-supply Trick Room.

How `role_id` becomes `trick_room_sweeper` without the move (same function, earlier):

| Path | Can produce sweeper-without-move? |
|---|---|
| `user_role` / locked `explicit_role` (`declared`) | **Yes** — this is the live path (Kingambit locked as Trick Room sweeper) |
| `compendium.exact[0].role_id` | **No file** — `data/roles/` has `trick_room_setter.v1.json` only |
| First mechanism with `role_id` | **No** — kit TR move is `provides` / `trick_room_setter`, and this branch only runs when that move is absent |
| `infer_role` fallback | **No** — `infer_role` returns `trick_room_sweeper` only when `"trickroom" in mids` (`recommend.py:137–138`), which fails the `not in move_ids` gate |

So the row is **declared/locked sweeper identity without a Trick Room move**. Covered by
`test_kingambit_trick_room_sweeper_still_teammate_expected_dependent`
(`tests/recommender/test_anchor_roles.py:37–48`).

If the kit **has** Trick Room, this row is not written. That Pokémon `provides` TR; it is
not a dependence case.

### 2. What currently produces `"trick_room"` needs in `query_support_needs`

**Layer 3 is the only producer inside `query_support_needs`.**

Grep of `category="trick_room"` / `category == "trick_room"` in `recommender/`:

| Site | Role |
|---|---|
| `support_needs.py:400–436` (`_layer3_needs`) | **Only emitter** in `query_support_needs` |
| `slot_fill.py:280` `_NEED_TARGET_ROLES` | Maps category → `trick_room_setter` / `move:trickroom` |
| `slot_fill.py:82, 971, 1095` | Satisfier + resolution (consumes, does not emit) |
| `condition_resilience.py:177, 216` | `multi_locked` gap needs — **not** called from `discover_single_locked` |

Call chain for Layer 3:

```
query_support_needs
  → _speed_needs          (support_needs.py:626–638)
       early-out: self-speed abilities (`speedboost` / `unburden` / `quickfeet`) → `[]`
       maybe emit `condition_setter` for weather/terrain abilities; speed-doublers return before Layer 3
       if primary_function != "offense": return (no Layer 3)
       if _spe_tier is None (empty threat Spe list): return
       → _layer3_needs(tier, has_priority)
```

`_layer3_needs` TR emission (`support_needs.py:396–447`, locked by
`test_layer3_need_want_matrix`):

| Spe tier | TR need? | trigger | stance |
|---|---|---|---|
| `low`, no priority | yes | `speed_tier:low_no_priority` | `need` |
| `low`, with priority | yes | `speed_tier:low_with_priority` | `want` |
| `middling` | yes (alongside Tailwind `need`) | `speed_tier:middling` | `want` |
| `already_fast` | **no** — Tailwind `want` only | — | — |
| `_spe_tier` is `None` | **no** | — | — |

There is **no** `needed_weathers`-style pass for Trick Room. The weather pass at
`support_needs.py:640–666` is gated by `_TRACKED_WEATHERS = {Rain, Sun, Sand, Snow}` and
emits `condition_setter`, not `trick_room`. Putting `"Trick Room"` into `needed_weathers`
would not produce a `trick_room` need; it would be skipped.

**Correction to the audit’s “fails either condition” wording.** The synthesized row
requires `role_id == "trick_room_sweeper"`, and `_primary_function` maps that id to
`"offense"` (`anchor_roles.py:653–659`). A sweeper-identity anchor **cannot** fail the
offense gate. The real Layer 3 miss is Spe-tier / early-out, not primary function.

Live probe (2026-08-11, `resolve_anchor_build` + `query_support_needs` via
`derive_role_shape_context`):

| Anchor | `benefits_from` TR row? | Layer 3 TR need? |
|---|---|---|
| Kingambit, no role | no | yes (`speed_tier:low_with_priority`, `want`) — Spe heuristic, no mechanism |
| Kingambit, `user_role=trick_room_sweeper` | yes (`present=False`, `wanted`) | yes, **same** Layer 3 row — mechanism ignored |
| Dragapult, declared sweeper | yes | **no** — `already_fast`, Tailwind `want` only |
| Flutter Mane, declared sweeper | yes | **no** — `already_fast` |
| Iron Valiant, declared sweeper | yes | yes (`speed_tier:middling`, `want`) — overlap |

User-visible `single_locked` miss: lock a TR-sweeper identity on a kit that does not run
Trick Room **and** is not slow/middling vs threats (Dragapult-shaped). Partner search never
asks for a TR setter, despite the relation already on `AnchorRoleDecision`. Kingambit-shaped
locks are masked by Layer 3 — that is coincidence of Spe, not consumption of the mechanism.

### 3. Double-counting risk (Kingambit / `distinct_needs` class)

**Yes. Trigger-string identity does not save it. Category-level skip is required.**

Shipped failure (`docs/master_project_log.md` 2026-08-09 condition-resilience entry;
`test_gap_need_deduped_when_anchored_trick_room_already_present`):

- Layer 3: `("trick_room", "speed_tier:...")`
- Resilience gap: `("trick_room", "condition_resilience:gap")`
- `distinct_needs` in `rank_multi_locked_candidates` is
  `{(need.need.category, need.need.trigger) for need in candidate.anchored_needs}`
  (`team_candidates.py:659–661`)
- A Farigiraf satisfying both would get `len(distinct_needs)` += 2 for one underlying TR
  ask

Fix that shipped: `_condition_already_covered` matches Trick Room by **category**, not
trigger (`condition_resilience.py:177–178`). `gap_support_needs` skips if any existing
need already has `category == "trick_room"`.

A second producer **inside** `query_support_needs` is a different site than
`gap_support_needs`, but the same identity problem:

- Layer 3 trigger is always `speed_tier:*`
- A mechanism-based need would use a different trigger (the evidence tag is
  `strategy:trick_room_sweeper`; a `condition_resilience:gap` clone would also differ)
- `SupportNeed` is a frozen dataclass; equality includes `trigger` / `stance` /
  `description`
- `query_support_needs` does **not** dedupe by category — it only sorts
  (`support_needs.py:666–668`)
- Weather’s `covered_labels` skip is **label**-level for `condition_setter`, not a
  `trick_room` skip
- `_matching_needs_for` returns every matching `SupportNeed` (`slot_fill.py:553–564`).
  One species with Trick Room in the learnset matches **every** `trick_room` row
- `single_locked` sort key is `-len(r.matching_needs)` (`slot_fill.py:1398–1411`) —
  two TR rows → double credit, same class as `distinct_needs` inflation
- `dict.fromkeys` on `matching_needs` does not collapse different `SupportNeed` values

Kingambit declared sweeper is the overlap case (probe: both the mechanism row **and**
Layer 3 TR `want` are live). Emitting a second `trick_room` need without a category skip
would re-open the Kingambit double-count in **both** phases, because
`collect_locked_anchor_contexts` also calls `query_support_needs`
(`team_candidates.py:166–174`).

`gap_support_needs` would then skip its own gap (category already present) — it cannot
dedupe two needs that were already both emitted by `query_support_needs`.

### 4. Phase scope

**The unconsumed-relation bug is `single_locked`-visible. `condition_resilience` does not
need changes. The natural hook is shared.**

| Phase | TR `benefits_from` consumed? | How |
|---|---|---|
| `single_locked` | **No** | `discover_single_locked` never calls `assess_condition_resilience` (`nodes.py:977–1041`). Shape drops TR. Layer 3 is the only ask, and it is Spe-gated |
| `multi_locked` | **Yes** | `assess_condition_resilience` reads `benefits_from` including `present=False` + `teammate_expected` (`condition_resilience.py:114–117`). Kingambit declared sweeper → `preferred` / `missing_provider` (`test_kingambit_present_false_counts_as_dependent_in_assess`). `gap_support_needs` emits `trick_room` only when no anchored `trick_room` need already exists |

Do not edit `assess_condition_resilience`, `gap_support_needs`, or
`_condition_already_covered`. Those already do the dependence → setter job for
`multi_locked`, including category-level TR dedup against Layer 3.

`query_support_needs` / `derive_role_shape_context` **are** shared. A producer added there
will also run per locked member in `multi_locked`. That is the same sharing as the Electro
Shot `needed_weathers` pass. It is acceptable **if and only if** `query_support_needs`
emits at most one `trick_room` need (Part 2 §2). Then `gap_support_needs` continues to
see “already covered” and stays quiet. No resilience-path edit.

---

## Part 2 — design

### 1. How the mechanism should drive a `trick_room` need

Same two-step pattern as Electro Shot, **not** stuffing Trick Room into `needed_weathers`.

**Step A — project.** In `derive_role_shape_context`, keep the weather loop on
`_SHAPE_WEATHERS`. Add one boolean (name bikeshed: `needed_trick_room`), true when any
mechanism has:

- `relation == "benefits_from"`
- `importance in ("needed", "wanted")`
- `present or supply == "teammate_expected"`
- evidence tag `condition:Trick Room`

That matches the weather gates (`anchor_roles.py:793–800`) and the synthesized row
(`wanted`, `present=False`, `teammate_expected`, `condition:Trick Room`). Do not require
`present=True` — this row is deliberately absent-from-kit.

Do **not** put `"Trick Room"` in `needed_weathers`. That tuple is consumed only as
`condition_setter` + `_TRACKED_WEATHERS` (`support_needs.py:645–648`). TR would be
silently dropped again, or worse, mis-emitted as a weather setter.

`RoleShapeContext` already has a custom `__init__` that accepts unused legacy keywords
(`match_status`, `setup_dependent`) and does not retain them. Add `needed_trick_room: bool = False` the same way. `test_role_shape_context_is_only_the_projection` currently
asserts exactly four field names — it must be updated when the field is added.

**Step B — emit.** In `query_support_needs`, after `_speed_needs` (so Layer 3 has already
run), if `role_shape_context.needed_trick_room` and no existing need has
`category == "trick_room"`, append one `SupportNeed`:

- `category="trick_room"` — existing `_NEED_TARGET_ROLES`, `_NEED_SATISFIERS`,
  `_compendium_roles_for_need` (`trick_room_setter` file) all already key off this
- `name="Trick Room"`
- `trigger` distinct from Layer 3, e.g. `strategy:trick_room_sweeper` (already on the
  mechanism evidence) — **not** `speed_tier:*`, **not** `condition_resilience:gap`
- `stance="want"` — the only writer of this row uses `importance="wanted"`; do not
  upgrade it to `need` in the projection

No new `NeedCategory`. No new target-role mapping. Resolution stays
`_resolve` via `move:trickroom` / compendium `trick_room_setter`.

### 2. Dedup (required, not optional)

**Inside `query_support_needs`, skip the mechanism emit when any need already has
`category == "trick_room"`.** Same discipline as `_condition_already_covered` for Trick
Room: category, not `(category, trigger)`.

Do not rely on:

- trigger-string equality (Layer 3 `speed_tier:*` ≠ mechanism `strategy:trick_room_sweeper`)
- `dict.fromkeys` on `matching_needs` (different frozen `SupportNeed` values stay distinct)
- `gap_support_needs` (too late; only runs in `multi_locked`, and only against its own gap)

Weather’s `covered_labels` is the structural analog (second producer skips if the first
already covered that weather) but the TR predicate is category-wide because there is only
one Trick Room condition.

When both Layer 3 and the mechanism would fire (Kingambit declared sweeper): **keep Layer
3, skip the mechanism emit.** Layer 3 already carries Spe-calibrated `need`/`want` and
`speed_tier:*` triggers that tests and the resilience dedup already know. The mechanism
path’s job is the case Layer 3 does not cover (`already_fast` / no Spe signal / Layer 3
early-out), not to replace a working Spe ask with a second identical category.

### 3. Relation to Layer 3: supplement, do not replace

| Producer | Question it answers | Keep? |
|---|---|---|
| Layer 3 Spe-tier | “This offense anchor is slow/middling vs threats — TR (or TW) would help” | **Yes.** Kingambit *without* a sweeper role still has no TR `benefits_from` row (probe) and still correctly gets a TR `want` from Spe |
| Mechanism projection | “This anchor’s strategic identity expects teammate Trick Room” | **Add.** Covers declared sweeper + non-slow Spe (Dragapult probe), and Spe-signal-less / Layer-3-suppressed cases |

Replacing Layer 3 would drop TR asks for slow offense that was never tagged
`trick_room_sweeper`. Running both without the category skip re-opens Kingambit
double-count. Supplement + skip-if-category-present is the intended pairing.

Stance note: for an `already_fast` declared sweeper the new row is `want`, not `need`.
That matches the written `importance="wanted"` and Layer 3’s own TR `want` on middling /
low-with-priority. Do not silently treat sweeper identity as `need`.

### 4. What this does not do

- No Tailwind emit (no `benefits_from` writer; separate emission-hole task)
- No `condition_resilience` / `gap_support_needs` / `discover_multi_locked` edits
- No new query tool, no dex-wide `classify_anchor_role` scan
- No change to `_NEED_TARGET_ROLES` or the `trick_room_setter` compendium file

### 5. Acceptance (when implementing)

1. Dragapult (or any `already_fast` offense) with `user_role="trick_room_sweeper"` and no
   Trick Room move: `needed_trick_room` true; `query_support_needs` contains exactly one
   `trick_room` need; trigger is the mechanism one; a known TR-setter species appears in
   `single_locked` need-resolution (not threat-only).
2. Kingambit declared `trick_room_sweeper`: still exactly one `trick_room` need, and it is
   still the Layer 3 `speed_tier:*` row (mechanism skipped). `matching_needs` length for a
   TR-setter candidate does not increase vs today.
3. Kingambit with **no** sweeper role: still Layer 3 only; `needed_trick_room` false (no
   `benefits_from` row).
4. Kingambit whose kit **includes** Trick Room: no synthesized `benefits_from`; no
   mechanism TR need from this path (they `provide` TR).
5. `test_gap_need_deduped_when_anchored_trick_room_already_present` and
   `test_kingambit_present_false_counts_as_dependent_in_assess` unchanged — resilience
   path not edited.
6. Pelipper / Archaludon weather paths unchanged (`needed_weathers` still weather-only).

---

## Summary

| Item | Verdict |
|---|---|
| Writer | `classify_anchor_role`, not `_mechanisms`: sweeper identity **and** no Trick Room move |
| `query_support_needs` TR producer today | Layer 3 Spe-tier **only** |
| Offense-gate miss in the audit | **Overstated** — sweeper identity always projects `primary_function="offense"` |
| Real miss | Spe-tier `already_fast` / no Spe signal / Layer 3 early-out, with the relation already recorded |
| Double-count if naïve second emit | **Yes** — different triggers; `single_locked` `-len(matching_needs)` and `multi_locked` `distinct_needs` both inflate. Skip on `category == "trick_room"` |
| `condition_resilience` | Already correct; do not touch |
| Design | Project `needed_trick_room` on `RoleShapeContext`; emit existing `trick_room` need after Layer 3; skip if category already present; **supplement** Layer 3, do not replace it |
