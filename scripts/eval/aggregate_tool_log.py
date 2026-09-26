#!/usr/bin/env python3
"""Aggregate RECOMMENDER_TOOL_LOG JSONL into per-tool latency/retry stats."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path


def p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    # nearest-rank: index = ceil(0.95 * n) - 1
    idx = max(0, min(len(ordered) - 1, (95 * len(ordered) + 99) // 100 - 1))
    return ordered[idx]


def aggregate_file(path: Path) -> dict[str, dict]:
    """Return {tool: {count, mean_ms, p95_ms, fail, fail_rate, retries}}."""
    by_tool: dict[str, list[tuple[float, bool, int]]] = defaultdict(list)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            by_tool[str(rec["tool"])].append(
                (float(rec["latency_ms"]), bool(rec["ok"]), int(rec.get("retries") or 0))
            )
    out: dict[str, dict] = {}
    for tool, rows in sorted(by_tool.items()):
        latencies = [r[0] for r in rows]
        fails = sum(1 for r in rows if not r[1])
        retries = sum(r[2] for r in rows)
        n = len(rows)
        out[tool] = {
            "count": n,
            "mean_ms": round(statistics.fmean(latencies), 3) if latencies else None,
            "p95_ms": round(p95(latencies), 3) if latencies else None,
            "fail": fails,
            "fail_rate": round(fails / n, 4) if n else 0.0,
            "retries": retries,
        }
    return out


def markdown_table(suite: str, stats: dict[str, dict]) -> str:
    lines = [
        f"### Suite: `{suite}`",
        "",
        "| tool | count | mean_ms | p95_ms | fail | fail_rate | retries |",
        "|------|------:|--------:|-------:|-----:|----------:|--------:|",
    ]
    if not stats:
        lines.append("| *(no calls)* | 0 | — | — | 0 | 0 | 0 |")
    else:
        for tool, s in stats.items():
            lines.append(
                f"| `{tool}` | {s['count']} | {s['mean_ms']} | {s['p95_ms']} | "
                f"{s['fail']} | {s['fail_rate']} | {s['retries']} |"
            )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="JSONL log paths (suite label = filename stem)",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=None,
        help="Write aggregate JSON (default: next to first path as tool_calls_aggregate.json)",
    )
    args = parser.parse_args()

    summary: dict[str, dict] = {}
    blocks: list[str] = []
    for path in args.paths:
        suite = path.stem.removeprefix("tool_calls_")
        stats = aggregate_file(path)
        summary[suite] = {"path": str(path), "tools": stats, "total_calls": sum(
            s["count"] for s in stats.values()
        )}
        blocks.append(markdown_table(suite, stats))

    print("\n\n".join(blocks))
    out = args.out_json
    if out is None:
        out = args.paths[0].parent / "tool_calls_aggregate.json"
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    # ponytail: one assert for p95 nearest-rank; no pytest file.
    assert p95([1.0] * 20) == 1.0
    assert p95(list(range(1, 101))) == 95
    raise SystemExit(main())
