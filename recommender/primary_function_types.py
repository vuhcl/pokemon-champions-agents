"""Primary-function resilience report types (import-safe for state)."""

from __future__ import annotations

from dataclasses import dataclass

from recommender.condition_types import ConditionClass, ConditionGap

PrimaryFunctionClass = ConditionClass
PrimaryFunctionGap = ConditionGap


@dataclass(frozen=True)
class PrimaryFunctionProviderMember:
    slot_index: int
    species: str


@dataclass(frozen=True)
class PrimaryFunctionResilienceRow:
    primary_function: str
    classification: PrimaryFunctionClass
    provider_count: int
    providers: tuple[PrimaryFunctionProviderMember, ...]
    gap: PrimaryFunctionGap


@dataclass(frozen=True)
class PrimaryFunctionResilienceReport:
    functions: tuple[PrimaryFunctionResilienceRow, ...]
