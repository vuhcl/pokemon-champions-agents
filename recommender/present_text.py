"""Plain-text rendering of recommender turn state for the CLI."""

from __future__ import annotations

from typing import Any, Mapping

from recommender.state import (
    CandidateDiscoveryError,
    CandidateEvidence,
    ProvisionalSlot,
    all_locked,
)

NO_PENDING_MESSAGE = (
    "No pending question to answer; start :new or wait for a prompt."
)
UNMATCHED_REPLY_PREFIX = "Didn't catch that."
BOOTSTRAP_PARSER_NOT_CONFIGURED = "bootstrap intake parser is not configured"
BOOTSTRAP_PARSER_FIX_HINT = (
    "No LLM provider is configured; bootstrap free-form replies require one. "
    "Fix: --provider ollama with BOOTSTRAP_OLLAMA_MODEL set, or --provider anthropic "
    "with BOOTSTRAP_ANTHROPIC_MODEL and ANTHROPIC_API_KEY."
)

_DEGRADATION_TOKENS = frozenset({"calc_unavailable", "static_type_estimate"})
_CALC_DISCOVERY_KINDS = frozenset({"calc_unavailable", "calc_incomplete"})

_FOOTERS: dict[str, str] = {
    "bootstrap_intake": (
        "Reply with a direction, anchor, available pool, or 'you pick'."
    ),
    "candidate_selection": (
        "Reply with a species name, 1/2/3, 'yes' for the default, or 'defer'."
    ),
    "completion_preference": (
        "Reply with a preference name, 1/2/3, or 'defer'."
    ),
    "full_build_confirmation": "Reply 'yes' to accept, or 'defer' to skip.",
}


def format_evidence_summary(evidence: CandidateEvidence | Mapping[str, Any]) -> str:
    """One-line: '{basis}, {confidence} confidence' (+ degradation tokens if present)."""

    if isinstance(evidence, CandidateEvidence):
        basis = evidence.basis
        confidence = evidence.confidence
        tokens = evidence.evidence
    else:
        basis = str(evidence.get("basis") or "unknown")
        confidence = str(evidence.get("confidence") or "unknown")
        tokens = tuple(evidence.get("evidence") or ())
    line = f"{basis}, {confidence} confidence"
    flagged = [t for t in tokens if t in _DEGRADATION_TOKENS]
    if flagged:
        line = f"{line} ({', '.join(flagged)})"
    return line


def format_roster(state: Mapping[str, Any]) -> str:
    """Locked members from team_draft (species + role if present)."""

    draft = state.get("team_draft") or []
    lines: list[str] = []
    for index, slot in enumerate(draft):
        if not all_locked(slot):
            continue
        species = getattr(slot.species, "value", None) or "?"
        role = getattr(slot.role, "value", None)
        label = f"{index + 1}. {species}"
        if role:
            label = f"{label} ({role})"
        lines.append(label)
    if not lines:
        return "Team: (no locked members)"
    return "Team:\n" + "\n".join(lines)


def format_no_pending(state: Mapping[str, Any]) -> str:
    """Idle pending-None vs fail-closed discovery: do not say wait for a prompt."""

    error = state.get("candidate_discovery_error")
    if error is None:
        return NO_PENDING_MESSAGE
    if isinstance(error, CandidateDiscoveryError):
        kind = error.kind
    else:
        kind = error.get("kind")
    hint = (
        "check the calc service, or use :new to start over."
        if kind in _CALC_DISCOVERY_KINDS
        else "use :new to start over."
    )
    return (
        f"Discovery stopped due to a {kind} error and hasn't produced a new question. "
        f"This won't resolve on its own; {hint}"
    )


def _format_discovery_error(error: CandidateDiscoveryError | Mapping[str, Any]) -> str:
    if isinstance(error, CandidateDiscoveryError):
        kind = error.kind
        message = error.message
        retryable = error.retryable
        stage = error.stage
    else:
        kind = error.get("kind")
        message = error.get("message")
        retryable = error.get("retryable")
        stage = error.get("stage")
    return (
        f"Discovery error [{kind}] at {stage}: {message} "
        f"(retryable={retryable})"
    )


def _format_option_role_bit(role: object) -> str | None:
    """Single-role id, or ambiguity joined with 'or' + (unresolved)."""
    if role is None:
        return None
    role_id = getattr(role, "role_id", None)
    if role_id is None and isinstance(role, Mapping):
        role_id = role.get("role_id")
    if role_id:
        return str(role_id)
    ambiguity = getattr(role, "ambiguity", None)
    if ambiguity is None and isinstance(role, Mapping):
        ambiguity = role.get("ambiguity")
    if ambiguity:
        return f"{' or '.join(str(r) for r in ambiguity)} (unresolved)"
    return None


def _format_candidate_selection(pending: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    prompt = pending.get("prompt_text")
    if prompt:
        lines.append(str(prompt))
    options = pending.get("options") or []
    for i, option in enumerate(options, start=1):
        species = option.get("species") or "?"
        bits = [f"{i}. {species}"]
        if option.get("direction_label"):
            bits.append(str(option["direction_label"]))
        role_bit = _format_option_role_bit(option.get("target_role_decision"))
        if role_bit:
            bits.append(role_bit)
        if option.get("primary_function"):
            bits.append(str(option["primary_function"]))
        evidence_rows = option.get("evidence") or ()
        if evidence_rows:
            bits.append(format_evidence_summary(evidence_rows[0]))
        else:
            bits.append("no evidence")
        lines.append(" — ".join(bits))
    return lines


def _format_full_build(state: Mapping[str, Any]) -> list[str]:
    provisional = state.get("provisional_slot")
    if provisional is None:
        return ["Accept this build? (yes / defer)"]
    if isinstance(provisional, ProvisionalSlot):
        species = provisional.species
        role = provisional.role
        ability = provisional.ability
        item = provisional.item
        nature = provisional.nature
        moves = provisional.moves
        spread = provisional.spread_dict()
    else:
        species = provisional.get("species")
        decision = provisional.get("target_role_decision") or {}
        role = getattr(decision, "role_id", None) or (
            decision.get("role_id") if isinstance(decision, Mapping) else None
        )
        ability = provisional.get("ability")
        item = provisional.get("item")
        nature = provisional.get("nature")
        moves = provisional.get("moves") or ()
        spread = dict(provisional.get("spread") or ())
    return [
        f"Proposed build for {species} ({role}):",
        f"  Ability: {ability}",
        f"  Item: {item}",
        f"  Nature: {nature}",
        f"  Moves: {', '.join(str(m) for m in moves)}",
        f"  Spread: {spread}",
        *(
            f"Note: {flag.get('claim')}"
            for flag in (state.get("pending_presentation") or {}).get("review_flags")
            or ()
        ),
        "Accept this build? (yes / defer)",
    ]


def format_turn(state: Mapping[str, Any], *, unmatched: bool = False) -> str:
    """MECE plain-text turn for the terminal."""

    blocks: list[str] = []
    bootstrap_err = state.get("bootstrap_intake_error")
    no_parser = bootstrap_err == BOOTSTRAP_PARSER_NOT_CONFIGURED
    if unmatched and not no_parser:
        payload = state.get("turn_payload")
        custom = None
        if isinstance(payload, Mapping):
            raw = payload.get("message")
            if isinstance(raw, str) and raw.strip():
                custom = raw.strip()
        blocks.append(custom or UNMATCHED_REPLY_PREFIX)

    if no_parser:
        blocks.append(BOOTSTRAP_PARSER_FIX_HINT)
    elif bootstrap_err:
        blocks.append(f"Bootstrap intake error: {bootstrap_err}")

    slot_err = state.get("slot_commit_error")
    if slot_err:
        blocks.append(f"Slot commit error: {slot_err}")

    discovery_err = state.get("candidate_discovery_error")
    if discovery_err is not None:
        blocks.append(_format_discovery_error(discovery_err))

    pending = state.get("pending_presentation")
    if pending:
        notices = pending.get("notices") or ()
        for notice in notices:
            blocks.append(str(notice))

        kind = pending.get("kind")
        if kind == "bootstrap_intake":
            prompt = pending.get("prompt_text") or ""
            if prompt:
                blocks.append(str(prompt))
        elif kind == "candidate_selection":
            blocks.extend(_format_candidate_selection(pending))
        elif kind == "completion_preference":
            blocks.append("Prefer next slot orientation:")
            for i, pref in enumerate(pending.get("preference_options") or (), start=1):
                blocks.append(f"{i}. {pref}")
        elif kind == "full_build_confirmation":
            blocks.extend(_format_full_build(state))
        else:
            blocks.append(f"(pending kind: {kind})")

        footer = _FOOTERS.get(str(kind or ""))
        if footer:
            blocks.append(footer)
    else:
        blocks.append(format_roster(state))
        review = state.get("last_team_review")
        if review is not None:
            status = getattr(review, "status", None) or (
                review.get("status") if isinstance(review, Mapping) else None
            )
            if status:
                blocks.append(f"Team review status: {status}")

    return "\n".join(blocks)
