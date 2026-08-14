"""Offense-bulk / offense-speed / def-payoff setup constructors (no persist)."""

from __future__ import annotations

from typing import Any

from recommender.ids import to_id
from recommender.role_compendium import (
    BULK_UP_ATTACKER_CRITERIA,
    CALM_MIND_ATTACKER_CRITERIA,
    DRAGON_DANCE_ATTACKER_CRITERIA,
    IRON_DEFENSE_BODY_PRESS_CRITERIA,
    NASTY_PLOT_ATTACKER_CRITERIA,
    CandidateEval,
    _SETUP_THREAT_ENCOUNTER_GAMES,
    _SETUP_THREAT_USAGE_PCT_FLOOR,
    _is_bulk_crossing,
    _ko_frac_bin,
    _ranked_payoff_moves,
    _self_boosts,
    _setup_bulk_crossings,
    _setup_threat_defenders,
    _sort_members_by_crossings,
    _sort_members_by_sweep,
    exact_self_boost_move,
    load_stat_boosts,
)


def test_exact_self_boost_locks_cm_bu_dd():
    assert exact_self_boost_move({"spa": 1, "spd": 1}) == "calmmind"
    assert exact_self_boost_move({"atk": 1, "def": 1}) == "bulkup"
    assert exact_self_boost_move({"atk": 1, "spe": 1}) == "dragondance"


def test_coil_is_not_bulk_up():
    coil = _self_boosts(load_stat_boosts()["moves"]["coil"])
    assert coil != {"atk": 1, "def": 1}


def test_criteria_kinds():
    assert CALM_MIND_ATTACKER_CRITERIA["kind"] == "offense_bulk_setup"
    assert BULK_UP_ATTACKER_CRITERIA["kind"] == "offense_bulk_setup"
    assert DRAGON_DANCE_ATTACKER_CRITERIA["kind"] == "offense_speed_setup"


def test_admission_keys_only_on_sd_cm_bu():
    assert CALM_MIND_ATTACKER_CRITERIA["damage_admission_floor"] == 0.708
    assert CALM_MIND_ATTACKER_CRITERIA["acceptable_floor_mult"] == 0.88
    assert BULK_UP_ATTACKER_CRITERIA["damage_admission_floor"] == 0.748
    assert BULK_UP_ATTACKER_CRITERIA["acceptable_floor_mult"] == 0.90
    for crit in (
        NASTY_PLOT_ATTACKER_CRITERIA,
        DRAGON_DANCE_ATTACKER_CRITERIA,
        IRON_DEFENSE_BODY_PRESS_CRITERIA,
    ):
        assert "damage_admission_floor" not in crit
        assert "acceptable_floor_mult" not in crit


def test_setup_threat_panel_uses_15_game_usage_floor():
    assert _SETUP_THREAT_ENCOUNTER_GAMES == 15
    assert abs(_SETUP_THREAT_USAGE_PCT_FLOOR - 100.0 * (1.0 - 0.5 ** (1.0 / 15))) < 1e-9
    panel = _setup_threat_defenders()
    names = {d["species"] for d in panel}
    assert "Whimsicott" in names
    assert "Garchomp" in names
    assert "Charizard-Mega-Y" in names
    assert "Garchomp-Mega" not in names
    assert "Charizard-Mega-X" not in names
    assert len(panel) > 8
    assert all(d.get("usage_moves") or d.get("moves") for d in panel)
    sable = next(d for d in panel if d["species"] == "Sableye")
    assert any(to_id(m) == "foulplay" for m in sable.get("usage_moves") or [])
    assert to_id(sable.get("item") or "") == "lightclay"
    sini = next(d for d in panel if d["species"] == "Sinistcha")
    assert to_id(sini.get("item") or "") == "kasibberry"
    cmy = next(d for d in panel if d["species"] == "Charizard-Mega-Y")
    assert to_id(cmy.get("item") or "") == "charizarditey"
    assert to_id(cmy.get("ability") or "") == "drought"
    garchomp = next(d for d in panel if d["species"] == "Garchomp")
    assert garchomp.get("nature") or garchomp.get("evs")


def test_ranked_stored_power_uses_boost_count_not_snapshot():
    snap = {
        "species": {"espeon": {"types": ["Psychic"]}},
        "moves": {
            "storedpower": {"category": "Special", "basePower": 20, "type": "Psychic"},
            "psybeam": {"category": "Special", "basePower": 65, "type": "Psychic"},
        },
    }
    unb = _ranked_payoff_moves(
        snap,
        "espeon",
        set(),
        boost_stat="spa",
        usage_moves=["storedpower", "psybeam"],
        usage_only=True,
        boost_count=0,
    )
    assert unb.index("psybeam") < unb.index("storedpower")
    boosted = _ranked_payoff_moves(
        snap,
        "espeon",
        set(),
        boost_stat="spa",
        usage_moves=["storedpower", "psybeam"],
        usage_only=True,
        boost_count=3,
    )
    assert boosted.index("storedpower") < boosted.index("psybeam")


def test_cm_exact_boosts_sum_is_two_for_stored_power_sort():
    """Calm Mind spa+spd → boost_count=2; Stored Power 60 BP beats a 50 BP special."""
    snap = {
        "species": {"espeon": {"types": ["Psychic"]}},
        "moves": {
            "storedpower": {"category": "Special", "basePower": 20, "type": "Psychic"},
            "psybeam": {"category": "Special", "basePower": 50, "type": "Psychic"},
        },
    }
    assert sum({"spa": 1, "spd": 1}.values()) == 2
    one = _ranked_payoff_moves(
        snap,
        "espeon",
        set(),
        boost_stat="spa",
        usage_moves=["storedpower", "psybeam"],
        usage_only=True,
        boost_count=1,
    )
    two = _ranked_payoff_moves(
        snap,
        "espeon",
        set(),
        boost_stat="spa",
        usage_moves=["storedpower", "psybeam"],
        usage_only=True,
        boost_count=2,
    )
    assert one.index("psybeam") < one.index("storedpower")
    assert two.index("storedpower") < two.index("psybeam")


def test_ko_frac_bins_and_bulk_crossings():
    assert _ko_frac_bin(1.0) == "ohko"
    assert _ko_frac_bin(0.99) == "2hko"
    assert _ko_frac_bin(0.5) == "2hko"
    assert _ko_frac_bin(0.49) == "3plus"
    assert _is_bulk_crossing(1.1, 0.8)
    assert _is_bulk_crossing(1.1, 0.4)
    assert _is_bulk_crossing(0.6, 0.4)
    assert not _is_bulk_crossing(0.4, 0.2)
    assert not _is_bulk_crossing(1.2, 1.0)
    assert not _is_bulk_crossing(0.7, 0.55)


def test_sort_members_by_crossings_within_tier():
    def cand(name: str, tier: str, k: int, score: float) -> CandidateEval:
        return CandidateEval(
            species=name,
            species_id=to_id(name),
            tier=tier,
            delivery_class="move_setup",
            mechanism="Bulk Up",
            criteria_notes={
                "bulk_crossings": f"{k}/20",
                "damage_score": f"{score:.3f}",
            },
            claimed_traits=[],
            reasoning="",
        )

    members = [
        cand("A", "Good", 2, 0.9),
        cand("B", "Excellent", 1, 1.0),
        cand("C", "Good", 8, 0.5),
    ]
    out = _sort_members_by_crossings(members, field="bulk_crossings")
    assert [c.species for c in out] == ["B", "C", "A"]


def test_sort_members_by_sweep_ohko_then_remain_na_last():
    def cand(
        name: str,
        tier: str,
        ohko: int,
        n: int,
        *,
        mean: str,
        score: float,
    ) -> CandidateEval:
        return CandidateEval(
            species=name,
            species_id=to_id(name),
            tier=tier,
            delivery_class="move_setup",
            mechanism="Swords Dance",
            criteria_notes={
                "sweep_ohko": f"{ohko}/{n}",
                "survive_hp_mean": mean,
                "damage_score": f"{score:.3f}",
            },
            claimed_traits=[],
            reasoning="",
        )

    members = [
        cand("SlowChip", "Good", 10, 37, mean="0.80", score=0.90),
        cand("FastKO", "Good", 22, 37, mean="n/a", score=0.76),
        cand("SliverKO", "Good", 22, 37, mean="0.10", score=0.95),
        cand("Top", "Excellent", 5, 37, mean="0.50", score=1.20),
    ]
    out = _sort_members_by_sweep(members)
    assert [c.species for c in out] == ["Top", "SliverKO", "FastKO", "SlowChip"]


def test_bulk_crossings_fallback_and_immunity_excluded():
    snap = {
        "species": {
            "garchomp": {"types": ["Dragon", "Ground"]},
            "incineroar": {"types": ["Fire", "Dark"]},
            "sinistcha": {"types": ["Grass", "Ghost"]},
            "blissey": {"types": ["Normal"]},
        },
        "moves": {
            "earthquake": {"category": "Physical", "basePower": 100, "type": "Ground"},
            "dragonclaw": {"category": "Physical", "basePower": 80, "type": "Dragon"},
            "poltergeist": {"category": "Physical", "basePower": 110, "type": "Ghost"},
        },
    }
    panel = [
        {"species": "Garchomp", "usage_moves": ["Earthquake"], "evs": {"hp": 32}},
        {"species": "Incineroar", "usage_moves": ["Earthquake"], "evs": {"hp": 32}},
        {"species": "Sinistcha", "usage_moves": ["Poltergeist"], "evs": {"hp": 32}},
        {
            "species": "Blissey",
            "usage_moves": ["Poltergeist", "Dragon Claw"],
            "evs": {"hp": 32},
        },
    ]

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for req in reqs:
            atk = str(req["attacker"]["species"])
            mid = to_id(req["move"])
            boosts = req["defender"].get("boosts") or {}
            boosted = bool(boosts.get("def"))
            dmg = 0
            if atk == "Garchomp" and mid == "earthquake":
                dmg = 40 if boosted else 100
            elif atk == "Incineroar" and mid == "earthquake":
                dmg = 40 if boosted else 60
            elif atk == "Sinistcha" and mid == "poltergeist":
                dmg = 0
            elif atk == "Blissey" and mid == "poltergeist":
                dmg = 0
            elif atk == "Blissey" and mid == "dragonclaw":
                dmg = 80
            out.append(
                {
                    "damageRange": [dmg, dmg],
                    "raw": {"stats": {"defender": {"hp": 100}, "attacker": {"spe": 100}}},
                }
            )
        return out

    k, n = _setup_bulk_crossings(
        snap=snap,
        candidate_name="Blissey",
        calc_name="Blissey",
        panel=panel,
        def_stat="def",
        stages=1,
        calculate_batch=calc,
    )
    # Garchomp OHKO→2HKO, Incineroar 2HKO→3HKO+, Sinistcha all-zero excluded,
    # Blissey Poltergeist 0 then Dragon Claw 80/80 still 2HKO (not a crossing).
    assert (k, n) == (2, 3)


def test_setup_kit_drops_choice_items():
    from recommender.role_compendium import _drop_setup_choice_item

    assert _drop_setup_choice_item("Choice Scarf") is None
    assert _drop_setup_choice_item("Choice Band") is None
    assert _drop_setup_choice_item("Choice Specs") is None
    assert _drop_setup_choice_item("Life Orb") == "Life Orb"
    assert _drop_setup_choice_item(None) is None


def _panel_result(
    *,
    dmg: int,
    hp: int = 100,
    atk_spe: int = 100,
    def_spe: int = 80,
) -> dict[str, Any]:
    return {
        "damageRange": [dmg, dmg],
        "koChance": "2HKO",
        "raw": {
            "stats": {
                "attacker": {"spe": atk_spe, "hp": 159},
                "defender": {"hp": hp, "spe": def_spe},
            }
        },
    }


def test_bulk_up_aquajet_priority_finisher_combined_ko():
    """Non-SD proof: Bulk Up carrier gets species-agnostic finisher credit."""
    from recommender.role_compendium import _damage_score
    from recommender.legality import load_snapshot

    fin_mid = "aquajet"

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for req in reqs:
            atk = req.get("attacker") or {}
            if not atk.get("boosts"):
                out.append(_panel_result(dmg=60, hp=100, atk_spe=150, def_spe=50))
                continue
            mid = to_id(str(req.get("move") or ""))
            dmg = 50 if mid == fin_mid else 60
            out.append(_panel_result(dmg=dmg, hp=100, atk_spe=50, def_spe=150))
        return out

    sweep: dict[str, Any] = {}
    _score, err = _damage_score(
        attacker_name="Starmie-Mega",
        item=None,
        ability=None,
        move="Liquidation",
        move_id="liquidation",
        boost_stat="atk",
        stages=1,
        boosts={"atk": 1, "def": 1},
        panel=[{"species": "Garchomp", "evs": {"hp": 32}, "usage_moves": ["Earthquake"]}],
        calculate_batch=calc,
        snap=load_snapshot(),
        sweep_out=sweep,
        kit_moves=["Bulk Up", "Liquidation", "Aqua Jet", "Protect"],
    )
    assert err == ""
    assert sweep["ohko"] == 1
    assert sweep["n_surv"] == 1
    assert abs(sweep["remain_mean"] - 1.0) < 1e-9


def test_present_usage_payoff_ids_stage_and_idbp_coverage(monkeypatch):
    """CM/BU bag and ID+BP coverage fallbacks drop sub-floor leftovers."""
    from recommender.legality import load_snapshot
    from recommender.role_compendium import (
        _UsageCtx,
        _present_usage_payoff_ids,
        _ranked_payoff_moves,
    )

    monkeypatch.setattr(
        "recommender.role_compendium.load_usage",
        lambda: {
            "ingame_doubles": {"species": {}},
            "showdown_vgc_mb": {"species": {}},
            "species": {},
        },
    )
    monkeypatch.setattr("recommender.role_compendium.showdown_species_map", lambda: {})

    uctx = _UsageCtx(live_fetch=lambda _n: None, showdown_fetch=lambda _n: None)

    cm_entry = {
        "name": "Medicham-Mega",
        "id": "medichammega",
        "common_moves": [
            {"name": "Psyshock", "pct": 0.0},
            {"name": "Psychic", "pct": 2.093},
            {"name": "Calm Mind", "pct": 0.129},
        ],
    }
    cm_ids = _present_usage_payoff_ids(
        "Medicham-Mega",
        cm_entry,
        [],
        uctx=uctx,
        sd_cache={"medichammega": cm_entry},
        showdown_fetch=None,
    )
    assert "psyshock" not in cm_ids
    assert "psychic" in cm_ids

    bu_entry = {
        "name": "Beartic",
        "id": "beartic",
        "common_moves": [
            {"name": "Double-Edge", "pct": 0.0},
            {"name": "Close Combat", "pct": 17.453},
            {"name": "Bulk Up", "pct": 0.219},
        ],
    }
    bu_ids = _present_usage_payoff_ids(
        "Beartic",
        bu_entry,
        [],
        uctx=uctx,
        sd_cache={"beartic": bu_entry},
        showdown_fetch=None,
    )
    assert "doubleedge" not in bu_ids
    assert "closecombat" in bu_ids

    id_entry = {
        "name": "Aggron-Mega",
        "id": "aggronmega",
        "common_moves": [
            {"name": "Body Press", "pct": 40.0},
            {"name": "Iron Defense", "pct": 30.0},
            {"name": "Shadow Ball", "pct": 0.0},
            {"name": "Heavy Slam", "pct": 15.0},
        ],
    }
    cov = _present_usage_payoff_ids(
        "Aggron-Mega",
        id_entry,
        ["Body Press", "Heavy Slam"],
        uctx=uctx,
        sd_cache={"aggronmega": id_entry},
        showdown_fetch=None,
    )
    assert "shadowball" not in cov
    assert "heavyslam" in cov
    ranked = _ranked_payoff_moves(
        load_snapshot(),
        "aggronmega",
        set(),
        boost_stat="atk",
        usage_moves=sorted(cov),
        usage_only=True,
        boost_count=2,
    )
    assert "shadowball" not in ranked
    assert "bodypress" in ranked or "heavyslam" in ranked


def test_dd_setup_presence_floor_excludes_thin_keeps_cluster(monkeypatch):
    """DD 1.0% floor: Dragonite-Mega 0.390 out; Scrafty-Mega 1.363 in."""
    from recommender.role_compendium import (
        _DD_SETUP_PRESENCE_FLOOR,
        _SETUP_PRESENCE_SET_PCT_FLOOR,
        _UsageCtx,
        _hits_clear_set_pct_floor,
    )

    assert _DD_SETUP_PRESENCE_FLOOR == 1.0
    assert _SETUP_PRESENCE_SET_PCT_FLOOR == 0.1

    monkeypatch.setattr(
        "recommender.role_compendium.load_usage",
        lambda: {
            "ingame_doubles": {"species": {}},
            "showdown_vgc_mb": {"species": {}},
            "species": {},
        },
    )
    monkeypatch.setattr("recommender.role_compendium.showdown_species_map", lambda: {})

    thin = {
        "name": "Dragonite-Mega",
        "id": "dragonitemega",
        "common_moves": [{"name": "Dragon Dance", "pct": 0.390}],
    }
    kept = {
        "name": "Scrafty-Mega",
        "id": "scraftymega",
        "common_moves": [{"name": "Dragon Dance", "pct": 1.363}],
    }
    uctx = _UsageCtx(live_fetch=lambda _n: None, showdown_fetch=lambda _n: None)

    assert not _hits_clear_set_pct_floor(
        "Dragonite-Mega",
        {"dragondance"},
        floor=_DD_SETUP_PRESENCE_FLOOR,
        uctx=uctx,
        sd_cache={"dragonitemega": thin},
        showdown_fetch=None,
    )
    # Still clears the shared 0.1% ghost floor — only the DD override rejects it.
    assert _hits_clear_set_pct_floor(
        "Dragonite-Mega",
        {"dragondance"},
        floor=_SETUP_PRESENCE_SET_PCT_FLOOR,
        uctx=uctx,
        sd_cache={"dragonitemega": thin},
        showdown_fetch=None,
    )
    assert _hits_clear_set_pct_floor(
        "Scrafty-Mega",
        {"dragondance"},
        floor=_DD_SETUP_PRESENCE_FLOOR,
        uctx=uctx,
        sd_cache={"scraftymega": kept},
        showdown_fetch=None,
    )


def test_cm_bu_presence_floor_unaffected_by_dd_override(monkeypatch):
    """CM/BU at DD's excluded band still clear the shared 0.1% floor."""
    from recommender.role_compendium import (
        _DD_SETUP_PRESENCE_FLOOR,
        _SETUP_PRESENCE_SET_PCT_FLOOR,
        _UsageCtx,
        _hits_clear_set_pct_floor,
    )

    monkeypatch.setattr(
        "recommender.role_compendium.load_usage",
        lambda: {
            "ingame_doubles": {"species": {}},
            "showdown_vgc_mb": {"species": {}},
            "species": {},
        },
    )
    monkeypatch.setattr("recommender.role_compendium.showdown_species_map", lambda: {})
    uctx = _UsageCtx(live_fetch=lambda _n: None, showdown_fetch=lambda _n: None)

    # Same numeric band as DD thin cluster (0.390) — CM/BU must stay admitted at 0.1%.
    cm_entry = {
        "name": "Cofagrigus",
        "id": "cofagrigus",
        "common_moves": [{"name": "Calm Mind", "pct": 0.390}],
    }
    bu_entry = {
        "name": "Passimian",
        "id": "passimian",
        "common_moves": [{"name": "Bulk Up", "pct": 0.390}],
    }
    assert _hits_clear_set_pct_floor(
        "Cofagrigus",
        {"calmmind"},
        floor=_SETUP_PRESENCE_SET_PCT_FLOOR,
        uctx=uctx,
        sd_cache={"cofagrigus": cm_entry},
        showdown_fetch=None,
    )
    assert _hits_clear_set_pct_floor(
        "Passimian",
        {"bulkup"},
        floor=_SETUP_PRESENCE_SET_PCT_FLOOR,
        uctx=uctx,
        sd_cache={"passimian": bu_entry},
        showdown_fetch=None,
    )
    # Same pct would fail DD's floor — proves the numeric band is real, not a no-op.
    assert not _hits_clear_set_pct_floor(
        "Cofagrigus",
        {"calmmind"},
        floor=_DD_SETUP_PRESENCE_FLOOR,
        uctx=uctx,
        sd_cache={"cofagrigus": cm_entry},
        showdown_fetch=None,
    )
