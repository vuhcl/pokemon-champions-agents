# Usage / build snapshot (derived)

Curated competitive usage for the current regulation — in-game doubles ladder
ranks plus Showdown chaos @ 1500 per-form builds.

| Path | Role |
|------|------|
| `champions-reg-mb.v1.json` | In-game top-50 + Showdown@1500 formes/builds and exact-form teammate co-occurrence (schema v3) |

## Rebuild (regulation-change / monthly refresh)

Parameterized. Do not hardcode a month into callers — pass the new Smogon
stats month and format id.

```bash
# Default: reuse existing CBD slice, full Smogon chaos, no move/item cap,
# pct = set% (weight / Raw count). Current M-B example:
uv run python scripts/extract_usage/fetch_usage_mb.py \
  --month 2026-07 \
  --format gen9championsvgc2026regmb \
  --rating 1500 \
  --regulation champions-reg-mb

# New regulation: point --format / --regulation at the new ids, then rebuild
# Role Compendium categories (construct + critic; persist only on sign-off).
uv run python scripts/extract_usage/fetch_usage_mb.py \
  --month YYYY-MM \
  --format gen9championsvgcYYYYYregXX \
  --rating 1500 \
  --regulation champions-reg-xx \
  --refresh-cbd

# Legacy MunchStats mirror (also untruncated) if chaos 404s:
uv run python scripts/extract_usage/fetch_usage_mb.py --source munchstats --month YYYY-MM
```

`--refresh-cbd` re-fetches Champions Battle Data doubles top-N. Omit it to keep
the existing in-game slice and only replace Showdown.

Meta records `showdown_month`, `showdown_format`, `showdown_rating`,
`showdown_source` (`smogon-chaos` | `munchstats-showdown`), `showdown_pct_kind`
(`set`), and `showdown_move_limit` (`null` = no cap).

Showdown teammate rows retain the top 10 exact-form chaos weights and expose
`conditional_pct = 100 * teammate_weight / max(sum(Abilities), sum(Teammates) / 6, 1)`.
These are ladder-weighted conditional estimates, not independent sample counts, a
sum-to-100 distribution, or curated tournament results.

Legacy Pikalytics-only extract (`fetch_pikalytics.py`) is superseded for M-B threat
ranking; keep it only if you need the older single-source shape.
