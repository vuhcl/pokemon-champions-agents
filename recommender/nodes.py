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
from recommender.legality import check_set, is_species_legal, load_snapshot
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


def classify_pending(
    text: str,
    pending_presentation: PendingPresentation | None = None,
    *,
    bootstrap_intake_parser=None,
) -> dict[str, Any]:
    """Resolve a reply to a pending presentation; generic classification remains open."""
    if pending_presentation is None:
        raise NotImplementedError(
            "classify_pending is not wired; monkeypatch in tests or configure ADR-013 LLM"
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
                "turn_intent": "pending_response",
                "pending_presentation": None,
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
                "turn_intent": "pending_response",
                "pending_presentation": None,
                "pending_slot_intent": None,
                "provisional_slot": None,
                "provisional_refinement": None,
            }
        return {"turn_intent": "pending_response"}

    options = pending_presentation.get("options") or []
    selected: set[int] = set()

    candidate_text = reply
    for prefix in _SELECTION_PREFIXES:
        if reply.startswith(prefix):
            candidate_text = reply[len(prefix) :].strip()
            break
    candidate_id = to_id(candidate_text)
    selected.update(
        i for i, option in enumerate(options) if to_id(option["species"]) == candidate_id
    )

    ordinal = _ORDINAL_REPLIES.get(reply)
    if ordinal is not None and ordinal < len(options):
        selected.add(ordinal)

    if len(selected) == 1 and not signals:
        index = next(iter(selected))
    elif not selected and signals == {"affirm"} and options:
        index = 0
    elif not selected and signals == {"defer"}:
        return {"turn_intent": "pending_response", "pending_presentation": None}
    else:
        return {"turn_intent": "pending_response"}

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


def classify_input(state: RecommenderState, *, bootstrap_intake_parser=None) -> dict:
    text = state.get("pending_input")
    if not text:
        raise ValueError("pending_input is required for subsequent turns")
    result = classify_pending(
        text,
        state.get("pending_presentation"),
        bootstrap_intake_parser=bootstrap_intake_parser,
    )
    out = {
        "turn_intent": result["turn_intent"],
        "turn_payload": result.get("turn_payload"),
        "pending_input": None,
        "turn": state.get("turn", 0) + 1,
    }
    if "pending_presentation" in result:
        out["pending_presentation"] = result["pending_presentation"]
    if "slot_commit_error" in result:
        out["slot_commit_error"] = result["slot_commit_error"]
    if "bootstrap_intake_error" in result:
        out["bootstrap_intake_error"] = result["bootstrap_intake_error"]
    for key in ("pending_slot_intent", "provisional_slot", "provisional_refinement"):
        if key in result:
            out[key] = result[key]
    if "team_completion_preference" in result:
        out["team_completion_preference"] = result["team_completion_preference"]
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
) -> tuple[list[dict[str, Any]], tuple[str, ...]]:
    snap = load_snapshot()
    accepted: list[dict[str, Any]] = []
    unresolved: list[str] = []
    seen: set[str] = set()
    for row in rows:
        raw = str(row.get("species") or "")
        species_id = to_id(raw)
        entry = (snap.get("species") or {}).get(species_id)
        if not raw or entry is None or not is_species_legal(snap, species_id):
            unresolved.append(raw)
            continue
        if species_id in seen:
            continue
        seen.add(species_id)
        canonical = str(entry.get("name") or raw)
        accepted.append(
            {**row, "species": canonical}
            if preserve_fields
            else {"species": canonical}
        )
    return accepted, tuple(unresolved)


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
        accepted, newly_unresolved = _validated_bootstrap_pool(
            rows, preserve_fields=True
        )
        unresolved = (
            *state.get("unresolved_pool_entries", ()),
            *newly_unresolved,
        )
    elif not pool_entries:
        accepted, unresolved = [], ()
    else:
        accepted, unresolved = _validated_bootstrap_pool(
            [{"species": label} for label in pool_entries],
            preserve_fields=False,
        )

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
    return {
        "provisional_slot": result,
        "provisional_refinement": None,
        "slot_commit_error": None,
        "pending_slot_intent": replace(
            intent, target_role_decision=result.target_role_decision
        )
        if intent.target_role_decision != result.target_role_decision
        else intent,
        "pending_presentation": PendingPresentation(
            schema_version=1,
            kind="full_build_confirmation",
            slot_index=result.slot_index,
            provisional_fingerprint=result.fingerprint,
        ),
    }


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
    committed = Slot(
        role=Attr(provisional.role, True, reason),
        species=Attr(provisional.species, True, reason),
        ability=Attr(provisional.ability, True, reason),
        item=Attr(provisional.item, True, reason),
        moveset=Attr(list(provisional.moves), True, reason),
        spread=Attr(spread, True, reason),
        nature=Attr(provisional.nature, True, reason),
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


def bootstrap_direction(state: RecommenderState) -> dict:
    """Prompt once, then discover a concrete, evidence-backed opening direction."""

    cleared = {
        "coverage": [],
        "spofs": [],
        "shared_teammates": None,
        "last_team_review": None,
        "candidate_discovery_error": None,
    }
    unresolved = tuple(state.get("unresolved_pool_entries", ()))
    unresolved_notices = tuple(
        f"Couldn't identify: {label}" for label in unresolved
    )
    if unresolved and not state.get("available_pool"):
        unresolved_notices = (
            *unresolved_notices,
            "No owned bias was applied because no pool entries were recognized.",
        )
    if not state.get("bootstrap_intake_complete"):
        return {
            **cleared,
            "pending_presentation": _bootstrap_intake_presentation(
                state, unresolved_notices
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
                state, (*unresolved_notices, message)
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
    pending["notices"] = unresolved_notices
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
        run_slot_fill_terminal,
    )
    from recommender.team_candidates import owned_species_ids

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
    merge_need_resolved(context)
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
