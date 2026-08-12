/**
 * Unknown species/item must be a stable {error}, not a TypeError and not [0, 0].
 */
import assert from 'node:assert/strict';
import {describe, it} from 'node:test';
import {
  runCalculate,
  runCalculateBatch,
  runCalculateSafe,
} from '../../services/calc/handlers.js';

const PELIPPER = {
  species: 'Pelipper',
  ability: 'Drizzle',
  item: 'Focus Sash',
  nature: 'Modest',
  evs: {hp: 2, atk: 0, def: 0, spa: 32, spd: 0, spe: 32},
} as const;

const GARCHOMP = {
  species: 'Garchomp',
  ability: 'Rough Skin',
  item: 'Life Orb',
  nature: 'Jolly',
  evs: {hp: 2, atk: 32, def: 0, spa: 0, spd: 0, spe: 32},
} as const;

const KINGAMBIT = {
  species: 'Kingambit',
  ability: 'Defiant',
  item: 'Black Glasses',
  nature: 'Adamant',
  evs: {hp: 32, atk: 32, def: 0, spa: 0, spd: 2, spe: 0},
} as const;

describe('unknown Champions identifiers', () => {
  it('display-name Maushold Family of Four is a stable species error, not [0, 0]', () => {
    const result = runCalculateSafe({
      attacker: PELIPPER,
      defender: {species: 'Maushold Family of Four', item: 'Wide Lens'},
      move: 'Hurricane',
    });
    assert.deepEqual(result, {
      error: 'unknown Champions species: Maushold Family of Four',
    });
  });

  it('Assault Vest is a stable item error, not megaStone TypeError', () => {
    const result = runCalculateSafe({
      attacker: GARCHOMP,
      defender: {...KINGAMBIT, item: 'Assault Vest'},
      move: 'Earthquake',
    });
    assert.deepEqual(result, {error: 'unknown Champions item: Assault Vest'});
  });

  it('Pelipper Hurricane vs Garchomp is unaffected', () => {
    const result = runCalculate({
      attacker: PELIPPER,
      defender: GARCHOMP,
      move: 'Hurricane',
    });
    assert.ok(result.damageRange[1] > 0);
  });

  for (const species of ['Maushold-Four', 'mausholdfour'] as const) {
    it(`${species} is a valid calc species`, () => {
      const result = runCalculate({
        attacker: PELIPPER,
        defender: {species, item: 'Wide Lens'},
        move: 'Hurricane',
      });
      assert.ok(result.damageRange[1] > 0, species);
    });
  }

  it('runCalculate throws the stable species error', () => {
    assert.throws(
      () =>
        runCalculate({
          attacker: PELIPPER,
          defender: {species: 'Maushold Family of Four'},
          move: 'Hurricane',
        }),
      {message: 'unknown Champions species: Maushold Family of Four'},
    );
  });

  it('batch keeps the error row; does not drop it or turn it into [0, 0]', () => {
    const rows = runCalculateBatch([
      {attacker: PELIPPER, defender: GARCHOMP, move: 'Hurricane'},
      {
        attacker: PELIPPER,
        defender: {species: 'Maushold Family of Four'},
        move: 'Hurricane',
      },
    ]);
    assert.equal(rows.length, 2);
    assert.ok(!('error' in rows[0]));
    assert.ok(rows[0].damageRange[1] > 0);
    assert.deepEqual(rows[1], {
      error: 'unknown Champions species: Maushold Family of Four',
    });
  });

  for (const species of [
    'mausholdfour',
    'vivillonfancy',
    'Basculegion',
    'Ninetales-Alola',
    'Floette-Eternal',
  ] as const) {
    it(`${species} calc-verifies with non-zero damage`, () => {
      const result = runCalculate({
        attacker: PELIPPER,
        defender: {species},
        move: 'Hurricane',
      });
      assert.ok(!('error' in result));
      assert.ok(result.damageRange[1] > 0, species);
    });
  }
});
