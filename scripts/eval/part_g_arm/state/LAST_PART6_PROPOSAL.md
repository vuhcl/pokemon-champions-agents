# Part 6 — covered list + state manifest proposal (NOT frozen)

Regenerated 2026-10-27 after find_species, repeat-run design, hand-audit form, and freeze checklist. Freeze target **2026-10-29 / 2026-10-30**. Covered three-run **2026-11-02**.

## Final covered list (proposed)

| bucket | count | notes |
|---|---|---|
| scorable-mechanical (B1∩covered) | 39 | +3 proposed if B1 refreshed for MS5/RB1/TB2 → 42 |
| hand audit (B1∩covered) | 54 | +3 proposed if B1 refreshed for GS1/IX1/SC2 → 57 |
| B1∩covered | 93 | |
| covered but absent from B1 | 6 | GS1, IX1, MS5, RB1, SC2, TB2 — see `LAST_FREEZE_CHECKLIST.md` §c |
| **covered total** | **99** | `covered_list.json` |
| not covered | 35 | includes MT4, H25/H26, H17/H18, OL1/OL2a/OL3, MM1/MM2, SC1/SC3, … |

H11 / H19 (learnset) / H20 / HU1 are tool-reachable via `find_species`. H11 acceptance vs tool set drift (`Castform-Rainy`) reported in freeze checklist. H19 compendium-role TR setters may still need hand/checklist when not learnset-equivalent.

Stale-pin rows MT2/H6 stay covered but scored as stale, not failed.

## Still out (readiness)

| rows | reason |
|---|---|
| MT4 | CS seed has no all_locked anchor for `show_candidates` t2 |
| H25 / H26 | fixtures not all_locked (outside `state/`) |
| H17 / H18 | empty; bootstrap out of scope |
| MM1 / MM2 | mega-stone PR #318 not merged |
| SC1 / SC3 | draft-condition store not built |
| OL1 / OL2a / OL3 | FBC provisional wire gap |

## Manifest proposal

See `STATE_MANIFEST_PROPOSAL.json` (`frozen: false`). Proposed prompt: `bd2b69cd…` (40/41 eev; Prankster-weather set fail as finding). Prankster key (independent): `6dba1caa…`. Freeze after Vu approval; Claude reviews seeds against row text first.
