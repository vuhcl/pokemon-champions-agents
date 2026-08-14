import assert from 'node:assert/strict';
import {describe, it} from 'node:test';
import {runCalculate} from '../../services/calc/handlers.js';

describe('moveOverrides.basePower', () => {
  const attacker = {
    species: 'Annihilape',
    evs: {hp: 4, atk: 32, spe: 32},
    boosts: {atk: 1},
    moves: ['Rage Fist'],
  } as const;
  const defender = {
    species: 'Garchomp',
    evs: {hp: 32, def: 32, spd: 32},
  } as const;

  it('Rage Fist default is snapshot 50 BP; override 100 BP raises damage', () => {
    const base = runCalculate({
      attacker,
      defender,
      move: 'Rage Fist',
      field: {gameType: 'Doubles'},
    });
    const scaled = runCalculate({
      attacker,
      defender,
      move: 'Rage Fist',
      field: {gameType: 'Doubles'},
      moveOverrides: {basePower: 100},
    });
    assert.ok(!('error' in base));
    assert.ok(!('error' in scaled));
    assert.ok(base.damageRange[1] > 0);
    assert.ok(scaled.damageRange[1] > base.damageRange[1]);
  });
});
