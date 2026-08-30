from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Literal, Optional

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
from recommender.present_text import BOOTSTRAP_PARSER_NOT_CONFIGURED, format_roster
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
    ReviseLockedSlotPayload,
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



import recommender.nodes_classify as _nodes_classify

for _name in dir(_nodes_classify):
    if _name.startswith("__"):
        continue
    globals()[_name] = getattr(_nodes_classify, _name)

del _nodes_classify, _name

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
    if "force_completion_preference_prompt" not in state:
        out["force_completion_preference_prompt"] = False
    if "masked_slot_indices" not in state:
        out["masked_slot_indices"] = ()
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
        team_draft=state.get("team_draft"),
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
        "force_completion_preference_prompt",
        "masked_slot_indices",
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


REVISE_REQUIRES_LOCKED_MSG = "Attribute revision requires a fully locked slot."


def _route_after_locked_bootstrap(state: RecommenderState) -> str:
    if state.get("slot_commit_error"):
        return "end"
    return "apply_provisional_edit"


def begin_locked_slot_revision(state: RecommenderState) -> dict:
    """Seed provisional edit state from a fully locked team_draft slot."""
    from recommender.build_alternatives import _provisional_from_draft

    payload: ReviseLockedSlotPayload = state["turn_payload"]  # type: ignore[assignment]
    slot_index = payload["slot_index"]
    draft = state["team_draft"]
    if not (0 <= slot_index < len(draft)):
        return _full_slot_error("slot index is out of range")
    slot = draft[slot_index]
    if not all_locked(slot) or not slot.species.value or not slot.role.value:
        return _full_slot_error(REVISE_REQUIRES_LOCKED_MSG)

    decision = TargetRoleDecision(
        role_id=slot.role.value,
        source="other",
    )
    fp = slot_fingerprint(slot)
    intent = PendingSlotIntent(
        schema_version=1,
        slot_index=slot_index,
        species=str(slot.species.value),
        target_role_decision=decision,
        source="mixed",
        base_slot_fingerprint=fp,
    )
    shell = ProvisionalSlot(
        schema_version=1,
        slot_index=slot_index,
        target_role_decision=decision,
        species=str(slot.species.value),
        ability="",
        item="",
        moves=("", "", "", ""),
        nature="",
        spread=(),
        base_slot_fingerprint=fp,
        fingerprint="",
    )
    provisional = _provisional_from_draft(shell, slot)
    return {
        "pending_slot_intent": intent,
        "provisional_slot": provisional,
        "slot_commit_error": None,
    }


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
    if field == "spread" and (payload.get("spread_set") or payload.get("spread_delta")):
        from recommender.slot_fill import apply_partial_spread

        adjusted = apply_partial_spread(
            provisional.spread_dict(),
            set_stats=payload.get("spread_set"),
            delta_stats=payload.get("spread_delta"),
        )
        if adjusted is None:
            return {"slot_commit_error": "Could not apply edit: malformed spread adjustment"}
        value = adjusted
    elif field == "spread" and scope == "field_only":
        # No partial (set/delta) form was given -- only a full-form
        # value_spread. Confirmed live, twice: the model can scramble
        # stats it wasn't actually asked to change while attempting a
        # full-replacement computation (e.g. swapping spd/spa values),
        # especially when the request was really a compound select+edit
        # that the model flattened into a plain edit without option_ids.
        # Never trust this as a literal final answer -- diff it against
        # the current build (the implied "default" base, since no
        # option_ids was given at all) and only accept it if exactly one
        # stat actually differs.
        derived, derive_err = _derive_trustworthy_spread_edit(
            value, provisional.spread_dict()
        )
        if derive_err is not None:
            # Was previously a bare slot_commit_error -- a dead end, since
            # the message asked a question ("which ONE stat...") with no
            # way to ever hear the answer. Confirmed live: a follow-up
            # reply naming a stat got treated as an unrelated fresh turn
            # against the still-displayed full_build_confirmation menu,
            # producing a confusing unrelated response. Now builds a real
            # interactive question, same architecture as
            # spread_reallocation_question.
            from recommender.slot_fill import _coerce_full_spread

            base = provisional.spread_dict()
            attempted = _coerce_full_spread(value)
            diffs = (
                tuple(s for s in base if attempted[s] != base[s])
                if attempted is not None
                else ()
            )
            current_pending = state.get("pending_presentation")
            held = current_pending if isinstance(current_pending, dict) else None
            question: PendingPresentation = {
                "schema_version": 1,
                "kind": "spread_target_question",
                "slot_index": provisional.slot_index,
                "target_question_diffs": diffs,
                "target_question_edited_fields": (field,),
            }
            if held is not None:
                question["held_pending"] = held
            return {
                "provisional_slot": provisional,
                "pending_slot_intent": intent,
                "slot_commit_error": None,
                "pending_presentation": question,
            }
        value = derived
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
        excluded = {
            s.lower()
            for s in {
                *(payload.get("spread_set") or {}),
                *(payload.get("spread_delta") or {}),
            }
        }
        mismatch = _handle_spread_budget_mismatch(
            result,
            field=field,
            excluded_stats=excluded,
            state=state,
            intent=intent,
            edited_fields=frozenset({field}),
        )
        if mismatch is not None:
            return mismatch
        if field == "item":
            conflict = _handle_item_moveset_conflict(
                result,
                previous_item=provisional.item,
                state=state,
                intent=intent,
                edited_fields=frozenset({field}),
            )
            if conflict is not None:
                return conflict
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

    # A non-spread field edit combined with the selection ("1, but with
    # Choice Scarf" -- field="item"), composed the same way as any other
    # override, applied together with the option's own overrides in one
    # apply_provisional_overrides call rather than a separate step.
    extra_field = payload.get("extra_field")
    extra_value = payload.get("extra_value")
    if extra_field:
        if extra_field in merged:
            return {
                "slot_commit_error": (
                    f"overlapping override key between selection and edit: {extra_field}"
                )
            }
        merged[extra_field] = extra_value

    previous_item_value = provisional.item
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

    spread_set = payload.get("spread_set")
    spread_delta = payload.get("spread_delta")
    edited_fields = frozenset(merged)
    if spread_set or spread_delta:
        from recommender.slot_fill import apply_partial_spread, revise_provisional_slot

        adjusted = apply_partial_spread(
            result.spread_dict(), set_stats=spread_set, delta_stats=spread_delta
        )
        if adjusted is None:
            return {
                "slot_commit_error": "Could not apply option: malformed spread adjustment"
            }
        result = revise_provisional_slot(
            result,
            field="spread",
            value=adjusted,
            scope="field_only",
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
        edited_fields = edited_fields | {"spread"}

    err = _verify_provisional_hard(result, state)
    if err:
        excluded = {s.lower() for s in {*(spread_set or {}), *(spread_delta or {})}}
        mismatch = _handle_spread_budget_mismatch(
            result,
            field="spread" if "spread" in edited_fields else "",
            excluded_stats=excluded,
            state=state,
            intent=intent,
            edited_fields=edited_fields,
        )
        if mismatch is not None:
            return mismatch
        if "item" in edited_fields:
            conflict = _handle_item_moveset_conflict(
                result,
                previous_item=previous_item_value,
                state=state,
                intent=intent,
                edited_fields=edited_fields,
            )
            if conflict is not None:
                return conflict
        return {"slot_commit_error": err}

    flags = collect_provisional_review_flags(
        result, state, edited_fields=edited_fields
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


LOCK_FULLY_LOCKED_SLOT_MSG = "Revise a locked slot is not supported yet."


def commit_full_slot(state: RecommenderState) -> dict:
    """Prevalidate every field, then replace one slot exactly once."""
    from recommender.constraint_enforcement import commit_unsupported_hard_predicates

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
    unsupported_hard = commit_unsupported_hard_predicates(state.get("constraints", []))
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
    slot_index = payload["slot_index"]
    draft = state["team_draft"]
    if 0 <= slot_index < len(draft) and all_locked(draft[slot_index]):
        return _full_slot_error(LOCK_FULLY_LOCKED_SLOT_MSG)
    if payload.get("locks"):
        out = _apply_locks_batch(state, payload)
    else:
        out = _apply_lock_single(state, payload)
    return _clear_rejected_for_newly_locked_species(state, out)


def _clear_rejected_for_newly_locked_species(
    state: RecommenderState, out: dict
) -> dict:
    """A locked species can never coherently also be rejected.

    Locking is the strongest, most unambiguous "I want this" signal in this
    system — there is no scenario where the user wants a species both locked
    into their team and excluded from candidate generation as rejected. This
    removes any stale rejection for a species that just got locked, so a
    misclassified rejection (e.g. "I want Kingambit, not X" misread as
    rejecting Kingambit) is not permanently sticky once the user actually
    locks the species they wanted.
    """
    draft = out.get("team_draft")
    rejected = state.get("rejected") or []
    if not draft or not rejected:
        return out
    locked_species_ids = {
        to_id(slot.species.value)
        for slot in draft
        if slot.species.locked and slot.species.value
    }
    if not locked_species_ids:
        return out
    remaining = [
        entry
        for entry in rejected
        if to_id(entry["species"]) not in locked_species_ids
    ]
    if len(remaining) != len(rejected):
        out = {**out, "rejected": remaining}
    return out


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
    from recommender.constraint_enforcement import build_constraint

    payload: ConstraintPayload = state["turn_payload"]  # type: ignore[assignment]
    constraint = build_constraint(payload, source_turn=state.get("turn", 0))
    return {"constraints": [*state.get("constraints", []), constraint]}


def record_rejection(state: RecommenderState) -> dict:
    payload: RejectionPayload = state["turn_payload"]  # type: ignore[assignment]
    turn = state.get("turn", 0)
    entry = RejectedEntry(
        species=payload.get("species") or "",
        reason=payload.get("reason", ""),
        turn=turn,
    )
    ban = payload.get("ban_need_categories")
    if ban:
        entry["need_categories"] = list(ban)
    out: dict = {"rejected": [*state.get("rejected", []), entry]}

    slot_index = payload.get("slot_index")
    if slot_index is not None and entry["species"]:
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
            from recommender.constraint_enforcement import build_constraint

            c = payload["constraint"]
            out["constraints"] = [
                build_constraint(c, source_turn=state.get("turn", 0)),
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


def discover_single_locked(
    state: RecommenderState, config: Optional[RunnableConfig] = None
) -> dict:
    """Run existing anchored discovery, or preserve legacy partial-slot handling."""
    from recommender.condition_resilience import anchor_has_obvious_need
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

    # Route to discover_multi_locked instead of continuing with
    # single_locked's own (weaker) candidate generation when the anchor
    # has nothing obvious to fill (see anchor_has_obvious_need). Confirmed
    # live (2026-08-21): single_locked produces sharp, well-targeted
    # candidates when a real external dependency exists (Archaludon needs
    # Rain, can't provide it -- real Rain-setters surface correctly), but
    # near-arbitrary ones otherwise (Charizard-Mega-Y is self-sufficient
    # for its own real need -- Archaludon and Sinistcha surfaced despite
    # actively conflicting with the team's locked Sun; Kangaskhan
    # surfaced despite zero real teammate co-occurrence with the anchor,
    # since query_shared_teammates is never even called in this
    # function). Rather than rebuilding single_locked's own weaker
    # threat-coverage/condition-beneficiary/ranking machinery piece by
    # piece, reuse discover_multi_locked's better-tested one -- it
    # already handles N=1 locked anchors correctly (collect_locked_
    # anchor_contexts/assess_condition_resilience/merge_multi_locked_
    # candidates have no hardcoded assumption of multiple locked
    # members). This does NOT fix every gap found in that investigation:
    # resolve_condition_beneficiaries' hardcoded confidence (Castform,
    # pinned by a dedicated test, not fixed here -- needs a real design
    # decision on how to fold usage into evidence quality) is a shared
    # function called from both pipelines, unaffected by routing; a
    # genuine benefits_from/type-weakness-vs-locked-weather conflict
    # check (Archaludon/Sinistcha specifically) doesn't exist in either
    # pipeline and is a distinct, not-yet-implemented capability -- not
    # something this routing decision can or should paper over.
    # (resolve_need_candidates' missing already-locked exclusion, found
    # during the same investigation, was fixed directly in this same
    # change, not just routed around -- see its own docstring.)
    if not anchor_has_obvious_need(
        discovery.anchor_role_decision, context.support_needs
    ):
        return discover_multi_locked(state, config or {})

    from recommender.anchor_roles import provided_weather_conditions

    anchor_weathers = (
        provided_weather_conditions(discovery.anchor_role_decision)
        if hasattr(discovery.anchor_role_decision, "mechanisms")
        else ()
    )
    resolve_all_support_needs(
        context,
        state,
        available_species=owned_species_ids(state),
        ownership_mode=state.get("ownership_mode", "off"),
        locked_weather=anchor_weathers[0] if anchor_weathers else None,
        locked_species=[str(anchors[0].species.value)],
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

    # Give single-locked candidates the same essential/missing-provider gap
    # priority signal multi_locked candidates already get (ADR-026 Amendment
    # 2026-08-17a). collect_locked_anchor_contexts and
    # assess_condition_resilience are purely mechanism/role-classification
    # based -- confirmed zero calc dependency -- so this doesn't touch or
    # weaken single_locked's existing calc-independent resilience (need-
    # based candidates still surface even when threat-discovery/calc is
    # degraded or unavailable; only the *priority signal*, not candidate
    # availability, changes here).
    if context.annotated_candidates:
        from recommender.condition_resilience import assess_condition_resilience
        from recommender.team_candidates import (
            annotate_composition_impact,
            collect_locked_anchor_contexts,
        )

        locked_contexts = collect_locked_anchor_contexts(state)
        resilience = assess_condition_resilience(locked_contexts)
        context.annotated_candidates = annotate_composition_impact(
            context.annotated_candidates,
            state,
            locked_anchors=locked_contexts,
            condition_resilience=resilience,
        )
        from recommender.constraint_enforcement import (
            apply_mechanical_constraints_to_discovery,
            discovery_soft_specs,
        )

        filtered, constraint_err = apply_mechanical_constraints_to_discovery(
            context.annotated_candidates,
            state.get("constraints", []),
            team_draft=state["team_draft"],
            open_slot_index=slot_index,
        )
        if constraint_err is not None:
            return {
                **cleared,
                "candidate_discovery_error": constraint_err,
                "pending_presentation": None,
            }
        context.annotated_candidates = filtered
        context.soft_mechanical = discovery_soft_specs(state.get("constraints", []))
        context.constraint_slot_index = slot_index
        context.constraint_team_draft = state["team_draft"]

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
    from recommender.team_candidates import collect_locked_anchor_contexts

    thread_id = (config.get("configurable") or {}).get("thread_id")
    bind_matchup_memo_thread(thread_id)
    candidates = get_relevant_threats(state)
    specs = [c.spec for c in candidates]
    regulation = state.get("regulation_mod") or "champions"
    draft = state["team_draft"]
    locked_contexts = collect_locked_anchor_contexts(state)
    try:
        coverage = compute_team_coverage(
            draft, specs, regulation=regulation, locked_contexts=locked_contexts
        )
    except (CalcClientError, MatchupEvidenceError) as exc:
        return _unavailable_team_review(candidates, exc, "coverage")
    try:
        spofs = detect_spof(
            draft, specs, regulation=regulation, locked_contexts=locked_contexts
        )
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
        banned_profiles_from_rejected,
        build_team_threat_objective,
        collect_locked_anchor_contexts,
        material_completion_preferences,
        mega_ceiling_notices,
        merge_multi_locked_candidates,
        owned_species_ids,
        rank_multi_locked_by_category,
        gather_masked_core_packages,
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

    objective = build_team_threat_objective(review)
    excluded = {
        lineage for species in locked_species for lineage in lineage_ids(species)
    }
    threat_discovery = query_candidates_for_threats(
        objective,
        available_pool=sorted(owned),
        ownership_mode=ownership_mode,
        excluded_species=excluded,
        locked_contexts=contexts,
    )
    if threat_discovery.status == "unavailable":
        return {
            **signals,
            "candidate_discovery_error": threat_discovery.error,
            "pending_presentation": None,
        }
    # "degraded" (calc unavailable, fell back to static type-effectiveness)
    # still produces usable candidates -- surface the error alongside the
    # real presentation rather than silently dropping the signal, matching
    # discover_single_locked's existing behavior for the same status.
    degraded_error = (
        threat_discovery.error if threat_discovery.status == "degraded" else None
    )

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
        objective=objective,
    )
    from recommender.constraint_enforcement import (
        apply_mechanical_constraints_to_discovery,
        discovery_soft_specs,
    )

    candidates, constraint_err = apply_mechanical_constraints_to_discovery(
        candidates,
        state.get("constraints", []),
        team_draft=state["team_draft"],
        open_slot_index=slot_index,
    )
    if constraint_err is not None:
        return {
            **signals,
            "candidate_discovery_error": constraint_err,
            "pending_presentation": None,
        }
    soft_mechanical = discovery_soft_specs(state.get("constraints", []))
    packages = gather_masked_core_packages(
        candidates, state, contexts, objective=objective
    )
    if packages:
        resolution_options: list[dict] = [
            {"id": "keep_core", "label": "Keep current core"}
        ]
        for index, package in enumerate(packages):
            resolution_options.append(
                {
                    "id": f"package_{index}",
                    "label": package.label,
                    "masked_slot_indices": package.masked_slot_indices,
                    "option": {
                        "species": package.candidate.species,
                        "source": package.candidate.source,
                        "evidence": package.candidate.evidence,
                        "track": package.label,
                    },
                }
            )
        return {
            **signals,
            "candidate_discovery_error": None,
            "pending_presentation": {
                "schema_version": 2,
                "kind": "core_resolution",
                "slot_index": slot_index,
                "resolution_options": resolution_options,
            },
        }
    preference = state.get("team_completion_preference")
    force_prompt = bool(state.get("force_completion_preference_prompt"))
    if preference is None:
        choices = material_completion_preferences(
            candidates,
            objective=objective,
            ownership_mode=ownership_mode,
            owned_species=owned,
            regulation=state.get("regulation_mod") or "champions-reg-mb",
        )
        prompt_choices = choices or (
            ("attacker", "support", "balanced") if force_prompt else ()
        )
        if prompt_choices:
            return {
                **signals,
                "candidate_discovery_error": None,
                "force_completion_preference_prompt": False,
                "pending_presentation": {
                    "schema_version": 2,
                    "kind": "completion_preference",
                    "slot_index": slot_index,
                    "preference_options": prompt_choices,
                },
            }

    # Category-aware cut, not the old single-ranking rank_multi_locked_candidates
    # -- confirmed live, a real, significant bug: that function's shared
    # top-10 cut (via the old _rank_key) was defeating select_diverse_candidates'
    # entire purpose, since genuinely valuable Category B/C candidates
    # got cut from the pool entirely whenever 10+ candidates ranked
    # higher by threat-coverage/type-synergy criteria alone -- the
    # common case with real threat-counter data from live calc.
    ranked = rank_multi_locked_by_category(
        candidates,
        contexts,
        category_b_uncapped=preference == "support",
        soft_mechanical=soft_mechanical,
        team_draft=state["team_draft"],
        open_slot_index=slot_index,
    )
    if not ranked:
        # Mirrors discover_single_locked's leniency exactly: try an
        # archetype-driven proposal before giving up outright, rather than
        # hard-failing. Simple unconditional passthrough, matching the
        # proven, already-tested legacy pattern -- not adding extra
        # untested logic on top. Uses real, freshly-computed `signals`
        # here (not zeroed/cleared the way discover_single_locked's own
        # fallback does) -- a strict improvement, not just parity.
        from recommender.propose import fill_team_draft

        return {**signals, **fill_team_draft({**state, **signals})}
    terminal = run_slot_fill_terminal(
        SlotFillContext(
            anchor=None,
            role_shape_context=None,
            annotated_candidates=ranked,
            candidates_pre_ranked=True,
            notices=mega_ceiling_notices(state),
            condition_resilience=resilience,
            locked_contexts=tuple(contexts),
            team_completion_preference=preference,
            banned_profiles=banned_profiles_from_rejected(state.get("rejected")),
            soft_mechanical=soft_mechanical,
            constraint_slot_index=slot_index,
            constraint_team_draft=state["team_draft"],
        ),
        state,
        slot_index=slot_index,
    )
    return {
        **signals,
        **terminal.state_updates,
        "candidate_discovery_error": degraded_error,
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
