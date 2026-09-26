# EVAL RESULTS — Pokémon Champions Agentic Team-Building System
## Kept separate from the narrative log so quantitative results don't get buried in prose.
## Populate starting in Phase 2 (Showdown-simulated evaluation). Do not backfill with vibes —
## if a number isn't measured yet, leave the section marked TBD rather than estimating.

---

## Legality-grounding accuracy (Phase 1 — should be measured even before Showdown eval exists)
*What to measure: does the recommender ever suggest a species/item that's actually illegal in the
target regulation? This is directly testable against known regulation data without needing
Showdown simulation at all, and should be the first hard number this project produces.*

- Measured: 2026-09-03
- Test set size: 15 scripted graph scenarios (3 baseline intake + 12 risky-path, 2 each across
  last-resort synthesis / role-aware synthesis / provisional completion / revise_locked_slot /
  repick_locked_slot / team-conditioned builds ADR-056). Masked-core excluded (ADR-038 reversal).
- Pairs checked: 28 locked `(species, item)` pairs
- False-legal rate: **0 / 28 (0.0%)**
- Stalls / non-complete terminals (kept in denominator; not silently dropped):
  - `baseline_intimidate`: hit turn-cap with 0 locked pairs (bootstrap/discovery loop stall)
  - `last_resort_incomplete`: `incomplete_build` (expected fail-closed)
  - `provisional_abandon`: `build_abandoned` (expected)
- Notes: Deterministic harness (`compile_graph` + `MemorySaver` + `classify_pending` patch; no
  live LLM). Independent oracle: fresh Showdown checkout extract of `formats-data.ts` /
  `items.ts` / `rulesets.ts` (+ base pokedex/items) via `scripts/eval/oracle_snapshot.ts` into a
  temp snapshot; eval-only boolean rules in `scripts/eval/oracle.py` (does **not** import
  `recommender.legality.is_species_legal` / `check_set` / `load_snapshot`). Oracle source commit
  `2f5b273925862ac242b419086c1e7a8868b51da1`. Calc service was healthy for the run. Runner:
  `EVAL_ORACLE_SNAPSHOT=… uv run python scripts/eval/run_legality.py`.

---

## Mechanical-claim verification accuracy (Phase 1)
*What to measure: when the agent makes a speed/damage/matchup claim, does it match an actual
calculation? Sample a set of claims, verify each by hand or via calc tool, report agreement rate.*

- Measured: 2026-09-03 (initial); Spe Check 1 re-measured 2026-09-04 after formula fix
- Method: Reran Task A’s 15 scripted scenarios + 2 seeded `compare` extras under a pass-through
  `CalcClient.calculate_batch` logger and `classify_matchup` spy (`scripts/eval/run_mech_claims.py`).
  Calc `/health` was required (healthy). No live LLM.
- Check 1 — Spe formula fidelity (`effective_spe` vs calc `raw.stats.attacker.spe`, scarf=False):
  **was 8 / 15 (53.3%)** on 2026-09-03 (real bug: `effective_spe` used gen9
  `((2*base+31+EV/4)*level)/100+5` with a pseudo-EV step on already-SP inputs; Champions is
  `floor(n*(base+SP+20))` in `@smogon/calc` `calcStatChampions`). **Fixed in PR #187
  (`bc156f1`); now 15 / 15 (100%)** on the same 15-scenario build sample (2026-09-04 re-run).
- Check 2 — damage/KO fidelity on `compare_build_options` lines:
  - (a) template↔logged correlation: **4 / 4 (100%)**
  - (b) fresh identical recalc (headline): **4 / 4 (100%)**
- Check 3 — matchup outcome/severity after `clear_matchup_memo` + identical `classify_matchup`:
  **10109 / 10109 (100%)** unique cache keys. No cache/key collisions observed.
- Check 4 — `turn_economy_note` structural (not user-text): confirmed populated —
  `charge_delayed` (Solar Beam-only Venusaur) and `recharge_vulnerable_lost` (Hyper Beam-only
  Gyarados). Field is not rendered in CLI today.
- Notes: Runner `uv run python scripts/eval/run_mech_claims.py`. Choice Scarf Spe display uses
  `effective_spe(scarf=True)` and is not part of Check 1’s equality rate (calc `raw.stats` omit
  scarf).

---

## Claude API validation (Phase 1 — ADR-013 hosted-backend check)
*What to measure: do the prompt-tuned classifiers (turn_intent / claim_correction path /
full_build_confirmation axis picks) agree with local/mocked fixture expectations when run
against a real Anthropic model via `build_anthropic_turn_intent_parser`?*

- Measured: blocked 2026-09-03 — `ANTHROPIC_API_KEY` unset in the measurement environment
  (fail closed; no mock fallback). Runner and 17 scenarios are in-tree:
  `uv run --extra anthropic python scripts/eval/run_claude_validation.py`
  (also requires `BOOTSTRAP_ANTHROPIC_MODEL`).
- Test set size: 17 parser-only scenarios (8 turn_intent_parser + 4 claim_correction +
  5 full_build_confirmation). No full graph. claim_correction texts chosen so
  `negation_matches_claim` / `_try_deterministic_claim_correction` do not fire.
- Agreement rate (turn_intent_parser): TBD (blocked on live key)
- Agreement rate (claim_correction): TBD (blocked on live key)
- Agreement rate (full_build_confirmation): TBD (blocked on live key)
- Notes: Includes one known-deferred multi-axis bare-number case (`ti_bare_number_multiaxis`,
  ADR-031) — reported separately, not fixed here. Re-run with a live key and fill rates +
  any `divergence_bug_candidate` triage rows.

---

## Species-fact grounding in clarification text (baseline, pre-guard-fix)

**BASELINE** — pair with an "after" re-run once the runtime pending_response fact-guard
(`rewrite_pending_response_message`) merges. Do not treat this section as post-fix.

**Supersedes** the #192 oracle-version numbers for this model: same scenarios/runner and still
pre-guard, but remeasured after expanding `species_fact_oracle.py` phrasing coverage
(separator/paren/possessive/inverse/`a/an …-type Pokémon`, multi-word abilities). Live
transcripts are **not** bit-identical to #192 (model nondeterminism); attribute count changes
to oracle coverage + a fresh run, not to scenario or production-code edits.

*What to measure: when `TurnIntentExtraction.message` is shown as a `pending_response`
clarification (idle / candidate_selection / completion_preference / full_build_confirmation),
how often does that free text assert a parseable species type/ability fact, and is the fact
true against `data/legality/champions.v1.json`? Separate from mechanical-claim / calc fidelity.*

- Measured: 2026-09-04 (remeasure after oracle expand)
- Model: Ollama `qwen2.5:7b` (`BOOTSTRAP_OLLAMA_MODEL`); calc `:4173` healthy
- Code under test: **unfixed** (`PendingResponsePayload` returns raw `extraction.message`; no
  `rewrite_pending_response_message`). Runner aborts if the rewrite guard is present.
- Runner: `BOOTSTRAP_OLLAMA_MODEL=qwen2.5:7b uv run python scripts/eval/run_species_fact_pending.py`
  (scenarios unchanged)
- Oracle: `scripts/eval/species_fact_oracle.py` — loads `champions.v1.json` directly; does
  **not** import `try_parse_verifiable_claim_from_message` / `claim_is_true_against_snapshot`.
  Hybrid type verdict: slash forms = set-equality; single type = membership. Multi-claim per
  message; negation spans skipped. Scores common direct assertions + simple list/glossary
  shapes (not general NLP). Artifact:
  `scripts/eval/artifacts/species_fact_baseline.json`.

### Methodology (elicitation honesty)

1. **Phase 1 — graph conversation (~32 turns):** live `compile_cli_graph` + `handle_line` +
   Ollama turn_intent_parser. Trick Room / Hatterene setup; elicit at each call site; affirm
   builds to progress; `force_completion_preference_prompt` if completion_preference never
   yields llm_authored clarifications.
2. **Phase 2 — targeted gap-fill probes:** same live `parse_turn_intent` (not the
   `classify_pending` mock harness) with rich pending_context after the graph pass — needed
   because graph-only turns rarely produced assertional typing lines on this local model.

**What worked**

- Asking `tell me each option's typing before I choose` during `candidate_selection` (graph +
  probe) produced multi-species assertional lines the independent oracle could score.
- `full_build_confirmation` and `idle` reliably produced llm_authored clarifications, but
  usually questions / re-prompts without parseable species-fact assertions.
- Organic `completion_preference` visits mostly hit canned
  `That action isn't available here.`; llm_authored completion_preference text came from the
  seeded force-prompt path + Phase 2 probe.

**What did not**

- Bare `I want a grass type` often → structured-parse fail (`CLASSIFY_FAIL_USER_MSG`) or
  misroute to `claim_correction` / rejection — not a usable clarification message.
- Phrases that name species+type in a dispute shape frequently classify as `claim_correction`
  (no `pending_response.message`).
- Model often echoes the user question as `message` (no asserted fact).
- `full_build_confirmation` / `idle` / `completion_preference` produced **0** claim-bearing
  messages in this run (attempts recorded; not fabricated).

### Message-level counts

| | count |
|--|------:|
| pending_response total | 14 |
| llm_authored | 9 |
| canned (fail-closed / deterministic) | 5 |
| claim-bearing messages (≥1 parseable claim) | 3 |

### Claim-level counts

| verdict | count |
|---------|------:|
| total parseable claims | 7 |
| TRUE | 4 |
| FALSE | 2 |
| unverifiable_shape | 1 |

Claim-level true rate among parseable claims: **4 / 7 (57.1%)**. False rate: **2 / 7 (28.6%)**.

### Per call site

| call site | elicitation | llm_authored msgs | claim-bearing msgs | claims TRUE | FALSE | unverifiable |
|-----------|-------------|-------------------:|-------------------:|------------:|------:|-------------:|
| idle | organic | 1 | 0 | 0 | 0 | 0 |
| candidate_selection | organic | 4 | 3 | 4 | 2 | 1 |
| completion_preference | seeded | 1 | 0 | 0 | 0 | 0 |
| full_build_confirmation | organic | 3 | 0 | 0 | 0 | 0 |

### FALSE claims logged (evidence only — do not expand the guard-fix PR)

1. **Sinistcha is Dark/Fairy** (real snapshot: Grass/Ghost) — graph `candidate_selection`,
   user `tell me each option's typing before I choose`. Beyond the known Heliolisk case.
2. **Heliolisk is Grass** (real: Electric/Normal) — Phase 2 probe `candidate_selection` with
   Heliolisk/Abomasnow/Whimsicott context. Same failure family as the v1.0.0 demo / ADR-050
   motivation (demo also saw Electric/Water; this run asserted Grass).

TRUE companions in the same messages: Clefable Fairy; Ariados Bug/Poison; Abomasnow Ice;
Whimsicott Fairy (membership / slash rules as documented in the oracle).

### AFTER, post-guard (#196) — qwen2.5:7b

**First after-numbers on main.** Closed #195 never merged, so there were no prior AFTER
figures on `main`. This run measures with the rewrite guard through #196
(`rewrite_pending_response_message` + `iter_verifiable_claims_from_message`). Scenarios and
oracle unchanged; production code unchanged on this branch (harness `--mode after` only).
Live transcripts are **not** bit-identical to #194 (model nondeterminism).

- Measured: 2026-09-06
- Model: Ollama `qwen2.5:7b`; calc `:4173` healthy
- Code under test: **guarded** (`PendingResponsePayload` rewrites via
  `rewrite_pending_response_message`). Runner aborts if rewrite /
  `_payload_for` wiring / `iter_verifiable_claims_from_message` is missing.
- Runner: `BOOTSTRAP_OLLAMA_MODEL=qwen2.5:7b uv run python scripts/eval/run_species_fact_pending.py --mode after`
- Artifact: `scripts/eval/artifacts/species_fact_after.json` (baselines left untouched)

#### Message-level counts

| | count |
|--|------:|
| pending_response total | 13 |
| llm_authored | 8 |
| canned (fail-closed / deterministic) | 5 |
| claim-bearing messages (≥1 parseable claim) | 3 |

#### Claim-level counts

| verdict | count |
|---------|------:|
| total parseable claims | 7 |
| TRUE | 6 |
| FALSE | 0 |
| unverifiable_shape | 1 |

Claim-level true rate among parseable claims: **6 / 7 (85.7%)**. False rate: **0 / 7 (0.0%)**.

#### Per call site

| call site | elicitation | llm_authored msgs | claim-bearing msgs | claims TRUE | FALSE | unverifiable |
|-----------|-------------|-------------------:|-------------------:|------------:|------:|-------------:|
| idle | organic | 1 | 0 | 0 | 0 | 0 |
| candidate_selection | organic | 4 | 3 | 6 | 0 | 1 |
| completion_preference | seeded | 1 | 0 | 0 | 0 | 0 |
| full_build_confirmation | organic | 2 | 0 | 0 | 0 | 0 |

#### Before / after vs #194 baseline (same model)

| | claim-bearing | claims | TRUE | FALSE | unverifiable |
|--|--------------:|-------:|-----:|------:|-------------:|
| BEFORE (#194) | 3 | 7 | 4 | 2 | 1 |
| AFTER (#196) | 3 | 7 | 6 | 0 | 1 |

#### Targeted-case confirmation (locked protocol)

- **Sinistcha / Heliolisk type assertions:** Re-elicited. Corrected spans present
  (`Sinistcha is Grass/Ghost`, `Heliolisk is Electric/Normal`) as TRUE; baseline false forms
  (`Dark/Fairy`, bare `is Grass`) absent as FALSE → **live rewrite confirmed**.
- **Surviving FALSE residual check:** No FALSE displays this run → ADR-051 Amendment
  2026-09-05a mid-sentence prose-prefix shape **not observed** (nothing to classify).

#### FALSE claims logged

None.

---

## Species-fact grounding in clarification text (baseline, pre-guard-fix, qwen3.5:latest)

**BASELINE** — second model-axis baseline, paired with the qwen2.5:7b section above. Same
**runner / scenarios** (`scripts/eval/run_species_fact_pending.py`, `scenarios_species_fact.py`);
shared expanded oracle; **only** `BOOTSTRAP_OLLAMA_MODEL` differs. Do not replace or discard
the qwen2.5:7b section. Pair each with its own "after" re-run once the runtime guard merges.

**Supersedes** the #193 oracle-version numbers for this model: scenarios/runner unchanged and
still pre-guard; remeasured with expanded oracle phrasing (dash/list forms now scored). Live
transcripts are **not** bit-identical to #193; the jump in scored claims is expected because
shapes like `1. Heliolisk - Electric/Grass type` were previously unscored.

*What to measure: identical to the qwen2.5:7b baseline — species type/ability facts in
`pending_response` clarification free text vs `data/legality/champions.v1.json`.*

- Measured: 2026-09-04 (remeasure after oracle expand)
- Model: Ollama `qwen3.5:latest` (`BOOTSTRAP_OLLAMA_MODEL`); calc `:4173` healthy
- Code under test: **unfixed** (no `rewrite_pending_response_message`); runner abort-if-guarded
  preflight passed
- Runner command: `BOOTSTRAP_OLLAMA_MODEL=qwen3.5:latest uv run python scripts/eval/run_species_fact_pending.py`
- Artifact: `scripts/eval/artifacts/species_fact_baseline_qwen35.json`
  (qwen2.5 artifact left at `species_fact_baseline.json`)

### Methodology / model behavior vs qwen2.5:7b (scenarios fixed)

Same Phase 1 graph conversation + Phase 2 targeted gap-fill probes. Honest differences in
how this model used the fixed prompts:

- **Idle over-production:** after `I want a fire type next`, the model looped many turns of the
  same llm_authored clarification asking for a slot number (continue did not escape). Inflates
  idle `pending_response` count vs qwen2.5:7b without adding claims.
- **Claim-bearing phrasing:** Phase 2 `tell me each option's typing…` produced numbered
  dash/list lines (`Heliolisk - Electric/Grass type`, etc.). Expanded oracle now scores those
  shapes (type-first, else ability longest-match, else skip).
- **Exploratory note:** a prior ad-hoc probe on this model saw `Electric/Water`; this fixed
  scenario run asserted `Electric/Grass` instead — same failure family, different wrong dual.
- `completion_preference`: **seeded** via `force_completion_preference_prompt` (same mechanism
  as the qwen2.5 run when organic llm_authored clarifications were insufficient).

### Message-level counts

| | count |
|--|------:|
| pending_response total | 35 |
| llm_authored | 34 |
| canned (fail-closed / deterministic) | 1 |
| claim-bearing messages (≥1 parseable claim) | 3 |

### Claim-level counts

| verdict | count |
|---------|------:|
| total parseable claims | 10 |
| TRUE | 3 |
| FALSE | 4 |
| unverifiable_shape | 3 |

Claim-level true rate among parseable claims: **3 / 10 (30.0%)**. False rate: **4 / 10 (40.0%)**.

### Per call site

| call site | elicitation | llm_authored msgs | claim-bearing msgs | claims TRUE | FALSE | unverifiable |
|-----------|-------------|-------------------:|-------------------:|------------:|------:|-------------:|
| idle | organic | 25 | 0 | 0 | 0 | 0 |
| candidate_selection | organic | 3 | 2 | 3 | 3 | 3 |
| completion_preference | seeded | 1 | 0 | 0 | 0 | 0 |
| full_build_confirmation | organic | 5 | 1 | 0 | 1 | 0 |

### FALSE claims logged (evidence only — do not expand the guard-fix PR)

1. **Heliolisk - Electric/Grass** (real: Electric/Normal) — Phase 2 `candidate_selection`
   numbered list (also Whimsicott Fairy/Fairy FALSE in the same message).
2. **Heliolisk - Electric/Grass** — second Phase 2 `candidate_selection` typing list.
3. **Heliolisk is Electric/Grass type** — Phase 2 `full_build_confirmation` probe.

Same failure family as the v1.0.0 demo Electric/Water case and the qwen2.5:7b baseline's
Grass assertion; dash-list forms are now scored evidence rather than silent misses.

### AFTER, post-guard (#196) — qwen3.5:latest

**First after-numbers on main** for this model-axis (same caveat as the qwen2.5 AFTER:
#195 closed unmerged). Guard through #196; scenarios/oracle unchanged; harness `--mode after`
only. Live transcripts are **not** bit-identical to #194.

- Measured: 2026-09-06
- Model: Ollama `qwen3.5:latest`; calc `:4173` healthy
- Code under test: **guarded** (same abort-if-unguarded preflight as the qwen2.5 AFTER)
- Runner: `BOOTSTRAP_OLLAMA_MODEL=qwen3.5:latest uv run python scripts/eval/run_species_fact_pending.py --mode after`
- Artifact: `scripts/eval/artifacts/species_fact_after_qwen35.json`
  (qwen2.5 after left at `species_fact_after.json`; baselines untouched)

#### Message-level counts

| | count |
|--|------:|
| pending_response total | 35 |
| llm_authored | 34 |
| canned (fail-closed / deterministic) | 1 |
| claim-bearing messages (≥1 parseable claim) | 3 |

#### Claim-level counts

| verdict | count |
|---------|------:|
| total parseable claims | 10 |
| TRUE | 7 |
| FALSE | 0 |
| unverifiable_shape | 3 |

Claim-level true rate among parseable claims: **7 / 10 (70.0%)**. False rate: **0 / 10 (0.0%)**.

#### Per call site

| call site | elicitation | llm_authored msgs | claim-bearing msgs | claims TRUE | FALSE | unverifiable |
|-----------|-------------|-------------------:|-------------------:|------------:|------:|-------------:|
| idle | organic | 25 | 0 | 0 | 0 | 0 |
| candidate_selection | organic | 3 | 2 | 6 | 0 | 3 |
| completion_preference | seeded | 1 | 0 | 0 | 0 | 0 |
| full_build_confirmation | organic | 5 | 1 | 1 | 0 | 0 |

#### Before / after vs #194 baseline (same model)

| | claim-bearing | claims | TRUE | FALSE | unverifiable |
|--|--------------:|-------:|-----:|------:|-------------:|
| BEFORE (#194) | 3 | 10 | 3 | 4 | 3 |
| AFTER (#196) | 3 | 10 | 7 | 0 | 3 |

#### Targeted-case confirmation (locked protocol)

- **Dash/list + parenthetical typing lists:** Re-elicited. Numbered dash forms scored
  (`Heliolisk - Electric/Normal type`, `Abomasnow - Ice/Grass type`,
  `Whimsicott - Grass/Fairy type`, plus a second list with `Grass/Ice` / `Fairy/Grass`
  orderings) as TRUE after rewrite; baseline FALSE duals (`Electric/Grass`,
  `Fairy/Fairy`) absent as FALSE. Parenthetical aside on Whimsicott in one message was not
  scored as a separate FALSE claim this run. → **live multi-claim rewrite confirmed**.
- **Surviving FALSE residual check:** No FALSE displays this run → ADR-051 Amendment
  2026-09-05a mid-sentence prose-prefix shape **not observed**.

#### FALSE claims logged

None. Unverifiable companions were generic `grass type request` spans (not species+type
assertions).

---

## Bootstrap tiered fallback (Part 2C — Layer 1 census + Layer 2 named)

*Layer 1: 35 `became_legal` ids via `discover_bootstrap_directions` (shipped hardcode
`regulation=champions-reg-mb` unchanged). Layer 2: named harness under `VGC_MC` via
`bootstrap_once_and_stop`, extended through select → `full_slot_confirmed` for NN CLEAN.*

- Measured: 2026-09-14
- Repo HEAD: `f6a7ee0a9b5d6cfd2e012d5a125575c6f9e88aeb`
- Runner: `uv run python scripts/eval/run_bootstrap_tiers.py`
- Layer 1: **N=31** (35 − 4 pre_tier) → **tier1=3/31**, **tier2=6/31**, **tier3=22/31**
  - pre_tier (4): Arboliva, Indeedee, Indeedee-F, Rillaboom (`target_role_from_strategic_evidence`)
  - tier1 (3): Baxcalibur, Baxcalibur-Mega, Pawmot (`bootstrap_kit_role_policy`)
  - tier2 (6): Absol-Mega-Z, Persian, Sirfetch’d, Swalot, Toxtricity, Toxtricity-Low-Key (`bootstrap_movepool_family_nn`)
- Layer 2 named: **14 / 14 PASS** (selectability through lock, not presentation-only)
  - Writeup: Baxcalibur, Pawmot, Baxcalibur-Mega (accept → provisional disclosure)
  - NN CLEAN (6): Absol-Mega-Z / Sirfetch’d / Swalot → `swords_dance_attacker`; Persian / Toxtricity / Toxtricity-Low-Key → `fast_pivot` — each **discover → select → refine → lock**; confirmation shows `similar to` provenance
  - THIN_REF: Gogoat, Grapploct → `fail_closed`
  - HARD_MULTI: Cinderace, Salamence → `fail_closed`
  - Fail-closed msg: Mabosstiff includes `_direction_phrase_examples`; no `standard_`
- Claim upgrade vs prior 13/13: earlier PASS only verified role presentation at `candidates_ready`. This run hard-fails if any NN CLEAN candidate cannot lock.
- Artifact: `.cache/eval/last_bootstrap_tiers_run.json`

---

## Showdown-simulated win rate (Phase 2)
*Primary quantitative eval, once built. Recommended teams played against a defined set of known
meta teams via Pokémon Showdown's simulator/API.*

- Format tested: TBD (BSS Reg M-B or VGC 2026 Reg M-B — see ADR-005)
- Opponent team source: TBD
- Number of simulated games: TBD
- Win rate: TBD
- Comparison baseline (e.g., a naive/random-legal team, or a popular sample team): TBD
- Notes:

---

## RL-policy divergence (Phase 3 — stretch goal)
*Once the battle log parser and new RL policy exist: for actual played battles, how often and
in what ways does the human-piloted line diverge from what the policy would have done, and is
that divergence flagged with an honest confidence level rather than treated as uniformly
significant?*

- Battles analyzed: TBD
- Divergence rate: TBD
- Notes:

---

## Bare-LLM baseline (no tools) — comparison axis
*What to measure: a bare LLM (no LangGraph / no tool access) on VGC 2026 Reg M-C doubles
team-building, scored against the same oracles Phase 1 grounded evals use (legality
`oracle.py` + fresh Showdown snapshot; species-fact oracle incl. move learnability;
`@smogon/calc` for mechanical claims), plus structural EV-vs-SP and Item Clause counts.
Sits beside grounded rates — not folded into them. Interview framing: measured evidence
for ADR-002/ADR-003 (“why grounding matters”).*

**Two conditions — report as distinct rows; never average or merge into one number.**

| Condition id | Label | Elicitation |
|--------------|-------|-------------|
| `chat` | ungrounded chat baseline | One open-ended whole-team ask (real-user chat shape). Not a CLI mirror. |
| `slot` | ungrounded, matched decomposition | Theme → species → full set, six slots — mirrors CLI decomposition, still no tools. |

- Measured: **slot** and **chat** filled 2026-09-25 (5 runs × 2 models each).
- Models: `qwen2.5:7b`, `qwen3.5:latest` (Claude out of scope — ADR-058)
- Runs per model × condition: 5 (temperature 0.7); soft mech nudge at most once if ≥4 slots
  and zero organic speed/damage claims
- Runner:
  `BOOTSTRAP_OLLAMA_MODEL=… uv run python scripts/eval/run_bare_llm_baseline.py --condition chat|slot|both`
- Artifacts (expected, one file per condition × model — do not combine):
  - `scripts/eval/artifacts/bare_llm_chat_qwen25.json` / `bare_llm_chat_qwen35.json`
  - `scripts/eval/artifacts/bare_llm_slot_qwen25.json` / `bare_llm_slot_qwen35.json`
- Results table (fill after measurement; one row per condition × model):

| Condition | Model | false-legal | false-illegal | species TRUE/FALSE/unv | mech TRUE/FALSE/unv | EV-shaped spreads | Item Clause viol. | completed teams |
|-----------|-------|-------------|----------------|------------------------|---------------------|-------------------|-------------------|-----------------|
| chat (ungrounded chat baseline) | qwen2.5:7b | 1/3 | 0 | 1/3/8 | 0/0/0 | 1 | 0 | 0/5 |
| chat (ungrounded chat baseline) | qwen3.5:latest | 2/2 | 0 | 2/0/2 | 0/0/4 | 2 | 0 | 0/5 |
| slot (ungrounded, matched decomposition) | qwen2.5:7b | 13/22 | 0 | 33/29/64 | 0/0/5 | 12 | 3 | 4/5 |
| slot (ungrounded, matched decomposition) | qwen3.5:latest | 12/22 | 0 | 35/16/67 | 0/0/27 | 16 | 3 | 3/5 |

- Notes: Same oracles as grounded Phase 1; elicitation differs from the scripted LangGraph
  harness. `chat` and `slot` answer different fairness questions — cite the matching row.
  ADR/log draft can proceed from these numbers.
  - **false-legal** cells are `false_legal / pairs_checked` (species@item pairs extracted).
  - **Mega + non-stone = false-legal:** a paste like `Lucario (Mega Evolution) @ Leftovers`
    is scored illegal; correct teambuilder form is `Lucario @ Lucarionite` (stone enables Mega).
    Uses `item_mega_forme` against the legality snapshot — not an LLM check.
  - **qwen3.5 invoke:** Ollama `think: false` so content is not empty (thinking otherwise
    consumes `num_predict` and yields blank ASSISTANT turns). Same prompt/steering as qwen2.5.
  - **chat completion is weak:** open-ended chat rarely yields a full extractable 6 (0/5
    completed both models). qwen3.5 often premise-pushes (“Reg M-C doesn’t exist”); harness
    sends one chat-shaped push for sets if the first reply has zero extractable slots, then
    at most 4 continuers. Slot’s Showdown steering is what makes pairs_checked large.
  - Slot Item Clause viol. counted only on completed 6-slot teams.
  - **Mech Spe/KO gate (2026-09-25 rescore on saved transcripts):** entities that are
    not known species ids in the legality snapshot score `unverifiable_shape` (was falling
    through to FALSE via `effective_spe` on sentence fragments). Audit: **0** genuine
    Spe/KO claims with both sides known species in either slot artifact (chat likewise:
    no both-known pairs). Before→after mechanical tallies — slot qwen2.5 `0/5/0` → `0/0/5`;
    slot qwen3.5 `2/18/7` → `0/0/27`; chat qwen2.5 unchanged `0/0/0`; chat qwen3.5
    `0/4/0` → `0/0/4`. Artifacts record `mech_rescore` with the same delta.

---

## Multi-turn steering correctness (Phase 1 — failure mode #5 regression)
*What to measure: over a scripted multi-turn conversation, do locks / rejections /
superseded entries / pending_flags / defer routing match the documented steering
contracts (persistence, contradiction handling), asserted after every turn?*

- Measured: 2026-09-25 (remeasured after constraint-vs-constraint axis supersede)
- Test set size: 12 scripted scenarios
- Pass rate: **12 / 12**
- Runner: `uv run python scripts/eval/run_steering.py` (real `compile_graph` +
  `MemorySaver` / SQLite for #12 + `classify_pending` monkeypatch; no live LLM)
- Notes: State-machine correctness only — not LLM parsing, legality, or mechanical
  fidelity. Scenario #09 exercises constraint→lock reconcile (ADR-020 trigger #1).
  Scenario #10 exercises hard constraint axis supersede (newest wins),
  `restore_constraint` true-swap, soft no-op, and ability-axis replacement.

| ID | Result | Checks |
|----|--------|--------|
| `01_lock_persists` | pass | Lock survives 5 unrelated fills |
| `02_reject_lineage` | pass | Locked reject keeps lock; rejected species filtered on rediscovery |
| `03_sibling_supersede` | pass | Conflicting sibling lock reopens prior + restorable superseded |
| `04_simultaneous_vivillon` | pass | Batch Vivillon Scarf+Sleep Powder: partial commit + pending_flags |
| `05_archetype_reconcile` | pass | Archetype change reopens only theme-mismatched locks |
| `06_reset_preserves_rejected` | pass | Reset clears provisional / old pending; rejected history survives |
| `07_restore_one_level` | pass | Second restore is a no-op (one-level undo only) |
| `08_defer_pending_kinds` | pass | Defer → deferred (candidate/completion) / build_abandoned (full_build) |
| `09_constraint_reconcile` | pass | no_dup leaves species lock; conflicting type constraint supersedes it |
| `10_constraint_axis_supersede` | pass | Hard type axis supersede + restore swap; soft no-op; ability axis |
| `11_idle_persist` | pass | Lock persists across continue/idle rediscovery turns |
| `12_sqlite_mid_contradiction` | pass | SQLite close/reopen mid-supersede sequence then restore |

---

## Tool-call observability (Phase 1 — measured latency / retry from #224 JSONL)
*What to measure: with structured tool-call logging on (`recommender/tool_log.py` →
`RECOMMENDER_TOOL_LOG`), what are real per-tool call counts, mean/p95 latency, failures,
and retries under the existing scripted eval harnesses?*

- Measured: 2026-09-25
- Schema (shipped, matches proposal): `ts`, `tool`, `args`, `latency_ms`, `ok`, `retries`;
  optional `error` when `ok=false`
- Runners (calc `:4173` healthy; no live LLM; from repo root):
  - `RECOMMENDER_TOOL_LOG=scripts/eval/artifacts/tool_calls_mech_claims.jsonl uv run python scripts/eval/run_mech_claims.py`
  - `RECOMMENDER_TOOL_LOG=scripts/eval/artifacts/tool_calls_legality.jsonl uv run python scripts/eval/run_legality.py`
  - `RECOMMENDER_TOOL_LOG=scripts/eval/artifacts/tool_calls_steering.jsonl uv run python scripts/eval/run_steering.py`
- Aggregator: `uv run python scripts/eval/aggregate_tool_log.py` on the three JSONL paths
- Artifacts:
  - `scripts/eval/artifacts/tool_calls_mech_claims.jsonl` (34962 lines)
  - `scripts/eval/artifacts/tool_calls_legality.jsonl` (23436 lines)
  - `scripts/eval/artifacts/tool_calls_steering.jsonl` (4 lines)
  - `scripts/eval/artifacts/tool_calls_aggregate.json`
- Heavier-weight complement (not from these suites): #224 Step 1 wall-clock for
  `query_threat_counters` (ADR-022 defaults, cold matchup-memo) — Incineroar ~303ms,
  Rillaboom ~630ms.
- Coverage note: deterministic scripted harnesses only. **Retries observed: 0** across all
  three suites (nothing actually retried). Live-fetch *did* fire (`fetch_json` /
  `fetch_live_showdown_detail` via M-C→M-B `regulation_lookup_chain` into `_LIVE_FORMATS`),
  but every live call succeeded on the first attempt (`retries=0`, `ok=true`). Steering
  (`calc_degraded=True`) produced no `CalcClient.*` lines — only two live-fetch pairs.
  This reflects the eval harness’s calc/live-call pattern, **not** real user-session
  tool-call distribution or stress under flaky network.

### Suite: `mech_claims` (15 Part 1 scenarios + compare extras)

| tool | count | mean_ms | p95_ms | fail | fail_rate | retries |
|------|------:|--------:|-------:|-----:|----------:|--------:|
| `CalcClient.POST /calculate/batch` | 34930 | 0.682 | 2.151 | 0 | 0.0 | 0 |
| `fetch_json` | 16 | 215.029 | 1615.611 | 0 | 0.0 | 0 |
| `fetch_live_showdown_detail` | 16 | 215.438 | 1615.992 | 0 | 0.0 | 0 |

### Suite: `legality` (15 Part 1 scenarios, calc healthy)

| tool | count | mean_ms | p95_ms | fail | fail_rate | retries |
|------|------:|--------:|-------:|-----:|----------:|--------:|
| `CalcClient.POST /calculate/batch` | 23404 | 0.615 | 2.066 | 0 | 0.0 | 0 |
| `fetch_json` | 16 | 152.632 | 647.302 | 0 | 0.0 | 0 |
| `fetch_live_showdown_detail` | 16 | 152.905 | 647.929 | 0 | 0.0 | 0 |

### Suite: `steering` (12 scenarios, `calc_degraded=True`)

| tool | count | mean_ms | p95_ms | fail | fail_rate | retries |
|------|------:|--------:|-------:|-----:|----------:|--------:|
| `fetch_json` | 2 | 255.195 | 319.28 | 0 | 0.0 | 0 |
| `fetch_live_showdown_detail` | 2 | 255.982 | 320.182 | 0 | 0.0 | 0 |

---

## LLM-call / turn-level observability
*What to measure: with LLM invokes logged through the same `tool_log` JSONL as calc/live-fetch
(`invoke_with_timeout` → `log_tool_call`, correlated by `(thread_id, turn)`), what are real
per-turn LLM latency and token costs on a live-Ollama graph session?*

- Measured: 2026-09-25
- Model / provider: `qwen2.5:7b` via Ollama (`POKEMON_CHAMPIONS_LLM_PROVIDER=ollama`)
- Runner (calc `:4173` healthy; live LLM; from repo root):
  ```bash
  RECOMMENDER_TOOL_LOG=scripts/eval/artifacts/tool_calls_species_fact_llm.jsonl \
  BOOTSTRAP_OLLAMA_MODEL=qwen2.5:7b \
  uv run python scripts/eval/run_species_fact_pending.py --mode after
  uv run python scripts/eval/aggregate_tool_log.py \
    scripts/eval/artifacts/tool_calls_species_fact_llm.jsonl \
    --out-json scripts/eval/artifacts/tool_calls_species_fact_llm_aggregate.json
  ```
- Schema extensions (optional fields when present): `thread_id`, `turn`, and for LLM lines
  `provider`, `prompt_tokens`, `completion_tokens` (from LangChain `usage_metadata` on
  `include_raw` responses; null/omitted if missing)
- Artifacts:
  - `scripts/eval/artifacts/tool_calls_species_fact_llm.jsonl` (4718 lines)
  - `scripts/eval/artifacts/tool_calls_species_fact_llm_aggregate.json`
- Per-tool (same suite):

| tool | count | mean_ms | p95_ms | fail | fail_rate | retries |
|------|------:|--------:|-------:|-----:|----------:|--------:|
| `CalcClient.POST /calculate/batch` | 4692 | 0.555 | 0.905 | 0 | 0.0 | 0 |
| `llm.bootstrap_intake` | 1 | 1016.245 | 1016.245 | 0 | 0.0 | 0 |
| `llm.turn_intent` | 25 | 809.212 | 1608.371 | 0 | 0.0 | 0 |

- Turn rollup summary (32 correlated turns; 26 with ≥1 LLM call, 6 tool-only):
  - LLM turns: mean total_ms **817.2**, p95 **1576.5**; mean prompt_tokens **1869.3**,
    mean completion_tokens **32.3**; session totals prompt **48603** / completion **839**
  - Tool-only turns: mean total_ms **434.3** (dominated by batch calc volume, not per-call cost)
  - In this harness, **no turn had both an LLM call and calc/tool calls** — gap-fill /
    bootstrap turns are LLM-only (`pending_response` / intake); lock/select turns are
    tool-heavy without an LLM. Turn rollup still correctly attributes each bucket; it does
    not prove a mixed “LLM then calc in the same user turn” path under these scenarios.
- Coverage note: scripted species-fact probe (~32 graph turns + Phase 2 gap-fill probes on
  the same thread), **not** a long realistic chat. Ollama `qwen2.5:7b` only for this first
  measurement (Anthropic path not run). Phase 2 probes are parser-only (no tools in-bucket).
  Correlation uses ContextVar + `threading.local` fallback because LangGraph may reset
  ContextVars per node.

---

## Known limitations / honest gaps (update as discovered)
*Mirror the honesty standard set by the VinylIQ RAG-not-shipped story — if something doesn't
work or an eval result is weak, it goes here plainly, not smoothed over.*

- ADR-010 Amendment 2026-08-11a text says defer on `candidate_selection`,
  `completion_preference`, and `full_build_confirmation` all emit `turn_intent="deferred"`.
  Shipped behavior (and existing tests): full_build defer emits `build_abandoned` and
  rediscovers; only the first two emit `deferred`. Steering eval #08 asserts shipped
  behavior; amendment draft for the Claude Project should note the intentional divergence.
- Species-fact clarification baselines (2026-09-04 remeasure, pre-guard, expanded oracle):
  qwen2.5:7b (3 claim-bearing / 7 claims, 4 TRUE / 2 FALSE / 1 unverifiable) and
  qwen3.5:latest (3 claim-bearing / 10 claims, 3 TRUE / 4 FALSE / 3 unverifiable — includes
  previously unscored dash/list Heliolisk Electric/Grass). Same runner/scenarios; model is the
  only variable between the two sections. Supersedes #192/#193 oracle-version counts.
- Species-fact AFTER, post-guard #196 (2026-09-06, first after-numbers on main; #195 closed
  unmerged): qwen2.5:7b 3 claim-bearing / 7 claims → 6 TRUE / 0 FALSE / 1 unverifiable;
  qwen3.5:latest 3 claim-bearing / 10 claims → 7 TRUE / 0 FALSE / 3 unverifiable. Targeted
  #195 shapes re-elicited and scored TRUE (live rewrite confirmed on both models). No
  surviving FALSE this run — ADR-051 Amendment 2026-09-05a mid-sentence prose-prefix residual
  not observed (still a known under-match, not disproven). Unverifiable spans remain
  (generic type-option / “grass type request” phrasing).
-
