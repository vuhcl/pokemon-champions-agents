# H11 drift: exclude battle-only transient formes in find_species

## Why the H11 key excludes Castform-Rainy

The frozen acceptance is `{Gyarados, Pelipper, Quaquaval}` (+ Mega as deliberate FP). That is **not** a separate key-builder filter for Castform. Product team-building already drops battle-only automatic formes via:

`recommender/slot_fill.py` → `_is_battle_only_transient_forme(sid, entry, regulation)`

Path: forme with `base_species_id` set **and** zero rows in both `ingame_species_map` and `showdown_species_map` for the active regulation. Confirmed cases: Castform weather formes, Terapagos-Stellar, Zygarde-Complete. Player-chosen formes with usage (e.g. Rotom-Wash) are kept.

## Fix

`find_species` now calls the **same** helper (reuse, no new rule). `prompt.md` unchanged → proposed sha stays **`bd2b69cd…`**. Tool description text in `STATE_TOOL_SPECS` also left unchanged (implementation detail aligned with slot_fill).

## Old → new result sets

| query | old | new |
|---|---|---|
| H11 Water+Hurricane | Castform-Rainy, Gyarados, Gyarados-Mega, Pelipper, Quaquaval | Gyarados, Gyarados-Mega, Pelipper, Quaquaval |
| HU1 Fire bulk ≥350 no Mega | Arcanine-Hisui, Armarouge, Emboar, Incineroar, Skeledirge, Torkoal | **unchanged** |
| H19 Trick Room learners | n=63 | n=60 (dropped Meowstic-F, Polteageist-Antique, Sinistcha-Masterpiece — same helper, zero-usage forme rows) |
| H20 Water pool no Mega | n=33 incl. Castform-Rainy | n=32 |
| Prankster+Sunny Day / Prankster weather key | 6 species, no transients | **unchanged**; key==find_species union still holds |

No other transient formes in HU1 or Prankster outputs.
