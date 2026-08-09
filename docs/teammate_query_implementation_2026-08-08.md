# Teammate extraction and query implementation — 2026-08-08

## Track 1: exact-form Showdown extraction

- Usage snapshot schema is now v3. Every `showdown_vgc_mb.species` exact-form record carries
  `teammates` and `teammates_meta`; the backward-compatible flat map deliberately does not.
- The extractor follows MunchStats' displayed denominator exactly:
  `max(sum(valid Abilities), sum(valid Teammates) / 6, 1)`.
- Rows keep exact display name/ID, one-based rank, raw chaos weight, and
  `conditional_pct`. Missing source data is `null`; a valid empty map is `[]`.
- Only the top 10 rows are retained. Metadata records source/retained counts, truncation,
  raw count, selected denominator branch, rating, format, month, and battle count.
- The fixed June-2026 Mega Swampert regression uses MunchStats' rendered values observed on
  2026-08-08: Pelipper 81.604%, Archaludon 67.781%, and Sinistcha 46.750%.

These values estimate `P(teammate present | exact anchor form present)` under ladder chaos
weighting. They are neither a sum-to-100 distribution nor independent sample counts, and
long-tail forms are less reliable.

## Track 2: callable query surface

- `query_teammates(species, regulation)` reads exact-form Showdown evidence offline-first,
  then uses the bounded live Showdown helper only when the exact-form snapshot row is absent.
  An existing malformed row returns unavailable evidence instead of masking an extraction bug.
  CBD is a final fallback; labels that cannot prove a form are marked `ambiguous` or
  `unresolved`. It reads only the bundled CBD base record, and its rank-only rows retain
  `None` percentages.
- `query_shared_teammates(species, regulation)` computes a strict all-N intersection,
  excludes every locked anchor's full legality lineage, and distinguishes a genuine empty
  retained-list intersection from unavailable anchor evidence.
- Fully percentage-backed intersections sort by highest bottleneck
  (`min conditional_pct`) first, then minimax worst rank. Rank-only evidence uses minimax
  worst rank, then summed rank and species ID for deterministic ties.
- `refresh_team_signals` publishes the typed result as
  `RecommenderState.shared_teammates`, additive to coverage and SPOF signals. Empty,
  single-locked, and complete phases clear it.

## Runtime fetch boundary

`recommender/usage_live.py` owns the fixed MunchStats/CBD endpoints used by approved runtime
exceptions. Teammate lookup uses only its MunchStats exact-form path; the CBD endpoint remains
limited to the existing spread lookup. The helper maps known regulations to a fixed month,
format, and rating, caches misses, and returns structured JSON only. It does not expose
general web search.
