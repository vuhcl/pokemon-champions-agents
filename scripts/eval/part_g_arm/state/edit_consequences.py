"""Deterministic edit consequences from pinned data (no LLM).

Used by edit_slot_field. Sources: TYPE_BOOST_ITEMS, reconcile Choice exceptions,
stat_boosts.v1.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from recommender.ids import to_id
from recommender.item_conditions import TYPE_BOOST_ITEMS
from recommender.legality import load_snapshot
from recommender.reconcile import _CHOICE_ITEMS, _ITEM_SWAP_MOVES
from recommender.state import Slot

_REPO = Path(__file__).resolve().parents[4]
_STAT_BOOSTS = _REPO / "data" / "moves" / "stat_boosts.v1.json"
_FLAGS = _REPO / "data" / "moves" / "flags.v1.json"


def _move_meta(snap: dict[str, Any], move: str) -> dict[str, Any]:
    return (snap.get("moves") or {}).get(to_id(move)) or {}


def _flags_entry(move: str) -> dict[str, Any]:
    doc = json.loads(_FLAGS.read_text(encoding="utf-8"))
    moves = doc.get("moves") or doc
    return moves.get(to_id(move)) or {}


def _stat_boost_entry(move: str) -> dict[str, Any] | None:
    doc = json.loads(_STAT_BOOSTS.read_text(encoding="utf-8"))
    moves = doc.get("moves") or {}
    return moves.get(to_id(move))


def _damaging_type_remaining(snap: dict[str, Any], moves: list[str], attack_type: str) -> list[str]:
    want = attack_type.title()
    out: list[str] = []
    for m in moves:
        meta = _move_meta(snap, m)
        if (meta.get("category") or "") == "Status":
            continue
        if (meta.get("type") or "") == want:
            out.append(str(meta.get("name") or m))
    return out


def _status_moves_except_swap(snap: dict[str, Any], moves: list[str]) -> list[str]:
    out: list[str] = []
    for m in moves:
        mid = to_id(m)
        if mid in _ITEM_SWAP_MOVES:
            continue
        meta = _move_meta(snap, m)
        cat = meta.get("category") or _flags_entry(m).get("category")
        if cat == "Status":
            out.append(str(meta.get("name") or m))
    return out


def _self_boost_stats(move: str) -> dict[str, int]:
    entry = _stat_boost_entry(move)
    if not entry:
        return {}
    # category Status self-boosters only
    if (entry.get("category") or "") != "Status":
        return {}
    stats: dict[str, int] = {}
    for boost in entry.get("boosts") or []:
        if boost.get("to") != "self":
            continue
        for stat, stages in (boost.get("stats") or {}).items():
            stats[stat] = stats.get(stat, 0) + int(stages)
    return stats


def consequences_after_edit(
    slot: Slot,
    *,
    changed_field: str,
    snap: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Facts only. Empty when nothing to report."""
    snap = snap or load_snapshot()
    facts: list[dict[str, Any]] = []
    item = slot.item.value if slot.item.locked else None
    moves = list(slot.moveset.value or []) if slot.moveset.locked else []

    if item and moves and (changed_field in {"item", "moveset", "moves"}):
        iid = to_id(item)
        if iid in TYPE_BOOST_ITEMS:
            t = TYPE_BOOST_ITEMS[iid]
            remaining = _damaging_type_remaining(snap, moves, t)
            if not remaining:
                facts.append({
                    "kind": "type_boost_inactive",
                    "item": item,
                    "type": t,
                    "detail": f"{item} no longer boosts: no remaining damaging {t} move on the set",
                    "remaining_damaging_moves_of_type": remaining,
                })
            else:
                facts.append({
                    "kind": "type_boost_active",
                    "item": item,
                    "type": t,
                    "remaining_damaging_moves_of_type": remaining,
                })
        if iid in _CHOICE_ITEMS:
            blocked = _status_moves_except_swap(snap, moves)
            facts.append({
                "kind": "choice_lock_status",
                "item": item,
                "unusable_status_moves": blocked,
                "exceptions": sorted(_ITEM_SWAP_MOVES),
                "detail": (
                    f"{item} locks into one move; status moves on the set become unusable "
                    f"(except Trick/Switcheroo): {blocked}"
                    if blocked
                    else f"{item} Choice-lock; no non-excepted status moves on the set"
                ),
            })

    if changed_field in {"moveset", "moves"} and len(moves) >= 2:
        # Status self-boosters sharing a raised stat
        boosts = [(m, _self_boost_stats(m)) for m in moves]
        boosts = [(m, s) for m, s in boosts if s]
        for i, (m1, s1) in enumerate(boosts):
            for m2, s2 in boosts[i + 1 :]:
                shared = sorted(set(s1) & set(s2))
                if shared:
                    facts.append({
                        "kind": "status_self_boost_overlap",
                        "moves": [m1, m2],
                        "shared_stats": shared,
                        "boosts": {m1: s1, m2: s2},
                        "detail": (
                            f"{m1} and {m2} are Status self-boosters sharing {shared}"
                        ),
                    })
    return facts
