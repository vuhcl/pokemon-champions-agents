# 4b — structured constraint tools

## Spec (as built)

| tool | wraps | notes |
|---|---|---|
| `add_constraint(predicate, scope, groundedness, slot?, mechanical_kind?, value?)` | `build_constraint` via `record_constraint` | `value` → `mechanical_value`. Default hardness=`hard`. Optional 1-based `slot` prefixes predicate (`slot N …`) for echo; product `Constraint` has **no** `slot_index`. |
| `read_constraints()` | state read | Returns predicate, type, scope, groundedness, still_active, mechanical_kind/value, optional `slot` parsed from predicate. |
| `restore_constraint()` | `nodes.restore_constraint` | True-swap of newest `constraints_superseded` entry; empty log → refuse. |

Not building: draft-condition store (SC1/SC3).

## Mechanical kinds that exist

`type` | `ability` | `item` | `no_duplicate_items`.

**MS6:** `mechanical_kind=type`, `value=Water`, `scope=per_slot`, `slot=1` → mechanical Water; echo `slot 1 Water`.

**MT3 / HC2 (real path):** no ban-ability / ban-weather kind. Record as `groundedness=judgment-only` with predicates `No Intimidate.` / `No weather.` (seeds keep `no_intimidate` / `no_weather_ability`).

## Scoring

`mechanical_class`: constraint-list change → **`recorded`** (MUTATION-OK accepts it).

## Tests

`test_constraint_tools.py` — 7 passed.

## Dev rows (keys first)

| id | call | key |
|---|---|---|
| dev-ms6-water | add Water type slot 1 | MUTATION-OK; mechanical type=Water; read echoes slot 1 |
| dev-mt3-intimidate | judgment-only No Intimidate | MUTATION-OK; mechanical null |
| dev-restore-type | Fire then Water then restore | MUTATION-OK; Fire active again |

## Reference trajectories

MS6 closed. Part 3 now **39/42** pass, **3** gaps (OL1, OL2a, OL3 — not in Part 4 build list).

Prompt description draft (Part 5): same as tool spec descriptions above.
