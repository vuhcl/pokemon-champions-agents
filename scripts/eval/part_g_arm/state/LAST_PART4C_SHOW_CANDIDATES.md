# 4c — show_candidates

Pre-build context: `LAST_PART4C_CANDIDATE_CONTEXT.md` (commit 8157142).

## Spec (as built)

`show_candidates(slot, n?)` → `discover_single_locked` (1× `all_locked`) or `discover_multi_locked` (≥2) → pending `candidate_selection`.  
`allow_live` not passed (offline pins). Caps options with `n`. Filters rejected **species lineages** after the producer (single_locked does not; multi_locked already does in merge). Does **not** write `team_draft`. Slot must be the next blank open index (CLI fills first open).

## Context table (item 1) — summary

| need | empty | partial all_locked | H25/H26 fixtures |
|---|---|---|---|
| locked anchor | **missing** → refuse | yes | species/ability/item only → **not** `all_locked` → refuse |
| rejected list | honored in wrapper | honored | n/a |
| bootstrap | out of scope | not needed | not needed |

## Determinism (item 3)

Same fully locked Venusaur + pins + same call → identical `(species, source, evidence)` twice (`test_determinism_same_options_twice`).  
Variance sources: calc service (degraded → static/need path; labeled via `candidate_discovery_error`); usage pins `data/usage/champions-reg-mc.ingame_doubles.v1.json` / showdown doubles (`31af0801…` / `63bcefe4…`).

## Registration facts (item 7)

| fact | value |
|---|---|
| Tool-determined | option identity, order, `source`, `evidence` strings from producer |
| Pins read | usage ingame + showdown doubles; legality snapshot; calc when up |
| LLM call | **none** |

## Tests

`test_show_candidates.py` — 5 passed (open slot; reject honored; empty refuse; determinism; locked-slot refuse).

## Dev rows (≥4, keys first, Venusaur/Blastoise/Beedrill)

| id | expect |
|---|---|
| dev-show-open | Venusaur fully locked; show slot 2 → options ≥1; draft unchanged |
| dev-show-reject | reject option 1; show again → species absent |
| dev-show-empty | empty team → refuse |
| dev-show-locked | show on locked slot 1 → refuse; draft unchanged |

## Reference trajectories (Part 3)

| row | status |
|---|---|
| MT4 | t1 `reject_option` ok; t2 rediscovery **blocked** — CS seed has no locked anchor |
| H25 / H26 | **blocked** — fixtures not `all_locked` (would need fixture/product change outside `state/`) |
| H17 / H18 | **blocked** — empty; bootstrap out of scope |

Producer path (reject + rediscover) proven on fully locked Venusaur, not on MT4 seed bytes.

## Stop rule

No LLM, no live web, no files outside `state/`. Did **not** mock. Did **not** alter fixtures to force H25/H26.

Prompt draft (Part 5): tool description above.
