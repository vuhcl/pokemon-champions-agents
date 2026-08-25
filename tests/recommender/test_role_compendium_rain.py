"""Rain Setter Role Compendium construction / critic pipeline (ADR-019)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from recommender.ids import to_id
from recommender.legality import is_species_legal, load_snapshot
from recommender.role_compendium import RAIN_SETTER_CRITERIA, CandidateEval, ClaimedTrait, RoleConstructionDraft, construct_role_category, critique_role_ranking, draft_to_dict, legal_species_pool, persist_approved, rebuild_role_category


def _rain_draft(pool: list[str] | None = None) -> RoleConstructionDraft:
    snap = load_snapshot()
    return construct_role_category(
        "weather_setter",
        RAIN_SETTER_CRITERIA,
        pool if pool is not None else legal_species_pool(snap),
        snap=snap,
        live_fetch=None,  # unit tests: offline snapshot only
    )


def _member_names(draft: RoleConstructionDraft, tier: str) -> set[str]:
    return {c.species for c in draft.candidates if c.tier == tier}


def test_rain_excellent_tied_pelipper_politoed():
    draft = _rain_draft()
    excellent = _member_names(draft, "Excellent")
    assert excellent == {"Pelipper", "Politoed"}, draft.tiers
    assert "Kyogre" not in excellent
    classes = {
        c.delivery_class
        for c in draft.candidates
        if c.species in ("Pelipper", "Politoed")
    }
    assert classes == {"ability"}


def test_rain_sableye_good_mega_excluded():
    draft = _rain_draft()
    good = _member_names(draft, "Good")
    assert "Sableye" in good, draft.tiers
    members = {c.species for c in draft.candidates if c.tier}
    assert "Sableye-Mega" not in members
    sableye = next(c for c in draft.candidates if c.species == "Sableye")
    assert sableye.delivery_class == "move_priority"
    assert sableye.mechanism == "Rain Dance"


def test_rain_prankster_rain_dance_above_floor_is_good():
    """July chaos: Banette-Mega 4.59 / Liepard 3.62 / Meowstic 4.56 / Klefki 6.32."""
    draft = _rain_draft()
    good = _member_names(draft, "Good")
    assert {"Banette-Mega", "Liepard", "Meowstic", "Klefki"} <= good, draft.tiers
    for sid in ("banettemega", "liepard", "meowstic", "klefki"):
        c = next(x for x in draft.candidates if x.species_id == sid)
        assert c.criteria_notes.get("usage_proven") == "True"
        assert c.delivery_class == "move_priority"


def test_legal_pool_bounds_construction():
    """Legal-first: omitting Pelipper from pool excludes it even though snap-legal."""
    snap = load_snapshot()
    pool = [n for n in legal_species_pool(snap) if to_id(n) != "pelipper"]
    draft = construct_role_category(
        "weather_setter", RAIN_SETTER_CRITERIA, pool, snap=snap, live_fetch=None
    )
    assert "Pelipper" not in _member_names(draft, "Excellent")
    assert "Politoed" in _member_names(draft, "Excellent")
    assert "Kyogre" not in {c.species for c in draft.candidates}
    assert not is_species_legal(snap, "kyogre")


def test_legal_pool_escape_raises():
    draft = _rain_draft()
    draft.candidates.append(
        CandidateEval(
            species="FakeMon",
            species_id="fakemon",
            tier="Excellent",
            delivery_class="ability",
            mechanism="Drizzle",
            criteria_notes={},
            claimed_traits=[],
            reasoning="injected",
        )
    )
    pool_ids = {to_id(s) for s in legal_species_pool()}
    with pytest.raises(ValueError, match="escaped legal_pool"):
        for c in draft.candidates:
            if c.species_id not in pool_ids:
                raise ValueError(f"candidate escaped legal_pool: {c.species}")


def test_critique_approves_known_correct_structure():
    draft = _rain_draft()
    result = critique_role_ranking(draft)
    assert result.approved, result.flags
    assert result.flags == []


def test_critique_tied_cluster_same_delivery_class():
    draft = RoleConstructionDraft(
        category="weather_setter",
        sub_criteria={"condition": "Rain"},
        candidates=[
            CandidateEval(
                species="Pelipper",
                species_id="pelipper",
                tier="Excellent",
                delivery_class="ability",
                mechanism="Drizzle",
                criteria_notes={},
                claimed_traits=[],
                reasoning="",
            ),
            CandidateEval(
                species="Politoed",
                species_id="politoed",
                tier="Good",
                delivery_class="ability",
                mechanism="Drizzle",
                criteria_notes={},
                claimed_traits=[],
                reasoning="",
            ),
        ],
        considered_rejected=[],
        tiers={"Excellent": ["Pelipper"], "Good": ["Politoed"]},
    )
    result = critique_role_ranking(draft)
    assert not result.approved
    assert any(f.principle == "tied_cluster" for f in result.flags)


def test_critique_self_consistency_silent_drop():
    draft = RoleConstructionDraft(
        category="weather_setter",
        sub_criteria={"condition": "Rain"},
        candidates=[
            CandidateEval(
                species="Pelipper",
                species_id="pelipper",
                tier="Excellent",
                delivery_class="ability",
                mechanism="Drizzle",
                criteria_notes={},
                claimed_traits=[],
                reasoning="",
            ),
        ],
        considered_rejected=[],
        tiers={"Excellent": ["Pelipper"]},
    )
    reference = {
        "candidates": [
            {"species": "Sableye", "species_id": "sableye", "tier": "Good"},
            {"species": "Pelipper", "species_id": "pelipper", "tier": "Excellent"},
        ]
    }
    result = critique_role_ranking(draft, reference_compendium=reference)
    assert not result.approved
    assert any(
        f.principle == "self_consistency"
        and any("sableye" in n.lower() for n in f.candidates)
        for f in result.flags
    )


def test_critique_function_fit_magic_guard_ally():
    draft = RoleConstructionDraft(
        category="weather_setter",
        sub_criteria={"condition": "Rain"},
        candidates=[
            CandidateEval(
                species="Clefable",
                species_id="clefable",
                tier="Good",
                delivery_class="move_priority",
                mechanism="Rain Dance",
                criteria_notes={},
                claimed_traits=[
                    ClaimedTrait(
                        name="Magic Guard",
                        criterion="secondary_role",
                        purpose_claimed="ally protection",
                    )
                ],
                reasoning="",
            ),
        ],
        considered_rejected=[],
        tiers={"Good": ["Clefable"]},
    )
    result = critique_role_ranking(draft)
    assert not result.approved
    assert any(f.principle == "function_fit" for f in result.flags)


def test_rebuild_approve_and_history(tmp_path: Path):
    r1 = rebuild_role_category(
        "weather_setter", RAIN_SETTER_CRITERIA, roles_dir=tmp_path, live_fetch=None
    )
    assert r1.status == "approved", r1.critique.flags
    assert r1.path is not None
    assert Path(r1.path).exists()
    r2 = rebuild_role_category(
        "weather_setter", RAIN_SETTER_CRITERIA, roles_dir=tmp_path, live_fetch=None
    )
    assert r2.status == "approved", r2.critique.flags
    hist = list((tmp_path / "history").glob("weather_setter_rain.*.json"))
    assert len(hist) >= 1


def test_rebuild_human_gate_on_flags(tmp_path: Path):
    # Seed a prior that construct will silently diverge from (Sableye Excellent → Good).
    prior_draft = _rain_draft()
    for c in prior_draft.candidates:
        if c.species == "Sableye":
            c.tier = "Excellent"
    prior_draft.tiers = {
        "Excellent": ["Pelipper", "Politoed", "Sableye"],
        "Good": [],
    }
    persist_approved(prior_draft, tmp_path)
    result = rebuild_role_category(
        "weather_setter",
        RAIN_SETTER_CRITERIA,
        roles_dir=tmp_path,
        live_fetch=None,
    )
    assert result.status == "needs_revision"
    assert result.path is None
    assert any(f.principle == "self_consistency" for f in result.critique.flags)
    stored = json.loads((tmp_path / "weather_setter_rain.v1.json").read_text())
    assert "Sableye" in (stored.get("tiers") or {}).get("Excellent", [])


def test_draft_to_dict_roundtrip_shape():
    draft = _rain_draft()
    d = draft_to_dict(draft)
    assert d["category"] == "weather_setter"
    assert d["condition"] == "Rain"
    assert "species_id" in d["candidates"][0]
    assert isinstance(d["considered_rejected"], list)
