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

- Measured: 2026-09-03
- Method: Reran Task A’s 15 scripted scenarios + 2 seeded `compare` extras under a pass-through
  `CalcClient.calculate_batch` logger and `classify_matchup` spy (`scripts/eval/run_mech_claims.py`).
  Calc `/health` was required (healthy). No live LLM.
- Check 1 — Spe formula fidelity (`effective_spe` vs calc `raw.stats.attacker.spe`, scarf=False):
  **8 / 15 (53.3%)**. Mismatches flagged as a real bug (Champions Spe is
  `floor(n*(base+SP+20))` in `@smogon/calc`; `effective_spe` still uses gen9 math). Not folded
  into noise; not fixed in this PR.
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

-
