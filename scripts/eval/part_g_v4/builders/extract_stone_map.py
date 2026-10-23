#!/usr/bin/env python3
"""Extract the Mega stone map (megaStone: {Holder: Mega}) from the pinned Showdown items.ts cache.

Writes key_artifacts/stone_map.v1.json, which the claim-battery generator reads so that it does not
need the .cache checkout (absent on CI). `--check` re-parses the cache and fails if the committed file
differs. Like the other builders, it hard-fails if the cache is missing or does not match the pin.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
ROOT = PKG.parents[2]
PIN = PKG / "key_artifacts" / "showdown_items_ts.pin.json"
OUT = PKG / "key_artifacts" / "stone_map.v1.json"


def to_id(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def parse(text: str) -> list[dict[str, str]]:
    rows = []
    for m in re.finditer(r"\n\t([a-z0-9]+): \{\n(.*?)\n\t\},", text, re.S):
        body = m.group(2)
        mm = re.search(r"megaStone: (\{[^}]*\})", body)
        if not mm:
            continue
        name = re.search(r'name: "([^"]+)"', body).group(1)
        for holder, mega in re.findall(r'"([^"]+)": "([^"]+)"', mm.group(1)):
            rows.append({"stone": name, "holder": to_id(holder), "mega": to_id(mega)})
    return sorted(rows, key=lambda r: (r["stone"], r["holder"], r["mega"]))


def build() -> dict:
    pin = json.loads(PIN.read_text())
    path = ROOT / pin["path"]
    if not path.is_file():
        raise SystemExit(f"items.ts cache missing: {path} (see key_artifacts/SHOWDOWN_CACHE.md)")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != pin["items_ts_sha256"]:
        raise SystemExit("items.ts sha256 does not match the pin")
    return {
        "schema": "part_g_v4_stone_map",
        "source": {k: pin[k] for k in ("path", "items_ts_sha256", "showdown_commit")},
        "pairs": parse(raw.decode()),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    text = json.dumps(build(), sort_keys=True, indent=1, ensure_ascii=False) + "\n"
    if args.check:
        if OUT.read_text() != text:
            print("FAIL: stone_map.v1.json differs from a fresh parse of the pinned items.ts")
            return 1
        print("PASS: stone_map.v1.json matches the pinned items.ts")
        return 0
    OUT.write_text(text)
    print(f"wrote {OUT} ({len(json.loads(text)['pairs'])} pairs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
