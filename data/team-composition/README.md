# Team composition

Species-level co-occurrence / cores, plus one full-build extract. Not merged into
the resolved-build cache. Sources are kept in separate files — do not treat them
as one population without checking `meta.population`.

| Path | Role | Population |
|------|------|------------|
| `champions-reg-mb.v1.json` | Reg M-B 4-cores + pairs from Pokemon-Zone `/champions/team-cores/` (Limitless) | **tournament** |
| `champions-reg-mc.pikalytics-team-usage.v1.json` | Reg M-C 6-mon team groups + uses-weighted pairs from Pikalytics `/team-usage` (**current**) | **tournament** (Limitless; verified 2026-09-12) |
| `champions-reg-mb.pikalytics-team-usage.v1.json` | Reg M-B archive of the same Pikalytics extract | **tournament** (Limitless; extracted 2026-08-12) |
| `champions-reg-mc.vgcpastes-builds.v1.json` | Reg M-C full teams from VGCPastes sheet (gid `736919171`) → pokepast.es | **mixed** (Twitter/community + tournament placers) |
| `champions-reg-mb.vgcpastes-builds.v1.json` | Reg M-B archive of the same extract (gid `1458357160`) | **mixed** |

Slug note: Pokemon-Zone uses `/champions/` + UI label `Regulation M-B` — distinct from Smogon
`vgc-2026-regulation-m-b`.

Pikalytics note: the team-usage page kicker is "Tournament Team Usage".
`GET /api/team-usage/championstournaments` is the single product URL (rolled forward
to M-C tournament labels as of 2026-09-11); every embedded team record has
`source: "limitless"`. This is **not** the same as Pikalytics' ladder-derived
per-species usage pages.

VGCPastes note: workbook `1axlwmz…`; current tab is **Champions M-C** (`gid=736919171`).
M-B tab (`gid=1458357160`) remains as archive. Sheet note: "Most of the teams we find are
from Twitter", with a Featured/results subset. Paste `species` ids are base forms (mega
stones live on `item`); `species_sheet` keeps the sheet's mega-aware labels. Refresh is
PR-gated via `.github/workflows/vgcpastes-refresh-mc.yml`.

Regenerate:

```bash
uv run python scripts/extract_usage/fetch_pokemon_zone.py
uv run python scripts/extract_usage/fetch_pikalytics_team_usage.py
uv run python scripts/extract_usage/fetch_vgcpastes_builds.py
```
