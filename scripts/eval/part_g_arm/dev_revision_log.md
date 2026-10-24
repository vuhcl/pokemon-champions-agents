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

## Dev3a and dev3b (revision 3, `runs/dev3a`, `runs/dev3b`)

- Commit `94de54f6567394cc8755de521cb2a0048ea558a7` for both; prompt sha256 `4087d7db7c366eb91be41a22d19cabc096b691022613c48835f988320e628c99`; stub tool and first-turn enforcement on. dev3a had `damage_rolls_in_result` true (V1), dev3b false (V2). No modified tracked files at launch; `calc_process.same_worktree` true; neither run restarted.
- Both: 350 of 350 `final`; no max_turns, model_error or invalid tool call; 448 tool calls, 6 errors (5 `calc_error` from an ability appended to a species name or in parentheses, 1 `bad_arguments` for weather "Drizzle"); every item made a real lookup; 0 `no_lookup_needed` calls; 1 enforcement firing (`move_static_027`, then `get_move_static`). All 44 ability and ability_form items called `check_species_ability`; all ability answers match the keys in both templates ("Does S have A?" 18 of 18, "Is A legal on S?" 14 of 14). Final calc results equal the key on all 53 damage items in both.
- **V1/V2 decision rule (fixed before the runs, threshold arbitrary):** choose V2 only if V2 has at least 3 fewer damage items with a false numeric statement than V1 across the 53, and no new yes/no verdict errors against the keys; otherwise V1.
- Damage items with a false numeric statement (heuristic audit plus hand adjudication of every flagged sentence and a read of the unflagged numeric sentences):
  - V1 (dev3a), clearly false: damage_000, damage_002, damage_011, damage_016, damage_019, damage_031, damage_049 (7). Off-by-one or half-of-HP thresholds, true under the scorer's roll-list rule but false on a plain reading: damage_005, damage_020, damage_032, damage_047 (4). Heuristic false positives: damage_030, damage_048.
  - V2 (dev3b), clearly false: damage_002, damage_005, damage_040 (3). damage_030 was a heuristic false positive.
  - Yes/no errors against the keys: V1 damage_031 ("every single roll would KO a 32 HP target"); V2 none.
  - Result: V2 has 4 fewer items (clearly-false only) or 8 fewer (with thresholds); no new V2 yes/no error. V2 is chosen under every reading of the rule.
- Caveats on the decision: the V1/V2 replay set was in-sample (chosen from dev2's failures); omitting `damage_rolls` is a product-config choice made partly for the gate, not only for accuracy; it removes surface but did not remove fabrication in the replay or in dev3b (damage_002 "the defender has 32 HP", damage_005 "32 SP out of 608 total HP", damage_040 "at least 94 damage (half of 186)" and "the maximum roll of 100 would KO" are all fabricated arithmetic with no rolls in the result).
- Registration prep (numeric sentences by whether a scorer rule or the data exists): only 2 sentences have no data in key or transcript, both garbled "32 SP out of N total HP" statements (dev3a damage_019, dev3b damage_005). The rest have data but no scorer rule today: speed stats and margins (142 + 38 sentences), damage as percent of HP (60), N-hit KO (HKO) statements (36), stated damage ranges (9), stated defender HP (12), base power (28; covered for the asked value). Rank assertions (232) are covered by the scorer's rank rule.

## After dev3: shipped config, independent read, dev split (2026-10-23)

- **Decision:** V2 (`damage_rolls` omitted from `calc_damage` results) is the shipped config per the pre-set rule in the dev3 entry (V2 had at least 3 fewer damage items with a false numeric statement and no new yes/no error). `ArmConfig.damage_rolls_in_result` now defaults to false explicitly, and `run_params` records it (`arm_config` and `run_time.damage_rolls_in_result`). Commit `e317345`. The rev-3 prompt is unchanged (hash `4087d7db7c366eb91be41a22d19cabc096b691022613c48835f988320e628c99`).
- **Claude's independent read of dev3** (supplied by Vu): V1 (dev3a), 13 damage items with a false numeric statement: 000, 002, 005, 011, 016, 017, 019, 020, 031, 032, 044, 047, 049. V2 (dev3b), 4 items: 002, 005, 024, 040. The read in the dev3 entry above differs by items 017, 044 (V1) and 024 (V2), which that read did not flag; they are re-checked against the audit script below.
- **Known inconsistency:** the rev-3 prompt still tells the model not to work out KO thresholds or roll counts "from the list of rolls", and the shipped config no longer gives the arm a roll list. The prompt is frozen at rev 3, so this stays.
- **Enforcement** fired once in dev3 (`move_static_027`, in both runs).
- **Workflows:** `usage-showdown-rollover.yml` is disabled (Vu, 2026-10-23); `usage-refresh-mc.yml` stays enabled. Neither is touched here.
- **damage_013 (no fix):** in `runs/dev3b` the arm sent ability "Mold Breaker" for Salamence-Mega; the calc replaced it with Aerilate (`ability_resolution.attacker`: applied "Aerilate", source "dex", supplied "Mold Breaker"), and the final text states no ability. The result equals the key.
- **Dev split:** `dev_split.json` (committed, seed 20261024, type-stratified random, P 177 items for parser building, T 173 items for the 50-answer timing sample only; sha256 `a1c8bb7f16d7a451cf838b192d6e3e690cccdf3b3a3d918f5c2345a4bc92dba6`). Not edited later; parsers are built and tuned on P only.

## Scorer, extractors, audit view and judge (2026-10-23, after dev3)

- Scorer rules added from Vu's note: unit slips and labelled values, KO-needed equals HP, roll-list rule for "rolls at or above X", speed stats and margins, damage range, percent of HP, guaranteed/possible nHKO, chance-based nHKO unverifiable on its own line, KO counts and percents tied to an HKO chance, the copied_unchanged sensitivity line (never decides), per-type false rate beside the headline. `--gate-ko-chance` is on by default; `--gate-usage-pct` is off and scores against the item's own tool results.
- Extractors (`scripts/eval/part_g_v4/extractors.py`) were built on dev half P only, from the shipped-config run (`runs/dev3b`), with dev2 text used for the seven annotated P items. They are not frozen. Before the split existed, the dev1, dev2 and dev3 analyses read answers from all 350 items, so the author has seen T answers; no rule was tuned on T after the split.
- Audit view and the exception-log gate: the headline is withheld until the exception log is committed and its sha256 stated.
- Judge: gemma4:12b prompt v3 tuned on Vu's 15 annotated items only (v1, v2, v3 hashes in `judge/README.md`); the 10-item test set has not been released or run.

## Disclosures (2026-10-23)

- **Half T is not unseen.** Before the P/T split existed, the dev1, dev2 and dev3 analyses read the answers of all 350 items, so the author has seen T answers. Since the split no extractor rule was tuned on T. The extractors were run over T for counts only, once alone and once inside an all-items count (identical counts).
- **Scorer rules 1-8 and the 0.1-point percent-of-HP tolerance were set after reading dev answers.** The rules came from Vu's note, which was written after reading dev3; the 0.1 tolerance was chosen because the calc truncates (154/177 = 87.01 shows as 87), which was seen in dev text; the audit patterns were written to flag the dev3 slips.
- **The claim count is dominated by list members and copied values.** On half P (`runs/dev3b`), 41% of the scored claims are list members, 64% are copied_unchanged, and usage items carry about 15 scored claims each (median) against about 1 for typing, item and legality.
- **Gate-unit definition.** The design document defines the gate's denominator as "scored claims the arm actually authors", not designed claim slots, and treats a named member of a set-valued answer not in the key as a false claim; its sizing table assumed about 1 claim per item (usage 2.0). Half P has 626 scored claims against 194 designed slots; that is allowed by the definition and far outside the sizing assumption.

## copied_unchanged redefined (Vu amendment, 2026-10-23 night)

- **Definition** (replaces the verbatim-value definition): a claim is copied_unchanged when the final_text contains the entire text line from the tool result that carries the claim, verbatim after whitespace and case normalisation. The per-tool line definition was written and committed first (`scripts/eval/part_g_v4/copied_unchanged_lines.md`, commit `935080f`), then the extractors were wired to it (`9ad0548`), then the shares were computed. The definition was not widened after the shares were seen.
- **Measured shares** (runs/dev3b, scored claims in the gate unit): half P 167 of 626 (26.7%), half T 160 of 639 (25.0%). By type on P: ability 61%, ability_form 31%, damage 9%, item 0%, legality 0%, move_static 79%, speed 0%, typing 55%, usage 36%, usage_showdown 0%. The earlier 64% (verbatim values) is superseded.
- **What drives the share:** one-word lines. Type and ability names, and in-game teammate names (rendered as the name alone) are lines, so any answer that mentions them contains the line; integers (Speed stats, base power, damage range and HP) are never lines, and percentages only count when the whole `"{name} {pct}"` line appears.
- The extractors were run over half T for counts once more for this recount (third time, counts only; nothing was tuned on T).

## Blind recall check (2026-10-23 night)

20 half-P items (2 per type, seed 20261026, excluding the 7 annotated items), annotated by Claude (Project chat) from prompt and final_text only. Extractors unchanged (commit `3226491`). Recall 92 of 99 units (92.9%; 94 of 99 counting asked-ability list members), 15 of 20 items complete; 7 misses (list phrasing "has two abilities:" and "(along with X and Y)", "OHKO" not read as nHKO = 1, "HP (N)" not read as a stated HP) and one spurious FALSE claim (`usage_015`, a "Note:" line read as a teammate). Report: `blind_recall_report.md`. No change to the extractors or the annotation.

## Extractor fixes after blind recall round 1 (2026-10-23 night)

- **Pre-fix figure (round 1, 20 half-P items, extractors at `3226491`):** 92 of 99 units recovered (92.9% strict; 94 of 99 counting the asked ability as covering its list duplicate). Split by kind: the asked claim 46 of 46; claims the arm added beyond the question 46 of 53 (all seven misses were additions). The 20 round-1 items are burned for recall.
- **Fixes (generic, with unit tests on invented strings):** "has N abilities:" as a list lead; "(along with / together with / as well as / plus / including X and Y)" parenthetical members; "OHKO" read as nHKO = 1 (and `<digit>HKO` unchanged); defender HP stated as "HP (N)"; label lines ("Note:", "Caveat:", "Source:", "Summary", "Warning:", and unmarked "Head: <long text>" lines) are never list entries. Nothing else in the extractors or the scorer changed.
- **Regression check (all 350 dev3b items, extractors before vs after):** 36 items changed, all as intended: new ability-list members (ability_000, 004, 026, 030), `guaranteed 1HKO` claims on guaranteed-OHKO damage answers (25 items), new stated-HP claims (damage_028, 039, 051), and the removal of a spurious `Note` teammate entry in 9 usage items (usage_002, 003, 009, 015, 017, 020, 023, 029, 030). No change from T results was made; T was read for this before/after comparison only.
- **Artifact scan (name-bearing claims whose name is not in the item's tool results; spans read by hand):** before the fix, the 9 `Note:` spans above; after the fix, one claim whose span is a real statement but whose extracted name is malformed: `ability_024`, `ability_list_member` "Intimidate as an ability" (span 136-160 of "...Scrafty-Mega can have Intimidate as an ability."). Not fixed (outside the listed gaps).
- **Known limit, unchanged:** the first sentence of an answer is consumed by the polarity claim, so ability or type lists stated inside it are not extracted.

## Blind recall round 2 (2026-10-23 night)

20 fresh half-P items (seed 20261027), annotated by Claude (Project chat) from dev3b prompt and final_text; export byte-identical to the dev3b records. Extractors at `6a5c2fb`, unchanged for the diff. Strict 92 of 93 units (98.9%), lenient 93 of 93; asked claim 46 of 46, added claims 46 of 47 strict; 19 of 20 items complete (the one strict miss is a restatement of the asked ability in `ability_008`). No spurious claims. Round 1 was 92 of 99 before the fixes; the round-2 items are now burned for recall too. Report: `blind_recall_round2_report.md`.

## After blind recall round 2 (2026-10-23 night)

- **Correction:** the fixes entry above says the new `guaranteed 1HKO` claims appeared on "25 items". The count is 22 (13 on half P, 9 on half T): damage_001, 003, 004, 006, 007, 008, 009, 012, 013, 014, 021, 022, 025, 026, 028, 030, 035, 036, 038, 043, 048, 051. The earlier figure was a miscount.
- **Double counting (not applied):** in those 22 answers the scorer sees three claims about one proposition: `guaranteed_ko yes`, `ko_count 16 of 16 rolls KO` and `nhko guaranteed 1HKO`. `dedupe` keys on (kind, subject, proposition), so they are distinct claims. Smallest deduplication proposed, not applied: map `nhko` "guaranteed 1HKO" to the `guaranteed_ko` "yes" key in `dedupe` (their truth values are identical: min roll at or above HP). `ko_count` 16 of 16 is equivalent too; mapping it as well would leave one claim per answer.
- **Extractor fix:** a trailing "as an ability" / "as one of its abilities" is trimmed from list-member names (`ability_024`); only that item's claims changed.
- **Extended artifact scan (every FALSE or UNVERIFIABLE claim on halves P and T of dev3b):** one artifact, `damage_040`: the span "half of 186" produced a second `ko_needed` claim (93) for one statement ("at least 94 damage (half of 186)"); the arm stated 94, and 93 is the extractor's own halving. Not fixed.
- **Item-level line:** added to the dev-only headline (`item_level`): items with at least one FALSE gated claim over items with at least one scored gated claim, same exact Clopper-Pearson table, per type; printed with the list-members and list-as-one lines under `--show-dev-headline` only.

## Dedupe, half-of-N, comparison and the proportional timing sample (2026-10-23 night)

- **Dedupe (Vu-approved):** `dedupe` now keys `nhko` "guaranteed 1HKO" and `ko_count` "16 of 16 rolls KO" onto the `guaranteed_ko` "yes" key and keeps the `guaranteed_ko` claim, in any order. "12 of 16", other partial counts, chance statements, "possible 1HKO" and a contradictory `guaranteed_ko` "no" are not collapsed. Commit `be71d8a`.
- **half-of-N:** a "half of N" phrase takes the figure the arm stated in the same sentence ("at least 94 damage (half of 186)") and does not compute N/2; with no stated figure it yields the existing needed-damage claim (N/2). "needs half of 186 HP" no longer reads 186 as a stated damage figure.
- **Old vs new over all 350 dev3b items (extractors at `1585728` vs `be71d8a`):** 27 items changed, all by the three causes below; no claim was added and nothing else was removed. 49 claims removed: half P 27 (13 `nhko`, 14 `ko_count`; 14 items), half T 22 (9 `nhko`, 12 `ko_count`, 1 `ko_needed`; 13 items).
  - nhko "guaranteed 1HKO" folded into `guaranteed_ko` yes: 22 claims, 22 items (damage_001, 003, 004, 006, 007, 008, 009, 012, 013, 014, 021, 022, 025, 026, 028, 030, 035, 036, 038, 043, 048, 051).
  - ko_count "16 of 16" folded into `guaranteed_ko` yes: 26 claims, 26 items (damage_001, 003, 004, 006, 007, 008, 009, 012, 013, 014, 015, 018, 021, 022, 025, 026, 028, 030, 035, 036, 038, 042, 043, 048, 051, 052).
  - half-of-N: 1 claim, damage_040.
- **Timing sample:** `timing_sample_T_proportional.json` (seed 20261028, 50 items from half T, proportional by claim type: ability 5, ability_form 2, damage 8, item 6, legality 5, move_static 5, speed 7, typing 6, usage 5, usage_showdown 1). It supersedes `timing_sample_T.json`. Rendered to `runs/timing_practice2/` (untracked) with the headline withheld; the practice CSV is not the audit log.

## Timing-audit rule, canaries, damage sanity export (2026-10-24)

- **Timing practice result (Vu):** 11:50 for 50 answers (14.2 s per answer) on `timing_sample_T_proportional.json`; two `missed_claim` exceptions (ability_018, ability_form_004), both of the form "A is one of X-Mega's abilities". Vu: not gated.
- **ability_plural (non-gating):** for a Mega-form subject whose key lists a single ability, "one of" / "among" its abilities (an owner such as "its", "the" or "X's") yields an `ability_plural` claim on its own line. It is in no denominator, headline, list-as-one line, item-level line or per-type rate; `has_ability` is unaffected; non-Mega subjects and multi-ability keys get no claim; the audit view shows it in a labelled non-gating group. This rule was driven by Vu's timing audit on half T, so it breaks the no-T-tuning discipline for this one rule. Commit `18ec6dc`.
- **Canaries:** `audit_canaries.py` (display-only: 7 wrong_verdict, 7 wrong_extraction, 6 missed_claim, one per item, fixed seed; the list goes to a separate file, only its sha256 and N are printed) and `audit_canary_check.py` (refuses until the exception log is committed and hashed; reports detected, type-matched and the one-sided 95% lower bounds; matched rows leave the real exception counts). Tested on synthetic data only; not run on the timing practice. Commit `5f211d3`. A flipped FALSE-to-TRUE canary displays with an empty reason, which is the one visible difference from a real TRUE claim that could not be avoided without inventing text.
- **Damage sanity export:** `damage_sanity_export.jsonl`, 8 dev3b damage items chosen with seed 20261029 (damage_011, 014, 018, 022, 028, 029, 034, 040): conditions, pinned base stats, move data (pinned and from the calc library), and the calc's own outputs (final stats, stats used, HP, rolls, min/max, description, type effectiveness, STAB). No battery keys beyond calc outputs; nothing compared.

## Canary matcher tightened and the freeze (2026-10-24)

- **Matcher:** `audit_canary_check.py` now detects a canary only when the normalised claim_text contains the canary target as whole tokens; there is no reverse containment ("1" does not match "125", "Fi" does not match "Fire"). Other exception rows on a canary item stay real and are listed. The headless-Chrome dry run (mock audit, synthetic items) was repeated against it and the driver committed (`diagnostics/canary_dry_run.py`, `canary_dry_run_driver.mjs`): 3 of 20 detected, 2 type-matched, 3 real rows left (two of them on canary items, listed). Commit `96a3869`.
- **Dev headline flag:** `--show-dev-headline` now accepts halves P, T and ALL (Vu, 2026-10-24); it still refuses seed 0 and any run whose `run_params.json` hash is not intact, and it prints the gate summary, the label "IN-SAMPLE" and the tolerated false count beside every bound. Commit `99d0a66`.
- **Old vs new claims, all 350 dev3b items, extractors at `18ec6dc` vs the freeze:** 0 items changed (1,462 claims both).
- **Freeze:** `scripts/eval/part_g_v4/FROZEN_MANIFEST.json` lists the path and sha256 of the extractors (with `copied_lines.py` and the copied_unchanged line definition), the scorer, `audit_view.py`, `audit_canaries.py`, `audit_canary_check.py`, `freeze_manifest.py`, `config.py`, `dev_split.json`, the rev-3 system prompt, `run_params.py` and `run_battery.py` (the run-record builders), and the judge prompt, schema/sampler/pinned digest (`extract.py`) and digest record (`README.md`); manifest sha256 `fd2ad4f098650d8cdf8f3b0577cd0a1721240b17cb0a6b3f57fa5b30c2837bcd`. A test fails if a listed file differs from the manifest. Changing a listed file means regenerating the manifest in the same commit and logging it here by item id and rule.

## After the freeze: dev headline and the gated FALSE verdicts (2026-10-24)

- The dev headline was printed for halves P, T and ALL with `--show-dev-headline` (all numbers IN-SAMPLE). Four gated FALSE verdicts on dev3b: damage_002 [T] (`labelled_value` hp=32 vs key 217), damage_005 [T] (hp=608 vs 196), damage_024 [P] (`ko_count` 6 of 10 vs 0 of 16), damage_040 [T] (`ko_needed` 94 vs HP 186). Each was checked against the rule recorded in the ledger; the scorer applied it as recorded in all four. No scorer bug found, so no scorer change and no manifest regeneration.
- Not a scorer bug, noted for Vu: statements with no extracted claim (an extractor recall gap, extractors frozen), e.g. damage_040 "The maximum damage roll is 100, which would KO" (no pattern for "roll X would KO"). Listing script: `diagnostics/false_verdicts.py`.
