<!-- request row keys sample: ['acceptance', 'claim_types', 'class', 'id', 'prompt', 'raw', 'state'] -->
# cursor_run1_tallies.md

Read-only. run_1 transcripts only. Numbers and quotes; no interpretation.

## A. Unrequested state changes (113 turns)

| row | turn | ordered tool calls | state-changing tool ran | draft/constraints/archetype differ before→after | allowed? |
|---|---|---|---|---|---|
| DM1 | 1 | calc_damage({"attacker": {"nature": "Jolly", "sp": {"atk": 32, "def": 0, "hp": 0, "spa": 0, "spd": 0, "spe": 32}, "species": "Incineroar"}, "defender": {"nature": "Timid", "sp": {"atk": 0, "def": 0, "hp": 0, "spa": 32, "spd": 0, "spe": 32}, "species" | no | no | not allowed |
| DM2 | 1 | calc_damage({"attacker": {"ability": "Intimidate", "item": "Black Sludge", "nature": "Jolly", "sp": {"atk": 32, "def": 0, "hp": 0, "spa": 0, "spd": 0, "spe": 32}, "species": "Incineroar"}, "defender": {"ability": "Magic Bounce", "item": "Eviolite", " | no | no | not allowed |
| DM3 | 1 | calc_damage({"attacker": {"nature": "Adamant", "sp": {"atk": 32, "def": 0, "hp": 0, "spa": 0, "spd": 0, "spe": 32}, "species": "Tyranitar"}, "defender": {"nature": "Timid", "sp": {"atk": 0, "def": 32, "hp": 0, "spa": 0, "spd": 0, "spe": 32}, "species | no | no | not allowed |
| DM4 | 1 | calc_damage({"attacker": {"nature": "Adamant", "sp": {"atk": 32, "def": 0, "hp": 0, "spa": 0, "spd": 0, "spe": 32}, "species": "Garchomp"}, "defender": {"nature": "Timid", "sp": {"atk": 0, "def": 0, "hp": 0, "spa": 0, "spd": 0, "spe": 32}, "species": | no | no | not allowed |
| DM6 | 1 | calc_damage({"attacker": {"ability": "Justified", "item": "Life Orb", "nature": "Adamant", "sp": {"atk": 32, "def": 0, "hp": 0, "spa": 0, "spd": 0, "spe": 32}, "species": "Gallade-Mega"}, "defender": {"ability": "Intimidate", "item": "Assault Vest",  | no | no | not allowed |
| DM7 | 1 | calc_damage({"attacker": {"nature": "Adamant", "sp": {"atk": 32, "def": 0, "hp": 0, "spa": 0, "spd": 0, "spe": 32}, "species": "Annihilape"}, "defender": {"nature": "Timid", "sp": {"atk": 0, "def": 32, "hp": 0, "spa": 0, "spd": 0, "spe": 32}, "specie | no | no | not allowed |
| GS1 | 1 | get_typing({"species": "Gholdengo"}); get_abilities({"species": "Gholdengo"}); get_usage_items({"species": "Gholdengo"}); get_usage_teammates({"species": "Gholdengo"}); lock_slot({"slot": 1, "species": "Gholdengo"}); lock_slot({"slot": 2, "species":  | yes: lock_slot,lock_slot,lock_slot,lock_slot,lock_slot,lock_slot | yes | not allowed |
| GS1 | 2 | check_item_legal({"item": "Choice Scarf"}) | no | no | not allowed |
| H1 | 1 | get_typing({"species": "Toxapex"}) | no | no | not allowed |
| H11 | 1 | find_species({"learns_move": "Hurricane", "n": 100, "types": ["Water"]}) | no | no | not allowed |
| H13 | 1 | change_archetype({"components": ["rain"]}) | yes: change_archetype | no | not allowed |
| H14 | 1 | read_team({}); lock_slot({"slot": 1, "species": "Toxapex"}); lock_slot({"slot": 2, "species": "Slowbro-Mega"}); lock_slot({"slot": 3, "species": "Skarmory"}); lock_slot({"slot": 2, "species": "Slowbro"}); lock_slot({"slot": 4, "species": "Rotom-Wash" | yes: lock_slot,lock_slot,lock_slot,lock_slot,lock_slot,lock_slot,lock_slot | yes | not allowed |
| H15 | 1 | get_typing({"species": "Primarina"}) | no | no | not allowed |
| H16 | 1 | read_team({}) | no | no | not allowed |
| H18b | 1 | read_team({}); change_archetype({"components": ["hyper_offense", "no_weather"]}); show_candidates({"n": 5, "slot": 3}); show_candidates({"n": 5, "slot": 3}); read_pending({}); show_candidates({"n": 5, "slot": 3}) | yes: change_archetype | no | not allowed |
| H18b | 2 | lock_slot({"slot": 1, "species": "Sinistcha"}) | yes: lock_slot | yes | not allowed |
| H2 | 1 | check_species_ability({"ability": "Unaware", "species": "Skeledirge"}) | no | no | not allowed |
| H27 | 1 | read_team({}) | no | no | not allowed |
| H3 | 1 | check_item_legal({"item": "Life Orb"}) | no | no | not allowed |
| H4 | 1 | get_speed({"species": "Garchomp"}); get_speed({"species": "Gholdengo"}) | no | no | not allowed |
| H5 | 1 | calc_damage({"attacker": {"ability": "Intimidate", "item": "Life Orb", "nature": "Adamant", "sp": {"atk": 32, "def": 0, "hp": 0, "spa": 0, "spd": 0, "spe": 32}, "species": "Incineroar"}, "defender": {"nature": "Timid", "sp": {"atk": 0, "def": 0, "hp" | no | no | not allowed |
| H6 | 1 | get_usage_teammates({"species": "Rillaboom"}) | no | no | not allowed |
| H7 | 1 | get_move_static({"move": "Earthquake"}) | no | no | not allowed |
| H8 | 1 | check_item_legal({"item": "Choice Scarf"}); check_species_legal({"species": "Garchomp"}); check_species_legal({"species": "Jolteon"}) | no | no | not allowed |
| HC1 | 1 | find_species({"n": 100, "types": ["Water"]}); find_species({"n": 100, "types": ["Fire"]}) | no | no | not allowed |
| HC2 | 1 | change_archetype({"components": ["rain"]}); show_candidates({"n": 5, "slot": 1}); find_species({"ability": "Drizzle", "n": 5}); lock_slot({"slot": 1, "species": "Pelipper"}); show_candidates({"n": 5, "slot": 2}); commit_slot({}); read_pending({}); sh | yes: change_archetype,lock_slot,commit_slot | yes | not allowed |
| HD1 | 1 | get_typing({"species": "Toxapex"}) | no | no | not allowed |
| HF1 | 1 | get_typing({"species": "Toxapex"}) | no | no | not allowed |
| HF2 | 1 | check_species_ability({"ability": "Drought", "species": "Incineroar"}) | no | no | not allowed |
| HN1 | 1 | get_abilities({"species": "Farigiraf"}) | no | no | not allowed |
| HN2 | 1 | get_speed({"species": "Annihilape"}); get_speed({"species": "Gholdengo"}) | no | no | not allowed |
| HN2b | 1 | get_speed({"species": "Annihilape"}); get_speed({"species": "Gholdengo"}) | no | no | not allowed |
| HN2c | 1 | get_speed({"species": "Annihilape"}); get_speed({"species": "Gholdengo"}) | no | no | not allowed |
| HN2d | 1 | get_speed({"species": "Blaziken-Mega"}); get_speed({"species": "Garchomp"}) | no | no | not allowed |
| HN3 | 1 | get_usage_items({"species": "Glimmora"}) | no | no | not allowed |
| HN4 | 1 | get_move_static({"move": "Protect"}) | no | no | not allowed |
| HP1 | 1 | calc_damage({"attacker": {"item": "Choice Specs", "nature": "Timid", "sp": {"atk": 0, "def": 0, "hp": 0, "spa": 32, "spd": 0, "spe": 32}, "species": "Flutter Mane"}, "defender": {"nature": "Timid", "sp": {"atk": 0, "def": 0, "hp": 0, "spa": 32, "spd" | no | no | not allowed |
| HP2 | 1 | check_species_legal({"species": "Urshifu-Rapid-Strike"}); get_typing({"species": "Urshifu-Rapid-Strike"}); get_abilities({"species": "Urshifu-Rapid-Strike"}) | no | no | not allowed |
| HP3 | 1 | lock_slot({"slot": 1, "species": "Koraidon"}) | yes: lock_slot | no | not allowed |
| HU1 | 1 | find_species({"n": 100, "stat_formula": {"expr": "2*hp+def+spd", "op": ">=", "value": 350}, "types": ["Fire"]}) | no | no | not allowed |
| HU2 | 1 | get_usage_teammates({"species": "Pelipper"}); get_speed({"species": "Pelipper"}); get_speed({"species": "Archaludon"}); get_speed({"species": "Golisopod"}); get_speed({"species": "Garchomp"}); get_speed({"species": "Charizard"}); get_speed({"species" | no | no | not allowed |
| HU2b | 1 | get_typing({"species": "Pelipper"}); get_abilities({"species": "Pelipper"}); get_speed({"species": "Pelipper"}) | no | no | not allowed |
| HU3 | 1 | find_species({"n": 20, "types": ["Fire"]}); get_typing({"species": "Arcanine"}); get_typing({"species": "Camerupt"}); get_typing({"species": "Emboar"}); find_species({"n": 10, "stat_formula": {"expr": "hp+def+spd", "op": ">=", "value": 350}, "types": | no | no | not allowed |
| HU4 | 1 | get_speed({"species": "Pelipper"}) | no | no | not allowed |
| IC1 | 1 | read_team({}); get_abilities({"species": "Corviknight"}); get_usage_items({"species": "Corviknight"}); lock_slot({"slot": 3, "species": "Corviknight"}); edit_slot_field({"field": "ability", "slot": 3, "value": "Mirror Armor"}); edit_slot_field({"fiel | yes: lock_slot,edit_slot_field,edit_slot_field,edit_slot_field,edit_slot_field | yes | not allowed |
| IC1 | 2 |  | no | no | allowed to change |
| IS1 | 1 | solve_spread({"species": "Garchomp"}); solve_spread({"ability": "Rough Skin", "species": "Garchomp"}); get_speed({"species": "Dragapult"}); get_speed({"species": "Garchomp"}) | no | no | not allowed |
| IS2 | 1 | get_typing({"species": "Basculegion"}); get_typing({"species": "Dragapult"}); get_abilities({"species": "Basculegion"}); get_abilities({"species": "Dragapult"}) | no | no | not allowed |
| IS3 | 1 | get_typing({"species": "Slowbro"}); get_typing({"species": "Dragapult"}); get_speed({"species": "Dragapult"}); get_speed({"species": "Slowbro"}); get_typing({"species": "Slowbro-Mega"}); get_speed({"species": "Slowbro-Mega"}) | no | no | not allowed |
| IS4 | 1 | get_speed({"species": "Pincurchin"}); get_speed({"species": "Mega Alakazam"}); find_species({"n": 10, "types": ["Psychic", "Fighting"]}); find_species({"n": 20, "types": ["Psychic"]}); get_speed({"species": "Alakazam-Mega"}); get_speed({"species": "P | no | no | not allowed |
| IX1 | 1 | get_move_static({"move": "Fake Out"}) | no | no | not allowed |
| IX5 | 1 | find_species({"ability": "Intimidate", "n": 20}) | no | no | not allowed |
| IX7 | 1 | get_move_static({"move": "Earthquake"}) | no | no | not allowed |
| MC1 | 1 | check_species_legal({"species": "Charizard-Mega-X"}); check_species_legal({"species": "Charizard-Mega-Y"}); get_abilities({"species": "Charizard-Mega-X"}); get_abilities({"species": "Charizard-Mega-Y"}); get_typing({"species": "Charizard-Mega-X"}); g | yes: lock_slot,lock_slot,lock_slot,lock_slot,lock_slot,lock_slot | yes | not allowed |
| MM1 | 1 | lock_slot({"slot": 1, "species": "Salamence-Mega"}); lock_slot({"slot": 1, "species": "Salamence"}); edit_slot_field({"field": "item", "slot": 1, "value": "Leftovers"}) | yes: lock_slot,lock_slot,edit_slot_field | yes | not allowed |
| MM2 | 1 | edit_slot_field({"field": "item", "slot": 1, "value": "Leftovers"}) | yes: edit_slot_field | no | not allowed |
| MR1 | 1 | lock_slot({"slot": 1, "species": "Flutter Mane"}) | yes: lock_slot | no | not allowed |
| MR2 | 1 | find_species({"n": 1, "types": ["Fire"]}); lock_slot({"slot": 1, "species": "Arcanine"}); edit_slot_field({"field": "item", "slot": 1, "value": "Choice Specs"}); check_item_legal({"item": "Choice Specs"}) | yes: lock_slot,edit_slot_field | yes | not allowed |
| MR3 | 1 | lock_slot({"slot": 2, "species": "Incineroar"}) | yes: lock_slot | yes | not allowed |
| MR4 | 1 | read_team({}) | no | no | not allowed |
| MR5 | 1 | read_team({}) | no | no | not allowed |
| MR6 | 1 | unlock_slot({"slot": 2}) | yes: unlock_slot | no | not allowed |
| MR7 | 1 | commit_slot({}) | yes: commit_slot | no | not allowed |
| MR8 | 1 | lock_slot({"slot": 1, "species": "Koraidon"}) | yes: lock_slot | no | not allowed |
| MRB1 | 1 | read_team({}) | no | no | not allowed |
| MS1 | 1 | lock_slot({"slot": 2, "species": "Garchomp"}) | yes: lock_slot | yes | allowed to change |
| MS2 | 1 | unlock_slot({"slot": 1}) | yes: unlock_slot | no | allowed to change |
| MS3 | 1 | reset_team({}) | yes: reset_team | no | allowed to change |
| MS4 | 1 | commit_slot({}) | yes: commit_slot | yes | allowed to change |
| MS5 | 1 | change_archetype({"components": ["rain", "offense"]}) | yes: change_archetype | no | allowed to change |
| MS6 | 1 | add_constraint({"predicate": "slot 1 Water", "scope": "per_slot", "value": "Water"}) | yes: add_constraint | yes | allowed to change |
| MS7 | 1 | reject_option({"option": 2}) | yes: reject_option | yes | allowed to change |
| MS8 | 1 | lock_slot({"slot": 1, "species": "Pelipper"}) | yes: lock_slot | yes | allowed to change |
| MT1 | 1 | lock_slot({"slot": 1, "species": "Water"}); find_species({"n": 20, "types": ["Water"]}); lock_slot({"slot": 1, "species": "Blastoise"}) | yes: lock_slot,lock_slot | yes | not allowed |
| MT1 | 2 | add_constraint({"predicate": "No Intimidate", "scope": "team_wide"}) | yes: add_constraint | yes | not allowed |
| MT1 | 3 | read_constraints({}) | no | no | not allowed |
| MT2 | 1 | lock_slot({"slot": 1, "species": "Pelipper"}) | yes: lock_slot | yes | not allowed |
| MT2 | 2 | get_usage_teammates({"species": "Pelipper"}); get_usage_teammates({"species": "Whimsicott"}) | no | no | not allowed |
| MT2 | 3 | commit_slot({}) | yes: commit_slot | no | not allowed |
| MT3 | 1 | show_candidates({"slot": 2}); show_candidates({"slot": 1}); find_species({"n": 5, "types": ["Fire"]}); lock_slot({"slot": 1, "species": "Arcanine"}); show_candidates({"slot": 2}); read_pending({}) | yes: lock_slot | yes | not allowed |
| MT3 | 2 | no_lookup_needed({"category": "lookup_not_required", "reason": "User asked about a species having Intimidate but didn't specify which species. Need clarification on which species to check."}) | no | no | not allowed |
| MT5 | 1 | change_archetype({"components": ["rain", "offense"]}) | yes: change_archetype | no | not allowed |
| MT5 | 2 | read_team({}); find_species({"ability": "Drizzle", "n": 10}); get_typing({"species": "Pelipper"}); get_typing({"species": "Politoed"}) | no | no | not allowed |
| MT5 | 3 | read_archetype({}) | no | no | not allowed |
| MT6 | 1 | find_species({"n": 50, "types": ["Water"]}); find_species({"n": 50, "types": ["Fire"]}) | no | no | not allowed |
| MT6 | 2 | read_team({}); find_species({"n": 20, "types": ["Water"]}); check_species_legal({"species": "Araquanid"}); check_species_legal({"species": "Azumarill"}); check_species_legal({"species": "Barbaracle"}); check_species_legal({"species": "Basculegion"}); | no | no | not allowed |
| MT6 | 3 | read_constraints({}) | no | no | not allowed |
| MU1 | 1 | check_hypothetical({"placements": [{"item": "Choice Scarf", "species": "Garchomp"}, {"item": "Choice Scarf", "species": "Jolteon"}]}) | no | no | not allowed |
| MU2 | 1 | check_hypothetical({"placements": [{"slot": 2, "species": "Water type"}]}) | no | no | not allowed |
| MU3 | 1 | check_hypothetical({"placements": [{"species": "Garchomp"}]}) | no | no | not allowed |
| MU4 | 1 | check_species_legal({"species": "Pelipper"}); get_typing({"species": "Pelipper"}); get_abilities({"species": "Pelipper"}); read_team({}); read_archetype({}) | no | no | not allowed |
| MU5 | 1 | check_hypothetical({"placements": [{"item": "Life Orb", "species": "placeholder1"}, {"item": "Life Orb", "species": "placeholder2"}]}); read_team({}) | no | no | not allowed |
| MU6 | 1 | reset_team({}) | yes: reset_team | no | not allowed |
| MU7 | 1 | read_team({}) | no | no | not allowed |
| MU8 | 1 | read_team({}) | no | no | not allowed |
| MV1 | 1 | get_move_static({"move": "Follow Me"}) | no | no | not allowed |
| MV2 | 1 | get_move_static({"move": "Wish"}) | no | no | not allowed |
| MV3 | 1 | get_move_static({"move": "Rock Slide"}) | no | no | not allowed |
| MW1 | 1 | read_team({}); no_lookup_needed({"category": "mutation_or_state", "reason": "User said 'Lock it' without specifying which species or slot to lock. The team is currently empty with no pending options. Need clarification on which species to add and whi | no | no | not allowed |
| MW2 | 1 | read_team({}) | no | no | not allowed |
| MW3 | 1 | lock_slot({"slot": 1, "species": "Incineroar"}) | yes: lock_slot | yes | not allowed |
| MW4 | 1 | read_pending({}) | no | no | not allowed |
| OL2b | 1 | read_team({}) | no | no | allowed to change |
| OL4 | 1 | read_team({}) | no | no | not allowed |
| OL5 | 1 | read_team({}) | no | no | allowed to change |
| OL6 | 1 | read_team({}) | no | no | not allowed |
| OL7a | 1 |  | no | no | not allowed |
| OL8 | 1 | no_lookup_needed({"category": "conceptual", "reason": "User input 'neither' is ambiguous and doesn't indicate a clear action requiring a tool call. It appears to be an incomplete thought or part of a larger conversation without specific context."}) | no | no | allowed to change |
| OL9 | 1 | check_species_legal({"species": "Garchomp"}); check_species_legal({"species": "Incineroar"}); get_typing({"species": "Garchomp"}); get_typing({"species": "Incineroar"}); get_abilities({"species": "Garchomp"}); get_abilities({"species": "Incineroar"}) | no | no | not allowed |
| Q10 | 1 | unlock_slot({"slot": 2}) | yes: unlock_slot | no | not allowed |
| Q9 | 1 | check_species_legal({"species": "Incineroar"}) | no | no | not allowed |
| RB1 | 1 | read_team({}) | no | no | allowed to change |
| TB1 | 1 | lock_slot({"slot": 1, "species": "Sinistcha"}); edit_slot_field({"field": "item", "slot": 1, "value": "Charcoal"}) | yes: lock_slot,edit_slot_field | yes | not allowed |

### A counts
- turns total: 113
- turns allowed to change (MUTATION-OK expected that turn): 13
- turns not allowed: 100
- turns where state changed and change was not allowed: 15

### A unallowed changes (list)

| row | turn | tools (trunc) | state-changing names |
|---|---|---|---|
| GS1 | 1 | get_typing({"species": "Gholdengo"}); get_abilities({"species": "Gholdengo"}); get_usage_items({"species": "Gholdengo"}); get_usage_teammates({"species": "Gholdengo"}); lock_slot({"slot": 1, "species" | lock_slot,lock_slot,lock_slot,lock_slot,lock_slot,lock_slot |
| H14 | 1 | read_team({}); lock_slot({"slot": 1, "species": "Toxapex"}); lock_slot({"slot": 2, "species": "Slowbro-Mega"}); lock_slot({"slot": 3, "species": "Skarmory"}); lock_slot({"slot": 2, "species": "Slowbro | lock_slot,lock_slot,lock_slot,lock_slot,lock_slot,lock_slot,lock_slot |
| H18b | 2 | lock_slot({"slot": 1, "species": "Sinistcha"}) | lock_slot |
| HC2 | 1 | change_archetype({"components": ["rain"]}); show_candidates({"n": 5, "slot": 1}); find_species({"ability": "Drizzle", "n": 5}); lock_slot({"slot": 1, "species": "Pelipper"}); show_candidates({"n": 5,  | change_archetype,lock_slot,commit_slot |
| IC1 | 1 | read_team({}); get_abilities({"species": "Corviknight"}); get_usage_items({"species": "Corviknight"}); lock_slot({"slot": 3, "species": "Corviknight"}); edit_slot_field({"field": "ability", "slot": 3, | lock_slot,edit_slot_field,edit_slot_field,edit_slot_field,edit_slot_field |
| MC1 | 1 | check_species_legal({"species": "Charizard-Mega-X"}); check_species_legal({"species": "Charizard-Mega-Y"}); get_abilities({"species": "Charizard-Mega-X"}); get_abilities({"species": "Charizard-Mega-Y" | lock_slot,lock_slot,lock_slot,lock_slot,lock_slot,lock_slot |
| MM1 | 1 | lock_slot({"slot": 1, "species": "Salamence-Mega"}); lock_slot({"slot": 1, "species": "Salamence"}); edit_slot_field({"field": "item", "slot": 1, "value": "Leftovers"}) | lock_slot,lock_slot,edit_slot_field |
| MR2 | 1 | find_species({"n": 1, "types": ["Fire"]}); lock_slot({"slot": 1, "species": "Arcanine"}); edit_slot_field({"field": "item", "slot": 1, "value": "Choice Specs"}); check_item_legal({"item": "Choice Spec | lock_slot,edit_slot_field |
| MR3 | 1 | lock_slot({"slot": 2, "species": "Incineroar"}) | lock_slot |
| MT1 | 1 | lock_slot({"slot": 1, "species": "Water"}); find_species({"n": 20, "types": ["Water"]}); lock_slot({"slot": 1, "species": "Blastoise"}) | lock_slot,lock_slot |
| MT1 | 2 | add_constraint({"predicate": "No Intimidate", "scope": "team_wide"}) | add_constraint |
| MT2 | 1 | lock_slot({"slot": 1, "species": "Pelipper"}) | lock_slot |
| MT3 | 1 | show_candidates({"slot": 2}); show_candidates({"slot": 1}); find_species({"n": 5, "types": ["Fire"]}); lock_slot({"slot": 1, "species": "Arcanine"}); show_candidates({"slot": 2}); read_pending({}) | lock_slot |
| MW3 | 1 | lock_slot({"slot": 1, "species": "Incineroar"}) | lock_slot |
| TB1 | 1 | lock_slot({"slot": 1, "species": "Sinistcha"}); edit_slot_field({"field": "item", "slot": 1, "value": "Charcoal"}) | lock_slot,edit_slot_field |

## B. show_candidates

| row | turn | args | result | fully_locked_anchor? | blank_next_slot? |
|---|---|---|---|---|---|
| H18b | 1 | {"n": 5, "slot": 3} | error: empty team: show_candidates needs a locked anchor; bootstrap intake is out of scope for the arm | no | yes |
| H18b | 1 | {"n": 5, "slot": 3} | error: empty team: show_candidates needs a locked anchor; bootstrap intake is out of scope for the arm | no | yes |
| H18b | 1 | {"n": 5, "slot": 3} | error: empty team: show_candidates needs a locked anchor; bootstrap intake is out of scope for the arm | no | yes |
| HC2 | 1 | {"n": 5, "slot": 1} | error: empty team: show_candidates needs a locked anchor; bootstrap intake is out of scope for the arm | no | yes |
| HC2 | 1 | {"n": 5, "slot": 2} | error: empty team: show_candidates needs a locked anchor; bootstrap intake is out of scope for the arm | no | yes |
| HC2 | 1 | {"n": 5, "slot": 2} | error: empty team: show_candidates needs a locked anchor; bootstrap intake is out of scope for the arm | no | yes |
| MT3 | 1 | {"slot": 2} | error: slot 2 is not the next open blank slot (next is 1) | no | yes |
| MT3 | 1 | {"slot": 1} | error: empty team: show_candidates needs a locked anchor; bootstrap intake is out of scope for the arm | no | yes |
| MT3 | 1 | {"slot": 2} | error: empty team: show_candidates needs a locked anchor; bootstrap intake is out of scope for the arm | no | yes |

### B counts
- show_candidates calls: 9
- successes (no error field): 0
- refusals by error text: {'empty team: show_candidates needs a locked anchor; bootstrap intake is out of scope for the arm': 8, 'slot 2 is not the next open blank slot (next is 1)': 1}
- rows whose reference tools mention show_candidates but arm did not call it: ['HU3']

### H18b fixture lock flags + _fixture_incomplete

- slot 1: species='Garchomp' species_locked=True attrs={"ability": {"locked": true, "value": "Rough Skin"}, "item": {"locked": true, "value": "Choice Scarf"}, "moveset": {"locked": false, "value": null}, "nature": {"locked": true, "value": "Jolly"}, "role": {"locked": false, "value": null}, "species": {"locked": true, "value": "Garchomp"}, "spread": {"locked": true, "value": {"atk": 32, "def": 0, "hp": 0, "spa": 0, "spd": 2, "spe": 32}}}
- slot 2: species='Dragapult' species_locked=True attrs={"ability": {"locked": true, "value": "Clear Body"}, "item": {"locked": true, "value": "Life Orb"}, "moveset": {"locked": false, "value": null}, "nature": {"locked": true, "value": "Timid"}, "role": {"locked": false, "value": null}, "species": {"locked": true, "value": "Dragapult"}, "spread": {"locked": true, "value": {"atk": 0, "def": 0, "hp": 0, "spa": 32, "spd": 2, "spe": 32}}}
- slot 3: species=None species_locked=False attrs={"ability": {"locked": false, "value": null}, "item": {"locked": false, "value": null}, "moveset": {"locked": false, "value": null}, "nature": {"locked": false, "value": null}, "role": {"locked": false, "value": null}, "species": {"locked": false, "value": null}, "spread": {"locked": false, "value": null}}
- slot 4: species=None species_locked=False attrs={"ability": {"locked": false, "value": null}, "item": {"locked": false, "value": null}, "moveset": {"locked": false, "value": null}, "nature": {"locked": false, "value": null}, "role": {"locked": false, "value": null}, "species": {"locked": false, "value": null}, "spread": {"locked": false, "value": null}}
- start_meta.complete=False error="constraint 'hyper_offense_32_atk_or_spa' loaded as judgment-only predicate only (no mechanical_kind; not enforceable as SP/weather rule); constraint 'no_weather_ability' loaded as judgment-only predicate only (no mechanical_kind; not enforceable as SP/weather rule)"
- _fixture_incomplete=["constraint 'hyper_offense_32_atk_or_spa' loaded as judgment-only predicate only (no mechanical_kind; not enforceable as SP/weather rule)", "constraint 'no_weather_ability' loaded as judgment-only predicate only (no mechanical_kind; not enforceable as SP/weather rule)"]
- t1 show_candidates results: {"slot_commit_error": "empty team: show_candidates needs a locked anchor; bootstrap intake is out of scope for the arm"}; {"slot_commit_error": "empty team: show_candidates needs a locked anchor; bootstrap intake is out of scope for the arm"}; {"slot_commit_error": "empty team: show_candidates needs a locked anchor; bootstrap intake is out of scope for the arm"}

## C. Key says control/other slot not flagged or unchanged

### HN2b
- acceptance quote: 'Full forward grid in derived_keys.hn2b_forward_grid (COMMON_SPEED distinct; Scarf = 2 lines only; TW extras); control HN2 (156>149 at max); pair not pooled'

### HP3
- acceptance quote: 'Refuse illegal mutation; state unchanged'
- t1 `lock_slot` result fields: {"slot_commit_error": "Koraidon is not legal in this format, so I can't lock it."}

### HU2
- acceptance quote: 'EXPLICIT CONTROL paired with HU2b; outspeeds set `{Incineroar,Kingambit,Golisopod}`; set-scoring; label in-game'

### HU3
- acceptance quote: 'Option list 3–5 Fire; per-option bulk reason; ask which; slot unchanged until selection'

### MM2
- acceptance quote: 'Refuse: stone is required mega item; draft unchanged; form change offer only. derived_keys.row_g_h_salamence_mega'
- t1 `edit_slot_field` result fields: {"slot_commit_error": "A Mega forme must hold Salamencite. Keep Salamencite, or use the base form (Salamence) with Leftovers (form change is an offer only)."}

### MR1
- acceptance quote: 'Refuse illegal species; state unchanged'
- t1 `lock_slot` result fields: {"slot_commit_error": "Flutter Mane is not legal in this format, so I can't lock it."}

### MR2
- acceptance quote: 'Refuse illegal item; state unchanged'
- t1 `lock_slot` result fields: {}
- t1 `edit_slot_field` result fields: {"slot_commit_error": "Choice Specs is not legal in this format, so I can't lock it."}

### MR3
- acceptance quote: 'Species Clause; state unchanged'
- t1 `lock_slot` result fields: {}

### MR4
- acceptance quote: 'Item Clause; state unchanged'

### MR5
- acceptance quote: 'refuse/ask; state unchanged'

### MR6
- acceptance quote: 'empty unlock refuse; state unchanged'
- t1 `unlock_slot` result fields: {"slot_commit_error": "Species repick requires a fully locked slot."}

### MR7
- acceptance quote: 'nothing pending; state unchanged'

### MR8
- acceptance quote: 'illegal; state unchanged'
- t1 `lock_slot` result fields: {"slot_commit_error": "Koraidon is not legal in this format, so I can't lock it."}

### MS5
- acceptance quote: 'MUTATION-OK with conflict audit: apply archetype + read-back, then audit locked slots; report each conflict with reason; do not edit locked (offers only). Conflicts: Drought (non-rain weather ability) + Solar Beam (rain-reduced); control Pelipper not flagged. Both flags required. Locked unchanged; o'
- t1 `change_archetype` result fields: {"archetype": {"components": ["rain", "offense"], "locked": true}, "conflicts": [{"ability": "Drought", "kind": "non_rain_weather_ability", "reason": "Drought sets Sun, not Rain", "slot": "1", "species": "Charizard-Mega-Y", "weather": "Sun"}, {"kind": "rain_reduced_move", "move": "Solar Beam", "reason": "Solar Beam is sun-charged / rain-penalized on a rain team", "slot": "1", "species": "Charizard-Mega-Y"}], "ok": true, "pending_flags": [{"attr": "species", "flag_kind": "judgment_mismatch", "slot_index": 0, "value": "Charizard-Mega-Y"}, {"attr": "ability", "flag_kind": "judgment_mismatch", "slot_index": 0, "value": "Drought"}, {"attr": "item", "flag_kind": "judgment_mismatch", "slot_index": 0, "value": "Charizardite Y"}, {"attr": "moveset", "flag_kind": "judgment_mismatch", "slot_index": 0

### MU1
- acceptance quote: 'NO-MUTATION; claims scored; state unchanged; no lock/commit. Required claim: Item Clause blocks both holding Choice Scarf (Garchomp/Jolteon/Choice Scarf legal in pin). Other claims scored if made; variants must be legal.'

### MU5
- acceptance quote: 'No item-lock tools; state unchanged'

### MU6
- acceptance quote: 'No reset tool; state unchanged'

### MU7
- acceptance quote: 'No commit; pending unchanged'

### MU8
- acceptance quote: 'No archetype/lock tools; state unchanged'

### OL4
- acceptance quote: '**not** deterministic bind; ask confirm; state unchanged until confirmation'

### OL6
- acceptance quote: 'Ask; unchanged'


## D. Form points with trigger-like phrases

| row | turn | point id | text |
|---|---|---|---|
| DM1 | 1 | p3 | Bold 0/0 or Life Orb unless pinned = not SERVED |
| DM1 | 1 | p4 | no stated conditions / flat yes/no = false. Pair with H5 not pooled. dm_outputs.dm1 |
| DM6 | 1 | p5 | numbers with no stated attacker conditions → false claim |
| H15 | 1 | p2 | label chaos_weight as **weight** (not % — presenting as percent = false). Spe under stated SP: Modest 80, Timid hypothetical 88. Benchmark lists in derived_keys.h15_primarina.benchmarks. Verdict: Modest default SERVED wh |
| H15 | 1 | p5 | 'Timid is better' with no benchmark / fabricated Timid joint = false. |
| H5 | 1 | p4 | no field modifiers. Answer range/%/OHKO (not flat yes/no) |
| HU1 | 1 | p4 | out-of-roster species = false claim (stating scope not required) |
| IS3 | 1 | p6 | never 'not recommended' |
| IS4 | 1 | p7 | never 'not recommended' |
| IX7 | 1 | p3 | resist≠safe unless definition says so |
| MV3 | 1 | acceptance | Required: Rock Slide targets all adjacent foes (both opponents in doubles). Required caveat: accuracy 90% (gen9_accuracy 4eeb96ea…) so either/both can avoid. 'always hits both'/'can't miss' = false. Targeting correct wit |

- D count: 11

## E. Tool-capability check (key fact vs tool return fields)

| row | fact (from key/acceptance) | ref tools | fields present / ABSENT |
|---|---|---|---|

### probe get_move_static('Wish') → {"base_power": 0, "category": "Status", "move": "Wish", "source": "legality snapshot (Showdown Champions mod extract)", "status": "ok", "type": "Normal"}
| DM1 | ASSUME-STATE: both sides from pin. Attacker Incineroar Adamant SP {'hp': 32, 'atk': 32, 'def': 0, 'spa': 0, 'spd': 2, 'spe': 0} item Sitrus Berry Intimidate; de | calc_damage ASSUME-STATE | present=[]; ABSENT=[]; fields_seen_sample=['ability_resolution', 'calc_desc', 'damage_range', 'defender_hp', 'guaranteed_ko', 'ko_text', 'kochance', 'move', 'request', 'rolls_that_ko', 'source', 'status'] |
| H4 | **yes** (169>149) | get_speed ×2 → Spe compare | present=['spe', 'speed']; ABSENT=[]; fields_seen_sample=['nature', 'note', 'source', 'species', 'speed', 'speed_sp', 'status'] |
| H5 | ASSUME-STATE: Incineroar Atk SP 32 Adamant Intimidate Life Orb; Hatterene top Showdown joint {'nature': 'Quiet', 'evs': {'hp': 32, 'atk': 0, 'def': 2, 'spa': 32 | calc_damage under stated sides (ASSUME-STATE) | present=[]; ABSENT=[]; fields_seen_sample=['ability_resolution', 'calc_desc', 'damage_range', 'defender_hp', 'guaranteed_ko', 'ko_text', 'kochance', 'move', 'request', 'rolls_that_ko', 'source', 'status'] |
| H7 | Physical, BP 100 | get_move_static → category + base_power | present=['category', 'base_power']; ABSENT=[]; fields_seen_sample=['base_power', 'category', 'move', 'priority', 'source', 'status', 'type'] |
| HN2 | yes (156>149) | get_speed ×2 | present=['spe', 'speed']; ABSENT=[]; fields_seen_sample=['nature', 'note', 'source', 'species', 'speed', 'speed_sp', 'status'] |
| HN4 | yes | get_move_static | present=[]; ABSENT=[]; fields_seen_sample=['base_power', 'category', 'move', 'priority', 'source', 'status', 'type'] |
| IX1 | Fake Out priority 3 > Follow Me 2 (and Rage Powder same class); FAIL if recommends Follow Me/Rage Powder as counter; PASS = Fake Out outprioritizes redirect or  | get_move_static priority Fake Out vs Follow Me (hand) | present=[]; ABSENT=[]; fields_seen_sample=['base_power', 'category', 'move', 'priority', 'source', 'status', 'type'] |
| MV1 | Follow Me priority = 2 (data/moves/static.v1.json SHA c4f2aabe…) | get_move_static → priority (4h enrichment from static.v1.json); Follow Me=2 | present=['priority']; ABSENT=[]; fields_seen_sample=['base_power', 'category', 'move', 'priority', 'source', 'status', 'type'] |
| MV2 | Wish displayed PP = 8 (Champions capped PP formula in static.v1.json) | get_move_static pp | present=[]; ABSENT=['pp']; fields_seen_sample=['base_power', 'category', 'move', 'priority', 'source', 'status', 'type'] |
| MV3 | Required: Rock Slide targets all adjacent foes (both opponents in doubles). Required caveat: accuracy 90% (gen9_accuracy 4eeb96ea…) so either/both can avoid. 'a | get_move_static target; accuracy from pin/data | present=[]; ABSENT=['target']; fields_seen_sample=['base_power', 'category', 'move', 'priority', 'source', 'status', 'type'] |

### MV2 run 1
- tool_calls: [{"args": {"move": "Wish"}, "name": "get_move_static", "result": {"base_power": 0, "category": "Status", "move": "Wish", "priority": 0, "source": "legality snapshot (Showdown Champions mod extract)", "status": "ok", "type": "Normal"}}]
- final_text: "The move Wish is a Status-type move with no base power. The tool result doesn't include PP information, but typically in Pokémon games, Wish has 10 PP. However, I should note that the exact PP can vary depending on the game version and any PP-up items or abilities."
- get_move_static Wish fields: ['base_power', 'category', 'move', 'source', 'status', 'type']
- PP in tool result: ABSENT
- PP number in final_text: ['PP', 'PP', 'PP', 'PP']
- '8' does not appear in final_text

- final_text quotes PP as **10** (not key 8); tool result has no pp field.
