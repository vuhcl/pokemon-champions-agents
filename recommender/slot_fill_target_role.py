"""Open-slot target-role derivation (ADR-023)."""

from __future__ import annotations

from dataclasses import replace
from typing import get_args

from recommender.anchor_roles import (
    AnchorRoleDecision,
    classify_anchor_role,
    resolve_anchor_build,
)
from recommender.ids import to_id
from recommender.role_compendium_read import ReverseCompendiumEvidence
from recommender.slot_fill import AnchoredSupportNeed, SlotFillContext
from recommender.state import (
    TargetRoleDecision,
    TargetRoleId,
    TargetRoleResult,
    UnresolvedTargetRoleDecision,
)
from recommender.support_needs import NeedCategory, SupportNeed, field_labels_from_trigger

_NEED_TARGET_ROLES: dict[NeedCategory, tuple[TargetRoleId, str]] = {
    "trick_room": ("trick_room_setter", "move:trickroom"),
    "tailwind": ("tailwind_setter", "move:tailwind"),
    "redirection": ("redirection", "move:followme"),
    "screens": ("screens_support", "move:lightscreen"),
}
_CONDITION_SETTER_TARGET_ROLES: dict[str, tuple[TargetRoleId, str]] = {
    "rain": ("rain_setter", "role:rain_setter"),
    "sun": ("sun_setter", "role:sun_setter"),
    "sand": ("sand_setter", "role:sand_setter"),
    "snow": ("snow_setter", "role:snow_setter"),
}
REVIEWED_STRATEGIC_TARGET_ROLES: dict[str, TargetRoleId] = {
    "rainsetter": "rain_setter",
    "sunsetter": "sun_setter",
    "sandsetter": "sand_setter",
    "snowsetter": "snow_setter",
    "redirection": "redirection",
    "trickroomsetter": "trick_room_setter",
    "tailwindsetter": "tailwind_setter",
    "swordsdanceattacker": "swords_dance_attacker",
    "nastyplotattacker": "nasty_plot_attacker",
}


def target_role_from_strategic_evidence(
    role_id: str,
    *,
    anchor_role: AnchorRoleDecision | None = None,
    compendium: ReverseCompendiumEvidence | None = None,
) -> TargetRoleDecision | None:
    """Map reviewed exact strategic evidence to an open-slot role intent."""
    normalized = to_id(role_id)
    mapped = REVIEWED_STRATEGIC_TARGET_ROLES.get(normalized)
    if mapped is None:
        return None

    evidence: list[str] = []
    provenance: list[str] = []
    for mechanism in anchor_role.mechanisms if anchor_role is not None else ():
        if (
            mechanism.present
            and mechanism.importance in ("needed", "wanted")
            and to_id(mechanism.role_id or "") == normalized
        ):
            evidence.append(f"mechanism:{to_id(mechanism.mechanic)}")
            provenance.append(f"anchor_role:{mechanism.source}")

    for row in compendium.exact if compendium is not None else ():
        if row.tier is not None and to_id(row.role_id) == normalized:
            detail = f"compendium:{row.tier}:{row.source_file}"
            if row.mechanism:
                detail += f":{to_id(row.mechanism)}"
            evidence.append(detail)
            provenance.append(f"role_compendium:{row.source_file}")

    if not evidence:
        return None
    return TargetRoleDecision(
        role_id=mapped,
        source="other",
        evidence=tuple(dict.fromkeys(evidence)),
        needed_constraints=(f"role:{mapped}",),
        confidence="high",
        provenance=tuple(dict.fromkeys(provenance)),
        producer_name="target_role_from_strategic_evidence",
    )


def target_role_from_needs(
    needs: tuple[SupportNeed, ...] | list[SupportNeed],
) -> TargetRoleResult | None:
    """Resolve actionable need roles while preserving speed-control ambiguity."""
    relevant: list[tuple[SupportNeed, TargetRoleId, str]] = []
    for need in needs:
        mapped = _NEED_TARGET_ROLES.get(need.category)
        if mapped is not None:
            role_id, constraint = mapped
            relevant.append((need, role_id, constraint))
            continue
        if need.category != "condition_setter" or not need.trigger:
            continue
        for label in field_labels_from_trigger(need.trigger):
            weather_mapped = _CONDITION_SETTER_TARGET_ROLES.get(label)
            if weather_mapped is None:
                continue
            role_id, constraint = weather_mapped
            relevant.append((need, role_id, constraint))
    if not relevant:
        return None

    # Prefer non-TR mapped roles when multi-need unless the peer is also
    # speed control (TR+TW stays unresolved ambiguity).
    _SPEED_ROLES = frozenset({"trick_room_setter", "tailwind_setter"})
    non_tr = [row for row in relevant if row[1] != "trick_room_setter"]
    if (
        non_tr
        and any(role_id == "trick_room_setter" for _, role_id, _ in relevant)
        and any(role_id not in _SPEED_ROLES for _, role_id, _ in non_tr)
    ):
        relevant = non_tr

    role_ids = tuple(dict.fromkeys(role_id for _, role_id, _ in relevant))
    needed = tuple(
        constraint
        for need, _, constraint in relevant
        if need.stance != "want"
    )
    wanted = tuple(
        constraint
        for need, _, constraint in relevant
        if need.stance == "want"
    )
    evidence = tuple(
        f"{need.category}:{need.trigger}" if need.trigger else need.category
        for need, _, _ in relevant
    )
    provenance = tuple(f"support_need:{need.category}" for need, _, _ in relevant)
    if len(role_ids) > 1:
        return UnresolvedTargetRoleDecision(
            reason="ambiguous_speed_control",
            ambiguity=role_ids,
            source="support_need",
            evidence=evidence,
            needed_constraints=needed,
            wanted_constraints=wanted,
            provenance=provenance,
        )
    return TargetRoleDecision(
        role_id=role_ids[0],
        source="support_need",
        evidence=evidence,
        needed_constraints=needed,
        wanted_constraints=wanted,
        confidence="high",
        provenance=provenance,
    )


def target_role_from_anchored_needs(
    anchored_needs: tuple[AnchoredSupportNeed, ...],
) -> TargetRoleResult | None:
    decision = target_role_from_needs([row.need for row in anchored_needs])
    if decision is None:
        return None
    origins = tuple(
        f"anchor:{row.anchor_id}:slot:{row.anchor_slot_index}"
        for row in anchored_needs
    )
    if isinstance(decision, UnresolvedTargetRoleDecision):
        return replace(
            decision,
            reason="incompatible_support_roles",
            provenance=tuple(dict.fromkeys((*decision.provenance, *origins))),
        )
    return replace(
        decision,
        provenance=tuple(dict.fromkeys((*decision.provenance, *origins))),
    )


def _candidate_target_role(
    ctx: SlotFillContext, matching_needs: tuple[SupportNeed, ...]
) -> TargetRoleResult | None:
    matched = target_role_from_needs(matching_needs)
    decision = ctx.target_role_decision
    if decision is None:
        return matched
    if decision.source != "support_need":
        return decision
    if isinstance(decision, UnresolvedTargetRoleDecision):
        return matched
    return (
        decision
        if isinstance(matched, TargetRoleDecision)
        and matched.role_id == decision.role_id
        else None
    )


def _kit_fallback_target_role(species: str) -> TargetRoleDecision | None:
    """Identity kit/role promotion when threat/support evidence yields no TargetRoleDecision.

    Without this, degraded threat-only rows are presented then dead-end on refine
    (pending cleared, UnresolvedSlotRefinement, no confirmation prompt).
    """

    vocabulary = frozenset(get_args(TargetRoleId))
    build = resolve_anchor_build(species, regulation="champions-reg-mb")
    anchor = classify_anchor_role(build)
    for raw in (anchor.kit_role, anchor.role_id):
        if not raw or raw not in vocabulary:
            continue
        return TargetRoleDecision(
            role_id=raw,  # type: ignore[arg-type]
            source="other",
            evidence=(f"kit_role:{raw}",),
            needed_constraints=(f"role:{raw}",),
            confidence="medium",
            provenance=("anchor_role:kit_role",),
            producer_name="slot_fill_kit_role_policy",
        )
    return None


def _resolved_candidate_target_role(
    ctx: SlotFillContext, species: str, matching_needs: tuple[SupportNeed, ...]
) -> TargetRoleResult | None:
    decision = _candidate_target_role(ctx, matching_needs)
    if isinstance(decision, TargetRoleDecision):
        return decision
    if isinstance(decision, UnresolvedTargetRoleDecision):
        return decision
    return _kit_fallback_target_role(species)


def derive_target_role(ctx: SlotFillContext) -> TargetRoleResult | None:
    """Populate the context's open-slot decision from selected support evidence."""
    if ctx.target_role_decision is None:
        needs = [ctx.chosen_need] if ctx.chosen_need is not None else ctx.support_needs or []
        ctx.target_role_decision = target_role_from_needs(needs)
    return ctx.target_role_decision
