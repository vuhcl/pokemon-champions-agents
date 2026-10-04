"""Unit tests for M-C Showdown graft (allowlist + idempotence; no network)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts.extract_usage.fetch_usage_mc_munchstats import (
    EXPECTED_SHOWDOWN_FORMAT,
    SHOWDOWN_BATTLES_FLOOR,
    SHOWDOWN_SPECIES_FLOOR,
    SOURCE,
)
from scripts.extract_usage import graft_showdown_mc as graft_mod


def _base(*, showdown: dict | None = None, meta_extra: dict | None = None) -> dict[str, Any]:
    meta = {
        "schema_version": 3,
        "regulation": "champions-reg-mc",
        "munchstats_generated_at": "2026-09-10T00:00:00+00:00",
        "sources": [SOURCE],
    }
    if meta_extra:
        meta.update(meta_extra)
    return {
        "meta": meta,
        "ingame_doubles": {
            "species": {
                "rillaboom": {
                    "id": "rillaboom",
                    "name": "Rillaboom",
                    "common_moves": [],
                    "common_items": [],
                    "common_abilities": [],
                    "teammates": [],
                    "top_spreads": [],
                    "featured_sets": [],
                    "source": SOURCE,
                }
            }
        },
        "showdown_vgc_mb": {"species": showdown or {}},
        "species": {},
    }


@pytest.mark.parametrize(
    "format_id",
    [
        "gen9championsvgc2026regmcbo3",
        "gen9championsou",
        "gen9championsuu",
        "gen9championsbssregmc",
    ],
)
def test_graft_rejects_unlisted_format_ids(format_id: str):
    with pytest.raises(ValueError, match="not in SHOWDOWN_FORMAT_ALLOWLIST"):
        graft_mod._assert_format_allowed(format_id)


def test_graft_allows_expected_format():
    graft_mod._assert_format_allowed(EXPECTED_SHOWDOWN_FORMAT)


def test_systemexit_becomes_runtimeerror():
    def boom(*_a, **_k):
        raise SystemExit("Smogon chaos fetch failed: http://x")

    with patch.object(graft_mod, "extract_showdown_chaos", side_effect=boom):
        with pytest.raises(RuntimeError, match="Smogon chaos fetch failed"):
            graft_mod._fetch_chaos("2026-09", EXPECTED_SHOWDOWN_FORMAT, 1500)


def test_idempotent_main_skips_write(tmp_path: Path):
    n = SHOWDOWN_SPECIES_FLOOR
    showdown = {
        f"p{i}": {
            "id": f"p{i}",
            "name": f"P{i}",
            "common_moves": [{"name": "Tackle"}],
            "common_items": [],
            "common_abilities": [],
            "teammates": [],
            "top_spreads": [],
            "featured_sets": [],
            "source": "smogon-chaos",
            "usage_pct": 1.0,
        }
        for i in range(n)
    }
    battles = SHOWDOWN_BATTLES_FLOOR
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
    out = tmp_path / "mc.json"
    out.write_text(json.dumps(base) + "\n", encoding="utf-8")
    before = out.read_text(encoding="utf-8")

    with patch.object(
        graft_mod,
        "extract_showdown_chaos",
        return_value=(showdown, {"number of battles": battles}),
    ):
        rc = graft_mod.main(
            ["--month", "2026-09", "--out", str(out)]
        )
    assert rc == 0
    assert out.read_text(encoding="utf-8") == before


def test_main_rejects_unlisted_via_cli(tmp_path: Path):
    out = tmp_path / "mc.json"
    out.write_text(json.dumps(_base()) + "\n", encoding="utf-8")
    rc = graft_mod.main(
        ["--month", "2026-09", "--format", "gen9championsou", "--out", str(out)]
    )
    assert rc == 2
