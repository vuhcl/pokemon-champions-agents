"""RECOMMENDER_FIXED_NOW_UTC pins every date the arm tools read; unset behavior is unchanged."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from recommender import arm_teammates, clock, regulation_registry


def test_unset_returns_real_time(monkeypatch):
    monkeypatch.delenv(clock.ENV_FIXED_NOW, raising=False)
    before = datetime.now(timezone.utc)
    got = clock.utc_now()
    after = datetime.now(timezone.utc)
    assert before <= got <= after
    assert got.tzinfo is not None


@pytest.mark.parametrize("raw", ["2026-11-05T12:00:00Z", "2026-11-05T12:00:00+00:00", " 2026-11-05T12:00:00Z "])
def test_pinned_value(monkeypatch, raw):
    monkeypatch.setenv(clock.ENV_FIXED_NOW, raw)
    assert clock.utc_now() == datetime(2026, 11, 5, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("raw", ["yesterday", "2026-13-01T00:00:00Z", "2026-11-05T12:00:00", "2026-11-05T12:00:00+09:00"])
def test_malformed_value_raises(monkeypatch, raw):
    monkeypatch.setenv(clock.ENV_FIXED_NOW, raw)
    with pytest.raises(ValueError, match=clock.ENV_FIXED_NOW):
        clock.utc_now()


def test_arm_tool_age_uses_the_pinned_date(monkeypatch):
    monkeypatch.setenv(clock.ENV_FIXED_NOW, "2026-11-05T12:00:00Z")
    assert arm_teammates._utc_today().isoformat() == "2026-11-05"
    assert arm_teammates._age_days_from_iso("2026-10-31") == 5


def test_regulation_resolution_uses_the_pinned_date(monkeypatch):
    when = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setenv(clock.ENV_FIXED_NOW, "2026-10-22T12:00:00Z")
    assert regulation_registry.regulation_status() == regulation_registry.regulation_status(now=when)
