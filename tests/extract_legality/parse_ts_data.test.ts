import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { extractDataTable, clearIdentifierSkips, getIdentifierSkips } from "../../scripts/extract_legality/parse_ts_data.js";

describe("extractDataTable", () => {
  it("keeps literals and skips methods", () => {
    const src = `
export const FormatsData: {[k: string]: ModdedSpeciesFormatsData} = {
  bulbasaur: {
    isNonstandard: "Past",
    tier: "Illegal",
    onValidateSet() { return ["nope"]; },
    getWeight() { return 1; },
  },
  mew: {
    isNonstandard: null,
    tier: "OU",
    tags: ["Mythical"],
    nums: [1, 2, -3],
    flag: true,
    nested: { a: "b" },
  },
};
`;
    const table = extractDataTable(src, "fixture.ts", "FormatsData");
    assert.deepEqual(table.bulbasaur, {
      isNonstandard: "Past",
      tier: "Illegal",
    });
    assert.deepEqual(table.mew, {
      isNonstandard: null,
      tier: "OU",
      tags: ["Mythical"],
      nums: [1, 2, -3],
      flag: true,
      nested: { a: "b" },
    });
  });

  it("throws on unsupported nodes instead of dropping", () => {
    const src = `
export const Items = {
  foo: {
    name: "Foo",
    ...bar,
  },
};
`;
    assert.throws(
      () => extractDataTable(src, "bad.ts", "Items"),
      /unsupported object spread/,
    );
  });

  it("logs Identifier undefined→null and other Identifier skips", () => {
    clearIdentifierSkips();
    const src = `
export const Moves = {
  belch: {
    inherit: true,
    onDisableMove: undefined,
    name: "Belch",
    type: "Poison",
    category: "Special",
    basePower: 120,
  },
  weird: {
    name: "Weird",
    type: "Normal",
    category: "Status",
    basePower: 0,
    someRef: otherThing,
  },
};
`;
    const table = extractDataTable(src, "moves-fix.ts", "Moves");
    assert.equal((table.belch as { onDisableMove: null }).onDisableMove, null);
    assert.equal("someRef" in (table.weird as object), false);
    const skips = getIdentifierSkips();
    assert.ok(skips.some((s) => s.action === "nulled" && s.path.includes("onDisableMove")));
    assert.ok(skips.some((s) => s.action === "skipped" && s.path.includes("someRef")));
  });
});
