from pathlib import Path

from recommender.ids import regulation_file_tag, to_id
from recommender.resolved_builds import get_resolved_build, put_resolved_build


def test_to_id_and_regulation_tag():
    assert to_id("Charizard-Mega-Y") == "charizardmegay"
    assert regulation_file_tag("champions") == "champions-reg-mb"
    assert regulation_file_tag("champions-reg-mb") == "champions-reg-mb"
    assert regulation_file_tag("championsregma") == "champions-reg-ma"


def test_put_get_roundtrip(tmp_path: Path):
    moves = ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"]
    put_resolved_build(
        "Garchomp",
        moves,
        "Life Orb",
        "champions",
        {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
        "champions-native",
        True,
        {"threat_set": ["kingambit"], "usage_snapshot": "champions-reg-mb.v1"},
        root=tmp_path,
    )
    hit = get_resolved_build(
        "Garchomp",
        list(reversed(moves)),  # order-insensitive
        "Life Orb",
        "champions-reg-mb",
        root=tmp_path,
    )
    assert hit is not None
    assert hit["verified"] is True
    assert hit["spread"]["atk"] == 32
    assert "date_resolved" in hit
    assert hit["moves"] == sorted(to_id(m) for m in moves)

    assert (
        get_resolved_build("Garchomp", moves, "Choice Scarf", "champions", root=tmp_path)
        is None
    )


def test_variants(tmp_path: Path):
    put_resolved_build(
        "Hatterene",
        ["Psychic", "Trick Room", "Protect", "Dazzling Gleam"],
        "Life Orb",
        "champions",
        {"hp": 32, "atk": 0, "def": 16, "spa": 18, "spd": 0, "spe": 0},
        "champions-native",
        False,
        {},
        variants=[{"hp": 32, "atk": 0, "def": 0, "spa": 34, "spd": 0, "spe": 0}],
        root=tmp_path,
    )
    hit = get_resolved_build(
        "Hatterene",
        ["Psychic", "Trick Room", "Protect", "Dazzling Gleam"],
        "Life Orb",
        "champions",
        root=tmp_path,
    )
    assert hit is not None
    assert hit.get("variants")
