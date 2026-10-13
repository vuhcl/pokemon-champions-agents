/**
 * Thin wrappers around @smogon/calc (Champions = Generations.get(0)) and @pkmn/sets.
 * No search/optimization — that stays in Python.
 */
import {calculate, Field, Generations, Move, Pokemon, Side, toID} from '@smogon/calc';
import {Sets} from '@pkmn/sets';
import type {PokemonSet} from '@pkmn/sets';
import {
  buildInitialHitState,
  computeRecoilHp,
  resolveAbility,
  type AbilityResolution,
  type AbilityResolutionSide,
  type DisguiseForm,
  type RecoilHp,
} from './recoil.js';

/** Champions pseudo-generation in @smogon/calc — NOT Generations.get('champions'). */
const GEN = Generations.get(0);

export type StatSpread = Partial<{
  hp: number;
  atk: number;
  def: number;
  spa: number;
  spd: number;
  spe: number;
}>;

export type PokemonSpec = {
  species: string;
  item?: string;
  ability?: string;
  /** Explicit mid-battle / Trace / Skill Swap result; overrides plain + Mega dex. */
  abilityOverride?: string;
  moves?: string[];
  nature?: string;
  /** Champions SP 0–32 (field name is still `evs` in Showdown/calc). */
  evs?: StatSpread;
  /** Accepted but ignored for gen 0 — calc forces level 50. */
  level?: number;
  /** Stat stages (−6…+6), forwarded to @smogon/calc. */
  boosts?: StatSpread;
  /** Current HP; default max HP. */
  curHP?: number;
  /** Substitute present. Fresh HP = floor(maxHP/4) unless substituteHp set. */
  substitute?: boolean;
  substituteHp?: number;
  /** Turn-level Endure (defender). */
  endure?: boolean;
  /** Wrapper Disguise state; default disguised when ability is Disguise. */
  form?: DisguiseForm;
  /** Current types (Soak/etc.) → calc overrides.types. */
  types?: string[];
};

export type SideSpec = Partial<{
  isReflect: boolean;
  isLightScreen: boolean;
  isAuroraVeil: boolean;
  isTailwind: boolean;
  isHelpingHand: boolean;
  isFriendGuard: boolean;
  isBattery: boolean;
  isProtected: boolean;
  spikes: number;
  isSR: boolean;
}>;

export type FieldSpec = Partial<{
  gameType: 'Singles' | 'Doubles';
  weather:
    | 'Sand'
    | 'Sun'
    | 'Rain'
    | 'Snow'
    | 'Harsh Sunshine'
    | 'Heavy Rain'
    | 'Strong Winds';
  terrain: 'Electric' | 'Grassy' | 'Psychic' | 'Misty';
  isGravity: boolean;
  isMagicRoom: boolean;
  isWonderRoom: boolean;
  attackerSide: SideSpec;
  defenderSide: SideSpec;
}>;

export type CalcRequest = {
  attacker: PokemonSpec;
  defender: PokemonSpec;
  move: string;
  field?: FieldSpec;
  /** Forwarded to @smogon/calc Move `overrides` (e.g. Rage Fist BP). */
  moveOverrides?: {basePower?: number};
};

export type CalcSuccess = {
  damageRange: [number, number];
  koChance: string;
  raw: {
    damage: number | number[] | number[][];
    range: [number, number];
    kochance: {chance: number | undefined; n: number; text: string};
    desc: string;
    fullDesc: string;
    recovery: {recovery: [number, number]; text: string};
    recoil: {recoil: number | [number, number]; text: string};
    stats: {attacker: StatSpread; defender: StatSpread};
  };
  /**
   * Project-convention HP recoil for accepted damage-fraction encodings
   * ([33,100], [1,2], [1,4]) via sim half-up on total damage dealt.
   * Single-hit: per-roll array. Parental Bond: sorted distinct totals.
   * Rock Head / Magic Guard: 0. Else label string.
   */
  recoilHp: RecoilHp;
  abilityResolution?: AbilityResolution;
};

export type CalcResult = CalcSuccess | {error: string};

const SPREAD_TARGETS = new Set(['allAdjacent', 'allAdjacentFoes']);

function toSide(spec?: SideSpec): Side | undefined {
  if (!spec) return undefined;
  return new Side(spec);
}

function toField(spec: FieldSpec | undefined, moveTarget: string): Field {
  if (!spec) return new Field();
  if (spec.gameType === undefined && SPREAD_TARGETS.has(moveTarget)) {
    throw new Error('field.gameType required for spread moves');
  }
  return new Field({
    gameType: spec.gameType,
    weather: spec.weather,
    terrain: spec.terrain,
    isGravity: spec.isGravity,
    isMagicRoom: spec.isMagicRoom,
    isWonderRoom: spec.isWonderRoom,
    attackerSide: toSide(spec.attackerSide),
    defenderSide: toSide(spec.defenderSide),
  });
}

function dexAbility0(speciesName: string): string {
  const sp = GEN.species.get(toID(speciesName));
  if (!sp) throw new Error(`unknown Champions species: ${speciesName}`);
  const a0 = sp.abilities[0];
  if (!a0) throw new Error(`no dex ability for ${speciesName}`);
  return a0;
}

function resolveSide(spec: PokemonSpec): AbilityResolutionSide {
  return resolveAbility({
    species: spec.species,
    ability: spec.ability,
    abilityOverride: spec.abilityOverride,
    dexAbility: dexAbility0(spec.species),
  });
}

function shouldRecord(side: AbilityResolutionSide, isMega: boolean): boolean {
  if (side.source === 'override') return true;
  if (side.source === 'dex' && isMega) return true;
  if (side.source === 'request') return true;
  return false;
}

function toPokemon(spec: PokemonSpec, ability: string): Pokemon {
  if (!spec?.species) throw new Error('species is required');
  if (!GEN.species.get(toID(spec.species))) {
    throw new Error(`unknown Champions species: ${spec.species}`);
  }
  if (spec.item && !GEN.items.get(toID(spec.item))) {
    throw new Error(`unknown Champions item: ${spec.item}`);
  }
  const overrides = spec.types
    ? {types: spec.types as [string] | [string, string]}
    : undefined;
  return new Pokemon(GEN, spec.species, {
    item: spec.item,
    ability,
    moves: spec.moves,
    nature: spec.nature,
    evs: spec.evs,
    boosts: spec.boosts,
    curHP: spec.curHP,
    overrides,
  });
}

export function runCalculate(req: CalcRequest): CalcSuccess {
  if (!req?.move) throw new Error('move is required');

  const atkRes = resolveSide(req.attacker);
  const defRes = resolveSide(req.defender);

  const attacker = toPokemon(req.attacker, atkRes.applied);
  const defender = toPokemon(req.defender, defRes.applied);
  const move = new Move(
    GEN,
    req.move,
    req.moveOverrides ? {overrides: req.moveOverrides} : undefined,
  );
  const field = toField(req.field, move.target);
  const result = calculate(GEN, attacker, defender, move, field);
  const range = result.range();
  const stats = {
    attacker: {...attacker.rawStats},
    defender: {...defender.rawStats},
  };
  const recovery = result.recovery();
  const recoil = result.recoil();

  const isSpread =
    field.gameType !== 'Singles' && SPREAD_TARGETS.has(move.target);
  // Ability + not-spread + hits===1: treat nesting as PB; missing second hit → label.
  const parentalBond =
    atkRes.applied === 'Parental Bond' && move.hits === 1 && !isSpread;

  const initial = buildInitialHitState({
    maxHP: defender.rawStats.hp,
    curHP: req.defender.curHP,
    substitute: req.defender.substitute,
    substituteHp: req.defender.substituteHp,
    endure: req.defender.endure,
    form: req.defender.form,
    defenderAbility: defRes.applied,
    item: req.defender.item,
  });

  const recoilHp = computeRecoilHp({
    damage: result.damage,
    moveRecoil: move.recoil,
    moveHits: move.hits,
    isSpread,
    attackerAbility: atkRes.applied,
    defenderAbility: defRes.applied,
    infiltrator: atkRes.applied === 'Infiltrator',
    initial,
    parentalBond,
  });

  const abilityResolution: AbilityResolution = {};
  if (shouldRecord(atkRes, req.attacker.species.includes('-Mega'))) {
    abilityResolution.attacker = atkRes;
  }
  if (shouldRecord(defRes, req.defender.species.includes('-Mega'))) {
    abilityResolution.defender = defRes;
  }

  const base = {
    recoilHp,
    ...(Object.keys(abilityResolution).length
      ? {abilityResolution}
      : {}),
  };

  // Immunity / status / BP-0: calc returns damage 0. kochance()/desc() with
  // err=true throw "damage[damage.length - 1] === 0." — treat as success.
  if (range[1] === 0) {
    return {
      damageRange: range,
      koChance: '',
      raw: {
        damage: result.damage,
        range,
        kochance: {chance: 0, n: 0, text: ''},
        desc: '',
        fullDesc: '',
        recovery,
        recoil,
        stats,
      },
      ...base,
    };
  }
  const kochance = result.kochance();
  return {
    damageRange: range,
    koChance: kochance.text,
    raw: {
      damage: result.damage,
      range,
      kochance,
      desc: result.desc(),
      fullDesc: result.fullDesc(),
      recovery,
      recoil,
      stats,
    },
    ...base,
  };
}

export function runCalculateSafe(req: CalcRequest): CalcResult {
  try {
    return runCalculate(req);
  } catch (e) {
    return {error: e instanceof Error ? e.message : String(e)};
  }
}

export function runCalculateBatch(requests: CalcRequest[]): CalcResult[] {
  return requests.map(runCalculateSafe);
}

export type MovesBatchRequest = {
  attacker: PokemonSpec;
  defender: PokemonSpec;
  field?: FieldSpec;
  moves: string[];
  moveOverrides?: {basePower?: number};
};

export type MovesBatchEntry = CalcResult & {move: string};

const MOVES_BATCH_CAP = 32;

/**
 * Shared-side moves batch. Cap 32 on moves.length; over-cap → whole-call error.
 * Expands to CalcRequest[] → runCalculateBatch. /calculate/batch stays uncapped.
 */
export function runCalculateMovesBatch(
  req: MovesBatchRequest,
): MovesBatchEntry[] | {error: string} {
  if (!Array.isArray(req?.moves)) {
    return {error: 'moves array required'};
  }
  if (req.moves.length > MOVES_BATCH_CAP) {
    return {
      error: `moves length ${req.moves.length} exceeds cap ${MOVES_BATCH_CAP}`,
    };
  }
  const requests: CalcRequest[] = req.moves.map((move) => ({
    attacker: req.attacker,
    defender: req.defender,
    move,
    field: req.field,
    moveOverrides: req.moveOverrides,
  }));
  const results = runCalculateBatch(requests);
  return results.map((r, i) => ({...r, move: req.moves[i]!}));
}

export function setsPack(set: Partial<PokemonSet>): string {
  return Sets.pack(set);
}

export function setsUnpack(packed: string): PokemonSet {
  const set = Sets.unpack(packed);
  if (!set) throw new Error('unpack failed');
  return set;
}

export function setsImport(text: string): Partial<PokemonSet> {
  return Sets.importSet(text);
}

export function setsExport(set: Partial<PokemonSet>): string {
  return Sets.exportSet(set);
}
