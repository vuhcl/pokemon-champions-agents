"""Live tuples are derived from registry + snapshot meta (ADR-014 2026-10-14b).

No network. A current regulation with a Showdown snapshot must have a live
tuple or a deliberately recorded deferral; a computed failure is not a deferral.
"""

from __future__ import annotations

import pytest

import recommender.usage_live as ul
from recommender.arm_teammates import arm_query_teammates
from recommender.regulation_registry import REGULATIONS, load_schedule
from recommender.usage_data import load_usage, showdown_species_map
from recommender.usage_live import (
    LiveDeferral,
    LiveTuple,
    _live_format_for,
    live_tuple_for,
)

COMPUTED_FAILURES = {"meta_month_invalid", "meta_rating_invalid", "format_mismatch"}


def live_tuple_guard_failures(tags: list[str]) -> list[str]:
    """One message per regulation that has a snapshot but neither tuple nor recorded deferral."""
    failures = []
    for tag in tags:
        if not ul.showdown_species_map(tag):
            continue  # no_showdown_snapshot is a valid computed reason
        result = live_tuple_for(tag)
        if isinstance(result, LiveTuple):
            continue
        if ul.RECORDED_DEFERRALS.get(tag) is result:
            continue
        failures.append(
            f"{tag}: has a Showdown snapshot but no live tuple and no recorded "
            f"deferral (computed reason: {result.reason})"
        )
    return failures


def _current_tags() -> list[str]:
    return [w.tag for w in load_schedule() if w.tag in REGULATIONS]


def _break_meta(monkeypatch, tag: str, **meta_overrides) -> None:
    real = load_usage(tag)
    broken = {**real, "meta": {**(real.get("meta") or {}), **meta_overrides}}
    monkeypatch.setattr(ul, "load_usage", lambda t: broken if t == tag else load_usage(t))


def test_current_regulations_with_snapshot_have_tuple_or_recorded_deferral():
    tags = _current_tags()
    assert "champions-reg-mc" in tags
    assert live_tuple_guard_failures(tags) == []


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"showdown_month": "not-a-month"}, "meta_month_invalid"),
        ({"showdown_month": None}, "meta_month_invalid"),
        ({"showdown_rating": "1500"}, "meta_rating_invalid"),
        ({"showdown_rating": None}, "meta_rating_invalid"),
        ({"showdown_format": "gen9championsvgc2026regmb"}, "format_mismatch"),
    ],
)
def test_guard_fails_naming_the_regulation_on_computed_failure(
    monkeypatch, overrides, reason
):
    _break_meta(monkeypatch, "champions-reg-mc", **overrides)
    result = live_tuple_for("champions-reg-mc")
    assert result == LiveDeferral("champions-reg-mc", reason, "computed")
    assert reason in COMPUTED_FAILURES
    assert _live_format_for("champions-reg-mc") is None
    failures = live_tuple_guard_failures(_current_tags())
    assert len(failures) == 1
    assert "champions-reg-mc" in failures[0] and reason in failures[0]


def test_recorded_deferral_passes_the_guard(monkeypatch):
    _break_meta(monkeypatch, "champions-reg-mc", showdown_month=None)
    recorded = LiveDeferral("champions-reg-mc", "awaiting_owner_decision", "test")
    monkeypatch.setitem(ul.RECORDED_DEFERRALS, "champions-reg-mc", recorded)
    assert live_tuple_for("champions-reg-mc") is recorded
    assert _live_format_for("champions-reg-mc") is None
    assert live_tuple_guard_failures(_current_tags()) == []


def test_no_snapshot_has_explicit_deferral_and_arm_reports_live_not_supported():
    assert not showdown_species_map("champions-reg-ma")
    result = live_tuple_for("champions-reg-ma")
    assert result == LiveDeferral("champions-reg-ma", "no_showdown_snapshot", "computed")
    assert _live_format_for("champions-reg-ma") is None

    def no_live(*_a):
        raise AssertionError("no fetch for a regulation without a live tuple")

    r = arm_query_teammates(
        "Rillaboom",
        source="showdown",
        regulation="champions-reg-ma",
        live_showdown_fetch=no_live,
    )
    assert r.status == "unavailable"
    assert r.attempts[0].reason == "live_not_supported"


def test_mb_tuple_keeps_format_and_rating_and_takes_month_from_snapshot():
    meta = load_usage("champions-reg-mb")["meta"]
    month, format_id, rating = _live_format_for("champions-reg-mb")
    assert (format_id, rating) == ("gen9championsvgc2026regmb", 1500)
    assert month == meta["showdown_month"]


def test_resolution_is_exact_tag():
    mb, mc = _live_format_for("champions-reg-mb"), _live_format_for("champions-reg-mc")
    assert mb and mc and mb != mc
    assert mc[1] == REGULATIONS["champions-reg-mc"]["showdown_format"]
    assert _live_format_for("champions") is None
    assert _live_format_for("not-a-regulation") is None
