"""Unit tests for vgcpastes refresh gate + validation floors."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.ci.build_vgcpastes_refresh_pr_body import build_body
from scripts.ci.vgcpastes_refresh_gate import run_gate, should_run_extract
from scripts.extract_usage.fetch_vgcpastes_builds import validate_vgcpastes_snapshot


def _snap(
    *,
    n: int = 120,
    sheet_rows: int | None = None,
    ok_6: int | None = None,
    members_total: int = 720,
    with_ev: int = 600,
    team_ids: list[str] | None = None,
) -> dict:
    sheet_rows = sheet_rows if sheet_rows is not None else n
    ok_6 = ok_6 if ok_6 is not None else n
    ids = team_ids or [f"T{i}" for i in range(n)]
    return {
        "meta": {
            "schema_version": 1,
            "sheet_rows": sheet_rows,
            "teams_resolved": n,
            "resolve_counts": {"ok_6": ok_6},
            "ev_completeness": {
                "members_with_nonzero_evs": with_ev,
                "members_total": members_total,
                "teams_all_members_have_evs": n - 10,
                "teams_all_members_zero_evs": 5,
                "teams_partial_evs": 5,
            },
            "extracted_at": "2026-09-20T00:00:00Z",
            "population_evidence": {"sheet_title": "Champions M-C"},
        },
        "teams": [{"team_id": tid, "members": []} for tid in ids],
    }


def test_validate_abs_floor():
    d, reason = validate_vgcpastes_snapshot(_snap(n=50))
    assert d == "fail"
    assert "abs_floor" in reason


def test_validate_drop_ratio():
    prev = _snap(n=200)
    new = _snap(n=150)
    d, reason = validate_vgcpastes_snapshot(new, previous=prev)
    assert d == "fail"
    assert "drop_ratio" in reason or "drop_abs" in reason


def test_validate_first_file_skips_drop():
    d, reason = validate_vgcpastes_snapshot(_snap(n=120), previous=None)
    assert d == "ok"
    assert reason.startswith("validated_n_")


def test_validate_noop_unchanged():
    snap = _snap(n=120, team_ids=[f"T{i}" for i in range(120)])
    d, reason = validate_vgcpastes_snapshot(snap, previous=snap)
    assert d == "noop"
    assert reason == "teams_unchanged"


def test_validate_resolve_ratio():
    d, reason = validate_vgcpastes_snapshot(
        _snap(n=120, sheet_rows=200, ok_6=100)
    )
    assert d == "fail"
    assert "resolve_ok_ratio" in reason


def test_spacing_blocks():
    now = datetime(2026, 9, 15, tzinfo=timezone.utc)
    run, reason = should_run_extract(
        now=now,
        marker={"last_extract_at": "2026-09-10T00:00:00Z"},
        force=False,
    )
    assert not run
    assert reason.startswith("spacing_")


def test_spacing_force():
    now = datetime(2026, 9, 15, tzinfo=timezone.utc)
    run, reason = should_run_extract(
        now=now,
        marker={"last_extract_at": "2026-09-14T00:00:00Z"},
        force=True,
    )
    assert run and reason == "force"


def test_run_gate_pr(tmp_path: Path):
    out = tmp_path / "out.json"
    marker = tmp_path / "marker.json"
    marker.write_text(json.dumps({"last_extract_at": None}) + "\n", encoding="utf-8")

    def extract_fn(**kwargs):
        snap = _snap(n=120)
        path = kwargs["out_path"]
        path.write_text(json.dumps(snap) + "\n", encoding="utf-8")
        return snap

    result = run_gate(
        now=datetime(2026, 9, 20, tzinfo=timezone.utc),
        force=True,
        marker_path=marker,
        out_path=out,
        extract_fn=extract_fn,
    )
    assert result["decision"] == "pr"
    assert result["bump_marker"] is True
    bumped = json.loads(marker.read_text(encoding="utf-8"))
    assert bumped["last_outcome"] == "pr_opened"
    assert bumped["teams_resolved"] == 120


def test_run_gate_fail_restores_previous(tmp_path: Path):
    out = tmp_path / "out.json"
    prev = _snap(n=200)
    out.write_text(json.dumps(prev) + "\n", encoding="utf-8")
    marker = tmp_path / "marker.json"
    marker.write_text(json.dumps({"last_extract_at": None}) + "\n", encoding="utf-8")

    def extract_fn(**kwargs):
        # Bad extract: too few teams
        snap = _snap(n=50)
        kwargs["out_path"].write_text(json.dumps(snap) + "\n", encoding="utf-8")
        return snap

    result = run_gate(
        now=datetime(2026, 9, 20, tzinfo=timezone.utc),
        force=True,
        marker_path=marker,
        out_path=out,
        extract_fn=extract_fn,
    )
    assert result["decision"] == "fail"
    restored = json.loads(out.read_text(encoding="utf-8"))
    assert restored["meta"]["teams_resolved"] == 200


def test_pr_body_fields():
    body = build_body(
        {
            "sheet_title": "Champions M-C",
            "sheet_gid": "736919171",
            "out_path": "data/team-composition/champions-reg-mc.vgcpastes-builds.v1.json",
            "extracted_at": "2026-09-20T00:00:00Z",
            "decision": "pr",
            "reason": "validated_n_120",
            "teams_resolved": 120,
            "prev_teams_resolved": 100,
            "resolve_counts": {"ok_6": 120},
            "ev_completeness": {
                "teams_all_members_have_evs": 100,
                "teams_all_members_zero_evs": 10,
                "teams_partial_evs": 10,
                "members_with_nonzero_evs": 600,
                "members_total": 720,
            },
        }
    )
    assert "736919171" in body
    assert "teams_resolved" in body
    assert "Delta: **20**" in body
    assert "Do **not** auto-merge" in body
