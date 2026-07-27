"""Live (non-mocked) integration: usage snapshot + calc service + recommend/quick_pick."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from recommender.calc_client import CalcClient
from recommender.calc_service import CalcService
from recommender.quick_pick import quick_pick
from recommender.recommend import recommend_build, select_opponent_builds, spread_sum, SP_BUDGET
from recommender.usage_data import featured_or_common_set, species_usage

pytestmark = pytest.mark.skipif(
    os.environ.get("CALC_LIVE") != "1",
    reason="needs live calc service (CALC_LIVE=1)",
)

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def live_client():
    with CalcService(repo_root=REPO) as svc:
        yield CalcClient(svc.base_url)


def test_live_select_opponent_builds_from_pikalytics_snapshot():
    sets = select_opponent_builds(
        ["Garchomp", "Kingambit", "Incineroar", "NotInSnapshot"],
        regulation="champions",
        k=5,
    )
    assert 1 <= len(sets) <= 3
    names = {s["species"] for s in sets}
    assert "Garchomp" in names or any("Garchomp" in n for n in names)
    for s in sets:
        assert s.get("moves")
        assert s.get("item")
        # Must come from real usage data, not invented
        assert species_usage(s["species"]) is not None


def test_live_recommend_build_garchomp(live_client: CalcClient, tmp_path):
    usage = featured_or_common_set("Garchomp")
    assert usage is not None
    moves = list(usage["moves"])
    item = usage["item"]
    assert "Earthquake" in moves or any(m == "Earthquake" for m in moves)

    out = recommend_build(
        "Garchomp",
        moves,
        item,
        regulation="champions",
        calculate_batch=live_client.calculate_batch,
        write_cache=False,
    )
    assert out["ok"], out
    built = out["set"]
    assert built is not None
    assert spread_sum(built.get("evs")) == SP_BUDGET
    assert built.get("item")
    assert len(built.get("moves") or []) >= 1

    # Known matchup sanity: Garchomp EQ vs Kingambit should KO / strong damage
    king = featured_or_common_set("Kingambit") or {
        "species": "Kingambit",
        "evs": {"hp": 32, "atk": 32, "def": 0, "spa": 0, "spd": 2, "spe": 0},
    }
    calc = live_client.calculate(
        {
            "species": "Garchomp",
            "item": built.get("item") or "Life Orb",
            "evs": built["evs"],
            "nature": "Jolly",
        },
        {
            "species": king.get("species") or "Kingambit",
            "evs": king.get("evs") or {"hp": 32, "atk": 32, "def": 0, "spa": 0, "spd": 2, "spe": 0},
        },
        "Earthquake",
        field={"gameType": "Doubles"},
    )
    lo, hi = calc["damageRange"]
    assert hi > 0
    assert "HKO" in calc["koChance"] or lo > 50
    # verification notes from recommend should mention calc when batch ran
    assert out.get("verification")


def test_live_quick_pick(live_client: CalcClient):
    def set_of(name: str) -> dict:
        s = featured_or_common_set(name)
        assert s is not None, f"missing usage for {name}"
        if not s.get("evs"):
            s = {
                **s,
                "evs": {"hp": 20, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 14},
            }
        return s

    team = [
        set_of("Garchomp"),
        set_of("Kingambit"),
        set_of("Incineroar"),
        set_of("Whimsicott"),
        set_of("Pelipper"),
        set_of("Sinistcha"),
    ]
    out = quick_pick(
        team,
        ["Garchomp", "Kingambit", "Incineroar"],
        regulation="champions",
        calculate_batch=live_client.calculate_batch,
    )
    assert out["ok"], out
    assert len(out["bring"]) == 4
    assert len(set(out["bring"])) == 4
    assert all(0 <= i <= 5 for i in out["bring"])
    assert len(out["rationales"]) == 4
