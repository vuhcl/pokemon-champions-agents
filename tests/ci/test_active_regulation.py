"""PR-B1: schedule + active_regulation + regulation_ready (no live network)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from recommender.format import resolve_format
from recommender.ids import regulation_file_tag
from recommender.regulation_registry import (
    SCHEDULE_PAST_END_NOT_READY,
    active_regulation,
    load_schedule,
    regulation_ready,
    regulation_status,
)
from recommender.session import DEFAULT_FORMAT_ID
from scripts.ci.validate_active_regulation_schedule import (
    validate_schedule_against_news,
)

FIXTURES = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).resolve().parents[2]


def _write_legality(tmp_path: Path, letter: str) -> Path:
    path = tmp_path / "champions.v1.json"
    path.write_text(
        json.dumps(
            {
                "meta": {
                    "formats": {
                        "vgc": f"[Gen 9 Champions] VGC 2026 Reg M-{letter}",
                        "bss": f"[Gen 9 Champions] BSS Reg M-{letter}",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_schedule(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "active_regulation.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "timezone": "UTC",
                "news_bookmark_page_id": 816,
                "regulations": rows,
            }
        ),
        encoding="utf-8",
    )
    return path


_MC_MB_ROWS = [
    {
        "tag": "champions-reg-mb",
        "letter": "B",
        "start": "2026-06-17T02:00:00Z",
        "end": "2026-09-09T01:59:00Z",
    },
    {
        "tag": "champions-reg-mc",
        "letter": "C",
        "start": "2026-09-09T02:00:00Z",
        "end": "2026-12-02T01:59:00Z",
    },
]


def test_committed_schedule_loads_mc_window():
    windows = load_schedule()
    assert [w.tag for w in windows] == ["champions-reg-mb", "champions-reg-mc"]
    mc = windows[-1]
    assert mc.letter == "C"
    assert mc.end == datetime(2026, 12, 2, 1, 59, tzinfo=timezone.utc)
    assert mc.exclusive_end == datetime(2026, 12, 2, 2, 0, tzinfo=timezone.utc)


def test_schedule_no_gap_no_overlap():
    """News end 01:59 is inclusive-minute → exclusive 02:00 abuts next start."""
    windows = load_schedule()
    for prev, nxt in zip(windows, windows[1:]):
        assert prev.exclusive_end == nxt.start, (
            f"gap/overlap between {prev.tag} and {nxt.tag}: "
            f"exclusive_end={prev.exclusive_end.isoformat()} "
            f"next_start={nxt.start.isoformat()}"
        )


def test_inclusive_minute_end_covers_0159(tmp_path: Path):
    """At published end minute, still inside window; at next start, past end."""
    schedule = _write_schedule(tmp_path, _MC_MB_ROWS)
    legality = _write_legality(tmp_path, "C")
    at_end_minute = datetime(2026, 12, 2, 1, 59, 30, tzinfo=timezone.utc)
    at_next_start = datetime(2026, 12, 2, 2, 0, 0, tzinfo=timezone.utc)
    inside = regulation_status(
        now=at_end_minute, schedule_path=schedule, legality_path=legality
    )
    past = regulation_status(
        now=at_next_start, schedule_path=schedule, legality_path=legality
    )
    assert inside.tag == "champions-reg-mc"
    assert inside.warnings == ()
    assert past.tag == "champions-reg-mc"
    assert SCHEDULE_PAST_END_NOT_READY in past.warnings


def test_regulation_ready_matches_legality_letter(tmp_path: Path):
    path = _write_legality(tmp_path, "C")
    assert regulation_ready("C", legality_path=path)
    assert not regulation_ready("D", legality_path=path)


def test_active_mid_window_when_ready(tmp_path: Path):
    schedule = _write_schedule(tmp_path, _MC_MB_ROWS)
    legality = _write_legality(tmp_path, "C")
    now = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
    status = regulation_status(
        now=now, schedule_path=schedule, legality_path=legality
    )
    assert status.tag == "champions-reg-mc"
    assert status.ready
    assert status.warnings == ()
    assert active_regulation(now=now, schedule_path=schedule, legality_path=legality) == (
        "champions-reg-mc"
    )


def test_past_end_not_ready_stays_previous_with_warning(tmp_path: Path):
    schedule = _write_schedule(tmp_path, _MC_MB_ROWS)
    legality = _write_legality(tmp_path, "C")  # M-D not extracted
    now = datetime(2026, 12, 2, 3, 0, tzinfo=timezone.utc)
    status = regulation_status(
        now=now, schedule_path=schedule, legality_path=legality
    )
    assert status.tag == "champions-reg-mc"
    assert SCHEDULE_PAST_END_NOT_READY in status.warnings


def test_window_not_ready_stays_on_previous(tmp_path: Path):
    schedule = _write_schedule(tmp_path, _MC_MB_ROWS)
    legality = _write_legality(tmp_path, "B")  # still on M-B legality
    now = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)  # inside M-C window
    status = regulation_status(
        now=now, schedule_path=schedule, legality_path=legality
    )
    assert status.tag == "champions-reg-mb"
    assert "regulation_not_ready" in status.warnings


def test_default_format_id_matches_active_when_ready(tmp_path: Path):
    schedule = _write_schedule(tmp_path, _MC_MB_ROWS)
    legality = _write_legality(tmp_path, "C")
    now = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
    status = regulation_status(
        now=now, schedule_path=schedule, legality_path=legality
    )
    assert status.ready
    product_tag = regulation_file_tag(
        resolve_format(DEFAULT_FORMAT_ID)["regulation_mod"]
    )
    assert product_tag == status.tag == active_regulation(
        now=now, schedule_path=schedule, legality_path=legality
    )


def test_validate_schedule_against_news_fixtures():
    html_by_id = {
        776: (FIXTURES / "champions_news_reg_mb.html").read_text(encoding="utf-8"),
        816: (FIXTURES / "champions_news_reg_mc.html").read_text(encoding="utf-8"),
    }

    def fetch(url: str) -> str:
        for page_id, html in html_by_id.items():
            if url.endswith(f"/{page_id}.html"):
                return html
        raise FileNotFoundError(url)

    # Bookmark 776 so scan finds M-B then M-C within window.
    warnings = validate_schedule_against_news(
        schedule_path=ROOT / "data" / "active_regulation.json",
        fetch=fetch,
        start_page_id=776,
        window=50,
    )
    assert warnings == []


def test_validate_schedule_mismatch_emits_warning(tmp_path: Path):
    bad = _write_schedule(
        tmp_path,
        [
            {
                "tag": "champions-reg-mc",
                "letter": "C",
                "start": "2026-09-09T02:00:00Z",
                "end": "2026-12-01T01:59:00Z",  # wrong end
            }
        ],
    )
    html = (FIXTURES / "champions_news_reg_mc.html").read_text(encoding="utf-8")

    def fetch(url: str) -> str:
        if url.endswith("/816.html"):
            return html
        raise FileNotFoundError(url)

    warnings = validate_schedule_against_news(
        schedule_path=bad, fetch=fetch, start_page_id=816, window=0
    )
    assert len(warnings) == 1
    assert "schedule_mismatch M-C" in warnings[0]
