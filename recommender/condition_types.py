"""Condition-resilience report types (no recommender imports — safe for state)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ConditionClass = Literal["essential", "preferred", "optional"]
ConditionGap = Literal["none", "missing_provider", "single_provider_spof"]
TRACKED_CONDITIONS = ("Rain", "Sun", "Sand", "Snow", "Trick Room", "Tailwind")

# Calibratable: wanted×2 → essential
MIN_WANTED_DEPENDENTS_FOR_ESSENTIAL = 2


@dataclass(frozen=True)
class ConditionDependentMember:
    slot_index: int
    species: str
    importance: Literal["needed", "wanted"]


@dataclass(frozen=True)
class ConditionProviderMember:
    slot_index: int
    species: str
    mechanic: str


@dataclass(frozen=True)
class ConditionResilienceRow:
    condition: str
    classification: ConditionClass
    provider_count: int
    providers: tuple[ConditionProviderMember, ...]
    dependents: tuple[ConditionDependentMember, ...]
    gap: ConditionGap


@dataclass(frozen=True)
class ConditionResilienceReport:
    conditions: tuple[ConditionResilienceRow, ...]
