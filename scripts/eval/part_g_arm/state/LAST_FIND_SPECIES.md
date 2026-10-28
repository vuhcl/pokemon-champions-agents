# find_species + Prankster weather key (2026-10-27)

## Tool

`find_species(types?, learns_move?, ability?, stat_formula?, include_formes?=true, n?)` — read-only AND filters over legality-snapshot legal species. No LLM, no network. Wired in `tools.py` / `harness.py`; in `READONLY_TOOL_NAMES`.

## Prankster ∩ weather key (BEFORE model eev)

| field | value |
|---|---|
| artifact | `dev_keys_prankster_weather.json` |
| sha256 | `6dba1caac2d45135779779f7867f6f442163bdb3fef35ca6270d7c76329fb543` |
| prior (circular builder) | `cbef455d7ff1610152f64fc17ad5e33796e82fd05669a8fca93d8b0fa47652d3` |
| builder | `build_prankster_weather_key.py` (legality only; **no** `find_species` import) |
| count | **6** (in band; not empty, ≤25) |

**Weather list source:** `recommender.move_narrowing.WEATHER_SETTING_MOVES` (`_WEATHER_MANUAL`) — Python constant, **not** a JSON pin field. Snapshot/`static.v1.json` have no `weather` field. Scope = all five map entries (Rain Dance, Sunny Day, Sandstorm, Snowscape, Chilly Reception). All Status; no conditional setters. Aurora Veil excluded.

**Species set:** Banette-Mega (mega), Klefki, Liepard, Meowstic (base; Meowstic-F lacks Prankster), Sableye (base; Sableye-Mega is Magic Bounce), Whimsicott.

**Per-move Prankster legal counts:** raindance 5, sunnyday 6, sandstorm 1, snowscape 0, chillyreception 0.

## Reference trajectory

Five `find_species(ability=Prankster, learns_move=<Name>)` calls → union == key; `mechanical_class` = `lookup only`; SERVED class match via `score_turn`. See `test_prankster_weather_key.py`.

## Hand map

H11 / H19 (learnset half) / H20 / HU1 GAP lines cleared in `reference_trajectories.py`. H19 compendium-role TR setters remain hand/checklist when not learnset-equivalent.

## Prompt / eev (after key sha on disk)

| field | value |
|---|---|
| prompt sha256 | `bd2b69cde151fdb4dd2431c294ca46f4fbc251f54cebd82a13844d4eba0aaf86` |
| transcript | `/Users/nowaki027/part-g-arm-state-out-find-species/` |
| eev | **40/41** |

Ordinary rows `dev-fs-types-move`, `dev-fs-stat-bulk`, `dev-fs-formes`: pass (class + tool called).

### `dev-fs-prankster-weather` finding (not a prompt tune)

- **Class:** `lookup only` (pass).
- **Set:** fail. Named `{Banette, Banette-Mega, Grimmsnarl, Klefki, Liepard, Meowstic, Sableye, Whimsicott}` ≠ key of 6. Banette (base) and Grimmsnarl are out-of-key; Banette also lacked a `find_species` hit.
- **Calls:** 25 (>16 limit). One `find_species(ability=Prankster)` with no `learns_move`, then 24× `check_learnset`. **Omitted all five** weather moves on `find_species` (omission note; set still full-key).
- Model did not derive the weather-move list from tools alone. Per plan: report as eev finding; **no** weather list in prompt and **no** weather-enum tool without Vu.

## Prompt / eev (historical)

Key sha was committed in `f1aa0ec` before this prompt revision.
