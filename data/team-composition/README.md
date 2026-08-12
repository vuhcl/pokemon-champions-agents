# Team composition

Species-level co-occurrence / cores, plus one full-build extract. Not merged into
the resolved-build cache. Sources are kept in separate files — do not treat them
as one population without checking `meta.population`.

| Path | Role | Population |
|------|------|------------|
| `champions-reg-mb.v1.json` | Reg M-B 4-cores + pairs from Pokemon-Zone `/champions/team-cores/` (Limitless) | **tournament** |
| `champions-reg-mb.pikalytics-team-usage.v1.json` | Reg M-B 6-mon team groups + uses-weighted pairs from Pikalytics `/team-usage` | **tournament** (Limitless; verified 2026-08-12) |
| `champions-reg-mb.vgcpastes-builds.v1.json` | Reg M-B full teams (item/ability/nature/EVs/moves per member) from VGCPastes sheet → pokepast.es | **mixed** (Twitter/community + tournament placers; see file `meta.population_evidence`) |

Slug note: Pokemon-Zone uses `/champions/` + UI label `Regulation M-B` — distinct from Smogon
`vgc-2026-regulation-m-b` and Pikalytics usage slug `battledataregmbs3`.

Pikalytics note: the team-usage page kicker is "Tournament Team Usage". API formats
`championstournaments` and `battledataregmbs3` return identical groups; every embedded team
record has `source: "limitless"`. This is **not** the same as Pikalytics' ladder-derived
per-species usage pages.

VGCPastes note: the Google Sheet title is "VGCPastes Repository (Champions M-B)" (not the
Pikalytics `/team-usage` API). Sheet note: "Most of the teams we find are from Twitter",
with a Featured/results subset. Paste `species` ids are base forms (mega stones live on
`item`); `species_sheet` keeps the sheet's mega-aware labels. Discovery extract only —
not wired into Tier 1 divergence or full_build_confirmation yet.

Regenerate:

```bash
uv run python scripts/extract_usage/fetch_pokemon_zone.py
uv run python scripts/extract_usage/fetch_pikalytics_team_usage.py
uv run python scripts/extract_usage/fetch_vgcpastes_builds.py
```
