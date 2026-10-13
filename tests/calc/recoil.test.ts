/**
 * recoilHp: project-convention 1/3-of-dealt, per-hit. Not "the game rule."
 */
import assert from 'node:assert/strict';
import {describe, it} from 'node:test';
import {runCalculate} from '../../services/calc/handlers.js';
import {
  RECOIL_NOT_IMPLEMENTED,
  recoilOneThirdHp,
  resolveAbility,
  resolveDealtForHit,
  sumRecoilAcrossHits,
  buildInitialHitState,
  type HitResolutionState,
} from '../../services/calc/recoil.js';

describe('recoilOneThirdHp operator pins', () => {
  it('187→62, 186→62, 5→1, 1→1, 2→1, 0→0', () => {
    assert.equal(recoilOneThirdHp(187), 62);
    assert.equal(recoilOneThirdHp(186), 62);
    assert.equal(recoilOneThirdHp(5), 1);
    assert.equal(recoilOneThirdHp(1), 1);
    assert.equal(recoilOneThirdHp(2), 1);
    assert.equal(recoilOneThirdHp(0), 0);
  });
});

describe('resolveAbility', () => {
  it('Mega ignores plain ability; override wins', () => {
    const mega = resolveAbility({
      species: 'Kangaskhan-Mega',
      ability: 'Scrappy',
      dexAbility: 'Parental Bond',
    });
    assert.deepEqual(mega, {
      applied: 'Parental Bond',
      supplied: 'Scrappy',
      source: 'dex',
    });
    const ov = resolveAbility({
      species: 'Kangaskhan-Mega',
      ability: 'Scrappy',
      abilityOverride: 'Intimidate',
      dexAbility: 'Parental Bond',
    });
    assert.equal(ov.applied, 'Intimidate');
    assert.equal(ov.source, 'override');
  });

  it('non-Mega passes request ability', () => {
    const r = resolveAbility({
      species: 'Infernape',
      ability: 'Blaze',
      dexAbility: 'Blaze',
    });
    assert.equal(r.source, 'request');
    assert.equal(r.applied, 'Blaze');
  });
});

function baseState(over: Partial<HitResolutionState> = {}): HitResolutionState {
  return {
    curHP: 100,
    maxHP: 100,
    subHp: null,
    disguiseIntact: false,
    sashAvailable: false,
    sturdyAvailable: false,
    endure: false,
    ...over,
  };
}

describe('resolveDealtForHit / survival', () => {
  it('Sash, Sturdy, Endure alone agree on full-HP KO roll', () => {
    const roll = 200;
    for (const over of [
      {sashAvailable: true},
      {sturdyAvailable: true},
      {endure: true},
    ] as Partial<HitResolutionState>[]) {
      const s = baseState(over);
      assert.equal(
        resolveDealtForHit({
          roll,
          state: s,
          attackerAbility: 'Blaze',
          defenderAbility: 'Torrent',
          infiltrator: false,
        }),
        99,
      );
      assert.equal(s.curHP, 1);
    }
  });

  it('Endure leaves 1; at 1 HP → 0; Sub blocks Endure', () => {
    const s = baseState({endure: true, curHP: 50});
    assert.equal(
      resolveDealtForHit({
        roll: 40,
        state: s,
        attackerAbility: 'Blaze',
        defenderAbility: 'Torrent',
        infiltrator: false,
      }),
      40,
    );
    assert.equal(s.curHP, 10);

    const at1 = baseState({endure: true, curHP: 1});
    assert.equal(
      resolveDealtForHit({
        roll: 50,
        state: at1,
        attackerAbility: 'Blaze',
        defenderAbility: 'Torrent',
        infiltrator: false,
      }),
      0,
    );

    const sub = baseState({endure: true, subHp: 25, curHP: 100});
    assert.equal(
      resolveDealtForHit({
        roll: 40,
        state: sub,
        attackerAbility: 'Blaze',
        defenderAbility: 'Torrent',
        infiltrator: false,
      }),
      25,
    );
    assert.equal(sub.curHP, 100);
  });

  it('Disguise absorbs once; MB family does not', () => {
    const abs = baseState({disguiseIntact: true, maxHP: 160, curHP: 160});
    assert.equal(
      resolveDealtForHit({
        roll: 100,
        state: abs,
        attackerAbility: 'Blaze',
        defenderAbility: 'Disguise',
        infiltrator: false,
      }),
      0,
    );
    assert.equal(abs.disguiseIntact, false);
    assert.equal(abs.curHP, 160 - Math.floor(160 / 8));

    const mb = baseState({disguiseIntact: true, maxHP: 160, curHP: 160});
    assert.equal(
      resolveDealtForHit({
        roll: 100,
        state: mb,
        attackerAbility: 'Mold Breaker',
        defenderAbility: 'Disguise',
        infiltrator: false,
      }),
      100,
    );
  });

  it('Infiltrator bypasses Sub', () => {
    const s = baseState({subHp: 40});
    assert.equal(
      resolveDealtForHit({
        roll: 50,
        state: s,
        attackerAbility: 'Infiltrator',
        defenderAbility: 'Torrent',
        infiltrator: true,
      }),
      50,
    );
    assert.equal(s.subHp, 40);
  });
});

describe('sumRecoilAcrossHits PB Case A/B', () => {
  it('Case A: all 256 pairs equal floor((h1+h2)/3) when remainders allow', () => {
    // Rolls all ≡0 mod 3 ⇒ per-hit sum === floor((h1+h2)/3) for every pair.
    const hit1 = Array.from({length: 16}, (_, i) => 60 + i * 3);
    const hit2 = Array.from({length: 16}, (_, i) => 15 + i * 3);
    const init = buildInitialHitState({
      maxHP: 500,
      defenderAbility: 'Torrent',
    });
    const totals = sumRecoilAcrossHits({
      hits: [hit1, hit2],
      initial: init,
      attackerAbility: 'Parental Bond',
      defenderAbility: 'Torrent',
      infiltrator: false,
    }) as number[];
    const expected = new Set<number>();
    for (const a of hit1) {
      for (const b of hit2) {
        assert.equal(
          recoilOneThirdHp(a) + recoilOneThirdHp(b),
          Math.floor((a + b) / 3),
        );
        expected.add(Math.floor((a + b) / 3));
      }
    }
    assert.deepEqual(totals, [...expected].sort((x, y) => x - y));
    assert.equal(hit1.length * hit2.length, 256);
  });

  it('Case B: achievable set exactly {50,51} (Endure; fails if once-on-total)', () => {
    const init = buildInitialHitState({
      maxHP: 153,
      curHP: 153,
      endure: true,
      defenderAbility: 'Torrent',
    });
    const totals = sumRecoilAcrossHits({
      hits: [
        [153, 150],
        [30, 36],
      ],
      initial: init,
      attackerAbility: 'Parental Bond',
      defenderAbility: 'Torrent',
      infiltrator: false,
    }) as number[];
    // Once-on-total would collapse; per-hit Endure path yields both 50 and 51.
    assert.deepEqual(totals, [50, 51]);
  });

  it('Endure worked example: HP 153, hit1=123, hit2 capped 29 → recoil 50', () => {
    const init = buildInitialHitState({
      maxHP: 153,
      curHP: 153,
      endure: true,
      defenderAbility: 'Torrent',
    });
    const totals = sumRecoilAcrossHits({
      hits: [[123], [29]],
      initial: init,
      attackerAbility: 'Parental Bond',
      defenderAbility: 'Torrent',
      infiltrator: false,
    });
    // hit1 dealt 123 → 41; hp 30; hit2 endure min(29,29)=29 → 9; total 50
    assert.deepEqual(totals, [50]);
  });

  it('Sash + Parental Bond: hit1 sash-leaves-1, hit2 chips last HP', () => {
    const init = buildInitialHitState({
      maxHP: 100,
      item: 'Focus Sash',
      defenderAbility: 'Torrent',
    });
    assert.equal(init.sashAvailable, true);
    const totals = sumRecoilAcrossHits({
      hits: [[200], [50]],
      initial: init,
      attackerAbility: 'Parental Bond',
      defenderAbility: 'Torrent',
      infiltrator: false,
    });
    // hit1 sash: dealt 99 → 33; hp 1; hit2: dealt 1 (no endure) → 1; total 34
    // Wait without endure at 1hp: dealt=min(50,1)=1 → recoil 1
    assert.deepEqual(totals, [34]);
  });

  it('Substitute + Parental Bond: Sub absorbs hit1, hit2 after Sub breaks', () => {
    const init = buildInitialHitState({
      maxHP: 200,
      substitute: true,
      substituteHp: 40,
      defenderAbility: 'Torrent',
    });
    const totals = sumRecoilAcrossHits({
      hits: [[50], [30]],
      initial: init,
      attackerAbility: 'Parental Bond',
      defenderAbility: 'Torrent',
      infiltrator: false,
    });
    // hit1 vs sub 40: dealt 40 → 13; sub gone; hit2 dealt 30 → 10; total 23
    assert.deepEqual(totals, [23]);
  });
});

describe('runCalculate recoilHp live', () => {
  it('Flare Blitz vs Primarina: AR3-style capped rolls → floor/3', () => {
    const result = runCalculate({
      attacker: {
        species: 'Infernape',
        ability: 'Blaze',
        nature: 'Adamant',
        evs: {atk: 32},
      },
      defender: {
        species: 'Primarina',
        ability: 'Torrent',
        evs: {hp: 32},
      },
      move: 'Flare Blitz',
    });
    assert.ok(Array.isArray(result.raw.damage));
    const dmg = result.raw.damage as number[];
    assert.ok(Array.isArray(result.recoilHp));
    const rh = result.recoilHp as number[];
    assert.equal(rh.length, dmg.length);
    for (let i = 0; i < dmg.length; i++) {
      const dealt = Math.min(dmg[i]!, result.raw.stats.defender.hp!);
      assert.equal(rh[i], recoilOneThirdHp(dealt));
    }
    // Pin: if any roll is 187 into hp>=187 → 62
    const hp = result.raw.stats.defender.hp!;
    for (let i = 0; i < dmg.length; i++) {
      if (Math.min(dmg[i]!, hp) === 187) assert.equal(rh[i], 62);
    }
  });

  it('Head Smash / Wild Charge → not-implemented label', () => {
    const head = runCalculate({
      attacker: {
        species: 'Tyrantrum',
        ability: 'Strong Jaw',
        nature: 'Adamant',
        evs: {atk: 32},
      },
      defender: {species: 'Primarina', ability: 'Torrent', evs: {hp: 32}},
      move: 'Head Smash',
    });
    assert.equal(head.recoilHp, RECOIL_NOT_IMPLEMENTED);
    const wild = runCalculate({
      attacker: {
        species: 'Luxray',
        ability: 'Intimidate',
        nature: 'Adamant',
        evs: {atk: 32},
      },
      defender: {species: 'Primarina', ability: 'Torrent', evs: {hp: 32}},
      move: 'Wild Charge',
    });
    assert.equal(wild.recoilHp, RECOIL_NOT_IMPLEMENTED);
  });

  it('Rock Head → recoilHp 0', () => {
    const r = runCalculate({
      attacker: {
        species: 'Aerodactyl',
        ability: 'Rock Head',
        nature: 'Adamant',
        evs: {atk: 32},
      },
      defender: {species: 'Primarina', ability: 'Torrent', evs: {hp: 32}},
      move: 'Double-Edge',
    });
    assert.equal(r.recoilHp, 0);
  });

  it('Magic Guard → recoilHp 0', () => {
    const r = runCalculate({
      attacker: {
        species: 'Clefable',
        ability: 'Magic Guard',
        nature: 'Adamant',
        evs: {atk: 32},
      },
      defender: {species: 'Primarina', ability: 'Torrent', evs: {hp: 32}},
      move: 'Double-Edge',
    });
    assert.equal(r.recoilHp, 0);
  });

  it('Kangaskhan-Mega: no ability → Parental Bond; Scrappy recorded + dex PB', () => {
    const bare = runCalculate({
      attacker: {
        species: 'Kangaskhan-Mega',
        nature: 'Adamant',
        evs: {atk: 32},
      },
      defender: {species: 'Primarina', ability: 'Torrent', evs: {hp: 32}},
      move: 'Double-Edge',
    });
    assert.equal(bare.abilityResolution?.attacker?.applied, 'Parental Bond');
    assert.ok(Array.isArray(bare.raw.damage) && Array.isArray((bare.raw.damage as number[][])[0]));
    assert.ok(Array.isArray(bare.recoilHp));

    const scrappy = runCalculate({
      attacker: {
        species: 'Kangaskhan-Mega',
        ability: 'Scrappy',
        nature: 'Adamant',
        evs: {atk: 32},
      },
      defender: {species: 'Primarina', ability: 'Torrent', evs: {hp: 32}},
      move: 'Double-Edge',
    });
    assert.equal(scrappy.abilityResolution?.attacker?.applied, 'Parental Bond');
    assert.equal(scrappy.abilityResolution?.attacker?.supplied, 'Scrappy');
    assert.equal(scrappy.abilityResolution?.attacker?.source, 'dex');
  });

  it('abilityOverride on Mega uses override', () => {
    const r = runCalculate({
      attacker: {
        species: 'Kangaskhan-Mega',
        abilityOverride: 'Intimidate',
        nature: 'Adamant',
        evs: {atk: 32},
      },
      defender: {species: 'Primarina', ability: 'Torrent', evs: {hp: 32}},
      move: 'Double-Edge',
    });
    assert.equal(r.abilityResolution?.attacker?.source, 'override');
    assert.equal(r.abilityResolution?.attacker?.applied, 'Intimidate');
    // No PB nesting without Parental Bond
    assert.ok(Array.isArray(r.raw.damage) && !Array.isArray((r.raw.damage as number[])[0]));
  });

  it('Disguise: Wood Hammer absorb → recoil 0; MB → normal; form absent → disguised', () => {
    const nonMb = runCalculate({
      attacker: {
        species: 'Rillaboom',
        ability: 'Grassy Surge',
        nature: 'Adamant',
        evs: {atk: 32},
      },
      defender: {
        species: 'Mimikyu',
        ability: 'Disguise',
        evs: {hp: 32},
      },
      move: 'Wood Hammer',
    });
    assert.ok(Array.isArray(nonMb.recoilHp));
    for (const v of nonMb.recoilHp as number[]) assert.equal(v, 0);

    const mb = runCalculate({
      attacker: {
        species: 'Excadrill',
        ability: 'Mold Breaker',
        nature: 'Adamant',
        evs: {atk: 32},
      },
      defender: {
        species: 'Mimikyu',
        ability: 'Disguise',
        evs: {hp: 32},
      },
      move: 'Wood Hammer',
    });
    const dmg = mb.raw.damage as number[];
    const rh = mb.recoilHp as number[];
    const hp = mb.raw.stats.defender.hp!;
    for (let i = 0; i < dmg.length; i++) {
      assert.equal(rh[i], recoilOneThirdHp(Math.min(dmg[i]!, hp)));
    }

    const busted = runCalculate({
      attacker: {
        species: 'Rillaboom',
        ability: 'Grassy Surge',
        nature: 'Adamant',
        evs: {atk: 32},
      },
      defender: {
        species: 'Mimikyu',
        ability: 'Disguise',
        form: 'busted',
        evs: {hp: 32},
      },
      move: 'Wood Hammer',
    });
    assert.ok((busted.recoilHp as number[]).some((v) => v > 0));
  });

  it('Normal vs Mimikyu immunity → damage 0, recoil 0', () => {
    const r = runCalculate({
      attacker: {
        species: 'Tauros',
        ability: 'Intimidate',
        nature: 'Adamant',
        evs: {atk: 32},
      },
      defender: {species: 'Mimikyu', ability: 'Disguise', evs: {hp: 32}},
      move: 'Double-Edge',
    });
    assert.equal(r.damageRange[1], 0);
    assert.equal(r.recoilHp, 0);
  });

  it('curHP absent: raw.damage matches baseline shape for EQ fixture', () => {
    const r = runCalculate({
      attacker: {
        species: 'Garchomp',
        nature: 'Jolly',
        evs: {hp: 2, atk: 32, def: 0, spa: 0, spd: 0, spe: 32},
      },
      defender: {
        species: 'Kingambit',
        nature: 'Adamant',
        evs: {hp: 32, atk: 32, def: 0, spa: 0, spd: 2, spe: 0},
      },
      move: 'Earthquake',
    });
    assert.deepEqual(r.raw.damage, [
      150, 150, 152, 152, 156, 158, 158, 162, 162, 164, 168, 168, 170, 170, 174,
      176,
    ]);
    assert.equal(r.recoilHp, RECOIL_NOT_IMPLEMENTED);
  });

  it('Endure on defender caps dealt', () => {
    const r = runCalculate({
      attacker: {
        species: 'Infernape',
        ability: 'Blaze',
        nature: 'Adamant',
        evs: {atk: 32},
      },
      defender: {
        species: 'Primarina',
        ability: 'Torrent',
        endure: true,
        evs: {hp: 0},
      },
      move: 'Flare Blitz',
    });
    const hp = r.raw.stats.defender.hp!;
    const rh = r.recoilHp as number[];
    const dmg = r.raw.damage as number[];
    for (let i = 0; i < dmg.length; i++) {
      const dealt = Math.min(dmg[i]!, hp - 1);
      assert.equal(rh[i], recoilOneThirdHp(dealt));
    }
  });

  it('[33,100] Double-Edge is numeric path', () => {
    const r = runCalculate({
      attacker: {
        species: 'Tauros',
        ability: 'Intimidate',
        nature: 'Adamant',
        evs: {atk: 32},
      },
      defender: {species: 'Primarina', ability: 'Torrent', evs: {hp: 32}},
      move: 'Double-Edge',
    });
    assert.ok(Array.isArray(r.recoilHp));
    assert.notEqual(r.recoilHp, RECOIL_NOT_IMPLEMENTED);
  });

  it('AR3 live: Flare Blitz vs Primarina HP 187 — no roll reaches 187; synthetic caps', () => {
    const live = runCalculate({
      attacker: {
        species: 'Infernape',
        ability: 'Blaze',
        nature: 'Adamant',
        evs: {atk: 32},
      },
      defender: {species: 'Primarina', ability: 'Torrent', evs: {hp: 32}},
      move: 'Flare Blitz',
    });
    assert.equal(live.raw.stats.defender.hp, 187);
    assert.deepEqual(live.damageRange, [62, 73]);
    const rolls = live.raw.damage as number[];
    assert.ok(rolls.every((d) => d < 187), 'no live roll reaches 187');
    assert.deepEqual(live.recoilHp, [
      20, 21, 21, 21, 21, 22, 22, 22, 22, 23, 23, 23, 23, 24, 24, 24,
    ]);
    // raw.recoil is % of attacker max HP, not HP points
    assert.deepEqual(live.raw.recoil.recoil, [13.5, 15.9]);

    // Synthetic: roll near 250 into HP 187 → dealt 187 → 62 (not 83)
    const syn = sumRecoilAcrossHits({
      hits: [250, 187, 186],
      initial: buildInitialHitState({
        maxHP: 187,
        defenderAbility: 'Torrent',
      }),
      attackerAbility: 'Blaze',
      defenderAbility: 'Torrent',
      infiltrator: false,
    }) as number[];
    assert.deepEqual(syn, [62, 62, 62]);
    // Partial HP: curHP 100, roll 187 → dealt 100 → 33
    const partial = sumRecoilAcrossHits({
      hits: [187],
      initial: buildInitialHitState({
        maxHP: 187,
        curHP: 100,
        defenderAbility: 'Torrent',
      }),
      attackerAbility: 'Blaze',
      defenderAbility: 'Torrent',
      infiltrator: false,
    }) as number[];
    assert.deepEqual(partial, [33]);
  });

  it('Protect isProtected: calc returns damage 0; recoilHp 0', () => {
    const r = runCalculate({
      attacker: {
        species: 'Infernape',
        ability: 'Blaze',
        nature: 'Adamant',
        evs: {atk: 32},
      },
      defender: {species: 'Primarina', ability: 'Torrent', evs: {hp: 32}},
      move: 'Flare Blitz',
      field: {defenderSide: {isProtected: true}},
    });
    assert.equal(r.raw.damage, 0);
    assert.deepEqual(r.damageRange, [0, 0]);
    assert.equal(r.recoilHp, 0);
  });

  it('PB vs Disguise: usable hit-2 rolls; absorb hit1 recoil 0', () => {
    const r = runCalculate({
      attacker: {
        species: 'Kangaskhan-Mega',
        nature: 'Adamant',
        evs: {atk: 32},
      },
      defender: {
        species: 'Mimikyu',
        ability: 'Disguise',
        types: ['Water'],
        evs: {hp: 32},
      },
      move: 'Double-Edge',
    });
    assert.ok(Array.isArray(r.raw.damage) && Array.isArray((r.raw.damage as number[][])[0]));
    const [h1, h2] = r.raw.damage as [number[], number[]];
    assert.equal(h1.length, 16);
    assert.equal(h2.length, 16);
    assert.ok(h2.every((x) => x > 0));
    const rh = r.recoilHp as number[];
    // hit1 absorbed → 0; only hit2 contributes
    for (const t of rh) {
      assert.ok(t >= recoilOneThirdHp(h2[0]!) && t <= recoilOneThirdHp(h2[15]!));
    }
  });

  it('abilityOverride PB vs Disguise also yields usable hit-2', () => {
    const r = runCalculate({
      attacker: {
        species: 'Tauros',
        ability: 'Intimidate',
        abilityOverride: 'Parental Bond',
        nature: 'Adamant',
        evs: {atk: 32},
      },
      defender: {
        species: 'Mimikyu',
        ability: 'Disguise',
        types: ['Water'],
        evs: {hp: 32},
      },
      move: 'Double-Edge',
    });
    assert.ok(Array.isArray(r.raw.damage) && Array.isArray((r.raw.damage as number[][])[0]));
    assert.ok(Array.isArray(r.recoilHp));
  });

  it('Mold Breaker vs Disguise: normal capped recoil (no absorb)', () => {
    const r = runCalculate({
      attacker: {
        species: 'Excadrill',
        ability: 'Mold Breaker',
        nature: 'Adamant',
        evs: {atk: 32},
      },
      defender: {species: 'Mimikyu', ability: 'Disguise', evs: {hp: 32}},
      move: 'Wood Hammer',
    });
    const dmg = r.raw.damage as number[];
    const rh = r.recoilHp as number[];
    const hp = r.raw.stats.defender.hp!;
    assert.ok(dmg.every((d) => d > 0));
    for (let i = 0; i < dmg.length; i++) {
      assert.equal(rh[i], recoilOneThirdHp(Math.min(dmg[i]!, hp)));
    }
  });

  it('bare-number zero damage (Ghost immune): recoilHp 0, no error', () => {
    const r = runCalculate({
      attacker: {
        species: 'Tauros',
        ability: 'Intimidate',
        nature: 'Adamant',
        evs: {atk: 32},
      },
      defender: {species: 'Mimikyu', ability: 'Disguise', evs: {hp: 32}},
      move: 'Double-Edge',
    });
    assert.equal(typeof r.raw.damage, 'number');
    assert.equal(r.raw.damage, 0);
    assert.equal(r.recoilHp, 0);
  });

  it('fresh Substitute defaults floor(maxHP/4); damaged needs substituteHp', () => {
    const fresh = buildInitialHitState({
      maxHP: 200,
      substitute: true,
      defenderAbility: 'Torrent',
    });
    assert.equal(fresh.subHp, 50);
    const damaged = buildInitialHitState({
      maxHP: 200,
      substitute: true,
      substituteHp: 12,
      defenderAbility: 'Torrent',
    });
    assert.equal(damaged.subHp, 12);
  });
});
