# Issue drafts (not filed)

Evidence labels follow CLAUDE.md: "sim-only" means the pinned Showdown/calc reading with no in-game observation.

## 1. calc_damage ignores Sturdy and Disguise, and does not say which ability it applied when none is sent

**What happens (verified 2026-10-23 on the arm tool, calc service from this worktree).** Garchomp (Adamant, 32 SP Atk) Earthquake into Bastiodon (32 SP HP, 167 HP), with the defender ability omitted, "Sturdy" or "Soundproof": range 180-216, `ko_text` "guaranteed OHKO", `guaranteed_ko` true in all three. Bastiodon's first ability in the calc species table is Sturdy; with Sturdy the sim leaves a full-HP target at 1 HP, so a "guaranteed OHKO" is not the result for that defender (sim-only; not observed in game). Mimikyu (Disguise) gives range 84-100 and "guaranteed 2HKO" with no mention of Disguise.

**Why it matters.** The Part G damage pool excludes defenders with Sturdy or Disguise for this reason (`part3_claim_battery_design_v4.md`), so the battery does not exercise it, but the arm tool is the product tool and will answer such questions.

**Second gap.** When the ability is omitted for a non-Mega side, the calc applies the first ability in its species table and `abilityResolution` does not report it (`shouldRecord` is true only for Mega, request and override). In dev2/dev3 the applied default differed from the stated ability on 7 of 12 omitted sides (for example Bastiodon: Sturdy applied, Soundproof stated; Goodra: Sap Sipper applied, Gooey stated). The arm then states conditions the calc did not use.

**Proposed scope.** (a) Return the applied ability for every side, not only Mega/request/override. (b) When the applied defender ability is Sturdy or Disguise, add a `caveat` field to the tool result instead of changing the numbers. (c) Do not change the vendored calc. Decision needed from Vu: whether (b) is a tool-result field only or also a prompt line; the rev-3 prompt is frozen.

## 2. Floette / Floette-Eternal: illegal base id, two legal forms, ability table mismatch

**What I verified (blob `data/legality/champions.v1.json`, usage files, vendored calc).**
- `floette`: `is_nonstandard` "Past", tier Illegal. `floetteeternal` (Floette-Eternal) and `floettemega` (Floette-Mega) are legal and both have `base_species_id` `floette`, so the legal Mega's base id is an illegal species.
- Abilities: the blob lists Floette-Eternal as Flower Veil (slot 0) and Symbiosis (hidden); the vendored calc species table has only Flower Veil for Floette-Eternal, and `Floette` is not in the calc table at all ("unknown Champions species").
- Usage: in-game has only `floetteeternal` (rank 30); Showdown has `floettemega` and `floetteeternal`. Commit 943eab2 ("never emit a row for an illegal Mega-collapse base (floette); pin floetteeternal behavior") already touches the Mega-collapse side.
- Effect seen in dev: `damage_029` states Symbiosis for Floette-Eternal; with the ability omitted the calc applied Flower Veil. The key was built with Symbiosis passed explicitly.

**What I could not establish.** Which of these Vu counts as "the floette/floetteeternal defect" (the illegal base id behind a legal Mega, the missing hidden ability in the calc table, or the user-input name "Eternal Floette" that `docs/empty_team_bootstrap_discovery_and_design_2026-08-08.md` leaves unresolved). The draft should be narrowed once that is stated.
