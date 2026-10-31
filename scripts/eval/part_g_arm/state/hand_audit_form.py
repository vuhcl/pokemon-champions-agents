"""Hand-audit HTML form for the state arm (gemma-blind).

Based on scripts/eval/part_g_v4/audit_view.py (HTML builder, localStorage,
Export CSV / Clear, Node-testable JS CSV helpers).

Deliberate differences from Part G:
- Part G shows scorer/extractor claim verdicts on the page (not gemma).
- This form shows neither gemma nor scorer verdicts.
- Verdicts are per rubric point: pass | fail | not_applicable; plus overall + note.
- Export download name: hand_audit_export.csv
  columns: row_id, turn, rubric_point_id, verdict, overall, note
  (one line per row-turn × rubric point).

Judge JSON stays in a separate file; merge only after Vu exports.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
CSV_COLUMNS = ["row_id", "turn", "rubric_point_id", "verdict", "overall", "note"]
VERDICTS = ("pass", "fail", "not_applicable")

EXPORT_JS = r"""
function csvField(v) { v = String(v == null ? '' : v); return /[",\r\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }
function buildRows(sections, state) {
  const rows = [];
  for (const sec of sections) {
    const st = (state.bySection || {})[sec.id] || {};
    const overall = st.overall || '';
    const note = st.note || '';
    for (const p of sec.points) {
      const v = ((st.points || {})[p.id]) || '';
      rows.push([sec.row_id, String(sec.turn), p.id, v, overall, note]);
    }
  }
  return rows;
}
function toCsv(rows) {
  const head = ['row_id', 'turn', 'rubric_point_id', 'verdict', 'overall', 'note'];
  return [head].concat(rows).map(r => r.map(csvField).join(',')).join('\r\n') + '\r\n';
}
"""

PAGE_JS = r"""
const KEY = 'state-arm-audit-' + SAMPLE_SHA;
let state = { bySection: {} };
function setStatus(t, cls) { const el = document.getElementById('status'); el.textContent = t; el.className = cls; }
function loadState() {
  try { const s = localStorage.getItem(KEY); if (s) state = JSON.parse(s); setStatus(s ? 'saved (restored)' : 'saved', 'ok'); }
  catch (e) { setStatus('not saved: browser storage unavailable', 'bad'); }
}
function save() {
  setStatus('unsaved', 'warn');
  try { localStorage.setItem(KEY, JSON.stringify(state)); setStatus('saved', 'ok'); }
  catch (e) { setStatus('not saved: browser storage unavailable', 'bad'); }
  updateCount();
}
function updateCount() {
  const n = SECTIONS.filter(s => {
    const st = (state.bySection || {})[s.id] || {};
    return st.overall === 'pass' || st.overall === 'fail';
  }).length;
  document.getElementById('count').textContent = n + ' of ' + SECTIONS.length + ' overall set';
}
function ensure(id) {
  state.bySection = state.bySection || {};
  if (!state.bySection[id]) state.bySection[id] = { points: {}, overall: '', note: '' };
  if (!state.bySection[id].points) state.bySection[id].points = {};
  return state.bySection[id];
}
function renderSection(sec) {
  const st = ensure(sec.id);
  const box = document.querySelector('.review[data-id="' + sec.id + '"]');
  if (!box) return;
  for (const p of sec.points) {
    const sel = box.querySelector('select.pverdict[data-pid="' + p.id + '"]');
    if (sel) sel.value = st.points[p.id] || '';
  }
  const ov = box.querySelector('select.overall');
  if (ov) ov.value = st.overall || '';
  const note = box.querySelector('textarea.note');
  if (note) note.value = st.note || '';
}
function renderAll() { SECTIONS.forEach(renderSection); updateCount(); }
document.addEventListener('change', ev => {
  const t = ev.target, sec = t.closest && t.closest('section'); if (!sec) return;
  const id = sec.id;
  const st = ensure(id);
  if (t.matches('select.pverdict')) { st.points[t.dataset.pid] = t.value; save(); }
  else if (t.matches('select.overall')) { st.overall = t.value; save(); }
});
document.addEventListener('input', ev => {
  const t = ev.target, sec = t.closest && t.closest('section'); if (!sec) return;
  if (t.matches('textarea.note')) { ensure(sec.id).note = t.value; save(); }
});
document.getElementById('exportcsv').addEventListener('click', () => {
  const blob = new Blob([toCsv(buildRows(SECTIONS, state))], { type: 'text/csv' });
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'hand_audit_export.csv';
  document.body.appendChild(a); a.click(); a.remove();
});
document.getElementById('clearall').addEventListener('click', () => {
  if (!confirm('Clear every verdict and note on this page? This cannot be undone.')) return;
  state = { bySection: {} }; renderAll(); save();
});
loadState(); renderAll();
"""


def split_acceptance_points(acceptance: str) -> list[dict[str, str]]:
    """Split acceptance on ';' into rubric points; else one point id=acceptance."""
    text = (acceptance or "").strip()
    if not text:
        return [{"id": "acceptance", "text": "(no acceptance text)"}]
    parts = [p.strip() for p in text.split(";") if p.strip()]
    if len(parts) <= 1:
        return [{"id": "acceptance", "text": text}]
    return [{"id": f"p{i+1}", "text": p} for i, p in enumerate(parts)]


def _tools_html(tool_calls: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for t in tool_calls or []:
        name = html.escape(str(t.get("name") or ""))
        args = html.escape(json.dumps(t.get("args") or t.get("arguments") or {}, ensure_ascii=False)[:120])
        result = html.escape(json.dumps(t.get("result"), indent=1, ensure_ascii=False)[:4000])
        chunks.append(
            f"<details><summary>{name} {args}</summary><pre>{result}</pre></details>"
        )
    return "".join(chunks) or "<p><i>no tool calls</i></p>"


def section_id(row_id: str, turn: int) -> str:
    return f"{row_id}__t{turn}"


def _key_text_with_errata(row_id: str, acceptance: str) -> str:
    from scripts.eval.part_g_arm.state.errata_read import (
        acceptance_with_key_overrides,
        key_override_hand_note,
        set_answer_hand_note,
    )

    text = acceptance_with_key_overrides(row_id, acceptance)
    notes = [n for n in (set_answer_hand_note(row_id), key_override_hand_note(row_id)) if n]
    if not notes:
        return text
    return "\n".join([text, *notes]) if text else "\n".join(notes)


def _points_with_set_errata(row_id: str, points: list[dict[str, str]]) -> list[dict[str, str]]:
    """Append one rubric point for allowed_not_required members when errata says so."""
    from scripts.eval.part_g_arm.state.errata_read import allowed_not_required, set_answer_errata

    entry = set_answer_errata(row_id)
    members = sorted(allowed_not_required(row_id))
    if not entry or not members:
        return points
    return [
        *points,
        {
            "id": "set_errata_allowed_not_required",
            "text": (
                f"allowed_not_required {{{', '.join(members)}}}: naming is not a false claim; "
                f"omitting is not incomplete. Required set members still required."
            ),
        },
    ]


def build_sections_from_transcript(
    transcript: list[dict[str, Any]],
    *,
    acceptance_by_id: dict[str, str] | None = None,
    points_by_id: dict[str, list[dict[str, str]]] | None = None,
    ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Build form sections from a harness/request_set transcript."""
    acceptance_by_id = acceptance_by_id or {}
    points_by_id = points_by_id or {}
    sections: list[dict[str, Any]] = []
    for entry in transcript:
        rid = entry.get("id")
        if not isinstance(rid, str):
            continue
        if ids is not None and rid not in ids:
            continue
        turns = list(entry.get("turns") or [])
        raw_acc = acceptance_by_id.get(rid, "")
        from scripts.eval.part_g_arm.state.errata_read import acceptance_with_key_overrides

        acc = acceptance_with_key_overrides(rid, raw_acc)
        base_points = points_by_id.get(rid) or split_acceptance_points(acc)
        points = _points_with_set_errata(rid, base_points)
        key_text = _key_text_with_errata(rid, raw_acc)
        for i, turn in enumerate(turns, start=1):
            sections.append(
                {
                    "id": section_id(rid, i),
                    "row_id": rid,
                    "turn": i,
                    "key_text": key_text,
                    "points": points,
                    "user": turn.get("user") or "",
                    "final_text": turn.get("final_text") or "",
                    "tool_calls": turn.get("tool_calls") or [],
                    "mechanical_class": turn.get("mechanical_class"),
                }
            )
    return sections


def build_sections_from_diff(
    differ: list[dict[str, Any]],
    transcripts_by_run: dict[int, list[dict[str, Any]]],
    *,
    acceptance_by_id: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Second sheet: only differing runs’ turns (not primary duplicates)."""
    acceptance_by_id = acceptance_by_id or {}
    by_run_id: dict[int, dict[str, dict[str, Any]]] = {}
    for run, rows in transcripts_by_run.items():
        by_run_id[run] = {r["id"]: r for r in rows if isinstance(r, dict) and "id" in r}
    sections: list[dict[str, Any]] = []
    for d in differ:
        rid = d.get("id")
        vs = d.get("vs_run")
        if not rid or vs not in by_run_id:
            continue
        entry = by_run_id[vs].get(rid)
        if not entry:
            continue
        # Prefer only turns listed in diffs; else all turns of that run.
        turn_nums = sorted(
            {
                x.get("turn")
                for x in d.get("diffs") or []
                if isinstance(x.get("turn"), int)
            }
        )
        turns = list(entry.get("turns") or [])
        indices = turn_nums or list(range(1, len(turns) + 1))
        from scripts.eval.part_g_arm.state.errata_read import acceptance_with_key_overrides

        raw_acc = acceptance_by_id.get(rid, "")
        points = split_acceptance_points(acceptance_with_key_overrides(rid, raw_acc))
        for tnum in indices:
            if tnum < 1 or tnum > len(turns):
                continue
            turn = turns[tnum - 1]
            sections.append(
                {
                    "id": f"{rid}__run{vs}__t{tnum}",
                    "row_id": rid,
                    "turn": tnum,
                    "key_text": _key_text_with_errata(rid, raw_acc) + f" [vs run {vs}]",
                    "points": points,
                    "user": turn.get("user") or "",
                    "final_text": turn.get("final_text") or "",
                    "tool_calls": turn.get("tool_calls") or [],
                    "mechanical_class": turn.get("mechanical_class"),
                }
            )
    return sections


def render_section(sec: dict[str, Any]) -> str:
    opts = "".join(f'<option value="{v}">{v}</option>' for v in ("",) + VERDICTS)
    point_rows = "".join(
        f"<tr><td>{html.escape(p['id'])}</td><td>{html.escape(p['text'])}</td>"
        f'<td><select class="pverdict" data-pid="{html.escape(p["id"])}">{opts}</select></td></tr>'
        for p in sec["points"]
    )
    return (
        f'<section id="{html.escape(sec["id"])}">'
        f'<h2>{html.escape(sec["row_id"])} turn {sec["turn"]} '
        f'<small>class={html.escape(str(sec.get("mechanical_class")))}</small></h2>'
        f'<p><b>User:</b> {html.escape(sec.get("user") or "")}</p>'
        f'<p><b>Key / acceptance:</b> {html.escape(sec.get("key_text") or "")}</p>'
        f'<div class="text"><b>Final text</b><br>{html.escape(sec.get("final_text") or "").replace(chr(10), "<br>")}</div>'
        f"<h4>Tool calls</h4>{_tools_html(sec.get('tool_calls') or [])}"
        f'<div class="review" data-id="{html.escape(sec["id"])}">'
        f'<table><tr><th>point</th><th>rubric</th><th>verdict</th></tr>{point_rows}</table>'
        f'<p>Overall: <select class="overall">{opts}</select></p>'
        f'<p>Note:<br><textarea class="note" rows="2" cols="80"></textarea></p>'
        f"</div></section>"
    )


def write_form(sections: list[dict[str, Any]], out_dir: Path, *, title: str = "State arm hand audit") -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    sample_sha = hashlib.sha256("\n".join(s["id"] for s in sections).encode()).hexdigest()
    # Strip heavy tool result blobs from the SECTIONS constant (already rendered in HTML).
    slim = [
        {
            "id": s["id"],
            "row_id": s["row_id"],
            "turn": s["turn"],
            "points": s["points"],
        }
        for s in sections
    ]
    head = (
        "<!doctype html><meta charset=utf-8>"
        f"<title>{html.escape(title)}</title>"
        "<style>body{font:14px sans-serif;max-width:960px;margin:1em auto;padding-top:3.2em}"
        "section{border-top:2px solid #888;margin-top:2em}table{border-collapse:collapse}"
        "td,th{border:1px solid #ccc;padding:2px 6px}"
        ".text{background:#f7f7f7;padding:.6em;margin:.6em 0}pre{white-space:pre-wrap}"
        "#bar{position:fixed;top:0;left:0;right:0;background:#fff;border-bottom:1px solid #888;padding:.5em 1em;z-index:5}"
        "#status.ok{color:#176b17}#status.warn{color:#9a6700}#status.bad{color:#b42318;font-weight:bold}"
        ".review{margin:.4em 0;padding:.4em;background:#eef3fb}textarea.note{width:100%}</style>"
        f'<div id="bar"><b>{html.escape(title)}</b> &nbsp; <span id="count"></span> &nbsp; '
        '<span id="status" class="warn">unsaved</span> &nbsp;'
        '<button type="button" id="exportcsv">Export CSV</button> '
        '<button type="button" id="clearall">Clear</button></div>'
        f"<h1>{html.escape(title)}</h1>"
        f"<p>{len(sections)} turn sections. No model/judge verdict is shown on this page. "
        "Export CSV downloads as hand_audit_export.csv (one line per row-turn × rubric point). "
        "Based on part_g_v4/audit_view.py; scorer/gemma verdicts deliberately omitted.</p>"
    )
    body = "".join(render_section(s) for s in sections)
    script = (
        "<script>const SECTIONS = "
        + json.dumps(slim).replace("</", "<\\/")
        + ";const SAMPLE_SHA = "
        + json.dumps(sample_sha)
        + ";"
        + EXPORT_JS
        + PAGE_JS
        + "</script>"
    )
    html_path = out_dir / "hand_audit.html"
    html_path.write_text(head + body + script, encoding="utf-8")
    csv_path = out_dir / "hand_audit.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_COLUMNS)
        for s in sections:
            for p in s["points"]:
                w.writerow([s["row_id"], s["turn"], p["id"], "", "", ""])
    sha = hashlib.sha256(html_path.read_bytes()).hexdigest()
    return {"html": str(html_path), "csv": str(csv_path), "sha256": sha, "sections": str(len(sections))}


def expected_csv_line_count(sections: list[dict[str, Any]]) -> int:
    return sum(len(s["points"]) for s in sections)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transcript", type=Path, required=True, help="transcript.json")
    parser.add_argument("--out", type=Path, required=True, help="output dir (outside repo)")
    parser.add_argument("--acceptance-json", type=Path, default=None, help='{"ROW": "acceptance text", ...}')
    parser.add_argument("--ids", type=Path, default=None, help='JSON {"ids": [...]} filter')
    parser.add_argument("--diff-json", type=Path, default=None, help="compare_runs differ list for --diff-runs sheet")
    parser.add_argument("--run2-transcript", type=Path, default=None)
    parser.add_argument("--run3-transcript", type=Path, default=None)
    parser.add_argument("--title", default="State arm hand audit")
    args = parser.parse_args(argv)

    acceptance: dict[str, str] = {}
    if args.acceptance_json and args.acceptance_json.is_file():
        acceptance = json.loads(args.acceptance_json.read_text(encoding="utf-8"))

    if args.diff_json:
        differ = json.loads(args.diff_json.read_text(encoding="utf-8"))
        if isinstance(differ, dict):
            differ = differ.get("differ") or []
        transcripts_by_run: dict[int, list[dict[str, Any]]] = {}
        if args.run2_transcript:
            transcripts_by_run[2] = json.loads(args.run2_transcript.read_text(encoding="utf-8"))
        if args.run3_transcript:
            transcripts_by_run[3] = json.loads(args.run3_transcript.read_text(encoding="utf-8"))
        sections = build_sections_from_diff(differ, transcripts_by_run, acceptance_by_id=acceptance)
    else:
        transcript = json.loads(args.transcript.read_text(encoding="utf-8"))
        ids = None
        if args.ids:
            ids = set(json.loads(args.ids.read_text(encoding="utf-8"))["ids"])
        sections = build_sections_from_transcript(
            transcript, acceptance_by_id=acceptance, ids=ids
        )

    meta = write_form(sections, args.out, title=args.title)
    print(
        f"wrote {meta['html']} sha256={meta['sha256']} sections={meta['sections']} "
        f"csv_lines={expected_csv_line_count(sections)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
