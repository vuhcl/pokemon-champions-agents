"""Showdown fetch: offline-first, None on incomplete meta (B4)."""

from __future__ import annotations

import recommender.usage_showdown as us


def test_fetch_showdown_vgc_species_none_when_showdown_meta_incomplete(monkeypatch):
    """Regulation without grafted Showdown meta must not raise or hit the network."""
    network = {"called": False}

    def _boom(*_a, **_k):
        network["called"] = True
        raise AssertionError("fetch_json must not run when meta is incomplete")

    monkeypatch.setattr(us, "showdown_species_map", lambda _regulation: {})
    monkeypatch.setattr(us, "fetch_json", _boom)

    import recommender.usage_chaos as uc

    monkeypatch.setattr(
        uc,
        "load_usage",
        lambda _regulation: {"meta": {"showdown_pct_kind": "weight_over_raw_count"}},
    )

    assert us.fetch_showdown_vgc_species("Pikachu", regulation="champions-reg-future") is None
    assert network["called"] is False
