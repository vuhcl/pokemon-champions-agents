/**
 * Build data/moves/stat_boosts.v1.json from Showdown mechanical moves
 * (base ⊕ Champions), keeping each stat change attributed to whoever receives it.
 *
 * Showdown spreads stat changes across four shapes that all mean different things:
 *   boosts            → the move's target (the user iff target === "self")
 *   self.boosts       → the user, guaranteed
 *   selfBoost.boosts  → the user, guaranteed (multi-hit moves, e.g. Scale Shot)
 *   secondary(ies)    → .boosts hits the target, .self.boosts hits the user, chance-gated
 * Flattening these into one field conflates a self-debuff (Overheat) with a foe
 * debuff (Acid Spray), so each effect is emitted separately with its recipient.
 *
 * Usage: npm run extract:move-stat-boosts
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { extractDataTable, type JsonValue } from "../extract_legality/parse_ts_data.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const DEFAULT_CACHE = path.join(ROOT, ".cache", "pokemon-showdown");
const OUT = path.join(ROOT, "data", "moves", "stat_boosts.v1.json");

type Boosts = Record<string, number>;
type BoostEffect = { to: "self" | "target"; chance: number; stats: Boosts; note?: string };

/**
 * Moves whose stat changes are assigned inside a method body (skipped by the TS
 * parser, which only serializes literals), so no static extraction can reach them.
 * Kept explicit rather than dropped — each needs its real condition recorded.
 */
const CODE_ONLY_BOOSTS: Record<string, BoostEffect[]> = {
  // onTryHit: a non-Ghost user gets move.self = {boosts}; a Ghost user instead
  // pays half its HP for the curse volatile and gets no stat change at all.
  curse: [
    {
      to: "self",
      chance: 100,
      stats: { spe: -1, atk: 1, def: 1 },
      note: "non-Ghost user only; a Ghost user gets no stat change",
    },
  ],
};

function asRecord(v: JsonValue | undefined): Record<string, JsonValue> | undefined {
  if (typeof v !== "object" || v === null || Array.isArray(v)) return undefined;
  return v as Record<string, JsonValue>;
}

function boostsOf(v: JsonValue | undefined, ctx: string): Boosts | undefined {
  const rec = asRecord(v);
  if (!rec) return undefined;
  const out: Boosts = {};
  for (const [stat, stages] of Object.entries(rec)) {
    if (typeof stages !== "number") {
      throw new Error(`${ctx}.${stat}: expected number, got ${typeof stages}`);
    }
    out[stat] = stages;
  }
  return Object.keys(out).length ? out : undefined;
}

/** Every stat change the move applies, tagged with its recipient and chance. */
function boostEffects(move: Record<string, JsonValue>, id: string): BoostEffect[] {
  const codeOnly = CODE_ONLY_BOOSTS[id];
  if (codeOnly) return codeOnly;

  const out: BoostEffect[] = [];
  const target = typeof move.target === "string" ? move.target : "normal";

  const direct = boostsOf(move.boosts, `${id}.boosts`);
  // `allies` covers the user as well as its partners (Howl), so it lands on both.
  const recipients: BoostEffect["to"][] =
    target === "self" ? ["self"] : target === "allies" ? ["self", "target"] : ["target"];
  if (direct) {
    for (const to of recipients) out.push({ to, chance: 100, stats: direct });
  }

  for (const key of ["self", "selfBoost"] as const) {
    const stats = boostsOf(asRecord(move[key])?.boosts, `${id}.${key}.boosts`);
    if (stats) out.push({ to: "self", chance: 100, stats });
  }

  const secondaries: JsonValue[] = Array.isArray(move.secondaries)
    ? move.secondaries
    : move.secondary != null
      ? [move.secondary]
      : [];
  for (const [i, raw] of secondaries.entries()) {
    const sec = asRecord(raw);
    if (!sec) continue;
    const chance = typeof sec.chance === "number" ? sec.chance : 100;
    const onTarget = boostsOf(sec.boosts, `${id}.secondary[${i}].boosts`);
    if (onTarget) out.push({ to: "target", chance, stats: onTarget });
    const onSelf = boostsOf(asRecord(sec.self)?.boosts, `${id}.secondary[${i}].self.boosts`);
    if (onSelf) out.push({ to: "self", chance, stats: onSelf });
  }
  return out;
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

  // Champions entries are `inherit: true` patches — per-key override, later wins.
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
    const boosts = boostEffects(move, id);
    if (!boosts.length) continue;
    moves[id] = {
      name: move.name,
      category: move.category,
      target: typeof move.target === "string" ? move.target : "normal",
      boosts,
    };
  }

  const sorted = Object.fromEntries(Object.entries(moves).sort(([a], [b]) => a.localeCompare(b)));
  const payload = {
    meta: { source: "pokemon-showdown/data/moves.ts", filter: "champions-legal" },
    moves: sorted,
  };
  fs.writeFileSync(OUT, JSON.stringify(payload, null, 2) + "\n");

  const selfOnly = Object.values(sorted).filter((m) =>
    (m as { boosts: BoostEffect[] }).boosts.some((b) => b.to === "self"),
  ).length;
  console.error(
    `Wrote ${OUT} (${Object.keys(sorted).length} moves, ${selfOnly} with a self stat change)`,
  );
}

main();
