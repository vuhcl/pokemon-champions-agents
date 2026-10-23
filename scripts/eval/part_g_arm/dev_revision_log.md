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
