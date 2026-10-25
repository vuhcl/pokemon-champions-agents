#!/usr/bin/env python3
"""Frozen manifest for the Part G scoring and audit tools (ADR-060: no recommender imports).

    python scripts/eval/part_g_v4/freeze_manifest.py write    # (re)write FROZEN_MANIFEST.json
    python scripts/eval/part_g_v4/freeze_manifest.py verify   # exit 1 naming every file whose sha256 differs from the manifest

The manifest records the path and sha256 of every listed file plus one manifest sha256 (the sha256 of the canonical JSON of the file table). Changing a
listed file requires regenerating the manifest in the same commit and logging why in the dev revision log.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = Path(__file__).resolve().parent / "FROZEN_MANIFEST.json"
V4, ARM = "scripts/eval/part_g_v4/", "scripts/eval/part_g_arm/"
FILES = [
    # extractors, scorer and the audit tools
    V4 + "extractors.py", V4 + "copied_lines.py", V4 + "copied_unchanged_lines.md", V4 + "scorer.py", V4 + "audit_view.py", V4 + "audit_canaries.py",
    V4 + "audit_canary_check.py", V4 + "audit_adjusted.py", V4 + "freeze_manifest.py",
    # config, split, system prompt (rev 3) and the run-parameter record builders
    ARM + "config.py", ARM + "dev_split.json", ARM + "system_prompt.md", "scripts/eval/run_params.py", ARM + "run_battery.py",
    # judge: prompt, schema/sampler/pinned digest (extract.py) and the digest record (README)
    ARM + "judge/extract_prompt.md", ARM + "judge/extract.py", ARM + "judge/README.md",
]


def sha256(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


def table() -> dict[str, str]:
    return {rel: sha256(rel) for rel in sorted(FILES)}


def manifest_sha256(files: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def differences() -> list[str]:
    saved = json.loads(MANIFEST.read_text())
    now = table()
    out = [f"{rel}: manifest {saved['files'].get(rel, 'absent')[:12]} != now {h[:12]}" for rel, h in now.items() if saved["files"].get(rel) != h]
    out += [f"{rel}: listed in the manifest but no longer in FILES" for rel in saved["files"] if rel not in now]
    if saved["manifest_sha256"] != manifest_sha256(saved["files"]):
        out.append("manifest_sha256 does not match the file table")
    return out


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in ("write", "verify"):
        raise SystemExit(__doc__)
    if sys.argv[1] == "write":
        files = table()
        doc = {"schema": "part_g_frozen_manifest_v1", "files": files, "manifest_sha256": manifest_sha256(files)}
        MANIFEST.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
        print(f"wrote {MANIFEST.name}: {len(files)} files, manifest sha256 {doc['manifest_sha256']}")
        return 0
    diff = differences()
    print("PASS frozen manifest" if not diff else "FAIL frozen manifest:\n - " + "\n - ".join(diff))
    return 1 if diff else 0


if __name__ == "__main__":
    raise SystemExit(main())
