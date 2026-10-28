# Post-merge #318 step 4 — MM1 / MM2 reference trajectories

Scripted from row text + `derived_keys.row_g_h_salamence_mega`. Loader/class scorer only. **Not** added to `covered_list.json`.

| row | key class | trajectory | observed | pass |
|---|---|---|---|---|
| MM1 | SERVED | `check_hypothetical([{Salamence-Mega, Leftovers}])` | lookup only; verdict `mega_stone` (names Salamencite; offers base+Leftovers) | **pass** |
| MM2 | MUTATION-REFUSED | fixture Mega+Salamencite fully locked → `edit_slot_field(item, Leftovers)` | refused; draft unchanged | **pass** |

Offer controls (MM1, not class-scored): Mega+Salamencite → ok; base Salamence+Leftovers → ok.

## Readiness if added (not applied)

| | |
|---|---|
| both pass | yes |
| covered now | 97 |
| with MM1+MM2 | **99** |
| leave not_covered | drop MM1/MM2 from not_covered list |
| proposed buckets | MM1 → hand audit (stated correction); MM2 → mechanical class + hand-audited “form change offer” statement (same dual rule as TB2) |

Do not add silently — Vu decides at freeze.
