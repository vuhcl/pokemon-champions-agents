# Covered PARTIAL / braced accepted-outcome audit (2026-10-28)

Searched covered request-set rows for cell `PARTIAL*` and key braces matching `{…bind…ask…}`.

| id | class cell | braced accepted set | how scored | correct alt would fail? |
|---|---|---|---|---|
| OL7a | PARTIAL | `{bind Jolteon, ask}`; other bind=fail | `outcome_sets` errata | **no** (a+b pass, c fail — tested) |
| IS2 | ASSUME-STATE (errata `PARTIAL+ASSUME-STATE`) | none (speed ASSUME-STATE claims) | class atom only | **no** — no bind/ask alt; lookup/no-change path |

No other covered row has a `{bind X, ask}` (or similar multi-outcome) key. OL7b has the same brace pattern but is **not_covered**.
