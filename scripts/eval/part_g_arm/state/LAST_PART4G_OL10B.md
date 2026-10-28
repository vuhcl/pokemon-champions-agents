# 4g — OL10b fixture route — DROPPED

## Spec

Build `provisional_slot` from the fixture’s own fingerprints (`provisional_fingerprint` stale on pending vs `provisional_fingerprint_now` on the file) so `commit_full_slot` sees a mismatch. Use only fields the fixture provides; invent none.

## Fixture fields available (`ol_fixtures/OL10b.json`)

- pending FBC with `provisional_fingerprint: "stale-old-fp"` and build_option_groups
- `provisional_fingerprint_now: "fixture-current-fp"`
- team slot 0: Rillaboom + Miracle Seed + Grassy Surge (no moveset/nature/spread)

## Decision

`commit_full_slot` / `ProvisionalSlot` require species, ability, item, four moves, nature, and a 66-SP spread. The fixture does **not** provide moves/nature/spread for a provisional. Building one would invent fields. Per the build note: **drop OL10b**. OL10a already dropped.

No code change.
