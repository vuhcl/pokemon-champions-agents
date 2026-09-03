"""Sanity gates for CBD ingame_doubles snapshot vs live CBD and Showdown."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from recommender.ids import to_id
from recommender.usage_cbd import fetch_ingame_doubles_species


def top_move_ids(row: dict[str, Any], *, n: int = 4) -> list[str]:
    moves = row.get("common_moves") or []
    return [to_id(m["name"]) for m in moves[:n] if m.get("name")]


def stale_vs_live_suspect(
    cached_row: dict[str, Any],
    live_row: dict[str, Any],
    *,
    top_n: int = 4,
) -> bool:
    """Cached ingame top-N has zero overlap with live CBD top-N (identity corruption)."""
    if cached_row.get("ladder_rank_only"):
        return False
    cached_moves = cached_row.get("common_moves") or []
    live_moves = live_row.get("common_moves") or []
    if len(cached_moves) < 3 or len(live_moves) < 3:
        return False
    live_top = live_moves[0]
    if (live_top.get("pct") or 0) < 20:
        return False
    cached_top = top_move_ids(cached_row, n=top_n)
    live_top_ids = top_move_ids(live_row, n=top_n)
    if len(cached_top) < 3 or len(live_top_ids) < 3:
        return False
    return not (set(cached_top) & set(live_top_ids))


def ingame_monotonic_tail_corrupt(
    ingame_row: dict[str, Any],
    showdown_row: dict[str, Any],
    *,
    top_n: int = 4,
) -> bool:
    """Tail-slice corruption: ingame top-N is disjoint from Showdown top-4 but monotonic deep."""
    if ingame_row.get("ladder_rank_only"):
        return False
    sd_moves = showdown_row.get("common_moves") or []
    ing_moves = ingame_row.get("common_moves") or []
    if len(sd_moves) < 3 or len(ing_moves) < 3:
        return False
    if (sd_moves[0].get("pct") or 0) < 20:
        return False

    sd_top4 = {to_id(m["name"]) for m in sd_moves[:4] if m.get("name")}
    ing_top = top_move_ids(ingame_row, n=top_n)
    if len(ing_top) < 3:
        return False
    if set(ing_top) & sd_top4:
        return False

    sd_ids = [to_id(m["name"]) for m in sd_moves if m.get("name")]
    if not all(mid in sd_ids for mid in ing_top):
        return False

    ing_all = {to_id(m["name"]) for m in ing_moves if m.get("name")}
    if sd_top4 & ing_all:
        return False

    ranks = [sd_ids.index(mid) for mid in ing_top]
    if ranks != sorted(ranks):
        return False
    return min(ranks) >= 4


def find_stale_vs_live_suspects(
    ingame: dict[str, dict],
    *,
    fetch: Callable[[str], dict[str, Any] | None] = fetch_ingame_doubles_species,
) -> list[tuple[str, str]]:
    suspects: list[tuple[str, str]] = []
    for sid, row in sorted(ingame.items()):
        if row.get("ladder_rank_only"):
            continue
        name = row.get("name") or sid
        live = fetch(name)
        if not live:
            continue
        if stale_vs_live_suspect(row, live):
            cached_top = top_move_ids(row)
            live_top = top_move_ids(live)
            suspects.append(
                (sid, f"cached={cached_top} live={live_top}")
            )
    return suspects
