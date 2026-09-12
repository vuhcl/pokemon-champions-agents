"""Event-driven gate: official Champions regulation start + Showdown mod ready."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from scripts.ci.champions_news import (
    fetch_html,
    parse_regulation_news_html,
    scan_for_letter,
)
from scripts.ci.regulation_letters import (
    archive_mod_for_letter,
    letter_from_format_name,
    letters_adjacent,
)

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "data" / "legality" / "champions.v1.json"
BOOKMARK = ROOT / "data" / "legality" / "fixtures" / "regulation_news_bookmark.json"
DEFAULT_CACHE = ROOT / ".cache" / "pokemon-showdown"

FetchFn = Callable[[str], str]


def _ensure_showdown(cache: Path = DEFAULT_CACHE) -> Path:
    cache.parent.mkdir(parents=True, exist_ok=True)
    if not (cache / ".git").exists():
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "https://github.com/smogon/pokemon-showdown.git",
                str(cache),
            ],
            check=True,
        )
    else:
        subprocess.run(
            ["git", "-C", str(cache), "fetch", "--depth", "1", "origin"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(cache), "reset", "--hard", "FETCH_HEAD"],
            check=True,
        )
    return cache


def _git_head(repo: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()


def champions_format_names(formats_ts: str) -> tuple[str, str]:
    """Return (vgc_name, bss_name) for mod: 'champions' entries."""
    vgc: str | None = None
    bss: str | None = None
    patterns = (
        r"\{\s*name:\s*[\"'`]([^\"'`]+)[\"'`][^}]*?mod:\s*[\"'`]champions[\"'`]",
        r"\{\s*mod:\s*[\"'`]champions[\"'`][^}]*?name:\s*[\"'`]([^\"'`]+)[\"'`]",
    )
    for pat in patterns:
        for block in re.finditer(pat, formats_ts, re.S):
            name = block.group(1)
            if re.search(r"\bVGC\b", name, re.I) and vgc is None:
                vgc = name
            elif re.search(r"\bBSS\b", name, re.I) and bss is None:
                bss = name
    if not vgc or not bss:
        raise ValueError("could not resolve champions VGC/BSS format names")
    return vgc, bss


def load_bookmark(path: Path = BOOKMARK) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def snapshot_vgc_name(path: Path = SNAPSHOT) -> str:
    snap = json.loads(path.read_text(encoding="utf-8"))
    vgc = ((snap.get("meta") or {}).get("formats") or {}).get("vgc")
    if not vgc:
        raise ValueError(f"missing meta.formats.vgc in {path}")
    return str(vgc)


def write_github_output(path: Path | None, fields: dict[str, str]) -> None:
    if path is None:
        return
    with path.open("a", encoding="utf-8") as f:
        for k, v in fields.items():
            f.write(f"{k}={v}\n")


def run_gate(
    *,
    now: datetime | None = None,
    showdown_repo: Path | None = None,
    news_url: str | None = None,
    formats_ts_text: str | None = None,
    snapshot_vgc: str | None = None,
    bookmark: dict[str, Any] | None = None,
    showdown_commit: str | None = None,
    require_prior_mod_dir: bool = True,
    fetch_html_fn: FetchFn = fetch_html,
) -> dict[str, Any]:
    """Core gate. Inject formats/snapshot/clock for unit tests (no network)."""
    now = now or datetime.now(timezone.utc)
    snap_vgc = snapshot_vgc or snapshot_vgc_name()
    current = letter_from_format_name(snap_vgc)

    if formats_ts_text is None:
        repo = showdown_repo or _ensure_showdown()
        formats_ts_text = (repo / "config" / "formats.ts").read_text(encoding="utf-8")
        commit = showdown_commit or _git_head(repo)
    else:
        repo = showdown_repo
        commit = showdown_commit or "test"

    live_vgc, live_bss = champions_format_names(formats_ts_text)
    live = letter_from_format_name(live_vgc)

    base: dict[str, Any] = {
        "current_letter": current,
        "live_letter": live,
        "snapshot_vgc": snap_vgc,
        "showdown_vgc": live_vgc,
        "showdown_bss": live_bss,
        "showdown_commit": commit,
        "checked_at_utc": now.isoformat().replace("+00:00", "Z"),
    }

    if live == current:
        return {
            **base,
            "decision": "noop",
            "reason": "showdown_letter_matches_snapshot",
        }

    if not letters_adjacent(current, live):
        return {
            **base,
            "decision": "fail",
            "reason": "non_adjacent_letter",
            "message": (
                f"live Reg M-{live} is not exactly one step after "
                f"snapshot Reg M-{current}"
            ),
        }

    bm = bookmark if bookmark is not None else load_bookmark()
    start_id = int(bm["last_seen_page_id"])
    try:
        if news_url:
            html = fetch_html_fn(news_url)
            page = parse_regulation_news_html(html, url=news_url, page_id=None)
            if page.letter != live:
                return {
                    **base,
                    "decision": "fail",
                    "reason": "news_url_letter_mismatch",
                    "message": (
                        f"REGULATION_NEWS_URL letter M-{page.letter} != live M-{live}"
                    ),
                    "news_url": news_url,
                }
        else:
            page = scan_for_letter(
                live, start_page_id=start_id, window=80, fetch=fetch_html_fn
            )
    except Exception as e:
        return {
            **base,
            "decision": "fail",
            "reason": "news_parse_failed",
            "message": str(e),
        }

    base.update(
        {
            "news_url": page.url,
            "news_page_id": page.page_id,
            "official_start_utc": page.start_utc.isoformat().replace("+00:00", "Z"),
            "official_end_utc": page.end_utc.isoformat().replace("+00:00", "Z"),
            "news_title": page.title,
        }
    )

    if now < page.start_utc:
        return {
            **base,
            "decision": "noop",
            "reason": "official_start_in_future",
        }

    # Leaving M-C → Showdown archives as championsregmc
    prior_archive = archive_mod_for_letter(current)
    base["prior_mod"] = prior_archive
    base["next_file_tag"] = f"champions-reg-m{live.lower()}"

    if require_prior_mod_dir:
        if repo is None:
            return {
                **base,
                "decision": "fail",
                "reason": "missing_showdown_repo",
                "message": "showdown repo required to verify prior mod dir",
            }
        mods_root = repo / "data" / "mods" / prior_archive
        if not mods_root.is_dir():
            return {
                **base,
                "decision": "fail",
                "reason": "missing_prior_mod",
                "message": f"expected Showdown archive mod dir {prior_archive}",
            }

    return {
        **base,
        "decision": "extract",
        "reason": "official_start_passed_and_showdown_ready",
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True, help="gate.json output path")
    p.add_argument(
        "--github-output",
        type=Path,
        default=None,
        help="Append decision=… fields for Actions",
    )
    p.add_argument("--showdown-path", type=Path, default=None)
    args = p.parse_args(argv)

    news_url = (sys.environ.get("REGULATION_NEWS_URL") or "").strip() or None
    result = run_gate(showdown_repo=args.showdown_path, news_url=news_url)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2), file=sys.stderr)

    write_github_output(
        args.github_output,
        {
            "decision": str(result["decision"]),
            "current_letter": str(result.get("current_letter", "")),
            "live_letter": str(result.get("live_letter", "")),
            "reason": str(result.get("reason", "")),
        },
    )

    if result["decision"] == "fail":
        print(result.get("message") or result.get("reason"), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
