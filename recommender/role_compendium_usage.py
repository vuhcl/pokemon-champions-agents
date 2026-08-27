"""Mega/showdown usage attribution and delivery helpers (Role Compendium)."""

from __future__ import annotations

from typing import Any

from recommender.ids import to_id
from recommender.reconcile import _item_mega_forme
from recommender.usage_data import ingame_species_map, showdown_species_map
from recommender.role_compendium import (
    LiveFetch,
    _MEGA_STONE_FALLBACK_PCT,
    _SHOWDOWN_BASE_USAGE_RATIO,
    _USAGE_SET_PCT_FLOOR,
    _UsageCtx,
    _entry_has_item,
    _entry_has_move,
)

def _best_move_set_pct(
    name: str,
    move_id: str,
    *,
    uctx: _UsageCtx,
    sd_cache: dict[str, dict[str, Any] | None],
    showdown_fetch: LiveFetch | None,
) -> float:
    """Max of CBD pct and Showdown set% for one move. Does not live-fetch."""
    sid = to_id(name)
    ch = ingame_species_map().get(sid)
    if not isinstance(ch, dict):
        ch = uctx.cache.get(sid)  # already-fetched live CBD only
    sd = _showdown_entry(name, cache=sd_cache, showdown_fetch=showdown_fetch)
    return max(_move_pct(ch if isinstance(ch, dict) else None, move_id), _move_pct(sd, move_id))


def _hits_clear_set_pct_floor(
    name: str,
    mids: set[str] | frozenset[str],
    *,
    floor: float,
    uctx: _UsageCtx,
    sd_cache: dict[str, dict[str, Any] | None],
    showdown_fetch: LiveFetch | None,
    require_all: bool = False,
) -> bool:
    """True when delivery rate clears the chaos set% floor.

    require_all: ID+BP — both moves must individually clear. Else max of hits.
    """
    if not mids:
        return False
    pcts = [
        _best_move_set_pct(
            name, mid, uctx=uctx, sd_cache=sd_cache, showdown_fetch=showdown_fetch
        )
        for mid in mids
    ]
    if require_all:
        return bool(pcts) and all(p >= floor for p in pcts)
    return max(pcts, default=0.0) >= floor


def _move_pct(entry: dict[str, Any] | None, move_id: str) -> float:
    if not entry:
        return 0.0
    mid = to_id(move_id)
    for m in entry.get("common_moves") or []:
        if to_id(m.get("name") or "") == mid:
            try:
                return float(m.get("pct") or 0.0)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _cbd_base_move_implausible_vs_mega(
    base_cbd: dict[str, Any] | None,
    mega_sd: dict[str, Any] | None,
    move_id: str,
) -> bool:
    """True when CBD base move% exceeds Mega's Showdown move% for the same move.

    CBD often collapses Mega into the base page, so a base move rate higher than the
    Mega's own form-separated rate is Scovillain/Skarmory-shaped contamination — not
    trustworthy standalone base usage. Requires Mega to actually run the move.
    """
    if not base_cbd or not mega_sd:
        return False
    if not _entry_has_move(mega_sd, move_id):
        return False
    return _move_pct(base_cbd, move_id) > _move_pct(mega_sd, move_id)


def _showdown_entry(
    species: str,
    *,
    cache: dict[str, dict[str, Any] | None],
    showdown_fetch: LiveFetch | None,
) -> dict[str, Any] | None:
    sid = to_id(species)
    if sid in cache:
        return cache[sid]
    offline = showdown_species_map().get(sid)
    if isinstance(offline, dict):
        cache[sid] = offline
        return offline
    if showdown_fetch is None:
        cache[sid] = None
        return None
    cache[sid] = showdown_fetch(species)
    return cache[sid]


def _mega_pair_ids(sid: str, snap: dict[str, Any], pool_ids: set[str]) -> tuple[str, str] | None:
    """Return (base_id, mega_id) if both are in the redirect pool."""
    entry = snap.get("species", {}).get(sid) or {}
    base = str(entry.get("base_species_id") or "")
    if base and sid == f"{base}mega" and base in pool_ids and sid in pool_ids:
        return base, sid
    mega = f"{sid}mega"
    if not base and mega in pool_ids and sid in pool_ids:
        return sid, mega
    return None


def _mega_stone_on_entry(
    entry: dict[str, Any] | None,
    base_sid: str,
    mega_sid: str,
    snap: dict[str, Any],
) -> bool:
    """True when entry's common items include this mega's stone at ≥80%."""
    if not entry:
        return False
    for item in entry.get("common_items") or []:
        iid = to_id(item.get("name") or "")
        try:
            pct = float(item.get("pct") or 0.0)
        except (TypeError, ValueError):
            pct = 0.0
        if pct < _MEGA_STONE_FALLBACK_PCT:
            continue
        if _item_mega_forme(iid, base_sid, snap) == mega_sid:
            return True
    return False


def _stone_fallback_usage(
    base_name: str,
    base_sid: str,
    mega_sid: str,
    move_ids: frozenset[str],
    *,
    uctx: _UsageCtx,
    snap: dict[str, Any],
) -> bool:
    """Attribute redirect usage to Mega when base CBD page shows mega-stone ≥80%."""
    entry = uctx.entry_for(base_name)
    if not entry or not any(_entry_has_move(entry, mid) for mid in move_ids):
        return False
    return _mega_stone_on_entry(entry, base_sid, mega_sid, snap)


def _stone_fallback_ability(
    base_name: str,
    base_sid: str,
    mega_sid: str,
    *,
    uctx: _UsageCtx,
    snap: dict[str, Any],
) -> bool:
    """Attribute weather-ability usage to Mega when base CBD shows mega-stone ≥80%."""
    return _mega_stone_on_entry(
        uctx.entry_for(base_name), base_sid, mega_sid, snap
    )


def _mega_usage_attribution(
    eligible: dict[str, str],
    move_ids: frozenset[str],
    *,
    snap: dict[str, Any],
    uctx: _UsageCtx,
    sd_cache: dict[str, dict[str, Any] | None],
    showdown_fetch: LiveFetch | None,
    notes: list[str],
) -> tuple[dict[str, bool], dict[str, str], bool]:
    """Split base/Mega usage for move-delivered roles.

    Returns (usage_proven overrides by species id, attribution notes, whether
    the mega-stone fallback fired).

    The discount treats a base form's usage as an artifact of pre-evolution
    turns, so it requires the Mega to actually run the move: otherwise the two
    forms are being used for unrelated strategies and the ratio would just
    dilute a real base-form strategy against an irrelevant denominator.
    """
    pair_usage: dict[str, bool] = {}
    pair_notes: dict[str, str] = {}
    seen_pairs: set[tuple[str, str]] = set()
    stone_fallback_used = False
    for sid in eligible:
        pair = _mega_pair_ids(sid, snap, set(eligible))
        if not pair or pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        base_sid, mega_sid = pair
        base_name, mega_name = eligible[base_sid], eligible[mega_sid]
        base_sd = _showdown_entry(base_name, cache=sd_cache, showdown_fetch=showdown_fetch)
        mega_sd = _showdown_entry(mega_name, cache=sd_cache, showdown_fetch=showdown_fetch)

        if mega_sd is not None:
            mega_pct = float(mega_sd.get("usage_pct") or 0.0)
            base_pct = float((base_sd or {}).get("usage_pct") or 0.0) if base_sd else 0.0
            mega_delivers = any(_entry_has_move(mega_sd, mid) for mid in move_ids)
            base_delivers = bool(base_sd) and any(
                _entry_has_move(base_sd, mid) for mid in move_ids
            )
            pair_usage[mega_sid] = mega_delivers
            if (
                base_delivers
                and mega_delivers
                and mega_pct > base_pct
                and base_pct < _SHOWDOWN_BASE_USAGE_RATIO * mega_pct
            ):
                pair_usage[base_sid] = False
                pair_notes[base_sid] = (
                    f"showdown usage discounted "
                    f"(base {base_pct:.3f}% < {_SHOWDOWN_BASE_USAGE_RATIO}× mega {mega_pct:.3f}%)"
                )
            elif base_sd is not None:
                pair_usage[base_sid] = base_delivers
                if base_delivers and not mega_delivers:
                    pair_notes[base_sid] = (
                        "independent base usage kept "
                        f"(Mega shows no {'/'.join(sorted(move_ids))} usage)"
                    )
            else:
                pair_usage[base_sid] = False
            pair_notes[mega_sid] = "showdown form-separated usage"
            notes.append(
                f"Showdown attribution ({base_name}/{mega_name}): "
                f"mega usage_pct={mega_pct:.3f} base={base_pct:.3f}; "
                f"stone-heuristic fallback unused"
            )
        elif _stone_fallback_usage(
            base_name, base_sid, mega_sid, move_ids, uctx=uctx, snap=snap
        ):
            stone_fallback_used = True
            pair_usage[mega_sid] = True
            pair_usage[base_sid] = False
            pair_notes[base_sid] = "usage attributed to Mega via mega-stone fallback"
            pair_notes[mega_sid] = "mega-stone fallback (≥80% on base CBD page)"
            notes.append(
                f"Showdown miss for {mega_name}; stone-heuristic fallback used "
                f"for {base_name}/{mega_name}"
            )
    return pair_usage, pair_notes, stone_fallback_used

def _move_display(snap: dict[str, Any] | None, mid: str) -> str:
    if snap:
        name = (snap.get("moves") or {}).get(to_id(mid), {}).get("name")
        if name:
            return str(name)
    return mid


def _species_types(snap: dict[str, Any], sid: str) -> set[str]:
    entry = snap.get("species", {}).get(sid) or {}
    return {str(t).lower() for t in (entry.get("types") or [])}

def _delivery_usage_hits(
    name: str,
    move_ids: frozenset[str] | set[str],
    *,
    uctx: _UsageCtx,
    sd_cache: dict[str, dict[str, Any] | None],
    showdown_fetch: LiveFetch | None,
    set_pct_floor: float = _USAGE_SET_PCT_FLOOR,
) -> tuple[set[str], str]:
    """Moves on CBD and/or Showdown at or above set_pct_floor. CBD does not suppress SD."""
    mids = {to_id(m) for m in move_ids}
    champ = uctx.champions_entry(name)
    sd = _showdown_entry(name, cache=sd_cache, showdown_fetch=showdown_fetch)
    cbd_hits = {mid for mid in mids if _entry_has_move(champ, mid)}
    sd_hits = {mid for mid in mids if _entry_has_move(sd, mid)}
    hits = cbd_hits | sd_hits
    if not hits:
        return hits, "none"
    extra_sd = sd_hits - cbd_hits
    if not extra_sd:
        source = "champions"
    elif champ is None:
        source = "showdown (no Champions row)"
    elif not cbd_hits:
        source = "showdown"
    else:
        source = "champions+showdown"
    cleared = {
        mid
        for mid in hits
        if max(_move_pct(champ, mid), _move_pct(sd, mid)) >= set_pct_floor
    }
    if not cleared:
        return set(), f"{source}_below_floor"
    return cleared, source


def _usage_has_item(
    name: str,
    item_id: str,
    *,
    uctx: _UsageCtx,
    sd_cache: dict[str, dict[str, Any] | None],
    showdown_fetch: LiveFetch | None,
) -> bool:
    if _entry_has_item(uctx.champions_entry(name), item_id):
        return True
    sd = _showdown_entry(name, cache=sd_cache, showdown_fetch=showdown_fetch)
    return _entry_has_item(sd, item_id)


def _same_row_both_moves(
    name: str,
    move_a: str,
    move_b: str,
    *,
    uctx: _UsageCtx,
    sd_cache: dict[str, dict[str, Any] | None],
    showdown_fetch: LiveFetch | None,
) -> bool:
    """Both moves on CBD, else both on Showdown. Never split across sources."""
    ch = uctx.champions_entry(name)
    if _entry_has_move(ch, move_a) and _entry_has_move(ch, move_b):
        return True
    sd = _showdown_entry(name, cache=sd_cache, showdown_fetch=showdown_fetch)
    return bool(sd) and _entry_has_move(sd, move_a) and _entry_has_move(sd, move_b)
