"""Process-metric scorer (FU27 / scorer_spec_draft_2026-11-02).

Deterministic: (transcript.json, run_record.json, expected-tools CSV) →
per-turn rows + per-rung summary. No model, no network. Does not import the
class scorer, claim scorers, or any oracle.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

HERE = Path(__file__).resolve().parent
DEFAULT_CSV = HERE / "expected_tools_fu16" / "expected_tools_rev3_2026-11-02.csv"


def resolve_expected_tools_csv(run_record: Mapping[str, Any] | None = None) -> Path:
    """Pick rev3 (committed) or rev5 (fu74) from the run record's key_set."""
    from scripts.eval.part_g_arm.state.revised_keys import expected_tools_csv

    ks = "committed"
    if isinstance(run_record, Mapping):
        ks = str(run_record.get("key_set") or (run_record.get("pin_hashes") or {}).get("key_set") or "committed")
    return expected_tools_csv(ks)

WRITE_TOOLS = frozenset(
    {
        "set_slot",
        "lock_slot",
        "edit_slot_field",
        "lock_fields",
        "unlock_fields",
        "unlock_slot",
        "select_option",
        "commit_slot",
        "confirm_build",
        "reject_pending",
        "reject_option",
        "reject_all",
        "add_constraint",
        "restore_constraint",
        "set_constraint_active",
        "change_archetype",
        "reset_team",
    }
)
REJECT_TOOLS = frozenset({"reject_pending", "reject_option", "reject_all"})
CONSTRAINT_WRITE_TOOLS = frozenset(
    {"add_constraint", "restore_constraint", "set_constraint_active"}
)
LOOKUP_READ_TOOLS = frozenset(
    {
        "get_typing",
        "get_abilities",
        "check_species_ability",
        "check_species_legal",
        "check_item_legal",
        "get_move_static",
        "check_learnset",
        "find_species",
        "get_usage_items",
        "get_usage_teammates",
        "get_usage_spreads",
        "get_usage_stats",
        "get_common_speeds",
        "get_meta_threats",
        "calc_damage",
        "get_speed",
        "solve_spread",
        "describe",
        "no_lookup_needed",
        "show_candidates",
        "read_team",
        "read_pending",
        "read_constraints",
        "read_archetype",
        "read_rejected",
        "check_hypothetical",
    }
)
LEGALITY_TOOLS = frozenset(
    {
        "check_species_legal",
        "check_item_legal",
        "check_species_ability",
        "check_learnset",
    }
)
CLASSES_FORBID_WRITE = frozenset(
    {"LOOKUP", "READ_STATE", "HYPOTHETICAL", "ASK", "READ_ONLY_REFUSE"}
)
CLASSES_ALLOW_WRITE = frozenset({"WRITE", "PENDING_ANSWER"})

# Rung 1–2: these satisfy a set_slot step when set_slot is absent.
SET_SLOT_EQUIV = frozenset({"lock_slot", "edit_slot_field"})


@dataclass
class CallScore:
    name: str
    args: dict[str, Any]
    result_status: str
    default_mark: str  # ok | redundant | extra | misused
    audit_mark: str = ""
    guard_blocked: bool = False
    ambiguous: str = ""


@dataclass
class TurnScore:
    row_id: str
    turn: int  # CSV / live index
    rung: int
    effective_class: str
    requirement_default: str  # met | missed | not_scorable | no_run_record
    missing_steps: str
    path_used: str  # expected | alternative | both | "" | none
    order_ok: bool
    structural: bool  # missed because a required tool is absent at this rung
    order_write_before_lookup: bool  # write preceded a required lookup that was called later
    n_calls: int
    n_redundant: int
    n_extra: int
    n_misused: int
    n_refused: int
    n_guard_blocked: int
    ambiguous: str
    calls: list[CallScore] = field(default_factory=list)
    requirement_mark: str = ""
    transcript_turn_index: int | None = None  # 1-based in transcript row, if any


def _canon_args(args: Any) -> str:
    if not isinstance(args, dict):
        args = {}
    return json.dumps(args, sort_keys=True, default=str)


def _split_steps(cell: str | None) -> list[list[str]]:
    """'a;b|c;d' → [['a'], ['b','c'], ['d']]. Empty → []."""
    out: list[list[str]] = []
    for step in (cell or "").split(";"):
        step = step.strip()
        if not step:
            continue
        alts = [a.strip() for a in step.split("|") if a.strip()]
        if alts:
            out.append(alts)
    return out


def _split_optional(cell: str | None) -> set[str]:
    names: set[str] = set()
    for step in _split_steps(cell):
        names.update(step)
    # optional cell may also be comma/space separated historically
    raw = (cell or "").strip()
    if raw and ";" not in raw and "|" not in raw:
        for part in re.split(r"[\s,]+", raw):
            if part:
                names.add(part)
    return names


def effective_class(row: Mapping[str, str]) -> str:
    o = (row.get("guard_class_override") or "").strip()
    return o or (row.get("proposed_guard_class") or "").strip()


def rung_from_flags(flags: Mapping[str, bool]) -> int:
    """Ladder: 1 flags-off … 6 judge. Cumulative."""
    if flags.get("judge"):
        return 6
    if flags.get("guard"):
        return 5
    if flags.get("draft"):
        return 4
    if flags.get("wrapper"):
        return 3
    if flags.get("tool_fields"):
        return 2
    return 1


def flags_from_run_record(rec: Mapping[str, Any]) -> dict[str, bool]:
    nested = rec.get("run_flags")
    if isinstance(nested, dict) and any(
        k in nested
        for k in (
            "tool_fields",
            "wrapper",
            "draft",
            "guard",
            "judge",
            "sticky_locks",
            "unlock_keeps_values",
            "tool_fixes_v2",
            "ix_tools_v1",
            "prompt_cut",
            "parser_v2",
            "parser_pending_options",
        )
    ):
        return {
            "tool_fields": bool(nested.get("tool_fields")),
            "wrapper": bool(nested.get("wrapper")),
            "draft": bool(nested.get("draft")),
            "guard": bool(nested.get("guard")),
            "judge": bool(nested.get("judge")),
            "sticky_locks": bool(nested.get("sticky_locks")),
            "unlock_keeps_values": bool(nested.get("unlock_keeps_values")),
            "tool_fixes_v2": bool(nested.get("tool_fixes_v2")),
            "ix_tools_v1": bool(nested.get("ix_tools_v1")),
            "prompt_cut": bool(nested.get("prompt_cut")),
            "parser_v2": bool(nested.get("parser_v2")),
            "parser_pending_options": bool(nested.get("parser_pending_options")),
        }
    # Legacy run 1: PRE-RS-ARM schema, no ladder flags.
    return {
        "tool_fields": False,
        "wrapper": False,
        "draft": False,
        "guard": False,
        "judge": False,
        "sticky_locks": False,
        "unlock_keeps_values": False,
        "tool_fixes_v2": False,
        "ix_tools_v1": False,
        "prompt_cut": False,
        "parser_v2": False,
        "parser_pending_options": False,
    }


def available_tools(rec: Mapping[str, Any], flags: Mapping[str, bool]) -> frozenset[str]:
    """Tools the run actually bound."""
    tool_set = rec.get("tool_set")
    if isinstance(tool_set, list) and tool_set:
        return frozenset(str(x) for x in tool_set)
    # Prefer reconstructing via combined_specs (same as the runner). Soft-fail if
    # the heavy tools module cannot import (offline smoke without full deps).
    try:
        from scripts.eval.part_g_arm.state.tools import combined_specs

        specs = combined_specs(
            tool_fields=bool(flags.get("tool_fields")),
            wrapper=bool(flags.get("wrapper")),
            draft=bool(flags.get("draft")),
        )
        return frozenset(s["function"]["name"] for s in specs)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "run_record lacks tool_set and combined_specs could not be imported; "
            f"cannot determine available tools ({type(exc).__name__}: {exc})"
        ) from exc


def _equiv_names(name: str, *, rung: int, available: frozenset[str]) -> frozenset[str]:
    """Names that satisfy a step requiring ``name`` at this rung."""
    if name == "set_slot" and "set_slot" not in available and rung <= 2:
        return SET_SLOT_EQUIV & available if (SET_SLOT_EQUIV & available) else SET_SLOT_EQUIV
    return frozenset({name})


def _step_satisfiers(
    step_alts: Sequence[str], *, rung: int, available: frozenset[str]
) -> frozenset[str]:
    out: set[str] = set()
    for alt in step_alts:
        out |= _equiv_names(alt, rung=rung, available=available)
    return frozenset(out)


def _call_matches_step(
    call_name: str, step_alts: Sequence[str], *, rung: int, available: frozenset[str]
) -> bool:
    return call_name in _step_satisfiers(step_alts, rung=rung, available=available)


def _path_steps_present(
    steps: Sequence[Sequence[str]], *, available: frozenset[str], rung: int
) -> tuple[bool, list[str]]:
    """Return (all_present_in_schema, missing_step_labels). Schema absence ≠ call miss."""
    missing: list[str] = []
    for step in steps:
        satisfiers = _step_satisfiers(step, rung=rung, available=available)
        if not (satisfiers & available) and not any(a in available for a in step):
            # Equiv may name tools not in available; still "present" if equiv applies
            if not (satisfiers & available):
                # If the named tool and all equivs are absent → cannot satisfy at rung
                if not satisfiers.intersection(available) and not any(
                    n in available for n in step
                ):
                    # Check raw names and equiv against available
                    ok = False
                    for alt in step:
                        if alt in available:
                            ok = True
                            break
                        if alt == "set_slot" and rung <= 2 and (SET_SLOT_EQUIV & available):
                            ok = True
                            break
                    if not ok:
                        missing.append("|".join(step))
    return (not missing, missing)


def _path_satisfied(
    steps: Sequence[Sequence[str]],
    calls: Sequence[Mapping[str, Any]],
    *,
    rung: int,
    available: frozenset[str],
) -> tuple[bool, list[str]]:
    """Every step has a matching call (by name/equiv). Returns (ok, missing_steps)."""
    names = [c.get("name") or "" for c in calls]
    missing: list[str] = []
    for step in steps:
        # Tool must be available (or equiv) at rung to be satisfiable.
        sat = _step_satisfiers(step, rung=rung, available=available)
        if not any(
            (alt in available)
            or (alt == "set_slot" and rung <= 2 and bool(SET_SLOT_EQUIV & available))
            for alt in step
        ):
            missing.append("|".join(step))
            continue
        if not any(_call_matches_step(n, step, rung=rung, available=available) for n in names):
            missing.append("|".join(step))
    return (not missing, missing)


def _first_write_index(calls: Sequence[Mapping[str, Any]]) -> int | None:
    for i, c in enumerate(calls):
        if (c.get("name") or "") in WRITE_TOOLS:
            return i
    return None


def _order_prewrite_lookup_hits(
    expected_steps: Sequence[Sequence[str]],
    calls: Sequence[Mapping[str, Any]],
    *,
    rung: int,
    available: frozenset[str],
) -> tuple[bool, bool]:
    """Return (order_ok, write_before_called_lookup).

    A required step never called is a miss, not an order failure — only lookups/reads
    that were actually called are checked against the first write call.
    """
    write_step_i = None
    for i, step in enumerate(expected_steps):
        if any(a in WRITE_TOOLS or a == "set_slot" for a in step):
            write_step_i = i
            break
    if write_step_i is None:
        return True, False
    first_write = _first_write_index(calls)
    if first_write is None:
        return True, False
    call_names = [(c.get("name") or "") for c in calls]
    order_ok = True
    write_before = False
    for step in expected_steps[:write_step_i]:
        if any(a in WRITE_TOOLS or a == "set_slot" for a in step):
            continue
        hit = None
        for j, n in enumerate(call_names):
            if _call_matches_step(n, step, rung=rung, available=available):
                hit = j
                break
        if hit is None:
            continue  # never called → missing_steps, not order
        if hit >= first_write:
            order_ok = False
            write_before = True
    return order_ok, write_before


def _user_named_tokens(user_text: str) -> set[str]:
    return {t for t in re.findall(r"[A-Za-z][A-Za-z0-9\-']*", user_text or "")}


def _species_from_result(result: Any) -> set[str]:
    out: set[str] = set()
    if not isinstance(result, Mapping):
        return out
    if isinstance(result.get("species"), str):
        out.add(result["species"])
    for s in result.get("species") or []:
        if isinstance(s, str):
            out.add(s)
    for opt in result.get("options") or []:
        if isinstance(opt, Mapping) and isinstance(opt.get("species"), str):
            out.add(opt["species"])
    return out


def _args_name_tokens(args: Mapping[str, Any]) -> set[str]:
    out: set[str] = set()
    for k in ("species", "item", "ability", "move"):
        v = args.get(k)
        if isinstance(v, str) and v.strip():
            out.add(v.strip())
    for v in args.get("types") or []:
        if isinstance(v, str):
            out.add(v)
    return out


def _is_protocol(
    name: str,
    args: Mapping[str, Any],
    *,
    calls: Sequence[Mapping[str, Any]],
    index: int,
    user_text: str,
) -> tuple[bool, str]:
    """Return (is_protocol, ambiguous_reason)."""
    names_before = [c.get("name") or "" for c in calls[:index]]
    names_after = [c.get("name") or "" for c in calls[index + 1 :]]
    has_write_after = any(n in WRITE_TOOLS for n in names_after)
    has_write_before = any(n in WRITE_TOOLS for n in names_before)
    first_write = _first_write_index(calls)

    if name == "read_team":
        if first_write is not None and index < first_write:
            return True, ""
        return False, ""

    if name == "read_pending":
        if any(n in ({"select_option"} | REJECT_TOOLS) for n in names_after):
            return True, ""
        return False, ""

    if name == "read_constraints":
        if first_write is not None and index < first_write:
            return True, ""
        if has_write_before and any(n in CONSTRAINT_WRITE_TOOLS for n in names_before):
            return True, ""
        return False, ""

    if name in LEGALITY_TOOLS:
        # Redundant if checking a species produced by find_species / show_candidates earlier.
        produced: set[str] = set()
        for c in calls[:index]:
            n = c.get("name") or ""
            if n in ("find_species", "show_candidates"):
                produced |= _species_from_result(c.get("result"))
        arg_toks = _args_name_tokens(args if isinstance(args, dict) else {})
        if arg_toks & produced:
            return False, ""  # not protocol → falls through to redundant/extra logic
        user_toks = _user_named_tokens(user_text)
        # About to be written: species/item in a later write's args this turn.
        write_toks: set[str] = set()
        for c in calls[index + 1 :]:
            if (c.get("name") or "") in WRITE_TOOLS:
                write_toks |= _args_name_tokens(c.get("args") or {})
        if arg_toks & user_toks or arg_toks & write_toks:
            return True, ""
        if not arg_toks:
            return False, f"legality {name} with no species/item/move arg"
        return False, ""

    return False, ""


def _result_status(call: Mapping[str, Any]) -> str:
    """Local copy of tools.tool_call_result_status — avoid importing tools.py (heavy)."""
    if call.get("result_status"):
        return str(call["result_status"])
    result = call.get("result") or {}
    if not isinstance(result, Mapping):
        result = {}
    name = call.get("name") or ""
    if name == "set_slot":
        if result.get("ok") is False or result.get("slot_commit_error"):
            return "refused"
        if result.get("ok") is True:
            return "ok"
        return "unknown"
    if result.get("slot_commit_error"):
        return "refused"
    if result.get("guard_blocked"):
        return "refused"
    if result.get("error_kind") or result.get("status") == "error":
        return "error"
    status = result.get("status")
    if isinstance(status, str) and status:
        return status
    if result.get("ok") is True:
        return "ok"
    if result.get("ok") is False:
        return "refused"
    return "ok" if result else "empty"


def _is_refused(status: str, call: Mapping[str, Any]) -> bool:
    if status in ("refused", "error"):
        return True
    result = call.get("result") or {}
    if isinstance(result, Mapping) and result.get("guard_blocked"):
        return True
    return False


def _has_replace_true(call: Mapping[str, Any]) -> bool:
    args = call.get("args") or {}
    if not isinstance(args, dict):
        return False
    if bool(args.get("replace")):
        return True
    slots = args.get("slots")
    if isinstance(slots, list):
        return any(isinstance(s, dict) and bool(s.get("replace")) for s in slots)
    return False


def score_turn_calls(
    *,
    row_id: str,
    turn: int,
    rung: int,
    effective_cls: str,
    csv_row: Mapping[str, str],
    calls: Sequence[Mapping[str, Any]],
    user_text: str,
    available: frozenset[str],
) -> TurnScore:
    expected = _split_steps(csv_row.get("expected_tools_ordered"))
    alternative = _split_steps(csv_row.get("alternative_path"))
    optional = _split_optional(csv_row.get("optional_tools"))
    new_tool = (csv_row.get("new_tool_needed") or "").strip()

    # Schema-level path availability
    exp_schema_ok, exp_schema_miss = _path_steps_present(
        expected, available=available, rung=rung
    )
    alt_schema_ok, alt_schema_miss = _path_steps_present(
        alternative, available=available, rung=rung
    )

    ambiguous_bits: list[str] = []
    structural = False
    order = True
    write_before_lookup = False

    # not_scorable: ONLY new_tool_needed with no listed expected/alternative path.
    if new_tool and not expected and not alternative:
        req = "not_scorable"
        path_used = ""
        missing = new_tool
        exp_ok = alt_ok = False
        exp_miss = alt_miss = [new_tool]
    else:
        exp_ok, exp_miss = (
            _path_satisfied(expected, calls, rung=rung, available=available)
            if expected
            else (False, [])
        )
        alt_ok, alt_miss = (
            _path_satisfied(alternative, calls, rung=rung, available=available)
            if alternative
            else (False, [])
        )
        # Vacuous empty expected with no alternative and no new_tool → met
        if not expected and not alternative and not new_tool:
            exp_ok = True
            exp_miss = []
        if not expected and alternative:
            exp_ok = False
        if expected and not alternative:
            alt_ok = False

        if exp_ok and alt_ok:
            req, path_used, missing = "met", "both", ""
        elif exp_ok:
            req, path_used, missing = "met", "expected", ""
        elif alt_ok:
            req, path_used, missing = "met", "alternative", ""
        else:
            req = "missed"
            path_used = "none"
            missing = ";".join(exp_miss or alt_miss)
            # Structural: no schema-available path at this rung (tools absent).
            # Behavioral: at least one path could have been satisfied with available tools.
            any_schema = (bool(expected) and exp_schema_ok) or (
                bool(alternative) and alt_schema_ok
            )
            structural = not any_schema and bool(expected or alternative)

        order, write_before_lookup = _order_prewrite_lookup_hits(
            expected, calls, rung=rung, available=available
        )

    # Build allowed set for call classification
    allowed_names: set[str] = set(optional)
    for step in list(expected) + list(alternative):
        allowed_names |= _step_satisfiers(step, rung=rung, available=available)

    call_scores: list[CallScore] = []
    seen_keys: set[tuple[str, str]] = set()

    n_red = n_extra = n_mis = n_ref = n_gb = 0

    for i, call in enumerate(calls):
        name = str(call.get("name") or "")
        args = call.get("args") if isinstance(call.get("args"), dict) else {}
        status = _result_status(call)
        result = call.get("result") if isinstance(call.get("result"), Mapping) else {}
        guard_blocked = bool(result.get("guard_blocked"))
        refused = _is_refused(status, call)
        if guard_blocked:
            n_gb += 1
        if refused:
            n_ref += 1

        key = (name, _canon_args(args))
        mark = "ok"
        amb = ""

        # Misused: write when class forbids; replace=true when class is not PENDING_ANSWER
        is_write = name in WRITE_TOOLS
        if is_write and effective_cls in CLASSES_FORBID_WRITE:
            mark = "misused"
            n_mis += 1
        elif _has_replace_true(call) and effective_cls != "PENDING_ANSWER":
            mark = "misused"
            n_mis += 1
        elif refused and is_write and effective_cls in CLASSES_FORBID_WRITE:
            mark = "misused"
            n_mis += 1

        if mark != "misused":
            proto, proto_amb = _is_protocol(
                name, args, calls=calls, index=i, user_text=user_text
            )
            if proto_amb:
                ambiguous_bits.append(proto_amb)
                amb = proto_amb
            # Redundant only: identical (name, args) repeat, or legality on
            # find_species/show_candidates species this turn. No other "already held".
            if name in LEGALITY_TOOLS:
                produced: set[str] = set()
                for c in calls[:i]:
                    if (c.get("name") or "") in ("find_species", "show_candidates"):
                        produced |= _species_from_result(c.get("result"))
                if _args_name_tokens(args) & produced:
                    mark = "redundant"
                    n_red += 1
                elif proto:
                    mark = "ok"
                elif name in allowed_names:
                    mark = "redundant" if key in seen_keys else "ok"
                    if mark == "redundant":
                        n_red += 1
                else:
                    mark = "extra"
                    n_extra += 1
            elif proto:
                mark = "ok"
            elif name in allowed_names:
                if key in seen_keys:
                    mark = "redundant"
                    n_red += 1
                else:
                    mark = "ok"
            else:
                mark = "extra"
                n_extra += 1

        if mark == "ok" and key in seen_keys:
            mark = "redundant"
            n_red += 1

        seen_keys.add(key)

        call_scores.append(
            CallScore(
                name=name,
                args=dict(args),
                result_status=status,
                default_mark=mark,
                guard_blocked=guard_blocked,
                ambiguous=amb,
            )
        )

    return TurnScore(
        row_id=row_id,
        turn=turn,
        rung=rung,
        effective_class=effective_cls,
        requirement_default=req,
        missing_steps=missing,
        path_used=path_used,
        order_ok=order,
        structural=structural,
        order_write_before_lookup=write_before_lookup,
        n_calls=len(calls),
        n_redundant=n_red,
        n_extra=n_extra,
        n_misused=n_mis,
        n_refused=n_ref,
        n_guard_blocked=n_gb,
        ambiguous="; ".join(ambiguous_bits),
        calls=call_scores,
    )


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def map_transcript_turns_to_csv(
    row_id: str,
    n_live: int,
    csv_turns: Sequence[int],
) -> list[tuple[int, int]]:
    """Return list of (transcript_turn_1based, csv_turn).

    When the transcript played fewer turns than the CSV (seeded prefix), map to
    the last n_live CSV turns (FU26/FU27: HC2/HD1/MT3).
    """
    if n_live <= 0:
        return []
    ordered = sorted(csv_turns)
    if n_live == len(ordered):
        return list(zip(range(1, n_live + 1), ordered, strict=True))
    if n_live < len(ordered):
        tail = ordered[-n_live:]
        return list(zip(range(1, n_live + 1), tail, strict=True))
    # More live than CSV — ambiguous; pair prefix and flag later
    return [(i + 1, ordered[i] if i < len(ordered) else ordered[-1]) for i in range(n_live)]


def score_run(
    *,
    transcript: Sequence[Mapping[str, Any]],
    run_record: Mapping[str, Any],
    csv_rows: Sequence[Mapping[str, str]],
) -> tuple[list[TurnScore], dict[str, Any], list[str]]:
    flags = flags_from_run_record(run_record)
    rung = rung_from_flags(flags)
    available = available_tools(run_record, flags)

    by_key: dict[tuple[str, int], dict[str, str]] = {}
    turns_by_row: dict[str, list[int]] = defaultdict(list)
    for r in csv_rows:
        rid = r["row_id"]
        turn = int(r["turn"])
        by_key[(rid, turn)] = dict(r)
        turns_by_row[rid].append(turn)

    transcript_by_id = {str(e.get("id")): e for e in transcript}
    scores: list[TurnScore] = []
    no_record: list[str] = []
    path_absent: list[str] = []

    # Path-absent inventory (all CSV rows × this rung's available tools)
    for r in csv_rows:
        rid, turn = r["row_id"], int(r["turn"])
        exp = _split_steps(r.get("expected_tools_ordered"))
        alt = _split_steps(r.get("alternative_path"))
        new_tool = (r.get("new_tool_needed") or "").strip()
        exp_ok, exp_miss = _path_steps_present(exp, available=available, rung=rung)
        alt_ok, alt_miss = _path_steps_present(alt, available=available, rung=rung)
        if new_tool and not exp and not alt:
            path_absent.append(f"{rid} t{turn}: new_tool_needed={new_tool} (no path)")
        elif exp or alt:
            if not ((exp and exp_ok) or (alt and alt_ok) or (not exp and not alt)):
                if not exp_ok and not alt_ok:
                    path_absent.append(
                        f"{rid} t{turn}: unavailable steps expected={exp_miss} alt={alt_miss}"
                    )

    scored_keys: set[tuple[str, int]] = set()
    for rid, entry in transcript_by_id.items():
        live_turns = list(entry.get("turns") or [])
        csv_turn_list = turns_by_row.get(rid, [])
        if not live_turns:
            if csv_turn_list:
                for t in csv_turn_list:
                    no_record.append(f"{rid} t{t}")
                    scores.append(
                        TurnScore(
                            row_id=rid,
                            turn=t,
                            rung=rung,
                            effective_class=effective_class(by_key[(rid, t)]),
                            requirement_default="no_run_record",
                            missing_steps="",
                            path_used="",
                            order_ok=True,
                            structural=False,
                            order_write_before_lookup=False,
                            n_calls=0,
                            n_redundant=0,
                            n_extra=0,
                            n_misused=0,
                            n_refused=0,
                            n_guard_blocked=0,
                            ambiguous="",
                        )
                    )
                    scored_keys.add((rid, t))
            continue

        mapping = map_transcript_turns_to_csv(rid, len(live_turns), csv_turn_list or list(range(1, len(live_turns) + 1)))
        if len(live_turns) > len(csv_turn_list) and csv_turn_list:
            # Should not happen for run 1; record ambiguous
            pass
        for live_i, csv_turn in mapping:
            crow = by_key.get((rid, csv_turn))
            if crow is None:
                continue
            turn_rec = live_turns[live_i - 1]
            calls = list(turn_rec.get("tool_calls") or [])
            user_text = turn_rec.get("user") or crow.get("user_turn_text") or ""
            ts = score_turn_calls(
                row_id=rid,
                turn=csv_turn,
                rung=rung,
                effective_cls=effective_class(crow),
                csv_row=crow,
                calls=calls,
                user_text=user_text,
                available=available,
            )
            ts.transcript_turn_index = live_i
            scores.append(ts)
            scored_keys.add((rid, csv_turn))

    # CSV turns never seen in transcript (seeded-only / not played)
    for rid, turns in turns_by_row.items():
        for t in turns:
            if (rid, t) in scored_keys:
                continue
            # Seeded prefix not in transcript → no_run_record for that live index
            no_record.append(f"{rid} t{t}")
            scores.append(
                TurnScore(
                    row_id=rid,
                    turn=t,
                    rung=rung,
                    effective_class=effective_class(by_key[(rid, t)]),
                    requirement_default="no_run_record",
                    missing_steps="",
                    path_used="",
                    order_ok=True,
                    structural=False,
                    order_write_before_lookup=False,
                    n_calls=0,
                    n_redundant=0,
                    n_extra=0,
                    n_misused=0,
                    n_refused=0,
                    n_guard_blocked=0,
                    ambiguous="",
                )
            )

    scores.sort(key=lambda s: (s.row_id, s.turn))
    summary = summarize_rung(scores, rung=rung, no_record=no_record, csv_rows=csv_rows)
    return scores, summary, path_absent


def csv_rows_never_scorable(csv_rows: Sequence[Mapping[str, str]]) -> list[str]:
    """Rows whose only path is new_tool_needed with no expected/alternative listed."""
    out: list[str] = []
    for r in csv_rows:
        new_tool = (r.get("new_tool_needed") or "").strip()
        exp = _split_steps(r.get("expected_tools_ordered"))
        alt = _split_steps(r.get("alternative_path"))
        if new_tool and not exp and not alt:
            out.append(f"{r['row_id']} t{r['turn']}: new_tool_needed={new_tool}")
    return out


def summarize_rung(
    scores: Sequence[TurnScore],
    *,
    rung: int,
    no_record: Sequence[str],
    csv_rows: Sequence[Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    played = [s for s in scores if s.requirement_default != "no_run_record"]
    met = [s for s in played if s.requirement_default == "met"]
    missed = [s for s in played if s.requirement_default == "missed"]
    missed_structural = [s for s in missed if s.structural]
    missed_behavioral = [s for s in missed if not s.structural]
    not_scorable = [s for s in played if s.requirement_default == "not_scorable"]
    order_false = [s for s in played if not s.order_ok]
    write_before = [s for s in played if s.order_write_before_lookup]
    never = csv_rows_never_scorable(csv_rows or [])
    return {
        "rung": rung,
        "turns_scored": len(played),
        "requirement_met": len(met),
        "requirement_missed": len(missed),
        "requirement_missed_structural": len(missed_structural),
        "requirement_missed_behavioral": len(missed_behavioral),
        "requirement_not_scorable": len(not_scorable),
        "met_list": [f"{s.row_id} t{s.turn}" for s in met],
        "missed_list": [f"{s.row_id} t{s.turn}" for s in missed],
        "missed_structural_list": [f"{s.row_id} t{s.turn}" for s in missed_structural],
        "missed_behavioral_list": [f"{s.row_id} t{s.turn}" for s in missed_behavioral],
        "not_scorable_list": [f"{s.row_id} t{s.turn}" for s in not_scorable],
        "csv_never_scorable_rows": never,
        "csv_never_scorable_count": len(never),
        "no_run_record_list": list(no_record),
        "order_ok_false": len(order_false),
        "order_ok_false_list": [f"{s.row_id} t{s.turn}" for s in order_false],
        "order_write_before_lookup": len(write_before),
        "order_write_before_lookup_list": [
            f"{s.row_id} t{s.turn}" for s in write_before
        ],
        "n_redundant": sum(s.n_redundant for s in played),
        "n_extra": sum(s.n_extra for s in played),
        "n_misused": sum(s.n_misused for s in played),
        "n_refused": sum(s.n_refused for s in played),
        "n_guard_blocked": sum(s.n_guard_blocked for s in played),
        "n_calls": sum(s.n_calls for s in played),
        # Hand-override tallies filled by apply_marks_pass when marks present
        "after_hand_overrides": None,
    }


def turn_score_to_row(s: TurnScore) -> dict[str, Any]:
    return {
        "row_id": s.row_id,
        "turn": s.turn,
        "rung": s.rung,
        "effective_class": s.effective_class,
        "requirement_default": s.requirement_default,
        "missing_steps": s.missing_steps,
        "path_used": s.path_used,
        "order_ok": str(s.order_ok).lower(),
        "structural": str(s.structural).lower(),
        "order_write_before_lookup": str(s.order_write_before_lookup).lower(),
        "n_calls": s.n_calls,
        "n_redundant": s.n_redundant,
        "n_extra": s.n_extra,
        "n_misused": s.n_misused,
        "n_refused": s.n_refused,
        "n_guard_blocked": s.n_guard_blocked,
        "ambiguous": s.ambiguous,
        "calls_json": json.dumps(
            [
                {
                    "name": c.name,
                    "args": c.args,
                    "result_status": c.result_status,
                    "default_mark": c.default_mark,
                    "audit_mark": c.audit_mark,
                    "guard_blocked": c.guard_blocked,
                }
                for c in s.calls
            ],
            sort_keys=True,
        ),
        "requirement_mark": s.requirement_mark,
        "transcript_turn_index": s.transcript_turn_index
        if s.transcript_turn_index is not None
        else "",
    }


TURN_CSV_FIELDS = [
    "row_id",
    "turn",
    "rung",
    "effective_class",
    "requirement_default",
    "missing_steps",
    "path_used",
    "order_ok",
    "structural",
    "order_write_before_lookup",
    "n_calls",
    "n_redundant",
    "n_extra",
    "n_misused",
    "n_refused",
    "n_guard_blocked",
    "ambiguous",
    "calls_json",
    "requirement_mark",
    "transcript_turn_index",
]


def call_mark_counts_by_tool(
    scores: Sequence[TurnScore],
) -> dict[str, dict[str, int]]:
    """Per default_mark → tool name → count (extra / misused / redundant)."""
    out: dict[str, Counter[str]] = {
        "extra": Counter(),
        "misused": Counter(),
        "redundant": Counter(),
    }
    for s in scores:
        if s.requirement_default == "no_run_record":
            continue
        for c in s.calls:
            if c.default_mark in out:
                out[c.default_mark][c.name] += 1
    return {k: dict(v) for k, v in out.items()}


def ambiguous_case_count(scores: Sequence[TurnScore]) -> tuple[int, list[str]]:
    """Turns with a non-empty ambiguous field; list 'row tN: reason'."""
    rows: list[str] = []
    for s in scores:
        if s.requirement_default == "no_run_record":
            continue
        if s.ambiguous.strip():
            rows.append(f"{s.row_id} t{s.turn}: {s.ambiguous}")
    return len(rows), rows


def write_turn_csv(path: Path, scores: Sequence[TurnScore]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=TURN_CSV_FIELDS)
        w.writeheader()
        for s in scores:
            w.writerow(turn_score_to_row(s))


def apply_marks_pass(turn_csv: Path) -> dict[str, Any]:
    """Second pass: read marked CSV; defaults never edited in place. Return override tallies."""
    rows = list(csv.DictReader(turn_csv.open(newline="", encoding="utf-8")))
    req_default = Counter(r["requirement_default"] for r in rows if r["requirement_default"] != "no_run_record")
    req_mark = Counter(
        (r["requirement_mark"] or r["requirement_default"])
        for r in rows
        if r["requirement_default"] != "no_run_record"
    )
    marks_default = Counter()
    marks_audit = Counter()
    for r in rows:
        if r["requirement_default"] == "no_run_record":
            continue
        for c in json.loads(r["calls_json"] or "[]"):
            marks_default[c.get("default_mark") or ""] += 1
            marks_audit[c.get("audit_mark") or c.get("default_mark") or ""] += 1
    return {
        "requirement_default_counts": dict(req_default),
        "requirement_mark_counts": dict(req_mark),
        "call_default_mark_counts": dict(marks_default),
        "call_audit_mark_counts": dict(marks_audit),
    }


def format_turn_detail(s: TurnScore) -> str:
    lines = [
        f"{s.row_id} t{s.turn} rung={s.rung} class={s.effective_class} "
        f"req={s.requirement_default} path={s.path_used} order_ok={s.order_ok} "
        f"structural={s.structural} write_before_lookup={s.order_write_before_lookup} "
        f"missing={s.missing_steps!r}",
        f"  calls={s.n_calls} red={s.n_redundant} extra={s.n_extra} "
        f"misused={s.n_misused} refused={s.n_refused} guard_blocked={s.n_guard_blocked}",
    ]
    if s.ambiguous:
        lines.append(f"  ambiguous={s.ambiguous}")
    for c in s.calls:
        lines.append(
            f"  - {c.name} {json.dumps(c.args, sort_keys=True)} "
            f"status={c.result_status} mark={c.default_mark}"
            + (" GUARD_BLOCKED" if c.guard_blocked else "")
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("run_dir", type=Path, help="directory with transcript.json + run_record.json")
    p.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV,
        help="frozen expected-tools CSV",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="write process_turns.csv + process_summary.json (default: run_dir)",
    )
    p.add_argument(
        "--apply-marks",
        action="store_true",
        help="second pass: read requirement_mark/audit_mark from existing process_turns.csv",
    )
    p.add_argument(
        "--spot-check",
        action="store_true",
        help="print 12-turn spot-check details",
    )
    args = p.parse_args(argv)
    run_dir: Path = args.run_dir
    out_dir: Path = args.out_dir or run_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    turns_path = out_dir / "process_turns.csv"
    summary_path = out_dir / "process_summary.json"

    if args.apply_marks:
        overrides = apply_marks_pass(turns_path)
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["after_hand_overrides"] = overrides
        summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(overrides, indent=2))
        return 0

    transcript = json.loads((run_dir / "transcript.json").read_text(encoding="utf-8"))
    run_record = json.loads((run_dir / "run_record.json").read_text(encoding="utf-8"))
    csv_path = args.csv
    if csv_path == DEFAULT_CSV:
        csv_path = resolve_expected_tools_csv(run_record)
    csv_rows = load_csv_rows(csv_path)
    scores, summary, path_absent = score_run(
        transcript=transcript, run_record=run_record, csv_rows=csv_rows
    )
    write_turn_csv(turns_path, scores)
    summary["path_absent_at_rung"] = path_absent
    by_tool = call_mark_counts_by_tool(scores)
    summary["by_tool"] = by_tool
    n_amb, amb_rows = ambiguous_case_count(scores)
    summary["ambiguous_case_count"] = n_amb
    summary["ambiguous_case_list"] = amb_rows
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in summary if not k.endswith("_list")}, indent=2))
    print("path_absent_count", len(path_absent))
    for line in path_absent:
        print("  path_absent:", line)
    print("ambiguous_case_count", n_amb)
    print("by_tool", json.dumps(by_tool, indent=2))

    if args.spot_check:
        by_key = {(s.row_id, s.turn): s for s in scores}
        # One per effective class among played turns + required spot rows
        wanted: list[tuple[str, int]] = []
        seen_cls: set[str] = set()
        for s in scores:
            if s.requirement_default == "no_run_record":
                continue
            if s.effective_class not in seen_cls:
                seen_cls.add(s.effective_class)
                wanted.append((s.row_id, s.turn))
        for pair in [("MT6", 2), ("MR4", 1), ("HD1", 2), ("MW3", 1)]:
            if pair not in wanted:
                wanted.append(pair)
        print("\n=== spot-check ===")
        for key in wanted:
            s = by_key.get(key)
            if s is None:
                print(f"{key[0]} t{key[1]}: MISSING")
                continue
            print(format_turn_detail(s))
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
