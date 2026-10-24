# Part G arm: dev revision log

Dev runs use the seed-1 battery (`dev_seed1/`). The held-out seed-0 battery is never run here.

**Revision cap: 3.** dev3 is the last revision before registration. Any change to the system prompt, tools or loop after dev3 needs a new decision.

## Revision 1 (dev1)

- Commit `272d8ab61f734363231105dca5776ec0a3b323dd`; prompt `system_prompt_rev1.md`, sha256 `ef1f62c87cf6a3e732aff4f085c66f7ef9a909b3e904859369131e2e7eee139a`.
- Config: qwen3.5:latest (digest `44a38603922e…`), temperature 0, think=False, num_ctx 16384, num_predict 2048, max_turns 8, Modelfile sampler defaults left as-is. `calc_damage` defaulted to gameType Doubles.
- Result: 350 of 350 items ended `final`, none hit max_turns, 1 to 8 turns (303 items took 2). 424 tool calls, 7 `calc_error` (all a species name with the ability appended), 0 invalid tool calls, 0 model errors. 2,291 s wall.
- 40 items were answered with no tool call (typing 11, move_static 11, ability 10, ability_form 5, legality 2, item 1). Checked against the pinned legality blob, 20 of the 40 contained at least one false statement, 3 were non-answers and 17 were correct.
- Other findings: wrong tool for an ability question (`ability_014`), two false KO-chance statements (`damage_002`, `damage_040`), one swapped pair of percentages (`usage_showdown_005`), 24 damage calls that left out the stated ability (results still equalled the key), one invalid weather value accepted by the calc (`damage_030`).

## Revision 2 (dev2)

What changed, and why:

- **Prompt** (`system_prompt.md`): look up before stating species, item, ability, type or move facts, with a tool named per question type; do not state unlooked-up facts, including as background; pass the stated conditions (including the ability) and add none the question did not state; species names never include an ability; a line about `no_lookup_needed`. Why: dev1's 40 no-tool answers, 20 of them with a false statement, and the 7 species-name errors.
- **`no_lookup_needed(reason, category)`** with categories `lookup_not_required`, `conceptual`, `mutation_or_state`, `cannot_answer`. It looks nothing up and exists only to make abstentions visible. The arm still has no mutation tools or team state.
- **First-turn enforcement**: a first model turn with no tool call is rejected once and re-asked to call a lookup tool or `no_lookup_needed`; the rejected text is kept in the record, not shown to the model again. No further nudge.
- **Record**: each answers.jsonl record has a top-level `abstentions` list (reason and category verbatim) and `enforcement` (`reasked`, `rejected_first_turn_text`).
- **`calc_damage`**: returns `rolls_that_ko` (k of 16) and `guaranteed_ko`, both derived from the calc rolls; validates `field.weather` against the calc's weather values and returns a tool error listing them.
- **Unknown-species errors**: the calc error says the name is not a species and suggests a species only when the suffix after a hyphen is one of that species' abilities.
- **Intent**: this change responds to dev1's 40 no-tool answers. No claim-count incentive was intended, and the arm is not being tuned toward zero abstentions. On this lookup-only battery every `no_lookup_needed` call is a miss, but that is a property of the battery, not a target for the product.
- Prompt sha256 (default config): `d230064a68149618dbcb23ec0f6c8fad270925e777bb61e06282a7f394fdc287`.
- Replay variants before any full rerun: A = rev2 prompt without the stub line, no stub tool, no enforcement; B = rev2 prompt with the stub tool and enforcement; C = rev1 prompt with the stub tool and enforcement.

## Replay before dev2 (not a dev run)

- Code: commit `8344920`. Driver and heuristic evaluation are in `diagnostics/` (throwaway, not scorer code). Each variant ran once, temperature 0, think=False.
- Set (50 prompts, from dev1): 40 that dev1 answered with no tool call (typing_001 typing_003 typing_005 typing_007 typing_009 typing_013 typing_017 typing_027 typing_035 typing_039 typing_041 ability_002 ability_007 ability_008 ability_011 ability_015 ability_017 ability_019 ability_027 ability_028 ability_031 ability_form_002 ability_form_006 ability_form_007 ability_form_008 ability_form_011 item_002 legality_003 legality_009 move_static_005 move_static_008 move_static_009 move_static_010 move_static_015 move_static_016 move_static_023 move_static_025 move_static_027 move_static_031 move_static_032) plus 10 tool-backed dev1 items that were correct, the lowest id per type (typing_000 ability_000 ability_form_000 item_000 legality_000 speed_000 damage_000 usage_000 usage_showdown_000 move_static_000).
- Variants: A = rev-2 prompt without the stub line, no stub tool, no enforcement. B = rev-2 prompt, stub tool, first-turn enforcement. C = rev-1 prompt, stub tool, first-turn enforcement. B was chosen by the pre-set rule.
- Transitions against the keys (dev1 heuristic baseline on the 40: 21 false, 18 correct, 1 non-answer; the 10 controls were correct):

  | | A | B | C |
  |---|---|---|---|
  | 40: false to correct | 20 | 21 | 20 |
  | 40: non-answer to correct | 1 | 1 | 1 |
  | 40: stays false | 1 (move_static_023, item tool on a move question) | 0 | 1 (move_static_023, same) |
  | 40: correct to correct | 18 | 18 | 18 |
  | 10 controls: correct to false | 0 | 0 | 0 |
  | 10 controls: correct to non-answer | 1 (speed_000, model_error) | 0 | 0 |
  | no_lookup_needed calls | n/a | 0 | 1 |
  | first turns rejected and re-asked | n/a | 0 | 16 |

- A model_error: variant A, speed_000, Ollama `ResponseError: XML syntax error on line 8: element <function> closed by </parameter> (status code: -1)`. The item ended with no answer; dev1 had none.
- C stub use: ability_008, category `cannot_answer`, reason "The available lookup tools do not include a function to check which moves a species can learn (learnset). The tools available are for typing, abilities, legality checks, move statistics, speed calculations, damage calculations, and usage data, but none provide learnset information." On this battery that is a miss.
- Limits: the replay set is enriched for dev1's failures, and the revision-2 prompt was written after seeing those failures. Single runs on 50 items; the scoring was a heuristic read by hand, and ten of B's previously false answers were read individually.

## Dev2 results (revision 2, `runs/dev2`)

- Commit `9bccbd275c5d6e19feb2e6e06c73ed5fa5bddffd`; prompt sha256 `d230064a68149618dbcb23ec0f6c8fad270925e777bb61e06282a7f394fdc287` (default config B: stub tool plus first-turn enforcement). Launch tree had no modified tracked files; `calc_process.same_worktree` was true.
- Run: 350 of 350 items `final`; 346 took 2 turns and 4 took 3 (damage retries); no max_turns, no model_error, no invalid tool calls; 440 tool calls with 4 errors (3 `calc_error` for an ability appended to a species name, each retried successfully after the suggestion; 1 `bad_arguments` for weather "Drizzle"). Wall 2,158 s.
- Abstentions: 0 items without a real lookup, 0 `no_lookup_needed` calls, 0 enforcement firings (dev1: 40 items with no tool call).
- False asked propositions (2): `ability_006` and `ability_014`, both answered from `check_item_legal` ("not legal as a held item"); keys say the species has the ability.
- Wrong-tool items (5, all ability items): `ability_005` (`check_species_legal` on "Machamp-Libero"), `ability_006`, `ability_009` and `ability_014` (`check_item_legal`) are "Is X legal on Y?" prompts; `ability_011` is "Does Kommo-o have Dragonize?" (`get_typing`). `ability_005`, `_009` and `_011` still reached the key's answer.
- Numeric slips (sentence-level audit, `diagnostics/numeric_audit.py`): `damage_000` ("183 is less than 177"), `damage_002` ("only one roll" KOs; 0 do), `damage_011` ("only the maximum roll" KOs; 0 do), `damage_016` (KO threshold "150 or more"; HP 157), `damage_031` ("32 SP out of 320 max"), `damage_040` (KO threshold "93 or higher"; HP 186), `usage_showdown_005` (two percentages swapped) and `usage_showdown_009` (three percentages shifted to the next row's value). The yes/no answers of all 53 damage items match the key.
- Damage conditions: 12 of 57 calls differed from the prompt: 9 left out the stated ability, 3 appended it to the species name; `damage_030` added weather (`Drizzle`, rejected; then `Rain`, unstated); `damage_039` sent an unstated 32 SP in HP. For 7 of the 12 omitted-ability sides the calc's default ability differs from the stated one (e.g. Bastiodon: Sturdy applied, Soundproof stated); results still equal the key.
- **Dev2 is in-sample with respect to the prompt changes.** Revision 2 was written after reading dev1's failures on the same battery, so dev2 results are not an estimate of out-of-sample behaviour.

## Revision 3 (dev3; the last revision, cap = 3)

- **Response to dev2:** the 5 wrong-tool ability items (2 with a false answer), the roll-count and KO-threshold slips (`damage_000`, `_002`, `_011`, `_016`, `_031`, `_040`), and the shifted usage percentages (`usage_showdown_005`, `_009`). No claim-count incentive was intended, and the arm is not being tuned toward claim counts.
- **Tool:** new `check_species_ability(species, ability)` (returns the boolean, the species' ability list and the source label), described as the tool for "Does S have A?" and "Is A legal on S?". `get_abilities` is kept. `check_item_legal` keeps `legal_as_held_item` false for a name that is not in the snapshot (keys unchanged) and adds a note saying no item with that name exists and which tool to use if the name is an ability, move or species.
- **Prompt** (`system_prompt.md`; `system_prompt_rev2.md` keeps revision 2): ability questions use `check_species_ability`; the number of the 16 rolls that KO is stated only from `rolls_that_ko`, with no KO thresholds or roll counts worked out from the roll list; usage percentages are quoted exactly as returned, row by row. sha256 (default config): `4087d7db7c366eb91be41a22d19cabc096b691022613c48835f988320e628c99`.
- Any change to the prompt, tools or loop after dev3 needs a new decision.

## Replay before dev3 (not a revision): chance-stating damage items

- Items: damage_000 damage_002 damage_011 damage_016 damage_023 damage_029 damage_040 damage_045 (the dev2 answers that stated a chance), one run each at temperature 0 under the revision-3 prompt (hash `4087d7db7c366eb91be41a22d19cabc096b691022613c48835f988320e628c99`): V1 = default `calc_damage` result, V2 = same with `damage_rolls` left out (`damage_range`, `defender_hp`, `rolls_that_ko`, `guaranteed_ko` kept). Code at commit `c5991b6`; driver `diagnostics/replay_damage.py`.
- Every yes/no answer matched the key in both variants (8 of 8), and every stated roll count matched `rolls_that_ko` except V1 `damage_011`.
- False statements against the keys and tool results, read by hand:
  - V1 (5 statements, 4 items): `damage_000` "those dealing 175-183" (175 does not KO HP 177); `damage_002` "the defender has 32 HP, less than half of its full HP" (HP is 217; 32 is SP); `damage_011` "168 or more damage" (HP is 167) and "6 of the 16 rolls reaching KO" (0 do); `damage_016` "lower damage rolls (142-165) would not be sufficient" (165 KOs HP 157).
  - V2 (3 statements, 2 items): `damage_002` the same "32 HP" slip; `damage_040` "at least 94 damage (half of 186) to KO" and "the maximum damage roll is 100, which would KO" (HP is 186, `rolls_that_ko` 0).
- V2 had fewer false statements than V1 on this 8-item set, so the "prefer V1 on a tie" rule does not apply. The set is in-sample (chosen for dev2 failures), single-run, and hand-read; nothing is adopted until Vu decides.
