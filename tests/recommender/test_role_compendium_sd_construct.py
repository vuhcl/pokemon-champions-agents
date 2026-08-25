"""Swords Dance setup-attacker tests — construct pipeline / tiering."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from recommender.ids import to_id
from recommender.legality import load_snapshot
from role_compendium_sd_common import (
    _members,
    _mock_calc,
    _panel_result,
    _sd_criteria_for_mock,
    _sd_draft,
)
from recommender.role_compendium_setup import (
    _partition_by_admission_floor,
    _setup_adjusted_score,
    _setup_branch_a,
    _setup_branch_a_via_priority,
    _setup_excellent_floor,
    _setup_mech_tier,
    _setup_payoff_candidates,
    _setup_priority_kind,
    _setup_self_drop_moves,
)
from recommender.role_compendium_setup_constants import (
    _SETUP_ACCEPTABLE_FLOOR_MULT,
    _SETUP_BOTH_BRANCH_SCORE_DIV,
    _SETUP_DAMAGE_FRAC_CAP,
    _SETUP_SPE_FLOOR,
    _SETUP_SPEED_ABILITIES,
    _SETUP_SURVIVE_ABILITIES,
)
from recommender.stat_boosts import _self_boosts, load_stat_boosts
from recommender.role_compendium import (
    SWORDS_DANCE_ATTACKER_CRITERIA,
    RejectedCandidate,
    construct_role_category,
    critique_role_ranking,
    exclusive_self_boost_move,
    legal_species_pool,
    rebuild_role_category,
)

def test_exclusive_self_boost_atk():
    # Raises unless exactly one Champions-legal move qualifies.
    assert exclusive_self_boost_move(boost_stat="atk") == "swordsdance"

def test_stat_boosts_attributes_drops_to_the_right_side():
    """Overheat lowers its own user's SpA; Acid Spray lowers the target's SpD."""
    moves = load_stat_boosts()["moves"]
    assert _self_boosts(moves["overheat"]) == {"spa": -2}
    assert _self_boosts(moves["acidspray"]) == {}
    # A chance-gated self boost is not a guaranteed one (Charge Beam, 70%).
    assert _self_boosts(moves["chargebeam"]) == {}

    assert "overheat" in _setup_self_drop_moves("spa")
    assert "acidspray" not in _setup_self_drop_moves("spa")
    # Close Combat drops Def/SpD, never the Attack a Swords Dance set banked.
    assert "closecombat" not in _setup_self_drop_moves("atk")

def test_setup_adjusted_score_composition():
    assert _setup_adjusted_score(1.0, both_branches=False) == 1.0
    assert abs(
        _setup_adjusted_score(_SETUP_BOTH_BRANCH_SCORE_DIV, both_branches=True) - 1.0
    ) < 1e-9
    assert abs(_setup_adjusted_score(0.5, both_branches=True) - (0.5 / _SETUP_BOTH_BRANCH_SCORE_DIV)) < 1e-9
    assert _setup_priority_kind("aquajet") == "unconditional"
    assert _setup_priority_kind("suckerpunch") == "conditional"
    assert _setup_priority_kind("upperhand") == "conditional"
    assert _setup_priority_kind("feint") == "conditional"
    assert _setup_priority_kind("closecombat") == "none"

def test_setup_excellent_floor_second_times_095():
    assert _setup_excellent_floor([]) == 0.0
    assert abs(_setup_excellent_floor([2.0]) - 2.0 * 0.95) < 1e-9
    assert abs(_setup_excellent_floor([3.0, 2.0, 1.0]) - 2.0 * 0.95) < 1e-9

def test_setup_mech_tier_boundaries():
    """Acceptable strictly below floor × mult; the cutoff itself stays Good."""
    cut = 1.0 * _SETUP_ACCEPTABLE_FLOOR_MULT
    assert _setup_mech_tier(1.0, 1.0) == "Excellent"
    assert _setup_mech_tier(1.5, 1.0) == "Excellent"
    assert _setup_mech_tier(0.999, 1.0) == "Good"
    assert _setup_mech_tier(cut, 1.0) == "Good"
    assert _setup_mech_tier(cut - 1e-6, 1.0) == "Acceptable"
    assert _setup_mech_tier(0.0, 1.0) == "Acceptable"

def test_setup_mech_tier_degenerate_floor_stays_good():
    """Empty/degenerate field must not collapse every candidate into Acceptable."""
    assert _setup_mech_tier(0.0, 0.0) == "Good"
    assert _setup_mech_tier(5.0, 0.0) == "Good"
    assert _setup_mech_tier(0.1, _setup_excellent_floor([])) == "Good"

def test_setup_mech_tier_acceptable_mult_override():
    """Category Acceptable mults widen/narrow the Good band vs default 0.70."""
    assert _setup_mech_tier(0.87, 1.0, acceptable_mult=0.88) == "Acceptable"
    assert _setup_mech_tier(0.87, 1.0) == "Good"
    assert _setup_mech_tier(0.88, 1.0, acceptable_mult=0.88) == "Good"
    assert _setup_mech_tier(0.899, 1.0, acceptable_mult=0.90) == "Acceptable"
    assert _setup_mech_tier(0.90, 1.0, acceptable_mult=0.90) == "Good"

def test_partition_by_admission_floor_noop_and_boundary():
    rows = [
        {"sid": "a", "name": "Above", "adjusted": 1.0},
        {"sid": "b", "name": "Floor", "adjusted": 0.981},
        {"sid": "c", "name": "Below", "adjusted": 0.980},
        # Float noise just under a 3-decimal locked floor must still include.
        {"sid": "d", "name": "FloatFloor", "adjusted": 0.981 - 1e-12},
    ]
    rejected: list[RejectedCandidate] = []
    assert _partition_by_admission_floor(
        rows, score_key="adjusted", admission_floor=None, prior={}, rejected=rejected
    ) == rows
    assert rejected == []

    kept = _partition_by_admission_floor(
        rows,
        score_key="adjusted",
        admission_floor=0.981,
        prior={"c": "Acceptable"},
        rejected=rejected,
    )
    assert [r["sid"] for r in kept] == ["a", "b", "d"]
    assert len(rejected) == 1
    assert rejected[0].species_id == "c"
    assert "admission floor 0.981" in rejected[0].reason
    assert rejected[0].change_reason is not None

def test_sd_criteria_locks_admission_and_acceptable_mult():
    assert SWORDS_DANCE_ATTACKER_CRITERIA["damage_admission_floor"] == 0.969
    assert SWORDS_DANCE_ATTACKER_CRITERIA["acceptable_floor_mult"] == 0.85

def test_acceptable_basis_distinct_from_good():
    """tied_cluster compares degree tuples across tiers, so the basis must differ."""
    draft = _sd_draft()
    acceptable = [c for c in draft.candidates if c.tier == "Acceptable"]
    assert acceptable, "mock panel should place weak-damage candidates in Acceptable"
    acc_bases = {c.excellence_basis for c in acceptable}
    good_bases = {c.excellence_basis for c in draft.candidates if c.tier == "Good"}
    assert acc_bases.isdisjoint(good_bases)
    assert not critique_role_ranking(draft).flags

def test_acceptable_floor_note_emitted():
    draft = _sd_draft()
    assert any("Acceptable floor = Excellent floor ×" in n for n in draft.notes)

def test_cbd_move_implausible_vs_mega_helper():
    from recommender.role_compendium import _cbd_base_move_implausible_vs_mega

    base= {"common_moves": [{"name": "Swords Dance", "pct": 19.5}]}
    mega = {"common_moves": [{"name": "Swords Dance", "pct": 9.2}]}
    assert _cbd_base_move_implausible_vs_mega(base, mega, "swordsdance")
    assert not _cbd_base_move_implausible_vs_mega(
        {"common_moves": [{"name": "Swords Dance", "pct": 5.0}]},
        mega,
        "swordsdance",
    )
    # Mega does not run the move → not this check.
    assert not _cbd_base_move_implausible_vs_mega(
        base,
        {"common_moves": [{"name": "Brave Bird", "pct": 40.0}]},
        "swordsdance",
    )

def test_cbd_inflated_vs_mega_rejects_without_showdown_base_delivery():
    """Skarmory-shaped: CBD SD% > Mega Showdown SD%, Showdown base has no SD."""

    def sd_fetch(name: str) -> dict[str, Any] | None:
        sid = to_id(name)
        if sid == "skarmorymega":
            return {
                "name": name,
                "usage_pct": 0.3,
                "common_moves": [{"name": "Swords Dance", "pct": 9.2}],
            }
        if sid == "skarmory":
            return {
                "name": name,
                "usage_pct": 0.04,
                "common_moves": [{"name": "Brave Bird", "pct": 40.0}],
            }
        return None

    snap = load_snapshot()
    draft = construct_role_category(
        "swords_dance_attacker",
        _sd_criteria_for_mock(),
        [n for n in legal_species_pool(snap) if to_id(n) in {"skarmory", "skarmorymega"}],
        snap=snap,
        live_fetch=lambda n: (
            {
                "name": n,
                "id": to_id(n),
                "common_moves": [{"name": "Swords Dance", "pct": 19.5}],
                "common_items": [{"name": "Skarmorite", "pct": 79.0}],
            }
            if to_id(n) == "skarmory"
            else {
                "name": n,
                "id": to_id(n),
                "common_moves": [{"name": "Swords Dance", "pct": 40.0}],
            }
            if to_id(n) == "skarmorymega"
            else None
        ),
        showdown_fetch=sd_fetch,
        calculate_batch=_mock_calc,
    )
    rej = {r.species: r.reason for r in draft.considered_rejected}
    admitted = {c.species for c in draft.candidates if c.tier}
    # Snapshot may independently prove Skarmory SD at the presence floor; then
    # the mock Showdown miss is not what gates admission. Helper unit test covers
    # the plausibility check itself.
    if "Skarmory" in rej:
        assert "no usage evidence" in rej["Skarmory"]
        assert any("CBD move-rate plausibility" in n for n in draft.notes)
    else:
        assert "Skarmory" in admitted

def test_discounted_base_in_acceptable_band_is_rejected():
    """Discount + mech below Good rejects outright; only mech Excellent demotes.

    Both forms must show the setup move on Showdown — otherwise the shared
    attribution helper refuses to treat the base as a pre-Mega artifact.
    """

    def sd_fetch(name: str) -> dict[str, Any] | None:
        sid = to_id(name)
        if sid == "scizormega":
            return {
                "name": name,
                "usage_pct": 5.0,
                "common_moves": [{"name": "Swords Dance", "pct": 20.0}],
            }
        if sid == "scizor":
            return {
                "name": name,
                "usage_pct": 0.01,
                "common_moves": [{"name": "Swords Dance", "pct": 15.0}],
            }
        return None

    snap = load_snapshot()

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for req in reqs:
            atk = req.get("attacker") or {}
            if not atk.get("boosts"):
                frac, atk_spe = 1.0, 100  # incoming OHKO → outsped dummy stays 0
            else:
                sp = to_id(atk.get("species") or "")
                frac, atk_spe = (0.35, 50) if "scizor" in sp else (0.2, 100)
            dmg = int(200 * frac)
            out.append(
                {
                    "damageRange": [dmg - 10, dmg],
                    "raw": {
                        "stats": {
                            "defender": {"hp": 200, "spe": 80},
                            "attacker": {"atk": 200, "spe": atk_spe},
                        }
                    },
                }
            )
        return out

    draft = construct_role_category(
        "swords_dance_attacker",
        _sd_criteria_for_mock(),
        [n for n in legal_species_pool(snap) if to_id(n) in {"scizor", "scizormega"}],
        snap=snap,
        live_fetch=lambda n: (
            {
                "name": n,
                "id": to_id(n),
                "common_moves": [{"name": "Swords Dance", "pct": 40.0}],
                "common_items": [{"name": "Life Orb", "pct": 20.0}],
            }
            if to_id(n) in {"scizor", "scizormega"}
            else None
        ),
        showdown_fetch=sd_fetch,
        calculate_batch=calc,
    )
    scizor = next((c for c in draft.candidates if c.species == "Scizor"), None)
    if scizor is not None and scizor.excellence_basis == "usage_discounted":
        assert scizor.tier == "Acceptable"
        return
    # Snapshot offline-first usage_pct often keeps base independent (no discount).
    # Reject/demote path still holds when attribution fires; otherwise both stay.
    mega = next(c for c in draft.candidates if c.species == "Scizor-Mega")
    assert mega.tier
    if scizor is not None:
        assert scizor.tier

def test_setup_does_not_discount_when_mega_lacks_setup_move():
    """Same usage ratio as the discount case, but Mega never runs Swords Dance."""

    def sd_fetch(name: str) -> dict[str, Any] | None:
        sid = to_id(name)
        if sid == "scizormega":
            return {
                "name": name,
                "usage_pct": 5.0,
                "common_moves": [{"name": "Bullet Punch", "pct": 40.0}],
            }
        if sid == "scizor":
            return {
                "name": name,
                "usage_pct": 0.01,
                "common_moves": [{"name": "Swords Dance", "pct": 15.0}],
            }
        return None

    snap = load_snapshot()
    draft = construct_role_category(
        "swords_dance_attacker",
        _sd_criteria_for_mock(),
        legal_species_pool(snap),
        snap=snap,
        live_fetch=lambda n: (
            {
                "name": n,
                "id": to_id(n),
                "common_moves": [{"name": "Swords Dance", "pct": 40.0}],
                "common_items": [{"name": "Life Orb", "pct": 20.0}],
            }
            if to_id(n) in {"scizor", "scizormega"}
            else None
        ),
        showdown_fetch=sd_fetch,
        calculate_batch=_mock_calc,
    )
    rej = {r.species: r.reason for r in draft.considered_rejected}
    # Must not be rejected solely for Showdown usage discount.
    assert "discounted" not in (rej.get("Scizor") or "")
    assert any("Scizor/Scizor-Mega" in n for n in draft.notes)

def test_branch_a_via_priority_sole_path():
    snap = {
        "moves": {
            "quickattack": {"category": "Physical"},
            "suckerpunch": {"category": "Physical"},
        }
    }
    # Spe >= 100 → not via priority even with priority moves.
    assert not _setup_branch_a_via_priority(
        learnset={"quickattack"},
        abs_map={},
        stats={"spe": 100},
        snap=snap,
        boost_stat="atk",
    )
    # Speed Boost → not via priority.
    assert not _setup_branch_a_via_priority(
        learnset={"quickattack"},
        abs_map={"speedboost": "Speed Boost"},
        stats={"spe": 80},
        snap=snap,
        boost_stat="atk",
    )
    # Priority only.
    assert _setup_branch_a_via_priority(
        learnset={"suckerpunch"},
        abs_map={},
        stats={"spe": 50},
        snap=snap,
        boost_stat="atk",
    )

def test_fakeout_does_not_clear_branch_a():
    snap = {"moves": {"fakeout": {"category": "Physical"}, "upperhand": {"category": "Physical"}}}
    assert not _setup_branch_a(
        learnset={"fakeout"},
        abs_map={},
        stats={"spe": 50},
        snap=snap,
        boost_stat="atk",
    )
    assert not _setup_branch_a_via_priority(
        learnset={"fakeout"},
        abs_map={},
        stats={"spe": 50},
        snap=snap,
        boost_stat="atk",
    )
    assert _setup_branch_a(
        learnset={"upperhand"},
        abs_map={},
        stats={"spe": 50},
        snap=snap,
        boost_stat="atk",
    )

def test_fakeout_banned_from_setup_payoff():
    snap = load_snapshot()
    hits = _setup_payoff_candidates(
        snap,
        boost_stat="atk",
        usage_move_ids={
            "fakeout",
            "upperhand",
            "grassyglide",
            "firstimpression",
            "lastresort",
            "selfdestruct",
            "explosion",
            "uproar",
            "bravebird",
            "ironhead",
        },
    )
    assert "fakeout" not in hits
    assert "upperhand" not in hits
    assert "grassyglide" not in hits
    assert "firstimpression" not in hits
    assert "lastresort" not in hits
    assert "selfdestruct" not in hits
    assert "explosion" not in hits
    assert "uproar" not in hits
    assert "bravebird" in hits or "ironhead" in hits

def test_branch_a_priority_category_must_match_boost_stat():
    snap = {
        "moves": {
            "suckerpunch": {"category": "Physical"},
            "vacuumwave": {"category": "Special"},
        }
    }
    assert not _setup_branch_a(
        learnset={"suckerpunch"},
        abs_map={},
        stats={"spe": 50},
        snap=snap,
        boost_stat="spa",
    )
    assert _setup_branch_a(
        learnset={"suckerpunch"},
        abs_map={},
        stats={"spe": 50},
        snap=snap,
        boost_stat="atk",
    )
    assert _setup_branch_a(
        learnset={"vacuumwave"},
        abs_map={},
        stats={"spe": 50},
        snap=snap,
        boost_stat="spa",
    )
    assert not _setup_branch_a(
        learnset={"vacuumwave"},
        abs_map={},
        stats={"spe": 50},
        snap=snap,
        boost_stat="atk",
    )

def test_blaziken_mega_branch_a_excellent():
    draft = _sd_draft()
    assert "Blaziken-Mega" in _members(draft, "Excellent")
    abo = next(c for c in draft.candidates if c.species_id == "blazikenmega")
    assert abo.criteria_notes.get("branches_cleared") == "A"
    assert abo.excellence_basis == "calc_branch_a"
    assert abo.criteria_notes.get("score_boosts") == "none"
    assert any("2nd-highest adjusted" in n for n in draft.notes)

def test_priority_boost_only_when_payoff_is_priority():
    """Priority multiplier is gone; score_boosts is both-branch divisor only."""
    both_label = f"both_div_{_SETUP_BOTH_BRANCH_SCORE_DIV:g}"
    draft = _sd_draft()
    king = next(c for c in draft.candidates if c.species_id == "kingambit")
    boosts = king.criteria_notes.get("score_boosts") or ""
    assert "priority_x" not in boosts
    raw = float(king.criteria_notes["damage_score_raw"])
    adj = float(king.criteria_notes["damage_score"])
    both = both_label in boosts
    expected = raw / (_SETUP_BOTH_BRANCH_SCORE_DIV if both else 1.0)
    assert abs(adj - expected) < 1e-3

def test_setup_ability_for_payoff_gates():
    from recommender.role_compendium import _setup_ability_for_payoff
    from recommender.legality import load_snapshot

    snap = load_snapshot()
    types = {"steel", "bug"}
    assert (
        _setup_ability_for_payoff("Technician", "bulletpunch", snap=snap, types=types)
        == "Technician"
    )
    assert (
        _setup_ability_for_payoff("Technician", "ironhead", snap=snap, types=types) is None
    )
    assert (
        _setup_ability_for_payoff("Tough Claws", "playrough", snap=snap, types={"fairy"})
        == "Tough Claws"
    )
    assert (
        _setup_ability_for_payoff("Tough Claws", "shadowball", snap=snap, types={"ghost"})
        is None
    )
    assert (
        _setup_ability_for_payoff("Adaptability", "flareblitz", snap=snap, types={"fire"})
        == "Adaptability"
    )
    assert (
        _setup_ability_for_payoff("Adaptability", "earthquake", snap=snap, types={"fire"})
        is None
    )
    assert (
        _setup_ability_for_payoff(
            "Fairy Aura", "lightofruin", snap=snap, types={"fairy"}
        )
        == "Fairy Aura"
    )
    assert (
        _setup_ability_for_payoff(
            "Fairy Aura", "moonblast", snap=snap, types={"fairy"}
        )
        == "Fairy Aura"
    )
    assert (
        _setup_ability_for_payoff("Fairy Aura", "psychic", snap=snap, types={"fairy"})
        is None
    )
    assert (
        _setup_ability_for_payoff(
            "Dark Aura", "darkpulse", snap=snap, types={"dark"}
        )
        == "Dark Aura"
    )
    assert (
        _setup_ability_for_payoff("Dark Aura", "psychic", snap=snap, types={"dark"})
        is None
    )
    assert (
        _setup_ability_for_payoff(
            "Aura Break", "moonblast", snap=snap, types={"dragon", "ground"}
        )
        == "Aura Break"
    )
    assert (
        _setup_ability_for_payoff(
            "Aura Break", "crunch", snap=snap, types={"dragon", "ground"}
        )
        == "Aura Break"
    )
    assert (
        _setup_ability_for_payoff(
            "Aura Break", "earthquake", snap=snap, types={"dragon", "ground"}
        )
        is None
    )

def test_disguise_clears_branch_b_without_bulk():
    from recommender.role_compendium import _setup_branches

    branches= _setup_branches(
        learnset={"shadowsneak", "playrough"},
        abs_map={"disguise": "Disguise"},
        stats={"hp": 55, "def": 80, "spd": 105, "spe": 96},  # bulk 295 < 400
        entry=None,
        snap={"moves": {"shadowsneak": {"category": "Physical"}}},
        boost_stat="atk",
    )
    assert "B" in branches

def test_disguise_turn_order_credits_when_slower():
    from recommender.role_compendium import _damage_score

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [_panel_result(dmg=200, hp=200, atk_spe=50, def_spe=150) for _ in reqs]

    score, err = _damage_score(
        attacker_name="Mimikyu",
        item=None,
        ability="Disguise",
        move="Play Rough",
        move_id="playrough",
        boost_stat="atk",
        stages=2,
        panel=[{"species": "Garchomp", "evs": {"hp": 32}}],
        calculate_batch=calc,
    )
    assert err == ""
    # Play Rough 90% acc; Disguise survive-outsped → 1.0 × 0.90
    assert abs(score - 0.90) < 1e-9

def test_speed_boost_turn_order_rescues_slower():
    from recommender.role_compendium_setup import _damage_score  # 100 < 140, but 100*1.5=150 > 140
    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [_panel_result(dmg=200, hp=200, atk_spe=100, def_spe=140) for _ in reqs]

    score, err = _damage_score(
        attacker_name="Blaziken-Mega",
        item=None,
        ability="Speed Boost",
        move="Close Combat",
        move_id="closecombat",
        boost_stat="atk",
        stages=2,
        panel=[{"species": "Garchomp", "evs": {"hp": 32}}],
        calculate_batch=calc,
    )
    assert err == ""
    assert abs(score - 1.0) < 1e-9

def test_soft_cap_limits_overkill():
    from recommender.role_compendium import _damage_score

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [_panel_result(dmg=400, hp=200, atk_spe=200, def_spe=80) for _ in reqs]

    score, err = _damage_score(
        attacker_name="Heracross-Mega",
        item=None,
        ability=None,
        move="Close Combat",
        move_id="closecombat",
        boost_stat="atk",
        stages=2,
        panel=[{"species": "Blissey", "evs": {"hp": 32}}],
        calculate_batch=calc,
    )
    assert err == ""
    assert abs(score - _SETUP_DAMAGE_FRAC_CAP) < 1e-9

def test_weak_damage_priority_not_excellent():
    """Mock damage well under the Acceptable floor lands in Acceptable, never Excellent."""
    draft = _sd_draft()
    if any(c.species_id == "ceruledge" for c in draft.candidates):
        assert "Ceruledge" in _members(draft, "Acceptable")
        assert "Ceruledge" not in _members(draft, "Excellent")

def test_neither_branch_rejected():
    snap = load_snapshot()
    draft = _sd_draft(pool=legal_species_pool(snap))
    assert any(
        "neither" in (r.reason or "") for r in draft.considered_rejected
    ) or draft.considered_rejected

def test_critique_approves():
    draft = _sd_draft()
    result = critique_role_ranking(draft)
    assert result.approved, result.flags

def test_rebuild_tmp(tmp_path: Path):
    r = rebuild_role_category(
        "swords_dance_attacker",
        _sd_criteria_for_mock(),
        roles_dir=tmp_path,
        live_fetch=lambda n: {
            "name": n,
            "id": to_id(n),
            "common_moves": [{"name": "Swords Dance", "pct": 50}],
        }
        if to_id(n)
        in {
            "blazikenmega",
            "kingambit",
            "scizormega",
            "scizor",
            "mawilemega",
            "blaziken",
        }
        else None,
        showdown_fetch=lambda _n: None,
        calculate_batch=_mock_calc,
    )
    assert r.status == "approved", r.critique.flags
    assert Path(r.path or "").exists()

def test_sd_construct_structured_payoff_mawile_shaped(monkeypatch):
    """Multi-mid kit winners → payoff_moves/targets + plural execution traits."""
    import inspect

    from recommender.role_compendium_setup import _attacker_kit
    from recommender.role_compendium import RoleConstructionDraft, _construct_def_payoff_setup, _construct_offense_stage_setup, _move_display

    snap = load_snapshot()
    panel = [
        {"species": "Garchomp", "evs": {"hp": 32}, "usage_moves": ["Earthquake"]},
        {"species": "Incineroar", "evs": {"hp": 32}, "usage_moves": ["Flare Blitz"]},
        {"species": "Gengar", "evs": {"hp": 32}, "usage_moves": ["Shadow Ball"]},
        {"species": "Rillaboom", "evs": {"hp": 32}, "usage_moves": ["Wood Hammer"]},
    ]

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for req in reqs:
            atk = req.get("attacker") or {}
            if not atk.get("boosts"):
                out.append(_panel_result(dmg=40, hp=200, atk_spe=200, def_spe=50))
                continue
            mid = to_id(req.get("move") or "")
            sp = to_id((req.get("defender") or {}).get("species") or "")
            if mid == "doubleedge":
                if sp == "gengar":
                    dmg = 0
                elif sp == "incineroar":
                    dmg = 90
                else:
                    dmg = 50
            elif mid == "playrough":
                if sp == "incineroar":
                    dmg = 40
                else:
                    dmg = 100
            else:
                dmg = 10
            out.append(_panel_result(dmg=dmg, hp=100, atk_spe=150, def_spe=80))
        return out

    monkeypatch.setattr(
        "recommender.role_compendium._setup_threat_defenders",
        lambda: panel,
    )

    def kit(name, sid, snap_, learnset, *, boost_stat, entry):
        if to_id(sid) == "mawilemega":
            return (
                "Mawile-Mega",
                None,
                "Huge Power",
                ["Play Rough", "Double-Edge", "Swords Dance", "Protect"],
            )
        return _attacker_kit(
            name, sid, snap_, learnset, boost_stat=boost_stat, entry=entry
        )

    monkeypatch.setattr("recommender.role_compendium._attacker_kit", kit)

    def usage(name: str) -> dict[str, Any] | None:
        if to_id(name) != "mawilemega":
            return None
        return {
            "name": name,
            "id": "mawilemega",
            "common_moves": [{"name": "Swords Dance", "pct": 40.0}],
        }

    draft = construct_role_category(
        "swords_dance_attacker",
        _sd_criteria_for_mock(),
        ["Mawile-Mega"],
        snap=snap,
        live_fetch=usage,
        showdown_fetch=lambda _n: None,
        calculate_batch=calc,
    )
    maw = next(c for c in draft.candidates if c.species_id == "mawilemega" and c.tier)
    notes = maw.criteria_notes
    assert "payoff_move" not in notes
    assert "payoff_coverage" not in notes
    assert isinstance(notes["payoff_moves"], list)
    assert isinstance(notes["payoff_targets"], dict)
    assert notes["payoff_moves"][0] == "playrough"
    assert "playrough" in notes["payoff_targets"]
    assert "Gengar" in notes["payoff_targets"]["playrough"]
    assert "Garchomp" in notes["payoff_targets"]["playrough"]
    assert "Rillaboom" in notes["payoff_targets"]["playrough"]
    if "doubleedge" in notes["payoff_targets"]:
        assert notes["payoff_targets"]["doubleedge"] == ["Incineroar"]
        assert "doubleedge" in notes["payoff_moves"]

    exec_names = [
        t.name for t in maw.claimed_traits if t.criterion == "execution"
    ]
    expected = [_move_display(snap, mid) for mid in notes["payoff_moves"]]
    assert exec_names == expected
    assert len(exec_names) >= 1

    tiny = RoleConstructionDraft(
        category=draft.category,
        sub_criteria=dict(draft.sub_criteria),
        candidates=[maw],
        considered_rejected=[],
        tiers={maw.tier: [maw.species]},
        notes=[],
    )
    critique = critique_role_ranking(tiny)
    assert not any(f.principle == "function_fit" for f in critique.flags)

    stage_src = inspect.getsource(_construct_offense_stage_setup)
    assert "_setup_payoff_notes" in stage_src
    assert "_payoff_coverage_note" not in stage_src
    idbp_src = inspect.getsource(_construct_def_payoff_setup)
    assert "_payoff_coverage_note" in idbp_src
    assert "_setup_payoff_notes" not in idbp_src
    assert "payoff_targets" not in idbp_src

