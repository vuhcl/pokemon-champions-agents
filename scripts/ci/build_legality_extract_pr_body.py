"""Build PR body for the legality extract gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "data" / "legality" / "champions.v1.json"
FIXTURES = ROOT / "data" / "legality" / "fixtures"


def _live_diff_path(from_mod: str) -> Path:
    return FIXTURES / f"{from_mod}_to_champions.diff.json"


def build_body(gate: dict) -> str:
    snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    commit = ((snap.get("meta") or {}).get("source") or {}).get("commit", "?")
    # Live diff: prior_mod on gate is the archive of the *outgoing* letter
    # (championsregmc when leaving C). write_snapshot derives from_mod from
    # the *new* VGC letter → same id (Reg M-D → championsregmc).
    from_mod = gate.get("prior_mod") or ""
    diff_path = _live_diff_path(str(from_mod))
    species_legal = species_illegal = item_legal = item_illegal = 0
    species_ids: list[str] = []
    item_ids: list[str] = []
    if diff_path.exists():
        diff = json.loads(diff_path.read_text(encoding="utf-8"))
        for e in diff.get("species") or []:
            if e.get("change") == "became_legal":
                species_legal += 1
                species_ids.append(e["id"])
            elif e.get("change") == "became_illegal":
                species_illegal += 1
        for e in diff.get("items") or []:
            if e.get("change") == "became_legal":
                item_legal += 1
                item_ids.append(e["id"])
            elif e.get("change") == "became_illegal":
                item_illegal += 1

    def fmt_ids(ids: list[str], limit: int = 40) -> str:
        if len(ids) <= limit:
            return ", ".join(ids) if ids else "(none)"
        return ", ".join(ids[:limit]) + f", … (+{len(ids) - limit} more)"

    lines = [
        "## Summary",
        "",
        f"- Regulation advance: **M-{gate.get('current_letter')} → M-{gate.get('live_letter')}**",
        f"- Showdown commit: `{commit}`",
        f"- Gate decision: `{gate.get('decision')}` (`{gate.get('reason')}`)",
        f"- Official start (UTC): `{gate.get('official_start_utc')}`",
        f"- News: {gate.get('news_url')} (page_id={gate.get('news_page_id')})",
        "",
        "## Diff fixture counts",
        "",
        f"- Live fixture: `{diff_path.relative_to(ROOT)}`",
        f"- Species `became_legal`: **{species_legal}** — {fmt_ids(species_ids)}",
        f"- Species `became_illegal`: **{species_illegal}**",
        f"- Items `became_legal`: **{item_legal}** — {fmt_ids(item_ids)}",
        f"- Items `became_illegal`: **{item_illegal}**",
        "",
        "## Preconditions (both required)",
        "",
        "1. Official champions-news Duration start has passed — **yes** "
        f"(`{gate.get('official_start_utc')}` ≤ `{gate.get('checked_at_utc')}`).",
        "2. Showdown champions VGC/BSS format names reflect the new regulation "
        f"and prior mod `{gate.get('prior_mod')}` exists — **yes** "
        f"(commit `{gate.get('showdown_commit')}`).",
        "",
        "## Identity retarget (same PR)",
        "",
        "- `recommender/session.py` `DEFAULT_FORMAT_ID`",
        "- `recommender/ids.py` `_MOD_TO_TAG` + `REGULATION_ARCHIVE_ORDER`",
        "- `recommender/format.py` archived prior-letter branch",
        "",
        "Do **not** auto-merge. Human review required (legality is actively "
        "dangerous if wrong).",
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
