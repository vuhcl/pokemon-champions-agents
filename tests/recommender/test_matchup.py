"""Tests for pairwise threat classifier (ADR-015 Amendment 2026-07-28c)."""

from __future__ import annotations

from typing import Any

import pytest

from recommender.calc_client import CalcClient, CalcRequest
from recommender.matchup import (
    MatchupEvidenceError,
    MatchupResult,
    Severity,
    _CONTACT_MOVES,
    _contact_punish_applies,
    _damaging_moves,
    _makes_contact,
    _profiles_from_batch,
    classify_matchup,
    clear_matchup_memo,
)


@pytest.fixture(autouse=True)
def _clear_matchup_memo():
    clear_matchup_memo()
    yield
    clear_matchup_memo()


def _calc(
    *,
    ko_chance: str = "100% OHKO",
    damage_range: list[int] | None = None,
    attacker_spe: int = 100,
    defender_hp: int = 100,
    attacker_hp: int = 100,
    kochance_n: int = 1,
    kochance_chance: float = 1.0,
) -> dict[str, Any]:
    dmg = damage_range or [defender_hp, defender_hp]
    return {
        "damageRange": dmg,
        "koChance": ko_chance,
        "raw": {
            "damage": dmg,
            "range": dmg,
            "kochance": {"chance": kochance_chance, "n": kochance_n, "text": ko_chance},
            "stats": {
                "attacker": {"spe": attacker_spe, "hp": attacker_hp},
                "defender": {"hp": defender_hp},
            },
        },
    }


class MockCalcClient(CalcClient):
    def __init__(self, responses: dict[tuple[str, str, str], dict[str, Any]]) -> None:
        super().__init__("http://mock")
        self._responses = responses

    def calculate_batch(self, requests: list[CalcRequest]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for req in requests:
            attacker = req["attacker"]["species"]
            defender = req["defender"]["species"]
            move = req["move"]
            key = (attacker, defender, move)
            if key not in self._responses:
                raise KeyError(f"unexpected calc request: {key}")
            out.append(self._responses[key])
        return out


@pytest.mark.parametrize(
    "results",
    [
        [],
        [{"error": "move failed"}],
        [None],
    ],
)
def test_incomplete_batch_evidence_raises(results):
    with pytest.raises(MatchupEvidenceError):
        _profiles_from_batch(["Tackle"], results)


GARCHOMP = {
    "species": "Garchomp",
    "item": "Life Orb",
    "ability": "Rough Skin",
    "moves": ["Earthquake", "Dragon Claw", "Protect"],
    "evs": {"hp": 0, "atk": 32, "spe": 32},
}
KINGAMBIT = {
    "species": "Kingambit",
    "item": "Black Glasses",
    "ability": "Defiant",
    "moves": ["Sucker Punch", "Kowtow Cleave", "Protect"],
    "evs": {"hp": 32, "atk": 32, "spe": 0},
}
TOXEL = {
    "species": "Toxapex",
    "item": "Black Sludge",
    "ability": "Regenerator",
    "moves": ["Scald", "Recover", "Protect"],
    "evs": {"hp": 32, "def": 32, "spd": 32, "spe": 0},
}
INCINEROAR_WALL = {
    "species": "Incineroar",
    "item": "Safety Goggles",
    "ability": "Intimidate",
    "moves": ["Flare Blitz", "Knock Off", "Protect"],
    "evs": {"hp": 32, "atk": 32, "spe": 10},
}
MAUSHOLD = {
    "species": "Maushold",
    "item": "Wide Lens",
    "ability": "Technician",
    "moves": ["Population Bomb", "Protect"],
    "evs": {"hp": 0, "atk": 32, "spe": 32},
}
SWAMPERT = {
    "species": "Swampert",
    "item": "Swampertite",
    "ability": "Swift Swim",
    "moves": ["Wave Crash", "Earthquake", "Protect"],
    "evs": {"hp": 2, "atk": 32, "spe": 32},
}
CHARIZARD = {
    "species": "Charizard",
    "item": "Charizardite Y",
    "ability": "Drought",
    "moves": ["Heat Wave", "Solar Beam", "Protect"],
    "evs": {"hp": 0, "spa": 32, "spe": 32},
}


def test_clean_kill():
    client = MockCalcClient(
        {
            ("Garchomp", "Kingambit", "Earthquake"): _calc(
                ko_chance="100% OHKO",
                attacker_spe=130,
                defender_hp=170,
            ),
            ("Garchomp", "Kingambit", "Dragon Claw"): _calc(
                ko_chance="100% 2HKO",
                damage_range=[90, 95],
                attacker_spe=130,
                defender_hp=170,
                kochance_n=2,
            ),
            ("Kingambit", "Garchomp", "Sucker Punch"): _calc(
                ko_chance="100% 2HKO",
                damage_range=[80, 90],
                attacker_spe=50,
                defender_hp=183,
                kochance_n=2,
            ),
            ("Kingambit", "Garchomp", "Kowtow Cleave"): _calc(
                ko_chance="100% 2HKO",
                damage_range=[75, 85],
                attacker_spe=50,
                defender_hp=183,
                kochance_n=2,
            ),
        }
    )
    result = classify_matchup(GARCHOMP, KINGAMBIT, client=client)
    assert result.outcome == "clean_kill"
    assert result.severity == "decisive"


def test_no_answer():
    client = MockCalcClient(
        {
            ("Garchomp", "Kingambit", "Earthquake"): _calc(
                ko_chance="100% 2HKO",
                damage_range=[90, 95],
                attacker_spe=130,
                defender_hp=170,
                kochance_n=2,
            ),
            ("Garchomp", "Kingambit", "Dragon Claw"): _calc(
                ko_chance="100% 3HKO",
                damage_range=[60, 65],
                attacker_spe=130,
                defender_hp=170,
                kochance_n=3,
            ),
            ("Kingambit", "Garchomp", "Sucker Punch"): _calc(
                ko_chance="100% OHKO",
                attacker_spe=50,
                defender_hp=183,
            ),
            ("Kingambit", "Garchomp", "Kowtow Cleave"): _calc(
                ko_chance="100% OHKO",
                attacker_spe=50,
                defender_hp=183,
            ),
        }
    )
    result = classify_matchup(GARCHOMP, KINGAMBIT, client=client)
    assert result.outcome == "no_answer"
    assert result.severity == "toss-up"


def test_intentional_non_ko_answer():
    client = MockCalcClient(
        {
            ("Toxapex", "Incineroar", "Scald"): _calc(
                ko_chance="0% KO",
                damage_range=[12, 18],
                attacker_spe=35,
                defender_hp=183,
                kochance_n=0,
                kochance_chance=0.0,
            ),
            ("Incineroar", "Toxapex", "Flare Blitz"): _calc(
                ko_chance="0% KO",
                damage_range=[8, 12],
                attacker_spe=90,
                defender_hp=216,
                kochance_n=0,
                kochance_chance=0.0,
            ),
            ("Incineroar", "Toxapex", "Knock Off"): _calc(
                ko_chance="0% KO",
                damage_range=[10, 14],
                attacker_spe=90,
                defender_hp=216,
                kochance_n=0,
                kochance_chance=0.0,
            ),
        }
    )
    result = classify_matchup(TOXEL, INCINEROAR_WALL, client=client)
    assert result.outcome == "intentional_non_ko_answer"
    assert result.severity == "decisive"


def test_conditionally_dependent_answer_with_rain():
    neutral = {
        ("Swampert", "Charizard", "Wave Crash"): _calc(
            ko_chance="100% 2HKO",
            damage_range=[90, 100],
            attacker_spe=120,
            defender_hp=180,
            kochance_n=2,
        ),
        ("Swampert", "Charizard", "Earthquake"): _calc(
            ko_chance="100% 3HKO",
            damage_range=[55, 60],
            attacker_spe=120,
            defender_hp=180,
            kochance_n=3,
        ),
        ("Charizard", "Swampert", "Heat Wave"): _calc(
            ko_chance="100% OHKO",
            attacker_spe=140,
            defender_hp=190,
        ),
        ("Charizard", "Swampert", "Solar Beam"): _calc(
            ko_chance="100% OHKO",
            attacker_spe=140,
            defender_hp=190,
        ),
    }
    rain = {
        ("Swampert", "Charizard", "Wave Crash"): _calc(
            ko_chance="100% OHKO",
            damage_range=[190, 200],
            attacker_spe=220,
            defender_hp=180,
        ),
        ("Swampert", "Charizard", "Earthquake"): _calc(
            ko_chance="100% 2HKO",
            damage_range=[80, 90],
            attacker_spe=220,
            defender_hp=180,
            kochance_n=2,
        ),
        ("Charizard", "Swampert", "Heat Wave"): _calc(
            ko_chance="100% 2HKO",
            damage_range=[70, 80],
            attacker_spe=140,
            defender_hp=190,
            kochance_n=2,
        ),
        ("Charizard", "Swampert", "Solar Beam"): _calc(
            ko_chance="100% 2HKO",
            damage_range=[65, 75],
            attacker_spe=140,
            defender_hp=190,
            kochance_n=2,
        ),
    }

    class DualFieldMock(MockCalcClient):
        def calculate_batch(self, requests: list[CalcRequest]) -> list[dict[str, Any]]:
            table = rain if requests and requests[0].get("field") else neutral
            out: list[dict[str, Any]] = []
            for req in requests:
                key = (
                    req["attacker"]["species"],
                    req["defender"]["species"],
                    req["move"],
                )
                out.append(table[key])
            return out

    result = classify_matchup(
        SWAMPERT,
        CHARIZARD,
        field={"weather": "Rain", "gameType": "Doubles"},
        client=DualFieldMock({}),
    )
    assert result.outcome == "conditionally_dependent_answer"
    assert result.severity == "decisive"


def _contact_punish_exchange_client() -> MockCalcClient:
    return MockCalcClient(
        {
            ("Garchomp", "Kingambit", "Earthquake"): _calc(
                ko_chance="100% 2HKO",
                damage_range=[85, 90],
                attacker_spe=130,
                defender_hp=170,
                attacker_hp=183,
                kochance_n=2,
            ),
            ("Garchomp", "Kingambit", "Dragon Claw"): _calc(
                ko_chance="100% 2HKO",
                damage_range=[85, 90],
                attacker_spe=130,
                defender_hp=170,
                attacker_hp=183,
                kochance_n=2,
            ),
            ("Kingambit", "Garchomp", "Sucker Punch"): _calc(
                ko_chance="100% 2HKO",
                damage_range=[100, 100],
                attacker_spe=50,
                defender_hp=183,
                kochance_n=2,
            ),
            ("Kingambit", "Garchomp", "Kowtow Cleave"): _calc(
                ko_chance="100% 2HKO",
                damage_range=[100, 100],
                attacker_spe=50,
                defender_hp=183,
                kochance_n=2,
            ),
        }
    )


def test_contact_moves_membership():
    assert len(_CONTACT_MOVES) == 166
    assert _makes_contact("Earthquake") is False
    assert _makes_contact("Dragon Claw") is True
    assert _makes_contact("Iron Head") is True
    assert _makes_contact("Play Rough") is True
    assert _contact_punish_applies(
        {**KINGAMBIT, "ability": "Rough Skin", "item": None}, "Earthquake"
    ) is False


def _dc_only_garchomp() -> dict[str, Any]:
    return {**GARCHOMP, "moves": ["Dragon Claw", "Protect"]}


def test_earthquake_no_contact_punish_chip():
    rough_skin = {**KINGAMBIT, "ability": "Rough Skin", "item": None}
    result = classify_matchup(
        GARCHOMP, rough_skin, client=_contact_punish_exchange_client()
    )
    assert result.outcome == "clean_kill"
    assert result.caveats.contact_punish_applied is False


def test_contact_punish_downgrades_severity():
    rough_skin = {**KINGAMBIT, "ability": "Rough Skin", "item": None}
    result = classify_matchup(
        _dc_only_garchomp(), rough_skin, client=_contact_punish_exchange_client()
    )
    assert result.outcome == "clean_kill"
    assert result.caveats.contact_punish_applied is True
    assert result.severity == "costly"


def test_flame_body_no_hp_chip():
    flame = {**KINGAMBIT, "ability": "Flame Body", "item": None}
    result = classify_matchup(
        _dc_only_garchomp(), flame, client=_contact_punish_exchange_client()
    )
    assert result.outcome == "clean_kill"
    assert result.caveats.contact_punish_applied is False


def test_static_no_hp_chip():
    static = {**KINGAMBIT, "ability": "Static", "item": None}
    result = classify_matchup(
        _dc_only_garchomp(), static, client=_contact_punish_exchange_client()
    )
    assert result.outcome == "clean_kill"
    assert result.caveats.contact_punish_applied is False


def test_multi_hit_downgrade():
    no_lens = {**MAUSHOLD, "item": "Focus Sash"}
    kingambit = {**KINGAMBIT, "moves": ["Sucker Punch", "Protect"]}
    client = MockCalcClient(
        {
            ("Maushold", "Kingambit", "Population Bomb"): _calc(
                ko_chance="guaranteed OHKO",
                damage_range=[180, 200],
                attacker_spe=130,
                defender_hp=170,
            ),
            ("Kingambit", "Maushold", "Sucker Punch"): _calc(
                ko_chance="100% 3HKO",
                damage_range=[30, 35],
                attacker_spe=50,
                defender_hp=110,
                kochance_n=3,
            ),
        }
    )
    result = classify_matchup(no_lens, kingambit, client=client)
    assert result.outcome == "clean_kill"
    assert result.caveats.multi_hit_assumed is True
    assert result.severity in {"costly", "toss-up"}


def test_severity_named_alias_path():
    assert Severity.__args__ == ("decisive", "costly", "toss-up")  # type: ignore[attr-defined]


def test_matchup_result_shape():
    client = MockCalcClient(
        {
            ("Garchomp", "Kingambit", "Earthquake"): _calc(
                ko_chance="100% OHKO",
                attacker_spe=130,
                defender_hp=170,
            ),
            ("Garchomp", "Kingambit", "Dragon Claw"): _calc(
                ko_chance="100% 2HKO",
                damage_range=[90, 95],
                attacker_spe=130,
                defender_hp=170,
                kochance_n=2,
            ),
            ("Kingambit", "Garchomp", "Sucker Punch"): _calc(
                ko_chance="100% 2HKO",
                damage_range=[80, 90],
                attacker_spe=50,
                defender_hp=183,
                kochance_n=2,
            ),
            ("Kingambit", "Garchomp", "Kowtow Cleave"): _calc(
                ko_chance="100% 2HKO",
                damage_range=[75, 85],
                attacker_spe=50,
                defender_hp=183,
                kochance_n=2,
            ),
        }
    )
    result = classify_matchup(GARCHOMP, KINGAMBIT, client=client)
    assert isinstance(result, MatchupResult)
    assert result.caveats.contact_punish_applied is False
    assert result.caveats.multi_hit_assumed is False
    assert result.turn_economy_note is None


SNORLAX = {
    "species": "Snorlax",
    "item": "Leftovers",
    "ability": "Thick Fat",
    "moves": ["Body Slam", "Protect"],
    "evs": {"hp": 32, "atk": 0, "spe": 0},
}
HYPER_BEAM_USER = {
    "species": "Tyranitar",
    "item": "Choice Specs",
    "ability": "Sand Stream",
    "moves": ["Hyper Beam", "Protect"],
    "evs": {"hp": 0, "spa": 32, "spe": 32},
}


def test_charge_delayed_under_neutral_flips_to_swampert():
    """Solar Beam does not fire T1 without Sun — Swampert OHKOs on the free turn."""
    client = MockCalcClient(
        {
            ("Swampert", "Charizard", "Wave Crash"): _calc(
                ko_chance="100% OHKO",
                attacker_spe=120,
                defender_hp=180,
                attacker_hp=190,
            ),
            ("Swampert", "Charizard", "Earthquake"): _calc(
                ko_chance="100% 2HKO",
                damage_range=[80, 90],
                attacker_spe=120,
                defender_hp=180,
                attacker_hp=190,
                kochance_n=2,
            ),
            ("Charizard", "Swampert", "Heat Wave"): _calc(
                ko_chance="100% 3HKO",
                damage_range=[40, 50],
                attacker_spe=140,
                defender_hp=190,
                kochance_n=3,
            ),
            ("Charizard", "Swampert", "Solar Beam"): _calc(
                ko_chance="100% OHKO",
                damage_range=[200, 220],
                attacker_spe=140,
                defender_hp=190,
            ),
        }
    )
    result = classify_matchup(SWAMPERT, CHARIZARD, client=client)
    assert result.outcome == "clean_kill"
    assert result.turn_economy_note == "charge_delayed"


def test_charge_instant_under_sun_naive_calc_read():
    """Under Sun, Solar Beam fires T1 — Charizard OHKOs faster Swampert."""
    client = MockCalcClient(
        {
            ("Swampert", "Charizard", "Wave Crash"): _calc(
                ko_chance="100% OHKO",
                attacker_spe=120,
                defender_hp=180,
                attacker_hp=190,
            ),
            ("Swampert", "Charizard", "Earthquake"): _calc(
                ko_chance="100% 2HKO",
                damage_range=[80, 90],
                attacker_spe=120,
                defender_hp=180,
                attacker_hp=190,
                kochance_n=2,
            ),
            ("Charizard", "Swampert", "Heat Wave"): _calc(
                ko_chance="100% 3HKO",
                damage_range=[40, 50],
                attacker_spe=140,
                defender_hp=190,
                kochance_n=3,
            ),
            ("Charizard", "Swampert", "Solar Beam"): _calc(
                ko_chance="100% OHKO",
                damage_range=[200, 220],
                attacker_spe=140,
                defender_hp=190,
            ),
        }
    )
    result = classify_matchup(
        SWAMPERT,
        CHARIZARD,
        field={"weather": "Sun", "gameType": "Doubles"},
        client=client,
    )
    assert result.outcome == "no_answer"
    assert result.turn_economy_note is None


def test_charge_pick_prefers_instant_ohko_over_delayed():
    """Heat Wave (instant OHKO) beats Solar Beam (delayed OHKO) under neutral."""
    frail = {
        "species": "Snorlax",
        "item": "Leftovers",
        "ability": "Thick Fat",
        "moves": ["Body Slam", "Protect"],
        "evs": {"hp": 0, "spe": 0},
    }
    client = MockCalcClient(
        {
            ("Charizard", "Snorlax", "Heat Wave"): _calc(
                ko_chance="100% OHKO",
                damage_range=[100, 100],
                attacker_spe=140,
                defender_hp=100,
                attacker_hp=180,
            ),
            ("Charizard", "Snorlax", "Solar Beam"): _calc(
                ko_chance="100% OHKO",
                damage_range=[200, 200],
                attacker_spe=140,
                defender_hp=100,
                attacker_hp=180,
            ),
            ("Snorlax", "Charizard", "Body Slam"): _calc(
                ko_chance="100% 3HKO",
                damage_range=[30, 35],
                attacker_spe=30,
                defender_hp=180,
                kochance_n=3,
            ),
        }
    )
    result = classify_matchup(CHARIZARD, frail, client=client)
    assert result.outcome == "clean_kill"
    assert result.turn_economy_note is None


def test_recharge_ohko_moot():
    client = MockCalcClient(
        {
            ("Tyranitar", "Snorlax", "Hyper Beam"): _calc(
                ko_chance="100% OHKO",
                attacker_spe=100,
                defender_hp=200,
                attacker_hp=180,
            ),
            ("Snorlax", "Tyranitar", "Body Slam"): _calc(
                ko_chance="100% 3HKO",
                damage_range=[40, 50],
                attacker_spe=30,
                defender_hp=180,
                kochance_n=3,
            ),
        }
    )
    result = classify_matchup(HYPER_BEAM_USER, SNORLAX, client=client)
    assert result.outcome == "clean_kill"
    assert result.turn_economy_note == "recharge_vulnerable_moot"


def test_recharge_non_ohko_defender_capitalizes():
    client = MockCalcClient(
        {
            ("Tyranitar", "Snorlax", "Hyper Beam"): _calc(
                ko_chance="100% 2HKO",
                damage_range=[100, 110],
                attacker_spe=100,
                defender_hp=200,
                attacker_hp=180,
                kochance_n=2,
            ),
            ("Snorlax", "Tyranitar", "Body Slam"): _calc(
                ko_chance="100% 2HKO",
                damage_range=[90, 90],
                attacker_spe=30,
                defender_hp=180,
                kochance_n=2,
            ),
        }
    )
    result = classify_matchup(HYPER_BEAM_USER, SNORLAX, client=client)
    assert result.outcome == "no_answer"
    assert result.turn_economy_note == "recharge_vulnerable_lost"


def test_recharge_non_ohko_defender_cannot_capitalize():
    client = MockCalcClient(
        {
            ("Tyranitar", "Snorlax", "Hyper Beam"): _calc(
                ko_chance="100% 2HKO",
                damage_range=[100, 110],
                attacker_spe=100,
                defender_hp=200,
                attacker_hp=180,
                kochance_n=2,
            ),
            ("Snorlax", "Tyranitar", "Body Slam"): _calc(
                ko_chance="100% 3HKO",
                damage_range=[20, 25],
                attacker_spe=30,
                defender_hp=180,
                kochance_n=3,
            ),
        }
    )
    result = classify_matchup(HYPER_BEAM_USER, SNORLAX, client=client)
    assert result.outcome == "clean_kill"
    assert result.turn_economy_note == "recharge_vulnerable_won"


# --- Track B: move usability caveats ---

STEEL_ROLLER = {
    "species": "Copperajah",
    "ability": "Heavy Metal",
    "item": "Leftovers",
    "moves": ["Steel Roller"],
    "nature": "Adamant",
    "evs": {"hp": 32, "atk": 32},
}
POLTERGEIST = {
    "species": "Gengar",
    "ability": "Cursed Body",
    "item": "Focus Sash",
    "moves": ["Poltergeist"],
    "nature": "Timid",
    "evs": {"spa": 32, "spe": 32},
}
EXPANDING_FORCE = {
    "species": "Armarouge",
    "ability": "Flash Fire",
    "item": "Life Orb",
    "moves": ["Expanding Force"],
    "nature": "Modest",
    "evs": {"spa": 32, "spe": 32},
}
DUMMY_FOE = {
    "species": "Blissey",
    "ability": "Natural Cure",
    "item": "Leftovers",
    "moves": ["Seismic Toss"],
    "nature": "Bold",
    "evs": {"hp": 32, "def": 32},
}


def test_steel_roller_fails_without_terrain():
    client = MockCalcClient(
        {
            ("Copperajah", "Blissey", "Steel Roller"): _calc(
                ko_chance="0%", damage_range=[0, 0], kochance_n=0, kochance_chance=0
            ),
            ("Blissey", "Copperajah", "Seismic Toss"): _calc(
                ko_chance="2HKO",
                damage_range=[50, 60],
                attacker_spe=50,
                defender_hp=200,
                kochance_n=2,
            ),
        }
    )
    result = classify_matchup(STEEL_ROLLER, DUMMY_FOE, client=client)
    assert result.outcome == "no_answer"


def test_steel_roller_damages_with_psychic_terrain():
    client = MockCalcClient(
        {
            ("Copperajah", "Blissey", "Steel Roller"): _calc(
                ko_chance="OHKO",
                damage_range=[200, 240],
                attacker_spe=40,
                defender_hp=200,
            ),
            ("Blissey", "Copperajah", "Seismic Toss"): _calc(
                ko_chance="3HKO",
                damage_range=[40, 50],
                attacker_spe=50,
                defender_hp=180,
                kochance_n=3,
            ),
        }
    )
    result = classify_matchup(
        STEEL_ROLLER,
        DUMMY_FOE,
        field={"terrain": "Psychic"},
        client=client,
    )
    assert result.outcome == "clean_kill"
    assert result.caveats.condition_fail is None


def test_poltergeist_fails_without_defender_item():
    foe = {
        "species": "Blissey",
        "ability": "Natural Cure",
        "moves": ["Seismic Toss"],
        "nature": "Bold",
        "evs": {"hp": 32, "def": 32},
    }
    client = MockCalcClient(
        {
            ("Gengar", "Blissey", "Poltergeist"): _calc(
                ko_chance="0%", damage_range=[0, 0], kochance_n=0, kochance_chance=0
            ),
            ("Blissey", "Gengar", "Seismic Toss"): _calc(
                ko_chance="OHKO",
                damage_range=[100, 120],
                attacker_spe=50,
                defender_hp=100,
            ),
        }
    )
    result = classify_matchup(POLTERGEIST, foe, client=client)
    assert result.outcome == "no_answer"


def test_poltergeist_damages_with_item():
    client = MockCalcClient(
        {
            ("Gengar", "Blissey", "Poltergeist"): _calc(
                ko_chance="OHKO",
                damage_range=[200, 240],
                attacker_spe=110,
                defender_hp=200,
            ),
            ("Blissey", "Gengar", "Seismic Toss"): _calc(
                ko_chance="2HKO",
                damage_range=[40, 50],
                attacker_spe=50,
                defender_hp=100,
                kochance_n=2,
            ),
        }
    )
    result = classify_matchup(POLTERGEIST, DUMMY_FOE, client=client)
    assert result.outcome == "clean_kill"
    assert result.caveats.condition_fail is None


def test_expanding_force_boosted_caveat_under_psychic_terrain():
    client = MockCalcClient(
        {
            ("Armarouge", "Blissey", "Expanding Force"): _calc(
                ko_chance="2HKO",
                damage_range=[100, 120],
                attacker_spe=80,
                defender_hp=200,
                kochance_n=2,
            ),
            ("Blissey", "Armarouge", "Seismic Toss"): _calc(
                ko_chance="3HKO",
                damage_range=[30, 40],
                attacker_spe=50,
                defender_hp=120,
                kochance_n=3,
            ),
        }
    )
    result = classify_matchup(
        EXPANDING_FORCE,
        DUMMY_FOE,
        field={"terrain": "Psychic", "gameType": "Doubles"},
        client=client,
    )
    assert result.caveats.expanding_force_boosted is True


def test_expanding_force_no_boost_caveat_without_terrain():
    client = MockCalcClient(
        {
            ("Armarouge", "Blissey", "Expanding Force"): _calc(
                ko_chance="2HKO",
                damage_range=[80, 100],
                attacker_spe=80,
                defender_hp=200,
                kochance_n=2,
            ),
            ("Blissey", "Armarouge", "Seismic Toss"): _calc(
                ko_chance="3HKO",
                damage_range=[30, 40],
                attacker_spe=50,
                defender_hp=120,
                kochance_n=3,
            ),
        }
    )
    result = classify_matchup(EXPANDING_FORCE, DUMMY_FOE, client=client)
    assert result.caveats.expanding_force_boosted is False


def test_electro_shot_rain_charge_skip_unaffected():
    """Regression: Rain still skips Electro Shot charge delay."""
    from recommender.matchup import _charge_delayed

    assert _charge_delayed("Electro Shot", {"weather": "Rain"}) is False
    assert _charge_delayed("Electro Shot", None) is True


# --- Track C: doubles tactical caveats ---

BRICK_BREAK = {
    "species": "Machamp",
    "ability": "Guts",
    "item": "Flame Orb",
    "moves": ["Brick Break"],
    "nature": "Adamant",
    "evs": {"atk": 32, "spe": 32},
}
PSYCHIC_FANGS = {
    "species": "Gyarados",
    "ability": "Intimidate",
    "item": "Leftovers",
    "moves": ["Psychic Fangs"],
    "nature": "Adamant",
    "evs": {"atk": 32, "spe": 32},
}
RAGING_BULL = {
    "species": "Tauros-Paldea-Combat",
    "ability": "Intimidate",
    "item": "Leftovers",
    "moves": ["Raging Bull"],
    "nature": "Adamant",
    "evs": {"atk": 32, "spe": 32},
}
UNSEEN_FIST = {
    "species": "Golurk-Mega",
    "ability": "Unseen Fist",
    "item": "Leftovers",
    "moves": ["Earthquake"],
    "nature": "Adamant",
    "evs": {"atk": 32, "spe": 32},
}
PIERCING_DRILL = {
    "species": "Excadrill-Mega",
    "ability": "Piercing Drill",
    "item": "Leftovers",
    "moves": ["Iron Head"],
    "nature": "Adamant",
    "evs": {"atk": 32, "spe": 32},
}
SCREEN_FOE = {
    "species": "Blissey",
    "ability": "Natural Cure",
    "item": "Leftovers",
    "moves": ["Seismic Toss"],
    "nature": "Bold",
    "evs": {"hp": 32, "def": 32},
}


def _ohko_pair(attacker: str, defender: str, move: str, foe_move: str = "Seismic Toss"):
    return {
        (attacker, defender, move): _calc(
            ko_chance="OHKO",
            damage_range=[200, 240],
            attacker_spe=90,
            defender_hp=200,
        ),
        (defender, attacker, foe_move): _calc(
            ko_chance="3HKO",
            damage_range=[30, 40],
            attacker_spe=50,
            defender_hp=150,
            kochance_n=3,
        ),
    }


def test_brick_break_sets_screen_clear_caveat_when_reflect_up():
    client = MockCalcClient(
        _ohko_pair("Machamp", "Blissey", "Brick Break")
    )
    result = classify_matchup(
        BRICK_BREAK,
        SCREEN_FOE,
        field={"defenderSide": {"isReflect": True}},
        client=client,
    )
    assert result.caveats.screen_clear_applied is True


def test_psychic_fangs_screen_clear_caveat():
    client = MockCalcClient(
        _ohko_pair("Gyarados", "Blissey", "Psychic Fangs")
    )
    result = classify_matchup(
        PSYCHIC_FANGS,
        SCREEN_FOE,
        field={"defenderSide": {"isLightScreen": True}},
        client=client,
    )
    assert result.caveats.screen_clear_applied is True


def test_raging_bull_screen_clear_caveat():
    client = MockCalcClient(
        _ohko_pair("Tauros-Paldea-Combat", "Blissey", "Raging Bull")
    )
    result = classify_matchup(
        RAGING_BULL,
        SCREEN_FOE,
        field={"defenderSide": {"isAuroraVeil": True}},
        client=client,
    )
    assert result.caveats.screen_clear_applied is True


def test_non_clear_move_no_screen_caveat():
    client = MockCalcClient(
        _ohko_pair("Machamp", "Blissey", "Brick Break")
    )
    # No screens up
    result = classify_matchup(BRICK_BREAK, SCREEN_FOE, client=client)
    assert result.caveats.screen_clear_applied is False


def test_unseen_fist_contact_sets_protect_bypass_when_protected():
    attacker = {**UNSEEN_FIST, "moves": ["Close Combat"]}
    client = MockCalcClient(_ohko_pair("Golurk-Mega", "Blissey", "Close Combat"))
    result = classify_matchup(
        attacker,
        SCREEN_FOE,
        field={"defenderSide": {"isProtected": True}},
        client=client,
    )
    assert result.caveats.protect_bypass_applied is True


def test_piercing_drill_contact_sets_protect_bypass_when_protected():
    client = MockCalcClient(
        _ohko_pair("Excadrill-Mega", "Blissey", "Iron Head")
    )
    result = classify_matchup(
        PIERCING_DRILL,
        SCREEN_FOE,
        field={"defenderSide": {"isProtected": True}},
        client=client,
    )
    assert result.caveats.protect_bypass_applied is True


def test_protect_blocks_contact_without_bypass():
    attacker = {
        "species": "Excadrill",
        "ability": "Sand Rush",
        "item": "Leftovers",
        "moves": ["Iron Head"],
        "nature": "Adamant",
        "evs": {"atk": 32, "spe": 32},
    }
    client = MockCalcClient(
        _ohko_pair("Excadrill", "Blissey", "Iron Head")
    )
    result = classify_matchup(
        attacker,
        SCREEN_FOE,
        field={"defenderSide": {"isProtected": True}},
        client=client,
    )
    assert result.caveats.protect_bypass_applied is False


def test_non_contact_move_no_protect_bypass_caveat():
    # Aura Sphere is non-contact; Unseen Fist should not bypass for it.
    attacker = {
        **UNSEEN_FIST,
        "moves": ["Shadow Ball"],
    }
    client = MockCalcClient(
        _ohko_pair("Golurk-Mega", "Blissey", "Shadow Ball")
    )
    result = classify_matchup(
        attacker,
        SCREEN_FOE,
        field={"defenderSide": {"isProtected": True}},
        client=client,
    )
    assert result.caveats.protect_bypass_applied is False


ARCHALUDON = {
    "species": "Archaludon",
    "item": "Leftovers",
    "ability": "Stamina",
    "moves": ["Electro Shot", "Dragon Pulse", "Flash Cannon", "Aura Sphere"],
    "evs": {"hp": 32, "spa": 32, "spe": 0},
}


def test_damaging_moves_excludes_status_keeps_electro_shot():
    assert _damaging_moves(
        {
            "species": "Garchomp",
            "moves": ["Earthquake", "Dragon Claw", "Rock Slide", "Wide Guard"],
        }
    ) == ["Earthquake", "Dragon Claw", "Rock Slide"]
    assert _damaging_moves({"moves": ["Protect", "Wide Guard"]}) == []
    assert _damaging_moves(ARCHALUDON) == [
        "Electro Shot",
        "Dragon Pulse",
        "Flash Cannon",
        "Aura Sphere",
    ]


def test_mixed_kit_zero_damage_row_does_not_abort_matchup():
    client = MockCalcClient(
        {
            ("Archaludon", "Garchomp", "Electro Shot"): _calc(
                ko_chance="",
                damage_range=[0, 0],
                attacker_spe=85,
                defender_hp=183,
                kochance_n=0,
                kochance_chance=0.0,
            ),
            ("Archaludon", "Garchomp", "Dragon Pulse"): _calc(
                ko_chance="100% OHKO",
                attacker_spe=85,
                defender_hp=183,
            ),
            ("Archaludon", "Garchomp", "Flash Cannon"): _calc(
                ko_chance="100% 2HKO",
                damage_range=[90, 95],
                attacker_spe=85,
                defender_hp=183,
                kochance_n=2,
            ),
            ("Archaludon", "Garchomp", "Aura Sphere"): _calc(
                ko_chance="100% 3HKO",
                damage_range=[50, 60],
                attacker_spe=85,
                defender_hp=183,
                kochance_n=3,
            ),
            ("Garchomp", "Archaludon", "Earthquake"): _calc(
                ko_chance="100% 2HKO",
                damage_range=[80, 90],
                attacker_spe=130,
                defender_hp=200,
                kochance_n=2,
            ),
            ("Garchomp", "Archaludon", "Dragon Claw"): _calc(
                ko_chance="100% 3HKO",
                damage_range=[40, 50],
                attacker_spe=130,
                defender_hp=200,
                kochance_n=3,
            ),
        }
    )
    result = classify_matchup(ARCHALUDON, GARCHOMP, client=client)
    assert result.outcome == "clean_kill"
    assert result.severity == "decisive"


def test_all_status_kit_is_no_answer_without_calc():
    protect_only = {"species": "Blissey", "moves": ["Protect"]}
    wide_only = {"species": "Garchomp", "moves": ["Wide Guard"]}
    client = MockCalcClient({})
    assert classify_matchup(protect_only, wide_only, client=client).outcome == "no_answer"
    assert classify_matchup(wide_only, protect_only, client=client).outcome == "no_answer"
