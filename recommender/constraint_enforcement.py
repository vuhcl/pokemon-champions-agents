"""Mechanically-checkable user constraint normalization and enforcement."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, TYPE_CHECKING

from recommender.ids import to_id
from recommender.legality import (
    is_item_legal,
    legal_items,
    load_snapshot,
    pick_synthesized_default_item,
    species_can_have_ability,
    team_item_ids,
)
from recommender.state import CandidateDiscoveryError, Constraint, Slot, all_locked

if TYPE_CHECKING:
    from recommender.slot_fill import AnnotatedCandidate

MechanicalKind = Literal["type", "ability", "item", "no_duplicate_items"]

_POKEMON_TYPES = frozenset(
    {
        "normal",
        "fire",
        "water",
        "electric",
        "grass",
        "ice",
        "fighting",
        "poison",
        "ground",
        "flying",
        "psychic",
        "bug",
        "rock",
        "ghost",
        "dragon",
        "dark",
        "steel",
        "fairy",
    }
)

_TYPE_PREDICATE_RE = re.compile(
    r"^type\s*[:_]\s*(?P<type>[a-zA-Z]+)$",
    re.IGNORECASE,
)
_ABILITY_PREDICATE_RES = (
    re.compile(r"^ability\s*[:_]\s*(?P<ability>.+)$", re.IGNORECASE),
    re.compile(r"^has[_\s-]+(?P<ability>[a-zA-Z][a-zA-Z0-9_\s-]*)$", re.IGNORECASE),
)
_NO_DUPLICATE_ITEMS_RE = re.compile(r"no\s+duplicate\s+items?", re.IGNORECASE)
_MONOTYPE_WITH_TYPE_RE = re.compile(
    r"monotype\s*(?P<type>[a-zA-Z]+)|(?P<type2>[a-zA-Z]+)\s+monotype",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MechanicalSpec:
    kind: MechanicalKind
    value: str
    scope: Literal["per_slot", "team_wide"]
    label: str


@dataclass(frozen=True)
class ConstraintPartition:
    unenforceable_hard: tuple[Constraint, ...]
    parsed_hard: tuple[MechanicalSpec, ...]
    soft_mechanical: tuple[MechanicalSpec, ...]


def _normalize_type(raw: str) -> str | None:
    cleaned = raw.strip().title()
    if cleaned.lower() in _POKEMON_TYPES:
        return cleaned
    return None


def _normalize_ability(raw: str) -> str | None:
    text = raw.strip().replace("_", " ")
    if not text:
        return None
    return text.title()


def _normalize_item(raw: str, snap: dict) -> str | None:
    text = raw.strip()
    if not text:
        return None
    iid = to_id(text)
    items = snap.get("items") or {}
    if iid in items:
        return str(items[iid].get("name") or text)
    for key, entry in items.items():
        if key == iid or str(entry.get("name", "")).lower() == text.lower():
            return str(entry.get("name") or text)
    return text if is_item_legal(snap, text) else None


def resolve_mechanical(
    constraint: Constraint,
    *,
    mechanical_kind: MechanicalKind | None = None,
    mechanical_value: str | None = None,
) -> MechanicalSpec | None:
    """Structured fields first, then predicate fallback. None = unenforceable."""
    if constraint.mechanical is not None:
        return constraint.mechanical

    snap = load_snapshot()
    kind = mechanical_kind
    value = mechanical_value
    predicate = (constraint.predicate or "").strip()
    scope = constraint.scope

    if kind is None and predicate:
        lowered = predicate.casefold()
        if _NO_DUPLICATE_ITEMS_RE.search(predicate):
            kind = "no_duplicate_items"
            value = ""
        else:
            type_match = _TYPE_PREDICATE_RE.match(predicate)
            if type_match:
                kind = "type"
                value = type_match.group("type")
            elif lowered in {"monotype", "is_type", "species"}:
                return None
            else:
                mono = _MONOTYPE_WITH_TYPE_RE.search(predicate)
                if mono:
                    kind = "type"
                    value = mono.group("type") or mono.group("type2")
                    scope = "team_wide"
                else:
                    for pattern in _ABILITY_PREDICATE_RES:
                        ability_match = pattern.match(predicate)
                        if ability_match:
                            kind = "ability"
                            value = ability_match.group("ability")
                            break
                    if kind is None and lowered not in {
                        "held_item",
                        "speed",
                        "aggressiveness",
                        "is_shiny",
                    }:
                        item = _normalize_item(predicate, snap)
                        if item and is_item_legal(snap, item):
                            kind = "item"
                            value = item

    if kind is None:
        return None

    label = predicate or kind
    if kind == "no_duplicate_items":
        return MechanicalSpec(kind=kind, value="", scope=scope, label=label)
    if kind == "type":
        normalized = _normalize_type(value or "")
        if normalized is None:
            return None
        return MechanicalSpec(
            kind=kind, value=normalized, scope=scope, label=label
        )
    if kind == "ability":
        normalized = _normalize_ability(value or "")
        if normalized is None:
            return None
        return MechanicalSpec(
            kind=kind, value=normalized, scope=scope, label=label
        )
    if kind == "item":
        normalized = _normalize_item(value or predicate, snap)
        if normalized is None:
            return None
        return MechanicalSpec(
            kind=kind, value=normalized, scope=scope, label=label
        )
    return None


def _species_types(snap: dict, species: str) -> list[str]:
    from recommender.counters import _species_types as _types

    return _types(snap, species)


def _locked_violates_team_wide_type(
    spec: MechanicalSpec,
    *,
    snap: dict,
    team_draft: list[Slot],
) -> bool:
    target = spec.value.casefold()
    allowed = {target}
    for slot in team_draft:
        if not all_locked(slot) or not slot.species.value:
            continue
        types = {t.casefold() for t in _species_types(snap, str(slot.species.value))}
        if not types or not types.issubset(allowed):
            return True
    return False


def _species_has_duplicate_item_headroom(
    species: str,
    *,
    snap: dict,
    team_draft: list[Slot],
    open_slot_index: int | None,
) -> bool:
    used = team_item_ids(team_draft, exclude_slot=open_slot_index)
    default = pick_synthesized_default_item(None, team_draft)
    if default and to_id(default) not in used and is_item_legal(snap, default):
        return True
    for item in legal_items(snap):
        if to_id(item) not in used and is_item_legal(snap, item):
            return True
    del species  # ponytail: per-species item pools not in snapshot; any legal free item suffices
    return False


def matches_species(
    species: str,
    spec: MechanicalSpec,
    *,
    snap: dict | None = None,
    team_draft: list[Slot] | None = None,
    open_slot_index: int | None = None,
) -> bool:
    snap = snap or load_snapshot()
    team_draft = team_draft or []
    sid = to_id(species)

    if spec.kind == "type":
        types = {t.casefold() for t in _species_types(snap, sid)}
        if spec.value.casefold() not in types:
            return False
        if spec.scope == "team_wide":
            return not _locked_violates_team_wide_type(
                spec, snap=snap, team_draft=team_draft
            )
        return True

    if spec.kind == "ability":
        return species_can_have_ability(snap, sid, spec.value)

    if spec.kind == "item":
        if not is_item_legal(snap, spec.value):
            return False
        used = team_item_ids(team_draft, exclude_slot=open_slot_index)
        return to_id(spec.value) not in used

    if spec.kind == "no_duplicate_items":
        return _species_has_duplicate_item_headroom(
            species,
            snap=snap,
            team_draft=team_draft,
            open_slot_index=open_slot_index,
        )

    return False


def soft_rank_bonus(
    species: str,
    specs: tuple[MechanicalSpec, ...],
    *,
    snap: dict | None = None,
    team_draft: list[Slot] | None = None,
    open_slot_index: int | None = None,
) -> int:
    if not specs:
        return 0
    snap = snap or load_snapshot()
    return sum(
        1
        for spec in specs
        if matches_species(
            species,
            spec,
            snap=snap,
            team_draft=team_draft,
            open_slot_index=open_slot_index,
        )
    )


def partition_constraints(constraints: list[Constraint]) -> ConstraintPartition:
    unenforceable_hard: list[Constraint] = []
    parsed_hard: list[MechanicalSpec] = []
    soft_mechanical: list[MechanicalSpec] = []

    for constraint in constraints:
        if not constraint.still_active:
            continue
        spec = resolve_mechanical(constraint)
        if constraint.type == "hard":
            if spec is None:
                unenforceable_hard.append(constraint)
            else:
                parsed_hard.append(spec)
        elif constraint.type == "soft" and spec is not None:
            soft_mechanical.append(spec)

    return ConstraintPartition(
        unenforceable_hard=tuple(unenforceable_hard),
        parsed_hard=tuple(parsed_hard),
        soft_mechanical=tuple(soft_mechanical),
    )


def filter_candidates(
    candidates: list[AnnotatedCandidate],
    specs: tuple[MechanicalSpec, ...],
    *,
    team_draft: list[Slot],
    open_slot_index: int | None,
) -> list[AnnotatedCandidate]:
    if not specs:
        return candidates
    snap = load_snapshot()
    for spec in specs:
        if spec.kind == "type" and spec.scope == "team_wide":
            if _locked_violates_team_wide_type(spec, snap=snap, team_draft=team_draft):
                return []
    out: list[AnnotatedCandidate] = []
    for row in candidates:
        if all(
            matches_species(
                row.species,
                spec,
                snap=snap,
                team_draft=team_draft,
                open_slot_index=open_slot_index,
            )
            for spec in specs
        ):
            out.append(row)
    return out


def apply_mechanical_constraints_to_discovery(
    candidates: list[AnnotatedCandidate],
    constraints: list[Constraint],
    *,
    team_draft: list[Slot],
    open_slot_index: int | None,
) -> tuple[list[AnnotatedCandidate], CandidateDiscoveryError | None]:
    part = partition_constraints(constraints)
    if part.unenforceable_hard:
        preds = ", ".join(c.predicate for c in part.unenforceable_hard)
        return [], CandidateDiscoveryError(
            kind="unsupported_constraint",
            stage="constraint_validation",
            message="Unsupported hard constraints: " + preds,
            retryable=False,
        )
    if not part.parsed_hard:
        return candidates, None
    filtered = filter_candidates(
        candidates,
        part.parsed_hard,
        team_draft=team_draft,
        open_slot_index=open_slot_index,
    )
    if not filtered:
        labels = ", ".join(spec.label for spec in part.parsed_hard)
        return [], CandidateDiscoveryError(
            kind="constraint_unsatisfiable",
            stage="constraint_validation",
            message="No candidates match hard constraint(s): " + labels,
            retryable=False,
        )
    return filtered, None


def discovery_soft_specs(constraints: list[Constraint]) -> tuple[MechanicalSpec, ...]:
    return partition_constraints(constraints).soft_mechanical


def commit_unsupported_hard_predicates(constraints: list[Constraint]) -> list[str]:
    out: list[str] = []
    for constraint in constraints:
        if not constraint.still_active or constraint.type != "hard":
            continue
        if resolve_mechanical(constraint) is None:
            out.append(constraint.predicate)
    return out


def build_constraint(
    payload: dict,
    *,
    source_turn: int,
) -> Constraint:
    spec = resolve_mechanical(
        Constraint(
            type=payload["type"],
            predicate=payload["predicate"],
            source_turn=source_turn,
            scope=payload["scope"],
            groundedness=payload["groundedness"],
        ),
        mechanical_kind=payload.get("mechanical_kind"),  # type: ignore[arg-type]
        mechanical_value=payload.get("mechanical_value"),
    )
    return Constraint(
        type=payload["type"],
        predicate=payload["predicate"],
        source_turn=source_turn,
        scope=payload["scope"],
        groundedness=payload["groundedness"],
        mechanical=spec,
    )


def _self_check() -> None:
    snap = load_snapshot()
    assert _normalize_type("grass") == "Grass"
    c = Constraint(
        "hard",
        "type:grass",
        0,
        True,
        "per_slot",
        "mechanically-checkable",
    )
    spec = resolve_mechanical(c)
    assert spec is not None and spec.kind == "type"
    assert matches_species("Rillaboom", spec, snap=snap, team_draft=[])
    assert not matches_species("Pelipper", spec, snap=snap, team_draft=[])
    shiny = Constraint("hard", "must be shiny", 0, True, "team_wide", "mechanically-checkable")
    assert resolve_mechanical(shiny) is None


if __name__ == "__main__":
    _self_check()
    print("constraint_enforcement self-check ok")
