"""Unit tests for compendium_refresh_gate (no live construct/calc)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.ci.build_compendium_refresh_pr_body import build_body
from scripts.ci.compendium_refresh_gate import (
    COMPENDIUM_CATEGORIES,
    category_semantic_diff,
    run_gate,
    should_run_check,
)
from recommender.role_compendium import RoleConstructionDraft


def test_registry_has_eighteen():
    assert len(COMPENDIUM_CATEGORIES) == 18


def test_should_run_force_skips_both():
    now = datetime(2026, 9, 20, tzinfo=timezone.utc)
    marker = {
        "last_check_at": "2026-09-19T00:00:00Z",
        "usage_munchstats_generated_at": "2026-09-20T00:00:00+00:00",
    }
    run, reason = should_run_check(
        now=now,
        marker=marker,
        usage_gen="2026-09-20T00:00:00+00:00",
        force=True,
    )
    assert run and reason == "force"


def test_should_run_usage_not_newer():
    now = datetime(2026, 9, 30, tzinfo=timezone.utc)
    marker = {
        "last_check_at": "2026-09-01T00:00:00Z",
        "usage_munchstats_generated_at": "2026-09-12T11:50:47.100047+00:00",
    }
    run, reason = should_run_check(
        now=now,
        marker=marker,
        usage_gen="2026-09-12T11:50:47.100047+00:00",
        force=False,
    )
    assert not run
    assert reason == "usage_not_newer_than_last_clear_check"


def test_should_run_spacing_blocks():
    now = datetime(2026, 9, 15, tzinfo=timezone.utc)
    marker = {
        "last_check_at": "2026-09-10T00:00:00Z",
        "usage_munchstats_generated_at": "2026-09-01T00:00:00+00:00",
    }
    run, reason = should_run_check(
        now=now,
        marker=marker,
        usage_gen="2026-09-14T00:00:00+00:00",
        force=False,
    )
    assert not run
    assert reason.startswith("spacing_")


def test_should_run_bootstrap_epoch():
    now = datetime(2026, 9, 15, tzinfo=timezone.utc)
    run, reason = should_run_check(
        now=now,
        marker={"last_check_at": None, "usage_munchstats_generated_at": None},
        usage_gen="2026-09-12T11:50:47.100047+00:00",
        force=False,
    )
    assert run and reason == "usage_newer_and_spacing_ok"


def test_semantic_diff_ignores_built_at_only_change():
    prior = {
        "tiers": {"Excellent": ["Pelipper"], "Good": [], "Acceptable": []},
        "built_at": "2026-01-01T00:00:00+00:00",
    }
    draft = RoleConstructionDraft(
        category="weather_setter",
        sub_criteria={"condition": "Rain"},
        candidates=[],
        considered_rejected=[],
        tiers={"Excellent": ["Pelipper"], "Good": [], "Acceptable": []},
        notes=[],
    )
    diff = category_semantic_diff(prior, draft)
    assert diff["has_diff"] is False


def test_semantic_diff_tier_move():
    prior = {
        "tiers": {
            "Excellent": ["Seed Sower"],
            "Good": [],
            "Acceptable": [],
        }
    }
    draft = RoleConstructionDraft(
        category="terrain_setter",
        sub_criteria={"condition": "Grassy"},
        candidates=[],
        considered_rejected=[],
        tiers={"Excellent": [], "Good": ["Seed Sower"], "Acceptable": []},
        notes=[],
    )
    diff = category_semantic_diff(prior, draft)
    assert diff["has_diff"] is True
    assert diff["tier_changed"][0]["species"] == "Seed Sower"
    assert diff["tier_changed"][0]["disk"] == "Excellent"
    assert diff["tier_changed"][0]["live"] == "Good"


def test_run_gate_fail_does_not_advance_fingerprint(tmp_path: Path):
    usage = tmp_path / "usage.json"
    usage.write_text(
        json.dumps(
            {
                "meta": {
                    "munchstats_generated_at": "2026-09-20T00:00:00+00:00",
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    marker = tmp_path / "marker.json"
    marker.write_text(
        json.dumps(
            {
                "last_check_at": "2026-09-01T00:00:00Z",
                "usage_munchstats_generated_at": "2026-09-01T00:00:00+00:00",
                "last_outcome": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    def rebuild_fn(**_kwargs):
        return {
            "status": "needs_revision",
            "has_semantic_diff": True,
            "categories": {
                "weather_setter_rain": {
                    "critic_flag_count": 1,
                    "critic_flags": [
                        {
                            "principle": "tied_cluster",
                            "candidates": ["A", "B"],
                            "detail": "x",
                        }
                    ],
                    "diff": {"has_diff": True},
                }
            },
        }

    result = run_gate(
        now=datetime(2026, 9, 20, tzinfo=timezone.utc),
        force=True,
        marker_path=marker,
        usage_path=usage,
        roles_dir=tmp_path / "roles",
        rebuild_fn=rebuild_fn,
    )
    assert result["decision"] == "fail"
    assert result["bump_marker"] is True
    bumped = json.loads(marker.read_text(encoding="utf-8"))
    assert bumped["last_outcome"] == "fail_flags"
    assert bumped["usage_munchstats_generated_at"] == "2026-09-01T00:00:00+00:00"
    assert bumped["last_check_at"] is not None


def test_run_gate_pr_advances_fingerprint(tmp_path: Path):
    usage = tmp_path / "usage.json"
    usage.write_text(
        json.dumps({"meta": {"munchstats_generated_at": "2026-09-20T00:00:00+00:00"}})
        + "\n",
        encoding="utf-8",
    )
    marker = tmp_path / "marker.json"
    marker.write_text(
        json.dumps(
            {
                "last_check_at": None,
                "usage_munchstats_generated_at": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    def rebuild_fn(**_kwargs):
        return {
            "status": "approved",
            "has_semantic_diff": True,
            "categories": {
                "x": {
                    "diff": {
                        "has_diff": True,
                        "admitted_new": [{"species": "A", "tier": "Good"}],
                        "dropped": [],
                        "tier_changed": [
                            {
                                "species": "Seed Sower",
                                "disk": "Excellent",
                                "live": "Good",
                            }
                        ],
                        "disk_admitted": 1,
                        "live_admitted": 2,
                    },
                    "critic_approved": True,
                    "critic_flag_count": 0,
                    "critic_flags": [],
                    "rejected": 0,
                }
            },
        }

    result = run_gate(
        now=datetime(2026, 9, 20, tzinfo=timezone.utc),
        force=True,
        marker_path=marker,
        usage_path=usage,
        roles_dir=tmp_path / "roles",
        rebuild_fn=rebuild_fn,
    )
    assert result["decision"] == "pr"
    bumped = json.loads(marker.read_text(encoding="utf-8"))
    assert bumped["usage_munchstats_generated_at"] == "2026-09-20T00:00:00+00:00"
    assert bumped["last_outcome"] == "pr_opened"


def test_pr_body_lists_tier_moves():
    report = {
        "usage_path": "data/usage/champions-reg-mc.v1.json",
        "usage_munchstats_generated_at": "2026-09-12T11:50:47+00:00",
        "checked_at_utc": "2026-09-20T00:00:00Z",
        "status": "approved",
        "categories": {
            "terrain_setter_grassy": {
                "rejected": 0,
                "diff": {
                    "disk_admitted": 5,
                    "live_admitted": 5,
                    "admitted_new": [],
                    "dropped": [],
                    "tier_changed": [
                        {
                            "species": "Seed Sower",
                            "disk": "Excellent",
                            "live": "Good",
                        }
                    ],
                },
                "critic_approved": True,
                "critic_flag_count": 0,
                "critic_flags": [],
            }
        },
    }
    body = build_body(report)
    assert "Seed Sower" in body
    assert "Excellent -> Good" in body
    assert "Do **not** auto-merge" in body
