# Freeze preparation item 2 — confirmations

## a. MT2 / H6 (stale pins)

```
score_transcript([{MT2…},{H6…}]) → excluded=stale_pin, stale=True for both
errata.stale_pin_rows = ["MT2", "H6"]
```

**Answer:** Reported separately as `excluded: "stale_pin"` — not scored as fail and not in per-class rates.

## b. errata.json

| entry | present |
|---|---|
| IC1 (`class_cells`) | yes |
| IS2 (`class_cells`) | yes |
| MRB1 (`substitutions`) | yes |
| H11 (`set_answer.allowed_not_required`) | yes |
| stale rows MT2, H6 | yes (`stale_pin_rows`) |
| H25 (`substitutions`) | yes; note says plan not-covered |

**Answer:** Leave H25 substitution in place (harmless when fixture unused; documents the loader rule if someone loads it). Removing is optional cleanup, not required for freeze.

## c. Not-covered reasons (35) vs registration draft categories

`LAST_PART6_PROPOSAL.md` only has counts (99/35) — **no per-row reason list**. Claude registration draft is not in this worktree. Mapping below is from local notes (`LAST_PART0_RETRIAGE`, `LAST_H19_H20`, `LAST_H25_H26_MT4`, Part 3/5) into the draft’s reason vocabulary. **Differ from any draft text Vu holds → send those rows.**

| id | local reason category |
|---|---|
| H12 | coverable-now / hand surface (large claim) — closest: **no freezable rule** for claim-level on arm |
| H17 | **bootstrap/empty team** |
| H18 | **bootstrap/empty team** |
| H19 | **bootstrap/empty team** |
| H20 | **bootstrap/empty team** |
| H21 | coverable-now hand — **no freezable rule** (ASSUME-STATE membership) |
| H22 | coverable-now hand — **no freezable rule** |
| H25 | **all-locked fixtures** / candidates not ready |
| H26 | **all-locked fixtures** / candidates not ready |
| H27 | coverable-now (pending loader) — left out by readiness — **no route** until Vu adds |
| MT4 | **no route to pass by correct behavior** (no show-candidates tool) |
| MT7 | **dev** |
| MT8 | **dev** |
| AR1 | **dev** (dup of MT7) |
| AR2 | **dev** (dup) |
| AR3 | **not built** (6-turn compound) |
| SC1 | **not built** (draft-condition store) |
| SC3 | **not built** |
| TS1 | **not built** |
| GT1 | **not built** / paste gap |
| LZ1 | **not built** |
| IX2 | **not built** |
| IX3 | **not built** |
| IX4 | **not built** |
| IX5 | **not built** |
| IX6 | **not built** |
| IX7 | **not built** |
| DM5 | **not built** (fixture route) |
| OL7a | coverable-now — left out — **no route** until Vu adds |
| OL7b | coverable-now — left out — **no route** until Vu adds |
| OL10a | **no freezable rule** / pin-fragile (CS gate cannot detect stale) |
| OL10b | **not built** (provisional wire) |
| OL1 | **no route to pass by correct behavior** (Part 3 capability gap) |
| OL2a | **no route to pass by correct behavior** |
| OL3 | **no route to pass by correct behavior** |

Rows that may **differ** from a Claude draft that still listed MM1/MM2 as not-covered or H19/H20 as covered: **MM1/MM2 are covered now**; **H19/H20 are not_covered**. Flag for Vu if the draft is stale on those.

## d. Final audit-form numbers

Generator method (same as `LAST_B1_REFRESH` turn×points table): hand-audit + dual rows; acceptance `;`-split; H11 +1 errata point; MM1 added (1×3). MM2 mechanical-only → not on the form.

| metric | count |
|---|---|
| hand-audit rows (incl dual) | **59** |
| form sections | **71** |
| rubric cells | **232** |
