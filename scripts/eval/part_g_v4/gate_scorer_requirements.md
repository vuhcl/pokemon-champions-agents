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
2. **H15 `chaos_weight pct≈` wording** in frozen request-set text (R10) — misleading `pct≈` alongside “not a percentage”; do not edit frozen text here.

---

## R9 — Frozen `false_claims` vs scoring conflicts

Where a frozen key’s `false_claims` entry (or equivalent list) **conflicts** with its `scoring` / request-set row text under the R6/R7 rules, the scorer follows **`scoring` and the decided R6/R7 rules**. The conflicting `false_claims` entry is a **known defect** in the frozen key (table below). A fix is a **new key version with a new hash**, out of scope here — do not edit `derived_keys.json` in this package.

### Sweep coverage (read-only; complete)

| Measure | Count |
|---|---|
| Top-level keys in `derived_keys.json` | 58 |
| Nodes with a `false_claims` field | **2** (`dm_outputs.dm6`, `mv3_rock_slide`) |
| Of those, also having scoring / class-fail fields (checked for conflict) | **2** / **2** |
| Confirmed conflicts under R6/R7 | **1** (DM6 only) |

**Required-row confirmations (individually):**

| Row / key | `false_claims`? | Conflict? |
|---|---|---|
| DM1 (`dm_outputs.dm1`) | No | None — `stated_conditions_differ_from_key` = not SERVED; no-conditions = false claim (aligned) |
| DM2 (`dm_outputs.dm2`) | No | None |
| DM3 (`dm_outputs.dm3`) | No | None |
| DM4 (`dm_outputs.dm4`) | No | None |
| DM5 (`dm_outputs.dm5`) | No | None |
| DM6 (`dm_outputs.dm6`) | Yes | **Yes** — see table |
| DM7 (`dm_outputs.dm7`) | No | None — `stated_attacker_differs_from_key` = not SERVED (no conflicting list). Row text “mismatch/unstated → not SERVED / false” is compressed; scoring splits mismatch vs unstated |
| H5 (`h5`) | No | None — row: spread ≠ key → not SERVED |
| H12 (`h12_sinistcha_calm_vs_bold`) | No | None — unsupported/wrong-winner live under `scoring`, not `false_claims` |
| H18 (`h18_hyper_offense`) | No | None |
| H18b (`h18b`) | No | None |
| MU1 (`mu1_item_clause`) | No | None |
| MU2–MU4 | No dedicated key objects in `derived_keys.json` | None (inline request-set “claims scored” only) |
| MV3 (`mv3_rock_slide`) | Yes | **None** — list items are true FALSE claims; `targeting_without_accuracy` = not SERVED is a different condition, not listed under `false_claims` |
| AR1–AR3 (`mt7_mt8_ar.*` / `ar3`) | No | None |

**No other `false_claims`↔scoring conflict found beyond DM6.**

### Structure differences (uniform reader note)

| Field | Shape | Where |
|---|---|---|
| `false_claims` | `list[str]` | `dm_outputs.dm6`, `mv3_rock_slide` |
| `failures` | `list[str]` (class / acceptance failures, **not** named `false_claims`) | `row_i_mega_charizard` |
| Class-fail as sibling string | e.g. `targeting_without_accuracy: "not SERVED"` | `mv3_rock_slide` (no `scoring` object) |
| Class-fail inside `scoring` | `scoring.<field>: "not SERVED"` / `"false claim"` / `"unsupported — does not pass"` | DM1/DM3/DM4/DM6/DM7, H12, H18, … |

A scorer needs a uniform reader over `false_claims` **and** must not treat `failures` as FALSE claims without applying R6/R7 (MC1 `failures` are class/acceptance fails). Prefer `scoring` / row text when they conflict with `false_claims` (this R9).

### Known defect table

#### A — `false_claims` vs scoring (R6/R7)

| Key id | `false_claims` entry (verbatim) | Conflicting scoring / row text (verbatim) | Path | Resolution |
|---|---|---|---|---|
| DM6 | `stated attacker nature/SP/item differing from key` | `scoring.stated_attacker_differs_from_key` = `"not SERVED"`; request-set DM6 row: `mismatch → not SERVED` | `derived_keys.dm_outputs.dm6`; `part3_request_set_v4.md` DM6 row | **not SERVED** (class fail, no FALSE) unless the arm also asserts the assumption is the top/most common (FALSE usage). Do **not** count the list entry as FALSE. |

Non-conflicting DM6 `false_claims` items (aligned with `scoring`): `applying -1 Atk stage`; `presenting intimidate_off as a meaningful second case`; `numbers with no stated attacker conditions` (= `scoring.numbers_without_stated_attacker_conditions` / `scoring.applying_minus1_or_second_case` = false claim).

#### B — unlabeled / misnamed `pct` fields that are chaos weights (R10)

Sweep of all numeric `pct` / `usage_pct` / `*_pct` fields in `derived_keys.json` (damage `move_pct` / `pct_of_hp_*` excluded): **663** examined; **17** are Showdown chaos weights (all values &gt; 100); **646** are real usage-style percentages (≤100). No unlabeled chaos-weight `pct` with value ≤100 was found. Of the 17 weights: **10** carry `pct_kind: "chaos_weight"`; **7** are unlabeled (prior note said 9/8 — corrected).

| Key path | Value | What it is | Pinned source | Resolution |
|---|---|---|---|---|
| `h15_primarina.modest_top.pct` | 8876.721851952036 | chaos weight (same number as `modest_top_joint.chaos_weight`) | Showdown doubles `primarina.top_spreads[0].pct` | Scorer **ignores** unlabeled `pct`; read `modest_top_joint.chaos_weight` (+ label). Fix = new key version / hash. |
| `hn2b_forward_grid.own_lines[0].pct` | 13607.750963984106 | chaos weight (Annihilape COMMON_SPEED / joint weight) | Showdown doubles `annihilape.top_spreads` pcts | Ignore unlabeled `pct` for share claims; use as weight for ranking only if needed. Fix = new key version / hash. |
| `hn2b_forward_grid.own_lines[1].pct` | 8140.390865164758 | chaos weight | same | same |
| `hn2b_forward_grid.own_lines[2].pct` | 3774.0833345089777 | chaos weight | same | same |
| `dm_outputs.dm2.per_joint_cell[0].pct` | 21764.332640641533 | chaos weight (Hatterene COMMON_JOINT) | Showdown doubles `hatterene.top_spreads` pcts | Ignore unlabeled `pct` for share claims; cell identity / ranking only. Fix = new key version / hash. |
| `dm_outputs.dm2.per_joint_cell[1].pct` | 11742.911732149212 | chaos weight | same | same |
| `dm_outputs.dm2.per_joint_cell[2].pct` | 6184.18133744593 | chaos weight | same | same |

Labeled (`pct_kind: "chaos_weight"`) weight fields — **not defects**, but confirm the name `pct` is still a weight: `sneasler.top.pct`, `sneasler.rows[0..2].pct`, `archaludon.rows[0..2].pct`, `ar3.primarina_common_joint[0..2].pct` (10 nodes). Scorer may read these only because `pct_kind` labels them (R10).

---

## R10 — Chaos weights vs percentages

The scorer reads **weights** only from fields named `chaos_weight` or carrying **`pct_kind = "chaos_weight"`**, never from an **unlabeled** `pct` field.

- Any arm claim that presents a chaos weight (or a rescaled weight) as a **percentage or share** is a **FALSE** usage claim.
- A **share** claim needs a real percentage source (pinned in-game or Showdown **usage** percentage). If none exists for that joint, a share claim for that joint is **UNVERIFIABLE**, not TRUE.
- Ranking / ordering claims that only need relative joint weight remain valid when the weight is taken from a labeled field (or, for defect rows above, from the known pin-backed weight value without calling it a percent).

**Open item (owner; frozen text not edited):** H15 request-set prose (emitted from `builders/gen_request_set_v4.py` L155 / L687 into `part3_request_set_v4.md` L203 and H15 table row L377) writes `chaos_weight pct≈8876.7` while also saying “label chaos_weight as **weight** (not % — presenting as percent = false)”. The `pct≈` token in the key text is misleading; scorer still treats presenting 8876.7 as a percent as FALSE per the row’s own rule and R10.

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
