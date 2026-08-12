# Team composition

Species-level co-occurrence / cores. Not merged into the resolved-build cache.
Sources are kept in separate files — do not treat them as one population without
checking `meta.population`.

| Path | Role | Population |
|------|------|------------|
| `champions-reg-mb.v1.json` | Reg M-B 4-cores + pairs from Pokemon-Zone `/champions/team-cores/` (Limitless) | **tournament** |
| `champions-reg-mb.pikalytics-team-usage.v1.json` | Reg M-B 6-mon team groups + uses-weighted pairs from Pikalytics `/team-usage` | **tournament** (Limitless; verified 2026-08-12) |

Slug note: Pokemon-Zone uses `/champions/` + UI label `Regulation M-B` — distinct from Smogon
`vgc-2026-regulation-m-b` and Pikalytics usage slug `battledataregmbs3`.

Pikalytics note: the team-usage page kicker is "Tournament Team Usage". API formats
`championstournaments` and `battledataregmbs3` return identical groups; every embedded team
record has `source: "limitless"`. This is **not** the same as Pikalytics' ladder-derived
per-species usage pages.

Regenerate:

```bash
uv run python scripts/extract_usage/fetch_pokemon_zone.py
uv run python scripts/extract_usage/fetch_pikalytics_team_usage.py
```
