# Follow-up 70 — tool_fixes_v2 (+ harness tests)

Draft PR branch `fu70-tool-fixes-v2`. One new flag `tool_fixes_v2` (default off). Flag off reproduces a393ae91 tool outputs. No frozen ladder artifacts edited. No key cut / prompt cut / re-pin / #367 / #368 / #310.

## Flag

- `scripts/eval/part_g_arm/state/tools.py`: `set_tool_fixes_v2` / `tool_fixes_v2_enabled`
- Wired through `request_set_runner.py` (`--tool-fixes-v2`) and `process_metric_scorer.py`
- Also toggles `recommender.slot_fill.set_keep_join_ts_unlisted_formes` for #364

---

## Item 1 — #369 check_set on partial / draft moveset

**Files:** `tools.py` (`edit_slot_field`), `set_slot_tool.py` (moves validation), `test_tool_fixes_v2.py`

**Repro call:** TB2 partly locked Incineroar; `edit_slot_field(1, "moveset", ["Flare Blitz","Knock Off","U-turn","Protect"])`

| | output |
|---|---|
| **old (flag off)** | `ok: true`; moveset written |
| **new (flag on)** | refuse `illegal moveset: learnset:Knock Off; learnset:U-turn`; state unchanged |

Draft `set_slot` with the same moveset: same learnset message under flag on.

**Not done:** ADR for draft-mode validation policy (issue acceptance 3); TB2 key revisit.

---

## Item 2 — #384 Mega + stone co-submit

**Files:** `set_slot_tool.py` (validate + apply staging), tests

**Repro:** `set_slot(slot=1, species="Salamence-Mega", item="Salamencite")`

| | output |
|---|---|
| **old** | `ok: false`; species cause mega_stone (item element may still be ok) |
| **new** | `ok: true`; species Salamence-Mega, item Salamencite |

Mega alone / Mega+Leftovers: still mega_stone refusal.

**Report (open question — no resolve-to-base):** today Mega id with **no item** → refuse mega_stone (`A Mega forme must hold Salamencite…`). Stopped there; did not add base+stone rewrite.

---

## Item 3 — #372 / #282 write tools return state read-back

**Tools changed** (new fields only when `tool_fixes_v2` on):

| tool | new fields |
|---|---|
| `edit_slot_field` | `value` (written attr from state), `slot_after` (all seven attrs) |
| `lock_slot` | `ok`, `value` (species), `slot_after` |
| `unlock_slot` | `ok`, `slot_after` |
| `lock_fields` | `value` (locked attrs), `slot_after` |
| `unlock_fields` | `value` (unlocked attrs), `slot_after` |
| `clear_slot` / `unlock_slot_draft` | `value: null`, `slot_after` |
| `commit_slot` | `ok`, `team_after` (occupied slots) |
| `set_slot` | already had `applied` read-back (unchanged) |

**Repro:** edit legal moveset under flag on → `value ==` moveset list from state.

---

## Item 4 — #364 Meowstic-F / join.ts six

**Files:** `recommender/slot_fill.py` (`JOIN_TS_UNLISTED_OTHER_FORMES`, gate), `tools.py` (flag sync), tests

**Six formes (join.ts unlisted otherFormes):** `meowsticf`, `mausholdfour`, `polteageistantique`, `sinistchamasterpiece`, `vivillonfancy`, `vivillonpokeball`

Predicate matrix (active regulation): flag off → all six `True` (battle-only heuristic); flag on → all six `False`. Castform-Sunny stays `True` under flag on.

**Repro:** `find_species(ability="Competitive")`

| | |
|---|---|
| **old** | Meowstic-F absent |
| **new** | Meowstic-F present |

**Not done:** ADR for predicate vs map-builder fix (issue acceptance 4).

---

## Item 5 — #370 archetype case-insensitive

**Files:** `tools.py` `change_archetype` / `_canonicalize_archetype_component`

**Repro:** `change_archetype(["rain","offense"])` vs `["Rain","Offense"]` on Pelipper → same `pending_flags` and `conflicts` when flag on.

**Other string-keyed component tables (grep):** `_WEATHER_COMMITMENTS`, `_COMPONENT_ROLE_FIT` (`TrickRoom`, `Tailwind`), `_POKEMON_TYPES`, `COMPOSITE_ARCHETYPE_LABELS` (`TailRoom`). All title-cased keys; weather was the live bug. Canonicalizer covers weather / types / role-fit; other labels get `Title` case.

---

## Item 6 — #371 pending_flags richer entries

**Files:** `tools.py` `_enrich_pending_flag_dict` (used from `change_archetype` + `edit_slot_field` reconcile list)

**New fields per flag:** `attribute`, `compared`, `result`, `advisory_or_blocking`

**`flag_kind` values `_apply_mismatch` can emit:**
`flag_exempt_conflict`, `judgment_mismatch`, `sibling_mismatch`, `severity_mismatch`, `theme_mismatch`

---

## Item 7 — calc_damage wrapper (not calc service)

**Files:** `harness.py` only

**(a) ability required** (implemented; **Vu not yet confirmed — strike if unwanted**): missing `attacker.ability` / `defender.ability` → `error_kind=bad_arguments`, `field` names the path.

**(b) Sturdy / Disguise:** result gets `calc_limitation` explaining calc does not model them.

---

## Item 8 — hypothetical answers (revision candidate g)

**Files:** `tools.py` `check_hypothetical` / `_hypothetical_verdict`

### Current a393ae91 rung-6 outputs (before fix)

**MU1** args `placements=[{Garchomp, Choice Scarf},{Jolteon, Choice Scarf}]` (idle empty team):

```json
{"verdict":"item_clause","conflicts_with_slot":1,
 "message":"Item Clause: Choice Scarf is already held in slot 1. Each item can be used only once."}
```

**MU2** args `placements=[{slot:2, species:"Water type"}]`:

```json
{"verdict":"unknown_species","conflicts_with_slot":null,
 "message":"I don't recognize 'Water type' as a Pokémon, so I can't lock it."}
```

### New (flag on)

Same verdicts; message prefixed `Hypothetical only (does not change the team): …`; lock wording removed; `hypothetical: true`, `applies_to_team: false`. MU1/MU2 **keys unchanged**.

---

## Item 9 — harness tests (#322 / #323) — no tool change

**Files:**
- `test_harness_start_state_fu70.py` — (a) lock-count match, (c) SC2/TB2 load + all covered loaded
- `freeze_manifest_arm_state.py` — `covered_loader_failures()` hooked into `verify`
- `results/fu70_key_silent_322.md` — (b) KEY SILENT list

| sub | added | #322 / #323 acceptance status |
|---|---|---|
| **(a)** | `test_322_lock_count_state_cells_match_loaded_start` | **#322 acceptance 4 done.** Acc 1–2 (fixture-before-token / lock-count fail-closed in resolver) already largely satisfied by current `EXPLICIT_START_SEEDS` + fixture-first paths; **not re-litigated here**. If a lock-count cell ever maps to empty again, (a) fails. |
| **(b)** | 89-row KEY SILENT one-liners in `fu70_key_silent_322.md` | **#322 acceptance 3 done** (listing produced). |
| **(c)** | freeze `verify` calls `covered_loader_failures`; tests SC2+TB2 load + all covered `loaded=True` | **#323 acceptance 2–3 done.** **#323 acceptance 1:** SC2/TB2 already load today (`Archaludon` fully locked / TB2 fixture); remains “documented load” rather than a new loader invent — **no remaining loader gap observed**. |

**Remaining after this PR (if issues stay open for paperwork):** none observed for #323; #322 ADR/docs polish only if owner wants acc 1–2 called out in an ADR.

---

## Item 10 — report only (was item 9)

### #385 sticky locks when user names a locked field

With `sticky_locks` on + draft: `set_slot` **still refuses** writes to locked attrs (`error_kind=field_locked`, `lock_unchanged`). Arm must call gated `unlock_fields` first. Guard: `unlock_fields` / `unlock_slot` only enter the allowed set when `user_requests_unlock` (explicit unlock language); unprompted unlock is blocked. `clear_slot` needs replace confirmation separately under unlock_keeps_values.

### `solve_spread` guarantees

From `spread_solve.solve_spread`: monotone constraints only; **66 SP total** (max 32/stat); natures searched; objective minimizes L1 to a 66-SP Showdown joint reference (weight tie-break). Status: optimal | feasible | infeasible | unknown | invalid_arguments. Outspeed constraints drive Spe; Scarf/Tailwind appear as constraint-side notes when encoded in constraints — not a silent always-on stack. Mega targets via species id + ability resolve. **Does not guarantee** Scarf+Tailwind stack unless those constraints are supplied.

### Featured builds for seeds

`get_featured_builds` **does not exist** at any rung (`new_tool_needed` in process metrics). Offline source: usage blob `featured_sets` / `featured_or_common_set` (ingame CBD then Showdown merge) in `recommender/usage_data.py`. Modal sets for seeds come from that usage path / fixtures — not a live featured API.

---

## Tests run

- Targeted arm: `test_tool_fixes_v2.py` + `test_harness_start_state_fu70.py` — **21 passed** (not on default `testpaths`; run by path)
- `run_all_checks.py` — **12/12 PASS**; keys_sha=`bba5787c…`; claim=`e7492a68…`; false_legal=`30251384…` (unchanged)
- `uv run pytest` — **4800 passed, 15 skipped**

Hashes (unbroken): claim=`e7492a6811f057f1e84ccac821c1249eb29a3fad1f25eec6f9a0e613b776f4b0` false_legal=`3025138427391e57a92e1862a87b0074d44a51b290836077abf094af92c4bdec` keys_sha=`bba5787ce95f9e0b615ce679d8622ca6b1d7709e2cc8e73dc493cda7b88354b2`

## Not done (out of scope)

- #367 / #368, #310 calc-service, key cut, prompt cut, ladder run, re-pin
- Resolving Mega id → base+stone (#384 open)
- Striking calc_damage 7a if Vu declines
- ADR drafts for #369 / #364 (chat-only if requested)
