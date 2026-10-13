/**
 * POST /calculate/moves shared-side batch (cap 32).
 */
import assert from 'node:assert/strict';
import {describe, it} from 'node:test';
import {
  runCalculate,
  runCalculateMovesBatch,
} from '../../services/calc/handlers.js';
import {RECOIL_NOT_IMPLEMENTED} from '../../services/calc/recoil.js';

const ATK = {
  species: 'Infernape',
  ability: 'Blaze',
  nature: 'Adamant',
  evs: {atk: 32},
} as const;

const DEF = {
  species: 'Primarina',
  ability: 'Torrent',
  evs: {hp: 32},
} as const;

describe('runCalculateMovesBatch', () => {
  it('matches N singles entry-by-entry including recoilHp', () => {
    const moves = ['Flare Blitz', 'Close Combat', 'U-turn'];
    const batch = runCalculateMovesBatch({
      attacker: {...ATK},
      defender: {...DEF},
      moves,
    });
    assert.ok(Array.isArray(batch));
    assert.equal(batch.length, 3);
    for (let i = 0; i < moves.length; i++) {
      const single = runCalculate({
        attacker: {...ATK},
        defender: {...DEF},
        move: moves[i]!,
      });
      const entry = batch[i]!;
      assert.equal(entry.move, moves[i]);
      assert.ok(!('error' in entry));
      if ('error' in entry) return;
      assert.deepEqual(entry.damageRange, single.damageRange);
      assert.deepEqual(entry.raw.damage, single.raw.damage);
      assert.deepEqual(entry.recoilHp, single.recoilHp);
    }
    assert.ok(Array.isArray((batch[0] as {recoilHp: unknown}).recoilHp));
    assert.equal(
      (batch[1] as {recoilHp: unknown}).recoilHp,
      RECOIL_NOT_IMPLEMENTED,
    );
  });

  it('one failing move (spread without gameType) leaves others OK', () => {
    // Unknown move names soft-zero; empty field + spread move throws gameType.
    const batch = runCalculateMovesBatch({
      attacker: {...ATK},
      defender: {...DEF},
      field: {},
      moves: ['Flare Blitz', 'Earthquake', 'Mach Punch'],
    });
    assert.ok(Array.isArray(batch));
    assert.ok(!('error' in batch[0]!));
    assert.ok('error' in batch[1]!);
    assert.match((batch[1] as {error: string}).error, /gameType/);
    assert.ok(!('error' in batch[2]!));
  });

  it('immune / zero-damage entry OK', () => {
    const batch = runCalculateMovesBatch({
      attacker: {
        species: 'Tauros',
        ability: 'Intimidate',
        nature: 'Adamant',
        evs: {atk: 32},
      },
      defender: {species: 'Mimikyu', ability: 'Disguise', evs: {hp: 32}},
      moves: ['Double-Edge', 'Earthquake'],
    });
    assert.ok(Array.isArray(batch));
    const de = batch[0]!;
    assert.ok(!('error' in de));
    if ('error' in de) return;
    assert.equal(de.damageRange[1], 0);
    assert.equal(de.recoilHp, 0);
  });

  it('preserves move order', () => {
    const moves = ['Mach Punch', 'Flare Blitz', 'U-turn'];
    const batch = runCalculateMovesBatch({
      attacker: {...ATK},
      defender: {...DEF},
      moves,
    }) as {move: string}[];
    assert.deepEqual(
      batch.map((e) => e.move),
      moves,
    );
  });

  it('over-cap → whole-call error', () => {
    const moves = Array.from({length: 33}, (_, i) =>
      i === 0 ? 'Flare Blitz' : 'Mach Punch',
    );
    const result = runCalculateMovesBatch({
      attacker: {...ATK},
      defender: {...DEF},
      moves,
    });
    assert.ok(!Array.isArray(result));
    assert.ok('error' in result);
    assert.match(result.error, /exceeds cap 32/);
  });
});
