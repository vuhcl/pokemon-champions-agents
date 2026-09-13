"""Cadence + validate gate for MunchStats Reg M-C usage refresh."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.ci.champions_news import (
    fetch_html,
    scan_for_current_season,
    scan_for_letter,
)
from scripts.ci.regulation_letters import letter_from_format_name
from scripts.extract_usage.fetch_usage_mc_munchstats import (
    DEFAULT_OUT,
    extract,
    validate_snapshot,
)

ROOT = Path(__file__).resolve().parents[2]
LEGALITY = ROOT / "data" / "legality" / "champions.v1.json"
REG_BOOKMARK = ROOT / "data" / "legality" / "fixtures" / "regulation_news_bookmark.json"
SEASON_BOOKMARK = ROOT / "data" / "usage" / "fixtures" / "season_news_bookmark.json"
EARLY_DAYS = 7
SEASON_RUN_DAYS = frozenset({0, 14})


def write_github_output(path: Path | None, fields: dict[str, str]) -> None:
    if path is None:
        return
    with path.open("a", encoding="utf-8") as f:
        for k, v in fields.items():
            f.write(f"{k}={v}\n")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def snapshot_letter(path: Path = LEGALITY) -> str:
    snap = load_json(path)
    vgc = ((snap.get("meta") or {}).get("formats") or {}).get("vgc")
    return letter_from_format_name(str(vgc or ""))


def resolve_reg_start(
    letter: str,
    *,
    bookmark: dict[str, Any] | None = None,
    fetch_html_fn=fetch_html,
) -> datetime:
    bm = bookmark if bookmark is not None else load_json(REG_BOOKMARK)
    start_id = int(bm["last_seen_page_id"])
    page = scan_for_letter(letter, start_page_id=start_id, window=80, fetch=fetch_html_fn)
    return page.start_utc


def should_run_cadence(
    *,
    now: datetime,
    reg_start: datetime,
    season_bookmark: dict[str, Any] | None = None,
    fetch_html_fn=fetch_html,
) -> tuple[bool, str]:
    """Return (should_run, reason)."""
    if now < reg_start:
        return False, "official_start_in_future"
    days = (now.date() - reg_start.date()).days
    if 0 <= days <= EARLY_DAYS:
        return True, f"early_window_day_{days}"

    bm = season_bookmark if season_bookmark is not None else load_json(SEASON_BOOKMARK)
    start_id = int(bm["last_seen_page_id"])
    try:
        season = scan_for_current_season(
            start_page_id=start_id, window=80, now=now, fetch=fetch_html_fn
        )
    except LookupError as e:
        # Fallback: every 14 days after early window.
        if (days - EARLY_DAYS) % 14 == 0:
            return True, f"day_count_fallback_day_{days} ({e})"
        return False, f"outside_window_season_scan_failed ({e})"

    day_of_season = (now.date() - season.start_utc.date()).days
    if day_of_season in SEASON_RUN_DAYS:
        return True, f"season_m{season.season_number}_day_{day_of_season}"
    return False, f"outside_window_season_day_{day_of_season}"


def bump_season_bookmark(page_id: int, season_number: int) -> None:
    SEASON_BOOKMARK.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_seen_page_id": int(page_id),
        "season_number": int(season_number),
        "note": (
            "news.pokemon-home.com /en/page/{id}.html — Ranked Battles Season M-* "
            "Event Period"
        ),
    }
    SEASON_BOOKMARK.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run_gate(
    *,
    now: datetime | None = None,
    out_path: Path = DEFAULT_OUT,
    force: bool = False,
    github_output: Path | None = None,
    fetch_html_fn=fetch_html,
    extract_fn=extract,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    letter = snapshot_letter()
    result: dict[str, Any] = {
        "checked_at_utc": now.isoformat().replace("+00:00", "Z"),
        "letter": letter,
    }

    if not force:
        try:
            reg_start = resolve_reg_start(letter, fetch_html_fn=fetch_html_fn)
        except Exception as e:
            result.update(
                {"decision": "fail", "reason": "reg_start_resolve_failed", "message": str(e)}
            )
            write_github_output(
                github_output, {"decision": "fail", "reason": result["reason"]}
            )
            return result
        result["reg_start_utc"] = reg_start.isoformat().replace("+00:00", "Z")
        run, reason = should_run_cadence(
            now=now, reg_start=reg_start, fetch_html_fn=fetch_html_fn
        )
        result["cadence_reason"] = reason
        if not run:
            result["decision"] = "noop"
            result["reason"] = reason
            write_github_output(
                github_output, {"decision": "noop", "reason": reason}
            )
            return result
    else:
        result["cadence_reason"] = "force"

    try:
        snap, index, stats = extract_fn()
    except Exception as e:
        result.update({"decision": "fail", "reason": "extract_failed", "message": str(e)})
        write_github_output(
            github_output, {"decision": "fail", "reason": "extract_failed"}
        )
        return result

    previous = None
    if out_path.exists():
        try:
            previous = load_json(out_path)
        except (OSError, json.JSONDecodeError):
            previous = None

    decision, reason = validate_snapshot(
        snap, index=index, stats=stats, previous=previous
    )
    result["validate_reason"] = reason
    result["stats"] = stats
    result["species_n"] = len(((snap.get("ingame_doubles") or {}).get("species")) or {})

    if decision == "fail":
        result["decision"] = "fail"
        result["reason"] = reason
        write_github_output(github_output, {"decision": "fail", "reason": reason})
        return result
    if decision == "noop":
        result["decision"] = "noop"
        result["reason"] = reason
        write_github_output(github_output, {"decision": "noop", "reason": reason})
        return result

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    result["decision"] = "commit"
    result["reason"] = reason
    result["out_path"] = str(out_path)
    write_github_output(
        github_output,
        {
            "decision": "commit",
            "reason": reason,
            "out_path": str(out_path),
        },
    )
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--github-output", type=Path, default=None)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument(
        "--force",
        action="store_true",
        help="Skip cadence window check (still validates freshness/floors)",
    )
    p.add_argument("--out-json", type=Path, default=None, help="Write gate result JSON")
    args = p.parse_args(argv)

    gh_out = args.github_output
    if gh_out is None:
        env = __import__("os").environ.get("GITHUB_OUTPUT")
        if env:
            gh_out = Path(env)

    result = run_gate(out_path=args.out, force=args.force, github_output=gh_out)
    if args.out_json:
        args.out_json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in result if k != "stats"}, indent=2))
    decision = result.get("decision")
    if decision == "fail":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
