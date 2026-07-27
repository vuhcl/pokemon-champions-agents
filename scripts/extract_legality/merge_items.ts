import type { JsonValue } from "./parse_ts_data.js";

export type ItemEntry = {
  id: string;
  name: string;
  is_nonstandard: string | null;
};

function asRecord(v: JsonValue, ctx: string): Record<string, JsonValue> {
  if (typeof v !== "object" || v === null || Array.isArray(v)) {
    throw new Error(`${ctx}: expected object`);
  }
  return v as Record<string, JsonValue>;
}

function nonstandard(v: JsonValue | undefined): string | null {
  if (v === undefined || v === null) return null;
  if (typeof v === "string") return v;
  throw new Error(`isNonstandard: expected string|null, got ${typeof v}`);
}

/**
 * effective_items(mod_stack) = base items, then each mod's items.ts overrides (later wins).
 * Returns the full effective map (all base ids, with overridden is_nonstandard where touched).
 */
export function mergeItems(
  baseItems: Record<string, JsonValue>,
  overrideTables: Record<string, JsonValue>[],
): Record<string, ItemEntry> {
  const out: Record<string, ItemEntry> = {};
  for (const [id, raw] of Object.entries(baseItems)) {
    const item = asRecord(raw, `items.${id}`);
    const name = item.name;
    if (typeof name !== "string") {
      throw new Error(`items.${id}.name: expected string`);
    }
    out[id] = {
      id,
      name,
      is_nonstandard: nonstandard(item.isNonstandard),
    };
  }
  for (const overrides of overrideTables) {
    for (const [id, raw] of Object.entries(overrides)) {
      const ov = asRecord(raw, `item-override.${id}`);
      const existing = out[id];
      if (!existing) {
        // Mod-only item not in base — keep if it has a name, else skip loud
        const name = ov.name;
        if (typeof name !== "string") {
          throw new Error(`item-override.${id}: unknown id with no name`);
        }
        out[id] = {
          id,
          name,
          is_nonstandard: nonstandard(ov.isNonstandard),
        };
        continue;
      }
      if ("isNonstandard" in ov) {
        existing.is_nonstandard = nonstandard(ov.isNonstandard);
      }
      if (typeof ov.name === "string") {
        existing.name = ov.name;
      }
    }
  }
  return out;
}
