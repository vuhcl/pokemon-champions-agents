#!/usr/bin/env python3
"""Write pins_manifest.json entries and check_pins.py EXPECTED_BLOB lines for the derived eval inputs.

Pins the stone map, the type chart, the damage pool and the hand-written item stratum with the existing
blob-sha mechanism (git blob sha + content sha256 in the manifest, a second copy of the blob sha in
check_pins.py). Run it again after any of those files changes; run it last for the pool file. `--check`
exits 1 if either file would change.
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
MANIFEST = PKG / "pins_manifest.json"
CHECK_PINS = PKG / "checks" / "check_pins.py"
MANAGED = (
    "scripts/eval/part_g_v4/key_artifacts/stone_map.v1.json",
    "scripts/eval/part_g_v4/key_artifacts/type_chart.v1.json",
    "scripts/eval/part_g_v4/key_artifacts/battery_damage_pool.json",
    "scripts/eval/part_g_v4/battery/item_stratum.json",
)


def blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def new_manifest(paths: tuple[str, ...]) -> str:
    doc = json.loads(MANIFEST.read_text())
    pins = [p for p in doc["pins"] if p["path"] not in paths]
    for rel in paths:
        f = ROOT / rel
        pins.append({"path": rel, "git_blob_sha": blob_sha(f), "content_sha256": hashlib.sha256(f.read_bytes()).hexdigest()})
    doc["pins"] = pins
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def new_check_pins(paths: tuple[str, ...]) -> str:
    src = CHECK_PINS.read_text()
    m = re.search(r"EXPECTED_BLOB = \{\n(.*?)\n\}\n", src, re.S)
    if not m:
        raise SystemExit("EXPECTED_BLOB block not found in check_pins.py")
    lines = [ln for ln in m.group(1).split("\n") if not any(f'"{rel}"' in ln for rel in paths)]
    lines += [f'    "{rel}": "{blob_sha(ROOT / rel)}",' for rel in paths]
    return src[: m.start()] + "EXPECTED_BLOB = {\n" + "\n".join(lines) + "\n}\n" + src[m.end():]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--only", nargs="+", choices=MANAGED, help="update a subset (e.g. the pool file last)")
    args = ap.parse_args()
    paths = tuple(args.only) if args.only else MANAGED
    man, chk = new_manifest(paths), new_check_pins(paths)
    if args.check:
        stale = [n for n, cur, new in (("pins_manifest.json", MANIFEST.read_text(), man), ("check_pins.py", CHECK_PINS.read_text(), chk)) if cur != new]
        if stale:
            print("FAIL update_pins: out of date:", ", ".join(stale))
            return 1
        print("PASS update_pins: manifest and check_pins.py agree with the files")
        return 0
    MANIFEST.write_text(man)
    CHECK_PINS.write_text(chk)
    print(f"pinned {len(paths)} file(s); EXPECTED_BLOB now has {len(re.findall(chr(34) + r'[^' + chr(34) + r']+' + chr(34) + ': ' + chr(34) + '[0-9a-f]{40}' + chr(34), chk))} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
