# H25 / H26 / MT4 status (2026-10-27)

Evidence: `LAST_PART4C_SHOW_CANDIDATES.md`, `reference_trajectories.py`, `covered_list.json`.

| row | was covered | pass by correct behavior? | blocker |
|---|---|---|---|
| **MT4** | yes | **No** (full t1–t3) | t1 `reject_option` ok; t2 `show_candidates` needs an all_locked anchor; CS seed has none. Producer+reject filter proven only on fully locked Venusaur. |
| **H25** | no | **No** | Fixture locks species/ability/item only → not `all_locked` → `show_candidates` refuses. Fix would be fixture/product outside `state/`. |
| **H26** | no | **No** | Same as H25 (Torkoal fixture). |
| H17 / H18 | no | **No** | Empty team; bootstrap out of scope. |

## Covered-list action

**MT4 → not_covered** (readiness: no passing full reference trajectory). H25/H26 stay not_covered. No fixture fields invented.
