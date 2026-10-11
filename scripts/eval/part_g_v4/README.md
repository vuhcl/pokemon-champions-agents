# Part G v4 — held-out request set + claim battery (eval-only)

Frozen held-out eval package. **Do not use for tuning.** Any change is a new version with a new hash.

## Contents

| Path | Role |
|---|---|
| `part3_request_set_v4.md` | 134-row request-level set |
| `key_artifacts/derived_keys.json` | Answer keys (builder-generated) |
| `key_artifacts/calc/` | Raw calc request/response + ids |
| `v4_request_set_report.md` | Design report |
| `part3_claim_battery_design_v4.md` | Battery design |
| `gate_scorer_requirements.md` | Pre-registered requirements for the unbuilt gate scorer (R1–R8) |
| `battery/` | Generator (seed 0), batteries, manifest + sha256 |
| `fixtures/`, `ol_fixtures/`, `h27_candidate_fixture.json` | Row fixtures |
| `pins_manifest.json` | Pinned data content sha256 + git blob SHAs |
| `builders/` | Key/request-set/report generators (ADR-060; no recommender imports) |
| `checks/` | Row, pin, independence, battery-hash checks |

## Checks

```bash
uv run python scripts/eval/part_g_v4/checks/run_all_checks.py
```

## Battery

```bash
uv run python scripts/eval/part_g_v4/battery/generate_claim_battery.py
# then
uv run python scripts/eval/part_g_v4/checks/check_battery_hash.py
```

Seed `0`. Canonical hash: sha256 of `json.dumps(..., sort_keys=True, separators=(",", ":")) + "\n"`.
