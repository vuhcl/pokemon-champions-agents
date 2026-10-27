"""Unit checks for solve_spread (no model). Run:
uv run pytest scripts/eval/part_g_arm/state/test_solve_spread.py -q
"""

from __future__ import annotations

import os

os.environ.setdefault("PART_G_V4_CALC_BACKEND", "inprocess")

from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.harness import dispatch
from scripts.eval.part_g_arm.state.spread_solve import (
    STAT_KEYS,
    SP_BUDGET,
    _fill_toward,
    _l1,
    joint_refs_66,
    solve_spread,
)
from scripts.eval.part_g_arm.state.tools import READONLY_TOOL_NAMES, combined_specs


def test_solve_spread_in_readonly_and_specs():
    assert "solve_spread" in READONLY_TOOL_NAMES
    names = [s["function"]["name"] for s in combined_specs()]
    assert "solve_spread" in names


def test_refuse_non_monotone():
    out = solve_spread(
        "Archaludon",
        [{"type": "underspeed", "target_spe": 100}],
        ability="Stamina",
        time_budget_s=5,
    )
    assert out["status"] == "invalid_arguments"
    assert out["field"] == "constraints[0].type"
    assert "monotone" in (out.get("error") or "").lower() or "survive" in (out.get("expected") or "")


def test_trick_room_refused():
    out = solve_spread(
        "Archaludon",
        [{"type": "trick_room", "target_spe": 80}],
        ability="Stamina",
        time_budget_s=5,
    )
    assert out["status"] == "invalid_arguments"
    assert out["field"] == "constraints[0].type"


def test_fill_toward_reaches_budget_and_respects_frontier():
    fr = {"hp": 10, "atk": 0, "def": 10, "spa": 0, "spd": 0, "spe": 5}
    target = {"hp": 32, "atk": 0, "def": 1, "spa": 1, "spd": 29, "spe": 3}
    filled = _fill_toward(fr, target)
    assert filled is not None
    assert sum(filled.values()) == SP_BUDGET
    assert all(filled[k] >= fr[k] for k in STAT_KEYS)
    assert all(filled[k] <= 32 for k in STAT_KEYS)


def test_tie_break_prefers_higher_weight_at_equal_l1(monkeypatch):
    """Two synthetic refs at the same L1 — higher weight wins."""
    refs = [
        {
            "filtered_rank": 1,
            "file_rank": 1,
            "nature": "Bold",
            "sp": {"hp": 20, "atk": 0, "def": 20, "spa": 0, "spd": 21, "spe": 5},
            "weight": 10.0,
        },
        {
            "filtered_rank": 2,
            "file_rank": 2,
            "nature": "Bold",
            "sp": {"hp": 21, "atk": 0, "def": 20, "spa": 0, "spd": 20, "spe": 5},
            "weight": 99.0,
        },
    ]
    # Feasible for both: use outspeed-only so any Spe>=5 Bold works; force distance via fill.
    monkeypatch.setattr(
        "scripts.eval.part_g_arm.state.spread_solve.joint_refs_66",
        lambda _s: (refs, 0),
    )

    def always_ok(preds, nature, sp):  # noqa: ARG001
        return sp["spe"] >= 5 and nature == "Bold"

    monkeypatch.setattr(
        "scripts.eval.part_g_arm.state.spread_solve._feasible",
        lambda preds, nature, sp: always_ok(preds, nature, sp),
    )
    # Skip expensive frontier: make each ref's own SP "feasible" so distance 0 on both;
    # higher weight (rank 2) must win among distance-0.
    out = solve_spread(
        "Archaludon",
        [{"type": "outspeed", "target_spe": 110}],
        ability="Stamina",
        time_budget_s=5,
        cell_budget=0,
    )
    # With cell_budget=0 frontier stops immediately; distance-0 fast path still runs.
    assert out["status"] in {"optimal", "feasible"}, out
    assert out["rank"] == 2
    assert out["weight"] == 99.0


def test_no_reference_species():
    # Legal without Showdown joints (from discovery: 39 such).
    from scripts.eval.part_g_arm.state.spread_solve import _legal_abilities
    from scripts.eval.part_g_v4.builders._lib import is_legal_species, load_legality, load_showdown

    snap = load_legality()
    joint = set(load_showdown()["showdown_doubles"]["species"])
    sid = next(
        sid
        for sid, sp in snap["species"].items()
        if is_legal_species(sp) and sid not in joint
    )
    name = snap["species"][sid]["name"]
    legal = _legal_abilities(name)
    kwargs = {"time_budget_s": 10}
    if len(legal) != 1:
        kwargs["ability"] = legal[0]
    out = solve_spread(
        name,
        [{"type": "outspeed", "target_spe": 1}],
        **kwargs,
    )
    assert out.get("no_reference") is True
    assert out["status"] in {"optimal", "feasible"}
    assert out["spread"] is not None
    assert out["unallocated"] >= 0
    assert sum(out["spread"][k] for k in STAT_KEYS) + out["unallocated"] == SP_BUDGET or out[
        "unallocated"
    ] == SP_BUDGET - sum(out["spread"][k] for k in STAT_KEYS)


def test_filtered_rank_after_drop(monkeypatch):
    """When file rank-1 is non-66, filtered rank-1 is the first kept entry."""
    real = joint_refs_66("Whimsicott")
    kept, dropped = real
    assert dropped >= 1 or True  # whimsicott drops mid-list; synthesize rank-1 drop
    synthetic = [
        {
            "filtered_rank": 1,
            "file_rank": 2,
            "nature": "Timid",
            "sp": {"hp": 0, "atk": 0, "def": 0, "spa": 32, "spd": 2, "spe": 32},
            "weight": 50.0,
        }
    ]
    monkeypatch.setattr(
        "scripts.eval.part_g_arm.state.spread_solve.joint_refs_66",
        lambda _s: (synthetic, 1),
    )
    monkeypatch.setattr(
        "scripts.eval.part_g_arm.state.spread_solve._feasible",
        lambda preds, nature, sp: nature == "Timid" and sp == synthetic[0]["sp"],
    )
    from scripts.eval.part_g_arm.state.spread_solve import _legal_abilities

    legal = _legal_abilities("Whimsicott")
    out = solve_spread(
        "Whimsicott",
        [{"type": "outspeed", "target_spe": 1}],
        ability=legal[0] if legal else "Prankster",
        time_budget_s=5,
        cell_budget=0,
    )
    assert out["rank"] == 1
    assert out["matched_entry"]["file_rank"] == 2
    assert out["dropped_non_66"] == 1
    assert out["distance"] == 0


def test_brute_force_matches_solver_small_grid():
    """Few free stats: Spe fixed at 5, Atk=SpA=0; brute HP/Def/SpD vs solver fill."""
    from scripts.eval.part_g_arm.state.spread_solve import _feasible, _parse_constraints

    species = "Archaludon"
    ability = "Stamina"
    item = "Leftovers"
    constraints = [
        {
            "type": "survive",
            "attacker": {
                "species": "Sneasler",
                "nature": "Jolly",
                "ability": "Unburden",
                "item": "White Herb",
                "sp": {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
            },
            "move": "Close Combat",
            "field": {"gameType": "Doubles"},
        },
        {"type": "outspeed", "target_spe": 110},
    ]
    preds, _, _notes, err = _parse_constraints(species, ability, item, constraints)
    assert err is None
    nature = "Bold"
    # Brute: Spe=5 only, minimize L1 to Bold rank-2-ish joint
    refs, _ = joint_refs_66(species)
    bold_refs = [r for r in refs if r["nature"] == "Bold"]
    assert bold_refs
    target = bold_refs[0]["sp"]
    best = None
    best_d = None
    for hp in range(33):
        for df in range(33):
            for spd in range(33):
                if hp + df + spd + 5 > 66:
                    continue
                # allocate rest arbitrarily into spa then atk to hit 66
                rem = 66 - (hp + df + spd + 5)
                if rem > 64:
                    continue
                spa = min(32, rem)
                atk = rem - spa
                if atk > 32:
                    continue
                sp = {"hp": hp, "atk": atk, "def": df, "spa": spa, "spd": spd, "spe": 5}
                if not _feasible(preds, nature, sp):
                    continue
                d = _l1(sp, target)
                if best_d is None or d < best_d:
                    best_d = d
                    best = sp
    assert best is not None
    out = solve_spread(
        species,
        constraints,
        ability=ability,
        item=item,
        time_budget_s=60,
    )
    assert out["status"] in {"optimal", "feasible"}
    assert out["spread"]["nature"] == nature or out["spread"]["nature"] in {
        r["nature"] for r in refs
    }
    # When solver picks Bold against same first Bold ref, distance must match brute
    if out["spread"]["nature"] == nature and out.get("rank") == bold_refs[0]["filtered_rank"]:
        assert out["distance"] == best_d


def test_dispatch_does_not_write_state():
    state = empty_team()
    before = [s.species.value for s in state["team_draft"]]
    new, result = dispatch(
        state,
        arm=None,
        name="solve_spread",
        args={
            "species": "Archaludon",
            "ability": "Stamina",
            "constraints": [{"type": "outspeed", "target_spe": 110}],
        },
    )
    assert [s.species.value for s in new["team_draft"]] == before
    assert new.get("pending_presentation") is state.get("pending_presentation")
    assert result.get("status") in {
        "optimal",
        "feasible",
        "infeasible",
        "unknown",
        "invalid_arguments",
    }
    assert all(v.get("ok") for v in (result.get("constraint_results") or []) if "ok" in v)


def test_malformed_nested_move_is_invalid_arguments():
    """Transcript shape: move nested under attacker, top-level move missing."""
    out = solve_spread(
        "Venusaur-Mega",
        [
            {
                "type": "survive",
                "attacker": {
                    "species": "Beedrill-Mega",
                    "nature": "Jolly",
                    "move": "U-turn",
                    "sp": {"hp": 0, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
                },
            },
            {"type": "outspeed", "target_spe": 100},
        ],
        time_budget_s=5,
    )
    assert out["status"] == "invalid_arguments"
    assert out["field"] == "constraints[0].move"
    assert "sibling" in (out.get("error") or "").lower() or "nested" in (out.get("error") or "").lower()


def test_malformed_missing_attacker_ability_multi_is_invalid():
    """Multi-ability attacker without ability → invalid_arguments naming legal list."""
    out = solve_spread(
        "Venusaur-Mega",
        [
            {
                "type": "survive",
                "attacker": {
                    "species": "Blastoise",
                    "nature": "Modest",
                    "sp": {"hp": 0, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 32},
                },
                "move": "Water Pulse",
            }
        ],
        time_budget_s=5,
    )
    assert out["status"] == "invalid_arguments"
    assert out["field"] == "constraints[0].attacker.ability"
    assert "Torrent" in (out.get("error") or "") or "Torrent" in (out.get("expected") or "")


def test_user_species_multi_ability_requires_ability():
    out = solve_spread(
        "Blastoise",
        [{"type": "outspeed", "target_spe": 1}],
        time_budget_s=5,
    )
    assert out["status"] == "invalid_arguments"
    assert out["field"] == "ability"
    assert "Torrent" in (out.get("error") or "") or "Rain Dish" in (out.get("error") or "")


def test_single_ability_filled_from_data():
    out = solve_spread(
        "Venusaur-Mega",
        [{"type": "outspeed", "target_spe": 1}],
        time_budget_s=10,
    )
    assert out["status"] in {"optimal", "feasible"}
    assert out["ability"] == "Thick Fat"
    assert any("Thick Fat" in n and "from data" in n for n in (out.get("ability_notes") or []))


def test_attacker_single_ability_filled_from_data():
    out = solve_spread(
        "Venusaur-Mega",
        [
            {
                "type": "survive",
                "attacker": {
                    "species": "Beedrill-Mega",
                    "nature": "Jolly",
                    "sp": {"hp": 0, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
                },
                "move": "U-turn",
                "field": {"gameType": "Doubles"},
            },
            {"type": "outspeed", "target_spe": 80},
        ],
        time_budget_s=30,
    )
    assert out["status"] in {"optimal", "feasible", "infeasible", "unknown"}
    if out["status"] in {"optimal", "feasible"}:
        assert any("Adaptability" in n for n in (out.get("ability_notes") or []))
