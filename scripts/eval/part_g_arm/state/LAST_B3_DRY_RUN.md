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
| MT1 | True | True | empty_team |  |
| MT2 | True | True | empty_team |  |
| MT3 | True | True | seeds/mt3_after_t1 |  |
| MT5 | True | True | empty_team (explicit) |  |
| MT6 | True | True | empty_team |  |
| H27 | True | True | load_fixture('H27') |  |
| HF1 | True | True | empty_team |  |
| HF2 | True | True | empty_team |  |
| HC1 | True | True | empty_team |  |
| HC2 | True | True | seeds/hc2_after_t1 |  |
| HD1 | True | True | seeds/hd1_history |  |
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
| MS2 | True | True | explicit:build_fully_locked_slot(Incineroar@1) |  |
| MS3 | True | True | explicit:Incineroar@1+Garchomp@2 fully locked |  |
| MS4 | True | True | seeds/fbc_pending |  |
| MS5 | True | True | load_fixture('MS5') |  |
| MS6 | True | True | empty_team |  |
| MS7 | True | True | seeds/cs_pending |  |
| MS8 | True | True | empty_team |  |
| MR1 | True | True | empty_team |  |
| MR2 | True | True | empty_team |  |
| MR3 | True | True | explicit:build_fully_locked_slot(Incineroar@1) |  |
| MR4 | True | True | explicit:Incineroar@1+Garchomp@2 fully locked |  |
| MR5 | True | True | explicit:build_fully_locked_slot(Garchomp@2) |  |
| MR6 | True | True | empty_team |  |
| MR7 | True | True | empty_team |  |
| MR8 | True | True | empty_team |  |
| MU1 | True | True | empty_team |  |
| MU2 | True | True | load_fixture('MU2') |  |
| MU3 | True | True | load_fixture('MU3') |  |
| MU4 | True | True | load_fixture('MU4') |  |
| MU5 | True | True | empty_team |  |
| MU6 | True | True | explicit:Incineroar@1+Garchomp@2 fully locked |  |
| MU7 | True | True | seeds/fbc_pending |  |
| MU8 | True | True | empty_team |  |
| MW1 | True | True | empty_team (explicit) |  |
| MW2 | True | True | explicit:Incineroar@1+Garchomp@2 fully locked |  |
| MW3 | True | True | empty_team |  |
| MW4 | True | True | explicit:seeds/cs_pending |  |
| MRB1 | True | True | build_mrb1_start | readback match=True got={'species': 'Torkoal', 'ability': 'Drought', 'item': 'Charcoal'} expected={'species': 'Torkoal', 'ability': 'Drought', 'item': 'Charcoal'} |
| OL2b | True | True | load_fixture('OL2b') |  |
| OL4 | True | True | load_fixture('OL4') |  |
| OL5 | True | True | load_fixture('OL5') |  |
| OL6 | True | True | load_fixture('OL6') |  |
| OL7a | True | True | load_fixture('OL7a') |  |
| OL8 | True | True | load_fixture('OL8') |  |
| OL9 | True | True | load_fixture('OL9') |  |
| HU2b | True | True | empty_team |  |
| HN2b | True | True | empty_team |  |
| HN2c | True | True | load_fixture('HN2c') |  |
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
| SC2 | True | True | build_fully_locked_slot(Archaludon) |  |
| MV1 | True | True | empty_team |  |
| MV2 | True | True | empty_team |  |
| MV3 | True | True | empty_team |  |
| IX1 | True | True | empty_team |  |
| IX5 | True | True | empty_team |  |
| IX7 | True | True | empty_team |  |
| IC1 | True | True | load_fixture('IC1') |  |
| GS1 | True | True | empty_team |  |
| TB1 | True | True | empty_team |  |
| TB2 | True | True | scripts/eval/part_g_v4/fixtures/tb2_incineroar_charcoal.json |  |
| MM1 | True | True | empty_team |  |
| MM2 | True | True | load_fixture('MM2') |  |
| MC1 | True | True | empty_team |  |
| RB1 | True | True | scripts/eval/part_g_v4/fixtures/rb1_lucario_megaz_calmmind.json |  |
