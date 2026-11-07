# Follow-up 71: CLI request-set rows (#280, #281, #282, #283)

## Evidence caveat (read first)

No live LLM was available in this session (`langchain_ollama` is not installed and no provider env is set). Every "current output" and "new output" below was produced by driving `handle_line` with the turn-intent parser **stubbed** to return the extraction the `turn_intent` prompt specifies for that row:

- MS1: `lock`, `slot_index=2`, `attr=species`, `value=Garchomp`.
- MS2, Q10, MR6: `repick_locked_slot` with `slot_index`.
- MR7: `pending_response`, and separately `full_slot_confirmed`.

Whether the real parser emits those intents for those sentences was not tested. The deterministic gates (item 1, and the MR7 gate) do not depend on the parser.

## Hard rule: arm output unchanged

- No return dict of `apply_lock`, `unlock_locked_slot`, `reset_team` or `commit_full_slot` changed. No node was edited.
- Changes are limited to:
  - `recommender/nodes.py`: `classify_input`, pre-parse wiring only.
  - `recommender/nodes_classify.py`: one new gate.
  - `recommender/present_text.py`: `format_turn` render.
  - `recommender/team_rules_qa.py`: new.
- The arm wrappers (`lock_slot`, `unlock_slot`, `reset_team_state`, `commit_slot`, `confirm_build`) do not call `classify_input` or `format_turn`.
- `tests/recommender/test_cli_layer_arm_isolation.py` calls each of those wrappers on 11 inputs and compares the sha256 of each result's repr against a golden captured from clean `HEAD` (891f2f1, in a throwaway worktree) before any edit. It passes.
- Existing arm tests pass unchanged.

## Item 1: #281 rules Q&A gate (H8, Q9, MU1, MU5)

Row text (`part3_request_set_v4.md`, located by id):

| id | Request | State | Expected |
|---|---|---|---|
| H8 | Can I put Choice Scarf on both Garchomp and Jolteon? | idle empty | **No** (Item Clause); no-mutation check |
| Q9 | Can I have two Incineroar on one team? | idle | **No** (Species Clause); no mutation |
| MU1 | What if I gave Choice Scarf to both Garchomp and Jolteon on this team? | idle empty | NO-MUTATION; claims scored; state unchanged; no lock/commit. Required claim: Item Clause blocks both holding Choice Scarf. Other claims scored if made; variants must be legal. |
| MU5 | Could I run two Life Orbs on this team? | any | NO-MUTATION; no item-lock tools; state unchanged |

Current output (all four, before the change; the parser is stubbed to `pending_response`):

```
I couldn't parse that clearly. Name the field (ability, item, moves, nature, or spread), the new value, and whether to change only that field or regenerate the set.
Team: (no locked members)
```

With no parser wired, `classify_pending` raises `NotImplementedError` and the CLI prints `NO_PENDING_MESSAGE`.

Change: `recommender/team_rules_qa.py::try_route_team_rules`, called first in `classify_input`, ahead of the item-holders pre-parse.

- It fires only on a question-shaped text with a duplicate cue (both, two, 2, twice, same).
- It finds one species ("two X") or one item named in the text.
- It builds a two-slot draft, puts the value in slot 1, and asks `validate_team_value` (ADR-081) about slot 2. The reply is the validator's refusal message, prefixed "No." If slot 1 itself is refused (unknown or illegal value), that refusal is the answer.
- It never raises (broad `except` returns None). Unrecognised questions fall through to the existing path.
- It reads no state and writes none. Like the item-holders gate, it returns a `pending_response`, so `stamp_system_claim` may set `last_system_claim`. The team draft is untouched.
- The arm's `describe` tool was not touched.

New output:

| Row | Output |
|---|---|
| H8, MU1 | `No. Item Clause: Choice Scarf is already held in slot 1. Each item can be used only once.` |
| Q9 | `No. Species Clause: Incineroar clashes with Incineroar in slot 1. One of each Pokémon, forms included.` |
| MU5 | `No. Item Clause: Life Orb is already held in slot 1. Each item can be used only once.` |

The "slot 1" in these answers is the hypothetical first holder, and it is the validator's wording. If you want hypothetical wording instead, that is a validator-message change that touches the arm, so I left it.

MU1 and MU5 behave per their rows: the answer states the Item Clause, and nothing is locked or committed.

Tests (`tests/recommender/test_cli_request_rows.py`):
- four parametrized rows: No plus the clause name, and team draft unchanged
- four fall-through cases: "Can Garchomp learn Earthquake?", "Can I have two weeks to decide?", "Lock two Incineroar", "I want both Garchomp and Jolteon"
- a never-raises test with a failing `load_snapshot`

Scope limits (the `shortcut:` comment in the module):
- Only duplicate-use phrasings are covered.
- MU1's other claims ("other claims scored if made") are not generated; the reply makes only the Item Clause claim.

## Item 2: #282 read-back after lock and unlock (MS1, MS2)

Row text:
- MS1: "Lock Garchomp in slot 2", idle empty. Expected: read-back slot2 species=Garchomp locked=true.
- MS2: "Unlock slot 1", slot 1 locked. Expected: read-back slot1 unlocked / empty.

Current output (stubbed parser):
- MS1: the state was correct (slot 2 Garchomp, locked) but the reply never said so. It showed only the discovery text (my scripted state landed on `Bootstrap intake is incomplete`).
- MS2: the slot was wiped to `empty_slot()` and the reply showed only discovery text.
- What the CLI does today on unlock: `unlock_locked_slot` replaces the slot with `empty_slot()`, so the key's "empty" is what the CLI does. `unlock_keeps_values` is an arm-harness flag and is not consulted by the CLI path. Unlock semantics are unchanged.

Change: `present_text._slot_readback`, called from `format_turn`.
- It runs only for `lock` and `repick_locked_slot` turns. The slot number comes from `turn_payload` (the index the node used, shown 1-based via `display_slot`). Species and locked fields are read from `team_draft`, not from the parsed intent.
- It is skipped on error, except for the nothing-locked unlock (item 3).

New output:
- MS1: `Slot 2: Garchomp (locked: species).`
- MS2: `Slot 1: empty (unlocked).`

Tests: `test_ms1_lock_garchomp_in_slot_2_reads_back_state`, `test_ms2_unlock_slot_1_reads_back_empty_slot`.

## Item 3: #283 empty-state responses (Q10, MR6, MR7)

Row text:
- Q10: "Can I unlock slot 2 when nothing is locked?", empty team. Expected: explains empty unlock; no mutation.
- MR6: "Unlock slot 2", none locked. Expected: empty unlock refuse; state unchanged.
- MR7: "Commit this build", idle. Expected: nothing pending; state unchanged.

Current output (stubbed parser):
- Q10 and MR6 (`repick_locked_slot`): `Slot commit error: Species repick requires a fully locked slot.` then `Team: (no locked members)`. The state is unchanged, but nothing says the slot is empty or that there is nothing to unlock. This differs from the row.
- MR7 (`pending_response`, or `full_slot_confirmed` at idle): the generic `I couldn't parse that clearly. Name the field...` text. State is unchanged, but nothing says that nothing is pending. This differs from the row.

Change:
- Q10 and MR6: `_slot_readback` adds a line when the repick error fires on a slot with no locked field. The existing error line stays and the node is untouched.
- MR7: `nodes_classify.try_route_idle_commit`, a narrow gate in `classify_input`. It fires only when no pending screen exists and the text is "commit/confirm/accept this/the/that build/set/slot". Otherwise it falls through.

New output:
- Q10 and MR6: the error line, then `Slot 2 has nothing locked, so there is nothing to unlock. Nothing was changed.`
- MR7: `Nothing is pending to commit. No build is waiting for confirmation; nothing was changed.`

A partly locked slot keeps the original error, which is still accurate there.

Tests: `test_unlock_with_nothing_locked_explains_and_changes_nothing` (Q10 and MR6) and `test_mr7_commit_with_nothing_pending_says_so_and_changes_nothing` (both parser variants). Each asserts `team_draft` equal before and after (MR7 also asserts no pending screen).

Gap: Q10 is phrased as a question. It only reaches this reply if the real parser emits `repick_locked_slot` for it, which was not tested live.

## Item 4: #280 slot-index convention

- The convention (1-based, converted once in `recommender/slot_index.py`) is in ADR-081 and the `turn_intent` prompt. It is tested in `test_slot_index_parse.py`.
- MS1 against the CLI with the stubbed extraction: user slot 2 writes `team_draft[1]`, species Garchomp, locked, and slot 3 stays empty. It **passes**, and it passed before my change (the state was already correct). The read-back now shows `Slot 2`.
- No fix was needed. Caveat: MS1 is verified through the stubbed parser plus the extractor's own conversion (`_payload_for`), not through a live LLM.

## Tests run

- `uv run pytest`: **4802 passed, 18 skipped**, in 2:00. This includes the 16 new tests (15 in `test_cli_request_rows.py`, 1 isolation test).
- `npm test`: 119 pass, 0 fail.
- `run_all_checks.py`: exit 0, every check PASS.
  - keys sha unchanged: `bba5787ce95f9e0b615ce679d8622ca6b1d7709e2cc8e73dc493cda7b88354b2`
  - claim battery hash unchanged: `e7492a6811f057f1e84ccac821c1249eb29a3fad1f25eec6f9a0e613b776f4b0`
  - false-legal battery hash unchanged: `3025138427391e57a92e1862a87b0074d44a51b290836077abf094af92c4bdec`
  - `LAST_CHECK.json` was rewritten by the run and restored with `git checkout`. No battery or key file was modified.
- Calc service: port 4173 was already held by a service from the other checkout (`/Users/nowaki027/pokemon-champions-agents`, pid 7145, started Oct 30). On your instruction I reused it instead of starting another one. Its `services/calc` and `vendor/smogon-calc` were identical to this worktree's, `package.json` is identical, and none of those files were newer than its start time. I did not stop it.

## Issues

The PR would close #281, #282, #283 and #280 (MS1 passes), each on its own `Closes #N` line. It does not close #284, #290, #291, #298 or #317. Nothing is committed or pushed yet.
