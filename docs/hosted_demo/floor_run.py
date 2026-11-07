"""Scripted demo-graph floor run. Fake parsers, no network, no model.

Uses compile_graph (not compile_cli_graph). Read-only on recommender/.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import MemorySaver

from recommender.graph import compile_graph
from recommender.nodes import LOCK_FULLY_LOCKED_SLOT_MSG, SLOT_ATTRS, all_locked
from recommender.present_text import _FOOTERS, format_turn
from recommender.session import DEFAULT_FORMAT_ID, thread_config
from recommender.turn_intent import CLASSIFY_FAIL_USER_MSG

OUT = Path(__file__).with_name("floor_run_output.json")

SIX = (
    "Pelipper @ Damp Rock, Drizzle, Hurricane / U-turn / Weather Ball / Protect; "
    "Incineroar @ Safety Goggles, Intimidate, Fake Out / Flare Blitz / Parting Shot / Snarl; "
    "Rillaboom @ Assault Vest, Grassy Surge, Grassy Glide / Wood Hammer / U-turn / Fake Out; "
    "Amoonguss @ Sitrus Berry, Regenerator, Spore / Rage Powder / Pollen Puff / Protect; "
    "Kingambit @ Black Glasses, Defiant, Kowtow Cleave / Sucker Punch / Iron Head / Protect; "
    "Flutter Mane @ Choice Specs, Protosynthesis, Moonblast / Shadow Ball / Dazzling Gleam / Protect"
)


def _jsonable(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return str(value)


def _pending_view(state: dict) -> dict:
    pending = state.get("pending_presentation") or {}
    kind = pending.get("kind")
    options = []
    for i, opt in enumerate(pending.get("options") or [], start=1):
        species = opt.get("species") or "?"
        label = species
        if opt.get("direction_label"):
            label = f"{species} ({opt['direction_label']})"
        options.append(
            {
                "id": str(i),
                "label": label,
                "send_text": str(i),
                "species": species,
            }
        )
    for group in pending.get("build_option_groups") or ():
        for opt in group.get("options") or ():
            oid = str(opt.get("option_id") or "")
            if not oid:
                continue
            options.append(
                {
                    "id": oid,
                    "label": str(opt.get("label") or oid),
                    "send_text": oid,
                    "axis": group.get("axis"),
                }
            )
    if kind == "full_build_confirmation":
        options.insert(
            0,
            {"id": "accept", "label": "Accept this build", "send_text": "yes"},
        )
    prov = state.get("provisional_slot")
    draft = state.get("team_draft") or []
    slots = []
    drafted = 0
    locked = 0
    for n, slot in enumerate(draft, start=1):
        fields = {}
        any_value = False
        for name in SLOT_ATTRS:
            attr = getattr(slot, name)
            if attr.value is not None:
                any_value = True
            fields[name] = {"value": _jsonable(attr.value), "locked": bool(attr.locked)}
        is_locked = bool(all_locked(slot))
        drafted += int(any_value)
        locked += int(is_locked)
        slots.append(
            {
                "index": n,
                "locked": is_locked,
                "species": fields["species"]["value"],
                "species_locked": fields["species"]["locked"],
                "fields": fields,
            }
        )
    payload = state.get("turn_payload")
    message = payload.get("message") if isinstance(payload, dict) else None
    return {
        "turn": state.get("turn"),
        "pending_kind": kind,
        "prompt_text": pending.get("prompt_text"),
        "footer": _FOOTERS.get(kind or "", None),
        "notices": list(pending.get("notices") or ()),
        "options": options,
        "slots_with_any_value": drafted,
        "slots_fully_locked": locked,
        "locked_flags": [row["locked"] for row in slots],
        "slot_species": [
            {"index": row["index"], "species": row["species"], "species_locked": row["species_locked"]}
            for row in slots
        ],
        "provisional_species": getattr(prov, "species", None),
        "slot_commit_error": state.get("slot_commit_error"),
        "bootstrap_intake_error": state.get("bootstrap_intake_error"),
        "turn_intent": state.get("turn_intent"),
        "turn_payload_message": message,
        "last_user_text_len": len(state.get("last_user_text") or ""),
        "visible": format_turn(state, unmatched=state.get("turn_intent") == "pending_response"),
    }


class _Box:
    """Mutable parser mode shared by the two Runnables."""

    def __init__(self) -> None:
        self.mode = "rain"
        self.seen: list[dict] = []

    def bootstrap(self, payload: dict) -> dict:
        text = payload.get("user_text") or ""
        self.seen.append({"parser": "bootstrap", "len": len(text), "mode": self.mode})
        if self.mode == "raise_bootstrap":
            raise RuntimeError("fake bootstrap parser failed")
        if self.mode == "naive_builds":
            # Extra keys the BootstrapExtraction schema forbids.
            return {
                "direction_text": "Rain",
                "anchor_text": "Pelipper",
                "pool_entries": ["Incineroar", "Rillaboom", "Amoonguss", "Kingambit", "Flutter Mane"],
                "delegated": False,
                "ownership_mode": None,
                "builds": [{"species": "Pelipper", "item": "Damp Rock"}],
            }
        if self.mode == "six_schema":
            return {
                "direction_text": None,
                "anchor_text": "Pelipper",
                "pool_entries": [
                    "Incineroar",
                    "Rillaboom",
                    "Amoonguss",
                    "Kingambit",
                    "Flutter Mane",
                ],
                "delegated": False,
                "ownership_mode": None,
            }
        if self.mode == "long":
            return {
                "direction_text": "Rain",
                "anchor_text": "Pelipper",
                "pool_entries": None,
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

    def turn(self, payload: dict) -> dict:
        text = payload.get("user_text") or ""
        self.seen.append(
            {
                "parser": "turn",
                "len": len(text),
                "mode": self.mode,
                "pending_kind": payload.get("pending_kind"),
            }
        )
        if self.mode == "raise_turn":
            raise RuntimeError("fake turn parser failed")
        if self.mode == "multi_intent_list":
            return {
                "turn_intents": [
                    {"turn_intent": "lock", "slot_index": 2, "attr": "species", "value": "Incineroar"},
                    {"turn_intent": "lock", "slot_index": 3, "attr": "species", "value": "Rillaboom"},
                ]
            }
        if self.mode == "one_of_six_locks":
            # Schema-valid: exactly one lock, one slot. The other five are not representable.
            return {
                "turn_intent": "lock",
                "slot_index": 2,
                "attr": "species",
                "value": "Incineroar",
            }
        if self.mode == "relock":
            return {
                "turn_intent": "lock",
                "slot_index": 1,
                "attr": "species",
                "value": "Pelipper",
            }
        if self.mode == "long_turn":
            return {"turn_intent": "team_review"}
        return {"turn_intent": "pending_response", "message": "unused"}


def _graph(box: _Box):
    return compile_graph(
        checkpointer=MemorySaver(),
        bootstrap_intake_parser=RunnableLambda(box.bootstrap),
        turn_intent_parser=RunnableLambda(box.turn),
    )


def _slim(state: dict) -> dict:
    view = _pending_view(state)
    return {
        "turn": view["turn"],
        "pending_kind": view["pending_kind"],
        "slots_with_any_value": view["slots_with_any_value"],
        "slots_fully_locked": view["slots_fully_locked"],
        "locked_flags": view["locked_flags"],
        "slot_species": view["slot_species"],
        "provisional_species": view["provisional_species"],
        "slot_commit_error": view["slot_commit_error"],
        "turn_intent": view["turn_intent"],
        "options": [
            o.get("species") or o.get("id") for o in view["options"]
        ][:8],
    }


def _run(box: _Box, steps: list[tuple[str, str]]) -> list[dict]:
    """compile_graph captures node callables, so patching discover_* after
    compile does nothing. These runs leave discovery on."""
    graph = _graph(box)
    config = thread_config("floor")
    transcript = []
    state = graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config)
    transcript.append({"user": None, "after": _pending_view(state)})
    for mode, text in steps:
        before_kind = (state.get("pending_presentation") or {}).get("kind")
        before_turn = state.get("turn")
        box.mode = mode
        state = graph.invoke({"pending_input": text}, config)
        checkpoint = graph.get_state(config).values
        transcript.append(
            {
                "user": text if len(text) < 500 else f"<len {len(text)}>",
                "user_len": len(text),
                "mode": mode,
                "pending_before": before_kind,
                "turn_before": before_turn,
                "after": _pending_view(state),
                "checkpoint_turn": checkpoint.get("turn"),
            }
        )
    return transcript


def main() -> None:
    os.environ["RECOMMENDER_TOOL_LOG"] = "/tmp/hosted_demo_floor_tool_log.jsonl"
    moves = ["Hurricane", "U-turn", "Weather Ball", "Protect"]
    spread = {"hp": 4, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 30}
    results: dict = {"format_id": DEFAULT_FORMAT_ID, "six_message": SIX}

    def with_builds(fn):
        def wrapped(*args, **kwargs):
            with (
                patch(
                    "recommender.propose.featured_or_common_set",
                    return_value={
                        "species": "Pelipper",
                        "ability": "Drizzle",
                        "moves": moves,
                        "item": "Damp Rock",
                        "nature": "Modest",
                    },
                ),
                patch(
                    "recommender.propose.get_resolved_build",
                    return_value={"spread": spread, "source_tier": "test", "verified": True},
                ),
            ):
                return fn(*args, **kwargs)

        return wrapped

    @with_builds
    def baseline():
        box = _Box()
        return _run(
            box,
            [
                ("rain", "Rain with Pelipper"),
                ("rain", "yes"),
                ("rain", "yes"),
            ],
        )

    results["baseline"] = baseline()

    def six():
        box = _Box()
        return _run(box, [("six_schema", SIX)]), box.seen

    six_transcript, six_seen = six()
    results["six_schema"] = {"transcript": six_transcript, "parser_seen": six_seen}

    def naive():
        box = _Box()
        return _run(box, [("naive_builds", SIX)])

    results["naive_builds"] = naive()

    @with_builds
    def after_one_lock(mode: str, text: str):
        box = _Box()
        return _run(
            box,
            [
                ("rain", "Rain with Pelipper"),
                ("rain", "yes"),
                ("rain", "yes"),
                (mode, text),
            ],
        )

    compound = (
        "Lock slot 2 as Incineroar. Lock slot 3 as Rillaboom. "
        "Lock slot 4 as Amoonguss. Lock slot 5 as Kingambit. "
        "Lock slot 6 as Flutter Mane."
    )
    results["one_of_six_locks"] = after_one_lock("one_of_six_locks", compound)
    results["multi_intent_list"] = after_one_lock("multi_intent_list", compound)
    results["relock"] = after_one_lock(
        "relock", "Lock slot 1 Pelipper again."
    )
    results["relock_message_constant"] = LOCK_FULLY_LOCKED_SLOT_MSG
    results["classify_fail_constant"] = CLASSIFY_FAIL_USER_MSG

    def parser_fail():
        box = _Box()
        # After one lock the graph is on candidate_selection, so an unmatched
        # reply reaches the turn parser.
        return _run(
            box,
            [
                ("rain", "Rain with Pelipper"),
                ("rain", "yes"),
                ("rain", "yes"),
                ("raise_turn", "lock everything"),
            ],
        )

    results["parser_fail_turn"] = with_builds(parser_fail)()

    def parser_fail_bootstrap():
        box = _Box()
        return _run(box, [("raise_bootstrap", "Rain with Pelipper")])

    results["parser_fail_bootstrap"] = parser_fail_bootstrap()

    long_text = "Rain with Pelipper " + ("x" * 20000)
    def long_msg():
        box = _Box()
        transcript = _run(box, [("long", long_text)])
        return {"transcript": transcript, "parser_seen": box.seen}

    results["long_message"] = long_msg()

    # Turn-parser length when there is no pending (idle after a lock).
    @with_builds
    def long_turn():
        box = _Box()
        text = "review " + ("y" * 20000)
        transcript = _run(
            box,
            [
                ("rain", "Rain with Pelipper"),
                ("rain", "yes"),
                ("rain", "yes"),
                ("long_turn", text),
            ],
        )
        return {"transcript_last": transcript[-1], "parser_seen": box.seen}

    results["long_turn"] = long_turn()

    def walk_accept_defaults():
        """Real builds. 'yes' takes option 0 then confirms. '1' is the first
        completion preference (attacker). No propose patch."""
        box = _Box()
        graph = _graph(box)
        config = thread_config("walk")
        state = graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config)
        rows = [{"user": None, "after": _slim(state)}]
        replies = {
            "bootstrap_intake": "Rain with Pelipper",
            "candidate_selection": "yes",
            "full_build_confirmation": "yes",
            "completion_preference": "1",
        }
        for _ in range(24):
            if rows[-1]["after"]["slots_fully_locked"] == 6:
                break
            kind = (state.get("pending_presentation") or {}).get("kind")
            text = replies.get(kind or "")
            if text is None:
                rows.append({"stopped": kind, "after": _slim(state)})
                break
            before_turn = state.get("turn")
            box.mode = "rain"
            state = graph.invoke({"pending_input": text}, config)
            rows.append(
                {
                    "user": text,
                    "pending_before": kind,
                    "turn_before": before_turn,
                    "after": _slim(state),
                }
            )
        return rows

    results["walk_accept_defaults"] = walk_accept_defaults()
    OUT.write_text(json.dumps(results, indent=2, default=str))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
