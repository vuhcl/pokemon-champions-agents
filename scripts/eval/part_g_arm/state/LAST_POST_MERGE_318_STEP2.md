# Post-merge #318 step 2 — mega-stone spot-checks (no model)

Scripted through arm `edit_slot_field` / `lock_slot` and product `apply_lock`. Full JSON: `LAST_POST_MERGE_318_STEP2.json`.

| id | call | result | signature |
|---|---|---|---|
| a_edit_slot_field_leftovers | MM2: fully locked Salamence-Mega+Salamencite → `edit_slot_field(1,item,Leftovers)` | refused; message names **Salamencite**; slot unchanged | draft_sig unchanged |
| a_apply_lock_leftovers | same pair incomplete → `apply_lock(item=Leftovers)` | refused; names Salamencite; unchanged | draft_sig unchanged |
| b_batch_ok | `apply_lock` batch Charizard-Mega-X + Charizardite X | succeeds; slot holds both | species+item locked |
| b_batch_refuse | batch Charizard-Mega-X + Leftovers | refused; names Charizardite X; **writes nothing** | empty draft |
| c_bare_mega | `lock_slot(1,Salamence-Mega)` empty | refused; names Salamencite; writes nothing | empty |
| c_item_then_species | item Salamencite then `lock_slot` Salamence-Mega | succeeds | Mega+stone |
| c_base_leftovers | `lock_slot` Salamence then item Leftovers | accepted | base+Leftovers |
