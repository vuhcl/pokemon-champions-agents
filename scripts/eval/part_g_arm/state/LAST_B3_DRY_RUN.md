# B3 — load-only dry run (covered rows, no model)

| row | loaded | complete | source | readback / note |
|---|---|---|---|---|
| H1 | True | True | empty_team |  |
| H2 | True | True | empty_team |  |
| H3 | True | True | empty_team |  |
| H4 | True | True | empty_team |  |
| H5 | True | True | empty_team |  |
| H6 | True | True | empty_team |  |
| H7 | True | True | empty_team |  |
| H8 | True | True | empty_team |  |
| Q9 | True | True | empty_team |  |
| Q10 | True | True | empty_team |  |
| H11 | True | True | empty_team |  |
| H13 | True | True | empty_team |  |
| H14 | True | True | empty_team |  |
| H15 | True | True | empty_team |  |
| H16 | True | True | empty_team |  |
| H18b | True | False | load_fixture('H18b') | constraint 'hyper_offense_32_atk_or_spa' loaded as judgment-only predicate only (no mechanical_kind; not enforceable as SP/weather rule); constraint 'no_weather_ability' loaded as judgment-only predicate only (no mechanical_kind; not enforceable as SP/weather rule) |
| H19 | True | True | empty_team |  |
| H20 | True | True | empty_team |  |
| MT1 | True | True | empty_team |  |
| MT2 | True | True | empty_team |  |
| MT3 | False | False | None | multi-turn seed 'after t1' not built (prior turn not replayed) |
| MT4 | False | False | None | pending start 'CS pending' needs a named OL/v4 fixture; not invented |
| MT5 | True | True | empty_team |  |
| MT6 | True | True | empty_team |  |
| HF1 | True | True | empty_team |  |
| HF2 | True | True | empty_team |  |
| HC1 | True | True | empty_team |  |
| HC2 | False | False | None | multi-turn seed 'after t1' not built (prior turn not replayed) |
| HD1 | False | False | None | multi-turn seed 'after H1 claim Poison/Water' not built (prior turn not replayed) |
| HU1 | True | True | empty_team |  |
| HU2 | True | True | empty_team |  |
| HU3 | True | True | empty_team |  |
| HU4 | True | True | empty_team |  |
| HN1 | True | True | empty_team |  |
| HN2 | True | True | empty_team |  |
| HN3 | True | True | empty_team |  |
| HN4 | True | True | empty_team |  |
| HP1 | True | True | empty_team |  |
| HP2 | True | True | empty_team |  |
| HP3 | True | True | empty_team |  |
| MS1 | True | True | empty_team |  |
| MS2 | True | True | empty_team |  |
| MS3 | True | True | empty_team |  |
| MS4 | False | False | None | pending start 'FBC pending valid' needs a named OL/v4 fixture; not invented |
| MS6 | True | True | empty_team |  |
| MS7 | False | False | None | pending start 'CS pending' needs a named OL/v4 fixture; not invented |
| MS8 | True | True | empty_team |  |
| MR1 | True | True | empty_team |  |
| MR2 | True | True | empty_team |  |
| MR3 | True | True | empty_team |  |
| MR4 | True | True | empty_team |  |
| MR5 | True | True | empty_team |  |
| MR6 | True | True | empty_team |  |
| MR7 | True | True | empty_team |  |
| MR8 | True | True | empty_team |  |
| MU1 | True | True | empty_team |  |
| MU2 | True | True | load_fixture('MU2') |  |
| MU3 | True | True | load_fixture('MU3') |  |
| MU4 | True | False | load_fixture('MU4') | slot 1: skipped unlocked 'Pelipper' |
| MU5 | True | True | empty_team |  |
| MU6 | True | True | empty_team |  |
| MU7 | False | False | None | pending start 'FBC pending' needs a named OL/v4 fixture; not invented |
| MU8 | True | True | empty_team |  |
| MW1 | True | True | empty_team |  |
| MW2 | True | True | empty_team |  |
| MW3 | True | True | empty_team |  |
| MW4 | True | True | empty_team |  |
| MRB1 | True | True | build_mrb1_start | readback match=True got={'species': 'Torkoal', 'ability': 'Drought', 'item': 'Charcoal'} expected={'species': 'Torkoal', 'ability': 'Drought', 'item': 'Charcoal'} |
| OL1 | True | True | load_fixture('OL1') |  |
| OL2a | True | True | load_fixture('OL2a') |  |
| OL2b | True | True | load_fixture('OL2b') |  |
| OL3 | True | True | load_fixture('OL3') |  |
| OL4 | True | True | load_fixture('OL4') |  |
| OL5 | True | True | load_fixture('OL5') |  |
| OL6 | True | True | load_fixture('OL6') |  |
| OL8 | True | True | load_fixture('OL8') |  |
| OL9 | True | True | load_fixture('OL9') |  |
| HU2b | True | True | empty_team |  |
| HN2b | True | True | empty_team |  |
| HN2c | True | False | load_fixture('HN2c') | slot 0: moves skipped (apply_lock moveset wiped siblings; Choice item + non-damaging move) |
| HN2d | True | True | load_fixture('HN2d') |  |
| IS1 | True | True | empty_team |  |
| IS2 | True | True | load_fixture('IS2') |  |
| IS3 | True | True | empty_team |  |
| IS4 | True | True | empty_team |  |
| DM1 | True | True | empty_team |  |
| DM2 | True | True | build_fully_locked_slot(Incineroar) |  |
| DM3 | True | True | empty_team (ASSUME-STATE sides from pin) |  |
| DM4 | True | True | empty_team |  |
| DM6 | True | True | empty_team |  |
| DM7 | True | True | empty_team |  |
| MV1 | True | True | empty_team |  |
| MV2 | True | True | empty_team |  |
| MV3 | True | True | empty_team |  |
| IC1 | True | True | load_fixture('IC1') |  |
| TB1 | True | True | empty_team |  |
| MC1 | True | True | empty_team |  |
