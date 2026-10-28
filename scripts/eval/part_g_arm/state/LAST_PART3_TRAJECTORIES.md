# Part 3 — reference trajectories (re-run after Part 4 / Part 5)

Script: `reference_trajectories.py` → `part3_reference_trajectories.json`.

## Mechanical covered

| metric | n |
|---|---|
| pass | **39/39** |
| unexpected fail | **0** |
| capability gap | **0** (OL1/OL2a/OL3 removed from covered at Part 5) |

### Moved to not-covered (gaps)

| row | missing |
|---|---|
| OL1 | FBC provisional wire in pending loader |
| OL2a | FBC provisional wire + suffix/label select |
| OL3 | label-select + FBC provisional wire |

### Closed by Part 4 tools (were gaps)

MS6 (4b), MR2/MR4 (4a), MS5 (4f) — trajectories pass.

## Hand-audit fact reachability

Still unreachable (4): H11, H19, H20, HU1.

Closed vs earlier report: MV1 (4h priority), IC1 t2 (4a), TB1 (4a consequences).
