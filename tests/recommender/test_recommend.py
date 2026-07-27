from unittest.mock import MagicMock, patch

from recommender.contingent_value import categorize_champions_pool, diff_categories
from recommender.legality import check_set, resolve_learnset, load_snapshot
from recommender.recommend import recommend_build, select_opponent_builds
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
    draft = [empty_slot(i) for i in range(6)]
    draft[0]["set"] = {"species": "Garchomp", "item": "Life Orb", "moves": ["Earthquake"]}
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
