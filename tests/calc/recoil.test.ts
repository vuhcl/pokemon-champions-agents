/**
 * recoilHp: 33/100 operator on total damage dealt (once per attack).
 * Not "the game rule."
 */
import assert from 'node:assert/strict';
import {describe, it} from 'node:test';
import {runCalculate} from '../../services/calc/handlers.js';
import {
  RECOIL_NOT_IMPLEMENTED,
  RECOIL_SEE_SELFDAMAGE,
  recoilHpFrom33Over100,
  recoilHpFromDamageFraction,
  computeRecoilHp,
  computeSelfDamage,
  crashSelfHp,
  struggleSelfHp,
  maxHpHalfSelfHp,
  struggleProtectApplies,
  resolveAbility,
  resolveDealtForHit,
  recoilHpFromTotalDealt,
  buildInitialHitState,
  type HitResolutionState,
} from '../../services/calc/recoil.js';

function totalDealt(
  hits: number[] | [number[], number[]],
  initial: HitResolutionState,
  n = 33,
  den = 100,
) {
  return recoilHpFromTotalDealt({
    hits,
    initial,
    attackerAbility: 'Blaze',
    defenderAbility: 'Torrent',
    infiltrator: false,
    n,
    den,
  });
}

describe('recoilHpFromDamageFraction encoding pins', () => {
  it('[33,100] observation + edge pins (d→r)', () => {
    const pins: [number, number][] = [
      [187, 62],
      [150, 50],
      [47, 16],
      [35, 12],
      [180, 59],
      [80, 26],
      [68, 22],
      [188, 62],
      [5, 2],
      [1, 1],
      [0, 0],
    ];
    for (const [d, r] of pins) {
      assert.equal(recoilHpFromDamageFraction(d, 33, 100), r, `33/100 ${d}→${r}`);
      assert.equal(recoilHpFrom33Over100(d), r);
    }
  });

  it('[1,2] pins', () => {
    for (const [d, r] of [
      [1, 1],
      [3, 2],
      [150, 75],
      [151, 76],
    ] as [number, number][]) {
      assert.equal(recoilHpFromDamageFraction(d, 1, 2), r, `1/2 ${d}→${r}`);
    }
  });

  it('[1,4] pins', () => {
    for (const [d, r] of [
      [1, 1],
      [2, 1],
      [6, 2],
      [7, 2],
      [150, 38],
    ] as [number, number][]) {
      assert.equal(recoilHpFromDamageFraction(d, 1, 4), r, `1/4 ${d}→${r}`);
    }
  });

  it('[1,3] is labeled (not numbered)', () => {
    const init = buildInitialHitState({maxHP: 100, defenderAbility: 'Torrent'});
    assert.equal(
      computeRecoilHp({
        damage: [150],
        moveRecoil: [1, 3],
        moveHits: 1,
        isSpread: false,
        attackerAbility: 'Blaze',
        defenderAbility: 'Torrent',
        infiltrator: false,
        initial: init,
        parentalBond: false,
      }),
      RECOIL_NOT_IMPLEMENTED,
    );
  });

  it('fails if floor(d/3) is substituted for [33,100] (rows floor misses)', () => {
    for (const d of [47, 35, 180]) {
      const got = recoilHpFromDamageFraction(d, 33, 100);
      const floor3 = Math.max(1, Math.floor(d / 3));
      assert.notEqual(got, floor3, `d=${d}: operator must ≠ floor(d/3)=${floor3}`);
    }
  });

  it('fails if round(d/3) is substituted for [33,100] (rows round misses)', () => {
    for (const d of [80, 68, 188]) {
      const got = recoilHpFromDamageFraction(d, 33, 100);
      const round3 = Math.max(1, Math.round(d / 3));
      assert.notEqual(got, round3, `d=${d}: operator must ≠ round(d/3)=${round3}`);
    }
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

describe('recoilHpFromTotalDealt PB + timing', () => {
  it('Case A: 256 actual calc pairs → once-on-total set [40..47]', () => {
    const hit1 = [
      97, 99, 99, 100, 102, 103, 105, 105, 106, 108, 109, 109, 111, 112, 114, 115,
    ];
    const hit2 = [
      24, 24, 24, 24, 24, 25, 25, 25, 25, 25, 27, 27, 27, 27, 27, 28,
    ];
    const init = buildInitialHitState({
      maxHP: 169,
      defenderAbility: 'Torrent',
    });
    const totals = recoilHpFromTotalDealt({
      hits: [hit1, hit2],
      initial: init,
      attackerAbility: 'Parental Bond',
      defenderAbility: 'Torrent',
      infiltrator: false,
      n: 33,
      den: 100,
    }) as number[];
    const expected = new Set<number>();
    for (const a of hit1) {
      for (const b of hit2) {
        expected.add(recoilHpFrom33Over100(a + b));
      }
    }
    assert.deepEqual(totals, [...expected].sort((x, y) => x - y));
    assert.deepEqual(totals, [40, 41, 42, 43, 44, 45, 46, 47]);
    assert.equal(hit1.length * hit2.length, 256);
  });

  it('Case B (no Endure): HP 153 KO → set exactly {50}', () => {
    const init = buildInitialHitState({
      maxHP: 153,
      curHP: 153,
      defenderAbility: 'Torrent',
    });
    assert.equal(init.endure, false);
    const totals = recoilHpFromTotalDealt({
      hits: [[148, 153], [36]],
      initial: init,
      attackerAbility: 'Parental Bond',
      defenderAbility: 'Torrent',
      infiltrator: false,
      n: 33,
      den: 100,
    }) as number[];
    // Total dealt always 153 → operator → 50
    assert.deepEqual(totals, [50]);
  });

  it('Case B Endure variant: total capped at 152 → set exactly {50}', () => {
    const init = buildInitialHitState({
      maxHP: 153,
      curHP: 153,
      endure: true,
      defenderAbility: 'Torrent',
    });
    const totals = recoilHpFromTotalDealt({
      hits: [
        [153, 200],
        [30, 36],
      ],
      initial: init,
      attackerAbility: 'Parental Bond',
      defenderAbility: 'Torrent',
      infiltrator: false,
      n: 33,
      den: 100,
    }) as number[];
    assert.deepEqual(totals, [50]);
  });

  it('Endure worked example: HP 153, hit1=123, hit2 capped 29 → recoil 50', () => {
    const init = buildInitialHitState({
      maxHP: 153,
      curHP: 153,
      endure: true,
      defenderAbility: 'Torrent',
    });
    const totals = recoilHpFromTotalDealt({
      hits: [[123], [29]],
      initial: init,
      attackerAbility: 'Parental Bond',
      defenderAbility: 'Torrent',
      infiltrator: false,
      n: 33,
      den: 100,
    });
    // dealt 123+29=152 → 50
    assert.deepEqual(totals, [50]);
  });

  it('Sash + Parental Bond: total dealt = HP 100 → 33', () => {
    const init = buildInitialHitState({
      maxHP: 100,
      item: 'Focus Sash',
      defenderAbility: 'Torrent',
    });
    assert.equal(init.sashAvailable, true);
    const totals = recoilHpFromTotalDealt({
      hits: [[200], [50]],
      initial: init,
      attackerAbility: 'Parental Bond',
      defenderAbility: 'Torrent',
      infiltrator: false,
      n: 33,
      den: 100,
    });
    assert.deepEqual(totals, [33]);
  });

  it('Substitute + Parental Bond: Sub 40 + hit2 30 → total 70 → 23', () => {
    const init = buildInitialHitState({
      maxHP: 200,
      substitute: true,
      substituteHp: 40,
      defenderAbility: 'Torrent',
    });
    const totals = recoilHpFromTotalDealt({
      hits: [[50], [30]],
      initial: init,
      attackerAbility: 'Parental Bond',
      defenderAbility: 'Torrent',
      infiltrator: false,
      n: 33,
      den: 100,
    });
    assert.deepEqual(totals, [23]);
  });

  it('hits 5+5: once-on-total 3; per-hit sum would be 4 (switch-back fails)', () => {
    const init = buildInitialHitState({
      maxHP: 200,
      defenderAbility: 'Torrent',
    });
    const totals = recoilHpFromTotalDealt({
      hits: [[5], [5]],
      initial: init,
      attackerAbility: 'Parental Bond',
      defenderAbility: 'Torrent',
      infiltrator: false,
      n: 33,
      den: 100,
    }) as number[];
    assert.deepEqual(totals, [3]);
    const perHitSum =
      recoilHpFrom33Over100(5) + recoilHpFrom33Over100(5);
    assert.equal(perHitSum, 4);
    assert.notEqual(totals[0], perHitSum);
  });
});

describe('runCalculate recoilHp live', () => {
  it('Flare Blitz vs Primarina: AR3-style capped rolls → 33/100 operator', () => {
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
      assert.equal(rh[i], recoilHpFrom33Over100(dealt));
    }
    const hp = result.raw.stats.defender.hp!;
    for (let i = 0; i < dmg.length; i++) {
      if (Math.min(dmg[i]!, hp) === 187) assert.equal(rh[i], 62);
    }
  });

  it('Head Smash [1,2] / Wild Charge [1,4] → numbered recoilHp', () => {
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
    assert.ok(Array.isArray(head.recoilHp));
    assert.notEqual(head.recoilHp, RECOIL_NOT_IMPLEMENTED);
    const hd = head.raw.damage as number[];
    const hrh = head.recoilHp as number[];
    const hhp = head.raw.stats.defender.hp!;
    for (let i = 0; i < hd.length; i++) {
      assert.equal(
        hrh[i],
        recoilHpFromDamageFraction(Math.min(hd[i]!, hhp), 1, 2),
      );
    }
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
    assert.ok(Array.isArray(wild.recoilHp));
    const wd = wild.raw.damage as number[];
    const wrh = wild.recoilHp as number[];
    const whp = wild.raw.stats.defender.hp!;
    for (let i = 0; i < wd.length; i++) {
      assert.equal(
        wrh[i],
        recoilHpFromDamageFraction(Math.min(wd[i]!, whp), 1, 4),
      );
    }
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
      assert.equal(rh[i], recoilHpFrom33Over100(Math.min(dmg[i]!, hp)));
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
      assert.equal(rh[i], recoilHpFrom33Over100(dealt));
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

  it('AR3 key scenario: Charizard-Mega-X +6 Flare Blitz vs Primarina HP 187 → every KO roll recoilHp 62', () => {
    const r = runCalculate({
      attacker: {
        species: 'Charizard-Mega-X',
        level: 50,
        nature: 'Adamant',
        ability: 'Tough Claws',
        item: 'Charizardite X',
        evs: {hp: 32, atk: 0, def: 0, spa: 0, spd: 0, spe: 0},
        boosts: {atk: 6},
      },
      defender: {
        species: 'Primarina',
        level: 50,
        nature: 'Modest',
        ability: 'Torrent',
        item: 'Life Orb',
        evs: {hp: 32, atk: 0, def: 0, spa: 32, spd: 2, spe: 0},
      },
      move: 'Flare Blitz',
      field: {gameType: 'Doubles'},
    });
    assert.equal(r.raw.stats.defender.hp, 187);
    assert.deepEqual(r.damageRange, [307, 362]);
    const rolls = r.raw.damage as number[];
    assert.ok(rolls.every((d) => d >= 187), 'every roll is a KO into 187');
    assert.ok(Array.isArray(r.recoilHp));
    for (const v of r.recoilHp as number[]) {
      assert.equal(v, 62);
    }
  });

  it('AR3 synthetic caps: 250/187→62, 186→61 into HP 187; partial curHP 100 → 33', () => {
    const syn = recoilHpFromTotalDealt({
      hits: [250, 187, 186],
      initial: buildInitialHitState({
        maxHP: 187,
        defenderAbility: 'Torrent',
      }),
      attackerAbility: 'Blaze',
      defenderAbility: 'Torrent',
      infiltrator: false,
      n: 33,
      den: 100,
    }) as number[];
    assert.deepEqual(syn, [62, 62, 61]);
    const partial = recoilHpFromTotalDealt({
      hits: [187],
      initial: buildInitialHitState({
        maxHP: 187,
        curHP: 100,
        defenderAbility: 'Torrent',
      }),
      attackerAbility: 'Blaze',
      defenderAbility: 'Torrent',
      infiltrator: false,
      n: 33,
      den: 100,
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

  it('PB vs Disguise: usable hit-2 rolls; absorb hit1 → recoil from hit2 total only', () => {
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
    for (const t of rh) {
      assert.ok(t >= recoilHpFrom33Over100(h2[0]!) && t <= recoilHpFrom33Over100(h2[15]!));
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
      assert.equal(rh[i], recoilHpFrom33Over100(Math.min(dmg[i]!, hp)));
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

describe('selfDamage (crash / Struggle / Steel Beam)', () => {
  it('formula pins: crash / struggle / max_hp_half', () => {
    assert.equal(crashSelfHp(201), 100);
    assert.equal(crashSelfHp(1), 1);
    assert.equal(struggleSelfHp(201), 50);
    assert.equal(struggleSelfHp(202), 51);
    assert.equal(struggleSelfHp(203), 51);
    assert.equal(maxHpHalfSelfHp(201), 101);
    assert.equal(maxHpHalfSelfHp(200), 100);
  });

  it('High Jump Kick → crash selfDamage; recoilHp see selfDamage', () => {
    const r = runCalculate({
      attacker: {
        species: 'Gallade',
        ability: 'Justified',
        nature: 'Adamant',
        evs: {hp: 32, atk: 32},
      },
      defender: {species: 'Primarina', ability: 'Torrent', evs: {hp: 32}},
      move: 'High Jump Kick',
    });
    assert.equal(r.recoilHp, RECOIL_SEE_SELFDAMAGE);
    assert.equal(typeof r.recoilHp, 'string');
    assert.ok(r.selfDamage);
    assert.equal(r.selfDamage!.length, 1);
    assert.equal(r.selfDamage![0]!.kind, 'crash');
    assert.equal(r.selfDamage![0]!.hp, crashSelfHp(r.raw.stats.attacker.hp!));
  });

  it('Axe Kick and Supercell Slam → crash', () => {
    const axe = runCalculate({
      attacker: {
        species: 'Gallade',
        ability: 'Justified',
        nature: 'Adamant',
        evs: {hp: 32, atk: 32},
      },
      defender: {species: 'Primarina', ability: 'Torrent', evs: {hp: 32}},
      move: 'Axe Kick',
    });
    assert.equal(axe.selfDamage?.[0]?.kind, 'crash');
    assert.equal(axe.recoilHp, RECOIL_SEE_SELFDAMAGE);
    const slam = runCalculate({
      attacker: {
        species: 'Pawmot',
        ability: 'Volt Absorb',
        nature: 'Adamant',
        evs: {hp: 32, atk: 32},
      },
      defender: {species: 'Primarina', ability: 'Torrent', evs: {hp: 32}},
      move: 'Supercell Slam',
    });
    assert.equal(slam.selfDamage?.[0]?.kind, 'crash');
    assert.equal(slam.recoilHp, RECOIL_SEE_SELFDAMAGE);
  });

  it('Struggle → struggle selfDamage', () => {
    const r = runCalculate({
      attacker: {
        species: 'Tauros',
        ability: 'Intimidate',
        nature: 'Adamant',
        evs: {hp: 32, atk: 32},
      },
      defender: {species: 'Primarina', ability: 'Torrent', evs: {hp: 32}},
      move: 'Struggle',
    });
    assert.equal(r.selfDamage?.[0]?.kind, 'struggle');
    assert.equal(r.selfDamage![0]!.hp, struggleSelfHp(r.raw.stats.attacker.hp!));
    assert.equal(r.recoilHp, RECOIL_SEE_SELFDAMAGE);
  });

  it('Steel Beam → max_hp_half selfDamage', () => {
    const r = runCalculate({
      attacker: {
        species: 'Metagross',
        ability: 'Clear Body',
        nature: 'Modest',
        evs: {hp: 32, spa: 32},
      },
      defender: {species: 'Primarina', ability: 'Torrent', evs: {hp: 32}},
      move: 'Steel Beam',
    });
    assert.equal(r.selfDamage?.[0]?.kind, 'max_hp_half');
    assert.equal(r.selfDamage![0]!.hp, maxHpHalfSelfHp(r.raw.stats.attacker.hp!));
    assert.equal(r.recoilHp, RECOIL_SEE_SELFDAMAGE);
  });

  it('Magic Guard zeroes crash and Steel Beam; not Struggle', () => {
    const crash = computeSelfDamage({
      move: {hasCrashDamage: true},
      attackerMaxHp: 201,
      attackerAbility: 'Magic Guard',
    });
    assert.equal(crash[0]!.hp, 0);
    const steel = computeSelfDamage({
      move: {mindBlownRecoil: true},
      attackerMaxHp: 201,
      attackerAbility: 'Magic Guard',
    });
    assert.equal(steel[0]!.hp, 0);
    const struggle = computeSelfDamage({
      move: {struggleRecoil: true},
      attackerMaxHp: 201,
      attackerAbility: 'Magic Guard',
    });
    assert.equal(struggle[0]!.hp, 50);
  });

  it('Rock Head does not zero crash / Struggle / Steel Beam', () => {
    for (const move of [
      {hasCrashDamage: true},
      {struggleRecoil: true},
      {mindBlownRecoil: true},
    ] as const) {
      const entries = computeSelfDamage({
        move,
        attackerMaxHp: 200,
        attackerAbility: 'Rock Head',
      });
      assert.ok(entries[0]!.hp > 0);
    }
  });

  it('Flare Blitz has recoilHp numbers and no selfDamage', () => {
    const r = runCalculate({
      attacker: {
        species: 'Infernape',
        ability: 'Blaze',
        nature: 'Adamant',
        evs: {atk: 32},
      },
      defender: {species: 'Primarina', ability: 'Torrent', evs: {hp: 32}},
      move: 'Flare Blitz',
    });
    assert.ok(Array.isArray(r.recoilHp));
    assert.equal(r.selfDamage, undefined);
  });

  it('Struggle isProtected → hp 0 and exact applies for H=201 and H=211', () => {
    for (const [H, amount] of [
      [201, 50],
      [211, 53],
    ] as const) {
      const entries = computeSelfDamage({
        move: {struggleRecoil: true},
        attackerMaxHp: H,
        attackerAbility: 'Intimidate',
        defenderProtected: true,
      });
      assert.equal(entries[0]!.hp, 0);
      assert.equal(entries[0]!.applies, struggleProtectApplies(amount));
      assert.equal(
        entries[0]!.applies,
        `observed 2026-10-13: no recoil when the target was protecting; amount would be ${amount} otherwise`,
      );
      assert.ok(!entries[0]!.applies.includes('formula'));
    }

    const live = runCalculate({
      attacker: {
        species: 'Tauros',
        ability: 'Intimidate',
        nature: 'Adamant',
        evs: {hp: 32, atk: 32},
      },
      defender: {species: 'Primarina', ability: 'Torrent', evs: {hp: 32}},
      move: 'Struggle',
      field: {defenderSide: {isProtected: true}},
    });
    assert.equal(live.selfDamage?.[0]?.hp, 0);
    assert.equal(
      live.selfDamage?.[0]?.applies,
      struggleProtectApplies(struggleSelfHp(live.raw.stats.attacker.hp!)),
    );
    assert.deepEqual(live.damageRange, [0, 0]);
    const dmg = live.raw.damage;
    if (typeof dmg === 'number') {
      assert.equal(dmg, 0);
    } else if (Array.isArray(dmg) && !Array.isArray(dmg[0])) {
      assert.ok((dmg as number[]).every((x) => x === 0));
    } else {
      assert.fail(`Struggle under Protect: unexpected non-zero raw.damage ${JSON.stringify(dmg)}`);
    }

    const unprotected = computeSelfDamage({
      move: {struggleRecoil: true},
      attackerMaxHp: 201,
      attackerAbility: 'Intimidate',
    });
    assert.equal(unprotected[0]!.hp, 50);
  });

  it('crash and Steel Beam keep formula hp when isProtected', () => {
    const crash = computeSelfDamage({
      move: {hasCrashDamage: true},
      attackerMaxHp: 201,
      attackerAbility: 'Justified',
      defenderProtected: true,
    });
    assert.equal(crash[0]!.hp, 100);
    const steel = computeSelfDamage({
      move: {mindBlownRecoil: true},
      attackerMaxHp: 201,
      attackerAbility: 'Clear Body',
      defenderProtected: true,
    });
    assert.equal(steel[0]!.hp, 101);
  });
});
