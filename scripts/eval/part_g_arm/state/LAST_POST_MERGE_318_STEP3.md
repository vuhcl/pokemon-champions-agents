# Post-merge #318 step 3 — Mega behavior-change sweep

Baseline “before”: product at `88ec1e0` had **no** `mega_stone` rule. Mechanical traj file at that commit vs now: **39/39 still pass**; no overlapping mega-text covered row had a mechanical trajectory then or now (hand-audit / dual).

## Covered rows with Mega text

DM6, H11, HN2d, HU1, HU2b, IS4, MC1, MS5, RB1 — all hand/dual; mechanical class traj **n/a**.

## Probe table (tool result / signature)

| call | before (88ec1e0) | after (#318) |
|---|---|---|
| `check_hypothetical([{species:Salamence-Mega}])` | ok | **changed** → `mega_stone` (names Salamencite) |
| `check_hypothetical([{species:Salamence-Mega, item:Salamencite}])` | ok | **unchanged** ok (arm `check_hypothetical` now sibling-stages like `apply_lock` batch) |
| `check_hypothetical([{species:Salamence-Mega, item:Leftovers}])` | ok | **changed** → `mega_stone` |
| `check_hypothetical([{species:Charizard-Mega-X}])` | ok | **changed** → `mega_stone` (Charizardite X) |
| `select_option` on Venusaur-Mega candidate (empty item) | would lock | **changed** → refuse mega_stone; writes nothing |
| `select_option` after Venusaurite staged | — | ok path (stone held) |
| restore superseded Mega after unlock | nothing to restore | **unchanged** (this unlock path does not push superseded) |

## Arm fix in this step

`check_hypothetical` staged species before item, so a joint Mega+stone placement falsely refused. Aligned with product batch lock sibling staging. Test: `test_check_hypothetical_mega.py` (3).

## Step 5 gate

Prompt only says use the returned `verdict` / `slot_commit_error` — it does **not** describe mega_stone outcomes. **No prompt edit. Skip gate-model eev.**
