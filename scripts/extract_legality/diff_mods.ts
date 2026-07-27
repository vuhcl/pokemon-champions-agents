import type { JsonValue } from "./parse_ts_data.js";
import type { ItemEntry } from "./merge_items.js";

export type LegalitySignals = {
  is_nonstandard: string | null;
  tier?: string | null;
};

export type DiffChange = "became_legal" | "became_illegal" | "other";

export type DiffEntry = {
  id: string;
  from: LegalitySignals;
  to: LegalitySignals;
  change: DiffChange;
};

function nonstandard(v: JsonValue | undefined): string | null {
  if (v === undefined || v === null) return null;
  if (typeof v === "string") return v;
  throw new Error(`isNonstandard: expected string|null`);
}

function tier(v: JsonValue | undefined): string | null {
  if (v === undefined || v === null) return null;
  if (typeof v === "string") return v;
  throw new Error(`tier: expected string|null`);
}

function asRecord(v: JsonValue, ctx: string): Record<string, JsonValue> {
  if (typeof v !== "object" || v === null || Array.isArray(v)) {
    throw new Error(`${ctx}: expected object`);
  }
  return v as Record<string, JsonValue>;
}

/** Available when is_nonstandard is null and (species) tier !== "Illegal". */
export function isAvailable(signals: LegalitySignals, kind: "species" | "item"): boolean {
  if (signals.is_nonstandard !== null) return false;
  if (kind === "species" && signals.tier === "Illegal") return false;
  return true;
}

export function classifyChange(
  from: LegalitySignals,
  to: LegalitySignals,
  kind: "species" | "item",
): DiffChange {
  const a = isAvailable(from, kind);
  const b = isAvailable(to, kind);
  if (!a && b) return "became_legal";
  if (a && !b) return "became_illegal";
  return "other";
}

function sameSignals(a: LegalitySignals, b: LegalitySignals, kind: "species" | "item"): boolean {
  if (a.is_nonstandard !== b.is_nonstandard) return false;
  if (kind === "species" && (a.tier ?? null) !== (b.tier ?? null)) return false;
  return true;
}

/** Key-wise compare of two formats-data tables. */
export function diffSpeciesTables(
  fromTable: Record<string, JsonValue>,
  toTable: Record<string, JsonValue>,
): DiffEntry[] {
  const ids = new Set([...Object.keys(fromTable), ...Object.keys(toTable)]);
  const out: DiffEntry[] = [];
  for (const id of [...ids].sort()) {
    const fromRaw = fromTable[id];
    const toRaw = toTable[id];
    const from: LegalitySignals = fromRaw
      ? (() => {
          const r = asRecord(fromRaw, `from.${id}`);
          return { is_nonstandard: nonstandard(r.isNonstandard), tier: tier(r.tier) };
        })()
      : { is_nonstandard: null, tier: null };
    const to: LegalitySignals = toRaw
      ? (() => {
          const r = asRecord(toRaw, `to.${id}`);
          return { is_nonstandard: nonstandard(r.isNonstandard), tier: tier(r.tier) };
        })()
      : { is_nonstandard: null, tier: null };
    if (sameSignals(from, to, "species")) continue;
    out.push({
      id,
      from,
      to,
      change: classifyChange(from, to, "species"),
    });
  }
  return out;
}

/** Compare two effective item maps. */
export function diffItemMaps(
  fromItems: Record<string, ItemEntry>,
  toItems: Record<string, ItemEntry>,
): DiffEntry[] {
  const ids = new Set([...Object.keys(fromItems), ...Object.keys(toItems)]);
  const out: DiffEntry[] = [];
  for (const id of [...ids].sort()) {
    const from: LegalitySignals = {
      is_nonstandard: fromItems[id]?.is_nonstandard ?? null,
    };
    const to: LegalitySignals = {
      is_nonstandard: toItems[id]?.is_nonstandard ?? null,
    };
    if (sameSignals(from, to, "item")) continue;
    out.push({
      id,
      from,
      to,
      change: classifyChange(from, to, "item"),
    });
  }
  return out;
}
