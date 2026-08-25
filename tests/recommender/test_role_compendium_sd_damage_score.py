"""Swords Dance setup-attacker tests — _damage_score and calc scoring paths."""

from __future__ import annotations

from typing import Any

from recommender.ids import to_id

from role_compendium_sd_common import (_panel_result,)
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

    assert 50* (1 + ASSUMED_HITS_TAKEN) > 70
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

    snap= load_snapshot()
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

    snap= {
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

    used= [
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

def test_damage_score_sweep_ohko_and_survive_remain():
    """Outgoing OHKO k/n + outsped-survive remain from the same batches."""
    from recommender.role_compendium_setup import _damage_score
    from recommender.role_compendium import _sweep_note_fields
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
    from recommender.role_compendium_setup import _damage_score
    from recommender.role_compendium import _sweep_note_fields
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
    from recommender.role_compendium_setup import _candidate_defender_spec, _setup_bulk_ok
    from recommender.role_compendium import _base_stats
    from recommender.legality import load_snapshot

    snap = load_snapshot()
    assert _setup_bulk_ok(_base_stats(snap, "aegislash"))
    assert not _setup_bulk_ok(_base_stats(snap, "aegislashblade"))
    spec = _candidate_defender_spec("Aegislash", "Aegislash-Blade")
    assert spec["species"] == "Aegislash-Shield"

def test_connect_recoil_move_set_locked():
    from recommender.role_compendium import _CONNECT_RECOIL_MOVES

    assert _CONNECT_RECOIL_MOVES== frozenset(
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

    assert _DRAIN_MOVES== frozenset(
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

    r50= _panel_result(dmg=60, hp=100, recovery_hp=50, atk_hp=100)
    r75 = _panel_result(dmg=60, hp=100, recovery_hp=75, atk_hp=100)
    assert abs(_drain_frac_from_result(r50, "bitterblade") - 0.50) < 1e-9
    assert abs(_drain_frac_from_result(r75, "drainingkiss") - 0.75) < 1e-9

def test_drain_frac_gated_ignores_shell_bell_on_non_drain():
    from recommender.role_compendium import _drain_frac_from_result  # Shell Bell heal on non-drain moves
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

    assert"fakeout" not in _SETUP_PRIORITY_FINISHER_MOVES
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

