# Blind recall round 2: extractor output vs Claude's annotation (20 fresh half-P items, runs/dev3b)

Annotation: `blind_recall_round2_annotation_claude.txt` (verbatim, not edited). Extractors at `6a5c2fb`, unchanged for this diff. The export's prompts and final texts are byte-identical to the dev3b records (0 differences, all 20).

Counting as in round 1: each annotated tuple counts once, list tuples once per member; `~` tuples are listed but not counted. "Strict" counts only claims the extractor emitted; "lenient" also counts a tuple that restates a claim the extractor emitted under another tuple.

| Part | Strict | Lenient |
|---|---|---|
| Asked claim | 46 / 46 | 46 / 46 |
| Claims added beyond the question | 46 / 47 | 47 / 47 |
| All units | 92 / 93 (98.9%) | 93 / 93 (100%) |

Items with full recall: 19 of 20 strict, 20 of 20 lenient.

## Every miss (1, strict)
- `ability_008`: the tuple `Clawitzer | has_ability Mega Launcher | yes`. The annotation lists it beside `Mega Launcher | legal_on Clawitzer | yes`. These are the same proposition; the extractor emits it once (`has_ability`, from the asked sentence), as designed. Counted as a strict miss for transparency, covered in the lenient count.

## Not counted (annotated `~`)
Source labels (`ability_008`, `legality_015`), the vague "one of the abilities" statement (`ability_form_010`), the caveats in `usage_029`, and the "conditional percentage" explanations in `usage_showdown_000` and `usage_showdown_002`. The extractors do not extract these.

## Spurious claims
None among these 20 items (no claim from a label, note or heading line).

No extractor or annotation change was made from this diff.
