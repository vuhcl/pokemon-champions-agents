# Part G judge (non-gating)

A second reader of the arm's final text, to look for claims the rule-based extractors miss. It never decides pass or fail. A failure drops the judge.

- **Model:** `gemma4:12b`, list ID `c7597fc90b86`, full digest `c7597fc90b86aff6965317f37dd5465402284e26382d9b4bf2dfe3ef1491f4b6` (from `ollama show` / `/api/tags`).
- **Call:** Ollama `/api/chat`, `think: false`, `format` = the JSON schema in `extract.py`, options `temperature 0, num_ctx 8192, num_predict 2000` (top_k 64, top_p 0.95 are the model's own defaults).
- **Input:** the question prompt and the arm's `final_text` only. No tool results, no keys.
- **Output:** `{"claims":[{subject,predicate,value,polarity}]}`, polarity `T` or `F`. No repair: output that does not parse or fit the schema counts as a failure.
- **Prompt:** `extract_prompt.md`, sha256 `3c510e80a9480457badc3487ffe8f8b32d0985a892f9eeadc2a191c6a9688bcd`.
- **Runner:** `run_judge.py` refuses to start unless `ollama ps` shows nothing loaded, checks the pinned digest, makes no retries, and unloads the model after the last item.

## Tuning (15 items, Vu's annotations against the dev2 final_text)

`tuning_items.jsonl` is built from the dev2 records (`runs/dev2`, commit 9bccbd27); `tuning_annotations_vu.txt` holds the annotations verbatim. Three prompt versions were run on those 15 items and nowhere else:

| Version | sha256 | What changed |
|---|---|---|
| v1 | `a4c47af146d05b3f67b90bc82b2d22456ffc2257adc8d1345d15bccfc2110311` | first draft; missed the `guaranteed_ko` verdict claim of damage_000, used Yes/No as values, invented a `legal_on Ceruledge` claim for ability_006, lost the 183 in a comparison, and missed caveats |
| v2 | `497813f27c525d44b52ee57a7a5d1f581eec4bb5c6c1a7c362a68b2db1774294` | verdict-as-claim rule, no Yes/No values, no subjects imported from the question, comparisons keep both numbers, caveats are claims |
| v3 | `3c510e80a9480457badc3487ffe8f8b32d0985a892f9eeadc2a191c6a9688bcd` | three invented examples that fix polarity for legality-style answers and stop question-derived claims |

On v3 every annotated claim is recovered (hand comparison, 15 of 15 items; `tuning_run_v3.jsonl`), all 15 outputs parse, and known leftovers are a few awkward predicate or value shapes ("is_poison_type | Yes | T", "is_guaranteed | No | F"). Tuning stops here: v3 is the committed prompt.

## Test set

Vu releases the 10-item test set once. Run it once with `run_judge.py`, with no retries or prompt edits. Pass bar (arbitrary, set by Vu): recall at least 90% on the test claims, every known-false claim recovered, JSON parses without repair. Failing the bar drops the judge. Not run yet.

## Test-set result (run once, 2026-10-23)

Run once with `run_judge.py` on Vu's 10 test items (built from the dev2 records; annotations in `test_annotations_vu.txt`, verbatim), prompt sha256 `3c510e80a9480457badc3487ffe8f8b32d0985a892f9eeadc2a191c6a9688bcd`, digest as above, sampler as above, `ollama ps` empty before the run and after. No retries, no prompt edits. Output: `test_run.jsonl`.

- **Parsing:** 10 of 10 outputs parsed and fit the schema without repair.
- **Recall:** 41 of 41 annotated claims recovered (hand comparison: a claim counts when a tuple carries the same subject and value; list members counted one by one, for example the five items with percents, the five teammates and the rank-only note in usage_018).
- **Known-false claims:** both recovered: the KO threshold 93 in damage_040 (tuples "KO | required_damage | 93" and "rolls of 93 and higher | guarantees_ko | KO"), and the three shifted percentages in usage_showdown_009 (Raichu-Mega-Y 21.08, Milotic 18.12, Wigglytuff 17.68).
- **Against the pass bar** (recall at least 90%, every known-false claim recovered, all parsed): met on all three. The judge stays, non-gating.
- **Not measured:** precision (extra or oddly shaped tuples such as "is_guaranteed | No | F" and duplicate restatements were not counted against it).
