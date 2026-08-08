/**
 * Field + Side golden tests for the calc HTTP service.
 *
 * Absolute ranges cross-checked 2026-07-26 against live
 * https://calc.pokemonshowdown.com/champions.html (Runtime.evaluate with
 * Generations.get(0) / same spreads) — independent of our vendored build:
 *   Doubles EQ [110,132]; Surf dry [75,88] / Rain [111,132].
 * Remaining terrain/screens goldens use the same engine path; doubles + weather
 * were the Champions-quirk risk cases and are the mandatory external locks.
 */
import assert from 'node:assert/strict';
import {describe, it} from 'node:test';
import {runCalculate, runCalculateSafe} from '../../services/calc/handlers.js';
import {createServer} from '../../services/calc/server.js';

const GARCHOMP = {
  species: 'Garchomp',
  nature: 'Jolly',
  evs: {hp: 2, atk: 32, def: 0, spa: 0, spd: 0, spe: 32},
} as const;

const KINGAMBIT = {
  species: 'Kingambit',
  nature: 'Adamant',
  evs: {hp: 32, atk: 32, def: 0, spa: 0, spd: 2, spe: 0},
} as const;

const GRENINJA = {
  species: 'Greninja',
  nature: 'Timid',
  evs: {spa: 32, spe: 32},
} as const;

const PIKACHU = {
  species: 'Pikachu',
  nature: 'Timid',
  evs: {spa: 32, spe: 32},
} as const;

/** Singles baseline — Garchomp EQ vs Kingambit. */
const EXPECTED_SINGLES_EQ: [number, number] = [150, 176];

/** Source: calc.pokemonshowdown.com/champions.html — Doubles EQ, same spreads. */
const EXPECTED_DOUBLES_EQ: [number, number] = [110, 132];

/** Source: calc.pokemonshowdown.com/champions.html — Greninja Surf dry vs Rain. */
const EXPECTED_SURF_DRY: [number, number] = [75, 88];
const EXPECTED_SURF_RAIN: [number, number] = [111, 132];

/** Pikachu Thunderbolt vs Kingambit — no terrain vs Electric Terrain. */
const EXPECTED_TB_DRY: [number, number] = [49, 58];
const EXPECTED_TB_ELECTRIC: [number, number] = [64, 76];

/** Garchomp Dragon Claw vs Kingambit — no terrain vs Misty Terrain (~half). */
const EXPECTED_DRAGON_CLAW_DRY: [number, number] = [29, 35];
const EXPECTED_DRAGON_CLAW_MISTY: [number, number] = [15, 18];

/** Reflect on defenderSide in Singles. */
const EXPECTED_REFLECT_EQ: [number, number] = [75, 88];

describe('Field goldens', () => {
  it('Doubles Earthquake: spread mod lowers damage vs Singles', () => {
    const result = runCalculate({
      attacker: GARCHOMP,
      defender: KINGAMBIT,
      move: 'Earthquake',
      field: {gameType: 'Doubles'},
    });
    assert.deepEqual(result.damageRange, EXPECTED_DOUBLES_EQ);
    assert.ok(result.damageRange[0] < EXPECTED_SINGLES_EQ[0]);
    assert.ok(result.damageRange[1] < EXPECTED_SINGLES_EQ[1]);
  });

  it('spread move with field but no gameType throws', () => {
    const result = runCalculateSafe({
      attacker: GARCHOMP,
      defender: KINGAMBIT,
      move: 'Earthquake',
      field: {},
    });
    assert.ok('error' in result);
    assert.match(result.error, /gameType/i);
  });

  it('Rain boosts Water move max damage vs dry field', () => {
    const dry = runCalculate({
      attacker: GRENINJA,
      defender: KINGAMBIT,
      move: 'Surf',
      field: {gameType: 'Singles'},
    });
    const rain = runCalculate({
      attacker: GRENINJA,
      defender: KINGAMBIT,
      move: 'Surf',
      field: {weather: 'Rain', gameType: 'Singles'},
    });
    assert.deepEqual(dry.damageRange, EXPECTED_SURF_DRY);
    assert.deepEqual(rain.damageRange, EXPECTED_SURF_RAIN);
    assert.ok(rain.damageRange[1] > dry.damageRange[1]);
  });

  it('Electric Terrain boosts grounded Electric move', () => {
    const none = runCalculate({
      attacker: PIKACHU,
      defender: KINGAMBIT,
      move: 'Thunderbolt',
      field: {gameType: 'Singles'},
    });
    const terrain = runCalculate({
      attacker: PIKACHU,
      defender: KINGAMBIT,
      move: 'Thunderbolt',
      field: {terrain: 'Electric', gameType: 'Singles'},
    });
    assert.deepEqual(none.damageRange, EXPECTED_TB_DRY);
    assert.deepEqual(terrain.damageRange, EXPECTED_TB_ELECTRIC);
    assert.ok(terrain.damageRange[1] > none.damageRange[1]);
  });

  it('Misty Terrain halves Dragon move damage', () => {
    const none = runCalculate({
      attacker: GARCHOMP,
      defender: KINGAMBIT,
      move: 'Dragon Claw',
      field: {gameType: 'Singles'},
    });
    const misty = runCalculate({
      attacker: GARCHOMP,
      defender: KINGAMBIT,
      move: 'Dragon Claw',
      field: {terrain: 'Misty', gameType: 'Singles'},
    });
    assert.deepEqual(none.damageRange, EXPECTED_DRAGON_CLAW_DRY);
    assert.deepEqual(misty.damageRange, EXPECTED_DRAGON_CLAW_MISTY);
    assert.ok(misty.damageRange[1] < none.damageRange[1]);
  });

  it('Reflect on defenderSide lowers physical damage in Singles', () => {
    const baseline = runCalculate({
      attacker: GARCHOMP,
      defender: KINGAMBIT,
      move: 'Earthquake',
      field: {gameType: 'Singles'},
    });
    const reflect = runCalculate({
      attacker: GARCHOMP,
      defender: KINGAMBIT,
      move: 'Earthquake',
      field: {gameType: 'Singles', defenderSide: {isReflect: true}},
    });
    assert.deepEqual(baseline.damageRange, EXPECTED_SINGLES_EQ);
    assert.deepEqual(reflect.damageRange, EXPECTED_REFLECT_EQ);
    assert.ok(reflect.damageRange[1] < baseline.damageRange[1]);
  });
});

describe('Field HTTP', () => {
  it('spread move with empty field returns 400', async () => {
    const server = createServer();
    await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
    const {port} = server.address() as {port: number};
    const base = `http://127.0.0.1:${port}`;

    try {
      const res = await fetch(`${base}/calculate`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          attacker: GARCHOMP,
          defender: KINGAMBIT,
          move: 'Earthquake',
          field: {},
        }),
      });
      assert.equal(res.status, 400);
      const body = await res.json();
      assert.match(body.error, /gameType/i);
    } finally {
      await new Promise<void>((resolve, reject) =>
        server.close((err) => (err ? reject(err) : resolve())),
      );
    }
  });

  it('attacker boosts raise Earthquake damage vs unboosted', () => {
    const plain = runCalculate({
      attacker: GARCHOMP,
      defender: KINGAMBIT,
      move: 'Earthquake',
      field: {gameType: 'Doubles'},
    });
    const boosted = runCalculate({
      attacker: {...GARCHOMP, boosts: {atk: 2}},
      defender: KINGAMBIT,
      move: 'Earthquake',
      field: {gameType: 'Doubles'},
    });
    assert.ok(boosted.damageRange[1] > plain.damageRange[1]);
  });
});
