# Part 5 — hand-audit judge prep

- Model: `gemma4:12b`, temperature 0
- Prompt: `state/judge_prompt.md`
- Prompt sha256: `89b9900570368074fd45a1ce44981e57fcd6e3da8f3c46f4dbcbb0fc437e5d87`
- Output (outside repo): `/Users/nowaki027/part-g-arm-state-out-judge/`
- Result sha256: see `calibration_meta.json` `output_sha256`

## Calibration (22 items; 12 planted / 10 correct)

| metric | value |
|---|---|
| agreement | 20 / 22 |
| false_pass | 2 |
| false_fail | 0 |

Misses are recorded in the outside-repo result file (not tuned further on covered rows).
output_sha256: `b410283381ffcd3103aee21440f1f80c93d6a367444454bff1f09df672b25ac0`

## Misses

- cal-05: expected fail, got pass
- cal-15: expected fail, got pass
