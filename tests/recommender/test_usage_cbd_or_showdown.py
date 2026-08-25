"""CBD row without a move must still consult Showdown (per-move, not wholesale)."""

from __future__ import annotations

from recommender.ids import to_id
from recommender.role_compendium import (
    _TRICK_ROOM_SET_PCT_FLOOR,
    _USAGE_SET_PCT_FLOOR,
    _UsageCtx,
    _delivery_usage_hits,
    _hits_clear_set_pct_floor,
    _same_row_both_moves,
    _usage_has_item,
)


def _uctx(cbd_moves: list[str], sd_moves: list[str], *, cbd_items: list[str] | None = None):
    cbd = {
        "name": "Skarmory",
        "id": "skarmory",
        "common_moves": [{"name": m, "pct": 10.0} for m in cbd_moves],
        "common_items": [{"name": i, "pct": 10.0} for i in (cbd_items or [])],
        "source": "championsbattledata",
    }
    sd = {
        "name": "Skarmory",
        "id": "skarmory",
        "common_moves": [{"name": m, "pct": 20.0} for m in sd_moves],
        "common_items": [],
        "source": "smogon-chaos",
    }
    return _UsageCtx(
        live_fetch=lambda _n: cbd,
        showdown_fetch=lambda _n: sd,
    )


_EMPTY_USAGE = {
    "ingame_doubles": {"species": {}},
    "showdown_vgc_mb": {"species": {}},
    "species": {},
}


def _patch_empty_usage_maps(monkeypatch) -> None:
    monkeypatch.setattr("recommender.role_compendium.load_usage", lambda: _EMPTY_USAGE)
    monkeypatch.setattr("recommender.role_compendium_usage.load_usage", lambda: _EMPTY_USAGE)
    monkeypatch.setattr("recommender.role_compendium.showdown_species_map", lambda: {})
    monkeypatch.setattr("recommender.role_compendium_usage.showdown_species_map", lambda: {})


def test_same_row_both_moves_uses_showdown_when_cbd_lacks_one(monkeypatch):
    _patch_empty_usage_maps(monkeypatch)
    uctx = _uctx(["Brave Bird"], ["Iron Defense", "Body Press"])
    assert _same_row_both_moves(
        "Skarmory",
        "irondefense",
        "bodypress",
        uctx=uctx,
        sd_cache={},
        showdown_fetch=uctx.showdown_fetch,
    )


def test_same_row_both_moves_false_when_split_across_sources(monkeypatch):
    _patch_empty_usage_maps(monkeypatch)
    uctx = _uctx(["Iron Defense"], ["Body Press"])
    assert not _same_row_both_moves(
        "Skarmory",
        "irondefense",
        "bodypress",
        uctx=uctx,
        sd_cache={},
        showdown_fetch=uctx.showdown_fetch,
    )


def test_delivery_hits_showdown_when_cbd_row_lacks_move(monkeypatch):
    _patch_empty_usage_maps(monkeypatch)
    uctx = _uctx(["Psychic"], ["Trick Room", "Psychic"])
    hits, source = _delivery_usage_hits(
        "Chimecho",
        {"trickroom"},
        uctx=uctx,
        sd_cache={},
        showdown_fetch=uctx.showdown_fetch,
    )
    assert hits == {"trickroom"}
    assert source == "showdown"
    assert to_id("Trick Room") in hits


def test_usage_has_item_falls_back_to_showdown(monkeypatch):
    _patch_empty_usage_maps(monkeypatch)
    uctx = _uctx(["Light Screen"], ["Light Screen"], cbd_items=[])
    uctx.showdown_fetch = lambda _n: {  # type: ignore[method-assign]
        "name": "Whimsicott",
        "id": "whimsicott",
        "common_moves": [{"name": "Light Screen", "pct": 2.32}],
        "common_items": [{"name": "Light Clay", "pct": 0.19}],
        "source": "smogon-chaos",
    }
    assert _usage_has_item(
        "Whimsicott",
        "lightclay",
        uctx=uctx,
        sd_cache={},
        showdown_fetch=uctx.showdown_fetch,
    )


def test_delivery_hits_drops_below_set_pct_floor(monkeypatch):
    _patch_empty_usage_maps(monkeypatch)
    uctx = _uctx([], ["Light Screen"])
    uctx.showdown_fetch = lambda _n: {  # type: ignore[method-assign]
        "name": "Sableye-Mega",
        "id": "sableyemega",
        "common_moves": [{"name": "Reflect", "pct": 1.98}],
        "common_items": [],
        "source": "smogon-chaos",
    }
    hits, source = _delivery_usage_hits(
        "Sableye-Mega",
        {"reflect"},
        uctx=uctx,
        sd_cache={},
        showdown_fetch=uctx.showdown_fetch,
        set_pct_floor=_USAGE_SET_PCT_FLOOR,
    )
    assert hits == set()
    assert source.endswith("_below_floor")


def test_delivery_hits_keeps_whimsicott_ls_at_screens_floor(monkeypatch):
    _patch_empty_usage_maps(monkeypatch)
    uctx = _uctx([], [])
    uctx.showdown_fetch = lambda _n: {  # type: ignore[method-assign]
        "name": "Whimsicott",
        "id": "whimsicott",
        "common_moves": [{"name": "Light Screen", "pct": 2.32}],
        "common_items": [],
        "source": "smogon-chaos",
    }
    hits, _source = _delivery_usage_hits(
        "Whimsicott",
        {"lightscreen"},
        uctx=uctx,
        sd_cache={},
        showdown_fetch=uctx.showdown_fetch,
        set_pct_floor=_USAGE_SET_PCT_FLOOR,
    )
    assert hits == {"lightscreen"}
    assert _hits_clear_set_pct_floor(
        "Whimsicott",
        {"lightscreen"},
        floor=_USAGE_SET_PCT_FLOOR,
        uctx=uctx,
        sd_cache={},
        showdown_fetch=uctx.showdown_fetch,
    )


def test_trick_room_floor_drops_attacker_incidental(monkeypatch):
    _patch_empty_usage_maps(monkeypatch)
    uctx = _uctx([], [])
    uctx.showdown_fetch = lambda _n: {  # type: ignore[method-assign]
        "name": "Gallade-Mega",
        "id": "gallademega",
        "common_moves": [{"name": "Trick Room", "pct": 2.90}],
        "common_items": [],
        "source": "smogon-chaos",
    }
    hits_tr, _ = _delivery_usage_hits(
        "Gallade-Mega",
        {"trickroom"},
        uctx=uctx,
        sd_cache={},
        showdown_fetch=uctx.showdown_fetch,
        set_pct_floor=_TRICK_ROOM_SET_PCT_FLOOR,
    )
    hits_default, _ = _delivery_usage_hits(
        "Gallade-Mega",
        {"trickroom"},
        uctx=uctx,
        sd_cache={},
        showdown_fetch=uctx.showdown_fetch,
        set_pct_floor=_USAGE_SET_PCT_FLOOR,
    )
    assert hits_tr == set()
    assert hits_default == {"trickroom"}
