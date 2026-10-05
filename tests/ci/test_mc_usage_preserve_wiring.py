"""Ingame-only writer wiring after B3a (no Showdown preserve-on-write)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.ci.usage_refresh_mc_gate import run_gate
from scripts.extract_usage.fetch_usage_mc_munchstats import (
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


def test_build_snapshot_is_ingame_only_no_showdown_preserve():
    ingame = _ingame_meeting_floor(5)
    previous = {
        "meta": {
            "schema_version": 4,
            "regulation": "champions-reg-mc",
            "munchstats_generated_at": "2026-09-10T00:00:00+00:00",
            "showdown_format": "gen9championsvgc2026regmc",
            "showdown_month": "2026-09",
        },
        "ingame_doubles": {"species": ingame},
        "showdown_doubles": {"species": {"salamence": _species_row("salamence")}},
    }
    index = {
        "generatedAt": "2026-09-20T12:00:00+00:00",
        "publishedAt": "2026-09-20T12:00:01+00:00",
        "capturedOn": "2026-09-20",
        "defaultSeason": "Current",
        "count": 5,
    }
    stats = {"join_n": 5, "detail_fetch_ok_n": 5, "detail_fetch_fail_n": 0, "index_count": 5}
    snap = build_snapshot(ingame, index, stats, previous=previous)
    assert set(snap) == {"meta", "ingame_doubles"}
    assert "showdown_doubles" not in snap
    assert "showdown_vgc_mb" not in snap
    assert "showdown_format" not in snap["meta"]
    assert snap["meta"]["schema_version"] == 4
    assert snap["meta"]["munchstats_generated_at"] == index["generatedAt"]


def test_run_gate_commits_ingame_without_showdown(tmp_path: Path):
    previous = {
        "meta": {
            "schema_version": 4,
            "regulation": "champions-reg-mc",
            "munchstats_generated_at": "2026-09-10T00:00:00+00:00",
            "sources": [SOURCE],
        },
        "ingame_doubles": {"species": _ingame_meeting_floor()},
    }
    out_path = tmp_path / "champions-reg-mc.ingame_doubles.v1.json"
    out_path.write_text(json.dumps(previous) + "\n", encoding="utf-8")

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
        snap = build_snapshot(new_ingame, index, stats, previous=previous)
        return snap, index, stats

    result = run_gate(out_path=out_path, force=True, extract_fn=extract_fn)
    assert result["decision"] == "commit"
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert set(written) == {"meta", "ingame_doubles"}
    assert len(written["ingame_doubles"]["species"]) == 230
    assert written["meta"]["munchstats_generated_at"] == index["generatedAt"]


def test_main_loads_previous_before_extract(tmp_path: Path, monkeypatch):
    previous = {
        "meta": {
            "schema_version": 4,
            "regulation": "champions-reg-mc",
            "munchstats_generated_at": "2026-09-10T00:00:00+00:00",
            "sources": [SOURCE],
        },
        "ingame_doubles": {"species": _ingame_meeting_floor()},
    }
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
