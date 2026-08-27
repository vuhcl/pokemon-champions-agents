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

### ADR-014 — Amendment 2026-08-08b

**Structured runtime teammate lookup exception.**

Exact-form teammate queries may fetch one structured MunchStats species record when the
bundled snapshot has no usable teammate record (offline row absent — matching the existing
`fetch_live_spreads` trigger condition exactly; a malformed-but-present offline row returns
explicit unavailable evidence, it does not trigger live fetch). No live CBD fetch is
authorized for teammate queries — CBD fallback reads only the existing offline/bundled
record.

This extends the existing per-species runtime exception from spread evidence to teammate
co-occurrence evidence, using the same `recommender/usage_live.py` mechanism: fixed
regulation/month/rating mappings, known endpoints, deterministic parsing, cached misses, and
no model-directed or free-form search. Construction-scoped extractors remain unavailable to
runtime paths.

MunchStats preserves exact-form IDs and ladder-weighted conditional percentages. CBD labels
that cannot establish an exact form remain explicitly ambiguous or unresolved; missing
percentages are not inferred.

This exception applies only to callable individual queries and shared signals during the
`multi_locked` phase. Complete-roster teammate review and candidate-ranking consumption
remain out of scope — `complete` phase publishes `shared_teammates: None` without querying.

**Status:** Broadens the bounded structured per-species runtime exception to include
exact-form teammate co-occurrence, MunchStats live fetch only, gated strictly on offline-row
absence. CBD fallback is offline-only, not a second live exception. ADR-014's general
prohibition on runtime web search remains unchanged.

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

### ADR-010 — Amendment 2026-08-10a

**REPL shape, session policy, rendering layer, and provider wiring — filling in ADR-010's
originally undecided scope.**

**Decision:** A thin stdlib REPL (`recommender/cli.py`/`__main__.py`) owns process lifetime
directly — no framework, no `compile_cli_graph` wrapper beyond a literal
`open_sqlite_checkpointer() + resolve_bootstrap_parser() + compile_graph(...)` composition.
Terminal rendering is a genuinely separate presentation layer (`recommender/present_text.py`,
pure `format_turn(state) -> str`, no I/O), not formatting logic embedded in graph nodes.
Session identity/resumption: newest-updated incomplete thread resumes by default with no
flags; `--new`/`--thread ID`/`--list-threads` as explicit overrides; "incomplete" is
`team_phase != "complete"` OR any pending/provisional state set. Meta commands
(`:q`/`:thread`/`:team`/`:new`/`:reset`) are handled entirely outside the graph — `:reset`
specifically stays a mint-new-thread alias rather than routing to the graph's `reset` intent,
structurally incapable of issuing a `pending_input` invoke at all. LLM provider selection for
bootstrap intake is env/flag-driven (`POKEMON_CHAMPIONS_LLM_PROVIDER`), mirroring ADR-013's
existing Ollama-for-dev/hosted-for-demo pattern with a new Anthropic factory built against the
same structured-output schema as the existing Ollama factory.

**Alternatives considered:** always-silently-resume the last session with no override. Always
require an explicit `--new`/`--thread` flag (no default resume). Wiring `:reset` to the
graph's actual `reset` intent. A richer TUI/framework-based interface.

**Why:** Always-silent-resume was rejected because a finished six-member team and a half-built
experiment would share one database with no escape hatch — a real risk of a demo session
silently continuing a stale, unrelated team. Always-requiring an explicit flag was rejected
because it fights the entire point of the SQLite checkpointer work (continuation after
restart) by making resumption opt-in every single time rather than the natural default.
Wiring `:reset` to the graph's real reset intent was rejected because it would have required
building a pending-free classification bypass, reopening ADR-027's deliberate closed-set-vs-
LLM boundary for a convenience that a simple mint-new-thread alias already achieves without
touching that boundary at all. A richer TUI was rejected as unnecessary scope for v1 — plain
stdout is sufficient, and colors/paging can be added later without any structural rework,
since rendering is already a separate, pure function.

A genuine SQLite concurrency defect was found and fixed during implementation, worth recording
as a real technical constraint rather than an incidental bug: nesting a `graph.get_state`
query inside an open `saver.list(None)` cursor on the same `SqliteSaver` connection deadlocks
— confirmed via an actual reproducible hang, not theoretical. Fixed by fully materializing the
thread list before issuing any per-thread `get_state` query. Worth noting as a constraint for
any future code composing these two APIs on a shared connection.

**Status:** Implemented and verified — 754 tests passing (up from 726), 7 skipped matching
baseline. A real automated end-to-end smoke test exercises the full session lifecycle
(bootstrap → candidate selection → build confirmation → lock → connection close/reopen →
resume) rather than relying on manual testing. The first-turn landmine (never sending
`pending_input` on a brand-new session) and the pre-invoke `NotImplementedError` guard are
each covered by dedicated tests proving the specific mechanism, not just end-to-end happy-path
behavior.

**Deliberately deferred, tracked as separate future scope:** generic free-form classification
without a pending presentation (deliberately avoided rather than implemented, per ADR-027);
web/hosted UI and any Postgres/Redis checkpointer; rich TUI/colors/pager; canonical name/form
resolution (now the last remaining structural gap in the project, unrelated to this ADR).

---

### ADR-010 — Amendment 2026-08-11a

**`turn_intent="deferred"` for successful soft-exit, distinct from unmatched
`pending_response`.**

`classify_pending` used `pending_response` both when a closed-set reply was unrecognized
(keep `pending_presentation`, re-prompt) and when `defer` correctly cleared pending (ADR-022
discardable terminal). The CLI unmatched check (`turn_intent == "pending_response"`) could not
tell these apart, so a successful defer rendered with "Didn't catch that." plus the idle/
roster body.

Defer on `candidate_selection`, `completion_preference`, and `full_build_confirmation` now
emits `turn_intent="deferred"` with the same pending/provisional clears. Graph maps `deferred`
to the existing `finish_pending_response` no-op (unknown intents fall through to
`route_team_phase` and would rediscover). `pending_response` is reserved for genuine unmatched
input. `candidate_discovery_error` is left set on defer — last-discovery calc health, not
presentation lifetime.

**Status:** Implemented. Recognition of defer phrases unchanged; CLI heuristic unchanged.
Verified via two independently required test layers (emit: `classify_pending` returns
`turn_intent == "deferred"` for all three kinds; render: `handle_line` omits the unmatched
prefix for a successful defer while a genuinely unmatched reply still shows it) — neither
layer can pass for the other, since emit never renders and render never classifies. Graph-
route regression confirmed via the real graph, not mocked. 805 tests passing (up from 796), 6
skipped, matching the established baseline. Read-only mirrors untouched.

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

### ADR-015 — Amendment 2026-08-09a

**Tier-3 last-resort build synthesis, gated by a correctness fix to ADR-024's mechanism-
evidence model.**

**Decision:** When usage/cache lookup misses (ADR-015's tiers 1-2 fail to produce a complete
build), the slot-fill refine path now attempts deterministic last-resort synthesis for item,
moves, spread, and nature — reusing existing mechanisms only (`diagnose_and_substitute`'s
item candidates, extended `assemble_moveset_fallback` role-pref pools, the existing spread/
`role_spread` gate, a small nature-derivation helper in the spirit of `_scarf_nature_
correction`). Ability synthesis is deliberately narrower: filled only via
`resolve_anchor_build`'s existing `_unique_legal_ability` discipline (exactly one legal
option) or a role constraint uniquely selecting one among several — never a guess among
multiple ambiguous options. If moves still fall short of four after exhaustive legal
narrowing, or ability remains genuinely ambiguous, the build honestly stays
`UnresolvedSlotRefinement` rather than padding with arbitrary learnset noise or a guessed
ability.

**Prerequisite correctness fix (ADR-024's `_mechanisms`, not a separate architectural
decision but load-bearing to this one):** confirmed via direct probe that ability-derived
mechanism evidence previously treated `build.ability` as a flat fact regardless of provenance
— a synthesized, entirely guessed Drizzle produced `present=True`, `confidence="high"`, and
`match_quality="clean"`, indistinguishable from a real confirmed ability at the exact point
role classification depends on it. Fixed by gating ability-derived mechanism emission on
provenance: `present=True` with real confidence only for `user_confirmed`/`usage_derived`/
`legality_only` sources; `synthesized`/`provisional` sources omit the mechanism entirely.
Shipped as its own sequenced prerequisite task, merged before any synthesizer code could write
`synthesized` abilities — not bundled speculatively.

A second, related gap was found and fixed during confirmation, in code neither planned task
had touched: `_role_decision` (candidate scoring, not anchor classification) labeled every
candidate kit ability `provisional`, which the new gate correctly omits — causing a real,
already-confirmed candidate ability (e.g. a genuine Drizzle from usage data) to stop
registering as a mechanism provider during composition-fit scoring. The first proposed fix
(unconditionally locking any `spec["ability"]` value) was rejected before acceptance — it
would have reopened the same gap this amendment closes, resting on an unverified "usually
comes from usage" assumption and falsely labeling the result `user_confirmed`. Corrected via
a real call-site trace confirming production paths reaching `_role_decision` populate ability
strictly from `featured_or_common_set`; the fix elevates a kit ability only when it actually
matches that data, labeled `usage_derived` with `confirmed=False` — grounded in a real check,
not trusted by convention.

**Alternatives considered:** picking an arbitrary legal ability among multiple options at low
confidence, labeled `synthesized`, when no role-mechanism match exists. Treating usage-
coverage expansion (more species entering the offline snapshot) as sufficient to close this
gap on its own. Role-adjacent species build-borrowing as a last resort.

**Why:** The arbitrary-ability-guess approach was proven unsafe, not just stylistically
rejected — six separate downstream consumers (`derive_role_shape_context`, `target_role_
from_strategic_evidence`, `condition_resilience`, `team_candidates` duplication checks, and
others) all key off `MechanismEvidence.present`/`importance` with no provenance branching, so
recording `source=synthesized` alone would not have protected any of them. Reusing the
existing unique-ability discipline instead of inventing new guessing logic meant there was no
guess left to carefully label. Usage-coverage expansion was rejected as a complete fix
(confirmed complementary only) via a direct experiment: mocking away both live and offline
spreads and running pure `tier3_role` synthesis still left nature and ability empty, proving
an algorithm gap exists independent of data coverage — thin competitive usage and live-fetch
failure are permanent edge cases, not something more ingestion eventually resolves. Role-
adjacent borrowing was rejected as too contamination-prone for v1, consistent with ADR-015's
own original preference for role-pattern-plus-verification over cross-species copying.

**Status:** Implemented as two sequenced tasks (the `_mechanisms` gate merged independently
before synthesizer code began) plus one confirmation-phase correction, all verified with
named regression tests including both the original synthesized-Drizzle probe and a negative
case (an unusual ability like Damp correctly staying non-authoritative). 659 tests passing at
ship, up from 385 at the start of this session's slot-fill arc. Deliberately deferred:
Mimikyu/usage-coverage expansion (complementary, not a substitute); role-adjacent species
borrowing; recursive `recommend_build` calls for opponent builds; the hardcoded opponent list
inside `_tier3_verify_spread` (a separate, orthogonal ADR-015 fidelity gap); calc verification
wiring into provisional build emission; `recommend_build`'s own nature path (untouched by this
amendment — only slot-fill's `_refine_defaults` was in scope).

---

### ADR-015 — Amendment 2026-08-09b

**`infer_role` (tier 2) vocabulary redesign — three-axis offense classification, driven by
a full usage scan rather than incremental patching.**

**Decision:** Replace `infer_role`'s two-value offense output (`fast_attacker`/
`bulky_attacker`) with a nine-value vocabulary spanning two independent axes: speed/
investment signal (`fast`/`bulky`/`standard`) × damage category (`physical`/`special`/
`mixed`), derived from real move-category damage bias on the active kit, not base-stat
inference. Two non-offense archetypes added (`fast_pivot`, `screens_support`);
`trick_room_sweeper` and `support_speed_control` retained unchanged. A backward-compatible
alias layer (`_DEPRECATED_ROLE_ALIASES`) maps the old two-value strings to their new
equivalents for any caller still holding a locked `TargetRoleId` using the prior vocabulary.

The redesign was driven by a full 180-build usage scan (50 in-game top-usage species + 77
Showdown featured sets + ability/dual-set variants) rather than patching the single case that
motivated it — confirming `infer_role`'s fallback wins 126 of 180 builds (70%), the majority
classification path for real top-usage kits, and that every multi-ability species in the
scanned corpus either under-differentiated on ability or only differed because an unrelated
signal happened to already fix the label.

**Alternatives considered:** patching the single motivating case (a Technician-ability
Maushold build) in isolation. Escalating differentiating-but-narrow patterns found by the
scan (Fake Out/Intimidate support, screens-heavy kits) directly into new Role Compendium
categories. A single bulky/fast axis with Mega-stone builds resolved into whichever bucket
seemed more common.

**Why:** Patching only the motivating case would have left the same gap open for the other
125 majority-path builds the scan actually found, and risked repeated incremental
redesigns of a vocabulary "never put much thought into" in the first place — better to see
the full shape once than patch it repeatedly. Widely-differentiating gap-table patterns were
kept at mechanism tier rather than promoted to Compendium categories, per this project's
existing tier-worthiness criterion (ADR-015 Amendment 2026-07-28d: role-specific search with
contested membership, not "just needs something strong" or taxonomic completeness) — Fake Out
support specifically was judged genuinely Compendium-plausible but held back pending actual
product role-search need, not escalated on differentiation alone. A single-axis Mega-stone
resolution was rejected after checking real post-Mega stat data: several Mega formes
(Metagross, Kangaskhan, Dragonite) carry simultaneous high-Speed *and* high-bulk signal where
a Speed-led rule and a bulk-led rule would disagree on the same Pokémon — confirming Mega
stones genuinely lack the single-direction signal that items like Leftovers or Life Orb
reliably carry, so the `standard_*` (no-signal) bucket is the honest answer, not a convenience.

A real dependency-circle risk was found and resolved during design review, not after
implementation: the tier-3 pin's spread half (`role_spread("trick_room_sweeper")`) is a
hardcoded literal, independent of `infer_role`; its role half
(`_propagate_and_refine`'s direct `infer_role` call) is not, and depends on `infer_role`
still returning `trick_room_sweeper` for Trick Room movesets — a different call site than the
one the original "effectively dead" removal reasoning actually covered. Resolved by keeping
the return rather than updating the pin, preserving existing tested behavior exactly.

**Status:** Implemented and verified — every gap-table `infer_role` row mapped to a named
before/after test (Mega-stone special attackers no longer land on bare `bulky_attacker`;
Archaludon's Leftovers/Electro Shot kit no longer misclassifies as a pivot; Garchomp/
Hydreigon differentiate correctly on physical/special; Technician Maushold reaches the fast
axis via the multi-hit hook). `role_spread` coverage verified complete via a parametrized
test over the full vocabulary plus both legacy aliases (14 values, each summing to exactly 66
points), not a manual spot-check. Signature changes threading ability through `anchor_roles`,
`propose`, `reconcile`, and `recommend_build` confirmed via a real repo-wide search for every
production caller, not assumed complete from the sites already touched. 709 tests passing (up
from 659), 7 skipped, matching the established baseline exactly.

**Deliberately deferred, tracked as separate future scope:** Fake Out support as a Role
Compendium category (candidate-only, pending product need); screens/Encore/Hospitality
mechanism emission (roster role-structure grouping's separately-tracked "Step A"
precondition); a `to_id` display-name mismatch confirmed to silently defeat exact Compendium
matching for usage-sourced form-qualified names (e.g. "Maushold Family of Four") — a concrete,
live cost of still-deferred canonical name/form resolution, not fixed here.

---

### ADR-015 Amendment 2026-08-26a — Explicit "no item" representation, distinct from unspecified

**Decision:** `item`'s type changes from `str` to `str | None` across the pipeline
(`recommend_build`, `find_set_matching`, `get_resolved_build`, `anchor_roles.resolve_anchor_build`,
`propose._refine_defaults`). `None` means unspecified — no item signal received yet.
`""` (empty string) means explicitly no held item — a real, deliberate build choice (e.g.
itemless Acrobatics Talonflame, or avoiding Knock Off/Poltergeist item-loss punishment),
not missing data. Both `anchor_roles.py` gates and `propose.py`'s cache-lookup gate had the
same latent bug — a truthiness check (`and values["item"]`) that treated `None` and `""`
identically, silently skipping tier-1 exact-match and cache lookups for any itemless request
regardless of intent. Both fixed to `is not None`.

At the intake/parsing layer (`turn_intent.py`): a new `_field_value_present` helper
special-cases the `item` field so an explicit `""` is recognized as present (existing
`_populated` stays untouched — it's deliberately truthy for other fields, per a documented
prior fix for model-inconsistent empty-dict/list handling on unrelated structured fields,
and this work correctly avoided disturbing that). A new phrase detector
(`_extract_explicit_itemless`) recognizes explicit signals ("no item," "itemless," "without
item," "holding nothing," "no held item") and maps them to `field="item", value_text=""`.
A real item name in the same message always wins over an itemless phrase. Silence never
implies itemlessness — absence of any item mention defaults to `None`, only an explicit
signal produces `""`.

Cache-write safety: `get_resolved_build` and the cache-write path in `recommend_build` both
short-circuit on `item is None`, preventing `to_id(None)` (which raises `AttributeError`,
confirmed directly against `recommender/ids.py`) from ever being reached.

**Why:** This was a real, pre-existing gap surfaced while designing VGCPastes exact-match
coverage (Amendment 2026-08-26b) — the corpus contains genuine itemless builds (3 members,
confirmed all itemless Acrobatics Talonflame) that the pipeline couldn't represent as a
distinct request from "item not yet specified," meaning those builds could never be matched
even once corpus coverage existed.

**Status:** Implemented and verified. Branch `feature/explicit-itemless-representation`,
merged via PR #150. 176 passed, 1 skipped on the named validation suite; full suite green
(1389 passed, 13 skipped) once cross-checked against the CI calc-service fix (Amendment
below, PR #152). One implementation improvement beyond the original plan: `recommend.py`'s
`b_item = built.get("item") or item` was also corrected to `if "item" in built: b_item =
built["item"]`, since the `or` form would have silently discarded a real explicit `""` via
the same class of truthiness bug being fixed elsewhere — caught and fixed proactively, not
spelled out in the original plan.

**Explicitly out of scope, not touched:** `lookup_live_build`'s stub status;
`ProvisionalSlot.item`'s own `str` type (provisional slots keep using `""`, not `None`);
a pre-existing, unrelated `str(None)` bug in `slot_fill._provisional_from_refined`.

---

### ADR-015 Amendment 2026-08-26b — VGCPastes exact-match priority over synthetic featured_sets

**Decision:** `find_set_matching` (tier-1 exact moves+item match) now scans the VGCPastes
corpus (`data/team-composition/champions-reg-mb.vgcpastes-builds.v1.json` — 712 real 6-mon
teams, resolved 2026-08-12, already wired into `build_alternatives.py`'s sibling generator)
**before** the legacy synthetic `featured_sets` row, and a VGCPastes match always wins when
both would match the same key — real joint player data outranks a mechanically-derived
top-4-moves/top-item marginal, even on the same combo. Return type changed from
`PokemonSet | None` to a ranked list (`SetMatchResult`): empty = miss, first element =
primary, remainder = alternatives. Each entry carries `source` (`"vgcpastes"` | `"featured"`),
determining both EV-strip behavior (`"featured"` hits still strip EVs — still a marginal;
`"vgcpastes"` hits keep real evs/nature) and whether alternatives can exist at all (only
`"vgcpastes"` hits can have more than one entry).

When multiple VGCPastes rows match the same (species, moves, item) key with different
(nature, spread): primary = highest-occurrence-count bucket; ties broken by earliest parsed
`date_shared` (real date parsing, `"%d %b %Y"` — corpus has 56 distinct date string formats,
confirmed unsuitable for lexicographic sort). Unparseable dates lose tie-break priority
(sorted last via an internal sentinel) without crashing or surfacing a bogus value.
Zero-EV corpus rows (52 teams, moves+item only) still count as a match — spread/nature
omitted from the built set, falling through to tier-2 (`select_usage_spread`) for EVs while
keeping the matched moves/item/ability. `RecommendResult` gained `match_alternatives`
(reusing `state.py`'s existing `"vgcpastes"` provenance literal, no new taxonomy).

Mega/form handling reuses `reconcile._item_mega_forme`'s exact logic (snapshot-existence
check and Meowstic special case intact), extracted to a new cycle-free shared module
(`recommender/species_forms.py`) rather than duplicated — the direct import would have
created a real cycle (`usage_data → reconcile → recommend → usage_data`, since
`reconcile.py` imports `infer_role` from `recommend.py`). An initial implementation instead
shipped a thinner, unvalidated string-suffix heuristic; caught in review (untested branch,
weaker than the real mechanism) and corrected before merge.

**Coverage, verified directly (not estimated):** 186 of 316 legal species have VGCPastes
coverage; 130 have none. Cross-checked those 130 against a larger 16,638-team tournament
corpus (`champions-reg-mb.pikalytics-team-usage.v1.json`) — only 11 have zero real tournament
presence; the other 119 (including Mega Venusaur at 970 uses, Mega Gengar at 743) are real,
played species the smaller VGCPastes sheet just doesn't happen to have full builds for.
That gap is disclosed, not silently closed — Pikalytics' team-usage data has species
co-occurrence but no spread/nature, so it can't supply what's missing.

**Alternatives considered — a dedicated live full-build fetcher (the original PR16 shape).**
Rejected for now: tracing the actual miss path in `recommend.py` shows a tier-1 miss already
falls through to (a) assembly from the user's own requested moves+item, then (b) tier-2's
`select_usage_spread`, which already has its own approved live-fetch exception (ADR-014
Amendment 2026-08-08a, `fetch_live_spreads`) for species with no offline usage row —
structurally the same problem as the 119-species gap. Building new live infrastructure for a
gap that already degrades gracefully through an existing, approved path would be speculative
scope. **Deferred, not abandoned** — revisit if real usage shows the fallback (user's exact
move/item choice + tier-2 spread) is unsatisfying in practice.

**Status:** Implemented and verified. Branch `feature/vgcpastes-priority-match`, merged via
PR #151. Named validation suite: 69 passed. Full suite green (1405 passed, 13 skipped) once
rebased onto `main` including both Amendment 2026-08-26a and the CI calc-service fix
(PR #152). New tests cover: VGCPastes-wins-over-featured on a shared key, featured fallback
when no VGCPastes match, multi-spread ranking with alternatives, zero-EV match falling
through to tier-2, itemless corpus members matching an explicit empty item, unspecified item
returning an empty list, base-species-plus-mega-stone-item matching, and both the equal-count
and unparseable-date tie-break cases specifically (the last two added after review flagged
the original multi-spread test only exercised count-based ranking, never an actual tie).

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

### ADR-019 — Amendment 2026-08-12a

**Setup-attacker damage scoring: per-defender payoff fallback, symmetric Dragon Dance Speed
threshold, and a fallback sort-key correctness fix.**

`_damage_score` previously dropped a panel member from the mean entirely when the primary
payoff move dealt zero damage (`if dmg_f <= 0: continue`) — since the denominator shrank with
the numerator, this could inflate a candidate's score on type-immune panel members rather than
penalize it. Fixed: for each defender, if the primary payoff zeroes, the next-ranked candidate
move (usage-sourced moves first, then learnset, STAB then base power — same priority order
`_best_payoff_move` already used) is tried before that defender is skipped. A defender is only
excluded from the average if every available move zeroes against it (a genuine coverage gap,
not a scoring artifact). Multi-move candidates now report per-defender coverage in notes
rather than a single panel-wide move label. Confirmed correct against every real hard block in
the 30-member panel: Farigiraf/Armor Tail (blocks priority entirely — the only ability-based
block on the panel) and three Levitate holders (Rotom-Wash, Hydreigon, Delphox-Mega, blocking
Ground) all behave as genuine immunities under the new logic, not scoring bugs.

Dragon Dance gets a symmetric, criteria-based promote/demote rule on top of the existing
offense score: `spe_crossings >= 10` (count of panel members flipped from slower to faster
after +1 Speed) is promote-eligible, `<= 7` is demote, one-tier movement only, with the
existing offense band as a hard cap in both directions (no jump past what offense alone would
allow). Calm Mind, Bulk Up, and Iron Defense+Body Press stay sort-only within tier — their
crossing-count distributions showed no natural breakpoint to threshold against, confirmed by
inspecting the real per-candidate distributions rather than assumed.

While investigating whether Annihilape's Bulk Up payoff should be Rage Fist instead of Close
Combat (motivated by Rage Fist's power scaling with hits taken — directly relevant to a
bulk-boosting category), found and fixed a real bug: the payoff-move sort key
(`_ranked_payoff_moves`) still ranked moves by static snapshot base power after
state-scaling moves (Rage Fist, Last Respects, Stored Power, Power Trip) had already been
wired to use their real, boosted power in the damage calc itself — meaning a weaker static
move could wrongly outrank a stronger state-scaling move in fallback selection. Fixed at the
sort key, not just for the one case that surfaced it. Confirmed blast radius: exactly one
candidate (Annihilape) across all six setup categories, including the two already shipped.
Close Combat remains Annihilape's selected payoff even after the fix (0.5632 vs. Rage Fist's
0.4607) — no special-case handling needed for its bulk-crossing count.

**Status:** Design and investigation complete; see Amendment 2026-08-12b for the resulting
ship.

---

### ADR-019 — Amendment 2026-08-12b

**Six-category setup-attacker expansion complete: Swords Dance, Nasty Plot, Calm Mind, Bulk
Up, Dragon Dance, and Iron Defense+Body Press all critic-approved and persisted on
consistent underlying data.**

All six categories share the same threat panel (Showdown-usage-threshold, 30 members,
carrying real natures/moves/items rather than the earlier incomplete backfill) and the same
corrected payoff-fallback and sort-key logic (Amendment 2026-08-12a). Swords Dance and Nasty
Plot were rebuilt and re-persisted against this corrected data after an earlier persist was
found to predate it — that earlier version is superseded and should not be treated as a
separate historical state.

Final floors and tier changes from the corrected rebuild:
- **Swords Dance** (1.201 Excellent / 0.841 Acceptable): Gallade-Mega and Skarmory-Mega move
  Good → Acceptable. Excellent unchanged (Aegislash, Kingambit, Mawile-Mega, Mimikyu).
- **Nasty Plot** (0.910 / 0.637): Delphox-Mega moves Excellent → Good; Houndoom-Mega and
  Meowstic-F-Mega move Good → Acceptable. Excellent: Alakazam-Mega, Raichu-Mega-Y.
- **Calm Mind** (0.484 / 0.339): Excellent — Meowstic-Mega-Mega, Delphox-Mega.
- **Bulk Up** (0.670 / 0.469): Excellent — Starmie-Mega, Blaziken-Mega.
- **Dragon Dance** (0.517 / 0.362): Dragonite promotes Good → Excellent on the Speed
  threshold (15/30 crossings); Flapple and Feraligatr-Mega demote Excellent → Good; Feraligatr
  and Tyranitar-Mega demote Good → Acceptable. Charizard-Mega-X stays Excellent on offense
  alone. Critic initially flagged a tied-cluster concern (promote and demote candidates
  sharing the same `excellence_basis` string) — a reporting gap, not a ranking error;
  `_dd_spe_excellence_basis` now includes the resulting tier, re-critic clean.
- **Iron Defense+Body Press** (0.268 / 0.188): Excellent — Aggron-Mega, Chesnaught-Mega.
  Dual-purpose behavior here is split across different candidates (high-offense members are
  not the same as high-bulk-crossing members) rather than concentrated in any one — no
  threshold applied, sort-only within tier, same as Calm Mind and Bulk Up.

Role Compendium is now 14 files on disk (weather ×4, redirection, trick_room_setter,
tailwind_setter, sleep_status_spreader, and the six setup categories above).

---

### ADR-019 — Amendment 2026-08-14a

**Aegislash-only Stance Change sequence added to setup-attacker scoring — pre-attack survival
now scores Shield Forme, not Blade; Shadow Sneak combined-KO and King's Shield reset credited
independently, gated strictly on real `kit_moves`.**

Bug: `_calc_species_name` forces every Aegislash calc call to Aegislash-Blade. Correct for the
SD payoff attack itself (Blade Atk/SpA is the real post-Stance-Change stat line), but the same
forcing also applied to pre-attack incoming-damage checks — Aegislash starts every battle in
Shield Forme and Swords Dance (status) never flips it, so SD's survival scoring (`remain`,
inside `_damage_score`'s Part D, reached via `_incoming_ohko_by_defender` /
`_candidate_defender_spec`) was reading Def/SpD 50 when it should have read Def/SpD 140. This
directly contradicted Branch B's admission check (`_base_stats`), which already correctly used
Shield stats to decide Aegislash qualifies as bulky — two parts of the same pipeline
disagreeing about the same fact.

Fix: new `_setup_defender_species` maps Aegislash to Shield Forme by default for defender-side
specs; `_candidate_defender_spec` takes an explicit `defender_species` override for the one
case that still needs Blade (see below). Attacker-side payoff damage construction is
untouched — Blade Forme stays correct there.

New mechanic, explicitly **not** a general forme-flip framework and **not** an extension of
`_scarf_nature_correction` (no such hook exists in the setup-scoring path — this is the first
species-specific multi-turn sequence scorer in the codebase, documented as such rather than
undersold as a small correction):

- **Combined-KO credit:** if Shadow Sneak is in the candidate's `kit_moves` and (SD payoff raw
  damage + Shadow Sneak raw damage) ≥ threat HP, credit `remain = 1.0` and count toward
  `sweep_ohko`. Sound because Shadow Sneak's priority means this resolves before the threat's
  turn 3 action — the threat never gets to act.
- **King's Shield reset credit:** only reached if combined-KO fails (or Shadow Sneak isn't in
  `kit_moves`). If King's Shield is in `kit_moves` and Aegislash survives the threat's one
  exposed hit against Blade Forme (`_incoming_ohko_by_defender` explicitly forced to
  `Aegislash-Blade` for this one check), credit `remain = 1.0` — King's Shield forces Stance
  Change back to Shield Forme, resetting to the starting state rather than leaving any ongoing
  degraded state to track further.
- Each half gated independently and strictly on `kit_moves` (the featured-or-common
  representative set) — never `usage_ids` (species-level move presence across all sets, which
  would credit builds that don't actually run the move) and never learnset (species-generic
  access, no bearing on a real candidate's set).

**Confirmed by direct verification, not just Cursor's report:** branch `fix/aegislash-setup-
forme-sequence` (built on the 5-commit `wip/setup-tr-usage-and-scoring` base) pulled and
diffed directly; `_setup_defender_species`/`_candidate_defender_spec`/
`_aegislash_sequence_remain` match the design exactly as described, including the independent
gating on `kit_ids`. All 65 tests in `test_role_compendium_swords_dance.py` +
`test_role_compendium_stage_setup.py` run directly and pass, including the six named Aegislash
tests (`test_aegislash_incoming_uses_shield_forme`,
`test_aegislash_combined_ko_credits_ohko_and_remain`,
`test_aegislash_combined_ko_requires_shadow_sneak_in_kit`,
`test_aegislash_ks_reset_independent_of_shadow_sneak`,
`test_aegislash_no_ks_no_combined_ko_gets_no_remain`,
`test_aegislash_branch_b_matches_shield_defender`) — the two adversarial-gating tests confirm
the `kit_moves`-only gate is real, not just happy-path.

**CM/BU/ID confirmed, not just SD.** _setup_bulk_crossings builds both its unboosted and boosted defender specs from the same _candidate_defender_spec, with no defender_species override — so it inherited the Shield Forme remap automatically, verified directly in the code (line 2380 onward) rather than left to the discovery-stage assumption. CM/BU/ID's boosts are all status moves, so the boosted spec staying Shield Forme is correct there too; no sequence logic (Shadow Sneak/King's Shield) applies outside SD, which is intentional — that credit is specific to SD's non-boosting payoff sequence. One honest gap: no dedicated _setup_bulk_crossings test asserts defender.species for Aegislash directly — coverage is indirect, via the shared-helper test (test_aegislash_branch_b_matches_shield_defender) plus an unrelated existing Blissey crossings test. Small test-coverage follow-up, not a missing fix.

**Status:** Shipped on `fix/aegislash-setup-forme-sequence`, PR into `wip/setup-tr-usage-and-
scoring` (#70). Not yet on `main` — this branch is still pre-critic-pass, pre-persist, same as
the rest of the setup-scoring arc (see master log 2026-08-09/12 entries).

---

### ADR-019 — Amendment 2026-08-14b

**Connect-recoil now deducted from setup-attacker `remain`; new `debuff_surv` standing signal
reports post-self-Def/SpD-drop panel survival, independent of primary `remain`'s existing
turn-order rules.**

Two disjoint-today mechanics, fixed together in `_damage_score` since both live at the same
`remain` computation site, but kept as independently-gated logic:

**Connect-recoil.** Recoil HP loss (Flare Blitz, Brave Bird, Wave Crash, Wood Hammer, Light of
Ruin, plus the not-yet-admitted Double-Edge/Volt Tackle/Wild Charge/Head Charge/Submission/
Take Down/Head Smash — `_CONNECT_RECOIL_MOVES`, table-driven not hand-picked) is read directly
from `raw.recoil` on the calc result, not recomputed from `ratio × dmg_f`. Confirmed necessary
via a direct probe during discovery: a Flare Blitz OHKO's real recoil is ≈34.4% (already
accounts for damage capping), while the naive ratio math overstates to ≈81% on the same hit.
Deduction (`remain = max(0, 1 - incoming_frac - recoil_frac)`, or `max(0, seq_remain -
recoil_frac)` when Aegislash/priority-finisher sequence credit already applies) only ever
lands where a `remain` entry already exists — i.e. the `outsped`/`disguise` branches — since
the moved-first case was independently confirmed (Cursor, this session) to intentionally
produce no `remain` entry at all. No new turn-order logic was introduced; this task correctly
left that alone.

**`debuff_surv`.** For any setup payoff move with a guaranteed self Def/SpD drop
(`_self_defense_drops`, sourced from `stat_boosts.v1.json` — Close Combat is the only current
admit, but the table covers Superpower/Headlong Rush/Armor Cannon/Clanging Scales/Scale Shot
generically for future admits), a once-per-candidate standing incoming-damage pass is run with
the drop stacked onto the candidate's own existing setup boosts (e.g. Bulk Up's own Def+1
netted against Close Combat's Def−1, correctly modeling the real post-setup-and-payoff state,
not the drop in isolation). Reported as `k/n` (panel members still not-OHKO'd), a flat
secondary field on `_sweep_note_fields` — deliberately not folded into or replacing primary
`remain`, and independent of any individual panel member's turn order by design (represents
"already used the payoff move once," the same "keep sweeping" framing that motivated the whole
mechanic).

**A real latent bug found and fixed as part of this task, not a separate one:**
`_incoming_ohko_by_defender`'s boost-application filter previously only applied a stage when it
was `> 0` — meaning any negative stage (any self-debuff) would have silently fallen through to
the unboosted path, producing a false "survives" reading against undebuffed stats. Fixed to
apply any nonzero stage (positive or negative), with correct handling of the harder case where
both Def and SpD are simultaneously nonzero (falls through to first-damaging-move-any-category
scoring with both stages applied on the defender, rather than the single-stat category-matched
path used when only one stat is nonzero).

**Confirmed by direct verification, not just Cursor's report:** branch
`fix/setup-recoil-debuff-sweep` (built on `wip/setup-tr-usage-and-scoring` post-Aegislash-merge)
pulled and diffed directly. Both most load-bearing tests inspected line-by-line, not just
run: `test_recoil_remain_uses_capped_raw_recoil_not_naive_ratio` asserts the exact expected
`remain_mean` (0.256 = 1 − 0.40 − 0.344) and explicitly checks the capped path beats the naive
one; `test_debuff_surv_applies_negative_def_spd_stages` is genuinely adversarial — it directly
inspects the defender spec sent to calc to confirm both `def: -1` and `spd: -1` actually land,
not just that the final reported count happens to be correct. All 12 new/modified tests run
directly and pass; full named-file run (`test_role_compendium_swords_dance.py` +
`test_role_compendium_stage_setup.py`) is 71/71, including Aegislash's six named tests
re-confirmed unmodified.

**Status:** Shipped on `fix/setup-recoil-debuff-sweep`, PR open against
`wip/setup-tr-usage-and-scoring`. Not yet on `main` — still pre-critic-pass, pre-persist, same
as the rest of the setup-scoring arc.

---

### ADR-019 — Amendment 2026-08-14c

**Priority-finisher combined-KO generalized beyond Aegislash to all six setup-attacker
categories; King's Shield reset stays Stance-Change-specific and composes only as a fallback
after the general check.**

Supersedes the Aegislash-only framing of the combined-KO half of Amendment 2026-08-14a — that
amendment's mechanic (payoff move doesn't OHKO, a priority move finishes it before the threat's
next action) was never actually about Stance Change; it was scoped to the one species it was
discovered on. King's Shield reset behavior is unchanged by this amendment.

**Split, not shared:** `_aegislash_sequence_remain` replaced by `_priority_finisher_combined_ko`
(species-agnostic) and `_aegislash_ks_reset` (still forme-gated). Caller tries the general
finisher check first; only if it doesn't credit **and** the candidate is Aegislash with King's
Shield in kit does it fall through to the reset. Aegislash's existing "no remain on a failed
sequence" behavior — a real, deliberate legacy silence, not an oversight — is explicitly
preserved with a documented branch, not silently changed; non-Aegislash candidates whose
finisher doesn't credit correctly fall through to the ordinary lived-shield `remain` calculation
instead, since that silence was never meant to generalize.

**`_SETUP_PRIORITY_FINISHER_MOVES`** (explicit set, not derived from `_OFFENSIVE_PRIORITY_MOVES`
alone — that set alone would wrongly include Fake Out and mistreat Grassy Glide as unconditional
priority): Extreme Speed, Feint, Aqua Jet, Bullet Punch, Jet Punch, Mach Punch, Quick Attack,
Shadow Sneak, Sucker Punch.

- **Hard-excluded:** Fake Out and First Impression (both first-turn-only — same restriction
  that already bans them as setup payoffs disqualifies them as finishers too, confirmed via a
  genuinely adversarial test: Fake Out present in kit with damage that numerically clears the
  threat if credited still correctly produces no credit). Upper Hand — its fail condition
  isn't covered by the existing `lived_shield` guarantee (unlike Sucker Punch, see below), so
  excluded until separately designed for.
- **Deferred, not included:** Grassy Glide — static priority is 0, only conditionally +1 under
  modeled Grassy Terrain, which this project doesn't model. Crediting it today would invent
  priority the calc field doesn't have.
- **Sucker Punch requires no special fail-condition modeling.** Its `onTry` failure (target
  used a non-damaging move) coincides exactly with the case where the panel's incoming-hit calc
  already has nothing to score `lived_shield` against — the mechanic's existing gate already
  covers this for free.

**Call sites:** all five `_damage_score` invocations across the setup-attacker path now receive
`kit_moves` — `_select_setup_payoff`, `_construct_setup_attacker` (SD), `_construct_offense_
stage_setup` (NP/CM/BU/DD), and both `_construct_def_payoff_setup` (ID+BP) calls. ID+BP wiring
is currently inert (no eligible finisher carrier in the admitted pool today) but wired
proactively rather than left as a follow-up gap.

**Confirmed by direct verification, not just Cursor's report:** branch pulled and diffed
directly; confirmed all five call sites pass `kit_moves` by direct grep, not assumed from the
report. All 9 eligible finisher moves individually tested by name against real species (not
just Shadow Sneak/Aegislash) — `_ELIGIBLE_FINISHER_CASES` covers Extreme Speed/Dragonite,
Feint/Pinsir-Mega, Aqua Jet/Feraligatr, Bullet Punch/Scizor, Jet Punch/Palafin, Mach
Punch/Crabominable-Mega, Quick Attack/Sylveon, Shadow Sneak/Mimikyu, Sucker Punch/Kingambit.
Fake Out and Grassy Glide exclusion tests both genuinely adversarial (damage totals that would
credit if the exclusion leaked). A real non-SD case (Bulk Up Starmie-Mega/Aqua Jet) directly
proves the call-site extension works end-to-end, not just that the function generalized in
isolation. Aegislash's six original named tests re-run unmodified and still pass. 77/77 across
both named test files.

**Status:** Shipped on `fix/setup-priority-finisher-combined-ko`, PR #72, merged into
`wip/setup-tr-usage-and-scoring`. Still pre-critic-pass, pre-persist, same as the rest of the
setup-scoring arc.

---

### ADR-019 — Amendment 2026-08-14d

**Setup-attacker payoff selection now filters the usage-move bag by real presence
(`_SETUP_PRESENCE_SET_PCT_FLOOR`, 0.1%) before damage-ranking — closes Problem A
(synthesized-payoff contamination).**

Root cause: `_usage_payoff_move_ids` unions kit moves with every `common_moves` name and every
featured-set move, including moves at ~0% real presence that never co-occur with the setup
move on any real played set. `_setup_payoff_candidates` filtered only by stat-match, no
presence floor; `_select_setup_payoff` ranked the unfiltered bag purely by panel
`_damage_score` — a move that scored well against the panel could win the payoff slot at 0.0%
real presence. Surfaced directly: Medicham-Mega admitted to Calm Mind with Psyshock (0.0% set%,
not on any featured set) alongside a genuine-but-thin Calm Mind presence (0.129%) — the two
never co-occur on any real set. A follow-up sweep found four more: Audino/Thunderbolt,
Mawile-Mega/Double-Edge, Salazzle/Belch, Beartic/Double-Edge.

**Confirmed not the same problem `_same_row_both_moves` solves** (that gate is ID+BP-specific
source-split prevention — both setup and payoff on the same data source, CBD or Showdown, never
split across them — and was correctly scoped there because ID+BP admits on *two* named moves
simultaneously; SD/NP/CM/BU/DD admit on one setup move only, with payoff chosen later from an
unconstrained bag. Confirmed via direct check: `_same_row_both_moves` would not have caught
Medicham-Mega — Calm Mind and Psyshock are both on the same Showdown species row, so that gate
returns true regardless).

New `_present_usage_payoff_ids` filters the bag via the existing `_best_move_set_pct` helper
before ranking — minimal new surface area, no new presence-lookup logic invented. Wired at all
three relevant call sites: `_construct_setup_attacker` (SD), `_construct_offense_stage_setup`
(NP/CM/BU/DD), and `_construct_def_payoff_setup`'s coverage-move fallback (ID+BP, which still
consults this bag for coverage after its own dual-move admission gate). Does not change setup
admission, `_same_row_both_moves`, or ranking logic itself — purely removes sub-floor
candidates before ranking runs.

**Confirmed by direct verification:** all 5 named cases individually tested by name with real
presence percentages, both the excluded move's absence and the legitimate alternative's survival
checked explicitly. Graceful-rejection path tested (a candidate whose entire bag falls below
floor produces no payoff, not a crash). SD's five originally-signed promote/demote motivating
cases (Weavile, Kingambit, Mimikyu, Aegislash, Beartic) confirmed unaffected — none were
payoff-floor violations. 85 tests passing (68 + 13 + 4 across the three affected test files,
initially miscounted at 81 in verification before the third file, `test_role_compendium_nasty_
plot.py`, was found to also be in scope).

**Status:** Shipped on `fix/setup-payoff-presence-floor`, PR #73 — merged directly into `main`
(not back into `wip/setup-tr-usage-and-scoring`), a deliberate deviation from this arc's
containment discipline. Confirmed safe: no persisted Role Compendium data
(`data/roles/*.v1.json`) was affected either way, since none of SD/NP/CM/BU/DD/ID+BP have ever
been persisted — the "no critic pass/persist" rule governs writing that data, not the
construction code that would produce it. `main` and `wip` to be resynced going forward.

---

### ADR-019 — Amendment 2026-08-14e

**Sweep-KO promote/demote: closes with a uniform "no rule" verdict across all six setup
categories on live current data. SD's originally-signed rule (Amendment 2026-08-13, not
formally numbered — chat-only draft) is retracted, not revived under new numbers. DD gets its
own independently-derived setup-move admission floor (1.0%, discovered but not yet
implemented) as the one real outcome of this arc's admission-floor side.**

**Problem B, admission floor (setup-move presence, distinct from Amendment 2026-08-14d's
payoff-presence fix):** real breakpoint-finding across SD/NP/CM/BU/DD found no natural gap
above the existing 0.1% floor for four of the five — presence smears continuously from ~0.1%
through several percent with no genuine cliff, confirmed via the same method used for the
Screens/Sleep/Trick Room floor derivations. DD is the one real exception: an independent hole
at (0.390, 1.363], Sleep-pattern (0.5% and 1.0% admit the identical set) → 1.0% floor,
justified on its own terms rather than assumed to match the others. CM's tempting-looking 6|8
Acceptable/Good gap (surfaced when testing a 0.5% hybrid cutoff) confirmed as an artifact of
that stopgap rather than a real breakpoint — d=2, not SD-rule-rigor d=6, and Espathra (the
Good-8 case) sits at 26.9% presence with Calm Mind on its own featured set, a high-presence
fact, not thin-setup noise. NP independently evidenced for the first time this arc (previously
absorbed into a group verdict without its own check) — no rule, same overlap pattern.

**SD's signed rule (P≥22 Acceptable→Good, D≤10 Good→Acceptable) does not hold on live current
data — root cause traced and confirmed, not assumed.** Direct comparison ruled out the more
obvious hypothesis first: panel composition was checked and confirmed unchanged between the
Aug 13 derivation and today (re-running today's constructor against the pre-rebuild June
snapshot fails to even reproduce Aug 13's numbers, while the July snapshot was already in use
at the time of the Aug 13 discovery). The real cause: this session's own correctness fixes —
Aegislash's Shield Forme correction (Amendment 2026-08-14a) and the priority-finisher
generalization (Amendment 2026-08-14c) — pushed Aegislash's score to 1.255, making it the new
second-highest overall. Since the Excellent floor is deliberately computed from the
second-highest score (not the top, to avoid single-outlier skew), Aegislash taking that
position raised the floor (1.158→1.192) and the downstream Acceptable/Good cut (0.811→0.835),
pulling several mid-high-OHKO candidates (Samurott-Hisui, Lucario, Abomasnow-Mega, Absol,
Victreebel-Mega) down into Acceptable — exactly filling the OHKO gap the original rule was
built to promote across. Weavile and Beartic's own scores never moved (0.766/0.810 unchanged
both dates); the floor moved under them. A legitimate, traceable side effect of unrelated
correctness fixes, not a bug in either the fixes or the original rule's derivation.

**Fresh re-derivation on today's data (n=59) confirms no rule survives:** Acceptable max OHKO
23 overlaps Good min 16 — smear, not a cliff, doesn't clear the same rigor bar the original
rule needed. Good↔Excellent likewise remains smear. SD joins NP/CM/BU/DD/ID+BP's "no rule"
verdict, closing the entire six-category sweep-KO question with one honest, uniform outcome:
OHKO/sweep-KO count is display-only information across all six setup categories, not a tier
adjustment mechanism.

**Status:** Discovery only — no code shipped from this amendment. Closes 3c item 3 (sweep-KO
display fields) from the 2026-08-14 handoff. **DD's 1.0% setup-move admission floor remains
unimplemented** — a real, derived finding not yet converted to a task; tracked as a small
follow-up, separate from item 6.

---

### ADR-019 — Amendment 2026-08-14f

**Setup-attacker payoff selection (SD/NP/CM/BU/DD) now picks each threat panel member's best
real kit move individually, instead of applying one panel-mean-optimized move uniformly across
all 37 members. Closes item 6 Stage 1 of the original Role Compendium construction backlog.**

**Problem:** `_select_setup_payoff` picked a single payoff move by ranking mean damage across
the whole panel, with per-defender variation limited to `fallback_mids`'s hard-zero trigger
(type immunity / ability block). A move that scored well on *average* could win even when a
different real move in the kit would clearly do more against most individual matchups — surfaced
concretely on Mawile-Mega, whose Double-Edge beat Play Rough on panel mean purely via
Ghost-type zero-fallback theft plus neutral-vs-resisted damage against Fire-types, despite
Play Rough being the mechanically stronger move (higher raw power with STAB, no recoil) against
nearly every real defender.

**Design decisions, locked before implementation:**
- **Selection rule per defender:** two-stage — best KO bin first (OHKO/combined-KO beats 2HKO
  beats 3HKO+), weighted-capped damage fraction as tiebreak within the same bin. Preserves
  today's existing scoring philosophy (turn-order weight, accuracy scaling) rather than
  switching to raw damage comparison.
- **Candidate pool (M):** kit damaging moves only (`_kit_damaging_mids`, category-matched to the
  boosted stat) — not the broader presence-filtered usage bag `_select_setup_payoff` previously
  searched. Deliberately narrower: ties every payoff choice to one real, coherent observed kit
  rather than a synthesized bag of independently-real-but-not-necessarily-co-occurring moves.
  Accepted tradeoff: a real usage payoff outside the kit's four moves is no longer reachable,
  even if it would score better against some defender.
- **Combined-KO evaluated as a genuine per-defender, per-candidate-mid competition, not
  "check the payoff, then separately check the finisher."** For each candidate mid under
  consideration as a defender's primary hit (excluding the finisher move itself,
  `mid != fin_mid`): does it alone reach OHKO? If not, and the kit contains an eligible priority
  finisher, does this mid's damage plus the finisher's clear the threat? The finisher move
  independently competes as its own standalone candidate too — both roles apply simultaneously.
  Verified via a dedicated adversarial test proving two *different* non-finisher primaries
  (Iron Head, Sacred Sword) each independently combined-KO different defenders using the same
  kit finisher (Shadow Sneak), with Shadow Sneak itself never winning as a primary despite being
  in the candidate pool.
- **`debuff_surv` redefined — a real semantic break, not a compatible extension.** Was `k/n`
  over the full panel using one candidate-wide `primary_mid`'s self Def/SpD drops, applied as a
  standing pass independent of selection. Now: `k/n` where `n` = count of defenders whose own
  *selected* move actually carries a self-drop, `k` = how many survive — variable denominator
  per candidate, not always `/37`. Implementation correctly handles heterogeneous drop
  signatures (grouping defenders by exact stage pattern before running each group's own standing
  survival pass) rather than assuming uniform stages across every self-drop move.
- **Cost, confirmed cheaper than today's search, not more expensive.** Today's `_select_setup_payoff`
  already pays `C`-many (9-17 typical) redundant `_damage_score` passes, each recomputing an
  identical incoming-OHKO mask, just to find one mean-optimized winner. Restructuring to compute
  that mask once and argmax across kit-only `M` (median 1-3 damaging moves) per defender is
  cheaper in real calc-call terms, not a "4-8× cost bomb" as an earlier, stale estimate assumed —
  that estimate predated this session's own three prior scoring additions (Aegislash sequence,
  recoil, priority-finisher) and was never re-checked against current code before being repeated.

**Explicitly out of scope, deferred:**
- ID+BP — confirmed structurally different (Body Press's damage is defined by the user's own
  Defense stat, not move choice); untouched, zero diff lines touch `_construct_def_payoff_setup`.
- `payoff_move` / `payoff_coverage` display schema — `_select_setup_payoff` currently returns the
  modal (most-frequently-winning) mid as an interim display value with a deterministic tiebreak;
  the real reporting-contract decision (single label vs. structured breakdown) is Stage 2.
- `_setup_bulk_crossings` / `_setup_spe_crossings` — confirmed independent of payoff selection,
  untouched.

**Confirmed by direct verification, not just Cursor's report:** branch pulled, full diff read
(not spot-checked, given the size — 466 lines in the core file). Two of the five new tests
inspected line-by-line as genuinely adversarial, not happy-path: the Mawile-shaped test asserts
Double-Edge *never* wins except the one contrived cell where its raw damage is deliberately set
higher; the combined-KO test proves genuine per-defender competition across distinct primaries
sharing one finisher. `debuff_surv`'s variable-denominator behavior confirmed via a real test
(`"1/1"` out of a 3-member panel, not `"1/3"`). All prior Aegislash-specific tests (6 original +
1 new from this task) re-run and pass unmodified — confirming the restructure correctly
generalized rather than regressed that already-shipped logic. 88/88 named-file tests, 979/979
full suite (8 skipped, consistent baseline), no regressions. One honest gap: live-construct
numbers reported by Cursor (Mawile-Mega's modal Iron Head, Mimikyu's coverage, the `11/22` /
`14/29` `debuff_surv` figures) were not independently reproduced via the actual calc service —
code- and test-level verification give high confidence but this specific claim rests on the
report, not independent reproduction.

**Status:** Shipped on `feature/setup-per-defender-payoff`, targeting `wip/setup-tr-usage-and-
scoring` (large-blast-radius item, deliberately kept off `main` per this session's containment
policy for big pieces). No critic pass, no persist — item 6 Stage 1 of 4 (core scoring); Stage 2
(signals/schema), Stage 3 (ID+BP policy), Stage 4 (rebuild + critic + persist) remain.

---

### ADR-019 — Amendment 2026-08-14g

**Dragon Dance gets its own independently-derived setup-move admission floor (1.0%, up from
the shared 0.1%). SD/NP/CM/BU stay on the shared floor — confirmed no comparable gap exists
for them.**

From the Problem B admission-floor discovery: DD's setup-move presence distribution has a real
hole at (0.390, 1.363] — Steelix-Mega/Altaria/Aerodactyl-Mega/Dragonite-Mega cluster thinly
below it, Scrafty-Mega and above sit cleanly beyond it, and 0.5%/1.0% admit the identical set
inside the hole (same pattern as the Sleep category's own independent floor). 1.0% chosen as
the conservative pick, just under the retained cluster. `_DD_SETUP_PRESENCE_FLOOR = 1.0`
applied only when `move_id == "dragondance"` inside the shared `_construct_offense_stage_setup`
path; CM/BU untouched.

**Confirmed by direct verification:** exclusion/inclusion boundary test proves Dragonite-Mega
(0.390%) still clears the shared 0.1% floor on identical data, isolating the DD-specific
override as the actual cause of exclusion — not a blanket change. A second test uses the
identical presence value (0.390) for a CM and a BU candidate as a direct control, confirming
category-scoping is real. Live DD pool: 17→13. 15/15 named tests, 974/974 full suite prior to
this, no regressions.

**Status:** Shipped on `fix/dd-setup-presence-floor`, PR #74, merged to `main`.

---

### ADR-019 — Amendment 2026-08-14h

**Payoff display schema redesigned for SD/NP/CM/BU/DD: single `payoff_move` string dropped
entirely, replaced by structured `payoff_moves` (list) + `payoff_targets` (mid → species list)
derived directly from Stage 1's per-defender matrix. `claimed_traits` now lists every real
winning move as its own execution trait, not one modal label.**

Stage 1 broke the "one payoff move per candidate" assumption; this closes the schema gap it
left open. Confirmed green-field before implementing: a full consumer sweep found zero real
runtime dependents on `payoff_move`/`payoff_coverage` — only a unit test of the old string
formatter (`_payoff_coverage_note`), no evidence/slot-fill/orchestrator/CLI path reads these
keys. SD and NP are technically persisted with the old schema, but nothing downstream
interprets `criteria_notes["payoff_*"]` today, so no live migration was required — a rebuild
was needed regardless, independent of this schema question, since Stage 1 already changed the
underlying scoring.

Design: `_setup_payoff_notes` derives `payoff_moves` (sorted by win-count, descending) and
`payoff_targets` from the existing `mid_counts`/`used` data Stage 1 already produces — no new
computation, purely a display-shape change. ID+BP untouched (`_payoff_coverage_note` remains
its path, confirmed by zero diff lines touching `_construct_def_payoff_setup`).

**Confirmed by direct verification:** branch pulled, diffed. 90/90 named tests, 981/981 full
suite, no regressions.

**Status:** Shipped on `feature/setup-payoff-display-schema`, PR #76, merged to
`wip/setup-tr-usage-and-scoring`.

---

### ADR-019 — Amendment 2026-08-14i

**Stage 3 (item 6): ID+BP formally and permanently excluded from per-defender best-move
selection — Body Press's damage is defined by the user's own Defense stat, not by move choice,
so the mechanic doesn't apply. Not a deferral; a permanent scope boundary.**

**Stage 4 (item 6): full construct + critic pass across all ten Role Compendium categories
under current code. No persist — critic-review only, three clusters, each independently
approved:**

- **Cluster 1 (staleness rebuilds — SD/NP/Trick Room):** SD 26→54 admitted, NP 6→23, both with
  real tier churn among survivors (Kingambit's modal payoff Sucker Punch→Kowtow Cleave;
  Aegislash Shadow Sneak→Poltergeist) — treated as fresh critic review, not reconfirmation of a
  prior approval computed under old scoring. Trick Room 38→28, zero tier changes among
  survivors, pure membership cut from its 22.5% floor. All three: critic-approved, 0 flags.
- **Cluster 2 (fresh builds — CM/BU/DD/ID+BP):** never previously persisted; the Aug 12 local
  builds were confirmed genuinely lost (uncommitted, discarded in branch/worktree cleanup —
  same failure mode as Cluster 3 below), not recoverable. Built fresh under current code: CM 49,
  BU 37, DD 12, ID+BP 24. All critic-approved, 0 flags. ID+BP's doc note (below) attached.
- **Cluster 3 (lost-support rebuilds — Tailwind Setter/Sleep Status Spreader/Screens
  Support):** confirmed not recoverable via any git/stash/dangling-commit search — genuinely
  lost, same Aug 12 uncommitted-persist failure. Rebuilt from scratch under existing
  constructors/tests (already in code, only the JSON was lost): TW 23, Sleep 14, Screens 18
  (Screens confirmed including Whimsicott at Excellent — the membership-gate reopen behavior
  from earlier in this arc). All critic-approved, 0 flags.

**Process note worth carrying into any retrospective:** all seven lost-and-rebuilt categories
(CM/BU/DD/ID+BP/TW/Sleep/Screens) trace to the identical Aug 12 failure — critic-approved
locally, never pushed, discarded in cleanup. This is the second time uncommitted work has been
lost in this project's history (the first being the ADR/log-mirror-write violations), a
different failure shape but the same root cause class. Direct evidence for why this session's
much stricter discipline (every task pushed to `origin` immediately, independently verified via
`git fetch`) exists.

**ID+BP doc note (paste-ready):** *Iron Defense + Body Press — permanent Stage 3 scope
boundary. ID+BP payoff stays fixed to Body Press by design. Body Press damage is defined by the
user's Defense stat, not by choosing among attacking moves, so Stage 1 per-defender best-move
selection and Stage 2 plural `payoff_moves`/`payoff_targets` do not apply. The category keeps
the single-string/fixed-payoff path (`payoff_move_id: bodypress`). This is an intentional
permanent boundary, not an oversight and not deferred work.*

**Confirmed by direct verification:** branch pulled; `docs/artifacts/stage4_compendium_critic_
2026-08-14.json` inspected directly (not just the summary markdown) — SD/NP/Trick Room's full
member lists cross-checked field-by-field against the raw JSON and matched exactly. `data/roles/`
confirmed unchanged (8 files, zero diff) — no persist occurred.

**Status:** Reported on `feature/stage4-compendium-critic-reports` (docs-only, never merged
into `wip` — worth merging or at minimum not losing track of, since the report itself is real
and useful). No code changes. No persist.

---

### ADR-019 — Amendment 2026-08-14j

**Burn-immunity/negation credit (item 10) and broader disruption/status-immunity signal (item
11) — both formally closed, no rule, no display field, no further work planned.**

Item 10 was reconsidered mid-session from its original "display-only" scope to a possible
tier-affecting promote rule, then closed after real discovery: a systematic ability-table sweep
confirmed the real mechanism set (Fire-type, Water Veil/Water Bubble/Thermal Exchange,
Comatose/Purifying Salt, and Guts — which inverts burn into a net Attack boost rather than
merely tolerating it). 13 real candidates across the six categories have genuine
burn-immunity/negation with a physical payoff — but every one's current tier is already
explained by the existing damage-score floor, a branch gate, or a usage discount, not by
missing burn credit. No motivating case survives the same hard-cap discipline every other
promote rule this session was held to. Closed entirely: no rule, no display field.

Item 11 closed on the strength of item 10's outcome rather than its own direct discovery pass —
worth noting that distinction plainly, since it's an extrapolation, not an independent finding.
Reopen only if a real motivating case for either surfaces later.

**Status:** Discovery only, both items. No code shipped, none planned.

---

### ADR-019 — Amendment 2026-08-14k

**Drain-move HP recovery now credited in setup `remain`, mirroring connect-recoil's existing
subtraction — a real, previously-silent correctness gap, not a threshold or design question.**

`_recoil_frac_from_result` subtracted connect-recoil from `remain` on outsped-and-surviving
candidates; nothing added the mirror-image credit for drain moves (Bitter Blade, Drain Punch,
Giga Drain, etc. — same mechanism, opposite sign). Found by direct inspection, motivated by
Ceruledge specifically (drain payoff on 33-34/37 real panel matchups across SD and BU).

New `_drain_frac_from_result` reads `raw.recovery.recovery[-1] / raw.stats.attacker.hp` —
**absolute HP healed divided by max HP**, a real shape difference from recoil's ready-made
percentage field, confirmed via live probe rather than assumed symmetric. Gated strictly on a
real `_DRAIN_MOVES` frozenset (eight Champions-legal drain moves; ratios non-uniform — Draining
Kiss 75%, the rest 50%, confirmed from real move data, not hardcoded since calc already applies
the ratio). Gating is mandatory: `raw.recovery` is also populated by non-drain healing sources
(Shell Bell, confirmed via live probe) — an ungated read would have falsely credited item-based
healing as a move property.

One shared helper patches both remain call sites (`_setup_kit_matrix_score` for Stage 1's
SD/NP/CM/BU/DD path, and the older `_damage_score` still used by ID+BP) — avoiding a third
near-duplicate alongside the existing recoil helper. Both sites: `min(1.0, max(0.0, base -
recoil_frac + drain_frac))`, applied symmetrically across the disguise and Aegislash
King's-Shield-reset branches, same as recoil already was.

**Confirmed by direct verification:** Shell Bell adversarial test present and correct (recovery
data on a non-drain move produces zero credit). Ceruledge magnitude test reconstructs the exact
discovery-reported deltas (SD `remain_min` 0.215→0.652) as a real numeric assertion, not just
"increased" — live spot-check confirmed exact match. 10/10 named tests, 989/989 full suite, no
regressions.

**Status:** Shipped on `feature/setup-drain-remain-credit`, PR #78, merged to
`wip/setup-tr-usage-and-scoring`.

---

### ADR-019 — Amendment 2026-08-14l

**SD/CM/BU get category-specific damage-score admission floors and raised Acceptable
multipliers, deliberately reshaping their tier distributions so Acceptable becomes the largest
tier instead of Good. NP/DD/ID+BP unchanged, confirmed byte-identical to Stage 4.**

**Motivation, stated honestly as a judgment call, not a data-derived correction:** post-Stage-1
rescoring left SD/CM/BU's Good tier both absolute-large and a high percentage of admitted
pool (SD 74%, CM 61%, BU 78%), with Excellent correspondingly thin (5-25% depending on
category) — a structural consequence of Excellent's top-relative anchor design diluting as
pool size grows, not a bug. Real breakpoint-finding across three separate passes (an initial
rank-20 target check, a widened 20-40 gap search, and a final 20-40-rank search) confirmed **no
genuine natural gap exists** in SD's or CM's score distributions anywhere near a reasonable
target size — both are thoroughly continuous fields. Cut points were therefore chosen as
explicit target-size judgment calls, not breakpoint-derived: SD keep=35 (the single largest gap
found in its whole search window, though below the formal significance threshold), CM keep=37
(a smaller, non-flagged gap, chosen over a technically-larger one sitting at the pool's edge),
BU keep=36 (the one genuine, highly-significant gap found — 0.305, dwarfing every other
candidate gap — but one that only excludes a single outlier, Sableye-Mega, and does essentially
nothing to reduce BU's overall size; that tradeoff was explicitly accepted in favor of using
real evidence where it existed).

**Mechanism:** new `_partition_by_admission_floor` runs *before* `_setup_excellent_floor`
computes its second-highest-score anchor — ensuring the anchor reflects the post-floor pool,
not the original. Per-category `damage_admission_floor` and `acceptable_floor_mult` added as
criteria-dict keys (SD 0.981/0.88, CM 0.708/0.88, BU 0.748/0.90) — opt-in via dict key presence,
not a category-name conditional, meaning NP/DD/ID+BP are structurally protected from ever being
affected rather than merely tested to currently match. `_setup_mech_tier` takes an
`acceptable_mult` parameter defaulting to the original shared 0.70, used by every unmodified
category's call site unchanged. Admission-floor comparison rounds to 3 decimals specifically so
each category's exact boundary species (Decidueye/Mr. Rime/Lycanroc) stay inclusive under
float-precision noise.

**A real design question checked and explicitly not pursued:** whether the support categories'
(Tailwind/Sleep) already-Acceptable-largest tier shape could be reused as a model — confirmed
their mechanism is fundamentally different (execution + secondary-role criteria, not a single
anchor-relative damage score) and not adaptable; this task stays within the existing
anchor-relative mechanism, redesigning its parameters rather than replacing it.

**Confirmed by direct verification, including a genuine cross-report consistency proof:** SD's
new keep=35 exclusion list (19 names) confirmed as a strict subset of the earlier keep=20
exclusion list (34 names) — every one of the 19 appears in the 34, exactly as required since a
looser cut must exclude a subset of what a stricter cut excludes. Same check on CM (12 vs. 29,
exact arithmetic match: 29−12=17 newly-included, 37−20=17). This validates cross-report
consistency, not an independent recomputation of underlying calc-derived scores, which weren't
directly re-verifiable without calc access. BU's Emboar usage-discount interaction (Excellent→
Acceptable override bypassing Good entirely) predicted by hand from first principles (5/13/18,
not the naive score-only 6/13/17) and confirmed exactly correct via the delivered report's own
embedded automated boolean self-check (`bu_emboar_5_13_18: True`). All three categories'
resulting tier counts matched their targets exactly (SD 3/6/26, CM 8/10/19, BU 5/13/18).
NP/DD/ID+BP confirmed byte-identical to Stage 4 via the report's own regression check
(`np_dd_idbp_tier_maps_equal: True`, zero mismatches either direction). 102/102 named tests,
993/993 full suite, no regressions.

**Status:** Shipped on `feature/sd-cm-bu-admission-floor`, PR #79, merged to
`wip/setup-tr-usage-and-scoring`. Fresh critic pass required and completed for SD/CM/BU
specifically (Stage 4's prior approval for these three does not carry over, since admission and
tier boundaries both changed); NP/DD/ID+BP's Stage 4 approval remains valid unchanged. No
persist yet.

---

### ADR-019 — Amendment 2026-08-14m

**Cross-source (CBD ∧ Showdown) usage corroboration for setup-move admission: investigated and
explicitly rejected. Today's OR-based `_best_move_set_pct` (max of CBD, Showdown) confirmed
structurally correct, not merely convenient.**

Real question worth asking given this session's pattern of catching single-source data
artifacts (cross-set contamination, the top-12 truncation bug, the CBD-first logic error) — but
confirmed via direct investigation that requiring both sources to agree would be actively
harmful here, not a data-quality improvement. Requiring AND-corroboration would exclude 145 of
175 currently-admitted candidates across SD/NP/CM/BU/DD, including multiple critic-approved
Excellent members, and would wipe NP's entire category (0 of 23 candidates would survive) — not
because CBD and Showdown disagree about real, high-usage play, but because of CBD's coverage
shape: offline snapshot truncation (already mitigated by an existing live-fetch-on-miss
fallback, itself the product of an earlier, deliberate 2026-08-08 fix for the same root
problem class — `TEAM_LADDER_N=50` excluding real candidates like Clefable) plus mega-forme
page gaps.

**A second, deeper investigation confirmed the remaining gap after live-fetch is a genuine,
permanent data-source ceiling, not a further fixable artifact:** CBD's own
`/api/battle/Doubles/{species}` endpoint returns exactly 10 move rows per species, always — our
extraction keeps everything the API provides (confirmed no move-level slice anywhere in the
pipeline, direct spot-check across five species showing `raw == parsed == 10` in every case).
Real, low-presence setup moves that fall outside CBD's own top-10-per-species window are
therefore permanently invisible to CBD, regardless of live-fetching, regardless of any
snapshot-freshness fix — there is no "fuller" CBD to access. Showdown remains the only source
capable of surfacing these; CBD still meaningfully corroborates anything within its window. The
existing OR design is therefore not a workaround but the structurally correct choice given what
each source is actually capable of providing.

**Status:** Discovery only, both passes. No code changes. No implementation planned —
question closed with a real, load-bearing explanation.

---

### ADR-019 — Amendment 2026-08-14n

**Item 7 scoped and Part A (spread-move credit) designed and shipped: setup-attacker threat
panel gains a real teammate for each of the 37 primaries, sourced from tournament-population
co-occurrence data. Spread payoffs now score against both panel members instead of the primary
alone — closing the gap where the real 0.75× Doubles-target penalty was applied with no
compensating credit for actually hitting a second target.**

**Scoping (discovery only, no design commitment yet):** item 7 split into two genuinely
different pieces. Part A (spread-move credit) requires real teammate data to construct
realistic pairs — confirmed available and dense (`data/team-composition/champions-reg-mb.
pikalytics-team-usage.v1.json`, 5,985 real, count-weighted, forme-specific pairs, tournament
population). Part B (ally-damage risk) is structurally independent and much smaller — narrowed
to essentially one move (Earthquake) among current admits, confirmed via real calc target
flags rather than assumed from memory.

**Part A design, locked before implementation:**
- **Panel construction — per-threat top-1 partner.** Each of the 37 Showdown-usage primaries
  keeps its slot; each gets exactly one partner, the highest-count real co-occurrence among the
  other 36 panel members. Zero pair-less members under this policy (weakest edge: Rotom-Wash↔
  Garchomp, count 201 — independently spot-checked against the raw data file and confirmed
  exact). Chosen over broader edge-set policies (top-3, count-threshold) specifically because
  those leave pair-less members needing singleton fallback, which Option 1 was meant to avoid.
- **Single-target payoffs stay primary-only** — the partner is panel context, not a damage
  target, for any non-spread mid. No invented second KO.
- **Spread payoffs originally scored as `mean(primary_frac, partner_frac)` with `worse-of-two`
  KO bin** — framed as a "clear the slot" signal (see Amendment 2026-08-14p: this framing was
  revised after shipping, once it became clear it could net *below* single-target-only scoring
  for many real candidates, contradicting the feature's own motivation).
- **Recoil/drain sum across both spread targets** — mechanically correct, not an approximation:
  real Doubles drain/recoil reflects total damage dealt across all hit targets in one combined
  amount, not two independent partial values.
- **Floette-Mega/`floetteeternal` co-occurrence bridge** — narrow, lookup-only (confirmed via
  code comment and dedicated identity-preservation test), does not rewrite calc identity;
  Floette-Mega keeps its real Fairy Aura stats for all damage computation.

**Confirmed by direct verification:** full 458-line core diff read in full (not spot-checked,
given the size), every design decision traced against the actual code — shared `ohko_mask`
computed once per candidate (not per mid, the source of the original cost estimate being wrong),
`mid != fin_mid` exclusion present, primary-first finisher gating confirmed mechanically correct
(a real move can only be thrown once per turn — the gate correctly reflects "attempted," not
"succeeded," a subtlety not obvious from the design text alone). Two of nine new tests
independently confirmed genuinely adversarial: the sweep_ohko test directly contrasts
one-cleared vs. both-cleared scenarios; the finisher test proves the single-move-per-turn
constraint holds via a real Aegislash-shaped sequence. 1002/1002 tests passing locally (matches
the reported 1004 once two environment-only skip differences — live calc service, Ollama — are
accounted for).

**Status:** Shipped on `feature/pair-defender-spread-credit`, PR #81, merged to
`wip/setup-tr-usage-and-scoring`. Superseded in part by Amendment 2026-08-14p (the scoring
formula) — the panel-construction and single-target-primary-only decisions above remain
unchanged and current.

---

### ADR-019 — Amendment 2026-08-14o

**Item 7 Part B (ally-damage risk) shipped: display-only `criteria_notes.ally_damage_risk`
field for setup-attacker candidates whose real payoff includes a genuinely ally-hitting
("allAdjacent") move.**

**Scope, confirmed via direct discussion:** display-only, no tier/admission impact — same
resolution as burn-immunity (item 10). Scoped to a static, move-intrinsic property check, not
team-context-aware — Role Compendium construction is species-level with no access to a specific
locked teammate, so "safety vs. this candidate's real locked ally" is structurally out of reach
at this stage; "safety vs. a typical partner" (using Part A's now-available co-occurrence data)
is a real possible future extension, not built here.

**Real, systematic move table:** `_ALLY_HIT_DAMAGE_MOVE_IDS` (14 moves), confirmed a genuine
subset of Part A's broader spread-move table, sourced from real `@smogon/calc` move-target data
rather than memory. Correctly distinguishes Surf (ally-hitting) from Muddy Water (foes-only) —
a real, easy-to-mistake Doubles-specific detail that the shipped test suite explicitly checks by
name, unprompted. Type-protection fragments (Ground→Flying/Levitate/Earth Eater, Water→Water
Absorb/Dry Skin/Storm Drain, Electric→Volt Absorb/Motor Drive/Lightning Rod, Fire→Flash Fire/
Well-Baked Body, Grass→Sap Sipper, Poison→Steel-type immunity, Normal→Ghost-type immunity, plus
universal Telepathy/Friend Guard and Soundproof for sound moves) independently verified accurate
against real type-chart mechanics, including correctly noting Dark/Fairy have no type-specific
immunity beyond the universal fallback.

**Confirmed by direct verification:** branch built from `wip`'s tip *before* Part A merged
(explicitly and honestly labeled as such in the ship report, not a mistake) — flagged the real
merge-conflict risk this created, resolved cleanly with no hand conflict-resolution needed (git
auto-merged both features' independent wire sites). Composition with Part A verified by direct
code inspection: `_ally_damage_risk_note` reads the same `payoff_moves` list that Part A's
restructure never mutates, only relabels via `payoff_targets` separately — structurally cannot
conflict. 5/5 named tests, 208/208 broader `role_compendium` suite, 998/998 full suite at ship
time; reconfirmed post-merge with Part A at 1017/1017 total (matching exactly once environment
skips accounted for).

**Status:** Shipped on `feature/ally-damage-risk-note`, PR #80, merged to
`wip/setup-tr-usage-and-scoring` (merged before Part A, per the actual PR sequence — #80 then
#81, inverted from the original plan but a legitimate, verified-clean outcome).

---

### ADR-019 — Amendment 2026-08-14p

**Item 7 Part A's original spread-scoring formula (mean-of-two continuous score, worse-of-two
KO bin) revised: spread payoffs now use `max(primary_alone, pair_mean)` for continuous score
and primary-alone-only for KO-bin/`sweep_ohko` classification — spread moves can no longer
score worse than a hypothetical single-target-only read, only better or equal.**

**The problem, caught by direct inspection of real post-ship numbers, not anticipated during
design:** the original "clear the slot" formula could net *below* the pre-Part-A single-target
score for many real candidates — Rhyperior, Garchomp, Diggersby, Blaziken-Mega, Primarina,
Barbaracle-Mega, Lycanroc, and others all showed real score *decreases* after gaining spread
scoring, directly contradicting the feature's own stated motivation ("stop punishing spread's
0.75× with no upside"). Root cause: `mean(primary, partner)` is only ≥ primary-alone when the
partner takes at least as much damage as primary did — a partner that resists the move type or
is simply bulkier drags the average down, and `worse-of-two` compounds this by requiring the
tougher of two real targets to clear for full OHKO credit, where before only one target needed
clearing.

**Revised design, with one non-obvious mathematical consequence explicitly surfaced and
confirmed intentional before implementation:**
- **Continuous score:** `weighted = max(primary_alone_weighted, pair_mean_weighted)` (and the
  same for `raw_frac`) — primary-alone computed identically to how single-target payoffs are
  scored, pair-mean only applied when it's genuinely better.
- **KO-bin / `sweep_ohko`: reverts to exactly primary-alone's own bin, unconditionally.**
  Confirmed via direct mathematical reasoning before implementation: since `worse-of-two` can
  by construction never exceed primary-alone's bin, "take the better of (primary-alone bin,
  worse-of-two pair bin)" is not a partial protection — it is mathematically identical to
  always using primary-alone's bin, full stop. This means the "clear the slot" bin signal is
  **completely erased** for scoring purposes, not softened. Explicitly confirmed as the desired
  outcome before shipping, not discovered as a surprise afterward.
- **Recoil/drain summing across both targets stays unconditional**, independent of which
  continuous-score alternative wins — real mechanical justification: a spread move mechanically
  always hits both targets when used in-game, so the attacker pays the full two-target
  recoil/drain cost regardless of which number gets reported as the move's evaluation score.
  This was a recommendation surfaced with reasoning (not silently decided) and implemented as
  proposed.
- **Aegislash's remain/King's-Shield-reset gate switched to reading primary's raw hit fraction
  directly (`_hit_frac_from_result(r)`, a pre-existing helper) instead of the scored `raw_frac`**
  (which could now be pair-mean-influenced) — ensures Aegislash's sequence mechanic, which was
  always primary-first by design, evaluates against primary's real damage output specifically,
  not a partner-contaminated number.

**Process note:** this revision was explicitly planned and independently plan-reviewed before
implementation, applying the lesson from Part A's original version (which skipped that step) —
confirmed directly with the person after an initial misreading of the ship report's silence on
the matter.

**Confirmed by direct verification:** full diff read in context against every locked decision.
The recoil-sums-even-when-primary-wins test is built around Rhyperior itself (the real
motivating case) with exact numeric assertions (0.80 continuous score, not 0.50; 0.40 remain
reflecting both targets' recoil despite primary alone winning the score) — proof, not assertion.
The bin-reversion test is genuinely adversarial in the harder direction: partner OHKO'd but
primary not, correctly confirmed to *not* count as OHKO, directly proving the accepted
mathematical consequence rather than just the obvious case. All 7 pre-existing Aegislash-named
tests re-run and pass unmodified. 11/11 pair-panel tests, 1017/1017 total.

**Status:** Shipped on `feature/spread-max-primary-floor`, PR #82, merged to
`wip/setup-tr-usage-and-scoring`. Supersedes the scoring-formula portion of Amendment
2026-08-14n; panel construction and Floette bridge from that amendment remain current.

---

### ADR-019 — Amendment 2026-08-14q

**SD/CM/BU admission floors and Acceptable multipliers re-derived a third time, following item
7's two scoring changes (Part A's original ship, then its revision) — supersedes the SD/CM/BU
values from Amendment 2026-08-14l. NP/DD/ID+BP unaffected throughout, values from 2026-08-14l
remain current for those three.**

**Why three rounds were needed, stated plainly:** Amendment 2026-08-14l's parameters (SD
0.981/0.88, CM 0.708/0.88, BU 0.748/0.90) were fit to post-Stage-1 singleton scores. Item 7 Part
A's original ship changed SD/CM/BU's distributions again (confirmed via a dedicated recheck:
SD/CM's target shapes broke, two real admission losses — Rhyperior from SD, Lycanroc from BU,
the latter notable since Lycanroc's own score had originally *defined* BU's floor value). A
second re-derivation (SD keep=34, CM keep=37 unchanged value, BU keep=36 re-anchored to
Lycanroc's new lower score) was interrupted mid-process when direct inspection of the real score
deltas revealed Part A's original formula could net *below* single-target-only for many
candidates — see Amendment 2026-08-14p. Once that revision shipped and was verified, a third and
final re-derivation was run against the now-stable, corrected scores.

**Final locked parameters:**
| Category | Floor | Acceptable mult | Keep | Live shape |
|---|---|---|---|---|
| SD | 0.969 (Lycanroc-Dusk) | **0.85** (changed from 0.88) | 37 | 3/14/20 |
| CM | 0.708 (Mr. Rime — numerically identical to 2026-08-14l's value; only its rank shifted, 37→38, as CM's admitted pool grew with Delphox's new entry) | 0.88 (unchanged) | 38 | 7/11/20 |
| BU | 0.766 (Lycanroc, recovered from round two's 0.723 once Amendment 2026-08-14p protected it from scoring below its Rock-Slide-standalone value) | 0.90 (unchanged) | 36 | 5/14/17 |

**Notable finding:** the original Excellent/Acceptable multipliers from 2026-08-14l (0.88 SD,
0.88 CM, 0.90 BU) were confirmed via a fresh multiplier grid to still produce Acceptable-largest
on the new, post-revision pools — the original choices were robust, not overfit to one scoring
snapshot. Only SD's multiplier was deliberately changed (0.88→0.85, a direct request, less
aggressive than the grid-confirmed 0.88 option) — not a data-driven correction.

**A genuine, correctly-explained discrepancy surfaced during verification:** live CM shape came
back 7/11/20, not the discovery grid's predicted 6/12/20. Traced to a real display-precision
artifact, not a bug: the discovery report's own tables rounded scores to 3 decimals (Armarouge
0.984 vs. floor 0.9842, appearing to miss by a hair), while the actual tier-assignment code
(`_setup_mech_tier`) compares at full float precision with no rounding — confirmed via direct
code inspection. Armarouge's true unrounded score clears the true unrounded floor; the discovery
report's rounded display created a misleading appearance of a near-miss that the real
computation never had.

**Confirmed by direct verification:** branch content confirmed minimal and exactly scoped (only
criteria constants and existing test assertion values changed — no data files, matching the
explicit "critic JSON and NP snapshot not committed" disclosure). CM's floor constant confirmed
byte-identical before/after (only its explanatory code comment changed). 102/102 named tests,
1017/1017 total, zero regressions. NP/DD/ID+BP tier maps confirmed unchanged throughout all
three re-derivation rounds.

**Status:** Shipped on `feature/sd-cm-bu-post-revision-floors`, PR #83, merged to
`wip/setup-tr-usage-and-scoring`. Fresh critic pass completed and approved (0 flags) for
SD/CM/BU specifically, per the same "admission/tier boundaries changed → prior approval doesn't
carry over" discipline as every prior recalibration round.

---

### ADR-019 — Amendment 2026-08-15a

**First real persist of the Role Compendium's setup-attacker and support categories: nine of
ten categories written to `data/roles/*.v1.json` on `main`, following a fresh construct+critic
pass against fully-current code. Screens Support intentionally excluded from this persist —
handled separately (Amendment 2026-08-15b) once its ranking redesign was actually finished.**

**Persisted:** Swords Dance Attacker (37, 3/14/20), Nasty Plot Attacker (23, 2/15/6 — real
current number, confirmed fresh rather than assumed from an earlier round's snapshot), Calm
Mind Attacker (38, 7/11/20 — first persist), Bulk Up Attacker (36, 5/14/17 — first persist),
Dragon Dance Attacker (12, 3/9/0 — first persist), Iron Defense + Body Press (24, 2/18/4 — first
persist), Tailwind Setter (23, 1/9/13 — first persist), Sleep Status Spreader (14, 1/2/11 —
first persist), Trick Room Setter (28, 2/14/12 — refreshed under its 22.5% floor). SD, NP, and
Trick Room's pre-refresh stale versions were archived to gitignored `data/roles/history/`
before being overwritten, not silently discarded — a real rollback path if ever needed.

**Confirmed by direct verification, not just Cursor's report:** every one of the nine
categories' persisted tier counts spot-checked directly against the actual JSON content (not
just the summary), not just aggregate numbers — SD's Excellent membership confirmed at the
species level. Weather×4 and `redirection.v1.json` confirmed byte-identical to their pre-task
state via direct SHA-256 hash comparison against `main`, not assumed unchanged. `data/roles/`
confirmed to contain exactly 14 files post-persist (5 untouched originals + 9 new/refreshed).
1017/1017 tests (matching the now-familiar environment-skip pattern), zero regressions.

**Process note:** an initial version of this persist run included Screens Support despite an
explicit correction sent beforehand to exclude it — resolved cleanly since nothing had been
committed yet; the final commit correctly contains only the nine intended files, independently
confirmed absent of `screens_support.v1.json`.

**Status:** Shipped on `feature/persist-ten-role-compendium`, PR #85, merged to `main`.

---

### ADR-019 — Amendment 2026-08-15b

**Screens Support fully redesigned and persisted — closes the three structural gaps identified
in the 2026-08-13 session (membership wrongly excluding lone-screen-plus-Prankster holders,
Light Clay's duration benefit unreflected in ranking, Aurora Veil's dual-screen scope
unreflected in ranking) that had survived, partially unresolved, since before this arc began.**

**Discovery during today's persist review:** Screens Support had actually been built, critic-
approved, and persisted once already (2026-08-13, without waiting for sign-off — a real process
slip, acknowledged at the time). That persisted file was subsequently lost in the same
uncommitted-local-persist failure pattern that affected CM/BU/DD/ID+BP/TW/Sleep. Stage 4's
rebuild this session (Amendment 2026-08-14i) silently reused the old, only-partially-fixed tier
scheme — membership gate corrected, but Clay-duration and Veil-scope ranking gaps never
resolved into code. Caught before commit: Whimsicott's real learnset (Light Screen only, no
Reflect, no Aurora Veil — independently verified) directly contradicted its Excellent placement
in that carried-forward state.

**New tier rule, fully locked and real-data-verified:**
- **Dual-screen capable** (core membership requirement): real Reflect **and** Light Screen
  access (verified via the existing `_same_row_both_moves` same-source discipline), **or** real
  Aurora Veil access plus genuine self-sufficient Snow-setting — **Snow Warning only**. Chilly
  Reception explicitly excluded as a qualifying path: it forces a switch-out, breaking the tempo
  needed to actually follow up with Veil, not genuine self-sufficiency.
- **Excellent** = dual-screen capable **and** Prankster (any ability slot). **Only male Meowstic
  qualifies** — female Meowstic's real ability set (Keen Eye / Infiltrator / Competitive,
  confirmed directly against the live Showdown pokedex, since the local snapshot has no
  distinct female-forme entry) has no Prankster in any slot.
- **Good** = dual-screen capable **and** Speed ≥ 100 (reused as-is from the prior scheme, not
  re-derived) **and not** Prankster.
- **Acceptable** = (dual-screen capable **and** Speed < 100) **or** (single-screen-only **and**
  Prankster — the Whimsicott case, real set% 2.321%, just clearing the category's own
  2.3% presence floor).
- **Excluded entirely, regardless of prior admission:** single-screen-only without Prankster
  (Florges — real data confirms Light Screen only, Flower Veil/Symbiosis abilities, no
  Prankster path); Veil-only without genuine Snow Warning (Avalugg — real Veil access but no
  self-Snow mechanism, ally-dependent, treated as disqualifying same as Florges' scope failure).

**Floor choice explicitly resolved, not left ambiguous:** uses Screens' own previously-derived
2.3% presence floor (a genuine breakpoint found in the real distribution, same rigor as every
other threshold locked this arc) — not the generic 0.1% setup-attacker floor, which was never
derived against Screens' own data and would have admitted candidates like base Gardevoir purely
on a borrowed, contextually-inappropriate threshold.

**Real-usage gate confirmed working, not just asserted:** Mega Gardevoir — fast, mechanically
dual-screen-eligible by learnset — explicitly named as the motivating adversarial case and
confirmed correctly excluded (real set% 0.016%/0.006%, far below floor), proving the existing
usage-gated candidate-discovery pipeline (reused as-is, not rebuilt) does its job.

**Confirmed by direct verification:** persisted content read directly — all three tier lists
match exactly (Excellent: Grimmsnarl/Klefki/Meowstic/Sableye; Good: Dragapult/Froslass-Mega/
Ninetales-Alola/Serperior; Acceptable: Abomasnow/Abomasnow-Mega/Aurorus/Vanilluxe/Whimsicott).
Whimsicott's actual persisted record spot-checked: Light Clay correctly surfaced only as an
informational `criteria_notes` field, not a membership gate, matching the resolved design
principle exactly. Weather×4/redirection confirmed byte-identical via hash comparison.
`data/roles/` confirmed at 15 files. 11/11 Screens-specific tests, 1017/1017 total.

**Status:** Shipped on `feature/screens-support-redesign`, PR (link provided, `gh` unauth),
merged to `main`.

---

### ADR-019/030 — Amendment 2026-08-15c

**Input-boundary species/form resolution shipped — closes the "input-boundary" half of the
canonical name/form resolution problem, the last remaining structural gap from the original
discovery report (open since 2026-08-08, repeatedly deferred through every subsequent session).
Record-side CBD remapping remains a separate, deliberately deferred task per the original
no-dependency ruling.**

**Real-data discovery preceded design, not the other way around.** Direct probes (not doc
review) confirmed both previously-identified halves were still genuinely unshipped: the
record-side gap had partially resolved itself as a side effect of other work (Showdown-offline
teammate storage now correctly stamps exact forms — the original motivating Swampert/
Swampert-Mega bug is gone on that path — but CBD's fallback path still stores ambiguous base
names), while the input-boundary half was untouched everywhere a name gets parsed (bootstrap
pool, bootstrap anchor, candidate-selection typing).

**Full scope enumerated from real Champions legality data, not the 5 species ADR-030's earlier
reactive audit happened to find:** 314 legal species, 107 legal non-base formes, 76 Megas, 15
regional forms, confirmed gender-locked cases (Basculegion/Basculegion-F — a real stat split,
not cosmetic). Zero legal children found to be cosmetic-identical — cosmetic variation
(Vivillon patterns, Alcremie flavors) never produces a second legal species id, narrowing the
resolver's real scope to genuine mechanical/naming variation only.

**Grounded against real Showdown data, not a curated table** (same discipline as ADR-030's
`_NON_DAMAGING` replacement): Showdown's own `aliases.ts` (filtered to species) plus
`@pkmn/dex`'s prefix/suffix `formeNames` rewrite loop — confirmed, after direct pushback,
to already include the full single-letter token set (`a`/`g`/`h`/`p`/`m`), not just the
spelled-out forms an earlier pass had incompletely assumed. A gated gender-suffix pass was
added on top: `male` strips to the bare base only if a real `{stem}f` sibling exists in the
snapshot (the sibling gate — proves a genuine gender-differentiated forme exists before
stripping anything, rather than blindly matching "Male" on any species); `female` concatenates
to `{stem}f` under the same gate. Two real corrections caught only by direct pushback on the
discovery's own analysis, not shipped as first drafted: "Basculegion Male" was initially
(wrongly) classified as genuinely ambiguous input needing to "not guess" — it's an explicit
disambiguator, not ambiguous, and the real gap was simply no suffix-gender rule existing yet.
`m` is already claimed by Mega in the letter-token system and must not be overloaded as male
(would silently break `Swampert-M`→Mega); `e`=Eternal was considered and explicitly rejected
(`Floette-E` only works via one specific Showdown alias entry, not a general rule — generalizing
would create false matches on any id ending in "e"). Chilly Reception was considered and
rejected as a valid self-Snow-setting qualifier for a *different*, adjacent piece of work
(Screens Support) for a real mechanical reason (forces a switch-out, breaking the tempo needed
to follow up), not folded into this resolver's scope.

**Genuine ambiguity still prompts, correctly distinguished from missing abbreviations.**
Dual-Mega species (Charizard/Raichu X vs. Y) and Paldea-cluster Tauros (Combat/Blaze/Aqua) have
no unique letter-code answer — confirmed to fall through to the existing fail-closed prompt
path, same bucket as Floette's illegal-base ambiguity, rather than have a rewrite rule invented
for them. The resolver sits *before* the existing `is_species_legal` check, not in place of it.

**Two adjacent fixes folded into the same branch, by direct request:**
- `_attribution_status`'s false-ambiguous bug (16 legal species, Grimmsnarl named) — was
  flagging any species with *any* snapshot lineage child as ambiguous, including illegal
  Gmax/event/Totem formes. Fixed to require a genuinely *legal* sibling before flagging
  ambiguity. Confirmed correct via direct contrast: Grimmsnarl (illegal Gmax sibling only) now
  resolves `exact`; Garchomp (legal Mega sibling) correctly still resolves `ambiguous`.
- The extraction pipeline (`join.ts`) now emits real, unlisted `otherFormes` — species present
  in the base Pokédex data but missing their own `formats-data.ts` row — inheriting the
  parent's legality flags, explicitly excluding `battleOnly` and `isCosmeticForme` entries.
  Surfaced six real species: `meowsticf`, `mausholdfour`, `polteageistantique`,
  `sinistchamasterpiece`, `vivillonfancy`, `vivillonpokeball`. This incidentally and cleanly
  resolved today's earlier open question from the Screens Support redesign — female Meowstic's
  Champions legality, previously confirmed invisible to the agent — without any special-casing;
  the resolver's existing female-sibling notice logic picked it up automatically once it became
  a real snapshot entry.

**A real regression was found and fixed during verification, not before shipping.** The
otherFormes fix enlarged `lineage_ids()`'s output for Maushold and Vivillon (now genuinely
including their new sibling formes), which changed branching in `coverage.py`'s
`_expand_ladder_species` — a function this task never touched directly — causing usage-data
threat expansion to silently substitute the base species' Showdown row for usage entries that
were already keyed to a specific child forme (`mausholdfour`/`vivillonfancy` stamped as
`Maushold`/`Vivillon`). Caught only because the full test suite was run rather than the three
originally-named files, which never included the affected test file
(`test_usage_species_stamp.py`) — a real, concrete argument for full-suite verification over a
narrower named command on anything touching shared data structures. Fixed precisely: usage
entries keyed to a non-base lineage member no longer expand across sibling Showdown hits, only
base-keyed entries still do (preserving the correct Charizard/Floette-style expansion
elsewhere).

**Confirmed by direct verification, not just Cursor's reports (two rounds, given the
regression):** every adversarial and positive test case from the design phase re-run directly
against the live resolver (`Eternal Floette`, `M-Swampert`, `Basculegion Male`, `A-Ninetales`,
`Ninetales-A`, `Floette-E` all resolve; `Floette`, `M-Charizard`, `Charizard-M`, `P-Tauros`,
`Swampert Male` all correctly stay unresolved). `_attribution_status` traced directly for
Grimmsnarl/Hatterene/Garchomp. All six new `otherFormes` species confirmed present in the actual
generated snapshot with correct inherited legality flags — not just claimed. `species_aliases`
count (1857) and `schema_version` (3, nested under `meta`) both confirmed exact. The
`coverage.py` regression traced to its root mechanism directly (`lineage_ids` before/after
comparison) before accepting the fix, then re-confirmed at the data level post-fix (`Maushold-
Four`/`Vivillon-Fancy` correctly stamped), not just via test pass/fail. 1036/1036 total tests
across both verification rounds, zero unexplained failures.

**Status:** Shipped on `feature/species-form-resolver` (two commits: the resolver itself, then
the `coverage.py` regression fix), not yet merged. Record-side CBD remapping remains its own
separate, deliberately deferred task.

---

### ADR-019/030 — Amendment 2026-08-15d

**Record-side CBD usage-ratio attribution shipped — closes the second, deliberately-deferred
half of canonical name/form resolution (the input-boundary half shipped in Amendment
2026-08-15c). Both halves of the problem first identified 2026-08-08 are now closed.**

**Real scope, corrected from an earlier session's imprecise count.** The originally-cited "8
rows" figure was Swampert's own CBD page-count, not the number of unique ambiguous species.
Direct census against the live snapshot found 24 unique CBD teammate labels flagged
`ambiguous` (plus 5 separate flavor-name `unresolved` strings, a different, orthogonal
problem). **Real production impact is far narrower than that count suggests:** 46 of 50 CBD
pages have a Showdown-offline row and are never read in production at all
(`query_teammates` uses Showdown first) — the remap only matters for the 4 CBD-only anchor
species (`floette`, `mawile`, `mausholdfour`, `vivillonfancy`) and whichever teammates appear
*only* on those four pages. Confirmed exactly one concrete real case this fixes: Mawile,
appearing as a teammate specifically on the `mausholdfour`/`vivillonfancy` shared-query path.
Explicitly decided to build it anyway despite the narrow practical footprint, since it closes a
real, previously-identified gap rather than leaving it permanently fail-closed.

**Real breakpoint search, not an assumed threshold.** CBD stone-holding percentage (the Mega
signal — confirmed abilities are pre-Mega on every checked page and do not distinguish) forms
three real clusters separated by two genuine gaps: Mega-dominated (81.0–99.3%), genuinely mixed
(29.3–65.9%, both forms independently real usage — e.g. Tyranitar), base-dominated (≤4.6%,
remapping would be actively wrong). A round 90% cutoff was explicitly checked and rejected —
it does not sit in a cluster-separating hole, and would incorrectly split Metagross (90.7%)
from Gardevoir (88.6%), both genuinely Mega-dominated. **`_MEGA_STONE_FALLBACK_PCT = 80`**
(an existing, unrelated Role Compendium constant — usage-proven role membership, a different
mechanism) was confirmed via direct data-check to sit safely inside the real 65.9→81.0 gap, and
reused deliberately as `_MEGA_STONE_REMAP_PCT` — a legitimate, data-grounded reuse this time,
not an assumed transfer, and documented in code as such.

**Dual-Mega handled with the same uniform rule, no species-specific carve-out.** If the single
highest-stone-percentage legal Mega clears 80%, remap to it — regardless of any runner-up's
residual share. Charizard-Y (95.6%) and Raichu-Y (81.0%, right at the threshold) both qualify
identically; Raichu-X's real, non-trivial 11.2% share is simply left unattributed by this
mechanism, correctly falling back to fail-closed for anyone actually running that minority
form. Confirmed adversarially: a dedicated test directly asserts Raichu-Mega-X's id never
appears in remapped output, proving the single-winner rule rather than a combined-share
shortcut.

**The load-bearing architectural finding: a real remap requires identity rewrite, not a status
flip.** Confirmed by tracing `team_candidates` directly — it keys admission off
`to_id(evidence.name)`, not `SharedTeammate.species_id`. Promoting `ambiguous` → `exact` on the
stored base name alone would have silently admitted base Swampert as if it were Swampert-Mega —
reproducing, in a different location, the exact silent-wrong-form bug this whole effort exists
to prevent. The shipped fix rewrites both `species_id` and `name` on the CBD evidence row to
the attributed forme's real canonical name, then sets `attribution_status` to `exact` so
existing admission logic picks it up correctly without any downstream widening.

**Correctly scoped out, not silently ignored:** mixed and base-dominated clusters stay
fail-closed (fail-closed remains the correct behavior there); cosmetic otherFormes ambiguity
(Sinistcha, Maushold, Vivillon — mechanically identical children, no usage signal exists at
all) confirmed untouched by this mechanism, since it isn't a stone-attribution problem in the
first place; Basculegion's gender ambiguity (a different signal type, not a stone) explicitly
left as a separate, real, un-actioned gap; flavor-name canonicalization (3 remaining unresolved
strings) confirmed orthogonal to usage-ratio attribution, not folded in; no new
`attribution_status` value added — downstream only tests `== "exact"` today, so a distinct
status would be pure unused observability, correctly deferred until a real need surfaces.

**Confirmed by direct verification, not just Cursor's report:** `_cbd_mega_remap` traced
directly against the code — reuses the existing `_item_mega_forme` stone-detection helper
rather than reinventing it, includes a deterministic alphabetical tiebreak for exact percentage
ties, correctly gates on `ambiguous` status only. Two of six new tests independently confirmed
genuinely adversarial: the Raichu test directly asserts the excluded form's id is absent, not
just that the included form is present; the Mawile test exercises the real downstream consumer
(`query_shared_teammates`) end-to-end with the actual two CBD-only anchors, not the internal
helper in isolation — reproduced independently via a direct call outside the test suite,
confirming `mawilemega` / `Mawile-Mega` / `exact` with base `mawile` absent. Sinistcha and the
flavor-name case both confirmed to remain untouched. 15/15 named tests, 1042/1042 full suite,
zero regressions.

**Status:** Shipped on `feature/cbd-mega-usage-attribution`, not yet merged (branch pushed, no
PR opened per standing instruction to wait until requested). Closes the record-side half of the
canonical name/form resolution problem; combined with Amendment 2026-08-15c, the entire
original 2026-08-08 discovery item is now fully resolved.

---

### ADR-019/028 — Amendment 2026-08-15e

**Secondary speed-control softening shipped: a real, adjacent signal on Trick Room/Tailwind
resilience rows recording kit-present alternative speed-control methods (Icy Wind-class Speed
drops, Sticky Web, guaranteed paralysis, Syrup Bomb, running Gooey/Static) — deliberately does
not touch classification, gap, or provider cardinality. Closes deferred item 1 from ADR-028's
own "deliberately deferred" list.**

**Real, precise enumeration, not scoped to the named examples.** Direct extraction against
Champions-legal move/ability data: 11 guaranteed opponent-Speed-drop moves (confirmed zero
Champions-legal chance-gated Speed drops remain — all Past-gen), Sticky Web, 5 guaranteed-
paralysis moves, plus code-only Syrup Bomb, and two abilities (Gooey, Static) gated on actually
running, not merely legal access.

**A real correction caught before implementation, not after.** The original framing ("this
softens gap severity") was checked against its literal consequences and found to be either
inert (demoting essential→preferred barely changes generation, since preferred still opens a
gap) or actively harmful (demoting preferred→optional would fully suppress backup-setter
generation, treating Icy Wind as if it mechanically closed the Trick Room gap — a false claim,
since Icy Wind doesn't invert turn order, doesn't help against Ground-immune targets, and isn't
always a doubles spread). Corrected to an adjacent, purely additive field before any code was
written — explicitly re-confirmed with sign-off given it reversed an earlier locked framing.

**Kit-vs-learnset discipline concretely proven, not asserted.** Milotic's Icy Wind sits at
35.9% real usage but isn't on its actual featured set (Protect/Scald/Muddy Water/Coil);
Rotom-Wash's Electroweb similarly misses its real Choice Scarf kit. Evidence bar confirmed as
`resolved_build.moves`/`ability`, `present=True` — the same standard as every existing ADR-028
provider, not learnset or raw usage%.

**Confirmed by direct verification:** full diff traced against every locked decision — no
`condition:*` tag ever emitted (confirmed via direct code read, preventing these from being
mistaken for primary providers downstream), Gooey/Static gated on the single actual running
ability rather than a set-membership legality check, deterministic behavior confirmed. Two
adversarial cases independently inspected: Raichu-shaped dual-form exclusion logic (not
directly applicable here, but the same discipline pattern held) and the Milotic/Rotom-Wash
kit-vs-usage% exclusion, both proven via tests using real `resolve_anchor_build` calls, not
mocks. Full suite regression clean at ship time.

**Status:** Shipped on `feature/secondary-speed-control-softening`, not yet merged.

---

### ADR-028 — Amendment 2026-08-15f

**Per-member Trick Room wanted-total discount and hindering-nature emission shipped. Trick
Room's wanted-total now both narrows (Speed-invested members stop voting) and widens (genuinely
slow-built members without a declared sweeper role start voting) — while classification
mechanics, `needed`-tier dependents, `benefits_from` mechanism presence, and
`_preferred_setter_direction` all stay untouched.**

**Subtract — four independent, OR-combined intent signals exclude a `wanted`-tier Trick Room
dependent from the count:** effective Speed ≥ a derived floor (125 today — the high side of a
real 90→125 gap in the live top-10 threat pool, explicitly checked against and rejected in
favor of two tempting-but-wrong alternatives: base Speed 100, already rejected by ADR-015
Amendment 2026-07-29d precedent via the Mega Kangaskhan case, and the existing `already_fast`
line at ~136, which sits inside the fast cluster rather than at its actual edge); any real
Speed EV investment > 0 (no minimum — even minimal dump-EV allocation reflects deliberate
normal-turn-order intent, and Trick Room inverts the value of exactly that choice); Choice
Scarf held; a Speed-boosting nature (Jolly/Timid/Naive/Hasty). `needed`-tier dependents are
never discounted. The underlying `benefits_from` mechanism itself is never deleted — a
discounted member's declared identity stays true, it simply doesn't add a vote.

**Add — a new evidence source, not a filter.** A locked member with a genuine Speed-hindering
nature (Brave/Quiet/Relaxed/Sassy) and no existing Trick Room `benefits_from` mechanism, who is
not itself a Trick Room provider, now generates a new `wanted`-importance mechanism. Two such
members with zero declared sweeper identities can independently drive `essential`
classification via `wanted×2` — confirmed as the intended design outcome, not a side effect,
and stated plainly as such to avoid it being mistaken for a bug if noticed without an obvious
declared cause.

**A genuinely subtle edge case, explicitly designed for and tested:** a hindering-nature member
who also independently triggers one of the four exclusion signals (e.g. real Speed EV
investment despite a hindering nature) gets the new mechanism emitted, then immediately
excluded by the same discount check — net contribution zero, not a contradiction or double-count.

**Why base stat was never viable, proven with a concrete case.** The same species, Garchomp,
produces three genuinely different effective Speeds (151 default usage, 129 under a
TR-sweeper-hinted spread, 151 again if user-locked at default) depending entirely on the
resolved build — a base-stat rule cannot distinguish any of them; only the resolved build's
real EVs/nature/item can.

**Explicit non-goal, stated plainly:** this discount narrows what counts as *evidence* the team
wants Trick Room — it does not discourage, penalize, or actively work against Trick Room being
present or used. A team can still run Trick Room even when every locked member's own signal is
discounted, if the person building the team wants it for reasons the need-counting doesn't
capture. `_preferred_setter_direction` (an existing heuristic promoting Trick Room to
`preferred` when a setter is locked alongside any offense teammate) is deliberately left
unchanged even when that offense teammate is Speed-discounted — confirmed as a real interaction
point, correctly reasoned through and left alone rather than "fixed," since changing it would
work against Trick Room, precisely the outcome this whole amendment exists to avoid.

**Explicitly out of scope, confirmed:** Tailwind (no per-member discount — its mechanism
uniformly benefits the whole side regardless of individual member Speed, unlike Trick Room's
inverted-order mechanic); priority-move access as a second discount signal (deferred, add only
if proven necessary); a raw wanted-count-vs-discount-count split on the resilience row
(considered and explicitly declined — no consumer exists that could use it yet, same "optional
observability, add only when a real need surfaces" discipline as the CBD remap's status-field
decision); Charizard-Y-on-Rain-shaped cross-configuration coexistence (a member that wants TR
in one alternate 4-mon selection but not another — blocked on unbuilt selected-four/one-Mega-
per-team roster modeling, a separate, still-unbuilt prerequisite, named as a known limitation
rather than attempted).

**Confirmed by direct verification, not just Cursor's report.** Full diff traced against every
specified detail, including subtle ones: the floor-derivation algorithm correctly excludes both
end-pairs

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

### ADR-022 — Amendment 2026-08-20a

**Support-need resolution restricted to real compendium candidates only, for any need
category with a real compendium mapping — plus two wrong/missing compendium mappings fixed.**

**A raw-move-learns-it fallback was too permissive for needs with a real compendium to check
against.** Confirmed live: Gholdengo mechanically learns Light Screen and Reflect but is
genuinely not a recognized screens user (confirmed directly against the real screens
compendium) — the raw-move fallback let it match anyway, at low confidence. Confirmed as the
correct design directly, not assumed: a need with a real compendium should exclude
unrecognized candidates entirely, not merely deprioritize them, since here the capability
claim itself isn't backed by real data (unlike the weather-conflict case, ADR-028 Amendment
2026-08-20a, where the capability is real but currently inapplicable). Scope, confirmed
directly rather than guessed: applies to every need category with a real compendium mapping
(`screens`, `tailwind`, `trick_room`); needs without one (`healing_cleric`,
`taunt_disruption`) are unaffected, since there's nothing to restrict against.

**Two compendium-role mappings corrected.** `_compendium_roles_for_need` had no case for
`"tailwind"` at all, despite a real `tailwind_setter` compendium category existing — every
tailwind match, including a real "Good"-tier setter (Staraptor-Mega), only ever received
raw-move (mechanical_only) evidence. Added the mapping. Separately, the existing
`fake_out_protection -> redirection` mapping was mechanically wrong — redirection cannot stop
Fake Out, which has higher priority than redirection moves — and no real "priority protection"
compendium alternative exists (confirmed directly: would have ~2 candidates even if built, not
representative enough to restrict against). Removed the mapping entirely;
`fake_out_protection` now stays on the raw-move/ability path unrestricted, same as
`healing_cleric`/`taunt_disruption`.

**Status:** Implemented and verified. Three pre-existing tests needed updating to reflect the
new, intentional behavior (a species found only via raw-move, with no real compendium
recognition, is no longer added for a category that now has a real compendium mapping) —
confirmed each test's actual prior purpose before rewriting, not just patched to pass.

---

### ADR-022 — Amendment 2026-08-20b

**A confidence-specificity spectrum added for support-need evidence: unconditional
(trigger=None) needs downgraded; Wish downgraded for a real, structural delivery cost.**

**Needs generated unconditionally for an anchor's shape** (e.g. `screens`/`healing_cleric`'s
broad, "attacker-universal" fallback trigger, `trigger=None`) previously received the same
evidence confidence as a genuinely, specifically-triggered need (e.g. `trick_room`'s real
`speed_tier:middling` trigger). Confirmed live this let broad, weakly-discriminating matches
look equivalent in strength to real, specific ones. `resolve_all_support_needs` now forces
confidence to `"low"` for any need with `trigger=None`, leaving `basis` untouched (the data
source quality isn't in question, only the match's specificity) — confirmed a real,
specifically-triggered need in the same resolution pass (e.g. `trick_room`,
`healing_cleric`'s `tank_no_self_heal` override) is correctly unaffected.

**Wish downgraded for a real, structural delivery cost the plain move-satisfies-need check
doesn't capture:** confirmed directly, not assumed — Wish doesn't heal immediately, it heals
whoever is on the field one turn later, meaning delivering it costs a real, vulnerable
switch-in turn (the incoming Pokemon can't attack, since switching consumes the turn) and
loses any stat boosts the switched-out user had, a genuinely worse mechanism than an
immediate-heal move. New `_DELAYED_DELIVERY_MOVES` constant; downgraded only when EVERY
healing_cleric-satisfying move a candidate has is Wish — a candidate that also knows a real
immediate-heal move is untouched.

**Status:** Implemented and verified against real species data (Sylveon: Wish-only,
downgraded with an explicit tag; Clefable: also knows Heal Pulse/Life Dew, correctly
unaffected).

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

### ADR-023 — Amendment 2026-08-11a

**`single_locked` inverts present weather `provides` into kit-emitted `benefits_from`
candidates.**

**Decision:** After `resolve_all_support_needs` and before `merge_need_resolved`,
`discover_single_locked` calls `resolve_condition_beneficiaries`. That private resolver reads
`provided_weather_conditions` on the already-computed `AnchorRoleDecision` (present + provides
+ needed/wanted, Rain/Sun/Sand/Snow only — Tailwind/Trick Room ignored) and inverts existing
kit-emitted beneficiary tables (`_NEEDED`/`_WANTED_CONDITION_ABILITIES` via
`CONDITION_DEPENDENT_ABILITIES`, plus `CHARGE_INSTANT_WEATHER` charge moves). Results merge
into `need_resolved_candidates` by species id. New `NeedCategory` `condition_beneficiary` is
Literal-only: `query_support_needs` does not emit it, and it is not mapped in
`_NEED_TARGET_ROLES`/`_CONDITION_SETTER_TARGET_ROLES`/`_NEED_SATISFIERS`. Unmapped category →
existing kit-fallback (3a); a leak into `resolve_need_candidates` still hits the existing
`NotImplementedError` skip.

Locked-anchor self-hits drop via `lineage_ids` of whatever is locked, not a Pelipper-specific
filter. Ranking is the existing usage-rank union (n=20), not a new stage and not needed-tier-
first. Ability hits are `mechanical_only`/`low`. Unresolvable kit-fallback misses (Qwilfish-
shaped) are a presentation-loop ceiling: `_route_after_refine` rediscovers (3c), they do not
hard-dead-end. Rediscovery may re-offer the same default; no presentation-time resolvability
filter until a real interactive session shows that repeating across cycles.

Weather helpers live in `anchor_roles` so `slot_fill` never imports `mechanism_condition` from
`condition_resilience` (that module already imports `slot_fill`).

**Alternatives considered:** Role Compendium-first admission for weather beneficiaries
(rejected: no M-B VGC Role Compendium exists; ADR-015 Amendment 2026-07-28d already forbids
Beneficiary as a Compendium membership type). Needed-tier-first ranking (rejected in plan-
review: would put unresolvable Qwilfish in the top-3). A presentation-time kit-fallback filter
(rejected: 3c is the safety mechanism). Wiring the same invert into `multi_locked` or
`condition_resilience` (out of scope: resilience stays gap-driven backup-setter search).

**Why:** `query_support_needs` answers "what the locked anchor needs," which is the wrong
question for a weather setter. Pelipper (Drizzle provides Rain) was presenting partners with
no rain-beneficiary logic — the mirror of the same-day Archaludon Electro Shot → rain-setter
fix. Inverting tables the kit already emits is the smallest structural close; a new public
ADR-022 query tool and a new ranking key were both unnecessary once matching_needs length was
shown to lift beneficiaries over high verified_score threat rows.

**Status:** Implemented and verified (`recommender/anchor_roles.py`,
`recommender/slot_fill.py`, `recommender/nodes.py`, `recommender/support_needs.py`; 832 tests
passing, 6 skipped). Deliberately deferred, not oversights: Tailwind/Trick Room beneficiary
invert; `multi_locked` wiring; presentation-time resolvability filter; Role Compendium
construction.

---

### ADR-023 — Amendment 2026-08-16a

**Selected-four Mega-ceiling guidance shipped: informational notices surfaced on both
`single_locked` and `multi_locked` candidate presentation when locked Mega-Stone holders
approach or reach the format's real ceiling — no ranking impact, no candidate exclusion.
Closes Gap 5 from the original 2026-08-02 discovery, previously deferred pending quick-pick's
design.**

**The prior deferral is superseded on the numbers, not overridden blindly.** Gap 5's original
reasoning bundled two different unknowns: "the format's real pick count" and "quick-pick's own
eventual behavior." Confirmed today that only the second is genuinely unbuilt — Reg M-B doubles'
bring-6/pick-4 structure is a fixed format constant (`flat_rules: Min Team Size = 6`, `Picked
Team Size` resolving to 4 for VGC), not something quick-pick's implementation determines. The
ceiling itself (`1 + (team_size - pick_count)`, re-derived independently this session from
"once M exceeds the ceiling, every possible 4-of-6 selection necessarily includes 2+ Mega-Stone
holders together, and only one can ever benefit from its held item in a given game" — corrected
mid-design from an earlier, inaccurate "forced" framing, since Mega Evolution is always
optional even when multiple holders are selected together) is computable now; only the
*surfacing UX* had any real quick-pick dependency, and even that was already envisioned as
happening during team-composition-stage narrowing, a moment that exists independent of
quick-pick.

**Counting method: per-species, confirmed as the right default via a real observation, not
picked arbitrarily.** The per-option-vs-per-species fork was found to be "almost vacuous" on
the actual locked-roster mechanism — existing lineage exclusion already prevents two Mega
formes of the same base species from ever being locked simultaneously, so the choice barely
matters for this task's real use case. Deferred as genuinely consequential only if a future
task extends this to the broader owned/candidate pool.

**Real, complete dual-Mega enumeration, not scoped from memory:** exactly 3 legal Champions
bases with more than one legal Mega option (Charizard X/Y, Raichu X/Y, Meowstic M/F-Mega),
systematically checked against a real exclusion sweep (Mewtwo X/Y illegal/Restricted;
Magearna, Tatsugiri, Absol/Garchomp/Lucario Mega-Z all illegal or Future).

**Scope, larger than initially expected, confirmed and accepted:** closing this required three
real pieces, not one — extending `annotate_composition_impact`'s existing `multi_locked` wiring,
building an entirely new equivalent for `single_locked` (which had no composition-impact
annotation at all, meaning the earliest and arguably most useful moment for this guidance — the
very first lock, if it's Mega-capable — was previously a real gap), and building the missing
notice channel for `present_candidates` (bootstrap already had `pending_presentation["notices"]`,
but it was unused on candidate selection).

**A real, small, incidentally-found bug fixed in the same pass:** `_item_mega_forme` built a
non-existent `"meowsticmega"` id for base Meowstic (the real ids are gender-specific,
`meowsticmmega`/`meowsticfmega`), silently returning `None`. Fixed to resolve deterministically
to the male/default forme — confirmed the female base already resolved correctly by coincidence
through the existing generic pattern, so only the broken case needed a fix, not a general
rewrite.

**Confirmed by direct verification, not just Cursor's report:** every locked design decision
traced directly against the actual diff — per-species counting confirmed via `lineage_ids`
base-normalization into a set; the ceiling formula confirmed genuinely parameterized (`len
(draft)`, `state["picked_team_size"]`), not hardcoded, independently reproduced for both the
real VGC value (3) and a hypothetical 3-pick format (4); `SlotFillContext`'s mutability
confirmed directly before trusting the attribute-assignment wiring pattern was safe. Two of the
new tests independently confirmed genuinely load-bearing on inspection: the Charizard-X-locked
case proves the notice stays "1 of 3" (not double-counted) using the real candidate-merge
pipeline, not an isolated function call; the `single_locked`-first-lock test proves the
previously-missing half of the scope actually works end-to-end, with `ctx.notices` captured at
the terminal step. The Meowstic fix and ceiling formula both independently reproduced via
direct code execution outside the test suite. 11/11 named tests, 1087/1087 full suite, zero
regressions.

**Status:** Shipped on `feature/mega-ceiling-guidance`, PR #91, merged to `main`.

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

### ADR-024 — Amendment 2026-08-11a

**Move-derived weather need-resolution — closing a self-documented gap in
`query_support_needs`'s `condition_setter` branch.**

**Decision:** `RoleShapeContext` gains a `needed_weathers: tuple[str, ...]` field, projected by
`derive_role_shape_context` from present `benefits_from` mechanisms (`needed`/`wanted`,
present or teammate-expected, tagged `condition:{Weather}`) — the same evidentiary bar already
used for condition-resilience dependents. `query_support_needs`'s `condition_setter` branch
now consults this field in addition to `_CONDITION_DEPENDENT_ABILITIES`, emitting a
`condition_setter`/`field_condition:any:{label}` need for any uncovered move-derived weather
dependency across all four tracked weathers (Rain/Sun/Sand/Snow), not a Rain-specific patch.
Labeling generalized via a new `_CONDITION_SETTER_TARGET_ROLES` companion map — `condition_
setter` is one need category mapping to four possible target roles depending on the resolved
weather label, modeled as a 1:many map alongside `_NEED_TARGET_ROLES` rather than forced into
that map's existing 1:1 shape.

**Alternatives considered:** a Rain-only patch, scoped narrowly to the specific bug that
surfaced it. Forcing `condition_setter` into a single `_NEED_TARGET_ROLES` row. Reusing
`CHARGE_INSTANT_WEATHER`'s move-to-weather table directly inside `query_support_needs` rather
than routing through the mechanism-evidence layer already built for this purpose.

**Why:** The gap was real and predated this fix by two days — `query_support_needs` had a
self-documented comment ("condition_setter is ability-only today... re-check if move-derived
weather needs are ever added") anticipating exactly this scenario, which the conditional-
mechanics work's Electro Shot→Rain emission then triggered without anyone closing the loop.
Scoping the fix to Rain only would have left the identical gap open for Sun/Sand/Snow the
moment any comparable move-derived mechanism needed it — confirmed as a real, not
hypothetical, risk by testing Sun via Solar Beam/Blaze Charizard specifically (not
Chlorophyll, which would only re-test the already-working ability path) as part of this same
fix. A single `_NEED_TARGET_ROLES` row was rejected because the category genuinely maps to
four different roles depending on the resolved weather — collapsing that into a 1:1 structure
would have required a different kind of workaround, not a simplification. Re-scanning
`CHARGE_INSTANT_WEATHER` directly inside `query_support_needs` was rejected in favor of
routing through the same mechanism-evidence layer already used elsewhere, keeping one source
of truth for "does this anchor need this condition" rather than two independently-maintained
interpretations.

**Status:** Implemented and verified. Dedup against `multi_locked`'s gap-need generation
confirmed via a dedicated regression test
(`test_gap_need_deduped_when_anchored_rain_already_present`, mirroring the original Trick Room
dedup fix) rather than assumed to generalize from the existing trigger-string-equality
mechanism. 792 tests passing (up from 786), 6 skipped, matching the established baseline.
**Confirmed still incomplete at the presentation layer, not silently treated as fully
closed:** `_format_candidate_selection` has no handling for `UnresolvedTargetRoleDecision`
(only reads `.role_id`, which that type doesn't have), so an ambiguous candidate carrying Rain
as a real possibility currently renders with no role label at all — filed as its own explicit
follow-up, not resolved by this amendment. `_sort_annotated`'s need-overlap ranking still
doesn't account for condition rarity, so a correctly-labeled rain-setter candidate can still
rank below multi-need Trick Room matches in the actual presented order — explicitly out of
scope for this fix, unchanged.

---

### ADR-024 Amendment 2026-08-26a — `_primary_function` vocabulary hole closed; consolidated into a shared role taxonomy

**Decision:** `_primary_function` (the classifier feeding `RoleShapeContext`'s `primary_function`
field) was a partial suffix heuristic — it recognized `role_id`s ending in `_attacker` plus a
small explicit offense set, and `_setter` plus a small explicit support set, silently mapping
everything else to `"unknown"`. A systematic sweep (30 anchor runs across 5 deliberately varied
archetypes — Trick Room-only, hyper offense, screens balance, mono-fire, tailwind offense —
explicitly avoiding this project's recurring Archaludon/Rain default) found this suppressed
every offense-universal need (`screens` want, `healing_cleric`'s universal path, `redirection`
soft-ask) for any anchor whose `role_id` didn't match the narrow pattern, and doubly excluded
`defensive_coverage` candidates whose `role_id` is bare `"support"`.

A full, verified enumeration of every real `role_id`-producing source (`classify_anchor_role`'s
priority chain: declared opaque string, Role Compendium exact hit, mechanism primary,
`infer_role` fallback, `"unresolved"`) found 40 distinct real ids in use, cross-checked against
live literals (`RoleArchetype`, `TargetRoleId`, all 15 `data/roles/*.json` files) rather than
assembled from what came up in discussion — matching this project's standing discipline after
prior incidents (Sand Force, the redirection candidate list) where a hardcoded list scoped to
conversation-mentioned cases missed a structurally identical one. `_sweeper`-suffixed ids
(`physical_sweeper`, `special_sweeper`) and bare `"support"` were the two patterns missing
generic coverage; `iron_defense_body_press` and `sleep_status_spreader` needed explicit
overrides (no suffix match). Consolidated into a new shared module,
`recommender/role_taxonomy.py` (`primary_function_for_role_id`, `normalize_role_id`), replacing
two independently-drifted hardcoded implementations — `anchor_roles._primary_function` and a
separate, inconsistent `_OFFENSE_ROLES` frozenset in `propose._default_item_candidates` (which
had the same `_attacker`-suffix-only gap, silently defaulting `physical_sweeper`/`special_sweeper`
anchors to the wrong tier-3 item default, Sitrus Berry-first instead of Life Orb-first).

**Important scoping clarification, worth stating plainly rather than leaving implicit:** the
`_sweeper` and coarse-`support` gap is not a moveset-classification bug. Verified directly
against `infer_role`'s real logic: it is a closed function that can only emit one of 14
`RoleArchetype` values, and no code path in it can produce `physical_sweeper`,
`special_sweeper`, or bare `support` — every `_attacker_role` return is constructed from real
move-category bias, not guessed. Those strings only ever enter the system through the
*declared* role path (`user_role`/`explicit_role`), which per ADR-024's original design accepts
any caller-supplied opaque string with no vocabulary validation. This fix makes declared-role
strings degrade gracefully when they resemble but don't exactly match the closed vocabulary's
naming — it does not change or improve `infer_role`'s real, moveset-derived classification,
which was already correct.

**`defensive_coverage`'s detection rate is unchanged on the sweep's own fixtures (1/30 → 1/33
after the sweep's `physical_sweeper_regression` fixture was added) — traced precisely, not
assumed.** The support-role anchors that gained a correct `primary_function` classification
(Klefki, Grimmsnarl, Incineroar) still fail `defensive_coverage`'s separate Def/SpD asymmetry
gate (their real ratios: 1.00–1.15, below the 1.5 threshold) — the semantic fix is real
(these anchors now correctly register as `"support"` rather than `"unknown"`, mattering for any
future asymmetric-bulk support case) but doesn't move this specific number on this specific
data.

**Alternatives considered:** deriving `primary_function` from Role Compendium category metadata
directly rather than continuing string-pattern matching. Rejected as YAGNI — 13 of 15 real
compendium categories already match the suffix rules, only 2 need explicit overrides, and the
fix adds a parametrized 40-id test plus a live glob-guard test (reading `data/roles/*.json`
directly, not a hardcoded snapshot) specifically to catch future staleness as new categories are
added, rather than trusting the string convention to hold forever unchecked.

**Also resolved in the same sweep, findings corrected rather than escalated:** the initial
discovery pass flagged a "`healing_cleric` satisfier/resolution gap" (Blissey, Clefairy,
Amoonguss, Comfey failing to match the satisfier move list). Checked directly against the real
Champions legality snapshot: all four are `tier: "Illegal"` — none are valid candidates
regardless of movepool, so their absence of Wish-family moves is moot, not a data or code gap.
The three legal species in the same probe (Incineroar, Toxapex, Whimsicott) genuinely lack any
satisfier move in real learnset data, which is correct, not a bug; Sinistcha and Clefable (the
two legal species that do carry a satisfier move) match correctly. **Downgraded from "likely
real gap" to "not supported" — the trigger side of `healing_cleric` was already correct (30/30
detections in the original sweep), and re-checking the satisfier side against real legality data
found no gap once illegal species were excluded from the probe set.**

**`condition_beneficiary`'s terrain/type-general-middle-tier gap** — confirmed by the same
sweep (Rillaboom Grassy Surge produces no beneficiary-path activity; `provided_weather_conditions`
is weather-only) but not newly discovered or changed by it. Remains a separate, already-tracked
open item.

**Status:** Implemented and verified. Branch `cursor/primary-function-vocabulary-fix`, merged
into `main`. Named validation suite: 121 passed. Full suite green: 1453 passed, 13 skipped.
New tests: a 40-id parametrized table (independently hand-written expected values, not derived
by calling the implementation on itself), a live compendium glob-guard, declared-string
integration tests for `physical_sweeper` and coarse `support` through the real `classify_anchor_role`
path, and a deprecated-alias normalization test. Sweep re-run post-fix (33 runs) confirms
`physical_sweeper` (Dragapult) now correctly resolves `primary: "offense"` and gains
`healing_cleric`/`redirection`/`screens`/`tailwind`.

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

## ADR-026: Multi-locked candidate discovery/ranking — team-portfolio evidence aggregation,
not a generalized single-anchor chain

**Decision:** For a team with 2+ fully locked members and an open slot, candidate discovery
and ranking is a genuinely different operation from `single_locked`'s anchor-relative chain
(Track C) — not a parameterized generalization of it. `multi_locked` collects evidence
independently from every locked anchor before any global cut, derives a team-wide threat
objective from coverage/SPOF gaps rather than concatenating per-anchor threat searches, adds
`shared_teammates` as a bounded candidate-generation source, and ranks candidates through a
severity-aware staged comparison rather than a single scalar or opaque weighted sum.

Supporting design, each load-bearing to this decision rather than separable from it:

- **Aggregation without anchor privilege.** Every locked anchor runs through the same
  `resolve_anchor_build -> classify_anchor_role -> derive_role_shape_context ->
  query_support_needs` sequence, with no "primary" or first-listed anchor. Cross-anchor
  breadth is measured by distinct anchors/needs supported, never raw evidence-row count —
  otherwise a verbose anchor emitting several correlated needs could dominate ranking despite
  every anchor being queried exactly once.
- **Team threat objective, not per-anchor concatenation.** The objective is built from
  coverage rows with no covering slot plus threats named in SPOF findings, deduplicated by
  normalized identity — then the full candidate search runs against that objective, with the
  tractable cut happening only after every candidate is evaluated against the complete
  objective. Independently querying `query_threat_counters` per anchor and merging top-N
  outputs was rejected: each invocation would locally cut before the team could observe
  cross-anchor value, preserving the same anchor-privilege problem the aggregation is meant
  to eliminate.
- **`shared_teammates` as a candidate source, not merely a ranking modifier.** A
  modifier-only design couldn't surface a shared teammate absent from every threat/support
  branch, and the original flow-discovery report explicitly called for teammate/cohesion
  candidates as their own evidence source. Bounded by design: only exact-attribution rows
  admit a candidate; unavailable, empty, or ambiguous evidence adds no candidate and no
  penalty; a shared-only candidate receives no automatic rank boost and must still clear
  every other ranking stage.
- **Severity-aware staged ranking, resolved through two rounds of correction, not the
  original design's binary ordering.** Team-threat-improvement was decomposed into severity
  bands (decisive/costly/toss-up/conditional/SPOF) with composition fit inserted between the
  high- and low-severity bands — so a severe composition problem (e.g. a second redundant
  Rain attacker) can outrank a *minor* threat gain, while a decisive or costly verified
  closure still wins even against a compositionally redundant candidate. `clean_kill` and
  `intentional_non_ko_answer` are treated as equally valid closures at matching severity,
  directly per ADR-015's own text ("a legitimate, deliberately-built answer type, not a
  lesser result") — verified this doesn't conflict with `query_threat_counters`'s existing
  `verified_score` scalar, since that scalar's own arithmetic doesn't actually implement
  strict outcome-then-severity ordering (a costly clean kill ties a decisive non-KO; a
  toss-up clean kill scores below a decisive non-KO) — it's a caller-local heuristic for
  single-matchup scoring, not a repository-wide invariant this task was obligated to match.
- **Usage as evidence-confidence, not popularity, per ADR-015.** A standalone
  usage-popularity tiebreak (the original design document's stage 7) was removed as a direct
  instance of what ADR-015 Amendment 2026-07-29a already prohibits — "real teams do X" as
  quality evidence independent of anything verified. `usage_backed` survives as one tier of
  `CandidateEvidence.basis`, but only when tied to a specific confirmed claim
  (`commitment_pct` — does this species carry this specific move, not how popular the
  species is overall) — a different, permitted claim under the same ADR's "discovery and
  legality confirmation" carve-out, and the same commitment metric this project has depended
  on since its original `commitment_rate` sourcing decision. Threat-candidate evidence
  retains `usage_rank`, reversed after being incorrectly removed during implementation —
  confirmed via prior-session history as deliberate, load-bearing design (`get_relevant_
  threats`' usage-based prioritization and `query_threat_counters`' deterministic
  merge-tiebreak), not an incidental detail available for removal.
- **`TargetRoleDecision` stays candidate-specific, never a context-level default.** A
  candidate satisfying incompatible support roles gets an explicit `UnresolvedTargetRoleDecision`
  rather than a forced pick; threat-only and shared-only candidates retain no target role.
  Same principle Track C already established for threat-only alternatives, extended to the
  multi-anchor case.
- **Calc failure is structurally honest, never silently degraded.** Transport failures
  (`CalcClientError`) and protocol/evidence failures on partial batches (`MatchupEvidenceError`,
  covering malformed batches, wrong result counts, and per-row error responses previously at
  risk of being silently treated as `no_answer`) both map to a structured
  `CandidateDiscoveryError` and stop discovery without presenting a partial or falsely-
  authoritative ranking. No static/legacy matchup fallback runs in this path.

**Alternatives considered:** Generalize Track C directly by looping its single-anchor chain
over each locked member and merging outputs afterward. Use a single opaque weighted-sum
ranking score instead of staged lexicographic comparison. Reuse `query_threat_counters`'s
existing `verified_score` scalar directly for portfolio-level ranking. Keep the original
design document's strict team-threat-improvement-before-composition-fit ordering.

**Why:** A naive per-anchor loop-and-merge would still let whichever anchor's local search
runs first (or has more emitted needs) dominate the combined pool — the exact anchor-privilege
failure this design exists to eliminate, just relocated rather than fixed. An opaque weighted
sum would hide exactly the kind of policy question this task had to resolve explicitly
multiple times (composition-vs-threat-severity precedence, outcome-vs-severity precedence) —
staged comparison keeps each policy decision auditable and independently testable, consistent
with this project's standing preference for documented, defensible tiered/lexicographic rules
over unexplained scalar combinations (the same discipline behind `rank_and_cut`'s tiered
admission and the compendium-priority leading-key correction). `verified_score` doesn't
transfer to portfolio ranking because it scores one candidate against one matchup, while
multi-locked counts verified closures across an entire team-threat objective — there's no
single scalar to reuse, and the aggregation itself is the actual missing capability.

**Status:** Implemented and verified (513 tests passing, up from 385 at the start of this
session's slot-fill arc; 5 skipped, unrelated live-service tests). Went through two
substantive correction rounds during design/plan review (ranking-order decomposition;
import-cycle verification gate that caught a real second-order cycle and a LangGraph
`get_type_hints` runtime requirement) and two real corrections during confirmation
(usage-evidence conflation between threat and support candidates; a near-miss removal of
deliberate prior-session `usage_rank` design, reversed after direct verification). Deliberately
deferred, not oversights: condition-resilience assessment; selected-four/bring-four modeling;
canonical name/form resolution; calc-unavailable static fallback; breadth-versus-severity
aggregate policy (one decisive closure currently outranks arbitrarily many costly closures,
explicitly left as a separate, unresolved policy question); target-role vocabulary completion
beyond shipped support-derived cases.

---

### ADR-026 — Amendment 2026-08-10a

**Breadth-vs-severity residual risk investigated and closed as intentional design, not left
open.**

**Decision:** The strict lexicographic ordering of `uncovered_verified_decisive_count` before
`uncovered_verified_costly_count` in `rank_multi_locked_candidates`' ranking key — meaning any
candidate with even one more decisive closure outranks another candidate regardless of how
many costly closures that candidate answers — is confirmed as intentional, correctly-designed
behavior. Reclassified from open residual risk to documented policy.

**Why this doesn't need a fix:** verified the "arbitrarily many costly closures" framing
overstated the real scenario. The team-threat objective is bounded (~50 ladder species,
~79 form-level threats in the current snapshot), and a live probe found realistic contested
costly deltas are single-digit (a strong generalist reached roughly 5-7 costly closures
against the largest usable objectives; smaller objectives typically show 0-1). No shipped
test, role-play transcript, or prior session ever reproduced this as an actual ranking
mistake — it was flagged out of appropriate caution when multi-locked shipped, never observed
to matter.

Confirmed this is the same underlying policy already validated by the composition-fit
severity-band work, not a separate problem needing its own answer: that work established
"a genuine, verified closure beats softening many things weakly" (decisive/costly verified
uncovered closures outrank composition; composition outranks toss-up/conditional/SPOF
improvements). Decisive-before-costly is the identical principle applied one level finer,
inside the already-verified-closure band — preferring one cleaner win (≥50% HP remaining)
over several weaker ones (20-50% HP remaining) is consistent with, not a departure from, the
tuple's existing design.

**Alternative considered and rejected:** introducing a breadth threshold (e.g., some N costly
closures collectively outweighing 1 decisive closure). Rejected because it would have been
calibrated against no real data and no observed failure — inventing an arbitrary threshold to
guard against a scenario that's never actually occurred would trade one undocumented arbitrary
property for a different, equally arbitrary one, with no evidence either is more correct.

**Status:** Closed, not deferred. No ranking-stage rework performed; no interaction with
`MIN_WANTED_DEPENDENTS_FOR_ESSENTIAL`, `_preferred_setter_direction`, or the outcome/severity
reconciliation from ADR-023 Amendment 2026-08-08b. **Explicit revisit condition, not
indefinite closure:** reopen only if a concrete session demonstrates a real case where a
specialist's single decisive closure wrongly buries a clearly better multi-costly generalist
candidate — at that point there would finally be real calibration data to design against,
which is exactly what was missing to justify a change now.

---

### ADR-026 — Amendment 2026-08-17a: essential/missing-provider gap-fill gets its own leading rank-key field

**Decision:** `AnnotatedCandidate` now carries `fills_essential_gap` as an explicit field
(previously computed correctly by `_candidate_fills_condition_gap` inside
`annotate_composition_impact` but only folded into the coarse `composition_fit` bucket and
discarded). `_rank_key` places `int(fills_essential_gap)` as the leading field of its sort
tuple — ahead of every threat-coverage count field — so a candidate that fills an essential,
missing-provider (or single-provider-SPOF) condition gap always outranks any threat-coverage
candidate, full stop.

**Why:** Confirmed live and reproduced against real repo code, not inferred: a team whose locked
anchor's real kit created a genuine essential Rain dependency (Archaludon + Electro Shot) produced
zero Rain-setter candidates anywhere in the ranked pool once real calc-verified threat coverage
was available — every candidate answering at least one verified threat (76 hits, in the reproduced
case) unconditionally outranked the one candidate answering the team's actual essential gap (0
threat hits), because `_rank_key`'s tuple had no field representing "this candidate is the answer
to an essential team need" at all. The nearest existing signal, `composition_fit`, both fires for
several unrelated reasons (any anchored need, corrected attacker-type skew, missing primary
function) and — independently — sits after every threat-coverage count in the sort tuple
regardless, so it could never have overridden this even undiluted.

This closes the "condition-resilience assessment" gap ADR-026's original Status section explicitly
deferred. ADR-028 later implemented condition-resilience *classification*; this amendment is the
missing wire from that classification into `multi_locked` ranking, not a duplicate of ADR-028's
work.

**Alternatives considered and rejected:** A floor-guarantee reserving a slot in the ranked pool
for at least one essential gap-filler, without reordering. Rejected because the CLI only ever
surfaces the top 3 candidates (`pick_default_and_alternatives`); guaranteeing inclusion in the
larger ranked-and-cut pool (`n=10`) wouldn't guarantee visibility in what the user actually sees —
a "real" fix under this design would still have needed to force the candidate near the top of the
displayed slice, ending up functionally equivalent to reordering, just split across two mechanisms
instead of one. A middle position (outranking only the softer threat tiers while still losing to a
decisive verified closure) was also considered; rejected in favor of unconditional priority, on the
reasoning that "essential" is already the strictest tier this system recognizes (ADR-028: a single
`needed`-importance mechanism from one locked member is sufficient on its own, regardless of how
many other members want it) — a team that cannot function as built without a given condition
shouldn't have that need traded off against marginal threat-coverage gains elsewhere.

**Status:** Implemented and merged. Two new regression tests added directly targeting this
rank-key change; two existing tests extended with direct `fills_essential_gap` assertions
confirming end-to-end population through `annotate_composition_impact`. Full suite: 1125 passed,
8 skipped (skip count/reasons unchanged from established baseline). Implemented directly (Cursor
unavailable), disclosed in the commit message; the one real design decision (priority ordering)
was explicitly confirmed live with Vu before implementation, not assumed.

**Deliberately not addressed here, tracked separately:** a distinct display-layer bug found during
the same investigation — `present_text.py`'s `_format_candidate_selection` reads a candidate's
first evidence-tuple item rather than its best evidence, which can show stale/misleading
confidence text for a correctly-ranked candidate. Does not affect ranking correctness, only
display text; left open.

---

### ADR-026 — Amendment 2026-08-20a

**select_diverse_candidates (ADR-033) supersedes this ADR's severity-staged ranking for the
default/alternatives-selection step specifically — the underlying evidence-aggregation and
`rank_multi_locked_candidates`/`_rank_key` machinery this ADR describes is otherwise
unchanged.**

Confirmed via extensive live testing across an entire session (not a design preference decided
up front) that the severity-staged single ranking this ADR establishes, while correct for
discovery/aggregation, could not represent three genuinely different kinds of candidate value
(threat-coverage, support-needs, condition-benefit) in one scalar/tuple without one kind
systematically crowding out the others. See ADR-033 for the full replacement design.

`rank_multi_locked_candidates` itself is untouched and still used by
`material_completion_preferences` (comparing attacker/support/balanced orderings) — a
genuinely different use case where the single-ranking approach remains the right tool. Only
`discover_multi_locked`'s call feeding `present_candidates`'s selection step was changed, to
`rank_multi_locked_by_category` (ADR-033).

**Status:** `select_diverse_candidates`'s architecture (ADR-033) is the current, correct design
for candidate presentation. This ADR's discovery/aggregation decisions remain in effect
unchanged.

---

## ADR-027: Empty-team bootstrap — LLM-backed free-form extraction behind a
deterministic-verification boundary; ADR-013's first real runtime consumer

**Decision:** For the `empty` team phase's combined direction/available-pool intake, use an
injected, model-agnostic LLM parser (`bootstrap_intake_parser`) to extract a draft payload
(`direction_text`, `anchor_text`, `pool_entries`, `delegated`, optional `ownership_mode`) from
free-form user text — the only pending-presentation kind in the graph that does this. The
other three existing closed-set kinds (candidate selection, full-build confirmation,
completion preference) remain fully deterministic, since they match against a small displayed
option set rather than open-ended text. Everything the LLM extracts is treated strictly as a
draft: legality, exact species identity, ownership, strategic-role evidence, and ranking all
remain deterministic and tool-verified downstream, with no extracted field trusted as fact on
its own.

Confirmed via direct investigation, not assumed: this is genuinely the first place the
runtime graph invokes a live LLM at all. Two candidate "existing seams" were checked and
ruled out — `classify_pending` is fully deterministic (tests monkeypatch it), and
`KitInteractionProposer` is an unused-at-runtime callable type with no live caller. No
prior-existing provider abstraction was bypassed or duplicated.

**Failure handling is fail-closed and non-mutating.** A missing parser, provider exception,
or malformed/inconsistent model output retains the intake presentation unchanged, mutates no
pool or bootstrap state, and surfaces an observable bootstrap-specific error — verified by a
named test asserting the full unchanged-state list (presentation, pool, completion flag,
saved response, unresolved diagnostics) after each of the three failure modes.

**Deterministic mapping stays strictly separate from extraction, at two levels:**
- Direction text extracted by the LLM is matched against a small, explicit, longest-match-first
  phrase table mapping to known strategic labels (weather names, "X offense," Redirection/
  Follow Me/Rage Powder, Trick Room setter/sweeper, Tailwind, Swords Dance, Nasty Plot,
  fast/bulky attacker, fast/bulky pivot) — deterministic pattern matching, not a second LLM
  judgment call. An unmappable or opaque direction re-prompts with clarification rather than
  guessing, verified by a test that directly patches `_pick_role` and asserts it is never
  called — a structural guard against the exact failure this whole session's slot-fill arc
  traces back to (a wrongly-guessed role shape producing fabricated downstream needs).
- `TargetRoleDecision` construction itself has two explicit, ordered evidence tiers: Track 1's
  exact strategic-evidence producer (mechanism or Compendium evidence, high confidence) runs
  first and wins whenever it returns a result; a coarse `kit_role`-to-`TargetRoleId` match
  (medium confidence) only fires when the exact producer returns `None`. A third,
  mechanism-based fallback was proposed during plan review and explicitly removed for
  duplicating the exact producer's own logic rather than kept as harmless redundancy.

**Alternatives considered:** A deterministic bounded grammar for the combined intake response.
Requiring callers to submit an already-structured payload instead of free text. Reusing
`_pick_role`'s existing coarse-fallback path for unmapped/ambiguous directions instead of a
dedicated re-prompt.

**Why:** A bounded grammar would need to already solve species-name recognition from free
text to handle the pool half of the intake — functionally most of canonical name resolution,
which is separately and deliberately deferred. A structured-payload requirement would abandon
the actual point of a combined intake (respond naturally in one message) rather than solve the
parsing problem. Reusing `_pick_role`'s fallback for unmapped directions was rejected because
it's the generic, low-confidence default this entire task exists to route around — bootstrap
should surface "I couldn't map that" rather than silently substitute a coarse guess.

**Status:** Implemented in two sequential tracks. **Track 1** (prerequisite, target-role
vocabulary expansion): added `rain_setter`/`sun_setter`/`sand_setter`/`snow_setter`/
`redirection`/`swords_dance_attacker`/`nasty_plot_attacker` to `TargetRoleId`'s domain
(previously seven values, now fourteen) plus the exact-evidence producer
(`target_role_from_strategic_evidence`), justified by direct measurement — roughly one-third
of realistic bootstrap-presented directions would otherwise dead-end on selection,
disproportionately the mechanically-distinct options the alternative-diversity rule is
specifically designed to surface. Verified via four real-species injection tests (Sinistcha/
redirection, Pelipper/rain_setter, Tyranitar/sand_setter, Gholdengo/nasty_plot_attacker,
each reaching a complete `ProvisionalSlot`) and an all-14-role round-trip test through
selection/refinement/commit. **Track 2** (full bootstrap implementation): combined direction+
pool intake, exact-ID-only pool validation with unresolved labels surfaced (never guessed —
`Eternal Floette` stays unresolved, `Floette-Eternal` is accepted), ownership-mode derivation
distinguishing default-`off` from user-requested-`off`, deterministic diverse direction
discovery (`query_by_usage` seed set -> `resolve_anchor_build`/`classify_anchor_role` ->
Track 1's evidence tiers), four-way separated `CandidateEvidence` provenance
(usage/ownership/compendium/policy, never collapsed), and full reuse of the existing
provisional-build/confirmation/atomic-commit terminal lifecycle — no bootstrap-specific commit
path. `_BASIS_RANK` extended additively with `ownership_backed` sharing rank 0 with
`synthesized` (ownership preference already has its own dedicated mechanism via `rank_and_cut`,
so a separate evidence-quality tier would double-count the same signal) — confirmed via
explicit before/after diff that no existing key's rank moved and no existing rank assertion
needed loosening.

578 tests passing (up from 513 at the start of this task, 385 at the start of this session's
whole slot-fill arc), 6 skipped (5 pre-existing live-calc-service skips, 1 new opt-in Ollama
live smoke test — accounted for exactly, not assumed). Full Python and TypeScript suites
clean; `git diff --check` clean; diff scope confirmed limited to the expected file list.

**Deliberately deferred, tracked as separate future scope:** canonical name/form resolution
beyond exact-ID acceptance; condition-resilience assessment; selected-four modeling; general
first-turn intent classification beyond the `bootstrap_intake` response specifically; further
target-role taxonomy work beyond Track 1's fourteen values; low-data Compendium member build
synthesis (confirmed independent of the vocabulary gap, separately reported).

---

### ADR-027 — Amendment 2026-08-10a

**`TargetRoleId` Fork A: absorb the `RoleArchetype` vocabulary wholesale, replace the interim
collapsing map with mechanism-resolved speed-control identity, and fix no-provider bootstrap
UX.**

**Decision:** Expand `TargetRoleId` from 14 to 25 values by absorbing every `RoleArchetype`
identity label (all nine fine-grained `{fast,standard,bulky} × {physical,special,mixed}`
attacker combinations, `support_speed_control`, `screens_support`), while keeping the
pre-existing umbrella values (`fast_attacker`, `bulky_attacker`, weather/setup setters,
pivots) unchanged. Delete the interim `_KIT_ROLE_TO_TARGET` collapsing map introduced during
initial CLI testing; kit-role promotion is now identity membership via
`bootstrap_kit_role_policy`, applied only after Track 1's strategic-evidence resolution fails
to produce a decision.

Speed-control resolution is now mechanism-driven rather than defaulted: added
`"tailwindsetter": "tailwind_setter"` to `REVIEWED_STRATEGIC_TARGET_ROLES` (previously
missing entirely — the actual root cause of Whimsicott-shaped anchors falling through to kit
collapse regardless of the interim map), and added a `_speed_control_pre_pass` that resolves
present Tailwind/Trick Room mechanisms: two or more distinct speed-control roles present
produces `UnresolvedTargetRoleDecision(reason="ambiguous_speed_control")` (a clarification
prompt on an explicit anchor, silent exclusion for a non-explicit alternative); exactly one
resolves to that role at high confidence; zero falls through to kit identity. The pre-pass is
deliberately deferred until *after* the remaining non-speed Track 1 strategic loop runs, not
before — this was corrected during implementation specifically to prevent Pelipper's
incidental Tailwind from short-circuiting its established primary `rain_setter` identity
before Rain's own strategic evidence gets a chance to resolve first.

Bootstrap's no-provider UX is fixed: when `bootstrap_intake_error` is
`BOOTSTRAP_PARSER_NOT_CONFIGURED`, presentation omits the generic `Didn't catch that.` prefix
and surfaces an actionable `BOOTSTRAP_PARSER_FIX_HINT` (also appended to startup provider
warnings) — replacing the prior behavior where every reply, regardless of content, produced
an identical unhelpful message and re-prompted as if retrying could work when it fundamentally
couldn't without a configured parser.

**Alternatives considered:** keeping the interim `_KIT_ROLE_TO_TARGET` collapsing map as the
permanent solution. Running the speed-control pre-pass before the remaining Track 1 strategic
loop. Silently picking one speed-control role when an anchor has both Tailwind and Trick Room
mechanisms present, rather than surfacing ambiguity.

**Why:** The interim map was found to be actively wrong in two specific, verified ways — not
just coarse. `standard_{physical,special,mixed}_attacker → bulky_attacker` asserted a
bulky-item-driven claim the anchor's classification never made (`standard_*` specifically
means no fast/bulky signal was detected at all). `support_speed_control → tailwind_setter`
picked one specific mechanism out of a category explicitly designed to need further
resolution — the same mistake the original `_pick_role` redesign had already found and fixed
once, reintroduced by a different path. Running the pre-pass before the remaining strategic
loop was rejected after discovering it would have broken Pelipper's established `rain_setter`
identity, which every worked example this project has used all session depends on — deferring
it until after non-speed evidence resolves first prevents an incidental secondary mechanism
from stealing precedence over a real primary one. Silent ambiguity resolution was rejected
because Tailwind and Trick Room are both real, independently self-supplied mechanisms with no
principled way to prefer one over the other absent stronger evidence — surfacing the
ambiguity (clarification on an explicit anchor, exclusion for an alternative) is consistent
with this project's standing "don't guess when evidence doesn't decide" discipline.

**Status:** Implemented and verified. Named tests confirm the Pelipper-ordering fix at the
bootstrap `_target_role` layer specifically (`test_pelipper_prefers_rain_over_incidental_
tailwind`, distinct from and not to be conflated with the pre-existing anchor-classification
contract `test_pelipper_primary_rain_secondary_tailwind_without_setup`, which covers a
different layer — primary/secondary `AnchorRoleDecision`, not open-slot `TargetRoleDecision`).
TW+TR ambiguity confirmed via `test_tw_and_tr_mechanisms_yield_unresolved_speed_control` and
`test_explicit_anchor_ambiguous_speed_control_asks_clarification`. Explicit-anchor survival
under a mismatched direction filter confirmed via
`test_explicit_anchor_survives_mismatched_direction_filter` (Archaludon correctly surfaces as
`bulky_special_attacker` under a Rain-direction payload, with a `rain_setter`-class
alternative like Pelipper still present rather than the anchor being dropped). 778 tests
passing at the close of this arc. Deliberately deferred: `_DIRECTION_PHRASES` expansion for
the newly-absorbed fine-grained labels; `role_spread`/`_ROLE_PREF_MOVES` coverage gaps for
weather/setup `TargetRoleId`s (pre-existing, unchanged by this amendment); deleting the
`RoleArchetype` type itself (still needed as the underlying classification vocabulary,
`TargetRoleId` absorption is additive, not a replacement); canonical name/form resolution.

---

## ADR-028: Condition classification and redundancy checks — generation-primary signal with
a scoped composition_fit override, not a new ranking stage

**Decision:** For a locked team with 2+ members, classify each tracked condition (Rain, Sun,
Sand, Snow, Trick Room, Tailwind) as `essential`/`preferred`/`optional` based on how many
locked members actually depend on it (not on whether it's merely present), and compute
provider cardinality (0/1/2+) independent of contest reliability. Publish as a team-wide
signal alongside coverage/SPOF/`shared_teammates` in `multi_locked`. Consumed two ways:
generation-primary (a gapped essential/preferred condition generates backup-setter candidates
through existing need-resolution paths — no new discovery mechanism) and as a scoped override
inside `annotate_composition_impact`, which prevents a gap-filling candidate from being
demoted as `duplicative`/`severe_duplication` for the specific condition it's closing, while
leaving unrelated duplication demoted as before. No new lexicographic ranking stage.

Supporting design: a `condition:{Canonical}` evidence tag stamped at mechanism-emission time
so classification never re-scans kits or re-imports move/ability tables to infer a condition
— emission and consumption share one source of truth. Two threshold-like policies
(`MIN_WANTED_DEPENDENTS_FOR_ESSENTIAL`, the `wanted×2` essential trigger; `_preferred_
setter_direction`, the softer "team is clearly on this plan" heuristic) shipped as named,
calibratable constants/functions with dedicated tests rather than silently baked in. Gap-need
generation deduplicates against needs already surfaced through each anchor's own
`query_support_needs` resolution, firing independently only for the aggregate-only case
(`wanted×2 -> essential`) that no single anchor's own ask would ever surface.

**Alternatives considered:** a new ranking-tuple stage for condition resilience, parallel to
the existing severity bands. Ranking-only consumption (annotate existing candidates, generate
nothing new). An unconditional `composition_fit` exemption for any `*_setter`-role candidate.

**Why:** `composition_fit` would have actively fought this feature if left unconnected — a
second Rain setter next to a `provider_count=1` essential Rain anchor repeats
`Drizzle`/`rain_setter` mechanics and would be ranked `duplicative` by the existing logic,
exactly in the scenario where it's the real fix for a genuine gap. Generating a backup-setter
candidate to close a resilience gap and then demoting it for "duplicating" the missing
capability would have shipped as contradictory, self-defeating behavior — found and designed
around before implementation. A new ranking stage was rejected because the fix belongs at the
point where duplication gets judged, not as a parallel signal competing for tuple position.
Ranking-only consumption was rejected because it can't surface a candidate no other branch
would generate. The unconditional exemption was rejected because it would blanket-protect
setter-type candidates regardless of whether they're actually closing a real gap — the scoped
version (`_candidate_fills_condition_gap`) was verified via a dedicated test proving unrelated
duplication is still correctly demoted.

**Status:** Implemented and verified end-to-end — a real `discover_multi_locked` run
(`test_discover_multi_locked_publishes_resilience_and_keeps_backup_rain_setter_complementary`)
confirmed the same `assess_condition_resilience` object published to state is what the
override actually consumes, not a manually reconstructed report. A real need-double-counting
bug was caught and fixed during plan review before implementation — a gap-driven need for a
condition already surfaced through an anchor's own per-anchor ask would have inflated
`distinct_needs` for any candidate satisfying both. 609 tests passing at ship. Deliberately
deferred: condition-independent fallback-mode demonstration (e.g. Icy Wind substituting for
Trick Room); weather-war contest reliability (who wins when two automatic setters contest, as
distinct from provider count); terrains as tracked conditions; Protosynthesis's Booster Energy
exemption (v1 always emits Sun-wanted regardless of item).

---

### ADR-028 — Amendment 2026-08-20a

**`fills_essential_gap` split into two distinct signals; ability-based condition-beneficiary
evidence confidence corrected; a real weather-conflict and an already-provided-need bug fixed.**

**`_candidate_fills_condition_gap` previously collapsed two genuinely different situations
into one top-priority boolean:** a candidate closing a genuinely missing provider gap
(`missing_provider`), and a candidate merely adding backup depth behind an existing
single-point-of-failure provider (`single_provider_spof`). Split into
`fills_essential_gap` (missing provider, unconditional top priority — unchanged) and the new
`fills_spof_backup_gap` (SPOF backup, real but deliberately lower priority, placed after
evidence quality in the ranking tuple) — confirmed live this was letting a mere backup
candidate outrank a genuinely stronger, higher-evidence-quality candidate that didn't happen
to touch the gapped condition at all.

**Ability-based condition-beneficiary evidence (`resolve_condition_beneficiaries`) was
hardcoded to `confidence="low"` regardless of match strength** — backwards from this project's
specificity-spectrum framework, since an innate ability directly interacting with a locked
condition (e.g. Swift Swim under Rain) is the most mechanically certain evidence tier
available, with none of the "might not actually run this" ambiguity a move-commitment check
has. Corrected to `confidence="high"`. Move-based condition-beneficiary matches are unaffected
and correctly retain usage-commitment-derived confidence, since that asymmetry (innate ability
vs. a move a species merely can learn) is real, not an inconsistency to unify away.

**Weather-conflict deprioritization confirmed and extended:** a support-need candidate whose
only satisfying move hard-requires a weather the team's already-locked weather conflicts with
(confirmed live: Abomasnow's Aurora Veil requiring Snow on a Rain team, matched via both the
raw-move and compendium evidence-tag formats, which were confirmed to differ) is downgraded,
not excluded — it may still be the least-bad option if nothing better exists.

**A tailwind-already-provided bug fixed:** a locked anchor's own, legitimately-triggered
tailwind support-need (a real speed-tier trigger, not a false generation) was still being
surfaced as unmet even when a different locked teammate already provides Tailwind — fixed via
a new `provided_conditions()` check filtering already-satisfied needs (tailwind/trick_room)
out of `anchored_needs` before candidate generation.

**Status:** All four fixes implemented and verified, each with dedicated regression tests
confirming the specific real scenario that motivated it, not just the general mechanism.

---

### ADR-028 — Amendment 2026-08-20b

**Mega-form retargeting (ADR-034) is also load-bearing for condition-beneficiary discovery,
not just general threat-counter discovery.**

Confirmed live: Swampert-Mega's real Swift Swim match under a locked Rain team was the
motivating case for both the confidence fix (Amendment 2026-08-20a) and for discovering
ADR-034's mega-form-identity gap in the first place — the two fixes are independent but
compound: `resolve_condition_beneficiaries`' own species-lookup logic
(`_species_with_abilities`) was confirmed to correctly find Swampert-Mega directly (it queries
the legality snapshot, not the affected in-game usage dataset), but `query_counters`
(consulted separately for Category A threat-coverage on the same candidate) previously would
have surfaced the base form instead. ADR-034's fix resolves this for both paths from one
underlying correction.

**Status:** No new code from this amendment — documents a cross-ADR dependency that wasn't
obvious until both investigations converged on the same live scenario.

---

### ADR-028 — Amendment 2026-08-21a

**`gap_support_needs` now fires only for `gap == "missing_provider"`, never
`single_provider_spof` — the dedup check it relied on was structurally
unable to see coverage for exactly the case it mattered most.**

Confirmed live: Whimsicott and Aerodactyl kept surfacing as compendium-backed
`tailwind_setter` support/utility picks turn after turn, and
Farigiraf/Aromatisse/Audino/Audino-Mega as `trick_room_setter` picks, despite
Pelipper and Sinistcha already providing those conditions. Root cause: inside
`merge_multi_locked_candidates`, the already-provided filter (Amendment
2026-08-20a) strips satisfied tailwind/trick_room needs out of
`anchored_needs` *before* that same, now-filtered tuple is passed into
`gap_support_needs` as `existing_needs`. `gap_support_needs`'
`_condition_already_covered` check looks for coverage evidence in exactly
that tuple — so once the real fix stripped it, the second function could
never see it, and re-emitted a full-strength need for the
`single_provider_spof` case every time, indistinguishable from a genuinely
missing provider, routed through the same `_compendium_roles_for_need`
primary-role Compendium lookup.

The original ADR-028 text already states the intended design — gap-need
generation was supposed to "deduplicate against needs already surfaced
through each anchor's own `query_support_needs` resolution, firing
independently only for the aggregate-only case." This amendment doesn't
change that intent; it corrects the implementation to actually match it, by
removing `single_provider_spof` from `gap_support_needs`' scope entirely
rather than depending on a dedup check that can't reliably tell "genuinely
missing" from "already covered, backup would be nice" once the coverage
signal has been deliberately removed upstream.

**Why exclusion, not a better dedup check:** a real team never wants a
second *primary* setter for a condition it already has one of — confirmed
directly against real team-building practice (a second Rain/Tailwind/Trick-
Room specialist competes for a roster slot the same team never spends twice
on the same primary job; any real "backup" value comes from a Pokémon
chosen for a *different* primary reason that happens to also carry the
condition, e.g. Sableye as a screens setter with incidental Rain support,
not a second Pelipper). `gap_support_needs`' mechanism — a direct
Role-Compendium primary-tier search — is structurally the wrong shape for
that secondary-provider case regardless of the dedup bug; legitimate backup
value is handled exclusively by `fills_spof_backup_gap` /
`_candidate_fills_condition_gap`, which annotates candidates already in the
pool for other reasons instead of searching for more specialists.

**Status:** Implemented and verified via PR #108 (merged, commit `656abb4`).
Confirmed via a test reproducing the exact live scenario (`condition_
resilience` wired through `merge_multi_locked_candidates` the same way
`discover_multi_locked` does) that fails on pre-fix code with Aerodactyl
surfacing via a spurious `tailwind` need, and passes after. 3 additional
direct unit tests on `gap_support_needs` for the tailwind/trick-room/weather
single-provider-spof cases. Screens and redirection are explicitly out of
scope — `TRACKED_CONDITIONS` has never covered them; whether/how to extend
provider-cardinality modeling to screens (which contest via Light Clay +
Item Clause exclusivity rather than a single automatic ability — confirmed
this isn't the "stacks freely" case it first looked like) is a separate,
undecided design question. 1272 tests passing (up from 1267), 8 skipped.

---

### ADR-028 — Amendment 2026-08-22a

**`resolve_condition_beneficiaries`'s ability-based confidence is now usage-aware,
correcting the gap Amendment 2026-08-20a's "high confidence" default left open.**

Amendment 2026-08-20a correctly fixed ability-based condition-beneficiary evidence from a
blanket `confidence="low"` to `confidence="high"`, reasoning that an innate ability is the
most mechanically certain evidence tier available. Confirmed live (2026-08-21) this default
had no upper bound: Castform (0.037% real Showdown usage, absent from the in-game top-50
snapshot entirely) received the identical "high confidence" as a genuinely strong pick,
purely from mechanically matching Forecast under Sun.

Two wrong approaches were caught during implementation, not shipped uncorrected. First,
`query_by_usage`'s `usage_rank`/`showdown_usage_pct` fields were tried as the signal —
confirmed directly that `query_by_usage` always returns `showdown_usage_pct=None`
regardless of real data; it never actually populates that field. Switched to querying
`ingame_species_map`/`showdown_species_map` directly. Second, a plain "usage present →
high, absent → low" rule was tried and broke the exact convention Amendment 2026-08-20a
established: it downgraded Swampert-Mega, which is absent from the in-game top-50 (the
same, separate data gap ADR-034 already covers — mega forms aren't in that dataset at all)
but has genuine, substantial 8.19% real Showdown usage. Absence from a known-incomplete
dataset is not evidence of poor quality.

**Final rule:** downgrade to `mechanical_only`/`low` only on *confirmed* negative evidence
— present in Showdown data, but below `move_narrowing.MIN_USAGE_PCT` (the same negligible-
usage floor already established elsewhere in this codebase). Real usage anywhere (in-game
top-50, or Showdown ≥ `MIN_USAGE_PCT`) → `usage_backed`/`high`. No data in either dataset →
`mechanical_only`/`high`, preserving Amendment 2026-08-20a's original default rather than
penalizing a data gap as a negative signal. Each species id is resolved to its lineage base
before the usage lookup — Castform's weather-formes each carry their own species id with no
usage entry of their own; only the base form has real data. This does not fix the separate,
still-open forme-duplication bug (they still surface as independent candidate rows) — it
only ensures whichever row is generated reads correct real usage data.

**Status:** Implemented and verified. Updated the prior pinning test into a real regression
test confirming Castform now gets `mechanical_only`/`low`; updated a second, pre-existing
test that had been asserting the old hardcoded behavior as correct; added a dedicated
sibling test confirming Swampert-Mega still correctly gets `usage_backed`/`high`, confirming
this is genuinely differentiated, not a blanket downgrade. Both new/updated tests confirmed
to fail on pre-fix code and pass after. 1285 passed, 8 skipped.

---

### ADR-028 — Amendment 2026-08-22b

**Battle-only transient formes now collapse to their base species in
`_species_with_abilities`, closing the forme-duplication gap flagged
alongside Amendment 2026-08-22a but not fixed there.**

Castform/Castform-Sunny/Castform-Rainy/Castform-Snowy surfaced as four
independent candidates from `resolve_condition_beneficiaries`, when a
player only ever picks base Castform — the weather-triggered formes are
automatic, exist only during live battle, and were never a real,
separate team-building choice.

A forme is now excluded when it has a real `base_species_id` (a genuine
forme relationship, not a standalone low-usage species) AND has zero
rows in both `ingame_species_map` and `showdown_species_map`. Verified
broadly, not just for Castform: every battle-only automatic forme
checked (Castform's three weather formes, Terapagos-Stellar,
Zygarde-Complete) has zero usage rows anywhere, since none can ever
appear in a real team export. Explicitly checked the adjacent case that
would break a naive "collapse every forme to its base" rule: Rotom's
appliance formes (Wash/Heat/Fan/Frost/Mow) are chosen at team-build time
and stay that way — confirmed every one has a real Showdown usage row,
so the exclusion correctly never fires for them.

Does not fix the display side of forme identity — a genuinely
low-usage-but-real species (base Castform itself, 0.037% Showdown usage)
must still appear on its own; the exclusion gates on being a forme
relationship, not on usage alone, confirmed by a dedicated test.

**Status:** Implemented and merged (PR #115). 3 new tests, each
confirmed to fail on pre-fix code and pass after. Full suite: 1295
passed, 8 skipped.

---

## ADR-029: Calc-unavailable static fallback — labeled degraded discovery for single_locked,
fail-closed unchanged for multi_locked and coverage/SPOF claims

**Decision:** Apply ADR-015's discovery-vs-ranking split to calc availability specifically.
`single_locked` degrades gracefully on calc failure — `query_threat_counters` returns a
structured `TeamThreatDiscovery(status="degraded", ...)` instead of letting the exception
propagate, with candidates built from already-computed static data
(`estimate_kind="static"`, `basis="mechanical_only"`, `confidence="low"`, explicit
degradation tokens, never `verified_score`). `multi_locked`'s authoritative team-threat
ranking and `complete`'s coverage/SPOF claims stay fail-closed without exception — static
axes cannot honestly populate ranking stages defined on verified closures.
`generate_team_review` no longer silently clears the graph-facing `candidate_discovery_error`
on failure; it now surfaces the real `calc_unavailable`/`calc_incomplete` distinction it
already computes internally.

Structural firewall, not just an evidence-string convention: `ThreatCounterCandidate.
estimate_kind` (`"verified"`/`"static"`) is a row-level type tag that `_sort_annotated` gates
on directly, so a static row cannot outrank a verified one even if a bug elsewhere left
`verified_score` nonzero on a static row — verified with an adversarial test constructing
exactly that falsified case. `candidate_discovery_error` stays set in both degraded branches
(empty result and presenting-candidates result) — not cleared when candidates are shown,
since clearing it there would have silently undermined the same honesty goal the
`generate_team_review` fix exists for.

**Alternatives considered:** letting static estimates feed `multi_locked`'s verified ranking
tuple. A new `CandidateEvidence.basis` value for degraded rows. Clearing
`candidate_discovery_error` when degraded candidates are actually presented (the first
submitted plan's choice, reverted after review).

**Why:** Multi-locked ranking is defined on verified closures (`clean_kill`/severity bands/
SPOF closure); static type-effectiveness axes have no honest way to populate those stages
without fabricating decisive/costly claims. A new evidence basis was rejected as unnecessary
per this project's established reuse discipline — `mechanical_only`/`low` confidence plus
explicit degradation tokens already carry the distinction without a second evidence model.
Clearing the graph error field when presenting degraded candidates was rejected because it
reintroduced, one layer downstream, the exact problem the bundled `generate_team_review` fix
existed to close: a caller watching only the graph-level error field would get a false
all-clear precisely when something potentially misleading (unverified static candidates) was
being shown. Traced whether any consumer actually depended on the old behavior before
reversing it — none did; bootstrap already pairs an error with a presentation elsewhere in
the codebase, so the fix made `single_locked` consistent with an existing pattern rather than
introducing a new one.

**Status:** Implemented and verified — consumer sweep found exactly one production caller of
`query_threat_counters` before its return type changed; `multi_locked`'s existing calc-failure
test confirmed byte-identical to its pre-task body; sort firewall confirmed adversarial via a
static row with a deliberately falsified high `verified_score`. 649 tests passing at ship.
Deliberately deferred: weather/terrain-aware static discovery (`query_counters` still never
passes field context — accepted, documented ceiling); support/shared-only presentation with an
explicit "team-threat ranking unavailable" banner for `multi_locked` under calc failure
(default remains hard stop).

---

## ADR-030: Legitimate zero-damage calc results are successes, not errors — batch semantics
must not let one immune/status row abort an otherwise-valid matchup

**Decision:** The calc handler (`services/calc/handlers.ts`) now distinguishes a legitimate
zero-damage result (type immunity, ability immunity, or a non-damaging/status move) from a
genuine calculation failure, based on the actual computed result rather than a re-derived
prediction of what the result should be. Concretely: after a successful `calculate()` call, if
`range()[1] === 0`, the row is returned as a normal success (`damageRange: [0, 0]`, empty KO
chance/text) without calling `result.kochance()`/`desc()`/`fullDesc()` — those calls are what
previously converted a correct zero into an error string. Anything that throws before or
during `calculate()` (malformed input, a genuine library bug, a real transport failure) is
unaffected and still produces `{error: ...}`, still mapping to `MatchupEvidenceError`/
`calc_incomplete` or `CalcClientError`/`calc_unavailable` exactly as before. On the Python
side, `_NON_DAMAGING` (a curated denylist of non-damaging move IDs) is replaced with a
data-grounded check against `data/moves/flags.v1.json`'s real `category` field — `_damaging_
moves` now excludes anything genuinely `Status`-category rather than relying on a manually
maintained list.

**Alternatives considered:** pre-checking move category/type-effectiveness in the handler
before calling `calculate()`, to decide upfront whether a zero-damage result should be
expected. Extending `_NON_DAMAGING` with the specific moves found missing during
investigation, rather than replacing it with a data-grounded source.

**Why:** A completed `calculate()` call has already correctly applied every immunity rule that
matters — type chart, ability-based immunities (Levitate, Water Absorb, etc.), Protect,
zero-base-power interactions — all of it. Re-deriving any of that logic in the handler to
predict "should this be zero" would duplicate `@smogon/calc`'s own correct computation and
would still miss ability-based immunities, which aren't visible from typing alone. Checking
the actual computed result is the only check that can't drift out of sync with what calc
itself determined. The prior behavior was a structural fragility, not a two-move bug: any kit
containing a type-immune hit or a status move missing from the curated denylist would abort an
*entire* matchup — including its other, perfectly valid damage rows — on a single legitimately-
zero row. This was discovered via what initially looked like a service-availability problem
(a port conflict revealed the calc service had been running continuously the whole time,
ruling out "service down" as the actual cause of the `calc_incomplete` errors being observed).
Extending `_NON_DAMAGING` with newly-found missing moves was rejected in favor of replacing it
entirely with the real move-flag data already ingested for the conditional-mechanics work —
the curated list itself was the actual class of bug (156 of 175 legal Status moves were
missing, not just the two or three that happened to surface in testing), and patching it
reactively would only have deferred the same failure mode to the next unlisted status move.

**Status:** Implemented and verified. All eight originally-reproduced cases (Electro Shot vs.
three real Ground-types; Dragon Claw vs. four real Fairy-types; Wide Guard) confirmed
individually as correct `[0, 0]` successes, not inferred from an aggregate pass count. A real
batch test confirms the actual fix — one immune row (Electro Shot) alongside three genuine
damage rows in a single `runCalculateBatch` call no longer aborts the batch; the Python-side
equivalent confirms the resulting matchup correctly reaches `clean_kill`/`decisive` via the
kit's actual best non-zero move, not a fabricated or default result. The original genuine-
failure regression test (`test_incomplete_batch_evidence_raises`, unmodified since its original
introduction) confirmed still passing exactly as written, proving real failures are unaffected.
796 tests passing (up from 792), full suites on both sides (`npm test`, `uv run pytest`), 6
skipped matching the established baseline.

**Deliberately deferred, tracked as a separate bug, not folded into this decision:** a
Kingambit + Assault Vest crash (`Cannot read properties of undefined (reading 'megaStone')`) —
confirmed to be a genuinely different failure mode (an item-data lookup issue in the vendored
calc library), still correctly producing `calc_incomplete` today, not silently swallowed by
this fix.

---

### ADR-030 — Amendment 2026-08-11a

**Calc identifier guard, usage display-name stamp correction, and blank move-key filter —
three related fixes closing the remaining calc crashes found in real 0.1.0 demo replay.**

**Decision:** Extends ADR-030's core principle (the calc boundary must correctly distinguish
legitimate results from genuine failures, never silently fabricate or crash) to two further
failure classes found via real demo replay after the zero-damage fix shipped.

1. **Unknown-identifier guard.** `toPokemon` (`services/calc/handlers.ts`) now rejects any
   species or item string that doesn't resolve in the Champions calc dex, throwing a stable,
   typed error (`unknown Champions species: {name}` / `unknown Champions item: {name}`)
   *before* constructing a `Pokemon` object — the first project-owned point where a string
   crosses into `gen.species.get()`/`gen.items.get()`. Routes through the existing
   `runCalculateSafe` → `{error}` → `MatchupEvidenceError`/`calc_incomplete` path unchanged.
   Explicitly does not return a fake `[0, 0]` (would be indistinguishable from the legitimate
   zero-damage case ADR-030 itself established) and does not silently drop the row.
2. **Usage display-name stamp correction.** `_set_from_entry`/`find_set_matching`
   (`recommender/usage_data.py`) previously stamped raw in-game display names onto
   `PokemonSpec.species` even when the name didn't `toID()` to a calc-valid identifier and a
   valid alternative existed. A systematic audit against all 324 real Champions calc species
   names, across every usage source, found exactly five affected rows (not assumed from the
   two that happened to crash first): Maushold Family of Four, Vivillon Fancy Pattern,
   Basculegion Male, Alolan Ninetales, Floette. Two were already silently correct via an
   unrelated merge-order side effect; the fix remaps all five consistently to a calc-valid
   label (legality name where one exists, otherwise the stored id).
3. **Blank move-key filter.** A genuine Showdown/MunchStats chaos-data artifact (an unparsed
   `""` move slot, faithfully ingested rather than a project-side construction bug) could
   reach the calc-batch layer as a "move," failing with `move is required`. Fixed with
   `_nonempty_moves`, applied at kit-construction time: blank/whitespace move names are
   skipped, and a featured set left with fewer than four real moves correctly falls through
   to common-move backfill rather than shipping an incomplete kit.

**Alternatives considered:** shipping the identifier guard alone as sufficient for 0.1.0.
Treating the Hurricane and Kingambit+Assault Vest crashes as one bug given their surface-level
similarity (both undefined-property-read crashes). Fixing the blank-move problem at
extraction time rather than at read time. Patching only the specific species/rows already
observed crashing rather than auditing the full blast radius first.

**Why:** Guard-only was rejected because it would have shipped 0.1.0 in a state where the
actual demo scenario's coverage pass still aborted on Maushold — a cleaner error message
doesn't unblock a real recommendation, it just fails more politely. Treating the two crashes
as one bug was rejected after direct, independent re-tracing showed they differ in every
structural respect that matters (lookup function, construction stage, and — critically —
whether either is even reachable via a legal, real gameplay path: Assault Vest is confirmed
format-illegal and only reaches calc via test fixtures today, meaning it was never the live
blocker Hurricane/Maushold was). An extraction-time fix for the blank-move issue was deferred
in favor of a runtime filter specifically because the runtime path is what a real coverage
pass actually depends on today, and a re-extraction-safe fix is a larger, separately-scoped
change to `fetch_usage_mb.py` that shouldn't block this release. Patching only the observed-
crashing species was rejected in favor of a full audit in both cases (species/name mismatches,
then again for blank-move rows) — this project's own recurring lesson (`_ROLE_PREF_MOVES`,
`_NON_DAMAGING`, the redirection compendium) is that lists built from what happened to surface
in testing are never actually complete, and each of the three fixes here confirms or refutes
that completeness with real data rather than assumption.

**Status:** Implemented and verified against the actual bar that mattered — not unit tests in
isolation, but the real demo scenario (Pelipper + Sylveon locked, `compute_team_coverage`
against all 79 real threats from `get_relevant_threats`, live calc service) completing with
zero `MatchupEvidenceError`. Maushold resolves to a real mechanical outcome (`no_answer`, a
genuine 2HKO-not-OHKO, not a masked failure); Kangaskhan's backfilled kit produces `clean_kill`
in both directions, confirming the backfilled fourth move is real and sensible, not just
"no longer blank"; Vivillon resolves to `clean_kill`. Node and Python test suites both
re-verified in full at each stage of this three-part fix, not accepted as scoped subsets.

**Deliberately deferred, tracked as separate future scope, stated explicitly rather than
implied resolved:** `fetch_usage_mb.py` still writes blank move keys into the snapshot on
re-extraction — this fix is a runtime read-boundary filter, and will need reapplying (or a
proper extract-time fix) whenever the snapshot is regenerated. `_damaging_moves` and a
calc-side `move is required` guard were both confirmed as viable defense-in-depth locations
but not implemented, since the kit-construction filter already closes the live path. The full
canonical-name/form-resolution backlog item remains open — its priority is now confirmed
higher than previously understood (it causes live crashes, not just missed Compendium
matches), but it was deliberately not absorbed into this narrower, evidence-bounded fix.

---

## ADR-031: full_build_confirmation redesign — anticipatory build-edit options with
axis-composed alternatives and non-mutating compare

Status: Implemented 2026-08-12 (feat/full-build-confirmation-options, 66725cb)

Context: full_build_confirmation offered only yes/defer, pushing every real build-change
request onto free-text extraction (Surface 1's edit-intent, ADR-013/ADR-027 lineage)
regardless of predictability. Live CLI testing surfaced a real ceiling — ambiguous edit
scope, and relative edits ("add Aura Sphere") failing because the model had no visibility
into the current build at all. Root cause wasn't extraction robustness; it was that the
confirmation surface itself carried no options.

Decision: default + 2-3 computed alternatives at confirmation, grouped by axis
(spread_nature / moveset / item / bundled) so independent axes compose (e.g. a spread pick
plus a separate move pick) rather than forcing a flat mutually-exclusive menu. A new,
non-mutating compare intent lets the user interrogate options (Spe/damage/KO, calc-backed)
before committing, kept structurally separate from edit (which always produces a new
provisional build) and from pending_response (which means "clarify," not "here's the
analysis"). Species selection stays outside build-confirm entirely — a species
reconsideration mid-confirmation is recognized as its own fork and routed back toward
candidate_selection, not folded into the option list.

Precedent, not invention: the original role-play transcript (Aug 2026) already practiced
this shape informally (default + usage-sourced sibling options as AskQuestion choices) —
this ADR formalizes and ships it as designed system behavior, not a new interaction pattern.

Key mechanisms:
- provisional_for_confirmation enforces the invariant that the provisional build always
  equals the composed default before any full_build_confirmation is presented, since affirm
  commits provisional_slot as-is with no separate reconciliation step.
- apply_provisional_overrides (multi-field) is new, distinct from the existing single-field
  revise_provisional_slot (chunk 2) -- reuses its verification/refine machinery but supports
  composing overrides across independent axes. Overlapping override keys across selected
  axes are rejected outright (slot_commit_error), never silently resolved by "later wins."
- Alternatives generation reuses condition_resilience/assess_condition_resilience directly
  for team-conditioned siblings rather than a parallel calculator, plus a bounded
  ally-support-move scan (fixed frozenset: Light Screen/Reflect/Aurora Veil/Tailwind/Trick
  Room) for cases like "an ally already provides screens, this SpD investment may be
  redundant."
- compare analyzes every requested option_id (never truncates the option set), capping only
  the number of distinct threat contexts (<=2) that get real calc calls -- bounds the
  expensive, variable cost axis while guaranteeing completeness on the axis the user
  controls.
- New real-build data source: MunchStats-linked Pokepaste sheet, 712 real 6-mon teams (659
  with real EV spreads), wired into the generator behind a >=15-occurrence gate per species
  to avoid noisy/thin samples. Addresses the honestly-flagged ceiling that usage APIs give
  spread/item/move marginals, not joint full builds (the "Choice+Protect mash" cautionary
  case) -- real Pokepaste builds are actual joint combinations a real player ran.
- Minimum bar for any presented option (non-negotiable): legal (check_set + Item Clause),
  provenance-labeled, diffed against the default, >=1 mechanical claim checked when the fork
  is bulk/offense/Speed, team-conditioned note when relevant. An option that can't meet
  legality/provenance/diff doesn't get presented as a peer of the default.

Rejected: a parallel condition-resilience calculator for team-conditioning (duplicates
existing logic, risks drift); folding compare into edit or pending_response (conflates
distinct meanings under one shape); presenting species alternatives inside build-confirm
(species is a different decision level than spread/item/moveset, not an axis of the same
build).

Consequence: full_build_confirmation now carries build_option_groups and default_option_ids
on PendingPresentation (parallel to candidate_selection's existing options field, not a
reuse of it -- that field is species-shaped and stays candidate-only). Two new turn_intents
(select_build_option, compare) join the existing vocabulary. Free-text edit (chunk 2)
remains the fallback path for novel requests, unchanged.

---

### ADR-031 — Amendment 2026-08-16a

**Cluster A classify-time gates shipped: gap-fill now enforces a real `(turn_intent,
pending_kind)` compatibility check and, on `full_build_confirmation`, genuine option-id
membership — closing the two specific failure modes that produced session-destroying,
self-compounding errors in live adversarial testing (2026-08-16 steering verification).**

**Motivated by direct, live evidence, not a hypothetical concern.** A scripted adversarial
session and an unscripted exploratory session (both run against live Ollama qwen3.5, following
ADR-005's reopened revisit condition) confirmed the core interaction layer would silently guess
on ambiguous or invalid input rather than ask, with real, compounding consequences: "I want the
faster one" was classified `select_build_option` with `option_ids: ["2"]` — a raw display
number, not the real id `spread_nature:2` — producing a `slot_commit_error` that then reprinted
on every subsequent turn for the rest of that session. Separately, "2" typed on a
`candidate_selection` screen (a different `pending_kind`, with no `option_ids` concept at all)
was misclassified the same way, permanently wedging that session — it never reached a build
confirmation again.

**Root cause, confirmed via direct code trace before any fix was designed:**
`SelectBuildPayload`/`ComparePayload` are unvalidated `TypedDict`s; the only real validation
lived on `TurnIntentExtraction` and checked nothing beyond "nonempty strings" (`compare`:
length ≥ 2). Real membership checking already existed — `_index_build_options`, used correctly
by the closed-set deterministic path — but the LLM gap-fill path bypassed it entirely. Separately,
zero code-level enforcement existed anywhere connecting `turn_intent` to `pending_kind`; the
system prompt's own "when pending_kind is X" language was pure guidance the model could ignore,
confirmed directly (`parse_turn_intent` never compares against `pending_kind`; `_route_intent`
is a bare dict lookup; `apply_provisional_option` doesn't check `pending["kind"]`).

**Fix, precisely scoped from a real, complete compatibility matrix (5 `pending_kind` values ×
12 intents), not a blanket rule:**
- **Screen/type mismatch, blocked outright:** `edit`/`select_build_option`/`compare` on
  `candidate_selection`, `completion_preference`, and the synthetic `none` state; `lock`
  unconditionally on `full_build_confirmation`, including cross-slot attempts — matching the
  prompt's already-stated intent ("never lock here") with real enforcement, no carve-out for
  same-slot or different-slot locking, both explicitly considered and rejected as unsupported
  capabilities this task shouldn't quietly invent.
- **Membership check, `full_build_confirmation` only** (the only screen with real `option_ids`
  to validate against — `candidate_selection`'s options are species-shaped, not id-shaped):
  every `select_build_option`/`compare` id must be a genuine member of
  `_index_build_options(pending)`, reusing the existing helper rather than duplicating it.
- **Failure messaging, two distinct shapes, deliberately not one and not three:** screen
  mismatches get a standalone `"That action isn't available here."` — no manual footer
  concatenation, since `format_turn` already appends the current screen's real footer
  automatically for any `pending_response`, a redundancy caught and corrected before
  implementation; membership failures name both the invalid and the real valid ids explicitly.
- **A subtle correctness requirement, both documented in code and proven by a dedicated test:**
  a blocked `lock` must not destroy the pending confirmation screen — `lock` is normally
  `_ACTIONABLE_INTENTS`-classed and would otherwise trigger pending-clearing side effects on
  success; the rejection path deliberately omits `_clear_pending_keys`.

**Explicitly, deliberately not fixed here — a real, stated scope boundary, not a silent gap:**
`continue` and `team_review` remain fully allowed to destructively clear a pending
`full_build_confirmation` with no confirmation step, even though these were the two intents
actually causing the worst live damage (a prompt-injection attempt succeeded via `continue`;
"show me the team, but first" via `team_review` wiped an in-progress build). Both are
technically legitimate steering (`A`-type in the compatibility matrix, not `I`-type mismatches)
— adding friction before they fire is a real, separate design question (whether *any*
actionable intent should get a confirmation step before destroying pending work), deferred to
its own cluster rather than folded in here. A dedicated test with an explicit docstring
("Cluster B boundary... This gate does not add a confirmation step") proves this is intentional,
not overlooked.

**Also explicitly not fixed: the sticky `slot_commit_error` lifecycle itself.** Confirmed via
direct trace: a failed apply writes the field and almost nothing downstream ever clears it
(only successful `_emit_full_build_confirmation`, successful `commit_full_slot`, and
`reset_team` do); `format_turn` prints it unconditionally whenever set, regardless of the
current turn's actual outcome. This task prevents its two specific, most commonly-hit triggers
from ever firing — a real, meaningful reduction — but the underlying state-lifecycle bug
persists for every other apply-time failure type (illegal edits, overlapping override keys,
refine failures). Named as the next cluster to scope, not addressed here.

**Confirmed by direct verification, not just Cursor's report:** every locked design decision
traced against the actual diff. Both headline live-session failures independently reproduced
outside the test suite with the fix applied — the exact `"2"`/`spread_nature:2` mismatch now
correctly returns `pending_response` naming real valid ids; the exact `candidate_selection`
wedge case now correctly rejects with the mismatch message, never reaching
`apply_provisional_option`. The two most load-bearing tests inspected directly:
`test_lock_on_confirmation_does_not_clear_pending` proves the subtle screen-preservation
requirement; `test_continue_and_team_review_on_confirmation_still_clear_pending` carries an
explicit docstring proving the Cluster B boundary is deliberate. 32/33 named tests (1
environment skip), 1099/1099 full suite, zero regressions.

**Status:** Shipped on `feat/cluster-a-classify-gates`, PR #92, merged to `main`.

---

### ADR-031 — Amendment 2026-08-16b

**Cluster B shipped (continue only): `continue` on `full_build_confirmation` no longer clears
and rediscovers immediately — it's intercepted onto a new `confirm_abandon_build` pending kind,
with the original intent stashed and only replayed after explicit confirmation. Closes the
prompt-injection vulnerability and the "show me the team, but first" damage found in the
2026-08-16 live steering verification, for this specific intent.**

**Scope deliberately split from the original framing, not defaulted.** `continue` and
`team_review` were both proven damaging live, but investigation found they're architecturally
different in a way that matters: `team_review`'s handler is already non-mutating (its damage is
purely classify-time), while `continue` routes into `route_team_phase`, which triggers genuine
rediscovery that overwrites pending regardless of clear-key handling. Given `team_review` likely
has a cheaper real fix (a `compare`-style non-mutating overlay, or fixing free-form "show me the
team" to route through the CLI's existing non-destructive `:team` path instead of the
destructive graph node), building the heavier stash-and-replay machinery for both was rejected —
`continue` gets it now; `team_review`'s lighter fix is a deliberate, separate follow-up.

**Why a new `pending_kind` was required, not an overlay on the existing confirmation screen:**
`yes` on `full_build_confirmation` already means `full_slot_confirmed`. Reusing that screen for
"discard this?" would make a bare `yes` genuinely ambiguous between confirming the build and
confirming the discard. `confirm_abandon_build` gives affirm/decline exactly one meaning.

**Mechanism:** the gate stashes `queued_turn_intent`/`queued_turn_payload`/`held_pending` and
omits `_clear_pending_keys`, so the provisional build survives intact across the round-trip.
Affirm (a deliberately narrow closed-set: `yes`/`yeah`/`yep`) replays the original stashed
intent with clear keys now attached — no second LLM call, confirmed directly via a real
call-counting parser across actual graph invocations, not asserted in prose. Decline
(`no`/`nope`) restores `held_pending` wholesale — same screen-preservation pattern as Cluster
A's `lock` rejection. Anything else (`ok`, `accept`, `defer`, or any other reply) deliberately
falls through to a safe, non-mutating `pending_response` rather than being interpreted either
way — confirmed this correctly prevents accidental discard via near-miss replies.

**Unconditional by design, checked against the real incident, not assumed sufficient.** No
customization-based gate (e.g., only confirm if the provisional build had real edits) — the
actual live-damaged session's edits never landed anyway (blocked by Cluster A's now-fixed
option-id failures), meaning the thing genuinely destroyed was an unedited default build. A
risk-aware heuristic would have offered zero protection in the real case that motivated this
whole cluster.

**Explicitly out of scope, confirmed and named rather than silently left:** `team_review` still
fully destroys pending, unchanged — its lighter fix is the natural next task. `rejection`/
`archetype_change` remain immediate-action by design (the prompt already documents species-swap-
as-rejection on this screen as intended UX; guarding it would work against the designed path).
`constraint`/`restore` stay unguarded pending a real live miss, not preemptively hardened.
`reset` is confirmed as a categorically bigger, separate question (wipes the whole locked team,
not one pending build) — not folded in here. Other screens (`candidate_selection`,
`completion_preference`) unaffected — `continue` there remains legitimate, closed-set behavior.

**An honestly-named residual:** A2's unconditional `compare_analysis` clear at the start of
every `classify_input` call means a `compare` overlay showing on the confirmation screen before
this sequence would still vanish across the confirm/decline round-trip. The build itself is
unaffected — only a displayed comparison the user can simply re-request.

**Confirmed by direct verification, not just Cursor's report.** Every locked design decision
traced against the actual diff, including a genuinely good, unrequested UX touch found during
review — the confirmation prompt names the actual species at stake ("Pending build: Pelipper."),
not a generic "are you sure?" The two graph-level tests are exceptionally rigorous: one uses an
actual call-counting parser to *prove* no second LLM call happens on affirm or decline, rather
than assert it; both confirm genuine downstream behavior (real rediscovery reaching
`bootstrap_intake` on affirm; the exact original screen and provisional build restored intact
on decline). The exact real adversarial injection text from the live-failing session was
reproduced verbatim in a regression test, not paraphrased. Independently reproduced the narrow
affirm/decline behavior outside the test suite against six real inputs including three
plausible near-misses (`ok`, `accept`, `defer`) — all correctly stayed on the abandon screen.
11/11 named tests, 1112/1112 full suite, zero regressions.

**Status:** Shipped on `feat/cluster-b-confirm-continue`, not yet merged.

---

### ADR-031 — Amendment 2026-08-16c
*(assuming Cluster A → a, Cluster B/continue → b under ADR-031's own corrected sequence —
adjust the letter if your correction landed differently)*

**`team_review` on `full_build_confirmation` no longer clears pending — the last named finding
from the 2026-08-16 live steering verification is now closed. Free-form requests like "show me
the team, but first" now overlay the locked roster directly on the confirmation screen, leaving
the pending build fully intact and answerable afterward.**

**Deliberately simpler than Cluster B's `continue` fix, not built to match it.** Investigation
found `team_review`'s handler (`generate_team_review`) is already non-mutating and already ENDs
without touching pending — the destruction was entirely upstream, in `parse_turn_intent`'s
blanket `_clear_pending_keys()` call for any `_ACTIONABLE_INTENTS` member. That meant no stash,
no replay, no new `pending_kind`, no follow-up confirmation turn was needed — a direct
classify-time gate answering with the roster immediately, in the same turn, was sufficient.

**A real correction to the original discovery framing, caught before implementation.** The
initial plan for this fix assumed overlaying `last_team_review` (the calc-backed review result)
would satisfy the live utterance. Investigation found this was wrong: `format_turn` only ever
renders that field as a one-line status string, never the actual roster — overlaying it would
have preserved the confirmation screen but still completely failed to show the user their team,
missing the entire point of the original complaint. The actual fix reuses `format_roster` — the
exact same content the CLI's `:team` command already produces — directly, not
`last_team_review`.

**Short-circuit confirmed deliberately, not for convenience.** `generate_team_review` is never
invoked for this path — no calc HTTP call, no writes to `coverage`/`spofs`/`last_team_review`/
`candidate_discovery_error`/`shared_teammates`/`condition_resilience`. Justified directly against
the live evidence: the utterance that motivated this fix was a mid-confirmation status peek, not
a request for competitive analysis, and `format_roster` doesn't even display the calc-review's
output — running it would have paid a real cost for something invisible to the user in this
exact moment. This also made two complications the original discovery flagged (sticky
`last_team_review` persistence across later turns; `candidate_discovery_error` painting onto the
confirmation screen) moot entirely, rather than needing separate handling.

**A second real architectural option was investigated and correctly rejected, not just
overlooked.** The CLI's existing `:team` command was considered as a possible routing target for
free-form requests, but confirmed to be a pure, pre-graph client-side string match — no
classify, no node, the graph never runs. Building a "divert free-form input to this instead"
signal would have been genuinely new architecture, and would only have fixed the CLI
specifically, leaving any other client that invokes the graph directly still broken. The shipped
fix lives entirely within the existing graph/classify path instead.

**Confirmed by direct verification, not just Cursor's report.** The core regression test proves
the short-circuit directly via `patch("recommender.nodes.generate_team_review")` and
`generate.assert_not_called()` — not inferred from absence of side effects — with sentinel
values planted across all six fields the review would normally touch, as thorough defensive
setup. The exact real live-failing utterance ("show me the team, but first") reproduced verbatim
at the real graph-invocation level, confirming the confirmation screen and the provisional build
both survive fully intact. Independently reproduced outside the test suite with a fresh,
direct call, confirming both the short-circuit and that `pending_presentation` is never touched
at all. 5/5 named tests, 1116/1116 full suite, zero regressions.

**Status:** Shipped on `feat/team-review-roster-overlay`, not yet merged.

---

### ADR-031 — Amendment 2026-08-16d

**Kingambit-rejection bug fixed: locking a species now clears any stale entry for that same
species from `rejected`. Closes the last named finding from the 2026-08-16 live steering
verification. Implemented and verified directly, not through Cursor, given it was unavailable
for the remainder of the session — flagged explicitly as a real deviation from this project's
established plan-review discipline, not a silent substitution.**

**The bug, confirmed precisely via direct trace, not re-derived from the original report.** "I
want Kingambit, not redirection or Trick Room" was classified `rejection` with
`payload: {species: Kingambit}` — the positively-requested species got recorded as rejected.
Root cause: `_EXTRACTION_SYSTEM_PROMPT`'s entire guidance for `rejection` was one line
("rejection requires species"), with no rule or example for compound utterances naming both a
wanted and unwanted species with opposite polarity.

**Severity confirmed worse than the original live-session report captured.** A systematic trace
of every place `"rejected"` is touched in the codebase found exactly three call sites —
`initialize`'s default, `record_rejection`'s one-way append, and `team_candidates.py`'s
permanent filter — and confirmed **`reset_team` ("start over") does not clear `rejected`
either**, meaning a misclassified rejection would survive even a full team reset, with a new
thread as the only real escape.

**A real self-caught mistake, worth recording honestly rather than omitting.** An initial fix
attempt had `reset_team` also clear `rejected`, on the assumption that this was an oversight
rather than intentional design. The existing test suite caught this directly:
`test_reset_wipes_draft_preserves_rejected` documents `rejected`-survives-reset as deliberate,
tested behavior — a user restarting their build should still remember species they'd explicitly
rejected before. Reverted before it went further, and the full suite re-confirmed clean
afterward. This is exactly the kind of check ("was this a deliberate prior decision, not an
oversight?") this project has repeatedly required before touching existing mechanisms — it
should have been done before writing the fix, not after a test failure forced it.

**Fix, scoped to what's actually load-bearing:** `apply_lock` (covering both the single-lock and
batch-lock paths) now strips any `rejected` entry matching a species that just got locked.
Reasoning: locking is the strongest, most unambiguous "I want this" signal in this system —
there is no coherent scenario where a user wants a species both locked into their team and
simultaneously excluded from candidate generation as rejected. No new intent, no new payload
type, no schema change — a pure backend consistency guarantee. Explicit prompt guidance for
compound rejection utterances was added alongside it, but deliberately not relied on as the
sole fix, consistent with this project's now-repeated finding (Clusters A/B/team_review) that
prompt-only guidance alone is insufficient.

**Explicitly not pursued:** a classify-time consistency check flagging a rejection as suspicious
when the same species is also named as wanted in the same utterance — no existing structured
signal to check against without inventing new machinery; speculative cost for uncertain benefit.

**Confirmed by direct verification, self-performed given Cursor's unavailability — the one real
limitation of this round, stated plainly rather than glossed over: no independent second review
was possible.** Two new graph-level tests added, matching this session's established real-
invocation pattern: `test_lock_clears_matching_stale_rejection` (the fix, end-to-end) and
`test_lock_preserves_unrelated_rejection` (regression — locking one species must not touch an
unrelated rejection). Both the single-lock and batch-lock paths independently reproduced via
direct calls outside pytest. 1118/1118 full suite, zero regressions.

**Status:** Implemented locally, patch prepared for manual application — not yet pushed or
merged as of this entry.

---

### ADR-031 — Amendment 2026-08-16e

**Hard timeout added to every LLM parser call; multi-species bootstrap collapse fixed. Closes
the most severe remaining item from the 2026-08-16 live steering verification's consolidated
finding log — the two 7-8 minute hangs requiring manual kill, and the related utterance-collapse
bug that produced them. Implemented and verified directly, not through Cursor, given it was
unavailable for roughly a week — the second consecutive round with no independent plan review,
flagged plainly rather than treated as equivalent to a normally-reviewed change.**

**Root cause, confirmed via direct trace: `parser.invoke()` had zero timeout anywhere, in either
the bootstrap-intake or turn-intent classification path.** A single blocking call with no
provider-level or wrapper-level deadline — the existing exception handling only catches things
that actually raise, and a hang never raises anything, so nothing in the codebase could recover
from one. Confirmed this wasn't bootstrap-specific: the identical pattern existed in
`parse_turn_intent` (`turn_intent.py`), meaning any LLM call anywhere in the system could hang
indefinitely, not just the bootstrap path that happened to surface it live.

**Fix: `invoke_with_timeout()` (new module, `recommender/llm_invoke.py`), a shared,
provider-agnostic wrapper around any `Runnable.invoke()` call, applied to both call sites.** A
genuine correctness subtlety was caught and fixed before it became a real bug: wrapping
`ThreadPoolExecutor` in the ordinary `with` context-manager idiom would have **blocked on exit**
waiting for the abandoned background call to finish anyway, silently defeating the entire
timeout — the caller would eventually get a `TimeoutError`, but only after still waiting out the
full original hang. Required an explicit `executor.shutdown(wait=False)` instead. Proven with a
real-timed test, not just asserted: a 0.5s configured timeout against a genuinely slow
(10-second) mock call completes in under 2 seconds, directly demonstrating the wrapper doesn't
block on the abandoned thread.

**Timeout value, revised once with real justification.** Initially set to 30s (a judgment call
made without real operational data on normal local-Ollama latency). Increased to **120s** after
further discussion, to better match legitimately slow-but-working call durations and avoid
false-positive timeouts — the correct kind of revision, made with real reasoning once better
information was available, not a default that stuck without scrutiny.

**A real architectural option was investigated and explicitly declined, not overlooked.**
Separate `connect_timeout`/`read_timeout` differentiation was confirmed genuinely achievable —
`ChatOllama`'s `sync_client_kwargs` passes through to the underlying `ollama` client, which
itself forwards straight to `httpx.Client`, which natively supports this distinction. Declined
on the real evidence: the live hangs are against a *local* Ollama instance, where connection
establishment is negligible — the actual bottleneck is generation time, already covered by the
single global timeout. A separate fast-fail connect timeout would add real, provider-specific
complexity for a failure mode ("Ollama isn't running at all") that isn't what was actually
observed live.

**Second, separate fix: bootstrap's extraction prompt had zero guidance for compound,
multi-species utterances.** "Indeedee-F is the setter, Kangaskhan is available" collapsed both
species names into a single `anchor_text` field — confirmed the underlying schema already had
separate `anchor_text`/`pool_entries` fields capable of representing this correctly; the gap was
purely in prompt guidance, not a schema limitation. Added explicit compound-utterance guidance
with a worked example matching the real live-failing case, same shape as the earlier
Kingambit-rejection prompt fix. **No automated test possible for this half** — genuinely
prompt-dependent, needs a live LLM session to verify, an honestly-disclosed limitation rather
than a false claim of completeness.

**Confirmed by direct verification, self-performed given Cursor's continued unavailability.**
Three new tests in `test_llm_invoke.py` (success case, the real-timed hang-proof, and confirming
non-timeout provider exceptions still propagate normally, not swallowed). Regression tests added
to both `test_empty_team_bootstrap.py` and `test_turn_intent.py`, using a parser that raises
`LLMInvokeTimeout` directly to exercise the downstream fail-closed handling without waiting out
a real 120-second timeout in the test suite — a deliberate choice to keep the suite fast while
still genuinely testing the integration point. 1123/1123 full suite, zero regressions.

**Status:** Committed on `fix/llm-invoke-timeout`, patch prepared for manual application — not
yet pushed or merged as of this entry.

---

### ADR-031 — Amendment 2026-08-16f

**Clarifying-question content errors fixed: `archetype_change` no longer asks for a species on
a named strategy pivot, and "TR" is correctly understood as Trick Room. Closes the last
remaining item from the 2026-08-16 live steering verification's consolidated finding log —
every finding from that session is now closed.**

**Two genuinely separate root causes, confirmed via direct trace before writing anything, not
assumed to share a fix just because both surfaced as "wrong clarifying question text."**

**Case 1 — `archetype_change` incorrectly asking for a species.** Traced the payload directly:
`ArchetypeChangePayload` is just `components: list[str]`, stored straight as the new team-wide
strategy with no species involved anywhere downstream. "Pivot to sun instead" should map
directly to `archetype_change` with `components: ["sun"]` — the live failure (asking "Which
Sun-type Pokémon? e.g. Venusaur, Clefairy") reflected a genuine gap in what the model understood
the intent to require, with the Clefairy fabrication a secondary symptom inside an
already-misclassified path, not the primary bug. **Confirmed no structural check applies here**,
unlike the earlier compound-intent fix (Amendment [Tier 2 letter]) — there's no schema-level
signal to validate post-hoc, since this is a live classification choice (which `turn_intent` to
emit), not a payload-consistency issue detectable after the fact. Fixed with explicit prompt
guidance: a named strategy pivot is a complete `archetype_change` on its own, never requiring or
asking for a specific species.

**Case 2 — "TR" read as Team Rocket instead of Trick Room** inside a generated clarifying
question — a narrow, standalone domain-vocabulary gap with no connection to case 1. Fixed with a
one-line prompt clarification that domain abbreviations use their competitive-Pokémon sense.

**No automated test possible for either fix** — pure prompt-guidance content, same disclosed
limitation as every content-generation fix this arc (bootstrap collapse, compare-criteria
fabrication). Confirmed, not assumed: explored whether a structural check could apply to either
case before falling back to prompt-only, same discipline as the Tier 2 semantic-fabrication
work.

**A real process failure occurred and was caught during this arc, worth recording precisely.**
The patch for the *prior* fix (Tier 2 semantic misclassification) was generated against a stale,
locally-cached view of `main` rather than a fresh fetch, and failed to apply on the first
attempt. Root cause: relying on a sandbox's cached remote-tracking state rather than fetching
immediately before generating a patch — especially risky given how many separate merges were
landing in quick succession during this solo-implementation period. Fixed going forward by
fetching fresh and, for this fix and this fix only so far, actually testing patch application
against a genuine clone of the real GitHub remote before handoff, rather than assuming a
locally-verified diff would apply cleanly elsewhere.

**Confirmed by direct verification on the real merged `main` tip, not just the local branch.**
1127/1127 full suite, zero regressions.

**Status:** Shipped on `fix/clarifying-question-content-errors`, PR #100, merged to `main`.

**This closes the entire consolidated finding log from the 2026-08-16 live steering
verification** — Clusters A/A2/B, `team_review`'s roster overlay, the Kingambit-rejection bug,
the LLM-timeout/bootstrap-collapse fix, Tier 2 semantic misclassification, and now clarifying-
question content errors. All implemented directly given Cursor's continued unavailability, none
independently plan-reviewed — a real, repeatedly-disclosed limitation across this whole solo
stretch, not silently normalized as equivalent to the earlier Cursor-reviewed work.

---

### ADR-031 — Amendment 2026-08-16g: LLM parser timeout raised to 300s; Ollama keep_alive set to 30m

**Two related fixes to the LLM-invocation infrastructure, discovered and shipped in the same
investigation while diagnosing why a live regression check kept timing out.**

**`keep_alive`: set to a hardcoded 30m on both Ollama parser factories.** Ollama's own default
is 5 minutes, forcing a cold model reload on any gap longer than that during normal,
thinking-time-heavy CLI sessions — a real cost easily misread as a slow or hung call rather than
ordinary model-loading overhead. Traced end-to-end through the real production entry point
(`resolve_llm_parsers` → both `build_ollama_*_parser` factories → `ChatOllama`), confirmed
`keep_alive` is a genuine `ChatOllama` field, not silently dropped. Fixed one real, existing test
as a byproduct: its mocked factories used single-argument lambdas incompatible with the new
keyword, raising a `TypeError` silently caught by `resolve_llm_parsers`' broad exception handler
— a real regression the test suite correctly caught. Closes standing backlog item 17.

**Timeout: raised from an initial 30s judgment call, to 120s, to a final 300s — each revision
grounded in progressively better real evidence, not repeated guessing.** Live, warm-model
measurements against the actual production prompt chains found the bootstrap intake path taking
115-146s for a genuinely simple, single-species input, even warm — with schema-complexity and
recent-prompt-change both directly isolated and ruled out as causes (`BootstrapExtraction` has
*fewer* fields than `TurnIntentExtraction`, which completed in 15-24s on the same session; the
pre-existing prompt, predating the multi-species collapse-fix guidance, was equally slow). 300s
gives real margin (~2x the worst observed 146s) above measured reality.

**The root cause of why the bootstrap path specifically runs 5-10x slower than turn-intent
classification remains open and unexplained** — this is a stopgap to unblock live verification,
explicitly not a claim the underlying problem is understood or fixed.

**A genuinely good technical question got a real, evidence-grounded answer, not a hand-wave.**
Separate `connect_timeout`/`read_timeout` (confirmed achievable via `ChatOllama`'s
`sync_client_kwargs` → `httpx.Timeout`) was investigated and declined — the live hangs are
against local Ollama, where connection establishment is negligible; the actual bottleneck is
generation time, already covered by the single global timeout.

**Confirmed by direct verification, self-performed given Cursor's continued unavailability.**
Full suite clean at each revision; the keep_alive propagation confirmed via a real,
non-mocked-at-the-constructor-level trace through the actual entry point.

**Status:** Shipped, merged to `main`.

---

### ADR-030/031 — Amendment 2026-08-16h: specific "not legal" message for illegal-but-identified anchor species

**A real, confirmed UX gap fixed: an anchor species that resolves correctly but is illegal in
this format (e.g. Indeedee-F, confirmed `is_nonstandard: Past`) previously got the same generic
"Couldn't identify anchor" message as genuine, unresolvable gibberish — misleading, since the
system understood the request perfectly and simply rejected it on legality grounds.**

**Root cause, confirmed via direct trace:** `resolve_species_label`'s single combined check
(`not candidate or candidate not in species or not is_species_legal(...)`) collapses three
genuinely different failure reasons into one `None` return, discarding the distinction between
"couldn't identify this at all" and "identified it perfectly, it's just banned here."

**Fix: a minimal, safe internal refactor**, not a change to `resolve_species_label`'s existing
public contract (confirmed unaffected across all 4 real call sites). Extracted the
pre-legality-check resolution logic into `_resolve_candidate_id()`, and added a new, separate
`illegal_species_display_name()` used only at the one call site that needs the richer
distinction (`discover_bootstrap_directions`'s anchor-resolution failure path).

**Confirmed by direct verification:** end-to-end reproduction of the exact real failing case
("Indeedee-F" → "Indeedee-F is not legal in this format."), plus adversarial regressions
(genuine gibberish still gets the generic message; a legal species is unaffected).

**Status:** Shipped on `fix/illegal-species-anchor-message`, **not yet merged** — pending
manual application.

---

### ADR-016/031 — Amendment 2026-08-16i: nature field for spreads that require one specific nature

**A real, serious bug fixed — the same failure shape as the earlier Medicham-Mega synthesis
bug: two independently-real attributes (a cached spread, an independently-sourced nature)
getting combined into a build no real source actually recommends.**

**Confirmed directly from the cached record's own source text**, not inferred: Archaludon's
"default" build paired a Choice Scarf spread (2/0/0/32/0/32) with Modest nature, while the
cached entry's own `rationale` explicitly states "A Timid nature is mandatory" for that exact
spread. Root cause: `get_resolved_build`'s cache (ADR-016, `data/resolved-builds/*.jsonl`) is
deliberately keyed on species+moveset+item only — nature intentionally out of scope per the
cache's own README, correct for genuinely nature-flexible spreads (confirmed: most entries
are), but silently wrong for the fraction that aren't.

**A real, honest self-correction happened mid-investigation, worth recording precisely.** An
initial automated scan claimed ~30% of all 59 cached entries were affected. Manually reading
every flagged entry's full rationale — not trusting the crude proximity-based match — caught
real false positives (a nature word describing an *opposing* Pokémon's set, or a *different*
alternative spread than the one actually cached) and one genuinely ambiguous case (a spread the
source presents as valid under either of two natures, correctly left unset rather than forced).
**The real, individually-verified count is 6 of 59 entries (~10%)**, each confirmed against an
exact, unambiguous textual tie before anything was written to the real data files.

**Fix:** an optional, structured `nature` field added to `ResolvedBuild`, populated only for
the 6 confirmed cases; `_refine_defaults` now prefers it over the independently-sourced usage
nature when present, falling back to existing behavior for the ~90% of entries with no such
field.

**A separate, real observation surfaced but not fixed here:** several entries in
`champions-reg-ma.jsonl` appear to be exact duplicates — a distinct data-quality issue, left
for its own future pass.

**Confirmed by direct verification:** end-to-end test against the real, committed data file
with **no mocks at all** — the exact original live-failing scenario now produces the correct
Modest-nature pairing.

**Status:** Shipped, merged to `main`.

---

### ADR-031 — Amendment 2026-08-17a: bare-number shorthand fixed — matches visible option id, not list position

**Decision:** `_deterministic_build_option_ids`'s numeric-shorthand path (bare `"1"`,
`"option 1"`) now matches exclusively against an option's own visible numeric suffix (e.g.
`spread_nature:1` → `1`), never its position in the presented options list. Exact integer
match only — `"1"` does not match `"spread_nature:11"`. Word-ordinals (`"first"`, `"the second
one"`) are unchanged and keep list-position semantics.

**Why:** `generate_build_option_groups` always prepends a synthetic, non-numeric default option
at list position `0`, ahead of the real numbered siblings. `_ORDINAL_REPLIES`'s prior semantics
mapped bare `"1"` to list position `0` — meaning it silently selected the default instead of the
option literally labeled `1`, off by one against every real numbered sibling. Confirmed live
and reproduced exactly against the real menu shape and build. This is a stronger finding than
2026-08-16's handoff described (which characterized bare numbers as "correctly rejected, safe
friction"): that description holds for the genuinely different multi-axis case
(`len(groups) == 1` correctly gates the ordinal fallback off entirely when multiple axis groups
are presented at once, so it correctly declines to guess there), but not for the single-axis,
default-prepended shape, which is the common case for this presentation and does not reject —
it silently resolves to the wrong option.

**Scope confirmed, not assumed:** `candidate_selection` and `completion_preference`'s existing
`_ORDINAL_REPLIES` usage is unaffected and untouched — both number options by literal list
position via `enumerate(..., start=1)` in their respective formatters, so list-position-based
ordinal matching is already correct there. Only `full_build_confirmation`'s option ids are
independently numbered, disconnected from list position once a default is prepended.

**Status:** Implemented and merged. Three regression tests added directly targeting the fix.
Full suite: 1130 passed (up from 1127), 8 skipped (baseline unchanged). Implemented directly
(Cursor unavailable), disclosed in the commit message; the one real design decision (exact-match
semantics against the visible id) was explicitly confirmed live with Vu before implementation.

**Deliberately not addressed here, left open:** resolving bare numbers when multiple axis
groups are presented simultaneously in the same menu — the `len(groups) == 1` gate remains a
hard exclusion, not a partial fix. Real open design question, per the original 2026-08-16
handoff, still unresolved.

---

### ADR-031 — Amendment 2026-08-18a: partial/delta spread edits — new schema fields, and the
reliability gaps that immediately followed

**Decision:** `TurnIntentExtraction` gains `value_spread_set` (set named stat(s) to an exact
value) and `value_spread_delta` (add a signed amount to named stat(s)), as alternatives to the
existing full-replace `value_spread` — at most one of the three populated per edit. Resolution
chains through existing machinery rather than new mutation logic: `apply_provisional_overrides`
(a selection, if any) then `revise_provisional_slot` (the field_only spread adjustment on top),
mirroring exactly what two sequential turns would already do.

**Why:** "spread_nature:3, but with 5 Spe" was silently dropping the stat override entirely,
because the only way to express a spread edit required the model to compute a full six-stat
replacement — a materially harder generation task than naming a single field's new value the way
"different item" edits already worked. Two smaller, real bugs found in the same investigation and
fixed alongside: a latent `KeyError` crash risk in the pre-existing spread-coercion code (no
guard against a missing stat key), and the compound-signal detector's clarifying message
hardcoding "an edit and a comparison" even when the actual second signal was a selection.

**Reliability gaps found immediately, live, not anticipated in the original design:**
- `edit_scope` is consistently omitted (not wrong — absent) by the local model for otherwise
  well-formed edits. Fixed by defaulting to `field_only` when omitted, rather than hard-failing —
  the conservative, safe choice, and an explicit `regenerate` from the model is never overridden.
- Stat keys are consistently emitted in conventional capitalized form (`Spe`, `HP`, `SpA`), not
  this codebase's internal lowercase convention — silently rejected nearly every real extraction
  as "unknown stat" until case-insensitive normalization was added, affecting the pre-existing
  full-replace path too, not just the new fields.
- The new optional fields being left as `{}` rather than `null` by the model tripped the shared
  edit validator for every edit type, not just spread ones — a plain item edit failed with zero
  relation to spread logic, which is what made this findable rather than another guess.

**Status:** Implemented, tested, merged (`feat/partial-spread-edits`, PR into main 2026-08-18).

---

### ADR-031 — Amendment 2026-08-18b: don't trust model-computed spread arithmetic — extract only
what's deterministically readable from the text

**Decision:** A full-form `value_spread` from the model is never trusted as a literal final
answer. When only a full-form value is given (no partial set/delta), it's diffed against the real
base spread; if exactly one stat differs, that's trusted and the rest of the model's dict is
discarded entirely. Separately, and more directly: `extract_single_stat_target()` reads a
single-stat instruction ("make it 5 Spe," "2, but make it 5 Spe") straight out of the raw request
text — stat name, value, set-vs-delta from nearby words — and rewrites the extraction to use the
partial form *before* any of the model's own (possibly wrong) computation is ever consulted. The
same principle recovers a dropped leading option reference ("2, but...") independently of whether
the model's own `option_ids` extraction succeeded.

**Why:** Confirmed live, twice, independently: the model's full-form computation reused unrelated
values from a different menu option in one case, and scrambled two stats it wasn't asked to
change in another, while correctly setting the one stat that was actually asked about. Prompt
engineering (field descriptions steering the model toward the partial forms) measurably helped but
did not reliably prevent this, especially for compound select+edit requests. Reframed directly by
Vu mid-arc, not inferred: *"the agent's supposed to do the computation, can't keep asking the user
for everything... the agent is useless if a fill form can do the job."* The fix that follows from
that isn't a nicer clarifying question — it's recognizing the user's original request already,
deterministically, contains everything needed, and there's no reason to route that through
unreliable model arithmetic at all when the code can read it directly.

**Scope, confirmed explicit:** the deterministic extractor only resolves single-stat requests.
Genuinely multi-stat text ("shift the points from Def to SpD") or text with no confident single
stat+value pairing is deliberately left unresolved (returns `None`, not a guess) and falls through
to the ask-based flow in Amendment 2026-08-18c. This is a real, disclosed scope boundary — a
generalized multi-stat deterministic resolver was not attempted.

**Status:** Implemented, tested, merged.

---

### ADR-031 — Amendment 2026-08-18c: hybrid auto-regenerate/ask for budget-mismatched spread
edits, and making the residual "ask" a real conversation

**Decision:** When a valid, single-stat spread edit pushes the total off `SP_BUDGET`: if the
mismatch is small (≤2 points) and there's one clear "smallest, has room" candidate stat among the
untouched ones, auto-adjust it — always disclosed via a notice, never silent. Otherwise, ask which
stat to adjust, with real defer support (cancels just the one edit, restores the prior build
state, not the broader "abandon this slot" defer used elsewhere). The same real interactive
architecture (a dedicated `PendingPresentation` kind, structured-data-driven display, a proper
graph node to resolve the answer) is reused for the separate case where Amendment 2026-08-18b's
deterministic extractor can't resolve a spread edit at all (genuinely multi-stat or unparseable
text) — `spread_target_question`, asking for both stat and value together.

**Why:** The auto/ask boundary and the "must never be silent" requirement were both put to Vu
directly as real design decisions, not defaulted into — three options were laid out (always ask;
always auto-regenerate silently-ish; hybrid) and the hybrid was chosen explicitly. Separately, the
first version of the residual "ask" (for text the deterministic extractor can't resolve) was
found, live, to be a dead end: a bare `slot_commit_error` phrased as a question with no state to
receive an answer — a follow-up reply got treated as an unrelated fresh turn against the
still-displayed menu. This is a distinct bug from Amendment b's scope: b eliminated most of the
cases that ever reached this dead end, but for the residual genuinely-ambiguous case, asking is
still correct — it just needs to actually function as a conversation when it does.

**Real mistakes caught before shipping, logged plainly:** a first draft of the reallocation sort
key applied `reverse=True` to the whole tuple, which would have inverted every other field's
already-correct ascending-order design, not just added the new leading field — caught by a direct
test before committing. A mid-arc refactor (moving stat-name parsing into `slot_fill.py` to avoid
an awkward cross-module import direction between `nodes.py` and `turn_intent.py`) left a dead,
duplicate function in the file for one commit, caught and removed in the next.

**Status:** Implemented, tested, merged.

---

### ADR-031 — Amendment 2026-08-18d: interactive item/moveset-conflict resolution

**Decision:** When an item edit creates a Choice-item/non-damaging-move conflict (e.g. Choice
Scarf + Protect), offer a real interactive choice instead of a static error: pick a real,
usage-backed damaging move alternative; keep the conflict deliberately ("keep it"); or revert the
item. New `PendingPresentation` kind (`item_moveset_conflict_question`), same architecture as the
spread-editing interactive flows from the prior branch (structured-data-driven display, a
dedicated graph node to resolve the answer, proper defer handling).

**Why:** Original request, held over from the spread-editing arc until that work was stable.
Move-alternative discovery needed no new data pipeline — `resolve_learnset` (real legal moves) and
`move_narrowing._commitment_pct` (real usage-backed commitment %) were already sufficient,
confirmed directly against the live Archaludon + Choice Scarf scenario before any resolution code
was written.

**Real, explicit scope decision, not defaulted into:** `simultaneous_lock_conflicts` bundles two
independent checks under the same `("item","moveset")` group — the status-move issue, and a
separate speed-direction interaction (Choice Scarf + Trick Room). Accepting the shown conflict
("keep it") must only bypass the specific issue actually shown and consented to, never an
unrelated one riding along in the same bundle. `_verify_provisional_hard` gained an
`accept_status_move_conflict` parameter that independently re-checks the speed-direction case even
when the status-move case is accepted — confirmed directly with a synthetic Choice Scarf + Trick
Room + status-move build that still correctly blocks after accepting the status-move conflict.

**Real bug found and fixed while building this:** the first draft's conflict detection
(`_handle_item_moveset_conflict`) only checked whether the current moveset contained a status
move — never whether the item was actually a real Choice item at all. A completely fake/illegal
item was misidentified as a conflict, masking the real "illegal edited slot" error the legality
check should have produced. Found via an existing test failing, not by inspection. Fixed by gating
on `reconcile._tier1_choice_status_moves` (the real detection function) before using the
display-name helper.

**Status:** Implemented, tested, merged (`feat/item-moveset-conflict-resolution`, PR #106).

---

### ADR-031 — Amendment 2026-08-18e: recovering a compound select+non-spread-field-edit request,
generalized beyond the spread-only case

**Decision:** The "model drops one half of a compound select+edit request" failure mode, already
fixed for spread edits in the prior branch, is not spread-specific — it recurs independently for
item (and, by the same mechanism, ability/nature/moves) edits, in multiple different concrete
shapes. Each was root-caused from real raw extraction debug output before being fixed:
- A bare, unresolved option id (`"1"` instead of `"spread_nature:1"`) recovered from text before
  the "Unknown build option id" safety net can reject it outright.
- An edit signal dropped entirely (every value field empty, not just malformed) recovered via
  direct text extraction.
- `"+"` recognized as a leading-option-reference separator, alongside comma/"but" — this
  interface's own documented composition syntax ("pick option ids (compose with +)") wasn't
  previously recognized at all.
- The recovery logic itself generalized from `field == "spread"` to
  `field in {ability, item, nature, moves}`, reusing the same `extra_field`/`extra_value` payload
  shape already built for the reverse direction (a present selection with a dropped edit signal).

**Why:** Each of these is a genuinely distinct failure captured live, not inferred — several
initially looked like they might be the same bug, and turned out not to be (e.g. "the model
dropped the item" vs. "the model dropped the option," confirmed as different cases by their raw
extractions, not assumed identical).

**Real regression found and fixed mid-implementation, not before:** the first version of the
generalized single-field-edit resolvability check didn't require exactly one selected option,
so a genuinely ambiguous two-option "compare" request (an existing test: *"make it modest, or
actually compare these two first"*) started being silently resolved as if only one option were
selected. Fixed by requiring exactly one option id for this resolvable shape — two or more is a
different, genuinely ambiguous case (which of several selected options would the edit even apply
to?), not the same well-defined two-step operation. Caught by re-running the full suite before
treating the fix as done.

**Status:** Implemented, tested, merged.

---

### ADR-031 — Amendment 2026-08-18f: general, phrase-free detection over trigger-phrase and
separator lists

**Decision:** Replaced trigger-phrase matching (a fixed list: "use X," "with X," "give it X," …)
with a general scanner that detects any substring matching a real, known value — a real item id,
nature name, or ability name — directly against game data, regardless of how it's phrased.
Separately, generalized option-reference detection for non-spread edits to scan the whole text
(any position, any separator word, or none at all) rather than requiring a specific leading
separator.

**Why:** Direct, repeated pushback, not inferred: *"I don't like having to fix specific
combinations like this... the fix only matches a group of trigger-phrases. Can't we do something
like detecting an id and an item name in the command and resolve it from there?"* — and, once the
value side was generalized, immediately followed by the same critique applied to the
option-reference side: *"even the separator options: and, plus, also... either right after the
leading position or at the end of the sentence."* Both were correct: a fixed phrase or separator
list is guaranteed to keep missing new real phrasings indefinitely, and the fix for one field
(item) would otherwise need re-doing separately for every other field this same failure mode
eventually showed up on.

**What the generalization bought, concretely:** confirmed working with zero new code for phrasing
the old approach could never have matched — "put a Choice Scarf on it," "I want it to hold Life
Orb," "use Choice Scarf and also select 2," "option 2 as well." Two new field types (nature,
ability) came along for free, since the same mechanism applies without modification. Ability
matching is a deduped union across every species' real abilities (311 distinct names) rather than
scoped to the specific target species' actual legal abilities — weaker than the item/nature
checks in that sense, but downstream legality validation already catches an invalid ability for a
given species, so a wrong match here fails safely rather than silently; broader coverage was
judged worth that tradeoff.

**Real, disclosed scope boundary — not silently applied everywhere:** the option-reference
whole-text scan is deliberately NOT applied to spread edits. A stat value is itself a number, and
could coincidentally collide with a real option's numeric suffix — a risk that genuinely doesn't
exist for ability/item/nature/moves edits (none have a numeric value of their own) but does for
spread. Solving that properly needs `extract_single_stat_target` to expose which number token it's
already claimed, so the option-finder can exclude it — considered and deferred as a distinct,
separate piece of work rather than solved partially or silently left inconsistent without comment.
Moves were also not covered by the general value scanner, for a different reason: a moveset edit's
semantics (a full 4-move list, or the conflict-flow's distinct single-substitution case) don't map
cleanly onto "detect one known value in text."

**Status:** Implemented, tested, merged.

---

## ADR-032 — Multi-slot batch locking with sequential refinement

### Status
**Proposed.** No implementation, no discovery, no plan yet. This documents the design
direction and its real open questions honestly, rather than presenting it as more settled than
it is.

### Context
Confirmed via live, unscripted regression testing (2026-08-16/17): a `candidate_selection`
screen presenting Archaludon and Pelipper as two *alternative* starting anchors correctly
rejected "confirm both species" — Cluster A's screen-mismatch gate blocked it, since that
screen structurally represents one choice among alternatives, not two independent picks. This
is correct, intentional behavior, confirmed via direct code trace: `LockPayload.locks`
(`recommender/state.py`) and `_apply_locks_batch` (`recommender/nodes.py`) already support
batch-locking, but only for **multiple attributes on one slot** (`slot_index` is a single,
top-level field shared across the whole payload) — not multiple different slots at once. There
is currently no path, anywhere in the codebase, for locking genuinely different species into
genuinely different slots in a single turn.

### The real distinguishing signal this design depends on
The motivating case that was correctly rejected (two alternatives, one slot) and the case this
ADR proposes to support (two real, complementary picks, two different slots) look superficially
similar in raw text ("both species") but are structurally opposite requests. This design
**only applies to genuinely open, distinct slots** — most naturally, `multi_locked` phase with
several real open slots — never to `candidate_selection`'s single-slot alternative-presentation
screens, which should keep rejecting ambiguous multi-species replies exactly as they do today.
This ADR does not propose changing that existing, correct behavior.

### Proposed design
1. **Require explicit slot-destination language**, not inferred from ambiguity. The system
   should not attempt to guess "multiple species named together" means "lock them into
   different slots" — that's exactly the kind of guess Cluster A's gates exist to prevent. The
   user should name explicit slot destinations (e.g. "lock Archaludon in slot 1 and Kingambit
   in slot 3") or the request should only fire when the number of named species matches the
   number of currently, genuinely open `multi_locked` slots unambiguously.
2. **New payload shape**, likely a real list of `{species, slot_index}` pairs — `LockPayload
   .locks`'s existing shape (`{attr, value}` pairs for one slot) does not fit this and should
   not be overloaded to mean something structurally different.
3. **Sequential refinement after a successful multi-lock**: once multiple slots are locked
   together, the system proceeds through refining each one's full build in the order they were
   locked — first-locked slot refined first, not all queued/batched into one confirmation.

### Open questions, deliberately not resolved here
- Exact new intent name / schema shape for the multi-slot payload.
- How `annotate_composition_impact` and other `multi_locked`-phase machinery interact with a
  multi-lock landing mid-discovery — does each newly-locked slot need fresh composition
  annotation before refinement starts, or does that wait until all locks in the batch resolve?
- UX for the sequencing itself: does refinement of slot 1 (first-locked) begin automatically and
  immediately, or does the system first present a summary of all newly-locked slots and let the
  user confirm the refinement order?
- Whether this needs its own `pending_kind`, reuses `full_build_confirmation` per-slot in
  sequence, or something else entirely.

### Explicit non-goals
- Does not change `candidate_selection`'s existing, correct rejection of ambiguous
  multiple-alternative replies for one slot.
- Does not touch `LockPayload.locks`'s existing single-slot multi-attribute behavior.

#### Next step
A real discovery pass, when picked up — confirming exact `multi_locked` state shape at the
moment multiple slots are genuinely open, and resolving the open questions above before any
design gets locked further.

---

## ADR-033: Multi-signal, per-category candidate presentation — select_diverse_candidates

**Decision:** For the `multi_locked` default/alternatives-selection step specifically (which
candidates to actually present to the user, not the underlying discovery/evidence-aggregation
ADR-026 already covers), replace the single combined ranking with three independently-scored
categories: A (type-synergy + threat-counter breadth), B (support-needs), C
(condition-benefit). Default is a genuine multi-category candidate (confirmed strong — top 3,
and only counting confidence != "low" evidence — in more than one category) when one exists,
otherwise falls back to Category A's top pick. Alternatives fill from each remaining category
in turn. Category B/C candidates must clear a real confidence bar (any evidence item with
confidence != "low") to be eligible at all — other signals (shared-teammate correlation,
additional matching_needs) only rank candidates within a tier, never substitute for one.
Evidence displayed alongside a candidate is scoped to the specific category it won, not the
single highest-quality item across its entire merged evidence tuple. Feeding this step
requires a category-aware top-N pre-cut (`rank_multi_locked_by_category`, each category gets
its own top-10, not one shared top-10) rather than the existing `rank_multi_locked_candidates`.

**Alternatives considered:** Keep refining the single combined ranking's tuple order (already
attempted multiple times this session — `fills_essential_gap` split, shared-teammate
repositioning — each fix surfaced a different symptom of the same underlying problem: one
scalar/tuple ordering cannot represent three genuinely different kinds of value
simultaneously). Use the existing `rank_multi_locked_candidates`/`_rank_key` top-10 cut
unmodified, accepting that Category B/C candidates ranking below 10 by threat-coverage
criteria alone would never be considered.

**Why:** Confirmed via extensive live, unscripted testing across this entire session that a
single ranking — even after several individually-correct fixes — kept surfacing narrow or
context-blind candidate sets: three Steel-type picks piling onto the same shared weakness, or
a real screens/Rain-beneficiary teammate that never entered the top ranks because its value
lives outside what any single score can see. Each of the three sub-fixes was independently
necessary, not redundant: without the confidence-tier gate, a uniformly-weak category (e.g.
every screens candidate sharing the same low-confidence floor, since screens is generated
unconditionally) could still produce a "top-ranked" pick that looks equivalent to a genuinely
strong one. Without evidence-scoping, a multi-signal candidate's displayed evidence could come
from an unrelated, stronger branch (confirmed live: a candidate labeled "support/utility"
displaying its unrelated real threat-counter evidence instead of its actual, weak
support-need match). Without the category-aware pre-cut, the entire architecture was
structurally defeated upstream — confirmed live, real Category B/C candidates (a real screens
setter, a real Rain-beneficiary) were being cut from the pool before this selection logic ever
ran, by an earlier top-10 cut still using the single, old `_rank_key`.

**Status:** Implemented and verified — 1267 tests passing at the end of the session that
introduced it (up from 1174 at branch start). Two real, confirmed bugs found and fixed during
its own development, not glossed over: (1) the multi-signal confidence-gate and the ranking
key both initially iterated a candidate's FULL, unscoped evidence tuple rather than the
evidence relevant to the specific category being evaluated — a candidate with strong,
unrelated evidence (real threat-counter data) could pass Category B's confidence gate purely
because of that unrelated strength; fixed via a shared `_need_branch_evidence` scoping helper.
(2) `rank_multi_locked_by_category`'s categorization logic was extracted into a shared
`_categorize_candidates` helper specifically to prevent it and `select_diverse_candidates`
from silently drifting apart over time.

**Deliberately deferred, disclosed not silently dropped:** the user's chosen orientation
preference (attacker/support/balanced) no longer factors into `rank_multi_locked_by_category`'s
cut at all — neither `_rank_category_a` nor `_rank_by_need_evidence` use it, unlike the old
`_rank_key`'s `preference_fit`. No design decision made on how to fold this back in; flagged
directly as an open question rather than guessed at, given the branch's size at merge time.
"Specialist crowding" (a strong generalist satisfying both threat-counter and support-need
criteria simultaneously can dominate multiple categories, crowding out true specialists) is a
known, disclosed limitation, not addressed this session.

---

### ADR-033 — Amendment 2026-08-21a

**`fills_essential_gap`/`fills_spof_backup_gap` are now consulted by
`_categorize_candidates` — they were computed correctly but never read by
any part of the category pipeline this ADR introduced.**

Confirmed via direct trace: `_FIT_RANK`/`composition_fit` and
`fills_essential_gap`/`fills_spof_backup_gap` were each consumed in exactly
one place — the old `_rank_key` — which this ADR's `select_diverse_
candidates` path bypasses entirely for `multi_locked` presentation. Every
existing test exercising these two fields called `_rank_key` directly, never
`select_diverse_candidates`, so the gap had no test coverage that could have
caught it. `fills_spof_backup_gap` in particular represents a candidate with
no `matching_needs` of its own by design (the anchor's own dependency is
already satisfied, so `query_support_needs` never asks for a backup) — with
`_categorize_candidates` routing candidates into B/C purely by
`matching_needs` category, such a candidate had no category to land in
regardless of how strong its divergence score was. Live symptom: no 2nd
Rain-setter ever got suggested even when that was the real, open need.

`_candidate_fills_condition_gap` now also returns which condition(s) earned
the backup flag. When it fires, real evidence (`branch="need"`,
`basis="synthesized"`, `confidence="medium"`, tagged `condition:<name>`) gets
attached in `annotate_composition_impact` so the candidate can clear
Category B's existing confidence gate (`_has_strong_evidence`) — without
this, routing it into Category B alone would have been silently defeated by
the same gate ADR-033 built to keep weak, unconditional matches out.
`_categorize_candidates` now also checks `fills_essential_gap`/
`fills_spof_backup_gap` directly, not just `matching_needs`.

**Why `fills_essential_gap` is included too, despite likely redundancy:**
the missing-provider case already gets a real `matching_needs` entry through
the normal (unaffected-by-this-fix) `gap_support_needs` path, so this is
probably belt-and-suspenders rather than fixing a second live bug — included
for parity and as a guard against that path being unavailable in some edge
case, not because a second live symptom was confirmed for it specifically.

**Status:** Implemented and verified via PR #108 (merged, commit `656abb4`),
same PR as the ADR-028 amendment above (found in the same live-testing
session; landed together since they compound). Confirmed via a test
isolating a candidate whose *only* signal is `fills_spof_backup_gap=True`
(no `threat_row`, no other `matching_needs`) — fails on pre-fix code with an
empty Category B, passes after. Does not address "specialist crowding"
(already disclosed, unaddressed, as of this ADR's original text) — a
related but distinct live finding this session sharpened: any candidate with
even one weak `threat_row` entry can compete for Category A's top-3 "genuine
multi-signal" default slot on the same terms as a real threat-counter,
structurally disadvantaging dedicated support specialists who rarely rank
well on `verified_score`. No fix decided or attempted; flagged as an open
design question requiring real calc-verified threat data to investigate
further, left for Cursor's own discovery pass.

---

## ADR-034: Mega-form identity resolution in threat-counter discovery (query_counters)

**Decision:** `query_counters` retargets a base species to its dominant mega form when that
base species' real in-game item-usage share shows a specific mega stone dominating usage
(>= 80%, confirmed live: e.g. "Swampert" is 95.5% Swampertite) — using the base form's own
real, strong `usage_rank` for the retargeted mega candidate's popularity, while evaluating its
actual mechanical properties (types/ability/moveset) using the mega form's own real data. For
species without a dominant mega-stone share, `_usage_popularity` falls back to Showdown's
`usage_pct` (a dataset that does track mega forms as separate entries) rather than always
treating a species lacking in-game `usage_rank` as maximally unpopular.

**Alternatives considered:** Give every mega form a weak, always-below-any-real-rank fallback
popularity signal derived from Showdown usage_pct alone (implemented first, in isolation,
before the deeper issue was found). Leave mega forms entirely unranked/absent from
threat-counter discovery.

**Why:** Confirmed live, the real root cause: the offline in-game usage dataset has no
separate entries for mega forms at all — most likely because usage-tracking records the
species brought to the team (base form + mega stone), not the mid-battle mega-evolved state.
This meant every mega form's mechanical evaluation (correctly using its own real ability/stats
via `featured_or_common_set`, confirmed unaffected) was paired with either no popularity
signal at all, or — after the first, shallower fix — a Showdown-usage_pct fallback
deliberately offset far below any real usage_rank so real ranks would always win ties. That
first fix was real and correct as far as it went, but was confirmed live to be structurally
self-defeating: it meant a mega form could correctly qualify as a real, mechanically-verified
counter (confirmed directly: Swampert-Mega's real best_bp against Archaludon, 300.0, exceeds
even the base form's 270.75) yet still always lose the pre-selection top-N cut whenever 20+
real-ranked candidates also qualified — the common case. The retargeting fix instead recovers
which form real popularity actually belongs to, using data the in-game dataset already has
(per-item usage share), directly reusing a design already reviewed and confirmed in an earlier
session (the "≥80%-single-stone heuristic," at the time superseded by a direct Showdown-ladder
query for a different, offline compendium-construction context) rather than reinventing an
approach from scratch — confirmed by searching past conversations before implementing, per
this project's standing discipline around prior decisions.

**Status:** Implemented and verified against real, live-motivating data at each step, not
mocked in isolation — confirmed the exact original live bug (`query_counters` for Archaludon
now reports "Swampert-Mega" directly, Swift Swim/Swampertite/usage_rank=20, not "Swampert"
with Torrent/base stats) is closed. Two real, confirmed bugs found and fixed during
verification: (1) `allowed`/`candidate_pool` filtering checked only the original base species
id against the allowed set, not the retargeted mega form's id — meaning a filter naturally
built from a retargeted candidate's own, correctly-reported name would incorrectly exclude it;
caught by an existing test's real, dynamically-computed data breaking after this change, not a
hand-constructed scenario. (2) Multi-mega-form disambiguation (e.g. Charizard X/Y) initially
compared the wrong strings ("Charizardite Y" and "Charizard-Mega-Y" share no common suffix
beyond the final letter itself) and never matched anything for multi-form species — caught by
a formal test before considering this done, not just the common single-form case.

**Deliberately scoped:** the 80% dominance threshold is a fixed constant

---

### ADR-034 — Amendment 2026-08-22a

**Two real, distinct bugs in the mega-form identity/ranking machinery
this ADR introduced, found via a live question about why Staraptor was
suggested over the empirically more popular Staraptor-Mega.**

**Bug 1, and the actual, complete root cause of the live question:**
`_dominant_mega_form`'s item match required the mega stone's item id to
contain the base species name as an exact substring. Most stones cleanly
append "ite" (`swampert` → `swampertite`, this ADR's original motivating
case), but several trim or alter the base name's ending first:
`staraptor` → `staraptite`, `mawile` → `mawilite`, `floette` →
`floettite`, `sceptile` → `sceptilite`, `dragonite` → `dragoninite`,
`blastoise` → `blastoisinite`. Confirmed directly against real in-game
data: all six have genuine, dominant real mega-stone usage (55-99%),
silently evaluated as their weaker base form indefinitely instead, with
no visible sign anything was wrong. Fixed via a shared-prefix-ratio
fallback (≥70% of the base name's characters matching from the start,
excluding `eviolite` explicitly since it's a real, unrelated item ending
in "ite") when the plain substring check fails — verified against every
base species with a real mega form in the snapshot, not just the six
known cases, confirming the previously-correct 8 retargets are unchanged
and Dragonite (55.4%, genuinely below the 80% dominance threshold)
correctly still returns `None`.

Also fixed multi-alternate-form disambiguation: Blastoise
(`['blastoisemega', 'blastoisegmax']`) and Floette
(`['floetteeternal', 'floettemega']`) each have two real alternate forms,
and the existing disambiguation only ever handled Charizard-style X/Y
suffixes — neither stone name ends in x/y, so both fell through to `None`
despite 95-99% real dominant usage. A "-ite" item is specifically a
mega-evolution mechanic, never a Gmax or other alternate-forme trigger,
so when exactly one candidate actually contains "mega" that's now an
unambiguous match, without needing the narrower X/Y path.

Confirmed via direct `query_counters` call that this fix *alone* fully
resolves the original question — Staraptor now correctly reports as
"Staraptor-Mega" with `usage_rank=11` (its base form's real, strong
in-game rank).

**Bug 2, a separate, real gap — explicitly not what caused the live
question, stated plainly rather than left ambiguous:** `query_counters`'
`_key` sorted every candidate without a real in-game `usage_rank` as
`float("-inf")` — tied at the single worst possible value regardless of
real Showdown popularity. This function's own comment claimed a fallback
(`_usage_popularity`) used `showdown_usage_pct` for exactly this case;
confirmed directly that function doesn't exist anywhere in this
codebase — the fallback data was computed and stored on `ThreatCandidate`
correctly, then silently never consulted. Fixed with an explicit tier:
real in-game rank still strictly outranks Showdown-only candidates
(in-game remains this project's primary data source), but Showdown-only
candidates are now ordered by real relative popularity instead of tied.
Likely affects other mega forms with genuine independent Showdown
popularity but no correspondingly-dominant base-form item share — not
confirmed against a second live case, flagged as a real possibility, not
verified further.

**Two of Claude's own test-construction mistakes caught and corrected
during verification, not shipped uncorrected — worth keeping in the
record as a caution for future work on this function, not just a
footnote:** an existing test (`test_owned_last_only_breaks_a_complete_
query_key_tie`) mined the live snapshot for a coincidental tie among
`usage_rank=None` candidates; that tie no longer exists once bug 2 is
fixed (real Showdown data now differentiates almost every candidate —
confirmed zero candidates in the test query lack both signals entirely),
so it was rebuilt to construct a deliberate, controlled tie via a patched
`showdown_species_map`. Separately, an initial version of the new bug-2
regression test passed on *both* old and new code — traced to a wrong
assumption that `candidate_pool` ordering controls tie-break order, when
it only filters which species are allowed; the real stable-tie order
comes from the raw snapshot dict's own key ordering. Rebuilt to determine
that order directly and assign test data against it deliberately.

**Status:** Implemented and merged (PR #117). 6 new/updated tests, each
confirmed to fail on pre-fix code and pass after. Full suite: 1299
passed, 8 skipped.

---

### ADR-034 — Amendment 2026-08-23a

**Two real, distinct bugs found via a live question about why Staraptor
was suggested over the empirically more popular Staraptor-Mega.**

**Bug 1, the actual root cause:** `_dominant_mega_form`'s item match
required the mega stone's item id to contain the base species name as an
exact substring. Most stones cleanly append "ite" (`swampert` →
`swampertite`), but several trim or alter the base name's ending first:
`staraptor` → `staraptite`, `mawile` → `mawilite`, `floette` →
`floettite`, `sceptile` → `sceptilite`, `dragonite` → `dragoninite`,
`blastoise` → `blastoisinite`. Confirmed directly: all six have genuine,
dominant real mega-stone usage (55-99%), silently evaluated as their
weaker base form indefinitely instead. Fixed via a shared-prefix-ratio
fallback (≥70% of the base name's characters matching from the start)
when the plain substring check fails — verified against every base
species with a real mega form in the snapshot, confirming the
previously-correct 8 retargets are unchanged and Dragonite (55.4%,
genuinely below the 80% dominance threshold) still correctly returns
`None`. Also fixed multi-alternate-form disambiguation (Blastoise:
mega vs. Gmax; Floette: mega vs. eternal) — a "-ite" item is specifically
a mega-evolution mechanic, so when exactly one alternate actually
contains "mega," that's now an unambiguous match. Confirmed via direct
`query_counters` call that this fix alone fully resolves the original
question.

**Bug 2, a separate, real gap — explicitly not what caused the live
question:** `query_counters`' `_key` sorted every candidate without a
real in-game `usage_rank` as `float("-inf")` — tied at the worst
possible value regardless of real Showdown popularity. The comment
historically here claimed a fallback function used `showdown_usage_pct`
for exactly this case; confirmed that function doesn't exist anywhere in
this codebase. Fixed with an explicit tier: real in-game rank still
strictly outranks Showdown-only candidates, but Showdown-only candidates
are now ordered by real relative popularity instead of tied.

Two of Claude's own test-construction mistakes were caught and corrected
during verification, not shipped uncorrected — a stale-tie test that
depended on real-data coincidence no longer possible post-fix, and an
initial regression test that passed on both old and new code due to a
wrong assumption about what controls iteration order.

**Status:** Implemented and merged (PR #117). 6 new/updated tests, each
confirmed to fail on pre-fix code and pass after. Full suite: 1299
passed, 8 skipped.

---

## ADR-035: Core-slot scarce-resource discount and bench-slot coverage-subset
reframing — two unified pieces of the same principle

**Context:** Live testing (2026-08-21) surfaced Swampert-Mega (real Rain-abuse value)
ranking as a top-3 threat-coverage pick for a core slot on a team already committed to
Sun via a locked Charizard-Mega-Y — Sun and Rain are mutually exclusive, so its actual
distinguishing strength could never fire on this team as built. Separately,
`mega_ceiling_notices` already correctly computed how many mega-stone holders a team can
usefully carry, but that signal was purely informational — never wired into ranking at
all, the same "signal computed but discarded" shape as `fills_spof_backup_gap` (ADR-026
Amendment 2026-08-17a) and this session's screens/Castform findings.

**Decision, part 1 (implemented): `candidate_wastes_core_slot`.** Both symptoms are the
same underlying principle: a candidate's real strength depends on a scarce, single-use
team resource (one weather, one mega evolution per battle) already claimed in a
*conflicting* way by something locked in. The check is scoped specifically to core-slot
construction (`slot_index < picked_team_size`) — confirmed directly in design discussion
that a second weather or mega is legitimate, real alternate-core bench value once the
core is settled (a Sun-core and Rain-core variant sharing the same locked anchors, swapped
in per matchup), not something to discourage there. Triggers on exactly two conditions,
nothing else: (a) the candidate requires a mega stone and a locked slot already holds a
*different* mega-stone base lineage; (b) the candidate has a real, `needed`-importance
`benefits_from` mechanism for a weather different from one a locked slot already
`provides`. `wastes_core_slot` pushes a candidate to the bottom of its category regardless
of raw score — wired into `_rank_category_a`, `_rank_by_need_evidence` (Category B/C), and
`_rank_key` (`discover_single_locked`'s remaining "obvious need" path).

**Decision, part 2 (implemented, deliberately NOT wired into ranking yet):
`candidate_improves_best_bring`.** Only `picked_team_size` of a roster ever actually plays
together in a given game — Category A has been asking the wrong question for slots beyond
the core ("does this add more stackable coverage," which assumes the whole roster fields
simultaneously). The right question is "does this candidate improve some real, coherent
bring-N combination." No plausibility filter on which combinations count — confirmed in
design discussion that almost any coherent combination of real picks is somebody's
legitimate answer to some real matchup, so there's no principled way to exclude one ahead
of time. Compares the best (fewest uncovered, then fewest spof) gap counts achievable from
any `pick_count`-sized combination of the locked roster alone against the best achievable
once the candidate is added.

Deliberately does not weight by threat severity: `MatchupResult.severity` is always the
placeholder `"toss-up"` for a genuine `no_answer` outcome, not a real signal — a real
severity-aware version needs the threat objective's own baseline severity classification,
not something this function has access to. Logged as a known, undertaken refinement.

**Wiring deferred pending a design refinement, not just a performance question.**
`candidate_improves_best_bring` is O(C(N, pick_count)) subset evaluations per candidate;
naively running it over a full bench-slot candidate pool multiplies real calc calls.
Design discussion (2026-08-21/22) converged on a cheaper, more correct approach than raw
enumeration: a candidate with an unmet `needed` dependency (e.g. Mega-Swampert wanting
Rain) must be evaluated *jointly* with a real provider of that dependency drawn from the
same candidate pool, not independently — both because independent evaluation is
combinatorially wasteful, and because `team_field_states` only forces a weather onto a
subset's matchup calc if that subset actually contains a real provider, so evaluating a
dependent candidate alone produces an honestly *wrong* (unamplified) coverage number for
it, not just an incomplete one. This reframes wiring from a search problem into direct
slot arithmetic (does a real provider exist in the remaining pool, is there an open slot
left to hold it) for the coupled case, with the full subset primitive reserved for
candidates with no hard dependency. Not yet implemented.

**Verification:** `candidate_wastes_core_slot`: 4 tests, each confirmed to fail on pre-fix
code and pass after, verified against real data (Swampert-Mega/weather, Metagross-Mega/
second-mega, Garchomp/no-conflict, both core and bench slot cases).
`candidate_improves_best_bring`: 3 tests built with real, deterministic `MockCalcClient`
scenarios (existing `test_coverage.py` convention), not synthetic pre-computed coverage
results — exercises the actual `compute_team_coverage`/`detect_spof` calls with scripted
calc responses. One test's own premise was caught as wrong during verification (assumed a
baseline with zero uncovered gaps couldn't be improved; the real behavior — a second
answer closing an existing SPOF is genuine improvement — was correct, the test's scenario
was fixed, not the code). Full suite: 1288 passed, 8 skipped at part-1 merge; 1287 passed,
8 skipped at part-2 merge.

**Deliberately out of scope for this ADR, scoped separately in design discussion (not
implemented):** masked alternate-core discovery (re-running discovery against a masked
locked slot when a strong conflicting candidate is found, rather than just ranking it
down); generalizing `wastes_core_slot`'s dependency detection beyond weather/mega to any
`needed` condition (blocks Mega-Mawile/Trick-Room-style cases); orientation-narrowing at
the bench-slot boundary (asking the user which of coverage/support/alternate-core they
want before presenting candidates, sharpening the still-unaddressed ADR-033 orientation-
preference gap).

---

### ADR-035 — Amendment 2026-08-22a

**Part 2 (bench-slot coverage-subset) is now wired into `_rank_category_a`,
completing what the original ADR left deliberately unwired.**

Scoped specifically to the "simple case" from that design discussion:
candidates with no unmet needed-importance weather dependency. For bench
slots (`slot_index >= picked_team_size`) with a real, `picked_team_size`-
sized core already locked, `annotate_composition_impact` constructs a
hypothetical `Slot` for the candidate (`coverage.spec_to_slot`) and calls
`candidate_improves_best_bring` with the real threat objective, now
threaded through via a new `objective` parameter from
`discover_multi_locked`. Result populates a new `improves_bench_subset`
field, wired into `_rank_category_a`'s sort key as a leading
discriminator — a no-op (constant) for core slots, meaningful only for
bench slots, positioned the same way `wastes_core_slot` sits at the
opposite end of the same tuple.

`candidate_has_unmet_needed_weather_dependency` (new) reuses the same
`mechanism_condition`/`provided_conditions` check as
`candidate_wastes_core_slot`'s weather half, asking a different question:
not "does this conflict" but "is this dependency unmet at all." This gate
is a correctness requirement, not just a scope limitation — evaluating a
dependent candidate (Mega-Swampert-shaped) alone would produce an
honestly *wrong* coverage number, since `team_field_states` only forces a
weather onto a subset's matchup calc if that subset actually contains a
real provider. Dependent candidates remain deliberately unevaluated
(neither credited nor penalized) pending masked alternate-core discovery,
which is the capability actually equipped to pair them with a real
provider correctly.

**Verification is honestly incomplete in one respect, disclosed rather
than glossed over:** no live calc service was available to verify the
real, live behavioral change end-to-end — the same limitation as all of
Category A's testing this session. Verified instead that the wiring
itself is correct by mocking `candidate_improves_best_bring` at its
source module boundary (confirmed via `recommender.coverage`, not
`recommender.team_candidates` — it's a local import, discovered by
hitting the `AttributeError` this produces when patched at the wrong
module first), trusting that function's own already-verified correctness
(real `MockCalcClient` scenarios, this ADR's original text). Live-tested
afterward against a real transcript (Archaludon/Pelipper/Swampert-Mega/
Sinistcha core, deciding Grimmsnarl's slot) and traced the gate's
activation directly: it correctly switches on for that exact state, and
all three real bench candidates (Mawile-Mega, Grimmsnarl, Basculegion)
correctly reach the real calc-dependent check — the observed identical-
to-`main` output for that specific team is consistent with the wiring
correctly finding no real subset improvement available for an already
well-covered core, not with the wiring failing to activate.

**Status:** Implemented and merged (PR #116). 3 new tests, each confirmed
to fail on pre-fix code (`TypeError` on the new `objective` kwarg) and
pass after. Full suite: 1298 passed, 8 skipped.

---

### ADR-035 — Amendment 2026-08-23a

**Part 2 (bench-slot coverage-subset) is now wired into `_rank_category_a`,
completing what the original ADR left deliberately unwired.**

Scoped to the "simple case": candidates with no unmet needed-importance
weather dependency. For bench slots with a real, `picked_team_size`-sized
core already locked, `annotate_composition_impact` constructs a
hypothetical `Slot` for the candidate and calls
`candidate_improves_best_bring` with the real threat objective, threaded
through via a new `objective` parameter from `discover_multi_locked`.
Result populates `improves_bench_subset`, wired into `_rank_category_a`'s
sort key as a leading discriminator — a no-op for core slots, meaningful
only for bench slots, mirroring `wastes_core_slot`'s position at the
opposite end of the same tuple.

`candidate_has_unmet_needed_weather_dependency` (new) reuses the same
`mechanism_condition`/`provided_conditions` check as
`candidate_wastes_core_slot`'s weather half, asking a different
question: not "does this conflict" but "is this dependency unmet at
all." Evaluating a dependent candidate alone would produce an honestly
*wrong* coverage number — `team_field_states` only forces a weather onto
a subset's matchup calc if that subset actually contains a real
provider — so this gate is a correctness requirement, not just a scope
limitation. Dependent candidates remain deliberately unevaluated
pending masked alternate-core discovery (ADR-038), which is the
capability actually equipped to pair them with a real provider correctly.

Verification could not confirm the real, live behavioral change
end-to-end — no live calc service available. Verified instead that the
wiring itself is correct by mocking `candidate_improves_best_bring` at
its source module boundary, trusting that function's own
already-verified correctness. Live-tested afterward against a real
transcript and confirmed the gate correctly activates and reaches the
real calc-dependent check for all real bench candidates.

**Status:** Implemented and merged (PR #116). 3 new tests, each
confirmed to fail on pre-fix code and pass after. Full suite: 1298
passed, 8 skipped.

---

## ADR-036: Dependency-reliability ranking — a soft demotion for candidates
whose real enabler isn't a genuine specialist

**Context:** Mawile-Mega's real Trick Room dependency can be nominally
"satisfied" by a locked Sinistcha whose real, aggregate Trick Room
commitment (57.2%) is barely more than a coinflip against its actual
defining move, Rage Powder (95.6%) — Sinistcha's real primary job is
redirection, not a genuine Trick-Room-specialist build the way Farigiraf
is. Nothing in the existing pipeline distinguished "a real provider
exists" from "a real, trustworthy specialist provides it."

**Decision:** `candidate_dependency_reliability` (condition_resilience.py)
computes a 0.0-1.0 score for a candidate's worst-case dependency, used as
an additional soft rank-sum dimension in `_rank_category_a` (team_
candidates.py) — never a hard gate, unlike `wastes_core_slot`. Ability-
based providers (Drizzle, etc.) are always 1.0 — mechanically certain,
the same reasoning already established for ability-based evidence
confidence (ADR-028 Amendment 2026-08-20a). Move-based providers use
real in-game commitment percentage for the specific providing move. A
real data gap (provider absent from the in-game dataset) defaults to 1.0,
not penalized as a negative signal (the same principle established in
ADR-034 Amendment 2026-08-23a for a different purpose).

Generalizes dependency detection beyond weather (`candidate_wastes_core_
slot`'s scope) to all six TRACKED_CONDITIONS, since Mawile-Mega's
dependency is Trick Room, not weather. Deliberately includes both
"needed" and "wanted" importance tiers, unlike `candidate_wastes_core_
slot`'s stricter "needed"-only gate — confirmed directly that every
Trick Room/Tailwind `benefits_from` mechanism in this codebase is
classified "wanted", never "needed" (weather-move dependencies like
Electro Shot/Rain are the ones that get "needed" — a real, deliberate
distinction: a hindering-nature/slow-attacker TR preference is inherently
softer and inferred, not tied to a specific locked move). Also does not
require `mechanism.present` — "wanted" dependencies are typically
`present=False` by design (inferred from role/nature, not concretely
move-locked).

**A real, unplanned finding along the way:** while building this
feature's own dense-rank tie-handling (to avoid injecting a spurious
per-candidate offset when every candidate ties on `dependency_
reliability`, the common case), directly demonstrated the SAME bug
already existed in the pre-existing `verified_rank`/`synergy_rank`
computations in `_rank_category_a` — not hypothetical: constructed a
case where two arbitrary tie-breaks exactly cancelled out, letting a
candidate with 8x worse `verified_score` (0.5 vs 4.0) win purely from
input list order, with both raw signals genuinely, correctly computed
and differentiated. Fixed all three rank dimensions uniformly with a
shared `_dense_rank` helper rather than leaving the two pre-existing
ones broken.

**Verification:** 9 new tests — 5 for the reliability primitives
directly against real data (Sinistcha 0.572, Farigiraf 0.952, ability-
based always 1.0, no-provider defaults to 1.0, no-dependency always
1.0), 2 for `_rank_category_a` wiring (soft nudge, not exclusion), 1
explicitly locking in the dense-rank fix with a concrete, non-contrived
demonstration. Full suite: 1309 passed, 8 skipped.

**Status:** Implemented and merged (PR #118).

---

## ADR-037: Redundant single-purpose speed-control demotion

**Context:** Found via live testing (2026-08-22) immediately after PR
#118 merged. Aromatisse (a single-purpose, compendium-backed `trick_
room` match) kept outranking genuinely multi-purpose real alternatives
(Sableye: screens + backup rain; Grimmsnarl: screens + disruption)
despite a locked Pelipper already providing Tailwind.

**A real correction made before implementation, not glossed over:**
first proposed as a `candidate_wastes_core_slot`-style hard conflict,
mirroring the weather/mega scarce-resource check. Corrected directly by
Vu: Trick Room and Tailwind are NOT mutually exclusive — a team can
legitimately run both. The real issue is narrower: a candidate whose
ENTIRE real support-need value is `trick_room` or `tailwind` alone, with
nothing else, is genuinely lower value once the team already has some
real speed control — not because they conflict, but because a single-
purpose pick offering only a partially-redundant thing has less to offer
than a multi-purpose one. Same "cumulative remaining value" principle
already established for Sableye's screens+backup-rain case (ADR-026
Amendment 2026-08-17a), applied to a new, narrower trigger condition.

**Decision:** `_rank_by_need_evidence` (team_candidates.py) gets a new
soft demotion tier, same shape as the existing `wastes_core_slot`/`_is_
backup_only` tiers — a candidate whose `matching_needs` is entirely a
subset of `{trick_room, tailwind}` ranks behind others once `provided_
conditions` confirms the team already has real speed control from
either. Deliberately does not fire when the team has no speed control
yet (a genuinely-needed single-purpose match stays un-demoted), and does
not fire for a multi-purpose candidate (real screens + trick_room both)
even when its speed-control half is redundant, since its other purpose
remains real, undiminished value.

**Verification:** 4 new tests, each confirmed to fail on pre-fix code
and pass after: redundant single-purpose TR demoted below a lower-
confidence but non-redundant screens candidate; not demoted with no
speed control locked at all; a multi-purpose candidate not demoted
despite redundant TR. Full suite: 1305 passed, 8 skipped.

**Explicitly not addressed here, from the same live-testing session —
handed to Cursor for discovery (2026-08-24):**
- Sinistcha's displayed "trick_room_setter" label vs. its real primary
  role (redirection, confirmed via Rage Powder 95.6% vs Trick Room 57.2%
  real commitment) — fresh evidence for the already-known, deprioritized
  role-label-accuracy backlog item, not fixed here.
- Orientation preference confirmed (again, via direct code trace) to
  never reach actual candidate ranking — the ADR-033 gap, still open.
- A possible reject-parsing reliability issue — traced through three
  candidate-pool mechanisms (exclusion set construction, categorization,
  default/alternatives selection), all three structurally correct for
  the "ran out of candidates" theory, meaning any real bug here is
  likely in a layer (state propagation, LLM intent classification) not
  verifiable through static code review alone.

**Status:** Implemented and merged (PR #119).

---

## ADR-038: Masked alternate-core discovery

When a core-slot candidate is independently strong (Category A top-3
with `wastes_core_slot` ignored, real calc-verified evidence, and
`usage_backed` basis) and conflicts with a locked member over an
exclusive resource (weather or mega evolution), the system now offers
labeled `core_resolution` options: keep the current core (the existing
rank-down, unchanged) vs. each real masked package. Masking excludes the
conflicting locked slot(s) from needs and field-state computation only —
kits stay locked, never rebuilt; the masked member still counts for mega
ceiling and Item Clause. Identity comes from `candidate_core_slot_conflicts`
(new — names the locked slot/species/resource), with
`candidate_wastes_core_slot` remaining a `bool()` wrapper over it so
existing ranking is untouched.

Gap-fill (`discover_masked_core_package`) is a pure function reuse of
merge/annotate/rank — deliberately not a graph re-entry, enforced by a
code-review gate (the engine module has no `nodes` import). Cascades by
consuming one genuinely fresh open slot per step until the roster ends;
a sole remaining provider of a hard dependency on the last open slot is
unmaskable for the rest of that build — no artificial recursion-depth
cap needed, roster size (max 6) is the natural stopping point. Package
ranking requires two signals to agree: lift-adjusted pairwise teammate
correlation plus real group co-occurrence (`query_shared_teammates`),
and calc-verified + `usage_backed` evidence — specifically to guard
against Mega-Mawile/Tinkaton-shaped false positives (mechanically
plausible, not actually good). Accepting a package sets
`masked_slot_indices` and locks only the current-slot candidate via
`slot_candidate_selected`; the shown gap-fill preview (e.g. a rain
setter) is not itself pre-locked — it's what normal discovery will
likely surface next, not a commitment made in the same action.

**Deliberately out of v1 scope, disclosed rather than silently absent:**
Mawile-Mega/Trick-Room-shaped conflicts do not trigger this path — TR
`benefits_from` is always "wanted," never "needed," and TR is not
exclusive with Tailwind, so generalizing the trigger to all
`TRACKED_CONDITIONS` would not correctly catch this case; it stays on
`candidate_dependency_reliability`'s ranking-only treatment instead.
Candidates whose Category A top-3 status depends entirely on the masked/
hypothetical field will not trigger exploration in v1 — the trigger bar
deliberately checks against the *current* field to avoid a full recalc
before a package is known to exist, so a candidate that's only strong
once the mask is applied is invisible to the trigger. Build-level kit
edits on locked members, folding `team_completion_preference` into
category-rank, and a formal cascade-mask-growth safeguard are all
explicitly not attempted.

**Amendment 2026-08-24a — `_calc_agrees` pessimistic-default fix, landed
before merge, not a separate PR.** The dual-signal calc gate
(`_search_gap_fill`) originally defaulted to `True` ("agrees") whenever
`picked_team_size` was unset, the threat objective was empty, or the
working roster was smaller than pick size — the opposite of
`candidate_improves_best_bring`'s own established "insufficient baseline
→ not favorable" convention, and a real gap: it let a package present
with a silently weaker verification basis specifically in early-game
scenarios, exactly when a real calc backstop matters most. Fixed to
return `False` in all three cases, unified into one branch (empty
objective and insufficient roster both mean "nothing was actually
verified"). `should_try_masked_core` additionally now requires
`unmasked_locked + 1 >= picked_team_size` before it fires at all, so the
`core_resolution` UI never presents when it's already known upfront that
calc verification can't succeed — with `pick = 4` and a typical 1-slot
mask, `core_resolution` cannot trigger until 4 real members are locked;
slots 1-3 get rank-down only. Confirmed via direct diff this was a real,
not-yet-caught bug — no test in the original PR covered either
pessimistic-default path.

**Status:** Implemented and merged (PR #121, including the amendment
above before merge). Full suite: 1338 passed, 8 skipped.

---

### ADR-038 — Amendment 2026-08-26a — Masked-alternate-core reachability fix

**Context:** Live discovery (2026-08-26) found that masked-alternate-core
discovery, as specified in ADR-038, was unreachable on the normal sequential
4-lock fill path. `is_core_slot` (`open_slot_index < picked_team_size`) was
the sole gate for both rank-demotion (`wastes_core_slot`) and conflict
computation feeding `should_try_masked_core`. ADR-038's own prior amendment
(2026-08-24a) states core_resolution should trigger once 4 real members are
locked — but on sequential fill, filling slot 5 means `open_slot_index=4`,
which is `>= picked_team_size`, so `is_core_slot` is False and conflicts
were never computed. The feature only ever fired on out-of-order ("gap-lock")
fill patterns, never on the sequential path most users take.

A global redefinition of `is_core_slot` was evaluated and rejected: `is_core_slot`
also gates bench-subset evaluation (`improves_bench_subset`) with the opposite
polarity, and redefining it to a lock-count-based check regresses both
bench-subset wiring and 3-lock rank-demotion behavior, each with existing
test coverage.

**Decision:** Split the single flag into two independent conditions:

- `is_core_slot` (unchanged, index-based) continues to gate rank-demotion
  (`wastes_core_slot`) and bench-subset eval — no change to either path.
- New `detect_core_resource_conflicts(state_locked, picked_team_size)` —
  `True` once `len(state_locked) >= picked_team_size`, computed from
  state-level locks (not gap-fill working rosters) — gates whether
  `core_slot_conflicts` is populated at all.
- `candidate_core_slot_conflicts` is now invoked whenever *either* condition
  holds (`is_core_slot or detect`); `wastes_core_slot` and `core_slot_conflicts`
  are then derived separately from that shared raw result, each gated on its
  own condition.
- `should_try_masked_core`'s first gate now checks `core_slot_conflicts`
  non-empty, not `wastes_core_slot` — decoupling the masked-core trigger from
  rank-demotion entirely.

Bench-subset eval and masked-core conflict detection can now both be true for
the same candidate at the same slot (confirmed as intended: they answer
different questions — remaining threat coverage vs. scarce-resource waste —
with no reason one should suppress the other). The 3-locked/filling-core-slot
case remains demote-only, consistent with both existing tests and ADR-038's
"4 real locks" trigger condition.

**Consequence:** Masked-alternate-core discovery now reaches
`core_resolution` on sequential fill once 4 real members are locked, verified
via live transcript replay (Metagross-Mega surfaced as the conflict candidate
on a sequential sun-core fixture, not Swampert — `independently_strong_category_a`
still gates which species can trigger, unchanged). `is_core_slot`'s definition,
bench-subset gating, and rank-demotion semantics are untouched. New tests
(`tests/recommender/test_masked_core.py`, Tests 0–5) cover the helper, the
annotation split, the decoupled trigger, the 3-lock negative case, and
bench/conflict coexistence. Full suite: 132 passed, 1 skipped (CALC_LIVE-gated
integration test). PR merged off `fix/masked-core-reachability`.

---

## ADR-039: Orientation preference — real per-preference selection
shapes, a revision escape hatch, and deterministic reject-N

**Context.** The soft category-order nudge from a prior attempt
(referenced in ADR-033 discussion but never merged — built on a
contaminated branch and discarded, see below) did not match the real
intended behavior. Confirmed directly with Vu: each of the three
preferences needed a genuinely distinct selection shape, not a shared
ranking nudge.

**Decision — three real shapes in `select_diverse_candidates`:**
`attacker` hard-excludes Category B as a selection source (B is
excluded as a source, not as a species attribute — a dual-branch
candidate with real A-side value may still appear via Category A).
`balanced`/unset picks exactly one candidate per category (A→B→C),
lineage-deduped, skipping the prior "genuine multi-signal default"
detection entirely since that logic could cover fewer than three
distinct categories with one multi-signal pick. `support` draws multiple
candidates from Category B specifically, diversified by
`SupportNeed.category` via new `_diversify_by_need_category` — greedy
new-category-first, then (per Amendment 2026-08-24b below) duplicate-
profile-aware fallback, then pure-rank fill only as a last resort.

**A real process failure worth recording plainly:** the first
implementation attempt was built via a cloud-agent workflow whose local-
sync step swept in a large, unrelated contaminated commit (most of the
masked-core implementation in a partial, pre-fix state, plus four
unrelated debug scripts) as the base the real feature was built on top
of. This surfaced only on review (5 real test failures on that branch,
confirmed absent on clean `main`) and could not be resolved by rebase —
the branch was discarded and the real feature (functionally identical,
verified line-for-line against what had already been reviewed) rebuilt
fresh, locally, off current `main`. No functional design was lost; only
the branch history was.

**Decision — preference-revision escape hatch (PR #123).** A user can
request a different orientation preference mid-`candidate_selection`
("different focus" and near-synonyms, a fixed deterministic phrase set,
deliberately not LLM-classified). Mechanism is `continue` + a state
patch (`team_completion_preference: None`, `pending_presentation: None`,
`force_completion_preference_prompt: True`) — not a new `turn_intent`,
not `archetype_change`/`reset` (both verified wrong semantics).
`rejected` is untouched by revision — a species rejected under one
preference stays rejected after the preference changes. The one-shot
force flag exists because `discover_multi_locked` normally skips the
preference prompt when `material_completion_preferences()` returns
empty (all three orderings identical) — without the flag, an explicit
revision request could silently fail to re-prompt. Confirmed directly
against the real code that the flag correctly survives a
`core_resolution` intercept (masked-alternate-core-discovery's own
early-return path, which sits before the preference-prompt check) —
verified with a real, non-vacuous test, not assumed.

**Decision — deterministic reject-N, shipped in the same PR.** `reject
N`/`reject option N` on `candidate_selection` now resolves to a direct
`rejection` intent via regex, not LLM classification. Out-of-range N
falls through to the existing LLM path rather than erroring (so "reject
Tornadus" still works). Gated specifically to `kind == "candidate_selection"`
via an extracted `_classify_candidate_selection_reply` helper, so future
schema-v1 kinds can't silently inherit this behavior.

**Amendment 2026-08-24a — subset-redundancy in `_diversify_by_need_category`'s
fallback, and an uncapped Category-B pool for `support` (PR #124).**
Live testing surfaced the actual original complaint (support preference
showing 3 `trick_room_setter` candidates) as two compounding causes, not
one: (1) the fallback phase had zero category awareness, admitting a
fully-redundant-profile candidate once genuinely new categories were
exhausted; (2) Category B was capped to the same 10-candidate slice used
for A/C, excluding a genuinely different-category real candidate
(confirmed reachable only via manual rejection) from ever being
considered. Fixed both: fallback now skips a candidate whose exact
support-need-category profile duplicates an already-picked one before
falling back to pure rank; Category B is genuinely uncapped for the
support path specifically (`category_b_uncapped`), not bumped to a
larger fixed number — `_diversify_by_need_category`'s own output stays
bounded to `n_alternatives + 1` regardless of input size, so widening
the input pool carries no real cost. A dead loop (an exact duplicate of
the greedy pass, mathematically guaranteed to find nothing) was found
and removed during this fix, not left as harmless redundancy.

**Amendment 2026-08-24b — the confidence gate and per-candidate
commitment weighting (PR #125).** Root-caused, not assumed: the fallback
fix alone did not resolve the symptom, because a screens candidate with
genuine 86%+ real commitment (Grimmsnarl) was being filtered out
*before* diversification ever ran. Unconditional-trigger support needs
(`trigger is None`, e.g. screens) were blanket-downgraded to `low`
confidence regardless of the *candidate's* real commitment to filling
them — conflating "is this need category conditionally specific" with
"is this candidate's real commitment strong," the same distinction
already established for `candidate_dependency_reliability`. Fixed to
reuse that exact pattern: unconditional needs stay low unless the
evidence is `usage_backed` with a real `commitment_pct` tag (in-game
data only, deliberately never falls back to Showdown-only data for this
purpose — a species absent from the in-game snapshot, like Klefki, has
no reliable per-move commitment signal available, and Showdown data
alone was confirmed to give an actively misleading picture for Klefki
specifically, not just an incomplete one). Separately, `_diversity_need_categories`
now discounts a matched need category from diversification credit when
its evidence is Role-Compendium-tier "Acceptable" with no real
commitment backing — Klefki's real primary job is screens (confirmed:
its `trick_room` match is Acceptable-tier, no commitment data,
correctly dropped from its diversification profile; its `screens` match
survives). The *displayed* role label (`target_role_from_needs`) is
still unresolved — same open backlog item as Sinistcha, now with Klefki
as a second confirmed case, not fixed in this PR.

Reject is now lineage-expanding for sticky-ban purposes (rejecting one
Gourgeist form correctly excludes the others), and `RejectedEntry.need_categories`
feeds a new `SlotFillContext.banned_profiles`, so a rejected candidate's
whole profile stays excluded across the rest of the reject cycle for
`support` specifically — the mechanism that most directly fixed the
live "cycling through 8 near-identical TR setters" complaint.

**Known, disclosed, not yet fixed — carried forward, not silently
dropped:**
- The sticky-ban/subset-redundancy protection above is scoped to
  `_select_support` only. `_select_balanced` (and possibly `attacker`,
  if a B candidate ever surfaces there) has no equivalent protection —
  confirmed live, the identical "cycle through many near-duplicate TR
  setters" symptom reproduces under `balanced` preference, just via a
  different code path.
- `Grimmsnarl` (and any candidate whose gate-passing evidence is a
  `usage_backed`/`commitment_pct` entry that ranks below a `compendium_backed`
  entry on the same candidate) still *displays* a misleadingly low
  confidence — `_format_best_evidence`'s basis-first tuple comparison
  ranks `compendium_backed` above `usage_backed` for display purposes,
  independent of and unrelated to the gate fix above. Real, narrow,
  not yet fixed.
- A confirmed regression, not yet fixed: `_NEED_SATISFIERS["fake_out_protection"]`
  still lists redirection moves as valid satisfiers, despite this exact
  mechanical error (redirection cannot stop Fake Out — priority +2 vs.
  +3) having been identified and removed from a different layer
  (`_compendium_roles_for_need`) in an earlier session (2026-08-21).
  The raw move-satisfier layer was never updated to match.
- A deeper, unresolved design question, deliberately held rather than
  guessed at: whether "protection" needs (`fake_out_protection`,
  likely `taunt_disruption`) should be structurally demoted below the
  needs they protect, given they are inherently softer — and whether
  the "glass offense" trigger for `fake_out_protection` specifically
  (as opposed to `requires_setup_turn`, which has a cleaner mutual-
  exclusivity rationale) survives scrutiny given every Pokémon already
  has universal access to Protect. Not scoped, not scheduled.
- Whether real need-detection systematically under-generates several
  entire `NeedCategory` values (`fake_out_protection`, `taunt_disruption`,
  `defensive_coverage`, `stat_lowering_partner`) for realistic teams,
  independent of anything the diversification-layer fixes above can
  address — flagged, not yet investigated.

**Status:** Implemented and merged (PR #122, #123, #124, #125). Full
suite at last verification: 1356 passed, 12 skipped (environment-only
skips — live calc, ollama).

---

## ADR-040: Sticky-ban parity for balanced preference, and commitment-preferred
evidence for display and ranking

**Context.** Live testing surfaced two gaps in the just-shipped support-preference
fixes (ADR-039). First: `balanced` preference reproduced the exact original
"cycle through near-duplicate TR setters" symptom, since `_select_balanced`
never called `_diversify_by_need_category` and had no `banned_profiles` check at
all. Second: Grimmsnarl displayed "compendium_backed, low confidence" despite
genuinely passing the strong-evidence gate via a real, commitment-backed
`usage_backed` entry (86%+ on both Light Screen and Reflect) — `_BASIS_RANK`
ranks `compendium_backed` above `usage_backed`, so the best-evidence selector
picked the lower-confidence entry purely on basis, independent of confidence.

**Decision, sticky-ban only, not full diversification.** `_select_balanced`'s
Category-B pick now checks `banned_profiles` before taking the first
lineage-new candidate — deliberately NOT wired to the rest of
`_diversify_by_need_category` (the new-category-first greedy pass would
change *which* B candidate gets chosen even on the very first presentation,
a second, unrelated behavior change `balanced` never asked for). Subset-
redundancy (comparing multiple simultaneous B picks) was confirmed to have no
meaningful transfer to a single-pick context — `balanced` never shows more
than one B candidate at once, so there's nothing for it to deduplicate
against; the cross-turn reject-cycling frustration is sticky-ban's job alone.

**Decision, commitment-preferred evidence.** When the best-ranked evidence by
`(_BASIS_RANK, _CONFIDENCE_RANK)` is a `compendium_backed` entry, and a
`usage_backed` entry with a real `commitment_pct` tag exists at strictly
higher confidence, the commitment-backed entry is now preferred — for both
display (`_best_evidence_row`, present_text.py) and ranking
(`_rank_by_need_evidence`'s own best-evidence selection, team_candidates.py).
Extended to ranking deliberately, not just display: a label that reads better
than the underlying decision-making is worse than an honestly-low one, since
it invites trust the ranking hasn't earned. `_BASIS_RANK`'s general ordering
is untouched — this is a narrow override for the specific case where a
real, quantified commitment signal is available and clearly stronger.

**Status:** Implemented and merged (PR #126, #127). Full suite green.

---

## ADR-041: Fake Out redirection regression fix, and a real species-vs-profile
reject distinction

**Decision, satisfier fix.** `_NEED_SATISFIERS["fake_out_protection"]`
(pre-ADR-042, see below) still listed redirection moves as valid satisfiers,
despite this exact mechanical error — redirection cannot stop Fake Out,
priority +2 vs. +3 — having already been identified and removed from a
different layer (`_compendium_roles_for_need`'s role-routing) in an earlier
session (2026-08-21). The raw move-satisfier layer was never updated to
match at the time. Fixed by dropping redirection moves from that satisfier
set. Superseded shortly after by ADR-042's removal of `fake_out_protection`
as a category entirely, but recorded here since it was a real, standalone
fix landed first.

**Decision, reject-species-vs-reject-profile.** Resolves the "reject
candidate vs. reject role" question held open before this session: a bare
`reject N` / `reject <species>` excludes only that species' lineage, with
no automatic profile ban — the default, matching the common case where a
rejection is about that specific Pokémon, not its whole role. An explicit
signal (`reject N, no TR` / `reject N because TR` / a bare "no more trick
room") stamps a real, singleton profile ban. Profile-ban matching was
widened to `banned <= raw` support needs (not just exact/sticky match),
closing a hole where an Acceptable-tier TR tag riding along on an otherwise-
unrelated cleric pick could dodge an explicit ban. Candidate option display
now shows all matched need categories (slash-separated), not just one, and
a short reject-usage hint was added to the CLI footer.

**Status:** Implemented and merged (PR #128, #129). Full suite green.

---

## ADR-042 (part 1): Category A speed-control redundancy parity, and a
fail-closed empty candidate pool

`support_speed_control`-shaped Category A candidates (e.g. Whimsicott,
Aerodactyl) now get the same redundant-speed-control demotion Category B's
`tailwind_setter`/`trick_room_setter` needs already had (ADR-037) — closing
a gap where a Category A speed-control pick could be just as redundant
against an already-locked Tailwind but wasn't being demoted the same way.

Separately: exhausting the candidate pool via repeated rejection now returns
a clear, honest empty-pool prompt instead of raising or falling through to a
generic "couldn't parse" response — a real reliability fix given how much
reject-cycling came up in this week's live testing.

**Status:** Implemented and merged (PR #130). Full suite green.

---

## ADR-042 (part 2): Disruption-shaped needs removed; redirection promoted
to a first-class category; TR sticky-ban specialized to pure main-job

**Context — resolves the deepest open question from before this session,**
more decisively than the "should this be a softer tier" framing it was held
under. `fake_out_protection`, `taunt_disruption`, and `stat_lowering_partner`
were modeled as "ally-emit" needs — something a teammate provides the way a
Trick-Room-setter provides Trick Room. That framing doesn't hold up
mechanically: unlike Trick Room/Tailwind/Screens, there is no single,
portable, ally-provided resource that reliably "answers" opposing Fake
Out/Taunt/stat-drops the way a dedicated setter answers a real team need —
redirection helps sometimes, priority-immunity abilities are rare and
narrow, and (per the mechanical correction surfaced this week) even the
Prankster-based reasoning used to justify similar needs in an earlier
session was itself wrong (+1 priority does not beat Fake Out's +3). These
were a category error, not a tier error — removed as `NeedCategory` values
entirely rather than demoted.

**`redirection` (Follow Me / Rage Powder) is promoted to its own real,
first-class `NeedCategory`** — this is a genuine, portable, ally-provided
resource in the way the removed categories weren't, and it directly absorbs
what `fake_out_protection`'s satisfier list was reaching for (ADR-041)
without the mechanical error, since it's evaluated on its own real merits
now rather than borrowed as a mismatched satisfier for a threat it can't
actually stop.

**The hard/soft split directly answers the "every Pokémon already has
Protect" critique.** A hard (needed) redirection ask now requires a
concrete, kit-derived vulnerability: `requires_setup_turn` (Protect and the
setup move are mutually exclusive — a real, forced cost) or a genuine
self-inflicted Defense/Special Defense drop (Weak Armor, or a move flagged
via `_self_defense_drops`). Plain offense-primary alone, without either,
gets only a soft `want` — deliberately not enough on its own to flip
`anchor_has_obvious_need`. Scoped conservatively: only the single confirmed
Weak Armor ability id is checked, not an invented "Weak-Armor-class"
ability list, pending a future abilities-extract pass with real structured
data on hit-triggered stat drops.

**A leaf→umbrella taxonomy** (`speed_control`, `damage_mitigation`,
`redirection`, `healing`, `condition`) groups related leaf categories for
reporting/diversification purposes, deliberately without its own
satisfier or reject logic at the umbrella level — matching is still leaf-only.

**TR sticky-ban specialized to pure main-job only.** Rejecting a pure
`{trick_room}` candidate (a genuine main-job setter — Armarouge, Chandelure)
sticky-bans that exact profile. A multi-purpose candidate whose real
diversification profile includes `trick_room` as a secondary tag (e.g. a
cleric with an Acceptable-tier TR option) is NOT caught by that same ban —
confirmed directly in code: `profile_is_banned`'s singleton-`{trick_room}`
case only matches when the candidate's own sticky profile is *also* exactly
`{trick_room}`, not merely a superset containing it. Multi-need candidates
now display all matched categories (slash-separated) with a note when a
secondary-TR option exists, rather than only ever showing one.

**Known follow-up, disclosed, not yet done:** a lazy import
(`role_compendium` -> `support_needs`) was needed to reach
`_self_defense_drops` and works correctly, but introduces a real import
cycle between the two modules. Next step is extracting the shared stat-drop
data into a thin, dependency-free module both can import from directly.

**Status:** Implemented and merged (PR #131). Full suite: 1377 passed, 12
skipped (environment-only skips).

---

## ADR-043: Role Compendium decomposition ("ponytail audit" phases 1-2)

**Context.** `role_compendium.py` had grown to ~7149 LOC, mixing dispatch,
setup-construct scoring, weather/support/sleep constructs, usage/Showdown
attribution, and JSON evidence reading in one file — high blast radius for
any change, and the direct cause of at least one real, confirmed bug this
week (ADR-042's `weakarmor` hardcoded-id follow-up lived here specifically
because the real data path was buried in this same god-file). Decomposed
across ten PRs (#132-140, #139 abandoned/unmerged) plus five more
(#142-148) continuing the same effort into `slot_fill.py` and `nodes.py`.
Explicitly disclosed throughout: product behavior is intentionally
unchanged except where separately noted (the Weak Armor data-driven fix,
below) — this is a decomposition effort, not a behavior change.

**Decision — split along existing dispatch seams, not a new framework.**
`construct_role_category` stays on the `role_compendium.py` façade as the
single dispatch router; each construct category was extracted to its own
leaf module (`role_compendium_setup.py`, `_support.py`, `_weather.py`,
`_usage.py`, `_read.py`, `_setup_constants.py`) and imported lazily inside
the relevant dispatch branch, avoiding import cycles without a generic
constructor abstraction. A generic `RoleConstructor` ABC / shared runner
framework was explicitly considered and rejected — splitting along seams
`construct_role_category` already implied was judged sufficient, consistent
with this project's standing preference for the smallest change that
resolves the real problem. `__getattr__`-based re-export frozensets
(`_SETUP_REEXPORTS`, `_USAGE_REEXPORTS`, `_SUPPORT_REEXPORTS`) kept every
existing call site and test working unchanged during the migration,
letting tests be moved to canonical imports incrementally rather than in
one disruptive pass. Verified directly: façade shrank from ~7149 to 1385
LOC, and every extracted module's line count matches exactly what was
claimed at each step.

**Decision — `stat_boosts.py` (PR #135) directly resolves the import-cycle
follow-up flagged in ADR-042 part 2.** `support_needs.py`'s lazy import of
`_self_defense_drops` from `role_compendium` (needed for the redirection
hard-ask's self-Def/SpD-debuff check) was real technical debt from
ADR-042, not a deliberate design choice — extracting the thin, ~43-line
`stat_boosts` module (JSON-backed, `@lru_cache`d) let `support_needs` take
a top-level import instead, breaking the cycle at its root rather than
working around it. Confirmed directly in the current code: `support_needs.py`
now imports `_self_defense_drops` from `recommender.stat_boosts` at module
level, no lazy import remaining.

**Decision — Weak Armor becomes data-driven, superseding ADR-042's
disclosed ponytail-scoped gap (PR #147/#148).** ADR-042 explicitly checked
only the single confirmed `weakarmor` ability id, declining to invent a
broader "Weak-Armor-class" ability list without real supporting data.
`ability_self_def_drop_on_physical_hit()` (new, `ability_classification.py`)
now reads a real `on_physical_hit.self_stages` field from
`data/abilities/all.v1.json`, so any ability with a genuine, data-backed
physical-hit Def/SpD self-drop is caught automatically — not just Weak
Armor — without ever having to hand-curate or guess at which abilities
qualify. This is the right way to resolve that kind of gap: real structured
data replacing a hand-picked id, not a broader guess.

**Decision — contact-move detection moved to real data (PR #146).**
`matchup.py` carried a ~174-line hardcoded `_CONTACT_MOVES` frozenset,
duplicating `data/moves/flags.v1.json` and drifting from ADR-007's
data-first convention. Replaced with a shared `counters._move_has_contact_flag()`
helper reading the real JSON directly. A real, if minor, mistake was
caught and fixed within this same PR, not shipped uncorrected: `_WIDE_LENS`
was accidentally deleted during the edit and restored on review — worth
recording as a reminder that even "pure mechanical" refactors need real
verification, not just diffing line counts.

**Test infrastructure work, no product implications:** the ~2800-line
`test_role_compendium_swords_dance.py` monolith was split by concern
(construct/payoff-select/damage-score) into focused modules sharing common
fixtures (PR #142); `pair_panel_ids.py`, `slot_fill_target_role.py`, and
`nodes_classify.py` were extracted from `team_candidates.py`, `slot_fill.py`,
and `nodes.py` respectively for the same import-cycle and blast-radius
reasons (PR #143-145) — `nodes.py` specifically kept a full re-export façade
so `graph.py` and every existing caller needed zero changes.

**Explicitly deferred, disclosed rather than silently dropped:**
`team_candidates.py` (~2383 LOC), `slot_fill.py` (~2249 LOC), and
`role_compendium_setup.py` (~3312 LOC, itself now a large single module)
remain unsplit — no further decomposition planned until a real "explore"
pass confirms a clean seam exists, matching the same discipline already
applied here (split along real, existing boundaries, not an imposed
structure). `lookup_live_build`/`fetch_live_build` (PR16 in the original
plan) has real ADR sign-off but is blocked on a separate, unresolved
featured-set mechanism design question, not implemented.

**Status:** Implemented and merged (PR #132-138, #140, #142-148; #139
abandoned/unmerged, its work absorbed into #140). Verified directly: full
suite 1379 passed, 12 skipped (environment-only skips), matching the
claimed baseline at every checked stack tip.

---

## ADR-044: condition_beneficiary shape taxonomy — terrain coverage, damage
mitigation, denial effects, and item/move gaps (comprehensive scoping, no
implementation)

**Context:** condition_beneficiary discovery (`provided_weather_conditions` →
`resolve_condition_beneficiaries`, ADR-024's `RoleShapeContext` lineage) was
known to be weather-only and to lack a "type-general middle tier" — flagged
repeatedly since the original design doc
(`docs/single_locked_condition_beneficiary_discovery_and_design_2026-08-11.md`)
deliberately deferred both. A systematic investigation this session — five
successive discovery passes, each surfacing a real shape the previous one
missed — replaced that open-ended flag with a complete, verified taxonomy.
**Every claim below was checked directly against real calc/game data
(`vendor/smogon-calc/dist/mechanics/champions.js`/`gen789.js`, the ability and
item extracts, the Champions legality snapshot) — nothing here is assumed or
conversation-assembled.** No implementation, tier assignment, or hard/soft
stance is decided by this ADR. This is a scoping document; build-order and
tier decisions are explicitly deferred to a future session.

**Decision (scope framing only):** condition_beneficiary's real design space
decomposes into seven mechanically distinct shapes, not one:

| # | Shape | Example | Real pool size (Champions-legal) | Wired today? |
|---|---|---|---|---|
| 1 | Offensive (STAB/BP/speed ability) | Water STAB under Rain; Swift Swim | 25–39/condition (STAB); small (ability) | Ability-tier only, weather-only |
| 2 | Defensive mitigation (damage ×0.5, def stat ×1.5) | Rain halves incoming Fire; Sand boosts Rock SpD | 20–106/condition, wider variance than offense | No |
| 3 | Denial (status/sleep/priority/chip block) | Electric blocks sleep; Psychic blocks priority; Sand chip immunity | 20–280/condition — **near-universal (87%) for Electric/Misty/Psychic at species-level "grounded" gate** | No (Psychic priority block exists in calc; Electric/Misty status denial is a game rule outside calc entirely) |
| 4 | Ability/move-specific (existing invert) | Swift Swim; Electro Shot charge-skip | Small, precise | Yes, weather-only (`weather_beneficiary_ability_ids`, `CHARGE_INSTANT_WEATHER`) |
| 5 | One-time held-item trigger | Terrain Seeds (Electric/Grassy → +1 Def; Misty/Psychic → +1 SpD) | ~entire legal dex if legal (species-agnostic) | No; all four seeds currently `is_nonstandard: "Past"`, 0 legal carriers |
| 6 | Duration extension | Heat/Damp/Icy/Smooth Rock, Terrain Extender | N/A — supports the *setter*, not a beneficiary | Already correctly classified as non-severe/duration in `legality.py:115-122` |
| 7 | Opt-out / anti-beneficiary | Utility Umbrella | N/A — cancels weather effects entirely for holder | Currently illegal; calc-aware if it returns |

**Terrain coverage — structural gap, confirmed at every layer.** Five real
terrain-setting abilities exist (Electric Surge, Grassy Surge, Psychic Surge,
Misty Surge, Hadron Engine — Electric Terrain has two independent setters);
`_mechanisms` (`anchor_roles.py:507-528`) reads only `field.get("weather")`
from `ABILITY_TO_FIELD`, never `field.get("terrain")` — terrain-setting
abilities produce zero mechanism evidence today. `provided_weather_conditions`,
`weather_beneficiary_ability_ids`, and the move-beneficiary charge table
(`CHARGE_INSTANT_WEATHER`) are all independently weather-keyed with no terrain
counterpart at any layer. **Seed Sower** (sets Grassy Terrain on being hit) is
a genuine asymmetry against even the surge-only pattern already assumed
elsewhere in the codebase — a real gap in an existing convention, not just a
missing terrain case. Current Champions legality makes this structurally real
but currently low-stakes: Electric Surge (Raichu-Mega-X) is the only legal
terrain setter; the Tapus and Indeedee (the game's other classic setters) are
all `Illegal` (Restricted Legendary / Past).

**Resolved this session: terrain generalization approach.** Rejected a
unified `condition:{label}` vocabulary spanning weather and terrain in favor
of **parallel, terrain-specific functions alongside the untouched weather
ones** — because weather and terrain can be simultaneously active (they
stack), and a unified single-value representation can't cleanly express "one
of each," which a shared vocabulary would obscure. This is the one concrete
implementation-shape decision made in this scoping pass; the surrounding
question of whether terrains join `TRACKED_CONDITIONS` (the resilience/
backup-setter closed set) remains open, per the original 2026-08-11 doc's
deferral.

**Type-general "middle tier" (offensive) — genuinely ambiguous, not resolved.**
A plain STAB-move qualifying bar (≥1 legal damaging move of the boosted type)
produces 25–39 species per condition where an offensive boost exists at all
(Rain/Water, Sun/Fire, Electric/Electric, Grassy/Grass — Sand/Snow/Misty/
Psychic have no symmetric offensive boost). No qualifying bar found is both
mechanically honest and non-noisy; six real design options were laid out
(status quo / featured-set-only gate / exclude ability-tier overlap /
move-specific-only / separate presentation category / offense-primary-only
prefilter), each with a real tradeoff, deliberately not chosen here.

**Defensive mitigation — mechanically distinct from offense, pool-size
comparison inconclusive on its own.** Three qualifying shapes within
mitigation itself: incoming-type-damage halving (Rain/Fire, Sun/Water,
Misty/Dragon, Grassy/EQ-Bulldoze — gated by ≥2× or ≥4× weakness to the
mitigated type), own-type defensive stat boost (Sand/Rock SpD, Snow/Ice
Def — gated by the *holder's own typing*, not weakness), and ability×field
hybrids (Grass Pelt, 0 legal carriers). At the ≥2× weakness gate, Rain/Sun/
Grassy mitigation pools (69–106 species) are *larger* than their offensive
counterparts, reversing the intuition that mitigation would be more targeted;
a ≥4×-only gate produces much smaller, more plausible pools (4–7 species) but
is a different, stricter design choice, not an inherent property of the
shape. **Correction applied this session:** Sun's 35-species overlap
(≥2×-Water-weak ∩ Fire-STAB) is a double *benefit* (halved incoming Water
damage and boosted outgoing Fire damage simultaneously) — an earlier framing
of this as "helps and hurts the same species" was backwards and has been
corrected. The real open question from this overlap is attribution
(double-counting across an offense tier and a mitigation tier), not harm.

**Denial — real, but likely too broad to use as-is.** Three terrain denial
effects (Electric Terrain blocks sleep/Yawn/Rest; Misty Terrain blocks
non-volatile status and confusion; Psychic Terrain blocks priority moves
entirely, the only one of the three actually modeled in `@smogon/calc`'s
damage path) plus Sand/Hail end-of-turn chip immunity and primal-weather
move-fail (Heavy Rain kills Fire moves, Harsh Sunshine kills Water moves).
At the natural species-level qualifying gate ("grounded" — not Flying-type,
no Levitate/Eelevatate, no Air Balloon), **87% of the legal dex qualifies**,
independently re-verified this session (276/316, consistent with the
original report's 280/320 despite a minor species-count-methodology
difference between passes). This is a finding, not a recommendation: denial
is mechanically real and interesting, but at the obvious gate it fails to
discriminate at all, and would need a materially tighter qualifier (a real
kit-derived status vulnerability, a calc-verified priority-threat exposure)
to be a useful `condition_beneficiary` signal rather than near-universal noise.

**Held items — three further distinct shapes, none currently actionable.**
Terrain Seeds (shape 5 above) are species-agnostic and currently illegal
(0 legal carriers) — explicitly documented for future-regulation readiness
per this session's direction, not dismissed for being currently illegal.
Duration-extending rocks and Terrain Extender are already correctly
classified elsewhere in the codebase as setter-support, not beneficiary
items. Utility Umbrella is a real, calc-modeled opt-out (cancels both
weather boosts and mitigation for its holder) — currently illegal, and
structurally an anti-beneficiary case rather than a beneficiary one if it
returns.

**Move effects — most are unwired, several outside the calc-modeled path
entirely.** Only three moves are wired into beneficiary invert today (Solar
Beam, Solar Blade, Electro Shot — all weather charge-skip). At least a dozen
more real condition-dependent move effects exist and are unwired (Rising
Voltage, Terrain Pulse, Expanding Force, Weather Ball, Misty Explosion,
Steel Roller's move-fail-without-terrain, Nature Power's terrain-dependent
type rewrite). A further category — accuracy changes (Thunder/Hurricane/
Blizzard), weather-dependent healing (Synthesis/Moonlight/Morning Sun/Shore
Up), and stat-change moves (Growth) — sits entirely outside `@smogon/calc`'s
damage-calculation path and would need a separate rules data source if ever
scoped, not an extension of the existing calc-based invert.

**Calc-layer vs. static-lookup — an explicit open design question, not
resolved.** Several shapes (mitigation, Psychic priority denial) are already
calc-modeled and already used elsewhere in this codebase for a structurally
similar purpose (`threat_counters.py`'s `_best_matchup_with_forced_fields`
re-evaluates locked-field matchups through real calc specifically because
Rain/Fire halving changes real severity). A static type-chart proxy is
cheap but ability/item-blind (Utility Umbrella, Thick Fat, Freeze-Dry, Tera
typing); a fully calc-verified beneficiary signal is faithful but heavier
and needs real threat context, mirroring the forced-field pattern rather
than a simple lookup. Not decided here.

**Status:** Discovery and scoping complete; nothing implemented. This ADR
exists to close out an open-ended investigation with a converged, verified
reference document rather than leave the shape taxonomy scattered across
session transcripts. **Explicitly deferred to a future session:** which of
the seven shapes (if any) get built, in what order, at what tier (hard
need / soft want / presentation-only / not modeled at all), and whether the
calc-verified or static-proxy approach is used for each. The one concrete
decision made — parallel terrain-specific functions rather than a unified
vocabulary, because weather and terrain can stack — is ready to inform
whatever gets built first, whenever that's decided.