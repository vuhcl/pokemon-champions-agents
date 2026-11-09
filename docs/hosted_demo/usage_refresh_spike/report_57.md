# Follow-up 57: the group-(c) failures on M-8

Read at `2b8a6bc`, usage file from `b49e27f`. No test edits and no product edits. M-7 values were read by loading `4d59608`'s ingame file from outside the worktree. The live Kangaskhan-Mega plus Torkoal block was executed.

| Item | Answer | One line |
|---|---|---|
| Kingambit, no Trick Room row | (i) | Spread `spe` 32 discounts the wanted vote, and a condition with no remaining dependent is omitted. |
| Rotom-Wash Electroweb | (i) | Electroweb is on the closed secondary-speed-control list. The M-8 kit has it. The M-7 kit had Protect. |
| Ariados strategic decision `None` | (i) | The M-8 kit is not redirection. `standard_physical_attacker` is not a reviewed strategic role. |
| Two hindering natures, and Kingambit plus Kangaskhan-Mega | (i) | Same Kingambit `spe` 32 discount. The wanted count is 1, so the class is `preferred`. |
| Live block inside the two-hindering test | executed | Kangaskhan-Mega Brave `spe` 0 and Torkoal Quiet `spe` 0. Trick Room is `essential` with two wanted dependents. The assertion holds. |

## 1. Kingambit

`assess_condition_resilience` in `recommender/condition_resilience.py`.

The declared build's Trick Room mechanism is the same on both files: `benefits_from`, importance `wanted`, `present` false, kind `teammate_condition_benefit`. M-8 spread is `spe` 32, `hp` 2, nature Adamant, item Chople Berry, moves Kowtow Cleave, Sucker Punch, Iron Head, Protect. M-7 spread is `spe` 0, `hp` 32, same nature, item, and moves.

`_discount_tr_wanted` (line 630) returns true when `spe` is greater than 0. The wanted dependent is then skipped (line 688). Provider count is 0. Needed is 0. Wanted is 0. The function `continue`s and emits no row (lines 711–712). On M-7 the wanted vote stays, so the row is Trick Room, `preferred`, 0 providers, 1 dependent.

That is the rule. It is not a defect in the branch. The plain role on both files is `standard_physical_attacker`. The empty row appears when the test forces `user_role="trick_room_sweeper"`, and when the other tests build the report from that same usage spread.

M-8 Garchomp-Mega plus this Kingambit produced Sand only, because both spreads have `spe` 32, so neither keeps a wanted Trick Room vote. Goodra's and Ampharos's pinned M-B moves still match. Their `StopIteration` is this missing row, not their own kits.

## 2. The other cases

Rotom-Wash. `_SECONDARY_SPEED_CONTROL_MOVES` in `recommender/anchor_roles.py` (line 578) includes `electroweb`. A kit move on that list is emitted as `secondary_speed_control` (line 837). M-8 moves are Hydro Pump, Thunderbolt, Will-O-Wisp, Electroweb. M-7 moves are Hydro Pump, Will-O-Wisp, Thunderbolt, Protect. Emitting the control for Electroweb is the designed rule. The test also pins the old move set and asserts Electroweb is absent, so updating only the set does not make it pass.

Ariados. M-7 role `redirection`, moves Protect, String Shot, Megahorn, Rage Powder. M-8 role `standard_physical_attacker`, moves Protect, Sucker Punch, Poison Jab, First Impression. `target_role_from_strategic_evidence` (`recommender/slot_fill_target_role.py` 63–88) returns `None` when the role is not in the reviewed map, or when the anchor has no matching mechanism or compendium row. `standard_physical_attacker` is not in that map. Redirection has nothing to match on the M-8 kit. Compared with M-7, which is beyond the failing line and was read for this cause.

Two hindering natures, and Kingambit plus Kangaskhan-Mega. Same discount. Goodra's spread `spe` is 0, so Goodra still votes. Kingambit does not. Wanted count is 1. `MIN_WANTED_DEPENDENTS_FOR_ESSENTIAL` is 2 (`condition_types.py` 23), so the class is `preferred`, not `essential`. Kangaskhan-Mega is Brave with `spe` 0 and still votes. Kingambit does not. Same count, same class. These are the Kingambit cause, plus the other partner still voting.

The live block was not executed in follow-up 55. It was executed here. Both natures match the `if`, and the report is `essential` with Kangaskhan-Mega and Torkoal wanted. That assertion does not fail on M-8. The test fails earlier, on Kingambit plus Goodra.

## 3. Data coupling

All 24 read the repo's usage or legality files. None of them substitute a fixture for the ladder row under test. Count: live 24, fixture 0.

The 12 group-(c) tests read that live build while the assertion is a rule (a Trick Room row, a wanted count, Electroweb as speed control, or a strategic decision). Goodra and Ampharos also pin an M-B move set. Those move asserts still match. Their failure is the Kingambit row from the M-C file. The other 12 failures pin a ladder value, so the live read is the subject of the test.

## 4. Frozen arm state

No. None of the three manifests lists `data/usage/champions-reg-mc.ingame_doubles.v1.json` or `pins_manifest.json`.

- `scripts/eval/part_g_v4/FROZEN_MANIFEST.json`: the file table has no usage path. Hashes match this tree.
- PRE-RS-ARM is `FROZEN_MANIFEST_ARM_STATE.json`. Its file table has no usage path. Eight listed files have already drifted, as the arm inventory records. That drift is not the usage file.
- `FROZEN_MANIFEST_ARM_V2.json` hashes `derived_keys.json`, `claim_battery_v4.json`, and `false_legal_battery_v4.json` (lines 20–22). Those bytes still match. They do not include the usage file. A later key cut that rewrote them would change this freeze. A re-pin that only moves the usage pin does not, by itself, edit those three files.

The PRE-MD-CLAIM and PRE-RS-ARM sections in `docs/pre_registration.md` cite the key and battery hashes. Those hashes are unchanged. Not checked: every sentence of those sections for a pasted usage blob id.
