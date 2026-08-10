# Calc-unavailable static fallback — discovery and design (2026-08-09)

**Status:** Discovery + design only. No implementation in this pass.

**Deferred-from:** multi-locked candidate discovery (ADR-026 / design §Calc-unavailable
static fallback), team-phase routing (ADR-025 residual: “labeled static fallback …
remains a separate, unresolved gap”), teammate-query / slot-fill flow backlog item
`calc unavailable -> labeled static fallback`. Always correctly deferred; never previously
traced end-to-end against current source for *every* real consumer.

**Precedent shape (not a copy of the mechanism):** ADR-015 Amendment 2026-07-29a —
usage/real-team data is legitimate for discovery and legality confirmation, never as
ranking evidence. A static type-effectiveness hint, if shown at all, should sit in the
same epistemic tier: discovery-time signal under degradation, never a substitute for
`classify_matchup` / verified ranking.

**Explicitly out of scope (per brief):** re-verifying calc’s own math; consuming Pass 2’s
conditional-mechanics inventory; canonical name/form resolution.

---

## Part 1 — verified current state

### 1. Calc-failure behavior by real consumer (not uniform)

Verified against current `recommender/` and graph wiring. “Fail-closed” here means:
structured `CandidateDiscoveryError` / unavailable status, no candidate presentation that
could be read as authoritative verified ranking.

| Consumer | Calls calc? | On `CalcClientError` / `MatchupEvidenceError` | Consistent with multi-locked fail-closed? |
|----------|-------------|-----------------------------------------------|-------------------------------------------|
| `discover_multi_locked` → `_compute_team_review` | Yes (`compute_team_coverage` / `detect_spof` → `classify_matchup`) | `TeamReviewResult(status="unavailable", error=…)`; node returns `candidate_discovery_error`, `pending_presentation=None` (`nodes.py:1142-1147`) | **Yes** |
| `discover_multi_locked` → `query_candidates_for_threats` | Yes (per-candidate `classify_matchup`) | `TeamThreatDiscovery(status="unavailable", candidates=(), error=…)` (`threat_counters.py:351-367`); node hard-stops same way (`nodes.py:1187-1192`) | **Yes** |
| `refresh_team_signals` | Yes (same `_compute_team_review`) | Publishes `candidate_discovery_error=review.error` and empty coverage/SPOF (`nodes.py:1071-1092`) | **Structured, but not on live graph** (see below) |
| `generate_team_review` (`complete` / explicit `team_review`) | Yes (`_compute_team_review`) | Stores unavailable `last_team_review` (with `.error`), clears `coverage`/`spofs` to `[]`, **always sets `candidate_discovery_error=None`** (`nodes.py:1266-1275`) | **No** — soft degrade into empty signals; error only inside `TeamReviewResult` |
| `discover_single_locked` → `build_anchored_slot_fill_context` → `query_threat_counters` | Yes (`classify_matchup` in verification loop) | **No catch.** Exception propagates out of the node (`threat_counters.py:254`; `slot_fill.py:203`; `nodes.py:1003`) | **No** — hard crash, not structured stop |
| Leaf `query_threat_counters` (same as above; also callable outside graph) | Yes | Propagates | **No** |
| Leaf `query_counters` | **No** (data-only; docstring at `counters.py:1-4`) | N/A — never depends on calc service | Calc-independent by design |
| Empty-team `discover_bootstrap_directions` | **No** (`query_by_usage` + role/build refinement) | N/A for calc; its own fail-closed is intake/parser/empty-candidate (`bootstrap.py:313+`, `nodes.py:920-935`) | N/A (no calc path) |
| Legacy `fill_team_draft` / `propose_team_draft` | Conditionally: only empty-draft gap probe calls `compute_team_coverage`/`detect_spof` without a try/except (`propose.py:60-70`) | Would propagate if that branch runs | Not a calc-unavailable *fallback*; separate proposal path |

**Graph wiring note (verified):** `multi_locked` routes to `discover_multi_locked` directly
(`graph.py` `_PHASE_ROUTES` + compiled edges). `refresh_team_signals` is still a registered
node and unit-tested, but has **no inbound/outbound edges** in the live graph. Multi-locked
recomputes review inside `discover_multi_locked` itself. Do not treat “refresh then legacy
propose” (older team-phase docs) as current runtime topology.

**“Legacy fallback” naming collision (verified):** team-phase tests’ `*_uses_legacy_fallback`
mean “drop into `fill_team_draft` when the open slot is partial or the anchored merge is
empty” (`test_team_phase_routing.py:221-272`, `369-387`). That is **not** a static matchup
estimate when calc is down. Conflating the two phrases is how this gap stayed untraced.

**single_locked detail:** even when calc is healthy, threat evidence is labeled with
`verified_score` via `_threat_evidence` (`slot_fill.py:500-527`). On calc failure today
there is no alternate path — the node does not fall through to support-only presentation,
nor to `fill_team_draft`, nor to a structured `CandidateDiscoveryError`. Support-need
resolution itself does not call calc, but it never runs if `query_threat_counters` raises
first.

**complete / team review detail:** `_unavailable_team_review` correctly distinguishes
`calc_unavailable` vs `calc_incomplete` (`nodes.py:1048-1068`). `generate_team_review`
then **discards** that error from the graph-facing `candidate_discovery_error` field while
still publishing empty coverage/SPOF lists — a silent-looking degrade unless the caller
inspects `last_team_review.status`.

**Verdict for Q1:** only the multi-locked discovery chain (and the structured leaf it uses,
`query_candidates_for_threats`) implements the fail-closed pattern ADR-026 described.
`query_threat_counters` / `single_locked` are fail-open-by-exception. `generate_team_review`
is a third shape: structured unavailable object, cleared public error field. Bootstrap and
`query_counters` are calc-independent and do not participate in this contract.

---

### 2. Does a “legacy matchup fallback” actually exist?

**No dedicated module or function implements a calc-down matchup substitute.**

What the multi-locked plan / ADR-026 excluded, traced against source:

| Phrase in prior docs | What exists today | Verdict |
|----------------------|-------------------|---------|
| “No static/legacy matchup fallback runs in this path” (ADR-026) | Prophylactic exclusion: multi-locked must not invent static scores or present support/shared candidates as if threat ranking succeeded | **Correct exclusion for multi-locked ranking.** There was nothing to “turn off” — the path was built fail-closed from the start |
| “Calc-unavailable static fallback” (deferred backlog) | Documented gap only; slot-fill discovery listed `calc unavailable -> labeled static fallback` as a missing edge (`slot_fill_flow_discovery_2026-08-08.md:351`) | **Not implemented** |
| “Legacy fallback” in team-phase tests | `fill_team_draft` proposal path for partial/empty candidate cases | **Different concept** — not matchup estimation |
| Living static machinery that *looks* related | (a) `query_counters` — cheap data-only threat discovery using type chart + crude BP proxy; (b) `_static_cut` in `threat_counters.py` — pre-verification pool cut by threat-count/usage, **before** calc | **Legitimate discovery machinery.** Misusing either as a verified ranking stand-in would be the mistake ADR-026 avoided |

**What `query_counters` / `_static_cut` compute (so exclusion can be judged):**

- `query_counters`: for each legal species, optionally using a featured/common usage set,
  admits on two binary axes — `wall` (all incoming attack types ≤0.5× after ability
  immunities) and `ko_threshold` (best move’s effective BP ≥ `KO_THRESHOLD_BP=200`). No
  HP, no EV-aware damage, no speed, no KO turns, no `MatchupResult`.
- `_static_cut`: ranks merged counter-of-counter candidates by how many threats they
  statically appear for, then usage popularity — still pre-`classify_matchup`.

**Was excluding them from multi-locked ranking the right call?** Yes. Multi-locked ranking
keys off verified outcomes (`clean_kill` / severity bands / SPOF closure) via
`verified_vs` (`team_candidates.py` ranking helpers). Feeding `query_counters` axes or
`_static_cut` counts into those bands would fabricate decisive/costly closures. Reusing
the same static machinery for **discovery-time degraded hints** (Part 2) is a different,
legitimate use — the same ADR-015 discovery-vs-ranking split.

**Session failure that motivated the backlog (historical, not current code):** slot-fill
flow Scenario 1 called `query_threat_counters` with calc down and “failed hard rather than
yielding a clearly labeled static fallback”
(`slot_fill_flow_discovery_2026-08-08.md:42-64`). That observation remains accurate for
`query_threat_counters` today.

---

### 3. Is `effective_move_type` / `type_effectiveness` reusable as a static core?

**Yes, as the type-effectiveness core of an already-shipped static pipeline — with explicit
ceilings.**

Both live in `recommender/counters.py` and are already consumed by `query_counters`
(`_walls`, `_ko_best_move`). They do **not** call the calc service.

**What they cover today:**

| Capability | Covered? | Notes |
|------------|----------|-------|
| SS/Champions type chart multiply | Yes | `TYPE_CHART` comment: Champions = SS chart |
| Dual-type defense multiply | Yes | Loop over defend types |
| Freeze-Dry vs Water | Yes | `type_effectiveness` special case |
| Flying Press dual chart | Yes | Fighting × Flying legs |
| Scrappy Ghost ignore | Yes | Normal/Fighting vs Ghost → 1.0 |
| Ate abilities (Aerilate / Pixilate / Refrigerate / Dragonize) on Normal | Yes | `effective_move_type` |
| Liquid Voice + sound flag → Water | Yes | Uses `data/moves/flags.v1.json` sound bit |
| Weather Ball / Terrain Pulse / Aura Wheel / Raging Bull type rewrite | Partially | Functions accept `weather`/`terrain`/`species`, but **`query_counters` never passes weather/terrain** (no `weather=`/`terrain=` call sites in `counters.py`) — those moves stay base type under current static discovery |
| Ability type immunities (Flash Fire, Levitate, etc.) | Yes on **incoming** wall check | `ABILITY_TYPE_IMMUNITY` via `_incoming_effectiveness` |
| Crude offensive “can KO threshold” via BP×type×STAB×accuracy×hit-factor | Yes inside `query_counters` only | `_ko_best_move`; threshold probe, not damage calc |
| Wall check (all incoming types ≤0.5) | Yes inside `query_counters` | Uses attacker ability only for Scrappy-style offense overrides on the wall path |

**What they deliberately do not cover (ceilings):**

- Real damage / %HP / KO turns / speed order / field effects as `classify_matchup` does.
- Stats, EVs, levels, items (Life Orb, Choice Band, etc.), natures — none enter
  `type_effectiveness`; `_ko_best_move` uses snapshot basePower only (+ a few assumed
  scaling cases: Last Respects, Rage Fist, Supreme Overlord).
- Full Pass 1 calc special cases (Adaptability, Technician, weather attack multipliers,
  terrain BP doubles, Steel Roller fail, etc.) — out of scope to invent here; conditional-
  mechanics Pass 2 inventory is a separate deferred item per brief.
- Soundproof / Bulletproof / priority-block immunities — not in `ABILITY_TYPE_IMMUNITY`.
- STAT-FRAGILITY axis already deferred in `counters.py` module docstring.

**Verdict for Q3:** reusable and already battle-tested as discovery math. Sufficient for a
**labeled type-effectiveness / wall / crude-BP hint**. Insufficient — and must never be
presented as — a verified matchup or KO calculation. Prefer calling through existing
`query_counters` / exported helpers over inventing a parallel estimator.

---

## Part 2 — design proposal

### 1. What a “static” estimate is (mechanical boundary)

A **static estimate** is a calc-independent, data-only signal derived from:

1. species types (legality snapshot),
2. `effective_move_type` + `type_effectiveness` (and, where already used, ability type
   immunities),
3. optionally the existing `query_counters` admission axes (`wall`, `ko_threshold` via the
   BP proxy) as **discovery filters only**.

It is **explicitly not**:

- a `MatchupResult` (`clean_kill`, `intentional_non_ko_answer`, …),
- a severity band (`decisive` / `costly` / …),
- a `verified_score`,
- coverage/SPOF closure evidence,
- anything that may enter multi-locked’s verified ranking tuple.

**Naming rule:** never use the words “verified”, “KO”, “coverage answer”, or
`verified_score:` in evidence strings for static rows. Prefer explicit tokens such as
`static_type_estimate`, `calc_unavailable`, `wall_axis`, `ko_threshold_proxy` (proxy ≠ KO).

### 2. Where labeled static estimates are legitimate vs fail-closed only

ADR-015 Amendment 2026-07-29a shape applied to calc degradation:

| Surface | Degraded mode allowed? | Rationale |
|---------|------------------------|-----------|
| **Discovery-time candidate generation** when calc is down (single-anchor threat branch; optional informational hints) | **Yes, if labeled** | Same role `query_counters` already plays when calc is healthy: cheap pool before verification. Without calc, stop before verification and surface the static pool as degraded discovery — never as ranked verified answers |
| **Support-need / compendium / teammate branches** that never required calc | **Yes (unchanged)** | Not substitutes for matchup ranking; must not be presented as “team-threat ranking succeeded” when the threat objective is unavailable (ADR-026 invariant 17) |
| **`multi_locked` authoritative team-threat ranking** | **No — stay fail-closed** | Ranking stages require verified closures against a calc-backed coverage/SPOF objective. Static axes cannot honestly populate those stages |
| **`complete` / `generate_team_review` coverage & SPOF claims** | **No authoritative claims** | May report `status="unavailable"` + structured error; must not invent covering slot indices or SPOF findings from type chart. Optional future: separate non-authoritative “static pressure” appendix — only if clearly outside `coverage`/`spofs` fields |
| **Bootstrap / `query_by_usage`** | N/A | Already calc-independent |

**Concrete consumer proposals:**

1. **`query_threat_counters` / `single_locked`:** catch `CalcClientError` /
   `MatchupEvidenceError`. Return a degraded discovery result (structured status, not a
   raised exception) whose candidates — if any — carry static evidence only, `confidence=
   "low"`, and **no** `verified_score`. Prefer still running support-need resolution so the
   user is not locked out of calc-independent branches. Do **not** silently fall into
   `fill_team_draft` and pretend slot-fill succeeded.
2. **`query_candidates_for_threats` / `discover_multi_locked`:** keep today’s hard stop for
   threat verification and for coverage/SPOF unavailability. Do not rank on static
   estimates. Optional later (separate decision): present support/shared-only with an
   explicit “team-threat ranking unavailable” banner — still must not claim threat
   precedence; default recommendation is **remain fail-closed** until product wants that
   UX.
3. **`generate_team_review`:** keep empty coverage/SPOF on failure, but stop clearing
   `candidate_discovery_error` (or equivalent graph-facing signal) so complete-phase
   unavailability matches multi-locked honesty. No static coverage fabrication.
4. **`refresh_team_signals`:** if re-wired later, same contract as `_compute_team_review`
   publishers — structured error, no invented coverage.

### 3. Labeling / provenance — reuse `CandidateEvidence`, do not invent a second model

Existing basis vocabulary (`state.py:153-160`):

`usage_backed` | `compendium_backed` | `mechanical_only` | `synthesized` |
`teammate_backed` | `ownership_backed`

**Proposal — no new evidence dataclass; no new basis value required for v1:**

- `basis="mechanical_only"`
- `confidence="low"` (never `high`; avoid `medium` so it cannot tie healthy mechanical
  threat rows that already use medium)
- `producer_name` = the degraded producer (`query_threat_counters` or a clearly named
  helper), not a fake `classify_matchup`
- `evidence` tuple **must** include an explicit degradation token, e.g.
  `("static_type_estimate", "calc_unavailable", …)` plus optional axis tags
  (`wall_axis`, `ko_threshold_proxy`) — never `verified_score:…`

**Why not a new `static_estimate` basis:** the brief’s session discipline is reuse
`CandidateEvidence` rather than a parallel model. `mechanical_only` already means
“mechanics without usage/compendium confirmation”; the degradation token + `low`
confidence carry the calc-unavailable distinction. A new basis remains optional if
presentation sorting later cannot distinguish healthy vs degraded mechanical rows —
YAGNI until a real sort collision appears.

**Confidence / ranking firewall:**

- Degraded static rows must not feed `verified_vs`, multi-locked severity counts, or any
  key that today reads `MatchupResult.outcome`.
- If a presentation sort still keys on `threat_row.verified_score`, static rows must either
  omit `threat_row` or force `verified_score=0` with status ≠ verified — prefer omitting
  verified fields entirely and using a distinct discovery status enum on the leaf return
  type (mirror `TeamThreatDiscovery.status`, extend `query_threat_counters` to a small
  result object rather than a bare `list` when degraded). That API shape change is
  implementation-track work; design requirement is: **status is structural, not only a
  string buried in evidence.**

### 4. Consumers that cannot degrade meaningfully

Confirmed stay fail-closed (this task must not force degraded mode everywhere):

| Consumer | Why fail-closed remains correct |
|----------|----------------------------------|
| `discover_multi_locked` threat ranking | Staged comparison is defined on verified closures; static estimates would either starve the ranking of meaning or lie |
| Coverage / SPOF objective construction | `build_team_threat_objective` reads calc-backed coverage/SPOF rows; empty/unavailable objective is honest |
| Any UI/API that claims “answers threat X” | Type SE is not an answer in this project’s matchup vocabulary |

Support/compendium/teammate/bootstrap paths are not “degraded calc mode”; they are
independent producers. When the threat objective is unavailable, presenting only those
producers is a product choice that must carry an explicit unavailable-threat banner — and
is **out of the minimum design** recommended here (default: hard stop as today).

---

## Design invariants (review checks, not implementation tests)

1. **Non-confusability:** a static estimate cannot be serialized as a `MatchupResult` or
   carry `verified_score` evidence.
2. **ADR-015 shape:** static signal may admit/discover; it must not break equal-candidate
   ties or outrank verified evidence when both exist.
3. **Fail-closed portfolio ranking:** multi-locked never claims team-threat ranking without
   calc-backed verification (ADR-026 invariant 17 preserved).
4. **Leaf consistency:** `query_threat_counters` and `query_candidates_for_threats` may
   differ on whether degraded discovery is returned, but neither may raise past a graph
   node without a structured error mapping.
5. **Reuse over rewrite:** computational core is existing `effective_move_type` /
   `type_effectiveness` / `query_counters`, not a new parallel type engine.
6. **One evidence model:** `CandidateEvidence` only; degradation via basis/confidence/
   evidence tokens (+ structured status on the result object).

---

## Residual risks / open questions for implementation

1. **`query_threat_counters` API shape.** Today it returns `list[ThreatCounterCandidate]`.
   Degraded mode needs a status channel (`TeamThreatDiscovery`-like) or graph nodes cannot
   distinguish empty-success from calc-failure. Prefer aligning with
   `query_candidates_for_threats` rather than inventing a third pattern.
2. **Weather/terrain-blind static discovery.** Until callers pass field context into
   `effective_move_type`, Weather Ball / Terrain Pulse estimates stay wrong-type under
   static mode — acceptable ceiling if labeled; do not silently claim field-aware SE.
3. **Support-only presentation under multi-locked calc failure.** Product UX question;
   default design = hard stop. If later allowed, banner + no threat precedence is
   mandatory.
4. **`generate_team_review` error surfacing.** Small honesty fix (stop clearing
   `candidate_discovery_error`) is separable from any static-estimate feature and should
   not wait on discovery UX.
5. **Orphan `refresh_team_signals`.** Any degraded-mode work should target
   `_compute_team_review` + live `discover_multi_locked` / `generate_team_review`, not
   assume the orphan node is wired.
6. **Pass 2 / fuller ability inventory.** Improving static fidelity beyond today’s
   counters helpers is a separate backlog item; not a blocker for labeled degraded
   discovery.

---

## Review gate

Approve or revise before an implementation plan:

1. Static estimate = type-effectiveness (+ existing counters axes as discovery filters
   only), never a matchup/KO substitute.
2. ADR-015-shaped boundary: degraded discovery OK when labeled; verified ranking /
   coverage / SPOF stay fail-closed without calc.
3. Provenance via existing `CandidateEvidence` (`mechanical_only` + `low` + explicit
   tokens), plus a structured result status — no second evidence model.
4. `multi_locked` ranking remains fail-closed; this task does not force every consumer
   into degraded mode.
5. First implementation targets should be: (a) stop `query_threat_counters` /
   `single_locked` from raising unstructured, (b) align `generate_team_review` public
   error surfacing — static candidate emission only where discovery-without-verification
   is actually useful.

---

## Scratchpad

- Goal: verify calc-failure non-uniformity; locate “legacy matchup fallback”; assess
  counters helpers; design ADR-015-shaped static boundary.
- [x] Trace multi / single / complete / bootstrap / leaf tools
- [x] Confirm refresh_team_signals orphaned on live graph
- [x] Confirm no dedicated legacy matchup fallback module
- [x] Confirm effective_move_type / type_effectiveness ceilings
- [x] Design doc (no code)
