"""Nov 5 usage-refresh measurements. Spike only. Does not edit product data.

    uv run python docs/hosted_demo/usage_refresh_spike/measure.py --part floor
    uv run python docs/hosted_demo/usage_refresh_spike/measure.py --part games
    uv run python docs/hosted_demo/usage_refresh_spike/measure.py --part species

USAGE_REFRESH_BLOB=old loads the ingame file from 4d59608 into a temp directory.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback
import uuid
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "results"
IDS = [
    "appletun", "arbok", "avalugg", "castform", "decidueye", "dedenne", "furfrou",
    "garbodor", "gogoat", "gourgeist", "gourgeistlarge", "gourgeistsuper", "pangoro",
    "persian", "qwilfish", "samurott", "simisage", "simisear", "stunfiskgalar",
    "swalot", "tauros", "tyrantrum",
]


def _install_blob() -> None:
    if os.environ.get("USAGE_REFRESH_BLOB") != "old":
        return
    import recommender.usage_data as usage_data

    tmp = Path("/tmp/usage-refresh-spike/old-usage")
    tmp.mkdir(parents=True, exist_ok=True)
    blob = subprocess.check_output(
        ["git", "show", "4d59608:data/usage/champions-reg-mc.ingame_doubles.v1.json"],
        cwd=ROOT,
    )
    (tmp / "champions-reg-mc.ingame_doubles.v1.json").write_bytes(blob)
    showdown = ROOT / "data" / "usage" / "champions-reg-mc.showdown_doubles.v1.json"
    (tmp / showdown.name).write_bytes(showdown.read_bytes())
    usage_data.USAGE_DIR = tmp
    usage_data.load_usage.cache_clear()
    usage_data.ingame_excluded_ids.cache_clear()


_install_blob()

from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import MemorySaver

from recommender.graph import compile_graph
from recommender.ids import to_id
from recommender.legality import check_set, load_snapshot, resolve_learnset
from recommender.nodes import all_locked
from recommender.session import DEFAULT_FORMAT_ID, thread_config


def _remeasure():
    path = ROOT / "docs" / "hosted_demo" / "matchup_memo_threads" / "remeasure.py"
    spec = spec_from_file_location("matchup_memo_remeasure", path)
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _locked(state: dict) -> list[str]:
    return [
        str(slot.species.value)
        for slot in state.get("team_draft") or []
        if all_locked(slot) and slot.species.value
    ]


def _options(state: dict) -> list:
    pending = state.get("pending_presentation") or {}
    out = []
    for opt in pending.get("options") or []:
        out.append(opt.get("species") or opt.get("option_id"))
    return out


def _role(state: dict) -> str | None:
    slot = state.get("provisional_slot")
    draft = state.get("team_draft") or []
    slots = [slot] if slot is not None else []
    slots.extend(draft)
    for item in slots:
        if item is None:
            continue
        role = getattr(item, "role", None)
        if role is not None and role.value:
            return str(role.value)
    return None


def floor(blob: str) -> dict:
    from unittest.mock import patch

    class Box:
        def __init__(self):
            self.mode = "rain"

        def bootstrap(self, payload):
            if self.mode == "six_schema":
                return {
                    "direction_text": None,
                    "anchor_text": "Pelipper",
                    "pool_entries": ["Incineroar", "Rillaboom", "Amoonguss", "Kingambit", "Flutter Mane"],
                    "delegated": False,
                    "ownership_mode": None,
                }
            return {
                "direction_text": "Rain",
                "anchor_text": "Pelipper",
                "pool_entries": None,
                "delegated": False,
                "ownership_mode": None,
            }

        def turn(self, _payload):
            return {"turn_intent": "pending_response", "message": "unused"}

    def graph_for(box):
        return compile_graph(
            checkpointer=MemorySaver(),
            bootstrap_intake_parser=RunnableLambda(box.bootstrap),
            turn_intent_parser=RunnableLambda(box.turn),
        )

    def play(box, steps, config_id):
        graph = graph_for(box)
        config = thread_config(config_id)
        state = graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config)
        rows = [{"user": None, "turn": state.get("turn"), "locked": _locked(state), "options": _options(state), "kind": (state.get("pending_presentation") or {}).get("kind")}]
        for mode, text in steps:
            box.mode = mode
            state = graph.invoke({"pending_input": text}, config)
            rows.append({"user": text, "turn": state.get("turn"), "locked": _locked(state), "options": _options(state), "kind": (state.get("pending_presentation") or {}).get("kind")})
        return rows

    moves = ["Hurricane", "U-turn", "Weather Ball", "Protect"]
    spread = {"hp": 4, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 30}

    def patched(fn):
        with (
            patch("recommender.propose.featured_or_common_set", return_value={"species": "Pelipper", "ability": "Drizzle", "moves": moves, "item": "Damp Rock", "nature": "Modest"}),
            patch("recommender.propose.get_resolved_build", return_value={"spread": spread, "source_tier": "test", "verified": True}),
        ):
            return fn()

    six_text = (
        "Pelipper @ Damp Rock, Drizzle, Hurricane / U-turn / Weather Ball / Protect; "
        "Incineroar @ Safety Goggles, Intimidate, Fake Out / Flare Blitz / Parting Shot / Snarl; "
        "Rillaboom @ Assault Vest, Grassy Surge, Grassy Glide / Wood Hammer / U-turn / Fake Out; "
        "Amoonguss @ Sitrus Berry, Regenerator, Spore / Rage Powder / Pollen Puff / Protect; "
        "Kingambit @ Black Glasses, Defiant, Kowtow Cleave / Sucker Punch / Iron Head / Protect; "
        "Flutter Mane @ Choice Specs, Protosynthesis, Moonblast / Shadow Ball / Dazzling Gleam / Protect"
    )
    baseline = patched(lambda: play(Box(), [("rain", "Rain with Pelipper"), ("rain", "yes"), ("rain", "yes")], f"base-{blob}"))
    six = play(Box(), [("six_schema", six_text)], f"six-{blob}")

    box = Box()
    graph = graph_for(box)
    config = thread_config(f"accept-{blob}")
    state = graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config)
    replies = {"bootstrap_intake": "Rain with Pelipper", "candidate_selection": "yes", "full_build_confirmation": "yes", "completion_preference": "1"}
    accept = [{"user": None, "turn": state.get("turn"), "locked": _locked(state), "options": _options(state), "kind": (state.get("pending_presentation") or {}).get("kind")}]
    for _ in range(24):
        if len(_locked(state)) >= 6:
            break
        kind = (state.get("pending_presentation") or {}).get("kind")
        text = replies.get(kind or "")
        if text is None:
            accept.append({"stopped": kind, "turn": state.get("turn"), "locked": _locked(state), "options": _options(state)})
            break
        state = graph.invoke({"pending_input": text}, config)
        accept.append({"user": text, "pending_before": kind, "turn": state.get("turn"), "locked": _locked(state), "options": _options(state), "kind": (state.get("pending_presentation") or {}).get("kind")})
    return {"blob": blob, "baseline": baseline, "six": six, "accept": accept}


def games() -> dict:
    mod = _remeasure()
    saved = {}
    for name, script in (("A", mod.SCRIPT_A), ("B", mod.SCRIPT_B)):
        bootstrap, turn = mod._parsers(script)
        graph = compile_graph(checkpointer=MemorySaver(), bootstrap_intake_parser=bootstrap, turn_intent_parser=turn)
        session = mod.Session(0, script, graph, thread_config(f"usage-{name}-{uuid.uuid4().hex[:8]}"), None)
        session.start()
        while not session.done:
            pending = session.state.get("pending_presentation") or {}
            options = _options(session.state)
            session.step()
            if session.messages:
                session.messages[-1]["options_before"] = options
                session.messages[-1]["kind_before"] = pending.get("kind")
        values = session.graph.get_state(session.config).values
        saved[name] = {
            "locked": _locked(values),
            "stop": session.stop,
            "error": session.error,
            "fingerprint": mod.fingerprint(values),
            "trace": session.messages,
        }
    refs = {
        "A": json.loads((ROOT / "tests/recommender/fixtures/matchup_memo_alone_A.json").read_text()),
        "B": json.loads((ROOT / "tests/recommender/fixtures/matchup_memo_alone_B.json").read_text()),
    }
    diffs = {name: mod._diffs(refs[name], saved[name]["fingerprint"]) for name in saved}
    # The imported differ stops at 8. Walk the top-level keys as well.
    summary = {}
    for name in saved:
        got = saved[name]["fingerprint"]
        ref = refs[name]
        summary[name] = {
            "draft_equal": got["draft"] == ref["draft"],
            "coverage_equal": got["coverage"] == ref["coverage"],
            "coverage_len": [len(ref["coverage"]), len(got["coverage"])],
            "spofs_equal": got["spofs"] == ref["spofs"],
            "options_equal": got["options"] == ref["options"],
            "pending_kind": [ref["pending_kind"], got["pending_kind"]],
            "first_diffs": diffs[name],
        }
    return {"games": {k: {kk: vv for kk, vv in row.items() if kk != "fingerprint"} for k, row in saved.items()}, "diff_summary": summary}


def _plain_moves(snap, species_name: str) -> list[str]:
    learnset = resolve_learnset(snap, species_name) or []
    for move in learnset:
        if to_id(move) == "protect":
            return ["Protect"]
    return [learnset[0]] if learnset else []


def species_probe() -> dict:
    snap = load_snapshot()
    catalog = snap.get("species") or {}
    rows = []
    for sid in IDS:
        entry = catalog.get(sid) or {}
        display = str(entry.get("name") or sid)
        moves = _plain_moves(snap, display)
        legal = check_set(display, moves, "", snap=snap)
        box_mode = {"anchor": display}

        def bootstrap(_payload, anchor=display):
            return {"direction_text": None, "anchor_text": anchor, "pool_entries": None, "delegated": False, "ownership_mode": None}

        def turn(_payload):
            return {"turn_intent": "pending_response", "message": "unused"}

        graph = compile_graph(
            checkpointer=MemorySaver(),
            bootstrap_intake_parser=RunnableLambda(bootstrap),
            turn_intent_parser=RunnableLambda(turn),
        )
        config = thread_config(f"sp-{sid}")
        error = None
        state: dict = {}
        try:
            state = graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config)
            state = graph.invoke({"pending_input": display}, config)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        rows.append(
            {
                "id": sid,
                "name": display,
                "in_snapshot": sid in catalog,
                "plain_moves": moves,
                "check_set_ok": bool(legal.ok),
                "check_set_failures": [f"{item.field}:{item.detail}" for item in legal.failures],
                "error": error,
                "kind": (state.get("pending_presentation") or {}).get("kind") if state else None,
                "options": _options(state) if state else [],
                "role": _role(state) if state else None,
                "locked": _locked(state) if state else [],
                "discovery_error": state.get("candidate_discovery_error") if state else None,
            }
        )
    return {"species": rows}


def main() -> None:
    part = sys.argv[sys.argv.index("--part") + 1] if "--part" in sys.argv else "all"
    blob = os.environ.get("USAGE_REFRESH_BLOB", "new")
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        if part == "floor":
            payload = floor(blob)
        elif part == "games":
            payload = games()
        elif part == "species":
            payload = species_probe()
        else:
            raise SystemExit("part must be floor, games, or species")
    except Exception:
        traceback.print_exc()
        sys.exit(1)
    dest = OUT / f"{part}-{blob}.json"
    dest.write_text(json.dumps(payload, default=str))
    print(f"wrote {dest}", flush=True)


if __name__ == "__main__":
    main()
