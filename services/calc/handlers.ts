/**
 * Thin wrappers around @smogon/calc (Champions = Generations.get(0)) and @pkmn/sets.
 * No search/optimization — that stays in Python.
 */
import {calculate, Field, Generations, Move, Pokemon, Side} from '@smogon/calc';
import {Sets} from '@pkmn/sets';
import type {PokemonSet} from '@pkmn/sets';

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
  moves?: string[];
  nature?: string;
  /** Champions SP 0–32 (field name is still `evs` in Showdown/calc). */
  evs?: StatSpread;
  /** Accepted but ignored for gen 0 — calc forces level 50. */
  level?: number;
};

export type SideSpec = Partial<{
  isReflect: boolean;
  isLightScreen: boolean;
  isAuroraVeil: boolean;
  isTailwind: boolean;
  isHelpingHand: boolean;
  isFriendGuard: boolean;
  isBattery: boolean;
  spikes: number;
  isSR: boolean;
}>;

export type FieldSpec = Partial<{
  gameType: 'Singles' | 'Doubles';
  weather:
    | 'Sand'
    | 'Sun'
    | 'Rain'
    | 'Hail'
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

function toPokemon(spec: PokemonSpec): Pokemon {
  if (!spec?.species) throw new Error('species is required');
  return new Pokemon(GEN, spec.species, {
    item: spec.item,
    ability: spec.ability,
    moves: spec.moves,
    nature: spec.nature,
    evs: spec.evs,
  });
}

export function runCalculate(req: CalcRequest): CalcSuccess {
  if (!req?.move) throw new Error('move is required');
  const attacker = toPokemon(req.attacker);
  const defender = toPokemon(req.defender);
  const move = new Move(GEN, req.move);
  const field = toField(req.field, move.target);
  const result = calculate(GEN, attacker, defender, move, field);
  const range = result.range();
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
      recovery: result.recovery(),
      recoil: result.recoil(),
      stats: {
        attacker: {...attacker.rawStats},
        defender: {...defender.rawStats},
      },
    },
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
