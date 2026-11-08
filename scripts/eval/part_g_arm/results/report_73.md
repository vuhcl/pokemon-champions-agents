# Follow-up 73 — #367 / #368 arm tools (`ix_tools_v1`)

Branch `fu73-ix-tools` from main. Flag `ix_tools_v1` default **off**. No frozen keys edited. No arm run / grade.

## What shipped

| Piece | Path |
|---|---|
| Move/item description extract | `scripts/extract_descriptions/extract_move_item_descriptions.py` |
| Pinned JSON | `data/moves/descriptions.v1.json`, `data/items/descriptions.v1.json` |
| Drift test | `tests/recommender/test_description_drift.py` |
| Tools | `scripts/eval/part_g_arm/state/ix_tools.py` (`find_by_effect`, `get_type_effectiveness`) |
| Flag + schema wire | `tools.py` `set_ix_tools_v1` / `combined_specs`; `harness.py` dispatch; `guard_allowed.py` CORE |
| Acceptance tests | `tests/recommender/test_ix_tools_v1.py` |
| Isolation | `test_cli_layer_arm_isolation.py` + `combined_specs_flag_off` golden (from main, prior keys unchanged) |

## #367 flags (derived only)

| Flag | Deriving field |
|---|---|
| `redirection` | `flags.v1.json` `volatileStatus ∈ {followme, ragepowder}` |
| `pivot` | `flags.v1.json` `selfSwitch` truthy |
| `phazing` | `flags.v1.json` `forceSwitch` truthy |
| `protection` | `flags.v1.json` `stallingMove` truthy |

**Not included (no Vu approval / (b) fails):** `priority` (`static.v1.json` `priority ≠ 0` has no single description phrase covering the full set), `speed control` (no deriving field).

**Keyword kinds:** move + item (Showdown text JSON) and ability (`all.v1.json`). Tool `source` labels Showdown text as not in-game.

**Canonical phrases (test b) + known near-miss extras (test c):**

| Flag | Phrase | Extras beyond flag set |
|---|---|---|
| redirection | `redirected` | Dragon Darts, Snipe Shot |
| pivot | `party` | Aurora Veil, Beat Up, Heal Bell, Healing Wish, Last Respects, Light Screen, Quick Guard, Reflect, Roar, Safeguard, Tailwind, Toxic Spikes, Whirlwind, Wide Guard |
| phazing | `Forces the target to switch` | (none) |
| protection | `protect` | Copycat, Feint, Phantom Force, Quick Guard, Stomping Tantrum, Temper Flare, Wide Guard |

`matched_by`: `flag` \| `description` \| `both`. Flag-first ranking. Word-boundary keyword. Aliases in `FLAG_ALIASES` (e.g. drag → phazing).

## #368

- New tool `get_type_effectiveness` (not a `get_typing` extension).
- Reads the same `scripts/eval/part_g_v4/key_artifacts/type_chart.v1.json` the eval uses (identity test).
- Champions `Generations.get(0)` vs gen9: **0 diffs** on the 18 types; tool still binds the Champions extract.
- Ground `no_damage` = `{Flying}` only. Levitate / Telepathy / Earth Eater are ability keyword facts via #367.

## Graded rows that would use these tools

| Row | Tool(s) | Notes |
|---|---|---|
| IX1 | `find_by_effect` (redirection) + existing `get_move_static` | Fake Out priority vs Follow Me / Rage Powder class |
| IX5 | `find_by_effect` (keyword Intimidate, kind=ability) + `find_species` | Arm buckets; key does not fix membership |
| IX7 | `get_type_effectiveness` (Ground) + `find_by_effect` (ability keywords) + `find_species` | Type half = Flying; ability half = Levitate / Telepathy / Earth Eater via keyword |

No other request-set rows are required to call these tools today; any “what resists X / what redirects” ASSUME-STATE lookup can use them once keys are re-cut (FU74+).

## Schema token cost (tiktoken cl100k_base)

| Surface | Tools | Tokens | Δ vs flag-off same surface |
|---|---:|---:|---:|
| All ladder flags off | 34 → 36 | 3767 → 4016 | +249 |
| `tool_fields+wrapper+draft` (guard surface) | 41 → 43 | 4902 → 5151 | +249 |

New configuration beside registered rungs — not part of them.

## Isolation

`test_cli_layer_arm_isolation.py`: all prior golden hashes unchanged; added `combined_specs_flag_off` hashed from main with `ix_tools_v1` off. Flag-off schema omits both new tools.

## Could not do / disagrees with repo

1. **`priority` / `speed control` flags** not shipped — no covering description phrase for (b), and speed control has no pinned deriving field.
2. **Pivot canonical phrase is `party`** — the only single token that covers all `selfSwitch` members including Revival Blessing / Shed Tail; player queries should use alias `pivot` / `self switch`, not the phrase.
3. **Intimidate-punish is not a curated flag** (per Vu) — keyword path only; Mirror Armor / Competitive may be absent from an `"Intimidate"` keyword hit if their descriptions do not contain that word (arm buckets).
4. Description extract is **verbatim Showdown text**, not Champions in-game copy; overrides stay on `describe`, not on this search index.
