"""Threat ranking, forme expand, and matchup memo (in-game + Showdown@1500)."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from recommender.calc_client import CalcClient, CalcRequest
from recommender.coverage import get_relevant_threats
from recommender.matchup import (
    MATCHUP_MEMO_MAX_ENTRIES,
    bind_matchup_memo_thread,
    classify_matchup,
    clear_matchup_memo,
    matchup_memo_stats,
)
from recommender.state import ThreatCandidate
from recommender.usage_data import TEAM_THREAT_N, SLOT_THREAT_N, lineage_ids


def _calc(**kwargs: Any) -> dict[str, Any]:
    defender_hp = kwargs.get("defender_hp", 100)
    dmg = kwargs.get("damage_range") or [defender_hp, defender_hp]
    return {
        "damageRange": dmg,
        "koChance": kwargs.get("ko_chance", "100% OHKO"),
        "raw": {
            "damage": dmg,
            "range": dmg,
            "kochance": {
                "chance": kwargs.get("kochance_chance", 1.0),
                "n": kwargs.get("kochance_n", 1),
                "text": kwargs.get("ko_chance", "100% OHKO"),
            },
            "stats": {
                "attacker": {
                    "spe": kwargs.get("attacker_spe", 100),
                    "hp": kwargs.get("attacker_hp", 100),
                },
                "defender": {"hp": defender_hp},
            },
        },
    }


class MockCalcClient(CalcClient):
    def __init__(self, default: dict[str, Any] | None = None) -> None:
        super().__init__("http://mock")
        self._default = default or _calc()
        self.calls = 0

    def calculate_batch(self, requests: list[CalcRequest]) -> list[dict[str, Any]]:
        self.calls += len(requests)
        return [dict(self._default) for _ in requests]


@pytest.fixture(autouse=True)
def _clear_memo():
    clear_matchup_memo()
    yield
    clear_matchup_memo()


# --- lineage / expand / ranking ---


def test_lineage_charizard_includes_megas_and_gmax():
    kids = lineage_ids("Charizard")
    assert "charizard" in kids
    assert "charizardmegax" in kids
    assert "charizardmegay" in kids
    assert "charizardgmax" in kids


def test_mega_capable_bases_absent_from_ingame_threat_ladder():
    """Mega-capable lineages are excluded from the in-game threat pool."""
    cands = get_relevant_threats({"regulation_mod": "champions"}, n=50)  # type: ignore[arg-type]
    ladder = {c.ladder_species for c in cands}
    assert "Charizard" not in ladder
    assert "Garchomp" not in ladder
    assert "Swampert" not in ladder


def test_ranked_by_ingame_usage_rank():
    cands = get_relevant_threats({"regulation_mod": "champions"}, n=5)  # type: ignore[arg-type]
    ranks = [c.usage_rank for c in cands if c.usage_rank is not None]
    # Ladder order preserved across expand (same rank may repeat for formes)
    assert ranks == sorted(ranks)
    assert cands[0].usage_rank == 1
    assert cands[0].ladder_species == "Kingambit"


def test_team_default_n_is_50_ladder_species():
    cands = get_relevant_threats({"regulation_mod": "champions"})  # type: ignore[arg-type]
    ladder = {c.ladder_species for c in cands}
    assert len(ladder) == TEAM_THREAT_N
    assert len(cands) >= TEAM_THREAT_N  # expand may grow


def test_slot_filter_default_n_is_10():
    cands = get_relevant_threats(
        {"regulation_mod": "champions"},  # type: ignore[arg-type]
        relevance_filter=lambda _s: True,
    )
    ladder = {c.ladder_species for c in cands}
    assert len(ladder) == SLOT_THREAT_N


def test_relevance_filter_drops_non_matching():
    cands = get_relevant_threats(
        {"regulation_mod": "champions"},  # type: ignore[arg-type]
        n=20,
        relevance_filter=lambda s: "kingambit" in s["species"].lower().replace("-", ""),
    )
    assert cands
    assert all("kingambit" in c.spec["species"].lower().replace("-", "") for c in cands)


def test_multi_form_never_ingame_build_source():
    cands = get_relevant_threats({"regulation_mod": "champions"}, n=10)  # type: ignore[arg-type]
    by_ladder: dict[str, list[ThreatCandidate]] = {}
    for c in cands:
        by_ladder.setdefault(c.ladder_species, []).append(c)
    multi = [cs for cs in by_ladder.values() if len(cs) >= 2]
    assert multi, "expected at least one multi-form lineage in top 10"
    for cs in multi:
        assert all(c.build_source in {"showdown_form", "showdown_partial_fallback"} for c in cs)


def test_no_inferred_mega_fields():
    cands = get_relevant_threats({"regulation_mod": "champions"}, n=5)  # type: ignore[arg-type]
    for c in cands:
        assert not hasattr(c, "inferred_mega_form")
        assert not hasattr(c, "inferred_mega_share")


# --- matchup memo ---


A = {
    "species": "Garchomp",
    "item": "Life Orb",
    "ability": "Rough Skin",
    "moves": ["Earthquake", "Dragon Claw"],
    "evs": {"hp": 0, "atk": 32, "spe": 32},
}
B = {
    "species": "Kingambit",
    "item": "Black Glasses",
    "ability": "Defiant",
    "moves": ["Sucker Punch", "Kowtow Cleave"],
    "evs": {"hp": 32, "atk": 32, "spe": 0},
}


def test_memo_hit_same_key_cross_call():
    client = MockCalcClient()
    bind_matchup_memo_thread("t1")
    r1 = classify_matchup(A, B, None, client=client)
    calls_after_first = client.calls
    r2 = classify_matchup(A, B, None, client=client)
    assert r1 == r2
    assert client.calls == calls_after_first
    stats = matchup_memo_stats()
    assert stats["hits"] >= 1
    assert stats["misses"] >= 1


def test_memo_miss_on_ev_change():
    client = MockCalcClient()
    bind_matchup_memo_thread("t1")
    classify_matchup(A, B, None, client=client)
    a2 = {**A, "evs": {"hp": 4, "atk": 32, "spe": 32}}
    classify_matchup(a2, B, None, client=client)
    assert matchup_memo_stats()["misses"] >= 2


def test_memo_clears_on_thread_change():
    client = MockCalcClient()
    bind_matchup_memo_thread("t1")
    classify_matchup(A, B, None, client=client)
    assert matchup_memo_stats()["misses"] >= 1
    bind_matchup_memo_thread("t2")
    assert matchup_memo_stats() == {"hits": 0, "misses": 0}
    classify_matchup(A, B, None, client=client)
    assert matchup_memo_stats()["misses"] >= 1


def test_memo_persists_across_same_thread_bind():
    client = MockCalcClient()
    bind_matchup_memo_thread("t1")
    classify_matchup(A, B, None, client=client)
    bind_matchup_memo_thread("t1")
    classify_matchup(A, B, None, client=client)
    assert matchup_memo_stats()["hits"] >= 1


def test_lru_eviction_under_tiny_cap():
    import recommender.matchup as m

    client = MockCalcClient()
    bind_matchup_memo_thread("lru")
    with patch.object(m, "MATCHUP_MEMO_MAX_ENTRIES", 2):
        for i in range(4):
            a = {**A, "evs": {"hp": i, "atk": 32, "spe": 32}}
            classify_matchup(a, B, None, client=client)
        # First key should be gone — recomputing it is a miss
        before = matchup_memo_stats()["misses"]
        classify_matchup({**A, "evs": {"hp": 0, "atk": 32, "spe": 32}}, B, None, client=client)
        assert matchup_memo_stats()["misses"] == before + 1


def test_spof_style_hit_rate_under_real_cap():
    """6 slots × 50 threats: within-call reuse should hit ≥ 0.75 under full LRU cap."""
    from recommender.coverage import detect_spof
    from recommender.state import Attr, Slot

    clear_matchup_memo()
    bind_matchup_memo_thread("hitrate")
    assert MATCHUP_MEMO_MAX_ENTRIES >= 8192

    slots = [
        Slot(
            species=Attr(value=f"Mon{i}", locked=True),
            item=Attr(value="Leftovers"),
            moveset=Attr(value=["Tackle", "Protect"]),
            spread=Attr(value={"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}),
        )
        for i in range(6)
    ]
    threats = [
        {
            "species": f"Threat{j}",
            "item": "Life Orb",
            "ability": "Pressure",
            "moves": ["Tackle"],
            "evs": {"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
        }
        for j in range(50)
    ]
    client = MockCalcClient()

    with patch("recommender.coverage._slot_to_spec") as slot_spec:
        slot_spec.side_effect = lambda slot, *, regulation="champions": {
            "species": slot.species.value,
            "item": slot.item.value,
            "moves": list(slot.moveset.value or []),
            "evs": dict(slot.spread.value or {}),
        }
        detect_spof(slots, threats, client=client)

    stats = matchup_memo_stats()
    total = stats["hits"] + stats["misses"]
    assert total > 0
    rate = stats["hits"] / total
    assert rate >= 0.75, f"hit rate {rate:.3f} stats={stats}"


def test_eviction_pressure_lowers_hit_rate():
    """Tiny LRU cap under the same SPOF pattern shows eviction pressure."""
    import recommender.matchup as m
    from recommender.coverage import detect_spof
    from recommender.state import Attr, Slot

    clear_matchup_memo()
    bind_matchup_memo_thread("pressure")
    slots = [
        Slot(
            species=Attr(value=f"Mon{i}", locked=True),
            item=Attr(value="Leftovers"),
            moveset=Attr(value=["Tackle"]),
            spread=Attr(value={"hp": i, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}),
        )
        for i in range(6)
    ]
    threats = [
        {"species": f"Threat{j}", "item": "Life Orb", "moves": ["Tackle"], "evs": {"hp": j}}
        for j in range(50)
    ]
    client = MockCalcClient()

    with (
        patch.object(m, "MATCHUP_MEMO_MAX_ENTRIES", 32),
        patch("recommender.coverage._slot_to_spec") as slot_spec,
    ):
        slot_spec.side_effect = lambda slot, *, regulation="champions": {
            "species": slot.species.value,
            "item": slot.item.value,
            "moves": list(slot.moveset.value or []),
            "evs": dict(slot.spread.value or {}),
        }
        detect_spof(slots, threats, client=client)

    stats = matchup_memo_stats()
    total = stats["hits"] + stats["misses"]
    rate = stats["hits"] / total
    assert rate < 0.75, f"expected eviction pressure, got rate={rate:.3f} stats={stats}"
