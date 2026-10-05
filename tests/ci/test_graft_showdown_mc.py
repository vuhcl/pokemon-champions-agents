"""Unit tests for M-C Showdown graft (registry Bo1 guard + idempotence; no network)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts.extract_usage.fetch_usage_mb import showdown_teammates_descriptor
from scripts.extract_usage.fetch_usage_mc_munchstats import (
    EXPECTED_SHOWDOWN_FORMAT,
    SOURCE,
)
from scripts.extract_usage import graft_showdown_mc as graft_mod


def _species_row(sid: str, *, source: str = "smogon-chaos") -> dict[str, Any]:
    return {
        "id": sid,
        "name": sid.title(),
        "common_moves": [{"name": "Tackle"}],
        "common_items": [],
        "common_abilities": [],
        "teammates": [],
        "top_spreads": [],
        "featured_sets": [],
        "source": source,
        "usage_pct": 1.0,
    }


def _showdown(n: int = 3) -> dict[str, dict[str, Any]]:
    return {f"p{i}": _species_row(f"p{i}") for i in range(n)}


def _base(*, showdown: dict | None = None, meta_extra: dict | None = None) -> dict[str, Any]:
    meta = {
        "schema_version": 4,
        "regulation": "champions-reg-mc",
        "section": "showdown_doubles",
        "sources": ["smogon-chaos"],
    }
    if meta_extra:
        meta.update(meta_extra)
    return {
        "meta": meta,
        "showdown_doubles": {"species": showdown or {}},
    }


@pytest.mark.parametrize(
    "format_id",
    [
        "gen9championsvgc2026regmcbo3",
        "gen9championsou",
        "gen9championsuu",
        "gen9championsbssregmc",
        "gen9championsvgc2026regmb",
    ],
)
def test_graft_rejects_non_registry_bo1_format_ids(format_id: str):
    with pytest.raises(ValueError, match="registry Bo1 VGC|bo3"):
        graft_mod._assert_format_allowed(format_id)


def test_graft_allows_expected_format():
    graft_mod._assert_format_allowed(EXPECTED_SHOWDOWN_FORMAT)


def test_systemexit_becomes_runtimeerror():
    def boom(*_a, **_k):
        raise SystemExit("Smogon chaos fetch failed: http://x")

    with patch.object(graft_mod, "extract_showdown_chaos", side_effect=boom):
        with pytest.raises(RuntimeError, match="Smogon chaos fetch failed"):
            graft_mod._fetch_chaos("2026-09", EXPECTED_SHOWDOWN_FORMAT, 1500)


def test_graft_rejects_empty_showdown():
    with pytest.raises(ValueError, match="empty"):
        graft_mod.graft(
            showdown={},
            info={"number of battles": 1},
            month="2026-09",
            format_id=EXPECTED_SHOWDOWN_FORMAT,
            rating=1500,
        )


def test_graft_meta_uses_injected_clock():
    clock = "2026-10-04T01:55:00Z"
    showdown = _showdown()
    out = graft_mod.graft(
        showdown=showdown,
        info={"number of battles": 100},
        month="2026-09",
        format_id=EXPECTED_SHOWDOWN_FORMAT,
        rating=1500,
        extracted_at=clock,
    )
    meta = out["meta"]
    assert meta["showdown_extracted_at"] == clock
    assert meta["showdown_teammates_extracted_at"] == clock
    assert meta["showdown_teammates"] == showdown_teammates_descriptor()
    assert meta["schema_version"] == 4
    assert set(out) == {"meta", "showdown_doubles"}


def test_idempotent_main_skips_write(tmp_path: Path):
    showdown = _showdown()
    battles = 42
    base = _base(
        showdown=showdown,
        meta_extra={
            "showdown_format": EXPECTED_SHOWDOWN_FORMAT,
            "showdown_month": "2026-09",
            "showdown_battles": battles,
            "showdown_rating": 1500,
            "showdown_source": "smogon-chaos",
        },
    )
    out = tmp_path / "mc.showdown_doubles.v1.json"
    out.write_text(json.dumps(base) + "\n", encoding="utf-8")
    before = out.read_text(encoding="utf-8")

    with patch.object(
        graft_mod,
        "extract_showdown_chaos",
        return_value=(showdown, {"number of battles": battles}),
    ):
        rc = graft_mod.main(["--month", "2026-09", "--out", str(out)])
    assert rc == 0
    assert out.read_text(encoding="utf-8") == before


def test_force_rewrites_when_idempotent_key_matches(tmp_path: Path):
    showdown = _showdown()
    battles = 42
    base = _base(
        showdown=showdown,
        meta_extra={
            "showdown_format": EXPECTED_SHOWDOWN_FORMAT,
            "showdown_month": "2026-09",
            "showdown_battles": battles,
            "showdown_rating": 1500,
            "showdown_source": "smogon-chaos",
            "showdown_extracted_at": "2026-09-23T19:09:09Z",
        },
    )
    out = tmp_path / "mc.showdown_doubles.v1.json"
    out.write_text(json.dumps(base) + "\n", encoding="utf-8")
    before = out.read_text(encoding="utf-8")

    with patch.object(
        graft_mod,
        "extract_showdown_chaos",
        return_value=(showdown, {"number of battles": battles}),
    ), patch.object(graft_mod, "_utc_now_z", return_value="2026-10-04T02:00:00Z"):
        rc = graft_mod.main(["--month", "2026-09", "--out", str(out), "--force"])
    assert rc == 0
    after = out.read_text(encoding="utf-8")
    assert after != before
    meta = json.loads(after)["meta"]
    assert meta["showdown_extracted_at"] == "2026-10-04T02:00:00Z"


def test_nov1_manual_command_2026_10_force(tmp_path: Path):
    """Exact Nov-1 runbook: --month 2026-10 --force (tmp fixtures, no network)."""
    showdown = _showdown(5)
    out = tmp_path / "champions-reg-mc.showdown_doubles.v1.json"
    with patch.object(
        graft_mod,
        "extract_showdown_chaos",
        return_value=(showdown, {"number of battles": 999}),
    ), patch.object(graft_mod, "_utc_now_z", return_value="2026-11-01T12:00:00Z"):
        rc = graft_mod.main(
            ["--month", "2026-10", "--force", "--out", str(out)]
        )
    assert rc == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["meta"]["showdown_month"] == "2026-10"
    assert written["meta"]["showdown_format"] == EXPECTED_SHOWDOWN_FORMAT
    assert len(written["showdown_doubles"]["species"]) == 5


def test_main_rejects_unlisted_via_cli(tmp_path: Path):
    out = tmp_path / "mc.json"
    out.write_text(json.dumps(_base()) + "\n", encoding="utf-8")
    rc = graft_mod.main(
        ["--month", "2026-09", "--format", "gen9championsou", "--out", str(out)]
    )
    assert rc == 2


def test_main_rejects_bo3_via_cli(tmp_path: Path):
    out = tmp_path / "mc.json"
    out.write_text(json.dumps(_base()) + "\n", encoding="utf-8")
    rc = graft_mod.main(
        [
            "--month",
            "2026-09",
            "--format",
            "gen9championsvgc2026regmcbo3",
            "--out",
            str(out),
        ]
    )
    assert rc == 2
