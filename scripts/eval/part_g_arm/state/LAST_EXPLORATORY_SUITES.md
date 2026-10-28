# Exploratory mode — manifests + suites (2026-10-28)

Draft manifests include `exploratory_runner.py`. Registered runner refuses exploratory dirs.

| suite | result |
|---|---|
| calc health before/after | ok |
| pytest | **4785** passed, 14 skipped |
| npm test | **119** passed |
| run_all_checks | **PASS** |
| keys sha | `e70672541b5215e7bfff7eccb34dc321b2bde3a4b9cf08d1f5a6419be1d2309a` |
| battery | claim=`6e6c6be4351240629416f1e279bbf495bbf4670d79aaaa7d083a2c62c6d67443` false_legal=`3025138427391e57a92e1862a87b0074d44a51b290836077abf094af92c4bdec` |

Stub/dev tests only — **no** model run on covered or not-covered request-set rows.
