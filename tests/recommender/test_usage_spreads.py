from unittest.mock import patch

from recommender.usage_spreads import (
    SpreadEvidence,
    fetch_live_spreads,
    select_usage_spread,
)

STATS = {
    "species": {
        "incineroar": {"base_stats": {"spe": 60}},
        "farigiraf": {"base_stats": {"spe": 60}},
        "garchomp": {"base_stats": {"spe": 102}},
    },
    "moves": {
        "flareblitz": {"category": "Physical"},
        "psychic": {"category": "Special"},
        "earthquake": {"category": "Physical"},
    },
}


def _row(**stats):
    spread = {"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}
    spread.update(stats)
    return {"evs": spread}


def test_bulky_role_selects_contextual_non_top_variant():
    rows = [
        _row(hp=2, atk=32, spe=32),
        _row(hp=32, atk=2, defense=0, spd=32),
    ]
    rows[1]["evs"]["def"] = rows[1]["evs"].pop("defense")
    with patch(
        "recommender.usage_spreads.species_usage",
        return_value={"source": "munchstats-showdown", "top_spreads": rows},
    ):
        choice = select_usage_spread(
            "Incineroar",
            "bulky_pivot",
            ["Flare Blitz"],
            snap=STATS,
        )
    assert choice is not None
    assert choice.spread == rows[1]["evs"]
    assert "rank=2" in choice.rationale


def test_trick_room_uses_nature_aware_low_speed_variant():
    rows = [
        {**_row(hp=2, spa=32, spe=32), "nature": "Timid"},
        {**_row(hp=32, defense=2, spa=32), "nature": "Quiet"},
    ]
    rows[1]["evs"]["def"] = rows[1]["evs"].pop("defense")
    with patch(
        "recommender.usage_spreads.species_usage",
        return_value={"source": "munchstats-showdown", "top_spreads": rows},
    ):
        choice = select_usage_spread(
            "Farigiraf",
            "trick_room_sweeper",
            ["Psychic"],
            snap=STATS,
        )
    assert choice is not None
    assert choice.spread["spe"] == 0
    assert choice.nature == "Quiet"


def test_invalid_candidates_are_rejected():
    rows = [
        _row(hp=2, atk=32, spe=31),
        _row(hp=2, atk=33, spe=31),
    ]
    with patch(
        "recommender.usage_spreads.species_usage",
        return_value={"top_spreads": rows},
    ):
        assert (
            select_usage_spread(
                "Garchomp", "fast_attacker", ["Earthquake"], snap=STATS
            )
            is None
        )


def test_out_of_coverage_species_uses_dedicated_live_fetch():
    calls = []
    evidence = (
        SpreadEvidence(
            spread={"hp": 32, "atk": 0, "def": 2, "spa": 32, "spd": 0, "spe": 0},
            nature="Quiet",
            source="showdown-live",
            weight=100.0,
            weight_kind="chaos_weight",
            rank=0,
        ),
    )

    def live_fetch(species, regulation):
        calls.append((species, regulation))
        return evidence

    with patch("recommender.usage_spreads.species_usage", return_value=None):
        choice = select_usage_spread(
            "Farigiraf",
            "trick_room_sweeper",
            ["Psychic"],
            snap=STATS,
            live_fetch=live_fetch,
        )
    assert choice is not None
    assert choice.source == "tier2_usage_live"
    assert calls == [("Farigiraf", "champions")]


def test_live_showdown_spreads_keep_nature_and_chaos_weight():
    fetch_live_spreads.cache_clear()

    def fetch(url):
        if url.endswith("_index.json"):
            return {"pokemon": {"Farigiraf": {"usage": 1.0}}}
        return {"Spreads": {"Quiet:32/0/2/32/0/0": 5432.1}}

    rows = fetch_live_spreads("Farigiraf", "champions", fetch)
    assert rows == (
        SpreadEvidence(
            spread={"hp": 32, "atk": 0, "def": 2, "spa": 32, "spd": 0, "spe": 0},
            nature="Quiet",
            source="showdown-live",
            weight=5432.1,
            weight_kind="chaos_weight",
            rank=0,
        ),
    )


def test_live_fetch_falls_back_to_cbd_percentage_rows():
    fetch_live_spreads.cache_clear()

    def fetch(url):
        if "munchstats" in url:
            return {"pokemon": {}}
        return {
            "rows": [
                {
                    "category": "stat_points",
                    "hp_points": 32,
                    "attack_points": 2,
                    "defense_points": 16,
                    "sp_atk_points": 0,
                    "sp_def_points": 16,
                    "speed_points": 0,
                    "percentage_value": 12.5,
                }
            ]
        }

    rows = fetch_live_spreads("Incineroar", "champions", fetch)
    assert rows[0].source == "cbd-live"
    assert rows[0].weight == 12.5
    assert rows[0].weight_kind == "percentage"
    assert rows[0].nature is None


def test_live_fetch_caches_misses_and_rejects_unknown_regulation():
    fetch_live_spreads.cache_clear()
    calls = []

    def fetch(url):
        calls.append(url)
        return None

    assert fetch_live_spreads("MissingNo", "champions", fetch) == ()
    assert fetch_live_spreads("MissingNo", "champions", fetch) == ()
    assert len(calls) == 2  # Showdown index, then CBD; second call is memoized.

    calls.clear()
    assert fetch_live_spreads("MissingNo", "champions-reg-zz", fetch) == ()
    assert calls == []
