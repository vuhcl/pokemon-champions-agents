/**
 * Build data/moves/flags.v1.json from Showdown mechanical moves
 * (base ⊕ Champions), retaining battle-flow flags for Pass 2.
 *
 * Usage: npm run extract:move-flags
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { extractDataTable, type JsonValue } from "../extract_legality/parse_ts_data.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const DEFAULT_CACHE = path.join(ROOT, ".cache", "pokemon-showdown");
const OUT = path.join(ROOT, "data", "moves", "flags.v1.json");

function asRecord(v: JsonValue | undefined): Record<string, JsonValue> | undefined {
  if (typeof v !== "object" || v === null || Array.isArray(v)) return undefined;
  return v as Record<string, JsonValue>;
}

function flagsOf(move: Record<string, JsonValue>): Record<string, 1> | undefined {
  const raw = asRecord(move.flags);
  if (!raw) return undefined;
  const out: Record<string, 1> = {};
  for (const [k, v] of Object.entries(raw)) {
    if (v === 1 || v === true) out[k] = 1;
  }
  return Object.keys(out).length ? out : undefined;
}

function main(): void {
  const basePath = path.join(DEFAULT_CACHE, "data", "moves.ts");
  const champPath = path.join(DEFAULT_CACHE, "data", "mods", "champions", "moves.ts");
  for (const p of [basePath, champPath]) {
    if (!fs.existsSync(p)) {
      throw new Error(
        `Missing ${p}. Run npm run extract:legality first (or clone pokemon-showdown into .cache).`,
      );
    }
  }

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

  const moves: Record<string, unknown> = {};
  for (const [id, move] of Object.entries(merged)) {
    if (move.isNonstandard != null) continue;
    if (typeof move.name !== "string" || typeof move.category !== "string") continue;
    const flags = flagsOf(move);
    const entry: Record<string, unknown> = {
      name: move.name,
      category: move.category,
      flags: flags ?? {},
    };
    if (typeof move.forceSwitch === "boolean") entry.forceSwitch = move.forceSwitch;
    if (move.selfSwitch === true || typeof move.selfSwitch === "string") {
      entry.selfSwitch = move.selfSwitch;
    }
    if (typeof move.breaksProtect === "boolean") entry.breaksProtect = move.breaksProtect;
    if (typeof move.stallingMove === "boolean") entry.stallingMove = move.stallingMove;
    // Top-level volatileStatus (Protect, etc.) or self.volatileStatus (Outrage lock / recharge).
    if (typeof move.volatileStatus === "string") {
      entry.volatileStatus = move.volatileStatus;
    } else {
      const self = asRecord(move.self);
      if (typeof self?.volatileStatus === "string") {
        entry.volatileStatus = self.volatileStatus;
      }
    }
    moves[id] = entry;
  }

  const sorted = Object.fromEntries(Object.entries(moves).sort(([a], [b]) => a.localeCompare(b)));
  const payload = {
    meta: {
      source: "pokemon-showdown/data/moves.ts ⊕ mods/champions/moves.ts",
      filter: "champions-legal",
    },
    moves: sorted,
  };
  fs.writeFileSync(OUT, JSON.stringify(payload, null, 2) + "\n");
  console.error(`Wrote ${OUT} (${Object.keys(sorted).length} moves)`);
}

main();
