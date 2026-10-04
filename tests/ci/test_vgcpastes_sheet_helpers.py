"""VGCPastes sheet header + species filter helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.extract_usage.fetch_vgcpastes_builds import load_sheet_rows, sheet_species


def test_load_sheet_rows_missing_team_id_header(tmp_path: Path):
    path = tmp_path / "welcome.csv"
    path.write_text("Welcome,,,,,,,,\nlinks only,,,,,,,,\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Team ID header missing"):
        load_sheet_rows(path)


def test_sheet_species_skips_reg_prefixed_ids():
    row = {
        "Team ID": "MC463",
        "Owner": "alice",
        "Pokemon Text for Copypasta": "Garchomp",
        "_a": "Incineroar",
        "_b": "Rillaboom",
        "_c": "Gholdengo",
        "_d": "Volcarona",
        "_e": "Farigiraf",
        "_f": "",
        "Team ID_1": "MC463",
        "extra": "MB861",
    }
    # After Owner: walk keys in insertion order
    names = sheet_species(row)
    assert "MC463" not in names
    assert "MB861" not in names
    assert names[:3] == ["Garchomp", "Incineroar", "Rillaboom"]
