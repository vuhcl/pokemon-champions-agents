"""Team-wide primary_function SPOF assessment (mirrors condition_resilience)."""

from __future__ import annotations

from collections.abc import Sequence

from recommender.primary_function_types import (
    PrimaryFunctionProviderMember,
    PrimaryFunctionResilienceReport,
    PrimaryFunctionResilienceRow,
)
from recommender.slot_fill import LockedAnchorContext

_TRACKED = ("offense", "support")


def assess_primary_function_resilience(
    locked: Sequence[LockedAnchorContext],
) -> PrimaryFunctionResilienceReport:
    """Emit SPOF rows for offense/support with ≥1 locked provider.

    ``missing_provider`` is not emitted — ``annotate_composition_impact`` already
    promotes via ``missing_primary`` when the function is absent.
    """
    rows: list[PrimaryFunctionResilienceRow] = []
    for primary in _TRACKED:
        providers: list[PrimaryFunctionProviderMember] = []
        for context in locked:
            if context.role_decision.primary_function != primary:
                continue
            species = str(
                context.resolved_build.species or context.pokemon.get("species") or ""
            )
            providers.append(
                PrimaryFunctionProviderMember(context.slot_index, species)
            )
        count = len(providers)
        if count < 1:
            continue
        classification = "essential" if primary == "offense" else "preferred"
        gap = "single_provider_spof" if count == 1 else "none"
        rows.append(
            PrimaryFunctionResilienceRow(
                primary_function=primary,
                classification=classification,
                provider_count=count,
                providers=tuple(providers),
                gap=gap,
            )
        )
    return PrimaryFunctionResilienceReport(functions=tuple(rows))
