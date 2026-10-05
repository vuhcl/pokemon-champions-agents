from unittest.mock import patch

from recommender.usage_spreads import (
    SpreadEvidence,
    effective_spe,
    fetch_live_spreads,
    select_usage_spread,
)


def test_effective_spe_champions_formula_verified_cases():
    """Discovery-backed Spe values vs calcStatChampions (scarf=False)."""
    assert (
        effective_spe(
            "Archaludon",
            {"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 3},
            "Modest",
        )
        == 108
    )
    assert (
        effective_spe(
            "Pelipper",
            {"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 32},
            "Modest",
        )
        == 117
    )
    assert (
        effective_spe(
            "Whimsicott",
            {"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 6},
            "Timid",
        )
        == 156
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
        "recommender.usage_spreads.build_synthesis_usage_entry",
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
        "recommender.usage_spreads.build_synthesis_usage_entry",
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
        "recommender.usage_spreads.build_synthesis_usage_entry",
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

    with patch("recommender.usage_spreads.build_synthesis_usage_entry", return_value=None):
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

    # Live tuple is M-B-only; M-C product ids no longer chain-walk.
    rows = fetch_live_spreads("Farigiraf", "champions-reg-mb", fetch)
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

    rows = fetch_live_spreads("Incineroar", "champions-reg-mb", fetch)
    assert rows[0].source == "cbd-live"
    assert rows[0].weight == 12.5
    assert rows[0].weight_kind == "percentage"
    assert rows[0].nature is None


def test_live_fetch_custom_fetcher_not_memoized_and_rejects_unknown_regulation():
    fetch_live_spreads.cache_clear()
    calls = []

    def fetch(url):
        calls.append(url)
        return None

    # M-C: exact-tag → no live → no network.
    assert fetch_live_spreads("MissingNo", "champions", fetch) == ()
    assert fetch_live_spreads("MissingNo", "champions", fetch) == ()
    assert calls == []

    # M-B: live supported; custom fetcher bypasses lower-level cache.
    assert fetch_live_spreads("MissingNo", "champions-reg-mb", fetch) == ()
    assert fetch_live_spreads("MissingNo", "champions-reg-mb", fetch) == ()
    assert len(calls) == 4  # Showdown index + CBD, twice.

    calls.clear()
    assert fetch_live_spreads("MissingNo", "champions-reg-zz", fetch) == ()
    assert calls == []


def test_mc_live_spreads_empty_without_chain_walk():
    fetch_live_spreads.cache_clear()
    calls: list[str] = []

    def fetch(url):
        calls.append(url)
        return {"pokemon": {"X": {}}}

    assert fetch_live_spreads("Farigiraf", "champions", fetch) == ()
    assert fetch_live_spreads("Farigiraf", "champions-reg-mc", fetch) == ()
    assert calls == []


def test_nature_for_spread_exact_ev_and_moveset_join():
    from recommender.usage_data import nature_for_spread

    # Modal CBD Spe-0 bulky row matches Showdown Bold exactly.
    assert (
        nature_for_spread(
            "Sinistcha",
            {"hp": 32, "atk": 0, "def": 4, "spa": 0, "spd": 30, "spe": 0},
            regulation="champions-reg-mb",
        )
        == "Bold"
    )
    # Live Quiet-ish CBD row: featured TR set wins over Spe=0 Quiet heuristic.
    assert (
        nature_for_spread(
            "Sinistcha",
            {"hp": 32, "atk": 0, "def": 32, "spa": 0, "spd": 2, "spe": 0},
            regulation="champions-reg-mb",
            moves=["Matcha Gotcha", "Rage Powder", "Trick Room", "Protect"],
        )
        == "Bold"
    )
    # Same Spe L1<=4 without moves still joins a real Spe-minus nature, not None.
    joined = nature_for_spread(
        "Sinistcha",
        {"hp": 32, "atk": 0, "def": 32, "spa": 0, "spd": 2, "spe": 0},
        regulation="champions-reg-mb",
    )
    assert joined in {"Bold", "Relaxed"}


def test_offline_cbd_with_nature_labels_cbd_not_showdown():
    """Finding (b): CBD rows carry natures; do not treat nature as Showdown."""
    rows = [
        {**_row(hp=2, atk=32, spe=32), "nature": "Adamant", "pct": 17.1},
        {**_row(hp=0, atk=32, spe=32, spd=2), "nature": "Jolly", "pct": 6.9},
    ]
    with patch(
        "recommender.usage_spreads.build_synthesis_usage_entry",
        return_value={"source": "munchstats-champions-data", "top_spreads": rows},
    ):
        choice = select_usage_spread(
            "Arbok",
            "fast_attacker",
            ["Protect"],
            snap=STATS,
        )
    assert choice is not None
    assert "cbd-offline" in choice.rationale
    assert "showdown-offline" not in choice.rationale


def test_offline_showdown_pct_kind_labels_chaos_weight():
    rows = [
        {
            **_row(hp=2, spa=32, spe=32),
            "nature": "Timid",
            "pct": 1000.0,
            "pct_kind": "chaos_weight",
        }
    ]
    with patch(
        "recommender.usage_spreads.build_synthesis_usage_entry",
        return_value={"source": "smogon-chaos", "top_spreads": rows},
    ):
        choice = select_usage_spread(
            "Salamence-Mega",
            "fast_attacker",
            ["Protect"],
            snap=STATS,
        )
    assert choice is not None
    assert "showdown-offline" in choice.rationale


def test_salamence_mega_committed_stays_showdown_offline():
    """Showdown-only mega: pct_kind/source keep showdown-offline after finding (b)."""
    choice = select_usage_spread(
        "Salamence-Mega",
        "fast_attacker",
        ["Protect"],
        regulation="champions",
    )
    assert choice is not None
    assert "showdown-offline" in choice.rationale
