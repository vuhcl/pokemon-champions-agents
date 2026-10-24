"""The frozen manifest matches the listed files; changing a frozen file without regenerating the manifest fails here."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/eval/part_g_v4"))
import freeze_manifest as fm  # noqa: E402


def test_manifest_matches_every_listed_file_and_its_own_hash():
    assert fm.differences() == []
    doc = json.loads(fm.MANIFEST.read_text())
    assert doc["manifest_sha256"] == fm.manifest_sha256(doc["files"]) and set(doc["files"]) == set(fm.FILES)
    for needed in ("extractors.py", "scorer.py", "audit_view.py", "audit_canaries.py", "audit_canary_check.py", "audit_adjusted.py", "dev_split.json", "system_prompt.md", "extract_prompt.md", "run_params.py"):
        assert any(rel.endswith(needed) for rel in doc["files"]), needed


def test_a_changed_file_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(fm, "MANIFEST", tmp_path / "m.json")
    files = fm.table()
    (tmp_path / "m.json").write_text(json.dumps({"files": {**files, "scripts/eval/part_g_v4/scorer.py": "0" * 64}, "manifest_sha256": fm.manifest_sha256({**files, "scripts/eval/part_g_v4/scorer.py": "0" * 64})}))
    assert [d.split(":")[0] for d in fm.differences()] == ["scripts/eval/part_g_v4/scorer.py"]
