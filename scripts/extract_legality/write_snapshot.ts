/**
 * Offline Showdown legality extractor (ADR-007b).
 *
 * Usage:
 *   npm run extract:legality
 *   npm run extract:legality -- --showdown-path /path/to/pokemon-showdown
 *   SHOWDOWN_PATH=/path/to/pokemon-showdown npm run extract:legality
 */
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { joinSpecies } from "./join.js";
import { extractLearnsets } from "./learnsets.js";
import { mergeItems } from "./merge_items.js";
import { mergeMoves } from "./merge_moves.js";
import { diffItemMaps, diffSpeciesTables } from "./diff_mods.js";
import {
  extractDataTable,
  extractFlatRules,
  extractFormatNames,
  clearIdentifierSkips,
  getIdentifierSkips,
} from "./parse_ts_data.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const DEFAULT_CACHE = path.join(ROOT, ".cache", "pokemon-showdown");
const OUT_SNAPSHOT = path.join(ROOT, "data", "legality", "champions.v1.json");
const OUT_DIFF = path.join(
  ROOT,
  "data",
  "legality",
  "fixtures",
  "championsregma_to_champions.diff.json",
);
const OUT_IDENTIFIER_SKIPS = path.join(
  ROOT,
  "data",
  "legality",
  "fixtures",
  "identifier_skips.json",
);

function parseArgs(argv: string[]): { showdownPath?: string } {
  let showdownPath: string | undefined;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--showdown-path") {
      showdownPath = argv[++i];
      if (!showdownPath) throw new Error("--showdown-path requires a value");
    } else if (a.startsWith("--showdown-path=")) {
      showdownPath = a.slice("--showdown-path=".length);
    }
  }
  return { showdownPath };
}

function ensureShowdown(override?: string): string {
  if (override) {
    const p = path.resolve(override);
    if (!fs.existsSync(path.join(p, "data", "pokedex.ts"))) {
      throw new Error(`SHOWDOWN_PATH does not look like pokemon-showdown: ${p}`);
    }
    return p;
  }
  const env = process.env.SHOWDOWN_PATH;
  if (env) return ensureShowdown(env);

  fs.mkdirSync(path.dirname(DEFAULT_CACHE), { recursive: true });
  if (!fs.existsSync(path.join(DEFAULT_CACHE, ".git"))) {
    console.error(`Cloning smogon/pokemon-showdown into ${DEFAULT_CACHE}…`);
    execFileSync(
      "git",
      ["clone", "--depth", "1", "https://github.com/smogon/pokemon-showdown.git", DEFAULT_CACHE],
      { stdio: "inherit" },
    );
  } else {
    console.error(`Updating ${DEFAULT_CACHE}…`);
    execFileSync("git", ["-C", DEFAULT_CACHE, "fetch", "--depth", "1", "origin"], {
      stdio: "inherit",
    });
    execFileSync("git", ["-C", DEFAULT_CACHE, "reset", "--hard", "FETCH_HEAD"], {
      stdio: "inherit",
    });
  }
  return DEFAULT_CACHE;
}

function gitHead(repo: string): string {
  return execFileSync("git", ["-C", repo, "rev-parse", "HEAD"], {
    encoding: "utf8",
  }).trim();
}

function read(repo: string, rel: string): string {
  return fs.readFileSync(path.join(repo, rel), "utf8");
}

function main(): void {
  const { showdownPath: argPath } = parseArgs(process.argv.slice(2));
  const repo = ensureShowdown(argPath);
  const commit = gitHead(repo);
  const extracted_at = new Date().toISOString();

  console.error(`Extracting from ${repo} @ ${commit}`);

  clearIdentifierSkips();

  const pokedex = extractDataTable(read(repo, "data/pokedex.ts"), "data/pokedex.ts", "Pokedex");
  const baseItems = extractDataTable(read(repo, "data/items.ts"), "data/items.ts", "Items");
  const championsFormats = extractDataTable(
    read(repo, "data/mods/champions/formats-data.ts"),
    "data/mods/champions/formats-data.ts",
    "FormatsData",
  );
  const championsItems = extractDataTable(
    read(repo, "data/mods/champions/items.ts"),
    "data/mods/champions/items.ts",
    "Items",
  );
  const regmaFormats = extractDataTable(
    read(repo, "data/mods/championsregma/formats-data.ts"),
    "data/mods/championsregma/formats-data.ts",
    "FormatsData",
  );
  const regmaItems = extractDataTable(
    read(repo, "data/mods/championsregma/items.ts"),
    "data/mods/championsregma/items.ts",
    "Items",
  );
  const flat_rules = extractFlatRules(
    read(repo, "data/mods/champions/rulesets.ts"),
    "data/mods/champions/rulesets.ts",
  );
  const formats = extractFormatNames(read(repo, "config/formats.ts"), "config/formats.ts");

  const baseMoves = extractDataTable(read(repo, "data/moves.ts"), "data/moves.ts", "Moves");
  const championsMoves = extractDataTable(
    read(repo, "data/mods/champions/moves.ts"),
    "data/mods/champions/moves.ts",
    "Moves",
  );
  const championsLearnsets = extractDataTable(
    read(repo, "data/mods/champions/learnsets.ts"),
    "data/mods/champions/learnsets.ts",
    "Learnsets",
  );

  const species = joinSpecies(championsFormats, pokedex);
  const items = mergeItems(baseItems, [championsItems]);
  const itemsRegma = mergeItems(baseItems, [championsItems, regmaItems]);
  const moves = mergeMoves(baseMoves, [championsMoves]);
  const learnsets = extractLearnsets(championsLearnsets);

  const snapshot = {
    meta: {
      schema_version: 2 as const,
      extracted_at,
      source: {
        repo: "smogon/pokemon-showdown",
        commit,
        mod: "champions",
      },
      formats,
    },
    flat_rules,
    species,
    items,
    moves,
    learnsets,
  };

  const speciesDiff = diffSpeciesTables(regmaFormats, championsFormats);
  const itemDiff = diffItemMaps(itemsRegma, items);
  const diff = {
    meta: {
      schema_version: 1 as const,
      extracted_at,
      source_commit: commit,
      from_mod: "championsregma",
      to_mod: "champions",
    },
    species: speciesDiff,
    items: itemDiff,
  };

  if (speciesDiff.length < 1) {
    throw new Error("expected non-empty species diff (championsregma → champions)");
  }

  fs.mkdirSync(path.dirname(OUT_SNAPSHOT), { recursive: true });
  fs.mkdirSync(path.dirname(OUT_DIFF), { recursive: true });
  fs.writeFileSync(OUT_SNAPSHOT, `${JSON.stringify(snapshot, null, 2)}\n`);
  fs.writeFileSync(OUT_DIFF, `${JSON.stringify(diff, null, 2)}\n`);

  const skips = [...getIdentifierSkips()];
  const skipReport = {
    meta: {
      extracted_at,
      source_commit: commit,
      note:
        "Identifier initializers during AST extract: 'nulled' = undefined→null stored; 'skipped' = other Identifier omitted",
    },
    counts: {
      nulled: skips.filter((s) => s.action === "nulled").length,
      skipped: skips.filter((s) => s.action === "skipped").length,
      total: skips.length,
    },
    entries: skips,
  };
  fs.writeFileSync(OUT_IDENTIFIER_SKIPS, `${JSON.stringify(skipReport, null, 2)}\n`);

  console.error(
    `Wrote ${OUT_SNAPSHOT} (${Object.keys(species).length} species, ${Object.keys(items).length} items, ${Object.keys(moves).length} moves, ${Object.keys(learnsets).length} learnsets)`,
  );
  console.error(
    `Wrote ${OUT_DIFF} (${speciesDiff.length} species flips, ${itemDiff.length} item flips)`,
  );
  console.error(
    `Identifier rule hits: ${skipReport.counts.nulled} nulled, ${skipReport.counts.skipped} skipped → ${OUT_IDENTIFIER_SKIPS}`,
  );
  for (const s of skips) {
    console.error(`  [${s.action}] ${s.file} :: ${s.path} = ${s.identifier}`);
  }
}

main();
