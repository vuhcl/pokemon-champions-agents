# EVAL RESULTS — Pokémon Champions Agentic Team-Building System
## Kept separate from the narrative log so quantitative results don't get buried in prose.
## Populate starting in Phase 2 (Showdown-simulated evaluation). Do not backfill with vibes —
## if a number isn't measured yet, leave the section marked TBD rather than estimating.

---

## Legality-grounding accuracy (Phase 1 — should be measured even before Showdown eval exists)
*What to measure: does the recommender ever suggest a species/item that's actually illegal in the
target regulation? This is directly testable against known regulation data without needing
Showdown simulation at all, and should be the first hard number this project produces.*

- Test set size: TBD
- False-legal rate (recommended something actually banned/unavailable): TBD
- Notes:

---

## Mechanical-claim verification accuracy (Phase 1)
*What to measure: when the agent makes a speed/damage/matchup claim, does it match an actual
calculation? Sample a set of claims, verify each by hand or via calc tool, report agreement rate.*

- Test set size: TBD
- Agreement rate: TBD
- Notes:

---

## Showdown-simulated win rate (Phase 2)
*Primary quantitative eval, once built. Recommended teams played against a defined set of known
meta teams via Pokémon Showdown's simulator/API.*

- Format tested: TBD (BSS Reg M-B or VGC 2026 Reg M-B — see ADR-005)
- Opponent team source: TBD
- Number of simulated games: TBD
- Win rate: TBD
- Comparison baseline (e.g., a naive/random-legal team, or a popular sample team): TBD
- Notes:

---

## RL-policy divergence (Phase 3 — stretch goal)
*Once the battle log parser and new RL policy exist: for actual played battles, how often and
in what ways does the human-piloted line diverge from what the policy would have done, and is
that divergence flagged with an honest confidence level rather than treated as uniformly
significant?*

- Battles analyzed: TBD
- Divergence rate: TBD
- Notes:

---

## Known limitations / honest gaps (update as discovered)
*Mirror the honesty standard set by the VinylIQ RAG-not-shipped story — if something doesn't
work or an eval result is weak, it goes here plainly, not smoothed over.*

-
