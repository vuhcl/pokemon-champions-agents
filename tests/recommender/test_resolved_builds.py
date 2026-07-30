from pathlib import Path

from recommender.ids import regulation_file_tag, regulation_lookup_chain, to_id
from recommender.resolved_builds import get_resolved_build, put_resolved_build


def test_to_id_and_regulation_tag():
    assert to_id("Charizard-Mega-Y") == "charizardmegay"
    assert regulation_file_tag("champions") == "champions-reg-mb"
    assert regulation_file_tag("champions-reg-mb") == "champions-reg-mb"
    assert regulation_file_tag("championsregma") == "champions-reg-ma"
    assert regulation_lookup_chain("champions") == [
        "champions-reg-mb",
        "champions-reg-ma",
    ]
    assert regulation_lookup_chain("champions-reg-ma") == ["champions-reg-ma"]


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
    assert hit["found_in_regulation"] == "champions-reg-mb"

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


def test_rationale_source_format_and_skip_verified(tmp_path: Path):
    moves = ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"]
    assert put_resolved_build(
        "Garchomp",
        moves,
        "Life Orb",
        "champions",
        {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
        "champions_native_writeup",
        True,
        {},
        root=tmp_path,
        rationale="outspeeds base 100s",
        source_format="champions/vgc-2026-regulation-m-b",
    )
    hit = get_resolved_build("Garchomp", moves, "Life Orb", "champions", root=tmp_path)
    assert hit is not None
    assert hit["rationale"] == "outspeeds base 100s"
    assert hit["source_format"] == "champions/vgc-2026-regulation-m-b"
    assert (
        put_resolved_build(
            "Garchomp",
            moves,
            "Life Orb",
            "champions",
            {"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
            "analogous_format_writeup",
            False,
            {},
            root=tmp_path,
            rationale="should not land",
            source_format="sv/vgc",
        )
        is False
    )
    hit2 = get_resolved_build("Garchomp", moves, "Life Orb", "champions", root=tmp_path)
    assert hit2 is not None
    assert hit2["verified"] is True
    assert hit2["rationale"] == "outspeeds base 100s"


def test_chain_lookup_from_archived_ma(tmp_path: Path):
    moves = ["Protect", "Psychic", "Thunderbolt", "Trick Room"]
    put_resolved_build(
        "Farigiraf",
        moves,
        "Sitrus Berry",
        "champions-reg-ma",
        {"hp": 30, "atk": 0, "def": 24, "spa": 0, "spd": 12, "spe": 0},
        "champions_native_writeup",
        False,
        {},
        root=tmp_path,
        rationale="trick room setter",
        source_format="champions/vgc-2026-regulation-m-a",
    )
    hit = get_resolved_build(
        "Farigiraf",
        moves,
        "Sitrus Berry",
        "champions-reg-mb",
        root=tmp_path,
    )
    assert hit is not None
    assert hit["found_in_regulation"] == "champions-reg-ma"
    assert hit["regulation"] == "champions-reg-ma"
    assert (
        get_resolved_build(
            "Farigiraf",
            moves,
            "Sitrus Berry",
            "champions-reg-mb",
            root=tmp_path,
            chain=False,
        )
        is None
    )
