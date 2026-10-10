import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const ACC = path.join(ROOT, "data", "moves", "gen9_accuracy.v1.json");
const LEGALITY = path.join(ROOT, "data", "legality", "champions.v1.json");

describe("data/moves/gen9_accuracy.v1.json", () => {
  const raw = JSON.parse(fs.readFileSync(ACC, "utf8")) as Record<string, unknown>;
  const meta = raw.meta as { source_commit: string; mod: string };
  const legality = JSON.parse(fs.readFileSync(LEGALITY, "utf8")) as {
    moves: Record<string, { is_nonstandard?: string | null }>;
  };
  const legalIds = Object.keys(legality.moves).filter(
    (id) => legality.moves[id]?.is_nonstandard == null,
  );

  it("records Showdown pin in meta", () => {
    assert.equal(meta.mod, "champions");
    assert.equal(meta.source_commit, "9fb3a5b99f1a0bea17f495c5cc1bfe04fdd19c3e");
  });

  it("every Champions-legal move has an accuracy entry marked standard", () => {
    for (const id of legalIds) {
      const entry = raw[id] as Record<string, unknown> | undefined;
      assert.ok(entry, `missing accuracy row for legal move ${id}`);
      assert.ok("accuracy" in entry, `${id}: missing accuracy field`);
      assert.equal(entry.is_nonstandard, null, id);
    }
  });
});
