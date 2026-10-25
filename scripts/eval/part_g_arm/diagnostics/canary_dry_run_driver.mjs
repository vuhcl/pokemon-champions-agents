// MOCK AUDITS ONLY. Drives a real audit.html in headless Chrome over the DevTools protocol: performs the actions in ACTIONS (click a highlighted span and
// "use pick", select text and add an exception, type an exception, tick reviewed), clicks Export CSV and writes the downloaded CSV to OUT.
// usage: node canary_dry_run_driver.mjs AUDIT_HTML ACTIONS_JSON OUT_CSV   (CHROME=/path/to/chrome overrides the macOS default)
import {spawn} from 'node:child_process';
import fs from 'node:fs';
const [HTML, ACTIONS, OUT] = process.argv.slice(2);
const actions = JSON.parse(fs.readFileSync(ACTIONS, 'utf8'));
const chrome = spawn(process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  ['--headless=new','--remote-debugging-port=9335','--user-data-dir='+fs.mkdtempSync((process.env.TMPDIR || '/tmp/') + 'chrome-dry-run-'),'--no-first-run','--no-default-browser-check','--disable-gpu','about:blank'], {stdio:'ignore'});
const sleep = ms => new Promise(r => setTimeout(r, ms));
let targets;
for (let i=0;i<50;i++){ try { targets = await (await fetch('http://127.0.0.1:9335/json/list')).json(); if (targets.length) break; } catch(e){} await sleep(200); }
const ws = new WebSocket(targets.find(t => t.type === 'page').webSocketDebuggerUrl);
await new Promise(r => ws.addEventListener('open', r));
let id = 0; const pend = new Map();
ws.addEventListener('message', ev => { const m = JSON.parse(ev.data); if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); } });
const send = (method, params={}) => new Promise(res => { const i = ++id; pend.set(i, res); ws.send(JSON.stringify({id:i, method, params})); });
const ev = async expr => { const r = await send('Runtime.evaluate', {expression: expr, awaitPromise: true, returnByValue: true}); if (r.result.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails)); return r.result.result.value; };
const log = [];
try {
  await send('Page.enable'); await send('Page.navigate', {url: 'file://' + HTML}); await sleep(1500);
  await ev("localStorage.clear()"); await send('Page.reload'); await sleep(1200);
  for (const a of actions) {
    const J = JSON.stringify;
    if (a.mode === 'click_mark_usepick') {
      const r = await ev(`(() => { const s = document.getElementById(${J(a.item)}); s.querySelector('.addex').click();            // an empty exception row first
        const m = [...s.querySelectorAll('mark.hl')].find(x => x.textContent === ${J(a.text)}); if (!m) return 'no highlighted span with that text';
        m.click(); const row = s.querySelector('.ex'); const sel = row.querySelector('.etype'); sel.value = ${J(a.type)}; sel.dispatchEvent(new Event('change', {bubbles:true}));
        s.querySelector('.ex .usepick').click(); return s.querySelector('.ex .eclaim').value; })()`);
      log.push([a.name, 'claim_text after use-pick: ' + J(r)]);
    } else if (a.mode === 'select') {
      const r = await ev(`(() => { const s = document.getElementById(${J(a.item)}); const box = s.querySelector('.text'); const full = box.textContent; const at = full.indexOf(${J(a.text)}); if (at < 0) return 'text not found';
        const w = document.createTreeWalker(box, NodeFilter.SHOW_TEXT); let pos = 0, n, start, end; const range = document.createRange();
        while ((n = w.nextNode())) { const len = n.textContent.length; if (!start && at < pos + len) { range.setStart(n, at - pos); start = true; } if (start && at + ${a.text.length} <= pos + len) { range.setEnd(n, at + ${a.text.length} - pos); break; } pos += len; }
        const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range); box.dispatchEvent(new MouseEvent('mouseup', {bubbles:true}));
        s.querySelector('.addex').click(); const row = s.querySelector('.ex'); const t = row.querySelector('.etype'); t.value = ${J(a.type)}; t.dispatchEvent(new Event('change', {bubbles:true}));
        return [s.querySelector('.picked').textContent, row.querySelector('.eclaim').value]; })()`);
      log.push([a.name, 'picked/claim_text: ' + J(r)]);
    } else if (a.mode === 'typed') {
      await ev(`(() => { const s = document.getElementById(${J(a.item)}); s.querySelector('.addex').click(); const row = s.querySelector('.ex'); const t = row.querySelector('.etype'); t.value = ${J(a.type)}; t.dispatchEvent(new Event('change', {bubbles:true}));
        const c = row.querySelector('.eclaim'); c.value = ${J(a.claim)}; c.dispatchEvent(new Event('input', {bubbles:true})); })()`);
      log.push([a.name, 'typed']);
    } else if (a.mode === 'review') {
      await ev(`(() => { const c = document.getElementById(${J(a.item)}).querySelector('.rev'); c.checked = true; c.dispatchEvent(new Event('change', {bubbles:true})); })()`);
      log.push([a.name, 'ticked']);
    }
  }
  const csv = await ev(`(async () => { let blob; URL.createObjectURL = b => { blob = b; return 'blob:x'; }; HTMLAnchorElement.prototype.click = function(){};
    document.getElementById('exportcsv').click(); return await blob.text(); })()`);
  fs.writeFileSync(OUT, csv);
  log.push(['status', await ev("document.getElementById('status').textContent")]);
} catch (e) { log.push(['ERROR', String(e).slice(0, 400)]); }
for (const l of log) console.log(l.join(' :: '));
chrome.kill(); process.exit(0);
