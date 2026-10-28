# Manifest proposal (pre-freeze round 3 item 4)

`STATE_MANIFEST_PROPOSAL.json`: `frozen: false`; `clean_tree_commit_sha: ""`.

| field | value |
|---|---|
| covered_list sha256 | `ebeef244f370688b73e2fd6e94b01c55cdb07a6e8123c43156352255a8a6ed85` |
| tools.py sha256 | `e5dd309e0a6ce4afb9eeddc0b2bb2172ea79086feda8e7ff07a3158ae4dd5d42` |
| eev transcript sha256 | `074e6f275c98b605846e9a16e60fd39ff413e0f68dc92ac12abc60ece930c942` |
| prompt | `bd2b69cde151fdb4dd2431c294ca46f4fbc251f54cebd82a13844d4eba0aaf86` |
| covered / not_covered | **99 / 35** |
| audit sections / rubric cells | **71 / 232** |
| MM1 / MM2 | hand audit / mechanical |

## Suites

| suite | result |
|---|---|
| calc health before/after | ok |
| `uv run pytest` | **4785 passed, 14 skipped** |
| `npm test` | **119 passed** |
| `run_all_checks.py` | **PASS** |
| keys sha | `e70672541b5215e7bfff7eccb34dc321b2bde3a4b9cf08d1f5a6419be1d2309a` |
| claim battery | `6e6c6be4351240629416f1e279bbf495bbf4670d79aaaa7d083a2c62c6d67443` |
| false_legal | `3025138427391e57a92e1862a87b0074d44a51b290836077abf094af92c4bdec` |

`LAST_CHECK.json` / `calc_coverage.json` restored (not committed).
