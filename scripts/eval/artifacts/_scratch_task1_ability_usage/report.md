# Task 1 ability-usage scratch demo

Regulation: `champions-reg-mc`

## Spotlight

```json
{
  "Indeedee": {
    "tier": "Excellent",
    "basis": "psychic_terrain_priority_denial",
    "notes": "bulk HP/Def/SpD=60/55/95; Psychic Terrain priority denial \u2014 Psychic Surge (On switch-in, this Pokemon summons Psychic Terrain.) (grounded gate: types + ability; items e.g. Air Balloon ignored)"
  },
  "Indeedee-F": {
    "tier": "Excellent",
    "basis": "psychic_terrain_priority_denial",
    "notes": "bulk HP/Def/SpD=70/65/105; Psychic Terrain priority denial \u2014 Psychic Surge (On switch-in, this Pokemon summons Psychic Terrain.) (grounded gate: types + ability; items e.g. Air Balloon ignored)"
  },
  "Kingambit": {
    "tier": "Good",
    "basis": "good_calc_both_branches",
    "notes": "damage_score=1.254 raw=1.003 floor=1.270 excellent_exec=False"
  },
  "Vivillon": {
    "tier": "Excellent",
    "basis": "secondary_stack",
    "has_friend_guard_trait": false
  }
}
```

## IG vs SD modal disagreements (5)

No TR candidates or weather/terrain setters on the disagreement list under current max(ig,sd) modal. No tie-break change proposed.

| Species | IG modal | SD modal | Merged |
|---|---|---|---|
| Dragapult | infiltrator | clearbody | clearbody |
| Heliolisk | dryskin | solarpower | dryskin |
| Infernape | ironfist | blaze | blaze |
| Mudsdale | stamina | innerfocus | stamina |
| Salazzle | corrosion | oblivious | corrosion |

## Non-modal ≥10% grants (tier assumes granting ability)

| Species | Path | Granting | Modal |
|---|---|---|---|
| Sandaconda | sand_spit | sandspit | sandveil |
| Farfetch’d | tr_priority_denial | innerfocus | defiant |
| Mudsdale | tr_priority_denial | innerfocus | stamina |
| Salazzle | tr_taunt_denial | oblivious | corrosion |
| Slowbro | tr_taunt_denial | oblivious | regenerator |
| Slowking | tr_taunt_denial | oblivious | regenerator |

## Vivillon Excellent path (not Friend Guard)

Friend Guard share is below the 10% membership floor, so it is absent from
`_usage_ability_map` and is not an admit/excellence ability path.
Vivillon stays Excellent via `excellence_basis=secondary_stack`: usage-proven
Rage Powder delivery plus closed Excellent secondary **moves** Tailwind and
Light Screen (`_REDIRECTION_EXCELLENT_SECONDARY_MOVES`). That path is
move-usage only — it does **not** rely on a non-modal ability.

## Membership churn (modal-only admit vs split ≥10%) — all 18

| Category | Modal-only n | Split n | Added by split | Dropped by split |
|---|---:|---:|---|---|
| bulk_up_attacker | 38 | 38 | — | — |
| calm_mind_attacker | 34 | 34 | — | — |
| dragon_dance_attacker | 15 | 15 | — | — |
| iron_defense_body_press | 27 | 27 | — | — |
| nasty_plot_attacker | 22 | 22 | — | — |
| redirection | 9 | 9 | — | — |
| screens_support | 30 | 30 | — | — |
| sleep_status_spreader | 17 | 17 | — | — |
| swords_dance_attacker | 37 | 37 | — | — |
| tailwind_setter | 26 | 26 | — | — |
| terrain_setter_electric | 2 | 2 | — | — |
| terrain_setter_grassy | 2 | 2 | — | — |
| terrain_setter_psychic | 3 | 3 | — | — |
| trick_room_setter | 37 | 37 | — | — |
| weather_setter_rain | 7 | 7 | — | — |
| weather_setter_sand | 4 | 5 | Sandaconda | — |
| weather_setter_snow | 6 | 6 | — | — |
| weather_setter_sun | 8 | 8 | — | — |

## Before/after (full legal + flinch-only → split + Psychic Terrain) — all 18

### bulk_up_attacker (38 → 38)
- (no tier/basis changes)

### calm_mind_attacker (34 → 34)
- (no tier/basis changes)

### dragon_dance_attacker (15 → 15)
- (no tier/basis changes)

### iron_defense_body_press (27 → 27)
- (no tier/basis changes)

### nasty_plot_attacker (22 → 22)
- (no tier/basis changes)

### redirection (9 → 9)
- Vivillon: Excellent/ally_mitigation → Excellent/secondary_stack

### screens_support (30 → 30)
- (no tier/basis changes)

### sleep_status_spreader (17 → 17)
- (no tier/basis changes)

### swords_dance_attacker (37 → 37)
- (no tier/basis changes)

### tailwind_setter (26 → 26)
- (no tier/basis changes)

### terrain_setter_electric (2 → 2)
- (no tier/basis changes)

### terrain_setter_grassy (2 → 2)
- (no tier/basis changes)

### terrain_setter_psychic (3 → 3)
- (no tier/basis changes)

### trick_room_setter (37 → 37)
- Indeedee: Excellent/flinch_denial → Excellent/psychic_terrain_priority_denial
- Indeedee-F: Acceptable/unprotected → Excellent/psychic_terrain_priority_denial

### weather_setter_rain (7 → 7)
- (no tier/basis changes)

### weather_setter_sand (5 → 5)
- (no tier/basis changes)

### weather_setter_snow (6 → 6)
- (no tier/basis changes)

### weather_setter_sun (8 → 8)
- (no tier/basis changes)

