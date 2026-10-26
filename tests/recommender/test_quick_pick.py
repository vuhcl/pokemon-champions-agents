from unittest.mock import MagicMock

from recommender.quick_pick import quick_pick


def _set(species: str, move: str = "Earthquake") -> dict:
    return {
        "species": species,
        "item": "Life Orb",
        "moves": [move, "Protect", "Dragon Claw", "Rock Slide"],
        "evs": {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
    }


def test_quick_pick_returns_four_indices():
    team = [
        _set("Garchomp"),
        _set("Kingambit", "Sucker Punch"),
        _set("Incineroar", "Flare Blitz"),
        _set("Whimsicott", "Moonblast"),
        _set("Pelipper", "Hurricane"),
        _set("Sinistcha", "Matcha Gotcha"),
    ]
    batch = MagicMock(
        side_effect=lambda reqs: [
            {"damageRange": [100, 120], "koChance": "guaranteed OHKO"} for _ in reqs
        ]
    )
    out = quick_pick(
        team,
        ["Garchomp", "Kingambit", "Incineroar"],
        calculate_batch=batch,
    )
    assert out["ok"]
    assert len(out["bring"]) == 4
    assert len(set(out["bring"])) == 4
    assert all(0 <= i <= 5 for i in out["bring"])
    assert len(out["rationales"]) == 4


def test_bring_list_fallback_is_not_labeled_as_a_team_slot():
    team = [
        _set("Garchomp"),
        _set("Kingambit", "Sucker Punch"),
        _set("Incineroar", "Flare Blitz"),
        {"species": "Pelipper", "item": "Life Orb", "moves": [], "evs": {}},
        {"species": "Whimsicott", "item": "Life Orb", "moves": [], "evs": {}},
        {"species": "Sinistcha", "item": "Life Orb", "moves": [], "evs": {}},
    ]
    batch = MagicMock(
        side_effect=lambda reqs: [
            {"damageRange": [100, 120], "koChance": "guaranteed OHKO"} for _ in reqs
        ]
    )
    out = quick_pick(team, ["Garchomp", "Kingambit", "Incineroar"], calculate_batch=batch)
    assert out["ok"]
    assert any(note.startswith("bring ") for note in out["rationales"])
    assert all(not note.startswith("slot ") for note in out["rationales"])


def test_quick_pick_no_opponents():
    team = [_set(f"Garchomp") for _ in range(6)]
    out = quick_pick(team, ["NotInSnapshot"], calculate_batch=MagicMock())
    assert not out["ok"]
    assert "usage snapshot" in (out.get("detail") or "")
