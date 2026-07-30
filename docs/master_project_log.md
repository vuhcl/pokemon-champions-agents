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

---

## CURRENT STATE

**Phase:** Not yet started — this log is the seed/kickoff document.

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

- **Team-wide threat-coverage check:** "does this team, as a whole, have a real answer to
  threat X" is a distinct, higher-level question from tier 3's per-slot breakpoint
  verification. No mechanism designed yet.
- **Single-point-of-failure detection:** identifying that a team's win condition depends
  entirely on one Pokémon surviving/acting, with no redundancy (surfaced via the Mega
  Charizard Y / weather-war example) is a distinct capability from the above — a structural
  read of `team_draft` as a whole, not a per-threat check. No mechanism designed yet.
- Both are explicitly *pre-battle, team-composition* concerns (does the team have the tools)
  — not in-battle sequencing/positioning (timing, baiting switches), which remains correctly
  out of scope per ADR-012a, belonging to the deferred phase-3 battle-log/RL work.

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

---

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
