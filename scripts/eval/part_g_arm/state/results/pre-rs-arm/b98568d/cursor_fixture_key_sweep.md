# cursor_fixture_key_sweep.md

Read-only. Covered 103, run_1. Verdict axis: locked-slot fields the key/state cell quotes.
ASSUME-STATE calc sides on empty_team → KEY SILENT on locked-slot axis.

## Counts

- MATCH: 7
- MISMATCH: 7
- KEY SILENT: 89
- build_fully_locked_slot rows: ['DM2']
- build_fully_locked_mega rows: []

| row | start-state source | loaded locked slot(s) | key / request-set quote | verdict |
|---|---|---|---|---|
| DM1 | empty_team | (no locked slots) | ASSUME-STATE dm1.attacker={"ability": "Intimidate", "evs": {"atk": 32, "def": 0, "hp": 32, "spa": 0, "spd": 2, "spe": 0}, "item": "Sitrus Berry", "nature": "Adamant", "source": {"ability": "explicit Intimid | KEY SILENT |
| DM2 | build_fully_locked_slot | s1:Incineroar* abl=Blaze* item=Sitrus Berry* nat=Modest* spr={'hp': 32, 'atk': 0, 'def': 0, 'spa': 32, 'spd': 2, 'spe': 0}* mv=['acrobatics', 'aerialace', 'assurance', 'attract']* | acceptance Locked fixture attacker = Adamant Life Orb Atk-32 ability Intimidate; locked_attacker_confirmed={"ability": "Intimidate", "evs": {"atk": 32, "def": 0, "hp": 0, "spa": 0, "spd": 4, "spe": 0}, "item": "Life Orb" | MISMATCH |
| DM3 | empty_team (ASSUME-STATE sides from pin) | (no locked slots) | ASSUME-STATE/calc (not locked start): "Doubles; Rock Slide allAdjacentFoes → 0.75 (≥2 targets assumed). Shared Incineroar top joint Adamant SP {'hp': 32, 'atk': 32, 'def': 0, 'spa" | KEY SILENT |
| DM4 | empty_team | (no locked slots) | ASSUME-STATE/calc (not locked start): 'Earthquake allAdjacent → 0.75 when ≥2 targets (Doubles); single-target-in-doubles = no 0.75 (not a Singles-format row). Same Incineroar top ' | KEY SILENT |
| DM6 | empty_team | (no locked slots) | ASSUME-STATE/calc (not locked start): "ASSUME-STATE. Gallade-Mega Inner Focus + Galladite; nature/SP/item from top Showdown joint+item (Jolly SP {'hp': 2, 'atk': 32, 'def': 0, 'sp" | KEY SILENT |
| DM7 | empty_team | (no locked slots) | ASSUME-STATE/calc (not locked start): "ASSUME-STATE. Annihilape; nature/SP/item from top Showdown joint+item (Jolly SP {'hp': 2, 'atk': 32, 'def': 0, 'spa': 0, 'spd': 0, 'spe': 32" | KEY SILENT |
| GS1 | empty_team | (no locked slots) | state='idle'; acceptance='t1 SERVED modal (MIR/SB/Protect/Nasty Plot; Life Orb). t2 MUTATION-OK Scarf+read-back; LO released; ' | KEY SILENT |
| H1 | empty_team | (no locked slots) | state='idle'; acceptance='`["Poison","Water"]`' | KEY SILENT |
| H11 | empty_team | (no locked slots) | state='idle'; acceptance='`{Gyarados,Pelipper,Quaquaval}`; set-scoring; script-derived; Mega Gyarados = deliberate false posit' | KEY SILENT |
| H13 | empty_team | (no locked slots) | state='idle'; acceptance='Must state **no per-team win-rate data**; no ranking' | KEY SILENT |
| H14 | empty_team | (no locked slots) | state='idle'; acceptance='OOF' | KEY SILENT |
| H15 | empty_team | (no locked slots) | state='idle'; acceptance="Modest top joint SP={'hp': 32, 'atk': 0, 'def': 0, 'spa': 32, 'spd': 2, 'spe': 0} chaos_weight pct≈8" | KEY SILENT |
| H16 | empty_team | (no locked slots) | state='idle no history'; acceptance='No history; fresh comparison OK without inventing prior rationale' | KEY SILENT |
| H18b | named fixture: load_fixture('H18b') | s1:Garchomp* abl=Rough Skin* item=Choice Scarf* nat=Jolly* spr={'hp': 0, 'atk': 32, 'def': 0, 'spa': 0, 'spd': 2, 'spe': 32}* mv=None \|\| s2:Dragapult* abl=Clear Body* item=Life Orb* nat=Timid* spr={'hp': 0, 'atk': 0, 'de | state='`scripts/eval/part_g_v4/fixtures/h18b_hyper_offense.json`'; acceptance='Binary checklist H18b: t1 establishes definition (no re-ask at t2); t2 Sinistcha fails top-joint SP ' | KEY SILENT |
| H2 | empty_team | (no locked slots) | state='idle'; acceptance='**true**' | KEY SILENT |
| H27 | named fixture: load_fixture('H27') | (no locked slots) | state='H27 fixture pending'; acceptance='**Garchomp**' | KEY SILENT |
| H3 | empty_team | (no locked slots) | state='idle'; acceptance='true,true' | KEY SILENT |
| H4 | empty_team | (no locked slots) | state='idle'; acceptance='**yes** (169>149)' | KEY SILENT |
| H5 | empty_team | (no locked slots) | ASSUME-STATE h5.attacker={"ability": "Intimidate", "atk_sp": 32, "item": "Life Orb", "nature": "Adamant", "species": "Incineroar"} | KEY SILENT |
| H6 | empty_team | (no locked slots) | state='idle'; acceptance='unordered `{Incineroar,Garchomp,Sneasler,Gholdengo,Raichu}`; set-scoring; must label **in-game** sou' | KEY SILENT |
| H7 | empty_team | (no locked slots) | state='idle'; acceptance='Physical, BP 100' | KEY SILENT |
| H8 | empty_team | (no locked slots) | state='idle empty'; acceptance='**No** (Item Clause); **no-mutation check**' | KEY SILENT |
| HC1 | empty_team | (no locked slots) | state='idle'; acceptance='Snapshot: no legal Water∧Fire species; state unsatisfiable as written; record nothing; must not appl' | KEY SILENT |
| HC2 | seed file: seeds/hc2_after_t1.json | (no locked slots) | state='after t1'; acceptance='Separate conflicting requests; ask resolve; no guess; no state change until user picks' | KEY SILENT |
| HD1 | seed file: seeds/hd1_history.json | (no locked slots) | state='after H1 claim Poison/Water'; acceptance='Correct types kept' | KEY SILENT |
| HF1 | empty_team | (no locked slots) | state='idle'; acceptance='Poison/Water' | KEY SILENT |
| HF2 | empty_team | (no locked slots) | state='idle'; acceptance='No; Blaze/Intimidate' | KEY SILENT |
| HN1 | empty_team | (no locked slots) | state='idle'; acceptance='`{Cud Chew, Armor Tail, Sap Sipper}`; set-scoring' | KEY SILENT |
| HN2 | empty_team | (no locked slots) | state='idle'; acceptance='yes (156>149)' | KEY SILENT |
| HN2b | empty_team | (no locked slots) | state='idle'; acceptance='Full forward grid in derived_keys.hn2b_forward_grid (COMMON_SPEED distinct; Scarf = 2 lines only; TW' | KEY SILENT |
| HN2c | named fixture: load_fixture('HN2c') | s1:Annihilape* abl=Defiant* item=Choice Scarf* nat=Jolly* spr={'hp': 0, 'atk': 32, 'def': 0, 'spa': 0, 'spd': 2, 'spe': 32}* mv=None | Annihilape locked Jolly Spe-32 | MATCH |
| HN2d | named fixture: load_fixture('HN2d') | s1:Blaziken-Mega* abl=Speed Boost* item=Blazikenite* nat=Jolly* spr={'hp': 0, 'atk': 32, 'def': 0, 'spa': 0, 'spd': 2, 'spe': 32}* mv=['Flare Blitz', 'Close Combat', 'Protect', 'Stone Edge']* | Blaziken-Mega+Blazikenite Spe Jolly-32 | MATCH |
| HN3 | empty_team | (no locked slots) | state='idle'; acceptance="COMMON_ITEM (ingame): Life Orb 37.0, Glimmoranite 30.7, Focus Sash 26.9 (cum≥90% at 3, cum 94.6); 'n" | KEY SILENT |
| HN4 | empty_team | (no locked slots) | state='idle'; acceptance='yes' | KEY SILENT |
| HP1 | empty_team | (no locked slots) | state='idle'; acceptance='Lead: Flutter Mane Past + Choice Specs Past; any damage labeled hypothetical; no team touch' | KEY SILENT |
| HP2 | empty_team | (no locked slots) | state='idle'; acceptance='Key: treat as **question** (legality), not implicit add; no team mutation' | KEY SILENT |
| HP3 | empty_team | (no locked slots) | state='idle'; acceptance='Refuse illegal mutation; state unchanged' | KEY SILENT |
| HU1 | empty_team | (no locked slots) | state='idle'; acceptance='`{Skeledirge,Incineroar,Arcanine-Hisui,Armarouge,Emboar,Torkoal}`; inclusive ≥350; formula membershi' | KEY SILENT |
| HU2 | empty_team | (no locked slots) | state='idle'; acceptance='EXPLICIT CONTROL paired with HU2b; outspeeds set `{Incineroar,Kingambit,Golisopod}`; set-scoring; la' | KEY SILENT |
| HU2b | empty_team | (no locked slots) | state='idle'; acceptance='Paired with HU2 (in-game lineage top10; not pooled). ASSUME-STATE: threats = shared Showdown per-for' | KEY SILENT |
| HU3 | empty_team | (no locked slots) | state='idle'; acceptance='Option list 3–5 Fire; per-option bulk reason; ask which; slot unchanged until selection' | KEY SILENT |
| HU4 | empty_team | (no locked slots) | state='idle'; acceptance='Assume important = top-N in-game usage and/or top threats to team; state N; Spe compare' | KEY SILENT |
| IC1 | named fixture: load_fixture('IC1') | s1:Sneasler* abl=Unburden* item=Psychic Seed* nat=None spr=None mv=None \|\| s2:Indeedee-F* abl=Psychic Surge* item=Rocky Helmet* nat=None spr=None mv=None | Sneasler=Psychic Seed, Indeedee-F=Rocky Helmet | MATCH |
| IS1 | empty_team | (no locked slots) | state='idle unlocked'; acceptance='See derived_keys.is1_min_spe: per Dragapult cell, bare + Scarf outcomes; N=0 → no investment needed;' | KEY SILENT |
| IS2 | named fixture: load_fixture('IS2') | s1:Basculegion* abl=Adaptability* item=Choice Scarf* nat=Jolly* spr={'hp': 10, 'atk': 32, 'def': 0, 'spa': 0, 'spd': 0, 'spe': 0}* mv=None | Basculegion locked Jolly Choice Scarf; non-Spe SP sum 42 | MATCH |
| IS3 | empty_team | (no locked slots) | state='idle'; acceptance='4-part min-SP; Slowbro max stack Spe=270 vs Dragapult Timid-32=213; vs max-speed Dragapult reachable' | KEY SILENT |
| IS4 | empty_team | (no locked slots) | state='idle'; acceptance='Prompt requires Mega; 4-part min-SP; Pincurchin max stack=218 < Alakazam-Mega Timid-32=222 → **unrea' | KEY SILENT |
| IX1 | empty_team | (no locked slots) | state='idle'; acceptance='Fake Out priority 3 > Follow Me 2 (and Rage Powder same class); FAIL if recommends Follow Me/Rage Po' | KEY SILENT |
| IX5 | empty_team | (no locked slots) | state='idle'; acceptance='Assume punish=blocked\|reflected\|boosted; set rule; separate buckets; verify holders vs legality; set' | KEY SILENT |
| IX7 | empty_team | (no locked slots) | state='idle'; acceptance='safe=no damage: Flying / Levitate / Telepathy / Earth Eater; examples+counts with source label; resi' | KEY SILENT |
| MC1 | empty_team | (no locked slots) | state='idle'; acceptance='No plain Charizard-Mega in pin; only X/Y. Pass = ASK which form, OR ASSUME-STATE Y (usage 9.51 vs X ' | KEY SILENT |
| MM1 | empty_team | (no locked slots) | idle; acceptance build target: 'Build with Salamencite; state mega cannot hold another item; offer keep stone or base form+Leftovers' | KEY SILENT |
| MM2 | named fixture: load_fixture('MM2') | s1:Salamence-Mega* abl=Aerilate* item=Salamencite* nat=None spr=None mv=None | state Salamence-Mega+Salamencite | MATCH |
| MR1 | empty_team | (no locked slots) | state='idle'; acceptance='Refuse illegal species; state unchanged' | KEY SILENT |
| MR2 | empty_team | (no locked slots) | state='idle'; acceptance='Refuse illegal item; state unchanged' | KEY SILENT |
| MR3 | empty_team | (no locked slots) | state 'one locked'; prompt Lock a second Incineroar | MISMATCH |
| MR4 | empty_team | (no locked slots) | state='two slots'; acceptance='Item Clause; state unchanged' | KEY SILENT |
| MR5 | empty_team | (no locked slots) | state='occupied'; acceptance='refuse/ask; state unchanged' | KEY SILENT |
| MR6 | empty_team | (no locked slots) | state='none locked'; acceptance='empty unlock refuse; state unchanged' | KEY SILENT |
| MR7 | empty_team | (no locked slots) | state='idle'; acceptance='nothing pending; state unchanged' | KEY SILENT |
| MR8 | empty_team | (no locked slots) | state='idle'; acceptance='illegal; state unchanged' | KEY SILENT |
| MRB1 | other: build_mrb1_start | s3:Torkoal* abl=Drought* item=Charcoal* nat=None spr=None mv=None | Torkoal/Drought/Charcoal slot3 | MATCH |
| MS1 | empty_team | (no locked slots) | state idle empty; acceptance end-state only | KEY SILENT |
| MS2 | empty_team | (no locked slots) | state 'slot1 locked' | MISMATCH |
| MS3 | empty_team | (no locked slots) | state '2 locked' | MISMATCH |
| MS4 | seed file: seeds/fbc_pending.json | (no locked slots) | FBC pending | KEY SILENT |
| MS5 | named fixture: load_fixture('MS5') | s1:Charizard-Mega-Y* abl=Drought* item=Charizardite Y* nat=None spr=None mv=['Heat Wave', 'Solar Beam', 'Protect', 'Scorching Sands']* \|\| s2:Pelipper* abl=Drizzle* item=Damp Rock* nat=None spr=None mv=['Hurricane', 'U-tu | acceptance Drought+Solar Beam conflicts; Pelipper control | MATCH |
| MS6 | empty_team | (no locked slots) | idle | KEY SILENT |
| MS7 | seed file: seeds/cs_pending.json | (no locked slots) | CS pending | KEY SILENT |
| MS8 | empty_team | (no locked slots) | idle; end-state Pelipper | KEY SILENT |
| MT1 | empty_team | (no locked slots) | state='idle'; acceptance='Both constraints in t3 read-back' | KEY SILENT |
| MT2 | empty_team | (no locked slots) | state='idle→locked'; acceptance='t2 unordered `{Charizard,Garchomp,Sneasler}`; set-scoring; label in-game; t3 Pelipper' | KEY SILENT |
| MT3 | seed file: seeds/mt3_after_t1.json | (no locked slots) | state='after t1'; acceptance='Binary checklist MT3 (Fire required; Intimidate → flag)' | KEY SILENT |
| MT5 | empty_team | (no locked slots) | state='mid-build'; acceptance='Archetype string in t3 read-back' | KEY SILENT |
| MT6 | empty_team | (no locked slots) | state='idle'; acceptance='t1 = HC1 behavior (unsatisfiable as written; record nothing); t2 resolves to Water only; t3 Water-on' | KEY SILENT |
| MU1 | empty_team | (no locked slots) | state='idle empty'; acceptance='NO-MUTATION; claims scored; state unchanged; no lock/commit. Required claim: Item Clause blocks both' | KEY SILENT |
| MU2 | named fixture: load_fixture('MU2') | s1:Garchomp* abl=Rough Skin* item=Choice Scarf* nat=None spr=None mv=None \|\| s3:Incineroar* abl=Intimidate* item=Sitrus Berry* nat=None spr=None mv=None | state='`scripts/eval/part_g_v4/fixtures/mu2_mu3_team.json`'; acceptance='NO-MUTATION; claims scored. Any species named as Water must be Water and legal; mechanical statement' | KEY SILENT |
| MU3 | named fixture: load_fixture('MU3') | s1:Garchomp* abl=Rough Skin* item=Choice Scarf* nat=None spr=None mv=None \|\| s3:Incineroar* abl=Intimidate* item=Sitrus Berry* nat=None spr=None mv=None | state='`scripts/eval/part_g_v4/fixtures/mu2_mu3_team.json`'; acceptance="NO-MUTATION; claims scored. Arm states what 'fit' means (legal, no Species/Item Clause conflict with" | KEY SILENT |
| MU4 | named fixture: load_fixture('MU4') | s1:Torkoal* abl=Drought* item=Heat Rock* nat=None spr=None mv=None | state='`scripts/eval/part_g_v4/fixtures/mu4_pelipper.json`'; acceptance='NO-MUTATION; claims scored. Yes/no/conditional with ≥1 tool-backed reason (Drizzle + explicit abilit' | KEY SILENT |
| MU5 | empty_team | (no locked slots) | state='any'; acceptance='No item-lock tools; state unchanged' | KEY SILENT |
| MU6 | empty_team | (no locked slots) | state='nonempty'; acceptance='No reset tool; state unchanged' | KEY SILENT |
| MU7 | seed file: seeds/fbc_pending.json | (no locked slots) | state='FBC pending'; acceptance='No commit; pending unchanged' | KEY SILENT |
| MU8 | empty_team | (no locked slots) | state='idle'; acceptance='No archetype/lock tools; state unchanged' | KEY SILENT |
| MV1 | empty_team | (no locked slots) | state='idle'; acceptance='Follow Me priority = 2 (data/moves/static.v1.json SHA c4f2aabe…)' | KEY SILENT |
| MV2 | empty_team | (no locked slots) | state='idle'; acceptance='Wish displayed PP = 8 (Champions capped PP formula in static.v1.json)' | KEY SILENT |
| MV3 | empty_team | (no locked slots) | state='idle'; acceptance='Required: Rock Slide targets all adjacent foes (both opponents in doubles). Required caveat: accurac' | KEY SILENT |
| MW1 | empty_team | (no locked slots) | state='ambiguous'; acceptance='Ask; no guess; no state change' | KEY SILENT |
| MW2 | empty_team | (no locked slots) | state ≥1 locked | MISMATCH |
| MW3 | empty_team | (no locked slots) | state='idle'; acceptance='Ask slot; no state change' | KEY SILENT |
| MW4 | empty_team | (no locked slots) | state='multi options'; acceptance='Ask which; no state change' | KEY SILENT |
| OL2b | named fixture: load_fixture('OL2b') | (no locked slots) | state='`OL2b.json` CS'; acceptance='Bound to Incineroar (positive control)' | KEY SILENT |
| OL4 | named fixture: load_fixture('OL4') | (no locked slots) | state='`OL4.json` CS'; acceptance='**not** deterministic bind; ask confirm; state unchanged until confirmation' | KEY SILENT |
| OL5 | named fixture: load_fixture('OL5') | (no locked slots) | state='`OL5.json` CS one option'; acceptance='Bound Garchomp' | KEY SILENT |
| OL6 | named fixture: load_fixture('OL6') | (no locked slots) | state='`OL6.json` CS multi'; acceptance='Ask; unchanged' | KEY SILENT |
| OL7a | named fixture: load_fixture('OL7a') | (no locked slots) | state='`OL7a.json` CS'; acceptance='Verifiably faster=Jolteon (Spe 200)' | KEY SILENT |
| OL8 | named fixture: load_fixture('OL8') | (no locked slots) | state='`OL8.json` CS'; acceptance='Reject; no lock' | KEY SILENT |
| OL9 | named fixture: load_fixture('OL9') | (no locked slots) | state='`OL9.json` CS'; acceptance='Ask; not applied' | KEY SILENT |
| Q10 | empty_team | (no locked slots) | state='empty team'; acceptance='Explains empty unlock; no mutation' | KEY SILENT |
| Q9 | empty_team | (no locked slots) | state='idle'; acceptance='**No** (Species Clause); no mutation' | KEY SILENT |
| RB1 | empty_team | (no locked slots) | Lucario-Mega-Z + Lucarionite Z; moves Aura Sphere/Flash Cannon/Calm Mind | MISMATCH |
| SC2 | load_fail | — | state='Arch on team or ask-add path'; acceptance='Soak not learned (script false); refusal through legality; slot conditions are drafts not mutations;' | KEY SILENT |
| TB1 | empty_team | (no locked slots) | state='idle'; acceptance='SERVED with stated correction: build as asked but state Charcoal has no effect (no legal damaging Fi' | KEY SILENT |
| TB2 | load_fail | — | Incineroar+Charcoal; Flare Blitz | MISMATCH |

## Addendum — MISMATCH rows: tool calls / final text / which set (quote only)

### DM2

- start source: `build_fully_locked_slot`
- loaded: `s1:Incineroar* abl=Blaze* item=Sitrus Berry* nat=Modest* spr={'hp': 32, 'atk': 0, 'def': 0, 'spa': 32, 'spd': 2, 'spe': 0}* mv=['acrobatics', 'aerialace', 'assurance', 'attract']*`
- key attacker: nature='Adamant' item='Life Orb' ability='Intimidate' evs={'hp': 0, 'atk': 32, 'def': 0, 'spa': 0, 'spd': 4, 'spe': 0}
- turn 1 tool_calls:
  - [1] `calc_damage` args={"attacker": {"ability": "Intimidate", "item": "Black Sludge", "nature": "Jolly", "sp": {"atk": 32, "def": 0, "hp": 0, "spa": 0, "spd": 0, "spe": 32}, "species": "Incineroar"}, "defender": {"ability": "Magic Bounce", "item": "Eviolite", "nature": "Timid", "sp": {"atk": 0, "def": 0, "hp": 0, "spa": 32, "spd": 0, "spe": 32}, "species": "Hatterene"}, "field": {"gameType": "Doubles"}, "move": "Flare Blitz"}
    attacker_set: species='Incineroar' ability='Intimidate' item='Black Sludge' nature='Jolly' spread={'atk': 32, 'def': 0, 'hp': 0, 'spa': 0, 'spd': 0, 'spe': 32} move='Flare Blitz'
    result_slim={"error_kind": "calc_error", "message": "{'error': 'unknown Champions item: Black Sludge'}", "status": "error"}
  - [2] `check_item_legal` args={"item": "Black Sludge"}
  - [3] `calc_damage` args={"attacker": {"ability": "Intimidate", "item": "", "nature": "Jolly", "sp": {"atk": 32, "def": 0, "hp": 0, "spa": 0, "spd": 0, "spe": 32}, "species": "Incineroar"}, "defender": {"ability": "Magic Bounce", "item": "Eviolite", "nature": "Timid", "sp": {"atk": 0, "def": 0, "hp": 0, "spa": 32, "spd": 0, "spe": 32}, "species": "Hatterene"}, "field": {"gameType": "Doubles"}, "move": "Flare Blitz"}
    attacker_set: species='Incineroar' ability='Intimidate' item='' nature='Jolly' spread={'atk': 32, 'def': 0, 'hp': 0, 'spa': 0, 'spd': 0, 'spe': 32} move='Flare Blitz'
    result_slim={"error_kind": "calc_error", "message": "{'error': 'unknown Champions item: Eviolite'}", "status": "error"}
  - [4] `calc_damage` args={"attacker": {"ability": "Intimidate", "item": "", "nature": "Jolly", "sp": {"atk": 32, "def": 0, "hp": 0, "spa": 0, "spd": 0, "spe": 32}, "species": "Incineroar"}, "defender": {"ability": "Magic Bounce", "item": "", "nature": "Timid", "sp": {"atk": 0, "def": 0, "hp": 0, "spa": 32, "spd": 0, "spe": 32}, "species": "Hatterene"}, "field": {"gameType": "Doubles"}, "move": "Flare Blitz"}
    attacker_set: species='Incineroar' ability='Intimidate' item='' nature='Jolly' spread={'atk': 32, 'def': 0, 'hp': 0, 'spa': 0, 'spd': 0, 'spe': 32} move='Flare Blitz'
    result_slim={"damage_range": [99, 117], "ko_text": "guaranteed 2HKO", "status": "ok"}
  - read_draft/locked_slot_before_calc: False
  - final_text: "Based on the damage calculation, **Flare Blitz from Incineroar does NOT KO Hatterene** in a single hit. The move deals 99-117 damage (75-88.6%), which is a guaranteed 2HKO against a Timid Hatterene with maximum Special Attack investment.\n\nThis calculation assumes:\n- Incineroar with Jolly nature and maxed Attack (32 SP)\n- Hatterene with Timid nature and maxed Special Attack (32 SP)\n- No items held by either Pokémon\n\nThe damage would be slightly lower if Hatterene holds an item like Leftovers or a Choice item, but it still wouldn't reach KO territory in one hit. Incineroar's Flare Blitz is not a reliable 1HKO threat against common Hatterene spreads."
  - match_loaded_fixture: no (loaded Blaze/Sitrus/Modest/spa32; calcs use Intimidate/Jolly/spe32)
  - match_key_attacker: no (key Adamant/Life Orb/atk32/spd4; calcs Jolly/empty-or-Black Sludge/spe32)
  - match: neither
  - numbers_in_final_text: ['99', '117', '75', '88.6%', '2', '32', '32', '1']

### MR3

- start source: `empty_team`
- loaded: `(no locked slots)`
- turn 1 tool_calls:
  - [1] `lock_slot` args={"slot": 2, "species": "Incineroar"}
  - read_draft/locked_slot_before_calc: False
  - final_text: 'Incineroar has been locked into slot 2. The team now has one Incineroar in slot 2, with all other slots remaining open for future selections.'
  - match_loaded_fixture: n/a (empty load)
  - match: neither vs key/state lock assumption (0 locked loaded)

### MS2

- start source: `empty_team`
- loaded: `(no locked slots)`
- turn 1 tool_calls:
  - [1] `unlock_slot` args={"slot": 1}
  - read_draft/locked_slot_before_calc: False
  - final_text: "The unlock was refused because there's no fully locked slot available. This error suggests that the team build system requires at least one species to be locked before you can make changes. \n\nTo proceed, you would need to either:\n1. Lock a species into a slot first using `lock_slot(slot, species)`\n2. Reset the entire team with `reset_team()` if you want to start fresh\n\nWould you like to lock a species into a slot or reset the team?"
  - match_loaded_fixture: n/a (empty load)
  - match: neither vs key/state lock assumption (0 locked loaded)

### MS3

- start source: `empty_team`
- loaded: `(no locked slots)`
- turn 1 tool_calls:
  - [1] `reset_team` args={}
  - read_draft/locked_slot_before_calc: False
  - final_text: 'The team has been reset. All six slots are now empty and unlocked, ready for you to build a new team.'
  - match_loaded_fixture: n/a (empty load)
  - match: neither vs key/state lock assumption (0 locked loaded)

### MW2

- start source: `empty_team`
- loaded: `(no locked slots)`
- turn 1 tool_calls:
  - [1] `read_team` args={}
  - read_draft/locked_slot_before_calc: True
  - final_text: "The team is currently empty - no slots are locked. There's nothing to unlock since all slots are already unlocked (species_locked: false for all slots).\n\nIf you meant to unlock a specific slot that was previously locked, please let me know which slot number you'd like to unlock."
  - match_loaded_fixture: n/a (empty load)
  - match: neither vs key/state lock assumption (0 locked loaded)

### RB1

- start source: `empty_team`
- loaded: `(no locked slots)`
- turn 1 tool_calls:
  - [1] `read_team` args={}
  - read_draft/locked_slot_before_calc: True
  - final_text: "Your team is currently empty - no species are locked in any slots. To add Nasty Plot, I need to:\n\n1. First lock a species into a slot\n2. Then edit that slot's moveset to include Nasty Plot\n\nWhich slot would you like to use for this? And which species do you want to put there?"
  - match_loaded_fixture: n/a (empty load)
  - match: neither vs key/state lock assumption (0 locked loaded)

### TB2

- start source: `load_fail`
- loaded: `—`
- turns: none (load_fail or empty)

