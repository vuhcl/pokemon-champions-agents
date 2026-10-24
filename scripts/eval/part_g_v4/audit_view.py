#!/usr/bin/env python3
"""Audit view for a sampled set of items (ADR-060: no recommender imports).

For each sampled item: the final text with the extracted spans highlighted, the extracted claims with their verdicts, the key values,
and the item's tool output collapsed. Writes audit.html and an empty-to-fill audit.csv (item_id, reviewed, exception_type, claim_text, note;
exception_type is one of missed_claim | wrong_extraction | wrong_verdict | other). It prints no headline figure: the false rate stays withheld until
the exception log is committed and hashed (see scorer.py).

    python scripts/eval/part_g_v4/audit_view.py --answers answers.jsonl --battery claim_battery.json --out DIR --size 100 --seed 0 [--split-file F --half P]
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extractors  # noqa: E402
import scorer  # noqa: E402

EXCEPTION_TYPES = ("missed_claim", "wrong_extraction", "wrong_verdict", "other")
CSV_COLUMNS = ["item_id", "reviewed", "exception_type", "claim_text", "note"]
COLORS = {"TRUE": "#cfe8cf", "FALSE": "#f4c7c3", "UNVERIFIABLE": "#fde9b6", "None": "#ddd"}


def highlight(text: str, claims) -> str:
    """Escape the text and wrap each claim's span in <mark>; overlapping spans are merged into the first one."""
    spans = sorted({c.span for c in claims if c.span}, key=lambda s: (s[0], -s[1]))
    out, pos = [], 0
    for lo, hi in spans:
        if lo < pos:
            continue
        out.append(html.escape(text[pos:lo]))
        verdicts = {str(c.verdict.value if c.verdict else None) for c in claims if c.span == (lo, hi)}
        colour = COLORS[sorted(verdicts)[0]] if len(verdicts) == 1 else "#e3d4f0"
        out.append(f'<mark style="background:{colour}" title="{html.escape(", ".join(sorted(verdicts)))}">{html.escape(text[lo:hi])}</mark>')
        pos = hi
    out.append(html.escape(text[pos:]))
    return "".join(out).replace("\n", "<br>")


def render_item(item: dict, answer: dict, claims) -> str:
    rows = "".join(
        f"<tr><td>{html.escape(c.kind)}</td><td>{html.escape(c.proposition)}</td><td style=\"background:{COLORS[str(c.verdict.value if c.verdict else None)]}\">"
        f"{c.verdict.value if c.verdict else 'no verdict'}</td><td>{html.escape(c.line)}</td><td>{'copied' if c.copied_unchanged else ''}</td><td>{html.escape(c.reason)}</td></tr>"
        for c in claims)
    tools = "".join(
        f"<details><summary>{html.escape(t['name'])} {html.escape(json.dumps(t['args'], ensure_ascii=False)[:90])}</summary>"
        f"<pre>{html.escape(json.dumps(t['result'], indent=1, ensure_ascii=False))}</pre></details>" for t in answer.get("tool_calls") or [])
    keys = json.dumps([c["ground_truth"] for c in item["claims"]], indent=1, ensure_ascii=False)
    return (f'<section id="{html.escape(item["id"])}"><h2>{html.escape(item["id"])} <small>{html.escape(item["claim_type"])}</small></h2>'
            f'<p><b>Prompt:</b> {html.escape(item["prompt"])}</p><div class="text">{highlight(answer["final_text"], claims)}</div>'
            f'<table><tr><th>kind</th><th>claim</th><th>verdict</th><th>line</th><th>flag</th><th>reason</th></tr>{rows}</table>'
            f'<details><summary>key values</summary><pre>{html.escape(keys)}</pre></details><h4>Tool output</h4>{tools}</section>')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--answers", type=Path, required=True)
    ap.add_argument("--battery", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--size", type=int, required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--split-file", type=Path, default=None)
    ap.add_argument("--half", choices=("P", "T"), default=None)
    args = ap.parse_args()
    items = {i["id"]: i for i in json.loads(args.battery.read_text())["items"] if i.get("gated", True)}
    if args.half:
        keep = {i for v in json.loads(args.split_file.read_text())[args.half].values() for i in v}
        items = {k: v for k, v in items.items() if k in keep}
    answers = {r["id"]: r for r in map(json.loads, args.answers.read_text().splitlines()) if r["id"] in items}
    ids = scorer.audit_sample(sorted(answers), args.size, args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    body = []
    with (args.out / "audit.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_COLUMNS)
        for i in ids:
            claims = extractors.extract_item(items[i], answers[i])
            body.append(render_item(items[i], answers[i], claims))
            w.writerow([i, "n", "", "", ""])  # one row per sampled item to start; the reviewer adds a row per exception
    (args.out / "audit.html").write_text(
        "<!doctype html><meta charset=utf-8><title>Part G audit view</title><style>body{font:14px sans-serif;max-width:960px;margin:1em auto}"
        "section{border-top:2px solid #888;margin-top:2em}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:2px 6px}"
        ".text{background:#f7f7f7;padding:.6em;margin:.6em 0}pre{white-space:pre-wrap}</style><h1>Part G audit view</h1>"
        f"<p>{len(ids)} items sampled, seed {args.seed}. Exception types: {', '.join(EXCEPTION_TYPES)}. No headline figure is shown here.</p>" + "".join(body))
    print(f"wrote {args.out / 'audit.html'} and audit.csv for {len(ids)} items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
