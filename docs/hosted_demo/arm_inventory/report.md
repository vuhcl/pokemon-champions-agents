# Arm inventory for a hosted demo (2026-11-05)

Read at `2b8a6bc`. No provider call. The scripted floor used a fake chat model in this process. Product files were not edited.

A hosted adapter can import the turn function and pass its own chat model. It does not have to edit a frozen file to do that. `tools.py` and the v2 prompts still match `FROZEN_MANIFEST_ARM_V2.json`. Eight files listed in the older `FROZEN_MANIFEST_ARM_STATE.json`, including `harness.py` and `tools.py`, no longer match that manifest.

## 1. Artifacts

1. Entry points.

- `scripts/eval/part_g_arm/loop.py` `ArmLoop` (line 48) is the Part G gate arm. It is a two-node StateGraph (`agent` then `tools`, line 59). One user string goes in through `run_item` (line 107). The model may call `recommender.arm_tools` lookups. The answer is the last model message's text (line 116). This file is under `scripts/eval/`. The tools it calls live in `recommender/arm_tools.py`.
- `scripts/eval/part_g_arm/state/harness.py` `run_turn` (line 339) is the request-set arm. One user string plus a state dict go in. The same function returns the updated dict and a record whose `final_text` is the answer (line 517). Under `scripts/eval/`. This is the loop a demo would call. `loop.py` has no team draft.
- Rungs are flags on that same `run_turn`, not separate programs. `request_set_runner.py` lines 58–65 default all five off. `--tool-fields` adds fields on existing tools. `--wrapper` turns on `set_slot` and drops `lock_slot` from the schema (`tools.py` 471–478). `--draft` makes `set_slot` write unlocked values and adds `lock_fields` (`set_slot_tool.py` 471–480, `draft_lock.py` 45). `--guard` runs one parser call then refuses tools outside the allowed set (`harness.py` 381, `guard_exec.py` 89). `--judge` runs judge-lite after the text and may retry the text once (`harness.py` 545–565). Rung 6 is all five on.

2. Frozen files.

- `scripts/eval/part_g_v4/FROZEN_MANIFEST.json` (PRE-MD-CLAIM): 17 files, all match this tree. It lists the gate prompt, extractors, and scorer. It does not list the stateful harness.
- `scripts/eval/part_g_arm/state/FROZEN_MANIFEST_ARM_STATE.json` (PRE-RS-ARM, status frozen, line 46 of that file): 28 files. Eight have drifted: `class_scorer.py`, `errata.json`, `errata_read.py`, `hand_audit_form.py`, `harness.py`, `pending.py`, `request_set_runner.py`, `tools.py`.
- `scripts/eval/part_g_arm/state/FROZEN_MANIFEST_ARM_V2.json` (status frozen): 15 files, all match. It lists `tools.py`, the rung prompts, the process scorer, the covered list, the parser prompt and labels, `derived_keys.json`, both batteries, and the request set. It does not list `harness.py`, `set_slot_tool.py`, `draft_lock.py`, `guard_parser.py`, `guard_exec.py`, or `judge_lite.py`.

A separate module can import `run_turn` and pass `llm` without modifying those files. An adapter that changed `tools.py` or a v2-listed prompt would be editing a file the v2 freeze still matches. An adapter that changed `harness.py` would be editing a file the PRE-RS-ARM manifest lists, and that file has already drifted from the recorded hash.

3. Product package. Lookup tools and `ArmTools` are in `recommender/arm_tools.py`. The turn loop, state tools, guard, and judge are under `scripts/eval/part_g_arm/`. The arm is not only under `scripts/eval/`.

## 2. Session state

1. The object is a plain dict. `empty_team()` (`fixtures.py` 31) creates six empty slots plus null pending fields. `start_state` (`harness.py` 612) builds the eval seeds. `run_turn` updates that dict through `dispatch` (line 125). `snapshot` (line 98) is the JSON view stored on the turn record. Team draft, locks, pending kind, constraints, and archetype signature are on that snapshot. Chat history is not inside the dict unless a seed put `_message_history` there. The request-set runner keeps user and assistant text in a local list and passes it back as `prior_messages` (`request_set_runner.py` 229–248).

2. No checkpointer. `ArmLoop.graph.compile()` (`loop.py` 65) is called with no saver. `run_turn` is a for-loop. The dict dies with the process. The eval runner writes a transcript of snapshots at the end of a row. That transcript is not loaded back into `Slot` objects by anything read here.

3. Many dicts can exist. These are process-wide:

- Five flag globals in `tools.py` 53–106 (`_TOOL_FIELDS`, `_WRAPPER`, `_DRAFT`, `_GUARD`, `_JUDGE`).
- `load_usage` and several other caches in `recommender/usage_data.py` (first is line 109).
- The matchup default memo, when no thread id is bound. `show_candidates` calls `discover_single_locked(state, {})` (`tools.py` 1741). `_bind_matchup_memo` (`nodes.py` 1703) then sees no `thread_id` and keeps the default memo.
- One tool-log path, `artifacts/tool_calls.jsonl` unless `RECOMMENDER_TOOL_LOG` is set (`recommender/tool_log.py` 14–18).
- `ArmLoop` writes `RECOMMENDER_FIXED_NOW_UTC` into the process environment (`loop.py` 50–51). `run_turn` does not.
- One calc base URL on the config (`config.py` 29), default `http://127.0.0.1:4173`.

4. The state dict has no lock. The flag globals have no lock. The runners play one row at a time. Two sessions in one process would share the flags, the usage cache, the default matchup memo, and the tool log. The dict itself is not safe to mutate from two threads.

## 3. Model and credentials

1. The builders are `ChatOllama`. `loop.build_llm` (`loop.py` 41) and `harness.run_dev` (`harness.py` 1061) pass `model`, `temperature`, `reasoning`, `num_ctx`, `num_predict`, and a client timeout. `run_turn` does not construct a model. It uses the object it is given, then `bind_tools` has already happened in the runner (`request_set_runner.py` 904 area, `harness.py` 1064). Passing another LangChain chat model means constructing it outside and handing it in. Nothing read here accepts `api_key=`. The guard parser calls `with_structured_output` on that same object (`guard_parser.py` 145). Judge-lite does not build a model (`judge_lite.py` 467). The judge text retry calls the same object with tools unwrapped (`harness.py` 330 and 577). A separate claim-extraction judge in `scripts/eval/part_g_arm/judge/extract.py` builds its own Ollama HTTP call. That is not the session loop.

2. Schemas are the dicts from `combined_specs`. Flags off: 34 tools, and `lock_slot` is present. Draft rung (`tool_fields`, `wrapper`, `draft`): 41 tools, listed in section 6. `lock_slot` is absent there. The v2 manifest records 3,731 tokens for the flags-off schema. This read did not recompute tokens and did not call a provider. Ollama-specific knobs are on the `ChatOllama` constructor and on `ArmConfig` (`config.py` 16–21): `num_ctx` 16384, `num_predict` 2048, `think` false. The schema dicts do not contain those keys. `run_turn` also reads `prompt_eval_count` from Ollama response metadata (`harness.py` 377–439). Not checked: whether Anthropic or OpenAI `bind_tools` accepts these dicts unchanged.

3. Writers that could see a credential if it were only inside the model object: none copy the model. `run_record` (`harness.py` 1018) stores the model name and a digest, not a key. Turn `errors` store `f"{type}: {exc}"` (`harness.py` 432 and 581), so a provider exception that echoes a key would land in the transcript. `log_tool_call` writes tool name and args (`tool_log.py` 22). The state snapshot does not include the model. Not checked: Ollama or HTTP client debug logs.

4. The guard parser uses the same object as the main loop. Judge-lite uses no model for the checks. Its one retry uses that same object.

## 4. What a turn is, and the floor

1. One user message is one `run_turn` call. Inside it, the model may be invoked up to `max_turns` (default 8, `config.py` 22). The registered failure policy (`request_set_runner.py` 68–74) is 300 seconds per turn, 16 tool calls, and "no usable answer" with no silent retry. The 16-call cap is enforced inside the guard (`guard_exec.py` 13 and 102). Calc infra may rerun a whole eval row once (`request_set_runner.py` 76–81). That is separate from a tool retry. A tool error or a refusal is a result dict on that same user message. A model exception or the deadline stops the loop and records the error. Judge-lite, when the flag is on, may revise the text once.

2. The output is prose in `final_text` plus the structured snapshot on the record. A team panel would read `read_team` (`tools.py` 535) or `snapshot` slots: species, `species_locked`, and per-attribute value and lock. The snapshot's pending field is a boolean and a kind, not the option list. `read_pending` exists. Its full shape was not opened.

3. Scripted floor. Fake model, no network. Species Pelipper, Incineroar, Rillaboom, Garchomp, Kingambit, Whimsicott. Amoonguss was refused as not legal (`is_nonstandard='Past'`), and that refusal applied nothing because `set_slot` is all-or-nothing (`set_slot_tool.py` lines 4–6).

| Configuration | Messages | What one call did |
|---|---|---|
| Rung 3 (`tool_fields` + `wrapper`, draft off) | 1 | One `set_slot` with a `slots` list locked species on all six. Other attributes stayed empty. `all_locked` was false on every slot. |
| Rung 4 (draft on) | 2 | Message 1 drafted all six species, none locked. Message 2 sent six `lock_fields` calls and locked species on all six. `all_locked` stayed false. |
| Rung 6 (guard and judge on, same tools) | 2 | Same as rung 4. Judge retries were 0 on this text. |

`lock_fields` takes one slot (`draft_lock.py` 45). Six slots were six tool calls inside one user message. A refused `set_slot` (`NotAPokemon`, and the Amoonguss batch) stayed on that same user message and left the draft unchanged. It did not add a message.

A drafted slot is not `all_locked` (`state.py` 717). `show_candidates` still requires a fully locked anchor (`tools.py` 1676 and 1734). `locked_pairs` in `scripts/eval/harness.py` 98 skips any slot that is not `all_locked`. Judge-lite treats "slot N is locked" as false unless `all_locked` (`judge_lite.py` 325–328). There is no separate numeric score that returns zero. Those gates ignore an unlocked draft. Species-only locks, including after `lock_fields` on a species-only draft, are still not `all_locked`, because role, ability, item, moveset, spread, and nature are empty.

4. At flags off, `lock_slot` is in the schema and `set_slot` is not. From the wrapper rung up, `lock_slot` is removed and `set_slot` is the write. `lock_fields` exists only with `--draft`. A full lock of valued fields is `lock_fields`. `set_slot` on the draft rung writes `locked=False`. It does not lock the build.

## 5. Cost and latency

1. Heavy tools, from the names and the call path, are `show_candidates` (it calls `discover_single_locked` or `discover_multi_locked`), `calc_damage`, `get_speed`, and `solve_spread`. `show_candidates` does call the CLI discover functions. The memo bind on that path gets no thread id, so it uses the default memo, not a session thread from #381. Not checked: the body of every lookup for how much calc it does.

2. In the scripted floor, every `set_slot` and `lock_fields` recorded `latency_ms` 0. The slowest call in that game is not distinguishable at millisecond resolution. The message wall was about 0.001 s without the guard and about 0.01–0.02 s with the guard parser running in-process. `RECOMMENDER_TOOL_LOG` was empty. No calc batch ran. `show_candidates` was not part of this script.

3. `ArmTools` asserts `allow_live` is False (`recommender/arm_tools.py` 64). `ArmConfig` does the same (`config.py` 36). The runners pass `allow_live=False`. Local HTTP that does exist, and was not called here: calc at `127.0.0.1:4173`, and Ollama at `127.0.0.1:11434` from `run_battery.model_facts` (`run_battery.py` 32 and 73) and from the claim-extraction judge (`judge/extract.py` 11). The request-set runner can spawn `npm start` if calc is down (`request_set_runner.py` 869). Not checked: a line-by-line search of every tool body for another URL.

## 6. Streaming and status

1. `run_turn` and `ArmLoop` call `llm.invoke`, not `stream`. No LangChain callback handler is attached. A tool's start is not an event. The record stores `latency_ms` after the call returns (`harness.py` 465). That is the analogue of a stage, and it is available only once the tool has finished.

2. Draft-rung tool names, 41: `no_lookup_needed`, `get_typing`, `get_abilities`, `check_species_ability`, `check_species_legal`, `check_item_legal`, `get_move_static`, `get_speed`, `calc_damage`, `get_usage_items`, `get_usage_teammates`, `describe`, `get_usage_spreads`, `get_common_speeds`, `get_meta_threats`, `get_usage_stats`, `set_constraint_active`, `unlock_slot`, `reset_team`, `commit_slot`, `read_team`, `read_pending`, `select_option`, `confirm_build`, `reject_pending`, `reject_option`, `reject_all`, `read_rejected`, `add_constraint`, `read_constraints`, `restore_constraint`, `show_candidates`, `check_learnset`, `change_archetype`, `read_archetype`, `find_species`, `set_slot`, `lock_fields`, `unlock_fields`, `check_hypothetical`, `solve_spread`.

## Needs a decision from Vu

- Which entry a hosted session calls. The team loop is `run_turn`. `loop.py` does not hold a team.
- Where the state dict is stored across processes. Nothing here survives a restart.
- Whether one process may host more than one session while the flag globals and the default matchup memo are shared.
- Which chat model is constructed outside `run_turn`, and whether the guard's `with_structured_output` call on that same object is acceptable.
- What "six locked" means for the panel. Species can be locked in one message. `all_locked` stays false until role, ability, item, moveset, spread, and nature are locked too.
- Which of the 41 names get a plain-language status label. Nothing in the arm maps a tool name to a sentence.

## Would require editing frozen code

- Any change to `tools.py` or to a prompt, scorer, key, battery, or request set listed in `FROZEN_MANIFEST_ARM_V2.json`. Those hashes match today.
- Any intentional edit to the eight drifted PRE-RS-ARM files, if that freeze is still in force. They already do not match. Importing them does not require a further edit.

## Not checked

Provider `bind_tools` behavior. Token recount of the 41 schemas. `show_candidates` wall time. Every tool body for a network call. `read_pending`'s full return shape. Ollama client logs. Reconstructing a `Slot` dict from a transcript.
