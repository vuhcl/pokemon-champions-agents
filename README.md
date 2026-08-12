# Pokémon Champions VGC team builder

[![tests](https://github.com/vuhcl/pokemon-champions-agents/actions/workflows/tests.yml/badge.svg)](https://github.com/vuhcl/pokemon-champions-agents/actions/workflows/tests.yml)

A verified, tool-grounded recommendation engine for VGC 2026 Regulation M-B doubles team building — current release: **0.1**. Recommendations are deterministic and calc-backed; legality, damage calculations, and matchup verification are never LLM-generated. The LLM's role is narrowly scoped to structured intent extraction, never decision-making.

This is not RAG (no embedding or vector retrieval). It is not yet agentic in the sense of multi-turn reasoning or revision-on-feedback — that loop is the labeled path to 1.0, not part of this checkpoint.

## What it does

- You describe a team direction (rain, Trick Room, …), name an anchor, list what you own, or say `you pick`.
- For each open slot it returns a short list of regulation-legal candidates, each tagged with why it appeared (usage, role compendium, or mechanical coverage) and a confidence label.
- You confirm a full set — ability, item, nature, moves, spread — before anything locks. Duplicate items are rejected under Item Clause rather than presented as done.
- Damage ranges and matchup outcomes come from `@smogon/calc`, not generated text. If calc is down, results are either labeled as static estimates or the turn fails closed — never silently invented.
- Sessions persist in SQLite and resume (`--thread`, or the newest incomplete thread by default).

## Architecture

LangGraph orchestrates a phase-routed state graph: `empty` → `single_locked` → `multi_locked` → `complete`, re-derived from the confirmed lock count on every turn. Closed-set replies (pick a candidate, confirm a build, choose a completion preference) are matched deterministically; the only live LLM call is empty-team bootstrap intake, which extracts a draft payload that downstream tools still have to verify.

The tool layer is ordinary structured queries over extracted Champions data (legality, usage, role compendium, teammate/support needs) plus a local HTTP calc service wrapping `@smogon/calc`. Every presented candidate carries `CandidateEvidence` (`basis` + `confidence` + producer). Durable CLI sessions use LangGraph's SQLite checkpointer.

## Interesting engineering decisions

Pulled from the ADR log — each is a real "why X, not Y," not a stack tour.

1. **Legality and damage are tool calls, never model assertions.** Cross-format contamination (SV OU species/items in a Champions team) and unverified speed/damage claims were the observed failure modes that motivated the project. Prompting was already tried and failed; the fix is structural. ([ADR-002](docs/architecture_decisions.md#adr-002-legality-checking-is-a-tool-call-not-a-model-assertion), [ADR-003](docs/architecture_decisions.md#adr-003-mechanical-claims-require-verification-calls))
2. **Champions is its own mod, not "gen 9 minus a banlist."** Species stats inherit gen 9; legality comes from the regulation mod's `formats-data.ts` / `items.ts` and uniform bans in `rulesets.ts`. Looking up the standard dex and subtracting bans would have been the wrong tool. ([ADR-007](docs/architecture_decisions.md#adr-007-regulationlegality-data-source--showdown-teambuilder-data-supplemented-by-other-sources))
3. **Compendium-first need resolution.** Where a Role Compendium category exists (Trick Room setter, weather setter, redirection), candidates are admitted from that catalog before raw legal-learner search, and compendium confidence is the leading sort key — not a tie-break that insertion order was mistakenly assumed to provide. ([ADR-023 amendment 2026-08-08b](docs/architecture_decisions.md#adr-023--amendment-2026-08-08b))
4. **Anchor role and target role are different producers.** What a locked Pokémon *is* (`classify_anchor_role`) and what the open slot *should become* (`_pick_role` → `TargetRoleDecision`) were collapsed into one "role decision" and produced fabricated support needs. Splitting them was a bug fix, not an abstraction preference. ([ADR-024](docs/architecture_decisions.md#adr-024-anchor-role-classification-is-a-separate-producer-from-target-role-decision))
5. **The LLM extracts structured intent; it does not decide.** Bootstrap intake is the graph's only live LLM call. Extracted direction/pool/anchor fields are drafts. Legality, identity, role evidence, and ranking stay deterministic downstream. Failures retain the intake prompt and mutate nothing. ([ADR-027](docs/architecture_decisions.md#adr-027-empty-team-bootstrap--llm-backed-free-form-extraction-behind-a))
6. **Calc-unavailable degradation is typed, not a softer ranking.** `estimate_kind` (`verified` / `static`) is a row-level tag that the sort function gates on, so a static row cannot outrank a verified one even if `verified_score` were wrongly left nonzero. `single_locked` may present labeled static estimates; `multi_locked` coverage/SPOF ranking stays fail-closed. ([ADR-029](docs/architecture_decisions.md#adr-029-calc-unavailable-static-fallback--labeled-degraded-discovery-for-single_locked))
7. **A shipped-looking calc-failure "continue" path was reverted.** Under review, continuing `multi_locked` after calc failure presented ordinary-looking usage-backed candidates with none of the honesty markers above — a silent regression against ADR-029, not a labeled policy change. Hard-stop restored; the usability gap remains an open design task. ([ADR-029](docs/architecture_decisions.md#adr-029-calc-unavailable-static-fallback--labeled-degraded-discovery-for-single_locked), [log 2026-08-10](docs/master_project_log.md))
8. **Open-ended reasoning may propose; it may not act until data confirms.** Any future judgment step (including the 1.0 reasoning loop) has to verify each claim against structured data before it can affect ranking, locking, or presentation. ([ADR-021](docs/architecture_decisions.md#adr-021-open-ended-reasoning-must-be-verification-gated-before-affecting-any-decision))

## Design history

[`docs/architecture_decisions.md`](docs/architecture_decisions.md) and [`docs/master_project_log.md`](docs/master_project_log.md) are the complete, contemporaneous record of every decision, correction, and bug found while building this — unusually complete for a portfolio project, and the right place to evaluate process, not just the snapshot of code.

## Quick start

CLI flags, LLM/calc setup, session resume, and troubleshooting: **[docs/cli.md](docs/cli.md)**.

```bash
uv sync --extra ollama   # or --extra anthropic
npm install && npm start # calc service, separate terminal
python -m recommender --new
```

A recorded 0.1 session (bootstrap → two confirmed locks → next-slot candidates) is in [`docs/demo/cli-session-0.1.txt`](docs/demo/cli-session-0.1.txt).

## Roadmap toward 1.0 (not in this checkpoint)

The original MVP floor includes an agentic reasoning loop — steering and revision-on-feedback — sitting on the same verification boundary this checkpoint already enforces (ADR-027: LLM extracts intent; tools decide). That loop is not started.

Smaller gaps still open in 0.1:

- Canonical name/form resolution at the input boundary (Maushold, Vivillon, and similar).

Out of scope until 1.0 exists: Showdown win-rate eval, battle-log/RL piloting.

## Tests

Verified 2026-08-11 against `main` at `99491aa` (merge of PR #63), not recalled from an older log entry:

| Suite | Command | Result |
|-------|---------|--------|
| Python recommender | `uv run pytest` | **816 passed, 6 skipped** |
| Node calc/extract | `npm test` | **50 passed** (not in CI) |

Skipped (pytest `-rs`): 5 live-calc tests that require `CALC_LIVE=1` / a live calc probe; 1 Ollama bootstrap smoke that requires `BOOTSTRAP_OLLAMA_MODEL` in the pytest process.

CI runs `uv run pytest` on push to `main` and on pull requests.

## License

[MIT](LICENSE)
