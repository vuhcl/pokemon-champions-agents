"""The two stone-map CI checks fail on the drift they exist to catch."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

CHECKS = Path(__file__).resolve().parents[2] / "scripts" / "eval" / "part_g_v4" / "checks"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, CHECKS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_source_check_passes_on_the_committed_files():
    assert load("check_stone_map_source").main() == 0


def test_source_check_fails_when_the_pin_moved(tmp_path):
    mod = load("check_stone_map_source")
    pin = json.loads(mod.PIN.read_text())
    pin["items_ts_sha256"] = "0" * 64
    (tmp_path / "pin.json").write_text(json.dumps(pin))
    mod.PIN = tmp_path / "pin.json"
    assert mod.main() == 1


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_calc_cross_check_passes_on_the_committed_map():
    assert load("check_stone_map_vs_calc").main() == 0


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_calc_cross_check_fails_on_a_missing_legal_pair(tmp_path, capsys):
    mod = load("check_stone_map_vs_calc")
    doc = json.loads(mod.MAP.read_text())
    doc["pairs"] = [p for p in doc["pairs"] if p["mega"] != "charizardmegax"]
    (tmp_path / "map.json").write_text(json.dumps(doc))
    mod.MAP = tmp_path / "map.json"
    assert mod.main() == 1
    assert "charizardmegax" in capsys.readouterr().out


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_calc_cross_check_only_reports_non_legal_pairs(tmp_path, capsys):
    mod = load("check_stone_map_vs_calc")
    doc = json.loads(mod.MAP.read_text())
    doc["pairs"].append({"stone": "Testite", "holder": "ditto", "mega": "dittomega"})  # not a legal Mega forme
    (tmp_path / "map.json").write_text(json.dumps(doc))
    mod.MAP = tmp_path / "map.json"
    assert mod.main() == 0
    assert "1 differences on non-legal pairs" in capsys.readouterr().out
