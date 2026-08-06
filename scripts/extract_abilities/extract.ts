/**
 * Extract ability names + verbatim effect text from Showdown text/abilities.ts,
 * then join is_nonstandard from mechanical data/abilities.ts.
 * Phase A also stamps the approved sample tag-sets onto matching ids.
 *
 * Regenerate only via `npm run extract:abilities` (extract → apply_phase_b →
 * retarget). Running this file alone resets tags to SAMPLE only.
 */
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { extractDataTable } from "../extract_legality/parse_ts_data.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const DEFAULT_CACHE = path.join(ROOT, ".cache", "pokemon-showdown");
const OUT = path.join(ROOT, "data", "abilities", "all.v1.json");

type Tag = { target: string; activation: string; purpose: string };
type AbilityOut = {
  id: string;
  name: string;
  description: string;
  is_nonstandard: string | null;
  tags: Tag[];
  composed_of?: string[];
  provisional_purpose?: boolean;
  field?: { weather?: string; terrain?: string; gameType?: string };
};

/** Text-only ids with no mechanical Abilities row (Showdown text umbrella). */
const TEXT_ONLY_ALLOWED = new Set(["asone"]);

function nonstandard(v: unknown): string | null {
  if (v === undefined || v === null) return null;
  if (typeof v === "string") return v;
  throw new Error(`isNonstandard: expected string|null, got ${typeof v}`);
}

type SamplePatch = Partial<
  Pick<AbilityOut, "tags" | "composed_of" | "provisional_purpose" | "field">
>;

const T = (target: string, activation: string, purpose: string): Tag => ({
  target,
  activation,
  purpose,
});

/** Phase A sample only — remainder keep tags: []. */
const SAMPLE: Record<string, SamplePatch> = {
  contrary: { tags: [T("self", "triggered", "boost")] },
  simple: { tags: [T("self", "triggered", "boost")] },
  swiftswim: {
    tags: [T("self", "triggered", "boost")],
    field: { weather: "Rain", gameType: "Doubles" },
  },
  chlorophyll: {
    tags: [T("self", "triggered", "boost")],
    field: { weather: "Sun", gameType: "Doubles" },
  },
  surgesurfer: {
    tags: [T("self", "triggered", "boost")],
    field: { terrain: "Electric", gameType: "Doubles" },
  },
  plus: { tags: [T("self", "triggered", "boost")] },
  minus: { tags: [T("self", "triggered", "boost")] },
  drizzle: {
    tags: [
      T("ally", "unconditional", "support"),
      T("opponent", "unconditional", "support"),
    ],
  },
  drought: {
    tags: [
      T("ally", "unconditional", "support"),
      T("opponent", "unconditional", "support"),
    ],
  },
  electricsurge: {
    tags: [
      T("ally", "unconditional", "support"),
      T("opponent", "unconditional", "support"),
    ],
  },
  intimidate: { tags: [T("opponent", "unconditional", "disrupt")] },
  friendguard: { tags: [T("ally", "unconditional", "support")] },
  battery: { tags: [T("ally", "unconditional", "boost")] },
  lightningrod: {
    tags: [
      T("self", "unconditional", "support"),
      T("self", "triggered", "boost"),
      T("ally", "triggered", "support"),
    ],
  },
  stormdrain: {
    tags: [
      T("self", "unconditional", "support"),
      T("self", "triggered", "boost"),
      T("ally", "triggered", "support"),
    ],
  },
  neutralizinggas: {
    tags: [
      T("ally", "unconditional", "disrupt"),
      T("opponent", "unconditional", "disrupt"),
    ],
  },
  roughskin: { tags: [T("opponent", "triggered", "disrupt")] },
  ironbarbs: { tags: [T("opponent", "triggered", "disrupt")] },
  cursedbody: { tags: [T("opponent", "triggered", "disrupt")] },
  hugepower: { tags: [T("self", "unconditional", "boost")] },
  regenerator: { tags: [T("self", "unconditional", "support")] },
  multiscale: { tags: [T("self", "unconditional", "support")] },
  speedboost: { tags: [T("self", "unconditional", "boost")] },
  adaptability: { tags: [T("self", "unconditional", "boost")] },
  flashfire: {
    tags: [T("self", "unconditional", "support"), T("self", "triggered", "boost")],
  },
  prankster: {
    tags: [T("self", "unconditional", "boost")],
    provisional_purpose: true,
  },
  trace: { tags: [T("self", "unconditional", "support")] },
  imposter: { tags: [T("self", "unconditional", "support")] },
  moody: {
    tags: [T("self", "unconditional", "boost"), T("self", "unconditional", "disrupt")],
  },
  asoneglastrier: {
    tags: [T("opponent", "unconditional", "disrupt"), T("self", "triggered", "boost")],
    composed_of: ["unnerve", "chillingneigh"],
  },
  asonespectrier: {
    tags: [T("opponent", "unconditional", "disrupt"), T("self", "triggered", "boost")],
    composed_of: ["unnerve", "grimneigh"],
  },
};

function gitCommit(repo: string): string {
  return execFileSync("git", ["-C", repo, "rev-parse", "HEAD"], {
    encoding: "utf8",
  }).trim();
}

function asRecord(v: unknown): Record<string, unknown> | null {
  if (v && typeof v === "object" && !Array.isArray(v)) {
    return v as Record<string, unknown>;
  }
  return null;
}

function pickDescription(entry: Record<string, unknown>): string {
  const desc = entry.desc;
  const shortDesc = entry.shortDesc;
  if (typeof desc === "string" && desc.length > 0) return desc;
  if (typeof shortDesc === "string" && shortDesc.length > 0) return shortDesc;
  return "";
}

function main(): void {
  const textPath = path.join(DEFAULT_CACHE, "data", "text", "abilities.ts");
  if (!fs.existsSync(textPath)) {
    throw new Error(
      `Missing ${textPath}. Run npm run extract:legality first (or clone pokemon-showdown into .cache).`,
    );
  }

  const sourceFiles = ["data/text/abilities.ts"];
  const table = extractDataTable(fs.readFileSync(textPath, "utf8"), textPath, "AbilitiesText");

  const modPath = path.join(DEFAULT_CACHE, "data", "mods", "champions", "abilities.ts");
  let modOverrides = 0;
  if (fs.existsSync(modPath)) {
    const modTable = extractDataTable(fs.readFileSync(modPath, "utf8"), modPath, "Abilities");
    for (const [id, raw] of Object.entries(modTable)) {
      const mod = asRecord(raw);
      if (!mod) continue;
      const hasText =
        typeof mod.desc === "string" || typeof mod.shortDesc === "string";
      if (!hasText) continue;
      const base = asRecord(table[id]) ?? {};
      if (typeof mod.desc === "string") base.desc = mod.desc;
      if (typeof mod.shortDesc === "string") base.shortDesc = mod.shortDesc;
      if (typeof mod.name === "string") base.name = mod.name;
      table[id] = base;
      modOverrides += 1;
      if (!sourceFiles.includes("data/mods/champions/abilities.ts")) {
        sourceFiles.push("data/mods/champions/abilities.ts");
      }
    }
  }

  const mechPath = path.join(DEFAULT_CACHE, "data", "abilities.ts");
  if (!fs.existsSync(mechPath)) {
    throw new Error(`Missing ${mechPath}`);
  }
  sourceFiles.push("data/abilities.ts");
  const mechTable = extractDataTable(
    fs.readFileSync(mechPath, "utf8"),
    mechPath,
    "Abilities",
  );

  const abilities: Record<string, AbilityOut> = {};
  const unexpectedTextOnly: string[] = [];
  for (const [id, raw] of Object.entries(table)) {
    const entry = asRecord(raw);
    if (!entry) continue;
    const name = typeof entry.name === "string" ? entry.name : id;
    const description = pickDescription(entry);
    if (!description && id === "noability") {
      // keep "Does nothing." from shortDesc path; if empty skip
    }
    const mech = asRecord(mechTable[id]);
    let is_nonstandard: string | null;
    if (mech) {
      is_nonstandard = nonstandard(mech.isNonstandard);
    } else if (TEXT_ONLY_ALLOWED.has(id)) {
      is_nonstandard = null;
    } else {
      unexpectedTextOnly.push(id);
      is_nonstandard = null;
    }
    const out: AbilityOut = {
      id,
      name,
      description,
      is_nonstandard,
      tags: [],
    };
    const patch = SAMPLE[id];
    if (patch) {
      if (patch.tags) out.tags = patch.tags;
      if (patch.composed_of) out.composed_of = patch.composed_of;
      if (patch.provisional_purpose) out.provisional_purpose = true;
      if (patch.field) out.field = patch.field;
    }
    abilities[id] = out;
  }
  if (unexpectedTextOnly.length) {
    throw new Error(
      `Text ability ids missing from data/abilities.ts (expected only {asone}): ${unexpectedTextOnly.join(", ")}`,
    );
  }

  const payload = {
    meta: {
      schema_version: 1,
      extracted_at: new Date().toISOString(),
      source: {
        repo: "pokemon-showdown",
        commit: gitCommit(DEFAULT_CACHE),
        files: sourceFiles,
        champions_text_overrides: modOverrides,
      },
      taxonomy_status: "sample_pending_review",
      taxonomy: "target_activation_purpose_v1",
      target_axis: ["self", "ally", "opponent"],
    },
    abilities,
  };

  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(payload) + "\n");
  const tagged = Object.values(abilities).filter((a) => a.tags.length > 0).length;
  console.error(
    `Wrote ${OUT} (${Object.keys(abilities).length} abilities, ${tagged} sample-tagged)`,
  );
}

main();
