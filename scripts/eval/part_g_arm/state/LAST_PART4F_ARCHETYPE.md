# 4f — archetype tools

## Spec

| tool | behavior |
|---|---|
| `change_archetype(components[])` | `handle_archetype_change`; refuses if reconcile would mutate draft; rain audit |
| `read_archetype()` | components + locked |

## Rain conflict audit (MS5)

Data: `ABILITY_TO_FIELD` (non-Rain weather abilities) + `CHARGE_INSTANT_WEATHER` (sun-charged moves e.g. Solar Beam). Pelipper/Drizzle not flagged. Locked slots unchanged.

## Calc

`reconcile_on_archetype_change` may call calc via `check_archetype_fit` (localhost). No live web. No bootstrap LLM.

## Tests

`test_archetype_tools.py` — 2 passed (MS5 fixture).

Prompt draft (Part 5): tool descriptions above.
