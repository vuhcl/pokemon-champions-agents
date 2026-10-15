# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Provenance note.** CLAUDE.md is the canonical rules file. Section headings that name a source (for example "from .cursor/rules/…") record where a rule came from when this file was created from the Cursor rules. They are history, not a pointer. The `.cursor/rules/*` files are no longer maintained; when the two disagree, follow this file.

## What this is

A LangGraph team-building recommender for **Pokémon Champions** VGC doubles (a standalone game, not mainline Scarlet/Violet). It is a portfolio project, so the code has to hold up when someone asks why it was built a certain way. Background lives in `docs/architecture_decisions.md` (the ADRs) and `docs/master_project_log.md`. Read the relevant ADR before changing a subsystem; don't ask the user to re-explain something that is already written down. `docs/CURSOR_HANDOFF.md` is the original scaffolding handoff and is historical only.

## Commands

```bash
uv sync --extra dev                  # add --extra ollama / --extra anthropic for live LLM intake
npm install && npm start             # calc service (tsx services/calc/server.ts) on 127.0.0.1:4173, GET /health
python -m recommender --new          # interactive CLI (flags/env: docs/cli.md)

uv run pytest                                        # Python suite (testpaths: tests/recommender, tests/ci)
uv run pytest tests/recommender/test_anchor_roles.py::test_name   # single test
CALC_LIVE=1 uv run pytest ...                        # enable live-calc tests (need calc service running)
npm test                                             # Node tests: extract_legality, extract_moves, calc (not in CI)
uv run python scripts/eval/part_g_v4/checks/run_all_checks.py   # held-out eval package checks (runs in CI)
```

CI (`.github/workflows/tests.yml`) starts the calc service, then runs `uv run pytest` and the part_g_v4 checks. Some tests need the calc service running even when `CALC_LIVE` is unset. The Ollama smoke tests are skipped unless `langchain-ollama` and `BOOTSTRAP_OLLAMA_MODEL` are present.

Data extraction scripts are in `package.json` (`npm run extract:legality`, `extract:abilities`, `extract:move-*`) and `scripts/extract_usage/`. Scheduled refreshes run as GitHub workflows (usage, compendium, legality, vgcpastes) gated by `scripts/ci/*_gate.py`.

## Hard constraints (from `.cursor/rules/project-context.mdc`; don't relitigate unless the user asks)

- **Legality (species/items/abilities) is always a tool lookup against extracted data** (`data/legality/`, `recommender/legality.py`), never an LLM assertion or general Pokémon knowledge.
- **Mechanical claims (speed, damage, KO, matchups) always come from `@smogon/calc`** through the calc service (`recommender/calc_client.py`). The vendored calc in `vendor/smogon-calc` has Champions-specific fixes, such as the Spe formula `floor(n*(base+SP+20))` with no level or IVs.
- **The LLM only extracts structured intent** (bootstrap intake, turn intent, claim_correction). Its output is a draft. Legality, identity, ranking, and locks are decided deterministically downstream. A failed parse keeps the prior prompt and changes nothing.
- **No free-form or model-directed web search at runtime.** Supplementary data is gathered offline (ADR-014). ADR-014's amendments permit structured fetches from named sources only (latest: 2026-10-14a and 2026-10-14b). Build-level sources such as VGCPastes are offline-only. Evaluation runs pass `allow_live=False` to the arm usage tools.
- **Regulation is a parameter and never a hardcoded literal.** `tests/ci/test_no_regulation_literals.py` enforces this with an AST scan and a path allowlist. The schedule is in `data/active_regulation.json`, and the regulation-to-mod/format mapping is in `recommender/regulation_registry.py`. Champions is its own Showdown mod (`data/mods/champions*`), not "gen9 minus a banlist." Check the current regulation letter; don't assume it.
- **Calc-unavailable behavior is typed** (ADR-029). `single_locked` may show static estimates labeled with `estimate_kind="static"`. `multi_locked` fails closed. Never let unverified rows look like verified ones.
- Out of scope: Showdown win-rate eval, battle-log/RL piloting, singles/BSS. Point out any drift toward these.
- Until the Oct 19-20 pin refresh is done, run no gate or scoring against the current keys.

## Never present plausible-looking results as complete

When a deliverable claims to be complete or correct against real data (a list, mapping, classification, or count), derive it from the data. If full certainty isn't possible, say so and name the gap. Don't fill gaps from general knowledge or pattern-matching. The owner checks results directly and treats a confidently wrong answer as a serious failure. Under-claim and flag.

## Evidence standard

Label every mechanical claim in code strings, PR bodies, ADRs and log entries by its evidence: owner in-game observation (own-screen readings, with the date), pinned-sim code, or secondary source (wikis). Owner observation outranks the other two. The pinned Showdown sim is a reference and not ground truth: it was wrong on Substitute handling for Struggle and Steel Beam, and it encodes 1/3 recoil as 33/100. A wiki reading is not confirmation either. Never write a claim as settled when only the sim and a wiki agree; say what is untested. No confidence percentages anywhere that is written to a PR body, ADR, log entry or task note.

## Frozen artifacts

The held-out eval keys (`scripts/eval/part_g_v4/key_artifacts/`), the claim and false-legal batteries, and the request-set text (`part3_request_set_v4.md`) are frozen. Don't edit them; they change only at a scheduled pin refresh on the owner's instruction. Known defects are handled by the scorer requirements (R9), so put proposed corrections in chat.

## PR and test rules

- One PR per task, branched from main. Never force-push a merged or shared branch; ask before any force-push, including a rebase of an unmerged stack.
- Run the full suites before calling anything ready (`uv run pytest`, `npm test`, `run_all_checks.py`). Targeted runs alone have missed breakage before.
- Report exact test counts, and say whether the keys sha and both battery hashes printed by `run_all_checks.py` are unchanged. Keep hashes on one unbroken line.
- One task per worktree. Do not spawn subagents or run parallel agents unless the owner asks (usage limits are shared with the owner's chat).

## Read-only mirror files: never write these

`docs/architecture_decisions.md` and `docs/master_project_log.md` mirror canonical copies kept in a separate Claude Project. Only the owner edits them, by hand; commits that touch them are the owner's and give agents no permission to edit them. **Don't write or edit them with any tool, shell redirect, or in-place edit**, however the request is worded ("amend ADR-0XX", "add a log entry", a plan step that names an ADR). Put the proposed text in chat for the owner to paste. Amendments are named `Amendment YYYY-MM-DDa`, then `b`, `c`, and so on. Append only: never delete or overwrite a prior amendment, and say which one a correction supersedes. Draft ADR or log text only when the owner asks. Put it in chat as one version, never in the mirror files. Other files under `docs/` are not covered by this ban.

## Architecture

**Graph** (`recommender/graph.py`, nodes in `recommender/nodes.py` and `nodes_classify.py`). Each CLI turn runs `START → classify_input → <intent handler> → route_team_phase → <phase discovery> → END`. `classify_input` sets `turn_intent`. Closed-set replies (picking a candidate, confirming a build) are matched deterministically, and only free text goes to the LLM parsers (`turn_intent.py`, `bootstrap.py`, `llm_provider.resolve_llm_parsers`). `_INTENT_ROUTES` maps each intent to its handler. Team phase (`empty → single_locked → multi_locked → complete`) is re-derived from the confirmed lock count on every turn, so it is never stored as authoritative state. The state schema is in `state.py`. The CLI (`cli.py`) persists threads with the LangGraph SQLite checkpointer (`checkpointer.py`).

**Candidate discovery** (the core producers):
- Anchor role (`anchor_roles.classify_anchor_role`, what a locked mon *is*) and target role (`slot_fill_target_role`, what the open slot *should become*) are deliberately separate producers (ADR-024).
- Need resolution is compendium-first. The Role Compendium (`role_compendium*.py`, data in `data/roles/*.v1.json`) admits candidates before any raw legal-learner search, and compendium confidence is the leading sort key (ADR-023). Weather and terrain setters flip "provides" into kit-backed beneficiaries (`support_needs.py`, `role_compendium_weather.py`).
- Ranking (`ranking.py`, `team_candidates.py`, `coverage.py`, `threat_counters.py`, `matchup.py`) gates on `estimate_kind` before score.
- Every presented candidate carries `CandidateEvidence` (basis, confidence, producer).
- Builds come from usage data (`usage_data.load_usage` prefers per-source files in `data/usage/`, `resolved_builds.py`). Role-aware synthesis (`role_aware_synthesis.py`) pulls a build toward the kit of the role that admitted it.

**Steering** after a lock: `edit`, `compare`, `defer`, `revise_locked_slot`, `repick_locked_slot`, and `claim_correction` (`system_claims.py`). A claim correction checks the disputed claim against the legality snapshot and fails closed. It never asks the LLM to regenerate the fact.

**Calc service** (`services/calc/`, TypeScript run via tsx). It is an HTTP wrapper around the vendored `@smogon/calc` with batch endpoints. A legitimate `damage=0` is a success, not an error, and one bad row must not abort a batch (ADR-030). Status-move filtering uses `data/moves/flags.v1.json`, not a denylist.

**Data** (`data/`) is generated by the extract scripts from Showdown's mod sources and usage sources. The files are versioned (`*.v1.json`), and schemas and fixtures sit next to them. Regenerate with the extract scripts rather than hand-editing.

**Eval** (`scripts/eval/`) contains scenario harnesses (legality grounding against an independent oracle, mechanical claims, steering, Claude validation). Pre-register a method (`docs/pre_registration.md`) before measuring anything new. Eval harnesses pin explicit regulations and are allowlisted until the M-C baseline is re-frozen.

## Code style (from `.cursor/rules/ponytail.mdc`)

Take the simplest change that works. Reuse an existing helper or dependency before writing a new one. Don't add abstractions or dependencies nobody asked for, and prefer deleting code to adding it. Fix bugs at the root cause: grep every caller of the shared function and fix it once. Mark a deliberate shortcut that has a known ceiling with a `ponytail:` comment naming the ceiling and the upgrade path. Non-trivial logic should leave one small runnable check behind (a test). Don't pre-build speculative integrations before a real gap shows up.
