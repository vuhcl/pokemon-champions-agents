"""VGCPastes-first exact match for find_set_matching."""

from __future__ import annotations

from unittest.mock import patch

from recommender.ids import to_id
from recommender.recommend import recommend_build, spread_sum, SP_BUDGET
from recommender.usage_data import find_set_matching, species_usage


_GARCHOMP_FEATURED_MOVES = ["Dragon Claw", "Rock Slide", "Earthquake", "Protect"]
_GARCHOMP_FEATURED_ITEM = "Life Orb"


def test_vgcpastes_wins_over_featured_same_key():
    """Garchomp featured combo has real paste coverage — vgcpastes must win."""
    fs = (species_usage("Garchomp", regulation="champions") or {}).get("featured_sets") or []
    assert fs, "expected chaos featured_sets for Garchomp"
    matches = find_set_matching(
        "Garchomp",
        _GARCHOMP_FEATURED_MOVES,
        _GARCHOMP_FEATURED_ITEM,
        regulation="champions",
    )
    assert matches
    assert matches[0]["source"] == "vgcpastes"
    assert matches[0]["provenance"] == "vgcpastes"
    assert matches[0].get("occurrence_count", 0) >= 1


def test_featured_fallback_when_no_vgcpastes():
    """Synthetic featured-only combo still matches when paste corpus has no hit."""
    # Use an impossible item so VGCPastes misses; force featured hit via stub.
    fake_entry = {
        "name": "Garchomp",
        "id": "garchomp",
        "featured_sets": [
            {
                "item": "Aguav Berry",
                "moves": ["Dragon Claw", "Earthquake", "Rock Slide", "Protect"],
                "ability": "Rough Skin",
            }
        ],
        "top_spreads": [
            {
                "nature": "Jolly",
                "evs": {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
            }
        ],
    }
    with patch("recommender.usage_data.species_usage", return_value=fake_entry):
        with patch("recommender.usage_data.load_vgcpastes_builds", return_value={"teams": []}):
            matches = find_set_matching(
                "Garchomp",
                ["Dragon Claw", "Earthquake", "Rock Slide", "Protect"],
                "Aguav Berry",
                regulation="champions",
            )
    assert len(matches) == 1
    assert matches[0]["source"] == "featured"
    assert matches[0]["provenance"] == "featured"


def test_multi_spread_ranking_and_alternatives():
    teams = {
        "teams": [
            {
                "date_shared": "1 Jul 2026",
                "members": [
                    {
                        "species": "garchomp",
                        "species_display": "Garchomp",
                        "item": "Life Orb",
                        "ability": "Rough Skin",
                        "nature": "Jolly",
                        "evs": {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
                        "moves": ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"],
                    }
                ],
            },
            {
                "date_shared": "15 Jun 2026",
                "members": [
                    {
                        "species": "garchomp",
                        "species_display": "Garchomp",
                        "item": "Life Orb",
                        "ability": "Rough Skin",
                        "nature": "Adamant",
                        "evs": {"hp": 20, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 14},
                        "moves": ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"],
                    }
                ],
            },
            {
                "date_shared": "20 Jun 2026",
                "members": [
                    {
                        "species": "garchomp",
                        "species_display": "Garchomp",
                        "item": "Life Orb",
                        "ability": "Rough Skin",
                        "nature": "Jolly",
                        "evs": {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
                        "moves": ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"],
                    }
                ],
            },
        ]
    }
    with patch("recommender.usage_data.load_vgcpastes_builds", return_value=teams):
        matches = find_set_matching(
            "Garchomp",
            ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"],
            "Life Orb",
            regulation="champions",
        )
    assert len(matches) == 2
    assert matches[0]["set"]["nature"] == "Jolly"
    assert matches[0]["occurrence_count"] == 2
    assert matches[0]["date_shared_earliest"] == "2026-06-20"
    assert matches[1]["set"]["nature"] == "Adamant"
    assert matches[1]["occurrence_count"] == 1
    assert all(m["provenance"] == "vgcpastes" for m in matches)


def test_zero_ev_match_keeps_moves_item_tier2_spread():
    teams = {
        "teams": [
            {
                "date_shared": "1 Jul 2026",
                "members": [
                    {
                        "species": "garchomp",
                        "species_display": "Garchomp",
                        "item": "Life Orb",
                        "ability": "Rough Skin",
                        "nature": "Jolly",
                        "evs": {"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
                        "moves": ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"],
                    }
                ],
            }
        ]
    }
    with patch("recommender.usage_data.load_vgcpastes_builds", return_value=teams):
        matches = find_set_matching(
            "Garchomp",
            ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"],
            "Life Orb",
            regulation="champions",
        )
    assert matches
    assert "evs" not in matches[0]["set"]
    assert matches[0]["set"]["item"] == "Life Orb"

    with (
        patch("recommender.recommend.find_set_matching", return_value=matches),
        patch("recommender.recommend.get_resolved_build", return_value=None),
        patch("recommender.recommend.lookup_live_build", return_value=None),
        patch(
            "recommender.recommend.select_usage_spread",
            return_value=None,
        ),
    ):
        out = recommend_build(
            "Garchomp",
            ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"],
            "Life Orb",
            write_cache=False,
        )
    assert out["ok"]
    assert spread_sum(out["set"].get("evs")) == SP_BUDGET


def test_itemless_corpus_member_matches_explicit_empty_item():
    teams = {
        "teams": [
            {
                "date_shared": "1 Jul 2026",
                "members": [
                    {
                        "species": "talonflame",
                        "species_display": "Talonflame",
                        "item": None,
                        "ability": "Gale Wings",
                        "nature": "Jolly",
                        "evs": {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
                        "moves": ["Brave Bird", "Flare Blitz", "Tailwind", "Protect"],
                    }
                ],
            }
        ]
    }
    with patch("recommender.usage_data.load_vgcpastes_builds", return_value=teams):
        matches = find_set_matching(
            "Talonflame",
            ["Brave Bird", "Flare Blitz", "Tailwind", "Protect"],
            "",
            regulation="champions",
        )
    assert matches
    assert matches[0]["source"] == "vgcpastes"
    assert matches[0]["set"].get("item") == ""


def test_unspecified_item_returns_empty_list():
    assert (
        find_set_matching(
            "Garchomp",
            _GARCHOMP_FEATURED_MOVES,
            None,
            regulation="champions",
        )
        == []
    )


def test_mega_form_label_matches_base_paste_member():
    teams = {
        "teams": [
            {
                "date_shared": "1 Jul 2026",
                "members": [
                    {
                        "species": "charizard",
                        "species_display": "Charizard",
                        "item": "Charizardite Y",
                        "ability": "Blaze",
                        "nature": "Modest",
                        "evs": {"hp": 4, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 30},
                        "moves": ["Heat Wave", "Weather Ball", "Helping Hand", "Protect"],
                    }
                ],
            }
        ]
    }
    with patch("recommender.usage_data.load_vgcpastes_builds", return_value=teams):
        matches = find_set_matching(
            "Charizard-Mega-Y",
            ["Heat Wave", "Weather Ball", "Helping Hand", "Protect"],
            "Charizardite Y",
            regulation="champions",
        )
    assert matches
    assert to_id(matches[0]["set"]["species"]) in {"charizard", "charizardmegay"}


_CHARIZARD_MEGA_Y_TEAMS = {
    "teams": [
        {
            "date_shared": "1 Jul 2026",
            "members": [
                {
                    "species": "charizard",
                    "species_display": "Charizard",
                    "item": "Charizardite Y",
                    "ability": "Blaze",
                    "nature": "Modest",
                    "evs": {"hp": 4, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 30},
                    "moves": ["Heat Wave", "Weather Ball", "Helping Hand", "Protect"],
                }
            ],
        }
    ]
}

_CHARIZARD_MEGA_Y_MOVES = ["Heat Wave", "Weather Ball", "Helping Hand", "Protect"]


def test_base_species_with_mega_stone_matches_paste_member():
    with patch("recommender.usage_data.load_vgcpastes_builds", return_value=_CHARIZARD_MEGA_Y_TEAMS):
        matches = find_set_matching(
            "Charizard",
            _CHARIZARD_MEGA_Y_MOVES,
            "Charizardite Y",
            regulation="champions",
        )
    assert matches
    assert matches[0]["source"] == "vgcpastes"
    assert matches[0]["set"]["item"] == "Charizardite Y"
    assert matches[0]["set"]["moves"] == _CHARIZARD_MEGA_Y_MOVES


def test_equal_count_buckets_tie_break_by_earliest_date():
    teams = {
        "teams": [
            {
                "date_shared": "15 Aug 2026",
                "members": [
                    {
                        "species": "garchomp",
                        "species_display": "Garchomp",
                        "item": "Life Orb",
                        "ability": "Rough Skin",
                        "nature": "Jolly",
                        "evs": {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
                        "moves": ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"],
                    }
                ],
            },
            {
                "date_shared": "1 Jun 2026",
                "members": [
                    {
                        "species": "garchomp",
                        "species_display": "Garchomp",
                        "item": "Life Orb",
                        "ability": "Rough Skin",
                        "nature": "Adamant",
                        "evs": {"hp": 20, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 14},
                        "moves": ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"],
                    }
                ],
            },
        ]
    }
    with patch("recommender.usage_data.load_vgcpastes_builds", return_value=teams):
        matches = find_set_matching(
            "Garchomp",
            ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"],
            "Life Orb",
            regulation="champions",
        )
    assert len(matches) == 2
    assert matches[0]["set"]["nature"] == "Adamant"
    assert matches[0]["occurrence_count"] == 1
    assert matches[0]["date_shared_earliest"] == "2026-06-01"
    assert matches[1]["set"]["nature"] == "Jolly"
    assert matches[1]["occurrence_count"] == 1


def test_unparseable_date_loses_tiebreak_priority():
    teams = {
        "teams": [
            {
                "date_shared": "not-a-real-date",
                "members": [
                    {
                        "species": "garchomp",
                        "species_display": "Garchomp",
                        "item": "Life Orb",
                        "ability": "Rough Skin",
                        "nature": "Jolly",
                        "evs": {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
                        "moves": ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"],
                    }
                ],
            },
            {
                "date_shared": "1 Jun 2026",
                "members": [
                    {
                        "species": "garchomp",
                        "species_display": "Garchomp",
                        "item": "Life Orb",
                        "ability": "Rough Skin",
                        "nature": "Adamant",
                        "evs": {"hp": 20, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 14},
                        "moves": ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"],
                    }
                ],
            },
        ]
    }
    with patch("recommender.usage_data.load_vgcpastes_builds", return_value=teams):
        matches = find_set_matching(
            "Garchomp",
            ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"],
            "Life Orb",
            regulation="champions",
        )
    assert len(matches) == 2
    assert matches[0]["set"]["nature"] == "Adamant"
    assert matches[0]["date_shared_earliest"] == "2026-06-01"
    assert matches[1]["set"]["nature"] == "Jolly"
    assert "date_shared_earliest" not in matches[1]
