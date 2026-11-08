"""Drift: move/item descriptions.v1.json must match data/showdown_text/*.ts parse."""

from __future__ import annotations

from scripts.extract_descriptions.extract_move_item_descriptions import check


def test_move_item_descriptions_match_showdown_text():
    assert check() == 0
