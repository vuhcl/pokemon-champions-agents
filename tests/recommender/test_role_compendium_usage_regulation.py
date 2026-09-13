"""Compendium construct usage regulation routing."""

from __future__ import annotations

from typing import Any

from recommender.role_compendium import (
    RAIN_SETTER_CRITERIA,
    RoleConstructionDraft,
    _UsageCtx,
    _offline_usage_row,
    construct_role_category,
    rebuild_role_category,
)


def _snap_for(tag: str, marker: str) -> dict[str, Any]:
    return {
        "meta": {"regulation": tag},
        "species": {
            "pelipper": {
                "name": "Pelipper",
                "id": "pelipper",
                "common_moves": [{"name": "Rain Dance", "pct": 50.0}],
                "marker": marker,
            }
        },
        "ingame_doubles": {
            "species": {
                "pelipper": {
                    "name": "Pelipper",
                    "id": "pelipper",
                    "common_moves": [{"name": "Rain Dance", "pct": 50.0}],
                    "marker": marker,
                }
            }
        },
        "showdown_vgc_mb": {"species": {}},
    }


def test_offline_usage_row_honors_regulation(monkeypatch):
    snaps = {
        "champions-reg-mb": _snap_for("champions-reg-mb", "mb"),
        "champions-reg-mc": _snap_for("champions-reg-mc", "mc"),
        "champions": _snap_for("champions-reg-mc", "mc"),
    }

    def fake_load(regulation: str = "champions-reg-mb") -> dict[str, Any]:
        return snaps.get(regulation) or snaps["champions-reg-mb"]

    monkeypatch.setattr("recommender.role_compendium.load_usage", fake_load)
    monkeypatch.setattr(
        "recommender.role_compendium.ingame_species_map",
        lambda regulation="champions-reg-mb": (
            fake_load(regulation).get("ingame_doubles") or {}
        ).get("species")
        or {},
    )
    monkeypatch.setattr(
        "recommender.role_compendium.showdown_species_map",
        lambda regulation="champions-reg-mb": {},
    )

    mb = _offline_usage_row("pelipper", regulation="champions-reg-mb")
    mc = _offline_usage_row("pelipper", regulation="champions-reg-mc")
    assert mb is not None and mb["marker"] == "mb"
    assert mc is not None and mc["marker"] == "mc"

    uctx_mb = _UsageCtx(live_fetch=None, regulation="champions-reg-mb")
    uctx_mc = _UsageCtx(live_fetch=None, regulation="champions-reg-mc")
    assert uctx_mb.entry_for("Pelipper")["marker"] == "mb"
    assert uctx_mc.entry_for("Pelipper")["marker"] == "mc"


def test_rebuild_default_regulation_is_champions(monkeypatch, tmp_path):
    seen: dict[str, Any] = {}

    def fake_construct(*_a, **kw):
        seen.clear()
        seen.update(kw)
        return RoleConstructionDraft(
            category="weather_setter",
            sub_criteria=dict(RAIN_SETTER_CRITERIA),
            candidates=[],
            considered_rejected=[],
            tiers={"Excellent": [], "Good": [], "Acceptable": []},
            notes=[],
        )

    monkeypatch.setattr(
        "recommender.role_compendium.construct_role_category", fake_construct
    )
    monkeypatch.setattr(
        "recommender.role_compendium.critique_role_ranking",
        lambda *_a, **_k: type("C", (), {"approved": False, "flags": []})(),
    )

    result = rebuild_role_category(
        "weather_setter",
        RAIN_SETTER_CRITERIA,
        roles_dir=tmp_path,
        live_fetch=None,
        showdown_fetch=None,
    )
    assert result.status == "needs_revision"
    assert seen.get("regulation") == "champions"
    assert "regulation" in seen
    assert seen["regulation"] != "champions-reg-mb"


def test_construct_forwards_explicit_regulation(monkeypatch):
    seen: dict[str, Any] = {}

    def fake_weather(*_a, **kw):
        seen["uctx_reg"] = kw["uctx"].regulation
        return RoleConstructionDraft(
            category="weather_setter",
            sub_criteria=dict(RAIN_SETTER_CRITERIA),
            candidates=[],
            considered_rejected=[],
            tiers={"Excellent": [], "Good": [], "Acceptable": []},
            notes=[],
        )

    monkeypatch.setattr(
        "recommender.role_compendium_weather._construct_weather_setter",
        fake_weather,
    )
    construct_role_category(
        "weather_setter",
        RAIN_SETTER_CRITERIA,
        ["Pelipper"],
        live_fetch=None,
        showdown_fetch=None,
        regulation="champions-reg-mb",
    )
    assert seen["uctx_reg"] == "champions-reg-mb"
