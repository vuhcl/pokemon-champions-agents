# Report 74 — revised arm wiring + IX key cut (DEV)

Branch stack: PR A `#394` (`fu74-ix-key-cut`) → PR B (`fu74-revised-arm`). No arm run, no grading.

## Discovery findings (carried)

See chat Discovery. Summary: keys_fu72/fu74 were unwired; `set_ix_tools_v1` had no runner flag; process-metric `flags_from_run_record` omitted `ix_tools_v1`; request overrides and fu72 seeds unused; refusal message named tool+class.

## Plan as built

| Item | Done |
|---|---|
| 2 IX key cut (`keys_fu74/`) | PR A (+ review fixes: IX7 item check, keyword notes, no manifest self-hash) |
| 3 `--keys fu74` | scorer CSV rev5, hand-audit points replace errata, overrides + seeds, pin_hashes |
| 4 `--ix-tools-v1`, `--revised-arm` | wired; profile forces guard rung 6; resolved flags recorded |
| 5 `--prompt-cut` | new `prompt_guard_cut.md` + refusal rewrite; FU69 literal drops = no-ops |
| 6 `--parser-v2` | new `prompt_guard_parser_v2.md`; live agreement **not measured** (no arm/LLM run) |
| 7 tests + this report | isolation extended; `test_fu74_revised_arm.py` on pytest path |

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
| `--revised-arm` | off | enables guard + sticky + unlock_keeps + tool_fixes_v2 + ix_tools_v1 + keys fu74 + prompt_cut + parser_v2 |

`--prompt-cut` / `--parser-v2` alone without guard → clear `SystemExit`.

## Prompt cut (DEV-tuned)

**FU69 literal hunt:** “state only read-back state”, per-kind rejection names, and `set_slot` moves-replacement text appear only in `report_72.md` prose — **not** in any prompt the arm loads, and not on an unmerged branch searched from main. Those drops are **no-ops**; nothing invented.

**Actual cut** (`prompt_guard.md` → `prompt_guard_cut.md`):

- `unlock_slot` wipe sentence → keeps values; `clear_slot` wipes with `replace`
- `_GUARD_DELTA` “naming the class” → refused without naming class; ask for missing detail
- Keep: do not invent; Spe/damage assumptions; added “Do not name internal tool names to the user”

### Refusal strings (`guard_exec.py`)

**(b) is new behavior, not a keep.**

| | Text |
|---|---|
| **Old** | `Refused {name}: not allowed for request class {cls}. Do not retry this call; answer from tools already returned or ask.` |
| **New** (`--prompt-cut`) | `That action was refused for this request. Do not retry it. Answer from what the tools already returned, or ask the user for the missing detail (which slot, which species, or confirmation to clear).` |

**What the arm loses in the user-visible string:** the refused tool name and the request class label. Structured fields `tool`, `class`, `reason` on the refusal result are unchanged so the arm can still learn what was blocked.

## Parser v2 (DEV)

- New file `prompt_guard_parser_v2.md` (committed `prompt_guard_parser.md` untouched when flag off).
- Clarifies: illegal/refused writes still WRITE; clear slot numbers → WRITE; conflicting dual constraints still WRITE; bare “slot I mentioned” → ASK; option lists without a named lock → LOOKUP.
- **No graded-turn text** in prompt, examples, or `dev_guard_parser_labels.json`.
- **Agreement numbers:** not computed this follow-up (no live LLM / no arm run). Scaffolding only. Label any future numbers DEV. When measured, report original-text vs fu74-override text for the 32 turns (override-affected: HC1, MT1, MT6, MR2, MR3, MR5, MW3, HU3, TB2, … from `request_text_overrides_fu72.json`).

## Key hashes

| Pin | Hash |
|---|---|
| keys_fu72 `key_hash` (unchanged) | `246e5a7daa194d42897e0ef2e89dcf470e9a9646ea232a077f42255949a0fa02` |
| keys_fu74 `key_hash` | `38785fcb77d171088f8a3a17d8ca9d6b1ec4ace90cf0cea584a6b0b565205f47` |
| combined `revised_key_hash` | `d11cea9849ce10bbfc095678d58b3b947f965471812c1a1c2e36d88d48fa325c` |
| derived_keys (unchanged) | `bba5787ce95f9e0b615ce679d8622ca6b1d7709e2cc8e73dc493cda7b88354b2` |
| claim battery (unchanged) | `e7492a6811f057f1e84ccac821c1249eb29a3fad1f25eec6f9a0e613b776f4b0` |
| false_legal (unchanged) | `3025138427391e57a92e1862a87b0074d44a51b290836077abf094af92c4bdec` |

`KEYS_MANIFEST_FU74.json` is **not** self-hashed (`manifest_self_hashed: false`).

Under `--keys fu74`, fu74 IX turns **replace** fu72 stubs (no point merge). Errata acceptance rewrites are skipped for rows that have hand-key points.

## Could not do

- Live parser-v2 agreement on 32 / 118 turns (needs model; out of scope).
- Arm run / grade.
- Judge / WRITE-bundle / uncertain-forces / #391 / #389 / calc #310.

## Tests

```
uv run pytest scripts/eval/part_g_arm/state/test_ix_facts_fu74_drift.py \
  scripts/eval/part_g_arm/state/test_fu74_revised_arm.py \
  tests/recommender/test_cli_layer_arm_isolation.py -q
```

**20 passed** (drift 3 + revised-arm 16 + isolation 1). Isolation golden hashes unchanged (flag-off = a393ae91).
