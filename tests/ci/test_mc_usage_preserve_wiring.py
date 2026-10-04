"""Preserve-on-write + previous-before-extract wiring for M-C usage refresh."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from scripts.ci.usage_refresh_mc_gate import run_gate
from scripts.extract_usage.fetch_usage_mc_munchstats import (
    EXPECTED_SHOWDOWN_FORMAT,
    SHOWDOWN_BATTLES_FLOOR,
    SHOWDOWN_SPECIES_FLOOR,
    SOURCE,
    build_snapshot,
    main as munchstats_main,
)


def _species_row(sid: str, *, source: str = SOURCE) -> dict[str, Any]:
    return {
        "id": sid,
        "name": sid.title(),
        "common_moves": [{"name": "Tackle", "pct": 50.0}],
        "common_items": [],
        "common_abilities": [],
        "teammates": [],
        "top_spreads": [],
        "featured_sets": [],
        "source": source,
    }


def _ingame_meeting_floor(n: int = 230) -> dict[str, dict[str, Any]]:
    return {f"s{i}": _species_row(f"s{i}") for i in range(n)}


def _grafted_previous(ingame: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    ingame = ingame or _ingame_meeting_floor()
    sd = {
        f"p{i}": _species_row(f"p{i}", source="smogon-chaos")
        for i in range(SHOWDOWN_SPECIES_FLOOR)
    }
    sd["salamence"] = _species_row("salamence", source="smogon-chaos")
    sd["garchomp"] = _species_row("garchomp", source="smogon-chaos")
    return {
        "meta": {
            "schema_version": 3,
            "regulation": "champions-reg-mc",
            "munchstats_generated_at": "2026-09-10T00:00:00+00:00",
            "munchstats_published_at": "2026-09-10T00:00:01+00:00",
            "munchstats_captured_on": "2026-09-10",
            "munchstats_default_season": "Current",
            "showdown_format": EXPECTED_SHOWDOWN_FORMAT,
            "showdown_month": "2026-09",
            "showdown_rating": 1500,
            "showdown_source": "smogon-chaos",
            "showdown_battles": SHOWDOWN_BATTLES_FLOOR,
            "showdown_pct_kind": "set",
            "sources": [SOURCE, "smogon-chaos"],
        },
        "ingame_doubles": {"species": ingame},
        "showdown_vgc_mb": {"species": sd},
        "species": dict(ingame),
    }


def test_build_snapshot_preserves_correct_format_showdown():
    ingame = _ingame_meeting_floor(5)
    previous = _grafted_previous(ingame)
    index = {
        "generatedAt": "2026-09-20T12:00:00+00:00",
        "publishedAt": "2026-09-20T12:00:01+00:00",
        "capturedOn": "2026-09-20",
        "defaultSeason": "Current",
        "count": 5,
    }
    stats = {"join_n": 5, "detail_fetch_ok_n": 5, "detail_fetch_fail_n": 0, "index_count": 5}
    snap = build_snapshot(ingame, index, stats, previous=previous)
    assert snap["showdown_vgc_mb"]["species"] == previous["showdown_vgc_mb"]["species"]
    meta = snap["meta"]
    assert meta["showdown_format"] == EXPECTED_SHOWDOWN_FORMAT
    assert meta["showdown_month"] == "2026-09"
    assert meta["showdown_battles"] == SHOWDOWN_BATTLES_FLOOR
    assert meta["munchstats_generated_at"] == index["generatedAt"]
    assert "smogon-chaos" in meta["sources"]
    assert snap["species"]["salamence"]["source"] == "smogon-chaos"


def test_build_snapshot_does_not_preserve_wrong_format():
    ingame = _ingame_meeting_floor(3)
    previous = _grafted_previous(ingame)
    previous["meta"]["showdown_format"] = "gen9championsvgc2026regmb"
    index = {"generatedAt": "2026-09-20T12:00:00+00:00", "count": 3}
    stats = {"join_n": 3, "detail_fetch_ok_n": 3, "detail_fetch_fail_n": 0, "index_count": 3}
    snap = build_snapshot(ingame, index, stats, previous=previous)
    assert snap["showdown_vgc_mb"]["species"] == {}
    assert "showdown_format" not in snap["meta"]


def test_run_gate_passes_previous_and_preserves_showdown(tmp_path: Path):
    previous = _grafted_previous()
    out_path = tmp_path / "champions-reg-mc.v1.json"
    out_path.write_text(json.dumps(previous) + "\n", encoding="utf-8")

    captured: dict[str, Any] = {}
    index = {
        "generatedAt": "2026-09-21T00:00:00+00:00",
        "publishedAt": "2026-09-21T00:00:01+00:00",
        "capturedOn": "2026-09-21",
        "defaultSeason": "Current",
        "count": 230,
    }
    stats = {
        "join_n": 230,
        "detail_fetch_ok_n": 230,
        "detail_fetch_fail_n": 0,
        "index_count": 230,
    }
    new_ingame = _ingame_meeting_floor(230)

    def extract_fn(*, previous=None):
        captured["previous"] = previous
        snap = build_snapshot(new_ingame, index, stats, previous=previous)
        return snap, index, stats

    result = run_gate(out_path=out_path, force=True, extract_fn=extract_fn)

    assert captured["previous"] is not None
    assert captured["previous"]["meta"]["showdown_format"] == EXPECTED_SHOWDOWN_FORMAT
    assert result["decision"] == "commit"
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["showdown_vgc_mb"]["species"] == previous["showdown_vgc_mb"]["species"]
    for k in (
        "showdown_format",
        "showdown_month",
        "showdown_rating",
        "showdown_source",
        "showdown_battles",
    ):
        assert written["meta"][k] == previous["meta"][k]
    assert written["meta"]["munchstats_generated_at"] == index["generatedAt"]


def test_run_gate_fails_without_writing_when_showdown_missing(tmp_path: Path):
    """Wiring (b): empty Showdown previous → validate fail; out_path unchanged."""
    previous = {
        "meta": {
            "schema_version": 3,
            "regulation": "champions-reg-mc",
            "munchstats_generated_at": "2026-09-10T00:00:00+00:00",
            "sources": [SOURCE],
        },
        "ingame_doubles": {"species": _ingame_meeting_floor()},
        "showdown_vgc_mb": {"species": {}},
        "species": {},
    }
    out_path = tmp_path / "champions-reg-mc.v1.json"
    before = json.dumps(previous) + "\n"
    out_path.write_text(before, encoding="utf-8")

    index = {
        "generatedAt": "2026-09-21T00:00:00+00:00",
        "publishedAt": "2026-09-21T00:00:01+00:00",
        "capturedOn": "2026-09-21",
        "defaultSeason": "Current",
        "count": 230,
    }
    stats = {
        "join_n": 230,
        "detail_fetch_ok_n": 230,
        "detail_fetch_fail_n": 0,
        "index_count": 230,
    }

    def extract_fn(*, previous=None):
        snap = build_snapshot(_ingame_meeting_floor(), index, stats, previous=previous)
        return snap, index, stats

    result = run_gate(out_path=out_path, force=True, extract_fn=extract_fn)
    assert result["decision"] == "fail"
    assert "showdown" in (result.get("reason") or "")
    assert out_path.read_text(encoding="utf-8") == before


def test_main_loads_previous_before_extract(tmp_path: Path, monkeypatch):
    previous = _grafted_previous()
    out_path = tmp_path / "out.json"
    out_path.write_text(json.dumps(previous) + "\n", encoding="utf-8")
    order: list[str] = []
    seen_previous: dict[str, Any] = {}

    index = {
        "generatedAt": "2026-09-21T00:00:00+00:00",
        "publishedAt": "2026-09-21T00:00:01+00:00",
        "capturedOn": "2026-09-21",
        "defaultSeason": "Current",
        "count": 230,
    }
    stats = {
        "join_n": 230,
        "detail_fetch_ok_n": 230,
        "detail_fetch_fail_n": 0,
        "index_count": 230,
    }

    def fake_extract(*, previous=None, **_kwargs):
        order.append("extract")
        seen_previous["value"] = previous
        snap = build_snapshot(_ingame_meeting_floor(), index, stats, previous=previous)
        return snap, index, stats

    monkeypatch.setattr(
        "scripts.extract_usage.fetch_usage_mc_munchstats.extract",
        fake_extract,
    )
    rc = munchstats_main(["--out", str(out_path), "--dry-validate"])
    assert rc == 0
    assert order == ["extract"]
    assert seen_previous["value"] is not None
    assert (
        seen_previous["value"]["meta"]["showdown_format"] == EXPECTED_SHOWDOWN_FORMAT
    )
    assert (
        len(seen_previous["value"]["showdown_vgc_mb"]["species"])
        >= SHOWDOWN_SPECIES_FLOOR
    )
