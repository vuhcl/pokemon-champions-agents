"""Unit tests for usage_refresh_mc_gate cadence/validate (no live network)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from scripts.ci.usage_refresh_mc_gate import should_run_cadence
from scripts.extract_usage.fetch_usage_mc_munchstats import (
    build_snapshot,
    entry_from_champions_detail,
    lookup_id_for_species,
    validate_snapshot,
)

REG_START = datetime(2026, 9, 9, 2, 0, tzinfo=timezone.utc)


def test_cadence_early_window():
    now = datetime(2026, 9, 12, 15, 0, tzinfo=timezone.utc)
    run, reason = should_run_cadence(
        now=now,
        reg_start=REG_START,
        season_bookmark={"last_seen_page_id": 822},
        fetch_html_fn=lambda url: (_ for _ in ()).throw(RuntimeError("no fetch")),
    )
    assert run
    assert reason.startswith("early_window")


def test_cadence_before_start():
    now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    run, reason = should_run_cadence(
        now=now,
        reg_start=REG_START,
        season_bookmark={"last_seen_page_id": 822},
        fetch_html_fn=lambda url: "",
    )
    assert not run
    assert reason == "official_start_in_future"


def test_cadence_season_day_14():
    html = (
        Path(__file__).parent
        / "fixtures"
        / "champions_news_season_m6.html"
    ).read_text(encoding="utf-8")

    def fetch(url: str) -> str:
        return html

    # Season start Sep 9 → day 14 is Sep 23
    now = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
    run, reason = should_run_cadence(
        now=now,
        reg_start=REG_START,
        season_bookmark={"last_seen_page_id": 822},
        fetch_html_fn=fetch,
    )
    assert run
    assert "season_m6_day_14" in reason


def test_lookup_id_prefers_base_species_id():
    assert (
        lookup_id_for_species(
            "absolmegaz", {"base_species_id": "absol", "name": "Absol-Mega-Z"}
        )
        == "absol"
    )
    # Regional/gender: base_species_id present but must NOT collapse.
    assert (
        lookup_id_for_species(
            "raichualola", {"base_species_id": "raichu", "name": "Raichu-Alola"}
        )
        == "raichualola"
    )
    assert (
        lookup_id_for_species(
            "indeedeef", {"base_species_id": "indeedee", "name": "Indeedee-F"}
        )
        == "indeedeef"
    )
    assert lookup_id_for_species("charizardmegay", {}) == "charizard"


def test_entry_nature_by_rank():
    detail = {
        "rows": [
            {
                "category": "stat_points",
                "rank": 1,
                "hp_points": 32,
                "attack_points": 32,
                "defense_points": 0,
                "sp_atk_points": 0,
                "sp_def_points": 2,
                "speed_points": 0,
                "percentage_value": 10.8,
            },
            {
                "category": "stat_alignment",
                "rank": 1,
                "name": "Adamant",
                "percentage_value": 86.5,
            },
            {
                "category": "move",
                "name": "Grassy Glide",
                "percentage_value": 97.0,
            },
            {
                "category": "held_item",
                "name": "Assault Vest",
                "percentage_value": 40.0,
            },
            {
                "category": "ability",
                "name": "Grassy Surge",
                "percentage_value": 99.0,
            },
            {
                "category": "teammate",
                "name": "Incineroar",
                "percentage_value": 50.0,
            },
        ]
    }
    entry = entry_from_champions_detail(
        detail, showdown_id="rillaboom", display_name="Rillaboom", usage_rank=2
    )
    assert entry["top_spreads"][0]["nature"] == "Adamant"
    assert entry["common_moves"][0]["name"] == "Grassy Glide"
    assert entry["usage_rank"] == 2


def test_validate_noop_when_generated_at_unchanged():
    index = {
        "generatedAt": "2026-09-12T11:50:47.100047+00:00",
        "count": 260,
        "defaultSeason": "Current",
        "pokemon": [],
    }
    species = {
        f"s{i}": {
            "id": f"s{i}",
            "name": f"S{i}",
            "common_moves": [],
            "common_items": [],
            "common_abilities": [],
            "teammates": [],
            "top_spreads": [],
            "featured_sets": [],
            "source": "munchstats-champions-data",
        }
        for i in range(230)
    }
    stats = {"join_n": 230, "detail_fetch_ok_n": 230, "detail_fetch_fail_n": 0, "index_count": 260}
    snap = build_snapshot(species, index, stats)
    previous = {
        "meta": {"munchstats_generated_at": "2026-09-12T11:50:47.100047+00:00"},
        "ingame_doubles": {"species": species},
    }
    decision, reason = validate_snapshot(
        snap, index=index, stats=stats, previous=previous
    )
    assert decision == "noop"
    assert "not newer" in reason
