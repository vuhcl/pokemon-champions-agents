"""ADR-023 orchestrator consumption: hold, annotate, merge, terminal lock."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from recommender.by_usage import query_by_usage
from recommender.calc_client import PokemonSpecOptional
from recommender.contingent_value import REDIRECT_MOVES
from recommender.coverage import ABILITY_TO_FIELD
from recommender.ids import to_id
from recommender.legality import is_species_legal, load_snapshot, resolve_learnset
from recommender.move_narrowing import narrow_candidates_for_move, pick_default_and_alternatives
from recommender.nodes import apply_lock
from recommender.state import (
    LockPayload,
    RecommenderState,
    ThreatCounterCandidate,
)
from recommender.support_needs import (
    NeedCategory,
    RoleShapeContext,
    SupportNeed,
    _weather_category_match,
    field_labels_from_trigger,
)
from recommender.usage_data import featured_or_common_set

Source = Literal["threat", "need", "both"]
SlotFillAction = Literal["accept_default", "choose", "defer"]

_FO_PROTECTION_ABILITIES = frozenset(
    {"armortail", "queenlymajesty", "dazzling"}
)


@dataclass(frozen=True)
class _NeedSatisfier:
    moves: frozenset[str] = frozenset()
    abilities: frozenset[str] = frozenset()


# Annotate: learnset ∩ moves OR abilities ∩ ability ids. No defensive_coverage /
# stat_lowering_partner entry — no cheap teammate signal → never matches.
_NEED_SATISFIERS: dict[NeedCategory, _NeedSatisfier] = {
    "trick_room": _NeedSatisfier(moves=frozenset({"trickroom"})),
    "tailwind": _NeedSatisfier(moves=frozenset({"tailwind"})),
    "fake_out_protection": _NeedSatisfier(
        moves=frozenset({"fakeout"}) | frozenset(REDIRECT_MOVES),
        abilities=_FO_PROTECTION_ABILITIES,
    ),
    "taunt_disruption": _NeedSatisfier(moves=frozenset({"taunt"})),
    "healing_cleric": _NeedSatisfier(
        moves=frozenset(
            {"wish", "healpulse", "lifedew", "aromatherapy", "healbell"}
        )
    ),
    "screens": _NeedSatisfier(
        moves=frozenset({"lightscreen", "reflect", "auroraveil"})
    ),
    "condition_setter": _NeedSatisfier(abilities=frozenset(ABILITY_TO_FIELD)),
}


@dataclass(frozen=True)
class AnnotatedCandidate:
    species: str
    matching_needs: tuple[SupportNeed, ...]
    source: Source
    threat_row: ThreatCounterCandidate | None = None
    spec: PokemonSpecOptional = field(default_factory=dict)  # type: ignore[assignment]


@dataclass
class SlotFillContext:
    anchor: PokemonSpecOptional
    role_shape_context: RoleShapeContext
    threat_counter_results: list[ThreatCounterCandidate] | None = None
    support_needs: list[SupportNeed] | None = None
    chosen_need: SupportNeed | None = None
    need_resolved_candidates: list[str] | None = None
    annotated_candidates: list[AnnotatedCandidate] | None = None


@dataclass(frozen=True)
class SlotFillPresentation:
    """Contract for classify_input lock intent: options map to LockPayload values.

    accept → LockPayload{slot_index, attr=\"species\", value=<species>}
    multi → LockPayload{slot_index, locks=[...]} via existing batch path
    """

    slot_index: int
    default: str | None
    alternatives: list[str]
    options: tuple[str, ...]


@dataclass(frozen=True)
class SlotFillResponse:
    action: SlotFillAction
    species: str | None = None  # required for choose


@dataclass
class SlotFillTerminalResult:
    presentation: SlotFillPresentation
    state_updates: dict[str, Any]
    deferred: bool


def _regulation(state: RecommenderState | None = None) -> str:
    reg = (state or {}).get("regulation_mod") or "champions-reg-mb"
    return "champions-reg-mb" if reg == "champions" else str(reg)


def _legality_abilities(snap: dict[str, Any], species: str) -> set[str]:
    entry = (snap.get("species") or {}).get(to_id(species)) or {}
    return {
        to_id(v) for v in (entry.get("abilities") or {}).values() if isinstance(v, str)
    }


def _species_abilities(species: str, *, snap: dict[str, Any], regulation: str) -> set[str]:
    out = _legality_abilities(snap, species)
    featured = featured_or_common_set(species, regulation=regulation)
    if featured and featured.get("ability"):
        out.add(to_id(str(featured["ability"])))
    return out


def _field_label_matches(aid: str, label: str) -> bool:
    field = ABILITY_TO_FIELD.get(aid)
    if not field:
        return False
    w, t = field.get("weather"), field.get("terrain")
    if w and _weather_category_match(str(w), label):
        return True
    if t and to_id(str(t)) == to_id(label):
        return True
    return False


def _ability_matches_field_labels(aid: str, labels: list[str]) -> bool:
    return any(_field_label_matches(aid, lab) for lab in labels)


def _candidate_satisfies_need(
    species: str,
    need: SupportNeed,
    *,
    snap: dict[str, Any],
    regulation: str = "champions-reg-mb",
) -> bool:
    sat = _NEED_SATISFIERS.get(need.category)
    if sat is None:
        return False
    ls = set(resolve_learnset(snap, species) or [])
    if sat.moves and ls & sat.moves:
        return True
    if sat.abilities:
        abs_ = _species_abilities(species, snap=snap, regulation=regulation)
        if need.category == "condition_setter" and need.trigger:
            labels = field_labels_from_trigger(need.trigger)
            if labels:
                return any(
                    aid in abs_ and _ability_matches_field_labels(aid, labels)
                    for aid in ABILITY_TO_FIELD
                )
        if abs_ & sat.abilities:
            return True
    return False


def _matching_needs_for(
    species: str,
    needs: list[SupportNeed],
    *,
    snap: dict[str, Any],
    regulation: str = "champions-reg-mb",
) -> tuple[SupportNeed, ...]:
    return tuple(
        n
        for n in needs
        if _candidate_satisfies_need(species, n, snap=snap, regulation=regulation)
    )


def annotate_overlap(ctx: SlotFillContext) -> list[AnnotatedCandidate]:
    """Cheap cross-branch annotation once both branch outputs exist."""
    if ctx.threat_counter_results is None or ctx.support_needs is None:
        raise ValueError(
            "annotate_overlap requires threat_counter_results and support_needs"
        )
    snap = load_snapshot()
    regulation = "champions-reg-mb"
    out: list[AnnotatedCandidate] = []
    for row in ctx.threat_counter_results:
        species = (
            row.candidate.spec.get("species")
            or row.candidate.form
            or row.candidate.ladder_species
        )
        matched = _matching_needs_for(
            species, ctx.support_needs, snap=snap, regulation=regulation
        )
        out.append(
            AnnotatedCandidate(
                species=species,
                matching_needs=matched,
                source="both" if matched else "threat",
                threat_row=row,
                spec=dict(row.candidate.spec) or {"species": species},
            )
        )
    ctx.annotated_candidates = out
    return out


def merge_need_resolved(ctx: SlotFillContext) -> list[AnnotatedCandidate]:
    """Merge threat rows with need-resolved species; chosen_need optional (resolve-all)."""
    if ctx.need_resolved_candidates is None or ctx.threat_counter_results is None:
        raise ValueError(
            "merge_need_resolved requires need_resolved_candidates "
            "and threat_counter_results"
        )
    needs = list(ctx.support_needs or [])
    if ctx.chosen_need is not None and ctx.chosen_need not in needs:
        needs = [*needs, ctx.chosen_need]
    snap = load_snapshot()
    regulation = "champions-reg-mb"

    by_id: dict[str, AnnotatedCandidate] = {}
    for row in ctx.threat_counter_results:
        species = (
            row.candidate.spec.get("species")
            or row.candidate.form
            or row.candidate.ladder_species
        )
        sid = to_id(species)
        matched = _matching_needs_for(species, needs, snap=snap, regulation=regulation)
        by_id[sid] = AnnotatedCandidate(
            species=species,
            matching_needs=matched,
            source="both" if matched else "threat",
            threat_row=row,
            spec=dict(row.candidate.spec) or {"species": species},
        )

    for name in ctx.need_resolved_candidates:
        sid = to_id(name)
        existing = by_id.get(sid)
        if existing is not None:
            matched = existing.matching_needs
            if ctx.chosen_need is not None and ctx.chosen_need not in matched:
                matched = (*matched, ctx.chosen_need)
            by_id[sid] = AnnotatedCandidate(
                species=existing.species,
                matching_needs=matched,
                source="both",
                threat_row=existing.threat_row,
                spec=existing.spec,
            )
            continue
        matched = _matching_needs_for(name, needs, snap=snap, regulation=regulation)
        if ctx.chosen_need is not None and ctx.chosen_need not in matched:
            matched = (*matched, ctx.chosen_need)
        by_id[sid] = AnnotatedCandidate(
            species=name,
            matching_needs=matched,
            source="need",
            threat_row=None,
            spec={"species": name},
        )

    out = list(by_id.values())
    ctx.annotated_candidates = out
    return out


def _union_move_candidates(
    move_ids: frozenset[str], state: RecommenderState
) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for mid in move_ids:
        for name in narrow_candidates_for_move(mid, state).candidates:
            sid = to_id(name)
            if sid in seen:
                continue
            seen.add(sid)
            out.append(name)
    return out


def _species_with_abilities(
    ability_ids: frozenset[str],
    *,
    snap: dict[str, Any],
    regulation: str,
) -> list[str]:
    out: list[str] = []
    for sid, entry in (snap.get("species") or {}).items():
        if not is_species_legal(snap, sid):
            continue
        name = str(entry.get("name") or sid)
        if _species_abilities(name, snap=snap, regulation=regulation) & ability_ids:
            out.append(name)
    return out


def _rank_by_usage(names: list[str], *, n: int = 20) -> list[str]:
    if not names:
        return []
    ranked = query_by_usage([{"species": n} for n in names], n=n)
    out: list[str] = []
    seen: set[str] = set()
    for c in ranked:
        sp = c.spec.get("species") or c.form or c.ladder_species
        if not sp:
            continue
        sid = to_id(sp)
        if sid in seen:
            continue
        seen.add(sid)
        out.append(str(sp))
    return out


def _resolve_condition_setter(need: SupportNeed, state: RecommenderState) -> list[str]:
    snap = load_snapshot()
    regulation = _regulation(state)
    labels = field_labels_from_trigger(need.trigger) if need.trigger else []
    names: list[str] = []
    for sid, entry in (snap.get("species") or {}).items():
        if not is_species_legal(snap, sid):
            continue
        name = str(entry.get("name") or sid)
        abs_ = _species_abilities(name, snap=snap, regulation=regulation)
        if labels:
            if any(
                aid in abs_ and _ability_matches_field_labels(aid, labels) for aid in abs_
            ):
                names.append(name)
        elif abs_ & frozenset(ABILITY_TO_FIELD):
            names.append(name)
    return _rank_by_usage(names)


def resolve_need_candidates(need: SupportNeed, state: RecommenderState) -> list[str]:
    cat = need.category
    if cat == "stat_lowering_partner":
        return []
    if cat == "defensive_coverage":
        raise NotImplementedError(
            f"need {need.category}: compendium/ability-search deferred"
        )
    if cat == "condition_setter":
        return _resolve_condition_setter(need, state)

    sat = _NEED_SATISFIERS.get(cat)
    if sat is None or not sat.moves:
        raise NotImplementedError(
            f"need {need.category}: compendium/ability-search deferred"
        )

    if cat in ("trick_room", "tailwind", "taunt_disruption"):
        mid = next(iter(sat.moves))
        return narrow_candidates_for_move(mid, state).candidates

    names = _union_move_candidates(sat.moves, state)
    if cat == "fake_out_protection" and sat.abilities:
        snap = load_snapshot()
        regulation = _regulation(state)
        seen = {to_id(n) for n in names}
        for n in _species_with_abilities(
            sat.abilities, snap=snap, regulation=regulation
        ):
            sid = to_id(n)
            if sid not in seen:
                seen.add(sid)
                names.append(n)
        return _rank_by_usage(names)
    return names


def resolve_all_support_needs(
    ctx: SlotFillContext, state: RecommenderState
) -> list[str]:
    """Resolve every surfaced need; skip deferred/empty; set need_resolved_candidates."""
    seen: set[str] = set()
    out: list[str] = []
    for need in ctx.support_needs or []:
        try:
            names = resolve_need_candidates(need, state)
        except NotImplementedError:
            continue
        for name in names:
            sid = to_id(name)
            if sid in seen:
                continue
            seen.add(sid)
            out.append(name)
    ctx.need_resolved_candidates = out
    return out


def _usage_rank_key(row: AnnotatedCandidate) -> float:
    if row.threat_row is not None and row.threat_row.candidate.usage_rank is not None:
        return float(row.threat_row.candidate.usage_rank)
    return float("inf")


def _sort_annotated(rows: list[AnnotatedCandidate]) -> list[AnnotatedCandidate]:
    return sorted(
        rows,
        key=lambda r: (
            -len(r.matching_needs),
            -(r.threat_row.verified_score if r.threat_row else 0.0),
            _usage_rank_key(r),
        ),
    )


def present_candidates(
    ctx: SlotFillContext, *, slot_index: int
) -> SlotFillPresentation:
    rows = _sort_annotated(list(ctx.annotated_candidates or []))
    names = [r.species for r in rows]
    picked = pick_default_and_alternatives(names)
    default = picked.get("default")
    alts = list(picked.get("alternatives") or [])
    options: list[str] = []
    if default:
        options.append(default)
    options.extend(a for a in alts if a and a not in options)
    return SlotFillPresentation(
        slot_index=slot_index,
        default=default,
        alternatives=alts,
        options=tuple(options),
    )


def run_slot_fill_terminal(
    ctx: SlotFillContext,
    state: RecommenderState,
    *,
    slot_index: int,
    response: SlotFillResponse,
) -> SlotFillTerminalResult:
    presentation = present_candidates(ctx, slot_index=slot_index)

    if response.action == "defer":
        return SlotFillTerminalResult(
            presentation=presentation, state_updates={}, deferred=True
        )

    if response.action == "accept_default":
        species = presentation.default
    elif response.action == "choose":
        species = response.species
    else:
        raise ValueError(f"unknown SlotFillResponse.action: {response.action!r}")

    if not species:
        raise ValueError("cannot lock: no species resolved from presentation/response")

    payload: LockPayload = {
        "slot_index": slot_index,
        "attr": "species",
        "value": species,
    }
    merged: RecommenderState = {**state, "turn_payload": payload}  # type: ignore[misc]
    updates = apply_lock(merged)
    return SlotFillTerminalResult(
        presentation=presentation, state_updates=updates, deferred=False
    )
