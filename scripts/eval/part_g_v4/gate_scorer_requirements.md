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
Request-set claims are **never** pooled into this denominator.

---

## R1 — Row-level false definition (Secondary B input)

A **scored row** is false if and only if it contains **at least one** typed claim with verdict **FALSE** (see R6).

Class-outcome pass/fail (SERVED, PARTIAL, FAIL-CLOSED, ASSUME-STATE, ASK, ASK|ASSUME-STATE, MUTATION-OK, MUTATION-REFUSED, NO-MUTATION) is reported as a **separate descriptive line** and is **never** the row-level CP input.

(Discovery: Secondary B previously said “same CP rule on scored rows” without defining false row — this requirement fixes that as candidate (i).)

---

## R2 — Request-set claim line (new, non-gating, descriptive)

Score every typed claim made inside request-set rows against the same pinned keys (R6 enum).

**Report:** observed FALSE count, scored-claim count, and the one-sided 95% Clopper-Pearson upper bound.

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

## R8 — UNVERIFIABLE handling (open — do not invent)

**Battery design does not state** whether unverifiable claims are **in or out** of the scored denominator for the ≤2% false-claim gate.

Closest quotes (not a denominator rule):

| Location | Text |
|---|---|
| `part3_claim_battery_design_v4.md` L120 | “Usage claims: always source-labeled (in-game vs Showdown); unlabeled → unverifiable share.” |
| `part3_claim_battery_design_v4.md` L139 | “prose about item effects = unverifiable share.” |
| `part3_claim_battery_design_v4.md` L176 | “Scored claims — Claims the arm actually authors that enter the false-claim gate denominator” |

“Unverifiable share” is named separately from “scored claims,” but the design never says UNVERIFIABLE is excluded from (or included in) *n* for the CP gate.

**Open item for owner:** choose whether UNVERIFIABLE is in or out of the battery headline scored denominator; apply the **same** rule to the R2 request-set claim line. Do not implement either choice until recorded here.

---

## R6 — Uniform claim verdict enum

Every typed claim receives exactly one of:

| Verdict | Meaning |
|---|---|
| **TRUE** | Claim matches the pinned key / allowed reading |
| **FALSE** | Claim contradicts the pinned key (false claim) |
| **UNVERIFIABLE** | Claim cannot be checked against pinned keys under the stated rules (e.g. unlabeled source, no pinned prose) |

Use row keys as they exist; do not re-derive keys.

### Mapping from existing design language → enum

| Existing language (source) | Families / rows | Maps to | Notes |
|---|---|---|---|
| “false claim” / “= false” / “→ false” | Set-answers; DM*; H5/H12 keys; HU1 out-of-roster; etc. | **FALSE** | Explicit |
| “wrong_winner_for_stated_metric”: “false claim” | H12 | **FALSE** | Explicit in report/key |
| Numbers with no stated attacker/defender conditions → “false claim” | DM1, DM6, DM5 (similar) | **FALSE** | Explicit |
| Unlabeled usage → “unverifiable” / “unverifiable share” | Usage claims (battery + request set D2) | **UNVERIFIABLE** | Explicit |
| Item-effect prose (no pinned item descriptions) → “unverifiable share” | Battery item type; request-set item prose | **UNVERIFIABLE** | Explicit |
| Claim matches key / calc / labeled correct reading | All with keys | **TRUE** | When design says pass / match |
| “mixed” / “depends on the metric” with numbers = “pass” | H12 | **TRUE** (for those claims) | Explicit pass |
| “incomplete” (missing key member; set-answer rule) | H6, MT2, HU2, HN1, H11, HU2b, IX5/IX7, any set-valued key | **OPEN** | Battery L106: “incomplete, not false” — not mapped to TRUE / FALSE / UNVERIFIABLE / exclude-from-scoring |
| “not SERVED” | H5, H12, H18, DM*, damage rows generally | **Not a claim verdict** (R7) | Class outcome only unless a FALSE claim is also present |
| Mismatched stated assumption / spread ≠ key → “not SERVED” | H5, DM1, DM6 | **OPEN** for claim-level | Class = not SERVED is clear (R7); whether any authored numeric claim is also FALSE is not stated uniformly |
| “unsupported — does not pass” (unqualified Calm/Bold better, no metric) | H12 | **OPEN** | Class fail vs UNVERIFIABLE vs FALSE not stated |
| “bare yes/no = fail” | MU4 | **OPEN** | May mean no scored typed claim + class fail, or an implicit FALSE; not stated |
| “adjectives unscored” | H12 | **Exclude** (not a typed claim) | Not TRUE/FALSE/UNVERIFIABLE |
| “claims scored” / “each reason scored” | MU1–MU4 | Per claim via key | Reasons that match tools → TRUE; that contradict → FALSE; unlabeled mechanics prose → UNVERIFIABLE when design says so |
| Binary checklist item fail with no typed false claim | Theme / H25 / H26 / MT3 / MT6 | Class descriptive only (R7) | Not automatically FALSE |
| IX*/MV*/HP* “ungated (a)(b)” (frozen wording) | IX1–7, MV1–3, HP1–3 | Per-claim via (a); (b) = tool-verified share | Treat as **descriptive-only** (R4); claims still get TRUE/FALSE/UNVERIFIABLE under R2 |

### Open items (owner)

1. **R8:** Is UNVERIFIABLE in or out of the scored denominator for the battery headline (and thus R2)?
2. **R6 / incomplete:** Map “incomplete” (missing set member) to UNVERIFIABLE, exclude-from-scoring, or something else?
3. **R6 / H12 unsupported:** Map “unsupported — does not pass” to FALSE, UNVERIFIABLE, or class-only?
4. **R6 / MU4 bare yes/no:** Class-only fail, or FALSE claim?
5. **R6 / mismatched assumption + numbers:** When class is not SERVED because stated spread ≠ key, are the numbers also FALSE claims or unscored?

---

## Threshold note (scorer must not conflate)

| Threshold | Meaning |
|---|---|
| **236** scored claims (`≈61.9%` of 381) | Below this, **1-failure tolerance is lost** (0 false only, or fail if below 149) |
| **240** scored claims | Stop/extend **design floor** (236 + margin); extend battery before reading results if scored &lt; 240 |

These are different things.

---

## Side-by-side outputs (once a run exists)

| Line | Role | Input | Gating? |
|---|---|---|---|
| Battery claim-level | Headline | Battery scored claims (TRUE/FALSE; UNVERIFIABLE TBD R8) | **Yes** — CP ≤ 2% |
| Battery item-level | Secondary | Scored items; false item TBD from FALSE claims | No (secondary) |
| Request-set claim line | Descriptive (R2) | Request-set typed claims | **No** |
| Request-set row-level | Secondary (R1); underpowered | Scored rows; false = ≥1 FALSE claim | **No** (cannot demonstrate 2% at ~101) |
| Class pass/fail | Descriptive | Expected class match | **No** |
