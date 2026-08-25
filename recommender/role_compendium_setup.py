"""Setup-attacker Role Compendium construction + calc scoring (ADR-015)."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from recommender.counters import _move_base_accuracy, _scaled_base_power, effective_move_type
from recommender.ids import to_id
from recommender.legality import load_snapshot, resolve_learnset
from recommender.matchup import _makes_contact, effective_accuracy
from recommender.reconcile import _item_mega_forme
from recommender.usage_data import (
    featured_or_common_set,
    ingame_species_map,
    set_from_ingame,
    set_from_showdown,
    showdown_species_map,
)
from recommender.role_compendium import (
    CalculateBatch,
    CandidateEval,
    ClaimedTrait,
    LiveFetch,
    RejectedCandidate,
    RoleConstructionDraft,
    SetupPriorityKind,
    ROLE_TIER_ORDER,
    _ALLY_HIT_DAMAGE_MOVE_IDS,
    _ALLY_HIT_TYPE_PROTECTIONS,
    _BODY_PRESS_EVS,
    _CALC_POKE_KEYS,
    _CONNECT_RECOIL_MOVES,
    _DD_SETUP_PRESENCE_FLOOR,
    _DEF_PAYOFF_DELTA_EPS,
    _DRAIN_MOVES,
    _OFFENSIVE_PRIORITY_MOVES,
    _PIKALYTICS_PAIRS_PATH,
    _SETUP_ACCEPTABLE_FLOOR_MULT,
    _SETUP_BANNED_PAYOFF,
    _SETUP_BITE_MOVES,
    _SETUP_BOTH_BRANCH_SCORE_DIV,
    _SETUP_BRANCH_A_PRIORITY,
    _SETUP_BULK_FLOOR,
    _SETUP_CHOICE_ITEMS,
    _SETUP_CONDITIONAL_PRIORITY,
    _SETUP_DAMAGE_FRAC_CAP,
    _SETUP_EXCELLENT_SECONDARY_ABILITIES,
    _SETUP_EXCELLENT_SECONDARY_MOVES,
    _SETUP_FLOOR_SECOND_MULT,
    _SETUP_LOCKIN_MOVES,
    _SETUP_NARROW_CONDITIONAL_PRIORITY,
    _SETUP_PRESENCE_SET_PCT_FLOOR,
    _SETUP_PRIORITY_FINISHER_MOVES,
    _SETUP_PULSE_MOVES,
    _SETUP_PUNCH_MOVES,
    _SETUP_SLICE_MOVES,
    _SETUP_SPE_FLOOR,
    _SETUP_SPEED_ABILITIES,
    _SETUP_SUSTAIN_DRAIN,
    _SETUP_SUSTAIN_HEALS,
    _SETUP_SUSTAIN_ITEMS,
    _SETUP_SURVIVE_ABILITIES,
    _SETUP_THREAT_ENCOUNTER_GAMES,
    _SETUP_THREAT_USAGE_PCT_FLOOR,
    _SOUND_ALLY_HIT_MOVE_IDS,
    _SPREAD_DAMAGE_MOVE_IDS,
    _USAGE_SET_PCT_FLOOR,
    _UsageCtx,
    _admit_move_delivery,
    _base_stats,
    _best_move_set_pct,
    _cbd_base_move_implausible_vs_mega,
    _discount_outcome,
    _draft_with_tiers,
    _drain_frac_from_result,
    _entry_has_item,
    _entry_has_move,
    _excellent_secondary,
    _hits_clear_set_pct_floor,
    _mega_pair_ids,
    _mega_stone_on_entry,
    _mega_usage_attribution,
    _move_display,
    _move_pct,
    _offline_usage_row,
    _pool_index,
    _recoil_frac_from_result,
    _ref_members,
    _secondary_support_notes,
    _self_boosts,
    _self_defense_drops,
    _serialize_criteria,
    _showdown_entry,
    _species_abilities,
    _species_id_is_mega,
    _species_types,
    _stone_fallback_usage,
    exact_self_boost_move,
    exclusive_self_boost_move,
    load_stat_boosts,
)


def _rc(name: str):
    """Resolve setup helper via role_compendium façade (test monkeypatch target)."""
    import recommender.role_compendium as rc

    return getattr(rc, name)


def _setup_priority_for_branch(
    learnset: set[str],
    snap: dict[str, Any],
    boost_stat: str,
) -> set[str]:
    """Priority moves that can open Branch A for this boost_stat (category-matched)."""
    want = "Physical" if boost_stat == "atk" else "Special"
    moves = snap.get("moves") or {}
    out: set[str] = set()
    for mid in learnset & _SETUP_BRANCH_A_PRIORITY:
        if (moves.get(mid) or {}).get("category") == want:
            out.add(mid)
    return out


def _setup_branch_a(
    *,
    learnset: set[str],
    abs_map: dict[str, str],
    stats: dict[str, int],
    snap: dict[str, Any],
    boost_stat: str,
) -> bool:
    if _setup_priority_for_branch(learnset, snap, boost_stat):
        return True
    if set(abs_map) & _SETUP_SPEED_ABILITIES:
        return True
    return int(stats.get("spe") or 0) >= _SETUP_SPE_FLOOR


def _setup_speed_path_a(
    *,
    abs_map: dict[str, str],
    stats: dict[str, int],
) -> bool:
    if set(abs_map) & _SETUP_SPEED_ABILITIES:
        return True
    return int(stats.get("spe") or 0) >= _SETUP_SPE_FLOOR


def _setup_branch_a_via_priority(
    *,
    learnset: set[str],
    abs_map: dict[str, str],
    stats: dict[str, int],
    snap: dict[str, Any],
    boost_stat: str,
) -> bool:
    """True when Branch A clears only via priority (not Spe / Speed Boost)."""
    if not _setup_priority_for_branch(learnset, snap, boost_stat):
        return False
    return not _setup_speed_path_a(abs_map=abs_map, stats=stats)


def _setup_priority_kind(move_id: str) -> SetupPriorityKind:
    mid = to_id(move_id)
    if mid in _SETUP_CONDITIONAL_PRIORITY | _SETUP_NARROW_CONDITIONAL_PRIORITY:
        return "conditional"
    if mid in _OFFENSIVE_PRIORITY_MOVES:
        return "unconditional"
    return "none"


def _setup_turn_order_weight(
    move_id: str,
    atk_spe: int,
    def_spe: int,
    ability: str | None,
    *,
    incoming_ohko: bool | None = None,
    spe_stages: int = 0,
) -> float:
    """Credit weight for a panel-member damage frac under turn order.

    Missing Spe → fail open (1.0). Priority payoff acts first. Disguise/Ice Face
    absorbs the first hit when outsped. spe_stages is already total (DD + Speed
    Boost); applied to unboosted Spe returned by @smogon/calc.
    Outsped: zero only if incoming_ohko is True. incoming_ohko is None → legacy
    zero (no snap / no mask). False → acts second, full credit.
    """
    if atk_spe <= 0 or def_spe <= 0:
        return 1.0
    mid = to_id(move_id)
    if mid in _OFFENSIVE_PRIORITY_MOVES:
        return 1.0
    aid = to_id(ability) if ability else ""
    if aid in _SETUP_SURVIVE_ABILITIES:
        return 1.0
    effective = int(atk_spe * (2 + spe_stages) / 2) if spe_stages else atk_spe
    if effective > def_spe:
        return 1.0
    if effective == def_spe:
        return 0.5
    if incoming_ohko is None:
        return 0.0
    return 0.0 if incoming_ohko else 1.0


def _setup_adjusted_score(raw: float, *, both_branches: bool) -> float:
    if both_branches:
        return raw / _SETUP_BOTH_BRANCH_SCORE_DIV
    return raw


def _setup_excellent_floor(adjusted_scores: list[float]) -> float:
    """Per-category floor: 2nd-highest adjusted × 0.95 (sole member → that × 0.95)."""
    if not adjusted_scores:
        return 0.0
    ranked = sorted(adjusted_scores, reverse=True)
    anchor = ranked[1] if len(ranked) >= 2 else ranked[0]
    return anchor * _SETUP_FLOOR_SECOND_MULT


def _setup_mech_tier(
    adjusted: float,
    floor: float,
    *,
    acceptable_mult: float = _SETUP_ACCEPTABLE_FLOOR_MULT,
) -> str:
    """Excellent ≥ floor; Acceptable below floor × mult; Good between."""
    if floor <= 0:
        return "Good"
    if adjusted >= floor:
        return "Excellent"
    if adjusted < floor * acceptable_mult:
        return "Acceptable"
    return "Good"


def _partition_by_admission_floor(
    provisional: list[dict[str, Any]],
    *,
    score_key: str,
    admission_floor: float | None,
    prior: dict[str, str],
    rejected: list[RejectedCandidate],
) -> list[dict[str, Any]]:
    """Drop rows below damage_admission_floor into rejected; return kept.

    No-op when admission_floor is None (NP/DD/ID+BP). Boundary is inclusive (>=).
    """
    if admission_floor is None:
        return provisional
    kept: list[dict[str, Any]] = []
    for p in provisional:
        score = float(p[score_key])
        # Floors are locked to 3 decimals; compare at that precision so boundary
        # species (Decidueye / Mr. Rime / Lycanroc) stay inclusive under float noise.
        if round(score, 3) >= round(float(admission_floor), 3):
            kept.append(p)
            continue
        sid = str(p["sid"])
        name = str(p["name"])
        rejected.append(
            RejectedCandidate(
                species=name,
                species_id=sid,
                reason=(
                    f"damage_score {score:.3f} below admission floor "
                    f"{admission_floor:g}"
                ),
                change_reason=(
                    f"setup admission floor re-eval / tier {prior.get(sid)!r} → rejected "
                    f"(score={score:.3f} < {admission_floor:g})"
                    if prior.get(sid)
                    else None
                ),
            )
        )
    return kept


@lru_cache(maxsize=None)
def _setup_self_drop_moves(boost_stat: str) -> frozenset[str]:
    """Damaging moves that always lower the user's own boost_stat — cashing out a
    setup with one of these immediately undoes the setup it is cashing out."""
    return frozenset(
        mid
        for mid, ent in (load_stat_boosts().get("moves") or {}).items()
        if ent.get("category") != "Status" and _self_boosts(ent).get(boost_stat, 0) < 0
    )


def _setup_banned_payoffs(boost_stat: str) -> frozenset[str]:
    return _SETUP_BANNED_PAYOFF | _setup_self_drop_moves(boost_stat)


def _usage_payoff_move_ids(
    entry: dict[str, Any] | None,
    kit_moves: list[str],
) -> set[str]:
    """Move ids with real usage / featured evidence (not bare learnset)."""
    ids: set[str] = {to_id(m) for m in kit_moves if m}
    for m in (entry or {}).get("common_moves") or []:
        mid = to_id(m.get("name") or "")
        if mid:
            ids.add(mid)
    for fs in (entry or {}).get("featured_sets") or []:
        for m in fs.get("moves") or []:
            mid = to_id(m)
            if mid:
                ids.add(mid)
    return ids


def _present_usage_payoff_ids(
    name: str,
    entry: dict[str, Any] | None,
    kit_moves: list[str],
    *,
    uctx: _UsageCtx,
    sd_cache: dict[str, dict[str, Any] | None],
    showdown_fetch: LiveFetch | None,
    floor: float = _SETUP_PRESENCE_SET_PCT_FLOOR,
) -> set[str]:
    """Usage-bag payoffs that clear the presence floor (drops ~0% leftovers)."""
    return {
        mid
        for mid in _usage_payoff_move_ids(entry, kit_moves)
        if _best_move_set_pct(
            name, mid, uctx=uctx, sd_cache=sd_cache, showdown_fetch=showdown_fetch
        )
        >= floor
    }


def _setup_payoff_candidates(
    snap: dict[str, Any],
    *,
    boost_stat: str,
    usage_move_ids: set[str],
) -> list[str]:
    """Usage-proven damaging payoffs: category match, not banned delayed/recharge/drop."""
    want_cat = "Physical" if boost_stat == "atk" else "Special"
    moves_map = snap.get("moves") or {}
    banned = _setup_banned_payoffs(boost_stat)
    out: list[str] = []
    for mid in sorted(usage_move_ids):
        if mid in banned or mid in {"protect", "substitute", "swordsdance", "nastyplot"}:
            continue
        ment = moves_map.get(mid) or {}
        if ment.get("category") != want_cat:
            continue
        try:
            bp = int(ment.get("basePower") or 0)
        except (TypeError, ValueError):
            bp = 0
        if bp <= 0:
            continue
        out.append(mid)
    return out


def _setup_ability_for_payoff(
    ability: str | None,
    move_id: str,
    *,
    snap: dict[str, Any],
    types: set[str],
) -> str | None:
    """Keep move-conditional abilities only when they can modify the scored payoff."""
    if not ability:
        return None
    aid = to_id(ability)
    mid = to_id(move_id)
    ment = (snap.get("moves") or {}).get(mid) or {}
    try:
        bp = int(ment.get("basePower") or 0)
    except (TypeError, ValueError):
        bp = 0
    mtype = str(ment.get("type") or "").lower()
    if aid == "technician":
        return ability if bp <= 60 else None
    if aid == "toughclaws":
        return ability if _makes_contact(mid) else None
    if aid == "adaptability":
        return ability if mtype in types else None
    if aid in {"fairyaura", "darkaura"}:
        et = effective_move_type(snap, mid, ability=ability)
        want = "fairy" if aid == "fairyaura" else "dark"
        return ability if et and et.lower() == want else None
    if aid == "aurabreak":
        et = effective_move_type(snap, mid, ability=ability)
        return ability if et and et.lower() in {"fairy", "dark"} else None
    if aid == "ironfist":
        return ability if mid in _SETUP_PUNCH_MOVES else None
    if aid == "strongjaw":
        return ability if mid in _SETUP_BITE_MOVES else None
    if aid == "sharpness":
        return ability if mid in _SETUP_SLICE_MOVES else None
    if aid == "megalauncher":
        return ability if mid in _SETUP_PULSE_MOVES else None
    return ability


def _setup_bulk_ok(stats: dict[str, int]) -> bool:
    hp = int(stats.get("hp") or 0)
    defense = int(stats.get("def") or 0)
    spd = int(stats.get("spd") or 0)
    return hp * 2 + defense + spd >= _SETUP_BULK_FLOOR


def _setup_sustain_ok(
    *,
    learnset: set[str],
    entry: dict[str, Any] | None,
) -> bool:
    if learnset & _SETUP_SUSTAIN_HEALS:
        return True
    usage_moves = {
        to_id(m.get("name") or "") for m in (entry or {}).get("common_moves") or []
    }
    if usage_moves & (_SETUP_SUSTAIN_HEALS | _SETUP_SUSTAIN_DRAIN):
        return True
    items = {
        to_id(i.get("name") or "") for i in (entry or {}).get("common_items") or []
    }
    return bool(items & _SETUP_SUSTAIN_ITEMS)


def _setup_branches(
    *,
    learnset: set[str],
    abs_map: dict[str, str],
    stats: dict[str, int],
    entry: dict[str, Any] | None,
    snap: dict[str, Any],
    boost_stat: str,
) -> list[str]:
    cleared: list[str] = []
    if _setup_branch_a(
        learnset=learnset,
        abs_map=abs_map,
        stats=stats,
        snap=snap,
        boost_stat=boost_stat,
    ):
        cleared.append("A")
    if (set(abs_map) & _SETUP_SURVIVE_ABILITIES) or (
        _setup_bulk_ok(stats) and _setup_sustain_ok(learnset=learnset, entry=entry)
    ):
        cleared.append("B")
    return cleared


def _common_move_names(entry: dict[str, Any] | None) -> list[str]:
    out: list[str] = []
    for m in (entry or {}).get("common_moves") or []:
        n = str(m.get("name") or "")
        if n:
            out.append(n)
    return out


def _setup_panel_build(
    name: str,
    sid: str,
    *,
    snap: dict[str, Any],
    regulation: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str]:
    """CBD-first panel build; Showdown only for mega/base gap or missing CBD.

    Mega ≥80% stone on the base CBD page (same `_mega_stone_on_entry` as usage
    attribution) → CBD item/moves, legality mega ability. Base whose CBD top
    item is a mega stone → Showdown. Returns (built, usage-move source row, tag).
    """
    ingame_map = ingame_species_map(regulation)
    sd_map = showdown_species_map(regulation)
    cbd_self = set_from_ingame(name, regulation=regulation) or set_from_ingame(
        sid, regulation=regulation
    )
    sd_built = set_from_showdown(name, regulation=regulation)
    entry = (snap.get("species") or {}).get(sid) or {}
    base_sid = str(entry.get("base_species_id") or sid)
    if _species_id_is_mega(sid):
        if _mega_stone_on_entry(ingame_map.get(base_sid), base_sid, sid, snap):
            built = set_from_ingame(base_sid, regulation=regulation)
            if built:
                out = dict(built)
                out["species"] = name
                abs_map = _species_abilities(snap, sid)
                if abs_map:
                    out["ability"] = next(iter(abs_map.values()))
                return out, ingame_map.get(base_sid), "cbd_stone"
        return sd_built, sd_map.get(sid), "showdown"
    if cbd_self:
        stone = _item_mega_forme(to_id(cbd_self.get("item") or ""), sid, snap)
        if stone:
            return sd_built, sd_map.get(sid), "showdown"
        return cbd_self, ingame_map.get(sid) or ingame_map.get(to_id(name)), "cbd"
    return sd_built, sd_map.get(sid), "showdown"


def _setup_threat_defenders(
    *,
    regulation: str = "champions",
) -> list[dict[str, Any]]:
    """Showdown formes with usage_pct ≥ 15-game 50% encounter floor.

    Selection is Showdown usage_pct. Builds are CBD-first; Showdown only when
    CBD is missing or cannot distinguish mega vs base (stone heuristic).
    Each primary gets one top-1 Pikalytics co-occurrence partner among panel
    members (item 7 Part A — pair-as-defender).
    """
    snap = load_snapshot()
    sd = showdown_species_map(regulation)
    ranked: list[tuple[float, str, str]] = []
    for sid, entry in sd.items():
        if not isinstance(entry, dict):
            continue
        try:
            pct = float(entry.get("usage_pct") or 0.0)
        except (TypeError, ValueError):
            continue
        if pct < _SETUP_THREAT_USAGE_PCT_FLOOR:
            continue
        ranked.append((pct, str(entry.get("name") or sid), sid))
    ranked.sort(key=lambda r: (-r[0], r[1]))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _pct, name, sid in ranked:
        if sid in seen:
            continue
        seen.add(sid)
        built, usage_row, source = _setup_panel_build(
            name, sid, snap=snap, regulation=regulation
        )
        defender: dict[str, Any] = {
            "species": name,
            "evs": (built or {}).get("evs")
            or {"hp": 32, "atk": 0, "def": 32, "spa": 0, "spd": 32, "spe": 0},
            "build_source": source,
        }
        if built:
            for key in ("item", "ability", "nature", "moves"):
                if built.get(key):
                    defender[key] = built[key]
        usage_moves = _common_move_names(usage_row)
        if usage_moves:
            defender["usage_moves"] = usage_moves
        out.append(defender)
    return _attach_top1_partners(out)


@lru_cache(maxsize=1)
def _pikalytics_panel_pair_counts() -> dict[tuple[str, str], int]:
    """Unordered panel-pair counts from Pikalytics tournament team-usage.

    Keys are sorted `(pair_lookup_id_a, pair_lookup_id_b)`. Confirms
    `meta.population == tournament` — raises if the file is the wrong population.
    """
    raw = json.loads(_PIKALYTICS_PAIRS_PATH.read_text())
    meta = raw.get("meta") or {}
    if meta.get("population") != "tournament":
        raise ValueError(
            f"expected Pikalytics tournament pairs, got population={meta.get('population')!r}"
        )
    out: dict[tuple[str, str], int] = {}
    for row in raw.get("pairs") or []:
        a, b = str(row.get("a") or ""), str(row.get("b") or "")
        if not a or not b or a == b:
            continue
        try:
            count = int(row.get("count") or 0)
        except (TypeError, ValueError):
            continue
        key = (a, b) if a < b else (b, a)
        out[key] = count
    return out


def _attach_top1_partners(panel: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach each primary's highest-count panel partner (directed top-1)."""
    # Lazy: team_candidates ↔ role_compendium would cycle at import time.
    from recommender.team_candidates import pair_lookup_species_id

    if len(panel) < 2:
        return panel
    by_sid = {to_id(str(d.get("species") or "")): d for d in panel}
    panel_ids = set(by_sid)
    counts = _pikalytics_panel_pair_counts()
    out: list[dict[str, Any]] = []
    for primary in panel:
        psid = to_id(str(primary.get("species") or ""))
        lookup = pair_lookup_species_id(psid)
        best: tuple[int, str] | None = None
        for other_sid in panel_ids:
            if other_sid == psid:
                continue
            other_lookup = pair_lookup_species_id(other_sid)
            key = (
                (lookup, other_lookup)
                if lookup < other_lookup
                else (other_lookup, lookup)
            )
            c = counts.get(key, 0)
            if c <= 0:
                continue
            if best is None or c > best[0] or (c == best[0] and other_sid < best[1]):
                best = (c, other_sid)
        row = dict(primary)
        if best is not None:
            partner = by_sid[best[1]]
            row["partner"] = {
                k: partner[k]
                for k in (*_CALC_POKE_KEYS, "usage_moves", "build_source")
                if k in partner
            }
            row["partner_count"] = best[0]
        out.append(row)
    return out


def _pair_entry_label(defn: dict[str, Any]) -> str:
    primary = str(defn.get("species") or "")
    partner = defn.get("partner") or {}
    pname = str(partner.get("species") or "")
    if primary and pname:
        return f"{primary}+{pname}"
    return primary


def _is_spread_damage_mid(mid: str) -> bool:
    return to_id(mid) in _SPREAD_DAMAGE_MOVE_IDS


def _threat_panel_label(panel: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for d in panel:
        primary = f"{d.get('species')}/{d.get('item') or 'no-item'}"
        partner = d.get("partner") or {}
        if partner.get("species"):
            parts.append(
                f"{primary}+{partner.get('species')}/{partner.get('item') or 'no-item'}"
            )
        else:
            parts.append(primary)
    return ", ".join(parts)


def _calc_pokemon_spec(
    raw: dict[str, Any], *, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Strip panel-only keys (usage_moves) before sending to calc."""
    out: dict[str, Any] = {}
    for k in _CALC_POKE_KEYS:
        val = raw.get(k)
        if val in (None, "", []):
            continue
        out[k] = val
    if extra:
        out.update(extra)
    return out




def _payoff_sort_bp(mid: str, snapshot_bp: int, *, boost_count: int = 0) -> int:
    """BP the damage calc actually uses — sort key must match, not snapshot."""
    if mid in {"storedpower", "powertrip"}:
        return 20 + 20 * max(0, boost_count)
    return _scaled_base_power(mid, snapshot_bp)


def _ranked_payoff_moves(
    snap: dict[str, Any],
    sid: str,
    learnset: set[str],
    *,
    boost_stat: str,
    usage_moves: list[str] | None = None,
    usage_only: bool = False,
    boost_count: int = 0,
    ability: str | None = None,
) -> list[str]:
    """Damaging payoffs matching Physical(atk)/Special(spa), STAB then BP.

    STAB uses effective_move_type (Liquid Voice, -ate, etc.). usage_moves
    first so they win STAB+BP ties. When usage_only, only those moves.
    Skips banned delayed/recharge/self-drop payoffs.
    Sort BP is the same corrected value damage calc uses (Rage Fist / Last
    Respects hits-taken, Stored Power / Power Trip boost count).
    """
    want_cat = "Physical" if boost_stat == "atk" else "Special"
    types = _species_types(snap, sid)
    moves_map = snap.get("moves") or {}
    banned = _setup_banned_payoffs(boost_stat)
    if usage_only:
        candidates = list(usage_moves or [])
    else:
        candidates = list(usage_moves or []) + sorted(learnset)
    hits: list[tuple[int, int, int, str]] = []  # stab, bp, -order, mid
    seen: set[str] = set()
    for order, raw in enumerate(candidates):
        mid = to_id(raw)
        if mid in seen or mid in {"protect", "substitute", "swordsdance", "nastyplot"}:
            continue
        seen.add(mid)
        if mid in banned:
            continue
        ment = moves_map.get(mid) or {}
        if ment.get("category") != want_cat:
            continue
        try:
            bp = int(ment.get("basePower") or 0)
        except (TypeError, ValueError):
            bp = 0
        if bp <= 0:
            continue
        bp = _payoff_sort_bp(mid, bp, boost_count=boost_count)
        et = effective_move_type(snap, mid, ability=ability, species=sid)
        mtype = (et or str(ment.get("type") or "")).lower()
        stab = 1 if mtype in types else 0
        hits.append((stab, bp, -order, mid))
    hits.sort(key=lambda h: (h[0], h[1], h[2]), reverse=True)
    return [h[3] for h in hits]


def _best_payoff_move(
    snap: dict[str, Any],
    sid: str,
    learnset: set[str],
    *,
    boost_stat: str,
    usage_moves: list[str] | None = None,
    usage_only: bool = False,
    ability: str | None = None,
) -> str | None:
    """Best damaging move matching Physical(atk)/Special(spa), prefer STAB then BP.

    When usage_only, only consider usage_moves (must be non-empty). Always skips
    banned delayed/recharge/self-drop payoffs.
    """
    ranked = _ranked_payoff_moves(
        snap,
        sid,
        learnset,
        boost_stat=boost_stat,
        usage_moves=usage_moves,
        usage_only=usage_only,
        boost_count=0,
        ability=ability,
    )
    return ranked[0] if ranked else None


_KO_BIN_RANK = {"ohko": 2, "2hko": 1, "3plus": 0}


def _kit_damaging_mids(
    snap: dict[str, Any],
    kit_moves: list[str] | None,
    *,
    boost_stat: str,
) -> list[str]:
    """Category-matched damaging moves from the kit (banned payoffs excluded)."""
    ids = {to_id(m) for m in (kit_moves or []) if m}
    return _setup_payoff_candidates(snap, boost_stat=boost_stat, usage_move_ids=ids)


def _setup_kit_matrix_score(
    *,
    snap: dict[str, Any],
    sid: str,
    calc_name: str,
    item: str | None,
    ability: str | None,
    boost_stat: str,
    stages: int,
    panel: list[dict[str, Any]],
    calculate_batch: CalculateBatch,
    mids: list[str],
    kit_moves: list[str],
    boosts: dict[str, int] | None = None,
    extra_spe_stages: int = 0,
) -> tuple[float, str, list[tuple[str, str]], dict[str, Any]]:
    """Per-defender best kit mid: KO-bin then weighted frac. Shared ohko once.

    Returns (mean_score, err, used[(dname, mid)], sweep_out).
    Zero-damage cells stay in the mean (raw_frac=0). No usage/learnset fallback.
    """
    if not mids or not panel:
        return 0.0, "empty_panel_or_move", [], {}
    boosts = dict(boosts) if boosts is not None else {boost_stat: stages}
    base_evs = {"hp": 4, "atk": 32, "def": 0, "spa": 32, "spd": 0, "spe": 32}
    types = _species_types(snap, sid)
    aid = to_id(ability) if ability else ""
    spe_stages = extra_spe_stages + (1 if aid in _SETUP_SPEED_ABILITIES else 0)
    disguise = aid in _SETUP_SURVIVE_ABILITIES
    kit_ids = {to_id(m) for m in kit_moves if m}

    ohko_mask = _incoming_ohko_by_defender(
        snap=snap,
        candidate_name=calc_name,
        calc_name=calc_name,
        panel=panel,
        boosts=boosts,
        calculate_batch=calculate_batch,
    )
    finisher_fracs: dict[str, float] = {}
    fin_mid: str | None = None
    finishers = kit_ids & _SETUP_PRIORITY_FINISHER_MOVES
    if finishers:
        # ponytail: ≤1 eligible finisher per kit today; sorted[0] if multi.
        fin_mid = sorted(finishers)[0]
        fin_disp = _move_display(snap, fin_mid)
        calc_ab = _setup_ability_for_payoff(
            ability, fin_mid, snap=snap, types=types
        )
        fin_atk: dict[str, Any] = {
            "species": calc_name,
            "evs": dict(base_evs),
            "boosts": dict(boosts),
            "moves": [fin_disp],
        }
        if item:
            fin_atk["item"] = item
        if calc_ab:
            fin_atk["ability"] = calc_ab
        fin_targets: list[dict[str, Any]] = []
        for defn in panel:
            fin_targets.append(defn)
            partner = defn.get("partner")
            if isinstance(partner, dict) and partner.get("species"):
                fin_targets.append(partner)
        fin_reqs = [
            {
                "attacker": fin_atk,
                "defender": _calc_pokemon_spec(defn),
                "move": fin_disp,
                "field": {"gameType": "Doubles"},
                **_move_override_extra(fin_mid),
            }
            for defn in fin_targets
        ]
        try:
            fin_results = calculate_batch(fin_reqs)
        except Exception:  # noqa: BLE001 — sequence credit fails open
            fin_results = []
        if len(fin_results) == len(fin_targets):
            for defn, r in zip(fin_targets, fin_results, strict=True):
                frac = _hit_frac_from_result(r)
                if frac is not None:
                    finisher_fracs[str(defn.get("species") or "")] = frac

    blade_mask: dict[str, float] = {}
    if to_id(calc_name) in _AEGISLASH_FORMES and "kingsshield" in kit_ids:
        blade_mask = _incoming_ohko_by_defender(
            snap=snap,
            candidate_name=calc_name,
            calc_name=calc_name,
            panel=panel,
            boosts=boosts,
            calculate_batch=calculate_batch,
            defender_species="Aegislash-Blade",
        )

    def _parse_hit(
        defn: dict[str, Any], r: Any, *, label: str
    ) -> tuple[str, float, int, int, Any]:
        dname = str(defn.get("species") or label)
        if not isinstance(r, dict):
            errors.append(f"{dname}:non_dict")
            return ("skip", 0.0, 0, 0, None)
        if "error" in r:
            errors.append(f"{dname}:{r.get('error')}")
            return ("skip", 0.0, 0, 0, None)
        dmg = (r.get("damageRange") or [0, 0])[-1]
        stats = (r.get("raw") or {}).get("stats") or {}
        def_stats = stats.get("defender") or {}
        atk_stats = stats.get("attacker") or {}
        try:
            hp_f = float(def_stats.get("hp") or 0)
            dmg_f = float(dmg)
            atk_spe = int(atk_stats.get("spe") or 0)
            def_spe = int(def_stats.get("spe") or 0)
        except (TypeError, ValueError):
            errors.append(f"{dname}:bad_range")
            return ("skip", 0.0, 0, 0, None)
        if hp_f <= 0:
            errors.append(f"{dname}:no_hp")
            return ("skip", 0.0, 0, 0, None)
        raw_frac = dmg_f / hp_f if dmg_f > 0 else 0.0
        return ("ok", raw_frac, atk_spe, def_spe, r)

    # mid → list aligned with panel (primary); optional partner row when spread
    by_mid: dict[str, list[tuple[str, float, int, int, Any]]] = {}
    by_mid_partner: dict[str, list[tuple[str, float, int, int, Any] | None]] = {}
    errors: list[str] = []
    for mid in mids:
        disp = _move_display(snap, mid)
        calc_ab = _setup_ability_for_payoff(ability, mid, snap=snap, types=types)
        attacker: dict[str, Any] = {
            "species": calc_name,
            "evs": dict(base_evs),
            "boosts": dict(boosts),
            "moves": [disp],
        }
        if item:
            attacker["item"] = item
        if calc_ab:
            attacker["ability"] = calc_ab
        extra = _move_override_extra(mid)
        spread = _is_spread_damage_mid(mid)
        reqs = [
            {
                "attacker": attacker,
                "defender": _calc_pokemon_spec(defn),
                "move": disp,
                "field": {"gameType": "Doubles"},
                **extra,
            }
            for defn in panel
        ]
        partner_idxs: list[int] = []
        if spread:
            for i, defn in enumerate(panel):
                partner = defn.get("partner")
                if isinstance(partner, dict) and partner.get("species"):
                    partner_idxs.append(i)
                    reqs.append(
                        {
                            "attacker": attacker,
                            "defender": _calc_pokemon_spec(partner),
                            "move": disp,
                            "field": {"gameType": "Doubles"},
                            **extra,
                        }
                    )
        try:
            results = calculate_batch(reqs)
        except Exception as e:  # noqa: BLE001
            return 0.0, f"batch_exception:{type(e).__name__}:{e}", [], {}
        if len(results) != len(reqs):
            return 0.0, f"batch_length:{len(results)}!={len(reqs)}", [], {}
        row: list[tuple[str, float, int, int, Any]] = []
        for defn, r in zip(panel, results[: len(panel)], strict=True):
            row.append(_parse_hit(defn, r, label=str(defn.get("species") or "")))
        by_mid[mid] = row
        partner_row: list[tuple[str, float, int, int, Any] | None] = [
            None
        ] * len(panel)
        if spread and partner_idxs:
            for j, i in enumerate(partner_idxs):
                partner = panel[i].get("partner") or {}
                partner_row[i] = _parse_hit(
                    partner,
                    results[len(panel) + j],
                    label=str(partner.get("species") or ""),
                )
        by_mid_partner[mid] = partner_row

    def _member_score(
        *,
        mid: str,
        defn: dict[str, Any],
        hit: tuple[str, float, int, int, Any],
        incoming_frac: float | None,
        incoming: bool,
        apply_finisher: bool,
    ) -> tuple[str, float, float, bool, int, int, Any] | None:
        kind, raw_frac, atk_spe, def_spe, r = hit
        if kind != "ok":
            return None
        effective = int(atk_spe * (2 + spe_stages) / 2) if spe_stages else atk_spe
        outsped = atk_spe > 0 and def_spe > 0 and effective < def_spe
        lived_shield = (
            outsped and incoming_frac is not None and incoming_frac < 1.0
        )
        combined = False
        dname = str(defn.get("species") or "")
        if (
            apply_finisher
            and fin_mid is not None
            and mid != fin_mid
            and lived_shield
            and raw_frac < 1.0
        ):
            _seq, combined = _priority_finisher_combined_ko(
                finisher_frac=finisher_fracs.get(dname),
                raw_frac=raw_frac,
            )
        kbin = "ohko" if combined else _ko_frac_bin(raw_frac)
        capped = min(raw_frac, _SETUP_DAMAGE_FRAC_CAP)
        ment = (snap.get("moves") or {}).get(mid) or {}
        capped *= effective_accuracy(
            _move_base_accuracy(mid),
            ability,
            defender_ability=defn.get("ability"),
            category=str(ment.get("category") or "") or None,
        )
        weight = _setup_turn_order_weight(
            mid,
            atk_spe,
            def_spe,
            ability,
            incoming_ohko=incoming,
            spe_stages=spe_stages,
        )
        return (kbin, weight * capped, raw_frac, combined, atk_spe, def_spe, r)

    used: list[tuple[str, str]] = []
    fracs: list[float] = []
    remains: list[float] = []
    sweep_ohko = 0
    sweep_2hko = 0
    per_defender: list[dict[str, Any]] = []
    mid_counts: dict[str, int] = {}

    for i, defn in enumerate(panel):
        dname = str(defn.get("species") or i)
        pair_label = _pair_entry_label(defn)
        partner_defn = defn.get("partner")
        has_partner = isinstance(partner_defn, dict) and bool(
            partner_defn.get("species")
        )
        incoming_frac = ohko_mask.get(dname)
        incoming = incoming_frac is not None and incoming_frac >= 1.0
        # best: bin_rank, weighted, mid, raw_frac, combined_primary,
        #        atk_spe, def_spe, r_primary, r_partner|None, pair_bin
        best: tuple[
            int, float, str, float, bool, int, int, Any, Any, str
        ] | None = None
        for mid in mids:
            prim = _member_score(
                mid=mid,
                defn=defn,
                hit=by_mid[mid][i],
                incoming_frac=incoming_frac,
                incoming=incoming,
                apply_finisher=True,
            )
            if prim is None:
                continue
            kbin_p, w_p, raw_p, comb_p, atk_spe, def_spe, r_p = prim
            r_s: Any = None
            spread = _is_spread_damage_mid(mid) and has_partner
            # Spread: bin = primary-alone; continuous = max(primary, pair_mean).
            # Partner miss → primary_alone (never worse than single-target).
            if spread:
                pair_bin = kbin_p
                combined = comb_p
                weighted, raw_frac = w_p, raw_p
                phit = by_mid_partner[mid][i]
                if phit is not None:
                    sec = _member_score(
                        mid=mid,
                        defn=partner_defn,  # type: ignore[arg-type]
                        hit=phit,
                        incoming_frac=incoming_frac,
                        incoming=incoming,
                        apply_finisher=False,
                    )
                    if sec is not None:
                        _kbin_s, w_s, raw_s, _comb_s, _as, _ds, r_s = sec
                        pair_mean_w = 0.5 * (w_p + w_s)
                        pair_mean_raw = 0.5 * (raw_p + raw_s)
                        if pair_mean_w > w_p:
                            weighted, raw_frac = pair_mean_w, pair_mean_raw
            else:
                pair_bin = kbin_p
                weighted = w_p
                raw_frac = raw_p
                combined = comb_p
            key = (
                _KO_BIN_RANK[pair_bin],
                weighted,
                mid,
                raw_frac,
                combined,
                atk_spe,
                def_spe,
                r_p,
                r_s,
                pair_bin,
            )
            if best is None or key[0] > best[0] or (
                key[0] == best[0]
                and (
                    key[1] > best[1]
                    or (key[1] == best[1] and mid < best[2])
                )
            ):
                best = key
        if best is None:
            continue
        (
            _br,
            weighted,
            mid,
            raw_frac,
            combined,
            atk_spe,
            def_spe,
            r,
            r_partner,
            pair_bin,
        ) = best
        fracs.append(weighted)
        used.append((pair_label, mid))
        mid_counts[mid] = mid_counts.get(mid, 0) + 1
        if pair_bin == "ohko":
            sweep_ohko += 1
        if pair_bin in {"ohko", "2hko"}:
            sweep_2hko += 1
        per_defender.append(
            {
                "species": dname,
                "pair_label": pair_label,
                "mid": mid,
                "bin": pair_bin,
                "combined": combined,
                "raw_frac": raw_frac,
                "weighted": weighted,
            }
        )
        effective = int(atk_spe * (2 + spe_stages) / 2) if spe_stages else atk_spe
        outsped = atk_spe > 0 and def_spe > 0 and effective < def_spe
        lived_shield = (
            outsped and incoming_frac is not None and incoming_frac < 1.0
        )
        if outsped:
            recoil_frac = _recoil_frac_from_result(r, mid)
            drain_frac = _drain_frac_from_result(r, mid)
            if r_partner is not None and _is_spread_damage_mid(mid):
                recoil_frac += _recoil_frac_from_result(r_partner, mid)
                drain_frac += _drain_frac_from_result(r_partner, mid)
            if disguise:
                remains.append(min(1.0, max(0.0, 1.0 - recoil_frac + drain_frac)))
            elif lived_shield:
                seq_remain: float | None = None
                if combined:
                    seq_remain = 1.0
                elif to_id(calc_name) in _AEGISLASH_FORMES:
                    seq_remain = _aegislash_ks_reset(
                        kit_ids=kit_ids,
                        blade_incoming=blade_mask.get(dname),
                    )
                if seq_remain is not None:
                    remains.append(
                        min(1.0, max(0.0, seq_remain - recoil_frac + drain_frac))
                    )
                elif to_id(calc_name) in _AEGISLASH_FORMES and (
                    (_hit_frac_from_result(r) or 0.0) < 1.0
                ):
                    # Primary raw only — scored raw_frac may be pair_mean.
                    pass  # Aegislash sequence failed — no remain (legacy)
                else:
                    remains.append(
                        min(
                            1.0,
                            max(
                                0.0,
                                1.0 - float(incoming_frac) - recoil_frac + drain_frac,
                            ),
                        )
                    )

    # debuff_surv: only defenders whose chosen mid has self Def/SpD drops
    debuff_surv: str | None = None
    drop_groups: dict[tuple[tuple[str, int], ...], list[str]] = {}
    for row in per_defender:
        drops = _self_defense_drops(str(row["mid"]))
        if not drops:
            continue
        sig = tuple(sorted((s, int(st)) for s, st in drops.items()))
        drop_groups.setdefault(sig, []).append(str(row["species"]))
    if drop_groups:
        k_surv = 0
        n_debuff = 0
        for sig, names in drop_groups.items():
            standing = dict(boosts)
            for s, st in sig:
                standing[s] = int(standing.get(s) or 0) + int(st)
            debuff_mask = _incoming_ohko_by_defender(
                snap=snap,
                candidate_name=calc_name,
                calc_name=calc_name,
                panel=[d for d in panel if str(d.get("species") or "") in set(names)],
                boosts=standing,
                calculate_batch=calculate_batch,
            )
            for dname in names:
                n_debuff += 1
                frac = debuff_mask.get(dname)
                if frac is None or frac < 1.0:
                    k_surv += 1
        debuff_surv = f"{k_surv}/{n_debuff}"

    sweep: dict[str, Any] = {
        "ohko": sweep_ohko,
        "ko2": sweep_2hko,
        "n": len(fracs),
        "n_surv": len(remains),
        "remain_mean": (sum(remains) / len(remains)) if remains else None,
        "remain_min": min(remains) if remains else None,
        "per_defender": per_defender,
        "mid_counts": mid_counts,
    }
    if debuff_surv is not None:
        sweep["debuff_surv"] = debuff_surv
    if not fracs:
        return 0.0, ";".join(errors[:4]) if errors else "no_usable_fracs", used, sweep
    return sum(fracs) / len(fracs), (";".join(errors[:4]) if errors else ""), used, sweep


def _select_setup_payoff(
    *,
    snap: dict[str, Any],
    sid: str,
    calc_name: str,
    item: str | None,
    ability: str | None,
    boost_stat: str,
    stages: int,
    panel: list[dict[str, Any]],
    calculate_batch: CalculateBatch,
    kit_moves: list[str] | None = None,
    used_out: list[tuple[str, str]] | None = None,
    exact_boosts: dict[str, int] | None = None,
    extra_spe_stages: int = 0,
    sweep_out: dict[str, Any] | None = None,
    # legacy kwargs ignored (callers/tests may still pass)
    usage_move_ids: set[str] | None = None,
    learnset: set[str] | None = None,
) -> tuple[str | None, float, str, SetupPriorityKind]:
    """Per-defender best kit damaging move; modal mid is admit-gate only.

    Selection: KO bin first, then weighted-capped frac. Shared incoming-OHKO once.
    Returns (modal_mid, raw_score, calc_error, priority_kind). Modal mid is the
    emptiness reject / legacy tuple shape — not a display payoff label (Stage 2).
    """
    del usage_move_ids, learnset  # Stage 1: kit-only M; usage bag no longer searched
    mids = _kit_damaging_mids(snap, kit_moves, boost_stat=boost_stat)
    if not mids:
        return None, 0.0, "no_kit_payoff", "none"
    score, err, used, sweep = _setup_kit_matrix_score(
        snap=snap,
        sid=sid,
        calc_name=calc_name,
        item=item,
        ability=ability,
        boost_stat=boost_stat,
        stages=stages,
        panel=panel,
        calculate_batch=calculate_batch,
        mids=mids,
        kit_moves=list(kit_moves or []),
        boosts=exact_boosts,
        extra_spe_stages=extra_spe_stages,
    )
    if used_out is not None:
        used_out.clear()
        used_out.extend(used)
    if sweep_out is not None:
        sweep_out.clear()
        sweep_out.update(sweep)
    counts = sweep.get("mid_counts") or {}
    if not counts:
        return None, score, err or "no_kit_payoff", "none"
    # Modal mid; tie → lexicographically smaller mid id
    modal = min(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]
    return modal, score, err, _setup_priority_kind(modal)


_AEGISLASH_FORMES = frozenset({"aegislash", "aegislashblade", "aegislashshield"})


def _calc_species_name(sid: str, name: str, snap: dict[str, Any]) -> str:
    if sid in _AEGISLASH_FORMES:
        return "Aegislash-Blade"
    return name


def _setup_defender_species(calc_name: str) -> str:
    if to_id(calc_name) in _AEGISLASH_FORMES:
        return "Aegislash-Shield"
    return calc_name


def _drop_setup_choice_item(item: str | None) -> str | None:
    """Choice + setup move cannot cash out; strip Choice from setup kits."""
    if item and to_id(item) in _SETUP_CHOICE_ITEMS:
        return None
    return item


def _attacker_kit(
    name: str,
    sid: str,
    snap: dict[str, Any],
    learnset: set[str],
    *,
    boost_stat: str,
    entry: dict[str, Any] | None,
) -> tuple[str, str | None, str | None, list[str]]:
    """Return (calc_species, item, ability, moves_display)."""
    calc_name = _calc_species_name(sid, name, snap)
    built = featured_or_common_set(name) or featured_or_common_set(calc_name)
    if built:
        moves = list(built.get("moves") or [])
        item = _drop_setup_choice_item(built.get("item"))
        ability = built.get("ability")
        return calc_name, item, ability, moves
    usage_moves = [str(m.get("name") or "") for m in (entry or {}).get("common_moves") or []]
    abs_map = _species_abilities(snap, sid)
    ability = next(iter(abs_map.values()), None) if abs_map else None
    payoff = _best_payoff_move(
        snap,
        sid,
        learnset,
        boost_stat=boost_stat,
        usage_moves=usage_moves,
        ability=ability,
    )
    item = None
    for it in (entry or {}).get("common_items") or []:
        item = _drop_setup_choice_item(str(it.get("name") or "") or None)
        break
    moves = [payoff] if payoff else []
    return calc_name, item, ability, moves




def _setup_payoff_notes(
    used: list[tuple[str, str]],
    mid_counts: dict[str, int],
) -> tuple[list[str], dict[str, list[str]]]:
    """Structured payoff display from Stage 1 kit matrix (not a single modal label)."""
    payoff_moves = sorted(mid_counts, key=lambda m: (-mid_counts[m], m))
    targets: dict[str, list[str]] = {}
    for dname, mid in used:
        targets.setdefault(mid, []).append(dname)
    return payoff_moves, targets


def _ally_damage_risk_note(
    payoff_moves: list[str],
    snap: dict[str, Any],
) -> str | None:
    """Display-only ally-hit risk when payoff_moves include allAdjacent mids.

    Move-intrinsic (no teammate context). Returns None when no ally-hit payoff.
    """
    hit: list[str] = []
    types: set[str] = set()
    sound = False
    moves_map = snap.get("moves") or {}
    for raw in payoff_moves:
        mid = to_id(raw)
        if mid not in _ALLY_HIT_DAMAGE_MOVE_IDS:
            continue
        hit.append(mid)
        if mid in _SOUND_ALLY_HIT_MOVE_IDS:
            sound = True
        typ = str((moves_map.get(mid) or {}).get("type") or "")
        if typ:
            types.add(typ)
    if not hit:
        return None
    names = [
        str((moves_map.get(mid) or {}).get("name") or mid) for mid in sorted(hit)
    ]
    parts: list[str] = []
    for typ in sorted(types):
        frag = _ALLY_HIT_TYPE_PROTECTIONS.get(typ)
        if frag:
            parts.append(f"{typ}: {frag}")
    if sound:
        parts.append("sound: Soundproof")
    parts.append("always: Telepathy, Friend Guard (3/4, not immune)")
    return (
        f"ally-hit payoff(s): {', '.join(names)} — " + "; ".join(parts)
    )


def _payoff_coverage_note(
    used: list[tuple[str, str]],
    *,
    snap: dict[str, Any],
    primary_mid: str,
) -> str | None:
    """Per-defender move breakdown when a candidate used more than one payoff.

    ID+BP / ``_damage_score`` fallback path only — Stage 2 setup categories use
    ``_setup_payoff_notes`` instead.
    """
    if not used:
        return None
    by_move: dict[str, list[str]] = {}
    for dname, mid in used:
        by_move.setdefault(mid, []).append(dname)
    if len(by_move) <= 1:
        return None
    primary = to_id(primary_mid)
    order = [primary] + [m for m in by_move if m != primary]
    parts: list[str] = []
    for mid in order:
        defs = by_move.get(mid) or []
        if not defs:
            continue
        disp = _move_display(snap, mid)
        if mid == primary:
            parts.append(f"{disp}×{len(defs)}")
        else:
            parts.append(f"{disp}×{len(defs)} ({', '.join(defs)})")
    return "; ".join(parts)


def _ko_frac_bin(frac: float) -> str:
    if frac >= 1.0:
        return "ohko"
    if frac >= 0.5:
        return "2hko"
    return "3plus"


def _is_bulk_crossing(unboosted: float, boosted: float) -> bool:
    a, b = _ko_frac_bin(unboosted), _ko_frac_bin(boosted)
    return (a == "ohko" and b != "ohko") or (a == "2hko" and b == "3plus")


def _move_override_extra(mid: str) -> dict[str, Any]:
    if mid in {"ragefist", "lastrespects"}:
        return {"moveOverrides": {"basePower": _scaled_base_power(mid, 50)}}
    return {}


def _candidate_defender_spec(
    name: str, calc_name: str, *, species: str | None = None
) -> dict[str, Any]:
    built = featured_or_common_set(name) or featured_or_common_set(calc_name)
    spec: dict[str, Any] = {"species": species or _setup_defender_species(calc_name)}
    if not built:
        return spec
    if built.get("evs"):
        spec["evs"] = dict(built["evs"])
    for k in ("item", "ability", "nature"):
        if built.get(k):
            spec[k] = built[k]
    return spec


def _hit_frac_from_result(r: Any) -> float | None:
    if not isinstance(r, dict) or "error" in r:
        return None
    dmg = (r.get("damageRange") or [0, 0])[-1]
    hp = ((r.get("raw") or {}).get("stats") or {}).get("defender") or {}
    try:
        hp_f = float(hp.get("hp") or 0)
        dmg_f = float(dmg)
    except (TypeError, ValueError):
        return None
    if hp_f <= 0:
        return None
    return dmg_f / hp_f


def _incoming_ohko_by_defender(
    *,
    snap: dict[str, Any],
    candidate_name: str,
    calc_name: str,
    panel: list[dict[str, Any]],
    boosts: dict[str, int],
    calculate_batch: CalculateBatch,
    defender_species: str | None = None,
) -> dict[str, float]:
    """Per panel member: incoming damage/HP frac from their usage hit.

    Nonzero def/spd in `boosts` (pos or neg) are applied on the candidate.
    Exactly one of def/spd nonzero → category-matched ranked payoffs.
    Both or neither → first damaging usage move (any category), still with
    both stages on the defender when both are set.
    Missing name → no connected hit. Callers treat frac ≥ 1.0 as OHKO.
    """
    nonzero = {
        s: int(boosts[s])
        for s in ("def", "spd")
        if int(boosts.get(s) or 0) != 0
    }
    cand = _candidate_defender_spec(
        candidate_name, calc_name, species=defender_species
    )
    if nonzero:
        cand = {**cand, "boosts": {**(cand.get("boosts") or {}), **nonzero}}
    moves_map = snap.get("moves") or {}
    out: dict[str, float] = {}
    try:
        if len(nonzero) == 1:
            def_stat = next(iter(nonzero))
            category_stat = "spa" if def_stat == "spd" else "atk"
            ranked_by_i: list[list[str]] = []
            for defn in panel:
                sid = to_id(str(defn.get("species") or ""))
                usage = list(defn.get("usage_moves") or defn.get("moves") or [])
                ranked_by_i.append(
                    _ranked_payoff_moves(
                        snap,
                        sid,
                        set(),
                        boost_stat=category_stat,
                        usage_moves=usage,
                        usage_only=True,
                        boost_count=0,
                        ability=str(defn.get("ability") or "") or None,
                    )
                )
            pending = [i for i, mids in enumerate(ranked_by_i) if mids]
            depth = 0
            while pending:
                reqs: list[dict[str, Any]] = []
                meta: list[int] = []
                next_pending: list[int] = []
                for i in pending:
                    mids = ranked_by_i[i]
                    if depth >= len(mids):
                        continue
                    mid = mids[depth]
                    disp = _move_display(snap, mid)
                    extra = _move_override_extra(mid)
                    atk = _calc_pokemon_spec(panel[i], extra={"moves": [disp]})
                    reqs.append(
                        {
                            "attacker": atk,
                            "defender": dict(cand),
                            "move": disp,
                            "field": {"gameType": "Doubles"},
                            **extra,
                        }
                    )
                    meta.append(i)
                if not reqs:
                    break
                results = calculate_batch(reqs)
                for i, r in zip(meta, results, strict=True):
                    frac = _hit_frac_from_result(r)
                    if frac is None or frac <= 0:
                        if depth + 1 < len(ranked_by_i[i]):
                            next_pending.append(i)
                        continue
                    out[str(panel[i].get("species") or "")] = frac
                pending = next_pending
                depth += 1
            return out
        reqs = []
        names: list[str] = []
        for defn in panel:
            dname = str(defn.get("species") or "")
            disp = None
            for raw in list(defn.get("usage_moves") or defn.get("moves") or []):
                ment = moves_map.get(to_id(raw)) or {}
                try:
                    bp = int(ment.get("basePower") or 0)
                except (TypeError, ValueError):
                    bp = 0
                if bp > 0 and ment.get("category") in {"Physical", "Special"}:
                    disp = str(ment.get("name") or raw)
                    break
            if not disp:
                continue
            extra = _move_override_extra(to_id(disp))
            atk = _calc_pokemon_spec(defn, extra={"moves": [disp]})
            reqs.append(
                {
                    "attacker": atk,
                    "defender": dict(cand),
                    "move": disp,
                    "field": {"gameType": "Doubles"},
                    **extra,
                }
            )
            names.append(dname)
        if not reqs:
            return out
        for dname, r in zip(names, calculate_batch(reqs), strict=True):
            frac = _hit_frac_from_result(r)
            if frac is None:
                continue
            out[dname] = frac
    except Exception:  # noqa: BLE001 — damage score fails open per defender
        return out
    return out


def _setup_bulk_crossings(
    *,
    snap: dict[str, Any],
    candidate_name: str,
    calc_name: str,
    panel: list[dict[str, Any]],
    def_stat: str,
    stages: int,
    calculate_batch: CalculateBatch,
) -> tuple[int, int]:
    """Incoming KO-bin flips after boosting candidate def_stat. Returns (k, n_relevant)."""
    category_stat = "spa" if def_stat == "spd" else "atk"
    unb_def = _candidate_defender_spec(candidate_name, calc_name)
    bst_def = {**unb_def, "boosts": {def_stat: stages}}
    ranked_by_i: list[list[str]] = []
    for defn in panel:
        sid = to_id(str(defn.get("species") or ""))
        usage = list(defn.get("usage_moves") or defn.get("moves") or [])
        ranked_by_i.append(
            _ranked_payoff_moves(
                snap,
                sid,
                set(),
                boost_stat=category_stat,
                usage_moves=usage,
                usage_only=True,
                boost_count=0,
                ability=str(defn.get("ability") or "") or None,
            )
        )
    pending = [i for i, mids in enumerate(ranked_by_i) if mids]
    connected: list[tuple[float, float]] = []
    depth = 0
    try:
        while pending:
            reqs: list[dict[str, Any]] = []
            meta: list[int] = []
            next_pending: list[int] = []
            for i in pending:
                mids = ranked_by_i[i]
                if depth >= len(mids):
                    continue
                mid = mids[depth]
                disp = _move_display(snap, mid)
                extra = _move_override_extra(mid)
                atk = _calc_pokemon_spec(panel[i], extra={"moves": [disp]})
                reqs.append(
                    {
                        "attacker": atk,
                        "defender": dict(unb_def),
                        "move": disp,
                        "field": {"gameType": "Doubles"},
                        **extra,
                    }
                )
                meta.append(i)
            if not reqs:
                break
            results = calculate_batch(reqs)
            hit_is: list[int] = []
            hit_unb: dict[int, float] = {}
            for i, r in zip(meta, results, strict=True):
                frac = _hit_frac_from_result(r)
                if frac is None or frac <= 0:
                    if depth + 1 < len(ranked_by_i[i]):
                        next_pending.append(i)
                    continue
                hit_is.append(i)
                hit_unb[i] = frac
            if hit_is:
                reqs_b: list[dict[str, Any]] = []
                for i in hit_is:
                    mid = ranked_by_i[i][depth]
                    disp = _move_display(snap, mid)
                    extra = _move_override_extra(mid)
                    atk = _calc_pokemon_spec(panel[i], extra={"moves": [disp]})
                    reqs_b.append(
                        {
                            "attacker": atk,
                            "defender": dict(bst_def),
                            "move": disp,
                            "field": {"gameType": "Doubles"},
                            **extra,
                        }
                    )
                results_b = calculate_batch(reqs_b)
                for i, r in zip(hit_is, results_b, strict=True):
                    frac_b = _hit_frac_from_result(r)
                    if frac_b is None:
                        continue
                    connected.append((hit_unb[i], max(frac_b, 0.0)))
            pending = next_pending
            depth += 1
    except Exception:  # noqa: BLE001 — construction continues with zero crossings
        return 0, 0
    n_rel = len(connected)
    k = sum(1 for u, b in connected if _is_bulk_crossing(u, b))
    return k, n_rel


def _setup_spe_crossings(
    *,
    candidate_name: str,
    calc_name: str,
    panel: list[dict[str, Any]],
    calculate_batch: CalculateBatch,
    snap: dict[str, Any] | None = None,
) -> tuple[int, int]:
    """not-faster → faster after +1 Spe. Returns (k, n_relevant)."""
    cand = _candidate_defender_spec(candidate_name, calc_name)
    moves_map = (snap or {}).get("moves") or {}
    reqs: list[dict[str, Any]] = []
    for defn in panel:
        usage = list(defn.get("usage_moves") or defn.get("moves") or [])
        move = "Tackle"
        for raw in usage:
            mid = to_id(raw)
            try:
                bp = int((moves_map.get(mid) or {}).get("basePower") or 0)
            except (TypeError, ValueError):
                bp = 0
            if bp > 0:
                move = str((moves_map.get(mid) or {}).get("name") or raw)
                break
        atk = _calc_pokemon_spec(defn, extra={"moves": [move]})
        reqs.append(
            {
                "attacker": atk,
                "defender": dict(cand),
                "move": move,
                "field": {"gameType": "Doubles"},
            }
        )
    if not reqs:
        return 0, 0
    try:
        results = calculate_batch(reqs)
    except Exception:  # noqa: BLE001
        return 0, 0
    k = 0
    n = 0
    for r in results:
        if not isinstance(r, dict) or "error" in r:
            continue
        stats = (r.get("raw") or {}).get("stats") or {}
        try:
            atk_spe = int((stats.get("attacker") or {}).get("spe") or 0)
            def_spe = int((stats.get("defender") or {}).get("spe") or 0)
        except (TypeError, ValueError):
            continue
        if atk_spe <= 0 or def_spe <= 0:
            continue
        n += 1
        boosted = int(def_spe * 1.5)
        if def_spe <= atk_spe < boosted:
            k += 1
    return k, n


def _crossing_k(note: str) -> int:
    try:
        return int(str(note).split("/")[0])
    except (TypeError, ValueError):
        return 0


def _sort_members_by_crossings(
    members: list[CandidateEval], *, field: str
) -> list[CandidateEval]:
    tier_i = {t: i for i, t in enumerate(ROLE_TIER_ORDER)}

    def key(c: CandidateEval) -> tuple:
        ti = tier_i.get(c.tier or "", 99)
        k = _crossing_k(c.criteria_notes.get(field) or "0")
        try:
            score = float(c.criteria_notes.get("damage_score") or 0)
        except (TypeError, ValueError):
            score = 0.0
        return (ti, -k, -score, c.species)

    return sorted(members, key=key)


def _sweep_note_fields(sweep: dict[str, Any] | None) -> dict[str, str]:
    """criteria_notes for OHKO/2HKO k/n and outsped-survive HP. n_surv=0 → n/a."""
    if not sweep:
        return {}
    n = int(sweep.get("n") or 0)
    n_surv = int(sweep.get("n_surv") or 0)
    mean = sweep.get("remain_mean")
    mn = sweep.get("remain_min")
    out = {
        "sweep_ohko": f"{int(sweep.get('ohko') or 0)}/{n}",
        "sweep_2hko": f"{int(sweep.get('ko2') or 0)}/{n}",
        "survive_n": str(n_surv),
    }
    if n_surv > 0 and mean is not None and mn is not None:
        out["survive_hp_mean"] = f"{float(mean):.2f}"
        out["survive_hp_min"] = f"{float(mn):.2f}"
    else:
        out["survive_hp_mean"] = "n/a"
        out["survive_hp_min"] = "n/a"
    debuff = sweep.get("debuff_surv")
    if debuff:
        out["debuff_surv"] = str(debuff)
    return out


def _sort_members_by_sweep(members: list[CandidateEval]) -> list[CandidateEval]:
    """Within-tier: OHKO k, then defined remain (n/a last), then damage_score."""
    tier_i = {t: i for i, t in enumerate(ROLE_TIER_ORDER)}

    def key(c: CandidateEval) -> tuple:
        notes = c.criteria_notes or {}
        ti = tier_i.get(c.tier or "", 99)
        ohko = _crossing_k(notes.get("sweep_ohko") or "0")
        mean_s = str(notes.get("survive_hp_mean") or "n/a")
        na = 0 if mean_s not in {"", "n/a"} else 1
        try:
            remain = float(mean_s) if na == 0 else 0.0
        except ValueError:
            na, remain = 1, 0.0
        try:
            score = float(notes.get("damage_score") or 0)
        except (TypeError, ValueError):
            score = 0.0
        return (ti, -ohko, na, -remain, -score, c.species)

    return sorted(members, key=key)


def _priority_finisher_combined_ko(
    *,
    finisher_frac: float | None,
    raw_frac: float,
) -> tuple[float | None, bool]:
    """Credit remain=1.0 + OHKO when payoff + priority finisher clears the threat.

    Caller already gated lived_shield and non-OHKO payoff. Species-agnostic.
    """
    if finisher_frac is not None and raw_frac + finisher_frac >= 1.0:
        return 1.0, True
    return None, False


def _aegislash_ks_reset(
    *,
    kit_ids: set[str],
    blade_incoming: float | None,
) -> float | None:
    """King's Shield Stance Change reset — Aegislash-only; caller gates forme."""
    if (
        "kingsshield" in kit_ids
        and blade_incoming is not None
        and blade_incoming < 1.0
    ):
        return 1.0
    return None


def _damage_score(
    *,
    attacker_name: str,
    item: str | None,
    ability: str | None,
    move: str,
    boost_stat: str,
    stages: int,
    panel: list[dict[str, Any]],
    calculate_batch: CalculateBatch,
    move_id: str | None = None,
    calc_ability: str | None = None,
    evs: dict[str, int] | None = None,
    fallback_mids: list[str] | None = None,
    snap: dict[str, Any] | None = None,
    attacker_sid: str | None = None,
    used_out: list[tuple[str, str]] | None = None,
    boosts: dict[str, int] | None = None,
    extra_spe_stages: int = 0,
    sweep_out: dict[str, Any] | None = None,
    kit_moves: list[str] | None = None,
) -> tuple[float, str]:
    """Mean turn-order-weighted damage/HP vs panel (soft-capped).

    `ability` is the ungated kit ability (Disguise / Speed Boost for turn-order).
    `calc_ability` is the payoff-gated ability passed to the calc (defaults to ability).

    If the primary move deals 0 (type immunity) to a defender, try `fallback_mids`
    in order against that defender. Skip the defender only if every candidate move
    also zeroes out. Calc errors are not retried.
    """
    if not move or not panel:
        return 0.0, "empty_panel_or_move"
    primary_mid = to_id(move_id or move)
    chain: list[str] = [primary_mid]
    seen_m = {primary_mid}
    for raw in fallback_mids or ():
        mid = to_id(raw)
        if mid and mid not in seen_m:
            seen_m.add(mid)
            chain.append(mid)
    boosts = dict(boosts) if boosts is not None else {boost_stat: stages}
    base_evs = (
        dict(evs)
        if evs is not None
        else {"hp": 4, "atk": 32, "def": 0, "spa": 32, "spd": 0, "spe": 32}
    )

    def _calc_ab_for(mid: str) -> str | None:
        if snap is not None:
            types = _species_types(snap, attacker_sid) if attacker_sid else set()
            return _setup_ability_for_payoff(ability, mid, snap=snap, types=types)
        if mid == primary_mid and calc_ability is not None:
            return calc_ability
        return ability

    def _read_result(
        r: Any, dname: str
    ) -> tuple[str, float, float, int, int] | tuple[str, str] | tuple[str]:
        if not isinstance(r, dict):
            return ("skip", f"{dname}:non_dict")
        if "error" in r:
            return ("skip", f"{dname}:{r.get('error')}")
        dmg = (r.get("damageRange") or [0, 0])[-1]
        stats = (r.get("raw") or {}).get("stats") or {}
        def_stats = stats.get("defender") or {}
        atk_stats = stats.get("attacker") or {}
        hp = def_stats.get("hp")
        try:
            hp_f = float(hp) if hp else 0.0
            dmg_f = float(dmg)
            atk_spe = int(atk_stats.get("spe") or 0)
            def_spe = int(def_stats.get("spe") or 0)
        except (TypeError, ValueError):
            return ("skip", f"{dname}:bad_range")
        if hp_f <= 0:
            return ("skip", f"{dname}:no_hp")
        if dmg_f <= 0:
            return ("zero",)
        return ("hit", hp_f, dmg_f, atk_spe, def_spe)

    pending: list[tuple[int, dict[str, Any]]] = list(enumerate(panel))
    fracs: list[float] = []
    errors: list[str] = []
    used: list[tuple[str, str]] = []
    aid = to_id(ability) if ability else ""
    spe_stages = extra_spe_stages + (1 if aid in _SETUP_SPEED_ABILITIES else 0)
    disguise = aid in _SETUP_SURVIVE_ABILITIES
    ohko_mask: dict[str, float] | None = None
    if snap is not None:
        ohko_mask = _incoming_ohko_by_defender(
            snap=snap,
            candidate_name=attacker_name,
            calc_name=attacker_name,
            panel=panel,
            boosts=boosts,
            calculate_batch=calculate_batch,
        )
    finisher_fracs: dict[str, float] = {}
    blade_mask: dict[str, float] = {}
    kit_ids: set[str] = set()
    debuff_surv: str | None = None
    drops = _self_defense_drops(primary_mid)
    # ponytail: if a move ever has both connect-recoil and self Def/SpD drop,
    # do not stack silently — flag and decide; sets are disjoint today.
    if drops and snap is not None and panel:
        standing = dict(boosts)
        for s, d in drops.items():
            standing[s] = int(standing.get(s) or 0) + int(d)
        debuff_mask = _incoming_ohko_by_defender(
            snap=snap,
            candidate_name=attacker_name,
            calc_name=attacker_name,
            panel=panel,
            boosts=standing,
            calculate_batch=calculate_batch,
        )
        n_panel = len(panel)
        k_surv = 0
        for defn in panel:
            dname = str(defn.get("species") or "")
            frac = debuff_mask.get(dname)
            if frac is None or frac < 1.0:
                k_surv += 1
        debuff_surv = f"{k_surv}/{n_panel}"
    if kit_moves is not None and snap is not None:
        kit_ids = {to_id(m) for m in kit_moves if m}
        finishers = kit_ids & _SETUP_PRIORITY_FINISHER_MOVES
        if finishers:
            # ponytail: ≤1 eligible finisher per kit today; sorted[0] if multi.
            fin_mid = sorted(finishers)[0]
            fin_disp = _move_display(snap, fin_mid)
            calc_ab = _calc_ab_for(fin_mid)
            fin_atk: dict[str, Any] = {
                "species": attacker_name,
                "evs": dict(base_evs),
                "boosts": dict(boosts),
                "moves": [fin_disp],
            }
            if item:
                fin_atk["item"] = item
            if calc_ab:
                fin_atk["ability"] = calc_ab
            fin_reqs = [
                {
                    "attacker": fin_atk,
                    "defender": _calc_pokemon_spec(defn),
                    "move": fin_disp,
                    "field": {"gameType": "Doubles"},
                }
                for defn in panel
            ]
            try:
                fin_results = calculate_batch(fin_reqs)
            except Exception:  # noqa: BLE001 — sequence credit fails open
                fin_results = []
            if len(fin_results) == len(panel):
                for defn, r in zip(panel, fin_results, strict=True):
                    frac = _hit_frac_from_result(r)
                    if frac is not None:
                        finisher_fracs[str(defn.get("species") or "")] = frac
        if (
            to_id(attacker_name) in _AEGISLASH_FORMES
            and "kingsshield" in kit_ids
        ):
            blade_mask = _incoming_ohko_by_defender(
                snap=snap,
                candidate_name=attacker_name,
                calc_name=attacker_name,
                panel=panel,
                boosts=boosts,
                calculate_batch=calculate_batch,
                defender_species="Aegislash-Blade",
            )
    sweep_ohko = 0
    sweep_2hko = 0
    n_hit = 0
    remains: list[float] = []
    for mid in chain:
        if not pending:
            break
        disp = _move_display(snap, mid) if snap is not None else (
            move if mid == primary_mid else mid
        )
        calc_ab = _calc_ab_for(mid)
        attacker: dict[str, Any] = {
            "species": attacker_name,
            "evs": dict(base_evs),
            "boosts": dict(boosts),
            "moves": [disp],
        }
        if item:
            attacker["item"] = item
        if calc_ab:
            attacker["ability"] = calc_ab
        req_extra: dict[str, Any] = {}
        if mid in {"ragefist", "lastrespects"}:
            # Snapshot Rage Fist / Last Respects is 50 BP; same assumptions as counters.py.
            req_extra["moveOverrides"] = {"basePower": _scaled_base_power(mid, 50)}
        reqs = [
            {
                "attacker": attacker,
                "defender": _calc_pokemon_spec(defn),
                "move": disp,
                "field": {"gameType": "Doubles"},
                **req_extra,
            }
            for _i, defn in pending
        ]
        try:
            results = calculate_batch(reqs)
        except Exception as e:  # noqa: BLE001 — construction continues with zero score
            return 0.0, f"batch_exception:{type(e).__name__}:{e}"
        if len(results) != len(pending):
            return 0.0, f"batch_length:{len(results)}!={len(pending)}"
        still: list[tuple[int, dict[str, Any]]] = []
        for (i, defn), r in zip(pending, results, strict=True):
            dname = str(defn.get("species") or i)
            parsed = _read_result(r, dname)
            kind = parsed[0]
            if kind == "hit":
                _k, hp_f, dmg_f, atk_spe, def_spe = parsed  # type: ignore[misc]
                raw_frac = dmg_f / hp_f
                n_hit += 1
                incoming_frac = None if ohko_mask is None else ohko_mask.get(dname)
                incoming = (
                    None if ohko_mask is None
                    else (incoming_frac is not None and incoming_frac >= 1.0)
                )
                effective = (
                    int(atk_spe * (2 + spe_stages) / 2) if spe_stages else atk_spe
                )
                outsped = atk_spe > 0 and def_spe > 0 and effective < def_spe
                lived_shield = (
                    outsped and incoming_frac is not None and incoming_frac < 1.0
                )
                seq_remain: float | None = None
                combined = False
                if kit_moves is not None and lived_shield and raw_frac < 1.0:
                    seq_remain, combined = _priority_finisher_combined_ko(
                        finisher_frac=finisher_fracs.get(dname),
                        raw_frac=raw_frac,
                    )
                    if (
                        seq_remain is None
                        and to_id(attacker_name) in _AEGISLASH_FORMES
                    ):
                        seq_remain = _aegislash_ks_reset(
                            kit_ids=kit_ids,
                            blade_incoming=blade_mask.get(dname),
                        )
                        combined = False
                kbin = "ohko" if combined else _ko_frac_bin(raw_frac)
                if kbin == "ohko":
                    sweep_ohko += 1
                if kbin in {"ohko", "2hko"}:
                    sweep_2hko += 1
                capped = min(raw_frac, _SETUP_DAMAGE_FRAC_CAP)
                ment = ((snap or {}).get("moves") or {}).get(mid) or {}
                capped *= effective_accuracy(
                    _move_base_accuracy(mid),
                    ability,
                    defender_ability=defn.get("ability"),
                    category=str(ment.get("category") or "") or None,
                )
                weight = _setup_turn_order_weight(
                    mid,
                    atk_spe,
                    def_spe,
                    ability,
                    incoming_ohko=incoming,
                    spe_stages=spe_stages,
                )
                if outsped:
                    recoil_frac = _recoil_frac_from_result(r, mid)
                    drain_frac = _drain_frac_from_result(r, mid)
                    if disguise:
                        remains.append(
                            min(1.0, max(0.0, 1.0 - recoil_frac + drain_frac))
                        )
                    elif lived_shield:
                        if seq_remain is not None:
                            remains.append(
                                min(
                                    1.0,
                                    max(0.0, seq_remain - recoil_frac + drain_frac),
                                )
                            )
                        elif (
                            to_id(attacker_name) in _AEGISLASH_FORMES
                            and kit_moves is not None
                            and raw_frac < 1.0
                        ):
                            pass  # Aegislash sequence failed — no remain (legacy)
                        else:
                            remains.append(
                                min(
                                    1.0,
                                    max(
                                        0.0,
                                        1.0
                                        - float(incoming_frac)
                                        - recoil_frac
                                        + drain_frac,
                                    ),
                                )
                            )
                fracs.append(weight * capped)
                used.append((dname, mid))
            elif kind == "zero":
                still.append((i, defn))
            else:
                errors.append(str(parsed[1]))
        pending = still
    for i, defn in pending:
        errors.append(f"{str(defn.get('species') or i)}:zero_damage")
    if used_out is not None:
        used_out.clear()
        used_out.extend(used)
    if sweep_out is not None:
        sweep_out.clear()
        sweep_out["ohko"] = sweep_ohko
        sweep_out["ko2"] = sweep_2hko
        sweep_out["n"] = n_hit
        sweep_out["n_surv"] = len(remains)
        if remains:
            sweep_out["remain_mean"] = sum(remains) / len(remains)
            sweep_out["remain_min"] = min(remains)
        else:
            sweep_out["remain_mean"] = None
            sweep_out["remain_min"] = None
        if debuff_surv is not None:
            sweep_out["debuff_surv"] = debuff_surv
    if not fracs:
        return 0.0, ";".join(errors[:4]) if errors else "no_usable_fracs"
    score = sum(fracs) / len(fracs)
    return score, (";".join(errors[:4]) if errors else "")


def _construct_setup_attacker(
    category: str,
    sub_criteria: dict[str, Any],
    legal_pool: list[str],
    *,
    snap: dict[str, Any],
    uctx: _UsageCtx,
    showdown_fetch: LiveFetch | None,
    reference_compendium: dict[str, Any] | RoleConstructionDraft | None,
    calculate_batch: CalculateBatch,
) -> RoleConstructionDraft:
    move_id = to_id(sub_criteria["move_id"])
    boost_stat = str(sub_criteria["boost_stat"])
    stages = int(sub_criteria.get("boost_stages") or 2)
    # Exhaustiveness guard (construction-time).
    exclusive = exclusive_self_boost_move(boost_stat=boost_stat, stages=stages)
    if exclusive != move_id:
        raise ValueError(f"criteria move_id {move_id} != exclusive {exclusive}")

    pool = _pool_index(legal_pool, snap)
    prior = _ref_members(reference_compendium)
    members: list[CandidateEval] = []
    rejected: list[RejectedCandidate] = []
    notes: list[str] = [
        f"delivery move locked by self +{stages} {boost_stat}-only Status rule → {move_id}"
    ]
    panel = _rc("_setup_threat_defenders")()
    notes.append(
        f"threat_panel=showdown>={_SETUP_THREAT_USAGE_PCT_FLOOR:.2f}%"
        f"/{_SETUP_THREAT_ENCOUNTER_GAMES}game n={len(panel)} pair=top1-partner "
        f"({_threat_panel_label(panel)})"
    )
    notes.append(
        "threat_panel_builds=cbd-first; showdown only for mega/base gap or missing CBD"
    )
    notes.append(
        "payoff=per-defender best kit damaging move (KO-bin then weighted frac); "
        "zeros kept in mean; no usage-bag search; sweep_ohko=best-move OHKO rate; "
        "debuff_surv n=defenders whose chosen mid has self Def/SpD drops"
    )

    # Learners.
    eligible: dict[str, str] = {}
    for sid, name in pool.items():
        ls = set(resolve_learnset(snap, sid) or [])
        if move_id not in ls:
            continue
        eligible[sid] = name

    # Showdown discount among eligible mega pairs (Acceptable path).
    # Reuse move-aware attribution: ratio-only discount is invalid when Mega does
    # not run the setup move. Stone-fallback notes are intentionally NOT mapped
    # into skip_discount (setup previously skipped discount when mega_sd was None).
    sd_cache: dict[str, dict[str, Any] | None] = {}
    _pair_usage, pair_notes, _stone = _mega_usage_attribution(
        eligible,
        frozenset({move_id}),
        snap=snap,
        uctx=uctx,
        sd_cache=sd_cache,
        showdown_fetch=showdown_fetch,
        notes=notes,
    )
    skip_discount = {sid for sid, note in pair_notes.items() if "discounted" in note}
    pair_attr = {sid: pair_notes[sid] for sid in skip_discount}

    # Pass 1: evaluate admitted candidates (no Excellent yet).
    provisional: list[dict[str, Any]] = []
    for sid, name in sorted(eligible.items(), key=lambda kv: kv[1]):
        learnset = set(resolve_learnset(snap, sid) or [])
        abs_map = _species_abilities(snap, sid)
        stats = _base_stats(snap, sid)
        entry = uctx.entry_for(name)
        branches = _setup_branches(
            learnset=learnset,
            abs_map=abs_map,
            stats=stats,
            entry=entry,
            snap=snap,
            boost_stat=boost_stat,
        )
        if not branches:
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason="clears neither neutralize-first (A) nor survive-and-sustain (B)",
                    change_reason=(
                        "setup membership gate"
                        if prior.get(sid)
                        else None
                    ),
                )
            )
            continue

        usage_proven = uctx.delivers(name, move_id)
        # CBD base move% > Mega Showdown move% → CBD is Mega-contaminated; only
        # trust Showdown form-separated base delivery (full-pool, not Skarmory-only).
        if usage_proven:
            pair_pool = set(eligible)
            mega_guess = f"{sid}mega"
            if mega_guess in (snap.get("species") or {}):
                pair_pool.add(mega_guess)
            pair = _mega_pair_ids(sid, snap, pair_pool)
            if pair and sid == pair[0]:
                _base_sid, mega_sid = pair
                mega_name = eligible.get(mega_sid) or str(
                    (snap.get("species") or {}).get(mega_sid, {}).get("name")
                    or mega_sid
                )
                mega_sd = _showdown_entry(
                    mega_name, cache=sd_cache, showdown_fetch=showdown_fetch
                )
                if _cbd_base_move_implausible_vs_mega(entry, mega_sd, move_id):
                    base_sd = _showdown_entry(
                        name, cache=sd_cache, showdown_fetch=showdown_fetch
                    )
                    usage_proven = _entry_has_move(base_sd, move_id)
                    notes.append(
                        f"CBD move-rate plausibility ({name}/{mega_name}): "
                        f"CBD {_move_pct(entry, move_id):.1f}% {move_id} > "
                        f"Mega Showdown {_move_pct(mega_sd, move_id):.1f}%; "
                        f"usage_proven={'Showdown base' if usage_proven else 'rejected'}"
                    )
        if usage_proven and not _hits_clear_set_pct_floor(
            name,
            {move_id},
            floor=_SETUP_PRESENCE_SET_PCT_FLOOR,
            uctx=uctx,
            sd_cache=sd_cache,
            showdown_fetch=showdown_fetch,
        ):
            usage_proven = False
        if not usage_proven:
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=f"learnset has {move_id} but no usage evidence of the setup move",
                    change_reason=(
                        f"CBD/Showdown usage re-eval / tier {prior.get(sid)!r} → rejected"
                        if prior.get(sid)
                        else None
                    ),
                )
            )
            continue

        calc_name, item, ability, kit_moves = _rc("_attacker_kit")(
            name, sid, snap, learnset, boost_stat=boost_stat, entry=entry
        )
        used: list[tuple[str, str]] = []
        sweep: dict[str, Any] = {}
        payoff_id, raw_score, calc_err, _priority_kind = _select_setup_payoff(
            snap=snap,
            sid=sid,
            calc_name=calc_name,
            item=item,
            ability=ability,
            boost_stat=boost_stat,
            stages=stages,
            panel=panel,
            calculate_batch=calculate_batch,
            used_out=used,
            sweep_out=sweep,
            kit_moves=kit_moves,
        )
        if not payoff_id:
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=(
                        "no kit damaging payoff matching boosted offense "
                        "(excluded recharge/charge/Focus Punch/Future Sight/Upper Hand/self-drop)"
                    ),
                    change_reason=(
                        f"setup calc/membership re-eval / tier {prior.get(sid)!r} → rejected"
                        if prior.get(sid)
                        else None
                    ),
                )
            )
            continue
        payoff_moves, payoff_targets = _setup_payoff_notes(
            used, sweep.get("mid_counts") or {}
        )

        both = set(branches) >= {"A", "B"}
        adjusted = _setup_adjusted_score(raw_score, both_branches=both)
        boosts: list[str] = []
        if both:
            boosts.append(f"both_div_{_SETUP_BOTH_BRANCH_SCORE_DIV:g}")

        sec_ability = bool(set(abs_map) & _SETUP_EXCELLENT_SECONDARY_ABILITIES)
        usage_move_ids = {
            to_id(m.get("name") or "") for m in (entry or {}).get("common_moves") or []
        }
        sec_move = bool(usage_move_ids & _SETUP_EXCELLENT_SECONDARY_MOVES)
        excellent_secondary = sec_ability or sec_move

        branch_note = "+".join(branches)
        if both:
            branch_basis = "calc_both_branches"
        elif "A" in branches:
            branch_basis = "calc_branch_a"
        else:
            branch_basis = "calc_branch_b"

        provisional.append(
            {
                "sid": sid,
                "name": name,
                "abs_map": abs_map,
                "raw_score": raw_score,
                "adjusted": adjusted,
                "boosts": boosts,
                "calc_err": calc_err,
                "calc_name": calc_name,
                "payoff_moves": payoff_moves,
                "payoff_targets": payoff_targets,
                "branch_note": branch_note,
                "branch_basis": branch_basis,
                "excellent_secondary": excellent_secondary,
                "sec_ability": sec_ability,
                "sweep": dict(sweep),
            }
        )

    # Damage-score admission floor (SD only via criteria; NP has no key → no-op).
    admit_floor = sub_criteria.get("damage_admission_floor")
    admit_floor_f = float(admit_floor) if admit_floor is not None else None
    provisional = _partition_by_admission_floor(
        provisional,
        score_key="adjusted",
        admission_floor=admit_floor_f,
        prior=prior,
        rejected=rejected,
    )
    if admit_floor_f is not None:
        notes.append(
            f"damage admission floor = {admit_floor_f:g} "
            f"(score >= floor; n_kept={len(provisional)})"
        )

    acc_mult = float(
        sub_criteria.get("acceptable_floor_mult") or _SETUP_ACCEPTABLE_FLOOR_MULT
    )

    # Pass 2: per-category floor from adjusted scores.
    floor = _setup_excellent_floor([p["adjusted"] for p in provisional])
    ranked = sorted(provisional, key=lambda p: p["adjusted"], reverse=True)
    top_label = ", ".join(
        f"{p['name']}={p['adjusted']:.3f}" for p in ranked[:2]
    ) or "none"
    notes.append(
        f"Excellent damage floor = 2nd-highest adjusted × {_SETUP_FLOOR_SECOND_MULT:g} "
        f"→ {floor:.3f} (top: {top_label})"
    )
    notes.append(
        f"Acceptable floor = Excellent floor × {acc_mult:g} "
        f"→ {floor * acc_mult:.3f}"
    )

    # Pass 3: assign tiers.
    for p in provisional:
        sid = p["sid"]
        name = p["name"]
        raw_score = p["raw_score"]
        adjusted = p["adjusted"]
        branch_note = p["branch_note"]
        branch_basis = p["branch_basis"]
        excellent_secondary = p["excellent_secondary"]
        abs_map = p["abs_map"]
        payoff_moves = p["payoff_moves"]
        payoff_targets = p["payoff_targets"]
        calc_name = p["calc_name"]
        calc_err = p["calc_err"]
        boosts = p["boosts"]

        mech_tier = _setup_mech_tier(adjusted, floor, acceptable_mult=acc_mult)
        excellent_exec = mech_tier == "Excellent"
        discounted = sid in skip_discount
        if discounted and mech_tier == "Excellent":
            demoted = _discount_outcome("Excellent")
            assert demoted == "Acceptable"
            tier = "Acceptable"
            basis = "usage_discounted"
            change_reason = (
                f"usage discount demote / mech Excellent → Acceptable "
                f"({pair_attr.get(sid, 'discounted')})"
            )
            usage_proven_note = "False"
        elif discounted:
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=(
                        f"Showdown usage discounted; mech {mech_tier} → reject "
                        f"({pair_attr.get(sid, '')})"
                    ),
                    change_reason=(
                        f"setup calc/membership re-eval / tier {prior.get(sid)!r} → rejected "
                        f"(score={adjusted:.3f}, branches={branch_note})"
                        if prior.get(sid)
                        else None
                    ),
                )
            )
            continue
        else:
            tier = mech_tier
            # Distinct basis per tier so tied_cluster does not flag across tiers.
            if tier == "Excellent":
                basis = branch_basis
            elif tier == "Good":
                basis = f"good_{branch_basis}"
            else:
                basis = f"acceptable_{branch_basis}"
            change_reason = None
            usage_proven_note = "True"

        prev_tier = prior.get(sid)
        if prev_tier and prev_tier != tier and change_reason is None:
            change_reason = (
                f"setup calc/membership re-eval / tier {prev_tier!r} → {tier!r} "
                f"(score={adjusted:.3f}, branches={branch_note})"
            )

        traits = [
            ClaimedTrait(
                name=str((snap.get("moves") or {}).get(move_id, {}).get("name") or move_id),
                criterion="delivery",
                purpose_claimed=f"setup via {move_id} (+{stages} {boost_stat})",
            ),
        ]
        for mid in payoff_moves:
            n_defs = len(payoff_targets.get(mid) or [])
            traits.append(
                ClaimedTrait(
                    name=_move_display(snap, mid),
                    criterion="execution",
                    purpose_claimed=(
                        f"calc damage fraction {adjusted:.3f} vs panel; "
                        f"branches={branch_note}; {n_defs} defender(s)"
                    ),
                )
            )
        if p["sec_ability"]:
            aid = next(iter(sorted(set(abs_map) & _SETUP_EXCELLENT_SECONDARY_ABILITIES)))
            traits.append(
                ClaimedTrait(
                    name=abs_map[aid],
                    criterion="secondary_role",
                    purpose_claimed="high-impact ability secondary (reliability×impact)",
                )
            )
        reinforce = "excellent_secondary" if excellent_secondary else ""
        members.append(
            CandidateEval(
                species=name,
                species_id=sid,
                tier=tier,
                delivery_class="move_setup",
                mechanism=str(
                    (snap.get("moves") or {}).get(move_id, {}).get("name") or move_id
                ),
                criteria_notes={
                    "delivery": "move-based setup (usage-proven)",
                    "execution": (
                        f"damage_score={adjusted:.3f} raw={raw_score:.3f} "
                        f"floor={floor:.3f} excellent_exec={excellent_exec}"
                    ),
                    "secondary_role": (
                        "excellent_secondary"
                        if excellent_secondary
                        else "none / Good-only reinforce"
                    ),
                    "branches_cleared": branch_note,
                    "usage_proven": usage_proven_note,
                    "attribution": pair_attr.get(sid, "none"),
                    "payoff_moves": payoff_moves,
                    "payoff_targets": payoff_targets,
                    "calc_species": calc_name,
                    "damage_score_raw": f"{raw_score:.3f}",
                    "damage_score": f"{adjusted:.3f}",
                    "score_boosts": "+".join(boosts) if boosts else "none",
                    **_sweep_note_fields(p.get("sweep")),
                    **({"calc_error": calc_err} if calc_err else {}),
                    **(
                        {"ally_damage_risk": ally_note}
                        if (
                            ally_note := _ally_damage_risk_note(
                                payoff_moves, snap
                            )
                        )
                        else {}
                    ),
                },
                claimed_traits=traits,
                reasoning=(
                    f"{tier}: branches={branch_note}; calc {adjusted:.3f} "
                    f"(floor {floor:.3f}); secondary={excellent_secondary}"
                ),
                change_reason=change_reason,
                reinforce_class=reinforce,
                excellence_basis=basis,
            )
        )

    notes.append(
        "sweep_ohko=outgoing OHKO k/n vs panel (unscaled max-roll); "
        "survive_hp=mean/min remain on outsped-and-survive (n_surv=0 → n/a); "
        "within-tier sort by sweep_ohko then survive_hp then damage_score"
    )
    members = _sort_members_by_sweep(members)
    return _draft_with_tiers(
        category, sub_criteria, members, rejected, notes=notes
    )


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


def _construct_offense_stage_setup(
    category: str,
    sub_criteria: dict[str, Any],
    legal_pool: list[str],
    *,
    snap: dict[str, Any],
    uctx: _UsageCtx,
    showdown_fetch: LiveFetch | None,
    reference_compendium: dict[str, Any] | RoleConstructionDraft | None,
    calculate_batch: CalculateBatch,
) -> RoleConstructionDraft:
    """Calm Mind / Bulk Up / Dragon Dance: +1 offense (+ matching bulk or Spe)."""
    move_id = to_id(sub_criteria["move_id"])
    boost_stat = str(sub_criteria["boost_stat"])
    stages = int(sub_criteria.get("boost_stages") or 1)
    want = {str(k): int(v) for k, v in (sub_criteria.get("exact_boosts") or {}).items()}
    exclusive = exact_self_boost_move(want)
    if exclusive != move_id:
        raise ValueError(f"criteria move_id {move_id} != exact boost {exclusive}")

    kind = str(sub_criteria.get("kind") or "")
    pool = _pool_index(legal_pool, snap)
    prior = _ref_members(reference_compendium)
    members: list[CandidateEval] = []
    rejected: list[RejectedCandidate] = []
    notes: list[str] = [
        f"exact Status self-boost {want} → {move_id}; no SD Branch A/B OR-gate"
    ]
    if kind == "offense_speed_setup":
        notes.append("Spe stage is setup-turn self-solve — rank on +1 Atk payoff only")
    panel = _rc("_setup_threat_defenders")()
    notes.append(
        f"threat_panel=showdown>={_SETUP_THREAT_USAGE_PCT_FLOOR:.2f}%"
        f"/{_SETUP_THREAT_ENCOUNTER_GAMES}game n={len(panel)} pair=top1-partner "
        f"({_threat_panel_label(panel)})"
    )
    notes.append(
        "threat_panel_builds=cbd-first; showdown only for mega/base gap or missing CBD"
    )
    notes.append(
        "payoff=per-defender best kit damaging move (KO-bin then weighted frac); "
        "zeros kept in mean; no usage-bag search; sweep_ohko=best-move OHKO rate; "
        "debuff_surv n=defenders whose chosen mid has self Def/SpD drops"
    )
    if kind == "offense_speed_setup":
        notes.append(
            "spe_crossings=not-faster→faster after int(unboosted*1.5); "
            "turn-order diagnostic only; k/n_relevant"
        )
    else:
        def_label = "SpD" if "spd" in want else "Def"
        notes.append(
            f"bulk_crossings=incoming {'Special' if 'spd' in want else 'Physical'} "
            f"after candidate {def_label}+{stages}; KO bins from damageRange[-1]/HP; "
            "OHKO→not-OHKO and 2HKO→3HKO+; immunity excluded from n_relevant"
        )
        notes.append(
            "within-tier sort by bulk_crossings; no promotion threshold (no natural gap)"
        )

    eligible = {
        sid: name
        for sid, name in pool.items()
        if move_id in set(resolve_learnset(snap, sid) or [])
    }
    sd_cache: dict[str, dict[str, Any] | None] = {}
    _pair_usage, pair_notes, _stone = _mega_usage_attribution(
        eligible,
        frozenset({move_id}),
        snap=snap,
        uctx=uctx,
        sd_cache=sd_cache,
        showdown_fetch=showdown_fetch,
        notes=notes,
    )
    skip_discount = {sid for sid, note in pair_notes.items() if "discounted" in note}
    pair_attr = {sid: pair_notes[sid] for sid in skip_discount}

    # DD has its own derived presence hole; CM/BU stay on the shared 0.1% ghost floor.
    presence_floor = (
        _DD_SETUP_PRESENCE_FLOOR
        if move_id == "dragondance"
        else _SETUP_PRESENCE_SET_PCT_FLOOR
    )

    provisional: list[dict[str, Any]] = []
    for sid, name in sorted(eligible.items(), key=lambda kv: kv[1]):
        learnset = set(resolve_learnset(snap, sid) or [])
        abs_map = _species_abilities(snap, sid)
        stats = _base_stats(snap, sid)
        entry = uctx.entry_for(name)
        if not uctx.delivers(name, move_id) or not _hits_clear_set_pct_floor(
            name,
            {move_id},
            floor=presence_floor,
            uctx=uctx,
            sd_cache=sd_cache,
            showdown_fetch=showdown_fetch,
        ):
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=f"learnset has {move_id} but no usage evidence of the setup move",
                    change_reason=(
                        f"usage re-eval / tier {prior.get(sid)!r} → rejected"
                        if prior.get(sid)
                        else None
                    ),
                )
            )
            continue
        calc_name, item, ability, kit_moves = _rc("_attacker_kit")(
            name, sid, snap, learnset, boost_stat=boost_stat, entry=entry
        )
        used: list[tuple[str, str]] = []
        sweep: dict[str, Any] = {}
        payoff_id, raw_score, calc_err, _pri = _select_setup_payoff(
            snap=snap,
            sid=sid,
            calc_name=calc_name,
            item=item,
            ability=ability,
            boost_stat=boost_stat,
            stages=stages,
            panel=panel,
            calculate_batch=calculate_batch,
            used_out=used,
            exact_boosts=want or None,
            extra_spe_stages=1 if kind == "offense_speed_setup" else 0,
            sweep_out=sweep,
            kit_moves=kit_moves,
        )
        if not payoff_id:
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason="no kit damaging payoff converting the boosted offense stat",
                    change_reason=(
                        f"payoff re-eval / tier {prior.get(sid)!r} → rejected"
                        if prior.get(sid)
                        else None
                    ),
                )
            )
            continue
        min_score = float(sub_criteria.get("min_score") or 0)
        if min_score > 0 and raw_score < min_score:
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=(
                        f"damage_score {raw_score:.3f} below membership floor "
                        f"{min_score:g}"
                    ),
                    change_reason=(
                        f"score floor {min_score:g} / tier {prior[sid]!r} → rejected"
                        if prior.get(sid)
                        else None
                    ),
                )
            )
            continue
        spe = int(stats.get("spe") or 0)
        has_pri = bool(_setup_priority_for_branch(learnset, snap, boost_stat))
        spe_note = (
            "priority_or_spe_ok"
            if has_pri or spe >= _SETUP_SPE_FLOOR
            else f"slow_no_priority spe={spe}"
        )
        payoff_moves, payoff_targets = _setup_payoff_notes(
            used, sweep.get("mid_counts") or {}
        )
        if kind == "offense_speed_setup":
            xk, xn = _setup_spe_crossings(
                candidate_name=name,
                calc_name=calc_name,
                panel=panel,
                calculate_batch=calculate_batch,
                snap=snap,
            )
        else:
            def_stat = "spd" if "spd" in want else "def"
            xk, xn = _setup_bulk_crossings(
                snap=snap,
                candidate_name=name,
                calc_name=calc_name,
                panel=panel,
                def_stat=def_stat,
                stages=stages,
                calculate_batch=calculate_batch,
            )
        provisional.append(
            {
                "sid": sid,
                "name": name,
                "raw_score": raw_score,
                "calc_err": calc_err,
                "calc_name": calc_name,
                "payoff_moves": payoff_moves,
                "payoff_targets": payoff_targets,
                "spe_note": spe_note,
                "abs_map": abs_map,
                "xk": xk,
                "xn": xn,
                "sweep": dict(sweep),
            }
        )

    # Damage-score admission floor (CM/BU via criteria; DD has no key → no-op).
    admit_floor = sub_criteria.get("damage_admission_floor")
    admit_floor_f = float(admit_floor) if admit_floor is not None else None
    provisional = _partition_by_admission_floor(
        provisional,
        score_key="raw_score",
        admission_floor=admit_floor_f,
        prior=prior,
        rejected=rejected,
    )
    if admit_floor_f is not None:
        notes.append(
            f"damage admission floor = {admit_floor_f:g} "
            f"(score >= floor; n_kept={len(provisional)})"
        )

    acc_mult = float(
        sub_criteria.get("acceptable_floor_mult") or _SETUP_ACCEPTABLE_FLOOR_MULT
    )

    floor = _setup_excellent_floor([p["raw_score"] for p in provisional])
    ranked = sorted(provisional, key=lambda p: p["raw_score"], reverse=True)
    top_label = ", ".join(f"{p['name']}={p['raw_score']:.3f}" for p in ranked[:2]) or "none"
    notes.append(
        f"Excellent damage floor = 2nd-highest × {_SETUP_FLOOR_SECOND_MULT:g} "
        f"→ {floor:.3f} (top: {top_label})"
    )
    notes.append(
        f"Acceptable floor = Excellent floor × {acc_mult:g} "
        f"→ {floor * acc_mult:.3f}"
    )

    for p in provisional:
        sid, name, raw_score = p["sid"], p["name"], p["raw_score"]
        mech_tier = _setup_mech_tier(raw_score, floor, acceptable_mult=acc_mult)
        discounted = sid in skip_discount
        if discounted and mech_tier == "Excellent":
            tier = "Acceptable"
            basis = "usage_discounted"
            change_reason = (
                f"usage discount demote / mech Excellent → Acceptable "
                f"({pair_attr.get(sid, 'discounted')})"
            )
        elif discounted:
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=(
                        f"Showdown usage discounted; mech {mech_tier} → reject "
                        f"({pair_attr.get(sid, '')})"
                    ),
                )
            )
            continue
        else:
            tier = mech_tier
            basis = (
                "calc_payoff"
                if tier == "Excellent"
                else f"{tier.lower()}_calc_payoff"
            )
            change_reason = None
        xk, xn = int(p["xk"]), int(p["xn"])
        xnote = f"{xk}/{xn}"
        prev = prior.get(sid)
        if prev and prev != tier and change_reason is None:
            change_reason = (
                f"stage-setup re-eval / tier {prev!r} → {tier!r} (score={raw_score:.3f})"
            )
        payoff_moves = p["payoff_moves"]
        payoff_targets = p["payoff_targets"]
        xfield = "spe_crossings" if kind == "offense_speed_setup" else "bulk_crossings"
        traits = [
            ClaimedTrait(
                name=str(
                    (snap.get("moves") or {}).get(move_id, {}).get("name") or move_id
                ),
                criterion="delivery",
                purpose_claimed=f"setup via {move_id} (+{stages} {boost_stat})",
            ),
        ]
        for mid in payoff_moves:
            n_defs = len(payoff_targets.get(mid) or [])
            traits.append(
                ClaimedTrait(
                    name=_move_display(snap, mid),
                    criterion="execution",
                    purpose_claimed=(
                        f"calc damage fraction {raw_score:.3f} vs panel; "
                        f"{n_defs} defender(s); {xfield}={xnote}"
                    ),
                )
            )
        members.append(
            CandidateEval(
                species=name,
                species_id=sid,
                tier=tier,
                delivery_class="move_setup",
                mechanism=str(
                    (snap.get("moves") or {}).get(move_id, {}).get("name") or move_id
                ),
                criteria_notes={
                    "delivery": "move-based setup (usage-proven)",
                    "execution": (
                        f"damage_score={raw_score:.3f} floor={floor:.3f} "
                        f"{p['spe_note']} {xfield}={xnote}"
                    ),
                    "payoff_moves": payoff_moves,
                    "payoff_targets": payoff_targets,
                    "calc_species": p["calc_name"],
                    "spe_note": p["spe_note"],
                    "damage_score": f"{raw_score:.3f}",
                    xfield: xnote,
                    **_sweep_note_fields(p.get("sweep")),
                    **({"calc_error": p["calc_err"]} if p["calc_err"] else {}),
                    **(
                        {"ally_damage_risk": ally_note}
                        if (
                            ally_note := _ally_damage_risk_note(
                                payoff_moves, snap
                            )
                        )
                        else {}
                    ),
                },
                claimed_traits=traits,
                reasoning=(
                    f"{tier}: calc {raw_score:.3f} (floor {floor:.3f}); "
                    f"{p['spe_note']}; {xfield}={xnote}"
                ),
                change_reason=change_reason,
                excellence_basis=basis,
            )
        )

    notes.append(
        "sweep_ohko=outgoing OHKO k/n vs panel (unscaled max-roll); "
        "survive_hp=mean/min remain on outsped-and-survive (n_surv=0 → n/a); "
        "display only — within-tier sort stays crossings"
    )
    xfield = "spe_crossings" if kind == "offense_speed_setup" else "bulk_crossings"
    members = _sort_members_by_crossings(members, field=xfield)
    return _draft_with_tiers(category, sub_criteria, members, rejected, notes=notes)


def _construct_def_payoff_setup(
    category: str,
    sub_criteria: dict[str, Any],
    legal_pool: list[str],
    *,
    snap: dict[str, Any],
    uctx: _UsageCtx,
    showdown_fetch: LiveFetch | None,
    reference_compendium: dict[str, Any] | RoleConstructionDraft | None,
    calculate_batch: CalculateBatch,
) -> RoleConstructionDraft:
    """Iron Defense + Body Press: Def-stage payoff."""
    setup_id = to_id(sub_criteria["setup_move_id"])
    payoff_id = to_id(sub_criteria["payoff_move_id"])
    boost_stat = str(sub_criteria.get("boost_stat") or "def")
    stages = int(sub_criteria.get("boost_stages") or 2)
    pool = _pool_index(legal_pool, snap)
    prior = _ref_members(reference_compendium)
    members: list[CandidateEval] = []
    rejected: list[RejectedCandidate] = []
    notes = [
        "learnset conjunction irondefense ∩ bodypress; admit iff the same usage "
        "row lists both (Champions row if present, else Showdown)",
        "Champions offline does not confirm ID+BP co-listing; Showdown-admitted "
        "field may be demoted at critic",
        "ID+BP dual-purpose split: high-offense members ≠ high-bulk-crossing "
        "members; sort-only, no promote/demote threshold",
    ]
    panel = _rc("_setup_threat_defenders")()
    notes.append(
        f"threat_panel=showdown>={_SETUP_THREAT_USAGE_PCT_FLOOR:.2f}%"
        f"/{_SETUP_THREAT_ENCOUNTER_GAMES}game n={len(panel)} pair=top1-partner "
        f"({_threat_panel_label(panel)})"
    )
    notes.append(
        "threat_panel_builds=cbd-first; showdown only for mega/base gap or missing CBD"
    )
    notes.append(
        "payoff_fallback=per-defender on type immunity (usage then learnset, "
        "STAB-then-corrected-BP); skip only if all candidate moves zero"
    )
    notes.append(
        f"bulk_crossings=incoming Physical after candidate Def+{stages}; "
        "KO bins from damageRange[-1]/HP; OHKO→not-OHKO and 2HKO→3HKO+; "
        "immunity excluded from n_relevant"
    )
    notes.append(
        "within-tier sort by bulk_crossings; no promotion threshold "
        "(gap does not map onto any single candidate)"
    )

    eligible = {
        sid: name
        for sid, name in pool.items()
        if {setup_id, payoff_id} <= set(resolve_learnset(snap, sid) or [])
    }
    sd_cache: dict[str, dict[str, Any] | None] = {}
    _pair_usage, pair_notes, _stone = _mega_usage_attribution(
        eligible,
        frozenset({setup_id, payoff_id}),
        snap=snap,
        uctx=uctx,
        sd_cache=sd_cache,
        showdown_fetch=showdown_fetch,
        notes=notes,
    )
    skip_discount = {sid for sid, note in pair_notes.items() if "discounted" in note}
    pair_attr = {sid: pair_notes[sid] for sid in skip_discount}

    payoff_disp = str((snap.get("moves") or {}).get(payoff_id, {}).get("name") or payoff_id)
    setup_disp = str((snap.get("moves") or {}).get(setup_id, {}).get("name") or setup_id)
    provisional: list[dict[str, Any]] = []
    for sid, name in sorted(eligible.items(), key=lambda kv: kv[1]):
        if not _same_row_both_moves(
            name,
            setup_id,
            payoff_id,
            uctx=uctx,
            sd_cache=sd_cache,
            showdown_fetch=showdown_fetch,
        ) or not _hits_clear_set_pct_floor(
            name,
            {setup_id, payoff_id},
            floor=_SETUP_PRESENCE_SET_PCT_FLOOR,
            uctx=uctx,
            sd_cache=sd_cache,
            showdown_fetch=showdown_fetch,
            require_all=True,
        ):
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=(
                        "learnset has irondefense+bodypress but same usage row "
                        "does not list both"
                    ),
                    change_reason=(
                        f"ID+BP usage re-eval / tier {prior.get(sid)!r} → rejected"
                        if prior.get(sid)
                        else None
                    ),
                )
            )
            continue
        learnset = set(resolve_learnset(snap, sid) or [])
        entry = uctx.entry_for(name)
        calc_name, item, ability, kit_moves = _rc("_attacker_kit")(
            name, sid, snap, learnset, boost_stat="atk", entry=entry
        )
        usage_ids = _present_usage_payoff_ids(
            name,
            entry,
            kit_moves,
            uctx=uctx,
            sd_cache=sd_cache,
            showdown_fetch=showdown_fetch,
        )
        ranked_payoffs = _ranked_payoff_moves(
            snap,
            sid,
            learnset,
            boost_stat="atk",
            usage_moves=sorted(usage_ids),
            boost_count=stages,
            ability=ability,
        )
        fallbacks = [m for m in ranked_payoffs if m != payoff_id]
        used_boosted: list[tuple[str, str]] = []
        unboosted, err0 = _damage_score(
            attacker_name=calc_name,
            item=item,
            ability=ability,
            move=payoff_disp,
            move_id=payoff_id,
            boost_stat=boost_stat,
            stages=0,
            panel=panel,
            calculate_batch=calculate_batch,
            evs=_BODY_PRESS_EVS,
            fallback_mids=fallbacks,
            snap=snap,
            attacker_sid=sid,
            kit_moves=kit_moves,
        )
        sweep: dict[str, Any] = {}
        boosted, err1 = _damage_score(
            attacker_name=calc_name,
            item=item,
            ability=ability,
            move=payoff_disp,
            move_id=payoff_id,
            boost_stat=boost_stat,
            stages=stages,
            panel=panel,
            calculate_batch=calculate_batch,
            evs=_BODY_PRESS_EVS,
            fallback_mids=fallbacks,
            snap=snap,
            attacker_sid=sid,
            used_out=used_boosted,
            sweep_out=sweep,
            kit_moves=kit_moves,
        )
        delta = boosted - unboosted
        calc_err = ";".join(x for x in (err0, err1) if x)
        if unboosted > _DEF_PAYOFF_DELTA_EPS and delta <= _DEF_PAYOFF_DELTA_EPS:
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=(
                        f"+{stages} Def does not convert on Body Press "
                        f"(unboosted={unboosted:.3f} boosted={boosted:.3f})"
                    ),
                )
            )
            continue
        coverage = _payoff_coverage_note(
            used_boosted, snap=snap, primary_mid=payoff_id
        )
        xk, xn = _setup_bulk_crossings(
            snap=snap,
            candidate_name=name,
            calc_name=calc_name,
            panel=panel,
            def_stat="def",
            stages=stages,
            calculate_batch=calculate_batch,
        )
        provisional.append(
            {
                "sid": sid,
                "name": name,
                "raw_score": boosted,
                "delta": delta,
                "unboosted": unboosted,
                "calc_err": calc_err,
                "calc_name": calc_name,
                "coverage": coverage,
                "xk": xk,
                "xn": xn,
                "sweep": dict(sweep),
            }
        )

    zero_boosted = sum(1 for p in provisional if p["raw_score"] <= 0)
    if provisional and zero_boosted == len(provisional):
        notes.append(
            "all admitted Body Press scores vs panel were 0 — Fighting immunities "
            "on the shared threat panel; panel not swapped"
        )
    elif zero_boosted:
        notes.append(
            f"{zero_boosted} admitted candidate(s) scored 0 vs panel "
            "(Fighting immunity likely); panel not swapped"
        )

    floor = _setup_excellent_floor([p["raw_score"] for p in provisional])
    ranked = sorted(provisional, key=lambda p: p["raw_score"], reverse=True)
    top_label = ", ".join(f"{p['name']}={p['raw_score']:.3f}" for p in ranked[:2]) or "none"
    notes.append(
        f"Excellent damage floor = 2nd-highest post-ID × {_SETUP_FLOOR_SECOND_MULT:g} "
        f"→ {floor:.3f} (top: {top_label})"
    )
    notes.append(
        f"Acceptable floor = Excellent floor × {_SETUP_ACCEPTABLE_FLOOR_MULT:g} "
        f"→ {floor * _SETUP_ACCEPTABLE_FLOOR_MULT:.3f}"
    )

    for p in provisional:
        sid, name, raw_score = p["sid"], p["name"], p["raw_score"]
        mech_tier = _setup_mech_tier(raw_score, floor)
        discounted = sid in skip_discount
        if discounted and mech_tier == "Excellent":
            tier = "Acceptable"
            basis = "usage_discounted"
            change_reason = (
                f"usage discount demote / mech Excellent → Acceptable "
                f"({pair_attr.get(sid, 'discounted')})"
            )
        elif discounted:
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=(
                        f"Showdown usage discounted; mech {mech_tier} → reject "
                        f"({pair_attr.get(sid, '')})"
                    ),
                )
            )
            continue
        else:
            tier = mech_tier
            basis = (
                "calc_body_press"
                if tier == "Excellent"
                else f"{tier.lower()}_calc_body_press"
            )
            change_reason = None
        prev = prior.get(sid)
        if prev and prev != tier and change_reason is None:
            change_reason = (
                f"def-payoff re-eval / tier {prev!r} → {tier!r} (score={raw_score:.3f})"
            )
        xnote = f"{int(p['xk'])}/{int(p['xn'])}"
        members.append(
            CandidateEval(
                species=name,
                species_id=sid,
                tier=tier,
                delivery_class="move_setup",
                mechanism=f"{setup_disp}+{payoff_disp}",
                criteria_notes={
                    "delivery": "irondefense+bodypress same-row usage",
                    "execution": (
                        f"post_id={raw_score:.3f} unboosted={p['unboosted']:.3f} "
                        f"delta={p['delta']:.3f} floor={floor:.3f} "
                        f"bulk_crossings={xnote}"
                    ),
                    "payoff_move": payoff_disp,
                    **({"payoff_coverage": p["coverage"]} if p["coverage"] else {}),
                    "calc_species": p["calc_name"],
                    "damage_score": f"{raw_score:.3f}",
                    "bulk_crossings": xnote,
                    **_sweep_note_fields(p.get("sweep")),
                    **({"calc_error": p["calc_err"]} if p["calc_err"] else {}),
                },
                claimed_traits=[
                    ClaimedTrait(
                        name=setup_disp,
                        criterion="delivery",
                        purpose_claimed=f"+{stages} Def via {setup_id}",
                    ),
                    ClaimedTrait(
                        name=(
                            payoff_disp
                            if not p["coverage"]
                            else f"{payoff_disp} + coverage"
                        ),
                        criterion="execution",
                        purpose_claimed=(
                            f"Body Press post-ID {raw_score:.3f} "
                            f"(delta {p['delta']:.3f})"
                            + (f"; {p['coverage']}" if p["coverage"] else "")
                            + f"; bulk_crossings={xnote}"
                        ),
                    ),
                ],
                reasoning=(
                    f"{tier}: post-ID {raw_score:.3f} delta={p['delta']:.3f} "
                    f"(floor {floor:.3f}); bulk_crossings={xnote}"
                ),
                change_reason=change_reason,
                excellence_basis=basis,
            )
        )

    notes.append(
        "sweep_ohko + sweep_2hko vs panel (ID+BP OHKO clumps; 2HKO+ is the "
        "spreading axis); survive_hp n_surv=0 → n/a; display only — sort stays "
        "bulk_crossings"
    )
    members = _sort_members_by_crossings(members, field="bulk_crossings")
    return _draft_with_tiers(category, sub_criteria, members, rejected, notes=notes)


