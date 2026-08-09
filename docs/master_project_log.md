# PROJECT LOG — Pokémon Champions Agentic Team-Building & Battle Review System
## Reference document: living log of decisions, mistakes, and technical detail
## Load this at the start of every conversation in this project — don't ask for background.

---

## PURPOSE & CONTEXT

Portfolio project closing an "agentic AI" skill gap flagged across multiple job applications (ML Engineer / Data Scientist roles, 2026 cycle). Built in parallel with ongoing DPO/preference data labeling on VinylIQ's Condition Classifier.

**Why this project over alternatives considered:** Evaluated against a text-to-SQL agent, support-ticket triage agent, RAG/lit-review agent, chest X-ray triage agent, and an ASR hallucination-detection agent. All were passed over for saturation (SQL/triage/RAG are common portfolio categories) or cold-start risk (X-ray and ASR would require building domain judgment from zero in a 3-4 week window, unlike this project). This project won on **domain expertise transfer**: same "know the failure modes, don't just trust the model" judgment pattern that makes the VinylIQ interview answers strong, applied to a domain (competitive Pokémon) where the candidate already has deep, real expertise — not borrowed or newly acquired.

**Resume-facing framing (decide/refine as project matures):** Lead with the ML system, not the game. Working draft: "Agentic recommendation system with simulator-grounded evaluation and RL-policy-based decision review" — same pattern as VinylIQ leading with "End-to-End ML System for Vinyl Record Valuation" rather than "vinyl records."

**Game/format specificity (critical, do not genericize):**
- Target game: **Pokémon Champions** — a standalone game, distinct from mainline Scarlet/Violet (SV). This distinction is the core of the project's differentiation and its main anti-failure-mode design constraint.
- Formats on Pokémon Showdown:
  - `[Champions] BSS Reg M-B` — Battle Stadium Singles (singles format)
  - `[Champions] VGC 2026 Reg M-B` — VGC (doubles format)
- **Regulations update over time** (currently M-B) and each regulation has a **different legal pool of Pokémon and items**. The system must treat the regulation as a hard, versioned constraint, not a static assumption baked in once.
- Singles vs. doubles priority: **TBD — decide before scaffolding**, since team composition logic (especially doubles-specific mechanics like spread moves, redirection, follow-me) differs meaningfully between BSS and VGC.

---

## KNOWN LLM FAILURE MODES — design guardrails against these explicitly

Identified from direct hands-on experience using Claude and Google AI (Gemini) for team-building help before starting this project. These are not hypothetical risks — they are observed, repeated failures, and the project's core value proposition is catching what general-purpose LLMs get wrong here.

1. **Cross-game/format contamination (most common failure).** Recommending Pokémon, items, or strategies from **SV OU** (mainline Scarlet/Violet's most popular competitive format) that are **not legal in Pokémon Champions** at all, or not legal in the current regulation. This is the single most frequent and most damaging failure mode — it's not a subtle edge case, it's the default failure when a general LLM isn't grounded in Champions-specific, regulation-specific legality data.

### Addition to Known LLM Failure Mode #1 (cross-game/format contamination)

Confirmed as a *live* instance, not just a documented risk: during the 2026-07-27 role-play
design session, the assistant itself pulled Sinistcha's common singles-format moveset/role
reasoning when the actual context was VGC doubles — the exact failure mode #1 describes,
occurring in the assistant's own reasoning rather than as a hypothetical example. Reinforces
that format-scoping must be enforced structurally by whatever performs the real move/ability
lookup (ADR-002's tool-grounding principle), not relied upon as something a model gets right
by default, even within this project's own design process.

2. **Item legality errors.** Same root cause as #1 — recommending items that are banned, not yet released, or not implemented in the current regulation.
3. **Format/game confusion generally.** Beyond species/items specifically — rules, clauses, team size, and mechanics get blended across games/formats when the model isn't explicitly anchored to "this is Champions, this is Reg M-B, this is BSS/VGC" for every single recommendation.
4. **Unverified mechanical claims ("thinking things through" failure).** Model asserts conclusions about speed tiers, damage ranges, or matchup outcomes **without actually running the calculation** — sounds confident, isn't checked. This is a reasoning-rigor failure, not a knowledge-gap failure, and it's the hardest one to catch by inspection since the output reads as plausible.
5. **Dropping user constraints over a multi-turn conversation.** Ignoring or forgetting requirements the user specified earlier in a session (e.g., "no Pokémon with X," "must keep this specific Pokémon"). Flagged as lower priority for this project's core design, but still worth a basic regression check once multi-turn steering exists.
6. **Item Clause violations from team-blind set construction.** When deciding a Pokémon's
item during set-building, the model reasons about that Pokémon in isolation and doesn't
check what's already been assigned elsewhere on the team — resulting in two Pokémon
recommended with the same item, which is illegal under Item Clause. Observed directly in
hands-on testing (same category as the other failure modes above: confident output that
silently ignores a real constraint). Design implication: item selection must be checked
against `RecommenderState.team_draft` as a whole, not decided per-slot in isolation.

### Second confirmed live failure-mode-#1 instance (2026-07-29, reconciliation design session)

During design discussion of theme/archetype reconciliation, the assistant asserted Mega
Staraptor's typing as Normal/Flying (its base form's typing) without checking, when Mega
Staraptor is actually Flying/Fighting — a type change on Mega Evolution. Corrected in the same
session. This is the second confirmed instance of failure mode #1 occurring in the assistant's
own reasoning during design work (first: Sinistcha singles/doubles mixup, 2026-07-27) — not a
hypothetical risk, a repeated, observed pattern. Reinforces the standing conclusion: any
species/typing/ability claim must go through a real data lookup, including during design
discussion in this chat environment, not just in the shipped system.

---

## CURRENT STATE

- **Multi-turn steering:** Checkpointer-backed graph with conditional first-turn vs classify
  routing, handler nodes (lock/constraint/rejection/archetype-change/reset/restore), and
  `classify_pending` monkeypatch seam (no LLM provider dependency required).
- **ADR-020 reconciliation:** `recommender/reconcile.py` — four-tier `check_theme_fit` /
  OR-composite `check_archetype_fit`, `reconcile_on_archetype_change` +
  `reconcile_on_sibling_change`, `superseded`/`pending_flags`/`exempt_from_theme`, restore
  intent wired in graph. Tier 3 bounded to `infer_role`'s five archetypes until Role
  Compendium (ADR-019).
- **Pairwise threat classifier:** `recommender/matchup.py` — `classify_matchup(build_a,
  build_b, field=None)` with four-way outcomes, HP-based severity (`Severity` at
  `recommender.matchup.Severity`), contact-punish/multi-hit caveats, and (as of 2026-07-31)
  charge-move/recharge-move turn-economy corrections. Thread-scoped LRU memoization
  (`MATCHUP_MEMO_MAX_ENTRIES=8192`), bound via `RunnableConfig.thread_id`.
- **Team-wide coverage + SPOF:** `recommender/coverage.py` — `get_relevant_threats` (real
  in-game usage-rank sourcing, multi-form expansion via Showdown@1500, `TEAM_THREAT_N=50`),
  `compute_team_coverage`, `detect_spof`. New `team_review` intent routes to
  `generate_team_review` (standalone report, not wired into recommendation logic).
- **propose_team_draft:** Real implementation (no longer a stub) — dependency-circle
  propagation (ADR-015 Amendment 2026-07-27c), Choice-item mechanical-fit rules, N-attribute
  simultaneous-lock conflict handling, move-narrowing procedure (Amendment 2026-07-27f) with
  priority-gated delivery-mechanism grouping and usage-commitment-rate ranking, redundancy
  validation (A-precondition/A-team/B-threat-denial patterns), and a verification-gated
  kit-reinforcement layer (new ADR-021 principle). Role -> species selection remains an
  explicit, tested no-op pending the Role Compendium.

122 tests passing, 5 skipped, as of 2026-07-31.

**Phase:** Core recommender loop is now substantively real, not scaffolding — multi-turn
steering, reconciliation, threat-aware team review, and propose logic all exist and are
tested. Remaining major gaps: Role Compendium (ADR-019, blocks real role->species search and
full tier-3 role-membership coverage), move-narrowing's step 4 (opportunity-cost ranking),
ability-interaction taxonomy (Amendment 2026-07-27e), and ADR-018's full chat/graph UX
wiring (default+alternatives presentation, currently only a thin bridge function exists).

**Build order (deliberately sequenced, decided in advance):**
1. **Team recommender agent** (priority) — multi-turn, steerable, grounded in real regulation-legal data, produces a defensible team
2. **Showdown-simulated eval** (phase 2, may run in parallel with #3 if time allows) — win rate against known meta teams via Pokémon Showdown battle simulator. Deliberately sequenced after #1 because eval design is likely to be more complex than expected and should not block shipping the core agentic system.
3. **Battle log parser + RL-grounded piloting advice** (stretch goal) — text-box-anchored event detection from battle footage/replays, turn-by-turn structured log, compared against a trained RL policy for "here's what you did vs. what the policy would have done."

**MVP floor (the line scope creep is not allowed to cross without an explicit decision):** Team recommender with multi-turn user steering, grounded in accurate regulation-legal data, functioning and demonstrable — **without** the Showdown eval attached. This alone is a legitimate, defensible resume bullet. The eval adds a quantified proof point on top of it later; its absence does not invalidate the core system.

---

## ON THE HORIZON

- Decide singles (BSS) vs. doubles (VGC) as primary format before scaffolding — this affects team composition logic non-trivially
- Source real regulation-legal species/item data for Reg M-B (Pokémon Showdown's own data files, since Showdown already supports and maintains these formats, are the most likely accurate/current source — verify in Cursor before building against it)
- Decide orchestration approach: named framework (e.g., LangGraph) vs. hand-rolled loop — decide deliberately, be able to justify either choice under questioning
- Train a **new** RL policy specifically for Pokémon Champions / current regulation (see below) — old policy is not reusable
- Design the mechanical-verification tool call (speed/damage calculation) as a first-class component, not an afterthought bolted onto the recommender at the end

### New flagged gaps — real, agreed as needed, not yet designed

- ~~**Team-wide threat-coverage check:**~~ "does this team, as a whole, have a real answer to
  threat X" is a distinct, higher-level question from tier 3's per-slot breakpoint
  verification. **CLOSED 2026-07-31** — see `recommender/coverage.py` and the corresponding
  KEY LEARNINGS entry below.
- ~~**Single-point-of-failure detection:**~~ identifying that a team's win condition depends
  entirely on one Pokémon surviving/acting, with no redundancy (surfaced via the Mega
  Charizard Y / weather-war example) is a distinct capability from the above — a structural
  read of `team_draft` as a whole, not a per-threat check. **CLOSED 2026-07-31** — same
  module.
- Both are explicitly *pre-battle, team-composition* concerns (does the team have the tools)
  — not in-battle sequencing/positioning (timing, baiting switches), which remains correctly
  out of scope per ADR-012a, belonging to the deferred phase-3 battle-log/RL work.
- **`archetype`/theme-as-selection-driver needs explicit wiring when `propose_team_draft`
  is built — not a design gap, a linkage risk.** The mechanism for turning a locked species
  or a detected theme into active selection guidance for remaining slots is already fully
  designed (ADR-015 Amendment 2026-07-27a: intrinsic signal + teammate role abstraction →
  needed-role list), and the schema field it operates on (`archetype: Attr[str]`) landed in
  the 2026-07-29 ADR-017 migration. But nothing currently consumes it — `propose_team_draft`
  is still a stub. Surfaced originally via a free-text role-play mock conversation ("build a
  doubles rain team with Archaludon and Mega Swampert") that exposed the gap concretely: a
  team-level theme like "Rain" isn't a restriction (`constraints` handles those) — it's
  positive guidance that should actively bias candidate search for unfilled slots, and
  `constraints`' hard/soft-predicate shape can't represent that. Flagging explicitly now,
  before `propose_team_draft` implementation starts, so this doesn't get rediscovered from
  scratch or silently dropped — the design and the schema exist in two different places
  (ADR-015 and ADR-017) with nothing currently pointing from one to the other.
  **NOTE (2026-07-31): likely substantially addressed** by the dependency-circle propagation
  work (see KEY LEARNINGS below — Trick Room/Tailwind archetype mapping,
  `reconcile_on_archetype_change` consuming `archetype` directly) — worth a deliberate
  check/close-out decision rather than assuming this is fully resolved.

### New flagged gaps — real, agreed as needed, not yet designed (addendum)

- **Role Compendium scope gap: agnostic/flex roles.** Some Pokémon (e.g. Archaludon under a
  composite Tailwind+TrickRoom "TailRoom" archetype) are valuable specifically because they
  benefit from *whichever* speed-control tool a team ends up deploying, not because they serve
  one specific role. The Compendium's membership model (ADR-019/ADR-015 Amendment 2026-07-28d)
  has no category for this yet — it currently assumes a candidate is evaluated against one role
  at a time. Needs a "benefits from any of [X, Y]" membership shape, not just per-role
  membership tests run independently.
- **Enumerable-but-uncoded category sourcing (ADR-017's groundedness tier) has no identified
  data source yet.** "Blue Pokémon," "Eeveelutions," etc. need a real, checkable category
  definition per ADR-017's stated intent ("derivable once, then checkable like anything
  mechanical"), but no source (Bulbapedia or otherwise) has been identified, and Showdown's own
  data doesn't carry this. Real offline-extraction gap, same one-time-offline pattern as
  everything else per ADR-014, just not yet scoped.
- **Reconciliation's role-membership tier (tier 3, see ADR-020) is bottlenecked on the Role
  Compendium.** Until the Compendium exists, tier 3 can only draw on tier-2's five hardcoded
  archetype buckets — any role distinction finer than that falls through to judgment-only.
  Bounded, known gap; not open-ended.

### Threat-sourcing / coverage gaps (surfaced 2026-07-31)

- ~~**get_relevant_threats does not actually rank by usage.**~~ **CLOSED 2026-07-31.**
  `get_relevant_threats` now ranks by in-game doubles `usage_rank` (top `TEAM_THREAT_N=50`),
  expands multi-form lineages via legality `base_species_id` ∩ Showdown@1500 index (one
  `ThreatCandidate` per listed forme; Gmax omitted when absent from Showdown), and routes
  builds Showdown-per-form for multi-form / in-game OK for single-form. `TeamReviewResult.
  threats` is `list[ThreatCandidate]`; coverage/SPOF still consume unwrapped specs.
  Thread-scoped LRU memo on `classify_matchup` (`MATCHUP_MEMO_MAX_ENTRIES=8192`) binds via
  `RunnableConfig.thread_id` in `generate_team_review` — persists across turns in a thread,
  clears on thread change (not per review). Snapshot: `data/usage/champions-reg-mb.v1.json`
  schema v2 via `scripts/extract_usage/fetch_usage_mb.py`. Full sourcing arc (Pikalytics/
  MunchStats/Smogon comparison, rating-cutoff decision, N-value reconsideration) logged in
  KEY LEARNINGS below.
- **Ability-based field-forcing reuses contingent_value's setter-ability keys plus a new, thin
  ability→FieldSpec map**, not the theme/core detection mechanism designed in ADR-015
  Amendment 2026-07-27a (which remains unimplemented — it depends on the Role Compendium,
  still not built). This is a reasonable stopgap for now, not a replacement — should be
  revisited once the Compendium/theme-detector exist properly.
- **Slot has no ability field.** Coverage's field-forcing check currently backfills ability
  from usage data when a slot's own build doesn't carry one directly. This is a real schema
  gap (Slot's ADR-017 shape covers role/species/item/moveset/spread, not ability) worth
  deciding on deliberately rather than continuing to patch around via usage-data fallback.

### Deferred follow-up — breakpoint memoization (matchup-shape layer)

Store calc-derived KO/speed breakpoints for a fixed (species/moves/item/field) shape while
EV/nature/level vary; clear-side resolution only; no fuzzy similarity bucketing. Own future
task — not ADR-016 and not the coverage/SPOF PR. (Also logged in Claude's memory system for
this project so it isn't lost between sessions.)

---

## KEY LEARNINGS & DECISIONS

### RL policy: retraining from scratch, not reusing the old project
The original Pokémon Battler RL project (SARSA agents, custom reward functions, stochastic simulator) is **~6 years old** and was trained for a different, older competitive format. It is **not directly reusable** for Pokémon Champions — different legal pool, different mechanics-relevant regulation constraints, and six years of both meta and personal-skill drift make the old policy a poor reference point even conceptually. Decision: **train a new policy specifically for Pokémon Champions / the current regulation**, using the original project as a starting reference for algorithm choice and state-representation lessons learned, not as a transplantable artifact.
*Reference for original project (for lessons-learned, not reuse): SARSA agents, custom reward functions, stochastic simulator — see resume-tailoring project's master resume for the existing resume bullet framing.*

### Legality grounding is the architectural core, not a feature
Given the failure-mode analysis above, the project's central technical bet is that **legality checking (species, item, regulation) and mechanical verification (speed/damage calculation) must be tool calls against real data/simulation, never LLM-generated assertions.** Every other design decision should be evaluated against whether it protects or erodes this core.

### Sequencing decision (recorded explicitly to prevent later re-litigation)
Team recommender ships first. Showdown eval is phase 2 and is explicitly allowed to slip or be simplified if it proves harder than expected — this was decided in advance specifically so that eval scope creep doesn't block the core deliverable. If eval must be cut for time, the recommender alone (with steering + legality grounding working correctly) still counts as project completion for portfolio purposes.

### Design philosophy note, worth keeping in mind generally

Several resolutions during the 2026-07-27 session turned out to be "here's another valid
dimension," not "here's the right answer instead of a wrong one" — e.g., weather-setting via
ability vs. via move are both legitimate mechanisms, and bulk-and-answer vs. speed-and-remove
are both legitimate approaches to the same threat. Consistent with the multi-role
"present options, don't silently collapse" principle above — worth defaulting to surfacing
genuine alternatives where they exist, rather than the system converging on one as if it were
uniquely correct.

### Interaction-design note (2026-07-28)

The role-play design session itself surfaced a real UX shortcoming directly: excessive
open-ended questioning ("what do you want here?") creates friction and is harder for a user
to respond to than a concrete, named default with alternatives. This is now the standing
design principle (ADR-018) rather than something to re-derive per interaction — propose
first, let the user react, rather than asking before proposing.

### Domain mechanics notes, confirmed during 2026-07-28/29 mock-run testing

- **Aegislash's stat stages persist across its Stance Change forme switch (Shield ↔ Blade).**
  This enables a genuine, high-value sequence: set up Swords Dance safely in defensive Shield
  Forme, then attack from Blade Forme with the boost already applied — a rare case where a
  single mechanic solves both the setup-turn survival and payoff-turn output questions at
  once. King's Shield (a separate move) also lowers a contacting attacker's Attack stat,
  adding a further deterrent on top of Shield Forme's natural bulk.
- **Champions-specific priority values differ from older mainline generations for at least
  Follow Me/Rage Powder: both are +2 priority in Champions, not +3** as in some earlier
  generations — confirmed directly against Champions-specific sources, not assumed from
  general Pokémon knowledge.
- **Huge Power doubles the final, calculated stat — not the base stat** — a materially
  different result. Concrete example: Diggersby's level-50 Attack with max investment and a
  beneficial nature is 118, doubled by Huge Power to 236 — exceeding Mega Blaziken's 233 at
  equal investment, despite Blaziken's base Attack (160) being nearly triple Diggersby's (56).
- **A priority-granting ability (e.g. Prankster) does not extend to a follow-up attacking
  move after a self-targeting setup move** — Prankster boosts the setup move's own priority
  only; the deferred attack that follows gets no benefit from it. This is a materially
  different situation from Prankster boosting an instant-payoff move (weather-setting,
  screens), where the whole benefit resolves in the same priority-boosted action.
- **Weather-setting activation order among simultaneously-triggering automatic abilities
  respects Speed order, with the *slower* Pokémon's weather persisting** (since each
  activates in Speed order and later activations overwrite earlier ones) — being the slower
  of two simultaneous automatic setters is the actual advantage for guaranteeing your weather
  sticks, the reverse of the usual faster-is-better instinct.
- **A candidate's real competitive standing can be entirely conditioned on a specific,
  time-bound matchup against a specific top threat**, not a fixed property — e.g. Ariados's
  real value in Reg M-A came specifically from resisting both of a then-dominant Sneasler's
  STAB types; that value fades as the specific threat's prevalence changes, independent of
  anything about Ariados itself. Same pattern as Klefki's Charizard-Y/Garchomp exposure and
  Maushold's Wide Lens-availability dependency, confirmed again in a new case.

### Tool/environment limitation, confirmed 2026-07-29

Smogon's Strategy Pokedex (`smogon.com/dex/*`) is a client-rendered SPA; its actual data is
served via a `POST` to a `dex/_rpc/{dump-format,dump-pokemon,dump-basics}` endpoint (with a
JSON body) — discovered by Cursor in an earlier session using tooling not available in this
conversational environment. From within this chat, `web_fetch` cannot execute JavaScript or
issue a POST with a body, and `smogon.com` is not in this environment's allowed
`bash_tool` network list, so this endpoint cannot be reached at all here. Any mock-run or
design discussion needing a *complete* Smogon-sourced learnset/candidate list (as opposed to
what ordinary web search happens to surface) requires either the person supplying the data
directly (as done for the Swords Dance run), or deferring to the actual Cursor-side
implementation, which has real access to this endpoint. This is a structural limitation of
this chat environment, not something resolvable by searching harder.

### 2026-07-29: Post-design-phase Cursor impact assessment + sequencing decision

Ran a full codebase audit against everything designed since Tracks A-D (Role Compendium,
ADR-017/018/019, extensive ADR-015/016 amendments). Confirmed most of the design phase is
not yet reflected in code — schema (ADR-017), multi-turn steering, Role Compendium, and the
pairwise threat classifier (2026-07-28c) are all still greenfield. Two corrections to prior
assumptions: tier-2 has a real (if pre-Compendium-scoped) implementation, not a bare stub;
and the ADR-016 chain-lookup gap was already fixed in the working tree, now committed and
pushed (see ADR-016 Amendment 2026-07-27a status update).

**Sequencing decided:** ADR-017 schema first (hard dependency for steering, tier-2 rework,
and ADR-018 behavior). Then multi-turn steering and the pairwise threat classifier in
parallel — steering because master_project_log.md's own MVP floor requires it and it's
currently 100% stub; the classifier because it's schema-light (standalone function, doesn't
need Compendium or tier-2 rework) and is one of the two concretely-flagged designed-but-
uncoded gaps. Tier-2 rework and the Role Compendium construction pipeline (ADR-019) follow,
in that order, since tier-2 remains the rare path per ADR-016 and shouldn't block a
demonstrable core steering loop. ADR-018 interaction-behavior polish trails steering
naturally, once there's a real conversation loop to apply it to.

Python pack/export bridge and eval design remain deliberately unscheduled — eval in
particular can't produce meaningful numbers until steering + real tier-2/3 exist.

### 2026-07-29 (cont.): ADR-017 schema migration landed

Following the impact assessment and sequencing decision earlier this session, the ADR-017
schema migration (Attr-per-field Slot, archetype, Constraint scope/groundedness,
verification_log removal) is implemented and merged. 31 tests passing, 5 skipped, no
unexpected blast radius — matched or narrowed the pre-migration audit's guessed call-site
list exactly (recommend.py/quick_pick.py/graph steering stubs confirmed untouched; only
legality.py and nodes.py needed real edits).

This unblocks the next planned parallel track: multi-turn steering (closing the MVP-floor
gap flagged in this doc's CURRENT STATE section) and the pairwise threat classifier
(ADR-015 Amendment 2026-07-28c), both of which depend on this schema and can now proceed.

### 2026-07-29 (cont.): archetype schema follow-up landed; docs/ read-only boundary formalized

Following ADR-020's design (theme/archetype reconciliation), a small follow-up migration
corrected `RecommenderState.archetype` from `Attr[str]` (as ADR-017 originally shipped) to
`Attr[list[str]]`, matching ADR-020's composite-archetype-as-component-set model. Confirmed
near-zero blast radius via grep before editing, held on execution — only the TypedDict
annotation changed; no consumer code exists yet to touch.

Also, during this task, discovered and corrected a real process gap: Cursor's implementation
plan included a "docs sync" step that would have edited `docs/architecture_decisions.md` and
`docs/master_project_log.md` directly in the repo — files that are meant to be a read-only
mirror of this Claude Project, per `CURSOR_HANDOFF.md`'s existing feedback-loop framing. This
was caught before execution and corrected. Added an explicit, hard rule to
`.cursor/rules/project-context.md` (never edit these paths, flag back instead) and a pointer
to it from `CURSOR_HANDOFF.md`'s feedback-loop section, so this doesn't recur. Worth noting
as a real instance of the same "verify, don't assume" discipline this project already applies
to code — just applied to tooling/process boundaries instead of game data this time.

### 2026-07-29 (cont.): Multi-turn steering + ADR-020 reconciliation + pairwise matchup
classifier all landed

Three-track orchestrated implementation (parallel Task 1 steering skeleton + Task 3 matchup
classifier on isolated worktrees, Task 2 reconciliation logic gated on Task 1's merge)
completed successfully. Suite grew from 31 to 52 passing tests, 5 skipped, no regressions.

This closes out the MVP-floor gap flagged earlier this session (steering was 100% stub) and
gives the project a real, working multi-turn conversation loop for the first time — the
recommender can now hold constraints, locks, rejections, and archetype changes across turns,
with reconciliation correctly reopening or flagging affected slots rather than silently
accumulating stale picks. The pairwise threat classifier (ADR-015 Amendment 2026-07-28c) also
landed as a standalone, reusable function, independent of the steering work.

**What's now unblocked for next steps:** team-wide threat-coverage and single-point-of-failure
detection (the "New flagged gaps" items above) can now be built as consumers of the
matchup classifier, since it exists and is tested. Tier-2 rework and the Role Compendium
construction pipeline (ADR-019) remain the largest un-built pieces, per the sequencing decided
earlier this session (schema → steering/classifier in parallel → tier-2 rework →
Compendium → ADR-018 interaction polish).

Remaining deliberate scope gaps (not bugs, not forgotten): tier 3's role-membership reuse
stays bounded to tier-2's five archetypes until the Compendium lands; locked-species rejection
keeps the lock by default; reset leaves rejection history intact; restore supports one level
of undo only.

### 2026-07-31: Team-wide threat-coverage + SPOF detection landed; new gaps surfaced

get_relevant_threats, compute_team_coverage, detect_spof (recommender/coverage.py) shipped,
consuming the matchup classifier (Task 3, corrected 2026-07-31 for turn economy) and reusing
existing weather/terrain-setter signal data for field-conditional coverage. New team_review
intent routes to a standalone generate_team_review node (END, not propose_team_draft) —
correctly scoped as a report generator, not wired into recommendation logic yet, per design.
65 tests passing (up from 58), 5 skipped.

This closes both items previously listed under "New flagged gaps" (team-wide threat-coverage,
single-point-of-failure detection).

**Closed 2026-07-31 (threat ranking + forme expand):** `get_relevant_threats` now
ranks by in-game doubles `usage_rank` (top `TEAM_THREAT_N=50`), expands multi-form
lineages via legality `base_species_id` ∩ Showdown@1500 index (one `ThreatCandidate`
per listed forme; Gmax omitted when absent from Showdown), and routes builds
Showdown-per-form for multi-form / in-game OK for single-form. `TeamReviewResult.threats`
is `list[ThreatCandidate]`; coverage/SPOF still consume unwrapped specs.
Thread-scoped LRU memo on `classify_matchup` (`MATCHUP_MEMO_MAX_ENTRIES=8192`) binds
via `RunnableConfig.thread_id` in `generate_team_review` — persists across turns in a
thread, clears on thread change (not per review). Snapshot: `data/usage/champions-reg-mb.v1.json`
schema v2 via `scripts/extract_usage/fetch_usage_mb.py`.

**Deferred follow-up — breakpoint memoization (matchup-shape layer):** store
calc-derived KO/speed breakpoints for fixed (species/moves/item/field) while
EV/nature/level vary; clear-side resolution only; no fuzzy similarity bucketing.
Own future task — not ADR-016 and not this PR. (See ON THE HORIZON for the tracked entry.)

### 2026-07-31 (cont.): Usage-source overhaul for get_relevant_threats — full arc

What started as a narrow fix (get_relevant_threats returned snapshot insertion order, not
real usage rank) expanded into a substantial data-sourcing redesign after direct verification
against real sites (Pikalytics, MunchStats, Smogon) surfaced several compounding issues:

- Pikalytics' in-game ladder has real rank but no percentage, and doesn't separate Mega/
  other forms from their base species — a property of the in-game ladder data itself, not
  fixable by choice of site.
- Smogon's own Showdown-format usage stats for "[Champions] VGC 2026 Reg M-B" (same ruleset,
  hosted on Showdown rather than in-game) DO list forms separately with real percentages —
  confirmed directly (e.g. doubles: Charizard-Mega-Y 11.44%, Charizard-Mega-X 0.59%, base
  Charizard 0.10%; singles: 6.08% / 2.49% / 0.19%, a near-even case by contrast). An initial
  >90%-confidence-threshold design (inferring the dominant form from item-usage rate) was
  correctly discarded once it became clear Showdown's data already measures each form
  directly — nothing to infer once real, separate measurements exist. Both a heavily-skewed
  and a near-even real example were checked to confirm the final design (expand every
  Showdown-listed form as its own distinct ThreatCandidate, no threshold/branch logic) holds
  in both cases without special-casing.
- A related, separate risk was caught before it caused harm: detailed build data (item/
  moveset/EV/ability) mixes across base/Mega forms even more severely than rank does, since
  the forms have genuinely different base stats and item-slot constraints (Mega locks the
  item to the Stone, ADR-015 Amendment 2026-07-29c). Confirmed no existing tier-1/2/3 code
  was silently affected (exact to_id-keyed lookups, no base<->mega fallback already in place)
  before building the fix.
- Rating cutoff for Showdown-format data: settled on 1500, matching Smogon's own stated
  convention for "high-level" play, rather than an arbitrary value between available options.
- Default N reconsidered: team-level pool raised from an initial 20 (borrowed from the Role
  Compendium's differently-scoped target size, ADR-015 Amendment 2026-07-29b) to 50, and
  slot-level from 3-5 (ADR-015 Amendment 2026-07-25a's original range) to 5-10 — doubles VGC's
  real field of distinct threats, especially once Mega-forms expand into separate candidates,
  warranted a wider pool than the Compendium-derived number implied.
- Cost of the wider pool was caught honestly rather than assumed fine: classify_matchup
  batches moves within one matchup call, not across threats, so N=50 means real per-threat
  calc calls (~3k-5k HTTP calls for a full team_review), not free via existing batching.
  Addressed with a thread-scoped LRU memoization cache on classify_matchup (cap 8192,
  bound via RunnableConfig.thread_id) rather than accepting the cost outright — covers both
  detect_spof's own redundant N+1 masked-recomputation pattern and reuse across separate
  team_review calls within one session.
- A further optimization (breakpoint memoization — learning and reusing the actual stat
  threshold a calc result implies for a fixed matchup shape, rather than only caching full
  results) was deliberately deferred as its own future task rather than folded in here, given
  its added design/correctness surface area. Logged in Claude's memory system for this
  project so it isn't lost. Naive similarity-based cache bucketing was explicitly considered
  and rejected as unsafe.

80 tests passing (up from 65), 5 skipped. Closes the ranking-accuracy gap flagged when
coverage/SPOF first landed earlier today.

### 2026-07-31 (cont.): propose_team_draft — first real implementation, bounded scope

Fixed-order propose_team_draft (role -> species -> moveset -> item -> spread) shipped,
replacing the stub. Deliberately bounded, not the full ADR-015 dependency-circle model:
- Empty-role slots use compute_team_coverage/detect_spof (landed earlier today) as a real
  team-review-scale gap signal, combined with tier-2's five hardcoded archetypes (Trick
  Room/Tailwind mapped explicitly) — per ADR-015 Amendment 2026-07-27c's per-slot vs.
  team-review reasoning boundary.
- Role -> species selection is an explicit, tested no-op — genuinely requires the Role
  Compendium (ADR-019), which doesn't exist yet; left honestly unimplemented rather than
  faked with a shaky stopgap.
- Species-locked slot refinement uses tier-1 cache (get_resolved_build) first, tier-2
  (infer_role/role_spread) fallback, per ADR-016's tier-1-resolves-the-majority design.
- All proposed values are locked=False with proper ReasonRef provenance (new
  ReasonRef.kind: "tier1_cache" added). Propose never calls reconciliation logic directly —
  confirmed and tested as the correct boundary (reconciliation only fires on user actions).
- Cost-aware: coverage/SPOF's full calc-backed check only runs for genuinely empty drafts;
  partial-team role-gap checks use a cheaper boolean signal, avoiding unnecessary N=50-threat
  calc calls on every propose call.

A real, subtle bug was caught during plan review before implementation: gating regeneration
on Attr.locked (rather than Attr.value) would have meant every turn re-treated propose's own
locked=False outputs as unfilled and regenerated them from scratch, never stabilizing.
Separately, confirmed directly against ADR-020's shipped reconciliation code (not assumed)
that a reopened Attr's value is cleared to None (with the prior value preserved in
superseded, not left on the Attr) — meaning the simple value-is-None gate correctly handles
reconciliation-reopened slots too, no additional condition needed.

88 tests passing (up from 80), 5 skipped.

Deliberately deferred, not oversights: full dependency-circle resolution (any attribute
pinning first, propagating to others), move-narrowing (ADR-015 Amendment 2026-07-27f),
ability-interaction taxonomy (Amendment 2026-07-27e), and real role->species search (Role
Compendium, ADR-019).

### 2026-07-31 (cont.): Dependency-circle propagation + Choice-item mechanical-fit rules

propose_team_draft upgraded from fixed-order resolution to single-pass dependency-circle
propagation (ADR-015 Amendment 2026-07-27c): locked attributes now bias fills on other
unlocked attributes regardless of resolution order (Choice item -> spread/moveset bias,
Trick Room moveset -> role/spread), rather than only propagating forward through a fixed
role->species->moveset->item->spread sequence.

Choice Scarf's spread propagation includes a real, minority-case correction: rather than
always maxing Speed, a breakpoint check (tier-3-adjacent, via a new thin Speed helper) can
free excess investment into a nature change when natural Speed + Scarf's multiplier already
clears relevant benchmarks — scoped to Speed only (discrete, calc-verifiable tiers), not
applied to Choice Band/Specs' offensive stat (continuous damage range, no equivalent clean
threshold).

Two new mechanical-fit rules added to check_theme_fit, reusing ADR-020's existing reconcile/
apply_lock machinery rather than new infrastructure: Choice item + non-damaging move (with
Trick and Switcheroo correctly exempted after verifying real move-effect data — both
genuinely swap items with the opponent; Thief/Bestow were checked and correctly excluded,
since they move an item one-directionally rather than swapping), and Choice item vs.
Trick-Room-implied Speed-direction conflict. Both fire through the existing "most-recent
lock is ground truth, earlier conflicting lock auto-reopens (superseded-logged, restorable)"
pattern.

New capability: N-attribute simultaneous lock handling via simultaneous_lock_conflicts,
correctly partitioning a batch lock into conflict-free attributes (locked normally) and
conflicting pairs (left unlocked, pending_flags entry) rather than all-or-nothing rejection
— confirmed via the motivating case ("Vivillon with Sleep Powder and Choice Scarf": species
locks, item/moveset pair flags and stays unlocked).

Honestly scoped gaps, not oversights: ADR-015 Amendment 2026-07-27a's intrinsic archetype-
signal table and Amendment 2026-07-29d's relative-TR-Speed reasoning remain design-only
(no dedicated code) — this task's propagation rules fall back to existing infer_role/
role_spread(TR) rather than partially reimplementing either design inline. Tier-3's
breakpoint search remains a stub beyond the new narrow Speed-check helper built for this
task's Scarf correction specifically.

100 tests passing (up from 88), 5 skipped.

### 2026-07-31 (cont.): Move-narrowing procedure (ADR-015 Amendment 2026-07-27f) + ADR-021

Implemented the four-step move-narrowing procedure as a moveset-selection fallback for
propose_team_draft (tier-1 usage-miss path), plus a new standing architectural principle
(ADR-021) discovered along the way.

**Design evolved substantially through iteration, not shipped as first drafted:**

- Initial design used base-Speed/margin-threshold clustering to group "comparable" move
  candidates — discarded before implementation once it became clear this systematically
  excluded bulky/slow-but-viable candidates (a bulky Will-o-Wisp user has no need to
  outspeed anything) and that a single fast outlier could shrink a margin-based cluster to
  near-nothing even with several other good candidates further down.
- Replaced with: priority gate (skip delivery-mechanism grouping entirely for moves whose
  own fixed priority already overrides Speed/ability — confirmed against real Champions
  data: Trick Room priority -7, Follow Me/Rage Powder +2 not +3 as in some other formats;
  calc_client returns undefined for Trick Room's priority, requiring a manual override — a
  real gap in the vendored calc service's Champions coverage, not assumed/guessed around),
  then delivery-mechanism grouping (Prankster vs. natural-Speed) for normal-priority moves,
  then within-group ranking by usage commitment rate.
- Two proposed commitment-rate formulas (usage-share-of-move inverse-weighted by species
  popularity; then a multiplicative variant) were checked algebraically and both found to
  either collapse back to the same crowding-sensitive ratio or reintroduce a popularity
  bias — confirmed via worked examples, not asserted. Settled on direct commitment rate
  (usage_of_move_on_species / usage_of_species_overall), openly accepting its known
  crowding bias (a versatile species like Sableye scores lower per-move due to movepool
  competition) and bounding the damage via delivery-mechanism grouping (a crowded-but-good
  candidate only competes within its own small group, e.g. Klefki among other Prankster
  users) rather than trying to algebraically remove the bias.
- **Real data bug caught before shipping:** the flat/merged species_usage(...).common_
  moves[].pct field was confirmed, by checking the actual extraction pipeline rather than
  the field name, to silently mix two different computations — true in-game commitment
  data where present, a Showdown/MunchStats top-12-move-weight renormalization otherwise.
  Concrete mismatch found: Garchomp's Dragon Claw showed 85.6% via true in-game commitment
  vs. 22.6% via the flat merged field for the same species/move. Fixed by sourcing
  commitment_rate specifically from ingame_doubles.species[...].common_moves[].pct, with
  Showdown-only rows treated as missing/untrusted commitment data rather than silently
  using the renormalized number. Logged in memory for when this project extends to singles
  (must read ingame_singles's equivalent field, not the flat merge, for the same reason).
- A demotion-gate scope bug was caught before implementation: an early plan draft gated
  MIN_USAGE_PCT-based demotion on each delivery-mechanism group's individual size, which
  would silently fail to protect against a large TRUE pool split across multiple
  comfortably-small groups (e.g. 15 Prankster + 18 natural-Speed = 33 combined, each group
  individually under the threshold). Corrected to gate on the final, recombined pool size.
- assemble_moveset_fallback was corrected from implicitly re-running the full narrowing
  procedure per move (expensive, redundant) to a lighter composition (learnset intersection
  -> commitment sort -> Protect padding -> redundancy scrub).
- A real implementation blocker was caught during plan review before coding: propose.py's
  existing _refine_defaults only wrote the moveset Attr when both moves AND item were
  already set — meaning the entire new fallback path would have silently never landed a
  moveset in the common case. Fixed to write moveset independent of the item gate.

**New: ADR-021 (open-ended reasoning must be verification-gated).** Surfaced while scoping
move-narrowing's kit-reinforcement check (does a candidate's ability/typing/moveset
mechanically boost a given move's effectiveness — Tough Claws + contact, Adaptability +
STAB, Contrary + self-debuff, self-set weather enabling a move, etc.) — this space is
genuinely open-ended, not enumerable via any fixed checklist. Generalizes a pattern already
present piecemeal throughout the project (tier-2/tier-3's draft-then-verify relationship,
check_theme_fit's tiered groundedness) into an explicit standing principle: an LLM may
propose open-ended candidate interactions, but no specific claim affects any ranking/
decision until verified against real data (ability effects, move flags, calc-confirmed
magnitude differences). Implemented here as an injectable KitInteractionProposer (real LLM
in production, canned test doubles in CI — no new required LLM dependency, consistent with
how classify_input's chat-model seam was already built) feeding a mandatory verification
step, only breaking near-ties (within 5 percentage points of commitment rate) rather than
overriding the primary usage-based ranking signal.

**Also shipped:** redundancy validation (Amendment 2026-07-27f's "no duplicate functional
moves unless justified") with two independently-checkable justification patterns —
A-precondition (a locked move hard-fails without a self-set condition, e.g. Aurora Veil
requiring Snow), A-team (a teammate's ability benefits from a different condition, checked
concretely via ABILITY_TO_FIELD matching), and B-threat-denial (removes a condition a real,
named threat's kit depends on, e.g. Mega Charizard Y's Drought-Sun dependency) — plus
pick_default_and_alternatives as a thin, correctly-scoped bridge toward ADR-018's eventual
default+alternatives presentation format (UX wiring itself remains a deferred follow-up).

122 tests passing (up from 100), 5 skipped.

Deliberately deferred, not oversights: step 4 (opportunity-cost ranking) beyond what's
already built, proactive/generative tech-pick suggestion (agent unprompted recommending a
redundant-seeming move — validation-only was the explicit scope), Role Compendium, ADR-018's
full chat/graph UX wiring, and a Hail-literal cleanup (Champions confirmed Snow-only, no
Hail, across calc_client.py/handlers.ts/reconcile.py — flagged, not yet actioned).

### 2026-08-01: rank_and_cut — generalized narrowing utility, ahead of ADR-022's tools

Before building any of ADR-022's new tools (query_counters, etc.), extracted the "narrow a
pool by some key, tiered admission, cut to a cap" shape already implicit in
get_relevant_threats, move-narrowing's step 3, and ADR-022's own discovery-tier design into
a single shared utility (recommender/ranking.py: rank_and_cut), rather than let a fourth
ad hoc implementation accumulate. Retrofitting the two existing call sites onto it is a
separate, deliberately deferred follow-up — not done in this task.

The contract went through substantial design iteration before shipping, worth recording
honestly rather than presenting as arrived-at cleanly:

- Generalized beyond usage-data specifically: `key` is any sortable-value function (usage
  stat, mechanical-fit score, severity grade, or a discovery-tier assignment), not narrowly
  a usage-table lookup — confirmed this also makes pick_default_and_alternatives (move-
  narrowing's ADR-018 bridge) essentially a thin wrapper around this utility.
- Original mid-tier-slice design (fill tiers in order, slice whichever tier the cap falls
  within) was caught as unsafe before implementation: a naive skip-on-non-fit default for
  tiers below the primary one risks silently under-filling results even when valid lower-
  tier candidates exist — worse, for this utility's actual purpose, than the false-
  precision risk of filling to n.
- Real correctness bug caught in the same design pass: an earlier framing scoped the
  "always fully keep this tier" exception to literal tier-index-0, which fails if tier 0
  happens to be empty (a real, expected case — e.g. "no Follow Me user is inherently
  better than another for delivery-mechanism reasons alone," so nothing populates an
  obvious/primary tier at all). Resolved by making Rule 1 (unconditional full-keep) about
  the actual tier-0 bucket specifically (verified empty tiers behave correctly via ordinary
  empty-list semantics, no special-casing needed) combined with Rule 2's fill-to-n phase
  correctly applying to whichever tier is first populated.
- Deliberate, intentional non-uniformity in the `slack` parameter: int is an ADDITIVE bound
  on top of n; float is a MULTIPLICATIVE total bound — two different formulas that both
  happen to express "no bonus room" via their own identity value (0 and 1.0 respectively),
  not one continuous formula encoded two ways. Documented explicitly as intentional rather
  than "simplified" into a single formula, given the risk of an implementer reasonably
  assuming one continuous scale and getting the boundary wrong.
- `order` (ascending/descending, explicit) chosen over a `reverse: bool` flag specifically
  for self-documentation at call sites — a real, meaningful parameter (not just naming
  preference), since an explicit "anti-meta" use case (deliberately preferring low-usage
  candidates) is a plausible future caller need this project has separately identified.
- Real bug caught during plan review, before implementation: naive tier iteration
  (`for t in sorted(buckets)`) could process a hypothetical negative tier index under
  Rule 2's bonus-tier logic before tier-0's unconditional keep ever ran, silently
  violating the tier-0 guarantee. Fixed by explicitly handling tier-0 via `buckets.get(0,
  [])` first, independent of however the remaining tier indices sort.
- n=0 is a valid input (tier-0-only, no bonus tiers admitted) with a well-defined meaning
  under Rule 1; only negative n raises.

137 tests passing (up from 122), 5 skipped. No existing call sites touched — retrofitting
get_relevant_threats and move-narrowing's step 3 onto this utility remains a separate,
explicitly deferred task.

### 2026-08-01: ADR-022 (generalized narrowing loop), rank_and_cut utility, and retrofit

Substantial design session extending yesterday's work into a general architecture for
slot-filling and candidate search, plus a new shared ranking utility consuming it.

**ADR-022 (new): slot-filling as a generalized narrowing loop.** Replaces the implicit
assumption of a fixed cascade (establish theme -> pick core -> find teammates -> refine
slot) with one loop: check if the candidate pool is presentable (ADR-018's existing
judgment), if not apply whichever narrowing tool is available given current state, repeat.
Motivated by two real cases a fixed cascade couldn't handle: a theme that's real and
constraining but not specific enough to imply an anchor (mono-Fairy narrows legality but
suggests no particular Pokemon), and the recognition that "how well-defined is a
candidate's teammate/support/threat profile" collapses exactly onto "does it belong to a
known archetype/role" (confirmed via the Mega Staraptor case, which has neither). Specifies
a two-stage pattern (cheap tiered-filter to a tractability cap, then deep verification-
gated reasoning, then cut to presentation size) generalizing move-narrowing's existing
shape; four new Compendium-independent tools (query_counters, query_counter_of_counters,
query_support_needs, query_theme_refinement_candidates); and three distinct, non-
interchangeable usage signals (popularity, discovery, cooccurrence) that must not be
conflated. ADR-019 and ADR-021 each received a small amendment connecting this design to
their existing scope (tiered admission generalizes to Compendium construction; usage-
flagged-but-unexplained candidates are a legitimate ADR-021 proposal source).

**rank_and_cut (recommender/ranking.py): shipped.** Extracted the "narrow a pool by a key,
tiered admission, cut to a cap" shape already implicit in get_relevant_threats and move-
narrowing candidate search (renamed from "move-narrowing" in conversation to avoid reading
as movepool search) into one shared, generic utility — `key` is any sortable-value
function, not narrowly usage data. Design went through substantial correction before
shipping: an original mid-tier-slice approach was replaced with a firm rule (tier 0 is
always returned in full, unconditionally, since `n` is an arbitrary tractability number and
tier 0 represents candidates with no principled basis for exclusion — the function can
return more than `n`); a real bug (naive tier iteration could process a hypothetical
negative tier index before tier 0's guarantee ran) was caught in plan review and fixed;
`slack` has deliberately different int (additive) vs. float (multiplicative) semantics,
both expressing "no bonus room" via their own identity value; `order` (ascending/
descending) is explicit rather than assumed from key type, since ordinal usage-rank data
and percentage-usage data require opposite sort directions for the same "more popular"
meaning. 137 tests passing (up from 122).

**Retrofit: get_relevant_threats and move-narrowing candidate search onto rank_and_cut.**
Confirmed get_relevant_threats has no real tiering (flat ordinal usage_rank, ascending,
ranked on pre-expand ladder rows so empty form-expansions don't consume n) and move-
narrowing's existing Prankster/natural-Speed delivery-mechanism split maps directly onto
rank_and_cut's tier parameter. Surfaced and corrected a real, previously-unexamined
behavior gap during this retrofit: the currently-shipped MIN_USAGE_PCT demotion could let a
well-supported natural-Speed candidate outrank a demoted, low-sample Prankster candidate —
crossing the tier boundary. This was never a deliberate design decision (it fell out of a
stable sort over the whole recombined list without the cross-tier implication being
examined) and was corrected as intentional: demoted Pranksters now always outrank natural-
Speed, since the entire reason delivery-mechanism is a TIER (not just a ranking factor) is
that it was judged categorically more important than usage. Three affected tests rewritten
with explicit before/after documentation rather than silently patched. CBD commitment-rate
sourcing (ingame_doubles-specific, per the 2026-07-31 fix) confirmed preserved exactly.
137 tests passing, no regressions.

**ADR-021 Amendment 2026-08-01b: verification must also tag WHICH mechanical axis an
interaction affects.** Surfaced while designing move-narrowing's tier-0 for damaging moves
(not just Prankster-gated status moves) — confirmed only 7 Prankster users are legal in
Champions M-B, but Prankster is irrelevant to damaging moves entirely; for those, tier-0
should be power-boosting-ability-class candidates (Adaptability/Technician/Tough Claws),
ranked within-tier by boost magnitude with usage as a same-magnitude tiebreak. Further
generalized via the Zap Cannon case (120 BP / 50% accuracy): a power-boosting ability
doesn't address this move's actual bottleneck (accuracy) the way No Guard does — these
aren't comparable magnitudes on one scale, they answer different mechanical questions, and
determining which axis is the real constraint is itself real judgment (not a fixed
threshold), correctly kept inside the reasoning step rather than hardcoded. Two further
cases confirmed verification must be kit-aware and candidate-specific, not a flat ability
table: Adaptability's effect is conditional on whether a move is actually STAB for a
specific candidate (not a fixed ability-level fact), and Milotic can address Hypnosis's
imperfect accuracy via Coil (a move, not an ability) — verification must scan a candidate's
full kit (ability + typing + moveset), not ability alone. Confirmed this is the same
underlying mechanism already needed for Role Compendium ranking (Amendment 2026-07-28d) —
one shared reasoning/verification function should serve both, not two separately-drifting
implementations.

**Deliberately deferred, not built:** the axis-tagged verification mechanism itself
(design-only per the amendment; a concrete build task is a named follow-up), richer tier-0
definitions for move-narrowing candidate search's damaging-move case (currently retains
today's simpler Prankster/natural-Speed structure; ships as-is per explicit decision not to
block the reviewed, ready retrofit on unscoped follow-on work).

### 2026-08-01 (cont.): query_counters — first ADR-022 tool, shipped

First real tool from ADR-022's raw-mechanical-reasoning toolkit: given a Pokemon, find
real, currently-relevant threats via two static, calc-free axes (merged from an original
three-axis design — KO-threshold and coverage-threat were found to be the same underlying
question, "does this candidate have a move that deals threatening damage," differing only
in STAB status, and were combined; wall-check remains separate).

KO_THRESHOLD_BP settled at 200 (not 180) via an empirical probe on real anchor/candidate
data, re-run twice as the underlying formula was corrected (axis merge; multi-hit expected-
value using real per-count distributions plus a separate accuracy factor, with Skill Link/
No Guard/Compound Eyes handled as distinct, verified cases — Compound Eyes confirmed as a
1.3x modifier, not a full guarantee, checked rather than assumed). A real formula bug
(Skill Link's guaranteed hit count still being multiplied by the move's own base accuracy
on top, double-penalizing a move like Population Bomb) was caught in plan review before
shipping. Move accuracy data, absent from the legality/calc snapshot, sourced as a
committed static extract (data/moves/gen9_accuracy.v1.json).

A real bug was found and corrected post-ship: Ceruledge (a legitimate wall-only threat to
Mega Blaziken) was missing from default results (n=20) due to within-tier ranking, not
tier/slack policy as initially suspected. The KO-threshold-primary composite key meant
every capped (=1.0) tier-0 candidate tied on the primary sort component, making usage the
de facto but unstated tiebreak; flipping the key to usage-primary, KO-score-secondary was
the actual fix (confirmed: Ceruledge moved from missing at tier-1 index 21 to present at
index 10). A proposed slack-based fix (multiplicative bonus-tier headroom, requested
separately) was empirically shown NOT to solve this class of problem — no multiplier ≤3
ever admits a large tier-1 whole once tier-0 alone reaches n, since "keep whole" only fires
when a tier fits within the bonus bound. Slack=1.5 shipped as requested (real, proportional
headroom, useful for smaller n where tier-0 doesn't already fill the cap) but is explicitly
documented as not the mechanism that fixes wall-only starvation at the tool's actual
default.

151 tests passing (up from 137 after the ranking-utility retrofit).

Deliberately deferred, not oversights: stat-fragility axis; ability-conditional damage
modifiers beyond the specific abilities checked (Skill Link/No Guard/Compound Eyes) —
deferred to ADR-021 Amendment 2026-08-01b's not-yet-built axis-tagged verification
mechanism; query_counter_of_counters, query_support_needs, query_theme_refinement_
candidates (remaining ADR-022 tools); a documentation clarification distinguishing
ADR-022's stage-1 n=20 tractability cap from ADR-015 Amendment 2026-07-25a's unrelated
tier-3 opponent count (3-5) — flagged, not yet written.

### 2026-08-02: query_threat_counters — second ADR-022 tool, shipped

Second tool from ADR-022's toolkit (named query_threat_counters in code; ADR-022's
original text calls this query_counter_of_counters — renamed during design discussion for
clarity, doc correction still needed, see below). Given an anchor, finds real candidates
that counter the anchor's own threats, with final ranking driven by VERIFIED classify_
matchup outcomes against the anchor's most-likely-encountered threats, not just static
typing/movepool claims.

Six-stage pipeline, refined substantially from ADR-022's original sketch during design:
query_counters(anchor) run at FULL, untrimmed output (not pre-cut to 3-5 as ADR-022's text
describes) -> query_counters(threat) run FULL for every threat, not a pre-cut subset ->
merge across all threats' candidate lists, tracking distinct-threats-countered count ->
rank_and_cut on the merged pool (count + usage composite key) cut to ~10 -> a SEPARATE,
purpose-specific rank_and_cut re-selection of the ORIGINAL full threat list, usage-only
(ignoring query_counters' own danger-first tiering), cut to top-5, specifically for
choosing which threats are worth real calc-service verification against (reasoning: the
question "which threats are worth spending real calc calls on" is "which are we likely to
actually face," which should weight toward raw popularity more than query_counters' own
mechanical-danger-first ordering) -> classify_matchup verification (~5x10=50 calls) as the
REAL final ranking step, not a confirm/discard gate on an already-final static order — a
candidate with fewer but more decisively-verified counters can and should outrank one with
a higher static count but weaker verified performance.

Design correction made explicit during this build: early trimming (popularity-filtering to
3-5 threats BEFORE recursing, as ADR-022 originally specified) was deliberately rejected —
a candidate's true value (countering several threats) is only visible once evaluated across
the full cross-product; trimming happens only after merging, never before.

A real gap was caught in plan review before implementation: the merge step needed to
retain enough threat identity to look up full builds for later classify_matchup calls
(threats_by_id lookup added), and merge-tiebreak determinism was tightened (best/lowest
usage_rank across all appearances, not first-seen-in-iteration-order, which would have
been silently nondeterministic).

160 tests passing (up from 151), 5 skipped.

Doc drift flagged, not yet corrected: ADR-022's written text still names this tool
query_counter_of_counters and describes early popularity-filtering before recursion —
both details are now inaccurate relative to the shipped design (rename + the deliberate
full-then-trim-after-merge correction above). Needs an ADR-022 amendment.

Deliberately deferred, not oversights: query_support_needs, query_theme_refinement_
candidates (remaining ADR-022 tools); the axis-tagged verification mechanism (ADR-021
Amendment 2026-08-01b, still design-only).

### 2026-08-02 (cont.): query_support_needs — third ADR-022 tool, shipped

Third tool from ADR-022's toolkit. Given an anchor and role-shape context, surfaces named
support-need options (screens/healing, ability/kit-conditional needs, Speed-axis needs) —
does NOT rank/score needs, does NOT resolve a chosen need into candidates (that dispatch
stays a separate, later step per design). Returns [] on a clean upstream archetype match,
per ADR-022 Amendment 2026-08-02b's scoping (this tool is the fallback for anchors that
didn't classify cleanly, not a general-purpose analyzer).

Design went through substantial refinement during this session, each correction driven by
a concrete counterexample rather than abstract reasoning:
- Healing/screens was originally scoped as a flat universal need, then corrected twice:
  first to gate on tank-vs-glass shape, then to the final, correct rule — universal ONLY
  for offense-primary (attacker) anchors, since a support piece's relationship to its own
  survival varies too much for a blanket default (a Tailwind setter's value is delivered
  instantly on setup; lingering afterward can cost tempo, not help).
- A tank-no-self-heal need stays a separate, non-duplicating conditional trigger, enriching
  (not doubling) the universal healing entry when both apply to an offense-tank.
- Defensive-stat-asymmetry-implies-coverage-need required a role-shape prerequisite after
  repeated counterexamples (Archaludon: asymmetry matters because it's tank+offense-primary;
  a glass cannon's low bulk is an accepted tradeoff, not a gap; Farigiraf carries strong
  attacking moves while being fundamentally Trick-Room/priority-denial support, its
  offense serving as insurance per the same Taunt-insurance principle as Amendment
  2026-07-27e) — this confirmed role-shape classification could not be a fixed heuristic and
  belongs upstream (orchestrator-level, ADR-022 Amendment 2026-08-02b), not inside this tool.
- A three-layer Speed-axis trigger was added: self-contained Speed-solving abilities
  (Speed Boost) suppress the need entirely; condition-dependent Speed abilities (Swift Swim,
  Sand Rush, etc.) redirect the need to "secure the enabling condition" (reusing the
  existing ABILITY_TO_FIELD table, checked against team_draft) rather than Trick Room/
  Tailwind; only then does a genuine Speed-tier-based Trick Room/Tailwind need/want
  distinction apply (reusing ADR-015 Amendment 2026-07-29b's two-axis execution-risk
  model). Explicitly NOT building a tier-2 stopgap "weather beneficiary" archetype to
  pre-empt this trigger — that category already belongs to the Role Compendium (Amendment
  2026-07-28d); building a duplicate now would likely be throwaway work. Logged as a
  deliberate follow-up: once the Compendium exists, audit which query_support_needs
  triggers (this one especially) are still doing real work versus fully absorbed by clean
  upstream classification, rather than guessing now.
- A real correctness bug caught in plan review before implementation: move_priority
  returned 0 for known-priority moves (Aqua Jet, Bullet Punch, etc.), which would have
  silently collapsed the Layer-3 need/want distinction (every low-Speed attacker treated
  as priority-less). Fixed via a local, direct priority-move set rather than the
  apparently-incomplete shared function.

176 tests passing (up from 160), 2 skipped [confirm reason for the skip-count drop from 5].

Deliberately deferred, not oversights: query_theme_refinement_candidates (last remaining
ADR-022 tool); need-to-candidate resolution (move-narrowing/Compendium/ability-search
dispatch — explicitly not built here); the axis-tagged verification mechanism (ADR-021
Amendment 2026-08-01b); Role Compendium itself.

### 2026-08-02 (cont.): query_by_usage + uniform pool interface — ADR-022 toolkit complete

What began as designing a fourth, separate tool (query_theme_refinement_candidates — given
an under-constrained locked theme like mono-Fairy, propose narrower compatible sub-themes)
resolved into a broader architectural simplification instead of a new tool.

The original framing required enumerating the space of possible sub-themes directly, which
has no natural, bounded answer ("what sub-themes exist below mono-type?" isn't enumerable
the way "which species satisfy mono-Fairy" is). Reframed around species instead of themes:
enumerate the legality-filtered species pool (already solved, bounded), infer each
candidate's natural theme via existing archetype classification, and let compatibility
checking happen per-candidate — at which point the operation became identical in shape to
query_counters/query_threat_counters, just with a narrower starting pool. This generalized
into a standing interface principle (ADR-022 Amendment 2026-08-02d): every query tool
should accept an optional candidate_pool, and any tool/mechanism producing a species list
(a legality filter, a future Role Compendium category, another query tool's own output) is
a valid source for another tool's pool input — composable, stackable tool chaining rather
than a fixed pipeline order. query_theme_refinement_candidates is retired as a planned
separate tool; its function is now served by pool-narrowing plus the new bootstrap tool
below.

**query_by_usage(pool=None, n=20): new, shipped.** The toolkit's bootstrap mechanism — ranks
a candidate pool (full legal pool by default, or any narrower pool) by usage alone via
rank_and_cut, no axes, no verification. This is the concrete mechanism for two previously-
unimplemented branches of ADR-022's narrowing loop: "nothing exists yet" (surfaces real,
usage-grounded starting options rather than an invented pick) and "under-constrained theme"
(mono-Fairy has no single natural anchor -> query_by_usage on the theme-narrowed pool gives
real starting candidates).

**query_counters and query_threat_counters retrofitted with an optional candidate_pool
parameter**, strictly additive (None preserves prior unrestricted behavior exactly). A real
mock-breaking bug was caught in plan review before implementation: unconditionally passing
the new parameter as a keyword (even at its None default) would have thrown TypeError
against existing test doubles with fixed signatures — fixed by only passing the kwarg when
actually set. query_threat_counters' pool restriction is asymmetric by design and verified
by a dedicated test: pool restricts only the candidate/teammate-producing side (step 2+),
never threat identification (step 1 always searches the full, unrestricted meta) — a locked
team theme narrows who's being searched FOR, not what threatens the anchor.

182 tests passing (up from 176), 5 skipped.

This completes ADR-022's tool inventory as currently scoped: query_counters,
query_threat_counters, query_support_needs, query_by_usage — plus the uniform pool-
composition contract connecting all of them. Deliberately deferred, not oversights: the
axis-tagged verification mechanism (ADR-021 Amendment 2026-08-01b); Role Compendium (ADR-
019, which would become a further pool source once built, per Amendment 2026-08-02d); the
top-level orchestrator/LangGraph wiring that actually calls these tools in sequence (still
conceptual, per ADR-022's own text — none of these four tools are wired into
propose_team_draft's live decision loop yet).

### 2026-08-02 (cont.): ADR-023 — orchestrator consumption procedure, shipped

Closes the structural gap directly identified by a role-play stress-test session earlier
today: the four ADR-022 tools (query_counters, query_threat_counters, query_support_needs,
query_by_usage) existed and were independently correct, but nothing connected them into an
actual, closeable slot-fill loop. The role-play surfaced two real orchestration failures,
distinct from factual/data errors: (1) a candidate satisfying both the threat-counter and
support-needs branches (Farigiraf, in a Kingambit-anchored scenario — answering Psychic
pressure from Staraptor/Sneasler while also resolving an open Trick-Room-setter need) was
not connected until explicitly prompted; (2) the orchestrator ran the three query tools and
then simply stopped, with no specified terminal action ever reached.

Shipped: SlotFillContext (per-invocation scratch state, not part of team_draft),
annotate_overlap (mandatory, runs as soon as both branches' initial outputs exist, before
any need is chosen — the structural fix for finding (1)), merge_need_resolved (a second
mandatory merge once a chosen need is resolved to candidates), and run_slot_fill_terminal
(present via the existing pick_default_and_alternatives -> receive via classify_input's
lock-intent contract -> commit via the existing apply_lock -> hand off to the existing
refinement pipeline -> deferral as a legitimate, non-error exit) — the structural fix for
finding (2). Every piece of the terminal action chains entirely pre-existing, already-
shipped mechanisms; no new locking/presentation/refinement logic was built.

Two small, independently-justified numeric fixes folded in from the same review: team-
state-scaling moves/abilities (Supreme Overlord, Last Respect: assumed 2 fainted teammates,
averaging the nonzero {1,2,3} states; Rage Fist: assumed 1 hit taken, kept SEPARATE from the
fainted-teammate figure since it's a genuinely different scaling mechanism — accumulating
hits requires repeatedly surviving attacks, an increasingly implausible and disproportio-
nately dangerous state the higher it climbs, so a low, deliberately conservative estimate
was chosen rather than reusing the fainted-teammate number). classify_matchup's
verification-build sourcing resolved: use the most common cached build (usage-informed
cache spread), falling back to a usage-sourced build when no cache entry exists — reusing
the existing tier-1/tier-2 fallback relationship rather than new logic.

Two real type-shape bugs caught in plan review before implementation: AnnotatedCandidate
originally couldn't represent a need-only match (no threat-counter data to attach) —
corrected to a unified row (species identity + optional threat-side payload); need_resolved_
candidates was specified against the wrong type (ThreatCandidate) when the real move-
narrowing function (narrow_candidates_for_move) actually returns list[str] — corrected to
match the real signature rather than a guessed shape.

192 tests passing (up from 182), 5 skipped.

**Important scope note, not yet fully closed:** of ADR-022's three need-resolution dispatch
paths (move-narrowing, Compendium/role lookup, ability-tag search), only move-narrowing is
real. The other two (defensive_coverage, condition_setter, stat_lowering_partner resolve
paths) raise NotImplementedError — a loud, correct failure mode, but it means a real
fraction of query_support_needs' surfaced options cannot currently be resolved to
candidates at all. The loop is closed for the move-narrowing path specifically, not
universally — worth being precise about this distinction rather than treating ADR-023 as
having fully closed the gap the role-play surfaced.

Deliberately deferred, not oversights: Compendium and ability-tag-search dispatch paths
(stubbed); the Mega-count soft-heuristic (ADR-023 Amendment 2026-08-02a item 5, tied to
future quick-pick design); real classify_pending wiring; Role Compendium itself; the axis-
tagged verification mechanism (ADR-021 Amendment 2026-08-01b).

### 2026-08-03 (cont.): CAP/non-official content provenance audit and fix

Surfaced while reviewing Phase B of the ability classification table: Cursor flagged
"Persistent" (a CAP — Create-A-Pokemon community project — ability) as present in the
extracted table, looking like official content. This led to a systemic audit across
abilities, moves, and species for whether CAP/non-official content is durably,
explicitly distinguishable from official content at the DATA level (not just currently
inert via a legality/actionability join) — since a live join only protects against CAP
content being used TODAY, not against a future official addition silently colliding with
a stale, unmarked CAP entry sharing the same name/id.

Audit found three different states across the three data types:
- Moves (legality snapshot): already durable — is_nonstandard sourced from Showdown's
  mechanical data.ts, correctly flagged (CAP moves stored, not silently absent).
- Species (Champions snapshot): mostly safe, but by ABSENCE rather than a stored flag —
  CAP species simply never enter the Champions-scoped join today; the isNonstandard
  marker exists and works correctly for other stored nonstandard categories (Past/
  Future/etc.), but there's no positive "CAP" row to check against. Documented as a
  known, pipeline-shape-dependent risk (protection could silently disappear if the
  species-merge pipeline were ever refactored to filter later) rather than fixed, since
  no current gap exists to fix.
- Abilities and the move-accuracy extract (gen9_accuracy.v1.json): both were REAL, open
  gaps — both extracted from Showdown's text-only source files (data/text/abilities.ts;
  an accuracy-only extract) with no cross-reference to the mechanical data files that
  actually carry is_nonstandard, meaning CAP/nonstandard content was present but
  completely unflagged in both tables.

Fixed by joining both extracts against Showdown's real mechanical data (data/
abilities.ts for abilities; the same mergeMoves(base, [championsMoves]) pattern the
legality snapshot already uses for moves, needed to correctly reach the verified
454-entry Champions-effective nonstandard count for the accuracy table — a naive join
against base moves.ts alone only accounted for ~269 non-null entries, undercounting by
over 150 real nonstandard moves).

A real, initially-uncertain edge case resolved cleanly during this work: As One's two
variants (Calyrex-Ice: Chilling Neigh+Unnerve; Calyrex-Shadow: Grim Neigh+Unnerve) were
suspected of being a Showdown-simulation-only split not reflected in the official games.
Checked directly and confirmed FALSE — official games track these as two genuinely
distinct Ability-index entries (266/267) with forme-dependent effects; Showdown mirrors
a real official distinction, not inventing one. The shared "asone" text-only id is
purely a messaging convenience (for generic in-battle references like Mummy/Trace
copying "As One" without naming a specific forme) — correctly handled as the one
expected text-only exception in the extraction's completeness check, not a data gap.

Final verified inventories: abilities (321 total) — 311 null (official), 6 Future, 3 CAP
(mountaineer, rebound, persistent), 1 Past (noability — notable, since it had been
assumed inert rather than checked). Move accuracy (954 keys, Champions-effective
merge) — 500 null, 437 Past, 13 LGPE, 3 CAP, 1 Future — 454 non-null, exactly matching
the legality snapshot's already-established count.

13 tests passing (test_cap_provenance.py expanded).

Deliberately not fixed, documented as an accepted, monitored risk: species' CAP-safety-
by-absence (no code change needed today, but the risk is real if the pipeline shape
ever changes) — a comment/test documenting this exists rather than a structural fix,
since there's no current gap to close.

### 2026-08-03 (cont.): query_support_needs completeness — FO gate + support-primary scope

Completeness audit of query_support_needs triggers (Compendium 28d diff + taxonomy
buckets + empirical batch). One real gap implemented: widen `fake_out_protection` to also
fire when `primary_function==offense` and `tankiness==glass` (not only `setup_dependent`);
same need category, wider gate; `taunt_disruption` stays setup-only. Skip list unchanged
(Intimidate-as-universal, ally-amp, Friend Guard cluster, field-clear, general Weather
Setter).

**Support-primary + match_status=none emptying — accepted scope boundary, not a second
gap.** Evidence available today (no live orchestrator telemetry yet — RoleShapeContext is
only constructed in tests / SlotFillContext; nothing wires production call frequencies):

1. ADR-022 Amendment 2026-08-02b: orchestrator runs archetype/role classification first;
   clean match IS the answer and raw tools are not the path. Named doubles Support roles
   (Weather Setter, Redirection, Trick Room Setter) are exactly that upstream vocabulary.
2. Test corpus never uses support + `match_status=none`; support cases use `partial` and
   still surface when mechanical gates apply (Tornadus: no screens/healing by design;
   support-tank asymmetry → coverage+heal; Farigiraf setup → FO+Taunt).
3. Glass support emptying (Whimsicott-shaped) is not a silent miss of encoded gaps — this
   tool's tables are mostly offense Spe / offense universals / kit conditionals; a
   provider-shaped support piece's teammate profile is Compendium membership, not
   attacker's residual needs. Deliberate: healing/screens already offense-primary-only.

Revisit only once Compendium + real orchestrator classification frequencies exist.

### 2026-08-03 (cont.): query_support_needs completeness audit + FO/redirection gate widening

Ran a structured completeness check on query_support_needs' trigger set — not just internal
consistency (already confirmed), but whether real teammate-need categories were missing
entirely. Combined three methods: a Compendium-category diff (Amendment 2026-07-28d's
planned doubles Support vocabulary vs. current triggers), a taxonomy-combination audit
(every teammate-providable target/activation/purpose combo, checked for trigger coverage),
and an empirical re-run across 16 varied real anchors. A naive full-ability-enumeration
approach (every purpose=support/disrupt ability, flagged as a gap if uncovered) was tried
and correctly abandoned — it produced false positives from abilities with no teammate-need
semantics at all (self-targeting drawback abilities under purpose=disrupt); filtered to
teammate-relevant combinations first instead.

One real, well-evidenced gap found: fake_out_protection/redirection was gated to
setup_dependent anchors only, but glass offense-primary anchors (Garchomp, Flutter Mane —
though the initial empirical sample was found to include non-Champions-legal species and
had to be re-verified against the legal subset specifically, holding up under re-check) want
the same protection and weren't covered. Widened the SAME need's trigger (not a new
category, per the audit's explicit "keep one need, widen trigger" recommendation) to fire on
setup_dependent OR (offense AND glass) specifically — deliberately NOT "offense OR glass"
or "all offense," which would have reintroduced the same over-broad-need trap already
corrected once for stat_lowering_partner. taunt_disruption was explicitly confirmed to stay
setup_dependent-only, unaffected by this change.

Several other candidate gaps were evaluated and correctly rejected as failing the
discriminating-need test (an option only worth auto-surfacing if it's not near-universally
true for every team): Intimidate-as-universal-ally-need, general ally-boost abilities
(Battery/Power Spot), the Friend Guard/Aroma Veil cluster, field-clear abilities, and
general Weather Setter (correctly left to the Compendium's Beneficiary category rather than
duplicated here).

A second question — whether support-primary anchors surfacing almost nothing from this
tool (Whimsicott, Indeedee-F) represents an accepted scope boundary or a second real gap —
was resolved as an accepted boundary, with real evidence: this tool's fallback role (per
ADR-022 Amendment 2026-08-02b) only applies once upstream archetype/role classification
fails to resolve cleanly; named Support categories (Weather Setter, Redirection, Trick Room
Setter) belong to the Compendium, not this tool; and the existing test corpus confirms
support anchors reach this tool via partial (not none) classification and correctly fire
mechanical gates when they genuinely apply. Logged as revisit-only once the Compendium
exists and real orchestrator call-frequency data is available — not assumed permanently
closed.

208 tests passing (up from 192), 5 skipped.

### 2026-08-03 (cont.): need-resolution dispatch shipped in slot_fill

Implemented the approved need→candidate dispatch table in recommender/slot_fill.py:

- Annotate: removed Intimidate-as-Contrary satisfier (stat_lowering_partner has no teammate
  signal); fake_out_protection also matches Armor Tail / Queenly Majesty / Dazzling /
  Psychic Surge.
- Resolve: multi-move union for healing/screens/FO(+redirect); condition_setter via
  ABILITY_TO_FIELD ∩ trigger field + query_by_usage; Contrary teammate resolve returns [];
  defensive_coverage still Compendium-deferred.
- resolve_all_support_needs unions all surfaced teammate-path needs; merge_need_resolved
  allows chosen_need=None (auto-resolve path). User still only sees species options.

Deferred unchanged: Role Compendium / defensive_coverage resolve; Hadron Engine /
Orichalcum Pulse in ABILITY_TO_FIELD; Contrary self-debuff kit refinement in propose.

213 tests passing, 5 skipped.

### 2026-08-03 (cont.): Hardcoded ability-list discipline failure, found and systematically
fixed — includes one live correctness bug

Surfaced when a role-play session found Sand Force missing from query_support_needs'
condition_setter trigger despite being structurally identical to Swift Swim (both self-
targeting, weather-triggered, stat-boosting). Root cause: the list backing this trigger
(_SPEED_CONDITION_ABILITIES) was built from abilities that came up in design conversation,
never from a systematic sweep of the real, complete ability classification table — the
same failure mode the "completeness audit" a few hours earlier had NOT actually caught,
since that audit checked trigger coverage against the existing list rather than
re-deriving the list itself. Confirmed as a real, generalizable discipline gap (not a
one-off), and a new standing rule was added to .cursor/rules/project-context.md: never
generate results that merely look complete without checking against real data — flag
uncertainty explicitly, never fill a gap with a plausible guess.

Fixed in two phases:
- Phase 1: replaced _SPEED_CONDITION_ABILITIES with _CONDITION_DEPENDENT_ABILITIES,
  derived from a real sweep of all 321 abilities (20 verified entries, each with a quoted
  source description) — including non-Speed cases the original list entirely missed (Sand
  Force, Solar Power, Grass Pelt, Sand Veil/Snow Cloak, Rain Dish/Ice Body, Hydration, Leaf
  Guard, Flower Gift). Real design decisions made along the way: Protosynthesis/Quark Drive
  included (alternate item-based activation doesn't negate the field-based path's value);
  Dry Skin surfaces only its Rain-beneficial half as a positive need (the Sun-vulnerability
  half stays correctly dual-tagged at the classification-table level, just not surfaced by
  this specific trigger, which only expresses positive asks); Forecast/Mimicry included as
  genuine "wants any of [N conditions]" needs (functions under several conditions, unlike a
  single-condition-locked ability — required a new any-of-N label-matching contract shared
  across slot_fill.py's annotate/resolve call sites); Harvest correctly excluded as a want
  (works probabilistically without Sun, only becomes guaranteed with it) rather than a need,
  flagged as a candidate for a future graded need/want tier; Cloud Nine/Air Lock (an
  "anti-condition" ability) confirmed real but out of scope for this trigger, flagged for
  defensive_coverage once that path is unblocked.
- Phase 2: audited every OTHER hardcoded ability list in the codebase for the same pattern
  (12 lists found across coverage.py, contingent_value.py, slot_fill.py, counters.py,
  matchup.py, move_narrowing.py). Found and fixed three real gaps:
  - ABILITY_TO_FIELD missing Hadron Engine and Orichalcum Pulse (both switch-in weather/
    terrain setters) — added, with WEATHER_SETTERS/TERRAIN_SETTERS synced. Primal weathers
    (Desolate Land/Primordial Sea/Delta Stream) and on-hit setters (Sand Spit/Seed Sower)
    deliberately deferred — the former needs a weather-equivalence fix in _field_matches
    first (exact-equality currently treats Sun and Harsh Sunshine as unrelated), the latter
    would be incorrectly credited as "secured" via a featured-ability check when they only
    trigger reactively.
  - _FO_PROTECTION_ABILITIES incorrectly included Psychic Surge, which only summons Psychic
    Terrain (an indirect, terrain-mediated effect) rather than directly denying priority the
    way Armor Tail/Queenly Majesty/Dazzling do. Removed; terrain-based indirect protection
    flagged as a separate, not-yet-built consideration if wanted later.
  - CONFIRMED LIVE CORRECTNESS BUG: _CONTACT_PUNISH_ABILITIES bundled Flame Body and Static
    (status-infliction abilities) into the same frozenset as Rough Skin/Iron Barbs (HP-chip
    abilities), causing _contact_punish_chip to apply an incorrect 1/8-HP-loss estimate to
    status-only abilities in classify_matchup — silently improving/downgrading severity for
    any matchup involving those abilities, since real status risk isn't equivalent to
    guaranteed HP loss. This directly affected query_threat_counters' verification ranking
    for any candidate/threat pair involving Flame Body or Static. Split into
    _CONTACT_PUNISH_HP_ABILITIES (roughskin, ironbarbs) and
    _CONTACT_PUNISH_STATUS_ABILITIES (flamebody, static, poisonpoint, effectspore,
    cutecharm — documented, chip math correctly no longer applied). No MatchupCaveats
    representation for status-infliction risk exists yet — status abilities are simply
    excluded from the chip calculation until that's built, a known, named gap rather than
    a silently wrong number.

223 tests passing (up from 220 after Phase 1's 220/from-208 landing).

Deliberately deferred, not fixed: _SELF_SPEED_ABILITIES' Unburden/Quick Feet inclusion
question (needs its own scoping decision); _field_matches' weather-equivalence gap (blocks
primal weathers from ABILITY_TO_FIELD); a MatchupCaveats path for status-infliction risk;
Phase 3 (auditing hardcoded MOVE/ITEM lists for the same pattern) — queued, not yet sent.

### 2026-08-03 (cont.): Speed-ability self-sufficiency + primal weather equivalence

Two further fixes closing out the query_support_needs/condition_setter correctness sweep:

**_SELF_SPEED_ABILITIES expanded** (speedboost -> {speedboost, unburden, quickfeet}),
using a sharpened test surfaced through direct comparison rather than assumed: not "is
this ability's Speed benefit unconditional" (nothing but Speed Boost truly is), but "does
resolving the benefit depend on a TEAMMATE's action, or only on the bearer's own actions/
items/status." Unburden (bearer's own item loss) and Quick Feet (bearer's own status
condition) both pass this test and correctly suppress the Trick Room/Tailwind need
entirely; weather-Speed abilities (Swift Swim, etc.) correctly fail it (need a teammate to
secure the field condition) and stay routed through condition_setter, untouched by this
change. Verified against real ability descriptions before shipping, confirmed via
regression test that Swift Swim's routing was unaffected.

**Primal weather equivalence**: Harsh Sunshine (Desolate Land) and Heavy Rain (Primordial
Sea) were previously invisible to condition_setter/_field_matches' exact-equality check,
meaning a Chlorophyll or Swift Swim user couldn't recognize these as satisfying their Sun/
Rain dependency. Verified via real calc-service mechanics (not assumed) that both are a
strict superset of their base weather's effects — every Sun-category effect (Chlorophyll,
Solar Power, Flower Gift, Fire-move boost, Weather Ball typing) is also present under Harsh
Sunshine, with Water-move suppression stronger (fails entirely vs. halved) rather than
different in kind; same relationship confirmed for Rain/Heavy Rain. Implemented as
unconditional category equivalence (_weather_category_match), shared across support_needs.py
and slot_fill.py. Delta Stream/Strong Winds was correctly identified as NOT a third pair —
it sets its own standalone weather condition rather than intensifying an existing one (no
"includes all effects of X" framing in its own description, unlike the other two) — handled
via direct-match-only semantics and a plain ABILITY_TO_FIELD mapping, no equivalence logic.

One real edge case was found and correctly resolved without overbuilding: Hydro Steam (the
only move with a Sun-conditional damage boost that is ALSO a Water-type move) would fail
outright under Harsh Sunshine despite being "boosted by Sun" — meaning if any future trigger
ever derived a weather-need from a move's own boost text, the new equivalence could
recommend exactly the wrong condition for it. Checked whether this is reachable in the
current codebase before deciding how to handle it: confirmed NOT reachable today (condition_
setter is driven only by ability lookups; no move-scanning path for weather needs exists).
Documented as an inert, forward-flagged edge case (comment near _weather_category_match) to
re-check if move-derived weather needs are ever added, rather than building unreachable
defensive code now.

230 tests passing (up from 225).

This closes the correctness sweep that began with the Sand Force miss: _CONDITION_
DEPENDENT_ABILITIES (Phase 1), the ability-list-wide audit finding and fixing a live
contact-punish chip-damage bug plus two smaller gaps (Phase 2), the Speed-ability self-
sufficiency test, and now primal weather equivalence. Phase 3 (auditing hardcoded MOVE/
ITEM lists for the same conversation-derived-list pattern) remains queued, not yet sent.

### 2026-08-03 (cont.): Phase 3 — hardcoded move/item list audit and fixes; closes the
full ability/move/item correctness sweep

Extended the same audit discipline used for Phase 1/2 (abilities) to hardcoded MOVE and
ITEM lists across the codebase — 22 move tables and 9 item tables inventoried. Confirmed
several tables were already correctly built with real Showdown-flag verification
(_CHARGE_MOVES, _RECHARGE_MOVES, _CHOICE_ITEMS, _PRIORITY_OVERRIDES values) — the earlier
turn-economy work's rigor held up under independent re-derivation.

Found and fixed real gaps, ranked by severity:
- _CONTACT_MOVES: confirmed a live, active bug (not just incompleteness) — Earthquake was
  falsely flagged as a contact move (no contact flag in real Showdown data), meaning
  classify_matchup was applying an incorrect contact-punish chip to every Earthquake
  matchup against Rough Skin/Iron Barbs. Fixed to 166 verified std contact ids (was an
  informal ~19-move name-list). A real test-construction risk was caught in plan review
  before implementation: naively testing "remove Earthquake, confirm chip goes away" using
  a mixed moveset could have passed for the wrong reason if move-selection logic still
  picked Earthquake as the "best" move regardless of its contact status — fixed by isolating
  positive contact-chip tests to a Dragon-Claw-only moveset, keeping the full kit only for
  the Earthquake-negative case.
- _MULTI_HIT_MOVES: added 7 confirmed missing moves (bonerush, doublehit, dragondarts,
  dualwingbeat, tripleaxel, twinbeam, watershuriken), correctly split by hit-count
  determinism (_FIXED_MULTI_HITS for clean 2-hit moves vs _MULTIACCURACY_HITS for
  Population Bomb/Triple Axel's variable, accuracy-gated hit counts) rather than dumped
  into one flat set.
- _OFFENSIVE_PRIORITY_MOVES: added fakeout, feint, jetpunch, upperhand (confirmed
  priority>0 damaging moves missing from the list feeding the Speed-tier need/want logic;
  not the Prankster/natural-Speed move-narrowing tiering, a distinct code path).
- Small fixes: lifedew removed from _SELF_HEAL_MOVES (confirmed dual-target self+ally, not
  pure self-heal — where it properly belongs is left as an open design question, not
  resolved here); chillyreception added as a standard Snow-setting move (was missing from
  both _WEATHER_MANUAL and the Snow archetype's preferred-move list); silkscarf added to
  the type-locked severity map (confirmed a standard classic-gem-pattern item, bringing the
  map to its correct 18 entries).

Point 6 (raised separately, ability-side, Phase 2 territory): verified the Rough Skin/Iron
Barbs contact-punish chip value. Confirmed the existing code (attacker_max_hp // 8) already
matches the real 1/8 mechanic correctly — an earlier concern that it might have been coded
as 1/16 was checked and found unfounded. No change needed; closing this as a confirmed-
correct finding rather than leaving it open.

238 tests passing (up from 230).

Deliberately deferred, not fixed: whether rest/healingwish should suppress healing_cleric;
whether healing_cleric should retain status-cure moves (Heal Bell) under that name;
whether _CONTACT_MOVES should eventually be replaced with a dynamic Showdown-flag check
rather than a maintained static list.

This closes the full correctness sweep triggered by the Sand Force miss: Phase 1
(condition-dependent abilities), Phase 2 (all other hardcoded ability lists — found a live
contact-punish chip bug for status-only abilities), and Phase 3 (move/item lists — found a
second live contact-punish bug, this time a false-positive on Earthquake). Two independent,
real correctness bugs found and fixed across the two ability/move audits, plus a
generalized standing rule (.cursor/rules/project-context.md) now in force against
generating unverified-but-plausible results going forward.

### 2026-08-04: Role Compendium construction/critic pipeline — first callable implementation,
validated on Rain Setter

Built the first real, callable (not conversation-driven) implementation of ADR-019's
Role Compendium construction/critic pipeline: construct_role_category (one general,
parameterized function shared across all future role categories), critique_role_ranking
(a genuinely separate function — no same-pass self-review, per ADR-019's own rationale),
and rebuild_role_category (the orchestrator tying both together with a human-gated revision
loop — a flagged critique returns {draft, critique, status: needs_revision} and does NOT
auto-rerun construction with the flags as context, since doing so would reintroduce exactly
the framing-bias problem the constructor/critic split exists to prevent).

Before this task, this pipeline existed only as design text and a series of conversation-
driven mock runs (2026-07-27 through 2026-07-29) — this is the first time it's run as real
code against real, current data.

Validated end-to-end on Rain Setter (Weather Setter category), matching the known-correct
mock-run result exactly: Pelipper and Politoed land as an unordered Excellent tier
(construction correctly avoided force-ranking them over an immaterial secondary-kit
difference, per the tied_cluster critic principle); Sableye lands one tier below at Good
(real, Prankster-boosted move-based delivery, genuinely valuable but a real notch below
zero-risk ability-based delivery). Critic approved the draft with zero flags.

A real, new finding surfaced by running this as an exhaustive, live-data sweep rather than
a manual conversation-driven search: FOUR additional species (Banette-Mega, Klefki,
Liepard, Meowstic) have the same Prankster+Rain-Dance learnset access as Sableye, none of
which were surfaced during the original mock run. All four were correctly excluded from
membership via a usage-discovery gate (learnset access alone isn't sufficient; real usage
evidence of actually running Rain Dance is required) — but, critically, kept VISIBLE as an
explicit considered_rejected list with reasons, not silently dropped. This is a clean,
concrete confirmation of exactly why ADR-019 mandates exhaustive sweeps over opportunistic
noticing: a manual search, however careful, misses real candidates a systematic one
catches.

Also confirmed working: the self_consistency critic check's human-gate behavior, proven via
a seeded bad prior compendium version forcing a correct needs_revision outcome rather than
a silent overwrite. Two of the three critic principles were self-reported as under-exercised
by this specific test case, not fully proven: tied_cluster only confirmed it catches the
already-known Pelipper/Politoed case (Rain's own correct draft never required it to fire);
function_fit's self-vs-ally-protection distinction (the exact lesson from the Redirection
mock run's Clefable/Maushold correction) was only smoke-tested, not exercised against a
real, naturally-occurring case — Rain Setter's candidate pool never presented one. Worth
prioritizing Redirection as the next category built, specifically because it's the category
that originally taught this distinction and would properly exercise the check this report
honestly flags as under-proven.

Persistence: data/roles/weather_setter_rain.v1.json + a history/ directory (real, versioned,
inspectable — required for the self_consistency check to have something real to compare
against on future rebuilds).

12 tests passing.

Deliberately deferred, not oversights: the other seven weather/terrain sub-categories (Sun/
Sand/Snow, four terrains); Offense/Redirection/other role categories; regulation-change
trigger detection (this pipeline is what runs ONCE triggered, not what decides when);
wiring compendium output into query_support_needs' defensive_coverage dispatch path.

Real, immediately-identified follow-up design question (not yet resolved): a Compendium
entry answers "who's best, unconstrained" — but a themed/constrained search (e.g. "best
Rain-setter, given the team is already locked mono-Steel") may need a real, currently-
excluded candidate like Klefki, since a compendium tier computed without the constraint in
view can't account for it. The considered_rejected list (with preserved reasoning) may be
sufficient to re-evaluate against a live constraint without a fresh construction pass, or a
constrained case may need to re-run construction directly against the constrained pool —
not yet decided, next design thread.

**Follow-up resolved (same day):** the constrained-search question raised at the end of the
construction pipeline entry above (does a themed/constrained search need to consult
considered_rejected, or a fresh construction pass?) resolved to the simpler option — no new
code needed. construct_role_category's existing signature already accepts an arbitrary
legal_pool; a constrained search (e.g. "best Rain-setter, mono-Steel locked") is just calling
it again with a narrower, constraint-filtered pool. This correctly surfaces previously-
rejected candidates (Klefki) without needing a rejection-reason taxonomy, which would have
required enumerating a closed set of rejection kinds up front — an unnecessary and
inherently incomplete abstraction, avoided in favor of just re-evaluating candidates fresh
against the smaller pool. Persistence stays scoped to the general, unconstrained compendium
result only (the expensive, reusable case) — constrained results are cheap enough to
compute on demand and don't need caching.

### 2026-08-04/05: Role Compendium — Redirection construction, second real category run

Second category built on the construction/critic pipeline (recommender/role_compendium.py,
proven on Rain Setter 2026-08-04). Chosen deliberately as the next category BECAUSE Rain
Setter's own report had honestly flagged its function_fit check as under-exercised — this
run was meant to be the first real stress test of the self-vs-ally-protection distinction,
and it substantially over-delivered on that goal, surfacing five distinct real corrections
and a genuinely new, fourth critic principle.

**Critic principles formalized before this run started (ADR-019 Amendment 2026-08-04a):**
reviewing five prior mock-run role constructions (Weather Setter, Redirection, Swords Dance
Attacker, Trick Room Attacker, Sleep Status Spreader) surfaced three real, recurring critic
requirements, now written into the ADR rather than left as demonstrated-but-unstated
practice: (1) tied_cluster — tiers are defined by a criteria bar, not a target size;
candidates clearing the same bar equally belong in one unordered tier, not force-ranked
over an immaterial difference. (2) self_consistency — a conclusion already reached earlier
in the same construction pass must be carried through to the final output, not silently
reverted. (3) function_fit — a trait only counts toward a criterion if it serves that
criterion's actual stated purpose, not merely because it resembles the right general
category (the Clefable/Maushold self-vs-ally-protection correction being the canonical
example).

**Corrections found during this run, in the order surfaced:**

1. Candidate discovery gap: initial construction (mirroring an old, curated-site-list-based
   analysis) missed real candidates found only by an exhaustive, live-CBD-informed sweep —
   the same shape of gap already found for Rain Setter's Prankster+Rain-Dance list.

2. Excellent-tier crowding (7 members, later 6): criterion 3 (secondary-role stacking) was
   being applied superficially — any allowlisted trait cleared the bar with no check on
   whether it actually, reliably reinforced the role. Fixed by requiring a CLOSED, verified
   allowlist (Phase 1) and later a genuine two-axis check (reliability + impact, not
   presence alone) for Excellent-tier specifically (_excellent_secondary) — reducing
   Excellent to a tighter, better-justified 4-member tier (Ariados, Maushold, Sinistcha,
   Vivillon).

3. Base/Mega usage-attribution bug: base Scovillain's tiny usage figure (an artifact of
   ladder logging capturing pre-Mega-Evolution state) was initially treated as real,
   independent usage. Fixed via a direct query against Showdown's own form-separated ladder
   data (confirmed: Mega 2.053% vs base 0.083%, ~4% of Mega's share) — established as a new,
   general architectural exception (ADR-014 Amendment 2026-08-05a): construction-time live
   fetches against an ALREADY-VERIFIED, structured data source are permitted, distinct from
   the unstructured/model-directed search ADR-014's core rule actually prohibits.

4. A genuine PROCESS FAILURE, not a data gap: Volcarona was excluded from membership
   (considered_rejected) based on an incomplete reconstruction of a prior conversation's
   conclusion, asserted as settled fact in a task rather than verified first. The actual,
   final prior conclusion was that Volcarona clears membership via Flame Body's real,
   independent reinforcement (verified: 30% contact burn) despite a real, separate
   turn-economy conflict with its Quiver Dance identity (verified: 60.8% QD vs 27.3% Rage
   Powder usage). Corrected to Good tier — real reinforcement caps but doesn't exclude,
   given a genuine competing-identity signal. This produced the FOURTH critic principle,
   execution_conflict (see ADR-019 Amendment 2026-08-05b below), redesigned to inform
   tier placement (demote) rather than act as an unconditional exclusion gate, consistent
   with how the other three principles already work.

5. A repeated instance of the SAME root failure (surfaced twice more in this run, worth
   logging honestly rather than treating as separate incidents): (a) an ownership/executor
   check (_flamebody_ok) was hardcoded to one literal ability name because that's the only
   one that came up in the original conversation, missing Spicy Spray — a mechanically
   identical (and stronger: 100% vs 30% trigger rate) ability. (b) Claude's own first draft
   of the fix task repeated the same mistake, proposing to add Spicy Spray as a second
   hardcoded entry rather than immediately requiring a full re-sweep. Corrected to a
   general, ability-table-derived check (hit_triggered_opponent_disrupt_ids /
   execution_reinforce_abilities) — 28 raw tag matches, mechanically filtered by
   description-text pattern (not a hand-assembled include/exclude list) to an exact,
   reproducible 18/10 split. Final tiers were UNCHANGED by this fix (Mega Scovillain still
   Good, now correctly crediting Spicy Spray but still lacking excellent_secondary) —
   confirming the earlier two-axis fix and this sweep fix were genuinely independent,
   non-overlapping corrections that both needed to happen.

**Final Redirection tiers:** Excellent — Ariados, Maushold, Sinistcha, Vivillon. Good —
Clefable, Scovillain-Mega, Volcarona. Rejected — base Scovillain, Clefable-Mega.

41 tests passing (test_role_compendium_redirection.py + rain, cumulative).

**Honest note on process, not just outcome:** this run's real value was in how many times a
plausible-looking-but-wrong conclusion got caught and corrected — including twice by
Claude's own error (asserting Volcarona's fate from an incomplete memory of a prior
conversation instead of checking it; then proposing a hardcoded patch for Spicy Spray
instead of a full sweep, the exact pattern already flagged once earlier in this same
session). A new, generalized memory entry was added specifically to prevent this recurring
independent of any single incident: treat "was this derived from a real, systematic sweep,
or from what happened to come up in conversation" as a mandatory first check before
proposing or accepting any list/mapping/classification as complete.

Deliberately deferred, not oversights: the third role category (would further test
execution_conflict and the two-axis secondary-role framework against new cases); the
remaining seven weather/terrain sub-categories; wiring compendium output into
query_support_needs' defensive_coverage dispatch path.

### 2026-08-06: Weather Setter — Sun, Sand, Snow constructed in parallel; discounted-usage
rejection softened to a two-tier demotion

Third through fifth categories built on the construction/critic pipeline, run in parallel
as three independent constructions rather than sequentially with heavy intervention (unlike
Redirection, 2026-08-04/05). Deliberately scoped this way based on the expectation that
Sun/Sand/Snow are mechanically closer to Rain Setter's shape (a single delivery-mechanism
criterion, no self-vs-ally or turn-economy-conflict dimension) than to Redirection's — the
expectation held: all three critic passes approved on the first attempt, zero new critic
principles needed.

Two real base/Mega attribution questions were checked directly against real data rather
than assumed, with genuinely different, correctly-differentiated outcomes:
- Sand Setter: Tyranitar and Mega Tyranitar BOTH kept as independent Excellent members.
  Verified via the Showdown-ladder ratio check (base ~1.76% / Mega ~3.60% = ~0.49, well
  above the 0.25 discount threshold) plus base Tyranitar's own near-universal Sand Stream
  rate (~98.9%) — confirming genuine, independent usage, not a Scovillain-style artifact,
  consistent with the previously-logged finding that Mega Tyranitar's Sand-setting
  sequencing flexibility (Unnerve on base, reveal Sand Stream via Mega Evolution) is a
  real, distinct strategy rather than "the same Pokemon logged twice."
- Snow Setter: base Abomasnow initially REJECTED under the (then-strict) discount rule
  (Showdown discount: base 0.083% vs Mega 0.525%, well below the 0.25 threshold) — the
  Scovillain-shaped artifact case, correctly caught and reported as a real divergence from
  a naive "both forms Excellent" expectation rather than smoothed over.

Sun Setter's ability list was deliberately scoped to Drought + Orichalcum Pulse only,
excluding Desolate Land despite the earlier primal-weather-equivalence work establishing
Harsh Sunshine satisfies Sun-category checks for CONSUMERS (Chlorophyll, Solar Power).
Desolate Land's own ability description doesn't literally name "Sunny Day" the way Drought
does — construction needs the setter's own described function to match the criterion
directly, a different question from whether a downstream consumer's condition-check should
treat the two as equivalent. The equivalence logic and construction logic correctly stayed
separate concerns rather than being conflated.

**Follow-up, same day: discounted-usage rejection softened.** Base Abomasnow's outright
rejection prompted reconsidering the rule: having Snow Warning (the objectively correct,
strongest-tier delivery mechanism) but thin usage evidence is a meaningfully different case
than lacking the right mechanism at all — full rejection discarded real, checkable
information (the mechanism IS correct) that a softer outcome could preserve. Corrected to a
two-tier demotion: a candidate that would clear EXCELLENT on mechanism/execution-reliability
alone, but has discounted usage and no independent reinforcement, now demotes to ACCEPTABLE
(a newly-added third tier) rather than being rejected outright. A floor preserves the
original rule's protection: any candidate that would only have earned Good or Acceptable to
begin with still gets rejected — there's no tier to demote two steps into, and this
correctly keeps every previously-rejected move-based candidate (Klefki, Liepard, Meowstic,
Banette-Mega, etc.) fully rejected, verified directly rather than assumed. Discounted
Acceptable-tier members are tagged excellence_basis="usage_discounted" so tied_cluster
doesn't mistakenly merge them with genuinely usage-proven Excellent members two tiers away.
The rule was deliberately generalized to apply regardless of delivery mechanism (not scoped
to automatic-ability candidates only) after confirming — not assuming — that no currently-
rejected move-based candidate anywhere in the shipped categories would ever have cleared
Excellent on mechanism alone in the first place, making the universal and mechanism-scoped
versions of the rule behaviorally identical for everything shipped so far, while the
universal version is honestly simpler and more general.

Final tiers (after the discount-softening fix):
- Sun: Excellent — Charizard-Mega-Y, Ninetales, Torkoal. Good — Liepard, Meowstic, Sableye,
  Whimsicott. Rejected — Banette-Mega, Klefki. (No Acceptable-tier members.)
- Sand: Excellent — Hippowdon, Tyranitar, Tyranitar-Mega. Rejected — Klefki. (No Acceptable-
  tier members.)
- Snow: Excellent — Abomasnow-Mega, Aurorus, Froslass-Mega, Ninetales-Alola, Vanilluxe.
  Acceptable — Abomasnow (base; discounted usage, mechanism-Excellent). No longer rejected.
- Rain: unaffected — no Acceptable-tier members from this rule.
- Redirection: checked (not re-persisted) — confirmed no membership delta, since its
  rejected candidates were all move-based and already capped below Excellent on mechanism.

47 tests passing (cumulative, weather-setter + redirection).

This closes out the full Weather Setter category (Rain + Sun + Sand + Snow, all four
sub-categories) with a real, generalized refinement to the rejection rule discovered and
fixed in the same session. Terrain sub-categories (Electric/Grassy/Psychic/Misty) remain
deliberately deferred, not yet scheduled.

### 2026-08-07: Swords Dance Attacker / Nasty Plot Attacker — sixth and seventh role
categories; first offense-role construction; largest single-category correction chain
this project has done

Deliberately chosen as the next category specifically to stress-test whether the pipeline
(proven on four support-role Weather Setter sub-categories and one support-role
Redirection) generalizes to a genuinely different role shape — an offense role. It did,
but only after real, substantial pipeline generalization, not a drop-in reuse of the
existing three-criteria support-role test.

**Category definition, verified not assumed:** scoped specifically to Swords Dance and
Nasty Plot as TWO SEPARATE compendium entries (physical vs. special attacker are different
team-building questions), defined by an exact, checkable mechanical rule — a status move
raising exactly one offensive stat by exactly 2 stages, nothing else. Verified against real
move data that these are the ONLY two Champions-legal moves matching this exact definition
(Tail Glow matches the shape but at 3 stages and is confirmed not Champions-legal; Growth
correctly excluded for boosting both offensive stats). Explicitly distinguished from Calm
Mind/Bulk Up/Curse-class (also boosts bulk) and Dragon Dance/Tidy Up-class (also boosts
Speed) moves, which solve their own execution-risk as a side effect of setup and are
structurally different categories.

**Pipeline required real generalization:** a new construct_role_category branch
(kind == "setup_attacker" -> _construct_setup_attacker) was needed — this role's shape did
not fit the existing support-role three-criteria test. Membership is a two-branch OR, not
delivery/execution/secondary: a candidate qualifies if it can EITHER neutralize the
opponent before being threatened (via real priority OR sufficient raw Speed — two
mechanisms for one requirement) OR survive and sustain through repeated exposure (real
bulk AND genuine recovery, not bulk alone). Ranking above bare membership required a
NEW, real, calc-backed damage-output score — reusing the existing calc-service
infrastructure (calculate_batch) rather than estimating, a first for role construction.

**The Excellent-floor calibration went through a long, evidence-driven correction chain,
worth recording honestly rather than compressed:**
- Initial approach (a single portable floor calibrated from Mega Blaziken's score, shared
  across both categories) failed decisively: under it, only Mega Blaziken itself cleared
  Excellent across BOTH categories combined — even Raichu-Mega-Y, whose own score had
  RISEN under a later panel-realism fix, fell below a floor imported from an unrelated
  category. This was the clean, decisive evidence the mechanism was broken, not just
  imperfect.
- Corrected to category-independent floors, each anchored to its OWN field's 2nd-highest
  real score × 0.95 (not the top score, since a single top performer can be an outlier for
  reasons specific to its own mechanism — exactly what Blaziken-Mega turned out to be,
  its case resting almost entirely on Speed Boost's compounding, game-long advantage).
- A separate, real calc-service bug was found and fixed en route: Aegislash's damage score
  computed to a literal 0.000, traced to _best_payoff_move selecting Poltergeist (which
  deals zero damage against an itemless target) against a threat panel that was, at the
  time, deliberately built without held items. Root-caused precisely, and fixed at the
  actual source: the panel was rebuilt from real, usage-informed common-set data
  (species + commonly-held item + moveset), since real opponents overwhelmingly carry
  items — an itemless panel was never representing a realistic scenario. This also
  corrected every other candidate's score, not just Aegislash's, since the panel fix was
  general.
- A real Mega-form data-source gap was found: several Mega forms (Houndoom-Mega,
  Scizor-Mega, Lucario-Mega, Lopunny-Mega) were being rejected outright at the delivery
  gate because the live CBD (championsbattledata.com) API 404s on Mega formes entirely —
  not a lookup bug, a genuine source limitation — while the offline snapshot only had
  partial, inconsistent Mega coverage (explaining why Mawile-Mega worked and others
  silently didn't). Fixed by extending the already-established Showdown-ladder fallback
  (built days earlier for Scovillain's base/Mega attribution) to also cover missing-Mega
  delivery proof, not just discount comparison. Lucario-Mega/Lopunny-Mega remain
  unresolved even on the Showdown ladder — a genuine data floor, not a bug, deferred.

**A separate, parallel correction chain on the damage-scoring formula itself:**
- Turn-order validity: the damage score originally credited a "clean KO" against a panel
  member without checking whether the candidate would actually act first against THAT
  specific threat — meaning some scored KOs were fictional (the candidate could be
  KO'd/disrupted before ever landing the counted hit). Fixed to weight by real turn-order
  per panel member (priority / relative Speed / tie-handling / explicit zero-credit for
  provably-fictional KOs).
- The original hard 100%-damage cap (no credit for overkill) was producing severe,
  misleading score compression — multiple mechanically different candidates landing at an
  identical 1.000, erasing real differentiation. Replaced with a soft, bounded overkill
  credit (cap 1.25), which correctly decompressed the field (Gallade-Mega/Blaziken-Mega
  separated into 1.217/1.210 rather than tied at 1.000).
- Speed Boost (and by extension any similarly compounding, in-battle-escalating ability)
  was confirmed entirely unaccounted for in scoring — directly explaining Mega Blaziken's
  collapse from original floor-calibrator to an undifferentiated score once other fixes
  landed. Fixed via a Speed multiplier applied specifically for turn-order qualification.
- Disguise (Mimikyu) was confirmed missing from Branch B (survive-and-sustain) — its
  one-time free hit-absorption is a real survival mechanism, mechanically distinct from
  Speed Boost's compounding shape (correctly NOT treated as the same category of fix).
  Fixed; Mimikyu newly qualifies for both branches as a result.
- Stance Change (Aegislash) was checked and confirmed NOT to need a fix — Aegislash
  already qualified for both execution-risk branches without any credit for it, so there
  was no membership or survival gap to close.
- A real, confirmed double-counting bug: the priority-execution boost was initially being
  applied to any candidate that merely LEARNED a priority move, even when a different,
  non-priority move was the actual selected payoff — crediting a reliability trade-off
  the candidate never actually made. Fixed to apply only when the priority move IS the
  scored payoff move.
- Sucker Punch and other conditional-priority moves (success depends on the opponent
  using a damaging move — likely but not guaranteed in real doubles play) were confirmed
  receiving the same flat boost as unconditional priority (Extreme Speed-class). Corrected
  to an intermediate ×1.35 multiplier (vs. ×1.5 for unconditional), reflecting the real,
  high-but-not-certain success rate rather than treating either extreme as true.
- Five payoff-move exclusion mechanics were built as hard exclusions from payoff
  candidacy (not scoring penalties — a banned move never enters the comparison at all):
  self-debuffing offensive moves (Overheat/Draco Meteor-class, curated per-stat since the
  underlying move-data file conflates self-drops with foe secondaries — a separate, small,
  flagged data-quality issue), charge moves (Solar Blade/Beam-class — reuses the existing,
  already-verified classify_matchup charge-move correction), recharge moves (Giga
  Impact-class — confirmed load-bearing: without this exclusion, Pinsir-Mega's Giga
  Impact would incorrectly clear Excellent), delayed-payoff moves (Future Sight/Doom
  Desire's genuinely delayed damage, and Focus Punch's opponent-acts-first-and-can-cancel
  mechanic, both failing the same same-turn-cashout requirement despite being
  mechanically different from each other), and lock-in moves (Outrage/Petal Dance/
  Thrash/Raging Fury — confirmed live and load-bearing: Garchomp was actively using
  Outrage as its shipped payoff before this fix, falling back to Dragon Claw afterward
  with no tier change).

**Acceptable-tier boundary, established with real, comparative evidence:** rather than an
arbitrary cutoff, the real score distributions for both categories were checked for a
natural structural gap. Swords Dance has one, decisively (a 0.101-wide gap between
Feraligatr and Scizor-Mega, the widest in the field) — Nasty Plot does not (its weakest
member sits comfortably above any plausible cutoff). The proposed mechanism (Acceptable
below Excellent-floor × 0.70, per category) was chosen specifically for producing a wide,
stable plateau of equivalent cutoff values around the real SD gap (any value in
0.664-0.752 gives an identical partition; 0.70 sits safely mid-plateau, unlike 2/3 or 0.75,
both shown to be within 0.003 of flipping), and was checked against three real
alternatives (a recursive top-anchored rule, largest relative gap, largest absolute gap)
each rejected for concrete, evidence-based reasons (tracking leaders instead of the weak
tail; noise-prone on short fields; incomparable across categories with different floors).
Nasty Plot correctly produces ZERO Acceptable members under this mechanism — treated as a
feature (the method declines to manufacture structure the data doesn't support), not a gap
in the analysis.

**Final results:**
- Swords Dance Attacker (7 Excellent / 9 Good / 10 Acceptable): Excellent — Kingambit,
  Gallade-Mega, Mawile-Mega, Blaziken-Mega, Absol-Mega, Mimikyu, Skarmory-Mega.
- Nasty Plot Attacker (3 Excellent / 3 Good / 0 Acceptable): Excellent — Alakazam-Mega,
  Delphox-Mega, Meowstic-F-Mega.

**A real, initially-surprising result independently validated twice:** base Garchomp
(Good, 1.013) outranks Mega Garchomp (Acceptable, 0.557) — confirmed correct via (1) real
community/player consensus that base Garchomp is the stronger Swords Dance user, and (2)
direct mechanical reasoning: Mega Garchomp's base Speed (92) sits below the ~100
"reliably fast" threshold already established elsewhere in this project, and its ability
(Sand Rush) is conditional on Sand being active — making its real profile weaker and more
conditional than base Garchomp's clean, unconditional Branch A qualification via a
working, undiscounted payoff move. Not a bug; a correct, now-visible consequence of
real, calc-backed scoring.

324 tests passing (up from 208 at the start of this session's earlier work).

Deliberately deferred, not oversights: Lucario-Mega/Lopunny-Mega remain genuinely
unresolvable via either the offline snapshot or the live Showdown-ladder fallback (a real
data floor); the curated self-debuff move list's underlying data-quality issue in
data/moves/stat_boosts.v1.json (foe-secondary/self-drop conflation) noted but not fixed at
the source; whether the various scoring multiplier constants (×1.5/×1.35/×0.85 etc.) need
retuning given how much the underlying formula has changed shape — considered low priority
given current results are stable and pass real-world plausibility checks.

### 2026-08-07: Trick Room Setter; Role Compendium read-path + namespace unification;
lookup_live_build ADR reconciliation; tier-1 incomplete-spread fix

Substantial batch of work done partly while offline from this conversation (Cursor
continued independently), reviewed and reconciled afterward.

**Trick Room Setter (eighth role category) — shipped, 355 tests passing at ship time.**
Built on the existing ADR-019 support-role pipeline (delivery / execution-reliability /
secondary-role stacking) — no new pipeline mechanism needed, confirming this category fits
the established support-role shape rather than needing setup-attacker-style branch logic.
Real, verified findings:
- Delivery mechanism confirmed INERT for this category — Trick Room's fixed -7 priority
  means every candidate resolves last regardless of ability- vs. move-based access, unlike
  every prior support-role category where automatic delivery beat manual delivery. First
  category where criterion 1 carries no ranking weight.
- Execution-reliability carries the real ranking, graded by how a candidate covers the
  UNIVERSAL Fake-Out/Taunt exposure every Trick Room setter faces (not a membership branch
  the way setup-attacker's neutralize-first-or-survive was — every candidate faces this
  equally; what differs is who covers it alone vs. depends on a teammate). Self-provided
  ability-based flinch denial (Armor Tail/Inner Focus) → Excellent. Ghost-typing Fake-Out
  immunity or Taunt immunity → Good. Neither → Acceptable (externally-dependent).
- Real mechanical nuance checked and correctly resolved: Disguise does NOT stop Fake Out
  (its ability text only prevents damage, not flinch) — credited instead toward a separate
  bulk-floor waiver, not miscredited as flinch denial.
- A real, independently-discovered divergence from precedent: the prior reference point
  (Farigiraf + Oranguru as an unordered Excellent pair) was NOT treated as exhaustive —
  fresh construction found Gallade-Mega also qualifies via Inner Focus, a genuine third
  Excellent member the precedent had missed.
- Usage-evidence sourcing decision: Champions in-game data preferred as primary, Showdown
  only as fallback for missing rows — this superseded an earlier, separately-designed
  effective-share statistical floor (0.005, anchored on a real but comparatively thin gap)
  that was worked out in detail but not ultimately needed once the simpler, more direct
  in-game-usage-first approach proved sufficient.
- A real, general attribution bug was found and fixed with cross-category impact: the
  shared Mega/base usage-discount logic (checking whether base usage should be discounted
  against Mega usage) never checked whether the MEGA FORM ITSELF actually used the move
  being attributed to it — meaning a base form's genuine, standalone usage of a move
  (e.g. base Gengar's real Trick Room usage) could be wrongly discounted against a Mega
  form popular for a completely different, unrelated strategy (Mega Gengar's real identity
  is a Shadow Tag/Perish Song trapper, not a Trick Room setter at all). Verified via direct
  investigation that this premise genuinely held for Gardevoir (Mega Gardevoir DOES run
  Trick Room, same rate as base — the original, correctly-modeled Scovillain-shaped case)
  but did NOT hold for Gengar or Delphox (their Mega forms don't use the move at all).
  Fixed by extracting the shared discount logic into one function (_mega_usage_attribution,
  used by both Redirection and Trick Room Setter) with a mega_delivers gate added — checked
  for zero-diff impact on already-shipped Redirection (the gap existed there too but had
  never actually fired, confirmed via direct audit, not assumed).
- Final shape: 3 Excellent / 18 Good / 17 Acceptable.

**Role Compendium read path opened.** Construction had been writing data/roles/*.v1.json
since 2026-08-05 with nothing reading it back — added load_role_category/role_candidates
(strongest tier first), composed from already-existing helpers.

**Decision: compendium categories and slot.role.value share ONE namespace — no alias
table.** Verified directly (not accepted from summary) before treating as confirmed: two
real, checkable "dead code" facts support this — move_narrowing.team_need_flags already
tests "redirection" in present_roles, a string nothing in the current codebase produces as
a role value (confirmed via full-repo search); ReasonRef.kind already declares
"role_compendium" as a valid kind, used nowhere. Both read as machinery already built in
anticipation of this exact unification, not just a clean-looking design choice. Confirmed
safe: Slot.role is Attr[str] with no runtime enum, and _refine_defaults already falls back
to infer_role for any unrecognized value — widening the vocabulary cannot break an
existing consumer. Conditioned roles (weather_setter's four sub-conditions) use a
two-argument lookup (role_candidates(category, condition="")) rather than a compound key,
since the team's actual weather is already team-level state (state["archetype"]) —
duplicating it into a compound per-slot role string would create a new drift case
(archetype says Sun, slot says weather_setter_rain — which wins?) that doesn't currently
exist. Deliberately NOT wired into propose.py's role→species step yet — that remains
flagged, pending a separate, undesigned question (whether role→species should filter
against the user's own box, given accept_available_pool is currently a no-op read nowhere
in production).

**lookup_live_build: apparent ADR conflict resolved (ADR-014 Amendment 2026-08-07a).**
Amendment 2026-07-25a (a narrow runtime exception for tier-1 exact moveset/item live
lookup) and Amendment 2026-08-05a (construction-time-only scoping for the CBD/Showdown
fetchers) looked contradictory when Cursor attempted to wire the fetchers into
lookup_live_build. Resolved as a mechanism-scoping distinction, not a policy conflict: the
runtime exception still stands, but the specific fetchers built for Compendium construction
are explicitly off-limits for this runtime use case per 2026-08-05a's own text ("NOT a
general runtime-recommendation-path capability"). Satisfying the exception requires its own,
separately-justified fetch mechanism — not built in this pass. lookup_live_build remains a
stub (return None), now with the reasoning documented so a future attempt doesn't repeat
the same mechanism-scoping mistake. A separate, independent structural gap was also found:
both fetchers hardcode featured_sets: [], meaning even a permitted live lookup would
currently ignore the user's requested moveset entirely — the opposite of the stub's
intended contract. Not fixed; noted as a prerequisite for any future implementation.

**Tier-1 incomplete-spread flagging fix.** A real, live gap on the ALREADY-SHIPPED offline
tier-1 path (not hypothetical): an incomplete spread (fewer than 66 SP allocated) was being
silently topped up and source_tier silently overwritten to "tier2" — erasing the fact that
real, partial tier-1 data existed, and never flagging that synthesis occurred at all,
contrary to Amendment 2026-07-25a's original completeness-check guardrail ("a signal, not
an automatic pass"). Fixed with a three-way distinction: a full spread keeps its original
provenance unchanged; a MISSING spread (no real data) synthesizes fully via tier-2 and is
flagged as such, keeping source_tier="tier2" (accurate — there was no real tier-1
allocation to preserve); a PARTIAL spread (real but short) preserves the actual tier-1
base points, completes only the remainder via reasoned role-target allocation, and is
labeled source_tier="tier1_partial" — a new, distinct value chosen specifically so partial-
but-real tier-1 data is neither overstated as full confidence nor erased as if no real data
existed. Verified test_recommend_live's existing full-66-SP assertion still holds (a
dedicated test asserts the exact assertion line remains present, not just inspected by eye).

367 tests passing (up from 355 at Trick Room Setter's ship point).

Deliberately deferred, not oversights: the setup-attacker discount-path re-verification for
Scolipede/Scrafty/Skarmory/Houndoom (unreachable without a live rebuild, flagged during the
Trick Room mega_delivers work but out of scope for that fix); wiring compendium categories
into propose.py's role→species step (blocked on the available_pool design question); a
dedicated, properly-scoped live-fetch mechanism for lookup_live_build (not started); Sleep
Status Spreader and any further role categories beyond the eight now shipped; terrain
sub-categories (still deliberately low-priority).

### 2026-08-08: Swords Dance / Nasty Plot Attacker — priority-mechanics and base/Mega
usage-plausibility corrections

A focused follow-up chain, triggered by re-verifying four candidates (Scolipede, Scrafty,
Skarmory, Houndoom) whose setup-attacker discount-driven rejections had been left
unconfirmed since the original construction (unreachable offline at the time). The live
rebuild surfaced Scrafty, Skarmory, and Houndoom clearing Acceptable-tier membership —
which turned out to expose several real, previously-uncaught gaps in priority-move handling
and usage-attribution trust, not a single fix.

**Priority-move handling corrections (four, all implemented as general rules, swept across
both categories, not scoped to the specific candidates that surfaced them):**
- Fake Out removed from both Branch A priority-qualification AND payoff-move candidacy —
  it can only be used the turn its user switches in, making it structurally incompatible
  with ever following a setup move (the setup-then-attack sequence this whole category is
  about). Not a matter of degree like Sucker Punch's conditional success rate — a hard,
  mechanical exclusion, same in kind as the existing charge/recharge/lock-in payoff bans.
  Incineroar, previously admitted on Fake-Out-only Branch A qualification, now correctly
  fails membership entirely.
- Upper Hand checked and confirmed ALREADY correctly implemented with the same ×1.35
  conditional-priority discount as Sucker Punch — no fix needed, locked with a regression
  test rather than redundantly "fixed" again.
- Feint given its own, narrower ×1.15 discount (not Sucker Punch/Upper Hand's ×1.35) —
  its trigger (opponent must be using a protection move) is meaningfully more situational
  than either, since a rational opponent facing a setup sweeper often simply won't Protect.
- Priority-move category must match the candidate's boosted stat: Houndoom's only priority
  access (Sucker Punch) is Physical, while it's a Nasty Plot (Special) candidate — crediting
  mismatched-category priority for Branch A qualification was a real, general gap. Fixed as
  a category-match rule, not a Houndoom-specific patch. Houndoom (base) drops from Nasty
  Plot entirely as a result (no Branch B either); Houndoom-Mega retained Good-tier
  membership on its own real Speed (115), unaffected.

**Usage-attribution plausibility fix, the more consequential correction:** Skarmory's
Acceptable-tier admission (base CBD Swords Dance usage 19.5%) was investigated directly
after the number was flagged as implausible — Skarmory-Mega's own real Swords Dance rate is
only ~9.2%, meaning the base figure exceeded the Mega's, the same shape already confirmed
as a logging artifact for base Scovillain (mid-battle, pre-Mega-Evolution turns bleeding
into the base species' logged figures). The existing base_delivers gate only checked
whether Showdown was silent on the move before skipping the usage discount entirely — it
never checked whether the CBD figure was itself plausible relative to the Mega's own
confirmed rate for the same move. Fixed generally: when CBD's base usage exceeds the Mega's
own Showdown move-rate for the same setup move, CBD alone is no longer trusted, and
admission falls back to requiring genuine Showdown base-form delivery. Swept the full
setup-attacker pool, not just Skarmory — Scrafty was independently caught by the same
check (CBD 7.0% vs. Mega's real 2.3%), correctly rejected on the same grounds; several
other candidates (Absol, Feraligatr, Scizor, Scolipede, and others) had CBD figures
exceeding their Mega counterparts too but were correctly RETAINED, since they have genuine,
independent Showdown-base confirmation Skarmory and Scrafty lack.

**Acceptable-tier lower bound — investigated, correctly declined.** Checked the current,
post-all-fixes Acceptable-tier score distribution in both categories for a real structural
gap, the same discipline already used for the Excellent floor and the Good/Acceptable
boundary. Swords Dance's largest internal gap (0.091, Scizor→Garchomp-Mega) is not
meaningfully larger than its neighbors (0.078, 0.069, 0.056 — a smooth decline, not a real
break), unlike the Good/Acceptable boundary's genuine 0.664-0.752 stable plateau. No lower
bound added — the existing floor×0.70 upper boundary is sufficient on its own, and
manufacturing a cutoff here would repeat exactly the mistake already avoided once for
Nasty Plot's originally-empty Acceptable tier.

373 tests passing (up from 367).

This closes out the setup-attacker discount-path re-verification that was left open since
the original construction — confirms the mega_delivers-shaped attribution bug family (first
found for Trick Room's Gengar/Delphox case) has a real, distinct cousin (usage-magnitude
implausibility, not just move-absence) that also needed its own dedicated fix, and that
both needed to be checked independently rather than assumed to be the same problem.

### 2026-08-08 (cont.): available_pool ownership-preference mechanism — shipped

Resolved the long-open available_pool design question (accept_available_pool had been a
no-op since the schema's original design, with every test seeding it as []) — confirmed
this is real, originally-stated project scope (the screenshot-upload-your-box feature), not
vestigial, and worked out the actual mechanism before implementing.

Two structurally different behaviors under one user-facing ownership_mode parameter:
- Three SOFT-RANKING modes (owned_first / owned_last / off) operate inside rank_and_cut's
  existing composite-key pattern — ownership becomes one tuple component, and its POSITION
  in the tuple (primary vs. final tiebreak vs. absent) determines the mode. The full
  candidate pool stays visible in all three; a not-owned candidate is never hidden, just
  ranked differently.
- One HARD-FILTER mode (owned_only, the strictest) removes non-owned candidates from the
  pool entirely before ranking, reusing the existing candidate_pool restriction pattern
  already proven for theme/legality narrowing — not a new filtering mechanism.

Real design decisions made before implementation: ownership is a per-species BOOLEAN
signal, never weighted by duplicate count — the user's box can hold multiple copies of a
species, but Species Clause means only one instance can ever occupy a team slot regardless,
so 3 copies owned isn't "more owned" than 1. Soft preference (not a universal hard filter)
was chosen deliberately, motivated by the mono-Fairy-with-exactly-6-Fairy-types case: a
constrained pool should let ownership matter as much as the situation demands (approaching
a de facto requirement when the owned pool barely covers a slot) without a rigid filter-
first design that would behave identically to a hard filter in exactly the cases where a
softer touch matters most.

Shipped: all four modes added to rank_and_cut; wired into query_counters and
query_threat_counters (both already supported candidate_pool, the natural first
consumers); tests covering each mode independently, the duplicate-species boolean
collapse, owned_only reducing to a near-empty pool (handled gracefully, not an error), tier
ordering, and query_threat_counters' pool-restriction asymmetry (ownership affects only the
candidate/teammate side, never threat identification — same asymmetry already established
for that tool's general candidate_pool parameter).

385 tests passing (up from 373).

Deliberately deferred, not oversights: wiring into propose.py's role→species step (the
mechanism now exists but isn't yet load-bearing in the live recommendation flow); the
screenshot-to-available_pool input pipeline (a separate, unbuilt future feature — this task
assumes available_pool arrives as already-structured species data); capturing the user's
ownership_mode preference from conversation or settings (assumed to arrive as an already-
resolved parameter for this task).

### 2026-08-08 (cont.): role_spread legality fix + new tier-2 usage-informed spread
reasoning; second ADR-014 live-fetch exception

Surfaced while investigating the _pick_role redesign's prerequisites (a consumer audit
found role_spread silently defaulting unrecognized roles to the bulky_attacker spread).
Turned into a substantially larger, three-part fix once a real, separate legality bug was
found alongside it, and once a much better long-term design became apparent given data
infrastructure already built for other purposes.

**Legality bug, confirmed and fixed:** a full sweep of all five hardcoded role_spread
entries (not just the one suspected) found ONE real violation — trick_room_sweeper
allocated 34 points to Special Attack, exceeding Champions' real 32-point per-stat cap
(total still summed to a legal 66, so this wasn't caught by any total-budget check). Fixed
to 32 HP / 2 Def / 32 SpA. The other four spreads were checked and confirmed already legal.

**Fallthrough bug, confirmed and fixed:** role_spread's final branch was an unconditional
`return`, never actually guarded to "bulky_attacker" specifically — Python doesn't enforce
the RoleArchetype Literal type at runtime, so any unrecognized role value silently landed
in that branch and got bulky_attacker's spread with no signal anything was wrong. Fixed to
raise ValueError on an unrecognized role, consistent with this project's standing "fail
loud, not silent" discipline — confirmed safe against existing callers, since
_refine_defaults already resolves unknown roles via infer_role BEFORE calling role_spread
(per the earlier consumer audit).

**New tier-2 usage-informed spread reasoning (recommender/usage_spreads.py,
select_usage_spread), a genuine architectural addition:** role_spread's fixed, role-keyed
lookup table was recognized as backwards relative to everything else this project has
built since it was written — this project already extracts real, per-species spread+nature
usage data (species_usage(...).top_spreads, up to 8 real, ranked variants per species,
already part of the same CBD/Showdown pipeline used for movesets/items) via the same
infrastructure used everywhere else. Confirmed the real data shape before designing
anything: Showdown's top_spreads carries nature but its pct field is an UNNORMALIZED
MunchStats chaos weight, not a true percentage (a real, live footgun if ever conflated with
a genuine percentage elsewhere); CBD's pct IS a real percentage but lacks nature. Real
examples confirmed genuinely distinct strategies coexist unlabeled in the same list
(Incineroar: offensive vs. bulky-special vs. bulky-physical variants; Farigiraf similarly
varied) — nothing in the data explains which variant fits which strategic context, and
no field proves a spread co-occurred with any specific moveset/item (each is independently
top-ranked). This meant the new tier-2 mechanism couldn't be a simple top-1 lookup (which
is what the existing featured_or_common_set already does, and was confirmed insufficient
for this purpose, since it discards the real variation this task exists to use) — it needed
genuine reasoning: given the real, available variants and real context (role, team state,
threats/needs already established), select the one that best fits, the same propose-then-
verify shape already proven for _best_payoff_move's selection in the setup-attacker work.

**Corrected spread-sourcing hierarchy**: tier-1 (exact cached build, unchanged) -> tier-2
(new: contextual reasoning over real top_spreads variants, offline or via a dedicated live
fetch for out-of-coverage species) -> tier-3 (role_spread's now-corrected, legal hardcoded
table, genuine last resort only). Integrated into both recommend.py and the slot-fill path.

**Second ADR-014 live-fetch exception (Amendment 2026-08-08a):** the offline usage
snapshot's top-50-species-plus-lineage cap (the same boundary that caused the earlier
Clefable gap) leaves otherwise-legal species with no real spread variants for tier-2 to
reason over. Resolved the same way as lookup_live_build's exception (Amendment
2026-08-07a) — confirmed this is a second, separately-justified instance of the same
purpose/mechanism distinction, not a blanket loosening: a dedicated fetch_live_spreads
mechanism (known MunchStats/CBD endpoints, known structured schemas, deterministic parsing,
explicitly NOT reusing the construction-scoped usage_cbd.py/usage_showdown.py fetchers)
fires only when a species has no offline usage row; any failure, unsupported regulation, or
unusable data returns no candidates and falls through cleanly to tier-3.

### 2026-08-08 (cont.): _pick_role redesign — design work, not yet implemented; discovered
the wiring gap is larger than assumed

Attempted to redesign _pick_role's output vocabulary (to support Compendium-shaped role
names alongside coarse fallback values) and design a top-level dispatcher connecting it to
SlotFillContext's discovery machinery. Real design progress was made, but the session
surfaced that the actual scope is bigger than a _pick_role redesign — the end-to-end
wiring flow connecting the many individually-built pieces has never actually been
specified, and almost none of it is live in production today.

**Vocabulary corrections worked out for _pick_role's RoleArchetype set:**
- support_speed_control confirmed as illegitimate output — not because it's too coarse,
  but because it names a CATEGORY of need (which itself requires further resolution:
  Trick Room? Tailwind? Sticky Web? Icy-Wind-class coverage?) rather than a terminal
  decision. Every other _pick_role output is directly actionable by a downstream
  mechanism; this one wasn't. Fix: _pick_role should output whichever SPECIFIC kind
  actually fits (same mechanism as any other role — name it if context favors one; if
  genuinely ambiguous among several real options — e.g. the TailRoom case, where Trick
  Room AND Tailwind can both apply simultaneously — that ambiguity needs its own
  resolution, not forced into a single coarse label).
- bulky_pivot confirmed to hide a real internal split (bulky/absorb-then-pivot vs. fast/
  pivot-before-being-hit) and should become two values, bulky_pivot/fast_pivot. Confirmed
  pivoting is NOT a universal need the way speed control was (fully opponent-dependent,
  "every team considers it, none highly prioritizes it") — meaning, unlike speed control,
  there's no better-positioned upstream mechanism to resolve it instead, so it correctly
  stays as a low-priority, coverage-gap-style _pick_role output.

**The more consequential finding: _pick_role and SlotFillContext are not two competing
decision paths (the "which branch fires first" framing this session started with was
wrong) — they answer genuinely different-grained questions.** Confirmed via direct
inspection of _pick_role's real implementation (previously only known from a summary
description): it decides WHAT KIND of role a slot needs (a coarse label), while
SlotFillContext's query-tool machinery (query_threat_counters, query_support_needs)
decides WHICH SPECIFIC SPECIES fills a role once one is known. This reframes the design
from "a three-way dispatcher choosing between competing reasoning systems" to a two-stage
pipeline: decide role first (deterministic, _pick_role's actual job), then discover
species for that role (SlotFillContext's job) — sequential, not alternative.

Also confirmed directly (not assumed) that _pick_role's "archetype components" and
"coverage-gap default" branches are less cleanly separated than their names suggest: the
coverage-gap branch has two materially different paths depending on whether any species
already exists in the draft (a coarse, threat-blind shortcut when one does; real
threat/coverage/SPOF machinery, calling classify_matchup, only when the draft is
completely empty of species) — the two reasoning "kinds" partially overlap in practice.

**The most important finding: almost none of ADR-022/023's machinery is actually wired
into the live proposal loop.** A repository-wide call-site search confirmed
query_threat_counters, query_support_needs, SlotFillContext, run_slot_fill_terminal, and
role_candidates are all instantiated ONLY in tests today — _pick_role, narrow as it is, is
the ONLY role/species-decision logic actually running in production. This means the real
next step isn't refining _pick_role's design further in isolation — it's specifying the
actual end-to-end flow that connects everything, which has never been done.

**Decided: rather than continue designing the flow abstractly, run a third role-play
session (via Cursor, with real code/tool access) explicitly framed as DISCOVERY rather
than validation** — given how many individually-correct, individually-tested pieces now
exist with no specified connecting sequence, the fastest way to find the actual natural
flow (and every gap in it) is to have Cursor attempt to actually use the tools end-to-end
for a real slot-fill and report where it breaks down, rather than keep whiteboarding the
sequence without testing it against the real pieces.

No code shipped this session on this thread. Deliberately deferred: the actual
_pick_role/dispatcher implementation (blocked on the role-play's findings); the
AnnotatedCandidate three-source generalization; the theme-filtered-pool producer for
case-3 slot-fill (from the earlier wiring-design thread, still unresolved and now folded
into the larger "what's the real flow" question this role-play session is meant to answer).

Next session should start by reading the Cursor role-play report before any further
design work — that report is expected to be the primary input for actually specifying the
end-to-end wiring flow.

### 2026-08-08 (cont.): slot-fill flow discovery (Cursor role-play) — end-to-end sequence
specified; phase routing corrected via follow-up

Read Cursor's slot-fill discovery report (four scenarios, real tool/data calls, not
role-play-in-chat) as the primary input for resuming the paused _pick_role redesign. This
report is higher-confidence than prior chat-based stress-tests since it exercised real
repository functions and surfaced failures directly rather than by simulation.

**Confirms the paused session's core framing.** _pick_role deciding WHAT KIND of role and
SlotFillContext's query machinery deciding WHICH SPECIES are sequential stages, not
competing paths — Scenario 1 (Kingambit) demonstrates this directly: the user's "Trick
Room" choice had to resolve to a role decision before the query tools could do anything
useful with it. The concrete missing piece, confirmed by direct inspection rather than
assumed: **no live node currently produces RoleShapeContext from real state.** This is the
paused _pick_role redesign's actual next job — _pick_role's output (or its redesigned
successor's) becomes the RoleShapeContext producer feeding SlotFillContext.

**Real structural bug in ADR-023, not just an unwired edge.** ADR-023's terminal chain
("hand off to refinement pipeline") commits species via apply_lock BEFORE refinement runs,
per Scenario 1 step 15 — an incomplete/wrong build (missing nature despite usage evidence)
gets locked before anyone sees it. Fix (from the report, adopted): split candidate
selection from build commitment — candidate chosen -> provisional full build -> user
confirmation -> atomic slot lock. This amends ADR-023's terminal procedure, not just
propose_team_draft's wiring.

**Team-phase routing confirmed necessary, but the report's own proposed boundary was
wrong** — flagged this directly rather than adopting it as-is (the "roughly three locked"
threshold read as anecdote-derived, not structurally justified: shared-teammate
intersection and coverage aggregation are computable at 2 locked, not 3). Sent a targeted
follow-up question to Cursor (which retains the role-play transcripts) rather than argue
from the report's summary. Cursor's transcript-level answer, confirmed against actual
scenario events rather than the report's own prose:

- Archaludon scenario: team-wide reassessment already happened correctly immediately after
  the 2nd lock (events 40-41 — Pelipper's Tailwind satisfaction detected, screens gap
  identified, Grimmsnarl selected before any 3rd-lock threshold). The later Basculegion
  failure (redundant Rain offense) was NOT a count-threshold problem — it was continuing to
  prioritize Archaludon's stale teammate list after team composition had changed, and the
  specific "duplicates Mega Swampert" objection literally couldn't fire before Mega
  Swampert existed to duplicate.
- Mono-Fairy scenario: no new orchestrator behavior appears at any count boundary past 2
  locked (checked at 3/4/5/6 explicitly) — later discoveries were candidate-specific
  (missing usage data, ability/move modeling gaps, Mega-roster semantics), not phase-
  specific. Six-lock review is terminal roster validation, materially different in kind
  from generating a next candidate — a real fourth phase, not folded into multi_locked.

**Corrected finding: the fix is a recompute trigger, not a phase boundary.** "Switch modes
at N locks" was the wrong shape of rule regardless of which N — team-wide signals must be
recomputed after every lock (or provisional candidate), not cached from whatever state
existed when a phase was entered.

**Final phase design (four phases, confirmed via transcript, not the report's original
three-way split):**
1. `empty` — no locked members, no anchor evidence exists.
2. `single_locked` — anchor-only evidence; unmodified from today's Scenario-1-shaped
   sequence.
3. `multi_locked` (2+, single bucket, no further count split) — team-wide signals active
   and MUST be recomputed after every lock, not cached at phase entry. Ranking receives
   changing parameters (remaining slot count, role/matchup deficits, attacker/support/
   balance preference, shared-teammate evidence, condition resilience, candidate
   redundancy) — not additional phase branches.
4. `complete` — terminal roster review (legality, item uniqueness, monotype, residual
   threats) once the roster is full; validates a finished roster rather than generating a
   next candidate, confirmed structurally distinct from `multi_locked` via the mono-Fairy
   trace.

**Scoped down from the report's full proposal, deliberately.** The report's "natural
end-to-end flow" (10 steps) and seven proposed module boundaries bundle in substantial
additional design surface — canonical name/form resolution at the input boundary,
ownership propagation across base/Mega forms, a teammate query API + shared-teammate
intersection, condition-resilience assessment, selected-four/bring-four compatibility
modeling, a labeled static fallback for calc-unavailable — that is real, individually
valid future work (several map to already-documented failure modes) but is NOT required to
answer the paused session's actual blocking question. Deliberately kept out of this pass's
scope rather than adopted wholesale under "wiring the flow."

**Minimal flow now specified to design the _pick_role dispatcher against:**
`route_team_phase` (the four phases above) -> `discover_slot_candidates` (redesigned
_pick_role produces role decision -> feeds RoleShapeContext -> SlotFillContext ->
existing ADR-022 query tools -> ADR-023's overlap/merge, corrected per above) -> present
-> provisional build -> user confirmation -> atomic lock -> post_lock_review (must
actually invalidate/refresh multi_locked's team-wide signals, not just re-route).

No code shipped this session. No ADR entries written yet, consistent with this project's
standing practice — this session specifies the flow; ADR-023's amendment and any new ADR
for phase routing should be drafted once the _pick_role dispatcher redesign is actually
finished against this flow, not before.

**Deliberately deferred, tracked as separate future scope, not folded into this task:**
canonical name/form resolution at input boundary; ownership propagation across base/Mega
forms; teammate query API + shared-teammate intersection mechanism; condition-resilience
assessment framework; selected-four/bring-four compatibility modeling; labeled static
fallback when calc is unavailable; Mimikyu usage-snapshot gap; `_union_move_candidates`
frozenset-iteration nondeterminism.

Next step: specify what `discover_slot_candidates` does with _pick_role's output to
actually construct RoleShapeContext — this is the concrete design surface that finishes
the paused _pick_role redesign.

### 2026-08-08 (cont.): anchor-role / target-role pipeline — Tracks A-C implemented,
closing out the slot-fill flow discovery arc

Closes the design arc opened by the paused `_pick_role` redesign and the Cursor slot-fill
discovery report earlier this session. Four discovery/design documents fed this
implementation, in order: `slot_fill_flow_discovery_2026-08-08.md` (four-phase team
routing, provisional/confirm/atomic-lock correction to ADR-023), `role_shape_context_
derivation_discovery_2026-08-08.md` (first pass at RoleShapeContext derivation — later
partially superseded), `anchor_role_and_target_role_discovery_2026-08-08.md` (the
consequential correction: RoleShapeContext describes the anchor, `_pick_role` has only
ever described the open slot — these are two different missing producers, not one), and a
final implementation plan that went through one correction round before being built.

**Core structural finding, worth restating plainly since an earlier statement in this same
session was wrong:** `_pick_role`'s redesign was never sufficient on its own to unblock the
slot-fill flow. A second, entirely new producer — `classify_anchor_role -> AnchorRoleDecision`
— was required and did not exist anywhere in the repo before this work. `_pick_role` stays
scoped to `TargetRoleDecision` (the open slot); `classify_anchor_role` is new, for the
existing anchor. Confirmed via direct transcript reconstruction of the Kingambit case: three
non-interchangeable role concepts were in play simultaneously (`infer_role`'s kit inference
-> `bulky_attacker`; user's strategic label -> `trick_room_sweeper`; the eventual open-slot
target role -> `trick_room_setter`), and nothing in the codebase previously separated them.

**Real correction to the first RoleShapeContext report, caught by testing against a second
anchor rather than trusting Kingambit alone:** that report proposed `match_status="clean"`
should mean "skip raw support-needs analysis." Direct execution against Archaludon (a build
that cleanly matches its proposed strategic identity) disproved this — clean classification
still surfaced real, useful needs (screens, healing, Tailwind). `match_status`/`match_quality`
is diagnostic classification quality, never a routing shortcut; orchestration always decides
whether raw support analysis runs.

**Shipped, three tracks:**
- **Track A (prerequisite):** `Slot.ability` persistence added; `all_locked()` now requires
  all seven complete-build fields (species, ability, item, moveset, nature, spread, role).
  Confirmed ability wins over usage-derived ability; usage-derived remains distinguishable
  via provenance, never silently promoted to confirmed. Sequenced strictly before Tracks
  B/C, consistent with this project's standing "don't build new logic on an unverified
  foundation" precedent (same shape as the earlier role_spread fallthrough fix).
- **Track B:** `resolve_anchor_build -> ResolvedAnchorBuild` (per-field provenance domain:
  user_confirmed/provisional/usage_derived/cached/synthesized/legality_only/unknown;
  fingerprinted for recomputation triggers) and `classify_anchor_role -> AnchorRoleDecision`
  (role_id, secondary_role_ids, structured mechanisms each tagged needed/wanted/secondary,
  kit_role as coarse infer_role evidence only, never promoted). `RoleShapeContext` narrowed
  to exactly `primary_function`, `tankiness`, `requires_setup_turn` (renamed from
  `setup_dependent`) — `match_status`, `archetype_id`, `partial_signals` removed (zero
  consumers, zero production constructors, confirmed twice across two reports).
- **Track C:** `TargetRoleDecision` (immutable, threaded through `SlotFillContext`,
  `AnnotatedCandidate`, and pending presentation — candidate-specific, not a single
  context-level field, so threat-only alternatives don't silently inherit a role they don't
  provide) and the provisional-build correction: candidate acceptance now produces
  `PendingSlotIntent`, not an immediate species lock; `ProvisionalSlot` requires all seven
  fields complete or returns a structured unresolved result; atomic full-slot commit
  prevalidates and locks all fields together or changes nothing. `_apply_locks_batch` left
  unchanged for ordinary partial steering — the new atomic path is additive, not a
  replacement.

**`_pick_role` vocabulary corrections (from the earlier paused session) confirmed carried
forward:** `support_speed_control` excluded from the target-role domain; `bulky_pivot`/
`fast_pivot` kept distinct. Deliberately does NOT invent a pivot-selection heuristic where
current inputs give no signal — this project's "don't build for a case you can't yet
verify" discipline applied correctly by Cursor without being asked.

**One real bug caught and fixed during plan review, before implementation:** the first
submitted plan sourced `secondary_role_ids` from `secondary`-tier (incidental) mechanisms —
inverted from the field's own definition, which needs `needed`/`wanted`-tier mechanisms
supporting a role other than the primary. Traced explicitly through Pelipper in the
corrected plan: needed automatic Drizzle -> primary `rain_setter`; wanted Tailwind -> distinct
`secondary_role_ids=("tailwind_setter",)`. Caught because the plan was reviewed as actual
content, not accepted from a summary confidence score (an intermediate "97.9% confidence"
scorecard-style review from Cursor was explicitly rejected as insufficient evidence and
resubmission of real plan text was required — worth normalizing as standing practice for any
future AI-generated review summary, not just this one).

**Deliberately deferred, not oversights:** Electro Shot -> Rain move-derived condition
detection (explicitly proposed for inclusion mid-plan, explicitly cut back out for scope
consistency with the discovery reports' own "Next priority, not this pass" categorization —
Archaludon's Stamina evidence still ships, Rain detection does not); canonical name/form
resolution; teammate query API; condition-resilience assessment; selected-four modeling;
calc-unavailable static fallback; a permanent strategic-role taxonomy (role_id stays an
opaque identifier); general team-phase routing beyond the specific candidate-selection ->
provisional-refinement -> full-build-confirmation -> atomic-commit transitions actually
needed here.

**One real open risk, not yet resolved:** the production checkpointer is undefined in
`recommender/graph.py` (tests use `MemorySaver`, which proves persistence-across-invokes but
not restart durability). If a strict-msgpack checkpointer is eventually deployed, the new
immutable state dataclasses (`TargetRoleDecision`, `PendingSlotIntent`, `ProvisionalSlot`,
etc.) will need explicit allowlisting to serialize. Deliberately NOT implemented speculatively
against an undetermined checkpointer interface — tracked as a required follow-up tied to the
actual checkpointer selection decision, not built ahead of that decision.

431 tests passing (up from 385), 5 skipped. Compile and diff checks pass. Verified directly
(not just "tests pass"): ability persistence and seven-field completion; Kingambit,
Archaludon, Pelipper, and Farigiraf acceptance cases by name; structured (non-silent-default)
ambiguous speed-control result; provisional refinement and atomic full-slot commit behavior.

Plan file itself left untouched by the implementation, per the discipline this project
already applies to source docs — implementation followed the plan, didn't rewrite its
record.

Next: resolve production checkpointer choice (blocks the msgpack-allowlisting follow-up);
Electro Shot -> Rain and other move-derived condition detection remain open, separately
scoped work; general team-phase routing (the four-phase design from the flow-discovery
report) is still only conceptually specified, not wired into the live graph beyond what
Track C's transitions required.

## TOOLS & RESOURCES

- **Pokémon Showdown** — battle simulator and reference data source. Formats: `[Champions] BSS Reg M-B` (singles), `[Champions] VGC 2026 Reg M-B` (doubles). Note regulation letter will update over time — do not hardcode "M-B" assumptions deep into the architecture; treat regulation as a parameter.
- **Original RL project** — reference only, for lessons learned on state representation and reward design, not for reuse of the trained artifact.

---

## DEEP TECHNICAL DETAILS (interview talking points — not resume bullets)

*(To be populated as the project develops — mirrors the structure of the VinylIQ master resume's Deep Technical Details section. Capture: why the legality-checking approach was designed the way it was, what regulation-versioning approach was chosen and why, any case where the agent's recommendation was wrong and what that revealed, RL training details once retrained, and any eval surprises once Showdown simulation work starts.)*

### Domain knowledge: weather/phase-order mechanics (2026-07-27)

- **Simultaneous automatic (switch-in) weather-setters resolve in Speed order, and the
  slower one's effect persists** — since weather-setting simply overwrites whatever's
  currently active, being the *slower* of two simultaneously-triggering automatic setters is
  the actual advantage for guaranteeing your weather sticks, the reverse of the usual
  faster-is-better instinct.
- **Champions' phase order is strict and sequential, not speed-contested, across switch-in
  effects → Mega Evolution → moves.** A same-turn Mega Evolution's weather-setting ability
  (e.g. Mega Charizard Y's Drought) always resolves after any automatic switch-in
  weather-setter (e.g. Pelipper's Drizzle), regardless of either Pokémon's Speed stat — this
  is a phase-structure guarantee, not a race. Correctly explains why the Mega Charizard Y
  weather-flip threat (flagged earlier this session) works the way it does.
- **A fast weather-re-setting move's real value is "before any attacker acts this turn,"
  not "faster than the opponent's setter."** E.g. Alolan Ninetales using a weather move isn't
  racing another setter — it's re-establishing weather after a mid-turn change (a switch-in
  or Mega Evolution) before either side's attacks resolve that turn, which is a broader and
  more accurate threat model than a setter-vs-setter framing.

These are concrete mechanics the still-open team-wide threat-coverage and single-point-of-
failure checks (flagged 2026-07-27, not yet designed) will need to reason about correctly
once built.

**Design implication:** Failure modes #1–#3 all point to the same root fix — legality (species + item + format + regulation) must be **checked programmatically against real Champions/regulation data**, never inferred or assumed by an LLM from general training knowledge. Failure mode #4 points to a second required fix — any mechanical claim (speed comparison, damage calc, matchup assessment) must be backed by an actual calculation/simulation call, not a generated assertion. These two fixes are the real "agentic" core of the project: tool-grounded legality checks + tool-grounded mechanical verification, not just a chat wrapper around Pokémon knowledge.