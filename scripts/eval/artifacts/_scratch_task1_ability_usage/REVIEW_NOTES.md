# Task 1 review notes (committed with demo)

## Vivillon still Excellent via secondary

Friend Guard is 4.777% on M-C (2.194% on M-B) vs Compound Eyes 96.3% — below the
10% membership floor, so Friend Guard is **not** in `_usage_ability_map` and is
not an admit or excellence ability path.

Vivillon remains Excellent with `excellence_basis=secondary_stack`:
- delivery: usage-proven Rage Powder
- Excellent secondary **moves**: Tailwind + Light Screen (closed
  `_REDIRECTION_EXCELLENT_SECONDARY_MOVES` allowlist)

That path is move-usage only. It does **not** use a non-modal ability.

## Test assertion changes (Task 1)

Policy: `_ABILITY_MEMBERSHIP_PCT_FLOOR = 10.0` (signed off). Old tests encoded
full-legal-slot ability credit; under the new policy those expectations are
wrong, so tests were updated — not the floor.

| Test | Change | Why |
|---|---|---|
| `test_taunt_denial_lands_good_not_excellent` | Slowbro Good/taunt → Acceptable/unprotected | M-B Oblivious 8% < 10%; old expectation assumed every legal ability |
| `test_taunt_denial_with_snapshot_usage_stays_good` | Slowbro Good → Acceptable; not in Good | Same M-B Oblivious floor |
| `test_redirection_good_learnset_only` | Assert Cute Charm **absent** from Clefable traits/notes | M-B Cute Charm ~4% < 10%; Clefable still admitted via Follow Me usage |
| `test_clefable_live_none_still_admitted_without_cute_charm` (renamed) | Assert no Cute Charm trait; still a member | Same floor; snapshot Follow Me admits without live CBD |

New file `test_ability_usage_tier.py` adds positive coverage (Indeedee terrain,
Vivillon FG excluded from usage map, Sandaconda Sand Spit grant, Kingambit Good).

## Task 3 membership delta (#248)

See `task3_presence_membership_delta.json` (copied from the Task 3 scratch audit).

Expected drops (all hit): Pinsir-Mega, Zoroark, Infernape, Lucario, Medicham,
Diggersby, Lycanroc-Dusk.

Expected keeps (all present): Rillaboom, Raichu-Mega-Y, Incineroar.

In-game-only mid-band admits (`0.1 ≤ pct < 1` with Showdown weight failing):
**count 0**.
