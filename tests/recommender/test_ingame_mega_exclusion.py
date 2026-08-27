"""Mega-capable CBD exclusion: identity helpers, filtered accessor, consumer inheritance."""

from __future__ import annotations

from unittest.mock import patch

from recommender.legality import load_snapshot
from recommender.move_narrowing import _commitment_pct
from recommender.usage_data import ingame_species_map
from recommender.role_compendium import _UsageCtx
from recommender.species_forms import ingame_excluded_species_ids, mega_capable_base_ids
from recommender.usage_data import (
    ingame_excluded_ids,
    ingame_species_map,
    load_usage,
    set_from_ingame,
    set_from_showdown,
)


def test_mega_capable_base_ids_spot_check():
    snap = load_snapshot()
    bases = mega_capable_base_ids(snap)
    assert "charizard" in bases
    assert "garchomp" in bases
    assert "sinistcha" not in bases
    assert "klefki" not in bases


def test_ingame_excluded_includes_base_and_mega_children():
    snap = load_snapshot()
    excluded = ingame_excluded_species_ids(snap)
    assert "charizard" in excluded
    assert "charizardmegay" in excluded
    assert "klefki" not in excluded


def test_ingame_species_map_excludes_mega_capable_bases():
    ig = ingame_species_map("champions-reg-mb")
    assert "charizard" not in ig
    assert "swampert" not in ig


def test_ingame_species_map_keeps_non_mega_species():
    ig = ingame_species_map("champions-reg-mb")
    raw = (load_usage("champions-reg-mb").get("ingame_doubles") or {}).get("species") or {}
    for sid in raw:
        if sid not in ingame_excluded_ids():
            assert sid in ig


def test_set_from_ingame_none_for_mega_capable():
    assert set_from_ingame("Charizard") is None


def test_set_from_showdown_works_for_mega_forme():
    assert set_from_showdown("Charizard-Mega-Y") is not None


def test_commitment_pct_none_for_excluded_species():
    assert "charizard" not in ingame_species_map("champions-reg-mb")
    assert (
        _commitment_pct("Charizard", "FakeMove", regulation="champions-reg-mb") is None
    )


def test_champions_entry_gates_excluded_species():
    ctx = _UsageCtx(live_fetch=lambda _s: {"common_moves": [{"name": "Fake", "pct": 100}]})
    assert ctx.champions_entry("Charizard") is None


def test_champions_entry_live_fetch_not_called_for_excluded():
    fetch_calls: list[str] = []

    def _track(species: str):
        fetch_calls.append(species)
        return {"common_moves": []}

    ctx = _UsageCtx(live_fetch=_track)
    assert ctx.champions_entry("Swampert") is None
    assert fetch_calls == []


def test_extract_ingame_skips_mega_capable(monkeypatch):
    import importlib.util
    from pathlib import Path

    mod_path = (
        Path(__file__).resolve().parents[2] / "scripts/extract_usage/fetch_usage_mb.py"
    )
    spec = importlib.util.spec_from_file_location("fetch_usage_mb", mod_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    legality = load_snapshot()
    excluded = ingame_excluded_species_ids(legality)

    def _fake_index():
        return {
            "pokemon": [
                {
                    "showdownName": "Charizard",
                    "showdownId": "charizard",
                    "summary": {
                        "battleSummary": {"Current": {"Doubles": {"position": 1}}}
                    },
                },
                {
                    "showdownName": "Klefki",
                    "showdownId": "klefki",
                    "summary": {
                        "battleSummary": {"Current": {"Doubles": {"position": 2}}}
                    },
                },
            ]
        }

    fetched: list[str] = []

    def _fake_fetch(name: str):
        fetched.append(name)
        return {"id": name.lower(), "name": name, "common_moves": []}

    monkeypatch.setattr(mod, "fetch_json", lambda _url: _fake_index())
    monkeypatch.setattr(mod, "fetch_ingame_doubles_species", _fake_fetch)

    out = mod.extract_ingame(top_n=None)
    assert "charizard" not in out
    assert "klefki" in out
    assert fetched == ["Klefki"]
    assert "charizard" in excluded
