# Blind recall check: extractor output vs Claude's annotation (20 half-P items, runs/dev3b)

Annotation: `blind_recall_annotation_claude.txt` (verbatim, not edited). Extractors: unchanged, commit `3226491`. The export's prompts and final texts were checked equal to the dev3b records (0 mismatches).

**Unit of recall.** Each annotated tuple counts once, and a list tuple counts once per member (the five items, each percentage, each teammate, each stated rank). Tuples marked `~` by the annotator are reported but not counted.
"Strict" counts only claims the extractor emitted. "Lenient" also counts a list member equal to the asked ability, which the extractor states through the `has_ability` claim instead of a separate list-member claim (by design).

| Item | Gold units | Recovered (strict) | Missed |
|---|---|---|---|
| ability_004 | 4 | 2 | Sheer Force and Rock Head as list members (Sheer Force is covered by `has_ability` in the lenient count; Rock Head is missed) |
| ability_026 | 3 | 1 | Sweet Veil and Aroma Veil as list members (Sweet Veil covered by `has_ability` in the lenient count) |
| ability_form_005 | 2 | 2 | none |
| ability_form_011 | 2 | 2 | none |
| damage_030 | 3 | 2 | guaranteed OHKO (nHKO = 1) |
| damage_051 | 6 | 4 | defender HP 182; guaranteed OHKO (nHKO = 1) |
| item_026 | 1 | 1 | none |
| item_038 | 1 | 1 | none |
| legality_001 | 1 | 1 | none |
| legality_006 | 1 | 1 | none |
| move_static_023 | 1 | 1 | none |
| move_static_024 | 1 | 1 | none |
| speed_011 | 3 | 3 | none |
| speed_025 | 4 | 4 | none |
| typing_041 | 3 | 3 | none |
| typing_042 | 3 | 3 | none |
| usage_013 | 20 | 20 | none |
| usage_015 | 20 | 20 | none (two `~` caveat statements not extracted) |
| usage_showdown_003 | 10 | 10 | none (the `~` explanation not extracted) |
| usage_showdown_009 | 10 | 10 | none (the `~` explanation not extracted) |
| **Total** | **99** | **92 (92.9%)** | 7 |

Lenient: 94 of 99 (95.0%). Items with full recall: 15 of 20.

## Every miss (7, strict)
1. `ability_004`: "Rock Head" in "(along with Rock Head and Sturdy)": only Sturdy was extracted.
2. `ability_004`: "Sheer Force" as a list member (stated through `has_ability`).
3. `ability_026`: "Aroma Veil" in "Alcremie has two abilities: Sweet Veil and Aroma Veil": no list claim; the lead phrase "has two abilities" is not recognised.
4. `ability_026`: "Sweet Veil" as a list member (stated through `has_ability`).
5. `damage_030`: "(guaranteed OHKO)": the nHKO pattern needs a digit before HKO, so "OHKO" is not read as nHKO = 1.
6. `damage_051`: defender HP 182 in "the defender's HP (182)": the HP patterns match "N HP (" and "HP of/is/: N" but not "HP (N)".
7. `damage_051`: "guaranteed OHKO", as in 5.

## Not a recall miss: one spurious claim
`usage_015`: the extractor emitted `teammates | Note | FALSE`. The line "Note: The teammate list carries rank only..." was read as a list entry named "Note", and a name not in the key scores FALSE. It is a false claim the arm never made, so it counts against precision, not recall. It is the only extra claim of this kind among the 20 items.

## Not counted (annotated `~`)
`usage_015` caveat "teammate list carries rank only" and "some entries have ambiguous attribution status"; the "conditional percentage" explanations in `usage_showdown_003` and `usage_showdown_009`. The extractors do not extract caveat or explanation statements.

No extractor change has been made from these findings. The four causes (list-lead phrases, "OHKO", "HP (N)", the entry parser accepting "Note:") are recorded for Vu's decision.
