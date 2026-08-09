# ARCHITECTURE DECISIONS — Pokémon Champions Agentic Team-Building System
## Lightweight ADR log. Each entry: decision, alternatives considered, why.
## Purpose: preserve "why X and not Y" answers for interview defensibility — same function as
## the VinylIQ master resume's "why ALS not re-ranking" / "why Cloud SQL not volume-mounted" notes.

---

## Amendment convention (adopted 2026-07-25)
Amendments to an ADR are appended, never overwritten in place, and never delete a prior
amendment — even a wrong one. Each gets a sequential same-day suffix: `Amendment YYYY-MM-DDa`,
`...b`, `...c`, etc. A corrected amendment's `Status:` line names exactly which prior
amendment it supersedes. This preserves an honest trail of what was believed and when,
rather than a silently-corrected final answer.

---

## Note on amendment lettering (2026-07-29)
The amendment letter sequence is not perfectly sequential across every ADR — a labeling
mixup on 2026-07-25/26 caused some amendments to be filed under the wrong ADR number
initially (later corrected) and caused ADR-015's own sequence to skip directly from `a` to
`b` on 2026-07-26 (no `2026-07-26a` was ever assigned to ADR-015). This is expected and not
a sign of lost or missing content — cross-references elsewhere in this file to specific
amendment labels (e.g. "Amendment 2026-07-26b") are accurate as written and should not be
renumbered to "fill the gap."

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
covered by the pre-extracted offline snapshot (ADR-007 Amendment 2026-07-25c sources, or the analogous-mainline-
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

### ADR-014 — Amendment 2026-08-05a

**First exercised instance of the ADR's own anticipated exception: construction-time live
fetch against an already-verified, structured data source.**

ADR-014's original status line explicitly anticipated this case ("if a genuine case for
live lookup emerges... treat it as an explicit exception to justify, not a default
capability"). Surfaced during Redirection role construction: the offline usage snapshot
(data/usage/champions-reg-mb.v1.json, TEAM_LADDER_N=50) only captures the in-game ladder's
top 50 species, silently excluding real, relevant candidates below that cutoff (Clefable,
confirmed via direct site inspection to run Follow Me as its most common move, was entirely
absent from the snapshot and therefore invisible to the Redirection construction pass).

**Clarification of what ADR-014's "no live web search" rule actually prohibits:** it targets
UNSTRUCTURED, model-directed search — the LLM deciding what to query and interpreting
free-form results, which is the actual mechanism behind cross-game/format contamination
(failure mode #1 — e.g. pulling SV data instead of Champions data). It does not prohibit
every live network call in every context. A live fetch against an ALREADY-IDENTIFIED,
ALREADY-VERIFIED, STRUCTURALLY-PARSED data source (the same championsbattledata.com/
MunchStats-CBD pipeline already trusted for the offline snapshot, using the same
extraction/parsing logic already built) carries none of the risk the original rule exists
to prevent — no model judgment is involved in what to fetch or how to interpret it,
identical to the offline extraction's own trust model, just triggered per-candidate rather
than batched once upfront.

**Scope of the exception, kept deliberately narrow:** permitted ONLY at construction/data-
prep time (Role Compendium construction, snapshot refresh/backfill) via the same structured,
already-built extraction path — NOT a general runtime-recommendation-path capability, and
NOT permission for open-ended web search anywhere in the system. Any future case invoking
this exception should cite this amendment and confirm it fits the same shape (known source,
known parser, no free-form interpretation) rather than assuming a blanket loosening.

**Status:** Exercises ADR-014's own pre-anticipated exception mechanism for the first time.
No change to the core rule (no unstructured/model-directed live search anywhere in the
system) — this narrowly permits per-candidate structured fetches against an
already-verified source, at construction time only.

---

### ADR-014 — Amendment 2026-08-07a

**Resolving an apparent conflict between Amendment 2026-07-25a (runtime tier-1 live-lookup
exception) and Amendment 2026-08-05a (construction-time-only fetcher scoping): both stand,
they govern different things, and lookup_live_build may NOT reuse the construction-scoped
fetchers to satisfy the runtime exception.**

Surfaced while attempting to wire recommend.py's lookup_live_build (a stub since ADR-015's
tier-1 design) using the CBD/Showdown fetchers (usage_cbd.py/usage_showdown.py) built for
Role Compendium construction. This is not a real conflict between the two amendments' policy
— it's a mechanism-scoping issue: Amendment 2026-07-25a grants a narrow runtime exception for
a specific PURPOSE (tier-1 exact moveset/item build lookup when the offline snapshot doesn't
cover the user's specific combination); Amendment 2026-08-05a scopes a specific MECHANISM
("those fetchers" — the CBD/Showdown extraction/parsing path) to construction/data-prep time
only, explicitly stating it is "NOT a general runtime-recommendation-path capability."

**Resolution:** Amendment 2026-07-25a's runtime exception remains valid and is NOT retracted
or narrowed by this amendment. However, satisfying it by reusing usage_cbd.py/usage_showdown.py
directly violates 2026-08-05a's explicit scope sentence — those specific fetchers may not be
called from a runtime-recommendation-path function, including lookup_live_build. If tier-1's
live-lookup exception is to be implemented, it requires its OWN, separately-justified,
separately-scoped fetch mechanism (following the same "known source, known parser, no
free-form interpretation" template already established by 2026-08-05a for the construction-
time case) — not a reuse of the construction-scoped tools.

**Separate, independent finding, not resolved by this amendment:** both usage_cbd.py and
usage_showdown.py currently hardcode featured_sets: [], and the adapter that would connect
them to a live-build lookup only performs exact moves+item matching against featured_sets.
Routed through as-is, any "live lookup" would silently fall back to top common moves and
IGNORE the user's requested moveset — the opposite of what tier-1's exception exists to
provide. This means even a properly-scoped, dedicated fetcher would need real, populated
featured-set data to satisfy the original guardrails, not just a data-source swap.

**Status quo, pending further work:** lookup_live_build remains a stub (returns None) until
a dedicated, properly-scoped fetch mechanism is designed and built. This is not a regression
— it was already a stub — this amendment records why the obvious-looking fix (reuse the
existing fetchers) is not a valid shortcut, so a future attempt doesn't repeat the same
mechanism-scoping mistake.

**Also noted, a live gap independent of this question:** of Amendment 2026-07-25a's three
mandatory guardrails (legality check, EV→SP conversion, completeness check on unused
points), only the legality check is currently implemented on the EXISTING offline tier-1
path in recommend.py — which currently silently tops up an incomplete spread and overwrites
source_tier to "tier2" rather than flagging the incompleteness as the amendment requires.
This applies to the already-shipped offline path today, not just the hypothetical live one —
worth its own, separate fix.

**Status:** Resolves the apparent 2026-07-25a/2026-08-05a conflict as a mechanism-scoping
distinction, not a policy contradiction. Both amendments stand unchanged. Identifies two
separate, real gaps (featured_sets population; the offline path's incomplete-spread
flagging) as follow-up work, not resolved here.

---

### ADR-014 — Amendment 2026-08-08a

Second separately-confirmed runtime exception: tier-2 spread reasoning may fetch structured
per-species spread variants when bundled usage data has no coverage.

Surfaced while implementing select_usage_spread: the offline usage snapshot's top-species
cap leaves otherwise legal species without the real spread variants needed for contextual
tier-2 selection.

This follows the purpose/mechanism distinction established by Amendment 2026-08-07a. The
runtime exception is implemented through the dedicated fetch_live_spreads mechanism, using
known MunchStats/CBD endpoints, known structured schemas, and deterministic parsing. It
does not call the construction-scoped usage_cbd.py or usage_showdown.py fetchers and does
not authorize free-form or model-directed search.

The fetch occurs only when the species has no offline usage row. Failure, unsupported
regulation, or unusable data returns no candidates, allowing explicit fallback to tier-3
role_spread.

Status: Adds a second, separately justified runtime exception for tier-2 spread evidence
only. Tier-1 lookup_live_build, construction-fetcher restrictions, and ADR-014's general
prohibition on runtime web search remain unchanged.

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

### ADR-007 — Offline legality snapshot (2026-07-25d)

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

### ADR-007 — Amendment 2026-07-26a

**Smogon's Strategy Pokedex added as a Champions-native source.**

`smogon.com/dex/champions/formats/vgc-2026-regulation-m-b/` (and the corresponding M-A page)
carries real written strategy analyses for Champions specifically — a separate source from
the three usage/tournament-data sources already listed in Amendment 2026-07-25c (Pikalytics,
Pokemon-Zone, MunchStats), which are stats/team-composition data, not written analysis. This
is the strongest available source for ADR-015's "preserve written rationale" requirement
(speed-tier justification, teammates, checks/counters) — better than inferring reasoning from
a stats page, and native to Champions rather than borrowed from an analogous format.

**Coverage is currently sparse, which is why the analogous-mainline-format fallback (SV
BSS/VGC, ADR-015 tier 1) remains necessary, not redundant.** Champions is new; the volume of
detailed Champions-native writeups is small compared to long-established formats. Tier 1's
priority order: Champions-native writeup (this source) first if it exists for the
species/combination in question, then usage-data sources (Amendment 2026-07-25c), then
analogous-mainline-format writeups as fallback, then live lookup (ADR-014 Amendment
2026-07-25a) — unchanged in spirit from ADR-015's original tiering, just adding this source
at the top of the "native" tier.

**Status:** Adds a source to the Amendment 2026-07-25c source list. Does not change tier
ordering logic, only adds a preferred source within the existing "Champions-native first"
step.

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
   ADR-007 Amendment 2026-07-25c), then analogous mainline Smogon formats as fallback (SV BSS for singles, SV VGC
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
   from current meta data (the same ADR-007 Amendment 2026-07-25c sources used for tier 1 — Pikalytics/Pokemon-
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

**Sourcing mechanics:** per ADR-014, offline sources (ADR-007 Amendment 2026-07-25c, analogous-format Smogon data)
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

### ADR-015 amendment index
- **2026-07-25a** — Opponent-build sourcing scope-bound to tier-1; speed-tier verification as
  a distinct check; written-rationale preservation from Smogon analyses; speed-tier
  reverification trigger (moves+item match).
- **2026-07-26b** — Legality pass ≠ usable/current/optimal; present-tense current-availability
  check replaces historical-delta reconstruction.
- **2026-07-26c** — Legality-failure diagnosis and substitution logic by element type/severity
  (universal/type-locked items, non-severe/severe-no-substitute, move substitution); team-aware
  Item Clause check; "no valid substitute" as a legitimate output.
- **2026-07-26d** — "Regulations only add, never remove" is Champions-specific and
  observed-so-far, not guaranteed; scoped blast-radius for a hypothetical mechanic-level
  retirement (e.g. Megas → Tera).
- **2026-07-27a** — Theme/core detection mechanism (intrinsic signal + teammate role
  abstraction); two-stage search architecture (mechanical interpretation, multi-axis search);
  "close enough" reverse-lookup definition; multi-role present-options rule.
- **2026-07-27b** — Correction: SP allocation driven by a Pokémon's own base stats/role, not
  team composition as the primary factor.
- **2026-07-27c** — Item/spread/moveset/role as a dependency circle (no fixed resolution
  order); no-obligation weakness compensation; `locked_fields`-driven resolution (no
  convergence loop); tradeoff-flagging scope; per-slot vs. team-review reasoning boundary.
- **2026-07-27d** — Build-refinement priority (strengths before compensation) and the
  trade-off test, including ability/move-based natural coverage, item-gated compounding
  (Assault Vest/Archaludon), and meta-dependence.
- **2026-07-27e** — Role vocabulary externally sourced (Role Compendium); ability/stat
  interaction model (override/reinforce/insurance-slot); Taunt-insurance rule;
  ruleset-conditioned "fast" threshold.
- **2026-07-27f** — Unified move-candidate narrowing procedure (pool size → team need →
  mechanical fit → opportunity cost); delivery-mechanism-aware matching; moveset redundancy
  rule.
- **2026-07-28a** — Default resolution order = the dependency circle with nothing forcing
  anything; true unconstrained case is vanishingly rare in practice.
- **2026-07-28b** — Internal/external reasoning unified as one narrowing-power-driven model;
  explains the doubles/singles asymmetry (ADR-005); team-level redundancy ordering
  (competence before redundancy); presentation format tied to narrowing power.
- **2026-07-28c** — Pairwise threat classifier (mechanism behind gaps #7/#8): inputs, field-
  condition contextual swap-in, four-way classification outcome, flagging rule by decision
  context, symmetry note, HP-based severity gradient, contact-punish and multi-hit-count calc
  gaps.
- **2026-07-28d** — Role Compendium scope/membership model: purpose (role-specific search
  only), source-as-seed-not-truth, doubles/singles top-level split rationale, offensive
  5-point conjunction test, support 3-criteria test, modifier tags, Beneficiary-bucket
  discovery-vs-narrowing, category emergence via regulation diff, singles compendium sketch,
  regulation-driven ranking shifts (absolute capability change vs. relative devaluation).
- **2026-07-29a** — Candidate-discovery discipline: search from regulation-scoped data, not
  generic queries; mandatory bidirectional Mega-form checking (only when the mechanism applies
  to both forms); usage for discovery/legality only, never ranking; near-universal moves
  provide no narrowing power.
- **2026-07-29b** — Refined membership/ranking criteria: offensive test collapses to the
  3-criterion support structure; two-axis execution-risk model for deferred-payoff roles;
  tightened Excellent-tier bar (mechanism-guaranteed, magnitude-aware); doubles-specific
  stricter bulk requirement; membership strictness scales with candidate-pool breadth
  (~15-20 total target); opportunity-cost-elsewhere is out of scope for single-move ranking.
- **2026-07-29c** — Mega Evolution's item-slot lock as a genuine trade-off (base form can
  access items the Mega can't); shared/divergent abilities across a base/Mega pair must be
  verified per form, never assumed.
- **2026-07-29d** — Trick Room attacker specifics: relative (not absolute) Speed-tier
  benefit; deliberate zero-Speed-investment mechanics widening the candidate pool; setup-move
  cost in a turn-limited role; inherent-multiplier magnitude comparison.
- **2026-07-29e** — Usage-data consistency check: usage must be treated identically regardless
  of which conclusion it supports; a usage/mechanical-model conflict should trigger
  re-examining the model, not selective acceptance or dismissal.
- **2026-07-29f** — Sleep-inducing status role specifics: delivery-mechanism reliability
  profiles (Spore/Sleep Powder/Hypnosis/Yawn); mechanism-dependent criterion weighting
  (Speed vs. bulk vs. delivery type); trapping-ability relevance conditional on delivery
  mechanism; accuracy-boosting mechanisms (Compound Eyes, Coil) as confirmed reinforcement.
- **2026-07-31a** — Matchup classifier turn-economy correction: charge-move delay (with
  per-move instant-weather conditions) and recharge-move in-sim vulnerability skip;
  move-selection ranking fix decoupled from simulation physics; accepted limitations
  (Power Herb, single-note A-centric reporting, no reverse-call).

---

### ADR-015 — Amendment 2026-07-25a

**Opponent-build sourcing for tier-3 verification is scope-bounded to avoid recursive
blowup.** Selecting a relevant opponent's *own* build does not invoke the full tier 1→2→3
pipeline — that would mean running the whole recommendation process once per threat checked,
for every candidate spread being evaluated. The opponent's build for verification purposes is
sourced via tier 1 (known-build lookup) only: the real, most-common competitive build for that
threat from the same usage data (ADR-007 Amendment 2026-07-25c). It only needs to be representative, not optimal —
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

### ADR-015 — Amendment 2026-07-26d

**"Regulations only add, never remove" is an observed pattern specific to Champions so far —
not a guaranteed mechanic, and not assumed to hold indefinitely.**

The M-A→M-B transition only added content (new Pokémon, moves, items) — nothing was removed.
This is a real, useful property for the current-availability check (Amendment 2026-07-26b)
and for the cache's cross-regulation carry-forward (ADR-016), since it means a build rarely
needs full reconstruction across a regulation change. But it is not a property of Champions
regulations in general, and mainline VGC regulations have both added and removed content
across their history — the additive-only pattern holds right now specifically because
Champions' Pokémon/item pool is still small relative to the mainline games, so early
regulations are naturally expanding a limited roster rather than trimming an established one.

**This should be re-confirmed at each regulation change, not hardcoded as a permanent
assumption.** The dynamic is expected to shift once the pool grows enough that Game Freak
starts trimming rather than only adding — a plausible future example being Mega Evolution
retired in favor of Tera Type, or an equivalent mechanic-level swap. That kind of change would
be structurally different from anything ADR-015's guardrails currently handle (which assume
per-element legality changes — one move, one item, one Pokémon) — it would be a foundational
mechanic disappearing, not a legality diff.

**Blast radius of a hypothetical mechanic-level retirement (e.g. Megas → Tera), scoped
correctly:** the SP stat formula and the calc service's `champions` mod handling are
unaffected — those are engine-level infrastructure tied to how stats are calculated, not to
which specific mechanic category happens to be legal, so swapping Megas for Tera is a legal-
pool change like any other (ADR-002/007b), not an SP-formula change. What would genuinely
break: cached builds (ADR-016) structurally built around a Mega slot — these would need real
invalidation, not a per-entry legality substitution, since a Mega slot is a foundational
structural assumption a build was organized around, not a swappable element. Similarly, tier-
2's role taxonomy (ADR-015/016) would need an archetype actually removed or restructured if
"Mega cornerstone"-type roles stopped being coherent, not just re-weighted in priority.

**Status:** Notes a real but currently-hypothetical risk category, scoped to what it would and
wouldn't affect. No action required now — flagged so it isn't rediscovered from scratch if
Champions' pool ever shifts from purely additive to include removals.

---

### ADR-015 — Amendment 2026-07-27a

**Theme/core detection mechanism, decided.**

Detection runs from two independent, combinable evidence sources, either of which can operate
alone:

1. **Intrinsic signal from the seed Pokémon itself** — fixed ability/move → archetype mappings
   (Swift Swim/Chlorophyll/Sand Rush → their respective weather; Electro Shot/Weather Ball →
   weather-conditional) and base-stat-threshold heuristics (low Speed + high offense/bulk →
   Trick Room candidate). Works with zero external data — even an undocumented Pokémon gets a
   grounded theme suggestion from this alone.
2. **Teammate role abstraction, sourced from two independent inputs:** (a) named teammates in
   a Champions-native or analogous-format writeup, and (b) real tournament/ladder team
   co-occurrence data (Pikalytics/Pokemon-Zone, ADR-007c — this is what finally wires Track G's
   previously-unused team-composition data into the system). In both cases, **abstract named
   teammates to their own role classification, not their literal species** — this is what
   keeps the inference current rather than stale: an M-A-era writeup naming Politoed doesn't
   recommend Politoed specifically, it recommends "a second Weather Setter," which is then
   searched for in current data (correctly surfacing Mega Swampert-as-attacker or whatever
   else is presently best, without the writeup ever needing updating). Tournament
   co-occurrence data and writeup-named teammates are not alternative/competing sources — the
   former grounds and can confirm or extend the latter empirically, especially where writeup
   coverage is thin.

Combine both sources into a needed-role list. This sometimes converges into a single named
`archetype` (Rain, Trick Room); sometimes it doesn't (Mega Staraptor: Contrary → wants a
stat-debuff partner; weakness profile → wants defensive-coverage partners — no single label,
still a valid, useful `core`).

**Search architecture: two-stage (mechanical interpretation, then multi-axis search), not a
fixed specificity ladder.** Earlier framing considered a staged ladder (full spec → partial
attribute → archetype-only). Rejected as too rigid — real inputs arrive as an open,
arbitrary combination of hints (a species, an item, one move, an adjective, a functional
target like "Charizard counter," a role label), not cleanly nested tiers. The actual
resolution process is:
1. **Stage 1 — mechanical interpretation.** Translate whatever's given into concrete,
   checkable game terms. "Revenge killer" → high Speed tier, and/or priority-move access,
   and/or Choice Scarf. "Charizard counter" → Fire/Flying resistance, and/or outspeeds it,
   and/or survives its hits (multiple valid mechanical readings can coexist — present options
   rather than silently picking one, same principle as below). A literal species/item name
   needs no translation, it's already stage-2-ready.
2. **Stage 2 — multi-axis search** using whatever stage 1 produced, querying species, item,
   ability, move, speed tier, type, or any combination as filters. This replaces the earlier,
   narrower "partial-key lookup" framing — it was never missing a specific lookup function,
   it was missing a stage-1 interpreter in front of the search entirely.

**"Close enough" reverse lookup (moveset/role → candidate species), defined concretely:** a
candidate matches when it shares the *role-relevant* moves specifically — the moves that
functionally define the role (e.g. Encore for a weather-setter-that-also-locks-opponents-in
role) — not a raw moveset-overlap count. Two species sharing only incidental moves (both know
Protect) don't count as a match.

**Multi-role species: present options, don't silently collapse to one build.** Some species'
"role" is a single fixed requirement plus a genuinely open secondary slot with several
non-overlapping real approaches (Pelipper: must set weather; secondary varies — special
attacker, utility, Tailwind, screens. Politoed: must set weather; secondary varies —
disruption, speed control, trapping. Sableye: pure support, but via weather+screens, OR
status+disruption, OR Fake Out+flex, as genuinely distinct, non-blending approaches). This is
the same primary/secondary structure already decided for build variance (Hatterene, earlier
session) — confirmed here to be the normal condition for most support-capable species, not a
rare exception. When a role resolves to multiple real, distinct sub-approaches, present them
rather than picking one silently — consistent with how ambiguous reverse-lookup candidates
(Sableye vs. Politoed) are already handled.

**Still open, not yet designed — flagged, not resolved:** tier-2's SP allocation needs to
account for what other `team_draft` slots already provide (e.g., don't max Speed on an
attacker when Tailwind support is already locked elsewhere) and needs to derive its role
classification from a Pokémon's actual base stats/movepool rather than an externally-supplied
label. Both principles are agreed; neither has an implementation mechanism designed yet.

**Status:** Resolves the theme/core detection mechanism and search architecture in full.
Leaves team-composition-aware allocation and base-stat-driven role derivation as agreed
principles without an implementation design — separate follow-up.

---

### ADR-015 — Amendment 2026-07-27b

**Correction to team-composition-aware allocation framing (Amendment 2026-07-27a).**

That amendment's still-open item framed the missing mechanism as "don't invest in a stat
another slot already provides" (e.g. don't max Speed on an attacker when Tailwind support is
locked elsewhere). That framing is wrong as a rule — support like Tailwind is never
guaranteed to be active in a given game, so an attacker can't safely assume it away entirely
and skip Speed on that basis alone.

**The actual principle:** SP investment in a stat should be judged by whether it meaningfully
changes an outcome for *this* Pokémon in *this* role, given its own base stats — not by what
teammates happen to provide.
- A middling-Speed attacker (Archaludon) usually can't realistically reach a speed tier that
  beats the format's fast threats regardless of investment, so those points are better spent
  on bulk — true most of the time because the investment wouldn't pay off given its own base
  stat line, not because Tailwind exists elsewhere on the team.
- A true glass-cannon archetype maxes Speed and its attacking stat regardless of team
  support, since outspeeding is the entire payoff of that role.
- Trick Room inverts the logic entirely — minimizing Speed (including a hindering nature) is
  correct there because slow-is-better is the mechanic itself, independent of teammates.

Team composition can still be a secondary input (e.g., hedging against support that might not
be up when needed), but a Pokémon's own base stats and role are the primary drivers of the
allocation decision, not what else is on the team.

**Status:** Corrects the team-composition-aware allocation framing in Amendment 2026-07-27a.
Base-stat-driven role derivation (also flagged as open in 2026-07-27a) is unaffected by this
correction.

---

### ADR-015 — Amendment 2026-07-27c

**Item/spread/moveset/role as a dependency circle, not a fixed resolution sequence.**

Earlier framing (Amendment 2026-07-27b) treated stat allocation as informed by team
composition as a secondary input. Refined further: item, spread, moveset, and role are not
resolved in a fixed sequence with speed-compensation as one optional step among others — they
form a dependency circle with no privileged starting point. A decision on any one attribute
can force reconsideration of the others: locking a moveset (Electro Shot) can imply a theme
that shapes the spread; choosing an item (Choice Scarf) can flip what spread is correct
(now max Speed is right) and simultaneously rule out certain moves (no Protect on a scarfed
set); a spread-level finding (Speed investment not worth it given base stats) can motivate
considering an item that changes the answer again. Whichever attribute gets pinned first (by
the user, by tier-1 data, or by tier-2 reasoning) propagates to the others — there is no
correct order to resolve them in.

**Compensating for a stat shortfall is one option to consider, never an obligation.** When a
stat investment is judged not worth it given a Pokémon's own base stats (per Amendment
2026-07-27b), external compensating mechanisms — Tailwind reliance, Choice Scarf, building
around Trick Room instead — are worth surfacing as *possibilities*, not something the system
must resolve. Many legitimate, common builds simply accept the shortfall and lean into what
the Pokémon is otherwise good at, with no compensating mechanism at all. That remains a fully
valid default, not a gap to be patched.

**Resolution of the dependency circle requires no internal convergence loop or iteration
cap.** Default behavior: tier 2 proposes one coherent build and states any real, structurally
relevant tradeoff plainly (see the tradeoff-flagging scope below — most inherent weaknesses
are not flagged by default), rather than looping through alternatives unprompted. The circle
only re-enters resolution when the user explicitly locks a new attribute (e.g. "give me the
Choice Scarf set"). At that point the newly-locked attribute is fixed via `locked_fields`
(ADR-017), and propagation runs once, outward from the fixed point — since a locked attribute
cannot be re-flipped, this is a single deterministic pass, not an unbounded loop.
`locked_fields` is what prevents cycling, not an iteration cap. The system reports back what
changed as a result of the new lock (spread, moveset implications, etc.) as the close of that
interaction.

**Scoping of tradeoff-flagging: not per-build by default.** No build is perfect, and most
inherent tradeoffs (a 4x type weakness a build doesn't cover, a common matchup a species is
just naturally bad into) are normal and expected — flagging them on every proposal would be
pure noise (Swampert's Grass weakness, Mega Charizard Y being walled by Dragons, etc., are not
re-surfaced by default). Flagging is scoped to: (1) an explicit user ask about issues with a
build/team; (2) a dedicated team-review checkpoint (see below); (3) a genuinely glaring,
structural issue — e.g. a build with no coverage move at all — which is qualitatively
different from an inherent tradeoff and worth surfacing proactively regardless of trigger.

**Scope boundary: filling a slot is team-review-scale reasoning; refining a filled slot is
narrow, forward-looking reasoning — a transition, not two parallel modes.** Filling an empty
or role-only slot (deciding what role or species belongs in a slot at all) is properly
informed by team-wide weakness analysis — "what does this team still need" depends directly
on "what is this team weak to," the same reasoning the team-wide checks (threat-coverage,
single-point-of-failure — see master_project_log.md, 2026-07-27 additions) perform, just
applied toward selecting a role/species rather than producing a report. Refining an
already-filled slot (species/role locked, resolving item/moveset/spread within the dependency
circle above) is where narrow reasoning applies: only "what's already locked elsewhere that
should inform this specific build" — team-level weakness analysis has already done its job by
the time a slot reaches this stage, and re-running it here reintroduces the wrong-time noise
the tradeoff-flagging scope above is meant to prevent. The transition point is exactly when a
role or species gets nailed down for that slot.

**Status:** Refines and partially corrects Amendment 2026-07-27b's team-composition-aware
allocation framing into a fuller dependency-circle model, resolves the iteration-bound
question left open there, and establishes the tradeoff-flagging and per-slot/team-review
scoping boundaries needed for the team-wide checks flagged earlier in this session to actually
have defined trigger conditions.

---

### ADR-015 — Amendment 2026-07-27d

**Build-refinement priority: lean into strengths before compensating for weaknesses, and
compensation must pass a real trade-off test.**

Refining a slot's build should prioritize maximizing what a Pokémon's stat profile already
makes it good at, before considering compensation for a weak side: a slow attacker leans into
its natural bulk (already there, not a compensation); a frail attacker leans into Speed; a
wall maximizes its defining bulk. Compensating a weakness sits on a spectrum from "not worth
it" to "fully split investment," never a default action.

**The trade-off test:** compensation is justified only when its marginal cost (SP points that
could go elsewhere, a held item slot) is paid back by a real, relevant outcome — surviving
specific hits it otherwise wouldn't, not patching a weakness reflexively just because it
exists. Glass cannons sit at one extreme — any investment taken from Speed/offense directly
undermines the role's entire purpose, so compensation there is rare and must be tightly
justified against one specific named threat. A wall has real flexibility across the spectrum
(all-in on one defensive side, split investment, or external item/move support), any of which
is valid depending on what the team actually needs it to survive.

**The trade-off test must also account for existing abilities/moves that already cover or
reinforce a stat, separately from investment.** Some Pokémon don't need investment in a
weak-looking stat because something else already covers it: Archaludon's Def side is strong
from a naturally high stat plus Stamina reinforcing it further on every hit taken — this is
"already strong and self-reinforcing," not investment being compounded. Will-O-Wisp reduces
incoming physical damage independent of any investment, partially covering Volcarona's
physical bulk weakness before SP is spent, while Quiver Dance lets it boost Speed/SpAtk/SpDef
together mid-battle, changing how much needs to be front-loaded in the base spread.

**Correction/clarification on genuine investment-compounding, using Archaludon as the
example:** the case where investment itself gets amplified (not just naturally covered) is
SpDef via Assault Vest — a flat multiplier that stacks with actual investment. Assault Vest
is not currently available in Champions, so this specific trade-off does not currently apply,
even though it's a real, previously-valid one for this exact species. This is gated by
current item legality — the same "check against what's currently available, don't assume
permanence" principle already established for build currency (ADR-015 Amendment 2026-07-26b,
Mega Swampert/Wave Crash) — and if Assault Vest becomes available in a future regulation,
this trade-off could become live again with nothing about Archaludon itself changing.

**The trade-off's correctness can also shift with the current meta, independent of the
Pokémon itself.** In extreme cases (e.g. a Pokémon with one stat so dominant that only its
other defensive side is worth addressing, or vice versa — Blissey's HP/physical-vs-special
split as the illustrative extreme, even though not currently in Champions), the correct
trade-off can flip based on the current meta's attack distribution (physical- vs.
special-heavy) rather than being fixed for that species. This reinforces that the trade-off
test is evaluated against current, real threat data, not computed once and reused
indefinitely — consistent with tier 3's opponent-selection already being threat-current
(ADR-015 Amendment 2026-07-26c).

**Status:** Establishes build-refinement priority (strengths first) and the trade-off test for
weakness compensation, including ability/move-based natural coverage, item-gated compounding,
and meta-dependence. Extends the Speed-specific principle in Amendment 2026-07-27b to stat
trade-offs generally.

---

### ADR-015 — Amendment 2026-07-27e

**Role vocabulary is externally sourced, not invented.** Role classification (for theme/core
detection, Amendment 2026-07-27a, and for build refinement generally) classifies into a
fixed, externally-sourced vocabulary — a "role compendium" derived from real community
resources (e.g. Smogon's VGC Regulation M-A Role Compendium forum thread) — not an
open-ended set of labels the system invents per-case.

**Ability/stat-distribution interaction: three relationships, not additive combination.**
When deriving a role from base stats and abilities/moves, the ability does not simply add its
own signal alongside a stat-distribution read — it can stand in one of three relationships to
what the stats alone would suggest, confirmed via worked examples (Grimmsnarl, Sableye,
Whimsicott, Klefki):
- **Override:** the ability makes a stat-based signal actively misleading and takes
  precedence. Grimmsnarl's high Attack would suggest "attacker," but Prankster (making
  support-move priority irrelevant to Speed) means the build should ignore that signal
  entirely and invest in bulk (split Def/SpDef, not Def-only) to protect the support
  gameplan instead.
- **Reinforce:** the ability points the same direction the stats already suggest, adding
  confidence rather than correcting anything. Sableye's flat, low stat spread already
  suggests non-offensive/support; Prankster reinforces that read rather than overriding a
  contradiction.
- **Reinforce-with-an-added-insurance-slot:** covers cases like Whimsicott's support set,
  where the ability reinforces the core read, but a viable one-move offensive option exists as
  Taunt-insurance (see below) — the ability still reinforces the primary gameplan, it just
  doesn't touch the one bolted-on damaging move.

**Structural Taunt-insurance rule, general, not species-specific.** Any proposed moveset
consisting entirely of non-damaging moves must be flagged for its structural vulnerability to
Taunt (which disables all of them at once). This is why sets built around pure disruption/
support commonly carry exactly one damaging move as insurance — the standard case is a single
attacking move whose specific quality depends on that species' own stats/movepool (Whimsicott:
Moonblasts's high SpAtk + neutral coverage makes for strong insurance; Klefki: Foul Play
leverages the opponent's Attack stat instead, since Klefki's own offense is mediocre — same
structural need, different mechanism, driven by each species' own stat profile). This applies
uniformly regardless of role or support type (screens, disruption, redirection,
weather-setting) — always flag an all-non-damaging moveset for this vulnerability.

**"Fast" is a ruleset-conditioned threshold, not a fixed constant.** The standard ~100 base
Speed cutoff for "fast" (used in role/theme detection) holds specifically because Champions'
`Flat Rules` bans Restricted Legendaries and Mythicals (confirmed directly from Showdown
source, ADR-002/007b). If Restricted Legendaries were ever legal, the effective speed
ceiling shifts (e.g. Lunala/Miraidon-class Speed becoming the real baseline), which can flip
what counts as "slow enough for Trick Room" even for objectively fast Pokémon. The threshold
should be derived by checking this specific ruleset fact, not hardcoded — though for
Champions' current rules, the standard threshold applies without adjustment.

**Status:** Establishes the ability/stat interaction model and the general Taunt-insurance
and ruleset-conditioned-Speed rules, derived from worked Prankster-support examples during the
2026-07-27 role-play session.

---

### ADR-015 — Amendment 2026-07-27f

**Move-candidate search: one unified narrowing procedure, not fixed relevance tiers.**

Searching for a species/build by a specific move (e.g. "weather setter with Encore," a
Prankster support option) resolves through one procedure with up to four steps, applied only
as far as needed:
1. **Check candidate-pool size from the move alone.** A rare, mechanically-gatekept move
   (Follow Me, Rage Powder) already narrows to a small, meaningful set — resolved here, no
   further steps needed.
2. **If the pool is still too large, narrow by team-context need** — what secondary role does
   this slot actually need to fill, informed by what's already locked elsewhere in
   `team_draft` (reuses the theme/core team-need read, Amendment 2026-07-27a).
3. **Or narrow by mechanical fit for executing the move well** — e.g. Prankster for a
   setter/support move needing reliable priority, or sufficient natural Speed for a move that
   needs to land without priority.
4. **Then check opportunity cost per remaining candidate** — does this move actually earn its
   slot for this specific species given what else it could run, or does it get crowded out by
   a better option (the "Encore is learnable but rarely worth it" case).

This replaces an earlier, incorrect three-tier "relevance gradient" framing (rare/gatekept vs.
common-but-situational vs. common-and-irrelevant) — that framing described outcomes, not the
actual mechanism; the real process is one procedure that different moves simply need
different amounts of, based on how large their candidate pool starts out.

**Delivery mechanism matters, not just move identity, when matching candidates.** Two species
with the identical move can have entirely different reliability profiles depending on how
that move gets its effect: a Prankster-based user of a move gets priority but is blocked by
Dark-type immunity, Armor Tail, and Queenly Majesty; a naturally-fast non-Prankster user of the
same move has no such blocks but can simply be outsped by something faster. This applies
symmetrically to alternative solutions for the same functional need — e.g. Thunder Wave
(permanent, single-target, blocked by Ground-immunity/Good as Gold/Dark-type-Prankster-
immunity/Armor Tail-Queenly Majesty) versus Tailwind (team-wide, temporary, not subject to any
of Thunder Wave's specific blocks) are two different-reliability-profile answers to the same
"does my team act first" need, not interchangeable options — and which one a given support
Pokémon actually offers is often simply fixed by its own movepool, not a live optimization
choice.

**Never duplicate a functional role within one set, except to cover a specific, nameable
scenario.** Running two moves that satisfy the same functional need on the same Pokémon
(Rain Dance stacked on an automatic Drizzle-setter; two speed-control moves on one set) is a
default violation, not a reasonable redundancy, unless the second move covers a distinct,
named failure case the first doesn't — e.g. Alolan Ninetales' own Speed letting it
re-establish weather after a mid-turn change (a switch-in or same-turn Mega Evolution) before
any attacker acts that turn, distinct from its passive Snow Warning trigger; or Whimsicott
running both Stun Spore and Tailwind specifically to hedge against an opposing Tailwind user.
This check applies at moveset-assembly time, after candidate narrowing (steps 1-4 above) has
already identified a viable species/build.

**Status:** Replaces the tiered relevance-gradient framing with a single procedural model;
establishes delivery-mechanism-aware candidate matching and the redundancy-justification rule
for moveset assembly.

---

### ADR-015 — Amendment 2026-07-28a

**"Default resolution order" is not a separate mechanism from the dependency circle
(Amendment 2026-07-27c) — it names the residual sequence once no requirement forces
anything, and that residual case is vanishingly rare in practice.**

When nothing about role, archetype, or an already-locked attribute forces a specific choice,
resolution follows a natural order: role/archetype → species (jointly with ability,
resolvable from either direction — a chosen ability narrows to a small species pool, or a
chosen species narrows to at most a few real ability options with a clear best pick or a
usage-based tiebreak) → moves → stat spread/item. By the time spread/item is reached, enough
is already locked that the choice is driven by what came before it.

This is not a competing system alongside the dependency circle — it's what the circle
reduces to when nothing forces anything out of sequence. The moment any real requirement
exists (a role mandating a specific move, an archetype mandating a specific ability), it
fires immediately via the same circle mechanism (2026-07-27c), regardless of where it falls
in the "default" sequence.

**In practice, true unconstrained default order essentially only applies to a single
completely unseeded first slot.** The moment any Pokémon exists on a team, theme/core
detection (Amendment 2026-07-27a) already produces inferred role requirements for remaining
slots — every subsequent slot inherits a real requirement from what's already locked, not a
blank default order. Even a first slot is rarely truly unseeded, since a user rarely opens
with literally zero input.

**Status:** Confirms the dependency circle and default ordering are one mechanism, and scopes
how rarely the unconstrained default case actually arises.

---

### ADR-015 — Amendment 2026-07-28b

**Internal vs. external reasoning unified: both are the same objective (add win condition,
eliminate threats), evaluated against whichever available constraint currently has the most
narrowing power — not two separate phases of team-building.**

Earlier framing (gaps #7/#8) treated "look inward" (core/team synergy) and "look outward"
(threat-coverage, single-point-of-failure) as sequential phases, switching around the
halfway point of team completion. Corrected: they're the same underlying question — what
most improves this team's actual chances — applied to whichever source of constraint still
has real narrowing power left. Sources, roughly in typical order of exhaustion: a slot's own
stated requirement; the rest of the team's unmet needs; the opposing metagame. Early on, the
slot's own requirement and the team's internal needs usually narrow hardest, so that's where
attention concentrates; once those are largely satisfied, they stop contributing much new
narrowing, and the opposing metagame (gaps #7/#8's domain) becomes the source with real
power left. This is not phase-driven or slot-count-driven — a team with strong, unmet
internal requirements keeps building inward regardless of how many slots that takes; a fuzzy
or loosely-defined core exhausts its internal narrowing power quickly and needs to lean
external earlier, not later.

**"Internal" and "external" are relative to whatever's currently being decided, not fixed
categories.** A single slot's own requirement is internal relative to that slot; the rest of
the team is internal relative to the team as a whole; the opposing metagame is external
relative to the team. Same function each time (a source of constraint that narrows the
candidate search), different scope.

**This directly explains the doubles-vs-singles asymmetry (ADR-005).** Doubles has
substantially more built-in mechanical interdependence (spread-move interactions,
redirection, shared speed-control payoffs like Tailwind) — more real internal narrowing power
available before it's exhausted. Singles has comparatively little structural interdependence,
so its internal-narrowing well runs dry almost immediately, and external/threat-facing
reasoning dominates from very early in construction. This is a difference in how quickly
internal value is exhausted, not a difference in kind — retroactively explains why doubles
was the richer, more worthwhile v1 target (ADR-005).

**Team-level redundancy (a direct case of gap #8, single-point-of-failure) is a real but
comparatively low-narrowing-power filter, and must be applied after competence, not before.**
Two slots that reduce to the same underlying vulnerability (e.g. two independent weather-
setters, both failing the instant weather is overwritten/nullified) do not meaningfully
improve team resilience — mirrors the moveset-level redundancy rule (Amendment 2026-07-27f)
one level up. But redundancy only ever eliminates the one specific overlapping candidate,
which is low narrowing power compared to filtering by whether a candidate performs the role
competently at all (which typically eliminates most of a broad pool). Competence must be
checked first; redundancy is then a flag on survivors, not a pre-filter — and it surfaces as
a consideration on a presented alternative, not automatic elimination, since a competent-but-
redundant option (e.g. Politoed alongside Pelipper) is still worth presenting as a real
alternative. As a general rule, a redundant-but-competent pick is preferable to a non-
redundant pick that doesn't actually perform the role — competence is the harder floor to
clear.

**Presentation format (one option vs. a bounded spread) is the same measurement as narrowing
power, read as a UX signal — corrects/refines ADR-018's "propose default + 1-2 alternatives"
into a variable rule rather than a fixed shape.** When available constraints have narrowed
a decision to one clear answer, present one main option (plus perhaps a token alternative) —
presenting a wide spread here would manufacture false choice the actual narrowing doesn't
support. When constraints haven't narrowed much (several genuinely comparable candidates
remain), the honest presentation is the fuller real spread — collapsing to one option here
overstates confidence the narrowing doesn't have. Even "the full spread" stays bounded by
real relevance/strength (same discipline as tier-3's fixed-small-threat-set scope, ADR-015
Amendment 2026-07-25a) — not every technically-valid candidate, just the genuinely
competitive ones.

**Worked example tying the above together:** searching for a second weather-setter (Rain
team, Pelipper already locked) — Rain Dance alone is far too broad a filter (learnable by
dozens of species), so competence-at-the-role narrows first and hardest. Politoed survives
that cut as a genuinely competent option and should be presented as a real alternative, not
pre-eliminated for redundancy with Pelipper — redundancy is flagged only after competence
filtering, as a lower-power, secondary consideration on an otherwise-valid candidate.

**Status:** Unifies gaps #7/#8's internal/external framing into one narrowing-power-driven
model, explains the doubles/singles asymmetry from this same principle, refines team-level
redundancy ordering, and ties presentation format (ADR-018) to the same underlying
narrowing-power measurement.

---

### ADR-015 — Amendment 2026-07-28c

**Pairwise threat classifier: the mechanism behind gaps #7/#8 (team-wide threat-coverage,
single-point-of-failure) and the "shared vulnerability" check (Amendment 2026-07-28b).**

**Inputs:** two full builds (species, moveset, item, ability — not bare species/stats), and
a field condition. Speed order is never a direct input — it's derived from the Speed stats
already present on the two builds given.

**Field condition defaults to a clean neutral baseline, but is contextually swapped when the
matchup is inherently about a condition.** A generic threat check runs neutral by default
(cheapest, broadly applicable). When the matchup is fundamentally about a specific condition
(e.g. Pelipper vs. Mega Charizard Y is a weather question), the classifier runs under the
actually-relevant condition(s) instead. The relevant condition can come from: (a) the team's
own already-locked state (Tailwind already secured), or (b) a reasonable inference about what
the specific opposing Pokémon typically brings with it (a Mega Swampert opponent is likely to
carry its own Rain support) — both are legitimate contextual sources, not just the neutral
default. This applies to damage-affecting conditions (weather/terrain) and separately to
speed-order-affecting conditions (Trick Room/Tailwind), which are a distinct axis (who acts
first, not how much damage lands).

**A build's own already-locked moves/item/ability are real inputs, not just species/stats.**
Will-O-Wisp enabling a burn-and-mitigate outcome, a specific set enabling a stall/attrition
win, a build that hard-walls an attacker outright — these are properties of the *specific
build* in that slot, not the species in the abstract. The classifier always evaluates full,
concrete builds.

**Classification outcome is four-way, not binary:**
1. **Clean kill** — wins in a vacuum, no dependency.
2. **Intentional non-KO answer** — mitigates, stalls, or walls without a clean kill (denial via
   forced switch, attrition over turns, damage reduction) — a legitimate, deliberately-built
   answer type, not a lesser result.
3. **Conditionally-dependent answer** — loses in a vacuum, but a specific condition (own
   team's locked support, or an assumed opponent condition) flips it to a win "most of the
   time" — kept qualitative, not a false-precision threshold.
4. **No answer** — loses regardless. (A no-answer that could theoretically be flipped by some
   hypothetical unbuilt Pokémon is out of scope — not chased.)

**Flagging rule: driven by decision context, not answer type.** The classifier itself is
purpose-agnostic (same species-in/outcome-out function regardless of caller) — whether a
result gets surfaced to the user is entirely the calling context's responsibility, not
something the classifier encodes:
- **Checking an already-locked build against a threat:** intentional non-KO answers (case 2)
  are not flagged — the user already built that set with that intention, this isn't new
  information requiring a decision.
- **Selecting a candidate specifically to answer a threat (not yet locked):** the same case-2
  outcome must be flagged with its caveat plainly stated (e.g. "this only walls them, they'll
  likely switch out") — the user hasn't committed to anything, and presenting it without the
  caveat overstates what's actually being offered.
- **Conditionally-dependent answers (case 3) are always flagged**, regardless of context —
  proposed to the user in the agent's own voice (e.g. "loses in a vacuum, but with Tailwind
  already locked, this turns into a win — a soft threat, not a clean answer") — matching
  ADR-018's proactive-default-plus-real-option pattern, not a silent unilateral accept/reject
  by the agent.

**Symmetry note:** the vacuum-level result (case 1/4, clean kill or no answer under a shared
neutral field) is strictly symmetric — a hard win for A over B necessarily means a hard loss
for B against A, since both describe the same underlying fact. This symmetry does not extend
to conditionally-dependent results (case 3): injecting context relevant to only one side (a
locked team condition, an assumed opponent-specific condition) makes the question inherently
directional, not a reversible relation — flipping perspective without granting the other side
an equivalent context is a different question, not the mirror of the same one. This matches
the classifier's actual intended use (gaps #7/#8): always evaluated one-directionally, from
the fully-known side (our own locked team) toward a representative opposing build, not
symmetrically in both directions.

**Outcome severity gradient applies uniformly across all four classification outcomes
(clean kill, intentional non-KO answer, conditionally-dependent answer, and losses too) —
not a separate scale per case.** Severity is measured by HP remaining after the exchange,
using the real in-game HP-bar thresholds (confirmed: green ≥50%, yellow 20–50%, red <20%,
stable from Gen V onward): Decisive (≥50%), Costly (20–50%), Toss-up (<20%, close enough
that damage-roll variance could flip the result). This replaces an initially-proposed padded
buffer (2/3 instead of the real 50% line, sized against typical chip-damage magnitudes like
Stealth Rock at ~12.5%) — the padding isn't warranted as a *default* given hazard stacking is
uncommon in Champions doubles compared to hazard-heavy 6v6 singles formats. Known, relevant
hazard/status chip (Stealth Rock, Spikes, burn, poison, an ability like Rough Skin) is folded
into the calc call explicitly when actually applicable to the specific matchup, not padded
for generically — same "use the real known value when available, real game-default otherwise"
pattern as the field-condition contextual swap-in.

**Two gaps confirmed in the raw calc output, requiring explicit handling on top of it —
triggered only when a known, applicable specific exists, not run speculatively by default:**

1. **Contact-punish abilities/items are not reflected in the calc's damage output.** A
   "guaranteed OHKO" via a contact move against a confirmed Rough Skin/Iron Barbs/Flame
   Body/Static/Rocky Helmet-type defender omits real damage the attacker actually takes back
   — this should be folded into severity classification (turning an apparent Decisive result
   into Costly) specifically when the defender's ability/item is confirmed and the move
   actually makes contact. Not checked as a standing default — same "known and applicable
   specific overrides the baseline" pattern as hazard/status chip (this amendment, above).

2. **Multi-hit move "guaranteed" results bake in an assumed, not-actually-guaranteed hit
   count.** The calculator defaults to an assumed number of strikes per multi-hit move
   (e.g. Population Bomb assumed at 10 hits, ~34.86% real likelihood without Wide Lens;
   Bullet Seed assumed at 3-of-5 unless Skill Link is confirmed, which locks in a true 5). An
   apparent "guaranteed OHKO/2HKO" resting on an unconfirmed high hit count is not reliably
   Decisive — it should be treated as closer to Toss-up/conditional unless the specific build
   actually confirms the higher hit count (Skill Link, Wide Lens).

**Confirmed already correct, no extra handling needed:** immunities (Dry Skin, Lightning Rod,
Armor Tail blocking Fake Out, etc.) correctly return 0% from the calculator; recoil damage
against the attacker is already included in its output.

**Status:** Establishes the pairwise threat classifier as the concrete mechanism for gaps
#7/#8 (single-point-of-failure/team-wide threat-coverage) and the shared-vulnerability check
(Amendment 2026-07-28b) — resolves how "does this team have an answer" is actually computed,
not just when it's checked.

---

### ADR-015 — Amendment 2026-07-28d

**Role Compendium: scope, membership model, and category structure.**

**Purpose, settled first since it shapes everything else:** the compendium exists to serve
"I need something that fulfills a specific functional role" (Weather Setter, Redirection,
Trick Room Setter). It is not the mechanism for "I just need something strong" — that's
already served directly by stats/coverage search against real usage data (the mechanical-
interpretation-then-multi-axis-search procedure, Amendment 2026-07-27a/f), with no category
needed. A category only earns a place in this model if it genuinely helps narrow a role-
specific search — not for taxonomic completeness. This is why "generalist attacker" isn't a
doubles category: its singles counterpart, "Wallbreaker," is defined in opposition to a
"Wall" role that doesn't exist in doubles (no forced matchups, per below) — with no role to
break through, there's nothing for the category to be named against.

**Source role: taxonomy/category seed only — never membership or tier truth.** Two real
Smogon community compendiums (VGC Reg M-A, SV OU) were reviewed directly. Both are useful
for discovering which functional buckets real competitive players consider worth naming, and
nothing more. Confirmed unreliable for membership and ranking, via multiple concrete cases:
Volcarona ranked "Red" despite being the only relevant Quiver Dance user in the format;
Milotic listed as a "Green" attacker despite its actual strategy being Hypnosis-stall, not
offense; Maushold's real attacker case (Technician + Population Bomb + Tidy Up) absent
entirely; weather/condition "beneficiary" buckets padded with popular Pokémon that have no
differential mechanical benefit from the condition at all (Mega Froslass, Alolan Ninetales,
Mega Gardevoir — good, popular attackers on those archetypes' teams, not genuine beneficiaries
of the condition itself); a freeze-chance-driven "Green" ranking for a 10% incidental Blizzard
proc nobody actually plays around. This is systemic to how the source ranks, not isolated
error — do not import tier/rank from the source under any circumstance. Membership and
ranking are both independently computed per the model below.

**Doubles vs. singles determines the top-level category split — not battle length or dex
size (an earlier, incorrect hypothesis this amendment corrects).** In singles, an opponent
can force an unfavorable matchup onto a fixed target, making sustained defense ("Wall") a
real, distinct role. In doubles, target selection is always a choice, so a slow/tanky
Pokémon isn't filling a structural role the way a singles wall does — it's a build trait, not
a category. This is why doubles has no "Defensive" top-level category and singles does;
"Support" vs. "Utility" naming is a cosmetic difference only.

**Offensive membership — a conjunction of criteria, not any single one:**
1. A genuine setup mechanism (move or ability) is present.
2. Base stats support the resulting stat line — **unless** access to the mechanism is itself
   rare enough to be its own signal (the same rarity-substitutes-for-stat-gating principle as
   the move-narrowing procedure, Amendment 2026-07-27f's step 1).
3. Real, usable attacking moves exist to convert the boosted stat into actual damage — access
   to a setup move alone (e.g. Swords Dance with no worthwhile physical coverage) is not
   sufficient.
4. **The set as a whole must actually exploit what's provided** — a nominally offensive move
   or ability present alongside a set whose real strategy is something else entirely does not
   qualify (Milotic/Coil: Attack boost present, but the set's actual plan is Hypnosis-stall,
   not attacking). This is the general test, stated once: does the rest of the set exploit
   this, or is it just present.
5. **Conditional-trigger abilities (e.g. Competitive) only count if the set's strategy
   actively engineers or reliably benefits from the trigger** — not merely possesses the
   ability. Contrast with Defiant users (e.g. Kingambit): these already qualify as attackers
   on base stats/moves alone, with Defiant as a bonus, not the sole justification — so no
   special "actively engineered" handling is actually needed there; it only matters when an
   ability is the *only* offered justification (Milotic's Competitive) and the base
   stat/moveset case otherwise fails.

**Support membership — three criteria, since support is inherently other-directed (no
"self-exploitation" test applies the way it does for offense):**
1. **Does an ability directly provide/enable the function?** Ability-based delivery is
   inherently more reliable than move-based (automatic, no turn cost, no moveslot
   competition, not preventable by the opponent acting first) — ranks above a move-based
   version of the same function when both exist (explains why weather-setting skews
   overwhelmingly ability-based; rare move-based cases like Alolan Ninetales tend to be
   secondary/insurance on a Pokémon whose primary identity is something else, not a
   competitive primary delivery method).
2. **How likely is successful execution?** Covers delivery-mechanism reliability (priority
   source and its failure modes, per Amendment 2026-07-27f — Prankster-priority vs.
   natural-Speed vs. no-priority; Thunder Wave vs. Tailwind's differing block conditions) and
   role-specific structural requirements the function itself imposes (a Trick Room setter
   needs bulk, since going last under normal turn order means it must survive to act).
3. **Does it stack a genuine second supportive role?** The existing primary/secondary
   multi-role structure (Amendment 2026-07-27a/e — Pelipper, Politoed, Sableye) is itself a
   real quality signal — covering two functions in one slot is more valuable than one,
   equally well.

**Modifier tags, distinct from primary-role categories.** Some abilities (Prankster,
Regenerator) don't define a role themselves — they modify how well or how safely an existing
role is executed, and attach to whatever primary role a build actually has (an offensive
pivot, a wall, a generalist attacker) rather than becoming their own Offensive/Support/
Defensive bucket. Regenerator specifically was considered for its own category and rejected
on this basis — it doesn't define what a Pokémon does, only how safely it can keep doing it.

**Weather/condition "Beneficiary" buckets are usage-discovered mechanical facts, not a
separate third membership type, and exclude setters by convention.** Two genuine membership
types exist: (a) catalogued, directly-enumerable interactions (Swift Swim, Electro Shot,
Hurricane — found by searching ability/move tables directly), and (b) obscure-but-real
interactions discoverable only through usage (Mega Meganium's ability+typing interaction
under Rain, Palafin's high Water-move density) — real mechanisms, just not ones a direct
table search would surface, so usage data's role here is *discovery*, not narrowing. A
condition's own setters (Mega Froslass, Alolan Ninetales under Snow; any Trick Room setter)
are excluded from the Beneficiary bucket by convention unless they independently qualify
through (a) or (b) — a setter inherently plays on that archetype's team already, so inclusion
in "Beneficiary" on that basis alone is circular, not independent evidence.

**Category emergence from future regulation changes is not a new mechanism.** A new category
(e.g. Terrain-based roles, if a Terrain-setting ability ever enters Champions' legal pool)
should surface via the same category-level diff-on-regulation-change mechanism already
designed for contingent-value detection (ADR-016 Amendment 2026-07-26b) — not manually
anticipated ahead of time.

**Singles compendium, sketched now (per Amendment 2026-07-27a/28a's doubles-first
sequencing, ADR-005) though not consumed until singles support is built:**
- Offensive: same membership test as doubles, largely transferable as-is (Wallbreakers,
  Choice-item users, Setup sweepers, Priority, plus Wallbreaker specifically since singles
  has a Wall role to break).
- Support/Utility: same three-criteria test as doubles, but relevant sub-roles shift toward
  entry hazards and hazard control (Stealth Rock, Spikes, Toxic Spikes, Sticky Web, Defog,
  Rapid Spin, Magic Bounce, Court Change) — far more load-bearing in longer 6v6 games than in
  Champions doubles.
- Defensive (does not exist in doubles, per the top-level split rationale above):
  - Walls — membership via base stats, defensive-relevant abilities, and status access
    (e.g. a genuine Hypnosis-stall set).
  - Pivots — membership via move access alone (U-turn/Volt Switch/Flip Turn/Parting
    Shot/Teleport), then sub-split into offensive vs. defensive pivot depending on what the
    rest of the kit actually does — same "what does the rest of the set do" test as
    everywhere else.

**Regulation change can also shift ranking/relative standing within an already-existing
category, independent of category emergence (see above) or individual build/cache
invalidation (Amendment 2026-07-26b, ADR-016).** Two distinct sub-cases:
- **Absolute capability change:** a Pokémon gains real new move/item access that improves its
  own execution of a role it already belongs to (e.g. Alolan Ninetales gaining a genuine Light
  Clay pairing for Aurora Veil, if Mega Froslass's Mega Evolution item-lock prevents the same
  pairing).
- **Relative/comparative devaluation:** an existing member's standing declines purely because
  a new, better competitor enters the same category — nothing about the existing member
  changes at all (Grimmsnarl's arrival in M-B making Sableye a comparatively weaker dual-
  screens pick, without any change to Sableye itself).

This confirms two hard requirements for whatever ranking/tier mechanism resolves the still-
open item above: (1) ranking must be recomputed on regulation change, using the same trigger
already established for category-diff/contingent-value detection (ADR-016 Amendment
2026-07-26b) and cache re-validation — not a separate schedule; (2) ranking must be
comparative across all current members of a category, never an absolute per-Pokémon score
computed in isolation, since a member's standing can change entirely due to someone else's
introduction rather than any fact about the member itself.

**Status:** Fully resolves the Role Compendium's scope (taxonomy seed only), membership
model (offensive conjunction test, support three-criteria test, modifier tags, beneficiary-
bucket discovery vs. narrowing), and top-level category structure (doubles/singles split
rationale corrected from an earlier, wrong hypothesis). Ranking/tier computation itself
remains open — flagged, not resolved: our own tier should likely draw on the pairwise threat-
classifier's severity gradient (Amendment 2026-07-28c) and/or real usage/tournament placement
data already pulled, but which signal(s) and how they combine into a category-membership tier
has not been decided.

---

### ADR-015 — Amendment 2026-07-29a

**Candidate discovery discipline — corrected after repeated failures during mock-run
testing (2026-07-28/29 sessions).**

**Search must start from regulation-scoped, structured data — never a generic "who learns
move X" query.** Generic web search repeatedly missed real, legal, currently-used candidates
(Mega Clefable for Redirection; Volcarona, Mega Scovillain, Vivillon, Ariados for Rage Powder,
found only after being told to search Champions-specific usage data directly rather than a
curated third-party "top picks" list). A curated list from any single source — even a
seemingly authoritative one — must never be treated as exhaustive without independently
confirming it, per the standing "verify against the primary source" practice (already a
tracked working preference). Where the authoritative source itself is inaccessible (see
tool-limitation note in master_project_log.md), this must be stated as a real gap, not
papered over with a lower-quality substitute presented as equivalent.

**Mega-form evaluation must be explicit and bidirectional, but only when the specific
mechanism in question genuinely applies to both forms.** Missed in both directions this
session: Mega Tyranitar's stat/sequencing advantage over base Tyranitar for Sand-setting was
initially collapsed into one entry; conversely, Mega Clefable was initially treated as a
Redirection candidate by default access-inheritance, when its real kit (Magic Bounce, Calm
Mind attacker) abandons the role entirely. The correct rule: check both forms independently,
but only meaningfully split them when both have a genuine, comparable claim to the mechanism
being evaluated — a base form's nominal, non-competitive access to a move/ability (e.g. base
Charizard's Sunny Day vs. Mega Charizard Y's Drought) does not warrant a full second
candidate entry.

**Usage/real-team data is legitimate only for discovery and legality confirmation — never as
ranking evidence.** Repeatedly misused this session as implicit evidence for a candidate's
quality (citing "real teams do X" as if it were a mechanical argument) rather than purely to
confirm a candidate exists and is legal. This directly contradicts the ranking model's
foundational premise (ADR-015 Amendment 2026-07-28d): ranking must be independent of
popularity, which measures team-synergy fit, not role-execution quality.

**Near-universal-access moves cannot be used to narrow or differentiate a candidate field.**
Protect is learnable by nearly every Pokémon; treating "has Protect" as a differentiating
factor (as initially attempted for setup-sweeper survival) provides zero narrowing power and
must be excluded from consideration on that basis alone — the same principle already
established for broadly-learnable moves in the search-narrowing procedure (Amendment
2026-07-27f), now confirmed by a concrete failure case.

**Status:** Corrects repeated process failures in candidate discovery, observed across four
mock-run role evaluations (Weather Setter Rain/Sand, Redirection, Swords Dance Attacker).

---

### ADR-015 — Amendment 2026-07-29b

**Refined membership/ranking criteria, corrected through extensive mock-run testing.**

**Offensive membership collapses to the same 3-criterion structure as support (Amendment
2026-07-28d), not a separate 5-part test.** Restated: (1) does an ability directly reinforce
the role's actual function (not merely exist) — e.g. Huge Power/Adaptability amplifying
output, Stance Change preserving stat boosts across a forme switch — distinguished from an
ability that is real but irrelevant to the payoff (Prankster does not boost the attacking
move that follows a self-buff, since it only affects the status move itself — a real,
repeated confusion this session, since Prankster's benefit for weather/screens moves comes
from the move's own effect being instant, while a setup move's payoff is deferred to the next
turn, which Prankster never touches); (2) does the moveset deliver the payoff and address
execution risk (see below); (3) does a genuinely distinct secondary function exist, unrelated
to the primary payoff (e.g. Intimidate on a Swords Dance user is a real secondary, not a
reinforcement of the setup-sweep function itself).

**Setup/sweeper roles (deferred payoff) have a distinct two-axis execution-risk model,
unlike instant-payoff roles (weather-setting) or same-turn-execution roles (redirection).**
A candidate must solve at least one of: (a) survive the setup turn to still be alive to
attack, or (b) outspeed/have priority on the follow-up attack to actually capitalize —
**only one is required for membership, but both independently raise ranking.** Protect cannot
satisfy (a): it cannot be used in the same turn as the setup move, so "has Protect" never
addresses setup-turn survival risk (a real, repeated error this session) — genuine solutions
to (a) are bulk/typing, a damage-reducing or deterrent ability (Rough Skin, Weak Armor,
Flame Body), a guaranteed damage-negation effect (Disguise), or a persistent decoy mechanism
distinct from Protect (e.g. Substitute, which can absorb hits across multiple turns).

**Tier bar, tightened after early over-generosity: "Excellent" requires an unconditional,
mechanism-guaranteed solution — not merely adequate stats — and, where relevant, the *type*
of mechanism at the top of a role matters, not just the presence of one.** For setup
sweepers specifically, the line between Excellent and Good is not "has priority" alone (many
Good-tier entries have real priority) — it is **priority backed by an ability that further
amplifies that specific move's damage** (Technician/Adaptability/ability-stacking on Bullet
Punch/Sucker Punch), versus priority with no amplifying mechanism (real but comparatively
modest output). Raw damage magnitude must be estimated (rough BP × effective stat math is
sufficient at scale — exact calc verification is not required nor practical across dozens of
candidates) and weighed alongside execution reliability; a mechanism that reliably executes
but produces weak output (e.g. a guaranteed free turn on a low base-Attack Pokémon) does not
automatically earn the top tier over one with both reliable execution and strong output.

**Doubles specifically imposes a stricter bulk requirement than singles for setup-turn
survival, due to focus-fire risk (two attackers, or an attacker plus a spread move, in one
turn).** A stat/ability profile that would clear survival easily in singles may not in
doubles — this must be checked as its own, format-specific factor, not assumed equivalent
across formats.

**Membership strictness must scale to the raw breadth of the candidate pool, with a target
total of roughly 15-20 candidates spread as evenly as practical across three tiers** (fewer
where the raw pool is inherently small — e.g. an ability held by only 2-3 species). A broadly
learnable mechanism (e.g. Swords Dance, dozens of real legal learners) requires the
membership test itself to carry much more of the filtering burden, or tiers become
uselessly large and stop differentiating anything (observed directly: an early pass placed
14+ candidates in "Excellent" before the bar was corrected).

**A real, better move/strategy existing elsewhere for a given species (e.g. Shell Smash over
Swords Dance on Barbaracle; Dragon Dance over Swords Dance on Mega Charizard X) is a genuine
opportunity-cost fact, but is out of scope for single-move membership/ranking exercises** —
it belongs in the actual move-selection loop (the "best remaining move" procedure,
established much earlier), not in evaluating candidacy for one specific move in isolation.

**Status:** Refines and unifies the offensive/support membership tests, establishes the
two-axis execution-risk model for deferred-payoff roles, and tightens the tier bar with a
concrete target scale — derived from repeated correction across the Weather Setter,
Redirection, and Swords Dance Attacker mock runs.

---

### ADR-015 — Amendment 2026-07-29c

**Mega Evolution's item-slot lock is a genuine trade-off, not merely a Mega-vs-base stat
comparison.** Mega Evolution locks the item slot to the Mega Stone — a base form can access
items (e.g. Life Orb) its own Mega counterpart structurally cannot. This means a base form is
sometimes the mechanically stronger pick for raw output despite lower stats, not just a
fallback when a Mega isn't used (confirmed concretely: base Blaziken/Scizor with Life Orb;
Mimikyu with Life Orb). This must be checked explicitly whenever comparing a base form
against its Mega, not assumed away as the Mega automatically superseding the base.

**Shared vs. divergent abilities across a base/Mega pair must be verified per form, never
assumed.** Confirmed failures both directions this session: assumed Mega Gallade retained
base Gallade's Sharpness (it does not — Mega Gallade has Inner Focus instead); dropped base
Scizor from consideration despite it sharing Technician identically with its Mega form. The
rule is simple but was violated repeatedly: check each form's actual ability list
independently, every time, regardless of what seems likely.

**Status:** Narrow but concrete corrections to Mega-form comparison discipline, arising from
specific verification failures during the Swords Dance Attacker mock run.

---

### ADR-015 — Amendment 2026-07-29c — Scope broadened to typing (2026-07-29)

This amendment's per-form verification discipline ("check each form's actual ability list
independently, every time") is confirmed to apply equally to **typing**, not just abilities —
surfaced by a live error during reconciliation design (ADR-020): Mega Staraptor's typing
(Flying/Fighting) was asserted from memory as its base form's typing (Normal/Flying) without
checking, a second confirmed live failure-mode-#1 instance (see master_project_log.md). Any
type-changing Mega (Staraptor, Charizard X, Gyarados, Altaria, others) requires the same
per-form verification already mandated for abilities. ADR-020's tier-1 reconciliation check is
built form-aware from the start on this basis, rather than assuming a single typing per
species.

**Status:** Broadens this amendment's stated scope from abilities to abilities-and-typing
together. Does not change the original ability-specific findings (Mega Gallade/Sharpness,
base-vs-Mega Scizor/Technician).

---

### ADR-015 — Amendment 2026-07-29d

**Trick Room attacker evaluation: relative speed, SP-investment mechanics, and setup-move
cost — derived from extensive mock-run correction (Trick Room Attacker role, 2026-07-29).**

**"Slow enough to benefit from Trick Room" is relative to current top-threat speed tiers,
not an absolute base-Speed threshold — confirmed via a real correction, not just restated
from the earlier weather-beneficiary precedent.** A Pokémon with base Speed at or near a
common benchmark (e.g. 100) still gains a real, relevant advantage under Trick Room against
the many threats faster than that benchmark, even though the same stat reads as "fast" by
ordinary standards (mirrors the Mega Gardevoir precedent already established for theme/role
detection, Amendment 2026-07-27a). An absolute low-Speed cutoff (e.g. treating base Speed
~100 as automatically disqualifying) incorrectly excludes real, legitimate candidates —
confirmed directly: Mega Kangaskhan (base Speed 100) was wrongly excluded on this basis, then
correctly reinstated.

**Deliberate SP investment can lower effective Speed far below a Pokémon's base stat,
widening the real candidate pool beyond naturally very-slow species.** A Trick Room build
on a middling-to-high base-Speed Pokémon (under roughly 80, and workable even at 100 with
more deliberate investment) typically uses zero Speed investment plus a Speed-hindering
nature — this both guarantees acting first under Trick Room (well below the raw base stat)
and frees the un-invested SP for bulk instead, a genuine double benefit, not a trade-off.
This means role membership should be evaluated against a Pokémon's effective, buildable
Speed under a real Trick Room SP allocation, not its raw base stat read in isolation.

**In a deferred-payoff, turn-limited role (Trick Room lasts ~5 turns), a manual setup move
is a genuine cost, not a free bonus — inherent, automatic, no-turn-cost damage
amplification should rank above access to a setup move that spends one of very few
available turns.** This is a sharper, role-specific version of the general "does this
actually pay off, or just sound like it should" discipline — confirmed via direct
correction: Hatterene's case rested partly on Calm Mind access, which was incorrectly
credited as a plus before being correctly identified as a cost specific to this
turn-limited role. Distinguish an inherent multiplier (an ability like Pixilate, Mega
Launcher, Huge Power, Iron Fist — automatic, every relevant turn, no setup cost) from a
manual setup path (a move that must be selected and pays off only afterward) when ranking
within a deferred-payoff role specifically.

**Relative magnitude of an inherent multiplier matters, not just its presence — confirmed
via direct comparison.** Iron Fist (20%), Pixilate (20%), Mega Launcher (50%), Huge Power
(100%), and Parental Bond (~effective 125% total) are not interchangeable just because each
is "an inherent ability boost" — the actual magnitude must be compared directly when ranking
within a tier, the same discipline already established for rough BP-based output comparison
in the Swords Dance run (Amendment 2026-07-29b), now confirmed to matter for ability-based
multipliers too, not just move base power.

**Status:** Extends the setup-sweeper/deferred-payoff model (Amendment 2026-07-29b) with
role-specific refinements for Trick Room specifically, derived from repeated correction
during mock-run testing.

---

### ADR-015 — Amendment 2026-07-29e

**Usage-data consistency check — a real inconsistency caught and corrected during mock-run
testing (2026-07-29).**

Usage/real-team data must be treated identically regardless of which conclusion it happens
to support — it is discovery/legality evidence only (Amendment 2026-07-29a), never ranking
evidence, and this applies the same way whether the candidate in question seems intuitively
strong or intuitively weak on paper. Confirmed failure case: heavy real usage on Mega
Gardevoir (an already-expected strong candidate) was treated as confirming evidence to trust
and mechanically verify; heavy real usage on Mega Kangaskhan (a candidate that initially
failed an incorrect absolute-Speed gate) was instead treated as a "false positive" requiring
correction via the mechanical model — two opposite epistemic stances applied to the same
kind of signal, based on which candidate's outcome had already been assumed rather than
checked. The correct, single standard: usage always means "this is real and worth verifying
mechanically" — never "this confirms my prior expectation" in one direction and "this must
be explained away" in the other. Once verified, both candidates in this specific case turned
out to have genuine, real mechanisms (relative-speed advantage under Trick Room) — the
usage signal was equally valid for both from the start; only the mechanical verification
step was being applied inconsistently.

**General principle:** when a candidate's usage-confirmed real-world presence conflicts with
an initial mechanical read, treat this as a signal to re-examine the mechanical model for a
missed factor (as happened here — the absolute-vs-relative Speed gate was wrong) rather than
either accepting the usage data as sufficient on its own, or dismissing it as noise, in
either direction.

**Status:** Records a specific, confirmed reasoning-consistency failure and its correction,
generalized into a standing check against directionally-biased use of usage/discovery data.

---

### ADR-015 — Amendment 2026-07-29f

**Sleep-inducing status role: delivery-mechanism-specific criteria, and two role-general
principles confirmed via mock-run correction (2026-07-29).**

**Real delivery mechanisms and their distinct reliability profiles, confirmed directly:**
Spore (100% accuracy) — but confirmed that all four Spore-line species (Breloom, Amoonguss,
Parasect, Toedscruel) are unavailable in Champions; this pathway does not exist in the
current compendium at all. Sleep Powder (75% accuracy, blocked by Grass-types/
Overcoat/Safety Goggles/Insomnia/Vital Spirit/Sap Sipper). Hypnosis (60% accuracy, blocked
by Dark-types). Yawn (100% accuracy to land, but the sleep effect is delayed a full turn —
the opponent can simply switch out during the delay window, a fundamentally different and
more easily-countered profile than an immediate-effect move, regardless of that 100% landing
rate).

**Criterion weighting is delivery-mechanism-dependent within a single role, not uniform —
confirmed via two concrete corrections:**
- **Speed matters enormously for immediate-effect delivery (Sleep Powder, Hypnosis) since
  landing the move before being hit denies the opponent an action entirely** — but is
  largely irrelevant for Yawn specifically, since the delayed effect means acting first
  buys nothing toward the actual lockout; Yawn's real counterplay is the switch-window
  during the delay, a team-composition question, not a stat the user itself can solve.
- **Bulk's relevance is conditional on how imperfect the move's accuracy is** — a real,
  secondary "insurance against a missed roll" asset that scales with miss probability (real
  and meaningful for Sleep Powder's 75%, would matter more for 60%, and is nearly irrelevant
  for a near-guaranteed-accuracy case like Vivillon's Compound-Eyes-corrected Sleep Powder).
  This is not the same kind of reinforcement as an ability/mechanism that improves execution
  directly — it's a lesser, fallback-case asset, and should not be weighted equally against
  an active execution-improving mechanism (Chlorophyll's speed advantage, Compound Eyes'
  accuracy correction) when ranking within a tier.

**Trapping abilities only reinforce delivery mechanisms that have an escape window to
close** — confirmed via direct correction: Shadow Tag provides real, major reinforcement
paired with a delayed-effect move (Yawn, closing the switch-window before the delayed sleep
triggers), but provides essentially no reinforcement paired with an immediate-effect move
like Hypnosis, which has no window to escape through in the first place. A reinforcement
mechanism must be checked against what specific failure mode it actually addresses, not
credited generically as "a strong ability" independent of the delivery mechanism it's paired
with.

**Confirmed accuracy-boosting mechanisms are real, direct criterion-2 reinforcement and were
initially missed by not checking each candidate's own full kit directly:** Compound Eyes
(+30% accuracy, checked directly against Vivillon rather than assumed) and Coil (+1 accuracy
stage among its effects, checked directly against Milotic) both meaningfully improve
execution reliability and were confirmed via direct verification, not assumption — both had
been initially missed by relying on partial recollection rather than checking the specific
candidate's kit.

**Status:** Establishes delivery-mechanism-specific criteria weighting for this role
(reusable pattern: check whether a general criterion's precondition actually holds for the
specific delivery mechanism in question, rather than applying it uniformly across a role).

---

### ADR-015 — Amendment 2026-07-31a

**Turn-economy correction to the pairwise matchup classifier (Amendment 2026-07-28c) —
charge and recharge moves.**

Two additional gaps confirmed in classify_matchup's raw calc output, same category as
Amendment 2026-07-28c's original contact-punish and multi-hit-count gaps — calc computes
per-hit damage assuming the move lands this turn unconditionally, which is wrong for two
move categories:

**Charge moves** (Solar Beam, Solar Blade, Sky Attack, Razor Wind, Skull Bash, Dig, Dive,
Fly, Bounce, Phantom Force, Shadow Force, Sky Drop, Freeze Shock, Ice Burn, Meteor Beam,
Geomancy, Electro Shot — sourced from Pokemon Showdown's data/moves.ts `flags.charge: 1`,
not from @smogon/calc, which has neither flag). A charge move doesn't deal damage on the
turn it's used unless an instant-fire condition is met — verified per-move rather than
assumed uniform: Solar Beam/Solar Blade fire instantly under Sun/Harsh Sunshine, Electro
Shot fires instantly under Rain/Heavy Rain (a genuinely new finding — the instant-condition
mapping is per-move and per-weather-type, not a single shared rule). If the condition isn't
met, the defender gets a full, live turn to act first — checkable within the classifier's
existing single-opponent, single-build frame, since it only needs the two builds already
given. This can flip an outcome entirely, not just delay it (worked motivating case: Mega
Swampert vs. Mega Charizard Y under a neutral field — Solar Beam doesn't fire turn one,
Swampert acts first and wins the exchange outright; under Sun, the naive calc read is
closer to correct).

**Recharge moves** (Hyper Beam, Giga Impact, Blast Burn, Frenzy Plant, Hydro Cannon, Rock
Wrecker, Roar of Time, Eternabeam, Meteor Assault, Prismatic Laser — same source,
`flags.recharge: 1`). Structurally distinct from charge moves: the hit lands on schedule,
but the user cannot act the turn after. Irrelevant if the hit is an outright OHKO. If not,
the following turn is a fully live, guaranteed free action for the opponent already given
to the classifier — a real, additional in-simulation turn-skip (not a lookup, not a
post-hoc flip), since the recharge-user simply has no action available that turn. This
was corrected during implementation to be a genuine in-sim skip (must_recharge state
consumed on the actor's next turn within the same exchange simulation) rather than a
separate "compute normally, then check afterward whether to flip" pass — the latter was
identified during plan review as producing wrong results, since it would let the recharge
user act on the turn it should be unable to.

**Move selection also required a correction independent of the simulation itself**: ranking
candidate moves by raw turns-to-KO could prefer a charge move that looks better on paper
(higher raw damage) over an instant move that actually resolves faster, once the charge
delay is accounted for. Fixed via an effective-turns-to-KO penalty (+1 when charge-delayed)
applied only in the move-selection comparison key — the simulation itself always uses the
real, un-penalized turn count, keeping move-ranking and simulated turn physics deliberately
decoupled so a fix to one can't silently corrupt the other.

**Accepted, stated limitations (not open questions):**
- Power Herb (item-based charge-skip override) is not handled — charge-delay is currently
  evaluated on weather/field alone. A real, known gap, deferred rather than silently missed.
- turn_economy_note is single-valued and attacker(A)-centric: if both sides have a
  turn-economy quirk in the same exchange, only one is surfaced (recharge takes precedence
  over charge if both apply). This is a deliberate, bounded simplification, not a defect —
  consistent with the classifier's original single-opponent scope never claiming to model
  everything about both sides simultaneously.
- No reverse-classify_matchup call is used for the recharge-vulnerability check (an earlier
  design draft proposed this); the in-simulation must_recharge skip, using the same
  already-batched calc results for both directions, was used instead — simpler, avoids an
  HP-reset/recursion risk a literal reverse-call approach would have introduced.

**Status:** Implements the two gaps flagged during Amendment 2026-07-28c's original design
discussion, found post-shipment. 58 tests passing (up from 52), 5 skipped. Classifier's
scope is unchanged — still pairwise, single-opponent, per Amendment 2026-07-28c's original
design; this only corrects what it computes within that frame, consistent with the
contact-punish/multi-hit corrections Amendment 2026-07-28c already documents.

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
`source_tier` (Champions-native / analogous-format / live-lookup, per ADR-007 Amendment 2026-07-25c/ADR-014a),
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
Zone's season-scoping, ADR-007 Amendment 2026-07-25c) — so a build verified months ago may have been checked
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

---

### ADR-016 — Amendment 2026-07-27a

**Confirmed: get_resolved_build does not chain backward through archived regulation files.
This is a real, current gap, not a design choice to leave as-is.**

Confirmed directly (Cursor): `get_resolved_build` resolves the path for the requested
regulation only and returns `None` on a miss — it does not walk into prior regulations'
archived files (e.g. `champions-reg-ma.jsonl`) automatically. Carry-forward currently only
happens when explicitly written via `put_resolved_build(..., carried_forward_from=...)` into
the *current* regulation's file — it is not a live fallback at lookup time.

**Why this matters, concretely:** Smogon's Champions Strategy Dex pages are additive and
per-debut-regulation, not cumulative — the M-B page only covers Pokémon that debuted in M-B;
a Pokémon available since M-A (e.g. Charizard-Mega-Y) keeps its writeup on the M-A page
indefinitely, even after M-B ships, since nothing is removed from Champions' legal pool so
far (ADR-015 Amendment 2026-07-26d). Without a lookup-time fallback, a query for the current
regulation's cache will silently miss a real, valid, still-applicable writeup that happens to
live in an older regulation's archived file — even though the underlying build is still
completely legal and current.

**Resolution:** `get_resolved_build` should walk backward through archived regulation files
(current → most recent prior → etc.) on a miss, not rely solely on explicit
`carried_forward_from` writes into the current file. Explicit carry-forward writes remain
useful (e.g. once a build has been re-validated for the current regulation, per ADR-016's
existing re-validation requirement) but should not be the only path to finding an
older-regulation entry — the chain-lookup is what prevents silently missing real, still-valid
data.

**Separately, confirmed: writeup coverage is not tied to regulation-change events at all.**
Smogon can publish a new writeup for a Pokémon available since an earlier regulation at any
time, independent of whether a newer regulation has since launched — unlike legality data,
which only changes when the regulation does. Re-scanning for new writeup coverage across all
regulation pages should happen on-demand ("when convenient"), not on a fixed schedule and not
tied to the regulation-change trigger already established for legality/current-availability
checks (ADR-015 Amendment 2026-07-26b, ADR-016 Amendment 2026-07-26b's contingent-value
diff). The existing analogous-format (SV) fallback covers the gap in between rescans, so
there's no urgency requiring a standing background process.

**Status:** Identifies a real gap in the current implementation (no chain-lookup on cache
miss) and resolves the separate open question of writeup-rescan cadence (on-demand, no fixed
schedule). Implementation of the chain-lookup fix is a follow-up task, not yet built.

---

### ADR-016 — Amendment 2026-07-27a — Status update (2026-07-29)

**Chain-lookup implemented, committed, and pushed.** The gap this amendment identified
(get_resolved_build not walking backward through archived regulation files on a miss) is
resolved in code: REGULATION_ARCHIVE_ORDER + regulation_lookup_chain() in recommender/ids.py,
get_resolved_build(..., chain=True) walking tags newest→oldest and recording
found_in_regulation, chain=False preserved for direct-only lookups. Covered by
tests/recommender/test_resolved_builds.py::test_chain_lookup_from_archived_ma.

**Status:** Implemented. Supersedes this amendment's prior "not yet built" framing —
the design conclusion stands, the gap it describes no longer exists in the codebase.

---

## ADR-017: RecommenderState extensions — team theme/core, granular locking, constraint scope

**Team theme/core.** `RecommenderState` gains two related concepts, populated by a detection
process (see ADR-015 Amendment 2026-07-27a for the mechanism):
- `core`: the working set of team slots and their inferred roles. Always populated once
  theme/core detection runs — even when no clean named archetype emerges (e.g. Mega
  Staraptor's Contrary/weakness-driven needs), `core` still holds the derived set of needed
  support functions.
- `archetype`: an optional named label (Rain, Trick Room, etc.), set only when a strong,
  clean pattern actually emerges. Not every team has one, and that's a valid, expected
  outcome, not a detection failure.

`core` is not a separate structure alongside `team_draft` — it *is* `team_draft` in its
earliest, most-unresolved state: a user-named seed Pokémon becomes a slot with only `species`
locked; each inferred needed role becomes a slot with only `role` locked. Detection and
steering use the same underlying representation throughout.

**Granular, per-attribute locking.** Replaces the single `locked: bool` on each slot with
`locked_fields: {role, species, item, moveset, spread}`, each independently toggleable.
Rationale: different attributes get "decided" at different points and for different reasons,
and users change their minds about one without wanting to reopen all of them (e.g., locking a
moveset while still being open to a different species that can run it).

**Default lock rule:** lock exactly whatever was the actual stated or inferred reason a slot
exists, nothing more. A user-named species locks only `species`. A theme-inferred role locks
only `role`. Nothing gets locked by inference beyond what was actually grounded in a real
stated or derived reason.

**Reason-tracking for cascading revisability.** Every inferred value (locked field, archetype,
a core's needed-role entry) must record *why* it was set, not just its current value. This
lets a later reversal ("actually, Sun instead of Rain") correctly cascade only to the things
that depended on the reversed reason — a role-locked slot that existed *because* of the old
archetype gets revisited; a species-locked slot the user wants regardless of weather does not.
This generalizes the existing `still_active` mechanism already present on `constraints` to
apply project-wide, not just to the constraints list.

**Constraint scope: per-slot vs. team-wide, and a groundedness spectrum.** `constraints`
gains a `scope: per_slot | team_wide` field. Team-wide freeform constraints (monotype, "all
Eeveelutions," "girlypop Pokémon only," "all monkeys") use the existing loose `predicate: str`
shape — no new structured field needed, since these are inherently open-ended and can't be
enumerated in advance.

Each constraint additionally carries a groundedness label reflecting how it can actually be
satisfied, not a value judgment on its legitimacy:
- `mechanically-checkable`: a real data field exists (monotype/type, ability/move-based
  rules).
- `enumerable-but-uncoded`: a real, definite category exists but isn't sitting in a data field
  yet (Eeveelutions, "monkeys") — derivable once, then checkable like anything mechanical.
- `judgment-only`: no data-groundable definition exists at all ("girlypop") — resolved by
  LLM judgment, with that fact stated plainly rather than implied to be as grounded as the
  others.

**Edge case, not a fourth category:** some constraints have both a mechanical interpretation
and a plausible looser judgment-based one that could disagree (e.g. "red Pokémon" — an
official color categorization exists, but a visual/aesthetic read might diverge from it).
Check the mechanical interpretation first, but surface the ambiguity rather than silently
assume the official categorization is what was meant.

**Status (2026-07-29):** Implemented. RecommenderState migrated to the Attr-per-field model:
`Slot` holds `Attr[T]` wrappers (value/locked/reason/still_active) for role, species, item,
moveset, spread, replacing the prior single `locked: bool`/`set: PokemonSet`/`slot_index`
shape. `core` is a computed helper over `team_draft`, not stored state. `archetype: Attr[str]`
added at top level; `verification_log` removed (confirmed zero appenders at time of removal —
verification lives per-slot). `Constraint` gains `scope`/`groundedness`, `type` unchanged
(`Literal["hard","soft"]`, preserved not narrowed). PokemonSet remains a separate type at the
calc/export boundary, not folded into Slot. Migration confirmed narrow: recommend.py,
quick_pick.py, and graph/nodes steering stubs untouched in type or behavior — only
legality.py's Item Clause check and nodes.py's slot initialization needed call-site updates.
31 tests passing, 5 skipped. No Slot Attr writers exist yet; default lock rule (inference →
locked=False, explicit user statement/lock → locked=True) is documented for whichever future
work writes to Slot fields first (steering, tier-2 rework, theme detection) — not yet
exercised in code.
`archetype`'s intended consumer is ADR-015 Amendment 2026-07-27a's theme/core detection
mechanism (intrinsic signal + teammate role abstraction → needed-role list) — see
master_project_log.md's flagged-gaps section for the wiring dependency, not yet implemented.

---

## ADR-018: Agent decision-making triggers, proactive defaults, and deferral handling

**When the agent decides for the user — three cases, not "insufficient input."** Nearly
every real search is under-specified (multiple species can satisfy almost any role), so
"the agent must decide" isn't triggered by input being sparse — it's triggered by:
1. Explicit deferral ("you pick").
2. Too many valid options to reasonably present.
3. Rejection of a suggestion without a reason or further requirement.
A structural fourth case — no interaction channel exists at all (the quick-pick tool,
ADR-012a) — is a distinct, separate case: there the agent must decide because there's no
back-and-forth to have, not because the user deferred.

**Timeout is its own case, not "proceed with best judgment."** Silently proceeding on a
stalled conversation spends resources (tokens/compute) the user may not want spent, without
consent — a real cost decision made on the user's behalf. Also rejected: prompting for
permission on timeout ("do you want me to fill this out?") — if a user has gone quiet long
enough to time out, they are not there to answer that prompt either. Correct behavior: do not
act, do not prompt. Let it sit until the user actually returns.

**Standing default: proactive, concrete, named-default-plus-alternatives — not open
questions.** Rather than asking "what do you want here?", propose a concrete grounded default
with 1-2 named real alternatives (e.g. "the most common weather setter here is Pelipper — go
with that, or an alternative like Politoed?"). This is the standing default for all users,
not a response calibrated to inferred experience level — an experienced user with a real
preference states it regardless of what's nudged, costing them nothing; a less experienced
user gets a concrete, easy-to-react-to anchor instead of an open-ended prompt they may
struggle to answer from nothing.

**No user-experience-level model is needed.** A nudge's rejection produces a stated reason
("I don't want X because Y"), which is inherently more informative than a bare preference
volunteered cold — nudging is a better information-gathering strategy than open questions,
independent of who's being asked. Where explanation depth actually needs to adapt, the
signal is available directly in the moment it matters (see below), without needing to
infer or track experience level at all.

**Deferral phrasing indicates what kind of explanation is wanted, not whether one is
warranted.** Every agent-made decision is explained regardless of how the deferral was
phrased — a bare "you pick" does not mean no explanation, only that the user isn't weighing
in on which option gets chosen. What varies by phrasing is the *kind* of explanation:
"I don't know the difference, care to explain?" calls for a conceptual explanation; "why
might Politoed be better here?" calls for the specific reasoning behind this decision; a
bare "you pick" calls for a minimal rationale alongside the choice made.

**Explanation depth also scales with how much the agent decided unilaterally, independent of
phrasing.** Deferring one narrow decision (e.g. species alone, with role/moves/item/spread
already fixed) only needs reasoning for that one choice. Deferring something broader (an
entire slot — role, species, moves, item, spread all left open) means every one of those
coupled decisions was made unilaterally, and the explanation needs to cover the whole chain,
not just the final result.

**Verification stays constant; narrating it does not.** Every claim, including user pushback,
is checked against real data the same way regardless of who's asking or how confident they
sound — user pushback being correct does not mean it was right *because* the user said it
confidently, and a user's demonstrated track record does not reduce verification rigor
anywhere. But routine verification is not narrated by default — a correct pushback gets
"you're right" or the agent simply proceeding with the update, not a recitation of what was
checked. Verification becomes visible specifically when it changes the answer (the user
was wrong about something and it's being corrected), not as a standing disclosure. Stating
"I verified this" on every routine confirmation reads as distrust and adds noise, mirroring
the existing rule against flagging every inherent build tradeoff by default (Amendment
2026-07-27c).

**Status:** Establishes agent decision-trigger cases, timeout handling, proactive-default
behavior, and the deferral/verification-narration rules from the 2026-07-27 role-play session.

---

## ADR-019: Role Compendium construction and maintenance pipeline

**Construction requires a separate constructor/critic split, not self-review.** Extensive
mock-run testing (2026-07-27 through 2026-07-29, across six roles) showed that a single
pass doing both construction and self-checking reliably misses real, checklist-level errors
— missed mandatory Mega-form splits (in both directions), inconsistent criteria application
across tiers within the same role, treating usage as ranking evidence after explicitly
deciding not to, and failing to cross-check a new placement against its actual tier-neighbors.
These are framework-adherence failures, not novel judgment calls the framework has no answer
for — a dedicated critic pass, explicitly tasked with auditing a constructed entry against
the established checklist, is expected to catch most of this mechanically. Reviewing one's
own construction in the same pass is weak self-checking, since the generation step has
already committed to a framing before any independent skepticism is applied.

**Exhaustive category sweeps, not opportunistic noticing, are required during construction.**
Confirmed failure pattern: real, direct reinforcement mechanisms (Compound Eyes on Vivillon,
Coil on Milotic) were missed despite "check for accuracy-boosting effects" already being an
established criterion, because each candidate's full kit was only checked when something
external prompted a closer look, not as a mandatory, exhaustive step run against every
candidate regardless of other context. The fix: run a mandatory sweep of every candidate's
complete ability list against the fixed taxonomy of effect-types already known to matter
(accuracy, power, priority, execution-risk-mitigation, etc.) for every entry, rather than
relying on incidental notice.

**Each criterion in the taxonomy carries a precondition and only applies when it holds.**
E.g. accuracy-boosting effects are only relevant when the delivery mechanism's base accuracy
is meaningfully below 100% and the role's success genuinely depends on that roll — checking
for this against an already-100%-accurate or ability-guaranteed mechanism is wasted effort
and should be skipped automatically, not evaluated and found irrelevant each time.

**Usage-based validation runs as a targeted review-trigger, never as ranking evidence
itself** (extends Amendment 2026-07-29a's usage-for-discovery-only principle to the
validation stage specifically):
1. **Pool-breadth is a prerequisite check, computed per delivery pathway (not per role, and
   not from raw learnset counts) using the effective candidate count after real mechanical
   narrowing.** A narrow pool (e.g. only 2 legal Drizzle-users) makes market-share numbers
   structurally uninformative on their own; a wide, genuinely competitive pool makes them
   meaningful. Two delivery pathways within the same role are treated as separate pools only
   when they differ in *reliability class* (e.g. ability-guaranteed vs. move-based-and-
   conditional) — pathways of the same reliability class (e.g. Follow Me vs. Rage Powder,
   both +2-priority moves) stay one combined pool; splitting further is unnecessary
   overhead when the combined numbers already agree with what the mechanical model predicts.
2. **Cheap check first: does raw/coarse usage already match what the mechanical
   reliability-class hierarchy predicts?** If yes, no further work is needed — the
   fine-grained pathway split would reveal nothing not already confirmed. Only a genuine
   mismatch (an expected-worse pathway showing surprisingly high share, or vice versa)
   triggers the more expensive, fine-grained investigation.
3. **When a mismatch is confirmed, two independent confounds must be checked before
   treating it as a real signal:** (a) candidate-level — does the candidate's low share in
   this specific role decompose sensibly across other roles it's independently confirmed
   strong at (a genuinely versatile piece diluting its own per-role numbers is not a
   weakness); (b) role-level — is the role itself generally lower-demand across the
   metagame, independent of any specific candidate's quality, requiring the "surprising"
   threshold to be calibrated per-role rather than by one fixed bar everywhere.
4. Only a mismatch surviving all of the above triggers an actual entry review — the default
   is to accept an entry without added scrutiny.

**Maintenance is a two-phase, event-triggered cycle — never a standing periodic re-run**
(consistent with the "no scheduled cadence" principle already established for contingent-
value detection, ADR-016 Amendment 2026-07-26b, and Smogon-writeup rescanning):
1. **Regulation-change trigger, immediate, mechanical (no usage data required):** a critic
   pass checks every existing entry touched by the change against four distinct trigger
   types:
   - Species added to or removed from the legal pool.
   - **An entire reliability class introduced or removed for a role** (e.g. an
     ability-based pathway entering a role that was previously move-only) — this devalues
     or revalues an entire existing population at once, not just one new candidate; flags
     the whole affected population for re-ranking, not just the new addition. (Confirmed
     already observed in practice: Spore's total absence pushed every remaining Sleep-role
     candidate's relative standing up; the same logic applies symmetrically if a
     reliability class were ever removed rather than added.)
   - **An item entering or leaving the legal pool, filtered by a fixed, permanent
     item-lock property (Mega Evolution, and potentially future Z-move-style mechanics) —
     not a per-candidate, per-regulation check.** A Mega-locked candidate can never benefit
     from any new item and should be excluded from this check entirely, rather than
     re-evaluated each time; this was previously mis-modeled as a per-candidate
     availability fact (the Aurora Veil Mega Froslass/Alolan Ninetales case) when it is
     actually a fixed structural property.
   - **A move's own parameters changing directly via balance patch** (accuracy, power,
     effect chance), independent of any species or item change (e.g. Dark Void's accuracy
     nerf reducing Darkrai's standing with no other change involved).
   - **Contingent-value detection, generalized from a binary check to a graded one, driven
     by a persisted dependency registry rather than brute-force re-checking every
     candidate's full movepool.** Extends ADR-016 Amendment 2026-07-26b: a condition→
     dependent relationship (e.g. "Expanding Force's value is contingent on Psychic
     Terrain uptime") is recorded as its own queryable structure at construction time —
     not left buried in one entry's prose — so a future regulation's category-level diff
     (e.g. "Psychic Surge just became available") can directly look up which existing
     entries are registered as depending on that condition, rather than re-deriving the
     dependency from scratch or checking every candidate's entire movepool against every
     new addition. This also generalizes beyond "did this become viable/non-viable" to
     "did this remain viable but become comparatively better or worse" — nothing about the
     dependent candidate needs to change for its real standing to shift.
2. **Usage-based mismatch detection, once enough real usage accumulates post-regulation**
   (the cheap-check-then-confound-check procedure above) — deliberately the later, slower
   phase, since no usage data exists to compare against immediately after a regulation
   change.
3. **No standing periodic re-run in either phase** — both are strictly event-triggered.

**Status:** Establishes the full compendium construction/maintenance pipeline: constructor/
critic separation, exhaustive-sweep-with-preconditions discipline, the four-part regulation-
change trigger taxonomy, the dependency-registry mechanism for contingent-value detection,
and the two-phase (mechanical-then-usage) maintenance cycle. Supersedes the ad hoc,
single-pass construction approach used during the 2026-07-27 through 2026-07-29 mock-run
testing.

---

### ADR-019 — Amendment 2026-08-01a

**Tiered admission generalizes beyond move-narrowing to Compendium construction itself.**

ADR-022's tiered-admission-to-a-tractable-cap pattern (mechanically-obvious candidates
first, mechanically-secondary second, usage-flagged-unexplained third, only as room
allows under a ~20 cap) is not specific to move-narrowing's step 3 — it is the same
shape already implicit in this ADR's pool-breadth gate and exhaustive-sweep discipline,
now stated explicitly as the general admission policy for **any** bounded-candidate-pool
construction in this project, including Role Compendium category membership itself.
When constructing a Compendium category, admit clear/direct members first, secondary/
conditional members second, and usage-flagged-but-unexplained candidates last (subject
to the same construction/critic verification discipline this ADR already mandates)
rather than treating pool admission as a single flat pass.

**Status:** Generalizes an already-adjacent pattern; no change to ADR-019's core
construction/critic pipeline or its four-part regulation-change trigger taxonomy.

---

### ADR-019 — Amendment 2026-08-04a

**Critic-pass requirements, formalized from concrete corrections across the 2026-07-29
mock-run series (Weather Setter, Redirection, Swords Dance Attacker, Trick Room Attacker,
Sleep Status Spreader).** These are not new design — they are the actual behavior already
demonstrated and corrected during construction, now stated as explicit, checkable
requirements for any future critic pass (human or automated), so they don't have to be
rediscovered per-category.

**1. Tiers are defined by a criteria bar, not a target size or a desire to rank everyone
distinctly.** Membership in a tier is binary — a candidate either clears the tier's stated
criteria at the required strength, or it doesn't. Ranking *within* a tier is only imposed
when a real, criteria-based difference in degree actually exists between candidates —
otherwise the tier is a genuine, unordered cluster. Confirmed pattern across multiple runs:
Pelipper and Politoed (Weather Setter) were initially force-ranked over a real-but-minor
secondary-kit difference, corrected to one unordered Excellent tier; the Swords Dance
Attacker run's Excellent tier settled as six unordered members (Kingambit, Scizor
base+Mega, Mega Mawile, Blaziken base+Mega, Aegislash) all clearing the same stated bar
(STAB priority + a damage-amplifying mechanism + adequate bulk), with Ceruledge and Mega
Lucario correctly excluded for lacking one required component despite sharing a trait with
the group; the Trick Room Attacker run correctly produced an unordered Farigiraf/Oranguru
pair in Excellent on the first pass, without requiring correction, once this principle had
been established. When checking a constructed ranking, the critic's default question for
any apparent gap between two candidates should be "does this reflect a real, criteria-based
difference in degree, or an incidental one" — only the former justifies separating them
into different tiers.

**2. A conclusion already reached earlier in the same construction pass must be carried
through to the final output, not silently reverted.** Confirmed failure: during the
Redirection run, Sinistcha vs. Clefable had already been correctly resolved (Sinistcha's
superior bulk, typing immunities, and resistance-to-live-threats profile) earlier in the
same session, but the final tier list reverted to the old, incorrect ordering without
applying that conclusion. The critic must check a constructed ranking against the
construction pass's own prior reasoning, not just against the criteria in isolation — a
self-consistency check, distinct from a correctness check.

**3. A candidate's trait only counts toward a criterion if it serves that criterion's
actual stated mechanical purpose — not merely because it resembles the right general
category of thing.** Confirmed failure and later correct self-application:
- Redirection (failure, corrected): Clefable's Magic Guard/Unaware were initially credited
  as reinforcing the role, but both protect only Clefable itself — the role's actual
  purpose is protecting an *ally*. Maushold's Friend Guard directly reduces ally damage
  taken, a genuine functional fit the self-protective abilities were not. Once corrected,
  Clefable's supposed edge over Maushold evaporated (both share Helping Hand as a wash on
  the tertiary criterion).
- Trick Room Attacker (correct self-application, no correction needed): Sinistcha's
  Hospitality was correctly identified as contributing nothing to Sinistcha's OWN
  execution likelihood for this specific role, since it's other-directed (heals an ally)
  rather than protecting Sinistcha's own setup turn — unlike Farigiraf's Armor Tail or
  Oranguru's Inner Focus, which directly protect the bearer's own ability to act.
- This generalizes a pattern already noted even earlier in the same mock-run series (the
  trapping-ability finding: reinforcement must be checked against the specific failure
  mode it actually addresses, not credited generically as "a strong ability"). The critic
  must verify, for each candidate's claimed reinforcing trait, that it mechanically serves
  the SPECIFIC function the criterion requires (protects the bearer vs. protects an ally;
  addresses this delivery mechanism's specific execution risk vs. a different one) —
  resemblance to the right general category (e.g., "a defensive ability," "a reinforcing
  ability") is not sufficient on its own.

**Status:** Formalizes critic-pass behavior already demonstrated and corrected across five
mock-run role constructions into explicit, reusable requirements for ADR-019's construction/
critic pipeline. No change to the pipeline's structure (constructor/critic split, exhaustive
sweeps, regulation-change triggers) — this amendment specifies what the critic pass must
actually check, closing a gap where the behavior existed as demonstrated practice but not
as a stated rule.

---

### ADR-019 — Amendment 2026-08-05b

**Fourth critic principle: execution_conflict — a candidate's real usage and real
move/ability access don't guarantee it can actually be piloted to fulfill a role, if its
own established playstyle structurally competes with executing that role on the turns it
matters. This principle informs tier placement (demotion), not membership eligibility — it
never acts as an unconditional exclusion gate, matching how the three principles from
Amendment 2026-08-04a already work.**

Surfaced during Redirection role construction: Volcarona has real Rage Powder access and
real usage, satisfying the role's basic delivery-mechanism and execution-reliability
criteria on their own terms. But real team data shows Volcarona's dominant, established
identity is as a Quiver Dance sweeper (verified: 60.8% Quiver Dance usage vs. 27.3% Rage
Powder usage) — a Pokemon cannot spend the same turn both setting up/attacking and
redirecting for an ally, so a Pokemon whose primary usage pattern is self-sweeping is
structurally unlikely to be the one pulling redirection duty when it matters.

**This is a genuinely different check than function_fit** (Amendment 2026-08-04a),
worth distinguishing precisely: function_fit asks whether a candidate's TRAIT serves the
role's stated purpose (a static property check — does this ability protect an ally or only
the bearer). execution_conflict asks whether a candidate's OWN USAGE PATTERN allows it to
actually execute the role at all, given real, structural turn-economy competition with a
different, dominant identity (a dynamic, usage-grounded check).

**Design correction made during implementation, worth recording:** the FIRST version of
this check was implemented as an unconditional exclusion gate (Volcarona ->
considered_rejected) — this was WRONG, and traced to a real process failure: the exclusion
was based on an incomplete reconstruction of a prior conversation's conclusion, asserted as
settled without re-verifying it first. The actual prior conclusion was that Volcarona
clears real membership via an independent, verified reinforcement (Flame Body, 30% contact
burn) despite the competing-identity signal. Corrected: execution_conflict informs
placement (a real, verified competing identity caps a candidate below the unconflicted
Excellent cluster) rather than excluding outright — a candidate with real, independent
reinforcement can still clear membership at a lower tier. This makes execution_conflict
consistent with how tied_cluster, self_consistency, and function_fit already operate: all
four principles inform tier placement/flagging, none act as a unilateral exclusion gate.

**Status:** Adds a fourth critic principle to Amendment 2026-08-04a's three. Corrects an
initial, incorrect exclusion-gate implementation to a placement-informing design consistent
with the other three principles.

---

## ADR-020: Theme/archetype reconciliation — mechanism for re-evaluating locked values when
team-level commitments or sibling attributes change

**Decision:** When the team's archetype, a team-wide constraint, or a locked sibling attribute
within the same slot changes, previously-locked values must be re-evaluated against the new
state — not silently kept, and not silently discarded. This ADR defines the check mechanism,
the trigger conditions, and the recovery path.

**Alternatives considered:** No reconciliation (locked stays locked regardless of later
changes) — rejected, since it silently accumulates stale/contradictory picks (a Swift Swim
sweeper on a team that's switched to Sun). Full team wipe on any theme change — rejected except
as an explicit, separate user intent (see `reset`, below), since it discards genuinely
unrelated, still-valid locked choices (a species locked "regardless of theme").

**Why this matters:** surfaced via a role-play mock conversation and extensive follow-on
scenario-testing this session (Fire-type-under-Rain, Sneasler-under-TrickRoom,
Mega-Staraptor-vs-mono-type, base-vs-Mega-form disagreement, Skarmory-IronPress-vs-Mega-
Skarmero, TailRoom composite archetypes) — a materially real gap, not a hypothetical edge case,
and one that came close to being addressed with ad hoc, per-mechanic hardcoded rules before
being generalized. Building it as one general, tiered mechanism instead of one bespoke checker
per mechanic is the central design commitment of this ADR.

### Trigger conditions (two distinct paths, one shared check)

1. **Team-level commitment change** — `archetype` changes, or a new team-wide `constraint` is
   recorded. Re-evaluate every currently-locked attribute across all slots against the new
   commitment.
2. **Same-slot dependency-circle propagation** (ADR-015 Amendment 2026-07-27c) — a locked
   attribute within a slot changes (e.g. `species` swapped from base to Mega form). Re-evaluate
   that slot's *other* locked attributes (item, moveset, spread) against the new value, since
   they may have been built around the old one. This is the dependency circle already designed
   for build resolution, now also firing on a *revision* to an already-locked value, not just
   during initial resolution.

Both paths call the same `check_theme_fit`/`check_archetype_fit` machinery below — they differ
only in what's being checked against what.

### Check mechanism: four tiers, cheapest/most-certain first, no bespoke per-mechanic rules

```python
def check_theme_fit(slot: Slot, commitment: str) -> FitResult:
    # Tier 1: direct attribute check against already-known species/build data
    # (typing, base stats, ability name, item name — from the legality snapshot,
    # no calc call needed). Must be FORM-AWARE: check every forme the build could
    # reach (e.g. base + Mega), not just the currently-active one — a type-changing
    # Mega (Staraptor, Charizard X, Gyarados, Altaria) can disagree with its base
    # form; if forms disagree, return ambiguous=True rather than silently picking one.
    ...
    # Tier 2: calc recompute-and-diff. Re-run the slot's existing verification
    # (ADR-003 calc client) under the new field condition (weather/terrain/screens)
    # or against the new base-stat line (post-Mega-Evolution), and diff against the
    # stored result. Produces a graded magnitude (via FitResult.severity, reusing
    # ADR-015 Amendment 2026-07-28c's Decisive/Costly/Toss-up scale), not a bare bool
    # — e.g. IronPress-on-Mega-Skarmory isn't illegal, just less effective given
    # Mega Skarmory's lower Def.
    ...
    # Tier 3: role-membership test reuse. Re-run whatever mechanism admits a
    # candidate to slot.role.value in the first place (tier-2 heuristic today; Role
    # Compendium membership test once built, ADR-019) against the NEW commitment's
    # context — e.g. Sneasler's fast-Unburden-sweeper role tested against Trick
    # Room's effective-Speed requirement (ADR-015 Amendment 2026-07-29d). No new
    # rule per archetype; the role's own membership definition IS the rule.
    ...
    # Tier 4: judgment-only. No data hook exists (e.g. "girlypop"). LLM judgment,
    # stated plainly as ungrounded, per ADR-017's groundedness model.
```

`FitResult` is graded, not binary:

```python
@dataclass
class FitResult:
    satisfies: bool
    groundedness: Literal["mechanically-checkable","enumerable-but-uncoded","judgment-only"]
    severity: Optional[Literal["decisive","costly","toss-up"]] = None
    ambiguous: bool = False
    detail: Optional[str] = None
```

### Composite archetypes (e.g. "TailRoom" = Tailwind + Trick Room together)

`archetype` is a **component set**, not a single string:

```python
class RecommenderState(TypedDict):
    ...
    archetype: Attr[list[str]]   # e.g. ["Tailwind", "TrickRoom"] — was Attr[str]
```

A composite label (e.g. "TailRoom") is a narration convenience only, resolved via a lookup
table never consulted by reconciliation logic itself — reconciliation always operates on the
component list directly.

**Composition semantics are OR, not per-slot assignment.** A slot fits a composite archetype if
it's compatible with *at least one* current component — this includes slots whose entire value
is being compatible with multiple components simultaneously (e.g. Archaludon's middling Speed
benefiting from either Tailwind or Trick Room, agnostic to which — a legitimate, positive
membership case per the flagged Role Compendium gap above, not a fallback):

```python
def check_archetype_fit(slot: Slot, components: list[str]) -> FitResult:
    per_component = [check_theme_fit(slot, c) for c in components]
    if any(r.satisfies for r in per_component):
        return FitResult(satisfies=True, ...)
    return FitResult(satisfies=False, ...)
```

Reconciliation on a component-set change only touches slots that fit *zero* remaining
components: adding a component (Trick Room → TailRoom) never invalidates anything already
locked, since gaining an additional acceptable role can't cause an existing valid pick to fail;
removing a component (TailRoom → solo Trick Room) only reopens slots with no remaining fit.

### Recovery: exemption and restore

**`Attr` gains `exempt_from_theme: bool`.** Set when the user explicitly overrides theme
relevance ("I want Garchomp regardless of weather"). Exemption changes what happens on a
mismatch, never whether the check runs — verification stays constant per ADR-018's existing
principle; only the action varies:

- Not exempt, mismatch, mechanically-checkable → auto-reopen (unlock, log to `superseded`).
- Not exempt, mismatch, judgment-only → flag, don't auto-decide.
- Exempt, mismatch, mechanically-checkable → **flag as `flag_exempt_conflict`, never
  auto-removed** — e.g. Mega Charizard X explicitly locked "regardless of theme," then team
  switches to Rain: Blaze/Solar Power's real synergy is Sun-conditioned, a genuine mechanical
  mismatch, but the user's explicit override is respected by never silently dropping it —
  only surfaced.
- Exempt, mismatch, judgment-only → silently respected, no flag (an explicit override on a
  vibes-level mismatch isn't worth re-litigating).

**`RecommenderState` gains `superseded: list[SupersededEntry]`** — a recoverable log, distinct
from `pending_flags` (undecided items). Every auto-reopen logs what was removed and why
(human-readable, for narration: *"it didn't fit Rain because Fire-type STAB is halved"*).
Pushback ("hey, I actually wanted that") is a new `classify_input` intent that reads the most
recent matching entry and restores it via the same lock machinery, reason set to
`user_stated`. Chaining beyond one level of undo (a restore displacing something
`propose_team_draft` had already filled in) is an open question, not resolved here.

### Reset

**"Start from scratch"** is a distinct, separate intent (`reset`), not routed through
reconciliation at all — full wipe of `team_draft`, `constraints`, and `archetype`, re-seeded
with whatever new archetype/constraint accompanied the reset statement. Simpler than a themed
reversal and shouldn't be forced through the same machinery.

**Status:** Decided in design (2026-07-29 reconciliation session). Implemented 2026-07-30
(`recommender/reconcile.py`). Depends on ADR-017 schema (landed) for `Attr`/`archetype`
shape; depends on ADR-019's Role Compendium (not yet built) for full tier-3 coverage —
until then, tier 3 is bounded to tier-2's five hardcoded archetypes, a known and bounded
gap (see master_project_log.md flagged gaps).

**Status update (2026-07-29):** `archetype: Attr[list[str]]` landed in `recommender/state.py`
— corrects the type ADR-017's original migration shipped (`Attr[str]`), which predated
ADR-020's composite-archetype design. One-line schema change; no consumer exists yet
(`nodes.initialize` still constructs a bare `Attr()`, `value=None`), so blast radius was
confirmed near-zero via grep before the edit, and held. 31 tests passing, 5 skipped.
Reconciliation logic itself (`check_theme_fit`/`check_archetype_fit`/`FitResult`,
`COMPOSITE_ARCHETYPE_LABELS`, `superseded`/`pending_flags`/`exempt_from_theme`) remains
unimplemented — this update is schema-only, per the scoped follow-up task.

**Status update (2026-07-30):** Reconciliation logic landed in `recommender/reconcile.py`
and wired into `handle_archetype_change`, `apply_lock` (sibling propagation), and
`restore_superseded` graph node. `FitResult.severity` imports `Severity` from
`recommender.matchup`. Tier 3 still bounded to `infer_role`'s five hardcoded archetypes
until ADR-019 Role Compendium.

---

### ADR-020 — Amendment 2026-07-29a

**Reconciliation check corrected: forward-looking and tag-agnostic, not gated on
prior component tagging.**

The original design checked a locked attribute's fit against the specific archetype
component being *removed*, gated on whether `reason.ref` matched that component. Both
are wrong: checking fit against a component that's leaving is backwards (the live
question is always "does this satisfy something still active"), and gating on the
tag being correct means an unintentionally multi-fitting pick (e.g. a team that
organically ends up Rain+TailRoom without the user ever declaring "TailRoom") could
be incorrectly reopened, since the tag only reflects why it was *originally* added,
not everything it happens to satisfy now.

**Fix:** on any archetype component-set change, re-run `check_archetype_fit` (OR
semantics) against the full *current* component set for every locked, non-exempt
attribute, regardless of its stored `reason.ref`. A slot only reopens if it fails
against every currently active component. This makes unintentional archetype overlap
safe by construction — nothing needs to detect, name, or correctly tag the overlap
for it to be preserved correctly.

**Status:** Corrects the reconciliation check in ADR-020's original text. No schema
change; `reason.ref` remains useful for narration ("this was originally picked for
Rain") but is no longer load-bearing for the reopen decision.

---

### ADR-020 — Implementation landed (2026-07-29)

Multi-turn steering graph (checkpointer + thread_id, classify_input routing, apply_lock/
record_constraint/record_rejection/reset_team/handle_archetype_change handlers) and ADR-020's
reconciliation logic (check_theme_fit's four tiers, check_archetype_fit's OR-composition,
reconcile_on_archetype_change/reconcile_on_sibling_change, exempt_from_theme, superseded log,
restore_superseded) are both implemented, via a three-track orchestrated build:
- Task 1 (steering skeleton) and Task 3 (pairwise matchup classifier, ADR-015 Amendment
  2026-07-28c) ran in parallel on isolated worktrees, disjoint files.
- Task 2 (this ADR's reconciliation logic) gated on Task 1 landing first, per the dependency
  it has on the handler nodes Task 1 builds.
- Severity literal shared cleanly across ADR-015's classifier and this ADR's FitResult:
  recommender.matchup.Severity defined once by Task 3, imported (not redefined) by Task 2's
  work — confirmed via an explicit handoff brief rather than left as an open flag.

52 tests passing (up from 31), 5 skipped, no regressions.

Known, deliberate scope boundaries carried from design into implementation:
- Tier 3 (role-membership reuse) remains bounded to tier-2's five hardcoded archetypes —
  full coverage depends on the Role Compendium (ADR-019), not yet built.
- Rejecting a locked species keeps the lock (default; user must explicitly unlock/relock
  to actually change a locked pick).
- reset_team leaves `rejected` history intact across a wipe.
- Restore (superseded-log recovery) supports one level of undo only; chained/multi-level
  restore was explicitly deferred, not designed.

**Status:** Implemented. Reconciliation's tier-3 ceiling and the Compendium dependency are
tracked in master_project_log.md's flagged-gaps section, not repeated here.

---

## ADR-021: Open-ended reasoning must be verification-gated before affecting any decision

**Decision:** Whenever the system needs to reason about something open-ended or judgment-
based — one that can't be reduced to a fixed, enumerable checklist — the reasoning step
itself may be as open-ended and LLM-driven as necessary, but no specific claim it produces
is allowed to affect an actual decision (ranking, locking, proposing, flagging) until that
claim is checked against real, structured data. The LLM's role is to *notice candidate
possibilities*; real data's role is to *confirm* them. Never the reverse — an unverified LLM
claim is never treated as sufficient grounds for a system action on its own.

**Alternatives considered:** Maintain a fixed, growing taxonomy of known interaction types
(the approach initially proposed for move/ability kit-interaction checking) — rejected as
insufficient once it became clear the space of possible ability/move/stat interactions
(Tough Claws + contact moves, Adaptability + STAB, Contrary + self-debuffing moves, a
priority move mattering differently for a slow setup sweeper, etc.) is genuinely open-ended,
not enumerable even with continuous additions. A checklist approach is always one
undiscovered interaction behind, no matter how large it grows.

**Why:** This generalizes a pattern already present piecemeal throughout the project —
tier-2's role-heuristic proposals being "a draft until tier-3 confirms it" (ADR-015),
`check_theme_fit`'s tiered structure explicitly separating mechanically-checkable judgment
from judgment-only cases (ADR-017/020), and ADR-002/003's foundational rule that legality
and mechanical claims are always tool calls, never model assertions — into one explicit,
standing architectural principle: **mechanics touch nearly every corner of this system, and
almost every future task will eventually need to reason about *some* open-ended mechanical
interaction.** Rather than rediscovering and re-arguing this same shape of problem each time
a new open-ended reasoning need arises (as happened when scoping move-narrowing's kit-
reinforcement checks), this principle should be checked against explicitly for any future
task involving judgment, ranking, or proposal logic.

**Concrete shape:** an LLM reasoning step proposes candidate interactions given a specific
context (e.g. "this candidate's Tough Claws should boost this move, since it's a contact
move"). Each proposed interaction is then verified against real, structured data before being
allowed to affect ranking/scoring/proposing: is the move actually flagged as contact in real
move data? Does the ability actually have the claimed effect in real ability data? Does the
calc client's actual output differ when the ability/interaction is applied vs. not? Only
interactions that survive this verification step affect any downstream decision; a proposed
interaction that doesn't check out against real data is discarded, not applied.

**Status:** Decided. Applies retroactively as the stated rationale for tier-2/tier-3's
existing draft-then-verify relationship and `check_theme_fit`'s tiered groundedness model
(no implementation change to those); applies going forward as a standing check for any new
task involving open-ended judgment, starting with move-narrowing's kit-reinforcement
follow-up.

---

### ADR-021 — Amendment 2026-08-01a

**Usage-flagged-but-unexplained candidates are a legitimate, structured proposal
source, subject to the same verification-gating discipline.**

ADR-022's tiered admission policy treats a candidate whose only justification is real
usage data (no cheap mechanical filter explains its presence) as an implicit
**proposal** — functionally equivalent to an LLM-proposed kit-interaction under this
ADR's original design, except the candidate proposes itself via data rather than an
explicit reasoning step. The same rule applies without modification: this proposal
affects no ranking or decision until deep reasoning actually finds and confirms a real,
verifiable mechanism behind it. A usage-flagged candidate that deep reasoning cannot
explain gets discarded, not kept on the strength of usage alone — usage is discovery
evidence, never sufficient justification by itself, consistent with this project's
standing usage-data discipline (Amendment 2026-07-29a/e).

**Status:** Extends ADR-021's verification-gating principle to a second concrete
trigger (usage-flagged admission), alongside its original trigger (open-ended
LLM-proposed kit interactions). No change to the core propose-then-verify mechanism.

---

### ADR-021 — Amendment 2026-08-01b

**Extension: verification-gated reasoning must also identify WHICH mechanical axis an
interaction affects, not only whether a valid interaction exists.**

ADR-021's original scope covers proposing a candidate kit-interaction and verifying it
against real data before it affects ranking. This amendment extends that verification step
to also tag which specific mechanical axis (power, accuracy, priority, or other) a verified
interaction addresses — surfaced while designing tier assignment for move-narrowing
candidate search's tier-0 definition (which power-boosting or accuracy-fixing abilities/
moves qualify a candidate for the "obvious, mechanically justified" tier for a given move),
and confirmed to be the same underlying operation already specified for Role Compendium
ranking (Amendment 2026-07-28d: "does this ability directly reinforce the role's actual
function").

**Why axis-tagging is necessary, not just convenient:** a move's real weakness is not
always the same axis, and abilities/moves that boost different axes are not interchangeable
or rankable against each other on one shared scale. Motivating case: Zap Cannon (base power
120, accuracy 50%) is effectively unusable without addressing its accuracy, not its power —
an ability that boosts power (e.g. Electric Surge boosting Electric-type move power) does
nothing to fix Zap Cannon's actual bottleneck, while an ability that bypasses accuracy
checks (No Guard) directly solves it. Ranking these two ability types against each other on
a single "how good is this boost" scale would misrepresent what's actually happening — they
answer different questions about what makes the move usable at all. Determining which axis
is the real bottleneck for a given move is itself a judgment call (how low is "low enough"
to matter, does priority matter for this specific role, which move flags are relevant) —
this is explicitly NOT a fixed threshold to hardcode; it stays inside the reasoning step,
per ADR-021's original principle, evaluated per-move-and-context rather than pre-decided.

**Verification must be kit-aware and candidate-specific, not a flat ability-to-effect
table.** Two confirmed cases where a naive, ability-name-keyed lookup would be wrong:

1. **Adaptability is candidate-and-move-conditional, not a fixed ability-level fact.**
   Adaptability boosts STAB damage — whether a given move receives STAB at all depends on
   the relationship between the move's type and the specific candidate's own typing. A
   flat table keyed only on "has Adaptability" would incorrectly apply its boost to a
   candidate for whom the move in question isn't even STAB. Verification must check
   `ability_effect(ability, move, candidate)`, not `ability_effect(ability)` alone.

2. **The mechanism addressing a constraint is not always an ability.** Milotic can address
   Hypnosis's imperfect accuracy via Coil (a MOVE it has access to, raising accuracy among
   its other effects), not via any innate ability. A verification step scoped only to a
   candidate's ability would miss this entirely, despite it being mechanically identical in
   effect (and equally real, equally checkable) to an ability-based fix. Verification must
   scan the candidate's full kit — ability, typing-derived properties, AND moveset — not
   ability alone. This reuses the same multi-source kit-scan already implicit in ADR-021's
   original kit-reinforcement check for move-narrowing; it does not require a separate
   mechanism.

**Consolidation, not proliferation.** These findings do not require building separate new
standalone tools (a move-profile lookup, an ability-effect table) alongside ADR-021's
existing verification step — attempting to enumerate every case in advance (as this
amendment's own design process tried, and found genuinely difficult to break past the
motivating cases above) is exactly the checklist trap ADR-021 already exists to avoid. The
correct scope is one extension to the existing propose-then-verify mechanism: when
verifying a proposed kit-interaction, also determine and tag which axis it addresses,
checked against the candidate's real, full kit (ability + typing + moveset together), with
the "what counts as a relevant constraint" judgment staying inside the reasoning step per
ADR-021's original design, never hardcoded as a fixed threshold or table.

**Status:** Extends ADR-021's verification mechanism with axis-tagging. Confirms (rather
than introduces) that this same mechanism is the correct basis for both move-narrowing
candidate search's tier assignment (this amendment's motivating case) and Role Compendium
ranking (Amendment 2026-07-28d) — both should consume one shared reasoning/verification
function, not separately-built, separately-drifting implementations of the same judgment.
Implementation of the shared function itself is not yet scoped — this amendment establishes
the design principle; a concrete build task remains a follow-up.

---

## ADR-022: Slot-filling as a generalized narrowing loop

**Decision:** Replace the implicit assumption that slot-filling is a fixed sequence of
named steps (establish theme → pick core → find teammates → refine slot) with a single
generalized loop: repeatedly check whether the current candidate pool is presentable
(per ADR-018's existing judgment), and if not, apply whichever narrowing tool is
appropriate given current state, then re-check. What varies between an empty team, a
locked theme, and an anchor Pokémon is not the mechanism — it's which narrowing tools are
available and relevant at that point in the loop.

**Why a loop, not a fixed cascade:** An earlier draft of this design treated "refine an
existing slot," "fill a slot from a theme," "fill a slot from an existing anchor," and
"ask the user when nothing exists" as four distinct named mechanisms with fixed hand-off
order. This broke down on two real cases: (1) a stated theme can be real and constraining
without being specific enough to imply an anchor (mono-Fairy narrows legality but suggests
no particular Pokémon — see below), and (2) the same underlying operation (narrow a pool,
check presentability, narrow again) recurs at every level regardless of what's already
known. Collapsing to one loop with state-dependent tool availability removes the need for
a fixed level structure and matches this project's existing house style (tier-1→2→3
escalation, ADR-015's dependency circle) of cascading fallback rather than upfront
branching.

**The loop:**

    loop:
      pool = current_candidate_set(state)
      if pool is presentable (per ADR-018: one concrete default + 1-2 real alternatives,
         or the honest fuller spread when nothing has narrowed much, per Amendment
         2026-07-28b):
        -> present it, STOP
      else:
        -> pick the next available narrowing tool given current state
        -> apply it, shrinking or reshaping the pool
        -> LOOP (re-check presentability)

**Termination is judged separately from tractability.** ADR-018's presentation judgment
(is this small/concrete enough to show a human) is a different question from whether a
pool is small enough to reason over deeply (see the two-stage pattern below). Do not
conflate the two thresholds — they were conflated in early drafts of this design and
produced confusion about what "small enough" actually meant at each stage.

### Two-stage pattern: cheap-filter-to-tractable, then deep-reason-to-presentable

Every instance of this loop that involves a real candidate search (not just a binary
theme check) follows the same two-stage shape already established independently by
move-narrowing (Amendment 2026-07-27f) and specified for Role Compendium construction
(ADR-019):

1. **Cheap filtering, tiered admission, to a tractable cap (not a fixed count).** Apply
   mechanical/data-cheap filters (legality, theme-fit, delivery-mechanism grouping,
   typing/weakness lookups) to build a working set bounded by a tractability cap
   (~20, matching Amendment 2026-07-29b's precedent) — this cap exists so that the
   subsequent deep-reasoning stage has a computationally reasonable set to work with,
   **not** because 20 is the right number to ever show a user. Admission within the cap
   is **tiered, not flat**: admit mechanically-obvious candidates first (e.g., an
   automatic ability-based delivery mechanism), then mechanically-secondary candidates
   (e.g., a reliable-but-non-automatic delivery mechanism), and only then — if room
   remains under the cap — admit candidates whose presence is justified by real usage
   data alone, with no cheap mechanical explanation yet found. This third tier is a
   **discovery signal** (per Amendment 2026-07-29a's "usage for discovery, never
   ranking"), not noise to be filtered out — it surfaces candidates that later,
   confirmed a real mechanism deep reasoning wouldn't otherwise have looked for.

2. **Deep reasoning as a bidirectional quality gate**, applied only to the bounded
   working set: verification-gated kit-interaction checks (ADR-021), counter-lookup
   chains, cooccurrence validation, calc-backed breakpoint checks, whatever is
   appropriate to the specific slot-filling context. This stage can **promote** a
   usage-flagged-but-unexplained candidate (deep reasoning finds and confirms a real
   mechanism — a genuine discovery) or **eject** any candidate, including ones admitted
   on mechanically-obvious grounds, that doesn't actually hold up under closer
   inspection. Cheap filters are deliberately permissive on the way in; deep reasoning
   is the real quality gate on the way out.

3. Only after deep reasoning does the result get cut down further to whatever ADR-018's
   presentation judgment actually calls for (typically far fewer than 20) — this final
   cut, plus the working memoized/cached result, happens after stage 2, not as part of
   the tractability cap itself.

### Ordering principle: archetype/role membership before raw mechanical reasoning

"How well-defined is this candidate's teammate/support/threat profile" is not an
independent quality to estimate — **it collapses exactly onto "does this candidate
belong to a known archetype/role."** A candidate with a clean archetype match (e.g. a
Sun-abuser under a Fire-type theme) inherits that archetype's already-encoded teammate/
support/threat reasoning for free (via tier-2's five hardcoded archetypes today, the
Role Compendium once built, ADR-019). A candidate with no clean archetype match (the
motivating case throughout this design: Mega Staraptor, whose real needs — a
stat-debuff partner, defensive-coverage support — have no categorized label) requires
the more expensive raw-mechanical-reasoning tools below instead.

**Ordering rule:** always attempt archetype/role-membership lookup first (cheap, reuses
existing infrastructure); fall through to raw counter-lookup/support-needs reasoning
only when no archetype match exists. This is the same tier-1-before-tier-2,
cheap-before-expensive discipline already used everywhere else in this project.

**Usage must inform this check, not be overridden by it.** A candidate with a clean
archetype match but low real-world usage may be well-defined *because it's
underexplored*, not because it's mechanically sound — clarity from data sparsity is not
the same as clarity from genuine strength (same caution already logged in Amendment
2026-07-29e's usage-consistency check). Archetype-membership and usage-popularity should
both weigh into candidate ranking; neither should be treated as sufficient alone.

### New tools required (none yet built)

These are genuinely new, Compendium-independent tools the loop needs when raw mechanical
reasoning is required (no archetype match, or when reasoning about a currently-locked
anchor's own needs):

- **`query_counters(pokemon)`** — given a Pokémon's typing/stats/kit, what real,
  currently-relevant threats exploit it. A cheap, mechanically-grounded lookup (typing
  chart + real usage-popularity filtering to 3-5 actually-relevant threats — **usage
  here means simple popularity of the threat itself**, not cooccurrence; see below),
  not open-ended reasoning.
- **`query_counter_of_counters(threat)`** — same tool, called once per relevant threat
  identified above (not recursively beyond one level) — "who beats this threat" becomes
  the candidate teammate pool. Depth is fixed at one additional level, not open-ended
  recursion, per the explicit design decision: `query_counters` → popularity-filter to
  3-5 → `query_counter_of_counters` once per filtered threat → compose.
- **`query_support_needs(pokemon)`** — a second, independent branch from
  `query_counters`, reasoning over the anchor's **own** kit (ability, stats, weaknesses,
  existing moveset) rather than any specific opponent: what functional support would
  help it perform, resolved either **by move** (routes to move-narrowing, already
  built) or **by role** (routes to archetype/Compendium lookup, or the same
  no-clean-role fallback Staraptor itself demonstrates). Runs in parallel with the
  threat-driven branch, not sequentially after it — they answer different questions
  from the same anchor.
- **`query_theme_refinement_candidates(theme)`** — given a locked-but-under-constrained
  theme (mono-Fairy), propose narrower, mechanically-compatible sub-themes (this is
  *not* the same operation as picking a specific anchor Pokémon within the theme — it
  narrows the theme itself, e.g. mono-Fire → Sun team is checkable-compatible via the
  same type/ability-interaction data already used elsewhere in this project; mono-Fairy
  → Rain team is not, since nothing about Fairy-typing relates to Rain). Both
  theme-refinement and anchor-selection are legitimate, parallel narrowing actions
  available at the same decision point when a theme is real but under-constrained —
  worth surfacing both as real path options (per ADR-018) rather than the system
  silently picking one.

**Cross-branch reconciliation is valuable in its own right.** A candidate that
satisfies both the threat-driven branch (denies/counters a real threat) *and* the
support-needs branch (fills a genuine gap in the anchor's own kit) is strictly more
valuable than one that satisfies only one — this mirrors what was already observed
empirically in yesterday's redundancy-validation work (Amendment 2026-07-27f's Mega
Froslass/Rain-Dance case: threat-denial and self-serving-sequencing benefit,
satisfied by the same single move). The composition step after both branches run should
check for this overlap explicitly, not just merge two separate candidate lists.

### Three distinct usage signals — do not conflate

This design uses real usage/co-occurrence data (ADR-007 Amendment 2026-07-25c) in three
genuinely different ways at three different points. Each is a separate query with a
separate shape:

1. **Popularity (species-alone usage)** — used to filter `query_counters`' raw output
   down to 3-5 *actually-relevant* threats (of everything a Pokémon is typologically
   weak to, which ones are commonly played), and to weigh candidates during
   archetype-ordered ranking (the anti-obscurity check above). Same signal
   `get_relevant_threats` already sources.
2. **Discovery (usage-flagged-but-mechanically-unexplained admission)** — used only
   during the tiered cheap-filtering stage, to admit candidates the mechanical filters
   alone wouldn't have surfaced, subject to deep-reasoning confirmation before being
   trusted (per ADR-021).
3. **Cooccurrence (pair-level usage)** — used only at final candidate validation: does
   real team-composition data actually support this specific candidate as a teammate
   *for this specific anchor*, not just "beats one of its threats" in isolation. A
   genuinely different query shape (pair statistics) from the other two (single-species
   statistics) — implementations must not reuse one query for the other's purpose.

### Integration with existing systems

- **Multiple slots proposed/locked at once** (e.g. one teammate covering multiple
  threats might justify proposing more than one lock in a single turn) must route
  through the existing `simultaneous_lock_conflicts`/N-attribute batch-lock machinery
  (built during the dependency-circle propagation work) rather than a new,
  separate multi-lock mechanism.
- **Hand-off to `propose_team_draft`'s existing refinement path**: once this loop
  produces a filled slot (species locked), refinement of that slot's remaining
  attributes (moveset/item/spread) is already fully handled by existing,
  already-shipped logic (tier-1 cache → move-narrowing → dependency-circle
  propagation) — this ADR's loop is only responsible for getting a slot from
  "empty/theme-only" to "species decided," not for anything after that.
- **The "nothing exists yet" case** — no theme, no anchor, no constraints — is the
  loop's first-pass state: the only available narrowing tool is `ask_user`, surfacing
  real archetype/core-Pokémon/general-theme options directly (per ADR-018), not an
  open-ended question.
- **Under-constrained-theme case** (mono-Fairy): both `query_theme_refinement_
  candidates` and direct anchor-selection (archetype-ordered, usage-weighted, per the
  ordering principle above) are available narrowing actions; when surfacing anchor
  candidates specifically, **prefer core-attacker candidates over support candidates**,
  since an attacker's own teammate/support/threat profile is comparably well-defined
  (real counter-lookup/support-needs signal to reason from), whereas support-Pokémon
  are often defined *by* their teammates rather than independently — a support-first
  anchor is a structurally weaker starting point for the rest of the loop to build
  from.

**Status:** Decided in design (2026-08-01 session). No implementation yet. Depends on
tier-2's existing five archetypes / eventual Role Compendium (ADR-019) for the
archetype-membership-first ordering to have real content; the raw-mechanical-reasoning
fallback tools (`query_counters`, `query_counter_of_counters`, `query_support_needs`,
`query_theme_refinement_candidates`) are new and Compendium-independent, and could be
built and tested before the Compendium exists.

### ADR-022 — Amendment 2026-08-02a

**Correction: rename query_counter_of_counters to query_threat_counters; correct the
described sequencing to match the shipped, deliberately-refined design.**

Two corrections to this ADR's original text, both surfaced during implementation:

**1. Naming.** The tool originally named `query_counter_of_counters` is implemented and
should be referred to going forward as `query_threat_counters` — the original name was
confusing in spoken/written discussion ("counter of counters" reads ambiguously) and the
new name states its actual purpose directly (finding candidates that counter an anchor's
threats).

**2. Sequencing.** This ADR's original text described popularity-filtering the anchor's
threat list down to 3-5 BEFORE recursing into `query_counters` per threat. This is not
what was built, and the actual shipped design is a deliberate improvement, not a deviation
to be reconciled after the fact:

- `query_counters(anchor)` runs at its own full, untrimmed output — not pre-cut to 3-5.
- `query_counters(threat)` runs FULL for every threat in that untrimmed list, not a
  pre-cut subset.
- Only AFTER merging candidates across all threats (tracking, per candidate, how many
  distinct threats it counters) does any trimming occur — via `rank_and_cut` on the
  merged pool (count-of-threats-countered + usage composite key), cut to ~10.

**Why this ordering is correct, not just different:** a candidate's true value under this
tool's whole premise — countering multiple threats — is only visible once evaluated across
the full cross-product of threats and candidates. Trimming the threat list to 3-5 before
ever running the per-threat candidate search would discard exactly the information this
tool exists to surface: a candidate that looks unremarkable against any single threat in
isolation, but is valuable specifically because it recurs across several. Early trimming
optimizes for a cost saving (fewer `query_counters` calls) at the expense of the tool's
actual purpose; since `query_counters` itself is a cheap, calc-free, data-only lookup (per
its own design), this cost saving was never necessary in the first place.

**Verification-threat selection is a separate, later step, not the same operation as the
threat-list trim described above.** A SECOND, independent `rank_and_cut` call re-ranks the
original, full anchor-threat list by usage alone (ignoring `query_counters`' own mechanical-
danger-first tiering) to select the top 5 threats worth spending real `classify_matchup`
calls verifying candidates against. This is a distinct operation from the merged-candidate-
pool trim above, serving a different purpose (selecting which threats are realistic to
actually face, for the sake of bounding expensive verification calls specifically) — it
should not be conflated with, or read as a restatement of, the originally-described
popularity-filter step.

**Verification is the real final ranking step, not a confirm/discard gate.** `classify_
matchup` outcomes (four-way outcome + severity, per ADR-015 Amendment 2026-07-28c) against
the selected top-5 threats determine final candidate order — a candidate with fewer
statically-counted counters but stronger verified performance can and should outrank one
with a higher static count but weaker verified results. The static, merged-pool ranking
exists only to produce a tractable candidate set worth the cost of real verification calls,
not to determine final standing on its own.

**Status:** Corrects this ADR's tool name and originally-described sequencing to match the
shipped, deliberately-refined design (recommender/threat_counters.py, 2026-08-02). No change
to this ADR's broader two-stage pattern or usage-signal principles — this amendment only
corrects one tool's specific described mechanics within that pattern.

---

### ADR-022 — Amendment 2026-08-02b

**Clarification: role/archetype classification is the orchestrator's own first step, not
something any individual raw-reasoning tool (query_counters, query_threat_counters,
query_support_needs) computes for itself.**

Surfaced while designing query_support_needs: role-shape classification (is this anchor
attacker-primary or support-primary, tanky-by-design or glass-cannon-by-design, etc.) kept
resisting a fixed, mechanical rule at every attempt (stat-asymmetry alone, tanky-gating,
attacker-vs-support-gating by attacking-move count) — each attempted rule had a real,
ordinary counterexample (Archaludon's asymmetric bulk only mattering because it's an
offense-primary tank; a glass cannon's low bulk being an accepted tradeoff, not a gap;
Farigiraf carrying multiple strong attacking moves while still being fundamentally a
Trick-Room/priority-denial support piece, its attacking moves serving as insurance per the
same Taunt-insurance principle as Amendment 2026-07-27e). This confirmed role-shape
classification is genuinely open-ended judgment (an ADR-021-shaped reasoning problem, not a
lookup), not something to force into a fixed heuristic tree.

This ADR already specifies the correct place for this classification to happen: "always
attempt archetype/role-membership lookup first (cheap, reuses existing infrastructure);
fall through to raw counter-lookup/support-needs reasoning only when no archetype match
exists." This amendment makes explicit what was previously implicit — this classification
attempt is the ORCHESTRATOR's own first move in the generalized narrowing loop, run once,
before any of the three raw-reasoning tools are called. It is NOT something query_counters,
query_threat_counters, or query_support_needs each re-derive internally.

**Concretely:** the orchestrator attempts role/archetype classification (today: tier-2's
five hardcoded archetypes; eventually: Role Compendium membership, per Amendment 2026-
07-28d's offensive/support criteria) before deciding whether a raw-reasoning tool needs to
run at all. If classification resolves cleanly, that result IS the answer for whatever
question is being asked (e.g., "what role is this" or "does this anchor already have a
known need-profile via its archetype"). If classification does NOT resolve cleanly (the
Staraptor case; possibly not the Farigiraf case, which may resolve via an existing "Trick
Room setter" archetype and never need the raw-reasoning fallback at all — check against
current archetype coverage before assuming a given anchor needs the hard path), the
orchestrator falls through to the raw-reasoning tools — and PASSES WHATEVER PARTIAL
CLASSIFICATION SIGNAL IT ALREADY PRODUCED (even if inconclusive) into that tool as context,
rather than having the tool re-run classification from scratch.

**Status:** Clarifies existing ADR-022 text (the ordering principle already stated this in
spirit); makes explicit that classification is orchestrator-level and its result/context is
an INPUT to the raw-reasoning tools, not something each tool independently computes. No
change to the ordering principle itself.

---

### ADR-022 — Amendment 2026-08-02c

**Corrections: signature and scope description for query_support_needs updated to match
the shipped implementation.**

1. This ADR's original text did not specify query_support_needs' actual signature. As
   shipped: query_support_needs(pokemon, role_shape_context, team_draft) — team_draft is
   required for the Speed-axis's condition-dependent-ability check (Layer 2: does the team
   already have the enabling weather/terrain secured elsewhere), not just role_shape_context
   alone as earlier text implied.

2. This ADR's original text described move/role resolution (the "by move" or "by role"
   dispatch for a chosen need) as potentially happening inside this tool. As shipped and
   as corrected during design discussion, query_support_needs stops at surfacing named
   need options — it does NOT resolve a need to move-narrowing candidate search, Compendium
   lookup, or any ability-based search. That dispatch is a separate, later step (the
   orchestrator's job, once a specific need is chosen), consistent with the "orchestrator
   decides which tool to call" framing already established in Amendment 2026-08-02b.

**Status:** Corrects ADR-022's description of query_support_needs to match the shipped
recommender/support_needs.py (2026-08-02). No change to the tool's underlying design intent
— these are documentation corrections, not behavior changes.

---

### ADR-022 — Amendment 2026-08-02d

**Uniform candidate-pool interface: every tool in ADR-022's toolkit should accept an
optional candidate pool as input, and any tool producing a species list is a valid source
for that pool — establishing composable, stackable tool chaining rather than a fixed
pipeline order.**

Surfaced while designing what was originally scoped as a fourth, separate tool
(query_theme_refinement_candidates — given an under-constrained locked theme like mono-
Fairy, propose narrower compatible sub-themes). That original framing required enumerating
the space of possible sub-themes directly, which has no natural, bounded answer ("what
sub-themes exist below mono-type?" is not an enumerable question the way "which species
satisfy mono-Fairy" is). The design collapsed once reframed: rather than enumerating
themes, enumerate the LEGALITY-FILTERED SPECIES POOL under the locked constraint (already
a solved, bounded problem) and let theme inference happen per-candidate, reusing existing
archetype classification — at which point the operation became identical in shape to
query_counters/query_threat_counters, just with a narrower starting pool instead of the
full legal species set.

**This generalizes into a standing interface requirement, not a one-off fix:**

1. Every query tool (query_counters, query_threat_counters, query_support_needs where
   applicable, and any future tool) SHOULD accept an optional `candidate_pool` parameter,
   defaulting to the full legal species pool when omitted.
2. Any tool or mechanism that produces a species list — a legality/theme filter, a Role
   Compendium category lookup (once ADR-019 is built), query_by_usage's own output (see
   below), or even a prior query_counters/query_threat_counters call's ranked result — is a
   VALID SOURCE for another tool's candidate_pool input. There is no fixed, required
   pipeline order; tools compose by whichever pool-producing step precedes them in a given
   reasoning chain.
3. query_theme_refinement_candidates as a separately-named fourth tool is RETIRED — its
   function is now: theme-lock a legality filter to produce a narrowed pool, call
   query_by_usage (see companion amendment/task) on that pool to get a starting anchor
   candidate, and let the normal per-candidate reasoning pipeline (theme inference,
   query_counters, etc.) proceed from there. No new dedicated tool is needed.

**New tool: query_by_usage(pool=None).** The bootstrap/starting-point tool — ranks a
candidate pool (full legal pool by default, or any narrower pool per point 2 above) by
usage alone via rank_and_cut, cut to a presentable set. This is the concrete mechanism for
two previously-unimplemented cases already named in this ADR's original text: the "nothing
exists yet" branch of the narrowing loop (no theme, no anchor -> ask_user, surfacing real
usage-grounded options rather than an invented pick), and the under-constrained-theme
branch (mono-Fairy has no single natural anchor -> query_by_usage on the theme-narrowed
pool provides real starting candidates to present).

**Note on scope asymmetry:** for tools with both an "anchor/threat" side and a "candidate/
teammate" side (query_threat_counters specifically), pool-restriction applies only to the
candidate/teammate-producing side, never to threat identification — a locked team theme
narrows who's being searched FOR, not what threatens the anchor, which remains sourced from
the full, unrestricted meta regardless of the team's own theme.

**Status:** Retires query_theme_refinement_candidates as a planned fourth tool; establishes
the uniform pool-in/pool-out interface as a standing contract for this and future tools;
introduces query_by_usage as the toolkit's bootstrap mechanism.

---

## ADR-023: Orchestrator consumption procedure — how ADR-022's tool outputs actually get
combined, held, and merged across a single slot-fill

**Decision:** ADR-022 specified WHICH tools exist and WHEN to call them (the narrowing
loop), but never specified the concrete procedure for HOLDING their outputs across a
multi-tool sequence, COMBINING outputs from different branches into one final answer, or
TERMINATING the loop with a real action. This gap was directly responsible for a real,
observed orchestration failure (see below) — ADR-022's own cross-branch overlap note was
descriptive prose relying on the orchestrator to "remember" to check it, and the loop had
no specified exit at all. This ADR closes both gaps with a real, structural procedure.

**Why this is a distinct problem from anything ADR-022 already covers:** ADR-022 designed
the capability layer (four tools, each independently correct) but not the consumption
layer (how a caller actually sequences and combines them, and how the loop actually ends).
Prose instructions embedded in an ADR ("the composition step should check for this overlap
explicitly") are not a structural guarantee — this project has already established,
repeatedly, that anything this important needs to be a callable step with a real trigger,
not a reasoning-step courtesy (same lesson behind ADR-021's verification gating, the fixed
intrinsic-signal tables, and rank_and_cut's tiered-admission rules rather than relying on
judgment calls).

**Motivating failure (role-play session, 2026-08-02):** building around Kingambit,
Farigiraf simultaneously satisfied the threat-counter branch (answers Psychic-type
pressure from Staraptor/Sneasler), the support-needs branch (resolves an open Trick-Room-
setter need), and had real cooccurrence data supporting the pairing — but the orchestrator
did not connect these until explicitly prompted. Separately and more fundamentally, the
orchestrator ran the three query tools and then simply stopped — it never reached a point
of presenting options to the user, taking a choice, and locking a slot. Both are named as
orchestration/composition failures distinct from factual errors: proof that (a) the
cross-branch check needs a hard structural home, not orchestrator judgment, and (b) the
loop's exit needs to be a mandatory, concrete action chain, not assumed to happen once the
tool calls are done.

### The procedure

**1. SlotFillContext — new, explicit scratch state for one narrowing-loop invocation.**
Not part of `RecommenderState`/`team_draft` (which holds committed/proposed team state) —
a lightweight, per-invocation structure holding intermediate tool outputs across the
several calls one slot-fill operation may involve:

    @dataclass
    class SlotFillContext:
        anchor: PokemonSpecOptional
        role_shape_context: RoleShapeContext
        threat_counter_results: list[ThreatCounterCandidate] | None = None
        support_needs: list[SupportNeed] | None = None
        chosen_need: SupportNeed | None = None
        need_resolved_candidates: list[...] | None = None
        annotated_candidates: list[...] | None = None   # see step 3

**2. Branch execution — both branches run, but on different timelines.**
- Threat-driven branch (`query_threat_counters`) is fully self-contained and deterministic
  (already internally verified via `classify_matchup`) — runs to completion with no user
  interaction required, populating `threat_counter_results`.
- Support-driven branch (`query_support_needs`) only surfaces named need OPTIONS — it
  cannot produce a candidate list until a human (or the orchestrator, per ADR-018's
  propose-a-default framing) picks one AND that need is resolved via whichever dispatch
  path fits (move-narrowing candidate search / Compendium lookup / ability-search, per
  ADR-022's original three-path design). This is inherently a later, round-trip-dependent
  step — `support_needs` populates immediately, `chosen_need`/`need_resolved_candidates`
  populate only after a choice is made.

**3. MANDATORY ANNOTATION STEP — runs as soon as BOTH `threat_counter_results` and
`support_needs` exist, BEFORE any need is chosen.** This is the structural fix for the
Farigiraf-shaped failure: for every candidate already present in `threat_counter_results`,
check whether it INDEPENDENTLY satisfies any of the surfaced need categories in
`support_needs` — reusing existing archetype/ability classification, no new tool calls,
no waiting on a user choice. This is cheap and must not be skipped:

    def annotate_overlap(ctx: SlotFillContext) -> list[AnnotatedCandidate]:
        # for each candidate in ctx.threat_counter_results, check membership against
        # each need category in ctx.support_needs; attach matching needs as metadata

A candidate satisfying both a verified threat-answer AND an independently-surfaced need
category is exactly the Farigiraf case, and this step surfaces it BEFORE the user ever has
to explicitly pick a need — it becomes the natural, boosted default candidate per ADR-018's
"propose a concrete default" principle, since it answers more than one open question at
once.

**4. IF the user explicitly chooses to search by a specific surfaced need** (rather than
accepting a boosted default from step 3), THAT triggers the full resolution pipeline
(dispatch to move-narrowing/Compendium/ability-search) producing `need_resolved_candidates`
— and a SECOND, equally mandatory merge step runs: intersect/score overlap between
`need_resolved_candidates` and `threat_counter_results` the same way, since a candidate
newly surfaced by the chosen-need search might also independently answer a threat that
wasn't obvious from the cheap step-3 annotation alone (step 3 only checks candidates
ALREADY in `threat_counter_results`; a need-search can surface entirely new candidates not
in that list at all).

**5. TERMINAL ACTION — present, receive choice, lock, hand off. Not optional, not a one-
line gesture; the loop is not considered complete until this executes end to end.** This
is the piece most directly responsible for the observed stall: the orchestrator's entry
(ADR-022) and middle (steps 1-4 above) were concrete, but nothing previously specified what
to actually DO with an annotated candidate pool once produced. Step 5 chains entirely
EXISTING, already-shipped mechanisms — no new machinery is required, only the explicit,
mandatory sequencing of what already exists:

   a. **Present.** Call `pick_default_and_alternatives` (already shipped, move-narrowing's
      ADR-018 bridge — reuse directly, do not build a second presentation mechanism)
      against the annotated/merged candidate pool from steps 3-4. A candidate satisfying
      multiple branches (the Farigiraf case) surfaces as the default; single-branch matches
      are the alternatives. This produces the actual message/options shown to the user —
      the loop does not terminate at "I have a ranked list," it terminates at "the user
      has been shown something and can react."

   b. **Receive.** The user's response (accept the default, pick an alternative, reject all
      and ask for something else, or — per ADR-022's multi-slot-lock note — indicate more
      than one candidate should be locked at once, e.g. a candidate that resolves two open
      slots) is the actual continuation trigger. This is not a new mechanism — it is
      `classify_input`'s existing intent-routing (the "lock" intent, already shipped as
      part of multi-turn steering), receiving this specific presentation's output as its
      context.

   c. **Lock.** On acceptance, call the EXISTING lock mechanism (`apply_lock`, with
      `simultaneous_lock_conflicts` handling if more than one slot is being committed at
      once, per ADR-020/the dependency-circle work) to actually commit the chosen
      candidate(s) to `team_draft`. This is not new machinery — it is the same mechanism
      every other user-lock action in this system already uses; SlotFillContext's job ends
      here, its output becomes a real, committed team_draft change.

   d. **Hand off.** Once a slot is locked (species now committed), control returns to
      ADR-022's own stated integration point: refinement of that slot's remaining
      attributes (moveset/item/spread) proceeds via the EXISTING refinement path (tier-1
      cache -> move-narrowing candidate search -> dependency-circle propagation) — this is
      not this ADR's concern, ADR-022 already correctly scopes this hand-off; step 5 just
      needed to actually REACH that hand-off point rather than stalling before it.

   **One legitimate exit that is NOT a stall:** if the user explicitly defers ("not now,"
   "let's come back to this slot later," or an equivalent per ADR-018's deferral handling)
   — that is a valid, designed terminal state, distinct from the loop simply running out of
   specified steps. SlotFillContext should be discardable/re-enterable in this case, not
   treated as an error.

**Why this had to be explicit rather than assumed:** every individual piece referenced in
step 5 (`pick_default_and_alternatives`, `classify_input`'s lock intent, `apply_lock`, the
refinement hand-off) already exists and is already correctly specified elsewhere in this
project. The gap was never a missing mechanism — it was that no single place stated "after
annotation, call these in this order, and do not stop until the loop has actually reached a
locked slot or an explicit user deferral." A procedure whose steps all exist individually
but are never chained into a mandatory sequence is exactly as prone to silently stalling as
a check that exists in prose but has no structural trigger — this correction closes both
failure shapes the same way: by making the full chain, start to terminal action, a single
specified, non-optional procedure.

### What this ADR resolves vs. leaves open

**Resolves:** the cross-branch overlap check (now a mandatory, structurally-triggered step,
twice — cheap annotation as soon as both branches' initial outputs exist, full merge if a
need-search is explicitly triggered); the loop's missing terminal action (now a mandatory,
concrete chain of entirely existing mechanisms — present, receive, lock, hand off).

**Does NOT resolve** (remain open, tracked separately, NOT silently absorbed by this ADR):
- Speed-axis bidirectionality (Trick Room vs. Tailwind as mutually exclusive answers) —
  a `query_support_needs` output-shape question, orthogonal to consumption-layer design.
- Team-state-scaling abilities (Supreme Overlord) having no tool home.
- `query_threat_counters`'s two internal `rank_and_cut` passes diverging — this ADR
  specifies what happens to that tool's OUTPUT once produced, not its internal logic;
  divergence within the tool itself is unaddressed.
- Ability-flipped threats (Defiant/Intimidate) — a `query_counters` axis gap.
- Champions' single-Mega-per-team constraint — a real team-composition constraint with
  no checking mechanism anywhere yet, including in this ADR's procedure. Worth flagging as
  a natural candidate for a future global-constraint check within SlotFillContext or
  team_draft-level validation, but not designed here.
- `classify_matchup`'s single-`build_a` signature vs. ADR-016's range-of-variants cache —
  a verification-input-sourcing question, not a consumption-procedure question.

**Status:** New ADR. No implementation yet. Directly informed by real, observed
orchestration failures during role-play testing (2026-08-02) — see master_project_log.md
for the full session summary. Six additional gaps from the same session remain open and
untracked by this ADR; each needs its own resolution.

---

### ADR-023 — Amendment 2026-08-02a

**Resolution of the six remaining gaps flagged during the 2026-08-02 role-play session.**

Two gaps dissolved on closer inspection (they were misdiagnosed, not real design holes);
two received concrete resolutions; one is accepted as risk; one is reframed and deferred to
future quick-pick design rather than resolved now.

**Dissolved — gap 1 (Speed-axis "bidirectionality"):** the original finding assumed Trick
Room and Tailwind must be presented as mutually exclusive answers to query_support_needs'
Speed-axis trigger. This is incorrect — this project already established TailRoom
(Tailwind+TrickRoom as a real, valid composite archetype, ADR-020) confirming a team can
legitimately want both simultaneously. No fix needed: query_support_needs already surfaces
named need options rather than forcing a single pick, which correctly accommodates this.
No change to the tool's design.

**Dissolved — gap 4 (ability-flipped threats, e.g. Defiant/Intimidate):** this collapses
into the already-accepted, already-logged scope limitation from ADR-021 Amendment
2026-08-01b — query_counters' KO-threshold axis deliberately does not chase ability-
conditional interactions (no calc-service calls, static/known multipliers only). An
ability-flip case is a specific instance of this same, already-documented deferral, not a
new or separate gap. No additional tracking needed beyond the existing amendment.

**Resolved — gap 2 (team-state-scaling moves/abilities: Supreme Overlord, Rage Fist, Last
Respect):** these three (one ability, two moves) share the same pattern — effective power
scales with a team-battle-state count (fainted teammates) not knowable at team-building
time. Resolution: use a fixed, stated assumed count for the KO-threshold BP estimate,
rather than treating this as unknowable or building real battle-state simulation. Given the
scaling only matters once nonzero (a rational player uses these specifically when the
boost is worth it), use the AVERAGE OF THE NONZERO STATES (1, 2, 3 teammates down -> average
2), not the average across all four possible states including zero (which would be 1.5).
This is a stated, reasoned assumption (not empirically probed, since there's no real usage
data to check it against the way threshold/margin values were checked elsewhere this
session) — document the choice and reasoning directly in code, consistent with this
project's standing practice of stating and justifying numeric defaults rather than leaving
them implicit.

**Accepted as risk — gap 3 (query_threat_counters' two rank_and_cut passes diverging):** no
reconciliation check is built, and none is planned. Accepted, consistent with several other
residual-risk-not-blocker findings from today's design work (tier-0 overshoot, incomplete
multi-hit tables, etc.).

**Reframed and deferred — gap 5 (Mega-count constraint):** the original finding
mischaracterized this as a hard, Item-Clause-style legality rule. It is not — Champions
places no legality restriction on how many Mega-Stone-capable Pokemon a team_draft can
contain; the real constraint (only one can actually Mega Evolve per battle) applies at
PICK time (quick-pick, ADR-012a), not team-composition time, and nothing is illegal about
holding several. The actual insight is a SOFT, efficiency-driven heuristic derivable from
the format's pick count: max USEFUL Mega-Stone holders during team-building ≈
1 + (team_size - pick_count) — e.g. doubles (6 Pokemon, pick 4): 1 + 2 = 3; singles (pick
3): 1 + 3 = 4. This is NOT a team_draft validation rule (does not belong near Item Clause's
hard-check logic) — it is a candidate for soft, ADR-018-style guidance ("you already have N
other Mega-Stone holders locked, worth knowing") surfaced during team-composition-stage
narrowing, informed by an anticipated picker-time constraint. Quick-pick itself has not
been designed at all yet. DEFERRED: do not build this now; revisit once quick-pick design
begins, since the exact numbers depend on knowing the format's real pick count and
quick-pick's own eventual behavior.

**Resolved — gap 6 (classify_matchup's single build_a vs. ADR-016's range of cached
variants):** use the single MOST COMMON cached build for verification. If no cached build
exists for a species at all, construct one from top usage data (reusing tier-1/tier-2's
existing fallback relationship — this is not new logic, it's the same cache-miss-falls-
through-to-usage-sourced-build pattern already established elsewhere in this project, e.g.
propose_team_draft's own tier-1-then-tier-2 fallback). Do not attempt to verify against
every cached variant — one representative build per species is sufficient for this tool's
purpose.

**Status:** Closes out all six gaps flagged during the 2026-08-02 role-play session
(alongside the terminal-action and cross-branch fixes already in ADR-023's main text). Two
dissolved as misdiagnoses, two resolved with concrete, stated defaults, one accepted as
risk, one correctly reframed and deferred to future quick-pick design rather than solved
prematurely.

---

### ADR-023 — Amendment 2026-08-03a

**Need-resolution consumption: auto-resolve all surfaced needs (species-only presentation).**

Step 4 of ADR-023's main text described need resolution as triggered when the user
explicitly chooses a surfaced need. That framing is superseded for orchestrator behavior:
`query_support_needs` still only surfaces named need tags, but the orchestrator
auto-resolves every teammate-path need behind the scenes (`resolve_all_support_needs` in
`recommender/slot_fill.py`), merges into the annotated candidate pool, and presents species
(default + alternatives per ADR-018). Needs remain annotation metadata explaining why a
species was suggested — never a user-facing need menu.

`SlotFillContext.chosen_need` remains optional for single-need / test cursors;
`merge_need_resolved` no longer requires it when `need_resolved_candidates` is set.

Dispatch paths (shipped): move-narrowing (incl. multi-move union for healing/screens/FO);
ability-search for `condition_setter` (`ABILITY_TO_FIELD` ∩ trigger) and FO priority-denial
abilities; `stat_lowering_partner` (Contrary) excluded from teammate resolve (anchor-kit
gap, empty list); `defensive_coverage` still Compendium-deferred.

**Status:** Documents shipped slot_fill behavior (2026-08-03). Does not build Role
Compendium or expand `ABILITY_TO_FIELD` for Hadron/Orichalcum.

---

### ADR-023 — Amendment 2026-08-08a

**Terminal procedure corrected: candidate acceptance no longer commits species before the
complete build is confirmed.**

**Decision:** Split ADR-023's original terminal chain into two stages. Candidate acceptance
now produces `PendingSlotIntent` (cross-turn, pre-commit) rather than calling `apply_lock`
directly. That intent is built into `ProvisionalSlot` — which requires all seven complete-
build fields (species, ability, item, moveset, nature, spread, role) or returns a structured
unresolved result rather than a partial one — then presented for confirmation, then
committed via a new atomic full-slot lock that prevalidates everything (fingerprint/stage
consistency, role/species agreement, seven-field completeness, exactly four moves, spread
bounds/budget, legality/item clause, simultaneous conflicts) and either locks every field
together or changes nothing on failure. `_apply_locks_batch` is left unchanged and remains
the correct path for ordinary partial steering (single-attribute constraint/lock updates
mid-conversation) — this amendment adds a second, stricter commit path, it does not replace
the first.

**Alternatives considered:** Keep the original immediate-commit-then-refine chain and instead
try to make refinement itself more reliable, so a bad commit becomes less likely without
restructuring the terminal sequence. Alternatively, make `_apply_locks_batch` itself
transactional/all-or-nothing and reuse it for this path instead of building a separate one.

**Why:** ADR-023's original chain (present -> receive -> lock -> hand off to refinement)
committed the species via `apply_lock` *before* refinement ran, on the assumption that
refinement was a reliable, always-complete hand-off. A real slot-fill discovery session
(Cursor role-play, 2026-08-08) disproved that assumption directly: Kingambit's build locked
with a missing nature despite usage evidence supplying one, because nothing gated commitment
on refinement actually completing. Improving refinement's reliability alone doesn't fix the
structural problem — an incomplete or wrong build could still slip through a future
refinement bug the same way, because nothing in the terminal chain *required* completeness
before commit. Reusing `_apply_locks_batch` was rejected because it is deliberately
conflict-skipping (it commits the conflict-free remainder and emits pending flags for the
rest) — correct behavior for incremental partial steering, wrong behavior for a "this
candidate is now the confirmed slot" commitment, which needs all-or-nothing semantics.

**Status:** Implemented and verified (431 tests passing, up from 385) as part of the
anchor-role/target-role pipeline (Tracks A-C, 2026-08-08). Does not affect `_apply_locks_batch`
or ordinary partial-steering behavior, confirmed by unchanged passing tests on that path.

---

### ADR-023 — Amendment 2026-08-08b

**Compendium-first need resolution and per-candidate evidence provenance.**

**Decision:** For support-need categories with a mapped Role Compendium category (`trick_room`
→ Trick Room Setter; `condition_setter` → Weather Setter per trigger label among Rain/Sun/
Sand/Snow; `fake_out_protection` → Redirection, as partial coverage alongside existing
mechanical avenues), candidate resolution now checks the compendium first via a new
`role_category_evidence` reader, rather than dispatching straight to raw legal-learner search.
Categories with no current compendium mapping (`tailwind`, `taunt_disruption`,
`healing_cleric`, `screens`, `stat_lowering_partner`, `defensive_coverage`) are unchanged —
this is "compendium first where one exists," not a blanket requirement. A rejection under one
role/condition/mechanism claim (e.g. rejected as a Rain setter) does not suppress a separately
supported claim for the same species (e.g. admitted as a Sun setter); rejection scope matches
the specific claim it was evaluated against, not the species globally.

Each presented candidate now carries typed `CandidateEvidence` (basis: `usage_backed` /
`compendium_backed` / `mechanical_only` / `synthesized`; confidence: `high` / `medium` /
`low`), threaded unchanged through `SlotFillPresentation` → `PendingPresentationOption` →
`PendingSlotIntent`. `AnchorRoleDecision` is explicitly NOT copied into this evidence — it
classifies the locked anchor, not the discovered candidate; candidate provenance is new,
purpose-built evidence, not a repurposed anchor-classification struct.

`_sort_annotated`'s ranking is corrected: compendium confidence is now the **leading** sort
key (exact/high-confidence compendium → species/medium-confidence compendium → no compendium
evidence, each tier then ordered by the existing matched-needs/verified-score/usage-rank
keys), bounded by an **active-need invariant** — compendium evidence with zero matching needs
is rejected by assertion and cannot exist as a candidate state, not merely deprioritized by
sort order. Above that bound, compendium priority is unconditional and intentional: pre-
verified compendium evidence outranks raw usage/threat signal even when the raw-signal
candidate would win on every other existing criterion.

**Alternatives considered:** Rely on stable-sort insertion order (compendium-admitted rows
appended before mechanical extras) to produce compendium-first ranking, rather than an
explicit leading sort key. Copy `AnchorRoleDecision`'s evidence directly into presented-
candidate provenance instead of building a separate `CandidateEvidence` type. Make compendium
priority conditional on also being competitive on existing criteria, rather than unconditional
above the active-need bar.

**Why:** The insertion-order approach was caught in plan review, not after implementation —
`_sort_annotated`'s actual keys (matched-need count, threat-verification score, usage rank)
are primary sort criteria, not tie-breaks, so stable-sort insertion order only preserved
compendium-first behavior among candidates already tied on all three; a mechanical-only
candidate with a stronger usage rank could otherwise outrank a compendium-admitted one,
silently violating the intended guarantee. Verified by an adversarial test
(`test_compendium_priority_beats_all_existing_sort_pressure`) constructing exactly that
case. `AnchorRoleDecision` reuse was rejected because it answers a different question (what
is the anchor's role) than candidate provenance needs (why is this specific species being
suggested) — conflating them would misattribute anchor-classification confidence to
candidates the anchor decision was never evaluated against. Unconditional-above-the-bound
priority was made explicit, not left implicit in key ordering, because compendium membership
is pre-verified evidence (consistent with ADR-021's verification-gating principle) and should
outrank raw signal on that basis — but the active-need bound was necessary because a
compendium member with zero relevance to what's actually being searched for has no business
jumping the queue regardless of how verified its unrelated membership is. Verified by
`test_compendium_priority_requires_an_active_matching_need`, which enforces the bound as a
construction-time invariant (an inadmissible candidate state cannot be built) rather than a
ranking outcome (a lower-priority candidate that could still slip through under different
sort pressure) — a stronger guarantee than what was originally scoped.

**Status:** Implemented and verified (450 tests passing, up from 440, 5 skipped; live dispatch
smoke test passed; no linter errors). Plan file left unmodified by implementation, per this
project's standing documentation-hygiene practice. Deliberately deferred, not oversights:
compendium categories for `tailwind`/`taunt_disruption`/`healing_cleric`/`screens`/
`stat_lowering_partner`/`defensive_coverage` (no compendium exists yet for these); Psychic
Terrain under `fake_out_protection` (current resolver doesn't implement it); new compendium
construction of any kind (out of scope for this task).

---

## ADR-024: Anchor-role classification is a separate producer from target-role decision

**Decision:** `RoleShapeContext` (which describes an anchor's strategic role shape, feeding
`query_support_needs`) and `_pick_role`'s output (which describes what the *open slot* should
become) are produced by two separate, non-competing mechanisms — not one "role decision"
concept applied at two points. A new producer, `classify_anchor_role -> AnchorRoleDecision`,
classifies an existing anchor's strategic role, kit evidence, and mechanism-level execution
detail; `_pick_role`, redesigned, stays scoped to producing `TargetRoleDecision` for the open
slot only. `AnchorRoleDecision` feeds a narrowed `RoleShapeContext` (exactly three fields:
`primary_function`, `tankiness`, `requires_setup_turn`) via a separate, narrow projection
function (`derive_role_shape_context`) that performs no role-identity reasoning of its own.

Supporting design, load-bearing to this decision rather than separable from it:
- **Mechanism evidence uses a three-tier model** (`needed` / `wanted` / `secondary`) per
  mechanic (e.g. Sucker Punch, Drizzle, Tailwind), each tagged with activation mode,
  interruptibility, and whether the anchor self-supplies the effect or expects a teammate.
  `requires_setup_turn` (renamed from `setup_dependent`) derives only from a present
  `needed`/`wanted` mechanism that is itself an exposed, interruptible action the anchor must
  complete before its own payoff — never from a role name, a species-level compendium
  membership the active build doesn't use, or condition-dependence on a teammate-supplied
  effect. `secondary_role_ids` is sourced from `needed`/`wanted`-tier mechanisms supporting a
  distinct role from the primary, not from incidental `secondary`-tier ones.
- **`match_status`, `archetype_id`, and `partial_signals` are removed from `RoleShapeContext`.**
  Match quality moves to `AnchorRoleDecision` as diagnostic classification metadata, never a
  routing shortcut — a clean role/build match does not imply raw support-needs analysis can
  be skipped (disproved directly by Archaludon, whose cleanly-classified build still surfaced
  real support needs). `archetype_id`/`partial_signals` had zero production consumers and
  zero production constructors, confirmed by direct repository search on two separate
  occasions.

**Alternatives considered:** Redesign `_pick_role` alone to handle both the anchor's shape and
the open slot's target role, on the theory that "role decision" is one concept applied twice.
Alternatively, keep `RoleShapeContext`'s original six fields and just fix the one field
(`setup_dependent`) that was observed to produce a wrong value.

**Why:** The single-producer framing was the actual root cause of a real, observed bug, not
just an abstraction preference. Reconstructing the Kingambit slot-fill transcript found three
simultaneously-present, non-interchangeable role concepts for one Pokémon — `infer_role`'s
kit inference (`bulky_attacker`), the user's stated strategic identity (`trick_room_sweeper`),
and the eventual partner's target role (`trick_room_setter`) — and a single unqualified "role
decision" cannot hold all three without collapsing distinctions that matter. The originally-
guessed `RoleShapeContext` (built by treating the strategic label as sufficient) set
`setup_dependent=True` and produced two fabricated needs (Fake Out protection, Taunt
disruption) that the anchor's actual kit (no setup move) didn't warrant. Correcting only that
one field, without separating anchor-shape classification from target-role decision as
distinct producers, would have fixed this one instance without fixing the structural cause —
the same class of conflation could recur with a different anchor/role pair. Removing
`match_status` as a routing signal specifically was necessary because the "clean means skip
analysis" assumption, while intuitive, was directly falsified by real execution against a
second anchor (Archaludon) rather than assumed correct from the Kingambit case alone.

**Status:** Implemented and verified (Tracks A-C, 2026-08-08) — `AnchorRoleDecision`,
`classify_anchor_role`, `derive_role_shape_context`, and the narrowed `RoleShapeContext` are
shipped and tested against Kingambit, Archaludon, Pelipper, and Farigiraf as named acceptance
cases. Ability persistence (`Slot.ability`, required for `all_locked()`) was a prerequisite
sequenced before this work, since several role identities here (Pelipper/Drizzle,
Archaludon/Stamina) are ability-defining and building the classifier on an unverifiable
ability field would have baked that gap into every derived decision. Deliberately deferred,
not resolved by this ADR: a permanent canonical strategic-role taxonomy (`role_id` remains an
opaque identifier, not an enumerated vocabulary); move-derived condition dependence (e.g.
Electro Shot -> Rain), explicitly scoped out to avoid drift beyond what this decision
required.

---

## ADR-025: Team-phase routing — confirmed-lock-count phases with a per-lock recompute
trigger, not a fixed threshold

**Decision:** Route slot-fill behavior through four phases derived purely from the count of
fully confirmed (`all_locked`) slots — `empty` (0), `single_locked` (1), `multi_locked` (2+,
single bucket), `complete` (all slots locked) — via an explicit `route_team_phase` graph node,
rather than a single undifferentiated proposal sequence that never changes as the team fills.
Team-wide signals (coverage, SPOF) are recomputed on every entry to `multi_locked`, not cached
at phase entry and not gated behind any fixed lock-count threshold beyond the 2-lock floor.
Each phase gets exactly the behavior its available evidence supports — `single_locked`
dispatches to the real, tested Track C anchored-discovery chain; `multi_locked` gets real
signal recomputation but not full multi-member candidate ranking (shared-teammate
intersection, condition resilience, and selected-four evidence remain unavailable and are
explicitly not simulated); `empty` and `complete` get real routing to what already exists
(`bootstrap_direction` as a stub, `generate_team_review` made automatic) without inventing
capability that doesn't exist yet.

**Alternatives considered:** Keep the pre-existing single fixed proposal path regardless of
team fill state. Use a fixed "switch modes at N locked" threshold — the original slot-fill
discovery report proposed "roughly three locked" as the anchor-to-team-wide transition point.
Cache team-wide signals once at phase entry rather than recomputing on every lock.

**Why:** A real, observed failure (Cursor slot-fill discovery role-play, Archaludon scenario)
showed the actual bug was not a threshold problem — the orchestrator kept relying on
Archaludon's stale teammate list after team composition had already changed, producing a
redundant Rain-offense pick (Basculegion) once Mega Swampert already filled that role. A
targeted follow-up check against the actual role-play transcripts (not the discovery report's
own summary of them) confirmed shared-teammate and coverage signals were already computable
and were correctly used at exactly 2 locked members (Archaludon + Pelipper), one full lock
before the report's proposed 3-lock boundary — meaning "roughly three locked" overstated the
importance of the count itself. The real fix is a recompute trigger (refresh team-wide signals
on every lock), not a boundary at any particular N. A second transcript (mono-Fairy, six
slots) confirmed no orchestrator behavior changes at any count boundary past 2 locked (checked
explicitly at 3/4/5/6) — supporting one `multi_locked` bucket rather than finer count-based
phases — while six-lock terminal review was confirmed materially distinct in kind (validating
a finished roster, not generating a next candidate), justifying `complete` as its own phase
rather than folding it into `multi_locked`.

**Status:** Implemented and verified (`recommender/nodes.py`, `recommender/graph.py`;
`tests/recommender/test_team_phase_routing.py`; 440 tests passing, up from 431, 5 skipped).
Deliberately deferred, not oversights: `empty`'s combined direction+available-pool interaction
(new UX design, not a missing backend capability — left as a documented stub); `single_locked`'s
owned-first propagation, target-role Compendium dispatch, and complete target-role resolution
for threat-only candidates; `multi_locked`'s shared-teammate intersection, condition
resilience, role-duplication scoring, and selected-four evidence, none of which have a
built mechanism yet. The labeled static fallback for an unavailable calc service remains a
separate, unresolved gap — coverage/SPOF still fail hard, unchanged by this pass.

---

