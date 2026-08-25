"""Swords Dance setup-attacker tests — payoff selection / turn order / usage bag."""

from __future__ import annotations

from typing import Any

from recommender.ids import to_id
from recommender.legality import load_snapshot
from role_compendium_sd_common import (_panel_result,)
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
    from recommender.role_compendium_setup import _best_payoff_move
    from recommender.role_compendium import _setup_payoff_candidates
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
    from recommender.role_compendium_setup import _best_payoff_move
    from recommender.role_compendium import _setup_payoff_candidates
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

def _empty_usage_maps():
    return {
        "ingame_doubles": {"species": {}},
        "showdown_vgc_mb": {"species": {}},
        "species": {},
    }

def test_present_usage_payoff_ids_drops_sub_floor_leftovers(monkeypatch):
    """Problem A: ~0% common_moves leftovers leave the bag; real alts stay."""
    from recommender.role_compendium_setup import _present_usage_payoff_ids, _select_setup_payoff, _usage_payoff_move_ids
    from recommender.role_compendium import _SETUP_PRESENCE_SET_PCT_FLOOR, _UsageCtx

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
    from recommender.role_compendium_setup import _present_usage_payoff_ids, _select_setup_payoff
    from recommender.role_compendium import _UsageCtx

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

