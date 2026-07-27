# ARCHITECTURE DECISIONS — Pokémon Champions Agentic Team-Building System
## Lightweight ADR log. Each entry: decision, alternatives considered, why.
## Purpose: preserve "why X and not Y" answers for interview defensibility — same function as
## the VinylIQ master resume's "why ALS not re-ranking" / "why Cloud SQL not volume-mounted" notes.

## Amendment convention (adopted 2026-07-25)
Amendments to an ADR are appended, never overwritten in place, and never delete a prior
amendment — even a wrong one. Each gets a sequential same-day suffix: `Amendment YYYY-MM-DDa`,
`...b`, `...c`, etc. A corrected amendment's `Status:` line names exactly which prior
amendment it supersedes. This preserves an honest trail of what was believed and when,
rather than a silently-corrected final answer.

---

## ADR-001: Scope sequencing — recommender before eval
**Decision:** Build the team recommender agent first. Showdown-simulated evaluation is phase 2, allowed to run in parallel with the battle-log-parser stretch goal, but not a blocker for calling the recommender "done."
**Alternatives considered:** Build both simultaneously; build eval-first to define success criteria before building the system it evaluates.
**Why:** Eval design against Showdown's simulator is expected to be non-trivial (opponent team sourcing, matchup sampling, statistical significance of a small number of simulated games). Blocking the core agentic deliverable on an uncertain-scope eval risks shipping nothing defensible in the time window. The recommender alone, done well, is already a legitimate resume-worthy deliverable.
**Status:** Decided, in effect from project start.

---

## ADR-002: Legality checking is a tool call, not a model assertion
**Decision:** Species legality, item legality, and regulation-pool membership are always checked against real structured data via a tool call. The LLM/agent layer never asserts legality from its own training knowledge.
**Alternatives considered:** Prompt-engineer the model to "remember" Champions-specific rules; fine-tune on legality data.
**Why:** This directly targets the most frequently observed failure mode in hands-on testing with Claude and Gemini — cross-contamination from SV OU (or other formats) into Champions recommendations. Prompting alone was already tried informally (via general chat use) and failed reliably; a grounded tool call removes the failure mode structurally instead of trying to prompt around it.
**Status:** Decided — core architectural constraint, treat as non-negotiable across the rest of the build.

---

## ADR-003: Mechanical claims require verification calls
**Decision:** Any claim involving speed comparisons, damage calculations, or matchup outcomes must be backed by an actual calculation/simulation call, not a generated statement. **Concrete tool: `@smogon/calc`** (the engine behind Pokémon Showdown's public damage calculator, calc.pokemonshowdown.com) — open source, deterministic, already implements the correct game mechanics rather than requiring a reimplementation of damage formulas.
**Alternatives considered:** Rely on the LLM's general Pokémon mechanics knowledge with careful prompting; hand-roll a damage calculator from scratch.
**Why:** Observed failure mode #4 (see master_project_log.md) — models produce confident-sounding but unverified mechanical conclusions. This is a reasoning-rigor gap, not a knowledge gap, so prompting for "show your work" is not sufficient; the check needs to be an actual computed value the agent retrieves and reasons over, not text it generates unassisted. Using the existing, actively-maintained `@smogon/calc` avoids the real risk of a hand-rolled calculator quietly getting damage mechanics wrong (a self-defeating outcome for a tool whose entire purpose is mechanical correctness).
**Status:** Decided — tool identified, integration approach (direct library call vs. subprocess/API wrapper) to be confirmed during scaffolding.

---

### ADR-003 — Amendment 2026-07-25a

**Runtime split clarified: extractor in TS is correct, calc integration runtime is still open.**

Project orchestration is Python; Showdown's source data and `@smogon/calc` are both
TypeScript/npm. Two different problems, not one:

- **Data extraction (ADR-002/007's legality data)** is offline and one-time-per-regulation
  (ADR-014). Writing this extractor in TS is the right choice, not a compromise — it reads
  Showdown's own TS source directly via the TypeScript compiler API/ts-node, and its only
  output is a plain JSON snapshot. No runtime coupling exists once extraction is done; Python
  orchestration just reads JSON. No action needed here.
- **Mechanical verification (`@smogon/calc`, ADR-003)** is a live, in-conversation call, not
  a batch job — this is where the Python/TS split is a real architectural decision, not a
  non-issue. Options under consideration: (1) subprocess/CLI call from Python to Node,
  (2) small local HTTP service wrapping the calc library, (3) switch orchestration to
  LangGraph.js (rejected as disproportionate — would affect the whole stack, including the
  Ollama-dev pattern, to solve one integration point).

**Status:** Extraction-script language choice: decided, no further discussion needed.
Calc integration runtime approach: **open, not yet decided** — narrowed to subprocess vs.
local HTTP service, pending a latency/complexity trade-off

---

### ADR-003 — Amendment 2026-07-25b

**@pkmn/dmg tested and rejected. Stock @smogon/calc confirmed to have native Champions
support — original stock-library concern was based on indirect signals and was wrong.**

**@pkmn/dmg test results** (Cursor spike, scratch/verify_pkmn_dmg_champions_sp.ts):
- Stat calc does not use Champions' SP formula natively — @pkmn/data's Stats.calc is always
  standard Gen EV/IV math; the mod's `statModify` override (in @pkmn/ps's
  mods/src/champions/scripts.ts) is never invoked by @pkmn/dmg.
- Workaround exists (SP×8 fed into standard 0-252 EV slot) and is algebraically exact at L50 —
  verified against Garchomp and Kingambit test cases — but this is a stat-only workaround, not
  genuine mod support.
- Damage calculation itself is unimplemented: `calculate()` always returns `HitResult.damage
  = 0`, has an explicit TODO in source. Package is git-only (not on npm), v0.0.1.
- **Verdict: not viable. Do not adopt.**

**Correction on stock @smogon/calc:** earlier discussion (this session) inferred from
indirect signals — Showdex tracking its own pinned @smogon/calc commit, Pikalytics describing
its calculator as "forked from Smogon ... with ongoing maintenance" — that the published
package likely lacked native Champions support. Checked directly against
github.com/smogon/damage-calc source instead of relying on that inference: **wrong**.
`calc/src/mechanics/champions.ts` is a dedicated, first-listed damage-mechanics module, and
`calc/src/stats.ts` has a `calcStatChampions` method (triggered for `gen.num === 0`, Champions
treated as its own pseudo-generation) using formula `base + sp + 20` (`+75` for HP), no IV
term — an exact match for Showdown's own mod formula. Confirmed against `package.json`:
this is v0.11.0, the same version currently published on npm.

**Decision: stay on @smogon/calc for ADR-003.** Champions support is native and current, not
something requiring a fork or patch. The Python/TS runtime bridge question (subprocess vs.
local HTTP service, from earlier discussion) remains open and is the actual next decision —
this amendment only resolves *which library*, not *how Python calls it*.

**Status:** Resolves the "which damage-calc library" question. Supersedes the implicit
assumption in the original ADR-003 that stock @smogon/calc's Champions support was uncertain.

---

### ADR-003 — Amendment 2026-07-26a

**Runtime bridge decided: persistent local HTTP service. npm @smogon/calc@0.11.0 lag found
and worked around.**

**Bridge decision (closes the open question from Amendments 2026-07-25a/b):** mechanical
verification runs through a thin Node HTTP service (`services/calc/`, `npm start`) wrapping
`@smogon/calc` and `@pkmn/sets` in one process. Python owns all search/optimization logic
(including SP breakpoint binary search via `POST /calculate/batch`) and, separately, process
lifecycle (spawn/health-check/SIGTERM on app launch and exit). Subprocess-per-call rejected —
per-call Node cold-start cost was judged too high for the SP-breakpoint-search and quick-pick
(ADR-012a) use cases, which both involve bursts of calc calls, not isolated one-offs. Aligns
with ADR-015's "thin service, smart client" framing — no search/decision logic lives in the
Node service.

**Champions generation selector:** `Generations.get(0)` — Champions is numeric gen `0` in
`@smogon/calc`, not the string `'champions'` (that string-based mod-lookup pattern is
`@pkmn/data`'s API shape, which throws — confirmed during the earlier `@pkmn/dmg` spike,
ADR-003b — and does not apply here). SP values (0–32) are passed directly in the `evs` field
as-is.

**npm lag, found during implementation — corrects Amendment 2026-07-25b.** That amendment
confirmed Champions support in `smogon/damage-calc`'s GitHub source and treated a matching
`package.json` version number (`0.11.0`) as sufficient confirmation it matched what's on npm.
It wasn't: installing the actual published `@smogon/calc@0.11.0` (published 2026-03-11) and
testing it directly shows **gen 0 is empty** — Champions support exists in GitHub source
only, added 2026-04-16, never republished to npm under any version. Verifying a source repo
is not the same as verifying the specific distributed artifact being depended on.

**Resolution:** the service depends on a vendored build of `calc/` from
`smogon/damage-calc@fc49580` (`vendor/smogon-calc`, `file:` dependency), not the npm package.
Verified correct via golden test against live Showdown's own champions.html calculator
(Garchomp Earthquake vs. Kingambit — stats and damage range match exactly).

**Tracking item:** drop the vendored copy and switch to a normal `npm install @smogon/calc`
dependency once npm republishes a version that actually includes Champions support. No
automatic signal for this — needs periodic manual checking.

**Status:** Closes the subprocess-vs-HTTP-service open question from Amendments
2026-07-25a/b. Corrects 2026-07-25b's premature "confirmed against package.json" claim
regarding npm parity — library choice (@smogon/calc) itself still stands, only the sourcing
mechanism changed (vendored pinned commit vs. npm).

---

### ADR-003 — Amendment 2026-07-26b

**Field support un-deferred: weather and screens prioritized now, not built speculatively
later.**

Correction to the prior session's scope call ("defer Field until VGC mechanics need it") —
that framing understated how central weather and screens actually are to Reg M-B doubles
play; they're mainstream team archetypes (Rain/Sun cores, Aurora Veil support), not edge
cases. Terrain, by contrast, is confirmed low-relevance in the current Champions meta and
stays low-priority — exposed in the API since `@smogon/calc`'s `Field` class already supports
it at no extra cost, but not a focus for test coverage.

**Verified directly:** `@smogon/calc`'s `Field`/`Side` classes (calc/src/field.ts) already
support weather, terrain, and screens (isReflect/isLightScreen/isAuroraVeil) plus Tailwind,
ruin abilities, and switch-in flags. Doubles spread-move damage reduction is automatic —
`mechanics/champions.ts` branches on `field.gameType !== 'Singles'` internally; setting
`gameType: 'Doubles'` on the Field object is sufficient, no custom reduction logic needed.

**Decision:** `/calculate` and `/calculate/batch` accept an optional `field` parameter
(weather, terrain, screens/side conditions, gameType) now, not as a later addition. Test
coverage prioritizes weather + screens + doubles-spread combinations; terrain gets basic
pass-through coverage only, given its current meta irrelevance.

**Correction, same day:** terrain coverage is not actually deprioritized. Implementation is
already native to @smogon/calc (same mechanism as weather/screens) — the earlier "basic
pass-through only" call conflated *current meta irrelevance* with *implementation cost*, which
aren't the same thing here. Full golden-test coverage for terrain, matching weather/screens,
costs the same marginal effort as the rest of the Field test suite already being built. Given
regulation is treated as a versioned, changing parameter throughout this project (not a static
assumption), there's no good reason to under-test a mechanic just because it happens to be
unused under the *current* regulation.

**Status:** Revises the calc-service scope from the 2026-07-25/26 build. Un-blocks tier-3
verification (ADR-015) from the "neutral field only" caveat for weather/screens cases
specifically — terrain-dependent claims remain a lower-confidence case for now, consistent
with its actual meta relevance.

---

### ADR-003 — Amendment 2026-07-26c

**Field support shipped and independently verified. Calc service fully operational.**

Weather/terrain/screens/doubles-spread support added to the calc service (services/calc/),
plus the Python-side client and lifecycle manager (spawn on ephemeral port, health-check,
clean shutdown). 18/18 Node tests, 10/10 Python tests (including live, non-mocked runs)
passing.

**Golden tests independently verified, not circular.** Field-condition goldens (Singles vs.
Doubles EQ, Surf under neutral/Rain) were cross-checked directly against live
calc.pokemonshowdown.com/champions.html — not just asserted against the vendored library's
own output, which would only guard against regression, not confirm correctness. Exact match
across all cases. This matters given ADR-003's prior npm-lag surprise (Amendment
2026-07-26a) — the standard from here is independent verification against a live reference,
not just internal consistency.

**Ephemeral port path confirmed exercised, not assumed.** server.ts reads `process.env.PORT`
(falls back to the fixed default only when unset); live Python-side tests spawned the
service on a free port and connected via the client's own `base_url`, not a hardcoded
address — confirms the two tracks' independent assumptions about port handling actually meet
correctly at the seam between them, rather than each track passing its own tests while
silently relying on the other having done something it hadn't.

**Status:** Calc service (mechanical verification, ADR-003) is complete and independently
verified: library choice, Champions generation selector, npm-lag workaround, runtime bridge,
and Field support. Ready to be built on by tier-3 breakpoint search (ADR-015) whenever that
work starts.

---

## ADR-014: Minimize live web search as a runtime agent tool
**Decision:** The agent's runtime tool set should not include general web search as a live, per-conversation tool call. Anything that would otherwise require a live search (e.g., supplementary legality data beyond what Showdown's data files cover, per ADR-007) should be gathered **once, offline, during data preparation**, and baked into the static legality dataset — not fetched live by the agent mid-conversation.
**Alternatives considered:** Give the agent a general web-search tool for anything not covered by bundled data.
**Why:** Live web search as a runtime tool is slow, non-deterministic (results can vary between calls, undermining reproducibility of recommendations), and costly per-invocation. It also reintroduces exactly the kind of ungrounded-claim risk the project exists to eliminate (ADR-002, ADR-003) if search results are used without the same rigor as the structured legality/calc tools. The fix is architectural: treat "supplementary source" work (ADR-007) as a one-time offline data-collection step, not a live tool in the agent's loop.
**Status:** Decided. If a genuine case for live lookup emerges during development (something that must be current at call-time and can't be pre-baked), treat it as an explicit exception to justify, not a default capability.

---

### ADR-014 — Amendment 2026-07-25a

**Explicit exception granted: live lookup permitted for tier-1 moveset/item-specific build
search (ADR-015).**

ADR-014's original text anticipated this: "if a genuine case for live lookup emerges during
development... treat it as an explicit exception to justify, not a default capability." This
is that case. When a user's chosen moveset and/or item for a Pokémon doesn't match what's
covered by the pre-extracted offline snapshot (ADR-007c sources, or the analogous-mainline-
format fallback, ADR-015), the agent may search live for a real build matching that specific
combination, rather than being limited to what was indexed ahead of time.

**Why this doesn't reopen ADR-014's original concerns:** the risks ADR-014 flagged —
non-determinism undermining reproducibility, and an ungrounded live result being used without
the rigor applied to structured tools — are addressed by mandatory post-lookup verification,
not by avoiding live lookup altogether:

1. **Legality check, unconditionally.** A live-found build passes through the same legality
   tool as any other recommendation (ADR-002) before being surfaced. No exception to this
   guardrail, live-sourced or not — a real build found online is not an implicit legality
   shortcut, same principle as ADR-015's tier-1 guardrail for offline-sourced builds.
2. **EV→SP conversion, where applicable.** A mainline-format result gets the same validated
   ÷8/round/cap translation as ADR-015's analogous-format fallback (confirmed algebraically
   exact at L50, ADR-003b) — not a fresh, unvalidated conversion each time.
3. **Completeness check: the spread must use all available points.** A translated or
   live-found spread that doesn't allocate the full 66 SP (or full ~508 EV before conversion)
   is a signal, not an automatic pass — it may indicate a stale build, a lossy or incorrect
   translation, or a genuinely suboptimal reference set. Flag rather than silently accept a
   spread that leaves points unused.

**Scope of the exception:** narrow — live lookup is permitted specifically for tier-1
moveset/item-specific build search (ADR-015), not a general-purpose runtime search capability
elsewhere in the agent. ADR-014's original policy (no live web search as a general runtime
tool) otherwise stands unchanged.

**Status:** Amends ADR-014 with a scoped, justified exception, per ADR-014's own anticipated-
exception clause. Does not reopen or weaken the general no-live-search policy.

---

## ADR-004: RL policy — retrain, do not reuse
**Decision:** Train a new RL policy specifically for Pokémon Champions and the current regulation, rather than adapting the ~6-year-old SARSA policy from the original Pokémon Battler project.
**Alternatives considered:** Fine-tune/adapt the old policy; use the old policy's reward structure unchanged with new state representation.
**Why:** The old policy was trained for a different, older format with a different legal pool and meta. Both the game rules and the six years of meta/personal-skill drift make direct reuse misleading rather than efficient. The original project remains a useful reference for algorithm and reward-design lessons learned, not as a transplantable artifact.
**Status:** Decided. Algorithm choice for the new policy (SARSA again, or reconsider given six years of RL progress) — open, decide before RL component work begins.

---

## ADR-005: Doubles (VGC) as v1 primary format; singles (BSS) as v2 extension
**Decision:** Build v1 against VGC 2026 Reg M-B (doubles) as the primary target. Singles (BSS) is explicitly scoped as a later extension, not a parallel v1 goal.
**Alternatives considered:** Support both formats from the start; build singles first.
**Why:** VGC has materially different team-building logic than singles — spread moves, redirection (Follow Me/Rage Powder), Trick Room speed control, and doubles-specific item/ability priorities. Trying to serve both from day one in a 3-4 week window risks building generic logic that fits neither well. VGC was chosen over BSS specifically because it maps to official tournament play, which is the stronger portfolio/credibility signal, even though the intended end-user base is broader than tournament players. Real-world "anyone who plays" appeal is a v2+ consideration, not a v1 architectural requirement.
**Status:** Decided. Revisit singles support only after VGC-specific logic (team preview bring-6-select-4, doubles mechanics) is working end to end.

---

## ADR-006: Orchestration framework — LangGraph
**Decision:** Use LangGraph for agent orchestration rather than a hand-rolled loop.
**Alternatives considered:** Hand-rolled orchestration (more defensible as "I understand the internals," per earlier discussion, but higher build risk for someone with no prior agent-framework experience); other frameworks (CrewAI, AutoGen).
**Why:** LangGraph is complex enough to represent a genuine production-relevant skill (explicit state graphs, multi-turn conversation state, tool-calling nodes), and named-framework experience has real JD-matching value. Hand-rolling was judged too much added risk for a first agentic project with no prior framework experience — the goal is to ship a working, defensible system, not to prove framework-independence on the first attempt.
**Status:** Decided.

---

## ADR-007: Regulation/legality data source — Showdown teambuilder data, supplemented by other sources
**Decision:** Use Pokémon Showdown's teambuilder/validator data as the primary legality-check source, but explicitly allow supplementing with other sources (official regulation rulings, community resources) for anything Showdown's data doesn't cover or where it may lag official rulings.
**Alternatives considered:** Showdown data only; official sources only.
**Why:** Showdown maintains the exact formats this project targets (`[Champions] BSS Reg M-B`, `[Champions] VGC 2026 Reg M-B`) and its validator logic is a practical, structured, immediately usable source. But Showdown is a third-party implementation, not the official rulebook — treating it as the sole source of truth risks inheriting any lag or error in Showdown's own data. Cross-checking against official sources when available is worth the extra effort given that legality accuracy is the project's core value proposition (see failure mode #1 in master_project_log.md).
**Status:** Decided on primary source; specific supplementary sources to be identified during Cursor scaffolding as gaps in Showdown data are actually found (don't pre-build supplementary integrations speculatively — add them when a real gap is hit).

---

### ADR-007 — Amendment 2026-07-25a

**Correction to sourcing assumption.** Original ADR-007 asked whether Showdown's data
"cleanly separates by regulation." Verified directly against `smogon/pokemon-showdown`
(cloned and inspected `data/mods/champions/`): it does not, and doesn't need to for v1 scope.

**What's actually there:** `data/mods/champions/` has no separate `pokedex.ts` — species
(names, types, stats, forms) inherit unmodified from the base `gen9` dex. Champions overrides
legality/availability via `formats-data.ts` (per-species `isNonstandard`/`tier` flags, e.g.
`bulbasaur: { isNonstandard: "Past", tier: "Illegal" }`), plus uniform bans (Mythicals,
Restricted Legendaries) enforced at the ruleset level via `Flat Rules` in `rulesets.ts` —
not per-format banlists.

**The correction:** `formats-data.ts` is a flat snapshot of *current* legality, not a table
indexed by regulation letter. `config/formats.ts` format entries for `BSS Reg M-A` and
`BSS Reg M-B` both point at the same `mod: 'champions'` data — the M-A entry is a
name-preserved historical shell, not an independently queryable legal pool anymore. When the
regulation moves, this file is edited in place; there's no `M-A` vs `M-B` field to query.

**Why this doesn't block v1:** the project only targets the current regulation (M-B). No
regulation-indexed lookup is needed yet.

**Practical implication for later:** if historical-regulation support is ever wanted (v2+,
not now), it requires checking out an older commit of the Showdown repo near the regulation
swap date — not a query parameter against current data. Recorded here so this isn't
re-discovered from scratch if it comes up later.

**Revised extraction approach:** treat every legality-data pull as a dated, commit-hash-tagged
snapshot (not a live or regulation-parameterized query). The commit hash is the reproducibility
anchor for "what regulation was this legality check run against."

**Status:** SUPERSEDED by Amendment 2026-07-25b below. This amendment incorrectly
concluded Showdown's data has no regulation indexing; corrected after direct inspection
of data/mods/championsregma/.

---

### ADR-007 — Amendment 2026-07-25b

**Verified against smogon/pokemon-showdown directly** (cloned, inspected `data/mods/`).

Champions species data has no separate `pokedex.ts` — species (names, types, stats, forms)
inherit from the base `gen9` dex. Legality/availability is layered on top via
`formats-data.ts` (per-species `isNonstandard`/`tier`) and `items.ts`. Uniform bans
(Mythicals, Restricted Legendaries) come from `rulesets.ts`'s `flatrules` entry, not
per-format banlists.

**Regulation IS structurally separated, as parallel mods — not flat/current-only as
originally assumed here.** `config/formats.ts` confirms: `BSS/VGC Reg M-B` → `mod: 'champions'`
(current); `BSS/VGC Reg M-A` → `mod: 'championsregma'`, which declares `inherit: 'champions'`
and overrides only `formats-data.ts` + `items.ts`. Diffing the two `formats-data.ts` files
directly surfaces exactly which species/items changed legality between regs (38 species
flip legality in the M-A→M-B diff) — this is a real, usable, already-existing answer key,
not something requiring git history.

**Practical implication:** the legality tool can resolve regulation by mod name directly
(`champions` = current reg, `championsregma` = prior reg, and presumably a new
`championsreg[x]` mod folder each time the regulation changes going forward) rather than by
timestamped snapshot + commit hash as previously stated here. Extraction should key off mod
name, and the mod-vs-mod diff itself is worth keeping as a test fixture — it's a ground-truth
set of "this species just became legal/illegal" cases to validate the legality tool against.

**Status:** Supersedes Amendment 2026-07-25a above, which incorrectly claimed no
regulation indexing exists in Showdown's data.

---

### ADR-007b — Offline legality snapshot (2026-07-25)

**Decision:** Extract Showdown Champions legality offline into a committed, versioned JSON
snapshot (`data/legality/champions.v1.json`) plus a `championsregma→champions` diff fixture.
The future legality tool loads these artifacts only — no live Showdown at agent runtime
(ADR-014). Schema and regenerate instructions: [`data/legality/schema.v1.md`](../data/legality/schema.v1.md).
Extractor: `npm run extract:legality` (AST parse via TypeScript compiler API; species join by
Showdown id onto `data/pokedex.ts`; full item merge `base → champions`; `effective_tags` =
union along `toId(baseSpecies)`). Reproducibility anchors: `meta.source.commit` +
`meta.source.mod`.

**Status:** Decided; snapshot committed under `data/legality/`.

---

### ADR-007 — Amendment 2026-07-25c

**Supplementary usage-data sources identified** (real gap: ADR-012a's quick-pick tool needs
assumed opponent sets, which Showdown's static legality data doesn't provide).

Four sources exist, not interchangeable:
- **Pokemon Showdown ladder usage** — ranked-battle-only, reflects the online ladder
  population, not necessarily tournament-caliber play.
- **Pikalytics** (`pikalytics.com/champions`) — blends Showdown ladder usage with real
  tournament results in one view; includes 2-core/3-core teammate data and full top-team
  builds from actual placements. Has a documented AI-facing API
  (`/ai/pokedex/[format]/[pokemon]`, markdown) suited to offline batch extraction (ADR-014).
- **Pokemon-Zone** (`pokemon-zone.com/champions`) — exclusively real-tournament data, sourced
  from Limitless (online tournaments) and pokedata.ovh (in-person VGC events), explicitly
  regulation- and season-scoped.
- **MunchStats** (`munchstats.com`) — explicitly cross-references ladder (Smogon usage) vs.
  tournament (Limitless + RK9.gg official events) data and surfaces their *divergence* as a
  first-class metric, rather than blending them. Its damage calculator runs a move against
  the full weighted distribution of real opponent EV spreads and returns a KO-probability
  breakdown, instead of assuming one spread. Open source (`PizzaTimeJoshua/munchstats`),
  methodology inspectable.

**For the quick-pick tool's assumed-opponent-set use case specifically**, MunchStats' weighted
approach is the best structural fit: rather than picking one "most common" opponent set and
treating a subsequent calc call as certain, the tool can represent the opponent's likely set
as a genuine distribution and report a KO-probability range — a more honest match for what's
actually knowable from a species-only Team Preview screenshot than false single-spread
precision. Pokemon-Zone/Pikalytics tournament data remains useful for team-building-stage
meta awareness (what's actually winning), separate from this specific in-the-moment use case.

**Status:** Identifies sources per ADR-007's "add supplementary sources only when a real gap
is found" policy. Not yet integrated — extraction/integration approach to be decided when the
quick-pick tool is actually built (after the core recommender loop, per ADR-012's original
sequencing).

---

## ADR-008: Underlying LLM for the agent — resolved, see ADR-013
**Status:** Superseded by ADR-013 (model-agnostic design, local model for development, hosted model for production/demo). Kept here only for numbering continuity.

---

## ADR-009: User input method for available Pokémon — manual text entry to start, screenshot recognition as a cheap v1 add-on
**Decision:** Core recommender loop is built and proven against manual text/list input first. Box **screenshot recognition** (fixed, known sprite set — template matching, not a meaningful CV challenge) may be added within v1 once the core loop works, since it's genuinely cheap to build. This is distinct from **battle video/log parsing** (text-box anchoring, OCR, HP-bar reading), which remains the harder, correctly-deferred phase 3 stretch goal — do not conflate the two CV components again.
**Status:** Decided. Sequence: manual entry → working core loop → screenshot recognition as a fast add-on. Battle video parsing stays phase 3.

---

## ADR-011: Team Preview mechanics are in-scope for the format/legality tool
**Decision:** VGC's "bring 6, select 4 at Team Preview" mechanic is a real constraint the recommender must account for — it is not sufficient to recommend 6 good Pokémon without reasoning about the bring/select structure.
**Status:** Decided — build this into the format tool's scope from the start, not as a later patch.

---

## ADR-010: Interface — CLI
**Decision:** CLI for v1. No dedicated UI.
**Status:** Decided.

---

## ADR-012: Team-selection-at-Team-Preview as a recommender extension
**Decision:** In addition to building the initial 6-Pokémon team, extend the recommender to handle the "given my 6 and the opponent's revealed 6, which 4 do I bring" decision. This is a static decision problem solvable with the same legality/matchup-calc tools already in scope — it does not require the battle-log parser or the RL policy, so it's a natural extension of the recommender (phase 1/1.5), not tied to the harder piloting/RL phase (phase 3).
**Status:** Decided as a scoped extension. Build after the core 6-Pokémon recommender loop works; don't build simultaneously with the first working version.

---

### ADR-012 — Amendment 2026-07-25a

**Change: this is a separate, single-shot tool — not an extension of the conversational
recommender.**

Original ADR-012 framed bring-4-of-6 as an extension of the recommender agent, reusing its
legality/matchup-calc tools within the same conversational loop. That framing didn't account
for the real usage constraint: Team Preview gives ~2 minutes, opponent info arrives as a
phone screenshot showing species names only (no items/abilities/moves/EVs), and there is
realistically no time for conversational back-and-forth about constraints in that window.

**Corrected design:**
- This is a **separate, stateless, single-shot tool** — no LangGraph conversational state,
  no steering loop. Input: `team_draft` (6 already-built, constraint-compliant PokemonSets)
  + `opponent_species` (species-name list only, from the screenshot). Output: which 4 slot
  indices to bring, plus one short rationale per pick. One call, one answer.
- `team_preview_opponent` is species-only, not full sets — Team Preview doesn't reveal item/
  ability/moves/EVs. Any matchup-calc call against the opponent therefore runs against an
  **assumed** set (most common competitive build per usage stats for that species/format),
  not a confirmed one.
- **This means the mechanical-verification tool call here is inherently probabilistic in a
  way the rest of the recommender isn't.** ADR-003's "always a real computed value, never a
  generated assertion" still holds — the calc call is real and grounded — but its input
  carries irreducible uncertainty the pre-battle team-build calc calls don't have. Worth
  stating plainly rather than letting "we always verify mechanically" imply more certainty
  than a species-only Team Preview screenshot can actually support.
- `RecommenderState` (used for the core 6-Pokémon build) does **not** carry
  `team_preview_opponent`/`bring_selection` fields — those were removed from that schema
  entirely once this tool became separate. See state-schema discussion, 2026-07-25.

**Why this still counts as a natural extension, just not an in-process one (per original
ADR-012 rationale):** it's still a static decision problem using the same underlying
legality/matchup tools, still doesn't require the battle-log parser or RL policy (phase 3).
Only the interaction shape changed — single-shot standalone tool instead of a turn inside
the recommender's conversation.

**Status:** Amends ADR-012. Original status (build after the core loop works, don't build
simultaneously) still holds — this only corrects the shape of what gets built, not the
sequencing.

---

## ADR-013: LLM provider — model-agnostic by design, local model for development
**Decision:** The agent's underlying LLM is a swappable config parameter, not hardcoded to a specific provider/client. Development and iteration use a local model via Ollama (same pattern already used for VinylIQ's LLM audit pipeline, for the same reason — eliminating per-call API cost and rate limits during heavy iteration). Claude API (or another hosted model) is the documented production/demo backend, validated occasionally near completion, not used for the bulk of iterative development.
**Alternatives considered:** Hardcoding a single hosted provider for both dev and production.
**Why:** Decouples two separate cost concerns — development cost (should be ~zero, borne by the builder) and end-user cost (should be borne by whoever deploys/runs it, via their own API key). This also has a genuine architectural benefit beyond cost: because legality-checking (ADR-002) and mechanical verification (ADR-003) already push the failure-prone reasoning out of the LLM and into deterministic tool calls, the system's correctness doesn't depend heavily on the underlying model's reasoning quality — only on orchestration and conversation, which materially reduces the risk of using a cheaper/local model for most of the build.
**Status:** Decided. Implementation detail (LangChain's model-agnostic chat interface or equivalent) to be confirmed during scaffolding.

---

## ADR-015: Build/spread sourcing strategy

**Decision:** Three tiers, in order, for proposing a Pokémon's full set (item, moves, SP
spread, nature):

1. **Known-build lookup.** Champions-native sources first (Pikalytics/Pokemon-Zone/MunchStats,
   ADR-007c), then analogous mainline Smogon formats as fallback (SV BSS for singles, SV VGC
   for doubles), translating EVs to SP via the validated ÷8/round/cap mapping (confirmed
   algebraically exact at L50, ADR-003b). When neither source covers the user's specific
   moveset/item combination, live lookup is permitted for that exact combination — a scoped
   exception to ADR-014, see ADR-014 Amendment 2026-07-25a.
2. **Role-pattern heuristic proposal**, used when no known build (offline or live) covers the
   situation. The agent reasons from the set's intended role — inferred from its moveset,
   typing, and stated purpose — to a spread archetype (e.g. "fast attacker": max offensive
   stat + Speed, remainder to HP; "bulky pivot": max HP + the relevant defensive stat, informed
   by which incoming moves it needs to answer). This reasoning becomes the slot's `rationale`
   — it's genuinely useful output, not just an intermediate step.
3. **Bespoke calc-driven breakpoint search** (binary search over calc + `kochance()`, per the
   ADR-003 runtime discussion) — used both as its own fallback (a specific numeric question
   tiers 1–2 can't answer) and as mandatory verification for tier 2's output.

   **Verification requires a specific, relevant opponent — not an arbitrary or generic one.**
   A damage calculation is inherently attacker-vs-defender; "does this build survive/KO"
   is meaningless without naming what it's being checked against. Tier 3 selects opponents
   from current meta data (the same ADR-007c sources used for tier 1 — Pikalytics/Pokemon-
   Zone/MunchStats usage and, where available, checks-and-counters/teammate data), not a
   hand-picked or generic example.

   **Relevance is determined by the build's own role (tier 2's classification), not a fixed
   opponent list.** A bulky defensive build gets checked against the highest-usage attackers
   whose offensive coverage/typing actually threatens it — not every top-usage Pokémon in the
   format regardless of relevance. An offensive build gets checked against the bulkiest
   commonly-fielded answers to it, to confirm it clears the breakpoints it's built to clear,
   not just any target. This makes tier 2 and tier 3 a connected pipeline, not independent
   stages: the role classification that produces the spread is the same classification that
   determines which threats matter enough to verify against.

   **Scope discipline:** this is a small, targeted set of relevant threats (a handful, not
   the full meta), since exhaustively checking against every top-usage Pokémon multiplies the
   search space (candidate spreads × opponents) without adding much verification value beyond
   the threats that are actually likely to matter for this specific role.

**Critical guardrail — borrowed or live-found builds are not a legality shortcut.** Every set
surfaced through tier 1, offline or live, passes through the same legality tool as any other
recommendation (ADR-002) before being surfaced. Champions' legality overlay
(isNonstandard/tier) can differ from a mainline format's in either direction — a real Smogon
or live-found set is not an implicit pass.

**Tier-2 guardrail — role-pattern reasoning is a plausible prior, not a verified claim.** This
is exactly the shape of failure mode #4 (master_project_log.md), made more dangerous by how
often the heuristic happens to be right. A tier-2 proposal is a draft until tier 3 confirms
it; `verification_log` (RecommenderState) should show a real tool call backing any breakpoint
the rationale implies, same as any other mechanical claim in this project.

**Completeness check — spreads must use all available points.** Any finalized spread
(tier 1 or 2) is checked for unused SP/EV points. A borrowed or live-found build (tier 1) that
doesn't allocate the full 66 SP (or ~508 EV pre-conversion) is a signal, not an automatic pass
— it may indicate a stale build, a lossy translation, or a genuinely suboptimal reference set.

**Incomplete-spread handling.** The agent does not silently dump leftover points into a
default stat. It applies tier 2's role-heuristic reasoning to decide where the remainder
should go — informed by the same moveset/typing/role signals tier 2 already uses — and tier
3's calc-driven breakpoint search to confirm that allocation is actually justified (secures a
real breakpoint, not points spent with no verified effect). This is the existing tier 2→3
pipeline applied to the leftover points specifically, not a fourth mechanism. The reasoning
behind the top-up becomes part of the slot's `rationale` — the user sees why the extra points
went where they did, not just a silently-completed spread.

**Sourcing mechanics:** per ADR-014, offline sources (ADR-007c, analogous-format Smogon data)
are gathered ahead of time, not queried live; the live-lookup path is the scoped exception
per ADR-014 Amendment 2026-07-25a, not a reopening of the general policy.

**Status:** Decided. Bespoke calc-search implementation (binary search shape, Python-side per
the "thin service, smart client" runtime decision) and role-taxonomy design (fixed archetype
list vs. free reasoning — open question, not yet resolved) still to be built. One known gap,
flagged not yet resolved: a tier-1 spread that already uses all its points currently receives
no tier-3 verification at all, since the completeness check is what triggers the tier 2→3
top-up pipeline — "a real build someone used" is currently sufficient grounding for that case
without a calc sanity check. Revisit if this proves too permissive in practice.

---

### ADR-015 — Amendment 2026-07-25a

**Opponent-build sourcing for tier-3 verification is scope-bounded to avoid recursive
blowup.** Selecting a relevant opponent's *own* build does not invoke the full tier 1→2→3
pipeline — that would mean running the whole recommendation process once per threat checked,
for every candidate spread being evaluated. The opponent's build for verification purposes is
sourced via tier 1 (known-build lookup) only: the real, most-common competitive build for that
threat from the same usage data (ADR-007c). It only needs to be representative, not optimal —
verification is checking against a plausible real opponent, not solving the opponent's build
too.

**Speed-tier verification is a distinct check from damage/KO verification.** Whether a build
outspeeds or is outsped by a relevant threat (or, for Trick Room builds, intentionally
underspeeds) is a stat comparison, not a `kochance()` question, and is checked separately
within tier 3 — same fixed 3–5 relevant-threat scope, same tier-1-sourced opponent builds.

**Tier 1 must capture written reasoning, not just numeric spreads, from analogous-format
Smogon analyses.** A raw EV/SP number doesn't carry the reason a speed benchmark was chosen
(e.g. "outspeeds uninvested base 100s," "underspeeds the format's common Trick Room setters
intentionally") — that reasoning exists only in the analysis prose. When tier 1 pulls from
SV BSS/VGC analogous-format data, the extraction should preserve this written rationale where
available, not just the translated spread, since it's the actual source of speed-tier
reasoning transfer, not something tier 2's role-heuristic can reconstruct from the numbers
alone.

**Speed-tier reverification trigger: moves and item match, full stop.** If the user's current
build still uses the same moves and item as the borrowed set the speed-tier reasoning came
from, that reasoning is treated as still valid — no reverification needed. This directly
targets what actually invalidates borrowed speed reasoning: speed-control logic is conditioned
on the set's own kit (does it run Choice Scarf, does it support Trick Room, is it built around
Tailwind, etc.) — moves + item capture that condition directly, without a separate fuzzy
"changed enough" threshold. If either changes, a heavier cross-format tier-relevance lookup is
triggered (see below); if neither changes, it's skipped entirely, even if other parts of the
build (SP spread, nature) have been adjusted.

**Cross-format tier-relevance lookup, when triggered, is a heavier operation than the standard
tier-3 threat check, not a drop-in re-run.** Smogon's speed benchmarks are calibrated to
tier-specific metagames (OU, UU, VGC Reg X, etc.), each defined by that format's own
usage/banlist — "outspeeds uninvested base 100s" is a claim about relevance *in that tier*,
which doesn't map directly onto Champions' actual current usage. Confirming whether the same
benchmark threat is still meta-relevant in Champions specifically requires cross-referencing
tier placement/relevance across formats, which isn't guaranteed to be answered by the same
structured extraction tier 1 already uses — it may require an online lookup rather than a
local snapshot query. This is a further, narrower instance of the ADR-014 Amendment
2026-07-25a exception, scoped specifically to this cross-format tier-relevance question, not a
general capability.

**Status:** Resolves the opponent-scope and reverification-trigger open questions from the
base ADR-015. Remaining open implementation question: the cross-format tier-relevance lookup
mechanism itself is not yet designed.

---

### ADR-015 — Amendment 2026-07-26b

**Legality check outcome does not map 1:1 onto usable/unusable — refines the tier-1
guardrail.**

**A legality failure doesn't always mean discard the whole build.** A borrowed set that fails
on one specific element (an illegal item, a move no longer available) may still be adaptable
— substitute the failing element for a legal analog and keep the rest of the build's
reasoning intact — rather than being thrown out wholesale. Passing through the legality tool
means every element is checked, not that the whole set is rejected the moment any single
element fails.

**A legality pass doesn't mean the build is current or optimal.** A build can be fully legal
under the current regulation and still be missing something better, because the regulation
unlocked an option the reference build predates. Concrete case: Mega Swampert became
available in Reg M-B and gained access to Wave Crash — a build sourced from an
analogous-format reference written before that unlock would be entirely legal in Champions
while missing an option that likely changes the intended set. Legality checking only confirms
"nothing here is currently illegal" — it does not confirm the build reflects everything
currently available.

**Practical implication, kept simple — check current availability directly, not a historical
delta.** Rather than reconstructing what changed since a reference build was written, check
what's currently legal for this species (moves, abilities, items) against what the build
actually uses, as a direct present-tense comparison. Any currently-legal option the build
doesn't incorporate is a candidate for tier-3 verification: does substituting or adding it
measurably improve a relevant breakpoint? If so, surface it as an alternative; if not, the
omission is fine as-is. This needs only the source regulation/format tag already captured for
provenance (ADR-016) — no timestamp or "what was available when written" tracking required.

**Status:** Refines ADR-015's tier-1 legality guardrail. Does not change tier ordering or the
core sourcing strategy — clarifies that legality is necessary but not sufficient for treating
a borrowed build as current or optimal.

---

### ADR-015 — Amendment 2026-07-26c

**Legality-failure diagnosis and substitution logic, resolved by element type and severity.**

When a borrowed set fails legality (ADR-015 Amendment 2026-07-26b), diagnose which specific
element failed — Pokémon, item, move, or ability — and resolve according to that element's
actual role, not a uniform "find something similar" search:

- **Universal-role items** (e.g. Life Orb-type power boosters with no type restriction): a
  substitute search among currently-legal options of the same category is usually
  straightforward. Check whether the Pokémon's actual moveset is concentrated enough in one
  type for a *type-locked* substitute to make sense before proposing one — a mixed attacker
  isn't well served by a type-restricted item (Fairy Feather, Black Glasses, type
  plates/gems) the way a mono-type-focused set is.
- **Type-locked items**: substitute must match the Pokémon's actual moveset type
  concentration, checked directly against move data (Fairy Feather for a Fairy-type
  Ghost/Fairy attacker like Mimikyu; Black Glasses for a Dark-focused attacker like
  Kingambit) — not proposed generically.
- **Non-severe, no-substitute items** (extension items: Damp/Heat/Smooth Rock, Light Clay,
  Terrain Extender): no substitute exists or is needed. Losing the item shortens a duration
  effect; the set still functions and remains worth using as-is. Resolves as "keep as-is,
  note the shortened duration," not as a search failure.
- **Severe, no-substitute items** (unique item-ability interactions, e.g. Toxic Orb enabling
  Gliscor's Poison Heal): no substitute exists, and forcing a different item onto the same
  Pokémon produces a materially different, worse set. Default resolution is a species swap —
  find a different Pokémon that fulfills the same tier-2 role — unless this specific Pokémon
  is uniquely required for the role (typing/stats/movepool), in which case the resolution is
  "keep the Pokémon, drop the item, accept the loss" rather than inventing a fake substitute.
- **Moves**: substitute must match on type and comparable base power (and category/secondary
  effects where relevant) as concrete, checkable criteria against existing move data — e.g.
  Aura Sphere for Body Press on Archaludon in Reg M-A (both Fighting-type, same base power).
  A substitute existing doesn't mean it's equally good — it may be a real downgrade (e.g. less
  commonly used specifically because it's a worse fit) even where it's a legal, functional
  swap. This should be reflected in the resulting `rationale`, not smoothed over as equivalent
  to the original.

**Item substitution must be team-aware, not decided per-slot in isolation** — checked against
`RecommenderState.team_draft` for Item Clause (no duplicate items across the team), per the
observed failure mode logged in master_project_log.md (#6, 2026-07-26). This applies to
substitution specifically but is really a restatement of a general constraint: item
assignment for any slot must always check the full team draft, borrowed-set substitution or
not.

**"No valid substitute" must be a legitimate output, not defaulted away.** The system should
be able to conclude "this build doesn't transfer" (severe-no-substitute case) rather than
always forcing some replacement, even a bad one, onto a build that should honestly be
reported as non-transferable.

**Status:** Refines ADR-015 Amendment 2026-07-26b's legality-failure handling with concrete,
element-type-specific resolution logic. Does not change tier ordering.

---

## ADR-016: Resolved-build cache — tier-1 accumulates verified knowledge over time

**Decision:** Maintain a persistent, shareable local store of resolved builds — species +
moveset/item role-combination, keyed however tier 1 identifies a combo — mapping to the
spread(s) actually used, source, and any written rationale captured alongside it (per
ADR-015's note on preserving Smogon writeup reasoning, e.g. speed-tier justification). Before
any tier-1 lookup (offline or live), check this cache first. A hit skips re-searching
entirely; a miss proceeds through tier 1 as designed, and a successful, tier-3-verified
result gets written back before moving on.

**Store the documented range of variants, not a single collapsed value.** Most Pokémon's real
competitive spreads vary narrowly, not arbitrarily — e.g. Hatterene is consistently
near-max-HP investment, with the remainder split between Def and SpA depending on set. Smogon
analyses already document this directly (alternate EV spreads, teammates, checks/counters
sections), so the cache should capture that documented variance as multiple entries or a
range, not compress it into one canonical number that discards real, precedented information.

**Why this resolves the primary/secondary SP-arbitration question (2026-07-26 discussion):**
rather than deriving a rule for splitting SP between competing roles (e.g. Trick Room bulk vs.
Calm Mind sweeping investment on the same Hatterene), look up the real build(s) people
actually use for that specific role combination. Arbitration has already been solved by
whoever plays that build competitively — tier 2's role-split logic becomes a genuine
fallback, used only when no real precedent exists for the specific combo, not the default
path for multi-role builds.

**Expected usage split — tier 2 is a rare edge case, not a coequal path.** Given the above,
tier 1 (cache + broader lookup) is expected to resolve the large majority of real
recommendations. Tier 2's bespoke role-heuristic reasoning is reserved for: a genuinely novel
combination with no documented precedent anywhere, or — rarely — a highly flexible species
(large movepool, multiple viable abilities, e.g. Archaludon) in a specific configuration that
happens not to already be documented, even though that species' *other* builds are. This
should inform eval design (eval_results.md) later: tier 2/3 bespoke-reasoning accuracy is a
narrow-but-important edge-case metric, not one that needs equal test volume to tier 1's
lookup-and-verify path.

**Why this matters beyond convenience:** it directly reduces reliance on the ADR-014a live-
lookup exception over time — the system gets less search-dependent and more grounded in its
own accumulated, already-verified knowledge the longer it's used. Good fit for the project's
"defensible under interview questioning" goal: not just "we verify every claim," but "we get
more efficient at it over time without sacrificing grounding."

**Shareable/distributable, decided 2026-07-26.** Storage format is structured JSON (or JSONL
for append-friendly growth), checked into the repo — not a binary DB — since diffability and
mergeability matter once this is meant to be shared, not just used locally.

Each entry must carry: `regulation` (explicit field, not inferred from file-update time),
`source_tier` (Champions-native / analogous-format / live-lookup, per ADR-007c/ADR-014a),
`verified` (bool — tier-3-confirmed, or just tier-1-sourced), `date_resolved`, and where
applicable a `variants` structure capturing documented alternate spreads rather than a single
value. A shared cache with unlabeled provenance is just numbers with no way to judge trust —
this isn't optional metadata.

**Content note:** this is a curated, derived dataset (specific resolved builds this project
verified), not a bulk mirror of any single source's underlying database — worth one line in
the cache's own README acknowledging it's derived from public competitive-data sources, same
spirit as the repo's existing MIT-license note about Pokémon data itself.

**Location:** likely `data/resolved-builds/`, organized per-regulation (e.g.
`champions-reg-mb.jsonl`) rather than one mixed file, so regulation-scoping is structural, not
just a field to check.

**A build does not go stale within a regulation.** The spread/moveset/item combination
remains a real, valid, functioning build for as long as the regulation holds — meta shift
changes which threats are currently popular, it doesn't invalidate the build itself. No
staleness/expiry framing applies to the build data itself.

**What actually can drift: verification-threat currency, a separate and narrower concept.**
Tier-3 verification checks a build against "the top 3–5 relevant threats by usage" *at the
time it ran* (ADR-015's fixed small-number scope). That specific threat set is a snapshot of
a moving target — usage rankings shift over a season even within one regulation (Pokemon-
Zone's season-scoping, ADR-007c) — so a build verified months ago may have been checked
against threats that are no longer the current top answers, even though the build itself is
unchanged and still sound. This isn't the build being wrong; it's the verification claim
being scoped to whenever it was run. Accordingly, each cache entry's `verified` field should
carry more than a boolean — the specific threat set it was checked against and a usage-
snapshot reference/date — turning "is this verification still current" into a well-defined,
checkable comparison against present-day top usage, rather than a vague time-based expiry.
Whether to act on a mismatch (re-verify against new top threats) is a judgment call for
implementation time, not decided here.

**Open design questions, not yet resolved:**
- **Cache key shape:** likely species + moveset + item (role combination implied, not stored
  redundantly) — needs confirming once tier 1's actual lookup identity is built.
- **Regulation invalidation.** A cached build resolved under Reg M-B needs invalidating or
  re-verifying when the regulation changes — same concern as ADR-007b's snapshot-not-indexed
  legality data. (Distinct from the resolved verification-currency question above, which is
  within-regulation.)

**Status:** Decided in principle (cache-before-search, write-back-after-verify, shareable
JSON/JSONL format, variant-preserving rather than single-value, verification-currency tracked
via recorded threat-set/snapshot rather than time-based expiry). Cache key shape and
cross-regulation invalidation still to be designed — implementation task, should land before
tier 1 is actually built, since retrofitting a cache layer onto an already-built stateless
tier 1 is more work than designing it in from the start.

---

### ADR-016 — Amendment 2026-07-26a

**Cross-regulation handling and cache key shape, resolved.**

**Cross-regulation handling mirrors Showdown's own mod-retirement pattern.** The "current"
regulation's cache file is the live one (e.g. champions-reg-mb.jsonl). When a new regulation
arrives, the prior file is archived under its own regulation tag (e.g.
champions-reg-ma.jsonl) — not deleted, not silently merged — same structural pattern as
Showdown demoting the previous regulation's mod to championsregma (ADR-007b).

Carrying an entry forward into a new regulation's cache is a re-validation, not a blind
carryover: legality re-check (ADR-002), plus a current-availability check (see ADR-015
Amendment 2026-07-26b) — comparing what's now legal for the species against what the build
actually uses, not a historical delta requiring knowledge of exactly when the build was
written. Most entries are expected to pass through with an unchanged or lightly adjusted
spread, since builds rarely undergo full revamps across a regulation shift — but this is
confirmed per entry, not assumed globally.

**Cache key shape, resolved:** species + moveset + item, scoped per-regulation-file. Source
regulation/format is structural (which file an entry lives in) plus the already-captured
`source_tier` provenance field — no separate timestamp or "what was available when written"
tracking is needed, since the present-tense current-availability check (ADR-015 Amendment
2026-07-26b) replaces any need to reconstruct historical deltas.

**Status:** Resolves the two open design questions from the base ADR-016 (cache key shape,
cross-regulation invalidation).

---

### ADR-016 — Amendment 2026-07-26b

**Contingent-value strategy detection: a rare, regulation-change-triggered check, not a
standing process.**

Some sets remain fully legal in Champions but lose most of their real competitive value
because the specific mechanic that made them good depends on a supporting condition
(commonly: a teammate providing terrain/weather/redirection) that is structurally rare or
absent in Champions, even though the move/set itself is untouched. Concrete case: Expanding
Force is legal and learnable in Champions and looks unchanged "in a vacuum," but its value in
mainline VGC came specifically from reliable Psychic Terrain via Psychic Surge setters
(e.g. Indeedee-F) — Champions has essentially no viable Psychic Surge source, so the
move's real value doesn't transfer even though nothing about it failed a legality check.

**This dependency is often not stated explicitly in source writeups** — it can surface only
structurally, split across a set's teammates section (naming a partner specifically because
it enables the mechanic) and its threats/counters section (naming a threat specifically
because it can remove that same mechanic). Relying on parsing this out of prose is fragile
and not the chosen approach.

**Chosen approach: category-level diff, not prose inference.** Compare category-level
presence (ability/mechanic categories — terrain-setters, weather-setters, redirection,
specific enabling item categories) between an analogous mainline format and Champions, using
the same species/ability data tier 1 already extracts. This surfaces candidate cases
mechanically (a category structurally rare or absent in Champions but common in the reference
format) rather than requiring prose-dependency extraction. Cross-reference which
currently-legal moves/sets specifically lean on the missing category to generate candidates
for review.

**These cases are real edge cases, expected to be rare** — a strategy being fully gone (not
just partially weakened) is uncommon. Resolution is a small, curated list (species/move/set →
the enabling condition it depends on → current Champions availability of that condition),
stored the same way as the rest of the resolved-build cache (ADR-016) — cheap to check at
recommendation time once populated.

**Trigger: regulation change only, not periodic.** The category-level diff is a one-shot
check run when the regulation updates (alongside the other regulation-change work already
decided: ADR-016's cache re-validation, ADR-015 Amendment 2026-07-26b's current-availability
check) — not a standing or scheduled process, since the underlying condition (what's
structurally available) only changes when the legal pool itself changes.

**Status:** Adds a narrow, rare-case detection mechanism triggered by regulation change,
feeding the same cache infrastructure as the rest of ADR-016. Does not require prose parsing
or ongoing/periodic execution.
