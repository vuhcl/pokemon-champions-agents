"""Tests for pairwise threat classifier (ADR-015 Amendment 2026-07-28c)."""

from __future__ import annotations

from typing import Any

import pytest

from recommender.calc_client import CalcClient, CalcRequest
from recommender.matchup import (
    MatchupResult,
    Severity,
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


def test_contact_punish_downgrades_severity():
    rough_skin = {
        **KINGAMBIT,
        "ability": "Rough Skin",
        "item": None,
    }
    client = MockCalcClient(
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
    result = classify_matchup(GARCHOMP, rough_skin, client=client)
    assert result.outcome == "clean_kill"
    assert result.caveats.contact_punish_applied is True
    assert result.severity == "costly"


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
