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

*What to measure: when `TurnIntentExtraction.message` is shown as a `pending_response`
clarification (idle / candidate_selection / completion_preference / full_build_confirmation),
how often does that free text assert a parseable species type/ability fact, and is the fact
true against `data/legality/champions.v1.json`? Separate from mechanical-claim / calc fidelity.*

- Measured: 2026-09-04
- Feature commit: `4771de9`
- Model: Ollama `qwen2.5:7b` (`BOOTSTRAP_OLLAMA_MODEL`); calc `:4173` healthy
- Code under test: **unfixed** `origin/main` tip at branch time (`PendingResponsePayload`
  returns raw `extraction.message`; no `rewrite_pending_response_message`). Runner aborts if
  the rewrite guard is present.
- Runner: `BOOTSTRAP_OLLAMA_MODEL=qwen2.5:7b uv run python scripts/eval/run_species_fact_pending.py`
- Oracle: `scripts/eval/species_fact_oracle.py` — loads `champions.v1.json` directly; does
  **not** import `try_parse_verifiable_claim_from_message` / `claim_is_true_against_snapshot`.
  Hybrid type verdict: slash forms = set-equality; single type = membership. Multi-claim per
  message; negation spans skipped. Artifact:
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
| claim-bearing messages (≥1 parseable claim) | 2 |

### Claim-level counts

| verdict | count |
|---------|------:|
| total parseable claims | 6 |
| TRUE | 4 |
| FALSE | 2 |
| unverifiable_shape | 0 |

Claim-level true rate among parseable claims: **4 / 6 (66.7%)**. False rate: **2 / 6 (33.3%)**.

### Per call site

| call site | elicitation | llm_authored msgs | claim-bearing msgs | claims TRUE | FALSE | unverifiable |
|-----------|-------------|-------------------:|-------------------:|------------:|------:|-------------:|
| idle | organic | 1 | 0 | 0 | 0 | 0 |
| candidate_selection | organic | 4 | 2 | 4 | 2 | 0 |
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

### After-run expectation

Re-run the same runner + scenarios on a tree that includes the runtime rewrite guard; add a
paired **"after, post-guard-fix"** section (or amend this one with an after block). Expect
FALSE assertional type/ability lines in `pending_response.message` to be rewritten before
display; this baseline must stay labeled BASELINE and must not be overwritten.

---

## Species-fact grounding in clarification text (baseline, pre-guard-fix, qwen3.5:latest)

**BASELINE** — second model-axis baseline, paired with the qwen2.5:7b section above. Same
**runner / scenarios / oracle** as that baseline (`scripts/eval/run_species_fact_pending.py`,
`scenarios_species_fact.py`, `species_fact_oracle.py`); **only** `BOOTSTRAP_OLLAMA_MODEL`
differs. Numbers are directly comparable. Do not replace or discard the qwen2.5:7b section.
Pair each with its own "after" re-run once the runtime guard merges.

*What to measure: identical to the qwen2.5:7b baseline — species type/ability facts in
`pending_response` clarification free text vs `data/legality/champions.v1.json`.*

- Measured: 2026-09-04
- Feature commit: *(filled at commit)*
- Model: Ollama `qwen3.5:latest` (`BOOTSTRAP_OLLAMA_MODEL`); calc `:4173` healthy
- Code under test: **unfixed** (no `rewrite_pending_response_message`); runner abort-if-guarded
  preflight passed
- Runner command: `BOOTSTRAP_OLLAMA_MODEL=qwen3.5:latest uv run python scripts/eval/run_species_fact_pending.py`
- Artifact: `scripts/eval/artifacts/species_fact_baseline_qwen35.json`
  (qwen2.5 artifact left at `species_fact_baseline.json`)

### Methodology / model behavior vs qwen2.5:7b (scenarios fixed)

Same Phase 1 graph conversation + Phase 2 targeted gap-fill probes. Honest differences in
how this model used the fixed prompts:

- **Idle over-production:** after `I want a fire type next`, the model looped ~20 turns of the
  same llm_authored clarification asking for a slot number (continue did not escape). Inflates
  idle `pending_response` count vs qwen2.5:7b without adding claims.
- **Claim-bearing phrasing:** Phase 2 `tell me each option's typing…` produced list lines like
  `Heliolisk - Electric/Grass type` (dash/list shape). The shared oracle only scores
  `Species is … type` assertions, so those lines are **unscored** here (not a scenario change).
  One scored FALSE came from a `full_build_confirmation` probe: `Heliolisk is Electric/Grass type`.
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
| claim-bearing messages (≥1 parseable claim) | 1 |

### Claim-level counts

| verdict | count |
|---------|------:|
| total parseable claims | 1 |
| TRUE | 0 |
| FALSE | 1 |
| unverifiable_shape | 0 |

Claim-level true rate among parseable claims: **0 / 1 (0.0%)**. False rate: **1 / 1 (100%)**.

### Per call site

| call site | elicitation | llm_authored msgs | claim-bearing msgs | claims TRUE | FALSE | unverifiable |
|-----------|-------------|-------------------:|-------------------:|------------:|------:|-------------:|
| idle | organic | 25 | 0 | 0 | 0 | 0 |
| candidate_selection | organic | 3 | 0 | 0 | 0 | 0 |
| completion_preference | seeded | 1 | 0 | 0 | 0 | 0 |
| full_build_confirmation | organic | 5 | 1 | 0 | 1 | 0 |

### FALSE claims logged (evidence only — do not expand the guard-fix PR)

1. **Heliolisk is Electric/Grass** (real: Electric/Normal) — Phase 2
   `full_build_confirmation` probe. Wrong dual-type line in the same family as the v1.0.0
   demo Electric/Water case and the qwen2.5:7b baseline's Grass assertion.

### After-run expectation

Re-run **this same model** (`qwen3.5:latest`) with the same runner/scenarios after the
runtime guard merges; add a paired after section. Keep this BASELINE intact beside the
qwen2.5:7b baseline so both before/after pairs demonstrate model-agnostic guard behavior.

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

## Known limitations / honest gaps (update as discovered)
*Mirror the honesty standard set by the VinylIQ RAG-not-shipped story — if something doesn't
work or an eval result is weak, it goes here plainly, not smoothed over.*

- Species-fact clarification baselines (2026-09-04, pre-guard): qwen2.5:7b (2 claim-bearing /
  6 claims, 4 TRUE / 2 FALSE) and qwen3.5:latest (1 claim-bearing / 1 FALSE —
  Heliolisk Electric/Grass). Same runner/scenarios/oracle; model is the only variable. See
  both BASELINE sections above — not post-fix numbers.
-
