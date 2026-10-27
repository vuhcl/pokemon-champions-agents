# Part 6 — covered list + state manifest proposal (NOT frozen)

## Final covered list (proposed)

| bucket | count | notes |
|---|---|---|
| scorable-mechanical | 42 | state signature + tool outcome |
| hand audit | 54 | claim rows; gemma second-rater only |
| **covered total** | **96** | plan 97 minus MT4 |
| not covered | 38 | prior 37 + **MT4** (no show-candidates tool) |

All 7 seeds load; MT4 seed loads but row is dropped from covered for the run. Stale-pin rows MT2/H6 stay covered but scored as stale, not failed.

## Solver tests outside default pytest

`pyproject.toml` `testpaths = ["tests/recommender", "tests/ci"]`. Solver tests under `scripts/eval/part_g_arm/state/test_*.py` are path-invoked only. Collecting them needs either adding that path to `testpaths` or a root `conftest`/pytest.ini `pythonpath` + explicit path — **not changed this round** (outside `state/` for pyproject).

## Manifest proposal

See `STATE_MANIFEST_PROPOSAL.json` (frozen: false). Claude reviews; freeze commit after Vu approves.
