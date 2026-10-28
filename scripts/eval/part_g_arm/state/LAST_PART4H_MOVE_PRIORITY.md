# 4h — move priority exposure

## Spec

State-side enrichment of `get_move_static`: after `ArmTools.call`, attach `priority` from `data/moves/static.v1.json` (`moves.<id>.priority`). Does not edit `recommender/arm_tools.py`. No new tool name.

## Why not edit arm_tools

Constraint: new files in `state/` only (except authorized MRB1 / mega product branch). The legality snapshot’s move rows omit priority; the static blob has it. Harness wraps LOOKUP `get_move_static` via `with_move_priority`.

## Results (MV1)

| move | priority |
|---|---|
| Follow Me | 2 |
| Extreme Speed | 2 |
| Aqua Jet | 1 |

## Tests

`test_move_priority.py` — 5 passed. Shows raw arm omits priority; dispatch adds it; not_found unchanged.

## Registration

- Field `priority` is tool-determined from the static pin (no LLM).
- Pin: `data/moves/static.v1.json`.
- Prompt draft (Part 5): mention that `get_move_static` also returns `priority`.
