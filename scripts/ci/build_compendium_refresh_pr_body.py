"""Build PR body for the Compendium refresh gate (Stage-4 style summaries)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _fmt_tier_moves(changes: list[dict[str, Any]], limit: int = 40) -> list[str]:
    lines: list[str] = []
    for row in changes[:limit]:
        sp = row.get("species")
        disk = row.get("disk")
        live = row.get("live")
        lines.append(f"- `{sp}`: {disk} -> {live}")
    if len(changes) > limit:
        lines.append(f"- … (+{len(changes) - limit} more)")
    return lines


def _fmt_members(rows: list[dict[str, Any]], key: str, limit: int = 30) -> list[str]:
    lines: list[str] = []
    for row in rows[:limit]:
        lines.append(f"- [{row.get('tier')}] {row.get('species')}")
    if len(rows) > limit:
        lines.append(f"- … (+{len(rows) - limit} more)")
    if not rows:
        lines.append("- (none)")
    return lines


def build_body(report: dict[str, Any]) -> str:
    cats = report.get("categories") or {}
    lines = [
        "## Summary",
        "",
        f"- Usage input: `{report.get('usage_path')}`",
        f"- Usage `munchstats_generated_at`: `{report.get('usage_munchstats_generated_at')}`",
        f"- Checked at (UTC): `{report.get('checked_at_utc')}`",
        f"- Rebuild status: `{report.get('status')}`",
        f"- Categories: **{len(cats)}**",
        "",
        "Do **not** auto-merge. Critic clear ≠ ship without looking "
        "(membership/tier decisions need a human glance).",
        "",
        "## Per-category diffs",
        "",
    ]
    for label in sorted(cats):
        c = cats[label]
        diff = c.get("diff") or {}
        admitted_new = diff.get("admitted_new") or []
        dropped = diff.get("dropped") or []
        tier_changed = diff.get("tier_changed") or []
        lines.extend(
            [
                f"### `{label}`",
                "",
                f"- **Admitted:** disk {diff.get('disk_admitted', c.get('disk_admitted'))} "
                f"→ live **{diff.get('live_admitted', c.get('admitted'))}** "
                f"(rejected {c.get('rejected')})",
                f"- **Newly admitted:** {len(admitted_new)}",
                f"- **Dropped:** {len(dropped)}",
                f"- **Tier changes:** {len(tier_changed)}",
                f"- **Critic:** approved={c.get('critic_approved')} "
                f"flags={c.get('critic_flag_count')}",
                "",
            ]
        )
        if tier_changed:
            lines.append("Tier moves:")
            lines.extend(_fmt_tier_moves(tier_changed))
            lines.append("")
        if admitted_new:
            lines.append("Newly admitted:")
            lines.extend(_fmt_members(admitted_new, "admitted"))
            lines.append("")
        if dropped:
            lines.append("Dropped:")
            lines.extend(_fmt_members(dropped, "dropped"))
            lines.append("")
        flags = c.get("critic_flags") or []
        if flags:
            lines.append("Critic flags:")
            for f in flags:
                cands = ", ".join(f.get("candidates") or [])
                lines.append(
                    f"- `{f.get('principle')}` ({cands}): {f.get('detail')}"
                )
            lines.append("")
        elif c.get("critic_flag_count") == 0:
            lines.append("Critic flags: _none_")
            lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)
    report = json.loads(args.report.read_text(encoding="utf-8"))
    body = build_body(report)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(body, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
