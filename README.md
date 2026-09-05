# Pokémon Champions VGC team builder

[![tests](https://github.com/vuhcl/pokemon-champions-agents/actions/workflows/tests.yml/badge.svg)](https://github.com/vuhcl/pokemon-champions-agents/actions/workflows/tests.yml)

A verified, tool-grounded recommendation engine for VGC 2026 Regulation M-B doubles team building — current release: **1.0.0**. Recommendations are deterministic and calc-backed; legality, damage calculations, and matchup verification are never LLM-generated. The LLM's role is narrowly scoped to structured intent extraction, never decision-making.

This is not RAG (no embedding or vector retrieval). The agentic steering loop — free-text mid-session edits, compare/defer, claim correction, and revise/repick of locked slots — ships in 1.0.0 on the same verification boundary: the model proposes structured intent; tools decide.

## What it does

- You describe a team direction (rain, Trick Room, …), name an anchor, list what you own, or say `you pick`.
- For each open slot it returns a short list of regulation-legal candidates, each tagged with why it appeared (usage, role compendium, or mechanical coverage) and a confidence label.
- After locking a weather setter, partner candidates can include kit-backed condition beneficiaries (e.g. Swift Swim / Rain Dish under Rain), not only threat-counters.
- You confirm a full set — ability, item, nature, moves, spread — before anything locks. Duplicate items are rejected under Item Clause rather than presented as done.
- Mid-session you can steer in free text: edit a locked slot's nature/item/spread, `compare` options, `defer` a prompt, dispute a stated claim (`claim_correction`), change one attribute on a locked slot (`revise_locked_slot`), or fully re-discover it (`repick_locked_slot`).
- Damage ranges and matchup outcomes come from `@smogon/calc`, not generated text. If calc is down, results are either labeled as static estimates or the turn fails closed — never silently invented.
- Sessions persist in SQLite and resume (`--thread`, or the newest incomplete thread by default).

## Architecture

LangGraph orchestrates a phase-routed state graph: `empty` → `single_locked` → `multi_locked` → `complete`, re-derived from the confirmed lock count on every turn. Closed-set replies (pick a candidate, confirm a build, choose a completion preference) are matched deterministically. Live LLM use is bootstrap intake plus turn-intent / claim_correction structured extraction (both parsers share the same provider/model via `resolve_llm_parsers`); extracted fields are drafts that downstream tools still have to verify.

The tool layer is ordinary structured queries over extracted Champions data (legality, usage, role compendium, teammate/support needs) plus a local HTTP calc service wrapping `@smogon/calc`. Every presented candidate carries `CandidateEvidence` (`basis` + `confidence` + producer). Durable CLI sessions use LangGraph's SQLite checkpointer.

## Interesting engineering decisions

Pulled from the ADR log — each is a real "why X, not Y," not a stack tour.

1. **Legality and damage are tool calls, never model assertions.** Cross-format contamination (SV OU species/items in a Champions team) and unverified speed/damage claims were the observed failure modes that motivated the project. Prompting was already tried and failed; the fix is structural. ([ADR-002](docs/architecture_decisions.md#adr-002-legality-checking-is-a-tool-call-not-a-model-assertion), [ADR-003](docs/architecture_decisions.md#adr-003-mechanical-claims-require-verification-calls))
2. **Champions is its own mod, not "gen 9 minus a banlist."** Species stats inherit gen 9; legality comes from the regulation mod's `formats-data.ts` / `items.ts` and uniform bans in `rulesets.ts`. Looking up the standard dex and subtracting bans would have been the wrong tool. ([ADR-007](docs/architecture_decisions.md#adr-007-regulationlegality-data-source--showdown-teambuilder-data-supplemented-by-other-sources))
3. **Compendium-first need resolution.** Where a Role Compendium category exists (Trick Room setter, weather setter, redirection), candidates are admitted from that catalog before raw legal-learner search, and compendium confidence is the leading sort key — not a tie-break that insertion order was mistakenly assumed to provide. ([ADR-023 amendment 2026-08-08b](docs/architecture_decisions.md#adr-023--amendment-2026-08-08b))
4. **Anchor role and target role are different producers.** What a locked Pokémon *is* (`classify_anchor_role`) and what the open slot *should become* (`_pick_role` → `TargetRoleDecision`) were collapsed into one "role decision" and produced fabricated support needs. Splitting them was a bug fix, not an abstraction preference. ([ADR-024](docs/architecture_decisions.md#adr-024-anchor-role-classification-is-a-separate-producer-from-target-role-decision))
5. **The LLM extracts structured intent; it does not decide.** Bootstrap intake and free-text turn-intent / claim_correction parsing are the live LLM calls. Extracted direction, pool, edit, and correction fields are drafts. Legality, identity, role evidence, ranking, and locks stay deterministic downstream. Failures retain the prior prompt and mutate nothing. ([ADR-027](docs/architecture_decisions.md#adr-027-empty-team-bootstrap--llm-backed-free-form-extraction-behind-a), [ADR-031](docs/architecture_decisions.md#adr-031-full_build_confirmation-redesign--anticipatory-build-edit-options-with))
6. **Calc-unavailable degradation is typed, not a softer ranking.** `estimate_kind` (`verified` / `static`) is a row-level tag that the sort function gates on, so a static row cannot outrank a verified one even if `verified_score` were wrongly left nonzero. `single_locked` may present labeled static estimates; `multi_locked` coverage/SPOF ranking stays fail-closed. ([ADR-029](docs/architecture_decisions.md#adr-029-calc-unavailable-static-fallback--labeled-degraded-discovery-for-single_locked))
7. **A shipped-looking calc-failure "continue" path was reverted.** Under review, continuing `multi_locked` after calc failure presented ordinary-looking usage-backed candidates with none of the honesty markers above — a silent regression against ADR-029, not a labeled policy change. Hard-stop restored; the usability gap remains an open design task. ([ADR-029](docs/architecture_decisions.md#adr-029-calc-unavailable-static-fallback--labeled-degraded-discovery-for-single_locked), [log 2026-08-10](docs/master_project_log.md))
8. **Open-ended reasoning may propose; it may not act until data confirms.** The 1.0 steering loop (edits, compare, claim correction, revise/repick) still verifies each claim against structured data before it can affect ranking, locking, or presentation. ([ADR-021](docs/architecture_decisions.md#adr-021-open-ended-reasoning-must-be-verification-gated-before-affecting-any-decision))
9. **Rule out the plausible explanation before accepting the real one.** A day of `calc_incomplete` failures looked like Electro Shot's Rain charge-turn modeling. That theory was checked and rejected (Ground immunity is weather-independent; every Ground target failed the same way). The real cause was three layers: `@smogon/calc` correctly returning `damage=0` → the handler calling `kochance(err=true)` on zeros → the batch aborting the whole matchup on one bad row. Fixing the handler to treat legitimate zero as success, and replacing an incomplete Status denylist with `flags.v1.json`, closed a structural class of failures — not two named moves. ([ADR-030](docs/architecture_decisions.md#adr-030-legitimate-zero-damage-calc-results-are-successes-not-errors--batch-semantics), [log 2026-08-11](docs/master_project_log.md))
10. **Weather setters ask "who benefits," not only "what do I need."** `query_support_needs` answers the locked anchor's own kit gaps. A Drizzle Pelipper has no Rain *need*, so partners were threat-counters only until `single_locked` inverted present weather `provides` into kit-emitted beneficiaries (Swift Swim, Rain Dish, Electro Shot, …). Same invert deliberately skipped for Tailwind under Reg M-B: Wind Rider / Wind Power exist, but zero legal holders. ([ADR-023 amendment 2026-08-11a](docs/architecture_decisions.md#adr-023--amendment-2026-08-11a))
11. **Reversed a whole feature after debugging its bug, not after a design review.** Masked alternate-core discovery (ADR-038) was built to resolve mega-exclusivity conflicts mid-build. A real transcript bug — replying "keep current core" looped forever — led to fixing the prompt wording, which exposed that the premise was wrong: Reg M-B doubles only enforces Item Clause and Species Clause at team-building time; Mega Evolution exclusivity is an in-battle choice. The flow was reversed cleanly rather than patched. ([ADR-038 Amendment 2026-09-03a](docs/architecture_decisions.md#adr-038--amendment-2026-09-03a--masked-alternate-core-discovery-reversed), [log 2026-09-03](docs/master_project_log.md))
12. **An eval number found a real Spe formula bug.** Mechanical-claim verification agreed on only 8 / 15 (53.3%) Spe checks until root-caused in the vendored `@smogon/calc` Champions path: `effective_spe()` was still using mainline gen math on already-SP inputs, while Champions uses `floor(n*(base+SP+20))` with no level/IVs. Fixed and re-verified at 15 / 15 (100%) on the same sample. ([eval results](docs/eval_results.md), [log 2026-09-04](docs/master_project_log.md))
13. **Disputed claims are corrected fail-closed, not regenerated.** When a user disputes a typed system claim (`claim_correction`), the path verifies against the legality snapshot and either retracts + re-runs with a recovered constraint or reports that the snapshot agrees — it never asks the LLM to rewrite the disputed fact. ([ADR-051](docs/architecture_decisions.md#adr-051-claim_correction--a-standing-pathway-for-retracting-and))
14. **Role-matched candidates get role-aware builds, not the species-wide default.** A screens Klefki admitted for `screens_support` could still be offered a Psych Up / Calm Mind default because resolution read the merged usage map without the need that admitted it. Role-aware synthesis pulls the provisional build toward the matched role's kit instead. ([ADR-053](docs/architecture_decisions.md#adr-053-role-aware-build-synthesis-for-genuinely-multi-role-species))

## Design history

[`docs/architecture_decisions.md`](docs/architecture_decisions.md) and [`docs/master_project_log.md`](docs/master_project_log.md) are the complete, contemporaneous record of every decision, correction, and bug found while building this — unusually complete for a portfolio project, and the right place to evaluate process, not just the snapshot of code.

## Measured eval

Phase-1 numbers are measured and reported in [`docs/eval_results.md`](docs/eval_results.md) — not estimated:

- **Legality-grounding:** 0 / 28 false-legal (0.0%) across 15 scripted graph scenarios, checked against an independent Showdown-source oracle (not a re-read of the production snapshot).
- **Mechanical-claim verification:** Spe formula fidelity was 8 / 15 (53.3%), then 15 / 15 (100%) after the Champions `effective_spe` fix; damage/KO and matchup-cache checks were 100% on their samples.
- **Claude API validation:** harness and 17 scenarios are built and ready; live run deferred solely on Anthropic account credits ([ADR-058](docs/architecture_decisions.md#adr-058-v100-published-with-claude-api-validation-explicitly-deferred)).

## Quick start

CLI flags, LLM/calc setup, session resume, and troubleshooting: **[docs/cli.md](docs/cli.md)**.

```bash
uv sync --extra ollama   # or --extra anthropic
npm install && npm start # calc service, separate terminal
python -m recommender --new
```

A recorded 1.0.0 session (Trick Room / Hatterene → free-text Focus Sash edit → compare → revise_locked_slot Quiet→Sassy → repick → claim_correction retract on a stamped Heliolisk typing claim → `:builds`) is in [`docs/demo/cli-session-1.0.0.txt`](docs/demo/cli-session-1.0.0.txt). The prior 0.2 transcript remains at [`docs/demo/cli-session-0.2.txt`](docs/demo/cli-session-0.2.txt) (Pelipper lock → rain-beneficiary partners including Rain Dish / Swift Swim → Blastoise confirmed). The prior 0.1 transcript remains at [`docs/demo/cli-session-0.1.txt`](docs/demo/cli-session-0.1.txt).

## What shipped in 1.0

- Agentic reasoning / steering loop on the existing verification boundary (LLM extracts intent; tools decide).
- Free-text edits, `compare`, `defer`, `claim_correction`, `revise_locked_slot`, and `repick_locked_slot`.
- Both Phase-1 eval numbers measured (legality-grounding 0% false-legal; mechanical-claim Spe fidelity 100% after a real bug fix).

## Known gaps / what's next

From the 2026-09-04 ship note — deliberately deferred, not forgotten:

- Tier 2 direction-vocabulary / new `TargetRoleId` destinations (Calm Mind, Bulk Up, Dragon Dance, Iron Defense/Body Press, sleep-status-spreader, terrain setters, ability-driven archetypes). Terrain setters prioritized once picked up, given Reg M-C's expected terrain relevance.
- Reg M-C legality-data migration — blocked until Showdown publishes the M-C ruleset; blast radius already mapped.
- Claude API validation — built and ready (`scripts/eval/run_claude_validation.py`); blocked only on Anthropic credits ([ADR-058](docs/architecture_decisions.md#adr-058-v100-published-with-claude-api-validation-explicitly-deferred)).

Out of scope until later phases: Showdown win-rate eval, battle-log/RL piloting.

## Tests

Verified 2026-09-04 against `docs/v1-0-0-readme` at feature commit `2b68b41`:

| Suite | Command | Result |
|-------|---------|--------|
| Python recommender | `uv run pytest` | **1632 passed, 12 skipped** |
| Node calc/extract | `npm test` | **52 passed** (not in CI) |

Skipped (pytest `-rs`): 8 live-calc tests that require a live calc probe / `CALC_LIVE=1`; 4 Ollama bootstrap/turn-intent smokes that require `langchain-ollama` and/or `BOOTSTRAP_OLLAMA_MODEL` in the pytest process.

CI runs `uv run pytest` on push to `main` and on pull requests.

## License

[MIT](LICENSE)
