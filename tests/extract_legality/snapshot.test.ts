import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

import { toId } from "../../scripts/extract_legality/to_id.js";
import { effectiveTags, joinSpecies } from "../../scripts/extract_legality/join.js";
import { mergeItems } from "../../scripts/extract_legality/merge_items.js";
import { mergeMoves } from "../../scripts/extract_legality/merge_moves.js";
import { extractLearnsets } from "../../scripts/extract_legality/learnsets.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const SNAPSHOT = path.join(ROOT, "data", "legality", "champions.v1.json");
const DIFF = path.join(
  ROOT,
  "data",
  "legality",
  "fixtures",
  "championsregma_to_champions.diff.json",
);

type Snapshot = {
  meta: {
    schema_version: number;
    source: { commit: string; mod: string };
  };
  flat_rules: { banlist: string[] };
  species: Record<
    string,
    {
      id: string;
      name: string;
      types: string[];
      effective_tags: string[];
      abilities?: { "0"?: string; H?: string };
      base_species_id?: string | null;
    }
  >;
  items: Record<string, { id: string; name: string; is_nonstandard: string | null }>;
  moves?: Record<
    string,
    {
      id: string;
      name: string;
      type: string;
      category: string;
      basePower: number;
      is_nonstandard: string | null;
    }
  >;
  learnsets?: Record<string, string[]>;
};

type DiffFixture = {
  meta: { schema_version: number; from_mod: string; to_mod: string };
  species: { id: string }[];
  items: { id: string }[];
};

describe("toId / effective_tags / merge", () => {
  it("toId strips non-alphanumeric", () => {
    assert.equal(toId("Zacian-Crowned"), "zaciancrowned");
    assert.equal(toId("Venusaur"), "venusaur");
  });

  it("effective_tags unions along baseSpecies chain", () => {
    const pokedex = {
      zacian: { name: "Zacian", tags: ["Restricted Legendary"], num: 888, types: ["Fairy"], baseStats: { hp: 1, atk: 1, def: 1, spa: 1, spd: 1, spe: 1 } },
      zaciancrowned: {
        name: "Zacian-Crowned",
        baseSpecies: "Zacian",
        num: 888,
        types: ["Fairy", "Steel"],
        baseStats: { hp: 1, atk: 1, def: 1, spa: 1, spd: 1, spe: 1 },
      },
    };
    const tags = effectiveTags("zaciancrowned", pokedex);
    assert.ok(tags.includes("Restricted Legendary"));
  });

  it("joinSpecies hard-fails missing pokedex keys", () => {
    assert.throws(
      () => joinSpecies({ missingno: { tier: "Illegal" } }, {}),
      /missing from pokedex/,
    );
  });

  it("mergeItems applies overrides onto full base map", () => {
    const base = {
      potion: { name: "Potion", isNonstandard: null },
      abomasite: { name: "Abomasite", isNonstandard: "Past" },
    };
    const champions = {
      abomasite: { isNonstandard: null },
    };
    const merged = mergeItems(base, [champions]);
    assert.equal(Object.keys(merged).length, 2);
    assert.equal(merged.abomasite!.is_nonstandard, null);
    assert.equal(merged.potion!.is_nonstandard, null);
  });

  it("mergeMoves applies basePower / isNonstandard overrides", () => {
    const base = {
      earthquake: {
        name: "Earthquake",
        type: "Ground",
        category: "Physical",
        basePower: 100,
        isNonstandard: null,
      },
      absorb: {
        name: "Absorb",
        type: "Grass",
        category: "Special",
        basePower: 20,
        isNonstandard: null,
      },
    };
    const champions = {
      absorb: { isNonstandard: "Past" },
      earthquake: { basePower: 100 },
    };
    const merged = mergeMoves(base, [champions]);
    assert.equal(merged.absorb!.is_nonstandard, "Past");
    assert.equal(merged.earthquake!.basePower, 100);
    assert.equal(merged.earthquake!.type, "Ground");
  });

  it("extractLearnsets flattens move ids", () => {
    const table = {
      garchomp: { learnset: { earthquake: ["9M"], dragonclaw: ["9M"] } },
    };
    const ls = extractLearnsets(table);
    assert.deepEqual(ls.garchomp, ["dragonclaw", "earthquake"]);
  });
});

describe("committed champions.v1.json", () => {
  it("exists and passes schema invariants", () => {
    assert.ok(fs.existsSync(SNAPSHOT), `missing ${SNAPSHOT} — run npm run extract:legality`);
    const snap = JSON.parse(fs.readFileSync(SNAPSHOT, "utf8")) as Snapshot;

    assert.equal(snap.meta.schema_version, 2);
    assert.equal(snap.meta.source.mod, "champions");
    assert.match(snap.meta.source.commit, /^[0-9a-f]{40}$/);

    const ban = new Set(snap.flat_rules.banlist);
    assert.ok(ban.has("Mythical"));
    assert.ok(ban.has("Restricted Legendary"));
    assert.equal(ban.size, 2);

    const ids = Object.keys(snap.species);
    assert.ok(ids.length > 1000);
    for (const id of ids) {
      const s = snap.species[id]!;
      assert.equal(s.id, id);
      assert.equal(typeof s.name, "string");
      assert.ok(Array.isArray(s.types));
      assert.ok(Array.isArray(s.effective_tags));
    }

    const crowned = snap.species.zaciancrowned;
    assert.ok(crowned, "zaciancrowned missing");
    assert.ok(
      crowned.effective_tags.includes("Restricted Legendary"),
      `zaciancrowned.effective_tags=${JSON.stringify(crowned.effective_tags)}`,
    );

    const garchomp = snap.species.garchomp;
    assert.ok(garchomp, "garchomp missing");
    assert.ok(garchomp.abilities, "garchomp.abilities missing");
    assert.ok(
      garchomp.abilities!["0"] === "Sand Veil" || garchomp.abilities!.H === "Rough Skin",
      `garchomp.abilities=${JSON.stringify(garchomp.abilities)}`,
    );

    const itemIds = Object.keys(snap.items);
    assert.ok(itemIds.length > 100);
    for (const id of itemIds) {
      assert.equal(snap.items[id]!.id, id);
      assert.equal(typeof snap.items[id]!.name, "string");
    }

    assert.ok(snap.moves, "moves missing");
    const eq = snap.moves!.earthquake;
    assert.ok(eq, "earthquake missing");
    assert.equal(eq.name, "Earthquake");
    assert.equal(eq.type, "Ground");
    assert.equal(eq.category, "Physical");
    assert.equal(eq.basePower, 100);

    const absorb = snap.moves!.absorb;
    assert.ok(absorb);
    assert.equal(absorb.is_nonstandard, "Past");

    assert.ok(snap.learnsets, "learnsets missing");
    assert.ok(snap.learnsets!.garchomp?.includes("earthquake"));

    // Mega forms have no own learnset row — runtime walks base_species_id.
    const mega = snap.species.swampertmega;
    assert.ok(mega, "swampertmega missing from species");
    assert.equal(mega.base_species_id, "swampert");
    assert.equal("swampertmega" in (snap.learnsets || {}), false);
    assert.ok(
      snap.learnsets!.swampert?.includes("wavecrash"),
      "Swampert (base) must learn Wave Crash (Reg M-B)",
    );
  });
});

describe("committed championsregma→champions diff fixture", () => {
  it("is non-empty and ids exist in snapshot", () => {
    assert.ok(fs.existsSync(DIFF), `missing ${DIFF}`);
    const snap = JSON.parse(fs.readFileSync(SNAPSHOT, "utf8")) as Snapshot;
    const diff = JSON.parse(fs.readFileSync(DIFF, "utf8")) as DiffFixture;

    assert.equal(diff.meta.schema_version, 1);
    assert.equal(diff.meta.from_mod, "championsregma");
    assert.equal(diff.meta.to_mod, "champions");
    assert.ok(diff.species.length >= 1);
    assert.ok(Array.isArray(diff.items));

    for (const e of diff.species) {
      assert.ok(e.id in snap.species, `diff species id missing from snapshot: ${e.id}`);
    }
    for (const e of diff.items) {
      assert.ok(e.id in snap.items, `diff item id missing from snapshot: ${e.id}`);
    }
  });
});
