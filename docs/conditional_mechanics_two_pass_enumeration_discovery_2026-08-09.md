# Conditional mechanics — two grounded enumeration passes (discovery, 2026-08-09)

**Status:** Discovery / design only. No implementation in this pass.

**Revises:** the single-source “scan `@smogon/calc` for special-cased mechanics” framing.
Calc remains Pass 1’s grounded source for **damage-math** special cases, but it is a static
damage calculator, not a battle simulator — it structurally will not encode turn-flow /
battle-state mechanics (semi-invulnerability, multi-turn locks, forced switch, etc.).
Missing those from Pass 1 is not a sweep failure.

**Deferred-from:** master log backlog item “move/ability conditional mechanics (Electro Shot
→ Rain, Liquid Voice, Freeze-Dry, Phantom Force)” and the domain edges in
[`docs/slot_fill_flow_discovery_2026-08-08.md`](slot_fill_flow_discovery_2026-08-08.md)
§Potential domain dependency edges.

---

## Verdict (read this first)

| Question | Answer |
|----------|--------|
| **Pass 1 source exists?** | **Yes.** Vendored Champions path: `vendor/smogon-calc/dist/mechanics/champions.js` (+ shared `util.js`). Routed as `MECHANICS[0]` / gen `0` in `vendor/smogon-calc/dist/calc.js`. |
| **Pass 2 source exists in this project today?** | **Yes.** [`data/moves/flags.v1.json`](../data/moves/flags.v1.json) (Champions-effective extract). Consumers not yet wired. |
| **Phantom Force in Pass 1?** | **No** (expected). |
| **Phantom Force in Pass 2?** | **Yes** — `flags.charge` + `breaksProtect` in `flags.v1.json`. |
| **Electro Shot / Solar Beam / Solar Blade in Pass 1?** | **Yes** (confirm shipped in calc; do not re-propose). |
| **Liquid Voice / Freeze-Dry source?** | **Pass 1** (type / effectiveness math inside calc). Not Pass 2. |

**Residual limitation (both passes):** even a complete Pass 1 scan plus a future complete
Pass 2 flag extract is **not** a logical proof of completeness. A mechanic that is neither a
calc damage-math special case nor represented on ingested move flags can still matter to
recommender reasoning (e.g. scripted `onTryMove` / volatile behaviors with no flag, item
overrides like Power Herb, doubles-only positioning heuristics). Do not treat these
inventories as exhaustive.

---

## Out of scope (unchanged)

- Implementation, ingest pipelines, recommender feature work, tests, or ADR amendments.
- Anecdote / memory-based move lists when a grounded source is missing (especially Pass 2).
- Scanning `gen789.js` / non-Champions calc paths as if they were Reg M-B truth (Champions
  uses `calculateChampions`; e.g. Punk Rock sound modifiers exist in `gen789.js` but **not**
  in `champions.js`, and Punk Rock has **no** Reg M-B-legal holder in the legality snapshot).
- Claiming battle-simulator completeness from a damage calculator.
- Re-proposing Electro Shot / Solar Beam / Solar Blade damage-math handling already present
  in calc (and charge-instant weather already shipped in `recommender/matchup.py` via
  hand-curated frozensets — separate from this enumeration).

---

## Method

**Pass 1.** Enumerate `move.named` / `move.originalName` / `switch (move.name)` / fixed-damage
helpers and ability branches in `champions.js` + `getMoveEffectiveness` /
`handleFixedDamageMoves` in `util.js`. Filter moves to Reg M-B via
`is_species_legal` + `resolve_learnset` + `moves[id].is_nonstandard is None` on
`data/legality/champions.v1.json` (314 legal species → 496 legal moves). Filter abilities to
those appearing on at least one legal species.

**Pass 2.** Inspect every committed move-shaped dataset the recommender / extract scripts
actually produce for structured battle-flow flags (`charge`, `recharge`, `protect`,
`bypassprotect` / `breaksProtect`, `sound`, forced-switch / `forceSwitch`, locked-move /
`volatileStatus`, etc.).

**Triage labels**

- **pure-damage-math** — changes a number (or fails a calc) once the hit is assumed to land
  this turn; does not by itself change turn timing / positioning / coverage *identity*.
- **recommender-reasoning-relevant** — changes what the move/ability *is* for team or
  matchup reasoning (type conversion, SE exceptions that open coverage roles, fail
  conditions, spread/spread identity, or — for Pass 2 by construction — turn-flow).

---

## Pass 2 gate (critical)

### Does Pass 2’s data source exist today?

**Yes (as of ingest).** Sibling artifact [`data/moves/flags.v1.json`](../data/moves/flags.v1.json)
— not legality `moves` rows (those remain slim). See Pass 2 inventory below.

| Candidate | What it carries | Battle-flow flags? |
|-----------|-----------------|--------------------|
| `data/moves/flags.v1.json` | Champions-effective move flags + `breaksProtect` / switch / `volatileStatus` | **Yes — Pass 2 source** |
| `data/legality/champions.v1.json` → `moves` | `id`, `name`, `type`, `category`, `basePower`, `is_nonstandard` only | Still none (by design) |
| `@smogon/calc` `MoveFlags` | damage-math flags only | Not Pass 2 |
| `recommender/matchup.py` charge/recharge frozensets | hand-frozen subset | Superseded as inventory source by `flags.v1.json` |

**Phantom Force:** grounded in Pass 2 via `flags.charge` (+ `breaksProtect`).

---

## Pass 1 inventory — calc special-cased damage-math (Reg M-B filtered)

**Source files:** `vendor/smogon-calc/dist/mechanics/champions.js`,
`vendor/smogon-calc/dist/mechanics/util.js`.

Illegal / non-learnset special cases seen in source but **excluded** from the Reg M-B
inventory below: Dragon Rage, Sonic Boom, Nature Power, Punishment, Smelling Salts,
Power-Up Punch (`is_nonstandard: "Past"`); Nihil Light (`"Future"`). Storm Drain / Water Veil
/ Slow Start appear in Champions ability lists but have **no** legal species holder in the
current snapshot — noted only as dead code paths, not inventory rows.

### A. Named-move special cases (legal)

| Move | Calc behavior (citation) | Triage |
|------|--------------------------|--------|
| **Electro Shot** | Pre-damage `+1` SpA (Contrary-aware) `champions.js:18-21`; Sheer Force treats as secondary-bearing `champions.js:472-473` | mostly **pure-damage-math**; Rain skip-charge is **not** in calc (shipped separately in `matchup.py`) |
| **Meteor Beam** | Same SpA boost as Electro Shot `champions.js:18-21` | **pure-damage-math** (charge delay = Pass 2) |
| **Solar Beam**, **Solar Blade** | BP ×½ under Rain/Sand/Hail/Snow unless Mega Sol `champions.js:426-430` | **pure-damage-math** for the half-power; charge / Sun instant-fire = Pass 2 / already in `matchup.py` |
| **Freeze-Dry** | vs Water → effectiveness `2` `util.js:181-182` (`getMoveEffectiveness`) | **recommender-reasoning-relevant** (coverage identity vs Water) |
| **Flying Press** | multiplies Flying chart into effectiveness `util.js:192-194` | **recommender-reasoning-relevant** (dual-type attack) |
| **Weather Ball** | type from weather / Mega Sol `champions.js:63-72`; BP ×2 if weather or Mega Sol `champions.js:348-350` | **recommender-reasoning-relevant** (type identity) + damage-math |
| **Terrain Pulse** | type from terrain if grounded `champions.js:74-86`; BP ×2 if grounded+terrain `champions.js:352-354` | **recommender-reasoning-relevant** + damage-math |
| **Liquid Voice** *(ability)* + sound moves | Normal→ not applicable: sound moves become Water `champions.js:130-145` | **recommender-reasoning-relevant** (coverage identity; e.g. Hyper Voice) |
| Aerilate / Dragonize / Pixilate / Refrigerate | Normal → Flying/Dragon/Fairy/Ice + ate BP mod `champions.js:124-145`, `493-495` | **recommender-reasoning-relevant** (type identity) + damage-math |
| **Expanding Force** | on Psychic Terrain + grounded: target `allAdjacentFoes`, BP ×1.5 `champions.js:415-418` | **recommender-reasoning-relevant** (spread identity in doubles) |
| **Rising Voltage** | BP ×2 if defender grounded on Electric Terrain `champions.js:356-358` | mostly **pure-damage-math**; terrain dependence soft signal |
| **Misty Explosion** | BP ×1.5 if grounded on Misty `champions.js:421` | **pure-damage-math** |
| **Grav Apple** | BP ×1.5 under Gravity `champions.js:422` | **pure-damage-math** |
| **Steel Roller** | fails (0 dmg) with no terrain `champions.js:161` | **recommender-reasoning-relevant** (hard fail condition) |
| **Poltergeist** | fails without defender item `champions.js:162` | **recommender-reasoning-relevant** |
| **Knock Off** | BP ×1.5 when item removable `champions.js:420-424` (+ Sticky Hold / mega-stone resist logic) | **pure-damage-math** (item removal itself is battle-state, not modeled as flow here) |
| **Facade** / **Venoshock** / **Lash Out** | status / negative-boost BP doubles `champions.js:409-413` | **pure-damage-math** |
| **Hex** / **Infernal Parade** | BP ×2 if defender statused `champions.js:320-323` | **pure-damage-math** |
| **Payback** | BP ×2 if moving second `champions.js:293-295` | **pure-damage-math** (speed order assumed by calc inputs) |
| **Assurance** | BP ×2 vs Parental Bond child `champions.js:341-342` | **pure-damage-math** |
| **Acrobatics** | BP ×2 without item `champions.js:337-339` | **pure-damage-math** |
| Variable BP: Electro Ball, Gyro Ball, Low Kick, Grass Knot, Heavy Slam, Heat Crash, Stored Power, Power Trip, Eruption, Water Spout, Flail, Reversal, Triple Axel, Hard Press, Fling, Punishment*(excluded)* | `calculateBasePowerChampions` switch `champions.js:292-384` | **pure-damage-math** |
| **Body Press** | uses Defense (Wonder Room → SpD) as attack stat `champions.js:527-528` | **pure-damage-math** |
| **Foul Play** | uses defender’s Attack `champions.js:526` | **pure-damage-math** |
| **Shell Side Arm** | may become Physical + contact `champions.js:35-38` | **pure-damage-math** |
| **Aura Wheel** | type Electric / Dark by Morpeko forme `champions.js:88-94` | **recommender-reasoning-relevant** (forme-tied type) |
| **Raging Bull** | forme type + breaks screens `champions.js:96-108` | type: reasoning-relevant; screen break: soft reasoning |
| **Brick Break**, **Psychic Fangs** | clear Reflect / Light Screen / Aurora Veil `champions.js:110-113` | **recommender-reasoning-relevant** (doubles screen plan) |
| **Bulldoze**, **Earthquake** | BP ×½ on Grassy Terrain if defender grounded `champions.js:446-448` | **pure-damage-math** |
| **Final Gambit** | damage = attacker current HP `champions.js:195-197` | **pure-damage-math** |
| **Pain Split** | averaged-HP damage path `champions.js:46-50` | **pure-damage-math** |
| **Seismic Toss**, **Night Shade** | fixed = level `util.js:683-684` | **pure-damage-math** |
| **Clangorous Soul** | Soundproof does not block `champions.js:173` | **pure-damage-math** / ability interaction edge |
| Contact protect-break via **Unseen Fist** / **Piercing Drill** | `breaksProtect` path `champions.js:40-44`, `226-229` | borderline: protect bypass is turn-flow-adjacent but **encoded as damage continuing through protect in calc** → triage **recommender-reasoning-relevant** for protect plans; full protect-bypass *move* inventory still Pass 2 |

### B. Ability / field special cases (legal holders; grouped)

These are almost all **pure-damage-math** once types and field are fixed. Cite the primary
block; do not re-list every standard weather × type multiplier as a separate “mechanic
product.”

| Group | Examples (Reg M-B legal) | Citation | Triage |
|-------|--------------------------|----------|--------|
| Type immunities / absorbs (calc early-out) | Sap Sipper, Flash Fire, Dry Skin/Water Absorb, Lightning Rod/Motor Drive/Volt Absorb, Levitate/Eelevate, Bulletproof (bullet), Soundproof (sound), Queenly Majesty/Armor Tail (priority), Earth Eater | `champions.js:165-175` | **pure-damage-math** (matchup zero); Soundproof↔sound also needs Pass 2 sound inventory for *which moves* qualify outside calc |
| Attacker BP abilities | Technician, Mega Launcher (pulse), Strong Jaw (bite), Sharpness (slicing), Sheer Force, Sand Force, Analytic, Tough Claws, Rivalry, Reckless, Iron Fist (punch), Supreme Overlord, ate-abilities | `champions.js:452-509` | **pure-damage-math** |
| Attacker Atk/SpA abilities | Solar Power, Guts, Overgrow/Blaze/Torrent/Swarm, Plus/Minus, Flash Fire (on), Fire Mane, Water Bubble, Huge Power/Pure Power, Hustle | `champions.js:551-590` | **pure-damage-math**; Solar Power / weather soft **reasoning** for condition dependence |
| Defender Atk-halving / Def abilities | Thick Fat, Water Bubble (Fire), Purifying Salt (Ghost), Heatproof, Marvel Scale, Fur Coat | `champions.js:592-657` | **pure-damage-math** |
| Final modifiers | Sniper, Multiscale, Solid Rock/Filter, Friend Guard, berries/Ripen, screens/Aurora Veil | `champions.js:689-756` | **pure-damage-math** |
| Weather on base damage | Sun/Rain × Fire/Water (Mega Sol as Sun) `champions.js:672-681`; Sand Rock SpD / Snow Ice Def `champions.js:632-640` | **pure-damage-math** |
| Speed abilities (affect Payback / Analytic turnOrder) | Chlorophyll, Sand Rush, Swift Swim, Slush Rush, Surge Surfer, Choice Scarf, etc. | `util.js:131-171` | **pure-damage-math** inside calc; condition dependence is separate reasoning (condition-resilience work) |
| Mold Breaker vs ignorable defensive abilities | long list `champions.js:52-57` | **pure-damage-math** |
| Parental Bond | child hit recursion `champions.js:235-240` | **pure-damage-math** |
| Scrappy | Ghost immunity bypass for Normal/Fighting `util.js:175-176` via `champions.js:148` | **recommender-reasoning-relevant** (coverage vs Ghost) |
| Forecast / Klutz / Intimidate / Infiltrator / etc. | pre-calc field/stat setup `util.js` + `champions.js:9-24` | mostly **pure-damage-math** |

**Not in Champions calc (relevant negative):** Punk Rock sound damage modifiers exist in
`gen789.js` but **not** in `champions.js`; Punk Rock also has no legal Reg M-B holder —
Soundproof is the live sound interaction on the Champions path.

### C. Pass 1 triage summary

- **Vast majority → pure-damage-math.** Calc already applies them when the recommender calls
  calc; the backlog item is not “reimplement BP formulas.”
- **Recommender-reasoning-relevant subset (Pass 1):** Freeze-Dry; Liquid Voice (+ sound
  moves); ate-abilities; Weather Ball / Terrain Pulse / Aura Wheel / Raging Bull type
  identity; Flying Press; Expanding Force spread conversion; Steel Roller / Poltergeist fail
  conditions; Brick Break / Psychic Fangs / Raging Bull screen clear; Scrappy; protect-contact
  bypass abilities. Electro Shot / Solar Beam / Blade appear here for **damage-math** only;
  their **turn-economy / instant-weather** story is already partially shipped outside calc
  (`matchup.py`) and is otherwise Pass 2.

---

## Pass 2 inventory — turn-flow / battle-state flags

**Status:** **Ingested.** Machine source: [`data/moves/flags.v1.json`](../data/moves/flags.v1.json)
(produced by `npm run extract:move-flags` → `scripts/extract_moves/extract_flags.ts`).
Filter: Champions-effective `base ⊕ mods/champions` merge with `isNonstandard == null`
(`meta.filter: "champions-legal"`, 500 moves). Slightly wider than Pass 1’s learnset-legal
cut (~496); inventory cites this extract filter.

**Consumers:** not implemented in this pass — inventory only.

### Flag-family tables (citations = `flags.v1.json` move ids)

| Family | Moves (ids) | Triage |
|--------|-------------|--------|
| `flags.charge` | bounce, dig, dive, electroshot, fly, meteorbeam, **phantomforce**, skyattack, solarbeam, solarblade | **recommender-reasoning-relevant** (turn delay / semi-invuln positioning for Dig/Dive/Fly/Bounce/Phantom Force) |
| `flags.recharge` | blastburn, frenzyplant, gigaimpact, hydrocannon, hyperbeam, rockwrecker | **recommender-reasoning-relevant** (post-hit skip) |
| `breaksProtect` | feint, **phantomforce** | **recommender-reasoning-relevant** |
| `forceSwitch` | circlethrow, dragontail, roar, whirlwind | **recommender-reasoning-relevant** (phazing) |
| `selfSwitch` | batonpass, chillyreception, flipturn, partingshot, shedtail, uturn, voltswitch | **recommender-reasoning-relevant** (pivots) |
| `volatileStatus: lockedmove` | outrage, petaldance, ragingfury, thrash | **recommender-reasoning-relevant** |
| `volatileStatus: mustrecharge` | same six as `flags.recharge` | bookkeeping twin of recharge |
| `flags.sound` (24) | alluringvoice, boomburst, bugbuzz, clangingscales, clangoroussoul, dragoncheer, eeriespell, healbell, howl, hypervoice, metalsound, nobleroar, partingshot, perishsong, psychicnoise, roar, round, screech, sing, snarl, snore, sparklingaria, torchsong, uproar | **recommender-reasoning-relevant** for Soundproof / Liquid Voice move inventory |
| `flags.protect` | 389 moves | mostly bookkeeping; useful when intersecting with bypass |

**Phantom Force:** present under `flags.charge` **and** `breaksProtect` — sanity check passed.

**Residual within flags:** semi-invulnerability is not a separate Showdown flag (scripted on
charge moves); Power Herb / other item overrides absent; `protect`-flag alone is not a
protect *move* inventory.

**Do not** treat hand-curated `_CHARGE_MOVES` / `_RECHARGE_MOVES` as the Pass 2 source — the
artifact above supersedes them as the grounded dataset (consumer migration is a follow-up).

---

## Revised sanity check

| Check | Result |
|-------|--------|
| Electro Shot in Pass 1 | **Yes** — SpA boost + Sheer Force special-case in `champions.js`. Rain skip-charge is **not** Pass 1; already shipped in `matchup.py` `_CHARGE_INSTANT_WEATHER`. Confirm done; do not re-propose. |
| Solar Beam / Solar Blade in Pass 1 | **Yes** — weather BP ×½ in `champions.js:426-430`. Charge / Sun instant in `matchup.py`, not calc. Confirm done; do not re-propose. |
| Phantom Force in Pass 1 | **No** — absent from Champions mechanics (correct: wrong source). |
| Phantom Force in Pass 2 | **Yes** — `phantomforce.flags.charge === 1` and `breaksProtect` in `flags.v1.json`. |
| Liquid Voice | **Pass 1** — `champions.js:130-145` type rewrite on `move.flags.sound`. Pass 2 sound list grounds which moves qualify. |
| Freeze-Dry | **Pass 1** — `util.js:181-182` effectiveness override. Not Pass 2. |

---

## Residual limitations (state plainly)

1. **Pass 1 ≠ battle flow.** Calc will never list Phantom Force-class mechanics no matter how
   thoroughly `champions.js` is scanned.
2. **Union still incomplete.** Mechanics that live only in Showdown scripts / volatiles /
   items (Power Herb, consecutive Outrage lock fatigue details, some Champions-only callbacks)
   can matter to reasoning without appearing in either grounded source.
3. **Pass 2 consumers not built.** Ingest + inventory only; wiring Phantom Force positioning
   (and siblings) into the recommender is a follow-up decision.
