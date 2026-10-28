# Part 2 — run-model identity

## out-final4 (A5 frozen-prompt run)

| field | value |
|---|---|
| Ollama tag | `qwen3.5:latest` |
| digest | `44a38603922e14f1e3ae68c5d900cc39f2a925a9749d12ab6d268d75a01a399f` |
| quantization | Q4_K_M (9.7B) |
| temperature | `0.0` |
| think | `False` |
| num_ctx | `16384` |
| num_predict | `2048` |
| seed | **none** (Ollama default; not pinned) |
| prompt sha256 | `b71764852eb66f87f17375ff3226a7e4be7517b09eb8961fb56e779fe32badd8` |

## Part G gate comparison

Same tag, same digest `44a38603…`, temperature 0, think off, num_ctx 16384 (`ArmConfig` / `QWEN_DIGEST`). **No rerun** — settings match; seed remains unset on both (not a digest/settings difference).

## Runner fixed values

Recorded in `request_set_runner.FIXED_RUN_SETTINGS` (and every `run_record.json`).
