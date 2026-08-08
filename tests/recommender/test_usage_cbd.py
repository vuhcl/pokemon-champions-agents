"""CBD parse helpers — offline fixture, no network."""

from __future__ import annotations

from recommender.usage_cbd import entry_from_battle, pct_rows


def test_pct_rows_moves():
    rows = [
        {"category": "move", "name": "Follow Me", "percentage_value": 80.0},
        {"category": "ability", "name": "Magic Guard", "percentage_value": 90.0},
        {"category": "move", "name": "Moonblast", "percentage": "40%"},
    ]
    moves = pct_rows(rows, "move")
    assert [m["name"] for m in moves] == ["Follow Me", "Moonblast"]
    assert moves[0]["pct"] == 80.0
    assert moves[1]["pct"] == 40.0


def test_entry_from_battle_follow_me():
    battle = {
        "pokemon": "Clefable",
        "showdownId": "clefable",
        "rows": [
            {"category": "move", "name": "Follow Me", "percentage_value": 55.0},
            {"category": "move", "name": "Moonblast", "percentage_value": 40.0},
        ],
    }
    entry = entry_from_battle(battle, display_name="Clefable")
    assert entry["id"] == "clefable"
    assert entry["source"] == "championsbattledata"
    assert entry["common_moves"][0]["name"] == "Follow Me"
