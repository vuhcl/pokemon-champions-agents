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
_KEEP_IT_REPLIES = frozenset(
    {
        "keep it", "keep it as is", "keep it as-is", "ignore", "ignore it",
        "ignore the conflict", "leave it", "leave it as is", "leave it as-is",
        "that's fine", "its fine", "it's fine", "fine", "keep as is",
    }
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
_BARE_NUMBER_RE = re.compile(r"^(?:option )?(\d+)$")


def _requested_option_number(part: str) -> int | None:
    """Extract N from bare 'N' or 'option N'. Exact match only -- '1' is not '11'."""
    match = _BARE_NUMBER_RE.match(part)
    return int(match.group(1)) if match else None


def _option_id_number(option_id: str) -> int | None:
    """Trailing numeric suffix after the last ':' (e.g. 'spread_nature:1' -> 1).

    None for non-numeric suffixes like 'spread_nature:default' -- those never
    match a bare-number reply, by design.
    """
    suffix = option_id.rsplit(":", 1)[-1]
    return int(suffix) if suffix.isdigit() else None


_DEFAULT_PHRASE_FILLER_WORDS = frozenset({"the", "one", "option", "please"})


def _is_default_phrase(part: str) -> bool:
    """True for informal references to the default option: 'default', 'the
    default', 'the default one', 'default one', 'the default option', etc.
    Confirmed live: 'the default one' failed to resolve at all before this,
    since the real id (e.g. 'spread_nature:default') is axis-prefixed and
    no bare-phrase matching existed for it."""
    words = [w for w in part.split() if w not in _DEFAULT_PHRASE_FILLER_WORDS]
    return words == ["default"]

# lock on full_build_confirmation is blocked (I-type).
# continue on that screen is intercepted by _apply_continue_abandon_gate (Cluster B).
# team_review on that screen is intercepted by _apply_team_review_roster_gate.
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


_LEADING_OPTION_NUMBER_RE = re.compile(
    r"^\s*(?:option\s+)?(\d+)\s*(?:,\s*(?:\bbut\b\s*)?|\bbut\b\s*|\+\s*)",
    re.IGNORECASE,
)


def _extract_leading_option_id(
    text: str, pending: PendingPresentation
) -> str | None:
    """Recover a leading option reference from mixed compound text ('2,
    but make it 5 Spe') that _deterministic_build_option_ids's stricter
    whole-text matching doesn't handle (it requires every split part to be
    a clean option reference, and 'but make it 5 spe' isn't one).

    Confirmed live: without this, the model unreliably extracts option_ids
    for this compound shape, and the edit silently falls back to applying
    against the currently-displayed default instead of the option the
    user actually named -- not scrambled anymore (the earlier fix already
    solved that), but still the wrong base spread.

    Only matches a real, unambiguous option id in the current single-group
    presentation -- returns None for anything else (multi-group menus,
    no match, ambiguous), same fail-closed contract as every other
    option-matching helper in this module.
    """
    match = _LEADING_OPTION_NUMBER_RE.match(text)
    if match is None:
        return None
    requested_number = int(match.group(1))
    groups = list(pending.get("build_option_groups") or ())
    if len(groups) != 1:
        return None
    opts = list(groups[0].get("options") or ())
    exact = [
        str(opt.get("option_id") or "")
        for opt in opts
        if _option_id_number(str(opt.get("option_id") or "")) == requested_number
    ]
    return exact[0] if len(exact) == 1 else None


def find_option_reference_anywhere(
    text: str, pending: PendingPresentation
) -> str | None:
    """Scan the WHOLE text (not just a leading position) for a real,
    unambiguous option reference -- a bare number, "option N", or an
    informal "default" phrase -- matching a real option id in the
    current single-group presentation. No separator word required at
    all, and no position requirement: "2, but use Choice Scarf", "use
    Choice Scarf and 2", "also select 2", "option 2 as well" all resolve
    the same way, since none of them need a specific trigger word to be
    recognized -- the real option number is just found wherever it is.

    Only safe when there's no competing numeric signal elsewhere in the
    same text -- true for ability/item/nature/moves edits (none have a
    numeric value of their own) but NOT true for spread edits (a stat
    value is itself a number that could coincidentally collide with a
    real option's numeric suffix). _extract_leading_option_id stays
    position-anchored specifically for that reason; this function is
    the generalized sibling used only where that risk doesn't apply.
    """
    groups = list(pending.get("build_option_groups") or ())
    if len(groups) != 1:
        return None
    opts = list(groups[0].get("options") or ())
    number_to_id: dict[int, str] = {}
    default_id: str | None = None
    for opt in opts:
        oid = str(opt.get("option_id") or "")
        if oid.endswith(":default"):
            default_id = oid
        num = _option_id_number(oid)
        if num is not None:
            number_to_id[num] = oid

    tokens = re.findall(r"[A-Za-z]+|\d+", text)
    found_ids: set[str] = set()
    for tok in tokens:
        if tok.isdigit() and int(tok) in number_to_id:
            found_ids.add(number_to_id[int(tok)])
    if default_id is not None and any(tok.lower() == "default" for tok in tokens):
        found_ids.add(default_id)

    return next(iter(found_ids)) if len(found_ids) == 1 else None


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
            requested_number = _requested_option_number(part)
            if requested_number is not None:
                # Numeric shorthand ("1", "option 1") always means the
                # option's own visible number (e.g. spread_nature:1), never
                # its position in the presented list -- those two diverge
                # whenever a default is prepended (default is always list
                # position 0 but carries no number of its own), which is
                # the common case for this presentation. Word-ordinals
                # ("first", "the second one") are handled separately below
                # and keep their existing list-position meaning, since
                # "first" naturally does mean "the first thing shown".
                if len(groups) == 1:
                    opts = list(groups[0].get("options") or ())
                    exact = [
                        str(opt.get("option_id") or "")
                        for opt in opts
                        if _option_id_number(str(opt.get("option_id") or ""))
                        == requested_number
                    ]
                    if len(exact) == 1:
                        matched = exact[0]
            elif _is_default_phrase(part):
                # Confirmed live: "the default one" failed with "Unknown
                # build option id: default" -- the real id is
                # "spread_nature:default" (axis-prefixed), and no bare
                # "default" phrasing was recognized at all before this.
                if len(groups) == 1:
                    opts = list(groups[0].get("options") or ())
                    exact = [
                        str(opt.get("option_id") or "")
                        for opt in opts
                        if str(opt.get("option_id") or "").endswith(":default")
                    ]
                    if len(exact) == 1:
                        matched = exact[0]
            else:
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


def _apply_team_review_roster_gate(
    result: dict[str, Any],
    pending: PendingPresentation | None,
    team_draft: list[Slot] | None,
) -> dict[str, Any]:
    """Show the locked roster without clearing a full_build_confirmation."""
    kind = str((pending or {}).get("kind") or "none")
    if result.get("turn_intent") != "team_review" or kind != "full_build_confirmation":
        return result
    return _pending_response(format_roster({"team_draft": team_draft or []}))


def _emit_full_build_confirmation(
    state: RecommenderState,
    provisional: ProvisionalSlot,
    *,
    review_flags: tuple = (),
    notices: tuple[str, ...] = (),
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
    if notices:
        pending["notices"] = notices
    return {
        "provisional_slot": base,
        "provisional_refinement": None,
        "slot_commit_error": None,
        "compare_analysis": None,
        "pending_presentation": pending,
    }


def _describe_invalid_spread(spread: dict[str, object]) -> str:
    """Specific, actionable message for why an edited spread failed hard
    verification -- confirmed live this was needed: a bare "invalid edited
    spread" gave the user no way to tell a 1-point budget overage (fixable
    by trimming another stat) from a structurally malformed dict, and no
    suggested next step either way.
    """
    expected = {"hp", "atk", "def", "spa", "spd", "spe"}
    if set(spread) != expected:
        missing = sorted(expected - set(spread))
        extra = sorted(set(spread) - expected)
        parts = []
        if missing:
            parts.append(f"missing {', '.join(missing)}")
        if extra:
            parts.append(f"unexpected {', '.join(extra)}")
        return "invalid edited spread: " + "; ".join(parts)
    out_of_range = [
        f"{stat}={value}"
        for stat, value in spread.items()
        if not isinstance(value, int) or value < 0 or value > 32
    ]
    if out_of_range:
        return (
            "invalid edited spread: each stat must be a whole number from 0 "
            "to 32 -- " + ", ".join(out_of_range)
        )
    total = spread_sum(spread)  # type: ignore[arg-type]
    diff = total - SP_BUDGET
    direction = "over" if diff > 0 else "under"
    action = "Reduce another stat to make room" if diff > 0 else "Add the leftover points to another stat"
    return (
        f"invalid edited spread: stats sum to {total}, but the budget is "
        f"{SP_BUDGET} ({abs(diff)} point{'s' if abs(diff) != 1 else ''} "
        f"{direction} budget). {action}, or ask me to regenerate the whole "
        "spread."
    )


def _derive_trustworthy_spread_edit(
    value: object, base_spread: dict[str, int]
) -> tuple[dict[str, int] | None, str | None]:
    """A field_only full-form value_spread from the model is never trusted
    as a literal final answer -- it's diffed against the real base spread
    (the current build, since no option selection was given -- i.e. the
    implied default). Confirmed live, twice: the model can scramble stats
    it wasn't actually asked to change while attempting a full-replacement
    computation (e.g. swapping spd/spa values), especially for what was
    really a compound select+edit request the model flattened into a
    plain edit without emitting option_ids at all.

    If exactly one stat differs from the base, that's trusted as the real
    intended change and everything else in the model's dict is discarded
    (the other 'differences,' if the model got any wrong, never mattered
    since the real base values are used instead). Zero or more than one
    differing stat is NOT silently trusted -- returns an error message
    instead of guessing which of several implied changes was real.

    Only applies to scope=="field_only" edits -- an explicit "regenerate"
    is a deliberate signal from the model (defaults to field_only when
    omitted, so regenerate only appears when genuinely intended) and a
    legitimate multi-stat regenerate request shouldn't be blocked here.
    """
    from recommender.slot_fill import _coerce_full_spread

    attempted = _coerce_full_spread(value)
    if attempted is None:
        return None, "invalid edited spread"
    diffs = [stat for stat in base_spread if attempted[stat] != base_spread[stat]]
    if not diffs:
        return dict(base_spread), None
    if len(diffs) == 1:
        return attempted, None
    stat_list = ", ".join(_stat_label_for_dispatch(s) for s in diffs)
    return None, (
        f"that implies changing {len(diffs)} stats ({stat_list}) at once, "
        "and I'm not confident in that computation -- which ONE stat did "
        "you actually want to change, and to what value?"
    )


_SPREAD_STAT_ORDER = ("hp", "atk", "def", "spa", "spd", "spe")


def _spread_structurally_valid(spread: dict[str, object]) -> bool:
    """True if spread has exactly the six expected keys, each an in-range int.
    Does NOT check the budget total -- that's a separate concern (see
    _spread_budget_diff), since a structurally-valid-but-over/under-budget
    spread is handled by a different flow (auto-reallocate or ask) than a
    genuinely malformed one (hard error, no clarifying flow).
    """
    expected = set(_SPREAD_STAT_ORDER)
    return set(spread) == expected and all(
        isinstance(v, int) and 0 <= v <= 32 for v in spread.values()
    )


def _spread_budget_diff(spread: dict[str, int]) -> int | None:
    """Signed budget diff (positive=over, negative=under) if spread is
    otherwise structurally valid but doesn't sum to SP_BUDGET. None if the
    spread is valid, or if it's invalid for a different reason entirely
    (those go through the plain hard-error path, not this one)."""
    if not _spread_structurally_valid(spread):
        return None
    diff = spread_sum(spread) - SP_BUDGET
    return diff if diff != 0 else None


# Overage/underage this small is treated as unambiguously fixable without
# asking -- confirmed reasonable scope with Vu, not assumed.
_AUTO_REALLOCATE_MAX_DIFF = 2


def _auto_reallocate_spread(
    spread: dict[str, int], diff: int, excluded_stats: set[str]
) -> tuple[dict[str, int], str] | None:
    """Attempt an unambiguous, deterministic fix for a small budget
    mismatch. Returns (adjusted_spread, description) on a clean, single-
    stat fix; None if the situation is genuinely ambiguous (multiple
    equally-plausible source stats, or no single stat has enough room) --
    the caller should ask the user instead of guessing.

    Rule: only for |diff| <= _AUTO_REALLOCATE_MAX_DIFF. Among the
    non-excluded stats with room to absorb the change, pick the one with
    the smallest current value (the most likely "dump stat," least likely
    to be a deliberate investment) -- but only if there's a single clear
    smallest, not a tie, since a tie is exactly the kind of case that
    should be asked about rather than decided silently.
    """
    if abs(diff) > _AUTO_REALLOCATE_MAX_DIFF:
        return None
    candidates = [
        stat
        for stat in _SPREAD_STAT_ORDER
        if stat not in excluded_stats
        and (
            (diff > 0 and spread[stat] - diff >= 0)
            or (diff < 0 and spread[stat] - diff <= 32)
        )
    ]
    if not candidates:
        return None
    smallest = min(spread[stat] for stat in candidates)
    tied = [stat for stat in candidates if spread[stat] == smallest]
    if len(tied) != 1:
        return None
    chosen = tied[0]
    adjusted = dict(spread)
    adjusted[chosen] -= diff
    verb = "reducing" if diff > 0 else "increasing"
    label = "HP" if chosen == "hp" else chosen.capitalize()
    return adjusted, (
        f"freed up {abs(diff)} point{'s' if abs(diff) != 1 else ''} by "
        f"{verb} {label} to {adjusted[chosen]}"
    )


def _disallowed_status_move_names(
    result: ProvisionalSlot, snap: dict[str, Any]
) -> list[str]:
    """Status-move names (excluding Trick/Switcheroo) present in the
    moveset -- mirrors reconcile._moveset_has_disallowed_status's exact
    matching logic, but collects the offending move names instead of a
    bare bool, purely for building a specific message. Does not change or
    duplicate the real conflict-detection logic in reconcile.py.
    """
    from recommender.reconcile import _ITEM_SWAP_MOVES

    moves_meta = snap.get("moves") or {}
    names = []
    for move in result.moves:
        mid = to_id(move)
        if mid in _ITEM_SWAP_MOVES:
            continue
        meta = moves_meta.get(mid) or {}
        if (meta.get("category") or "") == "Status":
            names.append(move)
    return names


def _find_damaging_move_alternatives(
    result: ProvisionalSlot, *, regulation: str, limit: int = 3
) -> list[str]:
    """Real, usage-backed damaging move alternatives for this species,
    excluding moves already in the current set. Reuses existing data
    (resolve_learnset, move_narrowing._commitment_pct) rather than
    inventing a new suggestion pipeline -- confirmed directly against the
    live Archaludon+Choice-Scarf scenario before this was written: yields
    Draco Meteor, Aura Sphere, Thunderbolt, in real commitment-% order,
    Aura Sphere being the exact move tried live in an earlier, unrelated
    timeout.
    """
    from recommender.legality import resolve_learnset
    from recommender.move_narrowing import _commitment_pct

    snap = load_snapshot()
    learnset = resolve_learnset(snap, result.species) or []
    moves_meta = snap.get("moves") or {}
    current = {to_id(m) for m in result.moves}

    candidates: list[tuple[str, float]] = []
    for mid in learnset:
        if mid in current:
            continue
        meta = moves_meta.get(mid) or {}
        if (meta.get("category") or "") == "Status":
            continue
        pct = _commitment_pct(result.species, mid, regulation=regulation)
        if pct is not None:
            candidates.append((mid, pct))
    candidates.sort(key=lambda pair: -pair[1])
    id_to_name = {to_id(m): m for m in learnset}
    return [
        moves_meta.get(mid, {}).get("name") or id_to_name.get(mid, mid)
        for mid, _ in candidates[:limit]
    ]


def _handle_item_moveset_conflict(
    result: ProvisionalSlot,
    *,
    previous_item: str,
    state: RecommenderState,
    intent: PendingSlotIntent,
    edited_fields: frozenset[str],
) -> dict | None:
    """If `result` fails hard verification specifically because of a
    Choice-item + non-damaging-move conflict, build an interactive
    resolution question (pick a damaging alternative, keep it anyway, or
    revert the item) instead of a dead-end error. Returns None if this
    isn't that specific failure -- caller proceeds to the normal error
    path unchanged, same pattern as _handle_spread_budget_mismatch.
    """
    from recommender.reconcile import _tier1_choice_status_moves

    reason = ReasonRef(kind="user_stated")
    snap = load_snapshot()
    # Gate on the real detection function first -- it verifies a genuine
    # Choice item is actually locked, not just that a status move happens
    # to be present. Confirmed live via a real test failure:
    # _disallowed_status_move_names alone fired for a completely fake,
    # illegal item (which should have surfaced as an "illegal edited slot"
    # error instead), since it never checked the item at all.
    if _tier1_choice_status_moves(result.to_slot(locked=True, reason=reason), snap) is None:
        return None
    status_moves = _disallowed_status_move_names(result, snap)
    if not status_moves:
        return None
    regulation = state.get("regulation_mod") or "champions-reg-mb"
    alternatives = _find_damaging_move_alternatives(result, regulation=regulation)
    current_pending = state.get("pending_presentation")
    held = current_pending if isinstance(current_pending, dict) else None
    question: PendingPresentation = {
        "schema_version": 1,
        "kind": "item_moveset_conflict_question",
        "slot_index": result.slot_index,
        "conflict_attempted_item": result.item,
        "conflict_previous_item": previous_item,
        "conflict_moves": tuple(status_moves),
        "conflict_move_alternatives": tuple(alternatives),
        "conflict_edited_fields": tuple(sorted(edited_fields)),
    }
    if held is not None:
        question["held_pending"] = held
    return {
        # The stored base is the PRE-edit, still-valid provisional (not
        # `result`, which carries the conflicted attempt) -- matches
        # spread_target_question's pattern: defer needs no special-case
        # revert logic, since leaving provisional_slot untouched at the
        # pre-edit state already IS the correct revert outcome. The
        # attempted item is preserved separately in the question's own
        # fields, and other resolution paths re-derive the final result
        # from this base plus the stored answer.
        "provisional_slot": state.get("provisional_slot"),
        "pending_slot_intent": intent,
        "slot_commit_error": None,
        "pending_presentation": question,
    }


def _verify_provisional_hard(
    result: ProvisionalSlot,
    state: RecommenderState,
    *,
    accept_status_move_conflict: bool = False,
) -> str | None:
    spread = result.spread_dict()
    if (
        set(spread) != {"hp", "atk", "def", "spa", "spd", "spe"}
        or any(not isinstance(v, int) or v < 0 or v > 32 for v in spread.values())
        or spread_sum(spread) != SP_BUDGET
    ):
        return _describe_invalid_spread(spread)
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
    slot = result.to_slot(locked=True, reason=reason)
    if accept_status_move_conflict:
        # The user explicitly consented to the Choice-item/status-move
        # conflict via item_moveset_conflict_question -- don't re-flag
        # that specific issue. But check the OTHER conflict this same
        # group can bundle (_tier1_speed_direction, Choice Scarf + Trick
        # Room) independently and separately, per explicit scope decision
        # with Vu: "ignore" only bypasses the specific issue shown and
        # consented to, never an unrelated one riding along in the same
        # bundled conflict group.
        from recommender.reconcile import _tier1_speed_direction

        speed_conflict = _tier1_speed_direction(slot)
        if speed_conflict is not None:
            return (
                "conflicting edited fields: item/moveset ("
                + speed_conflict.detail
                + ")"
            )
        return None
    conflicts = simultaneous_lock_conflicts(slot)
    if conflicts:
        if ("item", "moveset") in [tuple(sorted(g)) for g in conflicts]:
            status_moves = _disallowed_status_move_names(result, load_snapshot())
            if status_moves:
                return (
                    f"{result.item} locks you into repeating one move, which "
                    f"doesn't work with {', '.join(status_moves)} still in the "
                    "set. Swap out the status move too, or pick a different item."
                )
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
    team_draft: list[Slot] | None = None,
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
    if (
        result.get("turn_intent") == "select_build_option"
        and pending_presentation is not None
        and pending_presentation.get("kind") == "full_build_confirmation"
    ):
        payload = result.get("turn_payload")
        if isinstance(payload, dict):
            index = _index_build_options(pending_presentation)
            ids = tuple(str(i) for i in (payload.get("option_ids") or ()))
            if ids and any(oid not in index for oid in ids):
                # Confirmed live ("1, but with Choice Scarf"): the model can
                # extract a bare, unresolved option id ("1") instead of the
                # real axis-prefixed one ("spread_nature:1"), not just drop
                # option_ids entirely. Recover from the raw text, before the
                # "Unknown build option id" safety net (_apply_classify_gates)
                # gets a chance to reject it outright.
                #
                # Uses the general, position-independent finder unless the
                # payload also carries a spread signal (spread_set/delta) --
                # a stat value is itself a number that could coincidentally
                # collide with a real option's numeric suffix, so that case
                # stays on the position-anchored extractor to avoid the
                # ambiguity. Every other case (a plain, non-spread compound
                # select, or no edit signal at all) has no such risk.
                has_spread_signal = bool(
                    payload.get("spread_set") or payload.get("spread_delta")
                )
                recovered = (
                    _extract_leading_option_id(text, pending_presentation)
                    if has_spread_signal
                    else find_option_reference_anywhere(text, pending_presentation)
                )
                if recovered is not None:
                    result = {
                        **result,
                        "turn_payload": {**payload, "option_ids": (recovered,)},
                    }
    result = _apply_classify_gates(result, pending_presentation)
    result = _apply_continue_abandon_gate(result, pending_presentation)
    return _apply_team_review_roster_gate(result, pending_presentation, team_draft)


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


from recommender.slot_fill import parse_stat_reply as _parse_stat_reply
from recommender.slot_fill import stat_label as _stat_label_for_dispatch


def _reask_reallocation(
    pending_presentation: PendingPresentation, reason: str
) -> dict[str, Any]:
    updated: PendingPresentation = dict(pending_presentation)  # type: ignore[assignment]
    updated["reallocation_rejection_reason"] = reason
    return {"turn_intent": "pending_response", "pending_presentation": updated}


def resolve_spread_reallocation(state: RecommenderState) -> dict[str, Any]:
    """Apply the user's chosen stat to resolve a spread_reallocation_question,
    re-verify, and either succeed (full_build_confirmation) or re-ask (same
    kind, with a reason) if the chosen stat doesn't have enough room.

    A proper graph node (not resolved inline in classify_pending) because
    it needs state["provisional_slot"]/state["pending_slot_intent"] --
    classify_pending only receives specific extracted pieces, not full
    state, the same reason apply_provisional_edit/apply_provisional_option
    are also separate nodes rather than resolved inline.
    """
    from recommender.edit_review import collect_provisional_review_flags
    from recommender.slot_fill import revise_provisional_slot

    pending_presentation = state.get("pending_presentation")
    payload = state.get("turn_payload")
    if (
        not isinstance(pending_presentation, dict)
        or pending_presentation.get("kind") != "spread_reallocation_question"
        or not isinstance(payload, dict)
        or not payload.get("chosen_stat")
    ):
        return {"slot_commit_error": "missing or unsupported reallocation state"}
    chosen_stat = str(payload["chosen_stat"])

    spread = dict(pending_presentation.get("reallocation_attempted_spread") or {})
    diff = pending_presentation.get("reallocation_diff") or 0
    excluded = set(pending_presentation.get("reallocation_excluded_stats") or ())
    edited_fields = frozenset(
        pending_presentation.get("reallocation_edited_fields") or ()
    )
    intent = state.get("pending_slot_intent")
    provisional = state.get("provisional_slot")

    label = _stat_label_for_dispatch(chosen_stat)
    if chosen_stat in excluded:
        return _reask_reallocation(
            pending_presentation,
            f"{label} is the stat you're already changing -- pick a different one.",
        )
    current_value = spread.get(chosen_stat, 0)
    new_value = current_value - diff
    if new_value < 0 or new_value > 32:
        return _reask_reallocation(
            pending_presentation,
            f"{label} doesn't have enough room ({current_value} would become "
            f"{new_value}). Pick a different stat.",
        )
    adjusted_spread = dict(spread)
    adjusted_spread[chosen_stat] = new_value

    if (
        intent is None
        or provisional is None
        or not isinstance(provisional, ProvisionalSlot)
    ):
        return {
            "slot_commit_error": "Could not resolve reallocation: missing provisional state"
        }

    reapplied = revise_provisional_slot(
        provisional,
        field="spread",
        value=adjusted_spread,
        scope="field_only",
        intent=intent,
        state=state,
    )
    if isinstance(reapplied, UnresolvedSlotRefinement):
        return {
            "slot_commit_error": (
                "Could not apply that adjustment: "
                + (reapplied.reason or ",".join(reapplied.unresolved_fields))
            )
        }
    err = _verify_provisional_hard(reapplied, state)
    if err:
        return {"slot_commit_error": err}
    flags = collect_provisional_review_flags(
        reapplied, state, edited_fields=edited_fields
    )
    out = _emit_full_build_confirmation(state, reapplied, review_flags=flags)
    out["pending_slot_intent"] = intent
    return out


def resolve_spread_target_question(state: RecommenderState) -> dict[str, Any]:
    """Apply the stat+value the user named to resolve a
    spread_target_question, going through the same auto-reallocate/ask
    machinery as any other spread edit in case the answer itself creates a
    budget mismatch (e.g. answering 'Spe 5' still needs points freed up
    from somewhere else).
    """
    from recommender.edit_review import collect_provisional_review_flags
    from recommender.slot_fill import apply_partial_spread, revise_provisional_slot

    pending_presentation = state.get("pending_presentation")
    payload = state.get("turn_payload")
    if (
        not isinstance(pending_presentation, dict)
        or pending_presentation.get("kind") != "spread_target_question"
        or not isinstance(payload, dict)
        or not payload.get("stat")
        or payload.get("value") is None
    ):
        return {"slot_commit_error": "missing or unsupported spread target question state"}

    stat = str(payload["stat"])
    num_value = int(payload["value"])
    is_delta = bool(payload.get("is_delta"))
    intent = state.get("pending_slot_intent")
    provisional = state.get("provisional_slot")
    edited_fields = frozenset(
        pending_presentation.get("target_question_edited_fields") or ()
    )

    if (
        intent is None
        or provisional is None
        or not isinstance(provisional, ProvisionalSlot)
    ):
        return {
            "slot_commit_error": "Could not resolve that: missing provisional state"
        }

    adjusted = apply_partial_spread(
        provisional.spread_dict(),
        set_stats=None if is_delta else {stat: num_value},
        delta_stats={stat: num_value} if is_delta else None,
    )
    if adjusted is None:
        return {"slot_commit_error": "Could not apply that adjustment: malformed spread"}

    reapplied = revise_provisional_slot(
        provisional,
        field="spread",
        value=adjusted,
        scope="field_only",
        intent=intent,
        state=state,
    )
    if isinstance(reapplied, UnresolvedSlotRefinement):
        return {
            "slot_commit_error": (
                "Could not apply that adjustment: "
                + (reapplied.reason or ",".join(reapplied.unresolved_fields))
            )
        }
    err = _verify_provisional_hard(reapplied, state)
    if err:
        # The answer itself might create a budget mismatch (e.g. "Spe 5"
        # still needs points freed up) -- reuse the same auto-reallocate/
        # ask machinery rather than dead-ending again.
        mismatch = _handle_spread_budget_mismatch(
            reapplied,
            field="spread",
            excluded_stats={stat},
            state=state,
            intent=intent,
            edited_fields=edited_fields,
        )
        if mismatch is not None:
            return mismatch
        return {"slot_commit_error": err}
    flags = collect_provisional_review_flags(
        reapplied, state, edited_fields=edited_fields
    )
    out = _emit_full_build_confirmation(state, reapplied, review_flags=flags)
    out["pending_slot_intent"] = intent
    return out


def resolve_item_moveset_conflict(state: RecommenderState) -> dict[str, Any]:
    """Resolve an item_moveset_conflict_question: replace the conflicting
    move with the chosen alternative, or accept the conflict and apply the
    item change anyway (narrowly -- re-verifies everything else, including
    the OTHER conflict this same group can bundle, so "keep it" never
    silently waves through an unrelated issue).
    """
    from recommender.edit_review import collect_provisional_review_flags
    from recommender.slot_fill import apply_provisional_overrides

    pending_presentation = state.get("pending_presentation")
    payload = state.get("turn_payload")
    if (
        not isinstance(pending_presentation, dict)
        or pending_presentation.get("kind") != "item_moveset_conflict_question"
        or not isinstance(payload, dict)
        or payload.get("action") not in {"keep", "replace_move"}
    ):
        return {
            "slot_commit_error": "missing or unsupported item conflict question state"
        }

    intent = state.get("pending_slot_intent")
    provisional = state.get("provisional_slot")
    attempted_item = pending_presentation.get("conflict_attempted_item")
    conflicting_moves = pending_presentation.get("conflict_moves") or ()
    edited_fields = frozenset(
        pending_presentation.get("conflict_edited_fields") or ()
    )
    if (
        intent is None
        or provisional is None
        or not isinstance(provisional, ProvisionalSlot)
        or not attempted_item
    ):
        return {
            "slot_commit_error": "Could not resolve that: missing provisional state"
        }

    overrides: dict[str, Any] = {"item": attempted_item}
    accept_conflict = False
    if payload["action"] == "keep":
        accept_conflict = True
    else:
        chosen_move = str(payload["move"])
        new_moves = list(provisional.moves)
        # Replace the first conflicting move found in the current moveset
        # with the chosen alternative -- confirmed conflicting_moves[0]
        # exists in provisional.moves by construction (it was read from
        # this same provisional's moveset when the question was built).
        target = to_id(conflicting_moves[0]) if conflicting_moves else None
        replaced = False
        for i, move in enumerate(new_moves):
            if target is not None and to_id(move) == target:
                new_moves[i] = chosen_move
                replaced = True
                break
        if not replaced:
            return {
                "slot_commit_error": "Could not apply that adjustment: original move not found"
            }
        overrides["moves"] = tuple(new_moves)

    result = apply_provisional_overrides(
        provisional, overrides=overrides, intent=intent, state=state
    )
    if isinstance(result, UnresolvedSlotRefinement):
        return {
            "slot_commit_error": (
                "Could not apply that adjustment: "
                + (result.reason or ",".join(result.unresolved_fields))
            )
        }
    err = _verify_provisional_hard(
        result, state, accept_status_move_conflict=accept_conflict
    )
    if err:
        return {"slot_commit_error": err}
    flags = collect_provisional_review_flags(
        result, state, edited_fields=edited_fields | set(overrides)
    )
    out = _emit_full_build_confirmation(state, result, review_flags=flags)
    out["pending_slot_intent"] = intent
    return out


def classify_pending(
    text: str,
    pending_presentation: PendingPresentation | None = None,
    *,
    bootstrap_intake_parser=None,
    turn_intent_parser=None,
    gap_fill_context: dict[str, str] | None = None,
    team_draft: list[Slot] | None = None,
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
            team_draft=team_draft,
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
            team_draft=team_draft,
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
    if pending_presentation.get("kind") == "spread_reallocation_question":
        if pending_presentation.get("schema_version", 1) != 1:
            return {"turn_intent": "pending_response"}
        if reply in _DEFER_REPLIES:
            held = pending_presentation.get("held_pending")
            if held is None:
                return {
                    "turn_intent": "pending_response",
                    "pending_presentation": None,
                    "pending_slot_intent": None,
                    "provisional_slot": None,
                }
            return {
                "turn_intent": "pending_response",
                "turn_payload": {"message": KEEP_BUILD_MSG},
                "pending_presentation": held,
            }
        chosen_stat = _parse_stat_reply(reply)
        if chosen_stat is None:
            return _reask_reallocation(
                pending_presentation,
                "I couldn't tell which stat you meant.",
            )
        return {
            "turn_intent": "resolve_spread_reallocation",
            "turn_payload": {"chosen_stat": chosen_stat},
        }
    if pending_presentation.get("kind") == "spread_target_question":
        if pending_presentation.get("schema_version", 1) != 1:
            return {"turn_intent": "pending_response"}
        if reply in _DEFER_REPLIES:
            held = pending_presentation.get("held_pending")
            if held is None:
                return {
                    "turn_intent": "pending_response",
                    "pending_presentation": None,
                    "pending_slot_intent": None,
                    "provisional_slot": None,
                }
            return {
                "turn_intent": "pending_response",
                "turn_payload": {"message": KEEP_BUILD_MSG},
                "pending_presentation": held,
            }
        from recommender.turn_intent import extract_single_stat_target

        target = extract_single_stat_target(text)
        if target is None:
            updated: PendingPresentation = dict(pending_presentation)  # type: ignore[assignment]
            updated["target_question_rejection_reason"] = (
                "I couldn't tell which stat and value you meant."
            )
            return {"turn_intent": "pending_response", "pending_presentation": updated}
        stat, num_value, is_delta = target
        return {
            "turn_intent": "resolve_spread_target_question",
            "turn_payload": {"stat": stat, "value": num_value, "is_delta": is_delta},
        }
    if pending_presentation.get("kind") == "item_moveset_conflict_question":
        if pending_presentation.get("schema_version", 1) != 1:
            return {"turn_intent": "pending_response"}
        if reply in _DEFER_REPLIES:
            held = pending_presentation.get("held_pending")
            if held is None:
                return {
                    "turn_intent": "pending_response",
                    "pending_presentation": None,
                    "pending_slot_intent": None,
                    "provisional_slot": None,
                }
            return {
                "turn_intent": "pending_response",
                "turn_payload": {"message": KEEP_BUILD_MSG},
                "pending_presentation": held,
            }
        if reply in _KEEP_IT_REPLIES:
            return {
                "turn_intent": "resolve_item_moveset_conflict",
                "turn_payload": {"action": "keep"},
            }
        alternatives = pending_presentation.get("conflict_move_alternatives") or ()
        chosen_move: str | None = None
        if reply.isdigit():
            idx = int(reply) - 1
            if 0 <= idx < len(alternatives):
                chosen_move = alternatives[idx]
        else:
            for alt in alternatives:
                if to_id(alt) == to_id(text):
                    chosen_move = alt
                    break
        if chosen_move is None:
            updated_q: PendingPresentation = dict(pending_presentation)  # type: ignore[assignment]
            updated_q["conflict_rejection_reason"] = (
                "I couldn't tell which move you meant."
            )
            return {"turn_intent": "pending_response", "pending_presentation": updated_q}
        return {
            "turn_intent": "resolve_item_moveset_conflict",
            "turn_payload": {"action": "replace_move", "move": chosen_move},
        }
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
        result = _gap_fill(
            text,
            turn_intent_parser=turn_intent_parser,
            gap_fill_context=gap_fill_context,
            had_pending=True,
            pending_presentation=pending_presentation,
            team_draft=team_draft,
        )
        if result.get("turn_intent") == "edit":
            payload = result.get("turn_payload")
            if isinstance(payload, dict) and payload.get("field") == "spread" and (
                payload.get("spread_set") or payload.get("spread_delta")
            ):
                leading_id = _extract_leading_option_id(text, pending_presentation)
                if leading_id is not None:
                    # The model dropped the leading option reference
                    # ("2, but make it 5 Spe" -> no option_ids), so the
                    # edit would otherwise silently apply against the
                    # currently-displayed default instead of the option
                    # actually named. Recovered deterministically from
                    # the raw text; converts this into the same
                    # select_build_option + partial-spread shape the
                    # compound-resolution machinery already handles.
                    result = {
                        "turn_intent": "select_build_option",
                        "turn_payload": {
                            "option_ids": (leading_id,),
                            "spread_set": payload.get("spread_set"),
                            "spread_delta": payload.get("spread_delta"),
                        },
                    }
            elif isinstance(payload, dict) and payload.get("field") in {
                "ability", "item", "nature", "moves",
            }:
                # Confirmed live ("2+use Choice Scarf"): the model can
                # correctly extract a non-spread edit (field=item,
                # value_text=Choice Scarf) while dropping the option
                # reference entirely (option_ids=None) -- not just for
                # spread edits. Uses the general, position-independent
                # finder here (not the leading-position-only one): none
                # of ability/item/nature/moves have a numeric value of
                # their own, so there's no risk of confusing an option
                # number with something else, regardless of where in the
                # text it appears or what word (if any) surrounds it.
                leading_id = find_option_reference_anywhere(text, pending_presentation)
                if leading_id is not None:
                    result = {
                        "turn_intent": "select_build_option",
                        "turn_payload": {
                            "option_ids": (leading_id,),
                            "extra_field": payload.get("field"),
                            "extra_value": payload.get("value"),
                        },
                    }
        return result

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
            team_draft=team_draft,
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


def _handle_spread_budget_mismatch(
    result: ProvisionalSlot,
    *,
    field: str,
    excluded_stats: set[str],
    state: RecommenderState,
    intent: PendingSlotIntent,
    edited_fields: frozenset[str],
) -> dict | None:
    """If `result`'s spread is structurally valid but off the SP budget,
    either auto-reallocate (small, unambiguous overage/underage) or ask
    the user which stat to use. Returns None when there's nothing to
    handle here -- caller proceeds to the normal _verify_provisional_hard
    path unchanged. Only ever intervenes for field=="spread"; every other
    edit field and every other invalid-spread reason (out of range,
    malformed) is untouched, per the agreed scope.
    """
    if field != "spread":
        return None
    spread = result.spread_dict()
    diff = _spread_budget_diff(spread)
    if diff is None:
        return None

    from recommender.edit_review import collect_provisional_review_flags
    from recommender.slot_fill import revise_provisional_slot

    all_edited_fields = edited_fields | {"spread"}
    auto = _auto_reallocate_spread(spread, diff, excluded_stats)
    if auto is not None:
        adjusted_spread, description = auto
        reapplied = revise_provisional_slot(
            result,
            field="spread",
            value=adjusted_spread,
            scope="field_only",
            intent=intent,
            state=state,
        )
        if isinstance(reapplied, ProvisionalSlot):
            err = _verify_provisional_hard(reapplied, state)
            if err is None:
                flags = collect_provisional_review_flags(
                    reapplied, state, edited_fields=all_edited_fields
                )
                out = _emit_full_build_confirmation(
                    state,
                    reapplied,
                    review_flags=flags,
                    notices=(f"Adjusted spread: {description}.",),
                )
                out["pending_slot_intent"] = intent
                return out
        # Auto-reallocation didn't actually produce a clean result (should
        # be rare given the heuristic's own bounds-checking, but fail
        # closed to asking rather than silently giving up) -- fall through.

    current_pending = state.get("pending_presentation")
    held = current_pending if isinstance(current_pending, dict) else None
    reallocation_pending: PendingPresentation = {
        "schema_version": 1,
        "kind": "spread_reallocation_question",
        "slot_index": result.slot_index,
        "reallocation_attempted_spread": spread,
        "reallocation_diff": diff,
        "reallocation_excluded_stats": tuple(sorted(excluded_stats)),
        "reallocation_edited_fields": tuple(sorted(all_edited_fields)),
    }
    if held is not None:
        reallocation_pending["held_pending"] = held
    return {
        "provisional_slot": result,
        "pending_slot_intent": intent,
        "slot_commit_error": None,
        "pending_presentation": reallocation_pending,
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
        build_team_threat_objective,
        collect_locked_anchor_contexts,
        material_completion_preferences,
        mega_ceiling_notices,
        merge_multi_locked_candidates,
        owned_species_ids,
        rank_multi_locked_by_category,
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

    # Category-aware cut, not the old single-ranking rank_multi_locked_candidates
    # -- confirmed live, a real, significant bug: that function's shared
    # top-10 cut (via the old _rank_key) was defeating select_diverse_candidates'
    # entire purpose, since genuinely valuable Category B/C candidates
    # got cut from the pool entirely whenever 10+ candidates ranked
    # higher by threat-coverage/type-synergy criteria alone -- the
    # common case with real threat-counter data from live calc.
    ranked = rank_multi_locked_by_category(candidates, contexts)
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
