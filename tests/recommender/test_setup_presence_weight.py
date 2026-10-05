"""Setup presence: ingame pct OR Showdown weighted-set floor."""

from __future__ import annotations

from recommender.role_compendium import _UsageCtx
from recommender.role_compendium_setup_constants import (
    _SETUP_PRESENCE_INGAME_PCT_FLOOR,
    _SETUP_PRESENCE_SHOWDOWN_WEIGHT_FLOOR,
)
from recommender.role_compendium_usage import _hits_clear_setup_presence


def test_presence_constants():
    assert _SETUP_PRESENCE_INGAME_PCT_FLOOR == 0.1
    assert _SETUP_PRESENCE_SHOWDOWN_WEIGHT_FLOOR == 20


def test_presence_true_at_weight_20_when_ig_zero(monkeypatch):
    monkeypatch.setattr(
        "recommender.role_compendium_usage.ingame_species_map",
        lambda regulation="champions": {},
    )
    monkeypatch.setattr(
        "recommender.forme_identity.canonical_usage_species_id",
        lambda snap, sid, *, regulation: sid,
    )

    def fake_sd(name, *, cache, showdown_fetch, regulation="champions", snap=None):
        return {
            "common_moves": [
                {"name": "Swords Dance", "pct": 0.05, "weight": 20.0},
            ]
        }

    monkeypatch.setattr(
        "recommender.role_compendium_usage._showdown_entry", fake_sd
    )
    uctx = _UsageCtx(live_fetch=None, regulation="champions-reg-mc")
    assert _hits_clear_setup_presence(
        "Pinsir",
        {"swordsdance"},
        uctx=uctx,
        sd_cache={},
        showdown_fetch=None,
    )


def test_presence_false_at_weight_19_when_ig_zero(monkeypatch):
    monkeypatch.setattr(
        "recommender.role_compendium_usage.ingame_species_map",
        lambda regulation="champions": {},
    )

    def fake_sd(name, *, cache, showdown_fetch, regulation="champions", snap=None):
        return {
            "common_moves": [
                {"name": "Swords Dance", "pct": 0.05, "weight": 19.0},
            ]
        }

    monkeypatch.setattr(
        "recommender.role_compendium_usage._showdown_entry", fake_sd
    )
    monkeypatch.setattr(
        "recommender.forme_identity.canonical_usage_species_id",
        lambda snap, sid, *, regulation: sid,
    )
    uctx = _UsageCtx(live_fetch=None, regulation="champions-reg-mc")
    assert not _hits_clear_setup_presence(
        "Pinsir",
        {"swordsdance"},
        uctx=uctx,
        sd_cache={},
        showdown_fetch=None,
    )


def test_presence_missing_weight_is_showdown_false(monkeypatch):
    monkeypatch.setattr(
        "recommender.role_compendium_usage.ingame_species_map",
        lambda regulation="champions": {},
    )

    def fake_sd(name, *, cache, showdown_fetch, regulation="champions", snap=None):
        return {"common_moves": [{"name": "Swords Dance", "pct": 5.0}]}

    monkeypatch.setattr(
        "recommender.role_compendium_usage._showdown_entry", fake_sd
    )
    monkeypatch.setattr(
        "recommender.forme_identity.canonical_usage_species_id",
        lambda snap, sid, *, regulation: sid,
    )
    uctx = _UsageCtx(live_fetch=None, regulation="champions-reg-mc")
    assert not _hits_clear_setup_presence(
        "Pinsir",
        {"swordsdance"},
        uctx=uctx,
        sd_cache={},
        showdown_fetch=None,
    )


def test_presence_ingame_only_admits(monkeypatch):
    monkeypatch.setattr(
        "recommender.role_compendium_usage.ingame_species_map",
        lambda regulation="champions": {
            "rillaboom": {
                "common_moves": [{"name": "Swords Dance", "pct": 5.0}],
            }
        },
    )

    def fake_sd(name, *, cache, showdown_fetch, regulation="champions", snap=None):
        return None

    monkeypatch.setattr(
        "recommender.role_compendium_usage._showdown_entry", fake_sd
    )
    monkeypatch.setattr(
        "recommender.forme_identity.canonical_usage_species_id",
        lambda snap, sid, *, regulation: sid,
    )
    uctx = _UsageCtx(live_fetch=None, regulation="champions-reg-mc")
    assert _hits_clear_setup_presence(
        "Rillaboom",
        {"swordsdance"},
        uctx=uctx,
        sd_cache={},
        showdown_fetch=None,
    )


def test_presence_require_all_id_bp(monkeypatch):
    monkeypatch.setattr(
        "recommender.role_compendium_usage.ingame_species_map",
        lambda regulation="champions": {},
    )

    def fake_sd(name, *, cache, showdown_fetch, regulation="champions", snap=None):
        return {
            "common_moves": [
                {"name": "Iron Defense", "pct": 10.0, "weight": 25.0},
                {"name": "Body Press", "pct": 10.0, "weight": 10.0},
            ]
        }

    monkeypatch.setattr(
        "recommender.role_compendium_usage._showdown_entry", fake_sd
    )
    monkeypatch.setattr(
        "recommender.forme_identity.canonical_usage_species_id",
        lambda snap, sid, *, regulation: sid,
    )
    uctx = _UsageCtx(live_fetch=None, regulation="champions-reg-mc")
    assert not _hits_clear_setup_presence(
        "Corviknight",
        {"irondefense", "bodypress"},
        uctx=uctx,
        sd_cache={},
        showdown_fetch=None,
        require_all=True,
    )
