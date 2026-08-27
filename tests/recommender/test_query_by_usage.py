"""Tests for recommender.by_usage.query_by_usage."""

from __future__ import annotations

from recommender.by_usage import query_by_usage
from recommender.counters import query_counters
from recommender.ids import to_id
from recommender.legality import is_species_legal, load_snapshot
from recommender.usage_data import ingame_species_map


def test_default_pool_usage_ranking():
    out = query_by_usage(n=20)
    assert len(out) <= 20
    assert out

    ranks = [c.usage_rank for c in out if c.usage_rank is not None]
    assert ranks == sorted(ranks)
    # First ranked result should be the lowest usage_rank in the ingame map.
    ig = ingame_species_map("champions-reg-mb")
    best = min(
        int(e["usage_rank"])
        for e in ig.values()
        if e.get("usage_rank") is not None
    )
    assert ranks[0] == best


def test_narrowed_fairy_pool():
    snap = load_snapshot()
    fairy: list[dict] = []
    for sid, entry in snap["species"].items():
        if not is_species_legal(snap, sid):
            continue
        types = entry.get("types") or []
        if "Fairy" in types:
            fairy.append({"species": str(entry.get("name") or sid)})

    assert fairy, "expected at least one legal Fairy species"
    out = query_by_usage(pool=fairy, n=10)
    assert out
    pool_ids = {to_id(s["species"]) for s in fairy}
    for c in out:
        assert to_id(c.spec["species"]) in pool_ids
        entry = snap["species"].get(to_id(c.spec["species"])) or {}
        assert "Fairy" in (entry.get("types") or [])
    ranks = [c.usage_rank for c in out if c.usage_rank is not None]
    assert ranks == sorted(ranks)


def test_composes_into_query_counters():
    top = query_by_usage(n=5)
    assert top
    anchor = top[0].spec
    counters = query_counters(anchor, n=10)
    assert counters  # end-to-end composition works


def test_usage_admission_honors_ownership_before_cut():
    pool = [{"species": "Kingambit"}, {"species": "Sinistcha"}]
    owned = "Sinistcha"
    assert [
        row.spec["species"]
        for row in query_by_usage(
            pool,
            n=2,
            available_species=[owned],
            ownership_mode="owned_first",
        )
    ][0] == owned
    assert [
        row.spec["species"]
        for row in query_by_usage(
            pool,
            n=2,
            available_species=[owned],
            ownership_mode="owned_last",
        )
    ][0] == pool[0]["species"]
    assert [
        row.spec["species"]
        for row in query_by_usage(
            pool,
            n=2,
            available_species=[owned],
            ownership_mode="owned_only",
        )
    ] == [owned]
