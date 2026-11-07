"""Table-driven allowed_tools for the arm guard rung (mapping 2026-10-31).

Inputs are parser sub-requests + live state — never the answer key.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

# Deterministic unlock-request signal (FU66). Not LLM-filled; not confirms_replacement.
_UNLOCK_TEXT = re.compile(
    r"\b(?:unlock(?:ing|ed|s)?|clear(?:ing)?\s+(?:the\s+)?(?:lock|slot)|"
    r"wipe\s+(?:the\s+)?slot)\b",
    re.I,
)
_UNLOCK_PENDING_ACTIONS = frozenset(
    {"unlock_fields", "unlock_slot", "unlock", "clear"}
)

# --- Bundles (names only; token counts come from live schemas elsewhere) ---

CORE: frozenset[str] = frozenset(
    {
        "get_typing",
        "get_abilities",
        "check_species_ability",
        "check_species_legal",
        "check_item_legal",
        "get_move_static",
        "check_learnset",
        "find_species",
    }
)
USAGE: frozenset[str] = frozenset(
    {
        "get_usage_items",
        "get_usage_teammates",
        "get_usage_spreads",
        "get_usage_stats",
        "get_common_speeds",
        "get_meta_threats",
    }
)
NUMBERS: frozenset[str] = frozenset({"calc_damage", "get_speed", "solve_spread"})
EXTRAS: frozenset[str] = frozenset({"describe", "no_lookup_needed"})
READ: frozenset[str] = frozenset(
    {
        "read_team",
        "read_pending",
        "read_constraints",
        "read_archetype",
        "read_rejected",
    }
)
HYPO: frozenset[str] = frozenset({"check_hypothetical"})
SHOW: frozenset[str] = frozenset({"show_candidates"})

LOOKUP_BASE: frozenset[str] = CORE | USAGE | NUMBERS | EXTRAS | READ

# Parsed WRITE action → tool name(s) bound for that sub-request.
WRITE_ACTION_TOOLS: dict[str, frozenset[str]] = {
    "set_slot": frozenset({"set_slot"}),
    "build": frozenset({"set_slot"}),
    "draft": frozenset({"set_slot"}),
    "fill": frozenset({"set_slot"}),
    "lock_fields": frozenset({"lock_fields"}),
    "lock": frozenset({"lock_fields"}),
    "confirm": frozenset({"lock_fields"}),
    "set_and_lock": frozenset({"set_slot", "lock_fields"}),
    "unlock_fields": frozenset({"unlock_fields"}),
    "unlock_slot": frozenset({"unlock_slot"}),
    "unlock": frozenset({"unlock_fields", "unlock_slot"}),
    "clear": frozenset({"unlock_slot"}),
    "select_option": frozenset({"select_option"}),
    "pick": frozenset({"select_option"}),
    "commit_slot": frozenset({"commit_slot", "confirm_build"}),
    "commit": frozenset({"commit_slot", "confirm_build"}),
    "confirm_build": frozenset({"commit_slot", "confirm_build"}),
    "reject_pending": frozenset({"reject_pending", "reject_option", "reject_all"}),
    "reject_option": frozenset({"reject_pending", "reject_option", "reject_all"}),
    "reject_all": frozenset({"reject_pending", "reject_option", "reject_all"}),
    "reject": frozenset({"reject_pending", "reject_option", "reject_all"}),
    # set_constraint_active may lack a live schema until FU21; allowed_tools filters
    # against known schemas when a registry is passed (see filter_to_live_schemas).
    "add_constraint": frozenset(
        {"add_constraint", "restore_constraint", "set_constraint_active"}
    ),
    "restore_constraint": frozenset(
        {"add_constraint", "restore_constraint", "set_constraint_active"}
    ),
    "constraint": frozenset(
        {"add_constraint", "restore_constraint", "set_constraint_active"}
    ),
    "change_archetype": frozenset({"change_archetype"}),
    "archetype": frozenset({"change_archetype"}),
    "reset_team": frozenset({"reset_team"}),
    "reset": frozenset({"reset_team"}),
}

GUARD_CLASSES: frozenset[str] = frozenset(
    {
        "LOOKUP",
        "WRITE",
        "ASK",
        "HYPOTHETICAL",
        "READ_STATE",
        "PENDING_ANSWER",
        "READ_ONLY_REFUSE",
    }
)

_ATTR_NAMES = (
    "role",
    "species",
    "ability",
    "item",
    "moveset",
    "spread",
    "nature",
)


def team_fingerprint(state: Mapping[str, Any]) -> str:
    """Stable fingerprint of team_draft values+locks for OL10a."""
    from scripts.eval.part_g_arm.state.tools import draft_signature

    return repr(draft_signature(dict(state)))


def pending_fingerprint_matches(state: Mapping[str, Any]) -> bool:
    """True when a pending screen exists and its stored team fingerprint matches."""
    pending = state.get("pending_presentation")
    if not isinstance(pending, dict):
        return False
    stored = pending.get("team_fingerprint")
    if stored is None:
        # Legacy pending without OL10a stamp: treat as stale for select_option bind.
        return False
    return stored == team_fingerprint(state)


def _slot_attrs(slot: Any) -> Iterable[Any]:
    for name in _ATTR_NAMES:
        yield getattr(slot, name)


def has_fully_locked_anchor(state: Mapping[str, Any]) -> bool:
    from recommender.state import all_locked

    draft = state.get("team_draft") or []
    return any(all_locked(slot) for slot in draft)


def first_blank_slot_index(state: Mapping[str, Any]) -> int | None:
    """First open blank slot (drafted attrs mean not blank)."""
    from recommender.state import all_locked

    draft = state.get("team_draft") or []
    for i, slot in enumerate(draft):
        if all_locked(slot):
            continue
        if any(
            getattr(a, "locked", False) or getattr(a, "value", None) is not None
            for a in _slot_attrs(slot)
        ):
            continue
        return i
    return None


def has_valued_attribute(state: Mapping[str, Any]) -> bool:
    draft = state.get("team_draft") or []
    for slot in draft:
        for a in _slot_attrs(slot):
            if getattr(a, "value", None) is not None:
                return True
    return False


def has_pending_screen(state: Mapping[str, Any]) -> bool:
    pending = state.get("pending_presentation")
    return isinstance(pending, dict) and bool(pending.get("kind"))


def _normalize_sub(sub: Mapping[str, Any]) -> dict[str, Any]:
    cls = str(sub.get("class") or "").strip().upper()
    if cls not in GUARD_CLASSES or sub.get("uncertain"):
        cls = "ASK"
    action = sub.get("action")
    action_s = str(action).strip().lower() if action else None
    return {
        "class": cls,
        "action": action_s,
        "numeric_or_explain": bool(sub.get("numeric_or_explain")),
        "confirms_replacement": bool(sub.get("confirms_replacement")),
    }


def _write_tools_for_action(action: str | None, state: Mapping[str, Any]) -> set[str]:
    if not action:
        return set()
    tools = set(WRITE_ACTION_TOOLS.get(action, set()))
    # State-aware narrowing (mapping §4).
    if "lock_fields" in tools and not has_valued_attribute(state):
        tools.discard("lock_fields")
    if "select_option" in tools:
        if not has_pending_screen(state) or not pending_fingerprint_matches(state):
            tools.discard("select_option")
    if tools & {"reject_pending", "reject_option", "reject_all"}:
        if not has_pending_screen(state):
            tools -= {"reject_pending", "reject_option", "reject_all"}
    return tools


def _bundle_for_class(
    cls: str,
    *,
    action: str | None,
    numeric_or_explain: bool,
    state: Mapping[str, Any],
) -> set[str]:
    # FU22 / mapping intent: ASK + READ_ONLY_REFUSE = READ + no_lookup_needed (408).
    # READ_STATE = READ only (284). no_lookup_needed also in LOOKUP / HYPOTHETICAL;
    # never in WRITE, PENDING_ANSWER, or READ_STATE.
    if cls == "READ_STATE":
        return set(READ)
    if cls in ("ASK", "READ_ONLY_REFUSE"):
        return set(READ) | {"no_lookup_needed"}
    if cls == "LOOKUP":
        out = set(LOOKUP_BASE)
        if has_fully_locked_anchor(state) and first_blank_slot_index(state) is not None:
            out |= SHOW
        return out
    if cls == "HYPOTHETICAL":
        out = set(LOOKUP_BASE) | set(HYPO)
        if has_fully_locked_anchor(state) and first_blank_slot_index(state) is not None:
            out |= SHOW
        return out
    if cls in ("WRITE", "PENDING_ANSWER"):
        out = set(CORE) | set(USAGE) | set(READ)
        out |= _write_tools_for_action(action, state)
        if numeric_or_explain:
            # NUMBERS + describe; not no_lookup_needed (FU22 §1 / mapping §6.3).
            out |= set(NUMBERS) | {"describe"}
        if has_fully_locked_anchor(state) and first_blank_slot_index(state) is not None:
            out |= SHOW
        return out
    return set(READ) | {"no_lookup_needed"}


def live_tool_names() -> frozenset[str]:
    """Names on the guard surface (cumulative draft schemas; flag args explicit)."""
    from scripts.eval.part_g_arm.state.tools import combined_specs

    names: set[str] = set()
    # Guard is cumulative on draft — always compare against that schema, not flags-off.
    for spec in combined_specs(tool_fields=True, wrapper=True, draft=True):
        fn = (spec.get("function") or {}) if isinstance(spec, dict) else {}
        name = fn.get("name")
        if isinstance(name, str) and name:
            names.add(name)
    return frozenset(names)


def filter_to_live_schemas(names: set[str], live: frozenset[str] | None = None) -> set[str]:
    """Drop bound names that have no live schema (e.g. set_constraint_active pre-FU21)."""
    registry = live if live is not None else live_tool_names()
    return {n for n in names if n in registry}


def allowed_tools(
    sub_requests: Sequence[Mapping[str, Any]] | None,
    state: Mapping[str, Any],
    *,
    pending_asked: Mapping[str, Any] | None = None,
    live: frozenset[str] | None = None,
    user_text: str | None = None,
) -> set[str]:
    """Union of tools bound by each sub-request against current state.

    PENDING_ANSWER without an action uses ``pending_asked['action']``.
    Uncertain / unknown class falls to ASK (READ + no_lookup_needed).
    Names with no live schema are skipped (FU22 §7).
    Under sticky_locks: unlock_fields/unlock_slot bind only when
    ``user_requests_unlock`` is true (FU66).
    """
    if not sub_requests:
        return filter_to_live_schemas(set(READ) | {"no_lookup_needed"}, live)
    out: set[str] = set()
    writeish = False
    for raw in sub_requests:
        sub = _normalize_sub(raw)
        action = sub["action"]
        if sub["class"] == "PENDING_ANSWER" and not action and pending_asked:
            action = str(pending_asked.get("action") or "").strip().lower() or None
        if sub["class"] in ("WRITE", "PENDING_ANSWER"):
            writeish = True
        out |= _bundle_for_class(
            sub["class"],
            action=action,
            numeric_or_explain=sub["numeric_or_explain"],
            state=state,
        )
    from scripts.eval.part_g_arm.state.tools import sticky_locks_enabled

    if sticky_locks_enabled() and writeish:
        if user_requests_unlock(user_text, pending_asked):
            out |= {"unlock_fields", "unlock_slot"}
        else:
            out -= {"unlock_fields", "unlock_slot"}
    return filter_to_live_schemas(out, live)


def stamp_pending_team_fingerprint(state: MutableMapping[str, Any]) -> None:
    """Attach OL10a fingerprint when a pending screen is created or refreshed."""
    pending = state.get("pending_presentation")
    if isinstance(pending, dict):
        pending = dict(pending)
        pending["team_fingerprint"] = team_fingerprint(state)
        state["pending_presentation"] = pending


def prepare_start_state_for_guard(state: MutableMapping[str, Any]) -> None:
    """Stamp fingerprint on a seeded pending screen (created with the seeded team).

    Called from the request-set runner when ``guard`` is on — not from unit tests.
    """
    if isinstance(state.get("pending_presentation"), dict):
        stamp_pending_team_fingerprint(state)


def replace_allowed(
    *,
    confirms_replacement: bool,
    pending_asked: Mapping[str, Any] | None,
) -> bool:
    """Execution gate for replace=true (mapping §4 / brief)."""
    if confirms_replacement:
        return True
    if pending_asked and str(pending_asked.get("action") or "").lower() in {
        "unlock_slot",
        "set_slot",
        "replace",
        "confirm_replace",
    }:
        return True
    return False


def user_requests_unlock(
    user_text: str | None,
    pending_asked: Mapping[str, Any] | None = None,
) -> bool:
    """True when this turn's user text (or pending-asked unlock action) asks to unlock.

    Primary sticky_locks unlock gate (FU66). Deterministic on user text; also accepts
    ``pending_asked.action`` in the unlock/clear family for PENDING_ANSWER follow-ups.
    Does **not** read ``confirms_replacement`` (that flag blocked explicit unlocks on
    MR6/MS2 when used alone for replace=true).
    """
    if pending_asked and str(pending_asked.get("action") or "").strip().lower() in (
        _UNLOCK_PENDING_ACTIONS
    ):
        return True
    if isinstance(user_text, str) and _UNLOCK_TEXT.search(user_text):
        return True
    return False
