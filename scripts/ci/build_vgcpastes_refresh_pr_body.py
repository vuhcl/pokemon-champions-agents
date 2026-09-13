"""Build PR body for the VGCPastes M-C refresh gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def build_body(gate: dict[str, Any]) -> str:
    prev = gate.get("prev_teams_resolved")
    cur = gate.get("teams_resolved")
    delta = None
    if isinstance(prev, int) and isinstance(cur, int):
        delta = cur - prev
    ev = gate.get("ev_completeness") or {}
    resolve = gate.get("resolve_counts") or {}
    lines = [
        "## Summary",
        "",
        f"- Sheet title: **{gate.get('sheet_title') or '(unknown)'}**",
        f"- Sheet gid: `{gate.get('sheet_gid')}`",
        f"- Output: `{gate.get('out_path')}`",
        f"- Extracted at: `{gate.get('extracted_at')}`",
        f"- Gate: `{gate.get('decision')}` (`{gate.get('reason')}`)",
        "",
        "## Teams",
        "",
        f"- `teams_resolved`: **{cur}**",
        f"- Previous team count: **{prev}**",
        f"- Delta: **{delta if delta is not None else 'n/a (first extract)'}**",
        f"- `resolve_counts`: `{json.dumps(resolve, sort_keys=True)}`",
        "",
        "## EV completeness",
        "",
        f"- teams_all_members_have_evs: **{ev.get('teams_all_members_have_evs')}**",
        f"- teams_all_members_zero_evs: **{ev.get('teams_all_members_zero_evs')}**",
        f"- teams_partial_evs: **{ev.get('teams_partial_evs')}**",
        f"- members_with_nonzero_evs / members_total: "
        f"**{ev.get('members_with_nonzero_evs')}** / **{ev.get('members_total')}**",
        "",
        "Do **not** auto-merge. Human review required.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gate", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)
    gate = json.loads(args.gate.read_text(encoding="utf-8"))
    body = build_body(gate)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(body, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
