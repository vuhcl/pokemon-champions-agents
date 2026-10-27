"""B3 — load-only dry run for every covered request-set row (no model calls)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts.eval.part_g_arm.state.errata_read import expected_readback
from scripts.eval.part_g_arm.state.request_set_rows import load_covered_ids, load_request_rows, resolve_start_state

HERE = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    out = Path(argv[0]) if argv else HERE / "LAST_B3_DRY_RUN.md"
    covered = load_covered_ids()
    rows = [r for r in load_request_rows() if r["id"] in covered]
    lines = [
        "# B3 — load-only dry run (covered rows, no model)",
        "",
        "| row | loaded | complete | source | readback / note |",
        "|---|---|---|---|---|",
    ]
    table = []
    for row in rows:
        state, meta = resolve_start_state(row)
        rb = meta.get("readback")
        exp = expected_readback(row["id"])
        note = meta.get("error") or ""
        if exp and rb:
            ok = all(rb.get(k) == exp[k] for k in exp)
            note = f"readback match={ok} got={rb} expected={exp}"
        elif exp and not rb:
            note = f"expected readback {exp}; loader gave none"
        lines.append(
            f"| {row['id']} | {meta['loaded']} | {meta['complete']} | {meta.get('source')} | {note} |"
        )
        table.append({**meta, "expected_readback": exp})
    text = "\n".join(lines) + "\n"
    out.write_text(text, encoding="utf-8")
    (HERE / "b3_dry_run.json").write_text(json.dumps(table, indent=2) + "\n", encoding="utf-8")
    loaded = sum(1 for t in table if t["loaded"])
    print(f"wrote {out}; loaded {loaded}/{len(table)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
