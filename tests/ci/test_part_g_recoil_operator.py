"""ADR-079 recoil operator used by the Part G key builders (observations from the ADR)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[2] / "scripts/eval/part_g_v4/builders/_lib.py"
_spec = importlib.util.spec_from_file_location("part_g_v4_lib", _LIB)
_lib = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_lib)


@pytest.mark.parametrize(
    ("dealt", "recoil"),
    [(0, 0), (1, 1), (35, 12), (47, 16), (68, 22), (80, 26), (150, 50), (180, 59), (187, 62), (188, 62)],
)
def test_recoil_hp_matches_adr079_observations(dealt, recoil):
    assert _lib.recoil_hp_adr079(dealt) == recoil
