# Report 75 — `parser_pending_options` (DEV)

Stacked on #395 (`fu74-revised-arm` @ `24a65c5`). No arm run, no grading. Vu runs parser-eval locally.

## Defect (for key-defect register)

Harness defect: the guard parser’s compact state summary omitted the pending option list. Bare answers to a displayed candidate list (index / relative label / reject-all) had nothing to bind to. Affects the real arm path, not only parser-eval. Turns: **OL2b, OL7a, OL8** (ASK instead of PENDING_ANSWER in the audited run); **OL5** returned PENDING_ANSWER in that run but on the same incomplete summary (single-option fixture; user text `` `yes` ``).

## Where the options come from

| Reader | File | Notes |
|---|---|---|
| Store | `state["pending_presentation"]` | CS: `kind`, `options`, `slot_index`, `team_fingerprint` |
| `pending_fingerprint_matches` | `guard_allowed.py` ~147–156 | reads `pending_presentation` |
| `select_option` / `read_pending` | `tools.py` ~965–1040 | `_pending_options` flattens labels; CS label = species |
| FU75 summary | `guard_parser.compact_state_summary` | when flag on, maps `read_pending(...).options` → `{index, label}` |

No new store. Labels are the same strings `read_pending` returns (what the user was shown). Cap = full list length; no extra truncation.

## Flag

| Flag | Default | `--revised-arm` |
|---|---|---|
| `parser_pending_options` | off | **on** |
| CLI | `--parser-pending-options` | needs `--guard` (alone → `SystemExit`) |
| Prompt | `prompt_guard_parser_po.md` (v1 + one class-definition sentence) | own sha via `parser_prompt_sha256` |
| `parser_v2` | off | still off under profile |

Flag off: summary JSON and parser prompt sha are byte-identical to today (isolation golden extended with three new keys; prior hashes untouched).

## Summary before / after (OL2b fixture; no graded user text)

**Before (flag off):** `pending_kind: candidate_selection`, `asked_action: null`, no `pending_options`.

**After (flag on):** same fields plus:

```json
"pending_options": [
  {"index": 1, "label": "Garchomp"},
  {"index": 2, "label": "Incineroar"},
  {"index": 3, "label": "Jolteon"}
]
```

## Arm-side check (code read, no run)

`harness.py` ~465–468 passes `state.get("_guard_pending_asked")` into `parse_user_turn`, which calls `compact_state_summary`. Same function the eval uses. With the flag set on the process (runner `set_parser_pending_options`), the arm sees the same summary shape as parser-eval. Eval agreement therefore means what it says for the guard path.

## Parser-eval (Vu runs)

```bash
uv run python -m scripts.eval.part_g_arm.state.parser_eval --parser-eval \
  --model qwen3.5:latest --keys fu74 --parser-pending-options \
  --out /tmp/parser_eval_fu75.json
```

Compares **v1 (flag off)** vs **pending_options** on the 116 measured turns (MT2 t3 / MT6 t3 excluded). Prints gains/regressions by id, confusion by key class, and the four OL turns separately. All **DEV**. A regression outside OL turns is a finding — do not tune the prompt sentence to fix it.

## Tests

```
uv run pytest \
  scripts/eval/part_g_arm/state/test_fu75_parser_pending_options.py \
  scripts/eval/part_g_arm/state/test_fu74_revised_arm.py \
  scripts/eval/part_g_arm/state/test_fu74_parser_prompt_cut.py \
  tests/recommender/test_cli_layer_arm_isolation.py -q
```

**33 passed** (local).

## Could not do

- Live parser agreement numbers (Vu runs locally).
- Arm run / grade; parser v2 changes; #389 / #391 / judge / keys.
