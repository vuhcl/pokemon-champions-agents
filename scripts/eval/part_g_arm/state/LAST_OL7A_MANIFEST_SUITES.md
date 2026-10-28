# OL7a fix — manifests + suites (2026-10-28)

`errata.json` sha256 `2d8133d8e67b86e20b8f490e3f4a54b6f2840104667a9709c10f4cb0b9ca1d5a`.
Draft manifests refreshed (`status:draft` / `frozen:false`).

```bash
uv run python -m scripts.eval.part_g_arm.state.freeze_manifest_arm_state verify
```

| suite | result |
|---|---|
| calc health before/after | ok |
| pytest | **4785** passed, 14 skipped |
| npm test | **119** passed |
| run_all_checks | **PASS** |
| keys sha | `e70672541b5215e7bfff7eccb34dc321b2bde3a4b9cf08d1f5a6419be1d2309a` |
| battery | claim=`6e6c6be4351240629416f1e279bbf495bbf4670d79aaaa7d083a2c62c6d67443` false_legal=`3025138427391e57a92e1862a87b0074d44a51b290836077abf094af92c4bdec` |

Buckets/form unchanged: 41 / 59 / 3; 74 / 242.
