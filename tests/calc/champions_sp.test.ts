/**
 * Champions SP + damage verification for the calc HTTP service.
 *
 * Stats golden: Showdown Champions calc (same fixtures as scratch/verify_pkmn_dmg_champions_sp.ts).
 * Damage golden: locked against https://calc.pokemonshowdown.com/champions.html (live page Runtime.evaluate
 * with Generations.get(0) / same spreads) — 150–176 EQ, guaranteed 2HKO. Follow-up: spot-check
 * Pikalytics/MunchStats when convenient.
 */
import assert from 'node:assert/strict';
import {describe, it} from 'node:test';
import {runCalculate, setsPack, setsUnpack, setsImport, setsExport} from '../../services/calc/handlers.js';
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

const EXPECTED_GARCHOMP = {hp: 185, atk: 182, def: 115, spa: 90, spd: 105, spe: 169};
const EXPECTED_KINGAMBIT = {hp: 207, atk: 205, def: 140, spa: 72, spd: 107, spe: 70};

/** Source: calc.pokemonshowdown.com/champions.html — Garchomp EQ vs Kingambit, spreads above. */
const EXPECTED_EQ_RANGE: [number, number] = [150, 176];
const EXPECTED_EQ_ROLLS = [
  150, 150, 152, 152, 156, 158, 158, 162, 162, 164, 168, 168, 170, 170, 174, 176,
];

describe('Champions SP via Generations.get(0)', () => {
  it('Garchomp EQ vs Kingambit: stats + damage match Showdown Champions calc', () => {
    const result = runCalculate({
      attacker: {...GARCHOMP},
      defender: {...KINGAMBIT},
      move: 'Earthquake',
    });
    assert.deepEqual(result.raw.stats.attacker, EXPECTED_GARCHOMP);
    assert.deepEqual(result.raw.stats.defender, EXPECTED_KINGAMBIT);
    assert.deepEqual(result.damageRange, EXPECTED_EQ_RANGE);
    assert.deepEqual(result.raw.range, EXPECTED_EQ_RANGE);
    assert.deepEqual(result.raw.damage, EXPECTED_EQ_ROLLS);
    assert.equal(result.koChance, 'guaranteed 2HKO');
    assert.equal(result.raw.kochance.text, 'guaranteed 2HKO');
    assert.equal(result.raw.kochance.n, 2);
    assert.equal(result.raw.kochance.chance, 1);
  });
});

describe('@pkmn/sets thin wrappers', () => {
  it('pack/unpack and import/export round-trip a set', () => {
    const set = {
      species: 'Garchomp',
      nature: 'Jolly',
      evs: {hp: 2, atk: 32, spe: 32},
      moves: ['Earthquake'],
    };
    const packed = setsPack(set);
    const unpacked = setsUnpack(packed);
    assert.equal(unpacked.species, 'Garchomp');

    const text = setsExport(set);
    const imported = setsImport(text);
    assert.equal(imported.species, 'Garchomp');
  });
});

describe('HTTP smoke', () => {
  it('GET /health and POST /calculate', async () => {
    const server = createServer();
    await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
    const {port} = server.address() as {port: number};
    const base = `http://127.0.0.1:${port}`;

    try {
      const health = await fetch(`${base}/health`);
      assert.equal(health.status, 200);
      assert.deepEqual(await health.json(), {status: 'ok'});

      const calc = await fetch(`${base}/calculate`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          attacker: GARCHOMP,
          defender: KINGAMBIT,
          move: 'Earthquake',
        }),
      });
      assert.equal(calc.status, 200);
      const body = await calc.json();
      assert.deepEqual(body.raw.stats.attacker, EXPECTED_GARCHOMP);
      assert.deepEqual(body.damageRange, EXPECTED_EQ_RANGE);
      assert.equal(body.koChance, 'guaranteed 2HKO');
    } finally {
      await new Promise<void>((resolve, reject) =>
        server.close((err) => (err ? reject(err) : resolve())),
      );
    }
  });
});
