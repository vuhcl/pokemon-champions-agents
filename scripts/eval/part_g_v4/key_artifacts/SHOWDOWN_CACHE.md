# Showdown cache for Part G v4 keys (offline)

`builders/v4_rows_ah_derive.py` parses mega stones from a **local** Showdown
checkout. It does **not** fetch the network at key-build time.

## Pin

See `showdown_items_ts.pin.json`:

| Field | Value |
|---|---|
| Showdown commit | `942cda71d14bf0618bd57991708a2e2734b6daba` |
| `items.ts` sha256 | `75da206e2cb09868bb549360f38a144c2f50b24e1d189e03b485d550a4f6357a` |
| Stones parsed | **90** |

Provenance sidecar (same facts, plus usage note): `showdown_items_ts.provenance.json`.

## Provision (one-time / re-pin)

From the repo root:

```bash
mkdir -p .cache
if [ ! -d .cache/pokemon-showdown/.git ]; then
  git clone https://github.com/smogon/pokemon-showdown.git .cache/pokemon-showdown
fi
git -C .cache/pokemon-showdown fetch --tags origin
git -C .cache/pokemon-showdown checkout 942cda71d14bf0618bd57991708a2e2734b6daba
python3 -c "import hashlib; from pathlib import Path; p=Path('.cache/pokemon-showdown/data/items.ts'); print(hashlib.sha256(p.read_bytes()).hexdigest())"
# expect: 75da206e2cb09868bb549360f38a144c2f50b24e1d189e03b485d550a4f6357a
```

`.cache/` is not committed. Re-running the clone/checkout is offline data prep;
do not add a runtime agent tool that hits the network for this file.

## Builder behavior

- Missing `items.ts`, sha mismatch, wrong HEAD, or parse count ≠ 90 → **FATAL**
  (`SystemExit`), non-zero exit. **No** `error` field is written into
  `derived_keys.json`.
- `run_all_checks.py` includes `check_keys_no_error_fields.py`, which fails if
  any truthy `"error"` leaf appears in the committed keys.
