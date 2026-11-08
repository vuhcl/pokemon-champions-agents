"""Extract move/item shortDesc+desc from data/showdown_text/*.ts into versioned JSON.

Source pin: data/showdown_text/README.md (Showdown commit 942cda7). Verbatim fields only.
Drift: ``--check`` fails if JSON differs from a fresh parse of the .ts files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.eval.part_g_arm.state.describe_tool import _parse_text_file  # noqa: E402

OUT = {
    "move": ROOT / "data" / "moves" / "descriptions.v1.json",
    "item": ROOT / "data" / "items" / "descriptions.v1.json",
}


def build(kind: str) -> dict:
    entries, rel, sha = _parse_text_file(kind)
    by_id = {
        mid: {
            "id": mid,
            "name": fields.get("name") or mid,
            **({k: fields[k] for k in ("shortDesc", "desc") if k in fields}),
        }
        for mid, fields in sorted(entries.items())
    }
    return {
        "schema": f"champions_{kind}_descriptions_v1",
        "source": {
            "label": "Showdown text",
            "path": rel,
            "sha256": sha,
            "note": "Not in-game text. Pin: data/showdown_text/README.md (942cda7).",
        },
        "count": len(by_id),
        "by_id": by_id,
    }


def write_all() -> None:
    (ROOT / "data" / "items").mkdir(parents=True, exist_ok=True)
    for kind, path in OUT.items():
        path.write_text(json.dumps(build(kind), indent=2, sort_keys=True) + "\n")
        print(f"wrote {path}")


def check() -> int:
    bad = 0
    for kind, path in OUT.items():
        expected = json.dumps(build(kind), indent=2, sort_keys=True) + "\n"
        if not path.is_file() or path.read_text() != expected:
            print(f"FAIL: {path} differs from parse of showdown_text")
            bad += 1
        else:
            print(f"PASS: {path} matches showdown_text ({build(kind)['source']['sha256'][:12]}…)")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        return check()
    write_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
