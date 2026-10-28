# Freeze preparation item 1 — final verification (pre-approval)

Tree: `eval/part-g-arm-state` @ HEAD after Clopper-Pearson commit. **Not frozen.** Vu accepted Mega bare-hyp finding; prompt `bd2b69cd…`; tools `e5dd309e…`.

| artifact | value |
|---|---|
| `covered_list.json` sha256 | `ebeef244f370688b73e2fd6e94b01c55cdb07a6e8123c43156352255a8a6ed85` |
| covered / not_covered | **99 / 35** |
| `prompt.md` sha256 | `bd2b69cde151fdb4dd2431c294ca46f4fbc251f54cebd82a13844d4eba0aaf86` |
| `tools.py` sha256 | `e5dd309e0a6ce4afb9eeddc0b2bb2172ea79086feda8e7ff07a3158ae4dd5d42` |
| `seeds/SHA256SUMS` (file) | `e7537618c1105aeeeb9273d8ed0045370bd8eecabcea5586f78f14a46f47b2ba` |
| `cs_pending.json` | `34495be395c0f53e38319fd438c9bbbfc0e5174691d6d13bcb3be02e1999b6eb` |
| `fbc_pending.json` | `4337ddd0dc15d319bbef0bc1ea8cbc9f978c45fa9de1768534b291df3de50af6` |
| `hc2_after_t1.json` | `9d67bd3b7cc38cc7ad5c41fde9be130cdafdaceeb85bcb2f3dff8b34bbfab4f9` |
| `hd1_history.json` | `331da9c022897b7294549b01643ee7f6201cc82ad2ba4a8c74cde670606dd7c7` |
| `mt3_after_t1.json` | `0f6d61eb95dd6678301bdc91a3a746af2c8096f196e85b813f381e7d3f7720b2` |
| `errata.json` | `b08146bb89de9ea25b56a032a99b5faede36895e4c77e902e8e5ec5e1f0414b7` |
| `request_set_runner.py` | `3e66c2034ff617a46eefb42bc41fce7b615d1d578cd367f4cd897fefa6e7f3ed` |
| `class_scorer.py` | `b110e281c159528309e33851cd4091eee40b833ef7f1f70d90a29b1b651d60eb` |
| `compare_runs.py` | `2ae62010fd6aee73cfa122d691cc49ada2657d0de14d429a507c3caf6a2df6e4` |
| `hand_audit_form.py` | `9cce632b311d5fb6a5d34bb5ced781668c10335d55d69fd76e39d68b454b4010` |
| `judge_prompt.md` | `89b9900570368074fd45a1ce44981e57fcd6e3da8f3c46f4dbcbb0fc437e5d87` |
| `dev_keys.json` | `aa0e9169b45a20ece32376ac67a826b0d4898442c698c9860d87a0866b4a8e06` |
| `dev_keys_prankster_weather.json` | `6dba1caac2d45135779779f7867f6f442163bdb3fef35ca6270d7c76329fb543` |
| `dev_rows.json` | `b7e31f60ae2af645d6275774a518c1abc0a93990663c4603de571dc9e827a311` |
| `check_pins` | **PASS** 14 pins match |
| calc build | `@smogon/calc` `0.11.0-champions.5d5bf43` (`vendor/smogon-calc`; repo package `1.1.0`) |
| model | `qwen3.5:latest` digest `44a38603922e14f1e3ae68c5d900cc39f2a925a9749d12ab6d268d75a01a399f` |
| settings | temp 0, think false, num_ctx 16384, **num_predict 2048** (= Part G gate / `docs/pre_registration.md` / `ArmConfig` default) |
