/**
 * Legitimate zero-damage (type immunity / status) must be CalcSuccess, not
 * kochance's "damage[damage.length - 1] === 0." error.
 */
import assert from 'node:assert/strict';
import {describe, it} from 'node:test';
import {runCalculate, runCalculateBatch} from '../../services/calc/handlers.js';

const ARCHALUDON = {
  species: 'Archaludon',
  ability: 'Stamina',
  item: 'Leftovers',
  nature: 'Modest',
  evs: {hp: 252, atk: 0, def: 0, spa: 252, spd: 4, spe: 0},
  moves: ['Electro Shot', 'Dragon Pulse', 'Flash Cannon', 'Aura Sphere'],
} as const;

const GARCHOMP = {
  species: 'Garchomp',
  ability: 'Rough Skin',
  item: 'Life Orb',
  nature: 'Jolly',
  evs: {hp: 4, atk: 252, def: 0, spa: 0, spd: 0, spe: 252},
  moves: ['Earthquake', 'Dragon Claw', 'Rock Slide', 'Protect'],
} as const;

function assertZeroSuccess(result: ReturnType<typeof runCalculate>) {
  assert.deepEqual(result.damageRange, [0, 0]);
  assert.equal(result.koChance, '');
  assert.equal(result.raw.kochance.n, 0);
  assert.equal(result.raw.kochance.text, '');
}

describe('legitimate zero-damage', () => {
  for (const species of ['Garchomp', 'Excadrill', 'Rhyperior'] as const) {
    it(`Electro Shot vs ${species} is [0, 0] success`, () => {
      assertZeroSuccess(
        runCalculate({
          attacker: ARCHALUDON,
          defender: {species},
          move: 'Electro Shot',
        }),
      );
    });
  }

  for (const defender of [
    {species: 'Clefable'},
    {species: 'Hatterene'},
    {species: 'Gardevoir-Mega', item: 'Gardevoirite'},
    {species: 'Mawile-Mega', item: 'Mawilite'},
  ] as const) {
    it(`Dragon Claw vs ${defender.species} is [0, 0] success`, () => {
      assertZeroSuccess(
        runCalculate({
          attacker: GARCHOMP,
          defender,
          move: 'Dragon Claw',
        }),
      );
    });
  }

  it('Wide Guard is [0, 0] success', () => {
    assertZeroSuccess(
      runCalculate({
        attacker: GARCHOMP,
        defender: {species: 'Clefable'},
        move: 'Wide Guard',
      }),
    );
  });

  it('Archaludon other moves vs Garchomp are non-zero', () => {
    for (const move of ['Dragon Pulse', 'Flash Cannon', 'Aura Sphere'] as const) {
      const result = runCalculate({
        attacker: ARCHALUDON,
        defender: GARCHOMP,
        move,
      });
      assert.ok(result.damageRange[1] > 0, `${move} max damage`);
    }
  });

  it('Archaludon kit vs Garchomp batch: Electro Shot zero, rest damage', () => {
    const moves = ARCHALUDON.moves;
    const rows = runCalculateBatch(
      moves.map((move) => ({
        attacker: ARCHALUDON,
        defender: GARCHOMP,
        move,
      })),
    );
    assert.equal(rows.length, 4);
    const electro = rows[0];
    assert.ok(!('error' in electro));
    assert.deepEqual(electro.damageRange, [0, 0]);
    for (let i = 1; i < rows.length; i++) {
      const row = rows[i];
      assert.ok(!('error' in row), moves[i]);
      assert.ok(row.damageRange[1] > 0, moves[i]);
    }
  });
});
