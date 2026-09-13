"""Spacing gate for PR-gated VGCPastes M-C refresh."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.extract_usage.fetch_vgcpastes_builds import (
    DEFAULT_OUT,
    DEFAULT_REGULATION,
    DEFAULT_SHEET_GID,
    SHEET_ID,
    extract,
    validate_vgcpastes_snapshot,
)

ROOT = Path(__file__).resolve().parents[2]
MARKER_PATH = (
    ROOT / "data" / "team-composition" / "fixtures" / "vgcpastes_refresh_marker.json"
)
MIN_SPACING_DAYS = 14


def write_github_output(path: Path | None, fields: dict[str, str]) -> None:
    if path is None:
        return
    with path.open("a", encoding="utf-8") as f:
        for k, v in fields.items():
            f.write(f"{k}={v}\n")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_marker(path: Path = MARKER_PATH) -> dict[str, Any]:
    if not path.exists():
        return {
            "last_extract_at": None,
            "teams_resolved": None,
            "sheet_gid": DEFAULT_SHEET_GID,
            "last_outcome": None,
        }
    return load_json(path)


def write_marker(marker: dict[str, Any], path: Path = MARKER_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")


def should_run_extract(
    *,
    now: datetime,
    marker: dict[str, Any],
    force: bool = False,
    spacing_days: int = MIN_SPACING_DAYS,
) -> tuple[bool, str]:
    if force:
        return True, "force"
    last = _parse_iso(str(marker.get("last_extract_at") or "") or None)
    if last is None:
        return True, "no_prior_extract"
    days = (now.date() - last.date()).days
    if days < spacing_days:
        return False, f"spacing_{days}_lt_{spacing_days}"
    return True, "spacing_ok"


def run_gate(
    *,
    now: datetime | None = None,
    force: bool = False,
    github_output: Path | None = None,
    marker_path: Path = MARKER_PATH,
    out_path: Path = DEFAULT_OUT,
    extract_fn=extract,
    sheet_id: str = SHEET_ID,
    gid: str = DEFAULT_SHEET_GID,
    regulation: str = DEFAULT_REGULATION,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    marker = load_marker(marker_path)
    result: dict[str, Any] = {
        "checked_at_utc": now.isoformat().replace("+00:00", "Z"),
        "sheet_gid": str(gid),
        "out_path": str(out_path.relative_to(ROOT))
        if out_path.is_relative_to(ROOT)
        else str(out_path),
    }

    run, reason = should_run_extract(now=now, marker=marker, force=force)
    result["gate_reason"] = reason
    if not run:
        result["decision"] = "noop"
        result["reason"] = reason
        result["bump_marker"] = False
        write_github_output(
            github_output,
            {"decision": "noop", "reason": reason, "bump_marker": "false"},
        )
        return result

    previous = None
    previous_raw: str | None = None
    if out_path.exists():
        try:
            previous_raw = out_path.read_text(encoding="utf-8")
            previous = json.loads(previous_raw)
        except (OSError, json.JSONDecodeError):
            previous = None
            previous_raw = None

    try:
        snap = extract_fn(
            sheet_id=sheet_id,
            gid=gid,
            regulation=regulation,
            out_path=out_path,
        )
    except Exception as e:
        result.update(
            {"decision": "fail", "reason": "extract_failed", "message": str(e)}
        )
        result["bump_marker"] = False
        write_github_output(
            github_output,
            {"decision": "fail", "reason": "extract_failed", "bump_marker": "false"},
        )
        return result

    decision, vreason = validate_vgcpastes_snapshot(snap, previous=previous)
    result["validate_reason"] = vreason
    meta = snap.get("meta") or {}
    result["teams_resolved"] = meta.get("teams_resolved")
    result["extracted_at"] = meta.get("extracted_at")
    result["resolve_counts"] = meta.get("resolve_counts")
    result["ev_completeness"] = meta.get("ev_completeness")
    result["sheet_title"] = ((meta.get("population_evidence") or {}).get("sheet_title"))
    result["prev_teams_resolved"] = (previous or {}).get("meta", {}).get(
        "teams_resolved"
    )

    if decision == "fail":
        if previous_raw is not None:
            out_path.write_text(previous_raw, encoding="utf-8")
        result["decision"] = "fail"
        result["reason"] = vreason
        result["bump_marker"] = False
        write_github_output(
            github_output,
            {"decision": "fail", "reason": vreason, "bump_marker": "false"},
        )
        return result

    iso_now = now.isoformat().replace("+00:00", "Z")
    marker.update(
        {
            "last_extract_at": meta.get("extracted_at") or iso_now,
            "teams_resolved": meta.get("teams_resolved"),
            "sheet_gid": str(gid),
            "last_outcome": "pr_opened" if decision == "ok" else "noop_unchanged",
        }
    )
    write_marker(marker, marker_path)
    result["bump_marker"] = True

    if decision == "noop":
        result["decision"] = "marker_only"
        result["reason"] = vreason
        write_github_output(
            github_output,
            {
                "decision": "marker_only",
                "reason": vreason,
                "bump_marker": "true",
            },
        )
        return result

    result["decision"] = "pr"
    result["reason"] = vreason
    write_github_output(
        github_output,
        {
            "decision": "pr",
            "reason": vreason,
            "bump_marker": "true",
            "out_path": result["out_path"],
        },
    )
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--github-output", type=Path, default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--out-json", type=Path, default=None)
    p.add_argument("--marker", type=Path, default=MARKER_PATH)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--gid", default=DEFAULT_SHEET_GID)
    p.add_argument("--regulation", default=DEFAULT_REGULATION)
    args = p.parse_args(argv)

    gh_out = args.github_output
    if gh_out is None:
        env = os.environ.get("GITHUB_OUTPUT")
        if env:
            gh_out = Path(env)

    result = run_gate(
        force=args.force,
        github_output=gh_out,
        marker_path=args.marker,
        out_path=args.out,
        gid=args.gid,
        regulation=args.regulation,
    )
    if args.out_json:
        args.out_json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
