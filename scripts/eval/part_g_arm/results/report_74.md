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
| 6 `--parser-v2` | rewritten abstract prompt; 4-gram overlap test; parser-eval CLI for Vu |
| 7 tests + this report | isolation + wiring + parser/prompt-cut tests |

## Flag table

| Flag | Default | Notes |
|---|---|---|
| `sticky_locks` | off | unchanged |
| `unlock_keeps_values` | off | unchanged |
| `tool_fixes_v2` | off | unchanged |
| `ix_tools_v1` | off | new CLI → `set_ix_tools_v1` |
| `prompt_cut` | off | needs `--guard`; selects `prompt_guard_cut.md` |
| `parser_v2` | off | needs `--guard`; selects `prompt_guard_parser_v2.md` |
| `--keys` | `committed` | `fu74` = overrides + seeds + rev5 + hand keys |
| `--revised-arm` | off | guard + sticky + unlock_keeps + tool_fixes_v2 + ix_tools_v1 + keys fu74 + prompt_cut + parser_v2 |

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

## Parser v2 (DEV) — round 2

Prior DEV result (empty-team eval): v2 tied v1 at 84/118; fixed 6 / broke 6. **Do not freeze.**

Round-2 prompt changes (class definitions + committed v1 line only; no graded-turn wording):
1. Restored v1 build anchor verbatim: `"Give me a X build" / "Put Y in slot N" / "Add a constraint…" → WRITE (set_slot or constraint), not LOOKUP.`
2. Narrowed antecedent rule: ASK only when a referent points at a prior mention **and** that mention is absent from the state summary — not short field/move writes.
3. Invented examples kept (in-sample; labeled in eval splits).

### Parser-eval state fidelity

Eval now passes the same start builders as the runner (`resolve_start_state` + `prepare_start_state_for_guard`) and prints per-turn: pending_kind, asked_action, slots, constraints. OL2b/OL5/OL7a/OL8 load pending `candidate_selection` fixtures (measurable). **MT2 t3** and **MT6 t3** are mid-trajectory with empty start loaders → marked `state_dependent_not_measured`, excluded from headline, listed separately.

```bash
uv run python -m scripts.eval.part_g_arm.state.parser_eval --parser-eval \
  --model qwen3.5:latest --keys fu74 --out /tmp/parser_eval_fu74.json
```

Prints v1+v2 agreement, gains/regressions v1→v2, state-dependent table, and DEV agreement **with and without** the five in-prompt example rows. All numbers **DEV**. Do not freeze v2 from this run alone.
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

- Live parser agreement numbers (Vu runs `parser_eval` locally).
- Arm run / grade; #389 / #391 / judge / uncertain / #310.

## Tests

```
uv run pytest scripts/eval/part_g_arm/state/test_ix_facts_fu74_drift.py \
  scripts/eval/part_g_arm/state/test_fu74_revised_arm.py \
  scripts/eval/part_g_arm/state/test_fu74_parser_prompt_cut.py \
  tests/recommender/test_cli_layer_arm_isolation.py -q
```

**25 passed.** Isolation golden unchanged (flag-off = a393ae91).
