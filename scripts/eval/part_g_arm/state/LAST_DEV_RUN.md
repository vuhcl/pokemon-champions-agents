# Last full final-prompt eev rerun (find_species prompt revision)

- Transcript (outside repo): `/Users/nowaki027/part-g-arm-state-out-find-species/`
- **Proposed prompt sha256:** `bd2b69cde151fdb4dd2431c294ca46f4fbc251f54cebd82a13844d4eba0aaf86`
- Prior Part 5 proposal: `08a0917a3eb30977752858b1a86f84f0c6ad8f2cd02217d98d6c9865f872b86b`
- Model: `qwen3.5:latest` digest `44a38603922e14f1e3ae68c5d900cc39f2a925a9749d12ab6d268d75a01a399f`
- Result: **40/41** eev pass (41 rows after three ordinary find_species + Prankster weather).
- Fail: `dev-fs-prankster-weather` — class `lookup only` OK; set layer fail (named Banette + Grimmsnarl extras; omitted all five weather moves on `find_species`; 25 tool calls >16). See `LAST_FIND_SPECIES.md`.
- Prankster key sha (recorded before this run): `cbef455d7ff1610152f64fc17ad5e33796e82fd05669a8fca93d8b0fa47652d3`
- No further prompt tune without Vu (plan: finding only if set equality needs weather-enum or prompt hints).
- Does not inherit the rev3 PASS. See `RUN_PARAMS` in `harness.py` / `run_record.json`.
