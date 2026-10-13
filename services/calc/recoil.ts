/**
 * Project convention for 1/3-of-damage-dealt recoil as HP points.
 * Not "the game rule" — see plan appendix / PR notes. Operator and per-hit
 * summing are project conventions; ADR may change them.
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
 * Recoil HP for one hit from damage dealt.
 * Project convention: floor(dealt/3), min 1 when dealt > 0.
 * Secondary sources only for operator; [33,100]/ Showdown Math.round are not operator evidence.
 * min-1 = unsourced sim-clamp convention. ADR to change.
 */
export function recoilOneThirdHp(dealt: number): number {
  if (dealt <= 0) return 0;
  return Math.max(1, Math.floor(dealt / 3));
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
 * Only place per-hit recoil summing lives.
 * Single-hit: maps each roll independently from the same starting state.
 * PB: every (h1,h2) pair sequential; returns sorted distinct totals.
 *
 * Sim conflict (pinned Showdown @ 942cda7): `battle-actions.ts` L961–979
 * accumulates `move.totalDamage` across hits then calls `applyRecoilDamage`
 * once on that total. This helper assumes per-hit floor(dealt/3) then sum.
 * An in-game check decides which is correct; Parental Bond Case B `{50,51}`
 * is the pin and fails deliberately if summing is changed to once-on-total.
 */
export function sumRecoilAcrossHits(args: {
  hits: number[] | [number[], number[]];
  initial: HitResolutionState;
  attackerAbility: string;
  defenderAbility: string;
  infiltrator: boolean;
}): number | number[] {
  const {hits, initial, attackerAbility, defenderAbility, infiltrator} = args;
  const apply = (state: HitResolutionState, roll: number) => {
    const dealt = resolveDealtForHit({
      roll,
      state,
      attackerAbility,
      defenderAbility,
      infiltrator,
    });
    return recoilOneThirdHp(dealt);
  };

  if (!Array.isArray(hits[0])) {
    const rolls = hits as number[];
    return rolls.map((r) => apply(cloneState(initial), r));
  }

  const [hit1, hit2] = hits as [number[], number[]];
  const totals = new Set<number>();
  for (const a of hit1) {
    for (const b of hit2) {
      const state = cloneState(initial);
      const r1 = apply(state, a);
      const r2 = apply(state, b);
      totals.add(r1 + r2);
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
      return recoilOneThirdHp(
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
    let totals = sumRecoilAcrossHits({
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

  let result = sumRecoilAcrossHits({
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
  /** Dex abilities[0] (sole ability for legal Megas). */
  dexAbility: string;
};

/**
 * Ability resolution before @smogon/calc. Mega → dex unless abilityOverride.
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
