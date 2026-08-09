# CURSOR HANDOFF — Pokémon Champions Agentic Team-Building System

This doc is implementation-focused, written for building, not for narrative/portfolio framing
(that lives in the paired Claude project — see "Feedback loop" at the bottom). Use this to
scaffold the repo and resolve the open decisions before writing the recommender's core logic.

---

## What this system does (v1 scope)

An agentic team-building assistant for **Pokémon Champions** (a standalone game, not mainline
Scarlet/Violet) that:
1. Takes a user's available Pokémon (and optionally constraints/preferences)
2. Proposes a team, grounded in real regulation-legal data (species + items)
3. Supports multi-turn steering ("don't use that one, still cover X")
4. Backs any mechanical claim (speed, damage, matchup reasoning) with an actual calculation,
   never a generated assertion
5. (Extension, build after the core loop works) Given the user's 6 and an opponent's revealed
   6 at Team Preview, recommends which 4 to bring — a static decision problem using the same
   legality/matchup-calc tools, not tied to the battle-log/RL phase

**Explicitly out of scope for v1:** Showdown-simulated win-rate eval (phase 2), **battle video/
log parsing** and RL-grounded piloting advice (phase 3 stretch). Box screenshot recognition
(fixed sprite set, template matching) is *not* in this out-of-scope list — it's cheap enough to
add within v1 once the core text-input loop works; don't confuse it with the harder battle-video
CV work. Do not let the phase-2/phase-3 items creep into v1 scope — see `master_project_log.md`'s
MVP floor if this needs re-justifying mid-build.

---

## Formats — get this exactly right, it's the core failure mode this project exists to fix

- Target game: **Pokémon Champions**, distinct from mainline SV. Do not let any dependency,
  dataset, or reference material default to SV data without an explicit legality check first.
- Pokémon Showdown format identifiers:
  - `[Champions] BSS Reg M-B` — singles (Battle Stadium Singles)
  - `[Champions] VGC 2026 Reg M-B` — doubles (VGC)
- **Regulation letter (currently M-B) will change over time.** Do not hardcode "M-B" anywhere
  load-bearing — treat regulation as a config parameter from day one, even in v1, even if only
  one regulation is supported initially.
- **Decided: VGC 2026 Reg M-B (doubles) is the v1 target.** Singles (BSS) is a v2 extension, not
  a parallel v1 goal — don't build generic logic trying to serve both from the start. Doubles-
  specific mechanics (spread moves, Follow Me/Rage Powder redirection, Trick Room speed control,
  and Team Preview's bring-6-select-4 structure) are real, in-scope constraints, not edge cases.

---

## Data sourcing — decided, verify specifics before writing legality-check logic

- **Primary source: Pokémon Showdown's own teambuilder/validator data**, since Showdown already
  implements and maintains these exact formats. Verify during scaffolding:
  - Are the data files structured usably (JSON/JS exports) for programmatic legality checks?
  - Do they cleanly separate by regulation, or does regulation logic need to be derived/inferred?
- **Supplement with other sources as needed** (official regulation rulings, community resources)
  for anything Showdown's data doesn't cover or may lag on. Don't pre-build speculative
  integrations with these — add a supplementary source only when a real gap in Showdown's data
  is actually found during development, not preemptively.
- This data source choice is the single highest-leverage decision in the project — it's the
  direct fix for the most common LLM failure mode being targeted (recommending SV OU species/
  items that aren't legal in Champions/current regulation). Don't rush past this step.

---

## Guardrails to build in from the start (not retrofit later)

These map directly to failure modes observed from hands-on testing with general-purpose LLMs
(Claude, Gemini) before this project started. Build the fix as a structural tool call, not a
prompt-engineering patch:

1. **Cross-game/format contamination** — most common failure. Any species or item mention must
   be validated against the current regulation's actual legal pool via a real data lookup, never
   inferred from the model's general Pokémon knowledge.
2. **Item legality** — same fix as above.
3. **General format/game confusion** — every recommendation should be explicitly anchored to
   "Champions, Reg [X], [BSS/VGC]" in whatever internal representation the agent uses, not just
   in the prompt text.
4. **Unverified mechanical claims** — any speed comparison, damage calc, or matchup assessment
   must come from an actual computed value via **`@smogon/calc`** (the engine behind Showdown's
   public damage calculator), not generated text. It must be a real computation the agent
   retrieves, not something it writes out unassisted.
5. **Dropping user constraints across turns** — lower priority per project owner, but once
   multi-turn steering exists, a basic regression check (does the agent still respect an
   earlier-stated constraint N turns later) is worth having even if minimal.
6. **No live web search as a runtime agent tool.** Anything supplementary to Showdown's data
   (ADR-007) gets gathered once, offline, during data prep and baked into the static legality
   dataset — not fetched live mid-conversation. Live search is slow, non-deterministic (breaks
   reproducibility of recommendations), and reintroduces ungrounded-claim risk if used casually.
   Treat any genuine need for a live lookup as an exception to justify, not a default capability.

---

## LLM provider — model-agnostic, local for dev, hosted for demo

- **Decided (ADR-013):** The agent's underlying LLM is a swappable config parameter, not
  hardcoded to one provider's client. Use LangChain's model-agnostic chat interface (or
  equivalent) so swapping providers is a config change, not a rewrite.
- **Development:** use a local model via Ollama (same pattern as VinylIQ's LLM audit pipeline —
  eliminates per-call API cost and rate limits during heavy iteration). Do the bulk of building
  and debugging against this at zero marginal cost.
- **Production/demo:** Claude API (or user's own choice) as the documented reference backend —
  validate against this occasionally, especially before any interview demo, since local models
  may reason less reliably on complex multi-step planning.
- **Why this matters less than it might seem:** legality-checking and mechanical-verification
  are deterministic tool calls (ADR-002, ADR-003), not LLM judgment calls — so the system's
  correctness on the failure modes that matter doesn't hinge heavily on which model is doing the
  orchestration. Don't over-invest in prompt engineering to compensate for a weak local model on
  things that should be tool calls instead.

---

## Architecture decisions already made (see `architecture_decisions.md` for full rationale)

- Legality checking = tool call against real data, never a model assertion (ADR-002)
- Mechanical claims = verification calls via `@smogon/calc`, never generated assertions (ADR-003)
- RL policy will be retrained from scratch for Champions/current regulation — the 6-year-old
  SARSA policy from the prior Pokémon Battler project is not being reused (ADR-004), and is out
  of scope for v1 anyway (phase 3 stretch)
- Recommender ships before eval; eval is explicitly allowed to slip (ADR-001)
- VGC 2026 Reg M-B (doubles) is the v1 target format; singles is a v2 extension (ADR-005)
- Orchestration framework: **LangGraph** (ADR-006)
- Legality data source: Showdown teambuilder data, primary + supplement as gaps are found (ADR-007)
- User input: manual text/list entry first; screenshot recognition is a cheap v1 add-on once the
  core loop works, not a permanent cut (ADR-009)
- Interface: **CLI** (ADR-010)
- Team Preview (bring-6-select-4) mechanics are in-scope for the format/legality tool, not a
  later patch (ADR-011)
- Team-selection-against-a-revealed-opponent extension, built after the core loop (ADR-012)
- LLM provider: model-agnostic, local for dev, hosted for demo/production (ADR-013)
- No live web search as a runtime agent tool; supplementary data gathered offline instead (ADR-014)

No open decisions remain blocking scaffolding start. Proceed to build order below.

---

## Suggested build order within v1

1. Set up model-agnostic LLM config (local Ollama model for dev) and LangGraph skeleton
2. Legality-check tool: given a species/item + regulation, return legal/illegal + reason,
   sourced from Showdown teambuilder data; include Team Preview bring-6-select-4 constraint
3. Basic single-shot recommender: given a box of available Pokémon (manual text input), propose
   one team using the legality tool (no steering yet) — get the core loop working end to end
   before adding memory
4. Add multi-turn steering / conversation state on top of the working single-shot version
5. Add the mechanical-verification tool call (speed/damage calc) and wire it into recommendation
   reasoning, not just as a bolt-on justification after the fact
6. Cheap add-ons once the core loop is solid: box screenshot recognition (template matching);
   team-selection-against-a-revealed-opponent extension (ADR-012)
7. Validate against Claude API (or chosen hosted model) before any demo/interview walkthrough
8. Only after all of the above works: start phase 2 (Showdown eval) if time allows

---

## Feedback loop back to the Claude project

This repo's implementation work happens here in Cursor. A separate Claude Project holds the
narrative/portfolio-facing log (`master_project_log.md`, `architecture_decisions.md`,
`eval_results.md`). At natural checkpoints — a real decision made, a milestone hit, a failure
mode discovered in practice — summarize it and paste it into the Claude project so it gets
logged in the right format. Don't try to log every commit; log decisions and milestones. The
Claude project is also where this will eventually get translated into resume bullets and
interview talking points, the same way VinylIQ's build history did — so err on the side of
recording *why* a decision was made, not just *what* was built, since that's the part that
turns into a defensible interview answer later.

Amendment format and logging-promptness rules now live in `.cursor/rules/project-context.md`
(enforced every session) rather than duplicated here.

**Enforcement note:** `docs/architecture_decisions.md` and `docs/master_project_log.md` in
this repo are read-only mirrors, not editable by Cursor under any circumstance — see
`.cursor/rules/project-context.md` for the hard rule. If a task plan ever includes a step
that would touch either file, flag it back rather than executing it, even for a change as
small as a single type annotation.