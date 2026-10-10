/**
 * Build data/moves/static.v1.json — Champions-legal priority, target, displayed PP.
 *
 * Allowlist = moves with is_nonstandard null in data/legality/champions.v1.json.
 * Displayed PP from mods/champions/scripts.ts at the pin:
 *   init(): raw pp > 20 → 20
 *   calculatePP(): noPPBoosts ? pp : (pp / 5 + 1) * 4
 *
 * Usage: npm run extract:move-static
 * Expect .cache/pokemon-showdown checked out to the legality pin Showdown commit.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { extractDataTable, type JsonValue } from "../extract_legality/parse_ts_data.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const DEFAULT_CACHE = path.join(ROOT, ".cache", "pokemon-showdown");
const LEGALITY = path.join(ROOT, "data", "legality", "champions.v1.json");
const OUT = path.join(ROOT, "data", "moves", "static.v1.json");
const SOURCE_COMMIT = "9fb3a5b99f1a0bea17f495c5cc1bfe04fdd19c3e";

type MoveEntry = {
  id: string;
  name: string;
  priority: number;
  target: string;
  pp: number;
};

function asRecord(v: JsonValue | undefined): Record<string, JsonValue> | undefined {
  if (typeof v !== "object" || v === null || Array.isArray(v)) return undefined;
  return v as Record<string, JsonValue>;
}

function displayedPp(raw: number, noPPBoosts: boolean): number {
  const capped = raw > 20 ? 20 : raw;
  return noPPBoosts ? capped : (capped / 5 + 1) * 4;
}

function main(): void {
  const basePath = path.join(DEFAULT_CACHE, "data", "moves.ts");
  const champPath = path.join(DEFAULT_CACHE, "data", "mods", "champions", "moves.ts");
  for (const p of [basePath, champPath, LEGALITY]) {
    if (!fs.existsSync(p)) {
      throw new Error(`Missing ${p}`);
    }
  }

  const legality = JSON.parse(fs.readFileSync(LEGALITY, "utf8")) as {
    moves: Record<string, { is_nonstandard?: string | null }>;
  };
  const allowlist = Object.keys(legality.moves)
    .filter((id) => legality.moves[id]?.is_nonstandard == null)
    .sort((a, b) => a.localeCompare(b));
  const allowSet = new Set(allowlist);

  const base = extractDataTable(fs.readFileSync(basePath, "utf8"), basePath, "Moves");
  const champions = extractDataTable(fs.readFileSync(champPath, "utf8"), champPath, "Moves");

  const merged: Record<string, Record<string, JsonValue>> = {};
  for (const [id, raw] of Object.entries(base)) {
    const rec = asRecord(raw);
    if (rec) merged[id] = { ...rec };
  }
  for (const [id, raw] of Object.entries(champions)) {
    const ov = asRecord(raw);
    if (!ov) continue;
    merged[id] = { ...(merged[id] ?? {}), ...ov };
  }

  // Champions overrides vs base, restricted to allowlist (extracted set)
  type Ov = { id: string; field: string; base: unknown; champions: unknown };
  const overrides: Ov[] = [];
  for (const [id, raw] of Object.entries(champions)) {
    if (!allowSet.has(id)) continue;
    const ov = asRecord(raw);
    const b = asRecord(base[id]);
    if (!ov) continue;
    for (const field of ["priority", "target", "pp"] as const) {
      if (!(field in ov)) continue;
      const bv = b?.[field];
      const cv = ov[field];
      if (bv !== cv) overrides.push({ id, field, base: bv ?? null, champions: cv });
    }
  }
  console.error("=== Champions overrides in extracted set (priority/target/raw pp) ===");
  for (const o of overrides.sort((a, b) => a.id.localeCompare(b.id) || a.field.localeCompare(b.field))) {
    console.error(`${o.id}\t${o.field}\tbase=${JSON.stringify(o.base)}\tchampions=${JSON.stringify(o.champions)}`);
  }

  // Overlay overrides outside allowlist (illegal / not extracted) — for report only
  const outsideOv: Ov[] = [];
  for (const [id, raw] of Object.entries(champions)) {
    if (allowSet.has(id)) continue;
    const ov = asRecord(raw);
    const b = asRecord(base[id]);
    if (!ov) continue;
    for (const field of ["priority", "target", "pp"] as const) {
      if (!(field in ov)) continue;
      const bv = b?.[field];
      const cv = ov[field];
      if (bv !== cv) outsideOv.push({ id, field, base: bv ?? null, champions: cv });
    }
  }
  if (outsideOv.length) {
    console.error("=== Champions overrides NOT in extracted set (absent from file) ===");
    for (const o of outsideOv.sort((a, b) => a.id.localeCompare(b.id) || a.field.localeCompare(b.field))) {
      console.error(`${o.id}\t${o.field}\tbase=${JSON.stringify(o.base)}\tchampions=${JSON.stringify(o.champions)}`);
    }
  }

  const missingFromMerged = allowlist.filter((id) => !merged[id]);
  if (missingFromMerged.length) {
    throw new Error(
      `FAIL: ${missingFromMerged.length} legality-legal ids missing from Showdown merge: ${missingFromMerged.slice(0, 30).join(", ")}`,
    );
  }

  const noPPBoostsIds: string[] = [];
  const oddRawPp: { id: string; raw: number }[] = [];
  const cappedFromGt20: string[] = [];
  const moves: Record<string, MoveEntry> = {};

  for (const id of allowlist) {
    const move = merged[id]!;
    if (typeof move.name !== "string") {
      throw new Error(`${id}: missing name`);
    }
    if (typeof move.target !== "string") {
      throw new Error(`${id}: missing target`);
    }
    if (typeof move.pp !== "number") {
      throw new Error(`${id}: missing/non-number raw pp`);
    }

    const raw = move.pp;
    const noPPBoosts = move.noPPBoosts === true;
    if (noPPBoosts) noPPBoostsIds.push(id);
    if (raw > 20) cappedFromGt20.push(id);
    else if (raw !== 5 && raw !== 10 && raw !== 15 && raw !== 20) {
      oddRawPp.push({ id, raw });
    }

    const displayed = displayedPp(raw, noPPBoosts);
    if (!Number.isInteger(displayed)) {
      throw new Error(
        `${id}: displayed PP not integer (raw=${raw}, noPPBoosts=${noPPBoosts}, displayed=${displayed})`,
      );
    }

    const priority = typeof move.priority === "number" ? move.priority : 0;
    moves[id] = {
      id,
      name: move.name,
      priority,
      target: move.target,
      pp: displayed,
    };
  }

  console.error("=== PP edge cases ===");
  console.error(`noPPBoosts (${noPPBoostsIds.length}): ${noPPBoostsIds.join(", ") || "(none)"}`);
  console.error(
    `odd raw pp not in {5,10,15,20,>20} (${oddRawPp.length}): ${oddRawPp.map((x) => `${x.id}:${x.raw}`).join(", ") || "(none)"}`,
  );
  console.error(
    `capped from >20 (${cappedFromGt20.length}): ${cappedFromGt20.join(", ") || "(none)"}`,
  );

  const sorted = Object.fromEntries(Object.entries(moves).sort(([a], [b]) => a.localeCompare(b)));
  const payload = {
    meta: {
      source: "pokemon-showdown/data/moves.ts ⊕ mods/champions/moves.ts",
      source_commit: SOURCE_COMMIT,
      mod: "champions",
      filter: "champions-legal (legality blob is_nonstandard null)",
      pp_formula:
        "data/mods/champions/scripts.ts: init() caps raw pp>20 to 20; calculatePP() = noPPBoosts ? pp : (pp/5+1)*4",
      extracted_at: new Date().toISOString(),
      move_count: Object.keys(sorted).length,
    },
    moves: sorted,
  };
  fs.writeFileSync(OUT, `${JSON.stringify(payload, null, 2)}\n`);
  console.error(`Wrote ${OUT} (${payload.meta.move_count} moves)`);
}

main();
