#!/usr/bin/env python3
"""Discovery-only: drive REAL deterministic graph on role-play requests.

Scratch only — not tracked. Never touches user SQLite DB.
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys
import time
import traceback
import uuid
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Callable

REPO = Path("/Users/nowaki027/pokemon-champions-agents")
sys.path.insert(0, str(REPO))

OUT = Path(
    "/Users/nowaki027/pokemon-champions-agents/scripts/eval/artifacts/"
    "det_graph_capability_failclosed_a/after"
)
RUNS = OUT / "runs"
RUNS.mkdir(parents=True, exist_ok=True)

MERGED_USAGE = (
    REPO
    / "scripts/eval/artifacts/_scratch_mc_showdown_fill/merged_usage_dir"
)
SHIPPED_USAGE = REPO / "data" / "usage"

TURN_CAP = 6
MODELS = ["qwen2.5:7b", "qwen3.5:latest"]

# Judged classes from 2026-10-02 model-driven role-play (_summary / sessions)
JUDGED = {
    "S1": "c",
    "S2": "b",
    "S3": "c",
    "S4": "c",  # prior run errored; script expected c
    "S5": "c",  # prior run errored; script expected compositional
    "S6": "d",
    "S7": "a",  # prior run errored; script treated as legality a
    "S8": "d",
    "S9": "d",
    "i1": "c",
    "i2": "c",
    "i3": "a",
    "i4": "a",
    "i5L": "c",  # replaced illegal i5 (was d)
    "i6L": "a",  # replaced illegal i6
    "i7": "a",
    "i8L": "b",  # replaced illegal i8 (was b)
    "P1": "d",
    "P2": "a",
    "P3": "b",
    "C1": None,
    "C2": None,
    "C3": None,
    "C4": None,
    "D1": None,
}


def ser(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    if isinstance(obj, (list, tuple)):
        return [ser(x) for x in obj]
    if isinstance(obj, dict):
        return {k: ser(v) for k, v in obj.items()}
    if hasattr(obj, "__dict__") and not isinstance(obj, type):
        try:
            return ser(vars(obj))
        except Exception:
            return repr(obj)
    return obj


def draft_summary(state: dict) -> list[dict]:
    out = []
    for i, slot in enumerate(state.get("team_draft") or []):
        sp = getattr(slot.species, "value", None) if hasattr(slot, "species") else None
        if not sp:
            continue
        out.append(
            {
                "i": i,
                "species": sp,
                "locked": bool(getattr(slot.species, "locked", False)),
                "item": getattr(slot.item, "value", None) if hasattr(slot, "item") else None,
                "ability": getattr(slot.ability, "value", None)
                if hasattr(slot, "ability")
                else None,
                "role": getattr(slot.role, "value", None) if hasattr(slot, "role") else None,
            }
        )
    return out


def state_snapshot(state: dict) -> dict:
    pending = state.get("pending_presentation")
    prov = state.get("provisional_slot")
    groups = []
    if isinstance(pending, dict):
        for g in pending.get("build_option_groups") or ():
            axes = g.get("axis") if isinstance(g, dict) else getattr(g, "axis", None)
            opts = g.get("options") if isinstance(g, dict) else getattr(g, "options", None)
            groups.append(
                {
                    "axis": axes,
                    "n_options": len(opts or ()),
                    "option_ids": [
                        (o.get("option_id") if isinstance(o, dict) else getattr(o, "option_id", None))
                        for o in (opts or ())
                    ][:12],
                }
            )
    return {
        "turn_intent": state.get("turn_intent"),
        "turn_payload": ser(state.get("turn_payload")),
        "pending_kind": (pending or {}).get("kind") if isinstance(pending, dict) else None,
        "draft": draft_summary(state),
        "constraints": ser(state.get("constraints") or []),
        "archetype": ser(state.get("archetype")),
        "slot_commit_error": state.get("slot_commit_error"),
        "bootstrap_intake_error": state.get("bootstrap_intake_error"),
        "correction_response": state.get("correction_response"),
        "compare_analysis": state.get("compare_analysis"),
        "provisional_species": getattr(prov, "species", None) if prov else None,
        "provisional_nature": getattr(prov, "nature", None) if prov else None,
        "provisional_spread": ser(getattr(prov, "spread", None)) if prov else None,
        "build_option_groups": groups,
        "candidate_discovery_error": ser(state.get("candidate_discovery_error")),
    }


def lock_species(
    draft: list,
    idx: int,
    species: str,
    *,
    ability: str | None = None,
    item: str | None = None,
    moves: list[str] | None = None,
    nature: str | None = None,
    spread: dict | None = None,
    role: str = "support",
) -> None:
    from recommender.state import Attr

    slot = draft[idx]
    slot.species = Attr(value=species, locked=True, reason=None)
    slot.role = Attr(value=role, locked=True, reason=None)
    if ability:
        slot.ability = Attr(value=ability, locked=True, reason=None)
    if item:
        slot.item = Attr(value=item, locked=True, reason=None)
    if moves:
        slot.moveset = Attr(value=list(moves), locked=True, reason=None)
    if nature:
        slot.nature = Attr(value=nature, locked=True, reason=None)
    if spread:
        slot.spread = Attr(value=dict(spread), locked=True, reason=None)


def build_fbc_seed(species: str) -> dict:
    """Real constructors → full_build_confirmation with species provisional."""
    from recommender.format import resolve_format
    from recommender.nodes_classify import _emit_full_build_confirmation
    from recommender.session import DEFAULT_FORMAT_ID
    from recommender.slot_fill import build_provisional_slot
    from recommender.state import PendingSlotIntent, empty_slot

    fmt = resolve_format(DEFAULT_FORMAT_ID)
    state = {
        "format_id": DEFAULT_FORMAT_ID,
        **fmt,
        "team_draft": [empty_slot() for _ in range(6)],
        "constraints": [],
        "rejected": [],
        "archetype": None,
        "bootstrap_intake_complete": True,
    }
    intent = PendingSlotIntent(
        schema_version=1,
        slot_index=0,
        species=species,
        target_role_decision=None,
        source="threat",
    )
    result = build_provisional_slot(intent, state)
    if not hasattr(result, "species"):
        return {
            "error": f"build_provisional_slot unresolved: {ser(result)}",
            "updates": {
                "bootstrap_intake_complete": True,
                "pending_presentation": None,
            },
        }
    emitted = _emit_full_build_confirmation(state, result)
    # Keep intent aligned with provisional for graph validity.
    from recommender.state import TargetRoleDecision
    from dataclasses import replace

    decision = result.target_role_decision
    if decision is None:
        decision = TargetRoleDecision(role_id="special_attacker", source="other")
        result = replace(result, target_role_decision=decision)
        emitted = _emit_full_build_confirmation(state, result)
    intent = replace(intent, target_role_decision=result.target_role_decision)
    updates = {
        "bootstrap_intake_complete": True,
        "pending_slot_intent": intent,
        **emitted,
    }
    return {
        "updates": updates,
        "provisional": ser(result),
        "groups": state_snapshot({"pending_presentation": emitted["pending_presentation"], "provisional_slot": emitted["provisional_slot"], "team_draft": state["team_draft"]}).get(
            "build_option_groups"
        ),
    }


def legality_precheck() -> dict:
    from recommender.legality import is_item_legal, is_species_legal, load_snapshot
    from recommender.ids import regulation_file_tag
    from recommender.format import resolve_format
    from recommender.session import DEFAULT_FORMAT_ID

    snap = load_snapshot()
    fmt = resolve_format(DEFAULT_FORMAT_ID)
    names_species = [
        "Kingambit",
        "Hatterene",
        "Farigiraf",
        "Torkoal",
        "Lilligant",
        "Tornadus",
        "Garchomp",
        "Pelipper",
        "Gholdengo",
        "Sinistcha",
        "Walking Wake",
        "Chi-Yu",
        "Miraidon",
        "Scovillain",
        "Whimsicott",
        "Lilligant-Hisui",
        "Tornadus-Therian",
    ]
    names_items = ["Choice Scarf", "Choice Specs"]
    rows = []
    for n in names_species:
        rows.append({"name": n, "kind": "species", "legal": is_species_legal(snap, n)})
    for n in names_items:
        rows.append({"name": n, "kind": "item", "legal": is_item_legal(snap, n)})
    subs = [
        {
            "illegal": "Lilligant",
            "substitute": "Scovillain",
            "role": "Chlorophyll sun offense (seed S4; also i7 teammate name)",
            "rationale": "Nearest legal Chlorophyll offensive Grass in snapshot; Lilligant/Lilligant-Hisui both illegal.",
        },
        {
            "illegal": "Tornadus",
            "substitute": "Whimsicott",
            "role": "Prankster Tailwind (seed S5)",
            "rationale": "Nearest legal Prankster+Tailwind support; Tornadus/Tornadus-Therian both illegal.",
        },
    ]
    return {
        "format_id": DEFAULT_FORMAT_ID,
        "regulation_mod": fmt["regulation_mod"],
        "regulation_tag": regulation_file_tag(fmt["regulation_mod"]),
        "snapshot_formats": snap["meta"]["formats"],
        "results": rows,
        "substitutions": subs,
    }


def wrap_parser(parser, bucket: list, label: str):
    """Wrap a LangChain runnable to record latency."""
    if parser is None:
        return None
    from langchain_core.runnables import RunnableLambda

    inner = parser

    def _call(x):
        t0 = time.perf_counter()
        err = None
        try:
            out = inner.invoke(x)
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            bucket.append(
                {
                    "label": label,
                    "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                    "error": err,
                }
            )
            raise
        bucket.append(
            {
                "label": label,
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                "error": None,
                "preview": str(out)[:400],
            }
        )
        return out

    return RunnableLambda(_call)


TOOL_LATENCIES: list[dict] = []


def install_tool_timer():
    """Patch log_tool_call to capture tool latencies."""
    import recommender.tool_log as tool_log
    import recommender.calc_client as cc

    orig = tool_log.log_tool_call

    def wrapped(tool, args, *, latency_ms, ok=True, error=None, turn=None, thread_id=None, **kw):
        TOOL_LATENCIES.append(
            {
                "tool": tool,
                "latency_ms": latency_ms,
                "ok": ok,
                "error": error,
                "turn": turn,
            }
        )
        return orig(
            tool,
            args,
            latency_ms=latency_ms,
            ok=ok,
            error=error,
            turn=turn,
            thread_id=thread_id,
            **kw,
        )

    tool_log.log_tool_call = wrapped
    if getattr(cc, "log_tool_call", None) is not None:
        cc.log_tool_call = wrapped
    return orig


def choose_followup(state: dict, req_id: str, turn_i: int) -> str | None:
    """Minimal natural answer when the graph is waiting on the user."""
    pending = state.get("pending_presentation")
    if not pending:
        # Idle after first turn — stop unless we still need multi-turn for nothing
        return None
    kind = pending.get("kind")
    if kind == "candidate_selection":
        return "1"
    if kind == "completion_preference":
        return "1"
    if kind == "confirm_abandon_build":
        return "yes"
    if kind in ("spread_reallocation_question", "spread_target_question", "item_moveset_conflict_question"):
        return "1"
    if kind == "bootstrap_intake":
        # Contextual bootstrap answers
        boot = {
            "i1": "Trick Room team, no weather setters",
            "i2": "hyper offense glass cannon, no rain sun sand or snow",
            "i3": "mono Electric doubles team",
            "S8": "I want a strong Reg M-C VGC team",
            "S9": "balance team for VGC doubles",
            "i7": "sun team with Torkoal and Scovillain",
            "i8L": "Hatterene Trick Room support",
            "P3": "Walking Wake",
        }
        return boot.get(req_id, "VGC doubles team, no strong preference")
    if kind == "full_build_confirmation":
        # For C1/D1 the request IS about the provisional — do not auto-confirm
        if req_id in ("C1", "C1b", "D1", "D1b", "C2", "C3", "C4"):
            return None
        return "yes"
    return None


def classify_outcome(req: dict, turns: list, final_state: dict, visible: str) -> dict:
    """Heuristic outcome class + independent check notes (legality/calc only)."""
    from recommender.legality import is_item_legal, is_species_legal, load_snapshot
    from recommender.ids import to_id

    snap = load_snapshot()
    rid = req["id"]
    intents = [t.get("intent") for t in turns]
    start = req.get("start_snap") or {}
    end_draft = draft_summary(final_state)
    start_draft = start.get("draft") or []
    state_changed = ser(start_draft) != ser(end_draft) or ser(start.get("constraints")) != ser(
        final_state.get("constraints") or []
    )
    err = any(t.get("error") for t in turns)
    stalled = len(turns) >= TURN_CAP and final_state.get("pending_presentation") is not None
    visible_l = (visible or "").lower()
    fail_closed_markers = (
        "not legal",
        "illegal",
        "can't",
        "cannot",
        "don't support",
        "do not support",
        "not sure what",
        "clarify",
        "which",
        "could you",
        "i'm not able",
        "unable to",
        "fail",
        "outside",
        "ou is",
        "not a champions",
    )

    checks: list[str] = []
    outcome = "PARTIAL"

    if err:
        return {"outcome": "STALL/ERROR", "checks": ["exception during run"], "intents": intents}

    # Illegal probes
    if rid in ("P1", "P2", "P3"):
        illegal_ok = not state_changed
        # honesty: mention legality
        mentions_illegal = any(
            x in visible_l for x in ("illegal", "not legal", "banned", "can't use", "cannot")
        )
        silent_sub = False
        for row in end_draft:
            if rid == "P1" and to_id(row["species"]) in ("chiyu",):
                silent_sub = True
            if rid == "P2" and to_id(row["species"]) in ("miraidon",):
                silent_sub = True
            if rid == "P3" and to_id(row["species"]) in ("walkingwake",):
                silent_sub = True
        if illegal_ok and mentions_illegal and not silent_sub:
            outcome = "FAIL-CLOSED"
        elif silent_sub or (state_changed and any(to_id(r["species"]) in ("chiyu", "miraidon", "walkingwake") for r in end_draft)):
            outcome = "MISROUTED"
            checks.append("treated illegal entity as usable or silent-substituted")
        elif illegal_ok:
            outcome = "FAIL-CLOSED" if mentions_illegal or any(i == "pending_response" for i in intents) else "PARTIAL"
            checks.append(f"no state change; legality_mentioned={mentions_illegal}")
        else:
            outcome = "MISROUTED"
            checks.append("state changed on illegal-entity probe")
        return {"outcome": outcome, "checks": checks, "intents": intents, "silent_sub": silent_sub}

    # Slot type constraints S1/S2
    if rid == "S1":
        # SERVED if slot2 constrained to Water or filled with Water
        cons = final_state.get("constraints") or []
        water_cons = False
        for c in cons:
            blob = json.dumps(ser(c)).lower()
            if "water" in blob and ("type" in blob or "mechanical" in blob):
                water_cons = True
        slot2 = None
        draft = final_state.get("team_draft") or []
        if len(draft) > 1 and draft[1].species.value:
            types = (snap["species"].get(to_id(draft[1].species.value)) or {}).get("types") or []
            slot2 = types
            checks.append(f"slot2 species={draft[1].species.value} types={types}")
        if water_cons or (slot2 and "Water" in slot2):
            outcome = "SERVED"
        elif any(i in ("constraint", "lock", "edit") for i in intents):
            outcome = "PARTIAL"
        elif any(i == "pending_response" for i in intents) and not state_changed:
            outcome = "FAIL-CLOSED"
        else:
            outcome = "MISROUTED" if state_changed else "FAIL-CLOSED"
        checks.append(f"water_constraint={water_cons}")
        return {"outcome": outcome, "checks": checks, "intents": intents}

    if rid == "S2":
        cons = final_state.get("constraints") or []
        fire_cons = any("fire" in json.dumps(ser(c)).lower() for c in cons)
        slot4 = None
        draft = final_state.get("team_draft") or []
        if len(draft) > 3 and draft[3].species.value:
            types = (snap["species"].get(to_id(draft[3].species.value)) or {}).get("types") or []
            slot4 = types
            checks.append(f"slot4 species={draft[3].species.value} types={types}")
        # "bulky" has no mechanical kind — partial at best if Fire served
        if slot4 and "Fire" in slot4:
            outcome = "PARTIAL"  # fire yes, bulky unconstrained
            checks.append("Fire type present; bulky not mechanically enforced")
        elif fire_cons:
            outcome = "PARTIAL"
            checks.append("Fire constraint recorded; bulky not a kind")
        elif not state_changed and any(m in visible_l for m in fail_closed_markers):
            outcome = "FAIL-CLOSED"
        else:
            outcome = "MISROUTED" if state_changed else "FAIL-CLOSED"
        return {"outcome": outcome, "checks": checks, "intents": intents}

    if rid == "S3":
        # Need Fire in slot3 that outspeeds max Spe Garchomp — verify via calc if pick exists
        draft = final_state.get("team_draft") or []
        pick = draft[2].species.value if len(draft) > 2 else None
        if pick:
            types = (snap["species"].get(to_id(pick)) or {}).get("types") or []
            checks.append(f"slot3={pick} types={types}")
            if "Fire" in types:
                from recommender.calc_client import CalcClient

                client = CalcClient()
                try:
                    a = client.calculate(
                        {
                            "species": pick,
                            "nature": "Timid",
                            "evs": {"hp": 2, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 32},
                            "ability": "Blaze",
                            "item": "Focus Sash",
                            "moves": ["Protect"],
                        },
                        {
                            "species": "Garchomp",
                            "nature": "Jolly",
                            "evs": {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
                            "ability": "Rough Skin",
                            "item": "Life Orb",
                            "moves": ["Earthquake"],
                        },
                        "Protect",
                    )
                    spe_a = ((a.get("raw") or {}).get("stats") or {}).get("attacker", {}).get("spe")
                    spe_d = ((a.get("raw") or {}).get("stats") or {}).get("defender", {}).get("spe")
                    checks.append(f"calc Spe pick={spe_a} garchomp={spe_d}")
                    if spe_a is not None and spe_d is not None and spe_a > spe_d:
                        outcome = "SERVED"
                    else:
                        outcome = "PARTIAL"
                        checks.append("Fire pick does not outspeed max-SP Jolly Garchomp under Timid SP32")
                except Exception as e:
                    outcome = "PARTIAL"
                    checks.append(f"calc failed: {e}")
            else:
                outcome = "MISROUTED"
        elif stalled:
            outcome = "STALL/ERROR"
        elif not state_changed:
            outcome = "FAIL-CLOSED" if any(m in visible_l for m in fail_closed_markers) else "PARTIAL"
        else:
            outcome = "PARTIAL"
        return {"outcome": outcome, "checks": checks, "intents": intents}

    if rid == "i3":
        cons = final_state.get("constraints") or []
        elec = any(
            "electric" in json.dumps(ser(c)).lower() for c in cons
        )
        drafts = draft_summary(final_state)
        all_elec = True
        if drafts:
            for row in drafts:
                types = (snap["species"].get(to_id(row["species"])) or {}).get("types") or []
                if "Electric" not in types:
                    all_elec = False
                    checks.append(f"non-electric {row['species']} {types}")
        else:
            all_elec = False
        if elec or (drafts and all_elec):
            outcome = "SERVED" if elec or all_elec else "PARTIAL"
        elif not state_changed:
            outcome = "FAIL-CLOSED" if any(m in visible_l for m in fail_closed_markers) else "PARTIAL"
        else:
            outcome = "MISROUTED"
        checks.append(f"electric_constraint={elec}")
        return {"outcome": outcome, "checks": checks, "intents": intents}

    if rid == "i4":
        # scrap team — seed had Pelipper; served if draft empty / unlocked
        end = draft_summary(final_state)
        if not end:
            outcome = "SERVED"
            checks.append("draft empty after scrap")
        elif all(not r.get("locked") for r in end):
            outcome = "SERVED"
        elif not any(r["species"] == "Pelipper" for r in end):
            outcome = "PARTIAL"
            checks.append("Pelipper gone but draft not empty")
        else:
            outcome = "FAIL-CLOSED" if not state_changed else "MISROUTED"
        return {"outcome": outcome, "checks": checks, "intents": intents}

    if rid == "C4":
        # judgment — expect clarify or fail-closed
        if any(i == "compare" for i in intents):
            outcome = "PARTIAL"
            checks.append("compare ran but 'better' undefined")
        elif not state_changed and (
            any(i == "pending_response" for i in intents)
            or any(m in visible_l for m in ("better", "depend", "clarify", "prefer", "goal"))
        ):
            outcome = "FAIL-CLOSED"
        else:
            outcome = "MISROUTED" if state_changed else "FAIL-CLOSED"
        return {"outcome": outcome, "checks": checks, "intents": intents}

    if rid in ("C1", "C1b", "C2", "C3", "D1", "D1b"):
        if any(i == "compare" for i in intents):
            outcome = "PARTIAL"
            checks.append("build_compare intent observed")
        elif any(i == "edit" for i in intents):
            outcome = "PARTIAL"
            checks.append("edit path; may not be counterfactual compare")
        elif not state_changed and any(i == "pending_response" for i in intents):
            outcome = "FAIL-CLOSED"
        elif stalled:
            outcome = "STALL/ERROR"
        else:
            outcome = "MISROUTED" if state_changed and "compare" not in intents else "PARTIAL"
        if final_state.get("compare_analysis"):
            checks.append("compare_analysis present")
        return {"outcome": outcome, "checks": checks, "intents": intents}

    # Generic
    if stalled:
        outcome = "STALL/ERROR"
    elif any(i == "pending_response" for i in intents) and not state_changed:
        outcome = "FAIL-CLOSED"
    elif state_changed or final_state.get("compare_analysis") or final_state.get("last_team_review"):
        # served-ish if user-visible looks helpful — keep PARTIAL without stronger check
        outcome = "PARTIAL"
        if rid in ("S6", "S8", "S9") and not state_changed:
            outcome = "FAIL-CLOSED"
    else:
        outcome = "FAIL-CLOSED" if any(m in visible_l for m in fail_closed_markers) else "PARTIAL"
    return {"outcome": outcome, "checks": checks, "intents": intents}


def extract_claims(text: str) -> list[dict]:
    from recommender.system_claims import iter_verifiable_claims_from_message
    from recommender.legality import load_snapshot, is_species_legal, is_item_legal
    from recommender.ids import to_id

    snap = load_snapshot()
    out = []
    for c in iter_verifiable_claims_from_message(text or ""):
        row = {
            "kind": c.kind,
            "subject_species": c.subject_species,
            "asserted_value": c.asserted_value,
            "hand_verify": None,
            "false": None,
        }
        # hand verify type/ability against snapshot
        sid = to_id(c.subject_species or "")
        entry = snap["species"].get(sid) or {}
        if c.kind == "type":
            types = entry.get("types") or []
            ok = c.asserted_value in types
            row["hand_verify"] = f"snapshot types={types}"
            row["false"] = not ok
        elif c.kind == "ability":
            abs_ = entry.get("abilities") or {}
            vals = list(abs_.values()) if isinstance(abs_, dict) else list(abs_ or [])
            ok = any(to_id(a) == to_id(str(c.asserted_value)) for a in vals)
            row["hand_verify"] = f"snapshot abilities={vals}"
            row["false"] = not ok
        else:
            row["hand_verify"] = "extracted; manual kind"
        out.append(row)
    return out


def run_one(req: dict, *, model: str, usage_dir: Path, repeat: int = 0) -> dict:
    from langgraph.checkpoint.memory import MemorySaver
    from recommender.graph import compile_graph
    from recommender.cli import invoke_user_text
    from recommender.present_text import format_turn
    from recommender.session import DEFAULT_FORMAT_ID, thread_config
    from recommender.state import empty_slot, Attr
    from recommender.bootstrap import build_ollama_bootstrap_intake_parser
    from recommender.turn_intent import build_ollama_turn_intent_parser
    import recommender.usage_data as usage_data

    TOOL_LATENCIES.clear()
    llm_bucket: list[dict] = []

    # usage monkeypatch
    prev_usage = usage_data.USAGE_DIR
    usage_data.USAGE_DIR = usage_dir
    # clear caches if any
    for fn_name in ("load_usage", "species_usage", "showdown_species_map"):
        fn = getattr(usage_data, fn_name, None)
        if fn and hasattr(fn, "cache_clear"):
            fn.cache_clear()

    thread_id = f"disc-{req['id']}-{model.replace(':','_')}-r{repeat}-{uuid.uuid4().hex[:8]}"
    boot = wrap_parser(
        build_ollama_bootstrap_intake_parser(model, keep_alive="30m"),
        llm_bucket,
        "bootstrap",
    )
    turn_p = wrap_parser(
        build_ollama_turn_intent_parser(model, keep_alive="30m"),
        llm_bucket,
        "turn_intent",
    )
    graph = compile_graph(
        checkpointer=MemorySaver(),
        bootstrap_intake_parser=boot,
        turn_intent_parser=turn_p,
    )
    config = thread_config(thread_id)
    t_init = time.perf_counter()
    state = graph.invoke({"format_id": DEFAULT_FORMAT_ID}, config)
    init_ms = (time.perf_counter() - t_init) * 1000

    seed_notes = []
    if req.get("seed_fn"):
        updates = req["seed_fn"](state)
        seed_notes = updates.pop("_notes", [])
        if updates:
            graph.update_state(config, updates)
            state = graph.get_state(config).values

    start_snap = state_snapshot(state)
    req_local = {**req, "start_snap": start_snap}
    turns = []
    user_text = req["user"]
    visible_all = []
    errors = []

    for turn_i in range(TURN_CAP):
        text = user_text if turn_i == 0 else choose_followup(state, req["id"], turn_i)
        if text is None:
            break
        before = state_snapshot(state)
        t0 = time.perf_counter()
        try:
            state = invoke_user_text(graph, config, text)
            err = None
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            errors.append(err)
            traceback.print_exc()
            turns.append(
                {
                    "turn": turn_i,
                    "user": text,
                    "error": err,
                    "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                }
            )
            break
        wall_ms = (time.perf_counter() - t0) * 1000
        unmatched = state.get("turn_intent") == "pending_response"
        try:
            visible = format_turn(state, unmatched=unmatched)
        except Exception as e:
            visible = f"[format_turn error: {e}]"
        visible_all.append(visible)
        after = state_snapshot(state)
        # llm latencies this turn ≈ new entries
        turns.append(
            {
                "turn": turn_i,
                "user": text,
                "intent": state.get("turn_intent"),
                "payload": ser(state.get("turn_payload")),
                "route_pending_kind": after.get("pending_kind"),
                "before": before,
                "after": after,
                "visible": visible,
                "wall_ms": round(wall_ms, 1),
                "error": None,
                "correction_response": state.get("correction_response"),
                "compare_analysis": state.get("compare_analysis"),
            }
        )
        # stop if idle and we already sent the request
        if turn_i > 0 and state.get("pending_presentation") is None:
            # one more? stop — request handled
            break
        # For C*/D* on FBC: only send the comparison once
        if turn_i == 0 and req["id"] in ("C1", "C1b", "C2", "C3", "C4", "D1", "D1b"):
            pending_now = state.get("pending_presentation") or {}
            # allow one follow-up if it asks a clarifying question via pending_response
            if pending_now.get("kind") == "full_build_confirmation":
                if state.get("turn_intent") not in (None, "pending_response"):
                    break
            if not pending_now:
                break

    final_visible = "\n---\n".join(visible_all)
    claims = []
    for block in visible_all:
        claims.extend(extract_claims(block))
    outcome = classify_outcome(req_local, turns, state, final_visible)

    # showdown fill presence
    usage_meta = {}
    try:
        u = usage_data.load_usage("champions-reg-mc")
        sd = (u or {}).get("showdown_vgc_mb") or {}
        usage_meta = {
            "usage_dir": str(usage_dir),
            "showdown_species_n": len((sd.get("species") or {})),
            "meta_sources": (u or {}).get("meta", {}).get("sources"),
        }
    except Exception as e:
        usage_meta = {"usage_dir": str(usage_dir), "error": str(e)}

    result = {
        "id": req["id"],
        "model": model,
        "repeat": repeat,
        "thread_id": thread_id,
        "user": req["user"],
        "usage": usage_meta,
        "seed_notes": seed_notes,
        "start": start_snap,
        "init_ms": round(init_ms, 1),
        "turns": turns,
        "llm_calls": llm_bucket,
        "tool_latencies": list(TOOL_LATENCIES),
        "final": state_snapshot(state),
        "final_visible": final_visible,
        "claims": claims,
        "outcome": outcome,
        "judged_class": JUDGED.get(req["id"].rstrip("b")),
        "errors": errors,
        "n_turns": len(turns),
    }

    usage_data.USAGE_DIR = prev_usage
    tag = f"{req['id']}__{model.replace(':','_')}__{usage_dir.name}__r{repeat}"
    path = RUNS / f"{tag}.json"
    path.write_text(json.dumps(result, indent=2, default=str))
    print(
        f"DONE {tag} outcome={outcome.get('outcome')} turns={len(turns)} "
        f"llm_ms={sum(x['latency_ms'] for x in llm_bucket):.0f}",
        flush=True,
    )
    return result


def make_requests() -> list[dict]:
    """Capability + probe requests with seeds from prior scratch where present."""

    def seed_idle(state):
        # Clear bootstrap pending so turn_intent runs on idle
        return {
            "bootstrap_intake_complete": True,
            "pending_presentation": None,
            "_notes": ["idle: bootstrap complete, no pending"],
        }

    def seed_s4(state):
        from recommender.state import empty_slot

        draft = [empty_slot() for _ in range(6)]
        lock_species(
            draft,
            0,
            "Farigiraf",
            ability="Armor Tail",
            item="Sitrus Berry",
            moves=["Psychic", "Helping Hand", "Trick Room", "Protect"],
            role="support",
        )
        lock_species(
            draft,
            1,
            "Torkoal",
            ability="Drought",
            item="Heat Rock",
            moves=["Eruption", "Solar Beam", "Protect", "Yawn"],
            role="offense",
        )
        # SUBSTITUTE Lilligant → Scovillain
        lock_species(
            draft,
            2,
            "Scovillain",
            ability="Chlorophyll",
            item="Focus Sash",
            moves=["Flamethrower", "Solar Beam", "Protect", "Growth"],
            role="offense",
        )
        return {
            "team_draft": draft,
            "bootstrap_intake_complete": True,
            "pending_presentation": None,
            "_notes": [
                "seeded Farigiraf/Torkoal/Scovillain (Lilligant→Scovillain subst)",
            ],
        }

    def seed_s5(state):
        from recommender.state import empty_slot

        draft = [empty_slot() for _ in range(6)]
        # SUBSTITUTE Tornadus → Whimsicott
        lock_species(
            draft,
            0,
            "Whimsicott",
            ability="Prankster",
            item="Covert Cloak",
            moves=["Tailwind", "Moonblast", "Taunt", "Protect"],
            role="support",
        )
        lock_species(
            draft,
            4,
            "Garchomp",
            ability="Rough Skin",
            item="Life Orb",
            moves=["Earthquake", "Dragon Claw", "Rock Slide", "Protect"],
            role="offense",
        )
        return {
            "team_draft": draft,
            "bootstrap_intake_complete": True,
            "pending_presentation": None,
            "_notes": [
                "seeded Whimsicott locked (Tornadus→Whimsicott), Garchomp slot5",
            ],
        }

    def seed_i4(state):
        from recommender.state import empty_slot

        draft = [empty_slot() for _ in range(6)]
        lock_species(
            draft, 0, "Pelipper", ability="Drizzle", item="Damp Rock", role="support"
        )
        return {
            "team_draft": draft,
            "bootstrap_intake_complete": True,
            "pending_presentation": None,
            "_notes": ["seeded Pelipper slot0"],
        }

    def seed_fbc(species: str):
        def _fn(state):
            built = build_fbc_seed(species)
            notes = [f"FBC seed via build_provisional_slot({species})"]
            if built.get("error"):
                notes.append(built["error"])
            upd = built.get("updates") or {}
            upd["_notes"] = notes
            return upd

        return _fn

    # Exact strings from /tmp/md_tool_roleplay/roleplay_sessions.py SESSIONS
    # plus task-specified legal counterparts / new families.
    reqs = [
        {"id": "S1", "user": "Slot 2 should be a Water type.", "seed_fn": seed_idle, "usage_secondary": False},
        {"id": "S2", "user": "Give me a bulky Fire type for slot 4.", "seed_fn": seed_idle, "usage_secondary": False},
        {"id": "S3", "user": "Slot 3 should be a Fire type that outspeeds max-speed Garchomp.", "seed_fn": seed_idle, "usage_secondary": True},
        {"id": "S4", "user": "Which of my picks actually threatens Kingambit? Swap the weakest one for something that does.", "seed_fn": seed_s4, "usage_secondary": True},
        {"id": "S5", "user": "Swap slot 5 for something that handles Ground attackers without losing Tailwind.", "seed_fn": seed_s5, "usage_secondary": False},
        {"id": "S6", "user": "Why did you pick Farigiraf over Hatterene?", "seed_fn": seed_idle, "usage_secondary": False},
        {"id": "S7", "user": "Can I run two Choice Scarf users?", "seed_fn": seed_idle, "usage_secondary": False},
        {"id": "S8", "user": "What's the best team in Reg M-C right now?", "seed_fn": seed_idle, "usage_secondary": True},
        {"id": "S9", "user": "Build me something like an OU balance team.", "seed_fn": seed_idle, "usage_secondary": False},
        {"id": "i1", "user": "trick room team only please, no weather", "seed_fn": None, "usage_secondary": False},  # bootstrap
        {"id": "i2", "user": "glass cannon HO, no rain/sun/sand/snow, just hit hard", "seed_fn": None, "usage_secondary": False},
        {"id": "i3", "user": "mono electric doubles for fun", "seed_fn": None, "usage_secondary": False},
        {"id": "i4", "user": "scrap the whole team and start over", "seed_fn": seed_i4, "usage_secondary": False},
        {"id": "i5L", "user": "does Choice Scarf Gholdengo OHKO Kingambit", "seed_fn": seed_idle, "usage_secondary": True},
        {"id": "i6L", "user": "Garchomp + Scarf", "seed_fn": seed_idle, "usage_secondary": False},
        {"id": "i7", "user": "who pairs with both Torkoal and Scovillain", "seed_fn": seed_idle, "usage_secondary": True},  # subst Lilligant→Scovillain in text
        {"id": "i8L", "user": "what support does Hatterene need", "seed_fn": seed_idle, "usage_secondary": True},
        {"id": "P1", "user": "does Specs Chi-Yu OHKO Kingambit", "seed_fn": seed_idle, "usage_secondary": False, "probe": True},
        {"id": "P2", "user": "Miraidon + Scarf", "seed_fn": seed_idle, "usage_secondary": False, "probe": True},
        {"id": "P3", "user": "what support does Walking Wake need", "seed_fn": seed_idle, "usage_secondary": False, "probe": True},
        {"id": "C1", "user": "Does running Timid over Modest let Pelipper outspeed anyone important?", "seed_fn": seed_idle, "usage_secondary": True},
        {"id": "C1b", "user": "Does running Timid over Modest let Pelipper outspeed anyone important?", "seed_fn": seed_fbc("Pelipper"), "usage_secondary": True},
        {"id": "C2", "user": "Does Jolly vs Adamant change which threats my Garchomp outspeeds?", "seed_fn": seed_idle, "usage_secondary": True},
        {"id": "C3", "user": "Does max Attack on Kingambit change what it OHKOs?", "seed_fn": seed_idle, "usage_secondary": True},
        {"id": "C4", "user": "Is Modest or Timid better on Pelipper?", "seed_fn": seed_idle, "usage_secondary": False},
        {"id": "D1", "user": "Should I run max Def, max Sp. Def, or something in between for Sinistcha?", "seed_fn": seed_idle, "usage_secondary": True},
        {"id": "D1b", "user": "Should I run max Def, max Sp. Def, or something in between for Sinistcha?", "seed_fn": seed_fbc("Sinistcha"), "usage_secondary": True},
    ]
    # Note: task listed 25 = 9+5+3+3+4+1; C1b/D1b are the "also from FBC" variants of C1/D1
    return reqs


def independent_checks(usage_dir: Path) -> dict:
    """Calc-only independent checks for C1-C3, D1."""
    from recommender.calc_client import CalcClient
    from recommender.usage_data import load_usage, species_usage
    from recommender.by_usage import query_by_usage
    import recommender.usage_data as usage_data

    prev = usage_data.USAGE_DIR
    usage_data.USAGE_DIR = usage_dir
    client = CalcClient()
    out: dict[str, Any] = {"usage_dir": str(usage_dir), "sp_rules": {"budget": 66, "cap": 32}}

    # top threats
    try:
        usage_rows = query_by_usage(None, 20)
        threats = [getattr(r, "ladder_species", None) or getattr(r, "species", None) for r in usage_rows]
        threats = [t for t in threats if t][:20]
    except Exception as e:
        threats = []
        out["threats_error"] = str(e)
    out["threats"] = threats

    def spe_of(species, nature, spe_sp, **kit):
        # Full 66 SP: prioritize Spe, dump remainder into HP then attacking stat.
        rem = 66 - spe_sp
        hp = min(32, rem)
        rem -= hp
        atk = 0
        spa = 0
        if nature in ("Adamant", "Jolly", "Brave"):
            atk = min(32, rem)
            rem -= atk
        else:
            spa = min(32, rem)
            rem -= spa
        spd = rem
        evs = {"hp": hp, "atk": atk, "def": 0, "spa": spa, "spd": spd, "spe": spe_sp}
        r = client.calculate(
            {
                "species": species,
                "nature": nature,
                "evs": evs,
                "ability": kit.get("ability") or "Illuminate",
                "item": kit.get("item") or "Focus Sash",
                "moves": kit.get("moves") or ["Protect"],
            },
            {
                "species": "Blissey",
                "nature": "Bold",
                "evs": {"hp": 32, "atk": 0, "def": 32, "spa": 0, "spd": 2, "spe": 0},
                "ability": "Natural Cure",
                "item": "Leftovers",
                "moves": ["Soft-Boiled"],
            },
            "Protect",
        )
        return ((r.get("raw") or {}).get("stats") or {}).get("attacker", {}).get("spe")

    # C1 Pelipper Timid vs Modest Spe=32
    try:
        timid = spe_of("Pelipper", "Timid", 32, ability="Drizzle", item="Damp Rock", moves=["Hurricane"])
        modest = spe_of("Pelipper", "Modest", 32, ability="Drizzle", item="Damp Rock", moves=["Hurricane"])
        flips = []
        for t in threats:
            try:
                tspe = spe_of(t, "Timid", 32)
                # compare both pelipper speeds vs threat — use threat jolly/timid max as proxy
                # better: get threat spe at its usage set
                entry = species_usage(t, regulation="champions-reg-mc") or {}
                # fallback max spe
                t_spe = spe_of(t, "Jolly", 32)
                t_spe2 = spe_of(t, "Timid", 32)
                threat_spe = max(x for x in (t_spe, t_spe2) if x is not None)
                if timid is not None and modest is not None and threat_spe is not None:
                    if (timid > threat_spe) != (modest > threat_spe):
                        flips.append({"threat": t, "threat_spe_proxy": threat_spe, "timid": timid, "modest": modest})
            except Exception:
                continue
        out["C1"] = {"pelipper_timid_spe": timid, "pelipper_modest_spe": modest, "flips": flips, "n_threats": len(threats)}
    except Exception as e:
        out["C1"] = {"error": str(e)}

    # C2 Garchomp Jolly vs Adamant Spe=32
    try:
        jolly = spe_of("Garchomp", "Jolly", 32, ability="Rough Skin", item="Life Orb", moves=["Earthquake"])
        adamant = spe_of("Garchomp", "Adamant", 32, ability="Rough Skin", item="Life Orb", moves=["Earthquake"])
        flips = []
        for t in threats:
            try:
                threat_spe = max(
                    x
                    for x in (
                        spe_of(t, "Jolly", 32),
                        spe_of(t, "Timid", 32),
                    )
                    if x is not None
                )
                if (jolly > threat_spe) != (adamant > threat_spe):
                    flips.append({"threat": t, "threat_spe_proxy": threat_spe, "jolly": jolly, "adamant": adamant})
            except Exception:
                continue
        out["C2"] = {"garchomp_jolly_spe": jolly, "garchomp_adamant_spe": adamant, "flips": flips}
    except Exception as e:
        out["C2"] = {"error": str(e)}

    # C3 Kingambit max Atk vs not — damage vs top threats
    def kb_vs(target, atk_sp):
        # remaining SP: 66-atk_sp; put into hp/spe roughly
        rem = 66 - atk_sp
        hp = min(32, rem)
        rem -= hp
        spe = min(32, rem)
        rem -= spe
        spd = rem
        moves = ["Kowtow Cleave", "Sucker Punch", "Iron Head", "Protect"]
        results = {}
        for mv in moves[:3]:
            try:
                r = client.calculate(
                    {
                        "species": "Kingambit",
                        "nature": "Adamant",
                        "evs": {"hp": hp, "atk": atk_sp, "def": 0, "spa": 0, "spd": spd, "spe": spe},
                        "ability": "Defiant",
                        "item": "Black Glasses",
                        "moves": moves,
                    },
                    {
                        "species": target,
                        "nature": "Bold",
                        "evs": {"hp": 32, "atk": 0, "def": 20, "spa": 0, "spd": 14, "spe": 0},
                        "ability": "Illuminate",
                        "item": "Sitrus Berry",
                        "moves": ["Protect"],
                    },
                    mv,
                )
                results[mv] = {
                    "damageRange": r.get("damageRange"),
                    "koChance": r.get("koChance"),
                    "atk_stat": ((r.get("raw") or {}).get("stats") or {}).get("attacker", {}).get("atk"),
                }
            except Exception as e:
                results[mv] = {"error": str(e)}
        return {"spread": {"hp": hp, "atk": atk_sp, "def": 0, "spa": 0, "spd": spd, "spe": spe}, "vs": results}

    try:
        targets = threats[:8] or ["Flutter Mane", "Urshifu-Rapid-Strike", "Rillaboom"]
        # filter legal targets only
        from recommender.legality import is_species_legal, load_snapshot

        snap = load_snapshot()
        targets = [t for t in targets if is_species_legal(snap, t)][:8]
        out["C3"] = {
            "atk32": {t: kb_vs(t, 32) for t in targets},
            "atk20": {t: kb_vs(t, 20) for t in targets},
            "assumed_remainder": "hp first (cap 32), then spe, then spd; nature Adamant; item Black Glasses",
        }
    except Exception as e:
        out["C3"] = {"error": str(e)}

    # D1 Sinistcha bulk
    def sin_spread(defn, spdef):
        rem = 66 - defn - spdef
        hp = min(32, rem)
        rem -= hp
        spa = min(32, rem)
        rem -= spa
        spe = rem
        return {"hp": hp, "atk": 0, "def": defn, "spa": spa, "spd": spdef, "spe": spe}

    spreads = {
        "max_def": sin_spread(32, 0),
        "max_spd": sin_spread(0, 32),
        "split_16_16": sin_spread(16, 16),
    }
    # fix: max_def with 0 spd leaves points — already allocated to hp/spa/spe
    out["D1_spreads"] = spreads
    out["D1_assumed"] = "HP then Spa then Spe for remainder; nature Bold; ability Hospitality; item Sitrus Berry"
    d1 = {}
    for t in (threats[:10] or ["Kingambit", "Garchomp", "Rillaboom"]):
        entry = {}
        # usage moves
        try:
            su = species_usage(t, regulation="champions-reg-mc") or {}
            moves = []
            for mrow in (su.get("moves") or [])[:6]:
                if isinstance(mrow, dict):
                    moves.append(mrow.get("move") or mrow.get("name"))
                elif isinstance(mrow, str):
                    moves.append(mrow)
            moves = [m for m in moves if m and m not in ("Protect", "Substitute", "Rest")][:3]
            if not moves:
                moves = ["Frustration"]  # will likely error — skip
        except Exception:
            moves = []
        for sname, spr in spreads.items():
            entry[sname] = {}
            for mv in moves or []:
                try:
                    r = client.calculate(
                        {
                            "species": t,
                            "nature": "Adamant",
                            "evs": {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
                            "ability": "Illuminate",
                            "item": "Life Orb",
                            "moves": [mv],
                        },
                        {
                            "species": "Sinistcha",
                            "nature": "Bold",
                            "evs": spr,
                            "ability": "Hospitality",
                            "item": "Sitrus Berry",
                            "moves": ["Matcha Gotcha", "Rage Powder", "Strength Sap", "Protect"],
                        },
                        mv,
                    )
                    entry[sname][mv] = {
                        "damageRange": r.get("damageRange"),
                        "koChance": r.get("koChance"),
                    }
                except Exception as e:
                    entry[sname][mv] = {"error": str(e)[:120]}
        d1[t] = entry
    out["D1"] = d1

    usage_data.USAGE_DIR = prev
    return out


def main():
    os.chdir(REPO)
    os.environ.setdefault("POKEMON_CHAMPIONS_LLM_PROVIDER", "ollama")

    # HEAD
    import subprocess

    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO).decode().strip()
    head_subj = subprocess.check_output(["git", "log", "-1", "--oneline"], cwd=REPO).decode().strip()

    install_tool_timer()
    legal = legality_precheck()
    (OUT / "legality_precheck.json").write_text(json.dumps(legal, indent=2))
    print("LEGALITY", json.dumps(legal, indent=2)[:2000], flush=True)

    # verify merged usage
    import recommender.usage_data as usage_data

    usage_data.USAGE_DIR = MERGED_USAGE
    u = usage_data.load_usage("champions-reg-mc")
    print(
        "MERGED showdown n",
        len(((u or {}).get("showdown_vgc_mb") or {}).get("species") or {}),
        flush=True,
    )
    usage_data.USAGE_DIR = SHIPPED_USAGE

    meta = {
        "head": head,
        "head_subject": head_subj,
        "regulation_mod": legal["regulation_mod"],
        "regulation_tag": legal["regulation_tag"],
        "format_id": legal["format_id"],
        "models": MODELS,
        "merged_usage": str(MERGED_USAGE),
        "shipped_usage": str(SHIPPED_USAGE),
        "turn_cap": TURN_CAP,
        "substitutions": legal["substitutions"],
        "i7_user_note": "scratch had 'who pairs with both torkoal and lilligant'; capability set substituted Scovillain into user text",
        "i4_user_note": "scratch exact: 'scrap the whole team and start over' (task short form differed)",
    }
    (OUT / "meta.json").write_text(json.dumps(meta, indent=2))

    # Independent checks first (no LLM)
    print("Running independent calc checks...", flush=True)
    ind_merged = independent_checks(MERGED_USAGE)
    (OUT / "independent_checks_merged.json").write_text(json.dumps(ind_merged, indent=2, default=str))
    ind_shipped = independent_checks(SHIPPED_USAGE)
    (OUT / "independent_checks_shipped.json").write_text(json.dumps(ind_shipped, indent=2, default=str))

    reqs = make_requests()
    # subset filter via argv
    only = set(sys.argv[1:]) if len(sys.argv) > 1 else None
    if only:
        reqs = [r for r in reqs if r["id"] in only or r["id"].rstrip("b") in only]

    all_results = []
    # Primary: merged usage, both models
    for model in MODELS:
        os.environ["BOOTSTRAP_OLLAMA_MODEL"] = model
        for req in reqs:
            try:
                all_results.append(run_one(req, model=model, usage_dir=MERGED_USAGE, repeat=0))
            except Exception as e:
                print(f"FATAL {req['id']} {model}: {e}", flush=True)
                traceback.print_exc()
                all_results.append({"id": req["id"], "model": model, "fatal": str(e)})

    # Secondary pass: usage-dependent against shipped
    for model in MODELS:
        os.environ["BOOTSTRAP_OLLAMA_MODEL"] = model
        for req in reqs:
            if not req.get("usage_secondary"):
                continue
            try:
                all_results.append(run_one(req, model=model, usage_dir=SHIPPED_USAGE, repeat=0))
            except Exception as e:
                print(f"FATAL secondary {req['id']} {model}: {e}", flush=True)

    # Non-determinism subset re-run (merged only)
    subset = {"S1", "S2", "S3", "C1", "D1"}
    for model in MODELS:
        os.environ["BOOTSTRAP_OLLAMA_MODEL"] = model
        for req in reqs:
            if req["id"] not in subset:
                continue
            try:
                all_results.append(run_one(req, model=model, usage_dir=MERGED_USAGE, repeat=1))
            except Exception as e:
                print(f"FATAL rerun {req['id']} {model}: {e}", flush=True)

    (OUT / "all_results_index.json").write_text(
        json.dumps(
            [
                {
                    "id": r.get("id"),
                    "model": r.get("model"),
                    "usage": (r.get("usage") or {}).get("usage_dir"),
                    "outcome": (r.get("outcome") or {}).get("outcome"),
                    "repeat": r.get("repeat"),
                    "n_turns": r.get("n_turns"),
                    "fatal": r.get("fatal"),
                }
                for r in all_results
            ],
            indent=2,
        )
    )
    print("ALL DONE", len(all_results), flush=True)


if __name__ == "__main__":
    main()
