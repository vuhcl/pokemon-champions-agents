import type { JsonValue } from "./parse_ts_data.js";

export type MoveEntry = {
  id: string;
  name: string;
  type: string;
  category: string;
  basePower: number;
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
 * effective_moves = base moves.ts ⊕ champions moves.ts overrides (later wins).
 * Rows missing name/type/category/basePower (rare incomplete entries) are skipped.
 */
export function mergeMoves(
  baseMoves: Record<string, JsonValue>,
  overrideTables: Record<string, JsonValue>[],
): Record<string, MoveEntry> {
  const out: Record<string, MoveEntry> = {};
  for (const [id, raw] of Object.entries(baseMoves)) {
    const move = asRecord(raw, `moves.${id}`);
    if (typeof move.name !== "string" || typeof move.type !== "string") continue;
    if (typeof move.category !== "string" || typeof move.basePower !== "number") continue;
    out[id] = {
      id,
      name: move.name,
      type: move.type,
      category: move.category,
      basePower: move.basePower,
      is_nonstandard: nonstandard(move.isNonstandard),
    };
  }
  for (const overrides of overrideTables) {
    for (const [id, raw] of Object.entries(overrides)) {
      const ov = asRecord(raw, `move-override.${id}`);
      const existing = out[id];
      if (!existing) {
        if (
          typeof ov.name === "string" &&
          typeof ov.type === "string" &&
          typeof ov.category === "string" &&
          typeof ov.basePower === "number"
        ) {
          out[id] = {
            id,
            name: ov.name,
            type: ov.type,
            category: ov.category,
            basePower: ov.basePower,
            is_nonstandard: nonstandard(ov.isNonstandard),
          };
        }
        continue;
      }
      if ("isNonstandard" in ov) {
        existing.is_nonstandard = nonstandard(ov.isNonstandard);
      }
      if (typeof ov.name === "string") existing.name = ov.name;
      if (typeof ov.type === "string") existing.type = ov.type;
      if (typeof ov.category === "string") existing.category = ov.category;
      if (typeof ov.basePower === "number") existing.basePower = ov.basePower;
    }
  }
  return out;
}
