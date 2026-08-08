"""Nasty Plot Attacker Role Compendium (setup_attacker)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from recommender.ids import to_id
from recommender.legality import load_snapshot
from recommender.role_compendium import (
    NASTY_PLOT_ATTACKER_CRITERIA,
    construct_role_category,
    critique_role_ranking,
    exclusive_self_boost_move,
    legal_species_pool,
    rebuild_role_category,
)


def _mock_calc(requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for req in requests:
        sp = to_id((req.get("attacker") or {}).get("species") or "")
        frac = (
            1.0
            if sp
            in {
                "gholdengo",
                "delphox",
                "delphoxmega",
            }
            else 0.25
        )
        dmg = int(200 * frac)
        out.append(
            {
                "damageRange": [dmg - 10, dmg],
                "koChance": "ohko" if frac >= 1.0 else "3hko",
                "raw": {"stats": {"defender": {"hp": 200}, "attacker": {"spa": 200}}},
            }
        )
    return out


def _np_draft():
    snap = load_snapshot()
    proven = {"gholdengo", "delphox", "froslass", "lucariomega", "meowstic"}

    def _usage(name: str) -> dict[str, Any] | None:
        sid = to_id(name)
        if sid not in proven:
            return None
        return {
            "name": name,
            "id": sid,
            "common_moves": [{"name": "Nasty Plot", "pct": 35.0}],
            "common_items": [{"name": "Life Orb", "pct": 20.0}],
        }

    return construct_role_category(
        "nasty_plot_attacker",
        NASTY_PLOT_ATTACKER_CRITERIA,
        legal_species_pool(snap),
        snap=snap,
        live_fetch=_usage,
        showdown_fetch=lambda _n: None,
        calculate_batch=_mock_calc,
    )


def _members(draft, tier: str) -> set[str]:
    return {c.species for c in draft.candidates if c.tier == tier}


def test_exclusive_self_boost_spa():
    assert exclusive_self_boost_move(boost_stat="spa") == "nastyplot"


def test_np_uses_second_highest_floor():
    draft = _np_draft()
    assert any("2nd-highest adjusted" in n for n in draft.notes)
    assert any("× 0.95" in n or "0.95" in n for n in draft.notes)
    assert _members(draft, "Excellent") or _members(draft, "Good")


def test_critique_approves():
    draft = _np_draft()
    result = critique_role_ranking(draft)
    assert result.approved, result.flags


def test_rebuild_tmp(tmp_path: Path):
    r = rebuild_role_category(
        "nasty_plot_attacker",
        NASTY_PLOT_ATTACKER_CRITERIA,
        roles_dir=tmp_path,
        live_fetch=lambda n: {
            "name": n,
            "id": to_id(n),
            "common_moves": [{"name": "Nasty Plot", "pct": 40}],
        }
        if to_id(n) in {"gholdengo", "delphox"}
        else None,
        showdown_fetch=lambda _n: None,
        calculate_batch=_mock_calc,
    )
    assert r.status == "approved", r.critique.flags
    assert Path(r.path or "").exists()
