# Ownership form propagation — discovery and design (2026-08-09)

**Status:** Discovery + design only. No implementation in this pass.
**Final design revision:** base-form-only Mega propagation (regionals do not expand);
Z-A stone residual-risk wording tightened (decision to keep blanket rule stands).

**Deferred-from:** multi-locked candidate discovery, teammate-query, empty-team bootstrap,
team-phase routing / slot-fill flow reports. Always correctly deferred; never previously
traced end-to-end against current source.

**Precedent (attribution, not ownership):** the teammate-query design's reference to existing
item-to-Mega and conservative usage-ratio behavior
([`.cursor/plans/teammate_query_design_ea417cee.plan.md`](../.cursor/plans/teammate_query_design_ea417cee.plan.md)
§3) remains relevant as **usage/CBD attribution** discipline. Ownership propagation is a
separate modeling-policy decision and deliberately does **not** copy that stone-evidence
gate (see Part 2 §1–2).

---

## Part 1 — verified current state

### 1. `available_pool` / `owned_species_ids` normalization

**Storage shape.** `RecommenderState.available_pool` is `list[PokemonSet]`
(`recommender/state.py:446`). `PokemonSet` is a `TypedDict` that **can** carry `item`
(`recommender/state.py:54-71`). It is not a parser; the source comment defers pack/import
parsing.

**Intake can preserve items.** Bootstrap validation `_validated_bootstrap_pool(...,
preserve_fields=True)` keeps non-species fields when re-validating a presupplied pool
(`recommender/nodes.py:376-380`). Focused test confirms
`{"species": "Pelipper", "item": "Focus Sash"}` survives
(`tests/recommender/test_empty_team_bootstrap.py:104-118`). When the user supplies pool
*labels* only, rows are constructed as `{"species": label}` with no item
(`recommender/nodes.py:407-410`).

**`accept_available_pool` remains a no-op** (`recommender/nodes.py:290-291`). It does not
normalize ownership or strip items.

**Ownership extraction is exact-species only:**

```103:108:recommender/team_candidates.py
def owned_species_ids(state: RecommenderState) -> frozenset[str]:
    return frozenset(
        species_id
        for row in state.get("available_pool", [])
        if (species_id := to_id(row.get("species") or ""))
    )
```

Direct probe: `available_pool=[{"species": "Swampert", "item": "Swampertite"}]` →
`owned_species_ids` = `frozenset({"swampert"})` only. Held-item information is retained in
state storage but is **not** consulted for ownership (and is not required under the
unconditional rule).

**Parallel species-only extractions:**

| Site | What it builds | Used for |
|------|----------------|----------|
| `discover_multi_locked` (`nodes.py:1112-1116`) | `available: list[str]` of `row["species"]` | `query_candidates_for_threats(..., available_pool=available)` |
| `discover_bootstrap_directions` (`bootstrap.py:335-345`) | `available` species strings + `owned_ids = frozenset(to_id(...))` | `query_by_usage(..., available_species=available)` |
| Bootstrap presentation labels (`nodes.py:871-875`, `955-959`) | species display labels only | UI / notices |

**Leaf APIs expect species strings, not `PokemonSet`.** Each re-derives an owned ID set via
`to_id` on the string collection it was given:

- `query_counters` — `counters.py:348` (`available_pool: list[str] | None`)
- `query_threat_counters` / `query_candidates_for_threats` — `threat_counters.py:169`, `:267`
- `query_by_usage` — `by_usage.py:42` (`available_species`)
- `narrow_candidates_for_move` — `move_narrowing.py:370` (`available_species`)

Docstring at `counters.py:327-328` already states ownership is a **species-level boolean
signal**. That contract remains; form propagation will widen which IDs count as owned.

**Verdict:** every ownership path collapses to exact species IDs today. The gap is
base-form→Mega ID expansion.

---

### 2. Existing Mega-mapping mechanisms (and why ownership should not invent a third)

#### `_item_mega_forme` (`recommender/reconcile.py:660-671`)

Stone-suffix mapping (`itex`/`itey`/`ite` → `{base}megax`/`megay`/`mega`), returning the ID
only if present in `snap["species"]`. Used by:

1. **Slot reconciliation — reachable formes** (`_reachable_formes`, `reconcile.py:639-657`)
   when a *draft slot* holds a stone.
2. **Role Compendium usage attribution** stone fallback (`role_compendium.py` ~1027-1078)
   plus separate Showdown usage-ratio discount (`_SHOWDOWN_BASE_USAGE_RATIO = 0.25`).

No ownership caller exists today.

#### `lineage_ids` (`recommender/usage_data.py:195-203`)

Returns base id plus every legality child with the same `base_species_id`. Already used for
locked-slot exclusion (e.g. `discover_multi_locked` / `merge_multi_locked_candidates`).

```195:203:recommender/usage_data.py
def lineage_ids(ladder_species: str) -> list[str]:
    """Base id plus legality children, even when called with an exact child form."""
    requested = to_id(ladder_species)
    base = (_legality_species().get(requested) or {}).get("base_species_id") or requested
    kids = [base]
    for sid, ent in _legality_species().items():
        if ent.get("base_species_id") == base and sid not in kids:
            kids.append(sid)
    return kids
```

#### Equivalence check: `lineage_ids` vs `_item_mega_forme` (full legal Reg M-B Mega set)

Probe against `load_snapshot` + `is_species_legal` (76 legal Mega IDs ending in
`mega`/`megax`/`megay`; `meganium` excluded as a false substring match):

| Finding | Detail |
|---------|--------|
| Coverage | Every legal Mega appears in its base's `lineage_ids`. None missing. |
| Dual-Mega bases | `charizard` → X+Y; `raichu` → X+Y; `meowstic` → F-Mega + M-Mega. |
| **Divergence** | **`meowsticfmega` / `meowsticmmega`:** present in `lineage_ids("meowstic")`, but `_item_mega_forme("meowsticite", "meowstic", snap)` returns `None` — the helper builds `meowsticmega`, which does not exist. Mapping only works if the *base argument* is already `meowsticf` / `meowsticm`, which are not separate legal pool species. |

**Verdict:** the mechanisms are **not** equivalent across the full legal Mega set. Preferring
`lineage_ids` for discovering candidate Mega IDs is the more complete already-tested
grouping; ownership still must **not** treat every lineage member as Mega-capable (see §4
re-verify and Part 2 §1).

#### Non-Mega children in the same lineage

| Owned ID | Full `lineage_ids` also includes (legal, non-Mega) |
|----------|-----------------------------------------------------|
| `raichu` / `raichualola` | each other |
| `slowbro` / `slowbrogalar` | each other |
| `rotom` | all appliance forms |
| `floetteeternal` | `floette` (illegal) + `floettemega` |

---

### 3. Is `owned_species_ids` a single choke point?

**No.** It is the intended multi-locked ownership set, but not the only converter, and not
every ownership-mode caller goes through it.

| Caller / path | How ownership IDs are obtained | Uses `owned_species_ids`? |
|---------------|--------------------------------|---------------------------|
| Multi-locked merge / rank / preference / support branch | `owned = owned_species_ids(state)` then passed as `owned_species` (`nodes.py:1111`, `1191+`) | **Yes** |
| Multi-locked threat branch | Separate `available` species-string list → leaf `to_id` (`nodes.py:1112-1174`) | **No** (duplicate extraction) |
| Shared-teammate *admission* in multi-locked | `eligible()` checks `owned_species` inside `merge_multi_locked_candidates` (`team_candidates.py:195-201`, `279-281`) | **Yes** (via merge) |
| Shared-teammate *query* itself | No ownership filter; returns evidence only (`teammates.py`) | N/A |
| Bootstrap direction discovery | Local species-string extraction → `query_by_usage` (`bootstrap.py:335-345`) | **No** |
| `discover_single_locked` | Calls `resolve_all_support_needs(context, state)` with **defaults** `available_species=frozenset()`, `ownership_mode="off"` (`nodes.py:1008`) | **No — ownership unwired** |
| Direct leaf API use (`query_counters`, `query_by_usage`, `move_narrowing`, …) | Caller-supplied `list[str]` / `Collection[str]`; each leaf re-`to_id`s | Only if caller used the helper first |

**Implication for a fix:** expanding only `owned_species_ids` would fix multi-locked merge /
rank / shared admission / support *when that helper’s result is passed through*, but would
**miss** (a) multi-locked threat `available_pool`, (b) bootstrap, and (c) single-locked
unless wired. Leaf APIs do not need parallel Mega logic if every PokemonSet→ID conversion
site emits the expanded set.

Multi-locked design already required normalizing `PokemonSet` to species IDs once and
passing one policy to every branch
(`docs/multi_locked_candidate_discovery_and_ranking_design_2026-08-08.md` §5) — current code
partially violates that by building `owned` and `available` separately.

---

### 4. Champions Reg M-B form cases relevant to ownership

Snapshot probe (`load_snapshot` + `is_species_legal`), Reg M-B:

**Mega Evolution — the ownership-propagation case.** 76 legal Mega species IDs. Legality
lineage groups base+Mega (+ sometimes regionals) for *locked exclusion*. Ownership
propagation is narrower: only the Mega-capable base form expands (Part 2 §1).

**Regional variants cannot Mega Evolve (confirmed mechanical constraint).** Re-verify of
every legal non-Mega that shares a lineage with a legal Mega and is *not* that Mega’s
`base_species_id`:

| Owned ID | Mega(s) in same lineage | Naive lineage→Mega expand? | Correct under base-only? |
|----------|-------------------------|----------------------------|--------------------------|
| `raichu` | `raichumegax`, `raichumegay` | yes | **yes** — owned **is** the Mega base |
| `raichualola` | same | yes (wrong) | **no expand** — regional sibling |
| `slowbro` | `slowbromega` | yes | **yes** — owned **is** the Mega base |
| `slowbrogalar` | same | yes (wrong) | **no expand** — regional sibling |

Those two regional pairs are the **only** Reg M-B cases where a legal non-Mega sibling
shares a Mega’s `base_species_id`. No other regional-shares-base-with-Mega pairs appeared
in the probe.

**Already distinct species IDs — not this problem (out of scope unchanged).**

- **Rotom appliances:** separate legal IDs; do not infer appliances from `rotom`.
- **Other regionals / named variants** without a co-lineage Mega: exact ID only.
- **Illegal-but-present formes:** still gated by `is_species_legal` at candidate admission.

**Battle-only formes (still out of scope).** `aegislash` / `aegislashblade`, Castform weather
formes are not Mega IDs; base-only Mega expansion leaves them alone.

**Floette-Eternal — sole special snapshot/mechanics case.**

- `floettemega.base_species_id` = `floette`, and `floette` is **illegal** in Reg M-B.
- Sole legal non-Mega sibling in that lineage: `floetteeternal`.
- Under a strict `owned == mega.base_species_id` check, owning `floetteeternal` would
  **not** expand to `floettemega`.
- Champions mechanics (and Floettite docs) say **only Eternal Flower Floette** can Mega
  Evolve — Eternal is the Mega-capable forme, not a regional that cannot Mega.
- This is the **only** legal Mega whose recorded base is illegal
  (`floettemega` alone in that probe).

Part 2 §1 names the Eternal→Mega exception required for Champions-correctness.

---

### 5. Mega Stone obtainability spot-check (policy evidence)

**Question:** are all Reg M-B Mega Stones comparably easy for a competitively active player,
or are there meaningfully harder exceptions?

**Sources checked (secondary guides, not first-party patch notes):**
[Chouten Mega Stones guide](https://chouten.dev/articles/mega-stones-guide),
[Operation Sports stone list](https://www.operationsports.com/all-pokemon-champions-mega-stones-and-how-to-get-them/),
[GameSpot overview](https://www.gamespot.com/articles/pokemon-champions-mega-stones-explained-how-to-get-and-how-to-use/1100-6539404/).

**Not uniform.** Four acquisition routes exist:

| Route | Difficulty for a competitive player | Examples |
|-------|-------------------------------------|----------|
| Mega Evolution tutorial | Trivial (one free battle tutorial) | Abomasite, Garchompite, Gyaradosite, … (8 stones) |
| Frontier Shop @ 2,000 VP | Easy / grindable — no level gate, always in stock | Majority of stones, including Charizardite X/Y |
| Seasonal Battle Pass | Mild friction; some free-track, some premium-track; several also buyable in shop | Season M-1 cites Dragoninite, Meganiumite, Emboarite, Feraligite |
| **Legends: Z-A → HOME visitor mailbox** | **Meaningfully harder / cross-game gated** | **Chesnaughtite, Delphoxite, Greninjite, Floettite** |

**Decision (settled):** keep the blanket unconditional ownership rule for **all** Mega
stones, including these four. Do not encode per-stone obtainability gates in v1. Residual
risks state *why* the justification is uneven across the four (Part 2 residual-risks) —
not whether to reopen the decision.

---

## Part 2 — design proposal

### 1. Propagation rule (unconditional, base-form-only, via `lineage_ids`)

**Proposal:** when building the owned species-ID set from each accepted `available_pool`
row’s species ID `sid`:

1. Always include `sid` (current behavior).
2. **Explicit Floette deny:** if `sid == floette`, stop Mega expansion for that row.
   Regular Floette cannot Mega Evolve in Champions; only Eternal can. Encode this as a
   named rule, not as a side effect of Floette currently being illegal (it may become
   legal later and must still not gain Mega ownership via the base-form gate).
3. **Named Floette-Eternal exception:** if `sid == floetteeternal` and `floettemega` is
   legal, add `floettemega`. Prefer this named pair over an “illegal recorded base → sole
   legal sibling” heuristic — if plain Floette later becomes legal, that heuristic would
   stop and Eternal would silently lose Mega ownership.
4. For every other `kid` in `lineage_ids(sid)` that is a Mega forme ID
   (`endswith("mega")` / `"megax"` / `"megay"`) **and** `is_species_legal(snap, kid)`:
   - Let `mega_base` be that Mega’s lineage root (`lineage_ids(kid)[0]`).
   - **Add `kid` only if `sid == mega_base`.**
5. Do **not** consult `row.get("item")`.
6. Do **not** add non-Mega lineage siblings (no Rotom appliances, no regionals-as-owned).

Examples:

| pool row | owned IDs after propagation |
|----------|-----------------------------|
| `{species: Swampert}` | `{swampert, swampertmega}` |
| `{species: Swampert, item: Focus Sash}` | `{swampert, swampertmega}` (item ignored) |
| `{species: Charizard}` | `{charizard, charizardmegax, charizardmegay}` |
| `{species: Meowstic}` | `{meowstic, meowsticfmega, meowsticmmega}` |
| `{species: Raichu}` | `{raichu, raichumegax, raichumegay}` |
| `{species: Raichu-Alola}` | `{raichualola}` — **no Mega** |
| `{species: Slowbro}` | `{slowbro, slowbromega}` |
| `{species: Slowbro-Galar}` | `{slowbrogalar}` — **no Mega** |
| `{species: Floette-Eternal}` | `{floetteeternal, floettemega}` (exception) |
| `{species: Floette}` | `{floette}` — **explicit deny**, no Mega |
| `{species: Swampert-Mega}` | `{swampertmega}` |
| `{species: Rotom}` | `{rotom}` — appliances not added |

**Why `lineage_ids` instead of `_item_mega_forme`:** discover candidate Mega IDs from one
already-tested grouping (covers Meowstic); then **gate** addition with
`sid == mega.base_species_id` so regional siblings are excluded. Stone-mapping remains the
right tool for slot reconciliation and Compendium attribution, not ownership.

### 2. What remains conservative (and what does not)

**Deliberately not conservative (accepted):** no stone evidence required on the pool row.
Owning the Mega-capable base form is treated as equivalent to being able to field the Mega
for recommendation ownership.

**Still conservative / unchanged:**

- Regionals that cannot Mega do **not** gain Mega ownership.
- No guessing from Showdown usage ratios, CBD stone %, or “this base usually Megas.”
- Compendium `_SHOWDOWN_BASE_USAGE_RATIO` / `_MEGA_STONE_FALLBACK_PCT` stay in **usage
  attribution** only.
- Unresolved / illegal pool labels remain non-owned; propagation runs only on accepted rows.
- Propagation never overrides `is_species_legal` at candidate admission.
- Out-of-scope forms (Rotom appliances, regionals-as-owned, battle-forme aliasing, name
  resolution) stay exact-ID only.

### 3. Where the fix lands

**Proposal — one shared expansion helper, then route every PokemonSet→owned-ID conversion
through it, including single_locked.**

1. **Primary implementation site:** extend `owned_species_ids` in
   `recommender/team_candidates.py` to apply §1 using `lineage_ids` + legality snapshot
   (base-form gate + Floette exception).
2. **Mandatory call-site cleanup:**
   - `discover_multi_locked`: derive threat `available_pool` from the **same** expanded ID
     set (no second species-only list comprehension).
   - `discover_bootstrap_directions`: replace local `owned_ids` / `available_species`
     construction with `owned_species_ids(state)` (or the same helper).
3. **Required scope — `discover_single_locked`:** pass real `state["ownership_mode"]` and
   the expanded owned-ID set into `resolve_all_support_needs` / move-narrowing paths
   (`nodes.py:1008` today hardcodes `off` + empty owned). Leaving this unwired would
   silently omit Mega candidates on the single-anchor path after every other phase gained
   them — not acceptable as a follow-up.
4. **Leaf APIs** (`query_counters`, threat counters, `query_by_usage`, `move_narrowing`):
   **no Mega logic** if callers pass the expanded ID collection. Keep species-string
   contracts.

**Not proposed:** changing `accept_available_pool` into a second ownership engine; changing
`PokemonSet` storage; per-stone obtainability gates in v1; inventing a second Mega table.

### 4. Explicitly out of scope

- Canonical name / shorthand resolution (`Eternal Floette` → `Floette-Eternal`, etc.) —
  still separately deferred.
- New form-legality or Mega-stone databases / obtainability tables.
- Rotom appliance / regional / size-form inference from base IDs.
- Battle-forme ownership aliasing (Aegislash ↔ Blade).
- Treating Compendium usage-ratio / CBD stone% heuristics as ownership evidence.
- Mutually exclusive Mega roster / selected-four modeling (separate backlog).
- Encoding Z-A / Battle Pass stone gates as ownership exceptions (blanket rule kept).

---

## Residual risks / open questions for implementation

1. **`owned_only` tradeoff (deliberate, accepted).** Under `owned_only`, users will see Mega
   forms of every **Mega-capable base** they listed, **without any confirmation of stone
   possession**. That is the intended consequence of the unconditional rule.

2. **Z-A / HOME-gated stones — blanket rule kept; justification is uneven.**
   - **Floette-Eternal / Floettite:** airtight under this design. The Pokémon itself is
     Z-A-story-locked; owning Eternal already implies clearing the same cross-game gate the
     stone requires. There is no ordinary in-Champions path to own the Mega-capable forme
     without that barrier. Combined with the Eternal→Mega exception in §1, listing Eternal
     is a coherent ownership claim for Mega Floette.
   - **Chesnaughtite / Delphoxite / Greninjite:** **not** the same airtight argument.
     Chesnaught, Delphox, and Greninja are ordinarily obtainable without Legends: Z-A; only
     the *stone* is HOME/Z-A mailbox-gated. The blanket unconditional rule still expands
     those bases to their Megas and can therefore over-claim stone possession. Kept anyway
     for simplicity and consistency with the other stones — not because the Floette-style
     reasoning applies. v1 does not encode a special case for these three.

3. **Dual-Mega expansion:** owning Charizard / Raichu / Meowstic marks **both** Mega IDs
   owned. Ranking / one-Mega-per-team constraints remain separate backlog.

4. **Tests to add when implementing:**
   - base expands; regional sibling does not (`Raichu` vs `Raichu-Alola`, `Slowbro` vs
     `Slowbro-Galar`);
   - item field ignored; Rotom does not expand to appliances;
   - Charizard both Megas; Meowstic both gender Megas;
   - Floette-Eternal expands to Mega Floette;
   - plain Floette does not (explicit deny);
   - multi-locked threat + bootstrap + **single_locked** all see the expanded set;
   - soft vs `owned_only` differ only by filter/sort semantics over the same expanded IDs.

---

## Scratchpad

- Goal: final design — base-form-only Mega prop; Z-A residual wording.
- [x] Re-verify Raichu/Slowbro regional pairs (only two such cases)
- [x] Floette-Eternal vs floettemega.base=floette (illegal) — exception required
- [x] Tighten Z-A residual risks (Eternal airtight vs other three simplicity)
- [x] Final doc revision (no code)
