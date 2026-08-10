import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const FLAGS = path.join(ROOT, "data", "moves", "flags.v1.json");

type FlagsSnap = {
  meta: { source: string; filter: string };
  moves: Record<
    string,
    {
      name: string;
      category: string;
      flags: Record<string, 1>;
      breaksProtect?: boolean;
      volatileStatus?: string;
      forceSwitch?: boolean;
      selfSwitch?: boolean | string;
    }
  >;
};

describe("data/moves/flags.v1.json", () => {
  const snap = JSON.parse(fs.readFileSync(FLAGS, "utf8")) as FlagsSnap;

  it("uses Champions-effective merge meta", () => {
    assert.match(snap.meta.source, /mods\/champions\/moves\.ts/);
    assert.equal(snap.meta.filter, "champions-legal");
  });

  it("phantomforce has charge + breaksProtect", () => {
    const pf = snap.moves.phantomforce;
    assert.ok(pf);
    assert.equal(pf.flags.charge, 1);
    assert.equal(pf.breaksProtect, true);
  });

  it("outrage carries lockedmove via self.volatileStatus flatten", () => {
    assert.equal(snap.moves.outrage?.volatileStatus, "lockedmove");
  });

  it("hyperbeam has recharge flag + mustrecharge volatile", () => {
    assert.equal(snap.moves.hyperbeam?.flags.recharge, 1);
    assert.equal(snap.moves.hyperbeam?.volatileStatus, "mustrecharge");
  });

  it("excludes Past shadowforce", () => {
    assert.equal(snap.moves.shadowforce, undefined);
  });

  it("champions howl override keeps sound", () => {
    assert.equal(snap.moves.howl?.flags.sound, 1);
  });
});
