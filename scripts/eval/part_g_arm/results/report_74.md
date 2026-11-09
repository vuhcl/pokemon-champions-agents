# Report 74 — revised arm wiring + IX key cut (DEV)

Branch stack: PR A `#394` (`fu74-ix-key-cut`) → PR B (`fu74-revised-arm`). No arm run, no grading. Vu runs parser-eval locally.

## Discovery findings (carried)

See chat Discovery. Summary: keys_fu72/fu74 were unwired; `set_ix_tools_v1` had no runner flag; process-metric `flags_from_run_record` omitted `ix_tools_v1`; request overrides and fu72 seeds unused; refusal message named tool+class.

## Plan as built

| Item | Done |
|---|---|
| 2 IX key cut (`keys_fu74/`) | PR A (+ review fixes) |
| 3 `--keys fu74` | scorer CSV rev5, hand-audit points replace errata, overrides + seeds, pin_hashes |
| 4 `--ix-tools-v1`, `--revised-arm` | wired; profile forces guard rung 6 |
| 5 `--prompt-cut` | `prompt_guard_cut.md` + refusal rewrite; FU69 literal drops = no-ops |
| 6 `--parser-v2` | tried (round 2: no net gain on 116); stays opt-in; profile does not enable it |
| 7 tests + this report | isolation + wiring + parser/prompt-cut tests |

## Flag table

| Flag | Default | Notes |
|---|---|---|
| `sticky_locks` | off | unchanged |
| `unlock_keeps_values` | off | unchanged |
| `tool_fixes_v2` | off | unchanged |
| `ix_tools_v1` | off | new CLI → `set_ix_tools_v1` |
| `prompt_cut` | off | needs `--guard`; selects `prompt_guard_cut.md` |
| `parser_v2` | off | opt-in only; needs `--guard`; selects `prompt_guard_parser_v2.md`. Tried; **not adopted** (no net gain on 116). |
| `--keys` | `committed` | `fu74` = overrides + seeds + rev5 + hand keys |
| `--revised-arm` | off | guard + sticky + unlock_keeps + tool_fixes_v2 + ix_tools_v1 + keys fu74 + prompt_cut. Does **not** set `parser_v2` (resolved record: `parser_v2: false`). |

## Prompt cut (DEV-tuned)

**FU69 literal hunt:** drops are **no-ops** (literals only in `report_72` prose).

**Accepted cut:** unlock keeps values / `clear_slot` wipes with `replace`; class-naming removed from delta; “Do not name internal tool names”; Spe/damage assumptions kept.

**`clear_slot` under profile:** bound in `combined_specs` when draft + `unlock_keeps_values` (tested). Prompt documents `unlock_slot(slot)` and `clear_slot(slot, replace?)`.

**#389 note:** refusal string’s “or confirmation to clear” may interact with #389 (explicit unlock confirmation). Not tuned for #389 in this follow-up.

### Refusal: what the model actually sees

Harness sends `ToolMessage(dumps(model_facing_tool_result(recorded)))`. Transcript `entry["result"]` keeps the **full** patch for the run log.

**(b) was half-done before this review fix** — `tool` / `class` / `reason` still reached the model in the JSON body. **Now under `--prompt-cut` they are stripped from the model-facing payload** and kept only in the run log.

**Legacy model-facing (flag off), exact:**

```json
{"args":{"slot":2,"species":"Incineroar"},"class":"ASK","guard_blocked":true,"message":"Refused set_slot: not allowed for request class ASK. Do not retry this call; answer from tools already returned or ask.","reason":"tool not in allowed set for class ASK","status":"refused","tool":"set_slot"}
```

**Prompt-cut model-facing, exact:**

```json
{"args":{"slot":2,"species":"Incineroar"},"guard_blocked":true,"message":"That action was refused for this request. Do not retry it. Answer from what the tools already returned, or ask the user for the missing detail (which slot, which species, or confirmation to clear).","status":"refused"}
```

**Prompt-cut run-log (full result, not sent as ToolMessage body), exact:**

```json
{"args":{"slot":2,"species":"Incineroar"},"class":"ASK","guard_blocked":true,"message":"That action was refused for this request. Do not retry it. Answer from what the tools already returned, or ask the user for the missing detail (which slot, which species, or confirmation to clear).","reason":"tool not in allowed set for class ASK","status":"refused","tool":"set_slot"}
```

Note: the AIMessage still names the tool in the tool_call (`name: set_slot`); only the **result** payload is sanitized. Args may still contain species/slot values.

## Parser v2 (DEV) — close-out

**Decision:** revised arm keeps the committed parser (`parser_v2: false` under `--revised-arm`). v2 stays as an optional `--parser-v2` flag (needs `--guard`). Prompt not edited further. Numbers from `parser_eval_fu74.json` (`--keys fu74`, model `qwen3.5:latest`). All **DEV**.

### Headline (all CSV turns, MT2 t3 / MT6 t3 excluded)

| Parser | Agree | n | Rate |
|---|---|---|---|
| v1 (committed) | 83 | 116 | 71.6% |
| v2 | 82 | 116 | 70.7% |

**No net gain on the 116.** Gains 6 / regressions 7.

**State-dependent, not measured (excluded):**
- MT2 t3 — key `READ_STATE` — text `Confirm slot 1.`
- MT6 t3 — key `READ_STATE` — text `Confirm constraints.`

**Gains v1→v2 (all_csv):** H18b t1 (ASK→WRITE), HU3 t1 (WRITE→LOOKUP), MT3 t2 (WRITE→LOOKUP), MT6 t1 (ASK→WRITE), MT6 t2 (ASK→WRITE), SC2 t1 (WRITE→LOOKUP).

**Regressions v1→v2 (all_csv):** GS1 t1 (WRITE→LOOKUP), HD1 t2 (LOOKUP→READ_ONLY_REFUSE), IC1 t1 (WRITE→LOOKUP), MM2 t1 (WRITE→ASK), MR5 t1 (WRITE→ASK), RB1 t1 (WRITE→ASK), TB1 t1 (WRITE→LOOKUP).

### DEV labels (A6 + fu74)

| Split | n | v1 | v2 |
|---|---|---|---|
| with 5 in-prompt example rows | 32 | 27/32 (84.4%) | 30/32 (93.8%) |
| without those 5 | 27 | 23/27 (85.2%) | 25/27 (92.6%) |

Dev gains (no regressions): `a6-refuse-ou-stall`, `fu74-dev-options-electric` (in-prompt), `fu74-dev-refuse-export`. Dev-row gains are partly in-sample.

### Disagree-32

| Text | v1 | v2 | gains | regressions |
|---|---|---|---|---|
| original | 16/32 (50.0%) | 19/32 (59.4%) | H18b t1, MT5 t2, MT6 t1, MT6 t2 | TB1 t1 |
| fu74 played | 19/32 (59.4%) | 20/32 (62.5%) | H18b t1, MT5 t2 | TB1 t1 |

v2 is **dev-tuned and not validated held-out**. Tried; not adopted.

## OL input check (report only; no prompt edit)

Under `--keys fu74`, eval uses the same start builders as the runner. For OL2b / OL5 / OL7a / OL8, fixtures set `pending_presentation.kind = candidate_selection` with options in state, but `compact_state_summary` only exposes `pending_kind` — **not** the option list — and `asked_action` is null (`_guard_pending_asked` unset on these starts).

Parser results (both v1 and v2): OL2b / OL7a / OL8 → ASK; OL5 → PENDING_ANSWER. Key for all four: PENDING_ANSWER.

### Exact human message sent to the parser

Built in `guard_parser.parse_user_turn` as `User message:\n{text}\n\nState summary (JSON):\n{json.dumps(summary, sort_keys=True)}\n`.

**OL2b** (`user_turn_text` = `` `2` ``):

```
User message:
`2`

State summary (JSON):
{"asked_action": null, "constraint_count_active": 0, "constraint_count_total": 0, "pending_fingerprint_matches": true, "pending_kind": "candidate_selection", "slots": [{"attrs": {"ability": "empty", "item": "empty", "moveset": "empty", "nature": "empty", "role": "empty", "species": "empty", "spread": "empty"}, "slot": 1}, {"attrs": {"ability": "empty", "item": "empty", "moveset": "empty", "nature": "empty", "role": "empty", "species": "empty", "spread": "empty"}, "slot": 2}, {"attrs": {"ability": "empty", "item": "empty", "moveset": "empty", "nature": "empty", "role": "empty", "species": "empty", "spread": "empty"}, "slot": 3}, {"attrs": {"ability": "empty", "item": "empty", "moveset": "empty", "nature": "empty", "role": "empty", "species": "empty", "spread": "empty"}, "slot": 4}, {"attrs": {"ability": "empty", "item": "empty", "moveset": "empty", "nature": "empty", "role": "empty", "species": "empty", "spread": "empty"}, "slot": 5}, {"attrs": {"ability": "empty", "item": "empty", "moveset": "empty", "nature": "empty", "role": "empty", "species": "empty", "spread": "empty"}, "slot": 6}]}
```

**OL5** (`` `yes` ``): same state JSON as OL2b (byte-identical summary); only the user line differs.

**OL7a** (`` `the faster one` ``): same state JSON; only the user line differs.

**OL8** (`` `neither` ``): same state JSON; only the user line differs.

### Does the summary contain the pending option list?

**No.** Fixtures hold options in `pending_presentation.options` (OL2b/OL7a/OL8: Garchomp, Incineroar, Jolteon; OL5: Garchomp only), but `compact_state_summary` drops them. Parser sees `pending_kind: candidate_selection` and `asked_action: null` only.

### What differs for OL5?

From the parser’s input: **only the user text** (`` `yes` `` vs `` `2` `` / `` `the faster one` `` / `` `neither` ``). State summaries are identical. The fixture differs (1 option vs 3), but that difference never reaches the parser. `` `yes` `` is an accept-style bare answer; the others need option contents (index / relative label / reject-all) that the summary omits.

### Runner vs eval

Same path. Arm runner (`harness.py` ~465–468) passes `state.get("_guard_pending_asked")` into `parse_user_turn` → `compact_state_summary`. On these OL starts that field is unset (`None`), same as parser-eval’s `_resolve_parser_state`. Runner does **not** pass more than the eval; neither injects options into the summary.

### Proposed smallest follow-up (not implemented)

Option list is missing from what the parser sees. Smallest fix: new **default-off** flag (own pin) that adds a compact `pending_options` list (e.g. species labels only) into `compact_state_summary` when `pending_presentation` has options — or stamp a `pending_asked` of `{action: select_option, …}` on CS fixtures in the caller. Not a one-line plumbing fix; left as a proposal only.

## Key hashes

| Pin | Hash |
|---|---|
| keys_fu72 `key_hash` | `246e5a7daa194d42897e0ef2e89dcf470e9a9646ea232a077f42255949a0fa02` |
| keys_fu74 `key_hash` | `38785fcb77d171088f8a3a17d8ca9d6b1ec4ace90cf0cea584a6b0b565205f47` |
| combined `revised_key_hash` | `d11cea9849ce10bbfc095678d58b3b947f965471812c1a1c2e36d88d48fa325c` |
| derived_keys | `bba5787ce95f9e0b615ce679d8622ca6b1d7709e2cc8e73dc493cda7b88354b2` |
| claim battery | `e7492a6811f057f1e84ccac821c1249eb29a3fad1f25eec6f9a0e613b776f4b0` |
| false_legal | `3025138427391e57a92e1862a87b0074d44a51b290836077abf094af92c4bdec` |

## Could not do

- Arm run / grade; #389 / #391 / judge / uncertain / #310.
- Pending-options summary flag (proposed above; not implemented in this close-out).

## Tests

```
uv run pytest scripts/eval/part_g_arm/state/test_ix_facts_fu74_drift.py \
  scripts/eval/part_g_arm/state/test_fu74_revised_arm.py \
  scripts/eval/part_g_arm/state/test_fu74_parser_prompt_cut.py \
  tests/recommender/test_cli_layer_arm_isolation.py -q
```

**23 passed** (FU74 wiring + prompt-cut suite after close-out). Isolation golden unchanged (flag-off = a393ae91).
