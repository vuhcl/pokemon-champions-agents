from pathlib import Path

from recommender.ids import regulation_file_tag, regulation_lookup_chain, to_id
from recommender.resolved_builds import (
    get_resolved_build,
    get_writeup_ability,
    put_resolved_build,
)


def test_to_id_and_regulation_tag():
    assert to_id("Charizard-Mega-Y") == "charizardmegay"
    assert regulation_file_tag("champions") == "champions-reg-mc"
    assert regulation_file_tag("championsregmb") == "champions-reg-mb"
    assert regulation_file_tag("champions-reg-mb") == "champions-reg-mb"
    assert regulation_file_tag("championsregma") == "champions-reg-ma"
    assert regulation_lookup_chain("champions") == [
        "champions-reg-mc",
        "champions-reg-mb",
        "champions-reg-ma",
    ]
    assert regulation_lookup_chain("champions-reg-mb") == [
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
        "champions",
        root=tmp_path,
    )
    assert hit is not None
    assert hit["verified"] is True
    assert hit["spread"]["atk"] == 32
    assert "date_resolved" in hit
    assert hit["moves"] == sorted(to_id(m) for m in moves)
    assert hit["found_in_regulation"] == "champions-reg-mc"

    # Archived tag does not walk forward to newer mc file.
    assert (
        get_resolved_build(
            "Garchomp", moves, "Life Orb", "champions-reg-mb", root=tmp_path
        )
        is None
    )
    assert (
        get_resolved_build("Garchomp", moves, "Choice Scarf", "champions", root=tmp_path)
        is None
    )


def test_chain_lookup_from_archived_mb(tmp_path: Path):
    moves = ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"]
    put_resolved_build(
        "Garchomp",
        moves,
        "Life Orb",
        "champions-reg-mb",
        {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
        "champions-native",
        True,
        {"usage_snapshot": "champions-reg-mb.v1"},
        root=tmp_path,
    )
    hit = get_resolved_build("Garchomp", moves, "Life Orb", "champions", root=tmp_path)
    assert hit is not None
    assert hit["found_in_regulation"] == "champions-reg-mb"


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
        "champions",
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


def test_ability_fields_roundtrip(tmp_path: Path):
    moves = ["Flash Cannon", "Dragon Pulse", "Body Press", "Protect"]
    put_resolved_build(
        "Archaludon",
        moves,
        "Assault Vest",
        "champions-reg-mb",
        {"hp": 20, "atk": 0, "def": 4, "spa": 28, "spd": 4, "spe": 10},
        "analogous_format_writeup",
        False,
        {},
        root=tmp_path,
        source_format="sv/vgc",
        ability="Stamina",
        ability_candidates=["Stamina", "Sturdy"],
        ability_pick_index=0,
        ability_pick_policy="first_listed",
    )
    hit = get_resolved_build(
        "Archaludon", moves, "Assault Vest", "champions-reg-mb", root=tmp_path
    )
    assert hit is not None
    assert hit["ability"] == "Stamina"
    assert hit["ability_candidates"] == ["Stamina", "Sturdy"]
    assert hit["ability_pick_index"] == 0
    assert hit["ability_pick_policy"] == "first_listed"

    w = get_writeup_ability("Archaludon", "champions-reg-mb", root=tmp_path)
    assert w is not None
    assert w["ability"] == "Stamina"
    assert w["source_format"] == "sv/vgc"
    assert w["ability_pick_policy"] == "first_listed"


def test_writeup_ability_ranking(tmp_path: Path):
    moves = ["Protect", "Surf", "Hurricane", "U-turn"]
    put_resolved_build(
        "Pelipper",
        moves,
        "Damp Rock",
        "champions-reg-mb",
        {"hp": 4, "atk": 0, "def": 0, "spa": 28, "spd": 0, "spe": 34},
        "analogous_format_writeup",
        False,
        {},
        root=tmp_path,
        source_format="sv/battle-stadium-singles",
        ability="Keen Eye",
        ability_candidates=["Keen Eye"],
        ability_pick_index=0,
        ability_pick_policy="first_listed",
        rationale="bss " + ("x" * 100),
    )
    put_resolved_build(
        "Pelipper",
        moves,
        "Focus Sash",
        "champions-reg-mb",
        {"hp": 4, "atk": 0, "def": 0, "spa": 28, "spd": 0, "spe": 34},
        "champions_native_writeup",
        False,
        {},
        root=tmp_path,
        source_format="champions/battle-stadium-singles",
        ability="Drizzle",
        ability_candidates=["Drizzle"],
        ability_pick_index=0,
        ability_pick_policy="first_listed",
        rationale="champ bss " + ("x" * 100),
    )
    put_resolved_build(
        "Pelipper",
        moves,
        "Life Orb",
        "champions-reg-mb",
        {"hp": 4, "atk": 0, "def": 0, "spa": 28, "spd": 0, "spe": 34},
        "analogous_format_writeup",
        False,
        {},
        root=tmp_path,
        source_format="sv/vgc",
        ability="Drizzle",
        ability_candidates=["Drizzle", "Keen Eye"],
        ability_pick_index=0,
        ability_pick_policy="first_listed",
        rationale="sv vgc " + ("x" * 100),
    )
    w = get_writeup_ability("Pelipper", "champions-reg-mb", root=tmp_path)
    assert w is not None
    assert w["source_format"] == "sv/vgc"
    assert w["ability"] == "Drizzle"

    put_resolved_build(
        "Pelipper",
        moves,
        "Sitrus Berry",
        "champions-reg-mb",
        {"hp": 4, "atk": 0, "def": 0, "spa": 28, "spd": 0, "spe": 34},
        "champions_native_writeup",
        False,
        {},
        root=tmp_path,
        source_format="champions/vgc-2026-regulation-m-b",
        ability="Drizzle",
        ability_candidates=["Drizzle"],
        ability_pick_index=0,
        ability_pick_policy="first_listed",
        rationale="champ vgc " + ("x" * 100),
    )
    w2 = get_writeup_ability("Pelipper", "champions-reg-mb", root=tmp_path)
    assert w2 is not None
    assert w2["source_format"] == "champions/vgc-2026-regulation-m-b"
    assert w2["source_tier"] == "champions_native_writeup"


def test_writeup_ability_first_listed(tmp_path: Path):
    put_resolved_build(
        "Archaludon",
        ["Flash Cannon", "Protect", "Body Press", "Snarl"],
        "Leftovers",
        "champions-reg-mb",
        {"hp": 32, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
        "analogous_format_writeup",
        False,
        {},
        root=tmp_path,
        source_format="sv/vgc",
        ability="Stamina",
        ability_candidates=["Stamina", "Sturdy"],
        ability_pick_index=0,
        ability_pick_policy="first_listed",
    )
    w = get_writeup_ability("Archaludon", "champions", root=tmp_path)
    assert w is not None
    assert w["ability"] == "Stamina"
    assert w["ability_candidates"] == ["Stamina", "Sturdy"]


def test_writeup_ability_miss_without_ability_field(tmp_path: Path):
    put_resolved_build(
        "Gogoat",
        ["Horn Leech", "Bulk Up", "Milk Drink", "Protect"],
        "Leftovers",
        "champions-reg-mb",
        {"hp": 32, "atk": 20, "def": 0, "spa": 0, "spd": 0, "spe": 14},
        "analogous_format_writeup",
        False,
        {},
        root=tmp_path,
        source_format="sv/vgc",
    )
    assert get_writeup_ability("Gogoat", "champions-reg-mb", root=tmp_path) is None


def test_get_writeup_kit_returns_moves_and_ranks_like_ability(tmp_path: Path):
    from recommender.resolved_builds import get_writeup_kit, writeup_reason_ref

    moves = ["Protect", "Surf", "Hurricane", "U-turn"]
    put_resolved_build(
        "Pelipper",
        moves,
        "Damp Rock",
        "champions-reg-mb",
        {"hp": 4, "atk": 0, "def": 0, "spa": 28, "spd": 0, "spe": 34},
        "analogous_format_writeup",
        False,
        {},
        root=tmp_path,
        source_format="sv/battle-stadium-singles",
        ability="Keen Eye",
        rationale="bss " + ("x" * 100),
    )
    put_resolved_build(
        "Pelipper",
        moves,
        "Life Orb",
        "champions-reg-mb",
        {"hp": 4, "atk": 0, "def": 0, "spa": 28, "spd": 0, "spe": 34},
        "analogous_format_writeup",
        False,
        {},
        root=tmp_path,
        source_format="sv/vgc",
        ability="Drizzle",
        rationale="sv vgc " + ("x" * 100),
    )
    kit = get_writeup_kit("Pelipper", "champions-reg-mb", root=tmp_path)
    assert kit is not None
    assert kit["source_format"] == "sv/vgc"
    assert kit["ability"] == "Drizzle"
    assert kit["moves"]
    assert kit["proxy_from"] is None
    assert writeup_reason_ref(kit) == "analogous_format_writeup:sv/vgc"


def test_get_writeup_kit_bax_mega_proxy(tmp_path: Path):
    from recommender.resolved_builds import get_writeup_kit

    put_resolved_build(
        "Baxcalibur",
        ["Ice Shard", "Icicle Spear", "Protect", "Scale Shot"],
        "Loaded Dice",
        "champions-reg-mb",
        {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 4, "spe": 26},
        "analogous_format_writeup",
        False,
        {},
        root=tmp_path,
        source_format="sv/vgc",
        ability="Thermal Exchange",
        rationale="bax " + ("x" * 100),
    )
    kit = get_writeup_kit("Baxcalibur-Mega", "champions-reg-mb", root=tmp_path)
    assert kit is not None
    assert kit["proxy_from"] == "Baxcalibur"
    assert kit["ability"] == "Thermal Exchange"
    assert "iceshard" in {m.lower().replace(" ", "") for m in kit["moves"]} or any(
        "ice" in m.lower() for m in kit["moves"]
    )