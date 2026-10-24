#!/usr/bin/env python3
"""Audit view for a sampled set of items (ADR-060: no recommender imports).

For each sampled item: the final text with the extracted spans highlighted, the extracted claims with their verdicts, the key values,
and the item's tool output collapsed. Writes audit.html and an empty-to-fill audit.csv (item_id, reviewed, exception_type, claim_text, note;
exception_type is one of missed_claim | wrong_extraction | wrong_verdict | other). The page has a reviewed checkbox per answer, an add-exception control
(type, claim text picked by clicking a highlighted span or selecting text, note; several per answer), autosave to localStorage keyed by the sample id
list's sha256, Export CSV (one row per exception plus one per reviewed clean answer, same columns) and Clear. It prints no headline figure: the false rate stays withheld until
the exception log is committed and hashed (see scorer.py).

    python scripts/eval/part_g_v4/audit_view.py --answers answers.jsonl --battery claim_battery.json --out DIR (--size 100 --seed 0 | --ids-file F) [--split-file F --half P]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
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

# The CSV export logic lives in JavaScript (the page has no server). It is kept as pure functions in this string so a test can run them under node.
EXPORT_JS = r"""
function csvField(v) { v = String(v == null ? '' : v); return /[",\r\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }
function buildRows(ids, state) {
  const rows = [];
  for (const id of ids) {
    const reviewed = !!(state.reviewed || {})[id];
    const ex = (state.exceptions || {})[id] || [];
    for (const e of ex) rows.push([id, reviewed ? 'y' : 'n', e.type || '', e.claim || '', e.note || '']);
    if (reviewed && ex.length === 0) rows.push([id, 'y', '', '', '']);
  }
  return rows;
}
function toCsv(rows) {
  const head = ['item_id', 'reviewed', 'exception_type', 'claim_text', 'note'];
  return [head].concat(rows).map(r => r.map(csvField).join(',')).join('\r\n') + '\r\n';
}
"""

PAGE_JS = r"""
const KEY = 'partg-audit-' + SAMPLE_SHA;
let state = { reviewed: {}, exceptions: {} };
const pending = {};
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
function updateCount() { document.getElementById('count').textContent = IDS.filter(i => state.reviewed[i]).length + ' of ' + IDS.length + ' reviewed'; }
function esc(t) { const d = document.createElement('div'); d.textContent = t; return d.innerHTML.replace(/"/g, '&quot;'); }
function rowHtml(e, k) {
  const opts = ['', ...TYPES].map(t => '<option value="' + t + '"' + (e.type === t ? ' selected' : '') + '>' + (t || '(choose type)') + '</option>').join('');
  return '<div class="ex" data-k="' + k + '"><select class="etype' + (e.type ? '' : ' unset') + '">' + opts + '</select> <input class="eclaim" placeholder="claim_text" value="' + esc(e.claim) +
    '"> <input class="enote" placeholder="note" value="' + esc(e.note) + '"> <button type="button" class="usepick">use pick</button> <button type="button" class="rmex">remove</button></div>';
}
function renderExceptions(id) {
  const box = document.querySelector('.review[data-id="' + id + '"]');
  box.querySelector('.rev').checked = !!state.reviewed[id];
  box.querySelector('.exlist').innerHTML = (state.exceptions[id] || []).map((e, k) => rowHtml(e, k)).join('');
}
function renderAll() { IDS.forEach(renderExceptions); updateCount(); }
function pick(id, text) {
  text = (text || '').trim(); if (!text) return;
  pending[id] = text;
  const sp = document.querySelector('.review[data-id="' + id + '"] .picked'); sp.textContent = 'picked: ' + (text.length > 60 ? text.slice(0, 57) + '...' : text);
}
document.addEventListener('click', ev => {
  const t = ev.target, sec = t.closest && t.closest('section'); if (!sec) return;
  const id = sec.id;
  if (t.matches('mark.hl')) pick(id, t.textContent);
  else if (t.matches('.addex')) {
    (state.exceptions[id] = state.exceptions[id] || []).push({ type: '', claim: pending[id] || '', note: '' });
    state.reviewed[id] = true; renderExceptions(id); save();
  } else if (t.matches('.rmex')) { state.exceptions[id].splice(+t.closest('.ex').dataset.k, 1); renderExceptions(id); save(); }
  else if (t.matches('.usepick')) { const k = +t.closest('.ex').dataset.k; if (pending[id]) { state.exceptions[id][k].claim = pending[id]; renderExceptions(id); save(); } }
});
document.addEventListener('mouseup', ev => {
  const box = ev.target.closest && ev.target.closest('.text'); if (!box) return;
  const sel = window.getSelection ? window.getSelection().toString() : '';
  if (sel.trim()) pick(box.closest('section').id, sel);
});
document.addEventListener('change', ev => {
  const t = ev.target, sec = t.closest && t.closest('section'); if (!sec) return;
  const id = sec.id;
  if (t.matches('.rev')) { state.reviewed[id] = t.checked; save(); }
  else if (t.matches('.etype')) { state.exceptions[id][+t.closest('.ex').dataset.k].type = t.value; t.classList.toggle('unset', !t.value); save(); }
});
document.addEventListener('input', ev => {
  const t = ev.target, sec = t.closest && t.closest('section'); if (!sec) return;
  const id = sec.id;
  if (t.matches('.eclaim')) { state.exceptions[id][+t.closest('.ex').dataset.k].claim = t.value; save(); }
  else if (t.matches('.enote')) { state.exceptions[id][+t.closest('.ex').dataset.k].note = t.value; save(); }
});
document.getElementById('exportcsv').addEventListener('click', () => {
  const blob = new Blob([toCsv(buildRows(IDS, state))], { type: 'text/csv' });
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'audit_exceptions.csv';
  document.body.appendChild(a); a.click(); a.remove();
});
document.getElementById('clearall').addEventListener('click', () => {
  if (!confirm('Clear every reviewed mark and exception on this page? This cannot be undone.')) return;
  state = { reviewed: {}, exceptions: {} }; renderAll(); save();
});
loadState(); renderAll();
"""


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
        out.append(f'<mark class="hl" style="background:{colour}" title="{html.escape(", ".join(sorted(verdicts)))}">{html.escape(text[lo:hi])}</mark>')
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
            f'<div class="review" data-id="{html.escape(item["id"])}"><label><input type="checkbox" class="rev"> reviewed</label> '
            f'<button type="button" class="addex">add exception</button> <span class="picked" title="the last highlighted span clicked or text selected in this answer"></span>'
            f'<div class="exlist"></div></div>'
            f'<table><tr><th>kind</th><th>claim</th><th>verdict</th><th>line</th><th>flag</th><th>reason</th></tr>{rows}</table>'
            f'<details><summary>key values</summary><pre>{html.escape(keys)}</pre></details><h4>Tool output</h4>{tools}</section>')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--answers", type=Path, required=True)
    ap.add_argument("--battery", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--size", type=int, default=None, help="sample size (fixed-seed sample of the answered items)")
    ap.add_argument("--ids-file", type=Path, default=None, help='JSON {"ids": [...]} instead of a sample (a committed id list)')
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--split-file", type=Path, default=None)
    ap.add_argument("--half", choices=("P", "T"), default=None)
    args = ap.parse_args()
    items = {i["id"]: i for i in json.loads(args.battery.read_text())["items"] if i.get("gated", True)}
    if args.half:
        keep = {i for v in json.loads(args.split_file.read_text())[args.half].values() for i in v}
        items = {k: v for k, v in items.items() if k in keep}
    answers = {r["id"]: r for r in map(json.loads, args.answers.read_text().splitlines()) if r["id"] in items}
    if args.ids_file:
        ids = json.loads(args.ids_file.read_text())["ids"]
        missing = [i for i in ids if i not in answers]
        if missing:
            raise SystemExit(f"ids not in the answers (or outside the chosen half): {missing[:5]}")
    elif args.size:
        ids = scorer.audit_sample(sorted(answers), args.size, args.seed)
    else:
        raise SystemExit("give --size or --ids-file")
    args.out.mkdir(parents=True, exist_ok=True)
    body = []
    with (args.out / "audit.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_COLUMNS)
        for i in ids:
            claims = extractors.extract_item(items[i], answers[i])
            body.append(render_item(items[i], answers[i], claims))
            w.writerow([i, "n", "", "", ""])  # one row per sampled item to start; the reviewer adds a row per exception
    sample_sha = hashlib.sha256("\n".join(ids).encode()).hexdigest()
    origin = "ids from a committed list" if args.ids_file else f"seed {args.seed}"
    head = (
        "<!doctype html><meta charset=utf-8><title>Part G audit view</title><style>body{font:14px sans-serif;max-width:960px;margin:1em auto;padding-top:3.2em}"
        "section{border-top:2px solid #888;margin-top:2em}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:2px 6px}"
        ".text{background:#f7f7f7;padding:.6em;margin:.6em 0}pre{white-space:pre-wrap}mark.hl{cursor:pointer}"
        "#bar{position:fixed;top:0;left:0;right:0;background:#fff;border-bottom:1px solid #888;padding:.5em 1em;z-index:5}"
        "#status.ok{color:#176b17}#status.warn{color:#9a6700}#status.bad{color:#b42318;font-weight:bold}"
        ".review{margin:.4em 0;padding:.4em;background:#eef3fb}.ex{margin:.3em 0}.ex input{width:22em}.ex .enote{width:18em}select.unset{border:2px solid #b42318}"
        ".picked{color:#555;margin-left:.6em}</style>"
        '<div id="bar"><b>Part G audit view</b> &nbsp; <span id="count"></span> &nbsp; <span id="status" class="warn">unsaved</span> &nbsp;'
        '<button type="button" id="exportcsv">Export CSV</button> <button type="button" id="clearall">Clear</button></div>'
        f"<h1>Part G audit view</h1><p>{len(ids)} items sampled, {origin}. Exception types: {', '.join(EXCEPTION_TYPES)}. "
        "Click a highlighted span or select text in an answer to pick it, then add an exception. No headline figure is shown here.</p>")
    script = ("<script>const IDS = " + json.dumps(ids).replace("</", "<\\/") + ";const SAMPLE_SHA = " + json.dumps(sample_sha) + ";const TYPES = "
              + json.dumps(list(EXCEPTION_TYPES)) + ";" + EXPORT_JS + PAGE_JS + "</script>")
    (args.out / "audit.html").write_text(head + "".join(body) + script)
    print(f"wrote {args.out / 'audit.html'} and audit.csv for {len(ids)} items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
