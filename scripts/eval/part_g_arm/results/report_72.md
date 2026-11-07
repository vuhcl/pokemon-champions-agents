# Follow-up 72 — key cut for the revised arm (versioned keys, no rerun)

Source of truth: `key_cut_worksheet_2026-11-07.md` (copied under `state/keys_fu72/`). Chat §3 applied where it agreed; **worksheet wins** on disagreement (see `disagreements_fu72.md`).

## Deliverables

| Artifact | Path |
|---|---|
| Structured hand keys | `state/keys_fu72/hand_keys_fu72.json` |
| Tools/request CSV rev4 | `state/keys_fu72/expected_tools_rev4_2026-11-07.csv` |
| Point diff | `state/keys_fu72/point_diff_fu72.md` |
| Ambiguous splits | `state/keys_fu72/ambiguous_splits_fu72.md` |
| IS offline minima | `state/keys_fu72/is_minima_fu72.json` |
| Usage rebuild (H6/HU2/GS1/HN3/MT2) | `state/keys_fu72/usage_rebuild_fu72.json` |
| Legality | `state/keys_fu72/legality_report_fu72.md` |
| Unreachable rows | `state/keys_fu72/unreachable_fu72.md` |
| Request-text overrides | `state/keys_fu72/request_text_overrides_fu72.json` |
| Seeds (versioned) | `state/keys_fu72/seeds/` |
| Manifest + key hash | `state/keys_fu72/KEYS_MANIFEST_FU72.json` |
| Builder | `state/keys_fu72/build_fu72_artifacts.py` |

**key_hash:** `da150c89ad50d2904a0bcf5ac5624d8fb04f1012246934e6d41ea4707a9e0666` (see `KEYS_MANIFEST_FU72.json`).

## Old hashes (unchanged — frozen a393ae91 / Part G artifacts not edited)

Recorded in the manifest `old_hashes_unchanged` for:

- `expected_tools_rev3_2026-11-02.csv`
- `part3_request_set_v4.md`
- `derived_keys.json`
- `FROZEN_MANIFEST_ARM_V2.json`
- `claim_battery_v4.json`

## Config assumed by the revised keys

`sticky_locks=on`, `unlock_keeps_values=on`, `tool_fixes_v2=on` (#387).

## What changed per row (summary)

- **IS1–IS4**: Removed hidden 4-part min-SP. Assumption / tool-backed Spe / budget outcome / never “not recommended”. Minimum points **conditional** on claiming a minimum. Numbers from offline `get_speed`-equivalent Spe scan (`is_minima_fu72.json`), not `solve_spread`.
- **Refusal MR1/MR2/MR3/MR4/MR8/HP3**: Rule B (lookup or write+cited validator refusal).
- **MR4**: Seed with item unlocked; first Scarf applies; Item Clause blocks second; no other field touched.
- **MR5 / MR2 / MR3 / MW3**: Registered request texts in overrides + rev4 CSV (manifest revision; frozen runner untouched).
- **MS2**: Values kept, locks cleared (`unlock_keeps_values`).
- **RB1**: `field_locked` under sticky; boost consequence only if write allowed.
- **TB2**: Request/fixture use **Darkest Lariat** (Knock Off not learnable); moveset unlocked in seed (MR4 parallel).
- **MM1**: `no_lookup_needed` / validator refusal alt to `describe`.
- **H8, Q9**: `describe` required; no `no_lookup_needed` alt.
- **MM2, MR3, MR7, MR8, MU1, MU4, MU8**: Optional tool listed as `alternative_path` where applicable; **MU1/MU2 key text unchanged**.
- **Q10 / MV3**: `read_team` alt on Q10; MV3 accuracy caveat 90%.
- **MS5**: “Flagged” = `conflicts` field.
- **MT2 t1, MT3 t1, HC2 t1, MT1 t1/t2, MT5 t1/t2**: Write points so overall cannot be `not_applicable`.
- **MT3**: Five-point rewrite (constraint; Fire suggestion; t3 answers with ability lookup; Intimidate → flag + tool-backed alt; ask-not-suggest fails).
- **HC1 / MT6 t1**: Reworded request; either record both constraints or nothing if empty pool recognised (`find_species` Water∧Fire → 0).
- **H6 / HU2 / GS1 / HN3**: Rebuilt from re-pinned ingame blob. H6 top-5 partners lose Gholdengo, gain Kingambit. HU2 outspeeds `{Incineroar, Kingambit}` (Golisopod not in top-10). GS1 modal = top joint. MT2 t2 three-name set matched. HN3 percents unchanged.
- **OL4 / OL6 / OL9 / MW3**: Named ambiguities; OL4 draft-confirm ok / lock not; OL9 multi-select or ask.
- **MU6**: Expected `reset_team` explanation in points (no call).
- **MR6**: No-op or refusal accepted.
- **IX1 / IX5 / IX7**: Unreachable until #367/#368; keys not frozen as gradable.

## Legality

`check_learnset` / `is_species_legal` / `is_item_legal` over every named species/move/item: **no freeze blockers**. `Choice Specs` is illegal as a held item in Champions and is named only by refusal keys (expected). Incineroar learns Darkest Lariat; does **not** learn Knock Off.

## Unreachable (not graded as arm misses)

See `unreachable_fu72.md` — featured-builds / lock_fields / meta-threats Showdown set / #367/#368 rows.

## Ambiguous splits

11 flagged in `ambiguous_splits_fu72.md` (mostly shared multi-turn acceptance or terse CSV notes on the 15 bad-split turns). Rewritten section-A rows use explicit point lists instead.

## Could not do / repo disagreement

1. **Did not wire** the new keys into the frozen runner or `FROZEN_MANIFEST_ARM_V2` — by design (manifest revision only). Loading `keys_fu72` at score time is a later follow-up.
2. **Did not run or grade** the arm.
3. **TB2 sticky reading**: see disagreements file (unlock-moveset path taken).
4. **IS Spe numbers** use `final_spe_after_mods` (Champions Spe formula matching the calc `get_speed` path), scanned 0–32 SP offline — not live calc HTTP, not `solve_spread`.
5. **Prompt-cut delta for FU69** (section 9 of the brief): keep (a)(b)(c); drop read-back / per-kind / set_slot moves items — recorded below for the prompt cut, not implemented here.

### FU69 prompt-cut delta (report only)

Keep: (a) arm does not name tools to the user; (b) guard refusal wording does not name tools or classes; (c) arm states assumptions behind speed and damage numbers. Dropped: “state only read-back state”; per-kind names; set_slot moves replacement (#391). Label DEV-tuned; parser v2 agreement on 32 turns is a dev number.

## Tests

- `uv run pytest`: **4837 passed, 15 skipped**
- `run_all_checks.py`: all PASS; keys sha `bba5787ce95f9e0b615ce679d8622ca6b1d7709e2cc8e73dc493cda7b88354b2` unchanged; claim battery `e7492a6811f057f1e84ccac821c1249eb29a3fad1f25eec6f9a0e613b776f4b0` and false_legal `3025138427391e57a92e1862a87b0074d44a51b290836077abf094af92c4bdec` unchanged
- Regenerated `LAST_CHECK.json` restored; no frozen artifact committed
