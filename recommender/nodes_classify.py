"""Turn-intent classification, spread validation, and gap-fill (extracted from nodes)."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Literal, Optional

from langgraph.types import RunnableConfig

from recommender.calc_client import CalcClientError
from recommender.ids import to_id
from recommender.legality import check_set, load_snapshot
from recommender.matchup import MatchupEvidenceError
from recommender.present_text import BOOTSTRAP_PARSER_NOT_CONFIGURED, format_roster
from recommender.recommend import SP_BUDGET, spread_sum
from recommender.reconcile import simultaneous_lock_conflicts
from recommender.species_resolve import resolve_species_label
from recommender.state import (
    Attr,
    BootstrapResponsePayload,
    CandidateDiscoveryError,
    PendingPresentation,
    PendingFlag,
    PendingSlotIntent,
    ProvisionalSlot,
    ReasonRef,
    RecommenderState,
    Slot,
    SystemClaim,
    TargetRoleDecision,
    UnresolvedSlotRefinement,
    all_locked,
    empty_slot,
    slot_fingerprint,
)

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
_REJECT_OPTION_RE = re.compile(r"^reject(?:\s+option)?\s+(\d+)$")
_REJECT_OPTION_NO_PROFILE_RE = re.compile(
    r"^reject(?:\s+option)?\s+(\d+)\s*,\s*no\s+(.+)$",
    re.IGNORECASE,
)
_REJECT_OPTION_BECAUSE_PROFILE_RE = re.compile(
    r"^reject(?:\s+option)?\s+(\d+)\s+because\s+(.+)$",
    re.IGNORECASE,
)
_GLOBAL_PROFILE_REJECT_RE = re.compile(
    r"^(?:no(?:\s+more)?\s+|reject\s+)(.+)$",
    re.IGNORECASE,
)
_PROFILE_ALIAS_TO_NEED: dict[str, str] = {
    "tr": "trick_room",
    "trick room": "trick_room",
    "trickroom": "trick_room",
    "tw": "tailwind",
    "tailwind": "tailwind",
    "screens": "screens",
    "screen": "screens",
    "healing": "healing_cleric",
    "cleric": "healing_cleric",
    "healing cleric": "healing_cleric",
}
_PREFERENCE_REVISION_REPLIES = frozenset(
    {
        "different focus",
        "change focus",
        "other focus",
        "switch focus",
        "change preference",
        "different preference",
        "pick a different focus",
    }
)


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
    "candidate_selection": frozenset(
        {"edit", "select_build_option", "compare", "revise_locked_slot"}
    ),
    "completion_preference": frozenset(
        {"edit", "select_build_option", "compare", "revise_locked_slot"}
    ),
    "core_resolution": frozenset(
        {"edit", "select_build_option", "compare", "revise_locked_slot"}
    ),
    "full_build_confirmation": frozenset({"lock", "revise_locked_slot"}),
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


def _try_deterministic_claim_correction(
    text: str,
    last_system_claim: SystemClaim | None,
) -> dict[str, Any] | None:
    if last_system_claim is None or not last_system_claim.get("verifiable"):
        return None
    from recommender.system_claims import (
        build_deterministic_claim_correction,
        negation_matches_claim,
    )

    if negation_matches_claim(text, last_system_claim):
        return build_deterministic_claim_correction(text, last_system_claim)
    return None


def _gap_fill(
    text: str,
    *,
    turn_intent_parser,
    gap_fill_context: dict[str, str] | None,
    had_pending: bool,
    pending_presentation: PendingPresentation | None = None,
    team_draft: list[Slot] | None = None,
    last_system_claim: SystemClaim | None = None,
) -> dict[str, Any]:
    from recommender.turn_intent import parse_turn_intent

    deterministic = _try_deterministic_claim_correction(text, last_system_claim)
    if deterministic is not None:
        result = deterministic
    else:
        ctx = gap_fill_context or {}
        result = parse_turn_intent(
            turn_intent_parser,
            user_text=text,
            pending_kind=ctx.get("pending_kind") or ("none" if not had_pending else ""),
            pending_context=ctx.get("pending_context") or "",
            roster_summary=ctx.get("roster_summary") or "",
            last_system_claim=ctx.get("last_system_claim") or "",
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
        elif kind == "core_resolution":
            labels = [
                str(option.get("label") or "")
                for option in pending.get("resolution_options") or ()
            ]
            pending_context = f"core resolution options: {', '.join(labels)}"
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
    from recommender.system_claims import serialize_last_system_claim

    return {
        "pending_kind": pending_kind,
        "pending_context": pending_context,
        "roster_summary": roster_summary,
        "last_system_claim": serialize_last_system_claim(state.get("last_system_claim")),
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


def _parse_reject_option_index(reply: str) -> int | None:
    match = _REJECT_OPTION_RE.match(reply)
    if not match:
        return None
    return int(match.group(1)) - 1


def _normalize_profile_alias_key(text: str) -> str:
    return " ".join(text.lower().split())


def _parse_need_category_alias(text: str) -> str | None:
    return _PROFILE_ALIAS_TO_NEED.get(_normalize_profile_alias_key(text))


def _rejection_payload_for_option(
    *,
    species: str,
    slot_index: int,
    reason: str,
    ban_need_categories: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "species": species,
        "slot_index": slot_index,
        "reason": reason,
    }
    if ban_need_categories:
        payload["ban_need_categories"] = ban_need_categories
    return {
        "turn_intent": "rejection",
        "turn_payload": payload,
    }


def _try_classify_candidate_rejection(
    text: str,
    reply: str,
    pending_presentation: PendingPresentation,
) -> dict[str, Any] | None:
    """Deterministic reject parse for candidate_selection. None = not handled."""
    options = pending_presentation.get("options") or []
    slot_index = pending_presentation["slot_index"]

    for pattern in (_REJECT_OPTION_NO_PROFILE_RE, _REJECT_OPTION_BECAUSE_PROFILE_RE):
        match = pattern.match(reply)
        if match is None:
            continue
        index = int(match.group(1)) - 1
        need = _parse_need_category_alias(match.group(2))
        if need is None or not (0 <= index < len(options)):
            return None
        return _rejection_payload_for_option(
            species=options[index]["species"],
            slot_index=slot_index,
            reason=text.strip(),
            ban_need_categories=[need],
        )

    reject_index = _parse_reject_option_index(reply)
    if reject_index is not None and 0 <= reject_index < len(options):
        return _rejection_payload_for_option(
            species=options[reject_index]["species"],
            slot_index=slot_index,
            reason=text.strip(),
        )

    if reply.startswith("reject "):
        rest = reply[len("reject ") :].strip()
        ban_need: list[str] | None = None
        species_part = rest
        for sep in (", no ", " because ", " no "):
            # ", no " / " because " / " no " — not " as "
            idx = rest.find(sep)
            if idx < 0:
                continue
            species_part = rest[:idx].strip()
            need = _parse_need_category_alias(rest[idx + len(sep) :])
            if need is None:
                return None
            ban_need = [need]
            break
        if species_part.isdigit() or species_part.startswith("option "):
            return None
        resolved = resolve_species_label(species_part, load_snapshot())
        if resolved is None:
            # Global profile: "reject trick room"
            need = _parse_need_category_alias(rest)
            if need is None:
                return None
            return _rejection_payload_for_option(
                species="",
                slot_index=slot_index,
                reason=text.strip(),
                ban_need_categories=[need],
            )
        candidate_id = to_id(resolved.name)
        matches = [
            opt
            for opt in options
            if to_id(opt["species"]) == candidate_id
        ]
        if len(matches) == 1:
            return _rejection_payload_for_option(
                species=matches[0]["species"],
                slot_index=slot_index,
                reason=text.strip(),
                ban_need_categories=ban_need,
            )
        if ban_need is None:
            # Species named but not in options — still lineage-exclude
            return _rejection_payload_for_option(
                species=resolved.name,
                slot_index=slot_index,
                reason=text.strip(),
            )
        return None

    global_match = _GLOBAL_PROFILE_REJECT_RE.match(reply)
    if global_match and not reply.startswith("reject "):
        # "no trick room" / "no more trick room" (reject … handled above)
        need = _parse_need_category_alias(global_match.group(1))
        if need is not None:
            return _rejection_payload_for_option(
                species="",
                slot_index=slot_index,
                reason=text.strip(),
                ban_need_categories=[need],
            )
    return None


def _classify_candidate_selection_reply(
    text: str,
    reply: str,
    pending_presentation: PendingPresentation,
    *,
    turn_intent_parser,
    gap_fill_context: dict[str, str] | None,
    team_draft: list[Slot] | None,
    last_system_claim: SystemClaim | None = None,
) -> dict[str, Any]:
    options = pending_presentation.get("options") or []
    signals = {
        signal
        for signal, matched in (
            ("affirm", reply in _AFFIRMATIVE_REPLIES),
            ("defer", reply in _DEFER_REPLIES),
            ("reject", reply in _REJECT_ALL_REPLIES),
        )
        if matched
    }

    if signals == {"defer"}:
        return {"turn_intent": "deferred", "pending_presentation": None}

    classified_reject = _try_classify_candidate_rejection(
        text, reply, pending_presentation
    )
    if classified_reject is not None:
        return classified_reject

    if reply in _PREFERENCE_REVISION_REPLIES:
        return {
            "turn_intent": "continue",
            "team_completion_preference": None,
            "pending_presentation": None,
            "force_completion_preference_prompt": True,
        }

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
            last_system_claim=last_system_claim,
        )

    return {
        "turn_intent": "slot_candidate_selected",
        "selected_option": options[index],
    }


def classify_pending(
    text: str,
    pending_presentation: PendingPresentation | None = None,
    *,
    bootstrap_intake_parser=None,
    turn_intent_parser=None,
    gap_fill_context: dict[str, str] | None = None,
    team_draft: list[Slot] | None = None,
    last_system_claim: SystemClaim | None = None,
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
            last_system_claim=last_system_claim,
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
            last_system_claim=last_system_claim,
        )
    if pending_presentation.get("kind") == "core_resolution":
        if version != 2:
            return {
                "turn_intent": "pending_response",
                "pending_presentation": None,
                "slot_commit_error": f"unsupported pending schema version: {version}",
            }
        options = pending_presentation.get("resolution_options") or ()
        ordinal = _ORDINAL_REPLIES.get(reply)
        selected = next(
            (
                option
                for option in options
                if reply == str(option.get("label") or "").casefold()
                or reply == str(option.get("id") or "").casefold()
            ),
            None,
        )
        if selected is None and ordinal is not None and ordinal < len(options):
            selected = options[ordinal]
        if selected is not None:
            if selected.get("id") == "keep_core":
                return {
                    "turn_intent": "continue",
                    "pending_presentation": None,
                }
            constructed = selected.get("option")
            if not constructed:
                return {"turn_intent": "pending_response"}
            return {
                "turn_intent": "slot_candidate_selected",
                "selected_option": constructed,
                "masked_slot_indices": tuple(selected.get("masked_slot_indices") or ()),
                "team_completion_preference": None,
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
            last_system_claim=last_system_claim,
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
                "turn_intent": "build_abandoned",
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
            last_system_claim=last_system_claim,
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

    if pending_presentation.get("kind") == "candidate_selection":
        return _classify_candidate_selection_reply(
            text,
            reply,
            pending_presentation,
            turn_intent_parser=turn_intent_parser,
            gap_fill_context=gap_fill_context,
            team_draft=team_draft,
            last_system_claim=last_system_claim,
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
            team_draft=team_draft,
            last_system_claim=last_system_claim,
        )

    return {
        "turn_intent": "slot_candidate_selected",
        "selected_option": options[index],
    }


