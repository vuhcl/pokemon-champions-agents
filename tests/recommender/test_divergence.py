"""Unit tests for backup-redundancy divergence_score."""

from __future__ import annotations

from recommender.anchor_roles import classify_anchor_role, resolve_anchor_build
from recommender.divergence import (
    DIVERGENCE_COMPLEMENTARY_THRESHOLD,
    PROVIDER_TAG_BY_CONDITION,
    divergence_score,
)
from recommender.state import Attr, Slot


def _decide(species: str, ability: str, moves: list[str], *, role: str | None = None):
    slot = Slot(
        species=Attr(species, locked=True),
        ability=Attr(ability, locked=True),
        role=Attr(role, locked=True) if role else Attr(),
        moveset=Attr(moves, locked=True),
    )
    build = resolve_anchor_build(slot)
    return build, classify_anchor_role(build, explicit_role=role)


def _rain_div(cand_build, cand_dec, exist_build, exist_dec) -> float:
    return divergence_score(
        cand_dec,
        exist_dec,
        candidate_moves=cand_build.moves,
        existing_moves=exist_build.moves,
        candidate_ability=cand_build.ability,
        existing_ability=exist_build.ability,
        shared_provider_tags=frozenset({PROVIDER_TAG_BY_CONDITION["Rain"]}),
    )


def test_divergence_score_pelipper_sableye_clears_threshold():
    peli_b, peli_d = _decide(
        "Pelipper",
        "Drizzle",
        ["Hurricane", "Protect", "Tailwind", "U-turn"],
        role="rain_setter",
    )
    sab_b, sab_d = _decide(
        "Sableye",
        "Prankster",
        ["Rain Dance", "Encore", "Will-O-Wisp", "Light Screen"],
        role="rain_setter",
    )
    score = _rain_div(sab_b, sab_d, peli_b, peli_d)
    assert score >= DIVERGENCE_COMPLEMENTARY_THRESHOLD


def test_divergence_score_near_clone_rain_setters_below_threshold():
    peli_b, peli_d = _decide(
        "Pelipper",
        "Drizzle",
        ["Hurricane", "Protect", "Tailwind", "U-turn"],
        role="rain_setter",
    )
    poli_b, poli_d = _decide(
        "Politoed",
        "Drizzle",
        ["Hurricane", "Weather Ball", "Tailwind", "Protect"],
        role="rain_setter",
    )
    score = _rain_div(poli_b, poli_d, peli_b, peli_d)
    assert score < DIVERGENCE_COMPLEMENTARY_THRESHOLD


def test_divergence_score_sparse_kit_fail_closed():
    peli_b, peli_d = _decide(
        "Pelipper",
        "Drizzle",
        ["Hurricane", "Protect", "Tailwind", "U-turn"],
        role="rain_setter",
    )
    poli_b, poli_d = _decide(
        "Politoed",
        "Drizzle",
        ["Protect"],
        role="rain_setter",
    )
    score = _rain_div(poli_b, poli_d, peli_b, peli_d)
    assert score == 0.0
