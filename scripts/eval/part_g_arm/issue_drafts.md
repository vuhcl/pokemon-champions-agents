# Issue drafts (not filed)

Evidence labels follow CLAUDE.md: "sim-only" means the pinned Showdown/calc reading with no in-game observation.

## 1. calc_damage ignores Sturdy and Disguise; and the omitted-ability default is unreported

**What happens (verified 2026-10-23 on the arm tool, calc service from this worktree).** Garchomp (Adamant, 32 SP Atk) Earthquake into Bastiodon (32 SP HP, 167 HP), with the defender ability omitted, "Sturdy" or "Soundproof": range 180-216, `ko_text` "guaranteed OHKO", `guaranteed_ko` true in all three. Bastiodon's first ability in the calc species table is Sturdy; with Sturdy the sim leaves a full-HP target at 1 HP, so a "guaranteed OHKO" is not the result for that defender (sim-only; not observed in game). Mimikyu (Disguise) gives range 84-100 and "guaranteed 2HKO" with no mention of Disguise.

**Why it matters.** The Part G damage pool excludes defenders with Sturdy or Disguise for this reason (`part3_claim_battery_design_v4.md`), so the battery does not exercise it, but the arm tool is the product tool and will answer such questions.

**Omitted-ability default (a separate defect from the Sturdy/Disguise gap).** When the arm omits the ability for a non-Mega side, the calc applies the first ability in its species table, and the result does not report it (`abilityResolution` is recorded only for Mega, request and override sources: `shouldRecord` in `services/calc/handlers.ts`). In dev2 and dev3 the applied default differed from the stated ability on 7 of 12 omitted sides (for example Bastiodon: Sturdy applied, Soundproof stated; Goodra: Sap Sipper applied, Gooey stated), and the arm then states conditions the calc did not use. The numbers matched the key on all 53 damage items, so no outcome changed.

**Proposed scope.** (a) Return the applied ability for every side, not only Mega/request/override (fixes the omitted-ability paragraph). (b) When the applied defender ability is Sturdy or Disguise, add a `caveat` field to the tool result instead of changing the numbers. (c) Do not change the vendored calc. Decision needed from Vu: whether (b) is a tool-result field only or also a prompt line; the rev-3 prompt is frozen.

## 2. mega_capable_base_ids returns `floette` (illegal) instead of `floetteeternal`

**What happens (verified 2026-10-23: `recommender/species_forms.mega_capable_base_ids(snap)` against `scripts/eval/part_g_v4/key_artifacts/stone_map.v1.json`).** The function collects `base_species_id` of every legal Mega form. Floette-Mega's `base_species_id` is `floette`, so `floette` is returned and `floetteeternal` is not. Counting holders of legal Mega formes in the stone map gives 77 distinct ids; the function returns 76. The set difference is: only in the function, `floette`; only in the stone map, `floetteeternal` and `meowsticf`. `meowsticf` is the same cause (`meowsticfmega` has base `meowstic`); the Part G generator already works around it with `INGAME_EXCLUDE_EXTRA`. The stone map comes from the pinned Showdown source (sim-only reading, not observed in game).

**Effect.** Callers that treat `mega_capable_base_ids` as "species whose in-game usage row blends Mega-stone holders" (`ingame_excluded_species_ids`, `arm_teammates.mega_capable_base_ids`, the in-game caveat) cover an illegal species and miss Floette-Eternal.

**Not affected.** #303.

**Proposed fix (not decided).** Derive the holder from the stone map (or from the Mega form's `item` mapping) instead of `base_species_id`; add a test that the function equals the stone map's legal-Mega holders. Out of scope for this branch.
