# Legality snapshot schema v1 (schema_version 2 additive)

Offline, commit-pinned legality data for Pokémon Champions (Showdown mod `champions`).
Produced by `npm run extract:legality`. Consumed by the legality tool — **no live
Showdown dependency at agent runtime**.

## Artifacts

| Path | Role |
|------|------|
| `data/legality/champions.v1.json` | Full effective legality surface for mod `champions` |
| `data/legality/fixtures/championsregma_to_champions.diff.json` | Ground-truth regma→champions flips for tool tests |
| `data/legality/fixtures/identifier_skips.json` | Audit log: every Identifier initializer nulled (`undefined`→null) or skipped during extract |

Regeneration anchors: `meta.source.commit` + `meta.source.mod` (not a regulation letter).

## `champions.v1.json`

```ts
{
  meta: {
    schema_version: 2,             // was 1; additive moves/learnsets/abilities
    extracted_at: string,          // ISO-8601
    source: {
      repo: "smogon/pokemon-showdown",
      commit: string,              // full 40-char sha
      mod: "champions",
    },
    formats: {
      vgc: string,                 // display name from config/formats.ts (informational)
      bss: string,
    },
  },
  flat_rules: {
    banlist: string[],             // category bans, e.g. Mythical, Restricted Legendary
    ruleset: string[],
    desc: string,
  },
  species: {
    [speciesId: string]: {
      id: string,                  // === map key === Showdown id
      name: string,
      num: number,
      types: string[],
      base_stats: { hp, atk, def, spa, spd, spe: number },
      base_species_id: string | null,  // toId(baseSpecies); null if base forme
      abilities: { "0"?: string, "1"?: string, H?: string, S?: string },
      tags: string[],              // own pokedex tags only
      effective_tags: string[],    // union(own, ancestors via toId(baseSpecies))
      is_nonstandard: string | null,   // null = cleared/available; string e.g. "Past"
      tier: string | null,
    },
  },
  items: {
    [itemId: string]: {
      id: string,
      name: string,
      is_nonstandard: string | null,
    },
  },
  moves: {
    [moveId: string]: {
      id: string,
      name: string,
      type: string,
      category: string,            // Physical | Special | Status
      basePower: number,
      is_nonstandard: string | null,
    },
  },
  learnsets: {
    [speciesId: string]: string[], // move ids; Champions pool table (~237 species)
  },
}
```

### Field rules

- **No `is_legal` boolean.** The legality tool composes `is_nonstandard`, `tier`, and
  `effective_tags ∩ flat_rules.banlist`.
- **`items`** is the **full** effective map: `base data/items.ts ⊕ champions items.ts`
  overrides (later wins) — not overrides-only.
- **`moves`** is the **full** effective map: `base data/moves.ts ⊕ champions moves.ts`
  (same merge pattern as items). Rows missing name/type/category/basePower are omitted.
- **`learnsets`** is Champions-mod pool only (not base⊕merge). Mega/cosmetic formes often
  lack their own row — runtime resolves via `base_species_id` walk.
- **`effective_tags`** unions tags along the entire `baseSpecies` chain (does not stop at
  the first non-empty tags array).
- Lookup key: map key === `id` === Showdown object key (`[a-z0-9]+`).

## Diff fixture

```ts
{
  meta: {
    schema_version: 1,
    extracted_at: string,
    source_commit: string,
    from_mod: "championsregma",
    to_mod: "champions",
  },
  species: [{
    id: string,
    from: { is_nonstandard: string | null, tier: string | null },
    to:   { is_nonstandard: string | null, tier: string | null },
    change: "became_legal" | "became_illegal" | "other",
  }],
  items: [{
    id: string,
    from: { is_nonstandard: string | null },
    to:   { is_nonstandard: string | null },
    change: "became_legal" | "became_illegal" | "other",
  }],
}
```

Species side: key-wise compare of the two `formats-data.ts` tables.
Items side: compare effective maps `base⊕champions⊕regma` vs `base⊕champions`.
Entries only when normalized signals differ. `change` heuristic (fixture only): available
when `is_nonstandard` is null and (species) `tier !== "Illegal"`.

## Extract

```bash
npm run extract:legality
# or
npm run extract:legality -- --showdown-path /path/to/pokemon-showdown
```

Default source: shallow clone/update of `.cache/pokemon-showdown` (gitignored).
