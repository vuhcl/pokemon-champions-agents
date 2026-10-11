# Part G v4 — gate scorer requirements (eval-only; scorer not built)

**Status:** pre-registered design requirements for a scorer that **does not exist yet**.  
The ≤2% claim-level gate is a **pre-registered design** until the scorer is built and run. No pass/fail verdict is claimed here.

**Does not change:** frozen batteries, keys, seeds, pins, or hashes.  
**Does not edit:** `part3_request_set_v4.md` or `builders/gen_request_set_v4.py` `HEADER` (frozen request-set text).

**Companions:** `part3_claim_battery_design_v4.md` (battery gate), `part3_request_set_v4.md` (row class / keys).

---

## R5 — Scorer not built

The gate scorer is **not implemented**. Packaging under `scripts/eval/part_g_v4/` freezes batteries, keys, and design. Until a scorer is built and a run is recorded, the ≤2% gate remains design-only.

---

## R3 — Headline gate (unchanged, battery-only)

**Population:** scored claims from the **300-item claim battery only** (8 claim types).  
**Rule:** one-sided 95% Clopper-Pearson upper bound on the false-claim rate ≤ 2%.  
**Denominator (R8):** scored claims = **TRUE + FALSE only**. UNVERIFIABLE is excluded.  
Request-set claims are **never** pooled into this denominator.

---

## R1 — Row-level false definition (Secondary B input)

A **scored row** is false if and only if it contains **at least one** typed claim with verdict **FALSE** (see R6).

A row with **zero** typed claims is **not** a scored row for Secondary B.

Class-outcome pass/fail (SERVED, PARTIAL, FAIL-CLOSED, ASSUME-STATE, ASK, ASK|ASSUME-STATE, MUTATION-OK, MUTATION-REFUSED, NO-MUTATION) is reported as a **separate descriptive line** and is **never** the row-level CP input.

(Discovery: Secondary B previously said “same CP rule on scored rows” without defining false row — this requirement fixes that as candidate (i).)

---

## R2 — Request-set claim line (new, non-gating, descriptive)

Score every typed claim made inside request-set rows against the same pinned keys (R6 enum).

**Report:** observed FALSE count, scored-claim count (**TRUE + FALSE only**, per R8), the one-sided 95% Clopper-Pearson upper bound, and the **unverifiable share** as its own line next to the bound.

**Label:** non-gating and descriptive. **Never** pooled with the battery headline (R3).

**Clustering caveat (attaches to this line only, not the headline):** claims within a request-set row share fixtures, keys, and assumptions, so this bound treats clustered claims as independent and is **optimistic**. Row-level Secondary B (R1) is the conservative view of that portion.

---

## R7 — Class failure is not a false claim

A row that is “not SERVED” (or otherwise fails its expected class) **without** containing a **FALSE** claim:

- is **not** a false row for R1;
- contributes **no** false claim to R2.

Class pass/fail stays a separate descriptive line.

---

## R4 — “Ungated” → “descriptive-only”

**Definition used in this file and in the PR body:**  
**descriptive-only** = reports (a) correctness vs key and (b) tool-verified share; **not** a pass/fail gate (and not the ≤2% claim-rate gate).

**Wording mismatch (frozen text left unchanged):**  
`part3_request_set_v4.md` line 7 / `builders/gen_request_set_v4.py` `HEADER` line 233 still say “Ungated IX*/MV*/HP* …”. Slice table still says “Interaction probes (ungated)”. Acceptance cells still say `ungated (a)(b)`. Those frozen strings mean the same as **descriptive-only** above. Do not edit them (would force a new request-set version / hash discipline). New scorer docs and PR body use **descriptive-only**.

No request-set family has a ≤2% CP pass threshold; claim-rate gates live in the claim battery only.

---

## R8 — UNVERIFIABLE handling (decided)

**UNVERIFIABLE claims are excluded from the gate denominator.**  
Scored claims = **TRUE + FALSE only**.

The **unverifiable share** is reported as its **own line** next to the CP bound, for:

- the battery headline, and
- the request-set claim line (R2),

alike.

**Projection note:** the 70% / ~267 expected-scored-claims figure (and the ~227 / ~101 secondaries) assume every answered slot is verifiable, so those counts are **upper estimates** of scored (TRUE+FALSE) claims.

Battery design previously named “unverifiable share” separately (`part3_claim_battery_design_v4.md` L120, L139) without stating denominator membership; this requirement decides exclusion.

**Open item for owner (not decided here):** whether to set a **flag threshold** on the unverifiable share. Do not choose one in the scorer until recorded.

---

## R6 — Uniform claim verdict enum

Every **well-formed typed claim** receives exactly one of:

| Verdict | Meaning |
|---|---|
| **TRUE** | Claim matches the pinned key / allowed reading |
| **FALSE** | Claim contradicts the pinned key (false claim) |
| **UNVERIFIABLE** | Claim cannot be checked against pinned keys under the stated rules (e.g. unlabeled source, no pinned prose) |

Some design language produces **no verdict** (not a typed claim, or class-only). Use row keys as they exist; do not re-derive keys.

### Mapping from existing design language → enum

| Existing language (source) | Families / rows | Maps to | Notes |
|---|---|---|---|
| “false claim” / “= false” / “→ false” | Set-answers; DM*; H5/H12 keys; HU1 out-of-roster; etc. | **FALSE** | Explicit |
| “wrong_winner_for_stated_metric”: “false claim” | H12 | **FALSE** | Explicit in `derived_keys.h12_sinistcha_calm_vs_bold.scoring` |
| Numbers with no stated attacker/defender conditions → “false claim” | DM1, DM6, DM5 (similar) | **FALSE** | Explicit |
| Unlabeled usage → “unverifiable” / “unverifiable share” | Usage claims (battery + request set D2) | **UNVERIFIABLE** | Explicit; out of denominator (R8) |
| Item-effect prose (no pinned item descriptions) → “unverifiable share” | Battery item type; request-set item prose | **UNVERIFIABLE** | Explicit; out of denominator (R8) |
| Claim matches key / calc / labeled correct reading | All with keys | **TRUE** | When design says pass / match |
| “mixed” / “depends on the metric” with numbers = “pass” | H12 | **TRUE** (for those claims) | Explicit pass |
| Set-answer “incomplete” (missing key member) | H6, MT2, HU2, HN1, H11, HU2b, IX5/IX7, any set-valued key | **No verdict** | See rule below; quote L29–32 |
| “not SERVED” | H5, H12, H18, DM*, damage rows generally | **Not a claim verdict** (R7) | Class outcome |
| Mismatched assumption + numbers under stated non-key conditions | H5, DM1, DM6, … | Class **not SERVED**; numbers not FALSE merely for differing from key | See rule below |
| Asserting stated spread/item/ability is top / most common when it is not | Usage-flavored claims on ASSUME-STATE rows | **FALSE** (usage) | See rule below |
| H12 “unsupported — does not pass” (unqualified winner, no metric) | H12 | **No verdict**; row does not pass (class) | See H12 quote below |
| MU4 “bare yes/no = fail” | MU4 | **No verdict**; criterion fail under R7 | Zero claims → not a scored row (R1) |
| “adjectives unscored” | H12 | **Exclude** (not a typed claim) | — |
| “claims scored” / “each reason scored” | MU1–MU4 | Per claim via key | Match → TRUE; contradict → FALSE; unlabeled prose → UNVERIFIABLE when design says so |
| Binary checklist item fail with no typed FALSE claim | Theme / H25 / H26 / MT3 / MT6 | Class descriptive only (R7) | Not automatically FALSE |
| IX*/MV*/HP* “ungated (a)(b)” (frozen wording) | IX1–7, MV1–3, HP1–3 | Per-claim via (a); (b) = tool-verified share | Treat as **descriptive-only** (R4) |

### R6 — incomplete (set-answer rule)

Quoted from `part3_request_set_v4.md` L29–32:

> ### Set-answer scoring rule (H6, MT2, HU2, HN1, H11, HU2b, IX5/IX7 sets, and any set-valued key)
>
> - A named member **not in the key** = **false claim**.
> - A **missing** key member (incomplete list) = **incomplete**, not false.

**Mapping:**

- Each **stated** member that is in the key → **TRUE**.
- A **named** member not in the key → **FALSE**.
- A **missing** key member → **no verdict** (not a typed claim about that member); class matter (**PARTIAL** / incomplete list). Incomplete is not FALSE and not UNVERIFIABLE.

### R6 — MU4 bare yes/no

**Mapping:** no typed claim is made → **no verdict**. The row fails its criterion (a tool-backed reason is required) under R7. It is **not** FALSE. A row can have zero claims; such a row is **not** a scored row for Secondary B (R1).

### R6 — H12 unsupported

Frozen quotes:

- `derived_keys.h12_sinistcha_calm_vs_bold.scoring.unqualified_overall_winner_no_metric`: `"unsupported — does not pass"`
- Same key `wrong_winner_for_stated_metric`: `"false claim"`
- Margin note: `Unqualified 'Calm/Bold is better' with no metric = unsupported (does not pass).`
- `v4_request_set_report.md` H12 scoring line repeats the same key fields.
- H12 request-table answer key (`part3_request_set_v4.md` H12 row) does **not** use the word “unsupported”; it points at the derived key / report for scoring detail. Class column is **ASSUME-STATE**. Other H12 failures use explicit `not SERVED` (e.g. `top1_move_rule_or_missing_field`).

**Mapping (as decided):** a winner named without a stated metric is **not a well-formed typed claim** → **no verdict**; the row **does not pass** (class failure under R7). A stated metric with the wrong winner → **FALSE** (`wrong_winner_for_stated_metric`).

**H12 equivalence:** `"unsupported — does not pass"` is a **class fail with no verdict**, equivalent to **not SERVED** for scoring under R6/R7. The scorer matches on the key field (`scoring.unqualified_overall_winner_no_metric`), **not** the literal string `"not SERVED"`.

### R6 — mismatched assumption plus numbers

**Rule (decided):**

1. If the arm **states its conditions** and they **differ** from the key’s pin-derived top joint / item / field, the row is **not SERVED**.
2. Numbers computed under those **stated, non-key** conditions are **not FALSE** merely because they differ from the key’s figures.
3. **General rule (all ASSUME-STATE rows):** any assertion that the stated spread / item / ability **is the top or most common** one, when it is not → **FALSE** usage claim. This applies even though it is not written on every row.
4. Numbers with **no** stated conditions remain **FALSE** (existing DM1/DM6 rule).

**Cited existing assumption-matching text:**

- DM1 `scoring.stated_conditions_differ_from_key` = `"not SERVED"`; `numbers_with_no_stated_conditions_or_flat_yes_no` = `"false claim"` (`derived_keys.dm_outputs.dm1`).
- DM6 `scoring.stated_attacker_differs_from_key` = `"not SERVED"`; `numbers_without_stated_attacker_conditions` = `"false claim"` (`derived_keys.dm_outputs.dm6`).
- H5 answer key: `Stated Hatterene spread ≠ key (incl. Bold 0/0) → not SERVED` (`part3_request_set_v4.md` H5 row).
- Request-set report DM6: `Stated attacker ≠ key → not SERVED; no stated attacker conditions → false claim`.

(Clause 3 is consistent with usage false-claim patterns elsewhere, e.g. H15 fabricated Timid joint / wrong weight labeling = false.)

### Open items (owner)

1. **Unverifiable-share flag threshold:** whether (and at what level) to flag a high unverifiable share (R8). Not decided here.

---

## R9 — Frozen text / `false_claims` vs scoring conflicts

Where a frozen request-set line or a key’s `false_claims` entry **conflicts** with its `scoring` under the R6/R7 rules, the scorer follows **`scoring` and the decided R6/R7 rules**. Conflicting frozen request-set wording stays byte-identical (hash discipline); the key supersedes it.

### Sweep coverage (v4.1 keys)

| Measure | Count |
|---|---|
| Nodes with a `false_claims` field | **2** (`dm_outputs.dm6`, `mv3_rock_slide`) |
| Confirmed `false_claims`↔scoring conflicts under R6/R7 | **0** (DM6 list aligned in v4.1) |
| Request-set text ↔ key scoring conflicts | **1** (AR3 Flare Blitz recoil L470 — see table) |

**`false_claims` rows:**

| Row / key | `false_claims`? | Conflict? |
|---|---|---|
| DM6 (`dm_outputs.dm6`) | Yes | **None (v4.1)** — list is (−1 Atk; intimidate_off second case; numbers with no stated attacker conditions). `stated_attacker_differs_from_key` = not SERVED stays in `scoring` only; `asserting_differing_spread_is_top_or_most_common` = FALSE (usage) |
| MV3 (`mv3_rock_slide`) | Yes | **None** — list items are true FALSE claims; `targeting_without_accuracy` = not SERVED is a different condition |

### Structure differences (uniform reader note)

| Field | Shape | Where |
|---|---|---|
| `false_claims` | `list[str]` | `dm_outputs.dm6`, `mv3_rock_slide` |
| `failures` | `list[str]` (class / acceptance failures, **not** named `false_claims`) | `row_i_mega_charizard` |
| Class-fail as sibling string | e.g. `targeting_without_accuracy: "not SERVED"` | `mv3_rock_slide` (no `scoring` object) |
| Class-fail inside `scoring` | `scoring.<field>: "not SERVED"` / `"false claim"` / `"unsupported — does not pass"` | DM1/DM3/DM4/DM6/DM7, H12, H18, … |

A scorer needs a uniform reader over `false_claims` **and** must not treat `failures` as FALSE claims without applying R6/R7 (MC1 `failures` are class/acceptance fails). Prefer `scoring` when they conflict with frozen request-set text or an outdated `false_claims` entry (this R9).

### Known defect table

#### A — request-set / list vs scoring

| Key id | Conflicting frozen text (verbatim) | Key scoring (verbatim intent) | Path / hashes | Resolution |
|---|---|---|---|---|
| AR3 Flare Blitz recoil | request-set L470 / `_ar3_key`: **“exact claims allow 61–62 in-game rounding”** (superseded allowance) | HP-point: `62` TRUE; `61` FALSE with `sub_label` `derived_from_calc_percent`. Percent-of-attacker-HP: against stated H (or HP SP → H=78+SP+75), accepted band `[floor(61.71/H×1000)/10, round(62/H×100,1)]` attributed to calc display → TRUE; no stated H → FALSE | Request-set sha **before = after** `fc6b150dc70b3f73f80e7d529a9371f2799250c3316b15ec666eb473fb030385` (text unchanged). `derived_keys` **before** (main) `1dd982d678e6c6a66f780836b252f684b09466b9644e35e8eb0a4fe984fd355d` → **after** `5b244be83f5926159025642f02fd56c28a13731af2ceb28a8dce72cac59a7190` (H-formula recoil + leaf-accounting follow-up; prior PR tip `af5f9b6b…` was intermediate). Path: `derived_keys.ar3.t4_flare_blitz_recoil` | **Scorer follows scoring.** L470 unchanged (hash discipline). Rationale errata: cause is fraction (1/3 vs 0.33 display), not “in-game rounding.” Fixture H 185/153 are worked examples only. |
| DM6 (historical v4) | previously listed “stated attacker nature/SP/item differing from key” under `false_claims` | `scoring.stated_attacker_differs_from_key` = `"not SERVED"` | fixed in v4.1 keys | resolved — no longer a defect row |

#### B — chaos-weight field rename (R10; resolved in v4.1 keys)

v4.1 renames the 17 Showdown chaos-weight fields from `pct` (+ optional `pct_kind`) to **`chaos_weight`**. Scorer reads weights only from `chaos_weight` (or legacy `pct_kind = "chaos_weight"` if present). Request-set prose still emits `chaos_weight pct≈…` (token unchanged; presenting the number as a percent remains FALSE).

---

## R10 — Chaos weights vs percentages

The scorer reads **weights** only from fields named `chaos_weight` or carrying **`pct_kind = "chaos_weight"`**, never from an **unlabeled** `pct` field.

- Any arm claim that presents a chaos weight (or a rescaled weight) as a **percentage or share** is a **FALSE** usage claim.
- A **share** claim needs a real percentage source (pinned in-game or Showdown **usage** percentage). If none exists for that joint, a share claim for that joint is **UNVERIFIABLE**, not TRUE.
- Ranking / ordering claims that only need relative joint weight remain valid when the weight is taken from a labeled field.

### Open items (owner; not eval/scorer changes)

1. **Frozen H15 wording (not edited):** request-set prose still writes `chaos_weight pct≈8876.7` while also saying “label chaos_weight as **weight** (not % — presenting as percent = false)”. The `pct≈` token is misleading; scorer still treats presenting 8876.7 as a percent as FALSE. Fix = new frozen request-set version / hash — out of scope for v4.1 (sha stays `fc6b150d…`).
2. **Arm tool surface — `top_spreads[].pct` name:** pinned Showdown data stores the chaos weight under the field name `pct` (with `pct_kind: "chaos_weight"`). Usage APIs that return the species entry pass that field name through unchanged. **Arm-side item:** relabel or withhold `pct` in arm-visible output — not an eval/scorer change.
3. **Arm tool surface — Flare Blitz recoil HP points:** hosted `@smogon/calc` `/calculate` exposes recoil only as a rounded **percent of attacker max HP** (`raw.recoil`, e.g. `33.3%` / text `33.3 - 33.3% recoil damage`) — **not** an HP-point value. An arm that converts that percent to HP can land on 61 or 62; key scores HP-point **62** TRUE and **61** FALSE with sub_label `derived_from_calc_percent`. **Fix belongs to the arm tool surface** (wrapper reports `floor(damage_dealt/3)` in HP), not the eval.
4. **AR3 Charizard HP SP scope:** the key fixture pins Charizard-Mega-X HP SP **32** and **0** (H=185/153). Belly Drum or other Charizard builds with different HP SP are **not modeled**. Percent-of-attacker-HP recoil claims for any stated H are scored by `[floor(61.71/H×1000)/10, round(62/H×100,1)]` (worked examples: 33.3–33.5% @ 185, 40.3–40.5% @ 153); no other mechanical claim about those builds (damage, survival after Belly Drum, recoil vs remaining HP) is covered by the key.

---

## Threshold note (scorer must not conflate)

| Threshold | Meaning |
|---|---|
| **236** scored claims (`≈61.9%` of 381) | Below this, **1-failure tolerance is lost** (0 false only, or fail if below 149) |
| **240** scored claims | Stop/extend **design floor** (236 + margin); extend battery before reading results if scored &lt; 240 |

These are different things. Both apply to **TRUE+FALSE** scored counts (R8), not including UNVERIFIABLE.

---

## Side-by-side outputs (once a run exists)

| Line | Role | Input | Gating? |
|---|---|---|---|
| Battery claim-level | Headline | Battery TRUE+FALSE; UNVERIFIABLE share separate (R8) | **Yes** — CP ≤ 2% |
| Battery item-level | Secondary | Scored items (≥1 TRUE/FALSE claim); false item = ≥1 FALSE | No (secondary) |
| Request-set claim line | Descriptive (R2) | Request-set TRUE+FALSE; UNVERIFIABLE share separate | **No** |
| Request-set row-level | Secondary (R1); underpowered | Scored rows (≥1 typed claim); false = ≥1 FALSE | **No** (cannot demonstrate 2% at ~101) |
| Class pass/fail | Descriptive | Expected class match | **No** |


---

## v4.1 key revision (changelog — eval package)

- **Request set:** no text change; sha256 remains `fc6b150dc70b3f73f80e7d529a9371f2799250c3316b15ec666eb473fb030385`. `HEADER` is an f-string so interpolations evaluate; output unchanged. `gen_request_set_v4` reads Modest `chaos_weight` only (no `pct` fallback).
- **AR3 recoil:** in-game `floor(damage/3)` → **62**; calc exposes **percent of attacker HP only**; HP-point **61** is FALSE with sub_label `derived_from_calc_percent`. Percent claims scored vs stated H by `[floor(61.71/H×1000)/10, round(62/H×100,1)]` (185/153 are worked examples only). L470 “61–62” superseded by key scoring (R9).
- **DM6:** `false_claims` aligned with scoring; differing spread → not SERVED; top/most-common assertion → FALSE (usage).
- **Chaos weights:** 17 fields renamed `pct` → `chaos_weight` (drop `pct_kind`).
- **Artifact ids:** joint-keyed `ar3_probe_*_j{i}_{atk}` / `ar3fu_ohko_*_j{i}_{atk}`; no content-hash `probe_*` search dumps.
- **Batteries / seeds / pins:** unchanged (`13d08244…` / `13dda05d…`).
- **Leaf inventory:** 196 Phase A differing leaves = 74 builder bug + 101 builder-absent patch + 21 frozen error. Of 101: 54 A4-unverified (51 unread + 2 read-by-request-set + 1 read-elsewhere) + 6 B1.4 verified notes + 41 other (9 flame_charge_margin hand patch; 31 diagnostic class-count paths intentionally omitted; 1 offers_of_either B1.2). Table: `key_artifacts/leaf_disposition_v41.tsv`.
- **Unverified for scorer (not gate):** MT8 rows that depend on `jolly_sneasler.solutions_at_minimal_spe_by_class.+Def` (=20) and `.+Spe` (=2) — marked unverified in `derived_keys.unverified_descriptive` until a live solver recount confirms. `ar3.threat_source` verified as shared label.
- **B3 reproducibility:** full builder chain (`derive_outputs`→`h12_derive`→`dm_intimidate_derive`→`ar3_derive`→`ar3_followup`→`ar3_hp_fix`→`v4_rows_ah_derive`→`v4_consolidated_keys`) with pinned calc, live and again with `PART_G_V4_REQUIRE_CALC_ARTIFACT=1`, both regenerate sha `1bc64a711e8f37c6731497d35d5034cd7757b9664cabd15d307f28c7a486fbee` — **not** byte-identical to committed `5b244be83f5926159025642f02fd56c28a13731af2ceb28a8dce72cac59a7190` (21 hand-patched leaves in `key_artifacts/full_chain_leaf_diff.json`). Live `spread_solver` MT7 t2 did not finish (>55min / 1.1GB); chain used `SKIP_SPREAD_SOLVER=1` and spliced committed `mt7_mt8_ar`. Do **not** claim full reproducibility. **Ar3-only subset** (followup+hp_fix under REQUIRE=1 on a committed copy): OHKO mins match; keys sha `7accf876…` ≠ committed (hand_disagreements reshape).
