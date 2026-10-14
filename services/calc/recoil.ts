/**
 * Project convention for 1/3-class recoil as HP points from damage dealt.
 * Not "the game rule" — see PR notes / planned ADR-078 amendment.
 *
 * Observation table (owner, Champions casual; d = damage dealt, r = recoil;
 * all 1/3-class): floor(d/3) fails at 47→15, 35→11, 180→60; round(d/3) fails
 * at 80→27, 68→23, 188→63; floor((d*33+50)/100) fits every logged row
 * (including capped KO deals). Earlier floor(d/3) convention was contradicted.
 * Pinned sim (942cda7) `applyRecoilDamage` uses
 * clampIntRange(Math.round(dealt * n / d), 1) — same numbers for [33,100].
 * As a single multiplication the ratio is in about [0.33, 0.3306).
 *
 * Open: min-1 for d=1 unsourced/untested; once-on-total supported by sim
 * (battle-actions.ts L961–979) + one log line, not numerically pinned vs
 * per-hit; 1/2 and 1/4 moves untested (labeled not implemented).
 */

export const RECOIL_NOT_IMPLEMENTED = 'recoil rule not implemented' as const;

export type RecoilHp =
  | number
  | number[]
  | typeof RECOIL_NOT_IMPLEMENTED;

export type AbilitySource = 'dex' | 'request' | 'override';

export type AbilityResolutionSide = {
  applied: string;
  supplied?: string;
  source: AbilitySource;
};

export type AbilityResolution = {
  attacker?: AbilityResolutionSide;
  defender?: AbilityResolutionSide;
};

export type DisguiseForm = 'disguised' | 'busted';

export type HitResolutionState = {
  curHP: number;
  maxHP: number;
  subHp: number | null;
  disguiseIntact: boolean;
  sashAvailable: boolean;
  sturdyAvailable: boolean;
  endure: boolean;
};

export type HitResolutionOpts = {
  roll: number;
  state: HitResolutionState;
  /** Effective attacker ability (post-resolution). */
  attackerAbility: string;
  /** Effective defender ability (post-resolution). */
  defenderAbility: string;
  infiltrator: boolean;
};

const MB_FAMILY = new Set(['Mold Breaker', 'Teravolt', 'Turboblaze']);

/**
 * Recoil HP from total damage dealt via the 33/100 operator.
 * Integer only: floor((dealt * 33 + 50) / 100); d=0 → 0; d>0 → max(1, …).
 * Matches pinned-sim Math.round(dealt * 33 / 100) clamped to ≥1 when dealt>0.
 */
export function recoilHpFrom33Over100(dealt: number): number {
  if (dealt <= 0) return 0;
  return Math.max(1, Math.floor((dealt * 33 + 50) / 100));
}

export function isOneThirdRecoil(recoil: [number, number] | undefined): boolean {
  if (!recoil) return false;
  const [n, d] = recoil;
  return (n === 33 && d === 100) || (n === 1 && d === 3);
}

export function isMoldBreakerFamily(ability: string): boolean {
  return MB_FAMILY.has(ability);
}

/** Resolve dealt damage for one roll given survival / Sub / Disguise state. Mutates state. */
export function resolveDealtForHit(opts: HitResolutionOpts): number {
  const {roll, state, attackerAbility, defenderAbility, infiltrator} = opts;
  if (state.curHP <= 0) return 0;

  // Substitute (Infiltrator bypasses)
  if (state.subHp !== null && state.subHp > 0 && !infiltrator) {
    const dealt = Math.min(roll, state.subHp);
    state.subHp -= dealt;
    if (state.subHp <= 0) state.subHp = 0;
    return dealt;
  }

  // Disguise absorb (not under MB family)
  if (
    state.disguiseIntact &&
    defenderAbility === 'Disguise' &&
    !isMoldBreakerFamily(attackerAbility)
  ) {
    state.disguiseIntact = false;
    state.curHP = Math.max(0, state.curHP - Math.floor(state.maxHP / 8));
    return 0;
  }

  // Endure — any HP, not consumed
  if (state.endure) {
    if (state.curHP <= 1) return 0;
    const dealt = Math.min(roll, state.curHP - 1);
    state.curHP -= dealt;
    return dealt;
  }

  // Sash / Sturdy at max HP
  const atMax = state.curHP === state.maxHP;
  const sturdyOk =
    state.sturdyAvailable && !isMoldBreakerFamily(attackerAbility);
  if (atMax && roll >= state.curHP && (state.sashAvailable || sturdyOk)) {
    const dealt = state.curHP - 1;
    state.curHP = 1;
    if (state.sashAvailable) state.sashAvailable = false;
    return dealt;
  }

  const dealt = Math.min(roll, state.curHP);
  state.curHP -= dealt;
  return dealt;
}

function cloneState(s: HitResolutionState): HitResolutionState {
  return {...s};
}

/**
 * Only place once-on-total recoil timing lives.
 * Resolves dealt per hit sequentially (Sub / Disguise / Endure / Sash / Sturdy),
 * sums dealt, then applies recoilHpFrom33Over100 once.
 * Single-hit: each roll from a fresh copy of initial.
 * Parental Bond: every (h1,h2) pair; returns sorted distinct totals.
 */
export function recoilHpFromTotalDealt(args: {
  hits: number[] | [number[], number[]];
  initial: HitResolutionState;
  attackerAbility: string;
  defenderAbility: string;
  infiltrator: boolean;
}): number | number[] {
  const {hits, initial, attackerAbility, defenderAbility, infiltrator} = args;
  const dealtOne = (state: HitResolutionState, roll: number) =>
    resolveDealtForHit({
      roll,
      state,
      attackerAbility,
      defenderAbility,
      infiltrator,
    });

  if (!Array.isArray(hits[0])) {
    const rolls = hits as number[];
    return rolls.map((r) => {
      const state = cloneState(initial);
      return recoilHpFrom33Over100(dealtOne(state, r));
    });
  }

  const [hit1, hit2] = hits as [number[], number[]];
  const totals = new Set<number>();
  for (const a of hit1) {
    for (const b of hit2) {
      const state = cloneState(initial);
      const totalDealt = dealtOne(state, a) + dealtOne(state, b);
      totals.add(recoilHpFrom33Over100(totalDealt));
    }
  }
  return [...totals].sort((x, y) => x - y);
}

export type ComputeRecoilArgs = {
  damage: number | number[] | number[][];
  moveRecoil: [number, number] | undefined;
  moveHits: number;
  isSpread: boolean;
  attackerAbility: string;
  defenderAbility: string;
  infiltrator: boolean;
  initial: HitResolutionState;
  /** Parental Bond confirmed for this calc (ability + second hit path). */
  parentalBond: boolean;
};

/**
 * Gate + Rock Head/Magic Guard + single-hit / PB recoilHp.
 */
export function computeRecoilHp(args: ComputeRecoilArgs): RecoilHp {
  if (!isOneThirdRecoil(args.moveRecoil)) {
    return RECOIL_NOT_IMPLEMENTED;
  }
  // Inherent multi-hit recoil moves: none legal today; label if gated.
  if (args.moveHits > 1) {
    return RECOIL_NOT_IMPLEMENTED;
  }

  const {damage} = args;
  if (typeof damage === 'number') {
    if (damage === 0) {
      if (
        args.attackerAbility === 'Rock Head' ||
        args.attackerAbility === 'Magic Guard'
      ) {
        return 0;
      }
      const state = cloneState(args.initial);
      return recoilHpFrom33Over100(
        resolveDealtForHit({
          roll: 0,
          state,
          attackerAbility: args.attackerAbility,
          defenderAbility: args.defenderAbility,
          infiltrator: args.infiltrator,
        }),
      );
    }
    return RECOIL_NOT_IMPLEMENTED;
  }

  const nested = Array.isArray(damage[0]);
  if (nested) {
    if (!args.parentalBond || args.isSpread) {
      return RECOIL_NOT_IMPLEMENTED;
    }
    const pair = damage as [number[], number[]];
    if (pair.length < 2 || !Array.isArray(pair[1])) {
      return RECOIL_NOT_IMPLEMENTED;
    }
    const totals = recoilHpFromTotalDealt({
      hits: pair,
      initial: args.initial,
      attackerAbility: args.attackerAbility,
      defenderAbility: args.defenderAbility,
      infiltrator: args.infiltrator,
    });
    if (
      args.attackerAbility === 'Rock Head' ||
      args.attackerAbility === 'Magic Guard'
    ) {
      return 0;
    }
    return totals;
  }

  // Parental Bond claimed but no second hit nesting
  if (args.parentalBond) {
    return RECOIL_NOT_IMPLEMENTED;
  }

  const result = recoilHpFromTotalDealt({
    hits: damage as number[],
    initial: args.initial,
    attackerAbility: args.attackerAbility,
    defenderAbility: args.defenderAbility,
    infiltrator: args.infiltrator,
  });
  if (
    args.attackerAbility === 'Rock Head' ||
    args.attackerAbility === 'Magic Guard'
  ) {
    return 0;
  }
  return result;
}

export type PokemonAbilityInput = {
  species: string;
  ability?: string;
  abilityOverride?: string;
  /**
   * Fallback / Mega sole ability. For Megas the wrapper supplies
   * champions.v1.json's sole ability (not calc species.abilities[0]).
   */
  dexAbility: string;
};

/**
 * Ability resolution before @smogon/calc.
 * Mega → dexAbility (champions.v1 sole ability) unless abilityOverride.
 */
export function resolveAbility(input: PokemonAbilityInput): AbilityResolutionSide {
  if (input.abilityOverride) {
    return {
      applied: input.abilityOverride,
      supplied: input.abilityOverride,
      source: 'override',
    };
  }
  const isMega = input.species.includes('-Mega');
  if (isMega) {
    const side: AbilityResolutionSide = {
      applied: input.dexAbility,
      source: 'dex',
    };
    if (input.ability && input.ability !== input.dexAbility) {
      side.supplied = input.ability;
    }
    return side;
  }
  if (input.ability) {
    return {
      applied: input.ability,
      supplied: input.ability,
      source: 'request',
    };
  }
  return {applied: input.dexAbility, source: 'dex'};
}

export function buildInitialHitState(opts: {
  maxHP: number;
  curHP?: number;
  substitute?: boolean;
  substituteHp?: number;
  endure?: boolean;
  form?: DisguiseForm;
  defenderAbility: string;
  item?: string;
}): HitResolutionState {
  const maxHP = opts.maxHP;
  const curHP =
    opts.curHP !== undefined && opts.curHP <= maxHP ? opts.curHP : maxHP;
  let subHp: number | null = null;
  if (opts.substitute) {
    subHp =
      opts.substituteHp !== undefined
        ? opts.substituteHp
        : Math.floor(maxHP / 4);
  }
  const disguiseIntact =
    opts.defenderAbility === 'Disguise' &&
    (opts.form === undefined || opts.form === 'disguised');
  return {
    curHP,
    maxHP,
    subHp,
    disguiseIntact,
    sashAvailable: opts.item === 'Focus Sash',
    sturdyAvailable: opts.defenderAbility === 'Sturdy',
    endure: !!opts.endure,
  };
}
