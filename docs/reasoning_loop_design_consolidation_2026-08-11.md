# Agentic Reasoning Loop (v1.0) — Design Consolidation

**Date:** 2026-08-11
**Status:** Design record for review. No implementation started. Every section is either a
**Verified finding** (checked directly against `v0.2.0` source/tests) or a **Decision**
(settled in this session, not yet built) or an **Open item** (flagged, not resolved).
**Note on versioning:** the original handoff used "v2" for this milestone; the repo's actual
versioning (0.1 → 1.0) means this is v1.0 — the reasoning loop is the true MVP floor, not a
post-1.0 phase.

---

## 1. Track 1 — closed, verified against v0.2.0

**Verified finding:** `AnchorRoleDecision`, `classify_anchor_role`, `resolve_anchor_build`,
`derive_role_shape_context` (`recommender/anchor_roles.py`) and `TargetRoleDecision`,
`PendingSlotIntent`, `ProvisionalSlot` (`recommender/state.py`) are real, shipped, and tested
— not proposal-stage. Confirmed by running the suite directly at `v0.2.0`: **835 passed, 7
skipped**; `test_anchor_roles.py` **12/12**; live execution of `classify_anchor_role` against
a real Gholdengo build returns `role_id="nasty_plot_attacker"` as expected.

All six "Vu decisions required" from `anchor_role_and_target_role_discovery_2026-08-08.md`
are resolved as-shipped:

1. **Role vocabulary:** stays an opaque `str` identifier — no fixed taxonomy was built.
2. **Dual required roles:** `secondary_role_ids` sourced only from `needed`/`wanted`-tier
   mechanisms supporting a role other than the primary (a `secondary`-tier sourcing bug was
   caught and corrected in plan review before implementation). Pelipper: needed Drizzle →
   primary `rain_setter`; wanted Tailwind → `secondary_role_ids=("tailwind_setter",)`.
3. **`match_quality`:** kept `clean`/`partial`/`none`, confirmed diagnostic-only. The
   `RoleShapeContext.match_status` overload was resolved by removing `match_status`/
   `archetype_id`/`partial_signals` from `RoleShapeContext` entirely (zero consumers,
   confirmed twice), not by relabeling.
4. **`PendingSlotIntent`:** shipped with `schema_version`, `slot_index`, `species`,
   `target_role_decision`, `source`, `evidence`, `base_slot_fingerprint`, `stage`.
5. **Ability persistence:** Track A, sequenced strictly before Tracks B/C as a prerequisite.
   `Slot.ability` exists; `LockPayload`'s `SlotAttrName` includes `"ability"`.
6. **Role-correlated usage variants:** still genuinely open — not resolved, not claimed
   closed.

**No remaining Track 1 design work.**

---

## 2. Track 2, Surface 1 — turn-level steering

**Verified finding:** there is currently **zero live LLM in the graph**. `classify_pending`
(`recommender/nodes.py:101`) is entirely rule-based — frozensets of literal strings (yes/no/
ordinal/selection-prefix matching) against a `pending_presentation`'s options. If no
`pending_presentation` exists, it raises `NotImplementedError`. The only pluggable model seam
anywhere in the graph is `bootstrap_intake_parser`, scoped to one specific structured-intake
node — not a general reasoning surface.

**Decision — Option A (LLM fills the gap, doesn't replace the function):** the existing
rule-based matcher stays exactly as-is for anything it already handles (instant, free,
deterministic, fully covered by existing tests). The LLM engages only for: (a) no
`pending_presentation` exists, and (b) the rule matcher runs and finds nothing it recognizes
(today: silently falls through to `pending_response`). Rejected: routing every turn —
including literal "yes"/species-name replies — through the model, which would add latency/
cost/nondeterminism to a path that's currently instant and fully deterministic for no
benefit.

**Open item, not resolved:** exact routing for partial-signal replies (e.g. "no, show me
something bulkier" partially matches `_REJECT_ALL_REPLIES` but carries real steering intent)
— worth confirming during implementation whether a partial match should still route to the
LLM gap-fill path.

---

## 3. Edit-intent design (part of Surface 1's vocabulary)

**Decision:** a new intent for field edits on a pending `full_build_confirmation`, carrying a
structured delta (`{field, value}`). Rejected reusing the existing `rejection` intent — it
discards the whole candidate and re-enters discovery from scratch, which is semantically
wrong for "run Modest instead" (a correction to one field of a build the user otherwise
wants). Grounded directly in Scenario 4 of the slot-fill discovery report (Mega Mawile Swords
Dance addition, Hatterene Sitrus→Life Orb, Moonblast→Icy Wind — each requiring **fresh
confirmation after every material revision**, an invariant the discovery work already
established, not new).

### 3.1 Scope: field-only edit vs. full-set regeneration

Resolved by phrasing, extracted by the LLM at the same point as field/value:

- **Field-only** ("change the nature to Modest") → apply exactly that field; the
  re-verification table below still runs for the changed field, but no other field is
  revised to accommodate it.
- **Regenerate** ("give me a set with Modest nature") → the new value becomes a pinned
  constraint fed into the existing tier-1/2/3 refinement hierarchy, not a from-scratch
  discovery pass.
- **Ambiguous** → present a small closed choice, reusing `PendingPresentation`'s existing
  `completion_preference` kind rather than inventing new state.

### 3.2 Per-field re-verification table

**Revised 2026-08-11** after a Cursor review against real code and real transcript edits
(Section 3.2a/3.2b below) — several cells were missing, and one was found to be designed by
general reasoning rather than checked against actual shipped machinery. That one
(EV-into-nature-hindered) is explicitly marked as unimplemented rather than left looking
closed.

| Edited field | Legality | Mechanical-fit | Breakpoint/calc | Role re-check |
|---|---|---|---|---|
| **species** | — | — | — | *(not an edit — routes to `rejection` instead)* |
| **ability** | ✓ legal for species (`check_set`) | judgment unless tied to a named mechanism conflict — corrected from "ability-move synergy" (no such `check_theme_fit` rule exists; this is really `_mechanisms`/`infer_role` re-emit) | ✓ if stats change | ✓ mechanism evidence in `AnchorRoleDecision` |
| **item** | ✓ legality + Item Clause uniqueness (`check_set`) | ✓ Choice-item/non-damaging-move rule, Choice+TR Speed-direction conflict (existing `check_theme_fit` rules); **+ item×durability contradiction** (Focus Sash + HP≥20, or Leftovers/Sitrus + ~0 HP, via `_durability`) | ✓ Choice multiplier vs. breakpoints; **extended to any damage-modifying item** (Life Orb, Expert Belt, Muscle Band, Wise Glasses), not Choice-only — Hatterene's Sitrus→Life Orb edit needed this | rare |
| **item × nature** | — | **new cell:** if Scarf Speed already clears real breakpoints, prefer an offensive nature over further Speed investment (`scarf_clears_benchmarks`/`_scarf_nature_correction`, both confirmed real) | (same check) | — |
| **item vs. spread — binary contradictions** | — | ✓ **moved into the table** (see 3.4 for what stayed judgment) — Scarf overshoot, glass-item+tanky-spread, offense-amp+zero-offense-EV, category-boost+wrong-stat, Iron Ball+Speed-investment | — | — |
| **moves** | ✓ learnset legality; **exactly 4 moves, previously missing entirely** | ✓ same fit rules | ✓ category/BP shift vs. existing EV investment | ✓ **rescan `_mechanisms` over the full resulting moveset** — corrected from "only if the changed move was evidence," which misses a newly-*introduced* mechanism (the Icy Wind case, below) |
| **moves × nature axis** | — | **new cell, bidirectional:** physical/special/mixed bias checked both directions, not only when nature is the field being edited | — | — |
| **nature** | — | (see moves × nature, above) | ✓ breakpoint search (via existing tier-3-adjacent Speed-helper pattern) | ✓ nature-axis vs. `TargetRoleId`'s physical/special/mixed suffix (flag, see 3.3) |
| **spread** | ✓ totals exactly 66, each stat 0–32 (`_normalize_spread`) | **EV-into-nature-hindered-stat — not yet implemented anywhere; new rule to build**, not existing machinery (see 3.3) | ✓ breakpoint search (self-referential) | ✓ `_durability`'s `HP≥20` tankiness threshold |

Ordering follows the existing tier-1/2/3 refinement hierarchy's own cost ordering: legality
first (cheap, fails fast), mechanical-fit second (cheap, static), breakpoint/calc last
(expensive, live service call) — stop at the first hard failure.

**Structural note:** `ProvisionalSlot` is frozen; every edit produces a new instance with a
new fingerprint, which is what makes "fresh confirmation after every revision" fall out
naturally rather than needing separate enforcement.

### 3.2a Verified against real code (Cursor review, spot-checked)

`scarf_clears_benchmarks`/`_scarf_nature_correction` (propose.py) and
`_SETUP_MOVES["swordsdance"] → "swords_dance_attacker"` (anchor_roles.py) confirmed real.
**A useful, non-obvious finding surfaced along the way:** Choice Band, Choice Specs, and
Assault Vest are all `is_nonstandard: "Past"` — illegal in the current Champions snapshot
(148 legal items of 583 entries, confirmed by direct count). Choice Scarf is the only legal
Choice item today, which simplifies the item×spread story: "Choice item vs. spread mismatch"
only ever means the Scarf/Speed case, never a Band/Specs-vs-offense-EV case, in the current
format.

### 3.2b Stress-tested against real transcript edits

- **Archaludon (Timid 2/32/32 → Modest 32/1/5/25/3):** table's checks are sufficient. The
  *reasoning* behind the move (teammate Tailwind justifying the Speed drop, Stamina covering
  physical bulk) is correctly out of table scope — that's team-context judgment, not a
  per-field re-verify concern. Soft, non-urgent gap: a spread-only edit that drops offensive
  EVs (32→5 SpA here) doesn't currently trigger any flag, since no move changed.
- **Hatterene (Sitrus → Life Orb):** was under-specified before this revision — role/
  durability re-check was marked "rare," but an item alone can flip `_durability`'s tanky/
  glass read (Sitrus reads tanky, Life Orb doesn't), and the breakpoint column's Choice-only
  framing missed that Life Orb changes real damage against shared threats. Both fixed above.
- **Icy Wind swap (Moonblast → Icy Wind):** exposed the "diff the changed move" bug fixed
  above. Separately, and left honestly open: even with the table fixed, Icy Wind's speed-
  control mechanism isn't in `_mechanisms` today — the producer itself needs building before
  a rescan can surface it.
- **Mega Mawile + Swords Dance:** exposed two gaps now fixed above — exactly-4 completeness
  wasn't checked at all, and a setup-move addition should make the role re-check mandatory,
  not conditional on phrasing.

### 3.3 Deterministic flag checks (spread/nature)

Both are data-only lookups, no calc/legality dependency, surfaced but **not hard-blocking**
(consistent with the project's standing boundary: the agent proposes and verifies, it doesn't
override an explicit user request):

1. **EV investment into a nature-hindered stat** — **not implemented anywhere in the current
   codebase; this is new work, not an existing check** (corrected from the original framing,
   which presented it as already-covered without verifying). A neutral nature reaching the
   same effective total more efficiently always exists, so once built this is close to always
   a real mistake and should be flagged prominently.
2. **Nature-axis vs. role-axis mismatch** — compares the nature's hindered stat against the
   already-shipped `_physical_attacker`/`_special_attacker`/`_mixed_attacker` suffix on the
   resolved `TargetRoleId`. Softer flag — legitimate mixed/support builds exist where this
   isn't actually wrong.

Both output into a **new field**, not `AnchorRoleDecision.conflicts` — see 3.4 for why.

### 3.4 Item-vs-spread fit — partially deterministic, partially reasoning-loop

**Revised finding:** the original claim that item-vs-spread fit is "entirely judgment" was
too strong. A Cursor review against the real Champions-legal item list (148 items) found five
real binary contradiction patterns that reduce to a lookup, not a judgment call: Scarf
overshoot (covered above, item×nature), glass-item+tanky-spread (Focus Sash + HP≥20, via
`_durability`), offense-amp+zero-offense-EV (Life Orb/Expert Belt/Muscle Band/Wise Glasses +
0 Atk/SpA), category-boost+wrong-stat (Muscle Band + SpA-only, Wise Glasses + Atk-only), and
Iron Ball+Speed-investment. All five moved into the table above as mechanical-fit cells.

**What genuinely stays reasoning-loop:** degree judgments, not binary mismatches — e.g.
"how bulky is bulky enough" for a Leftovers/Sitrus spread (the Archaludon case). This is
scoped to the reasoning loop, grounded in real item/spread data pulled via the same tool
calls everything else in this design uses, never asserted from training-data assumptions
about what an item does.

**Decision — new field, not `AnchorRoleDecision.conflicts`:** `AnchorRoleDecision` is
`@dataclass(frozen=True)`, built once per call from the build it was given — its `conflicts`
tuple is the classifier's own account of that build, reproducible from the same input every
time. A reasoning-loop judgment arriving later, from a different trigger (item edit
triggering a spread-relevant check), evaluated by an LLM rather than computed by the
classifier, doesn't belong on that instance. Direct precedent already in this codebase for
resolving "one field, two meanings" by separating rather than tagging: `CandidateEvidence`
deliberately doesn't reuse `AnchorRoleDecision` for candidate-level evidence (logged reason:
"it classifies the anchor, not the candidate, and copying it would misattribute anchor-
classification confidence to species it was never evaluated against"); `match_status`/
`archetype_id`/`partial_signals` were removed from `RoleShapeContext` entirely rather than
kept and re-tagged.

New field: `review_flags: tuple[ReviewFlag, ...]` on the full-build re-confirmation
presentation, alongside the revised `ProvisionalSlot`. Each entry carries the claim, which
check produced it, and `basis="reasoning"` — deliberately **not** reusing
`CandidateEvidence.basis`'s vocabulary (`usage_backed`/`compendium_backed`/etc.), since none
of those mean "an LLM judged this from real data," and a same-named-different-meaning value
would recreate the exact conflation being solved.

**Open item, not resolved:** `ReviewFlag`'s exact shape (fields/types) needs a short schema
pass before implementation — only the field name, ownership location, and basis vocabulary
are decided here.

---

## 4. Track 2, Surface 2 — mid-discovery correction

**Correction to earlier framing:** a separate tool-calling loop with its own LLM harness (as
originally proposed) was over-scoped once checked against real code. Three specific cases,
each checked directly:

**Finding 1 — role-classification correction (Kingambit-style) already has almost
everything it needs.** `classify_anchor_role`'s `explicit_role` parameter already reads from
`Slot.role.value` whenever `Slot.role.locked` (confirmed at `slot_fill.py:203` and
`team_candidates.py:161`), and `apply_lock`'s existing relock/supersede path (`superseded`,
restorable via `restore_superseded`) already handles overriding an already-locked attribute
— the same machinery built for Choice-item conflicts. A correction that must persist "going
forward, not just one turn" is therefore already free. **Remaining gap:** Surface 1's
classifier needs to recognize this correction shape ("that's not X, it's Y" about an anchor's
strategic role) and emit it as the existing `lock` intent with `attr: "role"` — not a new
intent, handler, or state.

**Finding 2 — the Basculegion "stale anchor-centric reasoning" case is already structurally
solved.** Verified by reading `discover_single_locked`/`discover_multi_locked` directly:
phase dispatch is purely lock-count-based, and `multi_locked` never reads a single anchor's
teammate list — it aggregates via `collect_locked_anchor_contexts`/`build_team_threat_
objective`. The literal failure mode can't recur in the shipped system. Nothing to build.

**Finding 3 — "check the teammate data before recommending" is a genuine, unaddressed gap.**
Verified: `slot_fill.py` (the `single_locked` anchored-discovery chain) never calls teammate
data at all — only `multi_locked` does, and only for shared-teammate *intersection* across
multiple locked members, not a single anchor's own teammate list. `state["constraints"]` is
read only in `nodes.py`, not by discovery machinery, so it's not an existing hook either.
Doesn't need a reasoning loop — reads as a missing data source: `single_locked` discovery
should pull the anchor's own teammate record the same way `multi_locked` pulls shared
teammates.

---

## 5. Transcript re-audit outcome (Cursor, re-run against v0.2.0)

Cursor was asked to re-check every original "Neither" row from the role-play transcript
against current code (not the stale transcript), separate trust-boundary-violation rows from
genuine arbitration rows, and sort the remainder into deterministic-criteria vs.
presentation-policy buckets. Spot-checked directly rather than accepted on the table's word:

- `CHARGE_INSTANT_WEATHER` (Electro Shot→Rain), `type_effectiveness`'s `freezedry`/Water
  special case, and `effective_move_type`'s `liquidvoice`+sound-flag check all confirmed real
  in source — the three flagged mechanical-assertion trust-boundary rows are genuinely closed
  as tool-layer fixes, not open reasoning-surface scope.
- L25's Gholdengo claim confirmed by direct execution: `classify_anchor_role` on a real
  Nasty-Plot Gholdengo build returns `role_id="nasty_plot_attacker"`.
- L73's claim confirmed against ADR-026's actual text: severity-band ordering
  (`decisive/costly/toss-up/conditional/SPOF`) with `CompositionFit` deliberately inserted so
  a decisive/costly verified closure **still wins** even against a compositionally redundant
  candidate — meaning "diversity over raw counter count" isn't a missed dimension, it's the
  opposite of a deliberate existing design choice.
- Bucket B's L91 claim confirmed: `PendingPresentation.kind` is `Literal["candidate_
  selection", "full_build_confirmation", "completion_preference", "bootstrap_intake"]` — no
  non-deciding "deliberation" kind exists.

**Conclusion: no Surface 3 is justified.** Several "Neither" rows were already closed by
Tracks A–C and later work (target-role threading, Pelipper composite roles, need/compendium/
runtime-role taxonomy bridging, preference elicitation, confidence labels). Three mechanical-
assertion rows are already closed as tool-layer fixes; only Phantom Force positioning value
(L162) remains open, tracked as existing mechanical backlog, not new reasoning-surface scope.

**Bucket A — new deterministic scoring/selection dimensions (tool-side, not LLM judgment):**

- Hybrid/team-context spread selection consuming `secondary_role_ids` (currently unused for
  EV selection).
- Ability-utility arbitration beyond the current featured→unique-legal→weather-setter
  fallback chain (e.g. Unaware vs. compendium-default Cute Charm).
- A diversity-vs-decisive-closure axis — **flagged as a real product decision, not just an
  engineering scoping call** (see Open Items below), since ADR-026 built the current ordering
  deliberately in the opposite direction.
- Ally-damage/team-safety move-legality check (substituting a move to avoid hitting a
  teammate).
- The `single_locked` teammate hook (Finding 3 above) — restated here as a Bucket A item
  since it's a deterministic data-source addition, not reasoning-loop work.

**Bucket B — presentation/policy on existing `pending_presentation`, largely not new
architecture:**

- A non-deciding "deliberation" presentation kind (user asks to weigh options without
  choosing).
- Multi-plan keep-vs-collapse threshold (when discovery should present several ranked
  options vs. one default).
- Check-before-conditional-move ordering (verify a team-wide gap before offering a
  condition-dependent move choice).
- Claim-strength/confidence-overclaim policy (don't present "answers X" when calc only
  supports chip/2HKO).

**Separate, already-correctly-deferred producers — out of scope for this arc:**
bring-four/selected-four modeling, theme-bridge candidate generation (e.g. Mawile as a
Steel/Fairy bridge), monotype theme arbitration, condition-independent fallback-mode
demonstration.

---

## 7. Backup-redundancy / bring-4 composition modeling — new discovery track

**Distinct from Section 4's Surface 2 Findings 1–3** (which are about Basculegion/
single-locked-teammate mid-discovery correction) — this is a separate thread that grew out of
L73 (Open Item 1 below) and is tracked with its own numbering to avoid the collision.

**Origin:** L73 (Hydreigon over Incineroar, "role diversity over raw counter count") led to a
proposed fix — demote a redundant decisive/costly closure once a threat already has one —
that turned out to be **wrong**, contradicted by a real prior-session conversation (2026-08-12,
same arc as the slot-fill CLI validation work) about your actual Rain team (Pelipper/
Archaludon/Mega-Swampert/Sableye/Sinistcha/Maushold) and how bring-4 selection really works:
redundancy past the primary lineup (two rain setters, three attackers) isn't wasted roster
space — it's deliberate, giving real matchup-dependent choice at Team Preview. That
conversation had already flagged today's `duplicative` demotion as "backwards under this
model" and identified the need for a real discovery pass, not yet done at the time.

**Refinement from this session:** good backups don't overlap entirely. Pelipper and Sableye
share the critical role (rain setter) but diverge hard on everything else — Pelipper is
offense (Weather Ball/Hurricane) plus Tailwind/Wide Guard utility; Sableye is damage
mitigation (Light Screen/Will-O-Wisp) plus disruption (Encore). The backup needs to guarantee
redundancy on the one thing that's essential, while diverging elsewhere — not be a near-clone.

### 7.1 Verified code-level findings (corrected 2026-08-12 — see note)

**Correction note:** the first pass at this section contained a real error, caught and fixed
same-day. The original Finding 1 claimed move-based weather-setting wasn't recognized at all
— that was wrong, based on a grep that missed the actual variable name
(`WEATHER_SETTING_MOVES` in `move_narrowing.py`, aliasing `_WEATHER_MANUAL`). Verified live:
`classify_anchor_role` on a real Rain-Dance Sableye build correctly returns
`MechanismEvidence(mechanic='Rain Dance', relation='provides', role_id='rain_setter', ...)`.
Finding 2 was also overstated in the same pass and is corrected below (a partial escape hatch
does exist). Findings are renumbered to reflect what's actually true, checked more carefully
this time:

1. **The condition-side SPOF/backup escape hatch is real and already covers Sableye's actual
   case.** `_candidate_fills_condition_gap` (`team_candidates.py:568`) promotes a candidate to
   `complementary` when it fills a `single_provider_spof` gap on an essential/preferred
   condition, and move-based weather (Rain Dance included) is correctly recognized as
   `provides` evidence feeding it. **No fix needed here** — this was the error.
2. **The `primary_function` side has a narrower, differently-shaped escape hatch than the
   condition side, not none.** `corrects_skew` (`team_candidates.py:527`) promotes a second
   attacker to `complementary` if it corrects a physical/special balance — a real but narrow
   check. What's still genuinely missing: anything resembling the condition side's "there's
   only one provider, that's a SPOF, a second one has standby value" concept — two attackers
   of the *same* category (e.g. two physical attackers) still have no path to `complementary`
   even when the second is a legitimate Team-Preview alternate, since `corrects_skew` only
   fires on an imbalance, not on redundancy itself.
3. **Nothing measures divergence on the non-shared axes — this finding is unaffected by the
   correction above.** Neither `fills_gap` nor `corrects_skew` measure *degree* of difference
   on secondary functions; both are binary correction checks. Still the clearest gap of the
   three, and the one Section 7.2's data speaks to most directly.

### 7.2 Empirical grounding (real data, not just reasoning)

Existing offline data (`data/team-composition/champions-reg-mb.v1.json`) plus a new Pikalytics
team-usage extraction (`data/team-composition/champions-reg-mb.pikalytics-team-usage.v1.json`,
16,638 teams) give a real existence proof: **Pelipper+Sableye co-occur in 376 real tournament
teams (2.26%, usage-confirmed), with a computed divergence score matching the qualitative
description** — Pelipper reads Drizzle+Hurricane/Weather Ball+Tailwind/Wide Guard, Sableye
reads Prankster Rain Dance+Encore/WoW/screens/Fake Out.

**Two caveats on this data, not yet resolved:**
- **Population mismatch.** Both available sources are tournament data (Pokemon-Zone/Limitless
  and Pikalytics' `/team-usage`, confirmed directly — not ladder). Tournament play faces a
  narrow, often-scouted field and needs less broad-field redundancy than a general recommender
  (unpredictable single-opponent-at-a-time play) should assume. A tournament co-occurrence
  rate is a **lower bound** on how often this pattern should be treated as valuable, not the
  rate to calibrate against directly. No ladder-population source has been identified yet.
- **Compendium role tags may not reflect real usage weighting.** `sun_setter` showed 11.41%
  co-occurrence by compendium tag but only 0.18% once usage-confirmed — Whimsicott is tagged
  `sun_setter` for knowing Sunny Day (13.4% actual usage) while it's really Tailwind support
  (96.3%). Any Finding-2-style fix needs to check usage-weighted mechanism evidence, not raw
  compendium tags, or it will misfire on cases shaped like this one.

### 7.3 Backup-redundancy note

The move-based-weather correction above (7.1) removed part of what this section originally
called "not yet decided" — see 7.4 for the actual design, worked through the same session.

### 7.4 Design: unify Findings 2 and 3 into one mechanism, not two

**Decision:** the real remaining gap isn't "no escape hatch for `primary_function`" — it's
that neither existing escape hatch (`fills_gap` on the condition side, `corrects_skew` on the
`primary_function` side) checks *how different* the backup candidate actually is. That's one
missing piece, not two, and fixing it properly also closes a latent gap on the condition side
that's been present the whole time: `_candidate_fills_condition_gap` promotes *any*
SPOF-filling candidate to `complementary` today regardless of divergence — a near-clone second
rain setter would get the same free pass Sableye correctly gets, purely by accident of not
having occurred in practice yet.

Proposed shape:

1. **`divergence_score(candidate, existing_provider) -> float`** — built from real data, not
   an invented taxonomy: reuse the tagging approach the Pikalytics calibration script already
   validated (move-category tags from `flags.v1.json` + existing mechanism ids —
   weather/TR/Tailwind/screens/redirect/disruption), the same approach that scored
   Pelipper/Sableye at 0.8. Compares the two builds' non-shared-role function sets.
2. **Extend `primary_function` with the same essential/SPOF concept `assess_condition_
   resilience` already has for conditions** — a `primary_function` with exactly one current
   provider is a SPOF, mirroring `single_provider_spof`.
3. **Gate both escape hatches on divergence, not just presence.** A candidate filling a SPOF
   (condition *or* `primary_function`) gets `complementary` only if `divergence_score` clears
   a threshold; below it, falls through to `duplicative`/`severe_duplication` as today —
   correctly catching genuine near-clones on both sides, not just the `primary_function` side.

**Open, not resolved:** the divergence threshold itself is provisional. Tournament data gives
a real anchor (Pelipper/Sableye at 0.8 reads as a clear pass), but per 7.2's population
caveat, tournament data is a lower bound, not a calibration set — treat the threshold as a
first estimate, revisit if/when a ladder-population source is found.

**On L73, since it was blocked on this track:** this design doesn't automatically resolve it.
It fixes "should a genuinely diverging second provider of an already-covered need get
promoted" — a different question from L73's apparent shape ("does Incineroar's decisive
closure beat Hydreigon's diversity"), which only overlaps if Incineroar was itself a *second*
provider against a threat something else already covered. Still needs the transcript check
flagged earlier (was Incineroar's threat already covered elsewhere on the roster?) before it's
conclusively answered, even after this design lands.

---

## 8. Consolidated backlog

| # | Item | Status |
|---|---|---|
| 1 | `divergence_score` function, built from real move/mechanism tag data | Designed (7.4), ready to scope |
| 2 | `primary_function` SPOF concept (mirror `assess_condition_resilience`) | Designed (7.4), ready to scope |
| 3 | Gate both `fills_gap` and the new `primary_function` hatch on divergence threshold | Designed (7.4), ready to scope |
| 4 | Divergence threshold calibration | Open — provisional value only, needs ladder data or an explicit "best estimate, revisit later" call |
| 5 | L73 final resolution | Blocked on 1–3 landing, plus the Incineroar-threat-coverage transcript check |
| 6 | Surface 1 (turn-level steering, Option A) | Designed (Section 2), ready to scope |
| 7 | Edit-intent (scope resolution, re-verification table, `review_flags`) | Designed (Section 3), ready to scope |
| 8 | Surface 2 Findings 1–3 (Basculegion/single-locked-teammate) | Designed (Section 4), ready to scope |
| 9 | Bucket A (deterministic scoring extensions from the transcript audit) | Designed (Section 5), ready to scope |
| 10 | Bucket B (presentation/policy changes) | Designed (Section 5), ready to scope |
| 11 | Surface 1's partial-match routing | Open — flagged for implementation-time confirmation |
| 12 | `ReviewFlag`'s exact schema | Open — vocabulary decided, fields not written |
| 13 | EV-into-nature-hindered-stat | Open — confirmed unbuilt (Section 3.3), new deterministic rule |
| 14 | Icy Wind's speed-control mechanism missing from `_mechanisms` | Open — surfaced by transcript stress-test (3.2b) |
| 15 | Overall sequencing across items 6–10 | Open — not proposed anywhere in this document |
