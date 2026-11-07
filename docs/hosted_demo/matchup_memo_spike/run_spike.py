"""Matchup-memo latency and correctness spike. Does not edit recommender/.

One process per run, one shared file-backed SqliteSaver, one compile_graph
per session. Fake parsers. Real calc service on 127.0.0.1:4173.

    uv run python docs/hosted_demo/matchup_memo_spike/run_spike.py --run alone
    uv run python docs/hosted_demo/matchup_memo_spike/run_spike.py --all
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault(
    "RECOMMENDER_TOOL_LOG", "/tmp/hosted-demo-matchup-memo-spike/tool_log.jsonl"
)

from langchain_core.runnables import RunnableLambda

import recommender.matchup as matchup
from recommender.calc_client import CalcClient
from recommender.checkpointer import open_sqlite_checkpointer
from recommender.graph import compile_graph
from recommender.nodes import SLOT_ATTRS
from recommender.session import DEFAULT_FORMAT_ID, thread_config
from recommender.state import all_locked

OUT = Path(__file__).resolve().parent / "results"
_TLS = threading.local()
_INFLIGHT: set[int] = set()
_INFLIGHT_LOCK = threading.Lock()
_RACE = {"clears_while_other_invoke": 0, "clears": 0, "http_inflight_max": 0}
_HTTP_LOCK = threading.Lock()
_HTTP_INFLIGHT = 0

_ORIG_GET = matchup._memo_get
_ORIG_PUT = matchup._memo_put
_ORIG_BIND = matchup.bind_matchup_memo_thread
_ORIG_JSON = CalcClient._json_request


def _rec():
    return getattr(_TLS, "rec", None)


def _memo_get(key):
    result = _ORIG_GET(key)
    rec = _rec()
    if rec is not None and result is not None:
        rec["hits"] += 1
    return result


def _memo_put(key, result):
    _ORIG_PUT(key, result)
    rec = _rec()
    if rec is not None:
        rec["misses"] += 1


def _bind(thread_id):
    prev = matchup._MEMO_THREAD_ID
    tid = thread_id or ""
    with _INFLIGHT_LOCK:
        others = sum(1 for ident in _INFLIGHT if ident != threading.get_ident())
    if prev not in (None, tid):
        _RACE["clears"] += 1
        if others:
            _RACE["clears_while_other_invoke"] += 1
    return _ORIG_BIND(thread_id)


def _json_request(self, method, path, body=None, *, timeout=None):
    global _HTTP_INFLIGHT
    with _HTTP_LOCK:
        _HTTP_INFLIGHT += 1
        if _HTTP_INFLIGHT > _RACE["http_inflight_max"]:
            _RACE["http_inflight_max"] = _HTTP_INFLIGHT
    t0 = time.perf_counter()
    try:
        return _ORIG_JSON(self, method, path, body, timeout=timeout)
    finally:
        dt = time.perf_counter() - t0
        with _HTTP_LOCK:
            _HTTP_INFLIGHT -= 1
        rec = _rec()
        if rec is not None:
            rec["http_n"] += 1
            rec["http_s"] += dt
            if isinstance(body, dict) and isinstance(body.get("requests"), list):
                rec["http_rows"] += len(body["requests"])


matchup._memo_get = _memo_get
matchup._memo_put = _memo_put
matchup.bind_matchup_memo_thread = _bind
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
    seen = {"turn": 0}

    def bootstrap(_payload):
        return {
            "direction_text": script.direction,
            "anchor_text": script.anchor,
            "pool_entries": None,
            "delegated": False,
            "ownership_mode": None,
        }

    def turn(_payload):
        seen["turn"] += 1
        return {"turn_intent": "pending_response", "message": "unused"}

    return RunnableLambda(bootstrap), RunnableLambda(turn), seen


def _locked(state: dict) -> list[str]:
    names = []
    for slot in state.get("team_draft") or []:
        if all_locked(slot) and slot.species.value:
            names.append(str(slot.species.value))
    return names


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
    if isinstance(value, tuple):
        return [_j(v) for v in value]
    if isinstance(value, list):
        return [_j(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _j(v) for k, v in value.items()}
    return str(value)


def _fingerprint(state: dict) -> dict:
    draft = []
    for slot in state.get("team_draft") or []:
        row = {}
        for name in SLOT_ATTRS:
            attr = getattr(slot, name)
            row[name] = {"v": _j(attr.value), "locked": bool(attr.locked)}
        draft.append(row)
    pending = state.get("pending_presentation") or {}
    options = []
    for opt in pending.get("options") or []:
        options.append(opt.get("species") or opt.get("option_id"))
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
    spofs = []
    for sp in state.get("spofs") or []:
        spofs.append(
            {
                "slot": sp.slot_index,
                "threats": [(t or {}).get("species") for t in sp.threats_lost],
            }
        )
    return {
        "draft": draft,
        "pending_kind": pending.get("kind"),
        "options": options,
        "coverage": coverage,
        "spofs": spofs,
        "discovery_error": _j(state.get("candidate_discovery_error")),
    }


def _blank():
    return {
        "hits": 0,
        "misses": 0,
        "http_n": 0,
        "http_s": 0.0,
        "http_rows": 0,
        "error": None,
    }


class Session:
    def __init__(self, index: int, script: Script, graph, config: dict):
        self.index = index
        self.script = script
        self.graph = graph
        self.config = config
        self.state: dict = {}
        self.done = False
        self.stop = None
        self.messages: list[dict] = []
        self.init_s = 0.0
        self.error = None

    def start(self) -> None:
        ident = threading.get_ident()
        with _INFLIGHT_LOCK:
            _INFLIGHT.add(ident)
        try:
            t0 = time.perf_counter()
            self.state = self.graph.invoke({"format_id": DEFAULT_FORMAT_ID}, self.config)
            self.init_s = time.perf_counter() - t0
        except Exception as exc:
            self.error = f"init: {exc!r}"
            self.done = True
            self.stop = "init_error"
        finally:
            with _INFLIGHT_LOCK:
                _INFLIGHT.discard(ident)

    def step(self) -> None:
        if self.done:
            return
        if len(_locked(self.state)) >= 6 or len(self.messages) >= 20:
            self.done = True
            self.stop = self.stop or ("six_locked" if len(_locked(self.state)) >= 6 else "cap")
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
        rec["locked_before"] = _locked(self.state)
        _TLS.rec = rec
        ident = threading.get_ident()
        with _INFLIGHT_LOCK:
            _INFLIGHT.add(ident)
        t0 = time.perf_counter()
        try:
            self.state = self.graph.invoke({"pending_input": text}, self.config)
        except Exception as exc:
            rec["error"] = f"{type(exc).__name__}: {exc}"
            self.error = rec["error"]
            self.done = True
            self.stop = "invoke_error"
        finally:
            rec["wall_s"] = time.perf_counter() - t0
            _TLS.rec = None
            with _INFLIGHT_LOCK:
                _INFLIGHT.discard(ident)
        rec["locked_after"] = _locked(self.state) if self.state else []
        rec["memo_len"] = len(matchup._MATCHUP_MEMO)
        rec["bound"] = matchup._MEMO_THREAD_ID
        self.messages.append(rec)
        if self.done:
            return
        if len(rec["locked_after"]) >= 6:
            self.done = True
            self.stop = "six_locked"


def _percentile(values: list[float], p: float):
    if not values:
        return None
    ys = sorted(values)
    if len(ys) == 1:
        return ys[0]
    k = math.ceil((p / 100) * len(ys)) - 1
    return ys[min(max(k, 0), len(ys) - 1)]


def _aggregate(sessions: list[Session]) -> list[dict]:
    by: dict[int, list[dict]] = {}
    for session in sessions:
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
                "wall_p50": _percentile(walls, 50),
                "wall_p95": _percentile(walls, 95),
                "wall_max": max(walls),
                "locked_after_same": len({tuple(m["locked_after"]) for m in msgs}) == 1,
                "http_n_p50": _percentile([m["http_n"] for m in msgs], 50),
                "http_n_max": max(m["http_n"] for m in msgs),
                "http_s_p50": _percentile([m["http_s"] for m in msgs], 50),
                "http_s_max": max(m["http_s"] for m in msgs),
                "hits_p50": _percentile([m["hits"] for m in msgs], 50),
                "miss_p50": _percentile([m["misses"] for m in msgs], 50),
                "miss_max": max(m["misses"] for m in msgs),
                "errors": sum(1 for m in msgs if m["error"]),
            }
        )
    return rows


def _run(name: str, mode: str, scripts: list[Script]) -> dict:
    db = Path("/tmp/hosted-demo-matchup-memo-spike") / name / "checkpoints.db"
    if db.exists():
        for suffix in ("", "-wal", "-shm"):
            path = Path(str(db) + suffix)
            if path.exists():
                path.unlink()
    saver = open_sqlite_checkpointer(db)
    sessions: list[Session] = []
    for i, script in enumerate(scripts):
        bootstrap, turn, seen = _parsers(script)
        graph = compile_graph(
            checkpointer=saver,
            bootstrap_intake_parser=bootstrap,
            turn_intent_parser=turn,
        )
        tid = f"memo-{name}-{i}-{uuid.uuid4().hex[:8]}"
        session = Session(i, script, graph, thread_config(tid))
        session.turn_seen = seen
        sessions.append(session)

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
        fp = None
        fp_error = None
        try:
            values = session.graph.get_state(session.config).values
            fp = _fingerprint(values)
            locked = _locked(values)
        except Exception as exc:
            fp_error = repr(exc)
            locked = _locked(session.state) if session.state else []
        dumped.append(
            {
                "index": session.index,
                "script": session.script.name,
                "thread_id": session.config["configurable"]["thread_id"],
                "locked": locked,
                "n_locked": len(locked),
                "messages": len(session.messages),
                "stop": session.stop,
                "init_s": session.init_s,
                "error": session.error,
                "fp_error": fp_error,
                "fingerprint": fp,
                "turn_parser_calls": session.turn_seen["turn"],
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
                        "memo_len": m["memo_len"],
                        "bound_prefix": (m["bound"] or "")[:24],
                    }
                    for m in session.messages
                ],
            }
        )
    http_n = sum(m["http_n"] for s in sessions for m in s.messages)
    http_s = sum(m["http_s"] for s in sessions for m in s.messages)
    return {
        "run": name,
        "mode": mode,
        "n": len(sessions),
        "scripts": [s.name for s in scripts],
        "wall_s": wall,
        "http_n": http_n,
        "http_s": http_s,
        "http_inflight_max": _RACE["http_inflight_max"],
        "memo_clears": _RACE["clears"],
        "clears_while_other_invoke": _RACE["clears_while_other_invoke"],
        "errors": [s["error"] for s in dumped if s["error"]],
        "by_index": _aggregate(sessions),
        "by_script": {
            name: _aggregate([s for s in sessions if s.script.name == name])
            for name in ("A", "B")
            if any(s.script.name == name for s in sessions)
        },
        "sessions": dumped,
    }


PLANS = {
    "alone": ("serial", [SCRIPT_A, SCRIPT_A, SCRIPT_B]),
    "seq-3-A": ("round-robin", [SCRIPT_A] * 3),
    "seq-5-A": ("round-robin", [SCRIPT_A] * 5),
    "seq-10-A": ("round-robin", [SCRIPT_A] * 10),
    "seq-5-mix": ("round-robin", [SCRIPT_A, SCRIPT_B, SCRIPT_A, SCRIPT_B, SCRIPT_A]),
    "seq-10-mix": ("round-robin", [SCRIPT_A, SCRIPT_B] * 5),
    "conc-5-A": ("concurrent", [SCRIPT_A] * 5),
    "conc-10-A": ("concurrent", [SCRIPT_A] * 10),
    "conc-5-mix": ("concurrent", [SCRIPT_A, SCRIPT_B, SCRIPT_A, SCRIPT_B, SCRIPT_A]),
    "conc-10-mix": ("concurrent", [SCRIPT_A, SCRIPT_B] * 5),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", choices=sorted(PLANS))
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    if args.run:
        mode, scripts = PLANS[args.run]
        _RACE["clears"] = 0
        _RACE["clears_while_other_invoke"] = 0
        _RACE["http_inflight_max"] = 0
        try:
            payload = _run(args.run, mode, scripts)
        except Exception:
            traceback.print_exc()
            sys.exit(1)
        json.dump(payload, sys.stdout)
        sys.stdout.write("\n")
        return
    if not args.all:
        parser.error("pass --run or --all")
    OUT.mkdir(parents=True, exist_ok=True)
    for name in PLANS:
        print(f"START {name}", flush=True)
        # A fresh interpreter so the memo starts empty for every run.
        import subprocess

        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--run", name],
            check=False,
            capture_output=True,
            text=True,
            timeout=1500,
        )
        dest = OUT / f"{name}.json"
        if proc.returncode != 0:
            dest.write_text(
                json.dumps(
                    {
                        "run": name,
                        "error": "process_failed",
                        "returncode": proc.returncode,
                        "stderr_tail": proc.stderr[-4000:],
                        "stdout_tail": proc.stdout[-1000:],
                    }
                )
            )
            print(f"FAIL {name} rc={proc.returncode}", flush=True)
            continue
        dest.write_text(proc.stdout)
        summary = json.loads(proc.stdout)
        locked = [s["locked"] for s in summary["sessions"]]
        print(
            f"DONE {name} wall={summary['wall_s']:.1f}s errors={summary['errors']} locked={locked}",
            flush=True,
        )


if __name__ == "__main__":
    main()
