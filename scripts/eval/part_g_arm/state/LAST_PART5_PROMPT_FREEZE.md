# Part 5 — single prompt revision + freeze proposal

## Prompt

File: `state/prompt.md`  
**Chosen frozen sha256:** `08a0917a3eb30977752858b1a86f84f0c6ad8f2cd02217d98d6c9865f872b86b`

| candidate | sha256 | eev |
|---|---|---|
| prior (A5) | `b71764852eb66f87f17375ff3226a7e4be7517b09eb8961fb56e779fe32badd8` | would pass old rows; **no** Part 4 tool text |
| first draft | `c58e3ce8499d3c579899bed84ec7a450f55e0e9da83dedb7bca6582c3cd4dd18` | 35/37 class-ok; **MT7/MT8** failed silent-apply (`edit_slot_field` / `add_constraint`) |
| **chosen** | `08a0917a…` | **37/37** after one tune: solve_spread-only asks must not call edit/lock/constraint/archetype unless the user asks to change the team |

Why chosen: only prompt that both describes the new tools and keeps MT7/MT8 from writing `team_draft`. Last revision.

Transcript (outside repo): `/Users/nowaki027/part-g-arm-state-out-part5b/`  
Model: `qwen3.5:latest` digest `44a38603922e…`

## Per-row eev (chosen prompt)

All 37 PASS. New rows: edit×3, constraints×3, show_candidates×4, learnset×2, archetype×1, priority×1.

## Findings (not tuned further)

- MT7 t3 / MT8 t3 still call `add_constraint` on later turns (hand_grade allows it: no `team_draft` write). Recorded; not a class fail.
- MT8 Timid-before-way-out hand field: not re-audited in this pass (same standing finding as A5).

## Covered list (readiness; not frozen)

- **+** MS5, SC2, GS1, TB2, RB1, IX1  
- **−** OL1, OL2a, OL3 (Part 3 capability gaps → not-covered at freeze)  
- **stay not-covered:** MM1/MM2 until mega PR #318 merges into arm; SC1 (draft-condition store not built); H17/H18/H25/H26 (producer needs bootstrap / all_locked fixtures)

Counts: covered **100**, not_covered **34**. Hand-unreachable facts: H11, H19, H20, HU1 (4).

## Part 3 re-run

mechanical pass **39/39**, capability gaps **0** (OL gaps removed from covered).  

## Manifest

`STATE_MANIFEST_PROPOSAL.json` updated with chosen prompt sha and file hashes.  
**FROZEN_MANIFEST.json not written** — freeze after Vu approval.

## Registration facts (candidate discovery)

Unchanged from 4c: option identity/order/source/evidence tool-determined; pins usage+legality (+calc when up); no LLM in producer.
