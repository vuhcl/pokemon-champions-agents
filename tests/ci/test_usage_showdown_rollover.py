"""B5 Showdown rollover: owed pairs, DROP_RATIO/day, overdue cap (no network)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from recommender.regulation_registry import REGULATIONS, ScheduleWindow
from scripts.ci import usage_showdown_rollover as rollover


MC = "champions-reg-mc"
MD = "champions-reg-md"
MC_FMT = REGULATIONS[MC]["showdown_format"]


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def _window(
    tag: str,
    start: str,
    end: str,
    letter: str | None = None,
) -> ScheduleWindow:
    return ScheduleWindow(
        tag=tag,
        letter=letter or tag[-1].upper(),
        start=_dt(start),
        end=_dt(end),
    )


# Production-shaped M-C window + hypothetical M-D abutting at exclusive end.
MC_WINDOW = _window(MC, "2026-09-09T02:00:00Z", "2026-12-02T01:59:00Z", "C")
MD_WINDOW = _window(MD, "2026-12-02T02:00:00Z", "2027-03-01T01:59:00Z", "D")
SCHEDULE_MC = [MC_WINDOW]
SCHEDULE_MC_MD = [MC_WINDOW, MD_WINDOW]


def _species(n: int = 3) -> dict[str, dict[str, Any]]:
    return {
        f"p{i}": {
            "id": f"p{i}",
            "name": f"P{i}",
            "usage_pct": 1.0,
            "common_moves": [],
            "common_items": [],
            "common_abilities": [],
            "teammates": [],
            "top_spreads": [],
            "featured_sets": [],
            "source": "smogon-chaos",
        }
        for i in range(n)
    }


def _doc(
    *,
    month: str = "2026-09",
    battles: int = 1_000_000,
    species: dict | None = None,
    format_id: str = MC_FMT,
    tag: str = MC,
) -> dict[str, Any]:
    return {
        "meta": {
            "schema_version": 4,
            "regulation": tag,
            "section": "showdown_doubles",
            "showdown_format": format_id,
            "showdown_month": month,
            "showdown_battles": battles,
            "sources": ["smogon-chaos"],
        },
        "showdown_doubles": {"species": species if species is not None else _species()},
    }


def _write_doc(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def _fetch_ok(battles: int = 1_100_000, n: int = 3):
    def _fetch(month: str, format_id: str, rating: int):
        return _species(n), {"number of battles": battles}

    return _fetch


def _fetch_unpublished(month: str, format_id: str, rating: int):
    raise RuntimeError(f"Smogon chaos fetch failed: {month}/{format_id}")


def _fetch_empty(month: str, format_id: str, rating: int):
    return {}, {"number of battles": 10}


# --- overlap / owed matrix -------------------------------------------------


def test_mc_owed_pairs_sep_through_dec_overlap_classes():
    now = _dt("2026-11-01T13:07:00Z")
    pairs = {
        p.month: p
        for p in rollover.list_owed_pairs(
            SCHEDULE_MC, now=now, usage_dir=Path("/nonexistent"), tags={MC}
        )
    }
    assert set(pairs) == {"2026-09", "2026-10", "2026-11", "2026-12"}
    assert pairs["2026-09"].overlap_class == "full"
    assert pairs["2026-10"].overlap_class == "full"
    assert pairs["2026-11"].overlap_class == "full"
    assert pairs["2026-12"].overlap_class == "short"
    assert pairs["2026-12"].overlap_days < 2.0


def test_hypothetical_md_nov_not_owed_dec_full(tmp_path: Path):
    """M-D starts Dec 2; November does not intersect; December is full for M-D."""
    # Register MD format for this test only.
    REGULATIONS[MD] = {
        "letter": "D",
        "mod": "championsregmd",
        "vgc_format_id": "[Gen 9 Champions] VGC 2026 Reg M-D",
        "bss_format_id": "[Gen 9 Champions] BSS Reg M-D",
        "showdown_format": "gen9championsvgc2026regmd",
    }
    try:
        now = _dt("2026-12-15T13:07:00Z")
        pairs = rollover.list_owed_pairs(
            SCHEDULE_MC_MD, now=now, usage_dir=tmp_path, tags={MD}
        )
        months = {p.month: p for p in pairs}
        assert "2026-11" not in months
        assert months["2026-12"].overlap_class == "full"
    finally:
        REGULATIONS.pop(MD, None)


def test_eligible_tags_exclude_mb_without_file(tmp_path: Path):
    now = _dt("2026-11-01T13:07:00Z")
    # Only M-C file present; M-B is on real schedule but must not be eligible.
    _write_doc(tmp_path / f"{MC}.showdown_doubles.v1.json", _doc())
    from recommender.regulation_registry import load_schedule

    tags = rollover.eligible_tags(load_schedule(), now=now, usage_dir=tmp_path)
    assert MC in tags
    assert "champions-reg-mb" not in tags


def test_november_on_disk_supersedes_october(tmp_path: Path):
    path = tmp_path / f"{MC}.showdown_doubles.v1.json"
    _write_doc(path, _doc(month="2026-11", battles=900_000))
    now = _dt("2026-12-10T13:07:00Z")
    pair_oct = next(
        p
        for p in rollover.list_owed_pairs(
            SCHEDULE_MC, now=now, usage_dir=tmp_path, tags={MC}
        )
        if p.month == "2026-10"
    )
    doc = rollover.load_showdown_doc(path)
    assert rollover.pair_satisfied(doc, pair_oct)
    assert rollover.overdue_status(pair_oct, now=now, satisfied=True) == "ok"


def test_disk_month_overlap_class_nov_full_dec_short():
    assert rollover.disk_month_overlap_class(MC, "2026-11", SCHEDULE_MC) == "full"
    assert rollover.disk_month_overlap_class(MC, "2026-12", SCHEDULE_MC) == "short"


def test_short_overlap_skipped_when_full_month_on_disk(tmp_path: Path):
    path = tmp_path / f"{MC}.showdown_doubles.v1.json"
    _write_doc(path, _doc(month="2026-11", battles=900_000))
    now = _dt("2027-01-05T13:07:00Z")
    code, results = rollover.run_rollover(
        now=now,
        schedule=SCHEDULE_MC,
        usage_dir=tmp_path,
        fetch_chaos=_fetch_ok(),
        dry_run=False,
        write=True,
    )
    actions = {r.pair.month: r.action for r in results if r.pair.tag == MC}
    assert actions.get("2026-12") == "skip_short_over_full"
    # File unchanged month.
    assert json.loads(path.read_text())["meta"]["showdown_month"] == "2026-11"
    assert code == 0  # short warn-only, no loud overdue for short


def test_short_overlap_allowed_on_first_fill(tmp_path: Path):
    """Empty/first-fill file: Dec short-overlap pair is fetched (not gated)."""
    # No file on disk → first fill. Exercise process_pair for Dec alone so a
    # prior full-month write in the same run cannot re-gate the short pair.
    now = _dt("2027-01-05T13:07:00Z")
    pair = next(
        p
        for p in rollover.list_owed_pairs(
            SCHEDULE_MC, now=now, usage_dir=tmp_path, tags={MC}
        )
        if p.month == "2026-12"
    )
    assert pair.overlap_class == "short"
    result = rollover.process_pair(
        pair,
        now=now,
        force=False,
        schedule=SCHEDULE_MC,
        usage_dir=tmp_path,
        fetch_chaos=_fetch_ok(battles=40_000),
        dry_run=False,
        write=True,
    )
    assert result.action == "wrote"
    assert (tmp_path / f"{MC}.showdown_doubles.v1.json").is_file()


# --- overdue boundaries + quiet skip ----------------------------------------


def _oct_full_pair() -> rollover.OwedPair:
    return rollover.OwedPair(
        tag=MC,
        month="2026-10",
        overlap_class="full",
        overlap_days=31.0,
        format_id=MC_FMT,
    )


def _dec_short_pair() -> rollover.OwedPair:
    return rollover.OwedPair(
        tag=MC,
        month="2026-12",
        overlap_class="short",
        overlap_days=1.1,
        format_id=MC_FMT,
    )


def test_overdue_status_day7_no_alarm():
    pair = _oct_full_pair()
    assert (
        rollover.overdue_status(pair, now=_dt("2026-11-07T13:07:00Z"), satisfied=False)
        is None
    )


def test_overdue_status_day8_loud():
    pair = _oct_full_pair()
    assert (
        rollover.overdue_status(pair, now=_dt("2026-11-08T13:07:00Z"), satisfied=False)
        == "loud"
    )


def test_overdue_status_day37_still_loud():
    pair = _oct_full_pair()
    assert (
        rollover.overdue_status(pair, now=_dt("2026-12-07T13:07:00Z"), satisfied=False)
        == "loud"
    )


def test_overdue_status_day38_capped_warn():
    pair = _oct_full_pair()
    assert (
        rollover.overdue_status(pair, now=_dt("2026-12-08T13:07:00Z"), satisfied=False)
        == "warn"
    )


def test_overdue_status_short_never_loud():
    pair = _dec_short_pair()
    for now in (
        _dt("2027-01-01T13:07:00Z"),
        _dt("2027-01-08T13:07:00Z"),
        _dt("2027-02-15T13:07:00Z"),
    ):
        assert rollover.overdue_status(pair, now=now, satisfied=False) is None


def test_run_rollover_overdue_loud_exits_1(tmp_path: Path):
    _write_doc(tmp_path / f"{MC}.showdown_doubles.v1.json", _doc(month="2026-09"))
    code, _ = rollover.run_rollover(
        now=_dt("2026-11-09T13:07:00Z"),
        schedule=SCHEDULE_MC,
        usage_dir=tmp_path,
        fetch_chaos=_fetch_unpublished,
        write=True,
    )
    assert code == 1


def test_run_rollover_overdue_capped_exits_0(tmp_path: Path):
    """Nov unsatisfied at day 38 → warn only; Oct already on disk (supersedes)."""
    _write_doc(tmp_path / f"{MC}.showdown_doubles.v1.json", _doc(month="2026-10"))
    logs: list[str] = []
    code, _ = rollover.run_rollover(
        now=_dt("2027-01-07T13:07:00Z"),  # day 38 after Nov
        schedule=SCHEDULE_MC,
        usage_dir=tmp_path,
        fetch_chaos=_fetch_unpublished,
        write=True,
        log=logs.append,
    )
    assert any("overdue(capped)" in m and "2026-11" in m for m in logs)
    assert code == 0


def test_quiet_skip_unpublished_day1_exit_0_file_unchanged(tmp_path: Path):
    path = tmp_path / f"{MC}.showdown_doubles.v1.json"
    before = _doc(month="2026-09")
    _write_doc(path, before)
    code, results = rollover.run_rollover(
        now=_dt("2026-11-01T13:07:00Z"),
        schedule=SCHEDULE_MC,
        usage_dir=tmp_path,
        fetch_chaos=_fetch_unpublished,
        write=True,
    )
    oct_r = next(r for r in results if r.pair.month == "2026-10")
    assert oct_r.action == "quiet_skip_unpublished"
    assert "RuntimeError:" in oct_r.detail
    assert "Smogon chaos fetch failed" in oct_r.detail
    assert code == 0
    assert json.loads(path.read_text())["meta"]["showdown_month"] == "2026-09"


def test_quiet_skip_unpublished_day9_still_exits_1(tmp_path: Path):
    _write_doc(tmp_path / f"{MC}.showdown_doubles.v1.json", _doc(month="2026-09"))
    code, results = rollover.run_rollover(
        now=_dt("2026-11-09T13:07:00Z"),
        schedule=SCHEDULE_MC,
        usage_dir=tmp_path,
        fetch_chaos=_fetch_unpublished,
        write=True,
    )
    assert any(
        r.action == "quiet_skip_unpublished" and r.pair.month == "2026-10"
        for r in results
    )
    assert code == 1


def test_quiet_skip_systemexit_and_oserror_include_type(tmp_path: Path):
    path = tmp_path / f"{MC}.showdown_doubles.v1.json"
    _write_doc(path, _doc(month="2026-09"))
    now = _dt("2026-11-01T13:07:00Z")
    pair = _oct_full_pair()

    def boom_exit(month: str, format_id: str, rating: int):
        raise SystemExit(f"Smogon chaos fetch failed: {month}/{format_id}")

    def boom_os(month: str, format_id: str, rating: int):
        raise OSError("proxy reset")

    r_exit = rollover.process_pair(
        pair,
        now=now,
        force=False,
        schedule=SCHEDULE_MC,
        usage_dir=tmp_path,
        fetch_chaos=boom_exit,
        dry_run=False,
        write=True,
    )
    r_os = rollover.process_pair(
        pair,
        now=now,
        force=False,
        schedule=SCHEDULE_MC,
        usage_dir=tmp_path,
        fetch_chaos=boom_os,
        dry_run=False,
        write=True,
    )
    assert r_exit.action == "quiet_skip_unpublished"
    assert r_exit.detail.startswith("SystemExit:")
    assert r_os.action == "quiet_skip_unpublished"
    assert r_os.detail.startswith("OSError:")
    assert "proxy reset" in r_os.detail


def test_drop_ratio_raw_fail_per_day_pass():
    """Shorter calendar month: raw battles ratio < 0.90 but per-day >= 0.90."""
    prior_days = rollover.overlap_days(MC_WINDOW, "2026-10")
    new_days = rollover.overlap_days(MC_WINDOW, "2026-11")
    prior_b = 3_100_000
    prior_bpd = prior_b / prior_days
    new_b = int(0.91 * prior_bpd * new_days)
    ok, raw, per_day = rollover.check_drop_ratio(
        new_battles=new_b,
        new_overlap_days=new_days,
        prior_battles=prior_b,
        prior_overlap_days=prior_days,
    )
    assert raw < 0.90
    assert per_day >= 0.90
    assert ok is True


def test_drop_ratio_accepts_write_when_per_day_ok(tmp_path: Path):
    prior_days = rollover.overlap_days(MC_WINDOW, "2026-10")
    new_days = rollover.overlap_days(MC_WINDOW, "2026-11")
    prior_b = 3_100_000
    new_b = int(0.91 * (prior_b / prior_days) * new_days)
    _write_doc(
        tmp_path / f"{MC}.showdown_doubles.v1.json",
        _doc(month="2026-10", battles=prior_b),
    )
    now = _dt("2026-12-01T13:07:00Z")
    code, results = rollover.run_rollover(
        now=now,
        schedule=SCHEDULE_MC,
        usage_dir=tmp_path,
        fetch_chaos=_fetch_ok(battles=new_b),
        write=True,
    )
    nov = next(r for r in results if r.pair.month == "2026-11")
    assert nov.action == "wrote"
    assert code == 0


def test_drop_ratio_raw_pass_per_day_fail():
    """Longer month: raw >= 0.90 but per-day < 0.90."""
    prior_days = 30.0
    new_days = 31.0
    prior_b = 3_000_000
    # raw = 0.92 (pass); per_day = 0.92 * 30/31 ≈ 0.890 (fail)
    new_b = int(prior_b * 0.92)
    ok, raw, per_day = rollover.check_drop_ratio(
        new_battles=new_b,
        new_overlap_days=new_days,
        prior_battles=prior_b,
        prior_overlap_days=prior_days,
    )
    assert raw >= 0.90
    assert per_day < 0.90
    assert ok is False


def test_wrong_format_hard_fail_even_under_force(tmp_path: Path):
    _write_doc(tmp_path / f"{MC}.showdown_doubles.v1.json", _doc(month="2026-09"))
    now = _dt("2026-11-02T13:07:00Z")
    bad = rollover.OwedPair(
        tag=MC,
        month="2026-10",
        overlap_class="full",
        overlap_days=31.0,
        format_id="gen9championsvgc2026regmcbo3",
    )
    result = rollover.process_pair(
        bad,
        now=now,
        force=True,
        schedule=SCHEDULE_MC,
        usage_dir=tmp_path,
        fetch_chaos=_fetch_ok(),
        dry_run=False,
        write=True,
    )
    assert result.action == "fail_integrity"


def test_already_grafted_noop(tmp_path: Path):
    showdown = _species()
    battles = 42
    doc = _doc(month="2026-10", battles=battles, species=showdown)
    _write_doc(tmp_path / f"{MC}.showdown_doubles.v1.json", doc)
    now = _dt("2026-11-02T13:07:00Z")
    pair = rollover.OwedPair(
        tag=MC,
        month="2026-10",
        overlap_class="full",
        overlap_days=31.0,
        format_id=MC_FMT,
    )

    def fetch(month: str, format_id: str, rating: int):
        return showdown, {"number of battles": battles}

    import unittest.mock as mock

    with mock.patch.object(rollover, "pair_satisfied", return_value=False):
        result = rollover.process_pair(
            pair,
            now=now,
            force=False,
            schedule=SCHEDULE_MC,
            usage_dir=tmp_path,
            fetch_chaos=fetch,
            dry_run=False,
            write=True,
        )
    assert result.action == "already_grafted"


def test_second_run_same_day_noop(tmp_path: Path):
    # Start from a full prior month so DROP_RATIO does not trip on Sep's short span.
    _write_doc(
        tmp_path / f"{MC}.showdown_doubles.v1.json",
        _doc(month="2026-09", battles=1_000_000),
    )
    now = _dt("2026-11-01T13:07:00Z")
    showdown = _species(5)
    # Generous battles so Oct clears per-day DROP_RATIO vs partial-Sep prior.
    battles = 5_000_000

    def fetch(month: str, format_id: str, rating: int):
        return showdown, {"number of battles": battles}

    code1, r1 = rollover.run_rollover(
        now=now,
        schedule=SCHEDULE_MC,
        usage_dir=tmp_path,
        fetch_chaos=fetch,
        write=True,
    )
    assert any(r.action == "wrote" and r.pair.month == "2026-10" for r in r1), [
        (r.pair.month, r.action, r.detail) for r in r1
    ]
    code2, r2 = rollover.run_rollover(
        now=now,
        schedule=SCHEDULE_MC,
        usage_dir=tmp_path,
        fetch_chaos=fetch,
        write=True,
    )
    assert any(r.action == "satisfied_noop" and r.pair.month == "2026-10" for r in r2)
    assert code1 == 0
    assert code2 == 0


def test_force_skips_drop_ratio_thin(tmp_path: Path):
    prior_b = 2_000_000
    _write_doc(
        tmp_path / f"{MC}.showdown_doubles.v1.json",
        _doc(month="2026-09", battles=prior_b),
    )
    now = _dt("2026-11-02T13:07:00Z")
    thin = int(prior_b * 0.5)
    code, results = rollover.run_rollover(
        now=now,
        force=True,
        schedule=SCHEDULE_MC,
        usage_dir=tmp_path,
        fetch_chaos=_fetch_ok(battles=thin),
        write=True,
    )
    assert any(r.action == "wrote" and r.pair.month == "2026-10" for r in results)
    assert code == 0


def test_empty_fetch_integrity_fail(tmp_path: Path):
    _write_doc(tmp_path / f"{MC}.showdown_doubles.v1.json", _doc(month="2026-09"))
    now = _dt("2026-11-02T13:07:00Z")
    code, results = rollover.run_rollover(
        now=now,
        schedule=SCHEDULE_MC,
        usage_dir=tmp_path,
        fetch_chaos=_fetch_empty,
        write=True,
    )
    assert any(r.action == "fail_integrity" for r in results)
    assert code == 1


def test_ingame_file_never_touched(tmp_path: Path):
    sd = tmp_path / f"{MC}.showdown_doubles.v1.json"
    ing = tmp_path / f"{MC}.ingame_doubles.v1.json"
    _write_doc(sd, _doc(month="2026-09"))
    ing.write_text('{"marker": true}\n', encoding="utf-8")
    before = ing.read_text()
    now = _dt("2026-11-01T13:07:00Z")
    rollover.run_rollover(
        now=now,
        schedule=SCHEDULE_MC,
        usage_dir=tmp_path,
        fetch_chaos=_fetch_ok(),
        write=True,
    )
    assert ing.read_text() == before


def test_workflow_yaml_present_and_pinned():
    from tests.ci.test_workflow_yaml_guards import _latest_runner_failures, _github_yamls

    path = Path(".github/workflows/usage-showdown-rollover.yml")
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert 'cron: "07 13 * * *"' in text
    assert "ubuntu-24.04" in text
    assert "usage-showdown-rollover" in text
    assert "*-latest" not in text
    failures = _latest_runner_failures(_github_yamls())
    assert not failures
