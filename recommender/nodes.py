from __future__ import annotations

from dataclasses import replace
from typing import Any, Literal

from langgraph.types import RunnableConfig

from recommender.calc_client import CalcClientError
from recommender.coverage import (
    compute_team_coverage,
    detect_spof,
    get_relevant_threats,
)
from recommender.format import resolve_format
from recommender.ids import to_id
from recommender.legality import check_set, load_snapshot
from recommender.species_resolve import resolve_species_label
from recommender.matchup import MatchupEvidenceError
from recommender.present_text import BOOTSTRAP_PARSER_NOT_CONFIGURED
from recommender.recommend import SP_BUDGET, spread_sum
from recommender.reconcile import (
    reconcile_on_archetype_change,
    reconcile_on_sibling_change,
    simultaneous_lock_conflicts,
)
from recommender.state import (
    ArchetypeChangePayload,
    Attr,
    BootstrapResponsePayload,
    CandidateDiscoveryError,
    Constraint,
    ConstraintPayload,
    LockPayload,
    PendingPresentation,
    PendingFlag,
    PendingSlotIntent,
    ProvisionalSlot,
    ReasonRef,
    RecommenderState,
    RejectedEntry,
    RejectionPayload,
    ResetPayload,
    RestorePayload,
    SupersededEntry,
    Slot,
    TeamReviewResult,
    TargetRoleDecision,
    UnresolvedSlotRefinement,
    all_locked,
    empty_slot,
    slot_fingerprint,
)
from recommender.teammates import query_shared_teammates

SLOT_ATTRS = ("role", "species", "ability", "item", "moveset", "spread", "nature")
TeamPhase = Literal["empty", "single_locked", "multi_locked", "complete"]


_AFFIRMATIVE_REPLIES = frozenset(
    {
        "yes",
        "yeah",
        "yep",
        "ok",
        "okay",
        "sure",
        "default",
        "accept",
        "accept default",
        "use the default",
    }
)
_DEFER_REPLIES = frozenset(
    {"defer", "later", "not now", "skip for now", "come back to this"}
)
_REJECT_ALL_REPLIES = frozenset(
    {"no", "nope", "neither", "none", "reject", "reject all", "something else"}
)
_ORDINAL_REPLIES = {
    "1": 0,
    "option 1": 0,
    "first": 0,
    "first one": 0,
    "the first": 0,
    "the first one": 0,
    "2": 1,
    "option 2": 1,
    "second": 1,
    "second one": 1,
    "the second": 1,
    "the second one": 1,
    "3": 2,
    "option 3": 2,
    "third": 2,
    "third one": 2,
    "the third": 2,
    "the third one": 2,
}
_SELECTION_PREFIXES = ("choose ", "pick ", "go with ")

# lock on full_build_confirmation is blocked (I-type).
# continue on that screen is intercepted by _apply_continue_abandon_gate (Cluster B).
# team_review still clears pending — overlay fix is a follow-up, not this gate.
_BLOCKED_ON_KIND = {
    "candidate_selection": frozenset({"edit", "select_build_option", "compare"}),
    "completion_preference": frozenset({"edit", "select_build_option", "compare"}),
    "full_build_confirmation": frozenset({"lock"}),  # all lock, including cross-slot
    "none": frozenset({"edit", "select_build_option", "compare"}),
}
_MISMATCH_MSG = "That action isn't available here."
CONTINUE_ABANDON_MSG = "This will discard the pending build confirmation."
KEEP_BUILD_MSG = "Keeping the current build confirmation."
_ABANDON_AFFIRM = frozenset({"yes", "yeah", "yep"})
_ABANDON_DECLINE = frozenset({"no", "nope"})


def _index_build_options(
    pending: PendingPresentation,
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for group in pending.get("build_option_groups") or ():
        for opt in group.get("options") or ():
            oid = str(opt.get("option_id") or "")
            if oid:
                out[oid] = {**opt, "axis": group.get("axis")}
    return out


def _deterministic_build_option_ids(
    text: str, pending: PendingPresentation
) -> tuple[str, ...] | None:
    """Parse option ids / labels / ordinals across axis groups. None = not a clean select."""
    index = _index_build_options(pending)
    if not index:
        return None
    reply = text.strip().lower()
    for prefix in _SELECTION_PREFIXES:
        if reply.startswith(prefix):
            reply = reply[len(prefix) :].strip()
            break
    # split on + / and / ,
    raw_parts = [
        p.strip()
        for p in reply.replace(" and ", "+").replace(",", "+").split("+")
        if p.strip()
    ]
    if not raw_parts:
        return None
    groups = list(pending.get("build_option_groups") or ())
    picks: list[str] = []
    axes_used: set[str] = set()
    for part in raw_parts:
        matched: str | None = None
        if part in index:
            matched = part
        else:
            for oid, opt in index.items():
                if to_id(str(opt.get("label") or "")) == to_id(part):
                    matched = oid
                    break
                if oid.lower() == part:
                    matched = oid
                    break
        if matched is None:
            ordinal = _ORDINAL_REPLIES.get(part)
            if ordinal is not None and len(groups) == 1:
                opts = list(groups[0].get("options") or ())
                if ordinal < len(opts):
                    matched = str(opts[ordinal].get("option_id") or "")
        if not matched or matched not in index:
            return None
        axis = str(index[matched].get("axis") or "")
        if axis in axes_used:
            return None
        axes_used.add(axis)
        picks.append(matched)
    return tuple(picks) if picks else None


def _pending_response(message: str) -> dict[str, Any]:
    return {
        "turn_intent": "pending_response",
        "turn_payload": {"message": message},
    }


def _apply_classify_gates(
    result: dict[str, Any],
    pending: PendingPresentation | None,
) -> dict[str, Any]:
    """Replace illegal gap-fill intents with a non-mutating pending_response.

    Failure results omit _clear_pending_keys so classify_input leaves the
    current screen in place (lock is actionable and would otherwise clear it).
    """
    kind = str((pending or {}).get("kind") or "none")
    intent = result.get("turn_intent")
    if intent in _BLOCKED_ON_KIND.get(kind, frozenset()):
        return _pending_response(_MISMATCH_MSG)
    if (
        intent in {"select_build_option", "compare"}
        and kind == "full_build_confirmation"
    ):
        index = _index_build_options(pending) if pending is not None else {}
        payload = result.get("turn_payload") or {}
        ids = tuple(str(i) for i in (payload.get("option_ids") or ()))
        missing = [oid for oid in ids if oid not in index]
        if missing:
            valid = ", ".join(index)
            label = "id" if len(missing) == 1 else "ids"
            listed = ", ".join(missing)
            return _pending_response(
                f"Unknown build option {label}: {listed}. Valid ids: {valid}"
            )
    return result


def _apply_continue_abandon_gate(
    result: dict[str, Any],
    pending: PendingPresentation | None,
) -> dict[str, Any]:
    """Confirm before continue clears a full_build_confirmation.

    ponytail: A2 still nulls compare_analysis at classify_input start; a compare
    overlay vanishes across this round-trip. Re-request compare. Build is kept.
    """
    kind = str((pending or {}).get("kind") or "none")
    if result.get("turn_intent") != "continue" or kind != "full_build_confirmation":
        return result
    if pending is None:
        return result
    return {
        "turn_intent": "pending_response",
        "turn_payload": {"message": CONTINUE_ABANDON_MSG},
        "pending_presentation": {
            "schema_version": 1,
            "kind": "confirm_abandon_build",
            "queued_turn_intent": "continue",
            "queued_turn_payload": result.get("turn_payload"),
            "held_pending": pending,
        },
    }


def _emit_full_build_confirmation(
    state: RecommenderState,
    provisional: ProvisionalSlot,
    *,
    review_flags: tuple = (),
) -> dict[str, Any]:
    from recommender.build_alternatives import (
        generate_build_option_groups,
        provisional_for_confirmation,
    )

    base = provisional_for_confirmation(provisional, state)
    groups, default_ids = generate_build_option_groups(base, state)
    pending = PendingPresentation(
        schema_version=1,
        kind="full_build_confirmation",
        slot_index=base.slot_index,
        provisional_fingerprint=base.fingerprint,
        build_option_groups=groups,
        default_option_ids=default_ids,
    )
    if review_flags:
        pending["review_flags"] = review_flags
    return {
        "provisional_slot": base,
        "provisional_refinement": None,
        "slot_commit_error": None,
        "compare_analysis": None,
        "pending_presentation": pending,
    }


def _verify_provisional_hard(
    result: ProvisionalSlot, state: RecommenderState
) -> str | None:
    spread = result.spread_dict()
    if (
        set(spread) != {"hp", "atk", "def", "spa", "spd", "spe"}
        or any(not isinstance(v, int) or v < 0 or v > 32 for v in spread.values())
        or spread_sum(spread) != SP_BUDGET
    ):
        return "invalid edited spread"
    if len(result.moves) != 4 or any(not move for move in result.moves):
        return "edited build requires exactly four moves"
    legality = check_set(
        result.species,
        list(result.moves),
        result.item,
        ability=result.ability,
        team_draft=state["team_draft"],
        exclude_slot=result.slot_index,
    )
    if not legality.ok:
        return "illegal edited slot: " + "; ".join(
            f"{failure.kind}:{failure.element}" for failure in legality.failures
        )
    reason = ReasonRef(kind="user_stated")
    conflicts = simultaneous_lock_conflicts(
        result.to_slot(locked=True, reason=reason)
    )
    if conflicts:
        return "conflicting edited fields: " + ", ".join(
            "/".join(group) for group in conflicts
        )
    return None


def _gap_fill(
    text: str,
    *,
    turn_intent_parser,
    gap_fill_context: dict[str, str] | None,
    had_pending: bool,
    pending_presentation: PendingPresentation | None = None,
) -> dict[str, Any]:
    from recommender.turn_intent import parse_turn_intent

    ctx = gap_fill_context or {}
    result = parse_turn_intent(
        turn_intent_parser,
        user_text=text,
        pending_kind=ctx.get("pending_kind") or ("none" if not had_pending else ""),
        pending_context=ctx.get("pending_context") or "",
        roster_summary=ctx.get("roster_summary") or "",
        had_pending=had_pending,
    )
    result = _apply_classify_gates(result, pending_presentation)
    return _apply_continue_abandon_gate(result, pending_presentation)


def build_gap_fill_context(state: RecommenderState) -> dict[str, str]:
    """Prompt-only context for turn-intent gap-fill; never treated as verified facts."""

    pending = state.get("pending_presentation")
    kind = (pending or {}).get("kind") if pending else None
    pending_kind = str(kind or "none")
    pending_context = ""
    if pending:
        if kind == "candidate_selection":
            options = pending.get("options") or []
            names = ", ".join(str(o.get("species") or "") for o in options)
            pending_context = f"candidate options: {names}"
        elif kind == "completion_preference":
            prefs = pending.get("preference_options") or ()
            pending_context = f"preference options: {', '.join(str(p) for p in prefs)}"
        elif kind == "full_build_confirmation":
            intent = state.get("pending_slot_intent")
            provisional = state.get("provisional_slot")
            species = None
            if intent is not None:
                species = getattr(intent, "species", None)
            if not species and provisional is not None:
                species = getattr(provisional, "species", None)
            groups = pending.get("build_option_groups") or ()
            option_bits: list[str] = []
            for group in groups:
                axis = group.get("axis")
                for opt in group.get("options") or ():
                    option_bits.append(
                        f"{opt.get('option_id')}[{axis}]={opt.get('label')}"
                    )
            options_txt = "; ".join(option_bits) if option_bits else "none"
            pending_context = (
                f"full build confirmation for {species}; options: {options_txt}"
                if species
                else f"full build confirmation; options: {options_txt}"
            )
        elif kind == "bootstrap_intake":
            pending_context = "bootstrap intake"
    locked: list[str] = []
    for slot in state.get("team_draft") or []:
        if all_locked(slot):
            locked.append(str(getattr(slot.species, "value", None) or "?"))
    roster_summary = ", ".join(locked) if locked else ""
    return {
        "pending_kind": pending_kind,
        "pending_context": pending_context,
        "roster_summary": roster_summary,
    }


def classify_pending(
    text: str,
    pending_presentation: PendingPresentation | None = None,
    *,
    bootstrap_intake_parser=None,
    turn_intent_parser=None,
    gap_fill_context: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Resolve a reply to a pending presentation; gap-fill via injected turn_intent_parser."""
    if pending_presentation is None:
        if turn_intent_parser is None:
            raise NotImplementedError(
                "classify_pending is not wired; monkeypatch in tests or configure ADR-013 LLM"
            )
        return _gap_fill(
            text,
            turn_intent_parser=turn_intent_parser,
            gap_fill_context=gap_fill_context,
            had_pending=False,
            pending_presentation=pending_presentation,
        )

    reply = text.strip().casefold().strip(".!?")
    version = pending_presentation.get("schema_version", 1)
    if pending_presentation.get("kind") == "bootstrap_intake":
        if version != 1:
            return {
                "turn_intent": "pending_response",
                "bootstrap_intake_error": (
                    f"unsupported bootstrap schema version: {version}"
                ),
            }
        if bootstrap_intake_parser is None:
            return {
                "turn_intent": "pending_response",
                "bootstrap_intake_error": BOOTSTRAP_PARSER_NOT_CONFIGURED,
            }
        from recommender.bootstrap import (
            BootstrapIntakeParseError,
            parse_bootstrap_intake,
        )

        try:
            payload = parse_bootstrap_intake(bootstrap_intake_parser, text)
        except BootstrapIntakeParseError as exc:
            return {
                "turn_intent": "pending_response",
                "bootstrap_intake_error": str(exc),
            }
        return {
            "turn_intent": "bootstrap_response",
            "turn_payload": payload,
            "pending_presentation": None,
            "bootstrap_intake_error": None,
        }
    if pending_presentation.get("kind") == "completion_preference":
        if version != 2:
            return {
                "turn_intent": "pending_response",
                "pending_presentation": None,
                "slot_commit_error": f"unsupported pending schema version: {version}",
            }
        preferences = pending_presentation.get("preference_options") or ()
        ordinal = _ORDINAL_REPLIES.get(reply)
        selected = next(
            (
                preference
                for preference in preferences
                if reply == preference.casefold()
            ),
            None,
        )
        if selected is None and ordinal is not None and ordinal < len(preferences):
            selected = preferences[ordinal]
        if selected is not None:
            return {
                "turn_intent": "continue",
                "team_completion_preference": selected,
                "pending_presentation": None,
            }
        if reply in _DEFER_REPLIES:
            return {
                "turn_intent": "deferred",
                "pending_presentation": None,
            }
        if turn_intent_parser is None:
            return {"turn_intent": "pending_response"}
        return _gap_fill(
            text,
            turn_intent_parser=turn_intent_parser,
            gap_fill_context=gap_fill_context,
            had_pending=True,
            pending_presentation=pending_presentation,
        )
    if pending_presentation.get("kind") == "confirm_abandon_build":
        if pending_presentation.get("schema_version", 1) != 1:
            return {"turn_intent": "pending_response"}
        queued = pending_presentation.get("queued_turn_intent")
        held = pending_presentation.get("held_pending")
        if reply in _ABANDON_AFFIRM:
            if queued != "continue" or held is None:
                return {"turn_intent": "pending_response"}
            from recommender.turn_intent import _clear_pending_keys

            out: dict[str, Any] = {
                "turn_intent": "continue",
                **_clear_pending_keys(),
            }
            payload = pending_presentation.get("queued_turn_payload")
            if payload is not None:
                out["turn_payload"] = payload
            return out
        if reply in _ABANDON_DECLINE:
            if held is None:
                return {"turn_intent": "pending_response"}
            return {
                "turn_intent": "pending_response",
                "turn_payload": {"message": KEEP_BUILD_MSG},
                "pending_presentation": held,
            }
        return {"turn_intent": "pending_response"}
    if version != 1:
        return {
            "turn_intent": "pending_response",
            "pending_presentation": None,
            "slot_commit_error": f"unsupported pending schema version: {version}",
        }

    signals = {
        signal
        for signal, matched in (
            ("affirm", reply in _AFFIRMATIVE_REPLIES),
            ("defer", reply in _DEFER_REPLIES),
            ("reject", reply in _REJECT_ALL_REPLIES),
        )
        if matched
    }
    if pending_presentation.get("kind") == "full_build_confirmation":
        if signals == {"affirm"}:
            return {"turn_intent": "full_slot_confirmed"}
        if signals == {"defer"}:
            return {
                "turn_intent": "deferred",
                "pending_presentation": None,
                "pending_slot_intent": None,
                "provisional_slot": None,
                "provisional_refinement": None,
                "compare_analysis": None,
            }
        selected_ids = _deterministic_build_option_ids(text, pending_presentation)
        if selected_ids is not None:
            return {
                "turn_intent": "select_build_option",
                "turn_payload": {"option_ids": selected_ids},
            }
        if turn_intent_parser is None:
            return {"turn_intent": "pending_response"}
        return _gap_fill(
            text,
            turn_intent_parser=turn_intent_parser,
            gap_fill_context=gap_fill_context,
            had_pending=True,
            pending_presentation=pending_presentation,
        )

    options = pending_presentation.get("options") or []
    selected: set[int] = set()

    candidate_text = reply
    for prefix in _SELECTION_PREFIXES:
        if reply.startswith(prefix):
            candidate_text = reply[len(prefix) :].strip()
            break
    resolved = resolve_species_label(candidate_text, load_snapshot())
    candidate_id = to_id(resolved.name) if resolved else None
    selected.update(
        i
        for i, option in enumerate(options)
        if candidate_id is not None and to_id(option["species"]) == candidate_id
    )

    ordinal = _ORDINAL_REPLIES.get(reply)
    if ordinal is not None and ordinal < len(options):
        selected.add(ordinal)

    if len(selected) == 1 and not signals:
        index = next(iter(selected))
    elif not selected and signals == {"affirm"} and options:
        index = 0
    elif not selected and signals == {"defer"}:
        return {"turn_intent": "deferred", "pending_presentation": None}
    else:
        if turn_intent_parser is None:
            return {"turn_intent": "pending_response"}
        return _gap_fill(
            text,
            turn_intent_parser=turn_intent_parser,
            gap_fill_context=gap_fill_context,
            had_pending=True,
            pending_presentation=pending_presentation,
        )

    return {
        "turn_intent": "slot_candidate_selected",
        "selected_option": options[index],
    }


def initialize(state: RecommenderState) -> dict:
    format_id = state.get("format_id")
    if not format_id:
        raise ValueError("format_id is required")
    derived = resolve_format(format_id)
    out: dict = {**derived}
    if "team_draft" not in state or not state["team_draft"]:
        out["team_draft"] = [empty_slot() for _ in range(6)]
    if "archetype" not in state:
        out["archetype"] = Attr()
    if "rejected" not in state:
        out["rejected"] = []
    if "constraints" not in state:
        out["constraints"] = []
    if "available_pool" not in state:
        out["available_pool"] = []
    if "turn" not in state:
        out["turn"] = 0
    if "superseded" not in state:
        out["superseded"] = []
    if "pending_flags" not in state:
        out["pending_flags"] = []
    if "pending_presentation" not in state:
        out["pending_presentation"] = None
    if "pending_slot_intent" not in state:
        out["pending_slot_intent"] = None
    if "provisional_slot" not in state:
        out["provisional_slot"] = None
    if "provisional_refinement" not in state:
        out["provisional_refinement"] = None
    if "slot_commit_error" not in state:
        out["slot_commit_error"] = None
    if "compare_analysis" not in state:
        out["compare_analysis"] = None
    if "ownership_mode_source" not in state:
        out["ownership_mode_source"] = (
            "user" if "ownership_mode" in state else "default"
        )
    if "ownership_mode" not in state:
        out["ownership_mode"] = "off"
    if "bootstrap_intake_complete" not in state:
        out["bootstrap_intake_complete"] = False
    if "bootstrap_response" not in state:
        out["bootstrap_response"] = None
    if "bootstrap_intake_error" not in state:
        out["bootstrap_intake_error"] = None
    if "unresolved_pool_entries" not in state:
        out["unresolved_pool_entries"] = ()
    if "species_resolve_notices" not in state:
        out["species_resolve_notices"] = ()
    if "team_completion_preference" not in state:
        out["team_completion_preference"] = None
    if "candidate_discovery_error" not in state:
        out["candidate_discovery_error"] = None
    return out


def accept_available_pool(state: RecommenderState) -> dict:
    return {}


def team_phase(state: RecommenderState) -> TeamPhase:
    """Derive phase from fully confirmed members; partial slots do not count."""
    draft = state["team_draft"]
    confirmed = sum(all_locked(slot) for slot in draft)
    if draft and confirmed == len(draft):
        return "complete"
    if confirmed >= 2:
        return "multi_locked"
    if confirmed == 1:
        return "single_locked"
    return "empty"


def route_team_phase(_state: RecommenderState) -> dict:
    """Explicit graph decision point; conditional routing derives the phase."""
    return {}


def classify_input(
    state: RecommenderState,
    *,
    bootstrap_intake_parser=None,
    turn_intent_parser=None,
) -> dict:
    text = state.get("pending_input")
    if not text:
        raise ValueError("pending_input is required for subsequent turns")
    result = classify_pending(
        text,
        state.get("pending_presentation"),
        bootstrap_intake_parser=bootstrap_intake_parser,
        turn_intent_parser=turn_intent_parser,
        gap_fill_context=build_gap_fill_context(state),
    )
    out = {
        "turn_intent": result["turn_intent"],
        "turn_payload": result.get("turn_payload"),
        "pending_input": None,
        "turn": state.get("turn", 0) + 1,
        "slot_commit_error": None,
        "compare_analysis": None,
        "bootstrap_intake_error": None,
    }
    for key in (
        "pending_presentation",
        "slot_commit_error",
        "bootstrap_intake_error",
        "compare_analysis",
        "pending_slot_intent",
        "provisional_slot",
        "provisional_refinement",
        "team_completion_preference",
    ):
        if key in result:
            out[key] = result[key]
    option = result.get("selected_option")
    if option is not None:
        slot_index = int(state["pending_presentation"]["slot_index"])  # type: ignore[index]
        out["pending_slot_intent"] = PendingSlotIntent(
            schema_version=1,
            slot_index=slot_index,
            species=str(option["species"]),
            target_role_decision=option.get("target_role_decision"),
            source=option["source"],
            evidence=tuple(option.get("evidence", ())),
            base_slot_fingerprint=slot_fingerprint(state["team_draft"][slot_index]),
        )
        out["pending_presentation"] = None
    return out


def finish_pending_response(_state: RecommenderState) -> dict:
    return {}


def _validated_bootstrap_pool(
    rows: list[dict[str, Any]], *, preserve_fields: bool
) -> tuple[list[dict[str, Any]], tuple[str, ...], tuple[str, ...]]:
    snap = load_snapshot()
    accepted: list[dict[str, Any]] = []
    unresolved: list[str] = []
    notices: list[str] = []
    seen: set[str] = set()
    for row in rows:
        raw = str(row.get("species") or "")
        hit = resolve_species_label(raw, snap) if raw else None
        if hit is None:
            unresolved.append(raw)
            continue
        species_id = to_id(hit.name)
        if species_id in seen:
            continue
        seen.add(species_id)
        if hit.notice:
            notices.append(hit.notice)
        accepted.append(
            {**row, "species": hit.name}
            if preserve_fields
            else {"species": hit.name}
        )
    return accepted, tuple(unresolved), tuple(dict.fromkeys(notices))


def record_bootstrap_response(state: RecommenderState) -> dict:
    """Validate an extracted bootstrap payload without guessing names or strategy."""

    payload: BootstrapResponsePayload | None = state.get("turn_payload")  # type: ignore[assignment]
    if payload is None:
        return {
            "bootstrap_intake_error": "missing bootstrap response payload",
            "pending_presentation": state.get("pending_presentation"),
        }

    pool_entries = payload["pool_entries"]
    if pool_entries is None:
        rows = [dict(row) for row in state.get("available_pool", [])]
        accepted, newly_unresolved, pool_notices = _validated_bootstrap_pool(
            rows, preserve_fields=True
        )
        unresolved = (
            *state.get("unresolved_pool_entries", ()),
            *newly_unresolved,
        )
    elif not pool_entries:
        accepted, unresolved, pool_notices = [], (), ()
    else:
        accepted, unresolved, pool_notices = _validated_bootstrap_pool(
            [{"species": label} for label in pool_entries],
            preserve_fields=False,
        )
    anchor_notices: tuple[str, ...] = ()
    if payload.get("anchor_text"):
        anchor_hit = resolve_species_label(str(payload["anchor_text"]), load_snapshot())
        if anchor_hit and anchor_hit.notice:
            anchor_notices = (anchor_hit.notice,)
    species_resolve_notices = tuple(dict.fromkeys((*pool_notices, *anchor_notices)))

    requested_mode = payload.get("ownership_mode")
    if requested_mode is not None:
        ownership_mode = requested_mode
        ownership_source = "user"
    elif state.get("ownership_mode_source") == "user":
        ownership_mode = state.get("ownership_mode", "off")
        ownership_source = "user"
    else:
        ownership_mode = "owned_first" if accepted else "off"
        ownership_source = "default"

    return {
        "available_pool": accepted,
        "unresolved_pool_entries": unresolved,
        "species_resolve_notices": species_resolve_notices,
        "bootstrap_response": payload,
        "bootstrap_intake_complete": True,
        "bootstrap_intake_error": None,
        "ownership_mode": ownership_mode,
        "ownership_mode_source": ownership_source,
        "pending_presentation": None,
    }


def refine_provisional_slot(state: RecommenderState) -> dict:
    """Build a complete uncommitted slot, or retain a structured unresolved result."""
    intent = state.get("pending_slot_intent")
    if intent is None or intent.schema_version != 1:
        return {
            "provisional_refinement": UnresolvedSlotRefinement(
                schema_version=1,
                intent=intent
                or PendingSlotIntent(
                    schema_version=1,
                    slot_index=0,
                    species="",
                    target_role_decision=None,
                    source="threat",
                ),
                unresolved_fields=("pending_slot_intent",),
            ),
            "slot_commit_error": "missing or unsupported pending slot intent",
        }
    from recommender.slot_fill import build_provisional_slot

    result = build_provisional_slot(intent, state)
    if isinstance(result, UnresolvedSlotRefinement):
        reason = result.reason or "unresolved_fields:" + ",".join(
            result.unresolved_fields
        )
        return {
            "provisional_slot": None,
            "provisional_refinement": result,
            "slot_commit_error": f"Could not refine {intent.species}: {reason}",
        }
    out = _emit_full_build_confirmation(state, result)
    out["pending_slot_intent"] = (
        replace(intent, target_role_decision=result.target_role_decision)
        if intent.target_role_decision != result.target_role_decision
        else intent
    )
    return out


def apply_provisional_edit(state: RecommenderState) -> dict:
    """Revise pending provisional from EditPayload; re-present or keep prior on hard fail."""
    from recommender.edit_review import collect_provisional_review_flags
    from recommender.slot_fill import revise_provisional_slot

    intent = state.get("pending_slot_intent")
    provisional = state.get("provisional_slot")
    payload = state.get("turn_payload")
    if (
        intent is None
        or provisional is None
        or not isinstance(provisional, ProvisionalSlot)
        or not isinstance(payload, dict)
        or payload.get("field") is None
        or payload.get("scope") not in {"field_only", "regenerate"}
        or "value" not in payload
    ):
        return {"slot_commit_error": "missing or unsupported provisional edit state"}

    field = str(payload["field"])
    scope = payload["scope"]
    value = payload["value"]
    result = revise_provisional_slot(
        provisional,
        field=field,
        value=value,
        scope=scope,  # type: ignore[arg-type]
        intent=intent,
        state=state,
    )
    if isinstance(result, UnresolvedSlotRefinement):
        return {
            "slot_commit_error": (
                "Could not apply edit: "
                + (result.reason or ",".join(result.unresolved_fields))
            )
        }

    err = _verify_provisional_hard(result, state)
    if err:
        return {"slot_commit_error": err}

    flags = collect_provisional_review_flags(
        result, state, edited_fields=frozenset({field})
    )
    out = _emit_full_build_confirmation(state, result, review_flags=flags)
    out["pending_slot_intent"] = intent
    return out


def apply_provisional_option(state: RecommenderState) -> dict:
    """Apply selected build-option overrides; re-present or keep prior on hard fail."""
    from recommender.edit_review import collect_provisional_review_flags
    from recommender.slot_fill import apply_provisional_overrides

    intent = state.get("pending_slot_intent")
    provisional = state.get("provisional_slot")
    pending = state.get("pending_presentation")
    payload = state.get("turn_payload")
    if (
        intent is None
        or provisional is None
        or pending is None
        or not isinstance(provisional, ProvisionalSlot)
        or not isinstance(payload, dict)
        or not payload.get("option_ids")
    ):
        return {"slot_commit_error": "missing or unsupported provisional option state"}

    index = _index_build_options(pending)
    option_ids = tuple(str(i) for i in payload["option_ids"])
    merged: dict[str, object] = {}
    for oid in option_ids:
        opt = index.get(oid)
        if opt is None:
            return {"slot_commit_error": f"unknown build option id: {oid}"}
        for key, value in (opt.get("overrides") or {}).items():
            if key in merged:
                return {
                    "slot_commit_error": (
                        f"overlapping override key across selected options: {key}"
                    )
                }
            merged[key] = value

    result = apply_provisional_overrides(
        provisional,
        overrides=merged,
        intent=intent,
        state=state,
    )
    if isinstance(result, UnresolvedSlotRefinement):
        return {
            "slot_commit_error": (
                "Could not apply option: "
                + (result.reason or ",".join(result.unresolved_fields))
            )
        }

    err = _verify_provisional_hard(result, state)
    if err:
        return {"slot_commit_error": err}

    flags = collect_provisional_review_flags(
        result, state, edited_fields=frozenset(merged)
    )
    out = _emit_full_build_confirmation(state, result, review_flags=flags)
    out["pending_slot_intent"] = intent
    return out


def compare_build_options(state: RecommenderState) -> dict:
    """Non-mutating calc-backed compare; keeps pending/provisional."""
    from recommender.build_compare import compare_build_options as _compare

    provisional = state.get("provisional_slot")
    pending = state.get("pending_presentation")
    payload = state.get("turn_payload")
    if (
        provisional is None
        or pending is None
        or not isinstance(provisional, ProvisionalSlot)
        or not isinstance(payload, dict)
    ):
        return {"compare_analysis": "Nothing to compare."}
    option_ids = tuple(str(i) for i in (payload.get("option_ids") or ()))
    groups = tuple(pending.get("build_option_groups") or ())
    index = _index_build_options(pending)
    if len(option_ids) < 2 or any(oid not in index for oid in option_ids):
        return {
            "compare_analysis": "Name two or more valid build option ids to compare."
        }
    analysis = _compare(
        provisional,
        option_ids=option_ids,
        groups=groups,
        state=state,
    )
    return {"compare_analysis": analysis}


def _full_slot_error(message: str) -> dict:
    return {"slot_commit_error": message}


def commit_full_slot(state: RecommenderState) -> dict:
    """Prevalidate every field, then replace one slot exactly once."""
    intent = state.get("pending_slot_intent")
    provisional = state.get("provisional_slot")
    pending = state.get("pending_presentation")
    if (
        intent is None
        or provisional is None
        or pending is None
        or intent.schema_version != 1
        or provisional.schema_version != 1
        or pending.get("schema_version", 1) != 1
    ):
        return _full_slot_error("missing or unsupported full-slot confirmation state")
    if (
        pending.get("kind") != "full_build_confirmation"
        or pending.get("provisional_fingerprint") != provisional.fingerprint
        or intent.slot_index != provisional.slot_index
        or intent.species != provisional.species
        or not isinstance(intent.target_role_decision, TargetRoleDecision)
        or intent.target_role_decision != provisional.target_role_decision
    ):
        return _full_slot_error("stale or mismatched full-slot confirmation")

    index = provisional.slot_index
    if index < 0 or index >= len(state["team_draft"]):
        return _full_slot_error("slot index is out of range")
    current = state["team_draft"][index]
    if (
        not provisional.base_slot_fingerprint
        or provisional.base_slot_fingerprint != slot_fingerprint(current)
    ):
        return _full_slot_error("slot changed after candidate selection")

    spread = provisional.spread_dict()
    if (
        set(spread) != {"hp", "atk", "def", "spa", "spd", "spe"}
        or any(not isinstance(value, int) or value < 0 or value > 32 for value in spread.values())
        or spread_sum(spread) != SP_BUDGET
    ):
        return _full_slot_error("invalid provisional spread")
    if len(provisional.moves) != 4 or any(not move for move in provisional.moves):
        return _full_slot_error("a full slot requires exactly four moves")

    legality = check_set(
        provisional.species,
        list(provisional.moves),
        provisional.item,
        ability=provisional.ability,
        team_draft=state["team_draft"],
        exclude_slot=index,
    )
    if not legality.ok:
        return _full_slot_error(
            "illegal provisional slot: "
            + "; ".join(f"{failure.kind}:{failure.element}" for failure in legality.failures)
        )
    unsupported_hard = [
        constraint.predicate
        for constraint in state.get("constraints", [])
        if constraint.type == "hard"
        and constraint.still_active
        and "item" not in constraint.predicate.casefold()
    ]
    if unsupported_hard:
        return _full_slot_error(
            "unvalidated hard constraint: " + ", ".join(unsupported_hard)
        )

    reason = ReasonRef(kind="user_stated")
    committed = replace(
        provisional.to_slot(locked=True, reason=reason),
        rationale=current.rationale,
        verification=list(current.verification),
    )
    conflicts = simultaneous_lock_conflicts(committed)
    if conflicts:
        return _full_slot_error(
            "conflicting provisional fields: "
            + ", ".join("/".join(group) for group in conflicts)
        )

    draft = list(state["team_draft"])
    draft[index] = committed
    return {
        "team_draft": draft,
        "pending_presentation": None,
        "pending_slot_intent": None,
        "provisional_slot": None,
        "provisional_refinement": None,
        "slot_commit_error": None,
        "compare_analysis": None,
        "coverage": [],
        "spofs": [],
        "shared_teammates": None,
        "last_team_review": None,
        "candidate_discovery_error": None,
    }


def apply_lock(state: RecommenderState) -> dict:
    payload: LockPayload = state["turn_payload"]  # type: ignore[assignment]
    if payload.get("locks"):
        return _apply_locks_batch(state, payload)
    return _apply_lock_single(state, payload)


def _locks_pending_presentation(
    state: RecommenderState, payload: LockPayload
) -> bool:
    pending = state.get("pending_presentation")
    if (
        pending is None
        or pending.get("kind") != "candidate_selection"
        or payload.get("slot_index") != pending.get("slot_index")
        or payload.get("attr") != "species"
        or "value" not in payload
    ):
        return False
    selected = to_id(str(payload["value"]))
    return any(to_id(option["species"]) == selected for option in pending["options"])


def _apply_lock_single(state: RecommenderState, payload: LockPayload) -> dict:
    slot_index = payload["slot_index"]
    attr_name = payload["attr"]
    draft = list(state["team_draft"])
    slot = draft[slot_index]
    current: Attr[Any] = getattr(slot, attr_name)
    siblings_locked = any(
        getattr(slot, a).locked for a in SLOT_ATTRS if a != attr_name
    )

    if "value" in payload:
        new_attr = Attr(
            value=payload["value"],
            locked=True,
            reason=ReasonRef(kind="user_stated"),
            exempt_from_theme=current.exempt_from_theme,
        )
    else:
        new_attr = replace(current, locked=True)

    slot = replace(slot, **{attr_name: new_attr})
    out: dict = {}

    if siblings_locked:
        components = (state.get("archetype") or Attr()).value
        slot, superseded, pending_flags = reconcile_on_sibling_change(
            slot,
            attr_name,
            slot_index=slot_index,
            turn=state.get("turn", 0),
            components=components,
        )
        if superseded:
            out["superseded"] = [*state.get("superseded", []), *superseded]
        if pending_flags:
            out["pending_flags"] = [*state.get("pending_flags", []), *pending_flags]

    draft[slot_index] = slot
    out["team_draft"] = draft
    if _locks_pending_presentation(state, payload):
        out["pending_presentation"] = None
    return out


def _apply_locks_batch(state: RecommenderState, payload: LockPayload) -> dict:
    """N-attr simultaneous lock: lock conflict-free attrs; flag conflicting pairs."""
    slot_index = payload["slot_index"]
    locks = list(payload["locks"] or [])
    draft = list(state["team_draft"])
    slot = draft[slot_index]
    turn = state.get("turn", 0)
    components = (state.get("archetype") or Attr()).value
    out: dict = {}

    incoming: dict[str, object] = {}
    for entry in locks:
        attr = entry.get("attr")
        if not isinstance(attr, str) or attr not in SLOT_ATTRS:
            continue
        if "value" not in entry:
            continue
        incoming[attr] = entry["value"]

    # Provisional: all incoming as locked (detection only).
    provisional = slot
    for attr, value in incoming.items():
        provisional = replace(
            provisional,
            **{
                attr: Attr(
                    value=value,
                    locked=True,
                    reason=ReasonRef(kind="user_stated"),
                )
            },
        )

    groups = simultaneous_lock_conflicts(provisional)
    blocked: set[str] = set()
    for g in groups:
        blocked.update(a for a in g if a in incoming)

    pending: list[PendingFlag] = []
    for g in groups:
        if not any(a in incoming for a in g):
            continue
        values = {a: incoming[a] for a in g if a in incoming}
        pending.append(
            PendingFlag(
                slot_index=slot_index,
                attr=g[0],  # type: ignore[typeddict-item]
                value={"conflict": list(g), "values": values},
                flag_kind="simultaneous_lock_conflict",
            )
        )

    newly_locked: list[str] = []
    for attr, value in incoming.items():
        if attr in blocked:
            continue
        current: Attr[Any] = getattr(slot, attr)
        slot = replace(
            slot,
            **{
                attr: Attr(
                    value=value,
                    locked=True,
                    reason=ReasonRef(kind="user_stated"),
                    exempt_from_theme=current.exempt_from_theme,
                )
            },
        )
        newly_locked.append(attr)

    all_superseded: list[SupersededEntry] = []
    all_flags: list[PendingFlag] = list(pending)
    for attr in newly_locked:
        siblings_locked = any(
            getattr(slot, a).locked for a in SLOT_ATTRS if a != attr
        )
        if not siblings_locked:
            continue
        slot, superseded, flags = reconcile_on_sibling_change(
            slot,
            attr,
            slot_index=slot_index,
            turn=turn,
            components=components,
        )
        all_superseded.extend(superseded)
        all_flags.extend(flags)

    draft[slot_index] = slot
    out["team_draft"] = draft
    if all_superseded:
        out["superseded"] = [*state.get("superseded", []), *all_superseded]
    if all_flags:
        out["pending_flags"] = [*state.get("pending_flags", []), *all_flags]
    return out


def record_constraint(state: RecommenderState) -> dict:
    payload: ConstraintPayload = state["turn_payload"]  # type: ignore[assignment]
    constraint = Constraint(
        type=payload["type"],
        predicate=payload["predicate"],
        source_turn=state.get("turn", 0),
        scope=payload["scope"],
        groundedness=payload["groundedness"],
    )
    return {"constraints": [*state.get("constraints", []), constraint]}


def record_rejection(state: RecommenderState) -> dict:
    payload: RejectionPayload = state["turn_payload"]  # type: ignore[assignment]
    turn = state.get("turn", 0)
    entry = RejectedEntry(
        species=payload["species"],
        reason=payload.get("reason", ""),
        turn=turn,
    )
    out: dict = {"rejected": [*state.get("rejected", []), entry]}

    slot_index = payload.get("slot_index")
    if slot_index is not None:
        draft = list(state["team_draft"])
        slot = draft[slot_index]
        if not slot.species.locked:
            draft[slot_index] = replace(slot, species=Attr())
            out["team_draft"] = draft

    return out


def handle_archetype_change(state: RecommenderState) -> dict:
    payload: ArchetypeChangePayload = state["turn_payload"]  # type: ignore[assignment]
    new_components = payload["components"]
    out: dict = {
        "archetype": Attr(
            value=new_components,
            locked=True,
            reason=ReasonRef(kind="user_stated"),
        )
    }
    out.update(reconcile_on_archetype_change(state, new_components))
    return out


def restore_superseded(state: RecommenderState) -> dict:
    payload: RestorePayload = state["turn_payload"]  # type: ignore[assignment]
    slot_index = payload["slot_index"]
    attr_name = payload["attr"]
    superseded = list(state.get("superseded", []))
    match_idx = None
    for i in range(len(superseded) - 1, -1, -1):
        entry = superseded[i]
        if entry["slot_index"] == slot_index and entry["attr"] == attr_name:
            match_idx = i
            break
    if match_idx is None:
        return {}

    entry: SupersededEntry = superseded.pop(match_idx)
    draft = list(state["team_draft"])
    slot = draft[slot_index]
    restored = Attr(
        value=entry["value"],
        locked=True,
        reason=ReasonRef(kind="user_stated"),
        still_active=True,
    )
    draft[slot_index] = replace(slot, **{attr_name: restored})
    return {"team_draft": draft, "superseded": superseded}


def reset_team(state: RecommenderState) -> dict:
    payload: ResetPayload | None = state.get("turn_payload")  # type: ignore[assignment]
    out: dict = {
        "team_draft": [empty_slot() for _ in range(6)],
        "archetype": Attr(),
        "constraints": [],
        "pending_presentation": None,
        "pending_slot_intent": None,
        "provisional_slot": None,
        "provisional_refinement": None,
        "slot_commit_error": None,
        "compare_analysis": None,
        "coverage": [],
        "spofs": [],
        "shared_teammates": None,
        "last_team_review": None,
        "team_completion_preference": None,
        "candidate_discovery_error": None,
        "bootstrap_intake_complete": False,
        "bootstrap_response": None,
        "bootstrap_intake_error": None,
        "unresolved_pool_entries": (),
        "species_resolve_notices": (),
    }
    if payload:
        if "archetype" in payload:
            out["archetype"] = Attr(value=payload["archetype"])
        if "constraint" in payload:
            c = payload["constraint"]
            out["constraints"] = [
                Constraint(
                    type=c["type"],
                    predicate=c["predicate"],
                    source_turn=state.get("turn", 0),
                    scope=c["scope"],
                    groundedness=c["groundedness"],
                )
            ]
    return out


def propose_team_draft(state: RecommenderState) -> dict:
    from recommender.propose import fill_team_draft

    return fill_team_draft(state)


def _bootstrap_intake_presentation(
    state: RecommenderState, notices: tuple[str, ...] = ()
) -> PendingPresentation:
    labels = tuple(
        str(row["species"])
        for row in state.get("available_pool", [])
        if row.get("species")
    )
    existing = (
        f" Current available pool: {', '.join(labels)}." if labels else ""
    )
    return {
        "schema_version": 1,
        "kind": "bootstrap_intake",
        "prompt_text": (
            "What direction or anchor would you like to start with, and which Pokémon "
            "are available to you? You can provide either, both, or say 'you pick.' "
            "I can still recommend outside your available pool unless you request "
            f"owned-only.{existing}"
        ),
        "existing_pool_labels": labels,
        "notices": notices,
    }


def _bootstrap_notices(state: RecommenderState) -> tuple[str, ...]:
    unresolved = tuple(state.get("unresolved_pool_entries", ()))
    notices = tuple(f"Couldn't identify: {label}" for label in unresolved)
    if unresolved and not state.get("available_pool"):
        notices = (
            *notices,
            "No owned bias was applied because no pool entries were recognized.",
        )
    return (*notices, *state.get("species_resolve_notices", ()))


def bootstrap_direction(state: RecommenderState) -> dict:
    """Prompt once, then discover a concrete, evidence-backed opening direction."""

    cleared = {
        "coverage": [],
        "spofs": [],
        "shared_teammates": None,
        "last_team_review": None,
        "candidate_discovery_error": None,
    }
    notices = _bootstrap_notices(state)
    if not state.get("bootstrap_intake_complete"):
        return {
            **cleared,
            "pending_presentation": _bootstrap_intake_presentation(
                state, notices
            ),
        }

    from recommender.bootstrap import discover_bootstrap_directions
    from recommender.slot_fill import SlotFillContext, run_slot_fill_terminal

    discovery = discover_bootstrap_directions(state)
    if not discovery.candidates:
        message = discovery.clarification or "No bootstrap candidates were found."
        error = CandidateDiscoveryError(
            kind="no_candidates",
            stage="candidate_merge",
            message=message,
            retryable=True,
        )
        return {
            **cleared,
            "candidate_discovery_error": error,
            "pending_presentation": _bootstrap_intake_presentation(
                state, (*notices, message)
            ),
        }

    terminal = run_slot_fill_terminal(
        SlotFillContext(
            anchor=None,
            role_shape_context=None,
            annotated_candidates=list(discovery.candidates),
            candidates_pre_ranked=True,
        ),
        state,
        slot_index=0,
    )
    pending = dict(terminal.state_updates["pending_presentation"])
    pending["prompt_text"] = (
        "Choose the recommended starting direction or one of the strategically "
        "different alternatives."
    )
    pending["existing_pool_labels"] = tuple(
        str(row["species"])
        for row in state.get("available_pool", [])
        if row.get("species")
    )
    pending["notices"] = notices
    return {
        **cleared,
        **terminal.state_updates,
        "pending_presentation": pending,
    }


def discover_single_locked(state: RecommenderState) -> dict:
    """Run existing anchored discovery, or preserve legacy partial-slot handling."""
    from recommender.propose import fill_team_draft
    from recommender.slot_fill import (
        annotate_overlap,
        build_anchored_slot_fill_context,
        merge_need_resolved,
        resolve_all_support_needs,
        resolve_condition_beneficiaries,
        run_slot_fill_terminal,
    )
    from recommender.team_candidates import mega_ceiling_notices, owned_species_ids

    cleared = {
        "coverage": [],
        "spofs": [],
        "shared_teammates": None,
        "last_team_review": None,
        "candidate_discovery_error": None,
    }
    anchors = [slot for slot in state["team_draft"] if all_locked(slot)]
    open_slots = [
        (index, slot)
        for index, slot in enumerate(state["team_draft"])
        if not all_locked(slot)
    ]
    if len(anchors) != 1 or not open_slots:
        return {**cleared, **fill_team_draft({**state, **cleared})}

    slot_index, open_slot = open_slots[0]
    if any(
        getattr(open_slot, name).locked or getattr(open_slot, name).value is not None
        for name in SLOT_ATTRS
    ):
        return {**cleared, **fill_team_draft({**state, **cleared})}

    discovery = build_anchored_slot_fill_context(state, anchors[0])
    if discovery.context is None:
        return {**cleared, **fill_team_draft({**state, **cleared})}

    context = discovery.context
    annotate_overlap(context)
    resolve_all_support_needs(
        context,
        state,
        available_species=owned_species_ids(state),
        ownership_mode=state.get("ownership_mode", "off"),
    )
    resolve_condition_beneficiaries(
        context,
        discovery.anchor_role_decision,
        state,
        locked_species=[str(anchors[0].species.value)],
        available_species=owned_species_ids(state),
        ownership_mode=state.get("ownership_mode", "off"),
    )
    merge_need_resolved(context)
    context.notices = mega_ceiling_notices(state)
    if context.threat_discovery_status == "degraded":
        if not context.annotated_candidates:
            return {
                **cleared,
                "candidate_discovery_error": context.threat_discovery_error,
                "pending_presentation": None,
            }
        terminal = run_slot_fill_terminal(context, state, slot_index=slot_index)
        return {
            **cleared,
            **terminal.state_updates,
            "candidate_discovery_error": context.threat_discovery_error,
        }
    if not context.annotated_candidates:
        return {**cleared, **fill_team_draft({**state, **cleared})}
    terminal = run_slot_fill_terminal(context, state, slot_index=slot_index)
    return {**cleared, **terminal.state_updates}


def _compute_team_review(
    state: RecommenderState, config: RunnableConfig
) -> TeamReviewResult:
    from recommender.matchup import bind_matchup_memo_thread

    thread_id = (config.get("configurable") or {}).get("thread_id")
    bind_matchup_memo_thread(thread_id)
    candidates = get_relevant_threats(state)
    specs = [c.spec for c in candidates]
    regulation = state.get("regulation_mod") or "champions"
    draft = state["team_draft"]
    try:
        coverage = compute_team_coverage(draft, specs, regulation=regulation)
    except (CalcClientError, MatchupEvidenceError) as exc:
        return _unavailable_team_review(candidates, exc, "coverage")
    try:
        spofs = detect_spof(draft, specs, regulation=regulation)
    except (CalcClientError, MatchupEvidenceError) as exc:
        return _unavailable_team_review(candidates, exc, "spof")
    return TeamReviewResult(
        threats=candidates,
        coverage=coverage,
        spofs=spofs,
    )


def _unavailable_team_review(
    threats, exc: CalcClientError | MatchupEvidenceError, stage: Literal["coverage", "spof"]
) -> TeamReviewResult:
    return TeamReviewResult(
        threats=list(threats),
        coverage=[],
        spofs=[],
        status="unavailable",
        error=CandidateDiscoveryError(
            kind=(
                "calc_unavailable"
                if isinstance(exc, CalcClientError)
                else "calc_incomplete"
            ),
            stage=stage,
            message=str(exc),
            retryable=True,
            exception_type=type(exc).__name__,
            status_code=exc.status if isinstance(exc, CalcClientError) else None,
        ),
    )


def refresh_team_signals(state: RecommenderState, config: RunnableConfig) -> dict:
    """Recompute callable multi-member signals before the legacy proposal step."""
    from recommender.condition_resilience import assess_condition_resilience
    from recommender.team_candidates import collect_locked_anchor_contexts

    review = _compute_team_review(state, config)
    locked_species = [
        str(slot.species.value)
        for slot in state["team_draft"]
        if all_locked(slot) and slot.species.value
    ]
    contexts = collect_locked_anchor_contexts(state)
    return {
        "coverage": review.coverage,
        "spofs": review.spofs,
        "shared_teammates": query_shared_teammates(
            locked_species, state.get("regulation_mod") or "champions"
        ),
        "condition_resilience": assess_condition_resilience(contexts),
        "last_team_review": None,
        "candidate_discovery_error": review.error,
    }


def discover_multi_locked(
    state: RecommenderState, config: RunnableConfig
) -> dict:
    """Collect all locked-member evidence and present the next blank slot."""
    from recommender.condition_resilience import assess_condition_resilience
    from recommender.propose import fill_team_draft
    from recommender.slot_fill import SlotFillContext, run_slot_fill_terminal
    from recommender.team_candidates import (
        annotate_composition_impact,
        build_team_threat_objective,
        collect_locked_anchor_contexts,
        material_completion_preferences,
        mega_ceiling_notices,
        merge_multi_locked_candidates,
        owned_species_ids,
        rank_multi_locked_candidates,
    )
    from recommender.threat_counters import query_candidates_for_threats
    from recommender.usage_data import lineage_ids

    open_slots = [
        (index, slot)
        for index, slot in enumerate(state["team_draft"])
        if not all_locked(slot)
    ]
    if not open_slots:
        return {"candidate_discovery_error": None}
    slot_index, target = open_slots[0]
    ownership_mode = state.get("ownership_mode", "off")
    owned = owned_species_ids(state)
    locked_species = [
        str(slot.species.value)
        for slot in state["team_draft"]
        if all_locked(slot) and slot.species.value
    ]
    review = _compute_team_review(state, config)
    shared = query_shared_teammates(
        locked_species, state.get("regulation_mod") or "champions"
    )
    contexts = collect_locked_anchor_contexts(state)
    resilience = assess_condition_resilience(contexts)
    signals = {
        "coverage": review.coverage,
        "spofs": review.spofs,
        "shared_teammates": shared,
        "condition_resilience": resilience,
        "last_team_review": None,
    }
    if review.status == "unavailable":
        return {
            **signals,
            "candidate_discovery_error": review.error,
            "pending_presentation": None,
        }

    if any(
        getattr(target, name).locked or getattr(target, name).value is not None
        for name in SLOT_ATTRS
    ):
        return {
            **signals,
            **fill_team_draft({**state, **signals}),
            "candidate_discovery_error": None,
        }

    hard_constraints = [
        constraint.predicate
        for constraint in state.get("constraints", [])
        if constraint.type == "hard" and constraint.still_active
    ]
    if hard_constraints:
        error = CandidateDiscoveryError(
            kind="unsupported_constraint",
            stage="constraint_validation",
            message="Unsupported hard constraints: " + ", ".join(hard_constraints),
            retryable=False,
        )
        return {
            **signals,
            "candidate_discovery_error": error,
            "pending_presentation": None,
        }

    objective = build_team_threat_objective(review)
    excluded = {
        lineage for species in locked_species for lineage in lineage_ids(species)
    }
    threat_discovery = query_candidates_for_threats(
        objective,
        available_pool=sorted(owned),
        ownership_mode=ownership_mode,
        excluded_species=excluded,
    )
    if threat_discovery.status == "unavailable":
        return {
            **signals,
            "candidate_discovery_error": threat_discovery.error,
            "pending_presentation": None,
        }

    merged = merge_multi_locked_candidates(
        state,
        contexts,
        threat_discovery.candidates,
        shared,
        ownership_mode=ownership_mode,
        owned_species=owned,
        condition_resilience=resilience,
    )
    candidates = annotate_composition_impact(
        merged,
        state,
        locked_anchors=contexts,
        condition_resilience=resilience,
    )
    preference = state.get("team_completion_preference")
    if preference is None:
        choices = material_completion_preferences(
            candidates,
            objective=objective,
            ownership_mode=ownership_mode,
            owned_species=owned,
            regulation=state.get("regulation_mod") or "champions-reg-mb",
        )
        if choices:
            return {
                **signals,
                "candidate_discovery_error": None,
                "pending_presentation": {
                    "schema_version": 2,
                    "kind": "completion_preference",
                    "slot_index": slot_index,
                    "preference_options": choices,
                },
            }

    ranked = rank_multi_locked_candidates(
        candidates,
        objective=objective,
        preference=preference,
        ownership_mode=ownership_mode,
        owned_species=owned,
        regulation=state.get("regulation_mod") or "champions-reg-mb",
    )
    if not ranked:
        return {
            **signals,
            "candidate_discovery_error": CandidateDiscoveryError(
                kind="no_candidates",
                stage="candidate_merge",
                message="No eligible multi-locked candidates",
                retryable=False,
            ),
            "pending_presentation": None,
        }
    terminal = run_slot_fill_terminal(
        SlotFillContext(
            anchor=None,
            role_shape_context=None,
            annotated_candidates=ranked,
            candidates_pre_ranked=True,
            notices=mega_ceiling_notices(state),
        ),
        state,
        slot_index=slot_index,
    )
    return {
        **signals,
        **terminal.state_updates,
        "candidate_discovery_error": None,
    }


def generate_team_review(state: RecommenderState, config: RunnableConfig) -> dict:
    review = _compute_team_review(state, config)
    return {
        "coverage": review.coverage,
        "spofs": review.spofs,
        "shared_teammates": None,
        "condition_resilience": None,
        "last_team_review": review,
        "candidate_discovery_error": review.error,
    }
