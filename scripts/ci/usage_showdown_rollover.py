"""Daily Showdown chaos rollover into ``{tag}.showdown_doubles.v1.json``.

Schedule-enumerated owed pairs (not ``active_regulation()``). Integrity +
per-overlap-day DROP_RATIO for full-overlap non-first-fill. Ingame file never
touched.

Overdue alarm: loud from day 8 through day 37 of the month after the target
(30 days past the historical poll window ending day 7); from day 38 onwards
downgrades to a logged warning so a permanently missing ladder does not fail
CI forever.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from recommender.regulation_registry import (
    REGULATIONS,
    ScheduleWindow,
    load_schedule,
)
from scripts.extract_usage.graft_showdown_mc import (
    already_grafted,
    graft,
    _fetch_chaos,
)

ROOT = Path(__file__).resolve().parents[2]
USAGE_DIR = ROOT / "data" / "usage"
SHOWDOWN_SUFFIX = ".showdown_doubles.v1.json"

DROP_RATIO = 0.90
SHORT_OVERLAP = timedelta(hours=48)
OVERDUE_FROM_DAY = 8
# Poll window historically ended day 7; loud alarm for 30 days past that (= through day 37).
OVERDUE_LOUD_THROUGH_DAY = 7 + 30
DEFAULT_RATING = 1500

OverlapClass = Literal["short", "full"]
FetchChaos = Callable[[str, str, int], tuple[dict[str, dict], dict]]


@dataclass(frozen=True)
class OwedPair:
    tag: str
    month: str
    overlap_class: OverlapClass
    overlap_days: float
    format_id: str


@dataclass(frozen=True)
class PairResult:
    pair: OwedPair
    action: str
    detail: str = ""


def showdown_path(tag: str, usage_dir: Path = USAGE_DIR) -> Path:
    return usage_dir / f"{tag}{SHOWDOWN_SUFFIX}"


def month_start(yyyy_mm: str) -> datetime:
    y, m = (int(p) for p in yyyy_mm.split("-"))
    return datetime(y, m, 1, tzinfo=timezone.utc)


def month_end_exclusive(yyyy_mm: str) -> datetime:
    y, m = (int(p) for p in yyyy_mm.split("-"))
    if m == 12:
        return datetime(y + 1, 1, 1, tzinfo=timezone.utc)
    return datetime(y, m + 1, 1, tzinfo=timezone.utc)


def following_month_first(yyyy_mm: str) -> date:
    return month_end_exclusive(yyyy_mm).date()


def days_past_month_end(month: str, now: datetime) -> int:
    """1 on the 1st of the month after ``month``; negative while ``month`` is current."""
    return (now.date() - following_month_first(month)).days + 1


def month_has_ended(month: str, now: datetime) -> bool:
    return days_past_month_end(month, now) >= 1


def iter_yyyy_mm(start: datetime, end_exclusive: datetime) -> list[str]:
    """Calendar months that intersect ``[start, end_exclusive)``."""
    if end_exclusive <= start:
        return []
    cur = date(start.year, start.month, 1)
    last = (end_exclusive - timedelta(microseconds=1)).date()
    last_month = date(last.year, last.month, 1)
    out: list[str] = []
    while cur <= last_month:
        out.append(f"{cur.year:04d}-{cur.month:02d}")
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return out


def schedule_month_intersection(
    window: ScheduleWindow, yyyy_mm: str
) -> timedelta | None:
    """Intersection of schedule half-open window with calendar month half-open span."""
    m0 = month_start(yyyy_mm)
    m1 = month_end_exclusive(yyyy_mm)
    lo = max(window.start, m0)
    hi = min(window.exclusive_end, m1)
    if hi <= lo:
        return None
    return hi - lo


def overlap_days(window: ScheduleWindow, yyyy_mm: str) -> float:
    span = schedule_month_intersection(window, yyyy_mm)
    if span is None or span.total_seconds() <= 0:
        return 0.0
    return max(span.total_seconds() / 86400.0, 1e-9)


def overlap_class(window: ScheduleWindow, yyyy_mm: str) -> OverlapClass | None:
    span = schedule_month_intersection(window, yyyy_mm)
    if span is None or span.total_seconds() <= 0:
        return None
    return "short" if span < SHORT_OVERLAP else "full"


def window_for_tag(
    schedule: list[ScheduleWindow], tag: str
) -> ScheduleWindow | None:
    for w in schedule:
        if w.tag == tag:
            return w
    return None


def eligible_tags(
    schedule: list[ScheduleWindow],
    *,
    now: datetime,
    usage_dir: Path = USAGE_DIR,
) -> set[str]:
    """Current schedule window ∪ tags with an existing showdown file."""
    tags: set[str] = set()
    for w in schedule:
        if w.start <= now < w.exclusive_end:
            tags.add(w.tag)
    for path in usage_dir.glob(f"*{SHOWDOWN_SUFFIX}"):
        stem = path.name[: -len(SHOWDOWN_SUFFIX)]
        if stem:
            tags.add(stem)
    return tags


def load_showdown_doc(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def is_first_fill(doc: dict[str, Any] | None) -> bool:
    if doc is None:
        return True
    meta = doc.get("meta") or {}
    species = ((doc.get("showdown_doubles") or {}).get("species")) or {}
    month = meta.get("showdown_month")
    if not isinstance(species, dict) or len(species) < 1:
        return True
    if not isinstance(month, str) or not month.strip():
        return True
    return False


def disk_month_overlap_class(
    tag: str,
    showdown_month: str,
    schedule: list[ScheduleWindow],
) -> OverlapClass | None:
    """Classify the file's own ``showdown_month`` as full/short from the schedule.

    Used by the short-overlap skip rule: a short candidate is skipped when the
    committed month on disk is itself a full-overlap month for that tag.
    """
    window = window_for_tag(schedule, tag)
    if window is None:
        return None
    return overlap_class(window, showdown_month)


def pair_satisfied(
    doc: dict[str, Any] | None,
    pair: OwedPair,
) -> bool:
    if doc is None or is_first_fill(doc):
        return False
    meta = doc.get("meta") or {}
    species = ((doc.get("showdown_doubles") or {}).get("species")) or {}
    month = meta.get("showdown_month")
    if not isinstance(species, dict) or len(species) < 1:
        return False
    if meta.get("showdown_format") != pair.format_id:
        return False
    if not isinstance(month, str) or not month.strip():
        return False
    return month >= pair.month


def list_owed_pairs(
    schedule: list[ScheduleWindow],
    *,
    now: datetime,
    usage_dir: Path = USAGE_DIR,
    tags: set[str] | None = None,
) -> list[OwedPair]:
    want = tags if tags is not None else eligible_tags(
        schedule, now=now, usage_dir=usage_dir
    )
    pairs: list[OwedPair] = []
    for tag in sorted(want):
        window = window_for_tag(schedule, tag)
        if window is None:
            continue
        reg = REGULATIONS.get(tag) or {}
        format_id = reg.get("showdown_format")
        if not format_id:
            continue
        for month in iter_yyyy_mm(window.start, window.exclusive_end):
            klass = overlap_class(window, month)
            if klass is None:
                continue
            pairs.append(
                OwedPair(
                    tag=tag,
                    month=month,
                    overlap_class=klass,
                    overlap_days=overlap_days(window, month),
                    format_id=format_id,
                )
            )
    return pairs


def _prior_battles_and_days(
    doc: dict[str, Any],
    schedule: list[ScheduleWindow],
    tag: str,
) -> tuple[int, float, str]:
    meta = doc.get("meta") or {}
    try:
        battles = int(meta.get("showdown_battles") or 0)
    except (TypeError, ValueError):
        battles = 0
    prior_month = str(meta.get("showdown_month") or "")
    window = window_for_tag(schedule, tag)
    days = overlap_days(window, prior_month) if window and prior_month else 1e-9
    return battles, days, prior_month


def check_drop_ratio(
    *,
    new_battles: int,
    new_overlap_days: float,
    prior_battles: int,
    prior_overlap_days: float,
) -> tuple[bool, float, float]:
    """Return (ok, raw_ratio, per_day_ratio)."""
    raw = (new_battles / prior_battles) if prior_battles > 0 else 1.0
    prior_bpd = prior_battles / max(prior_overlap_days, 1e-9)
    new_bpd = new_battles / max(new_overlap_days, 1e-9)
    per_day = (new_bpd / prior_bpd) if prior_bpd > 0 else 1.0
    return per_day >= DROP_RATIO, raw, per_day


def overdue_status(
    pair: OwedPair, *, now: datetime, satisfied: bool
) -> Literal["ok", "loud", "warn"] | None:
    """None if not yet in overdue window; else loud/warn/ok(satisfied)."""
    if pair.overlap_class != "full":
        return None
    if satisfied:
        return "ok"
    if not month_has_ended(pair.month, now):
        return None
    day_n = days_past_month_end(pair.month, now)
    if day_n < OVERDUE_FROM_DAY:
        return None
    if day_n <= OVERDUE_LOUD_THROUGH_DAY:
        return "loud"
    return "warn"


def process_pair(
    pair: OwedPair,
    *,
    now: datetime,
    force: bool,
    schedule: list[ScheduleWindow],
    usage_dir: Path,
    fetch_chaos: FetchChaos,
    dry_run: bool,
    write: bool,
) -> PairResult:
    path = showdown_path(pair.tag, usage_dir)
    doc = load_showdown_doc(path)

    if pair_satisfied(doc, pair):
        return PairResult(pair, "satisfied_noop", f"month>={pair.month}")

    if not month_has_ended(pair.month, now) and not force:
        return PairResult(pair, "month_not_ended", "skip")

    # Short-overlap gate: skip when disk already holds a full-overlap month.
    if pair.overlap_class == "short" and not force and not is_first_fill(doc):
        meta = (doc or {}).get("meta") or {}
        disk_month = meta.get("showdown_month")
        if isinstance(disk_month, str) and disk_month.strip():
            disk_klass = disk_month_overlap_class(pair.tag, disk_month, schedule)
            if disk_klass == "full":
                return PairResult(
                    pair,
                    "skip_short_over_full",
                    f"disk={disk_month} full; refuse short {pair.month}",
                )

    try:
        showdown, info = fetch_chaos(pair.month, pair.format_id, DEFAULT_RATING)
    except (RuntimeError, SystemExit, OSError) as e:
        return PairResult(pair, "quiet_skip_unpublished", str(e) or "fetch failed")

    if not isinstance(showdown, dict) or len(showdown) < 1:
        # Empty after a "successful" transport — integrity hard-fail.
        return PairResult(pair, "fail_integrity", "showdown species empty")

    try:
        battles_n = int((info or {}).get("number of battles") or 0)
    except (TypeError, ValueError):
        battles_n = 0

    if (
        doc is not None
        and already_grafted(
            doc,
            month=pair.month,
            format_id=pair.format_id,
            battles=battles_n,
            species_n=len(showdown),
        )
        and not force
    ):
        return PairResult(pair, "already_grafted", "noop")

    # DROP_RATIO for full-overlap non-first-fill (skipped under force).
    if (
        pair.overlap_class == "full"
        and not is_first_fill(doc)
        and not force
        and doc is not None
    ):
        prior_b, prior_d, prior_m = _prior_battles_and_days(doc, schedule, pair.tag)
        ok, raw, per_day = check_drop_ratio(
            new_battles=battles_n,
            new_overlap_days=pair.overlap_days,
            prior_battles=prior_b,
            prior_overlap_days=prior_d,
        )
        detail = (
            f"raw={raw:.4f} per_day={per_day:.4f} "
            f"new={battles_n}/{pair.overlap_days:.4f}d "
            f"prior={prior_b}/{prior_d:.4f}d({prior_m})"
        )
        if not ok:
            return PairResult(pair, "fail_drop_ratio", detail)
        # Log both ratios on the success path via detail when writing.
        drop_detail = detail
    else:
        drop_detail = ""

    try:
        out = graft(
            showdown=showdown,
            info=info or {},
            month=pair.month,
            format_id=pair.format_id,
            rating=DEFAULT_RATING,
            regulation=pair.tag,
        )
    except ValueError as e:
        return PairResult(pair, "fail_integrity", str(e))

    summary = (
        f"write {path.name} month={pair.month} battles={battles_n} "
        f"species={len(showdown)}"
        + (f" {drop_detail}" if drop_detail else "")
    )
    if dry_run or not write:
        return PairResult(pair, "would_write", summary)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return PairResult(pair, "wrote", summary)


def run_rollover(
    *,
    now: datetime | None = None,
    force: bool = False,
    schedule: list[ScheduleWindow] | None = None,
    usage_dir: Path = USAGE_DIR,
    fetch_chaos: FetchChaos | None = None,
    dry_run: bool = False,
    write: bool = True,
    log: Callable[[str], None] | None = None,
) -> tuple[int, list[PairResult]]:
    """Run owed-pair fetch + overdue alarm. Return (exit_code, results)."""
    clock = now or datetime.now(timezone.utc)
    windows = schedule if schedule is not None else load_schedule()
    fetch = fetch_chaos or _fetch_chaos
    emit = log or (lambda msg: print(msg, file=sys.stderr))

    pairs = list_owed_pairs(windows, now=clock, usage_dir=usage_dir)
    results: list[PairResult] = []
    exit_code = 0
    wrote_any = False

    for pair in pairs:
        path = showdown_path(pair.tag, usage_dir)
        doc = load_showdown_doc(path)
        if pair_satisfied(doc, pair):
            results.append(PairResult(pair, "satisfied_noop"))
            continue

        result = process_pair(
            pair,
            now=clock,
            force=force,
            schedule=windows,
            usage_dir=usage_dir,
            fetch_chaos=fetch,
            dry_run=dry_run,
            write=write,
        )
        results.append(result)
        emit(f"{result.action}: {pair.tag} {pair.month} {result.detail}".rstrip())

        if result.action == "fail_integrity":
            exit_code = 1
        elif result.action == "fail_drop_ratio":
            exit_code = 1
        elif result.action in {"wrote", "would_write", "already_grafted"}:
            if result.action == "wrote":
                wrote_any = True
        elif result.action == "skip_short_over_full":
            emit(
                f"WARN short-overlap skipped over full disk month: "
                f"{pair.tag} {pair.month}"
            )

        # Re-read satisfaction after processing (write clears overdue).
        doc_after = load_showdown_doc(path)
        if result.action == "would_write":
            # Dry-run: treat as satisfied for overdue purposes this pass.
            satisfied_after = True
        elif result.action == "already_grafted":
            satisfied_after = True
        else:
            satisfied_after = pair_satisfied(doc_after, pair)

        if (
            pair.overlap_class == "short"
            and month_has_ended(pair.month, clock)
            and not satisfied_after
        ):
            emit(f"WARN short-overlap unsatisfied: {pair.tag} {pair.month}")

        od = overdue_status(pair, now=clock, satisfied=satisfied_after)
        if od == "loud":
            if force:
                emit(
                    f"WARN overdue(softened by force): {pair.tag} {pair.month} "
                    f"day={days_past_month_end(pair.month, clock)}"
                )
            else:
                emit(
                    f"ERROR overdue: {pair.tag} {pair.month} still missing "
                    f"(day {days_past_month_end(pair.month, clock)} of following "
                    f"month; loud through day {OVERDUE_LOUD_THROUGH_DAY})"
                )
                exit_code = 1
        elif od == "warn":
            emit(
                f"WARN overdue(capped): {pair.tag} {pair.month} still missing "
                f"(day {days_past_month_end(pair.month, clock)} > "
                f"{OVERDUE_LOUD_THROUGH_DAY}; alarm downgraded)"
            )

    if wrote_any:
        emit("showdown file(s) updated")
    return exit_code, results


def _parse_now(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--now",
        default=None,
        help="Override UTC clock (ISO-8601) for owed/overdue decisions",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Skip DROP_RATIO, overdue soft-path, and short-over-full gate",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute actions without writing files",
    )
    p.add_argument(
        "--usage-dir",
        type=Path,
        default=USAGE_DIR,
        help="Directory containing *.showdown_doubles.v1.json",
    )
    args = p.parse_args(argv)
    code, _results = run_rollover(
        now=_parse_now(args.now),
        force=bool(args.force),
        usage_dir=args.usage_dir,
        dry_run=bool(args.dry_run),
        write=not bool(args.dry_run),
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
