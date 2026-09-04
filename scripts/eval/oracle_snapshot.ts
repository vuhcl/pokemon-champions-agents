/**
 * Eval-only Champions legality extract → caller --out path (never production snapshot).
 *
 *   npx tsx scripts/eval/oracle_snapshot.ts --out /tmp/oracle.json
 */
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { joinSpecies } from "../extract_legality/join.js";
import { mergeItems } from "../extract_legality/merge_items.js";
import {
  extractDataTable,
  extractFlatRules,
  clearIdentifierSkips,
} from "../extract_legality/parse_ts_data.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const DEFAULT_CACHE = path.join(ROOT, ".cache", "pokemon-showdown");

function parseArgs(argv: string[]): { out?: string; showdownPath?: string } {
  let out: string | undefined;
  let showdownPath: string | undefined;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--out") out = argv[++i];
    else if (a.startsWith("--out=")) out = a.slice("--out=".length);
    else if (a === "--showdown-path") showdownPath = argv[++i];
    else if (a.startsWith("--showdown-path="))
      showdownPath = a.slice("--showdown-path=".length);
  }
  return { out, showdownPath };
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
  const { out, showdownPath } = parseArgs(process.argv.slice(2));
  if (!out) throw new Error("--out <path> is required");

  const repo = ensureShowdown(showdownPath);
  const commit = gitHead(repo);
  console.error(`Eval oracle extract from ${repo} @ ${commit}`);

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
  const flat_rules = extractFlatRules(
    read(repo, "data/mods/champions/rulesets.ts"),
    "data/mods/champions/rulesets.ts",
  );

  const snapshot = {
    meta: {
      schema_version: 3 as const,
      extracted_at: new Date().toISOString(),
      source: { repo: "smogon/pokemon-showdown", commit, mod: "champions" },
      purpose: "eval_oracle",
    },
    flat_rules,
    species: joinSpecies(championsFormats, pokedex),
    items: mergeItems(baseItems, [championsItems]),
  };

  const outPath = path.resolve(out);
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, `${JSON.stringify(snapshot, null, 2)}\n`);
  console.error(`Wrote ${outPath}`);
}

main();
