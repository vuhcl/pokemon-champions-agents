/**
 * Join is_nonstandard onto data/moves/gen9_accuracy.v1.json from Showdown
 * mechanical moves (base ⊕ Champions), matching the legality snapshot merge.
 *
 * Preserves existing accuracy / multihit / multiaccuracy fields.
 * Usage: npm run extract:move-accuracy
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { mergeMoves } from "../extract_legality/merge_moves.js";
import { extractDataTable } from "../extract_legality/parse_ts_data.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const DEFAULT_CACHE = path.join(ROOT, ".cache", "pokemon-showdown");
const OUT = path.join(ROOT, "data", "moves", "gen9_accuracy.v1.json");

function main(): void {
  if (!fs.existsSync(OUT)) {
    throw new Error(`Missing ${OUT}`);
  }
  const basePath = path.join(DEFAULT_CACHE, "data", "moves.ts");
  const champPath = path.join(DEFAULT_CACHE, "data", "mods", "champions", "moves.ts");
  if (!fs.existsSync(basePath)) {
    throw new Error(
      `Missing ${basePath}. Run npm run extract:legality first (or clone pokemon-showdown into .cache).`,
    );
  }
  if (!fs.existsSync(champPath)) {
    throw new Error(`Missing ${champPath}`);
  }

  const acc = JSON.parse(fs.readFileSync(OUT, "utf8")) as Record<
    string,
    Record<string, unknown>
  >;
  const base = extractDataTable(fs.readFileSync(basePath, "utf8"), basePath, "Moves");
  const champions = extractDataTable(
    fs.readFileSync(champPath, "utf8"),
    champPath,
    "Moves",
  );
  const merged = mergeMoves(base, [champions]);

  const counts: Record<string, number> = {};
  const missing: string[] = [];
  for (const id of Object.keys(acc)) {
    const entry = merged[id];
    if (!entry) {
      missing.push(id);
      continue;
    }
    const flag = entry.is_nonstandard;
    acc[id] = { ...acc[id], is_nonstandard: flag };
    const key = flag === null ? "null" : flag;
    counts[key] = (counts[key] ?? 0) + 1;
  }
  if (missing.length) {
    throw new Error(
      `Accuracy keys missing from merged moves (${missing.length}): ${missing.slice(0, 20).join(", ")}`,
    );
  }

  fs.writeFileSync(OUT, JSON.stringify(acc) + "\n");
  const nonNull = Object.entries(counts)
    .filter(([k]) => k !== "null")
    .reduce((s, [, n]) => s + n, 0);
  console.error(
    `Wrote ${OUT} (${Object.keys(acc).length} moves, ${nonNull} nonstandard) counts=${JSON.stringify(counts)}`,
  );
}

main();
