# Part 4 — runner shakedown

## Failure policy (fixed before run; in `FAILURE_POLICY` / run_record)

| key | value |
|---|---|
| per_turn_timeout_s | 300 |
| max_tool_calls_per_turn | 16 |
| on_no_answer_or_error | record as `no usable answer`; **no silent retry** |
| resume | `progress.json` finished ids; skip without rewriting |

## Stub end-to-end

- Out: `/Users/nowaki027/part-g-arm-state-out-stub/`
- 97/97 covered rows recorded; every turn has state_before/after + mechanical_class
- Scorer: hand_audit marked (53); MT2/H6 `stale_pin`

## Kill-and-resume

- Out: `/Users/nowaki027/part-g-arm-state-out-resume/`
- `--stop-after 3` on H1–H4 → finished H1,H2,H3; resume skipped them, ran H4; **H1 blob unchanged**

## Real-model --dev (vs harness out-final4)

Out: `/Users/nowaki027/part-g-arm-state-out-runner-dev/`

| row | runner classes | harness | match |
|---|---|---|---|
| dev-lock | wrote, refused | same | yes |
| dev-commit-ok | wrote | same | yes |
| dev-dismiss-later | dismissed | same | yes |
| dev-mt7 | lookup only ×2, no change | same | yes |

## Runtime estimate (from out-final4 ~251s / 30 turns)

| metric | value |
|---|---|
| wall / turn (avg, all dev) | ~8.4 s |
| solve_spread calls in out-final4 | 14 |
| wall / solve-heavy turn (MT7/MT8 t1) | ~15–25 s (order-of-magnitude from 84s/4-row runner-dev incl. MT7) |
| Covered turns (≈97 rows, ~1.2 turns/row ≈ 116) sequential Ollama | **~16–20 minutes** at 8.4 s/turn; longer if many solve_spread rows |
