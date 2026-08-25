"""Trick Room Setter Role Compendium (ADR-019 support-role pipeline).

Offline-deterministic: live_fetch / showdown_fetch default to None so the shipped
usage snapshots drive every assertion.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from recommender.ability_classification import (
    flinch_denial_ability_ids,
    load_abilities,
    taunt_denial_ability_ids,
)
from recommender.ids import to_id
from recommender.legality import load_snapshot
from recommender.move_narrowing import move_priority
from recommender.role_compendium import (
    TRICK_ROOM_SETTER_CRITERIA,
    CandidateEval,
    ClaimedTrait,
    RoleConstructionDraft,
    _mega_usage_attribution,
    _TRICK_ROOM_BULK_FLOOR,
    _TRICK_ROOM_SECONDARY_MOVES,
    _UsageCtx,
    construct_role_category,
    critique_role_ranking,
    legal_species_pool,
    rebuild_role_category,
)


# Real Champions Trick Room shares, so tiering tests exercise usage-proven
# members. Offline snapshots cover only ~80 species, and unproven usage now
# costs two tiers, so without this the whole field demotes.
_CHAMPIONS_TR_PCT = {
    "oranguru": 93.3,
    "slowbro": 45.9,
    "slowking": 78.2,
    "espeon": 23.0,
    "hatterene": 81.4,
    "aromatisse": 29.8,
    "farigiraf": 90.0,
    "sinistcha": 30.0,
}


def _champions_row(name: str, pct: float | None) -> dict[str, Any] | None:
    if pct is None:
        return None
    return {
        "name": name,
        "id": to_id(name),
        "common_moves": [{"name": "Trick Room", "pct": pct}],
        "featured_sets": [],
        "source": "championsbattledata",
    }


def _mock_champions_trick_room(name: str) -> dict[str, Any] | None:
    return _champions_row(name, _CHAMPIONS_TR_PCT.get(to_id(name)))


def _tr_draft(
    *,
    live_fetch: Any = None,
    showdown_fetch: Any = None,
    pool: list[str] | None = None,
    reference_compendium: Any = None,
    snap: dict[str, Any] | None = None,
) -> RoleConstructionDraft:
    snap = snap if snap is not None else load_snapshot()
    return construct_role_category(
        "trick_room_setter",
        TRICK_ROOM_SETTER_CRITERIA,
        pool if pool is not None else legal_species_pool(snap),
        snap=snap,
        live_fetch=live_fetch,
        showdown_fetch=showdown_fetch,
        reference_compendium=reference_compendium,
    )


def _members(draft: RoleConstructionDraft, tier: str) -> set[str]:
    return {c.species for c in draft.candidates if c.tier == tier}


def _find(draft: RoleConstructionDraft, species_id: str) -> CandidateEval:
    return next(c for c in draft.candidates if c.species_id == species_id)


# --- criterion 1: delivery cannot differentiate -----------------------------


def test_trick_room_priority_is_fixed_last():
    assert move_priority("trickroom") == -7


def test_no_ability_delivers_trick_room():
    """Nothing Drizzle-shaped exists for Trick Room, so delivery cannot rank.

    Persistent only extends an already-set Trick Room and Magician steals items;
    neither sets it. Pinned so a future setter ability fails here.
    """
    mentions = {
        aid
        for aid, entry in (load_abilities().get("abilities") or {}).items()
        if "trick room" in str(entry.get("description") or "").lower()
    }
    assert mentions == {"magician", "persistent"}, mentions


def test_delivery_class_identical_for_every_member():
    draft = _tr_draft()
    members = [c for c in draft.candidates if c.tier]
    assert members
    assert {c.delivery_class for c in members} == {"move_trick_room"}
    assert any("-7" in n for n in draft.notes)


# --- derived protection sets ------------------------------------------------


def test_flinch_denial_set_derived():
    ids = flinch_denial_ability_ids()
    assert {"armortail", "queenlymajesty", "innerfocus"} <= ids
    # Fake Out's flinch is a primary effect, so Shield Dust does not stop it.
    assert "shielddust" not in ids
    assert "steadfast" not in ids


def test_taunt_denial_set_derived():
    ids = taunt_denial_ability_ids()
    assert {"aromaveil", "oblivious"} <= ids
    # Blanket status denial covers Taunt without naming it.
    assert {"magicbounce", "goodasgold"} <= ids
    assert "sweetveil" not in ids


# --- tiering ---------------------------------------------------------------


def test_flinch_denial_lands_excellent():
    draft = _tr_draft(live_fetch=_mock_champions_trick_room)
    exc = _members(draft, "Excellent")
    assert {"Farigiraf", "Oranguru"} <= exc, draft.tiers
    fari = _find(draft, "farigiraf")
    assert fari.excellence_basis == "flinch_denial"
    assert fari.reinforce_class == "self_protection"
    assert "Armor Tail" in fari.criteria_notes["execution"]


def test_taunt_denial_lands_good_not_excellent():
    draft = _tr_draft(live_fetch=_mock_champions_trick_room)
    assert "Slowbro" in _members(draft, "Good")
    assert "Slowbro" not in _members(draft, "Excellent")
    slow = _find(draft, "slowbro")
    assert slow.excellence_basis == "taunt_denial"
    assert slow.reinforce_class == "self_protection"


def test_taunt_denial_with_snapshot_usage_stays_good():
    """July chaos lists Trick Room on Slowbro; taunt denial lands Good, not Excellent."""
    draft = _tr_draft()
    assert "Slowbro" in _members(draft, "Good")
    assert "Slowbro" not in _members(draft, "Excellent")


def test_ghost_typing_lands_good_on_fake_out_immunity():
    """Fake Out is Normal-type, so Ghost denies it without a teammate."""
    draft = _tr_draft(live_fetch=_mock_champions_trick_room)
    assert "Sinistcha" in _members(draft, "Good")
    sin = _find(draft, "sinistcha")
    assert sin.excellence_basis == "ghost_fakeout_immunity"
    assert sin.reinforce_class == "self_protection"
    assert "Fake Out cannot land" in sin.criteria_notes["execution"]
    # Narrower than the ability-based denial that earns Excellent.
    assert "Sinistcha" not in _members(draft, "Excellent")


def test_unprotected_member_is_acceptable_and_externally_dependent():
    live = {**_CHAMPIONS_TR_PCT, "gardevoirmega": 40.0}
    draft = _tr_draft(
        live_fetch=lambda n: _champions_row(n, live.get(to_id(n))),
    )
    mega = _find(draft, "gardevoirmega")
    assert mega.tier == "Acceptable"
    assert mega.excellence_basis == "unprotected"
    assert mega.reinforce_class == "none"
    assert "depends on a teammate" in mega.criteria_notes["execution"]


def test_flinch_denial_below_tr_floor_is_rejected():
    """Gallade-Mega TR 2.90% is below 22.5%; Inner Focus does not waive the floor."""
    draft = _tr_draft()
    rejected = {r.species_id for r in draft.considered_rejected}
    assert "gallademega" in rejected
    assert "Gallade-Mega" not in {c.species for c in draft.candidates if c.tier}


# --- bulk as a membership requirement ---------------------------------------


def test_bulk_floor_evicts_the_frail_and_binds_every_member():
    draft = _tr_draft(live_fetch=_mock_champions_trick_room)
    rej = next(r for r in draft.considered_rejected if r.species_id == "alakazam")
    assert f"bulk 195 below the {_TRICK_ROOM_BULK_FLOOR}" in rej.reason
    for c in draft.candidates:
        if c.tier and "bulk" in c.criteria_notes:
            assert int(c.criteria_notes["bulk"]) >= _TRICK_ROOM_BULK_FLOOR, c.species


def test_one_hit_absorption_waives_the_bulk_floor():
    """Disguise buys the same guaranteed turn to cast that raw bulk does."""
    snap = copy.deepcopy(load_snapshot())
    snap["species"]["mimikyu"]["base_stats"] |= {"hp": 1, "def": 1, "spd": 1}
    live = {**_CHAMPIONS_TR_PCT, "mimikyu": 30.0}.get
    draft = _tr_draft(
        snap=snap,
        live_fetch=lambda n: _champions_row(n, live(to_id(n))),
    )
    mimi = _find(draft, "mimikyu")
    assert int(mimi.criteria_notes["bulk"]) < _TRICK_ROOM_BULK_FLOOR
    assert mimi.tier, "Disguise should waive the floor"
    assert "absorbs one hit outright" in mimi.criteria_notes["execution"]


def test_every_admitted_excellent_and_good_member_is_usage_proven():
    draft = _tr_draft()
    for c in draft.candidates:
        if c.tier:
            assert c.criteria_notes["usage_proven"] == "True", c.species


def test_learnset_only_without_usage_or_protection_is_rejected():
    """Alakazam has the move but fails bulk and has no protection."""
    draft = _tr_draft()
    rejected = {r.species_id for r in draft.considered_rejected}
    assert "alakazam" in rejected
    assert "Alakazam" not in {c.species for c in draft.candidates if c.tier}


def test_secondary_role_alone_never_admits():
    """Talonflame has Tailwind usage and no Trick Room learnset."""
    draft = _tr_draft()
    assert "Talonflame" not in {c.species for c in draft.candidates if c.tier}


def test_tailwind_and_trick_room_excluded_from_secondary_allowlist():
    assert "tailwind" not in _TRICK_ROOM_SECONDARY_MOVES
    assert "trickroom" not in _TRICK_ROOM_SECONDARY_MOVES
    draft = _tr_draft()
    for c in draft.candidates:
        for t in c.claimed_traits:
            if t.criterion == "secondary_role":
                assert to_id(t.name) not in {"tailwind", "trickroom"}


# --- usage evidence precedence ---------------------------------------------


def test_champions_row_without_trick_room_does_not_suppress_showdown(monkeypatch):
    """CBD presence is not a Showdown blackout (Chimecho-shaped)."""
    from recommender.role_compendium import _delivery_usage_hits

    monkeypatch.setattr(
        "recommender.role_compendium.load_usage",
        lambda: {
            "ingame_doubles": {"species": {}},
            "showdown_vgc_mb": {"species": {}},
            "species": {},
        },
    )
    monkeypatch.setattr("recommender.role_compendium.showdown_species_map", lambda: {})
    cbd = {
        "name": "Chimecho",
        "id": "chimecho",
        "common_moves": [{"name": "Psychic", "pct": 40.0}],
        "source": "championsbattledata",
    }
    sd = {
        "name": "Chimecho",
        "id": "chimecho",
        "common_moves": [{"name": "Trick Room", "pct": 11.3}],
        "source": "smogon-chaos",
    }
    uctx = _UsageCtx(
        live_fetch=lambda _n: cbd,
        showdown_fetch=lambda _n: sd,
    )
    hits, source = _delivery_usage_hits(
        "Chimecho",
        {"trickroom"},
        uctx=uctx,
        sd_cache={},
        showdown_fetch=uctx.showdown_fetch,
    )
    assert hits == {"trickroom"}
    assert source == "showdown"


def test_forme_without_champions_row_falls_back_to_ladder():
    """No CBD row: Showdown is consulted. Snapshot TR sits below 22.5% → reject."""
    draft = _tr_draft()
    rejected = {r.species_id: r for r in draft.considered_rejected}
    assert "gardevoirmega" in rejected
    assert "Gardevoir-Mega" not in {c.species for c in draft.candidates if c.tier}


def test_champions_entry_never_returns_ladder_data():
    calls: list[str] = []

    def live(name: str) -> dict[str, Any] | None:
        calls.append(name)
        return {"name": name, "id": to_id(name), "source": "championsbattledata"}

    uctx = _UsageCtx(live_fetch=live, showdown_fetch=None)
    row = uctx.champions_entry("Cofagrigus")
    assert row is not None
    assert row["source"] == "championsbattledata"
    assert calls == ["Cofagrigus"]
    # Cached: no second fetch.
    uctx.champions_entry("Cofagrigus")
    assert calls == ["Cofagrigus"]


def test_mega_attribution_rejects_base_when_mega_also_delivers():
    """Slowbro/Slowbro-Mega: both deliver TR; base is discounted vs Mega."""
    draft = _tr_draft()
    rejected = {r.species_id: r for r in draft.considered_rejected}
    # July chaos: some bases now have independent TR (Gardevoir). Slowbro still
    # pairs with a delivering Mega — if the pair is discounted, base is out.
    members = {c.species for c in draft.candidates if c.tier}
    if "slowbro" in rejected:
        assert "discounted" in rejected["slowbro"].reason
        assert "Slowbro" not in members
    else:
        # Independent base usage kept; Mega may sit below the 22.5% floor.
        assert "Slowbro" in members


# --- the attribution guard, as a direct unit test ---------------------------


def _sd_pair(*, mega_has_move: bool) -> Any:
    def fetch(name: str) -> dict[str, Any] | None:
        sid = to_id(name)
        if sid == "gallademega":
            moves = [{"name": "Trick Room", "pct": 20.0}] if mega_has_move else []
            return {
                "name": "Gallade-Mega",
                "id": sid,
                "usage_pct": 4.0,
                "common_moves": moves,
                "source": "munchstats-showdown",
            }
        if sid == "gallade":
            return {
                "name": "Gallade",
                "id": sid,
                "usage_pct": 0.5,
                "common_moves": [{"name": "Trick Room", "pct": 11.0}],
                "source": "munchstats-showdown",
            }
        return None

    return fetch


def _attribution(monkeypatch, *, mega_has_move: bool) -> tuple[dict[str, bool], dict[str, str]]:
    monkeypatch.setattr("recommender.role_compendium.showdown_species_map", lambda: {})
    monkeypatch.setattr("recommender.role_compendium_usage.showdown_species_map", lambda: {})
    notes: list[str] = []
    pair_usage, pair_notes, _stone = _mega_usage_attribution(
        {"gallade": "Gallade", "gallademega": "Gallade-Mega"},
        frozenset({"trickroom"}),
        snap=load_snapshot(),
        uctx=_UsageCtx(live_fetch=None, showdown_fetch=None),
        sd_cache={},
        showdown_fetch=_sd_pair(mega_has_move=mega_has_move),
        notes=notes,
    )
    return pair_usage, pair_notes


def test_attribution_discounts_base_only_when_mega_delivers(monkeypatch):
    pair_usage, pair_notes = _attribution(monkeypatch, mega_has_move=True)
    assert pair_usage["gallade"] is False
    assert "discounted" in pair_notes["gallade"]
    assert pair_usage["gallademega"] is True


def test_attribution_keeps_base_when_mega_does_not_deliver(monkeypatch):
    """Same usage ratio, but the Mega runs a different strategy entirely."""
    pair_usage, pair_notes = _attribution(monkeypatch, mega_has_move=False)
    assert pair_usage["gallade"] is True
    assert "discounted" not in pair_notes.get("gallade", "")
    assert "independent base usage kept" in pair_notes["gallade"]
    assert pair_usage["gallademega"] is False


# --- critic ----------------------------------------------------------------


def test_critique_approves_real_draft():
    result = critique_role_ranking(_tr_draft())
    assert result.approved, result.flags


def _cand(
    species: str,
    sid: str,
    tier: str,
    *,
    basis: str = "usage_proven",
    reinforce: str = "none",
    notes: dict[str, str] | None = None,
    traits: list[ClaimedTrait] | None = None,
) -> CandidateEval:
    return CandidateEval(
        species=species,
        species_id=sid,
        tier=tier,
        delivery_class="move_trick_room",
        mechanism="Trick Room",
        criteria_notes=notes or {},
        claimed_traits=traits or [],
        reasoning="",
        reinforce_class=reinforce,
        excellence_basis=basis,
    )


def _synthetic(candidates: list[CandidateEval]) -> RoleConstructionDraft:
    tiers: dict[str, list[str]] = {}
    for c in candidates:
        tiers.setdefault(c.tier or "", []).append(c.species)
    return RoleConstructionDraft(
        category="trick_room_setter",
        sub_criteria={"condition": "", "kind": "trick_room_setter"},
        candidates=candidates,
        considered_rejected=[],
        tiers=tiers,
    )


def test_critique_tied_cluster_same_degree_across_tiers():
    draft = _synthetic(
        [
            _cand("Oranguru", "oranguru", "Excellent"),
            _cand("Musharna", "musharna", "Good"),
        ]
    )
    result = critique_role_ranking(draft)
    assert any(f.principle == "tied_cluster" for f in result.flags)


def test_real_draft_degrees_differ_across_tier_boundaries():
    draft = _tr_draft()
    by_tier: dict[str, set[tuple[str, str, str]]] = {}
    for c in draft.candidates:
        if not c.tier:
            continue
        key = (c.delivery_class, c.reinforce_class or "", c.excellence_basis or "")
        by_tier.setdefault(c.tier, set()).add(key)
    tiers = list(by_tier)
    for i, a in enumerate(tiers):
        for b in tiers[i + 1 :]:
            assert not (by_tier[a] & by_tier[b]), (a, b, by_tier[a] & by_tier[b])


def test_critique_self_consistency_on_silent_drop():
    prior = _synthetic([_cand("Oranguru", "oranguru", "Excellent")])
    draft = _synthetic([_cand("Musharna", "musharna", "Good")])
    result = critique_role_ranking(draft, reference_compendium=prior)
    assert any(f.principle == "self_consistency" for f in result.flags)


def test_critique_function_fit_self_only_ability_claimed_for_ally():
    draft = _synthetic(
        [
            _cand(
                "Oranguru",
                "oranguru",
                "Excellent",
                traits=[
                    ClaimedTrait(
                        name="Inner Focus",
                        criterion="secondary_role",
                        purpose_claimed="ally protection",
                    )
                ],
            )
        ]
    )
    result = critique_role_ranking(draft)
    assert any(f.principle == "function_fit" for f in result.flags)


def test_critique_execution_conflict_base_outranks_mega():
    draft = _synthetic(
        [
            _cand(
                "Gardevoir",
                "gardevoir",
                "Excellent",
                notes={
                    "usage_proven": "True",
                    "attribution": "showdown usage discounted (base 0.486%)",
                },
            ),
            _cand(
                "Gardevoir-Mega",
                "gardevoirmega",
                "Good",
                basis="learnset_only",
                notes={
                    "usage_proven": "False",
                    "attribution": "showdown form-separated usage",
                },
            ),
        ]
    )
    result = critique_role_ranking(draft)
    assert any(f.principle == "execution_conflict" for f in result.flags)


# --- pool + persistence ----------------------------------------------------


def test_legal_pool_bounds():
    snap = load_snapshot()
    pool = [n for n in legal_species_pool(snap) if to_id(n) != "farigiraf"]
    draft = _tr_draft(pool=pool)
    assert "Farigiraf" not in {c.species for c in draft.candidates if c.tier}


def test_rebuild_writes_expected_filename(tmp_path: Path):
    result = rebuild_role_category(
        "trick_room_setter",
        TRICK_ROOM_SETTER_CRITERIA,
        roles_dir=tmp_path,
        live_fetch=None,
        showdown_fetch=None,
    )
    assert result.status == "approved", result.critique.flags
    assert result.path is not None
    assert Path(result.path).name == "trick_room_setter.v1.json"
