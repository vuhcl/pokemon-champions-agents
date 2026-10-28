# find_species + Prankster weather key (2026-10-27)

## Tool

`find_species(types?, learns_move?, ability?, stat_formula?, include_formes?=true, n?)` — read-only AND filters over legality-snapshot legal species. No LLM, no network. Wired in `tools.py` / `harness.py`; in `READONLY_TOOL_NAMES`.

## Prankster ∩ weather key (BEFORE model eev)

| field | value |
|---|---|
| artifact | `dev_keys_prankster_weather.json` |
| sha256 | `cbef455d7ff1610152f64fc17ad5e33796e82fd05669a8fca93d8b0fa47652d3` |
| builder | `build_prankster_weather_key.py` |
| count | **6** (in band; not empty, ≤25) |

**Weather list source:** `recommender.move_narrowing.WEATHER_SETTING_MOVES` (`_WEATHER_MANUAL`) — Python constant, **not** a JSON pin field. Snapshot/`static.v1.json` have no `weather` field. Scope = all five map entries (Rain Dance, Sunny Day, Sandstorm, Snowscape, Chilly Reception). All Status; no conditional setters. Aurora Veil excluded.

**Species set:** Banette-Mega (mega), Klefki, Liepard, Meowstic (base; Meowstic-F lacks Prankster), Sableye (base; Sableye-Mega is Magic Bounce), Whimsicott.

**Per-move Prankster legal counts:** raindance 5, sunnyday 6, sandstorm 1, snowscape 0, chillyreception 0.

## Reference trajectory

Five `find_species(ability=Prankster, learns_move=<Name>)` calls → union == key; `mechanical_class` = `lookup only`; SERVED class match via `score_turn`. See `test_prankster_weather_key.py`.

## Hand map

H11 / H19 (learnset half) / H20 / HU1 GAP lines cleared in `reference_trajectories.py`. H19 compendium-role TR setters remain hand/checklist when not learnset-equivalent.

## Prompt / eev

Prompt revision (factual `find_species` blurb only — **no** weather-move list) and full eev are a **later** commit after this key sha is on disk.
