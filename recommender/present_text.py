"""Plain-text rendering of recommender turn state for the CLI."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Mapping

from recommender.state import (
    CandidateDiscoveryError,
    CandidateEvidence,
    ProvisionalSlot,
    Slot,
    SPOFFinding,
    TargetRoleDecision,
    TeamReviewResult,
    ThreatCandidate,
    ThreatCoverageResult,
    UnresolvedTargetRoleDecision,
    all_locked,
)
from recommender.team_candidates import _pick_best_evidence_item

NO_PENDING_MESSAGE = (
    "No pending question to answer; start :new or wait for a prompt."
)
NO_TEAM_REVIEW_MESSAGE = (
    "Team review: (not cached — ask for a team review or continue on a complete team)"
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
        "Reply with a species name, 1/2/3, 'yes' for the default, "
        "'reject N' to skip an option, 'different focus' to change preference, "
        "or 'defer'."
    ),
    "completion_preference": (
        "Reply with a preference name, 1/2/3, or 'defer'."
    ),
    "core_resolution": (
        "Reply with a resolution name, 1/2/3, or 'defer'."
    ),
    "full_build_confirmation": (
        "Reply 'yes' to accept, pick option ids (compose with +), "
        "'compare A B', free-text edit, or 'defer'."
    ),
    "confirm_abandon_build": (
        "Reply 'yes' to discard and continue, or 'no' to keep this build."
    ),
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


def _best_evidence_row(
    evidence_rows: tuple[CandidateEvidence | Mapping[str, Any], ...],
) -> CandidateEvidence | Mapping[str, Any]:
    """Pick the highest-quality evidence item via _pick_best_evidence_item.

    Same rule as Category B/C ranking (_rank_by_need_evidence), including
    the commitment_pct override when a lower-confidence compendium_backed
    row would otherwise win on basis alone. A candidate's evidence tuple is
    merged across every support need it happens to satisfy — evidence[0]
    is arrival order, not quality — so display must share ranking's pick.
    """
    if not evidence_rows:
        raise ValueError("_best_evidence_row requires a non-empty evidence tuple")
    normalized: list[CandidateEvidence] = []
    for row in evidence_rows:
        if isinstance(row, CandidateEvidence):
            normalized.append(row)
            continue
        normalized.append(
            CandidateEvidence(
                basis=str(row.get("basis") or "unknown"),  # type: ignore[arg-type]
                confidence=str(row.get("confidence") or "unknown"),  # type: ignore[arg-type]
                producer_name=str(row.get("producer_name") or "unknown"),
                evidence=tuple(row.get("evidence") or ()),
                branch=row.get("branch"),  # type: ignore[arg-type]
            )
        )
    picked = _pick_best_evidence_item(normalized)
    assert picked is not None
    return picked


def _format_build_fields(
    *,
    ability: object,
    item: object,
    nature: object,
    moves: Sequence[object],
    spread: object,
) -> list[str]:
    return [
        f"  Ability: {ability}",
        f"  Item: {item}",
        f"  Nature: {nature}",
        f"  Moves: {', '.join(str(m) for m in moves)}",
        f"  Spread: {spread}",
    ]


def _locked_slot_build_fields(slot: Slot) -> tuple[str, str | None, str | None, str | None, str | None, list[str], dict[str, int]]:
    return (
        getattr(slot.species, "value", None) or "?",
        getattr(slot.role, "value", None),
        getattr(slot.ability, "value", None),
        getattr(slot.item, "value", None),
        getattr(slot.nature, "value", None),
        list(getattr(slot.moveset, "value", None) or ()),
        dict(getattr(slot.spread, "value", None) or {}),
    )


def format_builds(state: Mapping[str, Any]) -> str:
    """Full locked-slot builds from team_draft."""

    draft = state.get("team_draft") or []
    blocks: list[str] = []
    for index, slot in enumerate(draft):
        if not all_locked(slot):
            continue
        species, role, ability, item, nature, moves, spread = _locked_slot_build_fields(slot)
        header = f"{index + 1}. {species}"
        if role:
            header = f"{header} ({role})"
        blocks.append(f"{header}:")
        blocks.extend(
            _format_build_fields(
                ability=ability,
                item=item,
                nature=nature,
                moves=moves,
                spread=spread,
            )
        )
    if not blocks:
        return "Builds: (no locked members)"
    return "Builds:\n" + "\n".join(blocks)


def _slot_label(team_draft: Sequence[Slot], index: int) -> str:
    if 0 <= index < len(team_draft):
        species = getattr(team_draft[index].species, "value", None)
        if species:
            return f"{index + 1}. {species}"
    return f"slot {index + 1}"


def _threat_species(threat: object) -> str:
    if isinstance(threat, Mapping):
        return str(threat.get("species") or "?")
    spec = getattr(threat, "spec", None)
    if isinstance(spec, Mapping) and spec.get("species"):
        return str(spec["species"])
    form = getattr(threat, "form", None)
    if form:
        return str(form)
    ladder = getattr(threat, "ladder_species", None)
    if ladder:
        return str(ladder)
    return "?"


def _coverage_row(row: ThreatCoverageResult | Mapping[str, Any]) -> tuple[object, object, list[int], bool]:
    if isinstance(row, ThreatCoverageResult):
        return row.threat, row.best_outcome, list(row.covering_slot_indices), row.flagged
    threat = row.get("threat")
    best = row.get("best_outcome")
    covering = list(row.get("covering_slot_indices") or ())
    flagged = bool(row.get("flagged"))
    return threat, best, covering, flagged


def _matchup_bits(outcome: object) -> tuple[str | None, str | None]:
    if outcome is None:
        return None, None
    if isinstance(outcome, Mapping):
        return outcome.get("outcome"), outcome.get("severity")
    return getattr(outcome, "outcome", None), getattr(outcome, "severity", None)


def format_team_review(
    review: TeamReviewResult | Mapping[str, Any],
    *,
    team_draft: Sequence[Slot] = (),
    include_error: bool = True,
) -> str:
    """Render cached team review findings (threats, coverage gaps, SPOFs)."""

    if isinstance(review, TeamReviewResult):
        status = review.status
        error = review.error
        threats = review.threats
        coverage = review.coverage
        spofs = review.spofs
        composition_gaps = review.composition_gaps
    else:
        status = review.get("status") or "available"
        error = review.get("error")
        threats = review.get("threats") or ()
        coverage = review.get("coverage") or ()
        spofs = review.get("spofs") or ()
        composition_gaps = review.get("composition_gaps") or ()

    lines: list[str] = ["Team review:"]
    if include_error and status == "unavailable" and error is not None:
        lines.append(_format_discovery_error(error))

    lines.append("Threats:")
    if threats:
        for threat in threats:
            if isinstance(threat, ThreatCandidate):
                label = threat.form or threat.ladder_species
                rank = threat.usage_rank
                source = threat.build_source
            elif isinstance(threat, Mapping):
                label = str(threat.get("form") or threat.get("ladder_species") or "?")
                rank = threat.get("usage_rank")
                source = threat.get("build_source")
            else:
                label = _threat_species(threat)
                rank = getattr(threat, "usage_rank", None)
                source = getattr(threat, "build_source", None)
            bits = [label]
            if rank is not None:
                bits.append(f"rank {rank}")
            if source:
                bits.append(str(source))
            lines.append(f"  - {' · '.join(bits)}")
    else:
        lines.append("  (none)")

    gaps: list[str] = []
    conditional: list[str] = []
    covered: list[str] = []
    for row in coverage:
        threat, best, covering, flagged = _coverage_row(row)
        species = _threat_species(threat)
        outcome, severity = _matchup_bits(best)
        outcome_text = outcome or "unknown"
        if severity:
            outcome_text = f"{outcome_text} ({severity})"
        if not covering:
            gaps.append(f"  - {species}: {outcome_text}")
        elif flagged:
            conditional.append(f"  - {species}: {outcome_text}")
        else:
            cover_labels = ", ".join(_slot_label(team_draft, i) for i in covering)
            covered.append(f"  - {species}: covered by {cover_labels} ({outcome_text})")

    lines.append("Coverage gaps:")
    lines.extend(gaps or ["  (none)"])
    lines.append("Conditional coverage:")
    lines.extend(conditional or ["  (none)"])
    if covered:
        lines.append("Covered:")
        lines.extend(covered)

    lines.append("SPOFs:")
    if spofs:
        for finding in spofs:
            if isinstance(finding, SPOFFinding):
                slot_index = finding.slot_index
                lost = finding.threats_lost
                severities = finding.threat_severity
            elif isinstance(finding, Mapping):
                slot_index = int(finding.get("slot_index", -1))
                lost = finding.get("threats_lost") or ()
                severities = finding.get("threat_severity") or {}
            else:
                slot_index = getattr(finding, "slot_index", -1)
                lost = getattr(finding, "threats_lost", ()) or ()
                severities = getattr(finding, "threat_severity", {}) or {}
            lost_names = ", ".join(_threat_species(t) for t in lost) or "?"
            sev_bits = ", ".join(f"{k}={v}" for k, v in severities.items())
            sev_suffix = f" [{sev_bits}]" if sev_bits else ""
            lines.append(
                f"  - {_slot_label(team_draft, slot_index)} loses {lost_names}{sev_suffix}"
            )
    else:
        lines.append("  (none)")

    lines.append("Composition gaps:")
    if composition_gaps:
        lines.extend(f"  - {gap}" for gap in composition_gaps)
    else:
        lines.append("  (none)")

    return "\n".join(lines)


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


_REJECT_HINT = (
    "reject N drops only that species. To also skip Trick Room–shaped picks: "
    "reject N, no TR or no more trick room."
)


def _should_show_species_primary(option: Mapping[str, Any]) -> bool:
    species_primary = option.get("species_primary_role")
    if not species_primary or species_primary == "unresolved":
        return False
    trd = option.get("target_role_decision")
    if isinstance(trd, TargetRoleDecision):
        return species_primary != trd.role_id
    if isinstance(trd, UnresolvedTargetRoleDecision):
        return species_primary not in trd.ambiguity
    return False


def _format_candidate_selection(pending: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    prompt = pending.get("prompt_text")
    if prompt:
        lines.append(str(prompt))
    options = pending.get("options") or []
    for i, option in enumerate(options, start=1):
        species = option.get("species") or "?"
        track = option.get("track")
        prefix = f"{i}. {track}: {species}" if track else f"{i}. {species}"
        bits = [prefix]
        if option.get("direction_label"):
            bits.append(str(option["direction_label"]))
        need_cats = option.get("need_categories") or ()
        role_bit = _format_option_role_bit(option.get("target_role_decision"))
        # Multi-need with TR: slash needs already show TR — omit lone TR role bit.
        if (
            role_bit == "trick_room_setter"
            and "trick_room" in need_cats
            and len(need_cats) > 1
        ):
            role_bit = None
        if role_bit:
            bits.append(role_bit)
        if need_cats:
            bits.append(" / ".join(str(c) for c in need_cats))
        if _should_show_species_primary(option):
            bits.append(f"primary: {option['species_primary_role']}")
        if option.get("primary_function"):
            bits.append(str(option["primary_function"]))
        evidence_rows = option.get("evidence") or ()
        if evidence_rows:
            bits.append(format_evidence_summary(_best_evidence_row(evidence_rows)))
        else:
            bits.append("no evidence")
        if option.get("secondary_trick_room"):
            bits.append(
                "base build includes Trick Room — say if you want it replaced"
            )
        lines.append(" — ".join(bits))
    if options:
        lines.append(_REJECT_HINT)
    return lines


def _stat_label(stat: str) -> str:
    return "HP" if stat == "hp" else stat.capitalize()


def _format_spread_reallocation_question(pending: Mapping[str, Any]) -> list[str]:
    """Built entirely from structured pending_presentation data (attempted
    spread, diff, excluded stats), not a stashed message string -- matches
    this module's convention for full_build_confirmation/candidate_selection
    rather than the ad-hoc message passed for confirm_abandon_build.
    """
    spread = pending.get("reallocation_attempted_spread") or {}
    diff = pending.get("reallocation_diff") or 0
    excluded = set(pending.get("reallocation_excluded_stats") or ())
    direction = "over" if diff > 0 else "under"
    verb = "reduce" if diff > 0 else "add to"
    current = ", ".join(
        f"{_stat_label(stat)} {spread.get(stat, 0)}"
        for stat in ("hp", "atk", "def", "spa", "spd", "spe")
        if stat not in excluded
    )
    lines = []
    reason = pending.get("reallocation_rejection_reason")
    if reason:
        lines.append(str(reason))
    lines.append(
        f"That puts you {abs(diff)} point{'s' if abs(diff) != 1 else ''} "
        f"{direction} budget. Which stat should I {verb}? Current: {current}."
    )
    lines.append("Reply with a stat name, or 'defer' to keep the current spread unchanged.")
    return lines


def _format_spread_target_question(pending: Mapping[str, Any]) -> list[str]:
    """Fires when the deterministic single-stat text extraction couldn't
    confidently resolve a spread edit either (genuinely multi-stat text,
    or the model's guess touched multiple stats with no single clear
    intent readable from the request). Asks for both stat and value in
    one reply, since -- unlike spread_reallocation_question -- neither is
    reliably known yet."""
    diffs = pending.get("target_question_diffs") or ()
    reason = pending.get("target_question_rejection_reason")
    lines = []
    if reason:
        lines.append(str(reason))
    elif diffs:
        lines.append(
            f"That implies changing {len(diffs)} stats "
            f"({', '.join(_stat_label(s) for s in diffs)}) at once, and I'm not "
            "confident in that computation."
        )
    lines.append(
        "Which ONE stat did you want to change, and to what value? "
        "(e.g. 'Spe 5' or 'Spe to 5')"
    )
    lines.append("Reply with a stat and a value, or 'defer' to keep the current spread unchanged.")
    return lines


def _format_item_moveset_conflict_question(pending: Mapping[str, Any]) -> list[str]:
    """Structured-data-driven, same convention as every other pending
    kind in this module -- the item/move/alternatives are stored fields,
    not a stashed message string."""
    item = pending.get("conflict_attempted_item") or "that item"
    previous = pending.get("conflict_previous_item") or "the previous item"
    moves = pending.get("conflict_moves") or ()
    alternatives = pending.get("conflict_move_alternatives") or ()
    reason = pending.get("conflict_rejection_reason")

    lines: list[str] = []
    move_list = ", ".join(moves) if moves else "a non-damaging move"
    if reason:
        lines.append(str(reason))
    else:
        lines.append(
            f"{item} locks you into repeating one move, which doesn't work with "
            f"{move_list} still in the set."
        )
    if alternatives:
        lines.append("Pick a damaging move to replace it:")
        for i, move in enumerate(alternatives, start=1):
            lines.append(f"{i}. {move}")
        lines.append(
            f"Reply with a move name or number, 'keep it' to leave {move_list} "
            f"as-is, or 'defer' to revert to {previous}."
        )
    else:
        lines.append(
            f"Reply 'keep it' to leave it as-is, or 'defer' to revert to {previous}."
        )
    return lines


def _format_full_build(state: Mapping[str, Any]) -> list[str]:
    provisional = state.get("provisional_slot")
    pending = state.get("pending_presentation") or {}
    lines: list[str] = []
    analysis = state.get("compare_analysis")
    if analysis:
        lines.append(str(analysis))
    if provisional is None:
        lines.append("Accept this build? (yes / defer)")
        return lines
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
    lines.append(f"Proposed build for {species} ({role}):")
    lines.extend(
        _format_build_fields(
            ability=ability,
            item=item,
            nature=nature,
            moves=moves,
            spread=spread,
        )
    )
    for flag in pending.get("review_flags") or ():
        lines.append(f"Note: {flag.get('claim')}")
    defaults = set(pending.get("default_option_ids") or ())
    for group in pending.get("build_option_groups") or ():
        lines.append(str(group.get("prompt") or f"Options ({group.get('axis')}):"))
        for opt in group.get("options") or ():
            oid = opt.get("option_id")
            marker = " (default)" if oid in defaults else ""
            tradeoff = opt.get("tradeoff") or ""
            diff = opt.get("diff_summary") or ""
            lines.append(f"  {oid}: {opt.get('label')}{marker} — {diff}; {tradeoff}")
            for note in opt.get("mechanical_notes") or ():
                lines.append(f"    mech: {note}")
            for note in opt.get("team_notes") or ():
                lines.append(f"    team: {note}")
    lines.append("Accept this build? (yes / defer / option id / free-text)")
    return lines


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

    correction = state.get("correction_response")
    if correction:
        blocks.append(str(correction))

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
        elif kind == "core_resolution":
            blocks.append("This candidate conflicts with the locked core:")
            for i, option in enumerate(pending.get("resolution_options") or (), start=1):
                blocks.append(f"{i}. {option.get('label')}")
        elif kind == "full_build_confirmation":
            blocks.extend(_format_full_build(state))
        elif kind == "confirm_abandon_build":
            provisional = state.get("provisional_slot")
            species = None
            if provisional is not None:
                species = getattr(provisional, "species", None)
                if not species and isinstance(provisional, Mapping):
                    species = provisional.get("species")
            if species:
                blocks.append(f"Pending build: {species}.")
        elif kind == "spread_reallocation_question":
            blocks.extend(_format_spread_reallocation_question(pending))
        elif kind == "spread_target_question":
            blocks.extend(_format_spread_target_question(pending))
        elif kind == "item_moveset_conflict_question":
            blocks.extend(_format_item_moveset_conflict_question(pending))
        else:
            blocks.append(f"(pending kind: {kind})")

        footer = _FOOTERS.get(str(kind or ""))
        if footer:
            blocks.append(footer)
    else:
        blocks.append(format_roster(state))
        review = state.get("last_team_review")
        if review is not None:
            blocks.append(
                format_team_review(
                    review,
                    team_draft=state.get("team_draft") or [],
                    include_error=discovery_err is None,
                )
            )

    return "\n".join(blocks)
