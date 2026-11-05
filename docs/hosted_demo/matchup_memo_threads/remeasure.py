"""Re-measure per-thread matchup memo with the #380 schedules.

Does not change product code. One process per run, shared SqliteSaver,
fake parsers, calc on 127.0.0.1:4173.

    uv run python docs/hosted_demo/matchup_memo_threads/remeasure.py --run alone
    uv run python docs/hosted_demo/matchup_memo_threads/remeasure.py --all
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault(
    "RECOMMENDER_TOOL_LOG", "/tmp/hosted-demo-matchup-memo-threads/tool_log.jsonl"
)

from langchain_core.runnables import RunnableLambda

import recommender.matchup as matchup
from recommender.calc_client import CalcClient
from recommender.checkpointer import open_sqlite_checkpointer
from recommender.graph import compile_graph
from recommender.nodes import SLOT_ATTRS
from recommender.session import DEFAULT_FORMAT_ID, thread_config
from recommender.state import all_locked

HERE = Path(__file__).resolve().parent
OUT = HERE / "results"
FIXTURES = (
    Path(__file__).resolve().parents[3] / "tests" / "recommender" / "fixtures"
)
_TLS = threading.local()
_ORIG_GET = matchup._memo_get
_ORIG_PUT = matchup._memo_put
_ORIG_JSON = CalcClient._json_request


def _rec():
    return getattr(_TLS, "rec", None)


def _memo_get(key):
    hit = _ORIG_GET(key)
    rec = _rec()
    if rec is not None and hit is not None:
        rec["hits"] += 1
    return hit


def _memo_put(key, result):
    stored = _ORIG_PUT(key, result)
    rec = _rec()
    if rec is not None:
        if stored is result:
            rec["misses"] += 1
        else:
            rec["hits"] += 1
    return stored


def _json_request(self, method, path, body=None, *, timeout=None):
    t0 = time.perf_counter()
    try:
        return _ORIG_JSON(self, method, path, body, timeout=timeout)
    finally:
        rec = _rec()
        if rec is not None:
            rec["http_n"] += 1
            rec["http_s"] += time.perf_counter() - t0


matchup._memo_get = _memo_get
matchup._memo_put = _memo_put
CalcClient._json_request = _json_request


@dataclass(frozen=True)
class Script:
    name: str
    bootstrap_text: str
    anchor: str
    direction: str | None
    candidate: str
    preference: str


SCRIPT_A = Script("A", "Rain with Pelipper", "Pelipper", "Rain", "yes", "1")
SCRIPT_B = Script("B", "Incineroar", "Incineroar", None, "2", "2")


def _parsers(script: Script):
    def bootstrap(_payload):
        return {
            "direction_text": script.direction,
            "anchor_text": script.anchor,
            "pool_entries": None,
            "delegated": False,
            "ownership_mode": None,
        }

    def turn(_payload):
        return {"turn_intent": "pending_response", "message": "unused"}

    return RunnableLambda(bootstrap), RunnableLambda(turn)


def _locked(state: dict) -> list[str]:
    return [
        str(slot.species.value)
        for slot in state.get("team_draft") or []
        if all_locked(slot) and slot.species.value
    ]


def _choose(script: Script, state: dict) -> str | None:
    pending = state.get("pending_presentation") or {}
    kind = pending.get("kind")
    if kind == "bootstrap_intake":
        return script.bootstrap_text
    if kind == "candidate_selection":
        options = pending.get("options") or []
        if script.candidate == "2" and len(options) >= 2:
            return "2"
        return "yes"
    if kind == "full_build_confirmation":
        return "yes"
    if kind == "completion_preference":
        prefs = list(pending.get("preference_options") or ())
        if script.preference == "2" and len(prefs) >= 2:
            return "2"
        return "1"
    return None


def _j(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (tuple, list)):
        return [_j(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _j(v) for k, v in value.items()}
    return str(value)


def fingerprint(state: dict) -> dict:
    draft = []
    for slot in state.get("team_draft") or []:
        row = {}
        for name in SLOT_ATTRS:
            attr = getattr(slot, name)
            row[name] = {"v": _j(attr.value), "locked": bool(attr.locked)}
        draft.append(row)
    pending = state.get("pending_presentation") or {}
    coverage = []
    for row in state.get("coverage") or []:
        best = row.best_outcome
        caveats = best.caveats
        field = row.forced_field or {}
        coverage.append(
            {
                "threat": (row.threat or {}).get("species"),
                "outcome": best.outcome,
                "severity": best.severity,
                "covering": list(row.covering_slot_indices),
                "flagged": bool(row.flagged),
                "weather": field.get("weather"),
                "terrain": field.get("terrain"),
                "caveats": [
                    caveats.contact_punish_applied,
                    caveats.multi_hit_assumed,
                    caveats.condition_fail,
                    caveats.expanding_force_boosted,
                    caveats.screen_clear_applied,
                    caveats.protect_bypass_applied,
                ],
                "note": best.turn_economy_note,
            }
        )
    spofs = [
        {
            "slot": sp.slot_index,
            "threats": [(t or {}).get("species") for t in sp.threats_lost],
        }
        for sp in state.get("spofs") or []
    ]
    return {
        "draft": draft,
        "pending_kind": pending.get("kind"),
        "options": [
            opt.get("species") or opt.get("option_id")
            for opt in pending.get("options") or []
        ],
        "coverage": coverage,
        "spofs": spofs,
        "discovery_error": _j(state.get("candidate_discovery_error")),
    }


def _blank():
    return {"hits": 0, "misses": 0, "http_n": 0, "http_s": 0.0, "error": None}


class Session:
    def __init__(self, index, script, graph, config, sem):
        self.index = index
        self.script = script
        self.graph = graph
        self.config = config
        self.sem = sem
        self.state: dict = {}
        self.done = False
        self.stop = None
        self.messages: list[dict] = []
        self.error = None

    def _invoke(self, payload):
        if self.sem is None:
            return self.graph.invoke(payload, self.config)
        with self.sem:
            return self.graph.invoke(payload, self.config)

    def start(self) -> None:
        try:
            self.state = self._invoke({"format_id": DEFAULT_FORMAT_ID})
        except Exception as exc:
            self.error = f"init: {exc!r}"
            self.done = True
            self.stop = "init_error"

    def step(self) -> None:
        if self.done:
            return
        if len(_locked(self.state)) >= 6 or len(self.messages) >= 20:
            self.done = True
            self.stop = self.stop or "six_locked"
            return
        kind = (self.state.get("pending_presentation") or {}).get("kind")
        text = _choose(self.script, self.state)
        if text is None:
            self.done = True
            self.stop = f"no_reply:{kind}"
            return
        rec = _blank()
        rec["index"] = len(self.messages) + 1
        rec["kind"] = kind
        rec["text"] = text
        _TLS.rec = rec
        t0 = time.perf_counter()
        try:
            self.state = self._invoke({"pending_input": text})
        except Exception as exc:
            rec["error"] = f"{type(exc).__name__}: {exc}"
            self.error = rec["error"]
            self.done = True
            self.stop = "invoke_error"
        finally:
            rec["wall_s"] = time.perf_counter() - t0
            _TLS.rec = None
        rec["locked_after"] = _locked(self.state) if self.state else []
        self.messages.append(rec)
        if not self.done and len(rec["locked_after"]) >= 6:
            self.done = True
            self.stop = "six_locked"


def _percentile(values, p):
    if not values:
        return None
    ys = sorted(values)
    if len(ys) == 1:
        return ys[0]
    k = math.ceil((p / 100) * len(ys)) - 1
    return ys[min(max(k, 0), len(ys) - 1)]


def _aggregate(sessions, script_name):
    chosen = [s for s in sessions if s.script.name == script_name]
    by: dict[int, list] = {}
    for session in chosen:
        for message in session.messages:
            by.setdefault(message["index"], []).append(message)
    rows = []
    for index in sorted(by):
        msgs = by[index]
        walls = [m["wall_s"] for m in msgs]
        rows.append(
            {
                "index": index,
                "n": len(msgs),
                "kind": msgs[0]["kind"],
                "text": msgs[0]["text"],
                "locked_after": msgs[0]["locked_after"],
                "locked_after_same": len({tuple(m["locked_after"]) for m in msgs}) == 1,
                "wall_p50": _percentile(walls, 50),
                "wall_p95": _percentile(walls, 95),
                "wall_max": max(walls),
                "http_n_p50": _percentile([m["http_n"] for m in msgs], 50),
                "http_s_p50": _percentile([m["http_s"] for m in msgs], 50),
                "hits_p50": _percentile([m["hits"] for m in msgs], 50),
                "miss_p50": _percentile([m["misses"] for m in msgs], 50),
                "errors": sum(1 for m in msgs if m["error"]),
            }
        )
    return rows


def _diffs(a, b, path=""):
    out = []
    if type(a) is not type(b):
        return [(path or "$", type(a).__name__, type(b).__name__)]
    if isinstance(a, dict):
        for key in list(dict.fromkeys([*a, *b])):
            if key not in a or key not in b:
                out.append((f"{path}.{key}", "missing", key in a))
            else:
                out.extend(_diffs(a[key], b[key], f"{path}.{key}"))
            if len(out) > 8:
                return out
        return out
    if isinstance(a, list):
        if len(a) != len(b):
            out.append((path + ".len", len(a), len(b)))
        for i, (x, y) in enumerate(zip(a, b)):
            out.extend(_diffs(x, y, f"{path}[{i}]"))
            if len(out) > 8:
                return out
        return out
    if a != b:
        out.append((path, a, b))
    return out


def run_plan(name: str, mode: str, scripts: list[Script], sem_n: int | None) -> dict:
    db = Path("/tmp/hosted-demo-matchup-memo-threads") / name / "checkpoints.db"
    if db.exists():
        for suffix in ("", "-wal", "-shm"):
            path = Path(str(db) + suffix)
            if path.exists():
                path.unlink()
    saver = open_sqlite_checkpointer(db)
    sem = threading.Semaphore(sem_n) if sem_n else None
    sessions = []
    for i, script in enumerate(scripts):
        bootstrap, turn = _parsers(script)
        graph = compile_graph(
            checkpointer=saver,
            bootstrap_intake_parser=bootstrap,
            turn_intent_parser=turn,
        )
        sessions.append(
            Session(
                i,
                script,
                graph,
                thread_config(f"memo-{name}-{i}-{uuid.uuid4().hex[:8]}"),
                sem,
            )
        )
    t0 = time.perf_counter()
    if mode == "concurrent":
        def play(session: Session) -> None:
            session.start()
            while not session.done:
                session.step()

        with ThreadPoolExecutor(max_workers=len(sessions)) as pool:
            list(pool.map(play, sessions))
    elif mode == "round-robin":
        for session in sessions:
            session.start()
        while any(not session.done for session in sessions):
            for session in sessions:
                if not session.done:
                    session.step()
    else:
        for session in sessions:
            session.start()
            while not session.done:
                session.step()
    wall = time.perf_counter() - t0
    dumped = []
    for session in sessions:
        values = session.graph.get_state(session.config).values
        dumped.append(
            {
                "index": session.index,
                "script": session.script.name,
                "locked": _locked(values),
                "stop": session.stop,
                "error": session.error,
                "fingerprint": fingerprint(values),
                "trace": [
                    {
                        "index": m["index"],
                        "kind": m["kind"],
                        "text": m["text"],
                        "wall_s": m["wall_s"],
                        "http_n": m["http_n"],
                        "http_s": m["http_s"],
                        "hits": m["hits"],
                        "misses": m["misses"],
                        "locked_after": m["locked_after"],
                        "error": m["error"],
                    }
                    for m in session.messages
                ],
            }
        )
    refs = {
        "A": json.loads((FIXTURES / "matchup_memo_alone_A.json").read_text()),
        "B": json.loads((FIXTURES / "matchup_memo_alone_B.json").read_text()),
    }
    diffs = []
    for session in dumped:
        found = _diffs(refs[session["script"]], session["fingerprint"])
        if found:
            diffs.append({"index": session["index"], "script": session["script"], "diff": found})
    return {
        "run": name,
        "mode": mode,
        "sem": sem_n,
        "wall_s": wall,
        "http_n": sum(m["http_n"] for s in sessions for m in s.messages),
        "http_s": sum(m["http_s"] for s in sessions for m in s.messages),
        "errors": [s["error"] for s in dumped if s["error"]],
        "diffs": diffs,
        "by_script": {
            script: _aggregate(sessions, script)
            for script in ("A", "B")
            if any(s.script.name == script for s in sessions)
        },
        "sessions": [
            {k: v for k, v in s.items() if k != "fingerprint"} | {"locked": s["locked"]}
            for s in dumped
        ],
    }


PLANS = {
    "alone": ("serial", [SCRIPT_A, SCRIPT_A, SCRIPT_B], None),
    "seq-5-A": ("round-robin", [SCRIPT_A] * 5, None),
    "seq-10-A": ("round-robin", [SCRIPT_A] * 10, None),
    "seq-5-mix": ("round-robin", [SCRIPT_A, SCRIPT_B, SCRIPT_A, SCRIPT_B, SCRIPT_A], None),
    "seq-10-mix": ("round-robin", [SCRIPT_A, SCRIPT_B] * 5, None),
    "conc-5-A": ("concurrent", [SCRIPT_A] * 5, None),
    "conc-10-A": ("concurrent", [SCRIPT_A] * 10, None),
    "conc-5-mix": ("concurrent", [SCRIPT_A, SCRIPT_B, SCRIPT_A, SCRIPT_B, SCRIPT_A], None),
    "conc-10-mix": ("concurrent", [SCRIPT_A, SCRIPT_B] * 5, None),
    "conc-10-mix-sem1": ("concurrent", [SCRIPT_A, SCRIPT_B] * 5, 1),
    "conc-10-mix-sem2": ("concurrent", [SCRIPT_A, SCRIPT_B] * 5, 2),
    "conc-10-mix-sem3": ("concurrent", [SCRIPT_A, SCRIPT_B] * 5, 3),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", choices=sorted(PLANS))
    parser.add_argument("--out")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    if args.run:
        mode, scripts, sem_n = PLANS[args.run]
        try:
            result = run_plan(args.run, mode, scripts, sem_n)
        except Exception:
            traceback.print_exc()
            sys.exit(1)
        line = (
            f"DONE {args.run} wall={result['wall_s']:.1f}s "
            f"diffs={len(result['diffs'])} errors={result['errors']}"
        )
        if args.out:
            dest = Path(args.out)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(result))
        else:
            json.dump(result, sys.stdout)
            sys.stdout.write("\n")
        print(line, flush=True)
        return
    if not args.all:
        parser.error("pass --run or --all")
    OUT.mkdir(parents=True, exist_ok=True)
    for name in PLANS:
        print(f"START {name}", flush=True)
        dest = OUT / f"{name}.json"
        proc = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--run",
                name,
                "--out",
                str(dest),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=1500,
        )
        print(proc.stdout.strip() or proc.stderr[-1500:], flush=True)
        if proc.returncode != 0:
            print(f"FAIL {name}", flush=True)


if __name__ == "__main__":
    main()
