"""Throwaway SqliteSaver checks. Fake parsers, one shared saver. Not product code.

    uv run python docs/hosted_demo/sqlite_spike/sqlite_checks.py
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import is_dataclass
from pathlib import Path

from langchain_core.runnables import RunnableLambda

ROOT = Path(__file__).resolve().parents[3]
OUT = Path("/tmp/hosted-demo-sqlite-spike")
DB = OUT / "checkpoints.db"
MARKER = OUT / "restart_marker.json"


def _parsers(label: str):
    def bootstrap(payload: dict) -> dict:
        return {
            "direction_text": "Rain",
            "anchor_text": "Pelipper",
            "pool_entries": None,
            "delegated": False,
            "ownership_mode": None,
        }

    def turn(payload: dict) -> dict:
        return {"turn_intent": "pending_response", "message": label}

    return RunnableLambda(bootstrap), RunnableLambda(turn)


def _compile(saver, label: str):
    from recommender.graph import compile_graph

    bootstrap, turn = _parsers(label)
    return compile_graph(
        checkpointer=saver,
        bootstrap_intake_parser=bootstrap,
        turn_intent_parser=turn,
    )


def _fingerprint(values: dict) -> dict:
    def norm(value):
        if is_dataclass(value):
            return {"__type__": type(value).__name__, **norm(value.__dict__)}
        if isinstance(value, dict):
            return {str(k): norm(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [norm(v) for v in value]
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return {"__type__": type(value).__name__, "__repr__": repr(value)}

    return {
        "turn": values.get("turn"),
        "last_user_text": values.get("last_user_text"),
        "obs_thread_id": values.get("obs_thread_id"),
        "turn_intent": values.get("turn_intent"),
        "pending_kind": (values.get("pending_presentation") or {}).get("kind"),
        "provisional_type": type(values.get("provisional_slot")).__name__,
        "team_draft": norm(values.get("team_draft")),
        "provisional_slot": norm(values.get("provisional_slot")),
    }


def _types(value, found: set[str]) -> None:
    if is_dataclass(value):
        found.add(type(value).__name__)
        _types(value.__dict__, found)
        return
    if isinstance(value, dict):
        for item in value.values():
            _types(item, found)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _types(item, found)


def _open():
    from recommender.checkpointer import open_sqlite_checkpointer

    return open_sqlite_checkpointer(DB)


def _play(graph, thread_id: str, texts: list[str]):
    from recommender.session import DEFAULT_FORMAT_ID, thread_config

    config = thread_config(thread_id)
    graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config)
    for text in texts:
        graph.invoke({"pending_input": text}, config)
    return graph.get_state(config).values


def concurrency() -> dict:
    from recommender.session import thread_config

    saver = _open()
    errors = []
    results = {}

    def one(i: int) -> dict:
        thread_id = f"team-sqlite-{i:02d}"
        rain = f"Rain with Pelipper #{i}"
        graph = _compile(saver, f"session-{i}")
        values = _play(graph, thread_id, [rain, "yes"])
        texts = []
        for snap in graph.get_state_history(thread_config(thread_id)):
            texts.append(snap.values.get("last_user_text"))
        return {
            "thread_id": thread_id,
            "turn": values.get("turn"),
            "obs_thread_id": values.get("obs_thread_id"),
            "history_texts": texts,
            "sent": [rain, "yes"],
        }

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=10) as pool:
        futs = [pool.submit(one, i) for i in range(10)]
        for fut in as_completed(futs):
            try:
                row = fut.result()
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
                continue
            results[row["thread_id"]] = row
    wall = time.perf_counter() - t0
    crosstalk = []
    lost = []
    for row in results.values():
        own = row["sent"][0]
        if row["obs_thread_id"] != row["thread_id"]:
            crosstalk.append(row["thread_id"])
        if own not in row["history_texts"]:
            crosstalk.append(f"{row['thread_id']} missing own text")
        foreign = [t for t in row["history_texts"] if isinstance(t, str) and t.startswith("Rain") and t != own]
        if foreign:
            crosstalk.append({"thread_id": row["thread_id"], "foreign": foreign})
        if row["turn"] != 2:
            lost.append({"thread_id": row["thread_id"], "turn": row["turn"]})
    return {
        "sessions": len(results),
        "exceptions": errors,
        "crosstalk": crosstalk,
        "turn_mismatches": lost,
        "turns": {k: v["turn"] for k, v in sorted(results.items())},
        "wall_s": round(wall, 3),
    }


def restart_write() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if MARKER.exists():
        MARKER.unlink()
    if DB.exists():
        DB.unlink()
    for suffix in ("-wal", "-shm"):
        side = Path(str(DB) + suffix)
        if side.exists():
            side.unlink()
    caught = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        saver = _open()
        graph = _compile(saver, "write")
        values = _play(graph, "team-restart", ["Rain with Pelipper", "yes", "yes"])
        found: set[str] = set()
        _types(values, found)
        marker = {
            "fingerprint": _fingerprint(values),
            "types": sorted(found),
            "warnings": [str(w.message) for w in caught],
        }
    tmp = MARKER.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(marker))
    os.replace(tmp, MARKER)
    time.sleep(60)


def restart_read() -> dict:
    marker = json.loads(MARKER.read_text())
    caught = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        saver = _open()
        graph = _compile(saver, "read-new-parsers")
        from recommender.session import thread_config

        config = thread_config("team-restart")
        restored = graph.get_state(config).values
        before = _fingerprint(restored)
        found: set[str] = set()
        _types(restored, found)
        graph.invoke({"pending_input": "yes"}, config)
        after = graph.get_state(config).values
        saver.conn.close()
    files = sorted(p.name for p in OUT.iterdir())
    return {
        "fingerprint_equal": before == marker["fingerprint"],
        "turn_before": before["turn"],
        "turn_marker": marker["fingerprint"]["turn"],
        "turn_after_continue": after.get("turn"),
        "types_seen": sorted(found),
        "types_at_write": marker["types"],
        "warnings_on_read": [str(w.message) for w in caught],
        "warnings_on_write": marker["warnings"],
        "files_while_open": files,
    }


def allowlist_walk() -> dict:
    """One accept-defaults game on the file saver, then a new saver reads it back."""
    import warnings

    from recommender.session import DEFAULT_FORMAT_ID, thread_config
    from recommender.state import all_locked

    if DB.exists():
        DB.unlink()
    for suffix in ("-wal", "-shm"):
        side = Path(str(DB) + suffix)
        if side.exists():
            side.unlink()
    replies = {
        "bootstrap_intake": "Rain with Pelipper",
        "candidate_selection": "yes",
        "full_build_confirmation": "yes",
        "completion_preference": "1",
    }
    caught: list = []
    teammate_roundtrip = None
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        saver = _open()
        graph = _compile(saver, "walk")
        config = thread_config("team-walk")
        graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config)
        for _ in range(24):
            values = graph.get_state(config).values
            if sum(bool(all_locked(slot)) for slot in values.get("team_draft") or []) == 6:
                break
            kind = (values.get("pending_presentation") or {}).get("kind")
            text = replies.get(kind or "")
            if text is None:
                break
            graph.invoke({"pending_input": text}, config)
            step_values = graph.get_state(config).values
            step_types: set[str] = set()
            _types(step_values, step_types)
            if "SharedTeammate" in step_types or "TeammateQueryResult" in step_types:
                held = _fingerprint(step_values)
                saver.conn.commit()
                other = _open()
                try:
                    with warnings.catch_warnings(record=True) as mid_warnings:
                        warnings.simplefilter("always")
                        reread_values = _compile(other, "mid").get_state(config).values
                    reread_types: set[str] = set()
                    _types(reread_values, reread_types)
                    teammate_roundtrip = {
                        "equal": _fingerprint(reread_values) == held,
                        "types": sorted(t for t in reread_types if "Teammate" in t or "Matchup" in t),
                        "warnings": [
                            str(w.message)
                            for w in mid_warnings
                            if "unregistered" in str(w.message).lower()
                        ],
                    }
                finally:
                    other.conn.close()
        values = graph.get_state(config).values
        before = _fingerprint(values)
        found: set[str] = set()
        _types(values, found)
        saver.conn.close()
    with warnings.catch_warnings(record=True) as reread:
        warnings.simplefilter("always")
        saver = _open()
        graph = _compile(saver, "walk-reread")
        restored = graph.get_state(config).values
        after = _fingerprint(restored)
        again: set[str] = set()
        _types(restored, again)
        saver.conn.close()
    interesting = [
        "MatchupResult",
        "MatchupCaveats",
        "SharedTeammate",
        "SharedTeammateQueryResult",
        "TeammateQueryResult",
        "TeammateEvidence",
        "ProvisionalSlot",
        "Attr",
        "Slot",
    ]
    return {
        "fingerprint_equal": before == after,
        "turn": before["turn"],
        "types": sorted(found),
        "types_reread": sorted(again),
        "interesting_present": [name for name in interesting if name in found],
        "warnings_on_write": [str(w.message) for w in caught if "msgpack" in str(w.message).lower() or "unregistered" in str(w.message).lower()],
        "warnings_on_read": [str(w.message) for w in reread if "msgpack" in str(w.message).lower() or "unregistered" in str(w.message).lower()],
        "teammate_roundtrip": teammate_roundtrip,
    }


def main() -> None:
    os.environ["RECOMMENDER_TOOL_LOG"] = "/tmp/hosted_demo_sqlite_spike_tool_log.jsonl"
    os.chdir(ROOT)
    OUT.mkdir(parents=True, exist_ok=True)
    if len(sys.argv) > 1 and sys.argv[1] == "walk":
        print(json.dumps(allowlist_walk(), indent=2))
        return
    if len(sys.argv) > 1 and sys.argv[1] == "restart-write":
        restart_write()
        return
    report: dict = {"concurrency": concurrency()}
    if MARKER.exists():
        MARKER.unlink()
    proc = subprocess.Popen([sys.executable, __file__, "restart-write"])
    deadline = time.time() + 180
    while time.time() < deadline and not MARKER.exists():
        if proc.poll() is not None:
            break
        time.sleep(0.2)
    if not MARKER.exists():
        proc.kill()
        report["restart"] = {"error": "marker missing", "returncode": proc.poll()}
    else:
        time.sleep(0.5)
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)
        report["restart"] = restart_read()
        report["files_after_close"] = sorted(p.name for p in OUT.iterdir())
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
