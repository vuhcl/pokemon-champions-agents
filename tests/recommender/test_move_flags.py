"""Smoke checks for committed move-flags artifact (Pass 2 ingest)."""

from __future__ import annotations

import json
from pathlib import Path

FLAGS_PATH = Path(__file__).resolve().parents[2] / "data" / "moves" / "flags.v1.json"


def test_phantom_force_has_charge_flag():
    data = json.loads(FLAGS_PATH.read_text())
    pf = data["moves"]["phantomforce"]
    assert pf["flags"]["charge"] == 1
    assert pf.get("breaksProtect") is True


def test_flags_artifact_is_champions_legal():
    data = json.loads(FLAGS_PATH.read_text())
    assert data["meta"]["filter"] == "champions-legal"
    assert "shadowforce" not in data["moves"]
