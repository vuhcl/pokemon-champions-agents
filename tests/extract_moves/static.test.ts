import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const STATIC = path.join(ROOT, "data", "moves", "static.v1.json");
const FLAGS = path.join(ROOT, "data", "moves", "flags.v1.json");
const LEGALITY = path.join(ROOT, "data", "legality", "champions.v1.json");

type StaticSnap = {
  meta: {
    source: string;
    source_commit: string;
    mod: string;
    filter: string;
    pp_formula: string;
    extracted_at: string;
    move_count: number;
  };
  moves: Record<
    string,
    {
      id: string;
      name: string;
      priority: number;
      target: string;
      pp: number;
    }
  >;
};

describe("data/moves/static.v1.json", () => {
  const snap = JSON.parse(fs.readFileSync(STATIC, "utf8")) as StaticSnap;
  const flags = JSON.parse(fs.readFileSync(FLAGS, "utf8")) as { moves: Record<string, unknown> };
  const legality = JSON.parse(fs.readFileSync(LEGALITY, "utf8")) as {
    moves: Record<string, { is_nonstandard?: string | null }>;
  };
  const legalIds = Object.keys(legality.moves)
    .filter((id) => legality.moves[id]?.is_nonstandard == null)
    .sort();

  it("has required meta fields and computed move_count", () => {
    assert.match(snap.meta.source, /mods\/champions\/moves\.ts/);
    assert.match(snap.meta.filter, /champions-legal/);
    assert.equal(snap.meta.mod, "champions");
    assert.equal(snap.meta.source_commit, "9fb3a5b99f1a0bea17f495c5cc1bfe04fdd19c3e");
    assert.match(snap.meta.pp_formula, /calculatePP/);
    assert.match(snap.meta.pp_formula, /init\(\)/);
    assert.ok(typeof snap.meta.extracted_at === "string" && snap.meta.extracted_at.length > 0);
    assert.equal(snap.meta.move_count, Object.keys(snap.moves).length);
    assert.equal(snap.meta.move_count, 515);
  });

  it("schema: id===key; name string; priority/pp numbers; target string", () => {
    for (const [id, m] of Object.entries(snap.moves)) {
      assert.equal(m.id, id);
      assert.equal(typeof m.name, "string");
      assert.equal(typeof m.priority, "number");
      assert.equal(typeof m.pp, "number");
      assert.equal(typeof m.target, "string");
      assert.ok(Number.isInteger(m.pp));
    }
  });

  it("move-id set equals legality-legal moves (is_nonstandard null)", () => {
    assert.deepEqual(Object.keys(snap.moves).sort(), legalIds);
  });

  it("every flags.v1.json key is also in static.v1.json (flags subset)", () => {
    for (const id of Object.keys(flags.moves)) {
      assert.ok(snap.moves[id], `flags move missing from static: ${id}`);
    }
  });

  it("spot checks: priorities", () => {
    assert.equal(snap.moves.fakeout.priority, 3);
    assert.equal(snap.moves.followme.priority, 2);
    assert.equal(snap.moves.ragepowder.priority, 2);
    assert.equal(snap.moves.protect.priority, 4);
  });

  it("spot checks: rockslide target", () => {
    assert.equal(snap.moves.rockslide.target, "allAdjacentFoes");
  });

  it("spot checks: displayed PP", () => {
    assert.equal(snap.moves.closecombat.pp, 8);
    assert.equal(snap.moves.wish.pp, 8);
    assert.equal(snap.moves.calmmind.pp, 20);
    assert.equal(snap.moves.fakeout.pp, 12);
    assert.equal(snap.moves.followme.pp, 20);
  });
});
