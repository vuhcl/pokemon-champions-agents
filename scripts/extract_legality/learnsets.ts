import type { JsonValue } from "./parse_ts_data.js";

function asRecord(v: JsonValue, ctx: string): Record<string, JsonValue> {
  if (typeof v !== "object" || v === null || Array.isArray(v)) {
    throw new Error(`${ctx}: expected object`);
  }
  return v as Record<string, JsonValue>;
}

/** Champions learnsets pool → speciesId → sorted move ids. */
export function extractLearnsets(
  learnsetsTable: Record<string, JsonValue>,
): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const [id, raw] of Object.entries(learnsetsTable)) {
    const entry = asRecord(raw, `learnsets.${id}`);
    const learnset = entry.learnset;
    if (learnset === undefined) {
      out[id] = [];
      continue;
    }
    const ls = asRecord(learnset, `learnsets.${id}.learnset`);
    out[id] = Object.keys(ls).sort();
  }
  return out;
}
