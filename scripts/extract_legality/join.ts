import { toId } from "./to_id.js";
import type { JsonValue } from "./parse_ts_data.js";

export type BaseStats = {
  hp: number;
  atk: number;
  def: number;
  spa: number;
  spd: number;
  spe: number;
};

export type SpeciesAbilities = {
  "0"?: string;
  "1"?: string;
  H?: string;
  S?: string;
};

export type SpeciesEntry = {
  id: string;
  name: string;
  num: number;
  types: string[];
  base_stats: BaseStats;
  base_species_id: string | null;
  abilities: SpeciesAbilities;
  tags: string[];
  effective_tags: string[];
  is_nonstandard: string | null;
  tier: string | null;
};

function asRecord(v: JsonValue, ctx: string): Record<string, JsonValue> {
  if (typeof v !== "object" || v === null || Array.isArray(v)) {
    throw new Error(`${ctx}: expected object`);
  }
  return v as Record<string, JsonValue>;
}

function asString(v: JsonValue | undefined, ctx: string): string {
  if (typeof v !== "string") throw new Error(`${ctx}: expected string`);
  return v;
}

function asNumber(v: JsonValue | undefined, ctx: string): number {
  if (typeof v !== "number") throw new Error(`${ctx}: expected number`);
  return v;
}

function asStringArray(v: JsonValue | undefined, ctx: string): string[] {
  if (v === undefined) return [];
  if (!Array.isArray(v) || !v.every((x) => typeof x === "string")) {
    throw new Error(`${ctx}: expected string[]`);
  }
  return v as string[];
}

function readBaseStats(v: JsonValue | undefined, ctx: string): BaseStats {
  const o = asRecord(v ?? {}, ctx);
  return {
    hp: asNumber(o.hp, `${ctx}.hp`),
    atk: asNumber(o.atk, `${ctx}.atk`),
    def: asNumber(o.def, `${ctx}.def`),
    spa: asNumber(o.spa, `${ctx}.spa`),
    spd: asNumber(o.spd, `${ctx}.spd`),
    spe: asNumber(o.spe, `${ctx}.spe`),
  };
}

function ownTags(dex: Record<string, JsonValue>): string[] {
  return asStringArray(dex.tags, "tags");
}

/**
 * Union of own tags and every ancestor's tags via toId(baseSpecies).
 * Does not stop at the first non-empty tags array.
 */
export function effectiveTags(
  speciesId: string,
  pokedex: Record<string, JsonValue>,
): string[] {
  const seen = new Set<string>();
  const out = new Set<string>();
  let cur: string | null = speciesId;
  while (cur && !seen.has(cur)) {
    seen.add(cur);
    const entry = pokedex[cur];
    if (!entry) break;
    const dex = asRecord(entry, `pokedex.${cur}`);
    for (const t of ownTags(dex)) out.add(t);
    const base = dex.baseSpecies;
    if (typeof base !== "string" || !base) break;
    cur = toId(base);
  }
  return [...out];
}

function nonstandard(v: JsonValue | undefined): string | null {
  if (v === undefined || v === null) return null;
  if (typeof v === "string") return v;
  throw new Error(`isNonstandard: expected string|null, got ${typeof v}`);
}

function tier(v: JsonValue | undefined): string | null {
  if (v === undefined || v === null) return null;
  if (typeof v === "string") return v;
  throw new Error(`tier: expected string|null, got ${typeof v}`);
}

function readAbilities(v: JsonValue | undefined, ctx: string): SpeciesAbilities {
  if (v === undefined || v === null) return {};
  const o = asRecord(v, ctx);
  const out: SpeciesAbilities = {};
  for (const key of ["0", "1", "H", "S"] as const) {
    const val = o[key];
    if (typeof val === "string") out[key] = val;
  }
  return out;
}

/** Join champions formats-data onto base pokedex by Showdown id. Hard-fail on missing keys. */
export function joinSpecies(
  formatsData: Record<string, JsonValue>,
  pokedex: Record<string, JsonValue>,
): Record<string, SpeciesEntry> {
  const missing = Object.keys(formatsData).filter((id) => !(id in pokedex));
  if (missing.length) {
    throw new Error(
      `formats-data keys missing from pokedex (${missing.length}): ${missing.slice(0, 10).join(", ")}${missing.length > 10 ? "…" : ""}`,
    );
  }

  const out: Record<string, SpeciesEntry> = {};
  for (const id of Object.keys(formatsData)) {
    const fmt = asRecord(formatsData[id]!, `formats-data.${id}`);
    const dex = asRecord(pokedex[id]!, `pokedex.${id}`);
    const baseSpecies = dex.baseSpecies;
    const base_species_id =
      typeof baseSpecies === "string" && baseSpecies ? toId(baseSpecies) : null;
    out[id] = {
      id,
      name: asString(dex.name, `pokedex.${id}.name`),
      num: asNumber(dex.num, `pokedex.${id}.num`),
      types: asStringArray(dex.types, `pokedex.${id}.types`),
      base_stats: readBaseStats(dex.baseStats, `pokedex.${id}.baseStats`),
      base_species_id,
      abilities: readAbilities(dex.abilities, `pokedex.${id}.abilities`),
      tags: ownTags(dex),
      effective_tags: effectiveTags(id, pokedex),
      is_nonstandard: nonstandard(fmt.isNonstandard),
      tier: tier(fmt.tier),
    };
  }
  return out;
}
