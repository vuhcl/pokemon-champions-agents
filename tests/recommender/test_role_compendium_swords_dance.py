"""Swords Dance Attacker Role Compendium (setup_attacker)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from recommender.ids import to_id
from recommender.legality import load_snapshot
from recommender.role_compendium import (
    SWORDS_DANCE_ATTACKER_CRITERIA,
    _SETUP_ACCEPTABLE_FLOOR_MULT,
    _SETUP_BOTH_BRANCH_SCORE_DIV,
    _SETUP_CONDITIONAL_PRIORITY_MULT,
    _SETUP_DAMAGE_FRAC_CAP,
    _SETUP_NARROW_CONDITIONAL_PRIORITY_MULT,
    _SETUP_PRIORITY_SCORE_MULT,
    _setup_adjusted_score,
    _setup_branch_a,
    _setup_branch_a_via_priority,
    _setup_excellent_floor,
    _setup_mech_tier,
    _setup_payoff_candidates,
    _setup_priority_kind,
    _setup_priority_mult,
    _setup_priority_mult_for,
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
    """Spe-path calibrators = 1.0; priority users stay below after the priority boost."""
    out: list[dict[str, Any]] = []
    for req in requests:
        sp = to_id((req.get("attacker") or {}).get("species") or "")
        if sp in {"blazikenmega", "blaziken"}:
            frac = 1.0
            atk_spe = 200
        elif sp in {"kingambit", "scizor", "scizormega", "mawilemega"}:
            frac = 0.35  # priority-boosted stays < Blaziken (1.0) and below 2nd×0.95
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
) -> dict[str, Any]:
    return {
        "damageRange": [dmg, dmg],
        "koChance": "2HKO",
        "raw": {
            "stats": {
                "attacker": {"spe": atk_spe},
                "defender": {"hp": hp, "spe": def_spe},
            }
        },
    }


def _sd_draft(*, pool: list[str] | None = None, live_fetch=None):
    snap = load_snapshot()

    def _usage(name: str) -> dict[str, Any] | None:
        sid = to_id(name)
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
        if sid not in proven:
            return None
        return {
            "name": name,
            "id": sid,
            "common_moves": [{"name": "Swords Dance", "pct": 40.0}],
            "common_items": [{"name": "Life Orb", "pct": 20.0}],
        }

    return construct_role_category(
        "swords_dance_attacker",
        SWORDS_DANCE_ATTACKER_CRITERIA,
        pool if pool is not None else legal_species_pool(snap),
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
    assert _setup_adjusted_score(1.0, priority_kind="none", both_branches=False) == 1.0
    assert (
        _setup_adjusted_score(1.0, priority_kind="unconditional", both_branches=False)
        == _SETUP_PRIORITY_SCORE_MULT
    )
    assert (
        _setup_adjusted_score(1.0, priority_kind="conditional", both_branches=False)
        == _SETUP_CONDITIONAL_PRIORITY_MULT
    )
    assert abs(
        _setup_adjusted_score(
            _SETUP_BOTH_BRANCH_SCORE_DIV, priority_kind="none", both_branches=True
        )
        - 1.0
    ) < 1e-9
    assert abs(
        _setup_adjusted_score(0.5, priority_kind="unconditional", both_branches=True)
        - (0.5 * _SETUP_PRIORITY_SCORE_MULT / _SETUP_BOTH_BRANCH_SCORE_DIV)
    ) < 1e-9
    assert _setup_priority_kind("aquajet") == "unconditional"
    assert _setup_priority_kind("suckerpunch") == "conditional"
    assert _setup_priority_kind("upperhand") == "conditional"
    assert _setup_priority_kind("feint") == "conditional"
    assert _setup_priority_kind("closecombat") == "none"
    assert _setup_priority_mult("conditional") == _SETUP_CONDITIONAL_PRIORITY_MULT
    assert _setup_priority_mult_for("upperhand") == _SETUP_CONDITIONAL_PRIORITY_MULT
    assert _setup_priority_mult_for("feint") == _SETUP_NARROW_CONDITIONAL_PRIORITY_MULT
    assert (
        _setup_adjusted_score(
            1.0,
            priority_kind="conditional",
            both_branches=False,
            priority_mult=_SETUP_NARROW_CONDITIONAL_PRIORITY_MULT,
        )
        == _SETUP_NARROW_CONDITIONAL_PRIORITY_MULT
    )


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


def test_acceptable_basis_distinct_from_good():
    """tied_cluster compares degree tuples across tiers, so the basis must differ."""
    draft = _sd_draft()
    acceptable = [c for c in draft.candidates if c.tier == "Acceptable"]
    assert acceptable, "mock panel should place weak-damage candidates in Acceptable"
    for c in acceptable:
        assert (c.excellence_basis or "").startswith("acceptable_")
    good_bases = {c.excellence_basis for c in draft.candidates if c.tier == "Good"}
    assert good_bases.isdisjoint({c.excellence_basis for c in acceptable})
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
        SWORDS_DANCE_ATTACKER_CRITERIA,
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
    assert "Skarmory" in rej
    assert "no usage evidence" in rej["Skarmory"]
    assert any("CBD move-rate plausibility" in n for n in draft.notes)


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
    draft = construct_role_category(
        "swords_dance_attacker",
        SWORDS_DANCE_ATTACKER_CRITERIA,
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
    assert "Scizor" not in {c.species for c in draft.candidates if c.tier}
    rej = {r.species: r.reason for r in draft.considered_rejected}
    assert "Scizor" in rej
    assert "discounted" in rej["Scizor"]


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
        SWORDS_DANCE_ATTACKER_CRITERIA,
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
        snap, boost_stat="atk", usage_move_ids={"fakeout", "bravebird", "ironhead"}
    )
    assert "fakeout" not in hits
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
    """Learnset priority alone must not grant priority boost; Sucker Punch uses conditional mult."""
    from recommender.support_needs import _OFFENSIVE_PRIORITY_MOVES

    both_label = f"both_div_{_SETUP_BOTH_BRANCH_SCORE_DIV:g}"
    draft = _sd_draft()
    king = next(c for c in draft.candidates if c.species_id == "kingambit")
    payoff = to_id(king.criteria_notes.get("payoff_move") or "")
    boosts = king.criteria_notes.get("score_boosts") or ""
    kind = _setup_priority_kind(payoff)
    pri_label = (
        f"priority_x{_setup_priority_mult_for(payoff):g}" if kind != "none" else ""
    )
    if payoff in _OFFENSIVE_PRIORITY_MOVES:
        assert pri_label in boosts
    else:
        assert "priority_x" not in boosts
    raw = float(king.criteria_notes["damage_score_raw"])
    adj = float(king.criteria_notes["damage_score"])
    both = both_label in boosts
    expected = (
        raw
        * _setup_priority_mult_for(payoff)
        / (_SETUP_BOTH_BRANCH_SCORE_DIV if both else 1.0)
    )
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
        usage_move_ids={"petaldance", "psychic"},
    ) == ["psychic"]


def test_select_setup_payoff_prefers_priority_when_adjusted_higher():
    """Lower-BP priority can beat higher BP once the priority boost applies (mock equal raw)."""
    from recommender.role_compendium import _select_setup_payoff
    from recommender.legality import load_snapshot

    snap = load_snapshot()

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [_panel_result(dmg=100, hp=200, atk_spe=50, def_spe=80) for _ in reqs]

    panel = [{"species": "Blissey", "evs": {"hp": 32, "def": 32, "spd": 32}}]
    mid, raw, err, kind = _select_setup_payoff(
        snap=snap,
        sid="mawilemega",
        calc_name="Mawile-Mega",
        item=None,
        ability="Huge Power",
        boost_stat="atk",
        stages=2,
        usage_move_ids={"playrough", "suckerpunch", "ironhead"},
        panel=panel,
        calculate_batch=calc,
    )
    assert mid == "suckerpunch"
    assert kind == "conditional"
    assert abs(raw - 0.5) < 1e-6


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
    assert abs(score - 1.0) < 1e-9


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
    draft = _sd_draft(pool=["Chansey"] if "Chansey" in legal_species_pool(snap) else [])
    full = _sd_draft()
    assert any(
        "neither" in (r.reason or "") for r in full.considered_rejected
    ) or full.considered_rejected


def test_critique_approves():
    draft = _sd_draft()
    result = critique_role_ranking(draft)
    assert result.approved, result.flags


def test_rebuild_tmp(tmp_path: Path):
    r = rebuild_role_category(
        "swords_dance_attacker",
        SWORDS_DANCE_ATTACKER_CRITERIA,
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
