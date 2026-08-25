"""Item 7 Part A: pair-as-defender panel + spread-move credit."""

from __future__ import annotations

from typing import Any

from recommender.ids import to_id
from recommender.legality import load_snapshot
from recommender.role_compendium_setup import (
    _is_spread_damage_mid,
    _pair_entry_label,
    _setup_kit_matrix_score,
    _setup_payoff_notes,
    _setup_threat_defenders,
)
from recommender.team_candidates import (
    _FLOETTE_ETERNAL_SID,
    _FLOETTE_MEGA_SID,
    pair_lookup_species_id,
)


def _hit(
    *,
    dmg: int,
    hp: int = 100,
    atk_spe: int = 200,
    def_spe: int = 50,
    recoil_pct: float | None = None,
    recovery_hp: float | None = None,
    atk_hp: int = 100,
) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "stats": {
            "attacker": {"hp": atk_hp, "spe": atk_spe},
            "defender": {"hp": hp, "spe": def_spe},
        }
    }
    if recoil_pct is not None:
        raw["recoil"] = {"recoil": [recoil_pct, recoil_pct]}
    if recovery_hp is not None:
        raw["recovery"] = {"recovery": [recovery_hp, recovery_hp]}
    return {"damageRange": [dmg, dmg], "raw": raw}


def test_pair_lookup_floette_bridge_only():
    assert pair_lookup_species_id(_FLOETTE_MEGA_SID) == _FLOETTE_ETERNAL_SID
    assert pair_lookup_species_id("garchomp") == "garchomp"
    assert pair_lookup_species_id(_FLOETTE_ETERNAL_SID) == _FLOETTE_ETERNAL_SID


def test_threat_panel_top1_partners_coverage():
    panel = _setup_threat_defenders()
    assert len(panel) == 37
    assert all(isinstance(d.get("partner"), dict) for d in panel)
    assert all(d["partner"].get("species") for d in panel)

    rw = next(d for d in panel if d["species"] == "Rotom-Wash")
    assert rw["partner"]["species"] == "Garchomp"
    assert rw["partner_count"] == 201

    garch = next(d for d in panel if d["species"] == "Garchomp")
    chary = next(d for d in panel if d["species"] == "Charizard-Mega-Y")
    assert garch["partner"]["species"] == "Charizard-Mega-Y"
    assert chary["partner"]["species"] == "Garchomp"
    assert garch["partner_count"] == chary["partner_count"] == 3435


def test_floette_mega_pair_bridge_keeps_mega_calc_identity():
    panel = _setup_threat_defenders()
    floette = next(d for d in panel if d["species"] == "Floette-Mega")
    assert floette["partner"]["species"] == "Kingambit"
    assert floette["partner_count"] == 1082
    # Calc identity must remain Mega (Fairy Aura), not Eternal.
    assert to_id(floette.get("ability") or "") == "fairyaura"
    assert "partner" in floette
    assert floette["partner"].get("species") != "Floette-Eternal"


def test_spread_move_ids():
    assert _is_spread_damage_mid("rockslide")
    assert _is_spread_damage_mid("Earthquake")
    assert not _is_spread_damage_mid("playrough")
    assert not _is_spread_damage_mid("expandingforce")  # terrain not modeled


def test_single_target_skips_partner_calc():
    """Non-spread mid: only primary is sent to calc."""
    panel = [
        {
            "species": "Primary",
            "evs": {"hp": 32},
            "usage_moves": ["Earthquake"],
            "partner": {
                "species": "Partner",
                "evs": {"hp": 32},
                "usage_moves": ["Earthquake"],
            },
            "partner_count": 99,
        }
    ]
    seen_defs: list[str] = []

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for req in reqs:
            atk = req.get("attacker") or {}
            defn = req.get("defender") or {}
            dname = str(defn.get("species") or atk.get("species") or "")
            if atk.get("boosts"):
                seen_defs.append(str(defn.get("species") or ""))
            # Incoming: panel hits candidate (no boosts on attacker side of ohko batch
            # uses panel member as attacker — species is Primary).
            if not atk.get("boosts"):
                out.append(_hit(dmg=10, hp=100, atk_spe=50, def_spe=200))
            else:
                out.append(_hit(dmg=80, hp=100, atk_spe=200, def_spe=50))
            del dname
        return out

    snap = load_snapshot()
    _score, err, used, sweep = _setup_kit_matrix_score(
        snap=snap,
        sid="mawilemega",
        calc_name="Mawile-Mega",
        item=None,
        ability="Huge Power",
        boost_stat="atk",
        stages=2,
        panel=panel,
        calculate_batch=calc,
        mids=["playrough"],
        kit_moves=["swordsdance", "playrough"],
    )
    assert err == ""
    assert "Partner" not in seen_defs
    assert seen_defs.count("Primary") >= 1
    assert used == [("Primary+Partner", "playrough")]
    assert sweep["ohko"] == 0  # 80/100 → 2hko


def _pair_panel() -> list[dict[str, Any]]:
    return [
        {
            "species": "Primary",
            "evs": {"hp": 32},
            "usage_moves": ["Earthquake"],
            "partner": {
                "species": "Partner",
                "evs": {"hp": 32},
                "usage_moves": ["Earthquake"],
            },
            "partner_count": 99,
        }
    ]


def test_spread_recoil_sums_even_when_primary_alone_wins(monkeypatch):
    """Partner weak → primary wins max(); recoil still sums both targets."""
    import recommender.role_compendium as rc

    monkeypatch.setattr(
        rc,
        "_CONNECT_RECOIL_MOVES",
        rc._CONNECT_RECOIL_MOVES | frozenset({"earthquake"}),
    )
    seen_defs: list[str] = []

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for req in reqs:
            atk = req.get("attacker") or {}
            defn = req.get("defender") or {}
            if not atk.get("boosts"):
                out.append(_hit(dmg=40, hp=100, atk_spe=150, def_spe=50))
                continue
            seen_defs.append(str(defn.get("species") or ""))
            sp = str(defn.get("species") or "")
            # Primary strong, partner weak → primary_alone wins continuous max.
            dmg = 80 if sp == "Primary" else 20
            out.append(
                _hit(
                    dmg=dmg,
                    hp=100,
                    atk_spe=50,
                    def_spe=150,
                    recoil_pct=10.0,
                )
            )
        return out

    snap = load_snapshot()
    score, err, _used, sweep = _setup_kit_matrix_score(
        snap=snap,
        sid="rhyperior",
        calc_name="Rhyperior",
        item=None,
        ability=None,
        boost_stat="atk",
        stages=2,
        panel=_pair_panel(),
        calculate_batch=calc,
        mids=["earthquake"],
        kit_moves=["swordsdance", "earthquake"],
    )
    assert err == ""
    assert seen_defs.count("Primary") == 1
    assert seen_defs.count("Partner") == 1
    row = sweep["per_defender"][0]
    # Continuous uses primary alone (0.80), not mean 0.50.
    assert abs(row["weighted"] - 0.80) < 1e-9
    assert abs(score - 0.80) < 1e-9
    # remain = 1 - 0.40 - (0.10+0.10) = 0.40 even though primary won max()
    assert sweep["n_surv"] == 1
    assert abs(sweep["remain_mean"] - 0.40) < 1e-9


def test_spread_primary_alone_wins_continuous():
    """Bulky partner → continuous score floors at primary-alone, not mean."""

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for req in reqs:
            atk = req.get("attacker") or {}
            defn = req.get("defender") or {}
            if not atk.get("boosts"):
                out.append(_hit(dmg=10, hp=100, atk_spe=50, def_spe=200))
                continue
            sp = str(defn.get("species") or "")
            dmg = 80 if sp == "Primary" else 20
            out.append(_hit(dmg=dmg, hp=100, atk_spe=200, def_spe=50))
        return out

    snap = load_snapshot()
    score, err, _used, sweep = _setup_kit_matrix_score(
        snap=snap,
        sid="garchomp",
        calc_name="Garchomp",
        item=None,
        ability=None,
        boost_stat="atk",
        stages=2,
        panel=_pair_panel(),
        calculate_batch=calc,
        mids=["earthquake"],
        kit_moves=["swordsdance", "earthquake"],
    )
    assert err == ""
    row = sweep["per_defender"][0]
    assert abs(row["weighted"] - 0.80) < 1e-9
    assert abs(row["raw_frac"] - 0.80) < 1e-9
    assert abs(score - 0.80) < 1e-9
    # Old mean-of-two would have been 0.50.
    assert score > 0.50


def test_spread_pair_mean_wins_continuous():
    """Frail partner → pair_mean beats primary_alone (genuine upside)."""

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for req in reqs:
            atk = req.get("attacker") or {}
            defn = req.get("defender") or {}
            if not atk.get("boosts"):
                out.append(_hit(dmg=10, hp=100, atk_spe=50, def_spe=200))
                continue
            sp = str(defn.get("species") or "")
            dmg = 40 if sp == "Primary" else 100
            out.append(_hit(dmg=dmg, hp=100, atk_spe=200, def_spe=50))
        return out

    snap = load_snapshot()
    score, err, _used, sweep = _setup_kit_matrix_score(
        snap=snap,
        sid="garchomp",
        calc_name="Garchomp",
        item=None,
        ability=None,
        boost_stat="atk",
        stages=2,
        panel=_pair_panel(),
        calculate_batch=calc,
        mids=["earthquake"],
        kit_moves=["swordsdance", "earthquake"],
    )
    assert err == ""
    row = sweep["per_defender"][0]
    assert abs(row["weighted"] - 0.70) < 1e-9  # mean of 0.40 and 1.0
    assert abs(row["raw_frac"] - 0.70) < 1e-9
    assert abs(score - 0.70) < 1e-9
    assert score > 0.40  # upside vs primary alone


def test_spread_ohko_bin_is_primary_alone():
    """sweep_ohko / bin follow primary only — partner KO neither required nor sufficient."""
    panel = _pair_panel()

    def calc_primary_ohko(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for req in reqs:
            atk = req.get("attacker") or {}
            defn = req.get("defender") or {}
            if not atk.get("boosts"):
                out.append(_hit(dmg=10, hp=100, atk_spe=50, def_spe=200))
                continue
            sp = str(defn.get("species") or "")
            dmg = 100 if sp == "Primary" else 40
            out.append(_hit(dmg=dmg, hp=100, atk_spe=200, def_spe=50))
        return out

    def calc_partner_only_ohko(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for req in reqs:
            atk = req.get("attacker") or {}
            defn = req.get("defender") or {}
            if not atk.get("boosts"):
                out.append(_hit(dmg=10, hp=100, atk_spe=50, def_spe=200))
                continue
            sp = str(defn.get("species") or "")
            dmg = 40 if sp == "Primary" else 100
            out.append(_hit(dmg=dmg, hp=100, atk_spe=200, def_spe=50))
        return out

    snap = load_snapshot()
    common = dict(
        snap=snap,
        sid="tyranitar",
        calc_name="Tyranitar",
        item=None,
        ability=None,
        boost_stat="atk",
        stages=2,
        panel=panel,
        mids=["rockslide"],
        kit_moves=["dragondance", "rockslide"],
    )
    _s1, e1, _u1, sw1 = _setup_kit_matrix_score(
        **common, calculate_batch=calc_primary_ohko
    )
    _s2, e2, _u2, sw2 = _setup_kit_matrix_score(
        **common, calculate_batch=calc_partner_only_ohko
    )
    assert e1 == e2 == ""
    assert sw1["ohko"] == 1
    assert sw1["per_defender"][0]["bin"] == "ohko"
    assert sw2["ohko"] == 0
    assert sw2["per_defender"][0]["bin"] != "ohko"


def test_combined_ko_finisher_primary_first():
    """Finisher on primary yields OHKO credit; partner need not be finished."""
    finisher_targets: list[str] = []

    def calc(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for req in reqs:
            atk = req.get("attacker") or {}
            defn = req.get("defender") or {}
            mid = to_id(req.get("move") or "")
            if not atk.get("boosts"):
                # Incoming 50% — lived_shield when outsped
                out.append(_hit(dmg=50, hp=100, atk_spe=150, def_spe=50))
                continue
            if mid == "shadowsneak":
                finisher_targets.append(str(defn.get("species") or ""))
                out.append(_hit(dmg=40, hp=100, atk_spe=200, def_spe=50))
                continue
            # Rock Slide: 70% each — needs finisher for OHKO; outsped
            out.append(_hit(dmg=70, hp=100, atk_spe=50, def_spe=150))
        return out

    snap = load_snapshot()
    _score, err, _used, sweep = _setup_kit_matrix_score(
        snap=snap,
        sid="aegislash",
        calc_name="Aegislash-Blade",
        item=None,
        ability="Stance Change",
        boost_stat="atk",
        stages=2,
        panel=_pair_panel(),
        calculate_batch=calc,
        mids=["rockslide"],
        kit_moves=["swordsdance", "rockslide", "shadowsneak", "kingsshield"],
    )
    assert err == ""
    assert "Primary" in finisher_targets
    assert sweep["per_defender"][0]["combined"] is True
    # Bin is primary-alone — combined on primary counts as ohko.
    assert sweep["ohko"] == 1


def test_payoff_targets_pair_label_format():
    used = [
        ("Garchomp+Charizard-Mega-Y", "rockslide"),
        ("Incineroar+Sinistcha", "earthquake"),
        ("Garchomp+Charizard-Mega-Y", "earthquake"),
    ]
    moves, targets = _setup_payoff_notes(
        used, {"rockslide": 1, "earthquake": 2}
    )
    assert moves == ["earthquake", "rockslide"]
    assert targets["rockslide"] == ["Garchomp+Charizard-Mega-Y"]
    assert targets["earthquake"] == [
        "Incineroar+Sinistcha",
        "Garchomp+Charizard-Mega-Y",
    ]
    assert _pair_entry_label(
        {
            "species": "Garchomp",
            "partner": {"species": "Charizard-Mega-Y"},
        }
    ) == "Garchomp+Charizard-Mega-Y"
