# Usage / build snapshot (derived)

Curated competitive usage for Reg M-B — in-game doubles ladder ranks plus
Showdown `gen9championsvgc2026regmb` @ 1500 per-form builds.

| Path | Role |
|------|------|
| `champions-reg-mb.v1.json` | In-game top-50 + Showdown@1500 formes/builds (schema v2) |

Regenerate:

```bash
uv run python scripts/extract_usage/fetch_usage_mb.py
```

Legacy Pikalytics-only extract (`fetch_pikalytics.py`) is superseded for M-B threat
ranking; keep it only if you need the older single-source shape.

Meta records `showdown_rating`, `showdown_format`, and source attribution separately
from our `regulation` tag (`champions-reg-mb`).
