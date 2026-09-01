"""Role-aware build field selection on the usage-hit synthesis path."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from recommender.anchor_roles import FieldProvenance, ResolvedAnchorBuild, classify_anchor_role
from recommender.ids import to_id
from recommender.legality import load_snapshot, resolve_learnset
from recommender.move_narrowing import (
    WEATHER_SETTING_MOVES,
    _commitment_pct,
    validate_moveset_redundancy,
)
from recommender.role_compendium_read import role_defining_move_ids
from recommender.state import RecommenderState
from recommender.usage_data import (
    PokemonSet,
    _display_ability,
    _display_item,
    _iter_usage_ranked_abilities,
    _iter_usage_ranked_moves,
    _nonempty_moves,
)

_SETTER_ROLES = frozenset(
    {"rain_setter", "sun_setter", "sand_setter", "snow_setter"}
)


@dataclass(frozen=True)
class RoleAwareBuildSelection:
    moves: list[str]
    ability: str | None = None


def _provisional_build(
    species: str,
    moves: list[str],
    *,
    ability: str | None = None,
    item: str | None = None,
    regulation: str,
) -> ResolvedAnchorBuild:
    return ResolvedAnchorBuild(
        species=species,
        ability=ability,
        item=item,
        nature=None,
        evs=(),
        moves=tuple(moves),
        regulation=regulation,
        provenance=(
            FieldProvenance("moves", "usage_derived"),
            FieldProvenance("ability", "usage_derived"),
        ),
        fingerprint="role_aware_provisional",
    )


def _classifies_as(
    species: str,
    moves: list[str],
    role_id: str,
    *,
    ability: str | None = None,
    item: str | None = None,
    regulation: str,
) -> bool:
    build = _provisional_build(
        species, moves, ability=ability, item=item, regulation=regulation
    )
    return classify_anchor_role(build).role_id == role_id


def _screens_minimum(role_moves: list[str]) -> list[str]:
    by_id = {to_id(m): m for m in role_moves}
    if "auroraveil" in by_id:
        return [by_id["auroraveil"]]
    out = [by_id[mid] for mid in ("lightscreen", "reflect") if mid in by_id]
    return out if len(out) >= 2 else role_moves


def _with_protect(chosen: list[str], learnset: set[str]) -> list[str]:
    body = [m for m in chosen if to_id(m) != "protect"]
    if "protect" in learnset:
        return body[:3] + ["Protect"]
    return body[:4]


def _assemble_moves_from_ranked(
    species: str,
    role_id: str,
    entry: dict[str, Any],
    *,
    regulation: str,
    learnset: set[str],
    state: RecommenderState | None,
) -> list[str]:
    role_moves = role_defining_move_ids(role_id)
    ranked = [m for m in _iter_usage_ranked_moves(entry) if to_id(m) in learnset]
    rank_index = {to_id(m): i for i, m in enumerate(ranked)}

    def _sort_key(move: str) -> tuple[int, float, int]:
        pct = _commitment_pct(species, move, regulation=regulation)
        return (0 if pct is None else 1, -(pct or 0.0), rank_index.get(to_id(move), 10**9))

    role_hits = sorted(
        [m for m in ranked if to_id(m) in role_moves],
        key=_sort_key,
    )
    if role_id == "screens_support":
        role_hits = _screens_minimum(role_hits)

    chosen_ids = {to_id(m) for m in role_hits}
    fillers = [m for m in ranked if to_id(m) not in chosen_ids]
    if role_id not in _SETTER_ROLES:
        fillers.sort(
            key=lambda m: (
                to_id(m) in WEATHER_SETTING_MOVES,
                *_sort_key(m)[1:],
            )
        )
    else:
        fillers.sort(key=_sort_key)

    moves = _with_protect(role_hits + fillers, learnset)
    if state is not None:
        red = validate_moveset_redundancy(
            species,
            moves,
            team_draft=list(state.get("team_draft") or []),
            state=state,
        )
        if red.seeming and not red.justified and red.drop_moves:
            drop = {to_id(m) for m in red.drop_moves}
            moves = _with_protect([m for m in moves if to_id(m) not in drop], learnset)
    return moves


def _featured_set_selection(
    species: str,
    role_id: str,
    entry: dict[str, Any],
    *,
    regulation: str,
) -> RoleAwareBuildSelection | None:
    for fs in entry.get("featured_sets") or []:
        moves = _nonempty_moves(fs.get("moves") or [])
        if len(moves) < 4:
            continue
        item = fs.get("item")
        if not item or item == "Nothing":
            continue
        ability = (
            _display_ability(fs["ability"]) if fs.get("ability") else None
        )
        display_item = _display_item(item)
        if _classifies_as(
            species,
            moves,
            role_id,
            ability=ability,
            item=display_item,
            regulation=regulation,
        ):
            return RoleAwareBuildSelection(moves=list(moves), ability=ability)
    return None


def _default_ability(entry: dict[str, Any]) -> str | None:
    for ability in _iter_usage_ranked_abilities(entry):
        return ability
    return None


def select_role_aware_build_fields(
    species: str,
    role_id: str | None,
    entry: dict[str, Any],
    *,
    regulation: str = "champions-reg-mb",
    usage: PokemonSet | None = None,
    item: str | None = None,
    state: RecommenderState | None = None,
) -> RoleAwareBuildSelection | None:
    """Usage-ranked moves/ability biased toward target_role; None → caller fallback."""
    if not role_id or not entry:
        return None
    role_moves = role_defining_move_ids(role_id)
    if not role_moves:
        return None

    snap = load_snapshot()
    learnset = set(resolve_learnset(snap, species) or [])

    if usage and usage.get("moves"):
        default_ability = usage.get("ability")
        default_item = item or usage.get("item")
        if _classifies_as(
            species,
            list(usage["moves"]),
            role_id,
            ability=str(default_ability) if default_ability else None,
            item=str(default_item) if default_item else None,
            regulation=regulation,
        ):
            return RoleAwareBuildSelection(
                moves=list(usage["moves"]),
                ability=str(default_ability) if default_ability else None,
            )

    featured = _featured_set_selection(
        species, role_id, entry, regulation=regulation
    )
    if featured is not None:
        return featured

    moves = _assemble_moves_from_ranked(
        species, role_id, entry, regulation=regulation, learnset=learnset, state=state
    )
    ability = _default_ability(entry)
    display_item = item or (
        _display_item(str(usage["item"])) if usage and usage.get("item") else None
    )

    if _classifies_as(
        species,
        moves,
        role_id,
        ability=ability,
        item=display_item,
        regulation=regulation,
    ):
        return RoleAwareBuildSelection(moves=moves, ability=ability)

    for candidate_ability in _iter_usage_ranked_abilities(entry):
        if _classifies_as(
            species,
            moves,
            role_id,
            ability=candidate_ability,
            item=display_item,
            regulation=regulation,
        ):
            return RoleAwareBuildSelection(moves=moves, ability=candidate_ability)

    return None
