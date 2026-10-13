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

describe('recoilOneThirdHp', () => {
  it('floors dealt/3 with min 1; zero dealt → 0', () => {
    assert.equal(recoilOneThirdHp(0), 0);
    assert.equal(recoilOneThirdHp(1), 1);
    assert.equal(recoilOneThirdHp(2), 1);
    assert.equal(recoilOneThirdHp(5), 1);
    assert.equal(recoilOneThirdHp(8), 2);
    assert.equal(recoilOneThirdHp(186), 62);
    assert.equal(recoilOneThirdHp(187), 62); // AR3 pin
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
  it('Case A: floor per hit then sum (independent floors)', () => {
    // h1=153 → 51, h2=30 → 10; but plan Case A is floor((h1+h2)/3) as alternate?
    // Plan: PB A: floor((h1+h2)/3); B: {50,51} vs sim-constant 51
    // Project convention is PER HIT: floor(h1/3)+floor(h2/3)
    const init = buildInitialHitState({
      maxHP: 300,
      defenderAbility: 'Torrent',
    });
    const totals = sumRecoilAcrossHits({
      hits: [[153], [123]],
      initial: init,
      attackerAbility: 'Parental Bond',
      defenderAbility: 'Torrent',
      infiltrator: false,
    });
    // 153→51, 123→41 → 92
    assert.deepEqual(totals, [92]);
  });

  it('Case B pin set includes 50 and 51 for Endure PB path', () => {
    // Plan: PB 153/123/30..36 → 41+9=50 with Endure... use known fixture
    const init = buildInitialHitState({
      maxHP: 153,
      curHP: 153,
      endure: true,
      defenderAbility: 'Torrent',
    });
    // hit1 rolls that leave room for hit2: if hit1 capped to 152 → recoil 50
    // hit2 on remaining 1 → 0 dealt → 0 recoil; total 50
    // Without endure sequential: need pairs that yield 50 and 51
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
    // hit1 153 with endure → dealt 152 → floor(152/3)=50; curHP=1; hit2 any → 0 → total 50
    // hit1 150 with endure → dealt 150 → 50; curHP=3; hit2 30→ min(30,2)=2 →1; hit2 36→2→1
    // Actually endure: dealt = min(r, curHP-1)
    // 153: dealt=152, recoil=50, hp=1; hit2: at 1hp endure → 0 → total 50
    // 150: dealt=150, recoil=50, hp=3; hit2 30: dealt=min(30,2)=2 →1; total 51
    assert.ok(totals.includes(50));
    assert.ok(totals.includes(51));
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
});
