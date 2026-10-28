# 4a — edit_slot_field

## Spec (as built)

`edit_slot_field(slot, field, value)` — slot 1-based; field ∈ item|ability|nature|spread|moveset.
Incomplete slots → `apply_lock`. Fully locked → validate (same validators) then write **only** that Attr; `reconcile_on_sibling_change` is probed for flags/superseded **reporting** but sibling clears are **not** applied (no silent move/item wipe — GS1).
Refusal → state unchanged, pending kept. Result includes `consequences` from `edit_consequences.py`.

## Consequences (data)

| kind | source |
|---|---|
| type_boost_inactive / active | TYPE_BOOST_ITEMS + snap move type/category |
| choice_lock_status | `_CHOICE_ITEMS` / `_ITEM_SWAP_MOVES` (same as reconcile) |
| status_self_boost_overlap | `data/moves/stat_boosts.v1.json` |

## Reconcile probe

On Choice Scarf over a set with Protect/Nasty Plot, reconcile would supersede/clear moveset (`choice item incompatible with non-damaging move`). Tool reports those superseded entries but **keeps** the moveset on the draft.

## Tests

`test_edit_slot_field.py` — 5 passed.

## Dev rows (keys first; species not in request-set text)

| id | turns | key |
|---|---|---|
| dev-edit-item-ok | Lock Venusaur s1; set item Sitrus Berry | MUTATION-OK; item=Sitrus Berry |
| dev-edit-item-refuse | Lock Venusaur; set item Choice Specs | MUTATION-REFUSED; draft unchanged |
| dev-edit-choice-consequence | Fully locked Venusaur with Protect+status; item→Choice Scarf | MUTATION-OK; consequences.choice_lock_status lists Protect; moves unchanged |

Prompt description draft (for Part 5): same as tool spec description above.

## Reference trajectories updated

MR2 / MR4 now reachable via edit_slot_field (re-run Part 3 after commit).
