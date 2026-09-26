#!/usr/bin/env python3
"""Aggregate RECOMMENDER_TOOL_LOG JSONL into per-tool and per-turn stats."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


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


def _is_llm(tool: str) -> bool:
    return tool.startswith("llm.")


def aggregate_turns(path: Path) -> list[dict[str, Any]]:
    """Roll up latency/tokens by (thread_id, turn); skip rows missing either."""
    buckets: dict[tuple[str, int], dict[str, Any]] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            thread_id = rec.get("thread_id")
            turn = rec.get("turn")
            if not isinstance(thread_id, str) or thread_id == "":
                continue
            if not isinstance(turn, int):
                continue
            key = (thread_id, turn)
            b = buckets.get(key)
            if b is None:
                b = {
                    "thread_id": thread_id,
                    "turn": turn,
                    "llm_ms": 0.0,
                    "tool_ms": 0.0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "llm_calls": 0,
                    "tool_calls": 0,
                    "_has_prompt": False,
                    "_has_completion": False,
                }
                buckets[key] = b
            ms = float(rec["latency_ms"])
            tool = str(rec["tool"])
            if _is_llm(tool):
                b["llm_ms"] += ms
                b["llm_calls"] += 1
                if isinstance(rec.get("prompt_tokens"), int):
                    b["prompt_tokens"] += rec["prompt_tokens"]
                    b["_has_prompt"] = True
                if isinstance(rec.get("completion_tokens"), int):
                    b["completion_tokens"] += rec["completion_tokens"]
                    b["_has_completion"] = True
            else:
                b["tool_ms"] += ms
                b["tool_calls"] += 1
    out: list[dict[str, Any]] = []
    for key in sorted(buckets, key=lambda k: (k[0], k[1])):
        b = buckets[key]
        row = {
            "thread_id": b["thread_id"],
            "turn": b["turn"],
            "llm_ms": round(b["llm_ms"], 3),
            "tool_ms": round(b["tool_ms"], 3),
            "total_ms": round(b["llm_ms"] + b["tool_ms"], 3),
            "prompt_tokens": b["prompt_tokens"] if b["_has_prompt"] else None,
            "completion_tokens": b["completion_tokens"] if b["_has_completion"] else None,
            "llm_calls": b["llm_calls"],
            "tool_calls": b["tool_calls"],
        }
        out.append(row)
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


def markdown_turns(suite: str, turns: list[dict[str, Any]]) -> str:
    lines = [
        f"### Turn rollup: `{suite}`",
        "",
        "| thread_id | turn | llm_ms | tool_ms | total_ms | prompt_tok | "
        "completion_tok | llm_calls | tool_calls |",
        "|-----------|-----:|-------:|--------:|---------:|-----------:|"
        "---------------:|----------:|-----------:|",
    ]
    if not turns:
        lines.append("| *(none)* | — | — | — | — | — | — | 0 | 0 |")
    else:
        for t in turns:
            lines.append(
                f"| `{t['thread_id']}` | {t['turn']} | {t['llm_ms']} | {t['tool_ms']} | "
                f"{t['total_ms']} | {t['prompt_tokens']} | {t['completion_tokens']} | "
                f"{t['llm_calls']} | {t['tool_calls']} |"
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
        turns = aggregate_turns(path)
        summary[suite] = {
            "path": str(path),
            "tools": stats,
            "turns": turns,
            "total_calls": sum(s["count"] for s in stats.values()),
        }
        blocks.append(markdown_table(suite, stats))
        blocks.append(markdown_turns(suite, turns))

    print("\n\n".join(blocks))
    out = args.out_json
    if out is None:
        out = args.paths[0].parent / "tool_calls_aggregate.json"
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    # ponytail: p95 + turn-rollup self-check; no pytest file.
    assert p95([1.0] * 20) == 1.0
    assert p95(list(range(1, 101))) == 95
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(
            json.dumps(
                {
                    "tool": "llm.turn_intent",
                    "latency_ms": 10.0,
                    "ok": True,
                    "retries": 0,
                    "thread_id": "t1",
                    "turn": 1,
                    "prompt_tokens": 5,
                    "completion_tokens": 2,
                }
            )
            + "\n"
        )
        fh.write(
            json.dumps(
                {
                    "tool": "CalcClient.POST /x",
                    "latency_ms": 3.0,
                    "ok": True,
                    "retries": 0,
                    "thread_id": "t1",
                    "turn": 1,
                }
            )
            + "\n"
        )
        demo = Path(fh.name)
    try:
        turns = aggregate_turns(demo)
        assert len(turns) == 1
        assert turns[0]["total_ms"] == 13.0
        assert turns[0]["llm_calls"] == 1 and turns[0]["tool_calls"] == 1
    finally:
        demo.unlink(missing_ok=True)
    raise SystemExit(main())
