# Nov 5 usage refresh vs hosted-demo numbers

Measured on `b49e27f` (M-8 ingame usage, 240 species). The parent `4d59608` has the same code and the M-7 file. Local calc on 127.0.0.1:4173. This directory is the harness. Product code and `data/` were not edited.

`USAGE_REFRESH_BLOB=old` points `load_usage` at a temp copy of the `4d59608` ingame file. The reply rules are the #381 rules. No reply change was needed for a script to finish: both still lock six Pokémon. The species change because option order changed.

## Checks

| Command | Result | Wall |
|---|---|---|
| `uv run pytest` | 4758 passed, 24 failed, 18 skipped | 132.75 s |
| `run_all_checks.py` | exit 1. `check_pins` and `check_battery_hash` fail. The other checks PASS, including `keys_sha` | 5.23 s |
| `npm test` | 119 passed, 0 failed | 0.42 s |
| `CALC_LIVE=1` on the live-calc modules except the fingerprint test | 57 passed | 10.38 s |
| `CALC_LIVE=1` `test_alone_games_match_380_fingerprints` | 1 failed | 76.50 s |

The 24 pytest failures all pass (26 cases, 0.73 s) when the M-7 file is restored. They are usage-derived roles, teammates, spreads, and the Gourgeist forme class (`gourgeistlarge` is no longer an independent usage row, so `classify_forme` returns `battle_transform`).

Hashes now:

- `keys_sha=e70672541b5215e7bfff7eccb34dc321b2bde3a4b9cf08d1f5a6419be1d2309a` unchanged
- committed `claim=` and `false_legal=` hashes are unchanged on disk. Regenerating them against the M-7 file still prints the previous values. Against M-8, `generate_claim_battery.py` stops because the usage pin does not match, so no new battery hash was produced.
- usage git blob moved from `31af0801235dc4158c6206363c70ae8cc2b6417b` to `daff5fd110d75764d360ec51929bfa279757a0eb`
- usage content sha256 moved from `4ac4985a9b7531b78744d7c5bf9454dab028b22ac156960c87d5f6aa050ae97e` to `7dae5512a83fd8ef20932aa83f1d7dd0d0b2ac6107bb5018b2b30df673e524c4`

`check_pins` passes on `4d59608`.

## Floor and scripts

Accept-defaults still ends at turn 14 with six locked. The locked species changed.

| path | before | now |
|---|---|---|
| baseline | turn 3, Pelipper locked | turn 3, Pelipper locked. Next options were Goodra, Blastoise, Swampert-Mega; now Swampert-Mega, Basculegion |
| six-paste | turn 1, 0 locked, options Pelipper, Rillaboom, Incineroar | turn 1, 0 locked, options Pelipper, Kingambit, Rillaboom. Notices still "Couldn't identify" for Amoonguss and Flutter Mane |
| accept-defaults / script A | Pelipper, Goodra, Excadrill-Mega, Basculegion, Sylveon, Floette-Eternal | Pelipper, Swampert-Mega, Gholdengo, Kommo-o, Archaludon, Floette-Eternal |

Script B still finishes in 14 messages. Message 2 options were Incineroar, Garchomp, Sneasler. They are now Incineroar, Sneasler, Garchomp, so the reply "2" locks Sneasler. Final lock: Sneasler, Indeedee-F, Primarina, Froslass-Mega, Audino, Blastoise. Previously Garchomp, Whimsicott, Indeedee-F, Arcanine-Hisui, Aromatisse, Audino.

Replaying A and B on the M-7 file on this commit reproduced those previous rosters and the #381 HTTP, hit, and miss counts, and the draft fingerprints matched the fixtures.

Message rows are wall seconds, HTTP batches, hits, misses. Previous column is #381 alone game 1 (A) and the B game.

Script A. Message 9 is no longer the heavy confirmation; completion preference moved to message 8.

| m | #381 | M-8 |
|---:|---|---|
| 1 | 0.17 / 0 / 0 / 0 | 0.18 / 0 / 0 / 0 |
| 2 | 0.03 / 0 / 0 / 0 | 0.02 / 0 / 0 / 0 |
| 3 | 0.77 / 68 / 0 / 46 | 12.41 / 5995 / 218 / 3872 |
| 4 | 0.04 / 0 / 0 / 0 | 0.02 / 0 / 0 / 0 |
| 5 | 8.95 / 3665 / 529 / 2404 | 3.79 / 758 / 1945 / 525 |
| 6 | 0.07 / 0 / 0 / 0 | 0.05 / 0 / 0 / 0 |
| 7 | 3.18 / 504 / 1937 / 355 | 2.62 / 303 / 1259 / 229 |
| 8 | 0.02 / 0 / 0 / 0 | 0.97 / 0 / 1488 / 0 |
| 9 | 5.90 / 2504 / 154702 / 2009 | 0.07 / 0 / 0 / 0 |
| 10 | 1.53 / 0 / 156711 / 0 | 2.53 / 937 / 74635 / 948 |
| 11 | 0.03 / 0 / 0 / 0 | 0.02 / 0 / 0 / 0 |
| 12 | 2.43 / 239 / 327848 / 200 | 1.72 / 132 / 169996 / 118 |
| 13 | 0.04 / 0 / 0 / 0 | 0.03 / 0 / 0 / 0 |
| 14 | 0.37 / 113 / 3363 / 97 | 0.33 / 97 / 3418 / 86 |

Script B:

| m | #381 | M-8 |
|---:|---|---|
| 1 | 0.44 / 0 / 0 / 0 | 0.47 / 0 / 0 / 0 |
| 2 | 0.01 / 0 / 0 / 0 | 0.01 / 0 / 0 / 0 |
| 3 | 6.77 / 1580 / 103 / 1601 | 0.73 / 26 / 0 / 26 |
| 4 | 0.03 / 0 / 0 / 0 | 0.03 / 0 / 0 / 0 |
| 5 | 6.36 / 2037 / 1561 / 1141 | 10.03 / 5442 / 601 / 3497 |
| 6 | 0.09 / 0 / 0 / 0 | 0.05 / 0 / 0 / 0 |
| 7 | 6.69 / 2999 / 2599 / 1630 | 3.11 / 493 / 2952 / 350 |
| 8 | 0.03 / 0 / 0 / 0 | 0.09 / 0 / 0 / 0 |
| 9 | 9.71 / 5524 / 258134 / 3785 | 9.38 / 5199 / 220673 / 3445 |
| 10 | 2.04 / 0 / 261919 / 0 | 1.81 / 0 / 224118 / 0 |
| 11 | 0.13 / 0 / 0 / 0 | 0.13 / 0 / 0 / 0 |
| 12 | 3.48 / 371 / 617936 / 248 | 3.54 / 20 / 738935 / 99 |
| 13 | 0.19 / 0 / 0 / 0 | 0.13 / 0 / 0 / 0 |
| 14 | 0.22 / 0 / 4372 / 87 | 0.35 / 93 / 4432 / 76 |

Largest alone message: script A 12.41 s (message 3; was 8.95 s at message 5). Script B 10.03 s (message 5; was 9.71 s at message 9).

The fingerprint test fails. Drafts differ. Script A starts with Pelipper's item Sitrus Berry versus Focus Sash and spread hp 2 versus 0, spd 0 versus 2, then slot 2 Goodra versus Swampert-Mega. Coverage rows 78 versus 80. SPOF rows differ. Final pending options are still empty on both sides. Script B's first slot is Garchomp versus Sneasler.

## The 22 species

`check_set` on a plain set (Protect when it is in the learnset, otherwise the first learnset move, no item, no ability) is ok for all 22. None raised.

Naming one as the anchor, on M-8:

- Seventeen open `candidate_selection` with that species as option 0: Appletun, Arbok, Avalugg, Castform, Decidueye, Dedenne, Furfrou, Gogoat, Gourgeist-Super, Pangoro, Persian, Samurott, Simisage, Simisear, Stunfisk-Galar, Swalot, Tyrantrum.
- Five stay on bootstrap: Garbodor, Gourgeist, Gourgeist-Large, Qwilfish, Tauros. `candidate_discovery_error` is `no_candidates` at `candidate_merge`: "Couldn't resolve a starting role". On the M-7 file those five opened `candidate_selection` with themselves as option 0. Path: `bootstrap.py` `query_by_usage` for the named species, `resolve_anchor_build`, `classify_anchor_role`, no target role, the movepool-family transfer misses, and the anchor is omitted from the candidate list.

In the script A/B games, Castform was the only one of the 22 on a suggestion list before (script A message 8: Basculegion, Indeedee-F, Castform). It is not on those lists now. The other 21 were not on those lists before either.

## Who reads the file

The file is opened by `recommender/usage_data.py` (`{tag}.ingame_doubles.v1.json` inside `_load_usage_uncached`). Everything else that sees ladder rows goes through `load_usage`, `ingame_species_map`, or `ingame_ladder_species_map`.

Direct path references:

- Writers: `scripts/extract_usage/fetch_usage_mc_metaroll.py`, `fetch_usage_mc_munchstats.py`, `split_usage_monolith.py`, `.github/workflows/usage-refresh-mc.yml`
- Readers that hash or open it: `scripts/eval/part_g_v4/checks/check_pins.py`, `pins_manifest.json`, `scripts/eval/part_g_v4/battery/generate_claim_battery.py`, `battery/battery_manifest.json`, `builders/_lib.py`, `scripts/ci/compendium_refresh_gate.py`, `tests/recommender/test_item_holders.py`
- Path recorded, not a content check of the current file: `data/roles/fixtures/compendium_refresh_marker.json`, `data/usage/README.md`, `scripts/eval/part_g_arm/dev_seed1/battery_manifest.json` (old blob `31af0801`), `scripts/eval/part_g_arm/state/STATE_MANIFEST_PROPOSAL.json`, the two `LAST_PART4C_*.md` notes, and the part3 design docs (an older blob `65f8c51e`)

`check_pins` and `pins_manifest.json` compare the file's git blob and content sha256 to the M-7 values. Those no longer match. `keys_sha` does not include this file and did not move. The committed claim and false-legal hashes did not move; regeneration refuses to run until the usage pin matches.
