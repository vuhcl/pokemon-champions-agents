# Usage / build snapshot (derived)

Curated, derived competitive usage data for this project — **not** a bulk mirror of
Pikalytics (or any other source). Used for tier-1 known-build lookup and assumed
opponent sets.

| Path | Role |
|------|------|
| `champions-reg-mb.v1.json` | Minimal Reg M-B snapshot from Pikalytics AI markdown |

Regenerate:

```bash
python scripts/extract_usage/fetch_pikalytics.py
```

Meta stores Pikalytics `format_code` (`battledataregmbs3`) separately from our
`regulation` tag (`champions-reg-mb`) — they are not interchangeable with Showdown mod names.
