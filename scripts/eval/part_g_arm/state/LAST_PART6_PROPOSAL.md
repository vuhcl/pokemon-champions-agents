# Part 6 — covered list + state manifest proposal (NOT frozen)

Regenerated 2026-10-27 after Part 4/5 tools and MT4 drop. Supersedes the stale “96 / MT4 missing show_candidates” draft.

## Final covered list (proposed)

| bucket | count | notes |
|---|---|---|
| scorable-mechanical | 39 | Part 3 trajectories pass 39/39 after OL1/OL2a/OL3 and MT4 removed |
| hand audit (B1 on covered) | 54 | gemma second-rater only; Vu audits |
| **covered total** | **99** | `covered_list.json` |
| not covered | 35 | includes MT4, H25/H26, H17/H18, OL1/OL2a/OL3, MM1/MM2, SC1/SC3, … |

H11 / H19 (learnset) / H20 / HU1 are tool-reachable via `find_species` (hand-map GAPs cleared). H19 compendium-role TR setters may still need hand/checklist when not learnset-equivalent.

Stale-pin rows MT2/H6 stay covered but scored as stale, not failed.

## Still out (readiness)

| rows | reason |
|---|---|
| MT4 | CS seed has no all_locked anchor for `show_candidates` t2 — see `LAST_H25_H26_MT4_STATUS.md` |
| H25 / H26 | fixtures not all_locked (outside `state/`) |
| H17 / H18 | empty; bootstrap out of scope |
| MM1 / MM2 | mega-stone PR #318 not merged into arm |
| SC1 / SC3 | draft-condition store not built |
| OL1 / OL2a / OL3 | FBC provisional wire gap |

## Solver / state tests

`pyproject.toml` `testpaths` still omit `scripts/eval/part_g_arm/state/test_*.py` — path-invoked only (unchanged).

## Manifest proposal

See `STATE_MANIFEST_PROPOSAL.json` (`frozen: false`). Proposed prompt after find_species: `bd2b69cd…` (40/41 eev; Prankster-weather set fail as finding). Prior Part 5: `08a0917a…`. Freeze after Vu approval; Claude reviews seeds against row text first.
