# Usage / build snapshot (derived)

Curated competitive usage for the current regulation — in-game doubles ladder
ranks plus Showdown chaos @ 1500 per-form builds.

| Path | Role |
|------|------|
| `champions-reg-mc.ingame_doubles.v1.json` | Reg M-C in-game doubles from MunchStats `champions-data` (schema v4). Daily refresh writes this file only. |
| `champions-reg-mc.showdown_doubles.v1.json` | Reg M-C Showdown@1500 (schema v4). Written by graft / monthly rollover — not by the daily MunchStats job. |
| `champions-reg-mb.v1.json` | Reg M-B archive monolith (schema v3, `showdown_vgc_mb`). Loader remaps to `showdown_doubles` in memory. |

Loader (`recommender.usage_data.load_usage`) prefers per-source files when present,
else a legacy monolith. In-memory keys: `ingame_doubles`, `showdown_doubles`,
`showdown_singles` (empty until BSS), plus flat `species` via `merge_species_flat`.

`showdown_ready(regulation)` is the Showdown integrity predicate (format id, nonempty
month, nonempty species). Distinct from `regulation_ready` (legality letter).

## Rebuild Reg M-C in-game (MunchStats champions-data)

Scheduled by `.github/workflows/usage-refresh-mc.yml` (daily cron; gate decides early-window vs biweekly). Manual:

```bash
uv run python -m scripts.extract_usage.fetch_usage_mc_munchstats
# or via cadence gate (writes only when validation passes):
uv run python -m scripts.ci.usage_refresh_mc_gate --force
```

## Graft / refresh Reg M-C Showdown

```bash
# Nov-1 (or any month) manual graft into the showdown per-source file:
uv run python -m scripts.extract_usage.graft_showdown_mc --month 2026-10 --force
```

Format id must equal the registry Bo1 VGC id (`gen9championsvgc2026regmc`);
bo3 / OU / BSS are rejected.

## Split a monolith (migration / merge recovery)

```bash
uv run python -m scripts.extract_usage.split_usage_monolith \
  --in data/usage/champions-reg-mc.v1.json
```

## Rebuild Reg M-B (CBD + Showdown chaos)

Parameterized. Do not hardcode a month into callers — pass the new Smogon
stats month and format id. **Leave unscheduled until those sources catch up to M-C.**

```bash
uv run python scripts/extract_usage/fetch_usage_mb.py \
  --month 2026-07 \
  --format gen9championsvgc2026regmb \
  --rating 1500 \
  --regulation champions-reg-mb
```

Meta records `showdown_month`, `showdown_format`, `showdown_rating`,
`showdown_source` (`smogon-chaos` | `munchstats-showdown`), `showdown_pct_kind`
(`weight_over_abilities_sum` = common_moves/items/abilities use **weight /
sum(Abilities weights)** — Smogon published scale; archives may still say
`weight_over_raw_count` or legacy `"set"`), fallback counters
(`showdown_pct_fallback_*`), and `showdown_move_limit` (`null` = no cap).

`top_spreads[].pct` is the **raw chaos Spreads weight** (not a percentage, not
divided by Raw). Rows stamp `pct_kind: chaos_weight`. Missing `pct_kind` means
legacy raw weight (M-B archives).

When Abilities weights are missing, items/abilities fall back to that bucket's
sum; moves use sum(Items) or fail closed (`showdown_moves_pct_unscaled`).

When `load_usage` assembles per-source files, showdown meta keys overwrite
ingame on clash (so in-memory `meta.sources` is often showdown-only). Section
maps stay separate; this is documented overwrite, not a merge of source lists.

Showdown teammate rows retain the top 10 exact-form chaos weights and expose
`conditional_pct = 100 * teammate_weight / max(sum(Abilities), sum(Teammates) / 6, 1)`.
These are ladder-weighted conditional estimates, not independent sample counts, a
sum-to-100 distribution, or curated tournament results.

Legacy Pikalytics-only extract (`fetch_pikalytics.py`) is superseded for M-B threat
ranking; keep it only if you need the older single-source shape.
