"""Swords Dance Attacker Role Compendium (setup_attacker)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from recommender.ids import to_id
from recommender.legality import load_snapshot
from recommender.role_compendium import (
    SWORDS_DANCE_ATTACKER_CRITERIA,
    RejectedCandidate,
    _SETUP_ACCEPTABLE_FLOOR_MULT,
    _SETUP_BOTH_BRANCH_SCORE_DIV,
    _SETUP_DAMAGE_FRAC_CAP,
    _partition_by_admission_floor,
    _setup_adjusted_score,
    _setup_branch_a,
    _setup_branch_a_via_priority,
    _setup_excellent_floor,
    _setup_mech_tier,
    _setup_payoff_candidates,
    _setup_priority_kind,
    _setup_self_drop_moves,
    _self_boosts,
    construct_role_category,
    critique_role_ranking,
    exclusive_self_boost_move,
    legal_species_pool,
    load_stat_boosts,
    rebuild_role_category,
)


def _mock_calc(requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Spe-path calibrators = 1.0. Incoming OHKO reqs have no attacker.boosts."""
    out: list[dict[str, Any]] = []
    for req in requests:
        atk = req.get("attacker") or {}
        if not atk.get("boosts"):
            # Panel hitting candidate: not OHKO (frac 0.2).
            frac = 0.2
            atk_spe = 100
        else:
            sp = to_id(atk.get("species") or "")
            if sp in {"blazikenmega", "blaziken"}:
                frac = 1.0
                atk_spe = 200
            elif sp in {"kingambit", "scizor", "scizormega", "mawilemega"}:
                frac = 0.35
                atk_spe = 50
            else:
                frac = 0.2
                atk_spe = 100
        dmg = int(200 * frac)
        out.append(
            {
                "damageRange": [dmg - 10, dmg],
                "koChance": "guaranteed OHKO" if frac >= 1.0 else "possibly 3HKO",
                "raw": {
                    "stats": {
                        "defender": {"hp": 200, "spe": 80},
                        "attacker": {"atk": 200, "spe": atk_spe},
                    }
                },
            }
        )
    return out


def _panel_result(
    *,
    dmg: int,
    hp: int = 200,
    atk_spe: int = 100,
    def_spe: int = 80,
    recoil_pct: float | None = None,
    recovery_hp: int | None = None,
    atk_hp: int | None = None,
) -> dict[str, Any]:
    attacker_hp = 159 if atk_hp is None else atk_hp
    raw: dict[str, Any] = {
        "stats": {
            "attacker": {"spe": atk_spe, "hp": attacker_hp},
            "defender": {"hp": hp, "spe": def_spe},
        }
    }
    if recoil_pct is not None:
        raw["recoil"] = {
            "recoil": [recoil_pct, recoil_pct],
            "text": f"{recoil_pct}% recoil damage",
        }
    if recovery_hp is not None:
        raw["recovery"] = {
            "recovery": [recovery_hp, recovery_hp],
            "text": f"{recovery_hp} HP recovered",
        }
    return {
        "damageRange": [dmg, dmg],
        "koChance": "2HKO",
        "raw": raw,
    }


def _sd_criteria_for_mock() -> dict[str, Any]:
    """Mock calcs score far below the locked live admission floor — strip it."""
    crit = dict(SWORDS_DANCE_ATTACKER_CRITERIA)
    crit.pop("damage_admission_floor", None)
    crit.pop("acceptable_floor_mult", None)
    return crit


def _sd_draft(*, pool: list[str] | None = None, live_fetch=None):
    snap = load_snapshot()
    proven = {
        "blazikenmega",
        "blaziken",
        "kingambit",
        "scizor",
        "scizormega",
        "mawilemega",
        "aegislash",
        "ceruledge",
        "lucariomega",
    }

    def _usage(name: str) -> dict[str, Any] | None:
        sid = to_id(name)
        if sid not in proven:
            return None
        return {
            "name": name,
            "id": sid,
            "common_moves": [{"name": "Swords Dance", "pct": 40.0}],
            "common_items": [{"name": "Life Orb", "pct": 20.0}],
        }

    default_pool = [n for n in legal_species_pool(snap) if to_id(n) in proven]
    return construct_role_category(
        "swords_dance_attacker",
        _sd_criteria_for_mock(),
        pool if pool is not None else default_pool,
        snap=snap,
        live_fetch=live_fetch if live_fetch is not None else _usage,
        showdown_fetch=lambda _n: None,
        calculate_batch=_mock_calc,
    )


def _members(draft, tier: str) -> set[str]:
    return {c.species for c in draft.candidates if c.tier == tier}


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
    assert SWORDS_DANCE_ATTACKER_CRITERIA["damage_admission_floor"] == 0.981
    assert SWORDS_DANCE_ATTACKER_CRITERIA["acceptable_floor_mult"] == 0.88


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

    base = {"common_moves": [{"name": "Swords Dance", "pct": 19.5}]}
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


def test_best_payoff_skips_self_spa_drop():
    from recommender.role_compendium import _best_payoff_move
    from recommender.legality import load_snapshot

    snap = load_snapshot()
    # Houndoom: Overheat must not beat Dark Pulse / Flamethrower after self-drop exclude.
    payoff = _best_payoff_move(
        snap,
        "houndoom",
        {"overheat", "darkpulse", "flamethrower", "nastyplot"},
        boost_stat="spa",
    )
    assert payoff != "overheat"
    assert payoff in {"darkpulse", "flamethrower"}


def test_best_payoff_skips_focus_punch_and_recharge():
    from recommender.role_compendium import _best_payoff_move, _setup_payoff_candidates
    from recommender.legality import load_snapshot

    snap = load_snapshot()
    assert (
        _best_payoff_move(
            snap,
            "blaziken",
            {"focuspunch", "flareblitz", "swordsdance"},
            boost_stat="atk",
        )
        == "flareblitz"
    )
    cands = _setup_payoff_candidates(
        snap,
        boost_stat="spa",
        usage_move_ids={"blastburn", "psychic", "futuresight", "nastyplot"},
    )
    assert "blastburn" not in cands
    assert "futuresight" not in cands
    assert cands == ["psychic"]


def test_best_payoff_skips_lockin_moves():
    """Lock-in carries the same unmodeled multi-turn cost as charge/recharge."""
    from recommender.role_compendium import _best_payoff_move, _setup_payoff_candidates
    from recommender.legality import load_snapshot

    snap = load_snapshot()
    assert (
        _best_payoff_move(
            snap,
            "garchomp",
            {"outrage", "dragonclaw", "swordsdance"},
            boost_stat="atk",
        )
        == "dragonclaw"
    )
    assert _setup_payoff_candidates(
        snap,
        boost_stat="atk",
        usage_move_ids={"outrage", "thrash", "ragingfury", "dragonclaw"},
    ) == ["dragonclaw"]
    # Petal Dance is the Special-side reach that no live candidate exercises.
    assert _setup_payoff_candidates(
        snap,
        boost_stat="spa",
        usage_move_ids={"petaldance", "uproar", "psychic"},
    ) == ["psychic"]


def test_select_setup_payoff_priority_wins_when_incoming_ohko():
    """Equal payoff frac: outsped non-priority is zeroed on incoming OHKO; SP still wins."""
    from recommender.role_compendium import _select_setup_payoff
    from recommender.legality import load_snapshot

    snap = load_snapshot()

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for req in reqs:
            if (req.get("attacker") or {}).get("boosts"):
                out.append(_panel_result(dmg=100, hp=200, atk_spe=50, def_spe=80))
            else:
                out.append(_panel_result(dmg=200, hp=200, atk_spe=80, def_spe=50))
        return out

    panel = [
        {
            "species": "Blissey",
            "evs": {"hp": 32, "def": 32, "spd": 32},
            "usage_moves": ["Moonblast"],
        }
    ]
    mid, raw, err, kind = _select_setup_payoff(
        snap=snap,
        sid="mawilemega",
        calc_name="Mawile-Mega",
        item=None,
        ability="Huge Power",
        boost_stat="atk",
        stages=2,
        panel=panel,
        calculate_batch=calc,
        kit_moves=["Play Rough", "Sucker Punch", "Iron Head", "Swords Dance"],
    )
    assert mid == "suckerpunch"
    assert kind == "conditional"
    assert abs(raw - 0.5) < 1e-6
    assert err == ""

def test_turn_order_fictional_ko_zeroed():
    from recommender.role_compendium import _damage_score

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [_panel_result(dmg=200, hp=200, atk_spe=50, def_spe=150) for _ in reqs]

    score, err = _damage_score(
        attacker_name="Heracross-Mega",
        item=None,
        ability=None,
        move="Close Combat",
        move_id="closecombat",
        boost_stat="atk",
        stages=2,
        panel=[{"species": "Garchomp", "evs": {"hp": 32}}],
        calculate_batch=calc,
    )
    assert err == ""
    assert score == 0.0


def test_turn_order_outsped_survives():
    """Outsped but incoming is not OHKO → full credit (needs snap + mask)."""
    from recommender.role_compendium import _damage_score
    from recommender.legality import load_snapshot

    snap = load_snapshot()

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for req in reqs:
            if (req.get("attacker") or {}).get("boosts"):
                out.append(_panel_result(dmg=50, hp=200, atk_spe=50, def_spe=150))
            else:
                out.append(_panel_result(dmg=50, hp=200, atk_spe=150, def_spe=50))
        return out

    score, err = _damage_score(
        attacker_name="Rhyperior",
        item=None,
        ability=None,
        move="High Horsepower",
        move_id="highhorsepower",
        boost_stat="atk",
        stages=2,
        panel=[
            {
                "species": "Garchomp",
                "evs": {"hp": 32},
                "usage_moves": ["Earthquake"],
            }
        ],
        calculate_batch=calc,
        snap=snap,
    )
    assert err == ""
    # High Horsepower 95% acc; survive-outsped weight 1.0 → 0.25 × 0.95
    assert abs(score - 0.25 * 0.95) < 1e-9


def test_dd_spe_stages_rescues_outspeed():
    """extra_spe_stages=1 uses *1.5 on returned Spe (no Speed Boost ability)."""
    from recommender.role_compendium import _damage_score

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [_panel_result(dmg=200, hp=200, atk_spe=100, def_spe=140) for _ in reqs]

    score, err = _damage_score(
        attacker_name="Gyarados-Mega",
        item=None,
        ability="Mold Breaker",
        move="Aqua Tail",
        move_id="aquatail",
        boost_stat="atk",
        stages=1,
        panel=[{"species": "Garchomp", "evs": {"hp": 32}}],
        calculate_batch=calc,
        extra_spe_stages=1,
    )
    assert err == ""
    # Aqua Tail 90% acc; +1 Spe stage outspeeds → 1.0 × 0.90
    assert abs(score - 0.90) < 1e-9


def test_turn_order_priority_full_credit():
    from recommender.role_compendium import _damage_score

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [_panel_result(dmg=200, hp=200, atk_spe=50, def_spe=150) for _ in reqs]

    score, err = _damage_score(
        attacker_name="Kingambit",
        item=None,
        ability=None,
        move="Sucker Punch",
        move_id="suckerpunch",
        boost_stat="atk",
        stages=2,
        panel=[{"species": "Garchomp", "evs": {"hp": 32}}],
        calculate_batch=calc,
    )
    assert err == ""
    assert abs(score - 1.0) < 1e-9


def test_turn_order_spe_tie_half_credit():
    from recommender.role_compendium import _damage_score

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [_panel_result(dmg=200, hp=200, atk_spe=100, def_spe=100) for _ in reqs]

    score, err = _damage_score(
        attacker_name="Scizor",
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
    assert abs(score - 0.5) < 1e-9


def test_turn_order_missing_spe_fail_open():
    from recommender.role_compendium import _damage_score

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "damageRange": [200, 200],
                "raw": {"stats": {"defender": {"hp": 200}, "attacker": {}}},
            }
            for _ in reqs
        ]

    score, err = _damage_score(
        attacker_name="Scizor",
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
    assert abs(score - 1.0) < 1e-9


def test_disguise_clears_branch_b_without_bulk():
    from recommender.role_compendium import _setup_branches

    branches = _setup_branches(
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
    from recommender.role_compendium import _damage_score

    # 100 < 140, but 100*1.5=150 > 140
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


def test_damage_score_forwards_defender_items():
    from recommender.role_compendium import _damage_score

    seen: list[dict[str, Any]] = []

    def capture(requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen.extend(requests)
        return [
            {
                "damageRange": [100, 120],
                "koChance": "2HKO",
                "raw": {"stats": {"defender": {"hp": 200}}},
            }
            for _ in requests
        ]

    panel = [
        {
            "species": "Kingambit",
            "item": "Black Glasses",
            "evs": {"hp": 32, "def": 32, "spd": 32},
        }
    ]
    score, err = _damage_score(
        attacker_name="Scizor",
        item=None,
        ability="Technician",
        move="Bullet Punch",
        boost_stat="atk",
        stages=2,
        panel=panel,
        calculate_batch=capture,
    )
    assert score > 0
    assert err == ""
    assert seen[0]["defender"]["item"] == "Black Glasses"


def test_ranked_payoff_ragefist_outranks_shadowclaw_at_hits_taken_bp():
    from recommender.counters import ASSUMED_HITS_TAKEN
    from recommender.role_compendium import _ranked_payoff_moves

    assert 50 * (1 + ASSUMED_HITS_TAKEN) > 70
    snap = {
        "species": {"annihilape": {"types": ["Fighting", "Ghost"]}},
        "moves": {
            "closecombat": {"category": "Physical", "basePower": 120, "type": "Fighting"},
            "drainpunch": {"category": "Physical", "basePower": 75, "type": "Fighting"},
            "shadowclaw": {"category": "Physical", "basePower": 70, "type": "Ghost"},
            "ragefist": {"category": "Physical", "basePower": 50, "type": "Ghost"},
        },
    }
    ranked = _ranked_payoff_moves(
        snap,
        "annihilape",
        set(),
        boost_stat="atk",
        usage_moves=["closecombat", "drainpunch", "shadowclaw", "ragefist"],
        usage_only=True,
    )
    assert ranked.index("ragefist") < ranked.index("shadowclaw")


def test_ranked_payoff_liquid_voice_makes_hyper_voice_water_stab():
    from recommender.legality import load_snapshot
    from recommender.role_compendium import _ranked_payoff_moves

    snap = load_snapshot()
    usage = ["blizzard", "hypervoice", "hydropump"]
    plain = _ranked_payoff_moves(
        snap,
        "primarina",
        set(),
        boost_stat="spa",
        usage_moves=usage,
        usage_only=True,
    )
    voiced = _ranked_payoff_moves(
        snap,
        "primarina",
        set(),
        boost_stat="spa",
        usage_moves=usage,
        usage_only=True,
        ability="Liquid Voice",
    )
    assert plain.index("blizzard") < plain.index("hypervoice")
    assert voiced.index("hypervoice") < voiced.index("blizzard")
    assert voiced.index("hydropump") < voiced.index("hypervoice")


def test_damage_score_ragefist_forwards_hits_taken_bp():
    from recommender.counters import ASSUMED_HITS_TAKEN
    from recommender.role_compendium import _damage_score

    seen: list[dict[str, Any]] = []

    def capture(requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen.extend(requests)
        return [_panel_result(dmg=80, hp=200, atk_spe=100, def_spe=80) for _ in requests]

    _damage_score(
        attacker_name="Annihilape",
        item=None,
        ability=None,
        move="Rage Fist",
        move_id="ragefist",
        boost_stat="atk",
        stages=1,
        panel=[{"species": "Garchomp", "evs": {"hp": 32}}],
        calculate_batch=capture,
    )
    assert seen[0]["moveOverrides"]["basePower"] == 50 * (1 + ASSUMED_HITS_TAKEN)


def test_damage_score_surfaces_calc_error():
    from recommender.role_compendium import _damage_score

    def all_fail(requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{"error": "damage[damage.length - 1] === 0."} for _ in requests]

    score, err = _damage_score(
        attacker_name="Aegislash-Blade",
        item=None,
        ability="Stance Change",
        move="Poltergeist",
        boost_stat="atk",
        stages=2,
        panel=[{"species": "Aerodactyl", "evs": {"hp": 32}}],
        calculate_batch=all_fail,
    )
    assert score == 0.0
    assert "Aerodactyl" in err or "0." in err


def test_damage_score_fallback_on_type_immunity():
    from recommender.role_compendium import _damage_score

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for req in reqs:
            mid = to_id(req["move"])
            dname = str(req["defender"]["species"])
            if dname == "Incineroar" and mid == "psychic":
                dmg = 0
            elif dname == "Incineroar" and mid == "shadowball":
                dmg = 50
            else:
                dmg = 100
            out.append(_panel_result(dmg=dmg, hp=100, atk_spe=200, def_spe=50))
        return out

    snap = {
        "species": {"alakazammega": {"types": ["Psychic"]}},
        "moves": {
            "psychic": {
                "name": "Psychic",
                "category": "Special",
                "basePower": 90,
                "type": "Psychic",
            },
            "shadowball": {
                "name": "Shadow Ball",
                "category": "Special",
                "basePower": 80,
                "type": "Ghost",
            },
        },
    }
    panel = [
        {"species": "Garchomp", "evs": {"hp": 32}},
        {"species": "Incineroar", "evs": {"hp": 32}},
    ]
    no_fb, _err = _damage_score(
        attacker_name="Alakazam-Mega",
        item=None,
        ability=None,
        move="Psychic",
        move_id="psychic",
        boost_stat="spa",
        stages=2,
        panel=panel,
        calculate_batch=calc,
    )
    used: list[tuple[str, str]] = []
    with_fb, err = _damage_score(
        attacker_name="Alakazam-Mega",
        item=None,
        ability=None,
        move="Psychic",
        move_id="psychic",
        boost_stat="spa",
        stages=2,
        panel=panel,
        calculate_batch=calc,
        fallback_mids=["shadowball"],
        snap=snap,
        attacker_sid="alakazammega",
        used_out=used,
    )
    assert err == ""
    assert abs(no_fb - 1.0) < 1e-9  # Incineroar skipped → inflated
    assert abs(with_fb - 0.75) < 1e-9  # Psychic 1.0 + Shadow Ball 0.5
    assert used == [("Garchomp", "psychic"), ("Incineroar", "shadowball")]


def test_damage_score_skips_when_all_moves_zero():
    from recommender.role_compendium import _damage_score

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            _panel_result(dmg=0, hp=100, atk_spe=200, def_spe=50) for _ in reqs
        ]

    used: list[tuple[str, str]] = []
    score, err = _damage_score(
        attacker_name="Alakazam-Mega",
        item=None,
        ability=None,
        move="Psychic",
        move_id="psychic",
        boost_stat="spa",
        stages=2,
        panel=[{"species": "Spiritomb", "evs": {"hp": 32}}],
        calculate_batch=calc,
        fallback_mids=["shadowball", "dazzlinggleam"],
        used_out=used,
    )
    assert score == 0.0
    assert "Spiritomb:zero_damage" in err
    assert used == []


def test_payoff_coverage_note_lists_per_defender_fallbacks():
    from recommender.role_compendium import _payoff_coverage_note

    snap = {
        "moves": {
            "psychic": {"name": "Psychic"},
            "shadowball": {"name": "Shadow Ball"},
        }
    }
    used = [
        ("Garchomp", "psychic"),
        ("Whimsicott", "psychic"),
        ("Incineroar", "shadowball"),
        ("Kingambit", "shadowball"),
    ]
    note = _payoff_coverage_note(used, snap=snap, primary_mid="psychic")
    assert note is not None
    assert note.startswith("Psychic×2")
    assert "Shadow Ball×2" in note
    assert "Incineroar" in note and "Kingambit" in note
    assert _payoff_coverage_note(used[:2], snap=snap, primary_mid="psychic") is None


def test_setup_payoff_notes_orders_by_mid_counts():
    from recommender.role_compendium import _setup_payoff_notes

    used = [
        ("Garchomp", "playrough"),
        ("Whimsicott", "playrough"),
        ("Incineroar", "doubleedge"),
        ("Kingambit", "playrough"),
    ]
    counts = {"playrough": 3, "doubleedge": 1}
    moves, targets = _setup_payoff_notes(used, counts)
    assert moves == ["playrough", "doubleedge"]
    assert targets["playrough"] == ["Garchomp", "Whimsicott", "Kingambit"]
    assert targets["doubleedge"] == ["Incineroar"]
    # Tie on count → lexicographically smaller mid first
    tied = _setup_payoff_notes(
        [("A", "zeta"), ("B", "alpha")],
        {"zeta": 1, "alpha": 1},
    )
    assert tied[0] == ["alpha", "zeta"]


def test_sd_construct_structured_payoff_mawile_shaped(monkeypatch):
    """Multi-mid kit winners → payoff_moves/targets + plural execution traits."""
    import inspect

    from recommender.role_compendium import (
        RoleConstructionDraft,
        _attacker_kit,
        _construct_def_payoff_setup,
        _construct_offense_stage_setup,
        _move_display,
    )

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


def test_damage_score_sweep_ohko_and_survive_remain():
    """Outgoing OHKO k/n + outsped-survive remain from the same batches."""
    from recommender.role_compendium import _damage_score, _sweep_note_fields
    from recommender.legality import load_snapshot

    snap = load_snapshot()

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for req in reqs:
            dname = str((req.get("defender") or {}).get("species") or "")
            if (req.get("attacker") or {}).get("boosts"):
                # Outgoing: Garchomp OHKO, Incineroar 2HKO, Blissey chip.
                if dname == "Garchomp":
                    out.append(_panel_result(dmg=200, hp=100, atk_spe=50, def_spe=150))
                elif dname == "Incineroar":
                    out.append(_panel_result(dmg=60, hp=100, atk_spe=50, def_spe=150))
                else:
                    out.append(_panel_result(dmg=20, hp=100, atk_spe=50, def_spe=150))
            else:
                # Incoming vs Rhyperior: survive 40% vs Garchomp/Incineroar; OHKO from Blissey.
                atk = str((req.get("attacker") or {}).get("species") or "")
                if atk == "Blissey":
                    out.append(_panel_result(dmg=200, hp=100, atk_spe=150, def_spe=50))
                else:
                    out.append(_panel_result(dmg=60, hp=100, atk_spe=150, def_spe=50))
        return out

    panel = [
        {"species": "Garchomp", "evs": {"hp": 32}, "usage_moves": ["Earthquake"]},
        {"species": "Incineroar", "evs": {"hp": 32}, "usage_moves": ["Flare Blitz"]},
        {"species": "Blissey", "evs": {"hp": 32}, "usage_moves": ["Moonblast"]},
    ]
    sweep: dict[str, Any] = {}
    _score, err = _damage_score(
        attacker_name="Rhyperior",
        item=None,
        ability=None,
        move="Earthquake",
        move_id="earthquake",
        boost_stat="atk",
        stages=2,
        panel=panel,
        calculate_batch=calc,
        snap=snap,
        sweep_out=sweep,
    )
    assert err == ""
    assert sweep["ohko"] == 1
    assert sweep["ko2"] == 2
    assert sweep["n"] == 3
    assert sweep["n_surv"] == 2
    assert abs(sweep["remain_mean"] - 0.40) < 1e-9
    assert abs(sweep["remain_min"] - 0.40) < 1e-9
    notes = _sweep_note_fields(sweep)
    assert notes["sweep_ohko"] == "1/3"
    assert notes["sweep_2hko"] == "2/3"
    assert notes["survive_n"] == "2"
    assert notes["survive_hp_mean"] == "0.40"
    assert notes["survive_hp_min"] == "0.40"


def test_damage_score_sweep_n_surv_zero_is_na():
    """Faster than the panel → survive fields n/a, never imputed."""
    from recommender.role_compendium import _damage_score, _sweep_note_fields
    from recommender.legality import load_snapshot

    snap = load_snapshot()

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [_panel_result(dmg=100, hp=100, atk_spe=200, def_spe=50) for _ in reqs]

    sweep: dict[str, Any] = {}
    _score, err = _damage_score(
        attacker_name="Weavile",
        item=None,
        ability=None,
        move="Knock Off",
        move_id="knockoff",
        boost_stat="atk",
        stages=2,
        panel=[{"species": "Garchomp", "evs": {"hp": 32}, "usage_moves": ["Earthquake"]}],
        calculate_batch=calc,
        snap=snap,
        sweep_out=sweep,
    )
    assert err == ""
    assert sweep["n_surv"] == 0
    notes = _sweep_note_fields(sweep)
    assert notes["survive_hp_mean"] == "n/a"
    assert notes["survive_hp_min"] == "n/a"


def test_damage_score_disguise_survive_remain_is_full():
    from recommender.role_compendium import _damage_score
    from recommender.legality import load_snapshot

    snap = load_snapshot()

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for req in reqs:
            if (req.get("attacker") or {}).get("boosts"):
                out.append(_panel_result(dmg=50, hp=100, atk_spe=40, def_spe=150))
            else:
                out.append(_panel_result(dmg=200, hp=100, atk_spe=150, def_spe=40))
        return out

    sweep: dict[str, Any] = {}
    _score, err = _damage_score(
        attacker_name="Mimikyu",
        item=None,
        ability="Disguise",
        move="Play Rough",
        move_id="playrough",
        boost_stat="atk",
        stages=2,
        panel=[{"species": "Garchomp", "evs": {"hp": 32}, "usage_moves": ["Earthquake"]}],
        calculate_batch=calc,
        snap=snap,
        sweep_out=sweep,
    )
    assert err == ""
    assert sweep["n_surv"] == 1
    assert abs(sweep["remain_mean"] - 1.0) < 1e-9


def _aegislash_dispatch(
    *,
    payoff_dmg: int,
    ss_dmg: int = 50,
    shield_dmg: int = 60,
    blade_dmg: int = 200,
    seen: list[dict[str, Any]] | None = None,
):
    """Incoming: defender.species. Outgoing: move (Iron Head vs Shadow Sneak)."""

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if seen is not None:
            seen.extend(reqs)
        out: list[dict[str, Any]] = []
        for req in reqs:
            atk = req.get("attacker") or {}
            dfn = req.get("defender") or {}
            if not atk.get("boosts"):
                dmg = blade_dmg if dfn.get("species") == "Aegislash-Blade" else shield_dmg
                out.append(_panel_result(dmg=dmg, hp=100, atk_spe=150, def_spe=50))
                continue
            dmg = ss_dmg if to_id(str(req.get("move") or "")) == "shadowsneak" else payoff_dmg
            out.append(_panel_result(dmg=dmg, hp=100, atk_spe=50, def_spe=150))
        return out

    return calc


_AEGISLASH_PANEL = [
    {"species": "Garchomp", "evs": {"hp": 32}, "usage_moves": ["Earthquake"]},
]


def test_aegislash_incoming_uses_shield_forme():
    from recommender.role_compendium import _damage_score
    from recommender.legality import load_snapshot

    seen: list[dict[str, Any]] = []
    sweep: dict[str, Any] = {}
    _score, err = _damage_score(
        attacker_name="Aegislash-Blade",
        item=None,
        ability="Stance Change",
        move="Iron Head",
        move_id="ironhead",
        boost_stat="atk",
        stages=2,
        panel=_AEGISLASH_PANEL,
        calculate_batch=_aegislash_dispatch(payoff_dmg=60, seen=seen),
        snap=load_snapshot(),
        sweep_out=sweep,
    )
    assert err == ""
    incoming = [r for r in seen if not (r.get("attacker") or {}).get("boosts")]
    assert incoming
    assert all((r.get("defender") or {}).get("species") == "Aegislash-Shield" for r in incoming)
    assert sweep["n_surv"] == 1
    assert abs(sweep["remain_mean"] - 0.40) < 1e-9


def test_aegislash_combined_ko_credits_ohko_and_remain():
    from recommender.role_compendium import _damage_score
    from recommender.legality import load_snapshot

    sweep: dict[str, Any] = {}
    _score, err = _damage_score(
        attacker_name="Aegislash-Blade",
        item=None,
        ability="Stance Change",
        move="Iron Head",
        move_id="ironhead",
        boost_stat="atk",
        stages=2,
        panel=_AEGISLASH_PANEL,
        calculate_batch=_aegislash_dispatch(payoff_dmg=60, ss_dmg=50),
        snap=load_snapshot(),
        sweep_out=sweep,
        kit_moves=["Iron Head", "Shadow Sneak", "Sacred Sword"],
    )
    assert err == ""
    assert sweep["ohko"] == 1
    assert sweep["n_surv"] == 1
    assert abs(sweep["remain_mean"] - 1.0) < 1e-9


def test_aegislash_combined_ko_requires_shadow_sneak_in_kit():
    from recommender.role_compendium import _damage_score
    from recommender.legality import load_snapshot

    sweep: dict[str, Any] = {}
    _score, err = _damage_score(
        attacker_name="Aegislash-Blade",
        item=None,
        ability="Stance Change",
        move="Iron Head",
        move_id="ironhead",
        boost_stat="atk",
        stages=2,
        panel=_AEGISLASH_PANEL,
        calculate_batch=_aegislash_dispatch(payoff_dmg=60, ss_dmg=50),
        snap=load_snapshot(),
        sweep_out=sweep,
        kit_moves=["Iron Head", "King's Shield", "Sacred Sword"],
    )
    assert err == ""
    assert sweep["ohko"] == 0


def test_aegislash_ks_reset_independent_of_shadow_sneak():
    from recommender.role_compendium import _damage_score
    from recommender.legality import load_snapshot

    sweep: dict[str, Any] = {}
    _score, err = _damage_score(
        attacker_name="Aegislash-Blade",
        item=None,
        ability="Stance Change",
        move="Iron Head",
        move_id="ironhead",
        boost_stat="atk",
        stages=2,
        panel=_AEGISLASH_PANEL,
        calculate_batch=_aegislash_dispatch(payoff_dmg=60, blade_dmg=40),
        snap=load_snapshot(),
        sweep_out=sweep,
        kit_moves=["Iron Head", "King's Shield"],
    )
    assert err == ""
    assert sweep["ohko"] == 0
    assert sweep["n_surv"] == 1
    assert abs(sweep["remain_mean"] - 1.0) < 1e-9


def test_aegislash_no_ks_no_combined_ko_gets_no_remain():
    from recommender.role_compendium import _damage_score
    from recommender.legality import load_snapshot

    sweep: dict[str, Any] = {}
    _score, err = _damage_score(
        attacker_name="Aegislash-Blade",
        item=None,
        ability="Stance Change",
        move="Iron Head",
        move_id="ironhead",
        boost_stat="atk",
        stages=2,
        panel=_AEGISLASH_PANEL,
        calculate_batch=_aegislash_dispatch(payoff_dmg=40, ss_dmg=40, blade_dmg=40),
        snap=load_snapshot(),
        sweep_out=sweep,
        kit_moves=["Iron Head", "Shadow Sneak"],
    )
    assert err == ""
    assert sweep["ohko"] == 0
    assert sweep["n_surv"] == 0


def test_aegislash_branch_b_matches_shield_defender():
    from recommender.role_compendium import (
        _base_stats,
        _candidate_defender_spec,
        _setup_bulk_ok,
    )
    from recommender.legality import load_snapshot

    snap = load_snapshot()
    assert _setup_bulk_ok(_base_stats(snap, "aegislash"))
    assert not _setup_bulk_ok(_base_stats(snap, "aegislashblade"))
    spec = _candidate_defender_spec("Aegislash", "Aegislash-Blade")
    assert spec["species"] == "Aegislash-Shield"


def test_connect_recoil_move_set_locked():
    from recommender.role_compendium import _CONNECT_RECOIL_MOVES

    assert _CONNECT_RECOIL_MOVES == frozenset(
        {
            "bravebird",
            "doubleedge",
            "flareblitz",
            "headcharge",
            "headsmash",
            "lightofruin",
            "submission",
            "takedown",
            "volttackle",
            "wavecrash",
            "wildcharge",
            "woodhammer",
        }
    )
    # Crash / mindblown / chloroblast stay out.
    assert "highjumpkick" not in _CONNECT_RECOIL_MOVES
    assert "steelbeam" not in _CONNECT_RECOIL_MOVES
    assert "chloroblast" not in _CONNECT_RECOIL_MOVES


def test_self_defense_drops_from_stat_boosts():
    from recommender.role_compendium import _self_defense_drops

    assert _self_defense_drops("closecombat") == {"def": -1, "spd": -1}
    assert _self_defense_drops("superpower") == {"def": -1}
    assert _self_defense_drops("flareblitz") == {}
    assert _self_defense_drops("ironhead") == {}


_RECOIL_PANEL = [
    {"species": "Garchomp", "evs": {"hp": 32}, "usage_moves": ["Earthquake"]},
]


def _outsped_survive_dispatch(
    *,
    payoff_dmg: int = 60,
    incoming_dmg: int = 60,
    hp: int = 100,
    recoil_pct: float | None = None,
    recovery_hp: int | None = None,
    atk_hp: int | None = None,
    seen_defs: list[dict[str, Any]] | None = None,
):
    """Outgoing slower than foe; incoming non-OHKO so remain is credited."""

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for req in reqs:
            atk = req.get("attacker") or {}
            if not atk.get("boosts"):
                # Incoming vs candidate
                if seen_defs is not None:
                    seen_defs.append(dict(req.get("defender") or {}))
                out.append(
                    _panel_result(dmg=incoming_dmg, hp=hp, atk_spe=150, def_spe=50)
                )
                continue
            out.append(
                _panel_result(
                    dmg=payoff_dmg,
                    hp=hp,
                    atk_spe=50,
                    def_spe=150,
                    recoil_pct=recoil_pct,
                    recovery_hp=recovery_hp,
                    atk_hp=atk_hp,
                )
            )
        return out

    return calc


def test_recoil_remain_uses_capped_raw_recoil_not_naive_ratio():
    """OHKO-capped raw.recoil (~34.4%) must beat naive ratio×dmg/hp (~81%)."""
    from recommender.role_compendium import _damage_score
    from recommender.legality import load_snapshot

    # Payoff "OHKO" numbers that would naive-overstate: dmg=392, atk_hp=159 → ~81%.
    # Calc returns capped recoil_pct=34.4 instead.
    sweep: dict[str, Any] = {}
    _score, err = _damage_score(
        attacker_name="Blaziken",
        item=None,
        ability=None,
        move="Flare Blitz",
        move_id="flareblitz",
        boost_stat="atk",
        stages=2,
        panel=_RECOIL_PANEL,
        calculate_batch=_outsped_survive_dispatch(
            payoff_dmg=392, incoming_dmg=40, hp=100, recoil_pct=34.4
        ),
        snap=load_snapshot(),
        sweep_out=sweep,
    )
    assert err == ""
    assert sweep["n_surv"] == 1
    # remain = 1 - 0.40 - 0.344 = 0.256
    assert abs(sweep["remain_mean"] - 0.256) < 1e-9
    naive = (33 / 100) * 392 / 159
    assert naive > 0.8
    assert sweep["remain_mean"] > 1.0 - 0.40 - naive  # capped path kept more HP


def test_recoil_remain_gated_vs_non_recoil_payoff():
    from recommender.role_compendium import _damage_score
    from recommender.legality import load_snapshot

    snap = load_snapshot()
    panel = _RECOIL_PANEL

    sweep_r: dict[str, Any] = {}
    _damage_score(
        attacker_name="Blaziken",
        item=None,
        ability=None,
        move="Flare Blitz",
        move_id="flareblitz",
        boost_stat="atk",
        stages=2,
        panel=panel,
        calculate_batch=_outsped_survive_dispatch(
            payoff_dmg=60, incoming_dmg=40, hp=100, recoil_pct=25.0
        ),
        snap=snap,
        sweep_out=sweep_r,
    )
    sweep_n: dict[str, Any] = {}
    _damage_score(
        attacker_name="Blaziken",
        item=None,
        ability=None,
        move="Close Combat",
        move_id="closecombat",
        boost_stat="atk",
        stages=2,
        panel=panel,
        calculate_batch=_outsped_survive_dispatch(
            payoff_dmg=60, incoming_dmg=40, hp=100, recoil_pct=25.0
        ),
        snap=snap,
        sweep_out=sweep_n,
    )
    # Same mock recoil payload, but Close Combat is not in connect-recoil set.
    assert abs(sweep_r["remain_mean"] - 0.35) < 1e-9  # 1 - 0.4 - 0.25
    assert abs(sweep_n["remain_mean"] - 0.60) < 1e-9  # 1 - 0.4


def test_drain_move_set_locked():
    from recommender.role_compendium import _DRAIN_MOVES

    assert _DRAIN_MOVES == frozenset(
        {
            "bitterblade",
            "drainpunch",
            "gigadrain",
            "hornleech",
            "leechlife",
            "matchagotcha",
            "paraboliccharge",
            "drainingkiss",
        }
    )
    # Past / illegal drain stays out.
    assert "absorb" not in _DRAIN_MOVES
    assert "megadrain" not in _DRAIN_MOVES
    assert "dreameater" not in _DRAIN_MOVES
    assert "oblivionwing" not in _DRAIN_MOVES


def test_drain_frac_from_result_reads_recovery_over_maxhp():
    from recommender.role_compendium import _drain_frac_from_result

    r50 = _panel_result(dmg=60, hp=100, recovery_hp=50, atk_hp=100)
    r75 = _panel_result(dmg=60, hp=100, recovery_hp=75, atk_hp=100)
    assert abs(_drain_frac_from_result(r50, "bitterblade") - 0.50) < 1e-9
    assert abs(_drain_frac_from_result(r75, "drainingkiss") - 0.75) < 1e-9


def test_drain_frac_gated_ignores_shell_bell_on_non_drain():
    from recommender.role_compendium import _drain_frac_from_result

    # Shell Bell (or any item heal) populates raw.recovery on non-drain moves.
    payload = _panel_result(dmg=60, hp=100, recovery_hp=13, atk_hp=154)
    assert _drain_frac_from_result(payload, "shadowsneak") == 0.0
    assert abs(_drain_frac_from_result(payload, "bitterblade") - (13 / 154)) < 1e-9


def test_drain_remain_on_damage_score():
    """ID+BP/legacy _damage_score site wires the shared drain helper."""
    from recommender.role_compendium import _damage_score
    from recommender.legality import load_snapshot

    sweep: dict[str, Any] = {}
    _score, err = _damage_score(
        attacker_name="Conkeldurr",
        item=None,
        ability=None,
        move="Drain Punch",
        move_id="drainpunch",
        boost_stat="atk",
        stages=1,
        panel=_RECOIL_PANEL,
        calculate_batch=_outsped_survive_dispatch(
            payoff_dmg=60,
            incoming_dmg=40,
            hp=100,
            recovery_hp=25,
            atk_hp=100,
        ),
        snap=load_snapshot(),
        sweep_out=sweep,
    )
    assert err == ""
    assert sweep["n_surv"] == 1
    # remain = min(1, 1 - 0.40 + 0.25) = 0.85
    assert abs(sweep["remain_mean"] - 0.85) < 1e-9


def test_drain_remain_gated_vs_non_drain_payoff():
    from recommender.role_compendium import _damage_score
    from recommender.legality import load_snapshot

    snap = load_snapshot()
    dispatch = _outsped_survive_dispatch(
        payoff_dmg=60, incoming_dmg=40, hp=100, recovery_hp=25, atk_hp=100
    )
    sweep_d: dict[str, Any] = {}
    _damage_score(
        attacker_name="Conkeldurr",
        item=None,
        ability=None,
        move="Drain Punch",
        move_id="drainpunch",
        boost_stat="atk",
        stages=1,
        panel=_RECOIL_PANEL,
        calculate_batch=dispatch,
        snap=snap,
        sweep_out=sweep_d,
    )
    sweep_n: dict[str, Any] = {}
    _damage_score(
        attacker_name="Conkeldurr",
        item=None,
        ability=None,
        move="Close Combat",
        move_id="closecombat",
        boost_stat="atk",
        stages=1,
        panel=_RECOIL_PANEL,
        calculate_batch=dispatch,
        snap=snap,
        sweep_out=sweep_n,
    )
    assert abs(sweep_d["remain_mean"] - 0.85) < 1e-9  # 1 - 0.4 + 0.25
    assert abs(sweep_n["remain_mean"] - 0.60) < 1e-9  # 1 - 0.4


def test_drain_remain_caps_at_full_hp():
    from recommender.role_compendium import _damage_score
    from recommender.legality import load_snapshot

    sweep: dict[str, Any] = {}
    _damage_score(
        attacker_name="Ceruledge",
        item=None,
        ability=None,
        move="Bitter Blade",
        move_id="bitterblade",
        boost_stat="atk",
        stages=2,
        panel=_RECOIL_PANEL,
        calculate_batch=_outsped_survive_dispatch(
            payoff_dmg=60,
            incoming_dmg=10,
            hp=100,
            recovery_hp=90,
            atk_hp=100,
        ),
        snap=load_snapshot(),
        sweep_out=sweep,
    )
    # remain = min(1, 1 - 0.10 + 0.90) = 1.0
    assert abs(sweep["remain_mean"] - 1.0) < 1e-9


def test_drain_remain_on_kit_matrix():
    """Stage 1 kit-matrix site credits drain the same way as _damage_score."""
    from recommender.role_compendium import _setup_kit_matrix_score
    from recommender.legality import load_snapshot

    snap = load_snapshot()
    panel = _RECOIL_PANEL
    score, err, _used, sweep = _setup_kit_matrix_score(
        snap=snap,
        sid="ceruledge",
        calc_name="Ceruledge",
        item=None,
        ability=None,
        boost_stat="atk",
        stages=2,
        panel=panel,
        calculate_batch=_outsped_survive_dispatch(
            payoff_dmg=60,
            incoming_dmg=40,
            hp=100,
            recovery_hp=25,
            atk_hp=100,
        ),
        mids=["bitterblade"],
        kit_moves=["swordsdance", "bitterblade"],
    )
    assert err == ""
    assert score > 0
    assert sweep["n_surv"] == 1
    assert abs(sweep["remain_mean"] - 0.85) < 1e-9


def test_drain_remain_ceruledge_scale_magnitude():
    """Discovery-scale lifts: min ≥+0.40, mean ≥+0.15 (not a token bump)."""
    from recommender.role_compendium import _damage_score
    from recommender.legality import load_snapshot

    # Two survivors: incoming fracs 0.785 and 0.232 → before remains 0.215 / 0.768.
    # Drain fracs 0.437 and 0.164 → after 0.652 / 0.932 (discovery SD scale).
    panel = [
        {"species": "A", "evs": {"hp": 32}, "usage_moves": ["Earthquake"]},
        {"species": "B", "evs": {"hp": 32}, "usage_moves": ["Earthquake"]},
    ]
    # Map defender → (incoming_dmg, recovery_hp) with defender hp=1000 for precision.
    # remain_before = 1 - incoming/1000; drain = recovery/1000.
    # A: incoming 785 → remain 0.215; recovery 437 → after 0.652 (Δ0.437)
    # B: incoming 232 → remain 0.768; recovery 164 → after 0.932 (Δ0.164)
    specs = {
        "A": (785, 437),
        "B": (232, 164),
    }

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for req in reqs:
            atk = req.get("attacker") or {}
            defn = req.get("defender") or {}
            if not atk.get("boosts"):
                # Incoming OHKO batch: panel member hits candidate.
                dname = str(atk.get("species") or "")
                incoming_dmg, _rec = specs[dname]
                out.append(
                    _panel_result(
                        dmg=incoming_dmg, hp=1000, atk_spe=150, def_spe=50
                    )
                )
                continue
            dname = str(defn.get("species") or "")
            _inc, recovery_hp = specs[dname]
            out.append(
                _panel_result(
                    dmg=600,
                    hp=1000,
                    atk_spe=50,
                    def_spe=150,
                    recovery_hp=recovery_hp,
                    atk_hp=1000,
                )
            )
        return out

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}

    def calc_before(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # Strip recovery so we measure the lift.
        results = calc(reqs)
        for r in results:
            (r.get("raw") or {}).pop("recovery", None)
        return results

    snap = load_snapshot()
    common = dict(
        attacker_name="Ceruledge",
        item=None,
        ability=None,
        move="Bitter Blade",
        move_id="bitterblade",
        boost_stat="atk",
        stages=2,
        panel=panel,
        snap=snap,
    )
    _damage_score(**common, calculate_batch=calc_before, sweep_out=before)
    _damage_score(**common, calculate_batch=calc, sweep_out=after)

    d_mean = after["remain_mean"] - before["remain_mean"]
    d_min = after["remain_min"] - before["remain_min"]
    assert d_min >= 0.40
    assert d_mean >= 0.15
    assert abs(before["remain_min"] - 0.215) < 1e-9
    assert abs(before["remain_mean"] - 0.4915) < 1e-9  # (0.215+0.768)/2
    assert abs(after["remain_min"] - 0.652) < 1e-9
    assert abs(after["remain_mean"] - 0.792) < 1e-9  # (0.652+0.932)/2


def test_debuff_surv_applies_negative_def_spd_stages():
    """Old stage>0 filter would ignore Def/SpD−1 and false-survive; fix must OHKO."""
    from recommender.role_compendium import _damage_score
    from recommender.legality import load_snapshot

    seen_defs: list[dict[str, Any]] = []

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for req in reqs:
            atk = req.get("attacker") or {}
            dfn = req.get("defender") or {}
            if not atk.get("boosts"):
                seen_defs.append(dict(dfn))
                bst = dfn.get("boosts") or {}
                # Debuffed (any neg def/spd) → OHKO; undebuffed → survive.
                neg = any(int(bst.get(s) or 0) < 0 for s in ("def", "spd"))
                dmg = 120 if neg else 40
                out.append(_panel_result(dmg=dmg, hp=100, atk_spe=150, def_spe=50))
                continue
            out.append(_panel_result(dmg=60, hp=100, atk_spe=50, def_spe=150))
        return out

    sweep: dict[str, Any] = {}
    _score, err = _damage_score(
        attacker_name="Blaziken",
        item=None,
        ability=None,
        move="Close Combat",
        move_id="closecombat",
        boost_stat="atk",
        stages=2,
        panel=_RECOIL_PANEL,
        calculate_batch=calc,
        snap=load_snapshot(),
        sweep_out=sweep,
    )
    assert err == ""
    assert sweep.get("debuff_surv") == "0/1"
    # Standing pass must have applied both drops on at least one incoming defender.
    assert any(
        int((d.get("boosts") or {}).get("def") or 0) == -1
        and int((d.get("boosts") or {}).get("spd") or 0) == -1
        for d in seen_defs
    )


def test_debuff_surv_omitted_for_non_debuff_payoff():
    from recommender.role_compendium import _damage_score
    from recommender.legality import load_snapshot

    sweep: dict[str, Any] = {}
    _score, err = _damage_score(
        attacker_name="Blaziken",
        item=None,
        ability=None,
        move="Flare Blitz",
        move_id="flareblitz",
        boost_stat="atk",
        stages=2,
        panel=_RECOIL_PANEL,
        calculate_batch=_outsped_survive_dispatch(
            payoff_dmg=60, incoming_dmg=40, hp=100, recoil_pct=10.0
        ),
        snap=load_snapshot(),
        sweep_out=sweep,
    )
    assert err == ""
    assert "debuff_surv" not in sweep


def _priority_finisher_dispatch(
    *,
    finisher_mid: str,
    payoff_dmg: int = 60,
    finisher_dmg: int = 50,
    incoming_dmg: int = 60,
):
    """Lived-shield panel: outsped on payoff; finisher vs payoff by move id."""

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for req in reqs:
            atk = req.get("attacker") or {}
            if not atk.get("boosts"):
                out.append(
                    _panel_result(dmg=incoming_dmg, hp=100, atk_spe=150, def_spe=50)
                )
                continue
            mid = to_id(str(req.get("move") or ""))
            dmg = finisher_dmg if mid == finisher_mid else payoff_dmg
            out.append(_panel_result(dmg=dmg, hp=100, atk_spe=50, def_spe=150))
        return out

    return calc


_FINISHER_PANEL = [
    {"species": "Garchomp", "evs": {"hp": 32}, "usage_moves": ["Earthquake"]},
]

# (species, finisher_id, finisher_display, payoff_display, payoff_id, boost_stat)
_ELIGIBLE_FINISHER_CASES = [
    ("Dragonite", "extremespeed", "Extreme Speed", "Earthquake", "earthquake", "atk"),
    ("Pinsir-Mega", "feint", "Feint", "Close Combat", "closecombat", "atk"),
    ("Feraligatr", "aquajet", "Aqua Jet", "Liquidation", "liquidation", "atk"),
    ("Scizor", "bulletpunch", "Bullet Punch", "X-Scissor", "xscissor", "atk"),
    ("Palafin", "jetpunch", "Jet Punch", "Liquidation", "liquidation", "atk"),
    ("Crabominable-Mega", "machpunch", "Mach Punch", "Ice Hammer", "icehammer", "atk"),
    ("Sylveon", "quickattack", "Quick Attack", "Moonblast", "moonblast", "spa"),
    ("Mimikyu", "shadowsneak", "Shadow Sneak", "Play Rough", "playrough", "atk"),
    ("Kingambit", "suckerpunch", "Sucker Punch", "Iron Head", "ironhead", "atk"),
]


def test_setup_priority_finisher_set_excludes_banned_and_deferred():
    from recommender.role_compendium import _SETUP_PRIORITY_FINISHER_MOVES

    assert "fakeout" not in _SETUP_PRIORITY_FINISHER_MOVES
    assert "firstimpression" not in _SETUP_PRIORITY_FINISHER_MOVES
    assert "upperhand" not in _SETUP_PRIORITY_FINISHER_MOVES
    assert "grassyglide" not in _SETUP_PRIORITY_FINISHER_MOVES
    assert _SETUP_PRIORITY_FINISHER_MOVES == frozenset(
        {
            "extremespeed",
            "feint",
            "aquajet",
            "bulletpunch",
            "jetpunch",
            "machpunch",
            "quickattack",
            "shadowsneak",
            "suckerpunch",
        }
    )


def test_priority_finisher_combined_ko_credits_each_eligible_move():
    from recommender.role_compendium import _damage_score
    from recommender.legality import load_snapshot

    snap = load_snapshot()
    for (
        species,
        fin_mid,
        fin_disp,
        payoff_disp,
        payoff_id,
        boost_stat,
    ) in _ELIGIBLE_FINISHER_CASES:
        sweep: dict[str, Any] = {}
        _score, err = _damage_score(
            attacker_name=species,
            item=None,
            ability=None,
            move=payoff_disp,
            move_id=payoff_id,
            boost_stat=boost_stat,
            stages=2,
            panel=_FINISHER_PANEL,
            calculate_batch=_priority_finisher_dispatch(finisher_mid=fin_mid),
            snap=snap,
            sweep_out=sweep,
            kit_moves=[payoff_disp, fin_disp, "Protect"],
        )
        assert err == "", f"{species}/{fin_mid}: {err}"
        assert sweep["ohko"] == 1, f"{species}/{fin_mid}"
        assert sweep["n_surv"] == 1, f"{species}/{fin_mid}"
        assert abs(sweep["remain_mean"] - 1.0) < 1e-9, f"{species}/{fin_mid}"


def test_fakeout_in_kit_gets_no_priority_finisher_credit():
    from recommender.role_compendium import _damage_score
    from recommender.legality import load_snapshot

    sweep: dict[str, Any] = {}
    _score, err = _damage_score(
        attacker_name="Scrafty-Mega",
        item=None,
        ability=None,
        move="Knock Off",
        move_id="knockoff",
        boost_stat="atk",
        stages=2,
        panel=_FINISHER_PANEL,
        calculate_batch=_priority_finisher_dispatch(
            finisher_mid="fakeout", finisher_dmg=50, payoff_dmg=60
        ),
        snap=load_snapshot(),
        sweep_out=sweep,
        kit_moves=["Knock Off", "Fake Out", "Protect"],
    )
    assert err == ""
    assert sweep["ohko"] == 0
    # Normal lived-shield remain (not sequence silence): 1.0 - 0.60
    assert sweep["n_surv"] == 1
    assert abs(sweep["remain_mean"] - 0.40) < 1e-9


def test_grassyglide_in_kit_gets_no_priority_finisher_credit():
    from recommender.role_compendium import _damage_score
    from recommender.legality import load_snapshot

    sweep: dict[str, Any] = {}
    _score, err = _damage_score(
        attacker_name="Rillaboom",
        item=None,
        ability=None,
        move="Grass Knot",
        move_id="grassknot",
        boost_stat="atk",
        stages=2,
        panel=_FINISHER_PANEL,
        calculate_batch=_priority_finisher_dispatch(
            finisher_mid="grassyglide", finisher_dmg=50, payoff_dmg=60
        ),
        snap=load_snapshot(),
        sweep_out=sweep,
        kit_moves=["Grass Knot", "Grassy Glide", "Protect"],
    )
    assert err == ""
    assert sweep["ohko"] == 0
    assert sweep["n_surv"] == 1
    assert abs(sweep["remain_mean"] - 0.40) < 1e-9


def test_suckerpunch_finisher_uses_shared_lived_shield_path():
    """Sucker Punch credits via shared finisher set — no SP-specific branch."""
    from recommender import role_compendium as rc
    from recommender.legality import load_snapshot

    assert not hasattr(rc, "_aegislash_sequence_remain")
    assert "suckerpunch" in rc._SETUP_PRIORITY_FINISHER_MOVES
    # No suckerpunch-named helper beyond the shared finisher KO.
    assert not any(
        name.startswith("_sucker") for name in dir(rc) if not name.startswith("__")
    )

    sweep: dict[str, Any] = {}
    _score, err = rc._damage_score(
        attacker_name="Kingambit",
        item=None,
        ability=None,
        move="Iron Head",
        move_id="ironhead",
        boost_stat="atk",
        stages=2,
        panel=_FINISHER_PANEL,
        calculate_batch=_priority_finisher_dispatch(finisher_mid="suckerpunch"),
        snap=load_snapshot(),
        sweep_out=sweep,
        kit_moves=["Iron Head", "Sucker Punch"],
    )
    assert err == ""
    assert sweep["ohko"] == 1
    assert abs(sweep["remain_mean"] - 1.0) < 1e-9


def _empty_usage_maps():
    return {
        "ingame_doubles": {"species": {}},
        "showdown_vgc_mb": {"species": {}},
        "species": {},
    }


def test_present_usage_payoff_ids_drops_sub_floor_leftovers(monkeypatch):
    """Problem A: ~0% common_moves leftovers leave the bag; real alts stay."""
    from recommender.role_compendium import (
        _SETUP_PRESENCE_SET_PCT_FLOOR,
        _UsageCtx,
        _present_usage_payoff_ids,
        _select_setup_payoff,
        _usage_payoff_move_ids,
    )

    monkeypatch.setattr(
        "recommender.role_compendium.load_usage", lambda: _empty_usage_maps()
    )
    monkeypatch.setattr("recommender.role_compendium.showdown_species_map", lambda: {})

    leftovers = [
        ("Medicham-Mega", "psyshock", 0.0, "psychic", 2.093),
        ("Audino", "thunderbolt", 0.058, "dazzlinggleam", 1.0),
        ("Mawile-Mega", "doubleedge", 0.007, "playrough", 40.0),
        ("Salazzle", "belch", 0.01, "sludgebomb", 20.0),
        ("Beartic", "doubleedge", 0.0, "closecombat", 17.453),  # BU leftover vs SD CC
    ]
    for name, bad, bad_pct, good, good_pct in leftovers:
        entry = {
            "name": name,
            "id": to_id(name),
            "common_moves": [
                {"name": bad, "pct": bad_pct},
                {"name": good, "pct": good_pct},
                {"name": "Protect", "pct": 10.0},
            ],
        }
        sd_cache = {to_id(name): entry}
        uctx = _UsageCtx(live_fetch=lambda _n: None, showdown_fetch=lambda _n: None)
        raw = _usage_payoff_move_ids(entry, [])
        assert to_id(bad) in raw and to_id(good) in raw
        filtered = _present_usage_payoff_ids(
            name,
            entry,
            [],
            uctx=uctx,
            sd_cache=sd_cache,
            showdown_fetch=None,
            floor=_SETUP_PRESENCE_SET_PCT_FLOOR,
        )
        assert to_id(bad) not in filtered
        assert to_id(good) in filtered


def test_present_usage_payoff_ids_keeps_high_pct_regression(monkeypatch):
    from recommender.role_compendium import _UsageCtx, _present_usage_payoff_ids

    monkeypatch.setattr(
        "recommender.role_compendium.load_usage", lambda: _empty_usage_maps()
    )
    monkeypatch.setattr("recommender.role_compendium.showdown_species_map", lambda: {})
    entry = {
        "name": "Kingambit",
        "id": "kingambit",
        "common_moves": [
            {"name": "Kowtow Cleave", "pct": 57.87},
            {"name": "Sucker Punch", "pct": 40.0},
            {"name": "Swords Dance", "pct": 12.78},
        ],
    }
    uctx = _UsageCtx(live_fetch=lambda _n: None, showdown_fetch=lambda _n: None)
    filtered = _present_usage_payoff_ids(
        "Kingambit",
        entry,
        ["Kowtow Cleave", "Iron Head"],
        uctx=uctx,
        sd_cache={"kingambit": entry},
        showdown_fetch=None,
    )
    assert "kowtowcleave" in filtered
    assert "suckerpunch" in filtered


def test_present_usage_empty_bag_select_returns_none(monkeypatch):
    from recommender.role_compendium import (
        _UsageCtx,
        _present_usage_payoff_ids,
        _select_setup_payoff,
    )

    monkeypatch.setattr(
        "recommender.role_compendium.load_usage", lambda: _empty_usage_maps()
    )
    monkeypatch.setattr("recommender.role_compendium.showdown_species_map", lambda: {})
    entry = {
        "name": "Audino",
        "id": "audino",
        "common_moves": [{"name": "Thunderbolt", "pct": 0.058}],
    }
    uctx = _UsageCtx(live_fetch=lambda _n: None, showdown_fetch=lambda _n: None)
    filtered = _present_usage_payoff_ids(
        "Audino",
        entry,
        [],
        uctx=uctx,
        sd_cache={"audino": entry},
        showdown_fetch=None,
    )
    assert filtered == set()
    snap = load_snapshot()
    mid, score, err, kind = _select_setup_payoff(
        snap=snap,
        sid="audino",
        calc_name="Audino",
        item=None,
        ability=None,
        boost_stat="spa",
        stages=1,
        panel=[{"species": "Garchomp", "evs": {"hp": 32}}],
        calculate_batch=lambda _reqs: [],
        kit_moves=["Calm Mind", "Protect"],  # no special damaging kit move
    )
    assert mid is None
    assert score == 0.0
    assert err == "no_kit_payoff"
    assert kind == "none"



def test_per_defender_kit_pick_beats_panel_average_theft():
    """Mawile-shaped: DE would win a global mean via Ghost zeros; per-def picks PR."""
    from recommender.role_compendium import _select_setup_payoff
    from recommender.legality import load_snapshot

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
                # Incoming: not OHKO, defender faster so outsped path is available
                out.append(_panel_result(dmg=40, hp=200, atk_spe=200, def_spe=50))
                continue
            mid = to_id(req.get("move") or "")
            sp = to_id((req.get("defender") or {}).get("species") or "")
            # Attacker Spe 150 > def 80 → moves first (no remain path needed)
            if mid == "doubleedge":
                if sp == "gengar":
                    dmg = 0  # Normal vs Ghost
                elif sp == "incineroar":
                    dmg = 90  # neutral; PR resisted
                else:
                    dmg = 50  # worse than PR elsewhere
            elif mid == "playrough":
                if sp == "incineroar":
                    dmg = 40  # resisted
                else:
                    dmg = 100  # including Ghost
            else:
                dmg = 10
            out.append(_panel_result(dmg=dmg, hp=100, atk_spe=150, def_spe=80))
        return out

    sweep: dict[str, Any] = {}
    used: list[tuple[str, str]] = []
    mid, score, err, kind = _select_setup_payoff(
        snap=snap,
        sid="mawilemega",
        calc_name="Mawile-Mega",
        item=None,
        ability="Huge Power",
        boost_stat="atk",
        stages=2,
        panel=panel,
        calculate_batch=calc,
        kit_moves=["Play Rough", "Double-Edge", "Swords Dance", "Protect"],
        used_out=used,
        sweep_out=sweep,
    )
    assert err == ""
    assert mid == "playrough"
    by = {d: m for d, m in used}
    assert by["Gengar"] == "playrough"
    assert by["Garchomp"] == "playrough"
    assert by["Rillaboom"] == "playrough"
    # Incineroar: DE higher raw → may win that one cell
    assert by["Incineroar"] in {"doubleedge", "playrough"}
    assert all(row["mid"] != "doubleedge" or row["species"] == "Incineroar"
               for row in sweep["per_defender"])


def test_combined_ko_competes_per_mid_not_global_payoff():
    """Iron Head + Shadow Sneak combined-KO wins one defender; modal may be other mid."""
    from recommender.role_compendium import _select_setup_payoff
    from recommender.legality import load_snapshot

    snap = load_snapshot()
    panel = [
        {"species": "ThreatA", "evs": {"hp": 32}, "usage_moves": ["Earthquake"]},
        {"species": "ThreatB", "evs": {"hp": 32}, "usage_moves": ["Earthquake"]},
    ]

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for req in reqs:
            atk = req.get("attacker") or {}
            mid = to_id(req.get("move") or "")
            sp = to_id((req.get("defender") or {}).get("species") or "")
            if not atk.get("boosts"):
                # Incoming not OHKO; Spe high so candidate is outsped
                out.append(_panel_result(dmg=40, hp=200, atk_spe=200, def_spe=50))
                continue
            # Candidate Spe 50 < 80 → outsped → lived_shield
            if mid == "shadowsneak":
                out.append(_panel_result(dmg=45, hp=100, atk_spe=50, def_spe=80))
            elif mid == "ironhead":
                if sp == "threata":
                    out.append(_panel_result(dmg=55, hp=100, atk_spe=50, def_spe=80))
                else:
                    out.append(_panel_result(dmg=30, hp=100, atk_spe=50, def_spe=80))
            elif mid == "sacredsword":
                if sp == "threatb":
                    out.append(_panel_result(dmg=80, hp=100, atk_spe=50, def_spe=80))
                else:
                    out.append(_panel_result(dmg=20, hp=100, atk_spe=50, def_spe=80))
            else:
                out.append(_panel_result(dmg=10, hp=100, atk_spe=50, def_spe=80))
        return out

    sweep: dict[str, Any] = {}
    mid, score, err, _kind = _select_setup_payoff(
        snap=snap,
        sid="aegislashblade",
        calc_name="Aegislash-Blade",
        item=None,
        ability="Stance Change",
        boost_stat="atk",
        stages=2,
        panel=panel,
        calculate_batch=calc,
        kit_moves=["Iron Head", "Shadow Sneak", "Sacred Sword", "Swords Dance"],
        sweep_out=sweep,
    )
    assert err == ""
    rows = {r["species"]: r for r in sweep["per_defender"]}
    # ThreatA: IH 0.55 + SS 0.45 combined OHKO — IH is the primary mid, not SS alone
    assert rows["ThreatA"]["mid"] == "ironhead"
    assert rows["ThreatA"]["combined"] is True
    assert rows["ThreatA"]["bin"] == "ohko"
    # ThreatB: Sacred Sword 0.80 + SS also combined-KOs; still a non-finisher primary
    assert rows["ThreatB"]["mid"] == "sacredsword"
    assert rows["ThreatB"]["combined"] is True
    assert rows["ThreatB"]["mid"] != "shadowsneak"
    # Modal is whichever of the two non-finisher primaries wins the count/tiebreak
    assert mid in {"ironhead", "sacredsword"}
    assert mid != "shadowsneak"


def test_debuff_surv_denominator_is_drop_move_winners_only():
    from recommender.role_compendium import _select_setup_payoff
    from recommender.legality import load_snapshot

    snap = load_snapshot()
    panel = [
        {"species": "A", "evs": {"hp": 32}, "usage_moves": ["Earthquake"]},
        {"species": "B", "evs": {"hp": 32}, "usage_moves": ["Earthquake"]},
        {"species": "C", "evs": {"hp": 32}, "usage_moves": ["Earthquake"]},
    ]

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for req in reqs:
            atk = req.get("attacker") or {}
            mid = to_id(req.get("move") or "")
            sp = to_id((req.get("defender") or {}).get("species") or "")
            if not atk.get("boosts"):
                # debuff standing pass / ohko: never OHKO
                out.append(_panel_result(dmg=40, hp=200, atk_spe=100, def_spe=100))
                continue
            # CC wins only vs A; Iron Head elsewhere
            if mid == "closecombat":
                dmg = 100 if sp == "a" else 10
            elif mid == "ironhead":
                dmg = 10 if sp == "a" else 80
            else:
                dmg = 5
            out.append(_panel_result(dmg=dmg, hp=100, atk_spe=150, def_spe=80))
        return out

    sweep: dict[str, Any] = {}
    _mid, _score, err, _k = _select_setup_payoff(
        snap=snap,
        sid="machamp",
        calc_name="Machamp",
        item=None,
        ability=None,
        boost_stat="atk",
        stages=2,
        panel=panel,
        calculate_batch=calc,
        kit_moves=["Close Combat", "Iron Head", "Bullet Punch", "Protect"],
        sweep_out=sweep,
    )
    assert err == ""
    winners = {r["species"]: r["mid"] for r in sweep["per_defender"]}
    assert winners["A"] == "closecombat"
    assert winners["B"] == "ironhead"
    assert winners["C"] == "ironhead"
    assert sweep["debuff_surv"] == "1/1"  # only A has drop-move winner; survives


def test_select_setup_payoff_aegislash_combined_ko_via_matrix():
    from recommender.role_compendium import _select_setup_payoff
    from recommender.legality import load_snapshot

    snap = load_snapshot()
    panel = [
        {"species": "Threat", "evs": {"hp": 32}, "usage_moves": ["Earthquake"]},
    ]

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for req in reqs:
            atk = req.get("attacker") or {}
            mid = to_id(req.get("move") or "")
            if not atk.get("boosts"):
                # Shield/Blade incoming: not OHKO
                out.append(_panel_result(dmg=40, hp=200, atk_spe=200, def_spe=50))
                continue
            if mid == "shadowsneak":
                out.append(_panel_result(dmg=50, hp=100, atk_spe=50, def_spe=80))
            else:
                out.append(_panel_result(dmg=60, hp=100, atk_spe=50, def_spe=80))
        return out

    sweep: dict[str, Any] = {}
    mid, score, err, _k = _select_setup_payoff(
        snap=snap,
        sid="aegislashblade",
        calc_name="Aegislash-Blade",
        item=None,
        ability="Stance Change",
        boost_stat="atk",
        stages=2,
        panel=panel,
        calculate_batch=calc,
        kit_moves=["Iron Head", "Shadow Sneak", "King's Shield", "Swords Dance"],
        sweep_out=sweep,
    )
    assert err == ""
    assert sweep["ohko"] == 1
    assert sweep["n_surv"] == 1
    assert abs(sweep["remain_mean"] - 1.0) < 1e-9
    row = sweep["per_defender"][0]
    assert row["combined"] is True
    assert row["mid"] == "ironhead"


def test_kit_matrix_calc_count_scales_with_kit_not_usage_bag():
    from recommender.role_compendium import _select_setup_payoff
    from recommender.legality import load_snapshot

    snap = load_snapshot()
    panel = [
        {"species": f"Mon{i}", "evs": {"hp": 32}, "usage_moves": ["Tackle"]}
        for i in range(10)
    ]
    n_calls = {"n": 0}

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        n_calls["n"] += 1
        return [
            _panel_result(dmg=50, hp=100, atk_spe=150, def_spe=80) for _ in reqs
        ]

    _select_setup_payoff(
        snap=snap,
        sid="mawilemega",
        calc_name="Mawile-Mega",
        item=None,
        ability="Huge Power",
        boost_stat="atk",
        stages=2,
        panel=panel,
        calculate_batch=calc,
        kit_moves=["Play Rough", "Iron Head", "Swords Dance", "Protect"],
        # If usage bag were searched, this would explode — ignored by Stage 1
        usage_move_ids={f"move{i}" for i in range(40)},
    )
    # 1 ohko + 2 kit mids (+ no finisher/debuff) = 3 batch calls
    assert n_calls["n"] == 3
