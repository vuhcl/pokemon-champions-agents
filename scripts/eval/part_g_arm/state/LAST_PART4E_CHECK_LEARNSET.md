# 4e — check_learnset

## Spec

`check_learnset(species, move)` — read-only via `legal_moves_for` / `resolve_learnset`. No new rule. Does not write state.

## Results

| case | learns |
|---|---|
| Archaludon + Snarl (SC1 learnable half) | true |
| Archaludon + Soak (SC2) | false |
| Venusaur + Sludge Bomb (dev) | true |

## Tests

`test_check_learnset.py` — 4 passed.

Prompt draft (Part 5): tool description above.
