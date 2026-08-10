# Role_id gap scan — full corpus results + infer_role vocabulary proposal (2026-08-09)

**Status:** Design + implemented three-axis `infer_role` / `role_spread` (2026-08-09).
No Step A `_mechanisms` emission or new Compendium files in this pass.

**Implements methodology from:**
[`docs/role_id_vocabulary_usage_scan_discovery_and_design_2026-08-09.md`](role_id_vocabulary_usage_scan_discovery_and_design_2026-08-09.md)
Part 2 §1.

**Machine-readable raw builds:**
[`docs/artifacts/role_id_gap_scan_2026-08-09.json`](artifacts/role_id_gap_scan_2026-08-09.json)
(180 classified builds). Repro: `uv run python scripts/role_id_gap_scan.py`.

---

## Corpus executed

| Pass | Corpus | Builds |
|------|--------|-------:|
| 1 | `ingame_doubles` baseline (ability₀ / item₀ / moves₀₋₃) | 50 |
| 2 | `showdown_vgc_mb` featured sets | 77 |
| 3a | Ingame ability variants (every ability ≥5% usage, moves/item fixed) | 35 |
| 3b | Ingame dual-set move clusters (move₃ & move₄ both ≥40%) | 18 |
| | **Total** | **180** |

**Cascade winners (all builds):** `infer_role` 126 · `mechanism` 31 · `exact` 23 ·
declared/unresolved 0.

**Flags:** `infer_role_fallback` 126 · `ability_ignored_underdiff` 52 (17 species) ·
`support_moves_present_but_offense_label` 5.

**Dual-set species (pass 3b):** Aerodactyl, Basculegion Male, Blaziken, Delphox, Excadrill,
Floette, Mawile, Sinistcha, Venusaur.

**Notable dual-set flip:** Floette `Calm Mind` cluster → `mechanism`/`setup_attacker`;
Light of Ruin cluster → `infer_role`/`bulky_attacker`. Sinistcha Trick Room vs Life Dew
both stay `exact`/`redirection` (Life Dew drops `trick_room_setter` secondary only).

---

## Classification vs contested-slot grouping (read first)

These are **different concerns** that both use the word "attacker":

| Concern | Where | What "attacker" means |
|---------|--------|------------------------|
| **Classification correctness** | `infer_role` / `RoleArchetype` / primary `role_id` | Must distinguish **physical vs special** (and mixed) from **move categories on the active kit** — Archaludon (special) ≠ Mega-Swampert (physical) for coverage identity and matchup-relevant labeling |
| **Contested bring-4 slot structure** | Roster role-structure grouping's coarse `attacker` bucket from `primary_function == "offense"` | Deliberately **does not** split physical/special — those members still compete for the same bring-4 offense slots |

**Not a contradiction.** Grouping coarsens for slot competition; `infer_role` must refine for
classification. The gap-table / vocabulary proposal below puts phys/special **only** in the
`infer_role` vocabulary, never as a requirement to subdivide the roster-grouping `attacker`
bucket ([`roster_role_structure_grouping_discovery_and_design_2026-08-09.md`](roster_role_structure_grouping_discovery_and_design_2026-08-09.md)
§1.6).

**Damage bias** in this scan = `move_category_counts` over the build's damaging moves
(`usage_spreads.py` via snapshot move `category`) → `physical` | `special` | `mixed` |
`status_only`. **Not** base-stat inference.

---

## Complete gap table

Threshold (per design): pattern kept if **≥2 species** OR **≥1 top-20 species with a clear
mechanical gate**. Tier tags: `compendium` | `mechanism` | `infer_role` | `defer`.

| # | Pattern | Species (n) / builds | Evidence (examples) | Tier | One-line reasoning |
|---|---------|----------------------|---------------------|------|--------------------|
| 1 | Mega stone + damaging kit → bare `bulky_attacker` | 13 special + 11 physical species; 44 builds | Charizard-Y Heat Wave kit; Swampertite Wave Crash kit; Staraptite Brave Bird | **`infer_role`** | Dominant fallback mass; needs bulky×{physical,special,mixed} labels from move categories — not a membership-contested role-search category |
| 2 | Focus Sash offense → bare `bulky_attacker` | 7 species; 8 builds | Excadrill Sand Rush sash; Glimmora; Annihilape; Vivillon Fancy + Rage Powder | **`infer_role`** (+ **`defer`** name for Fancy/form ids) | Glass offense mislabeled bulky; sash + bias → fast_* ; Rage Powder form-id miss is name resolution OOS |
| 3 | Life Orb / Choice attacking / Scarf → `fast_attacker` without phys/special | Scarf phys 4 sp. / special 5 sp.; LO phys 3 / special 2 | Garchomp LO physical; Hydreigon Scarf special; Basculegion Scarf physical | **`infer_role`** | Existing fast branch is right axis, wrong granularity — split by move-category bias |
| 4 | Leftovers/Sitrus/Helmet → `bulky_pivot` without pivot move | 5 species; 7 builds | Archaludon Stamina LO-less Electro Shot kit; Milotic; Toxapex (Regenerator) | **`infer_role`** | False pivot from item alone; require pivot move (`U-turn`/`Volt Switch`/`Flip Turn`/`Parting Shot`/`Teleport`) for `*_pivot` |
| 5 | Leftovers/Sitrus **with** pivot move | Incineroar (also #9); Rotom-W shaped | Parting Shot + Sitrus | **`infer_role`** | Keep pivot archetype once pivot move present; still add phys/special on the attacking half only if primary stays pivot (primary = pivot, not attacker) |
| 6 | Weather-speed ability ignored for primary | 4 species; 10 builds | Venusaur Chlorophyll; Excadrill Sand Rush; Basculegion Swift Swim vs Adaptability underdiff | **`mechanism`** primary/secondary + light **`infer_role`** ability hook | `benefits_from` emission exists for needed weather abilities when provenance allows; primary still falls through — ability must participate in cascade or infer_role; not Compendium "Chlorophyll attacker" |
| 7 | Ability under-differentiation (meta) | 17 species; 52 flagged builds | Maushold Friend Guard vs Technician same moves; Kingambit Defiant vs Supreme Overlord; Charizard Blaze vs Solar Power | **`mechanism`** / **`infer_role`** (ability-aware) | Same moves/item → identical `role_id` whenever ability lacks mechanism/Compendium gate; systemic, not species lore |
| 8 | Technician + multi-hit still coarse / underdiff | Maushold Family of Four (rank 25) | Usage kit is Follow Me + Pop Bomb; FG vs Technician both `bulky_attacker` | **`infer_role`** (+ **`mechanism`**) + **`defer`** form id | Technician×multi-hit should force fast_physical (or mechanism role); usage species string `Maushold Family of Four` also misses Compendium `Maushold` exact redirection (`to_id` mismatch) — canonical resolution OOS |
| 9 | Fake Out (+ often Intimidate) support collapsed | 8 species Fake Out; Incineroar Intimidate+FO top-2 | Sneasler FO; Raichu FO; Incineroar FO/Parting Shot → `bulky_pivot` | **`mechanism`** first; **`compendium` candidate** only if product wants "Fake Out support" search | Widely differentiating **support** function; membership contested — Compendium-worthy *if* role-search is a product need; first cut: emit Fake Out mechanism / support tag, don't invent Compendium in wave 1 |
| 10 | Screens + Prankster / Light Clay → offense fallback | Grimmsnarl (top-20) | Reflect + Light Screen + Parting Shot → `bulky_attacker` | **`mechanism`** | Kit-proof screens emission for secondary (and primary when screens-dominant); overlaps roster Step A — not automatic Compendium |
| 11 | Pure disruption / status kit → `bulky_attacker` | Sableye-Mega showdown | WoW / Encore / Disable / Recover | **`mechanism`** | Status-only bias + disruption moves; same emission family as screens/Encore Step A |
| 12 | Generic physical "other item" fallback | 3 species; 6 builds | Kingambit Black Glasses; Tsareena Wide Lens | **`infer_role`** | Default bulky_physical_attacker from move categories when no faster signal |
| 13 | Redirect move present but no exact Compendium | Maushold Family of Four; Vivillon Fancy Pattern | Follow Me / Rage Powder on form-qualified names → infer_role | **`defer`** (canonical name/form) + **`mechanism`** backup | Exact path works for species id `maushold`; usage display forms don't match — OOS name resolution; emitting redirect `provides` from moves would kit-proof without waiting on names |
| 14 | Unrecognized setup beyond SD/NP/CM/Bulk Up | Floette dual-set; (Tidy Up absent from top-50 moves) | Calm Mind cluster OK via mechanism; non-CM cluster fallback | **`mechanism`** | Extend setup map for high-frequency setups as they appear (Tidy Up when present); Calm Mind already works |
| 15 | Working mechanism/Compendium paths (non-gaps) | setup_attacker, nasty_plot, tailwind_setter, rain/sun/sand setters, redirection, TR setter | Ceruledge Bulk Up; Pelipper; Sinistcha; Whimsicott Tailwind | — | Documented as healthy cascade; no vocabulary change required |

**Not promoted to table (failed threshold or non-flagged):** one-off lore without shared
signature; healthy Compendium/mechanism hits without fallback flags.

---

## Coherent `infer_role` / `RoleArchetype` revision (design-only)

Reflects **every `infer_role`-tagged row above** as one vocabulary, not per-pattern patches.
Also covers `recommend.py` callers that use `infer_role` outside `classify_anchor_role`.

### Explicit split vs roster grouping

- **`infer_role` offense output:** always physical / special / mixed — no bare
  `*_attacker` without a category suffix.
- **Non-offense archetypes** (`trick_room_sweeper`, `support_speed_control`,
  `screens_support`, pivots) stay as named labels without a phys/special suffix.
- **Roster grouping `attacker` bucket:** unchanged — still `primary_function == "offense"`
  only; phys/special must **not** be introduced there.

### Proposed `RoleArchetype` vocabulary

```text
# Offense (damage bias from move categories on the kit; three axes)
fast_physical_attacker
fast_special_attacker
fast_mixed_attacker
standard_physical_attacker
standard_special_attacker
standard_mixed_attacker
bulky_physical_attacker
bulky_special_attacker
bulky_mixed_attacker

# Pivot (requires a pivot move on the kit)
bulky_pivot          # keep; item may reinforce but must not create alone
fast_pivot           # NEW — Choice Scarf (or equivalent) + pivot move

# Support / control (non-offense primaries when infer_role is the cascade winner)
trick_room_sweeper      # KEEP — dependency-circle role pin + role_spread table (final)
support_speed_control   # Tailwind-shaped (usually preempted by mechanism tailwind_setter)
screens_support         # NEW — ≥2 screen moves and/or Light Clay + a screen move
```

**Removed / replaced:**

| Current | Disposition |
|---------|-------------|
| `bulky_attacker` | Replace with `bulky_{physical\|special\|mixed}_attacker` (bulky-item axis only); default catch-all is `standard_*` |
| `fast_attacker` | Replace with `fast_{physical\|special\|mixed}_attacker` |
| `trick_room_sweeper` | **Keep** in `RoleArchetype`, in `infer_role`'s decision tree (`"trickroom" in mids` → return), and in `role_spread`. Final decision — see §“Trick Room dependency-circle pin” |

**Not added to `infer_role` (stay mechanism / later Compendium):** Fake Out support,
Technician as its own archetype name, weather-speed beneficiary *labels* (ability still hooks
the **fast** axis), redirection (Compendium + mechanism backup), Encore/WoW disruption
secondaries, Mega Spe/bulk species signals (Mega stones stay on `standard_*`).

### Proposed decision logic (single coherent tree)

Inputs widen to `(moves, item, ability | None)`. Damage bias from snapshot move categories.

```text
mids, iid, aid = ids(moves, item, ability)
bias = damage_bias(moves)   # physical | special | mixed | status_only
has_pivot = mids ∩ {uturn, voltswitch, flipturn, partingshot, teleport}
screens = mids ∩ {lightscreen, reflect, auroraveil}
fast_item = iid ∈ {lifeorb, choiceband, choicespecs, choicescarf}
bulky_item = iid ∈ {sitrusberry, leftovers, rockyhelmet}
multi_hit = mids ∩ MULTI_HIT_SET
technician_fast = (aid == technician ∧ multi_hit)

1. If "trickroom" ∈ mids:
     → trick_room_sweeper
     # KEEP: _propagate_and_refine role pin calls infer_role directly
     # (propose.py:174-176); preserves test_trick_room_moveset_implies_role_and_spread.
     # Independent of classify_anchor_role's mechanism-first path.

2. If |screens| ≥ 2 OR (iid == lightclay ∧ |screens| ≥ 1):
     → screens_support

3. If "tailwind" ∈ mids:
     → support_speed_control
     # (classify path usually already took mechanism tailwind_setter)

4. If has_pivot:
     → fast_pivot if iid == choicescarf OR technician_fast
     → else bulky_pivot
     # Intimidate+Fake Out with Parting Shot lands here via partingshot ∈ has_pivot

5. If bulky_item AND NOT has_pivot:
     → do NOT return pivot
     → if bias == status_only: screens_support if any screen else bulky_special_attacker
       as weak default only if needed — prefer leaving status-only to mechanism
     → else bulky_{bias}_attacker
     # Fixes Archaludon Leftovers false pivot (#4)

6. If fast_item OR technician_fast OR iid == focussash OR weather_speed ability:
     # sash treated as glass → fast axis (#2); weather-speed hooks fast axis (#6)
     → if bias == status_only: fall through
     → else fast_{bias}_attacker
     # Covers LO/Choice/Scarf phys/special (#3) and Technician×Pop Bomb (#8)

7. Default (mega stones, Black Glasses, Wide Lens, …):
     → if bias == status_only: standard_special_attacker  # weak; mechanism should own disruption
     → else standard_{bias}_attacker
     # Covers mega phys/special mass (#1) and Kingambit-shaped (#12)
     # Mega stones stay on standard_* — post-Mega Spe/bulk not a clean partition
```

**Ability hooks in this tree (minimal):** Technician×multi-hit → fast axis; weather-speed
abilities hook the **fast** axis (no dedicated sand/chlorophyll archetype id). Fake Out alone
does not select a new infer_role id (tier = mechanism / optional Compendium).

**`role_spread` implication (design note only):** each new offense archetype needs a spread
template (physical vs special investment). Pivot/screens/speed-control keep or adapt current
templates. **Keep** `role_spread("trick_room_sweeper")` unchanged for the dependency-circle
spread pin (hardcoded literal) and for any caller that still holds that role label. Out of
scope to implement here.

### Trick Room dependency-circle pin — final decision: keep `infer_role` return

Tier-3 discovery names the pin as Trick Room → `role_spread("trick_room_sweeper")`
([`tier3_build_attribute_completeness_discovery_and_design_2026-08-09.md`](tier3_build_attribute_completeness_discovery_and_design_2026-08-09.md)).
Trace in `_propagate_and_refine` (`recommender/propose.py`):

```174:196:recommender/propose.py
    if moves is not None and slot.role.value is None and not slot.role.locked:
        item_for_role = slot.item.value or ""
        implied["role"] = infer_role(moves, item_for_role)
    ...
    if has_tr and slot.spread.value is None and not slot.spread.locked:
        tr_spread = dict(role_spread("trick_room_sweeper"))
        if "spread" in implied and implied["spread"] != tr_spread:
            # Contradictory pins (e.g. Scarf + TR) — leave unset.
            implied.pop("spread", None)
        else:
            implied["spread"] = tr_spread
```

| Pin | Source | Depends on `infer_role` → `trick_room_sweeper`? |
|-----|--------|--------------------------------------------------|
| **Spread** | Hardcoded `role_spread("trick_room_sweeper")` when locked moves contain Trick Room (`has_tr`) | **No** — literal string |
| **Role** | `implied["role"] = infer_role(moves, item_for_role)` when role unset | **Yes** — `infer_role` returns `trick_room_sweeper` when `"trickroom" in mids` (`recommend.py:49-50`). Covered by `test_trick_room_moveset_implies_role_and_spread` (`tests/recommender/test_dependency_circle.py:92-105`) |

**Final decision:** **Keep** the `trick_room_sweeper` return in `infer_role`'s decision tree
(step 1 above). Do **not** update `_propagate_and_refine` — smaller, safer change; preserves
existing tested role+spread behavior exactly. The earlier idea that the branch is “effectively
dead” only applied to `classify_anchor_role`'s mechanism-first cascade, not this call site.

`classify_anchor_role` still accepts declared `user_role="trick_room_sweeper"` independently
(`anchor_roles.py:704+`); that path is unrelated and also stays.

### Mapping from gap-table `infer_role` rows → vocabulary

| Gap # | Satisfied by |
|-------|----------------|
| 1 Mega bare | Step 7 `standard_{bias}_attacker` |
| 2 Sash bare bulky | Step 6 sash → `fast_{bias}_attacker` |
| 3 LO/Choice/Scarf bare fast | Step 6 `fast_{bias}_attacker` |
| 4 False bulky pivot | Step 5 bulky item without pivot → `bulky_{bias}_attacker` |
| 5 True pivot | Step 4 |
| 6 Weather speed | Step 6 weather-speed ability → `fast_{bias}_attacker` (no dedicated weather archetype) |
| 7 Ability underdiff | Technician hook + mechanisms for other abilities |
| 8 Technician multi-hit | Step 6 `technician_fast` |
| 10–11 Screens / status | Step 2 + mechanism emission (shared with roster Step A) |
| 12 Generic physical | Step 7 `standard_{bias}_attacker` |
| (TR-locked moveset role pin) | Step 1 `trick_room_sweeper` (**kept**) |

---

## Relation to roster Step A / Compendium discipline

- Screens / Encore / Hospitality emission remain **separately scoped** roster Step A work;
  this scan **confirms frequency** (Grimmsnarl #10, Sableye-Mega #11) but does not merge
  tickets.
- **No new Compendium file** proposed for wave 1. Only Fake Out support (#9) is marked
  `compendium` **candidate** pending product role-search need.
- Form-qualified usage names (#8, #13) are **`defer`** to canonical name/form resolution
  (explicitly OOS) — scan must not paper over that with a fake Compendium species row.

---

## Acceptance for this deliverable

1. All three corpus passes ran (50 + 77 + ability variants) — summary counts above.
2. Gap table covers every threshold-passing pattern with a tier tag and one-line reason.
3. `infer_role` proposal is one coherent vocabulary including **mandatory** phys/special/mixed
   offense labels derived from move categories, **and** retained `trick_room_sweeper` (role
   pin / tested dependency-circle behavior — final, not optional).
4. Deliverable explicitly separates infer_role classification from roster-grouping
   `attacker` coarsening.
5. Design tree synced to three-axis implementation (`standard_*` default).

---

## Scratchpad

- [X] Full scan script + JSON artifact
- [X] Gap table with tier tags
- [X] Coherent infer_role vocab + decision tree + phys/special requirement
- [X] Grouping vs classification distinction stated
- [X] Finalized: keep `infer_role` → `trick_room_sweeper` (do not touch role pin)
- [X] Implementation: three-axis `infer_role` + `role_spread` templates (`standard_*` default)
