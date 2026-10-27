# B5 — proposed final covered list (not frozen)

Vu approves before registration. Manifest freeze is **not** done here.

## Keep (loaded + has a tool path + scorable-mechanical, or hand-audit-with-state-check)

Plan upper bound remains 97 (`covered_list.json`). After B1 + B3:

### Proposed **scorable now** (mechanical class scorer)

Rows with B1 bucket `scorable-mechanical`, B3 `loaded=true`, and a state/lookup tool on the arm.

From B1 (42 scorable-mechanical) minus load failures and stale pins:

Load failures removed from “runnable now”:
- MT3, HC2, HD1 — multi-turn seed not built
- MT4, MS4, MS7, MU7 — pending start without named fixture

Stale (report as stale, not failed): **MT2**, **H6**

### Proposed **hand audit** (still covered for a run, not class-scored for rates)

B1 bucket `hand audit` (55): SERVED / ASSUME-STATE / PARTIAL / ASK|ASSUME-STATE claim rows. State-unchanged half can be checked; claim facts need a transcript adapter the Part G scorer does not have (plan decision 7).

### Move to **not-covered** (drop rule)

Already in plan not-covered (37): see `covered_list.json` `not_covered`.

**Additional drop candidates from B3** (cannot load start state without inventing):

| row | drop rule |
|---|---|
| MT3 | multi-turn seed `after t1` not built |
| MT4 | `CS pending` without named fixture |
| HC2 | multi-turn seed `after t1` not built |
| HD1 | multi-turn seed `after H1…` not built |
| MS4 | `FBC pending valid` without named fixture |
| MS7 | `CS pending` without named fixture |
| MU7 | `FBC pending` without named fixture |

If Vu accepts those seven drops: **covered = 90**, not-covered = 44. If Vu keeps them in covered with “incomplete fixture” disclosure, covered stays 97 and they score as excluded/not-run.

## Recommendation

Keep plan **97** as the registration upper bound; mark the seven as `excluded: load_failed` in the scorer (like stale), not as silent fails. Do **not** freeze the manifest until Vu picks 90 vs 97.
