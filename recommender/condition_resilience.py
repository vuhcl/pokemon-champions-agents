"""Team-wide condition essentiality, provider cardinality, and gap needs."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from recommender.anchor_roles import MechanismEvidence
from recommender.condition_types import (
    MIN_WANTED_DEPENDENTS_FOR_ESSENTIAL,
    TRACKED_CONDITIONS,
    ConditionClass,
    ConditionDependentMember,
    ConditionGap,
    ConditionProviderMember,
    ConditionResilienceReport,
    ConditionResilienceRow,
)
from recommender.slot_fill import AnchoredSupportNeed, LockedAnchorContext
from recommender.support_needs import SupportNeed, field_labels_from_trigger

_SETTER_ROLE_FOR_CONDITION = {
    "Rain": "rain_setter",
    "Sun": "sun_setter",
    "Sand": "sand_setter",
    "Snow": "snow_setter",
    "Trick Room": "trick_room_setter",
    "Tailwind": "tailwind_setter",
}
_WEATHER_LABEL = {
    "Rain": "rain",
    "Sun": "sun",
    "Sand": "sand",
    "Snow": "snow",
}

__all__ = [
    "MIN_WANTED_DEPENDENTS_FOR_ESSENTIAL",
    "TRACKED_CONDITIONS",
    "ConditionClass",
    "ConditionDependentMember",
    "ConditionGap",
    "ConditionProviderMember",
    "ConditionResilienceReport",
    "ConditionResilienceRow",
    "assess_condition_resilience",
    "gap_support_needs",
    "mechanism_condition",
]


def mechanism_condition(m: MechanismEvidence) -> str | None:
    """Prefer evidence tag condition:X; else role_id *_setter; else mechanic name."""
    for item in m.evidence:
        if item.startswith("condition:"):
            condition = item.removeprefix("condition:")
            if condition in TRACKED_CONDITIONS:
                return condition
    if m.role_id:
        for condition, role_id in _SETTER_ROLE_FOR_CONDITION.items():
            if m.role_id == role_id:
                return condition
    if m.mechanic in {"Trick Room", "Tailwind"}:
        return m.mechanic
    return None


def _as_support_need(
    need: SupportNeed | AnchoredSupportNeed,
) -> SupportNeed:
    return need if isinstance(need, SupportNeed) else need.need


def _preferred_setter_direction(
    locked: Sequence[LockedAnchorContext], condition: str
) -> bool:
    setter_id = _SETTER_ROLE_FOR_CONDITION[condition]
    has_setter = False
    has_offense = False
    for context in locked:
        decision = context.role_decision
        roles = (decision.role_id, *decision.secondary_role_ids)
        if setter_id in roles:
            has_setter = True
        if (
            decision.primary_function == "offense"
            and decision.role_id != setter_id
        ):
            has_offense = True
    return has_setter and has_offense


def assess_condition_resilience(
    locked: Sequence[LockedAnchorContext],
) -> ConditionResilienceReport:
    rows: list[ConditionResilienceRow] = []
    for condition in TRACKED_CONDITIONS:
        providers: list[ConditionProviderMember] = []
        dependents: list[ConditionDependentMember] = []
        seen_providers: set[int] = set()
        seen_dependents: set[int] = set()

        for context in locked:
            species = str(
                context.resolved_build.species or context.pokemon.get("species") or ""
            )
            best_dependent: Literal["needed", "wanted"] | None = None
            provider_mechanic: str | None = None
            for mechanism in context.role_decision.mechanisms:
                if mechanism_condition(mechanism) != condition:
                    continue
                if mechanism.present and mechanism.relation == "provides":
                    provider_mechanic = mechanism.mechanic
                if (
                    mechanism.relation == "benefits_from"
                    and mechanism.importance in ("needed", "wanted")
                    and (mechanism.present or mechanism.supply == "teammate_expected")
                ):
                    if mechanism.importance == "needed" or best_dependent is None:
                        best_dependent = mechanism.importance  # type: ignore[assignment]
            if provider_mechanic is not None and context.slot_index not in seen_providers:
                seen_providers.add(context.slot_index)
                providers.append(
                    ConditionProviderMember(
                        context.slot_index, species, provider_mechanic
                    )
                )
            if best_dependent is not None and context.slot_index not in seen_dependents:
                seen_dependents.add(context.slot_index)
                dependents.append(
                    ConditionDependentMember(
                        context.slot_index, species, best_dependent
                    )
                )

        provider_count = len(providers)
        needed = sum(1 for row in dependents if row.importance == "needed")
        wanted = sum(1 for row in dependents if row.importance == "wanted")

        if needed or wanted >= MIN_WANTED_DEPENDENTS_FOR_ESSENTIAL:
            classification: ConditionClass = "essential"
        elif wanted or _preferred_setter_direction(locked, condition):
            classification = "preferred"
        elif provider_count:
            classification = "optional"
        else:
            continue

        if classification in ("essential", "preferred"):
            if provider_count == 0:
                gap: ConditionGap = "missing_provider"
            elif provider_count == 1:
                gap = "single_provider_spof"
            else:
                gap = "none"
        else:
            gap = "none"

        rows.append(
            ConditionResilienceRow(
                condition=condition,
                classification=classification,
                provider_count=provider_count,
                providers=tuple(providers),
                dependents=tuple(dependents),
                gap=gap,
            )
        )
    return ConditionResilienceReport(conditions=tuple(rows))


def _condition_already_covered(
    condition: str, existing_needs: Sequence[SupportNeed | AnchoredSupportNeed]
) -> bool:
    for raw in existing_needs:
        need = _as_support_need(raw)
        if condition == "Trick Room" and need.category == "trick_room":
            return True
        if condition == "Tailwind" and need.category == "tailwind":
            return True
        if condition in _WEATHER_LABEL and need.category == "condition_setter":
            labels = field_labels_from_trigger(need.trigger or "")
            if _WEATHER_LABEL[condition] in labels:
                return True
    return False


def gap_support_needs(
    report: ConditionResilienceReport,
    existing_needs: Sequence[SupportNeed] | Sequence[AnchoredSupportNeed],
) -> tuple[SupportNeed, ...]:
    """Emit gap needs only for conditions not already covered by existing_needs."""
    out: list[SupportNeed] = []
    for row in report.conditions:
        if row.gap == "none":
            continue
        if _condition_already_covered(row.condition, existing_needs):
            continue
        if row.condition in _WEATHER_LABEL:
            label = _WEATHER_LABEL[row.condition]
            out.append(
                SupportNeed(
                    category="condition_setter",
                    name=f"{row.condition} setter",
                    description=(
                        f"Team {row.classification} {row.condition} plan has "
                        f"provider gap ({row.gap})."
                    ),
                    trigger=f"field_condition:any:{label}",
                    notes=f"condition_resilience:{row.gap}",
                )
            )
        elif row.condition == "Trick Room":
            out.append(
                SupportNeed(
                    category="trick_room",
                    name="Trick Room",
                    description=(
                        f"Team {row.classification} Trick Room plan has "
                        f"provider gap ({row.gap})."
                    ),
                    trigger="condition_resilience:gap",
                    stance="need",
                )
            )
        elif row.condition == "Tailwind":
            out.append(
                SupportNeed(
                    category="tailwind",
                    name="Tailwind",
                    description=(
                        f"Team {row.classification} Tailwind plan has "
                        f"provider gap ({row.gap})."
                    ),
                    trigger="condition_resilience:gap",
                    stance="need",
                )
            )
    return tuple(out)
