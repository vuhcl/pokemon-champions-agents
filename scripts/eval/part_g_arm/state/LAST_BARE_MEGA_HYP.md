# Round 3 item 2 — bare Mega `check_hypothetical` / `select_option`

Before #318: no `mega_stone` rule → bare Mega species hyp ≈ `ok`.  
After: bare Mega → `verdict=mega_stone` (stone named; keep stone or base+item).

## Inventory

| source | row | turn | tool | Mega without item? | old verdict | new verdict | key / expected class | class change? |
|---|---|---|---|---|---|---|---|---|
| covered ref traj | — | — | — | **none** | — | — | — | — |
| covered request-set prompt | — | — | — | **none** ask bare Mega via hyp | — | — | — | — |
| seeds | — | — | — | **none** | — | — | — | — |
| ref traj | MU1–MU8 etc. | — | check_hypothetical | placements are non-Mega | n/a | n/a | — | — |
| **dev** | `dev-hyp-species-clause` | 1 | check_hypothetical (prompted) | joint `Venusaur` + `Venusaur-Mega` | `species_clause` | `species_clause` (same; Mega still clashes after base) | wiring / Species Clause | **no** |
| probe (not a row) | — | — | check_hypothetical([{Salamence-Mega}]) | yes | `ok` | `mega_stone` | n/a | lookup only both ways |
| probe | — | — | select_option Venusaur-Mega bare | yes | would lock | `mega_stone` refuse | n/a | refused vs wrote — **not a covered traj** |

No covered turn’s mechanical class changes. No seed/ref traj sends a bare Mega to hyp/select.

## What the user hears

`check_hypothetical([{species: "Salamence-Mega"}])` →

> A Mega forme must hold Salamencite. Keep Salamencite, or use the base form (Salamence) with that item (form change is an offer only).

Not a flat refusal: it states the Mega is allowed **with its stone**, and offers base+other item. **No wording change proposed** (existing validator message already names the keep-stone path).

## Proposed wording (do not apply)

N/A — message already states keep-stone allowance. If Vu wants softer lead-in later: prefix “Not with that item loadout: …” only via the same `_mega_stone_message` helper (product), not arm-side.
