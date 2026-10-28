# Not-covered reasons (final tool set, 2026-10-28)

Registration copy. Covered **103** / not_covered **31**. H22 keep-out (Vu default). One line per row.

| id | reason |
|---|---|
| H12 | Claim surface 19 rubric cells; trajectory `no_lookup_needed` is vacuous for the class scorer (cannot check Calm/Bold content). Also needs empty_team seed for loader. |
| H17 | Bootstrap empty: `show_candidates` needs an `all_locked` anchor including role; `edit_slot_field` cannot set role. |
| H18 | Bootstrap empty / HO checklist needs progressing 32-SP slots; `show_candidates` blocked without `all_locked`. |
| H19 | Bootstrap empty (same as H17/H18): checklist item 1 needs TR-setter candidates or locks; nonempty `find_species(Trick Room)` pool is not a pass (`LAST_H19_H20_NOT_COVERED`). |
| H20 | Bootstrap empty (same as H17/H18): checklist item 1 needs presented/locked Electric slots; nonempty `find_species(Electric)` pool is not a pass. |
| H21 | No frozen checklist; trajectory `no_lookup_needed` vacuous for class scorer. |
| H22 | Vu keep-out (default): assumption-labeled aesthetic; trajectory `no_lookup_needed` vacuous (frozen 4-item checklist exists but not chosen for cover). |
| H25 | Fixture locks species/ability/item only → not `all_locked` → `show_candidates` refuses. |
| H26 | Same as H25 (Torkoal fixture). |
| MT4 | `show_candidates` exists; CS seed has 0 `all_locked` anchors (not a missing tool). |
| MT7 | Permanent DEV (multi-turn Archaludon compound). |
| MT8 | Permanent DEV (MT7 continuation). |
| AR1 | Keep out — near-dup of MT7 t1. |
| AR2 | Keep out — near-dup of MT7 Pareto-t2. |
| AR3 | 6-turn Mega-X Belly Drum compound not built. |
| SC1 | `sc1_start.json` not in `_SLOT_BASE`; draft-condition store unwired (`check_learnset` ok for Snarl). |
| SC3 | `sc3_two_slots.json` not in `_SLOT_BASE`; slot-2-only condition unwired. |
| TS1 | `ts1_sequence.json` unwired; no draft-retain across topic switch. |
| GT1 | No VGCPastes / usage-moves surface for Trick+Scarf (n=2). |
| LZ1 | No common_moves / usage-moves tool for Top4 Protect+Detect drop. |
| IX2 | No Showdown interaction tool (Pain Split / Magic Guard). |
| IX3 | `flags.v1` slicing not exposed by `get_move_static` (priority enrichment only). |
| IX4 | Good as Gold / Mold Breaker / Wandering Spirit→Contrary multi-step interaction not in any arm tool. |
| IX6 | No Unburden×White Herb interaction tool. |
| DM5 | `dm5_working_draft.json` not in `_SLOT_BASE`. |
| OL7b | Frozen FBC fixture omits `provisional_slot` → `select_option` refuses. |
| OL10a | CS staleness undetectable (no presentation fingerprint). |
| OL10b | FBC provisional null; select refuses; fingerprint path incomplete. |
| OL1 | FBC no `provisional_slot`; select cannot bind. |
| OL2a | FBC no `provisional_slot`; select refuses bare `2`. |
| OL3 | Label bind + FBC no `provisional_slot`. |
