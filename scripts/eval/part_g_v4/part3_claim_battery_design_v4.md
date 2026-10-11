# Part G v4 — claim battery + false-legal battery design (plan-only; not generated)

**HEAD:** `e935de9b2051da6fe968b87087b27c7b5901168b`  
**Companion:** `scripts/eval/part_g_v4/part3_request_set_v4.md`  
**Generated:** claim + false-legal batteries under `scripts/eval/part_g_v4/battery/` (seed 0; see `battery_manifest.json`). Do not run items through the graph or any model in this package PR.

**Location:** `scripts/eval/part_g_v4/` (eval-only), including generator, seed, pinned SHAs, generated battery + file hash.

**Ground-truth framing:** the 8-type claim battery measures **fidelity to the pinned snapshot**, not independent game truth. Both the pinned legality blob and the Showdown-source oracle derive from Showdown — a cross-check catches **extraction/transform bugs**, not Showdown-vs-game differences.

**Scoring context:** request-set scoring is **per slice** (see companion). Bare-LLM comparison on the battery uses the same extractor and same items; bare-LLM rate is comparison-only, not gated.

---

## Gate decision rule (verbatim; Vu decided)

**Gate:** one-sided 95% Clopper-Pearson upper bound on the false-claim rate ≤ 2%, applied to **scored claims the arm actually authors** (model-authored / extracted), **not** to designed claim slots.

**Exact pass table** (smallest scored-claim count `n` at which `k` false claims still pass; binary-search CP UCB ≤ 0.02):

| Observed false claims k | Exact min scored claims n | Prior design-table n | Δ |
|---|---|---|---|
| 0 | **149** | 149 | 0 |
| 1 | **236** | 237 | −1 |
| 2 | **313** | 314 | −1 |
| 3 | **386** | (not listed; ~387 approx) | — |

**Denominator:** the arm’s **scored** (model-authored) claim count after a run.

**Design floor 240:** the 1-failure threshold (**236**) plus a small margin; stop/extend if scored claims &lt; 240 before reading results.

**Size target:** **300** items → **381** designed claim slots → expected scored claims = `381 × 0.70 ≈ 267` under the explicit **70% answer-rate** pre-run assumption (below). At that expected scored count, headline tolerance is **1** false claim (not 2).

**Stop/extend rule:** If scored claims are less than 240 after a run, the battery is **extended BEFORE any results are read**; no conclusions from a short run.

**Verdict cost accepted:** a failing result is reported as a **failure**, not re-run or re-sized after the fact.

**Bare-LLM:** same extractor, same items; report its scored count separately; bare-LLM rate is a **comparison, not gated**.

---

## Pinned data (same as request set)

SHAs are **git blob SHAs** (`git hash-object <file>`).

| Blob | Path | Blob SHA (`git hash-object`) |
|---|---|---|
| Legality | `data/legality/champions.v1.json` | `ca5bb8181448765875396ce3b02561923c3e4694` |
| In-game usage | `data/usage/champions-reg-mc.ingame_doubles.v1.json` | `65f8c51e3ce4068736a2c8aa65609f836064cbcc` |
| Showdown usage | `data/usage/champions-reg-mc.showdown_doubles.v1.json` | `63bcefe4512a202d75b62e79f2ccc5436527b46e` |
| Move static | `data/moves/static.v1.json` | `c4f2aabe8ffb420a70e77afaa50b5a4d616a1f54` |
| Move flags | `data/moves/flags.v1.json` | `89a00b2c46df4c139027f81f77627a4a85fdd631` |
| Move accuracy | `data/moves/gen9_accuracy.v1.json` | `4eeb96eacfdee56ccaf7e9a7b8d6a65c6fb1da20` |
| Move stat boosts | `data/moves/stat_boosts.v1.json` | `040059884684b27f0894e484c7c987fb5aef158e` |

Record repo commit: `e935de9b2051da6fe968b87087b27c7b5901168b`. Move static at `8cfe63a` (PR #259); flags/accuracy/boosts refresh merge `6674b74c41810f63d1a25453d26ea8498d0b9341` (PR #260); four move blob SHAs in the table.  
**Re-pin invalidates keys.** Arm and bare-LLM harness both read the frozen copy.

**Defect D7:** `query_teammates` Showdown-first vs in-game default — unchanged here. Usage tools take explicit **source** + label.

**ADR-060:** answer keys / battery GT from pinned JSON, standalone Spe/HP formulas, or calc HTTP — not recommender claim verifiers.

---

## Oracle cross-check (one pass; this task)

**Mod:** `champions` (matches pinned `meta.source.mod`; formats Reg M-C). Not `championsregmb` (would be regulation noise).

**Artifact:** `scripts/eval/part_g_v4/key_artifacts/oracle_crosscheck.json` (filled by `scripts/eval/part_g_v4/builders/oracle_crosscheck.py`).

**Result (one pass completed):** artifact `scripts/eval/part_g_v4/key_artifacts/oracle_crosscheck.json`.

| Axis | only_in_pinned | only_in_oracle | notes |
|---|---|---|---|
| species legality | 0 | 0 | match |
| item legality | 0 | 0 | match |
| types (intersection sample) | — | — | mismatch_count 0; **sample size = 355** (full legal-species intersection; script caps at 5000) |
| abilities (intersection sample) | — | — | mismatch_count 0; **sample size = 355** (same intersection) |
| moves | 515 | 0 | **oracle_snapshot.ts writes `moves: {}`** (no move extract in eval oracle path) — not a roster disagreement; do not treat as extraction bug |

**Moves and learnsets were NOT cross-checked** (oracle writes `moves: {}`). **H11, SC1, SC2, IX4 and the damage keys rest on pinned learnsets and pinned move data only.**

Oracle Showdown commit in this pass: `942cda71…` (live cache). Pinned extract source commit: `9fb3a5b9…`. Species/item agreement still held across that commit drift for this pass. **Do not tune keys to this output.**

---

## Generator conventions

- **Seed:** `random.seed(0)` (stdlib); record in battery header.
- **Stratification:** legal vs illegal; usage top- vs bottom-quartile species; Spe ties; Mega/regional forms; common vs rare moves/items.
- **Derived-stat (9th type):** **deferred (D6)**. HU1 remains request-level only. Battery = **8 types**.

---

## Model-authored claim (scoring definition)

**Include:** text the model writes in the turn payload / free prose.  
**Exclude:** text rendered **verbatim** by tools (tool read-backs, formatted pending footers, stamped claim templates that are byte-identical to tool output).

**Counting (D5 lean — freeze at registration):**

1. **Primary:** frozen **per-template answer parsers** for battery templates (deterministic).  
2. **Audit:** fixed-seed **human** sample (size fixed at registration) to estimate missed extra claims in free prose.  
3. **Cross-check only:** LLM judge from a **different model family** — not the gate.

**Set-valued answers (same rule as request set):** named member not in key = false claim; missing member = incomplete, not false.

**Must freeze before scoring:** negation policy; multi-claim dedupe; whether partial lists count as N claims; tool-verbatim exclusion rules.

---

## Claim forms added in v4

- **Speed condition labels:** Scarf, Tailwind, Spe stage boosts, Unburden — claims must name the condition they assume.
- **Min-SP 4-part** (inverse speed): neutral and beneficial nature, each as “N suffices and N−1 does not”. Outcomes vs budget R: fits / shortfall / unreachable. Reachability considers Scarf+Tailwind stack. Never “not recommended”.
- **Quantified grid claims:** Spe numbers must match script cells.
- **Crit-conditioned damage:** score from calc description string (“on a critical hit”).
- **Chip damage:** standalone formula line (Rocky Helmet 1/6, Rough Skin/Iron Barbs 1/8, Life Orb recoil 1/10, floored, min 1) — mark hand-derived unless verified from Showdown source or calc.
- **Ability-text quotes:** verbatim quotes from `data/abilities/all.v1.json` allowed as ability claims (string match).
- **Usage claims:** always source-labeled (in-game vs Showdown); unlabeled → unverifiable share.

---

## Per-type design (8 types)

### 1. Typing
- **Templates:** “What type is {S}?” / “Is {S} a {T} type?” / “What are {S}’s types?” / “Is {S} dual-type {T1}/{T2}?” / “Does {S} have {T} typing?”
- **GT:** pinned snapshot `species.*.types` — **fidelity to pinned snapshot**.
- **Independence:** JSON only; no recommender verifiers.

### 2. Ability
- **Templates:** “Does {S} have {A}?” / “What abilities can {S} have?” / “Is {A} legal on {S}?”
- **GT:** snapshot abilities + legality flags.
- **Independence:** JSON. Verbatim ability-description quotes allowed when matching pinned text.

### 3. Item
- **Templates:** “Is {I} legal on {S}?” / “Is {I} legal?”
- **GT:** snapshot items + rules.
- **Independence:** JSON. (No pinned item descriptions — prose about item effects = unverifiable share.)

### 4. Legality (species)
- **Templates:** “Is {S} legal?” / “Can I use {S} in Champions VGC?”
- **GT:** snapshot `is_nonstandard` / tier / tags (pinned fidelity).
- **Independence:** JSON-only for keys; Showdown-source oracle used once for extraction cross-check (see above), not as live GT for items.

### 5. Speed
- **Templates:** outspeed / who-faster / scarf / TW-conditioned / min-SP.
- **GT:** standalone `floor(n*(base+SP+20))` from snapshot base Spe; optional calc `raw.stats`.
- **COMMON_SPEED:** top 3 distinct grouped final-Speed values (group joints by Spe, sum weights, rank).
- **Scarf lines:** only Spe-32 at neutral and beneficial Spe+ nature (2 per side); other values without Scarf.
- **Independence:** standalone formula or calc HTTP — not `effective_spe` as oracle.

### 6. Damage
- **Templates:** OHKO / damage range / 2HKO / crit-conditioned.
- **GT:** `@smogon/calc` via HTTP; store requests+responses.
- **Independence:** **invocation path**, not engine (D4).
- **Ability:** every damage claim carries the ability it was computed under; verifier compares like with like. Mega formes use the form ability from pinned legality (Mega-X = Tough Claws — never rely on calc default Blaze).

### 7. Usage (reg + date)
- **Templates:** top partners / common items / teammates.
- **GT:** pinned usage files by labeled source. In-game default; Showdown for Mega/form and joints. **D9:** no in-game joint nature+spread claims.
- **Independence:** pinned JSON.

### 8. Move static
- **Templates:** category / base power / type / status BP 0 / priority / target / displayed PP.
- **Closed property list (inventory-confirmed):** id, name, type, category, basePower, is_nonstandard, flags (`flags.v1.json` SHA `89a00b2c…`), boosts (`stat_boosts.v1.json` SHA `04005988…`), accuracy (`gen9_accuracy.v1.json` SHA `4eeb96ea…`), priority / target / displayed PP (`static.v1.json` SHA `c4f2aabe…`, 515 moves).
- **Independence:** JSON.

---

## What “realized” / scored means (two different counts)

| Term | What it counts | When |
|---|---|---|
| **Claim slots (battery inventory)** | Designed scorable claim entries on the 300 items (`n_claims` / `claims[]`) | At generation |
| **Scored claims** | Claims the arm actually authors that enter the false-claim gate denominator | After a model run |

**381** = designed claim slots (seed 0). **Expected scored claims** = `381 × 0.70 ≈ 267` under the explicit **70% answer-rate** pre-run assumption (30% decline/incomplete → no scored claims from that item). The gate always uses the arm’s **actual** scored count; if the answer rate is lower, tolerance shrinks (see staircase).

## Sizing arithmetic (300 items → 381 slots → ~267 expected scored)

**Assumptions (explicit):**

- Per-type claims/item (if answered): typing 1.0, ability 1.0, item 1.1, legality 1.0, speed 1.2, damage 1.5, usage 2.0, move static 1.3.
- **Answer rate 70%** (pre-run assumption): fraction of items that yield a scorable response.

| Type | Items | Claims/item | Designed slots @100% | Est. scored @70% |
|---|---|---|---|---|
| typing | 38 | 1.0 | 38.0 | 26.6 |
| ability | 38 | 1.0 | 38.0 | 26.6 |
| item | 38 | 1.1 | 41.8 | 29.3 |
| legality | 30 | 1.0 | 30.0 | 21.0 |
| speed | 44 | 1.2 | 52.8 | 37.0 |
| damage | 44 | 1.5 | 66.0 | 46.2 |
| usage | 38 | 2.0 | 76.0 | 53.2 |
| move static | 30 | 1.3 | 39.0 | 27.3 |
| **Sum** | **300** | | **381.6** | **267.2** |

**Generated battery (seed 0):** **300** items → **381** claim slots.  
**Expected scored:** `381 × 0.70 ≈ 267`. At that count, headline max false claims that still pass = **1**.  
**Design floor 240** = 1-failure threshold (236) + margin; if scored &lt; 240, extend before reading results.

### Answer rates at which headline tolerance drops

Scored claims ≈ `381 × answer_rate`. Exact thresholds from the pass table:

| If answer rate falls below… | Scored n falls below… | Max false claims that still pass |
|---|---|---|
| **82.2%** (`313/381`) | 313 (2-failure min n) | drops from 2 → **at most 1** |
| **61.9%** (`236/381`) | 236 (1-failure min n) | drops from 1 → **0 only** |
| **39.1%** (`149/381`) | 149 (0-failure min n) | even **0** false fails the gate (extend) |

At the assumed **70%** rate (expected ~267 scored), tolerance is **1** false claim. If the arm’s actual answer rate is lower, tolerance shrinks accordingly.

---

## Gate independence assumption (statistical)

The headline gate treats scored-claim outcomes as **independent**. That is **not** addressed by ADR-060 (oracle independence from code under test).

**Limitation:** claims cluster by battery item (and by shared keys / fixtures — e.g. Intimidate DM rows, H12 threats). The effective independent sample is smaller than the scored-claim count, so the claim-level bound is **optimistic**.

**70% answer rate** is a **pre-run sizing assumption**. The gate verdict uses the arm’s **actual** scored counts from the first run. An answer rate below about **62%** (`236/381`) loses the 1-failure tolerance (0-only reading, or extend if below 149).

Headline gate is unchanged: claim-level, one-sided 95% Clopper-Pearson UCB ≤ 2% on scored claims. Two labeled secondaries sit beside it (same exact thresholds: 0→149, 1→236, 2→313, 3→386).

### What is a battery item vs a request-set row?

| Pool | Count | Unit |
|---|---|---|
| Claim battery | **300** items | One prompt item with `n_claims` designed slots (mean ≈ 1.27; seed 0 → 381 slots) |
| Request set | **134** rows | One outcome-class row each (multi-turn cases = **one** row, not one item per turn) |

These are **separate** eval pools — not one battery item per request-set row, and not repeated phrasings of rows. Request-set companions (AR3, IS2, build traps, H12/DM*) are documented next to the battery and are **not** in the battery item pool. Battery items have no `fixture_id` linking them to request-set rows; some claim types reuse species/keys conceptually. Within a request-set row, turns/claims share fixtures, keys, and assumptions (not independent).

### Secondary A — item-level (claim battery)

Same CP rule on **scored items** (items with ≥1 model-authored claim).

**Independence assumption (within item):** each designed claim slot is answered iid with \(p = 0.70\); an item is scored if at least one of its slots is answered. Items are treated as independent of each other for this secondary.

**Method (direct):** \(\mathbb{E}[\text{scored items}] = \sum_i \bigl(1 - (1-p)^{n_i}\bigr)\) over the 300 generated items (seed 0).  
`300 × 0.70 = 210` is a **lower bound** (it ignores multi-slot items; mean \(n_i \approx 1.27\)).

| | Value |
|---|---|
| Expected scored items (direct) | **≈227** (`227.01` on seed-0 battery; `≈227.14` from design rates) |
| Distance to 236 (1-failure line) | **9** below |
| Max false items that still pass | **0** |

### Secondary B — row-level (request set)

Same CP rule on **scored rows** (rows with ≥1 answered claim-type slot).

**Independence assumption (within row):** each claim-type token on the row (split on `+`) is answered iid with \(p = 0.70\); a row is scored if at least one slot is answered.

**Method (direct):** \(\mathbb{E}[\text{scored rows}] = \sum_j \bigl(1 - (1-p)^{n_j}\bigr)\) over the 134 rows’ claim-type token counts → **≈101**. One-opportunity lower bound = `134 × 0.70 ≈ 94`.

| | Value |
|---|---|
| Expected scored rows (direct) | **≈101** |
| Max false rows that still pass | **none** (`max_k = −1`; even 0 false fails — need ≥149 for k=0) |

**Plainly:** under the 70% answer-rate assumption, the request set **cannot demonstrate the 2% bound at row level**.

### Side-by-side

| Level | Expected n (at 70%) | Max false that still pass | Independence assumption |
|---|---|---|---|
| **Headline** (scored claims) | ≈267 | **1** | scored claims independent |
| **Secondary A** (scored battery items) | ≈227 | **0** | slots iid within item; items independent |
| **Secondary B** (scored request-set rows) | ≈101 | **cannot demonstrate** | claim-type tokens iid within row |

---

## False-legal battery

- **Size:** **≥ 240** illegal-entity prompts under the same gate spirit.
- **Generator:** illegal species × illegal items × templates; stratify species-only / item-only / both.
- **Control:** matched **legal**-entity prompts **75–100** for over-refusal (false-illegal).
- **Score:** treats illegal as usable → fail; legal treated illegal → false-illegal (reported; not the ≤2% false-claim gate unless Vu merges metrics later).

---

## Bare-LLM condition

- Same items, same extractor, same frozen data.
- Report realized claim count separately.
- Rate is **comparison only**, not gated.

---

## Request-set companions (not battery item pool)

**AR3** — Multi-turn Mega Charizard X Belly Drum. Classes: t1 SERVED; t2 SERVED|ASK; t3 MUTATION-OK; t4 SERVED; t5 PARTIAL; t6 SERVED. Claims: learnset/item, move suggest, mutation lock, damage+recoil (Tough Claws), speed ladder +1, leftover HP. Keys: `derived_keys.ar3` + `part1_followup`.

**IS2** — Basculegion Scarf R=24 vs Dragapult. Class: ASSUME-STATE+PARTIAL. Claims: speed. Key: `derived_keys.is2_min_spe`.

**Build traps (IC1…MC1)** — per-turn claim types / classes:

| Id | Turns / class | Claim types |
|---|---|---|
| IC1 | t1 SERVED, t2 MUTATION-OK | usage+legality (item; Item Clause) |
| GT1 | SERVED | usage+legality (Trick+Scarf; Choice Past) |
| GS1 | t1 SERVED, t2 MUTATION-OK | usage+legality+state (choice-lock status names) |
| LZ1 | SERVED (+ ASSUME-STATE form) | usage+legality (stallingMove; mega stone) |
| TB1 | SERVED (stated correction) | legality+learnset (type-boost no Fire) |
| TB2 | MUTATION-OK (stated consequence) | legality+state (Charcoal after swap) |
| MM1 | SERVED | legality (mega stone required) |
| MM2 | MUTATION-REFUSED | legality+state |
| MC1 | ASK or ASSUME-STATE | usage+legality+ability (form/stone/Drought) |
| RB1 | MUTATION-OK (stated consequence) | move-static (category, boosts from stat_boosts) |
| H12 | ASSUME-STATE (Calm vs Bold Sinistcha; variant A/B) | damage |
| DM3/DM4 | ASSUME-STATE (dual Intimidate cases) | damage (+ ability assumption) |
| DM6 | SERVED (immune single case) | damage+ability |
| DM7 | ASSUME-STATE (Defiant on/off) | damage+ability |

## Risks / unknowns

1. Defect D7 teammate source mismatch until tool source argument ships.
2. Damage GT shares calc engine (invocation independence only).
3. Per-template parsers miss free-prose extras — human audit estimates residual.
4. Realized n may fall below 240 → extend before reading results.
5. Move-inventory refresh pins (static/flags/accuracy/boosts) must stay byte-identical to recorded SHAs; re-pin invalidates MV/IX keys.

---

## Status

Design frozen with generated battery + hash in this package. Held-out: do not use for tuning; any change is a new version with a new hash.
