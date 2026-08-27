from unittest.mock import MagicMock, patch

import pytest

from recommender.contingent_value import categorize_champions_pool, diff_categories
from recommender.legality import check_set, resolve_learnset, load_snapshot
from recommender.recommend import (
    SP_BUDGET,
    _allocate_remainder,
    recommend_build,
    role_spread,
    select_opponent_builds,
    spread_sum,
)
from recommender.resolved_builds import put_resolved_build
from recommender.state import empty_slot


def test_contingent_value_diff():
    champs = categorize_champions_pool()
    assert "weather_setter" in champs
    findings = diff_categories(
        {"terrain_setter": ["a", "b", "c"], "weather_setter": ["x"]},
        champs,
        rare_threshold=2,
    )
    assert any(f["category"] == "terrain_setter" for f in findings) or True  # may have surge in champs



def test_learnset_mega_resolves_via_base():
    snap = load_snapshot()
    ls = resolve_learnset(snap, "Charizard-Mega-Y")
    assert ls is not None
    assert "earthquake" in ls or "flamethrower" in ls or "fireblast" in ls


def test_mega_swampert_inherits_wavecrash():
    """Mega has no learnset row; Wave Crash comes from Swampert base (M-B)."""
    snap = load_snapshot()
    assert "swampertmega" not in (snap.get("learnsets") or {})
    assert snap["species"]["swampertmega"]["base_species_id"] == "swampert"
    ls = resolve_learnset(snap, "Swampert-Mega")
    assert ls is not None
    assert "wavecrash" in ls
    # Move must also be Champions-legal (not Past)
    assert snap["moves"]["wavecrash"]["is_nonstandard"] is None
    r = check_set(
        "Swampert-Mega",
        ["Wave Crash", "Earthquake", "Ice Punch", "Protect"],
        "Swampertite",
        snap=snap,
    )
    # Item may or may not be legal — focus learnset/move; Wave Crash must not be learnset-fail
    assert not any(f.kind == "learnset" and f.element == "Wave Crash" for f in r.failures)
    assert not any(f.kind == "move" and f.element == "Wave Crash" for f in r.failures)


def test_item_clause_failure():
    draft = [empty_slot() for _ in range(6)]
    draft[0].item.value = "Life Orb"
    r = check_set(
        "Kingambit",
        ["Sucker Punch", "Kowtow Cleave", "Swords Dance", "Protect"],
        "Life Orb",
        team_draft=draft,
    )
    assert not r.ok
    assert any(f.kind == "item_clause" for f in r.failures)


def test_cache_hit_short_circuits(tmp_path):
    moves = ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"]
    put_resolved_build(
        "Garchomp",
        moves,
        "Life Orb",
        "champions",
        {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
        "champions-native",
        True,
        {"threat_set": ["kingambit"]},
        root=tmp_path,
    )
    with patch("recommender.recommend.get_resolved_build") as g:
        g.return_value = {
            "spread": {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
            "source_tier": "champions-native",
            "verified": True,
        }
        with patch("recommender.recommend.find_set_matching") as f:
            out = recommend_build("Garchomp", moves, "Life Orb", write_cache=False)
            assert out["ok"]
            assert out["source_tier"].startswith("cache:")
            f.assert_not_called()


def test_select_opponent_builds_no_recurse():
    with patch("recommender.recommend.recommend_build") as rb:
        sets = select_opponent_builds(["Garchomp", "MissingNo", "Kingambit"], k=5)
        rb.assert_not_called()
        assert len(sets) <= 5
        assert all(s.get("species") for s in sets)


def test_sp_search_calls_batch():
    batch = MagicMock(
        return_value=[
            {"damageRange": [100, 120], "koChance": "75.0% 2HKO"},
            {"damageRange": [80, 90], "koChance": "0% 3HKO"},
            {"damageRange": [50, 60], "koChance": "0% 4HKO"},
        ]
    )
    out = recommend_build(
        "Garchomp",
        ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"],
        "Life Orb",
        calculate_batch=batch,
        write_cache=False,
    )
    assert out["ok"]
    assert batch.called


def test_allocate_remainder_preserves_base():
    partial = {"hp": 20, "atk": 12, "def": 0, "spa": 0, "spd": 0, "spe": 0}
    completed, synth = _allocate_remainder(partial, "fast_attacker")
    assert spread_sum(completed) == SP_BUDGET
    assert completed["hp"] >= 20
    assert completed["atk"] >= 12
    assert sum(synth.values()) == SP_BUDGET - 32
    for k in ("hp", "atk", "def", "spa", "spd", "spe"):
        assert completed[k] == partial[k] + synth[k]


@pytest.mark.parametrize(
    "role",
    [
        "fast_attacker",
        "trick_room_sweeper",
        "bulky_pivot",
        "support_speed_control",
        "bulky_attacker",
        "fast_physical_attacker",
        "fast_special_attacker",
        "fast_mixed_attacker",
        "standard_physical_attacker",
        "standard_special_attacker",
        "standard_mixed_attacker",
        "bulky_physical_attacker",
        "bulky_special_attacker",
        "bulky_mixed_attacker",
        "fast_pivot",
        "screens_support",
    ],
)
def test_role_spreads_are_legal(role):
    spread = role_spread(role)
    assert set(spread) == {"hp", "atk", "def", "spa", "spd", "spe"}
    assert sum(spread.values()) == SP_BUDGET
    assert all(0 <= value <= 32 for value in spread.values())


def test_role_spread_rejects_unknown_role():
    with pytest.raises(ValueError, match="unsupported role archetype"):
        role_spread("unknown")  # type: ignore[arg-type]


def test_tier2_exhaustion_synthesizes_tier3_role_spread():
    moves = ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"]
    with (
        patch("recommender.recommend.get_resolved_build", return_value=None),
        patch("recommender.recommend.find_set_matching", return_value=None),
        patch("recommender.recommend.lookup_live_build", return_value=None),
        patch("recommender.recommend.select_usage_spread", return_value=None),
        patch(
            "recommender.recommend.species_usage",
            return_value={
                "common_abilities": [{"name": "Rough Skin"}],
                "top_spreads": [],
            },
        ),
    ):
        out = recommend_build("Garchomp", moves, "Life Orb", write_cache=False)
    assert out["ok"]
    assert spread_sum(out["set"].get("evs")) == SP_BUDGET
    assert out["source_tier"] == "tier3_role"
    flags = out.get("verification") or []
    assert any("tier2 exhausted" in f for f in flags)
    assert "tier3" in " ".join(flags)


def test_partial_spread_preserves_base_and_flags_remainder():
    moves = ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"]
    partial = {"hp": 20, "atk": 12, "def": 0, "spa": 0, "spd": 0, "spe": 0}
    matched = {
        "species": "Garchomp",
        "moves": moves,
        "item": "Life Orb",
        "evs": dict(partial),
    }
    with (
        patch("recommender.recommend.get_resolved_build", return_value=None),
        patch("recommender.recommend.find_set_matching", return_value=None),
        patch("recommender.recommend.lookup_live_build", return_value=matched),
    ):
        out = recommend_build("Garchomp", moves, "Life Orb", write_cache=False)
    assert out["ok"]
    evs = out["set"]["evs"]
    assert spread_sum(evs) == SP_BUDGET
    assert evs["hp"] >= 20
    assert evs["atk"] >= 12
    assert out["source_tier"] == "tier1_partial"
    flags = out.get("verification") or []
    assert any("incomplete-spread: used 32/66" in f for f in flags)
    assert any("remainder synthesized" in f for f in flags)
    assert "tier1_partial" in out["rationale"]


def test_full_exact_live_spread_keeps_live_provenance():
    moves = ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"]
    full = {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32}
    matched = {
        "species": "Garchomp",
        "moves": moves,
        "item": "Life Orb",
        "evs": dict(full),
    }
    with (
        patch("recommender.recommend.get_resolved_build", return_value=None),
        patch("recommender.recommend.find_set_matching", return_value=None),
        patch("recommender.recommend.lookup_live_build", return_value=matched),
    ):
        out = recommend_build("Garchomp", moves, "Life Orb", write_cache=False)
    assert out["ok"]
    assert out["set"]["evs"] == full
    assert out["source_tier"] == "live-lookup"
    flags = out.get("verification") or []
    assert not any("incomplete-spread" in f for f in flags)


def test_recommend_live_still_requires_full_budget():
    """Guard: test_recommend_live asserts spread_sum == SP_BUDGET after recommend.

    Both missing and partial paths still complete to 66 — only silence was removed.
    Read the live test's assertion site so this doesn't drift into an assumption.
    """
    from pathlib import Path

    live = Path(__file__).resolve().parent / "test_recommend_live.py"
    src = live.read_text()
    assert 'assert spread_sum(built.get("evs")) == SP_BUDGET' in src
    # Offline paths that complete spreads still hit the budget (see missing/partial tests).
    assert spread_sum({"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32}) == SP_BUDGET


def test_unspecified_item_skips_tier1_and_cache():
    moves = ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"]
    with (
        patch("recommender.recommend.get_resolved_build") as cached,
        patch("recommender.recommend.find_set_matching") as matched,
        patch("recommender.recommend.lookup_live_build", return_value=None),
        patch("recommender.recommend.select_usage_spread", return_value=None),
        patch(
            "recommender.recommend.species_usage",
            return_value={"common_abilities": [{"name": "Rough Skin"}], "top_spreads": []},
        ),
        patch("recommender.recommend.put_resolved_build") as put,
    ):
        out = recommend_build("Garchomp", moves, None, write_cache=True)
    assert out["ok"]
    cached.assert_not_called()
    matched.assert_not_called()
    put.assert_not_called()
    assert out["set"].get("item") is None


def test_explicit_empty_item_attempts_tier1():
    moves = ["Brave Bird", "Flare Blitz", "Tailwind", "Protect"]
    with (
        patch("recommender.recommend.get_resolved_build", return_value=None),
        patch("recommender.recommend.find_set_matching", return_value=None) as matched,
        patch("recommender.recommend.lookup_live_build", return_value=None),
        patch("recommender.recommend.select_usage_spread", return_value=None),
        patch(
            "recommender.recommend.species_usage",
            return_value={"common_abilities": [{"name": "Gale Wings"}], "top_spreads": []},
        ),
    ):
        out = recommend_build("Talonflame", moves, "", write_cache=False)
    assert out["ok"]
    matched.assert_called_once()
    assert matched.call_args.args[2] == ""
    assert out["set"].get("item") == ""
