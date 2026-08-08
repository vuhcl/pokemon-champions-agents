"""Role Compendium construction / critic / rebuild (ADR-019).

Three separate callables — construct does not self-critique.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, cast

from recommender.ability_classification import (
    execution_reinforce_abilities,
    flinch_denial_ability_ids,
    get_ability,
    taunt_denial_ability_ids,
)
from recommender.calc_client import calculate_batch as _default_calculate_batch
from recommender.coverage import ABILITY_TO_FIELD, get_relevant_threats
from recommender.ids import to_id
from recommender.legality import is_species_legal, load_snapshot, resolve_learnset
from recommender.matchup import _CHARGE_MOVES, _RECHARGE_MOVES, _makes_contact
from recommender.move_narrowing import move_priority
from recommender.reconcile import _item_mega_forme
from recommender.state import RecommenderState
from recommender.support_needs import _OFFENSIVE_PRIORITY_MOVES, _SELF_HEAL_MOVES
from recommender.usage_cbd import fetch_ingame_doubles_species
from recommender.usage_data import (
    featured_or_common_set,
    ingame_species_map,
    load_usage,
    showdown_species_map,
)
from recommender.usage_showdown import fetch_showdown_vgc_species

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROLES_DIR = ROOT / "data" / "roles"
_STAT_BOOSTS_PATH = ROOT / "data" / "moves" / "stat_boosts.v1.json"

LiveFetch = Callable[[str], dict[str, Any] | None]
CalculateBatch = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]

# Redirection Phase 2: Quiver Dance vs redirect turn-economy.
_COMPETING_IDENTITY_MOVES = frozenset({"quiverdance"})
# Base Showdown usage_pct must be ≥ this fraction of Mega's to keep usage_proven.
_SHOWDOWN_BASE_USAGE_RATIO = 0.25
# Fallback only when Mega has no Showdown entry: mega-stone item share on base CBD page.
_MEGA_STONE_FALLBACK_PCT = 80.0

# Setup attacker membership / ranking (ADR-015 deferred-payoff).
_SETUP_SPE_FLOOR = 100
# ponytail: doubles bulk heuristic; Role Compendium can replace with threat-calced bulk later.
_SETUP_BULK_FLOOR = 400
_SETUP_SUSTAIN_HEALS = _SELF_HEAL_MOVES | frozenset({"rest"})
_SETUP_SUSTAIN_ITEMS = frozenset({"leftovers", "blacksludge", "sitrusberry"})
_SETUP_SUSTAIN_DRAIN = frozenset(
    {
        "bitterblade",
        "drainpunch",
        "drainkiss",
        "gigadrain",
        "hornleech",
        "strengthsap",
    }
)
_SETUP_SPEED_ABILITIES = frozenset({"speedboost"})
# One-hit absorption — Branch B survival + turn-order exception (ADR-015).
_SETUP_SURVIVE_ABILITIES = frozenset({"disguise", "iceface"})
_SETUP_EXCELLENT_SECONDARY_ABILITIES = frozenset(
    {"intimidate", "defiant", "stancechange", "supremeoverlord"}
)
_SETUP_EXCELLENT_SECONDARY_MOVES = frozenset(
    {"tailwind", "lightscreen", "reflect", "stickyweb", "trickroom", "auroraveil"}
)
_SETUP_THREAT_PANEL_N = 8
# Priority score boost: inverse of modal 40 BP priority vs 80 BP non-priority.
# Applied only when the scored payoff move itself is priority (not learnset access).
_SETUP_PRIORITY_SCORE_MULT = 1.5
# Conditional priority (Sucker Punch etc.): usage-mix proxy ≈70% success → 1+0.7*(1.5-1).
_SETUP_CONDITIONAL_PRIORITY = frozenset({"suckerpunch", "thunderclap", "upperhand"})
_SETUP_CONDITIONAL_PRIORITY_MULT = 1.35
# Soft overkill cap: credit up to 25% beyond a KO (hard 1.0 flattened useful signal).
_SETUP_DAMAGE_FRAC_CAP = 1.25
# A+B: inverse of the former both-branch Excellent gate discount (floor × div).
_SETUP_BOTH_BRANCH_SCORE_DIV = 0.80
_SETUP_FLOOR_SECOND_MULT = 0.95
# Good/Acceptable split: anchored on the widest real gap in the SD Good field
# (0.869 | 0.768), whose stable plateau is (0.664, 0.752] × floor; 0.70 is the midpoint.
_SETUP_ACCEPTABLE_FLOOR_MULT = 0.70

SetupPriorityKind = Literal["none", "unconditional", "conditional"]
# ponytail: curated Showdown self.boosts offense drops — legality/stat_boosts conflate foe secondaries.
_SETUP_SELF_DROP_SPA = frozenset(
    {
        "overheat",
        "leafstorm",
        "dracometeor",
        "fleurcannon",
        "psychoboost",
        "makeitrain",
    }
)
_SETUP_SELF_DROP_ATK = frozenset(
    {
        "superpower",
        "vcreate",
    }
)
# Lock-in: 2-3 forced turns then self-confusion — same unmodeled multi-turn cost as charge/recharge.
_SETUP_LOCKIN_MOVES = frozenset({"outrage", "petaldance", "thrash", "ragingfury"})
# Same-turn unreliable / delayed / recharge / lock-in — not valid setup cash-out payoffs.
_SETUP_BANNED_PAYOFF = (
    frozenset({"focuspunch", "futuresight", "doomdesire"})
    | _CHARGE_MOVES
    | _RECHARGE_MOVES
    | _SETUP_LOCKIN_MOVES
)
_SETUP_PUNCH_MOVES = frozenset(
    {
        "bulletpunch",
        "drainpunch",
        "firepunch",
        "focuspunch",
        "icepunch",
        "machpunch",
        "megapunch",
        "poweruppunch",
        "shadowpunch",
        "skyuppercut",
        "thunderpunch",
        "cometpunch",
        "dizzypunch",
        "dynamicpunch",
        "jetpunch",
        "surgingstrikes",
        "wickedblow",
    }
)
_SETUP_BITE_MOVES = frozenset(
    {
        "bite",
        "crunch",
        "firefang",
        "fishiousrend",
        "hyperfang",
        "icefang",
        "jawlock",
        "poisonfang",
        "psychicfangs",
        "thunderfang",
    }
)
_SETUP_SLICE_MOVES = frozenset(
    {
        "aerialace",
        "aircutter",
        "airslash",
        "aquacutter",
        "behemothblade",
        "ceaselessedge",
        "crosspoison",
        "cut",
        "furycutter",
        "kowtowcleave",
        "leafblade",
        "nightslash",
        "populationbomb",
        "psyblade",
        "psychocut",
        "razorleaf",
        "razorshell",
        "sacredsword",
        "slash",
        "solarblade",
        "stoneaxe",
        "xscissor",
    }
)
_SETUP_PULSE_MOVES = frozenset(
    {
        "aurasphere",
        "darkpulse",
        "dragonpulse",
        "healpulse",
        "originpulse",
        "terrainpulse",
        "waterpulse",
    }
)

RAIN_SETTER_CRITERIA: dict[str, Any] = {
    "kind": "weather_setter",
    "condition": "Rain",
    "ability_ids": frozenset({"drizzle"}),
    "move_id": "raindance",
    "priority_abilities": frozenset({"prankster"}),
}

SUN_SETTER_CRITERIA: dict[str, Any] = {
    "kind": "weather_setter",
    "condition": "Sun",
    "ability_ids": frozenset({"drought", "orichalcumpulse"}),
    "move_id": "sunnyday",
    "priority_abilities": frozenset({"prankster"}),
}

SAND_SETTER_CRITERIA: dict[str, Any] = {
    "kind": "weather_setter",
    "condition": "Sand",
    "ability_ids": frozenset({"sandstream"}),
    "move_id": "sandstorm",
    "priority_abilities": frozenset({"prankster"}),
}

SNOW_SETTER_CRITERIA: dict[str, Any] = {
    "kind": "weather_setter",
    "condition": "Snow",
    "ability_ids": frozenset({"snowwarning"}),
    "move_id": "snowscape",
    "priority_abilities": frozenset({"prankster"}),
}

REDIRECTION_CRITERIA: dict[str, Any] = {
    "kind": "redirection",
    "condition": "",
    "move_ids": frozenset({"followme", "ragepowder"}),
    "ability_ids": frozenset(),
    "ally_reinforce_abilities": frozenset({"friendguard"}),
}

TRICK_ROOM_SETTER_CRITERIA: dict[str, Any] = {
    "kind": "trick_room_setter",
    "condition": "",
    "move_ids": frozenset({"trickroom"}),
    # No ability delivers Trick Room, so criterion 1 cannot separate candidates.
    "ability_ids": frozenset(),
}

SWORDS_DANCE_ATTACKER_CRITERIA: dict[str, Any] = {
    "kind": "setup_attacker",
    "condition": "",
    "move_id": "swordsdance",
    "boost_stat": "atk",
    "boost_stages": 2,
}

NASTY_PLOT_ATTACKER_CRITERIA: dict[str, Any] = {
    "kind": "setup_attacker",
    "condition": "",
    "move_id": "nastyplot",
    "boost_stat": "spa",
    "boost_stages": 2,
}

# Phase 1 closed secondary allowlist (never include primary redirect moves).
_REDIRECTION_SECONDARY_MOVES = frozenset(
    {
        "helpinghand",
        "encore",
        "tailwind",
        "lightscreen",
        "reflect",
        "auroraveil",
        "stickyweb",
        "trickroom",
        "lifedew",
    }
)
_REDIRECTION_SECONDARY_ABILITIES = frozenset({"friendguard", "hospitality"})
# Excellent floor: contemporaneous passive (Friend Guard) or persistent_after_setup.
# Hospitality / HH / LD / Encore / Aurora Veil: verified_secondary only (Good / admit).
_REDIRECTION_EXCELLENT_SECONDARY_MOVES = frozenset(
    {"tailwind", "lightscreen", "reflect", "stickyweb", "trickroom"}
)

# Trick Room's own closed allowlist: the redirection list minus the primary
# mechanism (trickroom) and minus tailwind — Tailwind and Trick Room are
# opposing turn-order strategies, so Tailwind cannot reinforce this role.
_TRICK_ROOM_DELIVERY_NOTE = (
    "move-only delivery at fixed -7 priority; identical for every candidate"
)
# Membership floor: a setter that moves last must survive to act (ADR-015
# 2026-07-28d). The only real gap in the field is 195 (Alakazam) → 220, so any
# value in (195, 220) excludes the same single candidate; 210 is the midpoint.
_TRICK_ROOM_BULK_FLOOR = 210
# Fake Out is Normal-type, so Ghost typing denies it outright — self-provided,
# but narrower than Armor Tail (all opposing priority) or Inner Focus (all
# flinch sources), which is why it ranks below them.
_FAKE_OUT_IMMUNE_TYPE = "ghost"
_TRICK_ROOM_SECONDARY_MOVES = _REDIRECTION_SECONDARY_MOVES - {"trickroom", "tailwind"}
_TRICK_ROOM_EXCELLENT_SECONDARY_MOVES = _REDIRECTION_EXCELLENT_SECONDARY_MOVES - {
    "trickroom",
    "tailwind",
}

_SUPPORT_MOVE_IDS = frozenset(
    {
        "tailwind",
        "lightscreen",
        "reflect",
        "auroraveil",
        "encore",
        "fakeout",
        "helpinghand",
        "followme",
        "ragepowder",
        "willowisp",
        "thunderwave",
        "wideguard",
        "quickguard",
        "allyswitch",
        "partingshot",
        "haze",
    }
)


@dataclass(frozen=True)
class ClaimedTrait:
    name: str
    criterion: str  # delivery | execution | secondary_role
    purpose_claimed: str


@dataclass
class CandidateEval:
    species: str
    species_id: str
    tier: str | None
    delivery_class: str
    mechanism: str
    criteria_notes: dict[str, str]
    claimed_traits: list[ClaimedTrait]
    reasoning: str
    change_reason: str | None = None
    reinforce_class: str = ""
    excellence_basis: str = ""


@dataclass
class RejectedCandidate:
    species: str
    species_id: str
    reason: str
    change_reason: str | None = None


@dataclass
class RoleConstructionDraft:
    category: str
    sub_criteria: dict[str, Any]
    candidates: list[CandidateEval]
    considered_rejected: list[RejectedCandidate]
    tiers: dict[str, list[str]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CritiqueFlag:
    principle: str
    candidates: tuple[str, ...]
    detail: str


@dataclass
class CritiqueResult:
    approved: bool
    flags: list[CritiqueFlag]


@dataclass
class RebuildResult:
    status: str
    draft: RoleConstructionDraft
    critique: CritiqueResult
    path: str | None


@dataclass
class _UsageCtx:
    live_fetch: LiveFetch | None
    showdown_fetch: LiveFetch | None = None
    mega_showdown_fallback: bool = False
    cache: dict[str, dict[str, Any] | None] = field(default_factory=dict)
    sd_cache: dict[str, dict[str, Any] | None] = field(default_factory=dict)

    def entry_for(self, species: str) -> dict[str, Any] | None:
        """Forme-aware offline row, else CBD live fetch; optional Mega→Showdown."""
        sid = to_id(species)
        offline = _offline_usage_row(sid)
        if offline is not None:
            return offline
        if self.live_fetch is not None:
            if sid not in self.cache:
                self.cache[sid] = self.live_fetch(species)
            live = self.cache[sid]
            if live is not None:
                return live
        if (
            self.mega_showdown_fallback
            and self.showdown_fetch is not None
            and _species_id_is_mega(sid)
        ):
            if sid not in self.sd_cache:
                self.sd_cache[sid] = self.showdown_fetch(species)
            return self.sd_cache[sid]
        return None

    def delivers(self, species: str, move_id: str) -> bool:
        return _entry_has_move(self.entry_for(species), move_id)

    def champions_entry(self, species: str) -> dict[str, Any] | None:
        """Champions in-game doubles row only, never ladder data.

        Champions is the target format, so where a row exists its verdict on a
        move outranks Showdown's. Shares entry_for's live-fetch cache.
        """
        sid = to_id(species)
        ingame = (load_usage().get("ingame_doubles") or {}).get("species") or {}
        row = ingame.get(sid)
        if isinstance(row, dict):
            return row
        if self.live_fetch is None:
            return None
        if sid not in self.cache:
            self.cache[sid] = self.live_fetch(species)
        return self.cache[sid]


def _species_id_is_mega(sid: str) -> bool:
    return sid.endswith("mega") or sid.endswith("megax") or sid.endswith("megay")


def _offline_usage_row(sid: str) -> dict[str, Any] | None:
    """Any usage map entry whose key == sid or startswith(sid)."""
    usage = load_usage()
    maps: list[dict[str, Any]] = [usage.get("species") or {}]
    maps.append((usage.get("ingame_doubles") or {}).get("species") or {})
    maps.append((usage.get("showdown_vgc_mb") or {}).get("species") or {})
    for smap in maps:
        if sid in smap and isinstance(smap[sid], dict):
            return smap[sid]
        for key, ent in smap.items():
            if isinstance(key, str) and key.startswith(sid) and isinstance(ent, dict):
                return ent
    return None


def _entry_has_move(entry: dict[str, Any] | None, move_id: str) -> bool:
    if not entry:
        return False
    mid = to_id(move_id)
    for m in entry.get("common_moves") or []:
        if to_id(m.get("name") or "") == mid:
            return True
    for fs in entry.get("featured_sets") or []:
        for m in fs.get("moves") or []:
            if to_id(m) == mid:
                return True
    return False


def _criteria_sets(
    sub_criteria: dict[str, Any],
) -> tuple[frozenset[str], str, frozenset[str], str]:
    ability_ids = frozenset(to_id(a) for a in sub_criteria["ability_ids"])
    move_id = to_id(sub_criteria["move_id"])
    priority = frozenset(to_id(a) for a in sub_criteria["priority_abilities"])
    condition = str(sub_criteria["condition"])
    return ability_ids, move_id, priority, condition


def _serialize_criteria(sub_criteria: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in sub_criteria.items():
        if isinstance(v, (set, frozenset)):
            out[k] = sorted(v)
        else:
            out[k] = v
    return out


def _species_abilities(snap: dict[str, Any], sid: str) -> dict[str, str]:
    entry = snap["species"].get(sid) or {}
    out: dict[str, str] = {}
    for name in (entry.get("abilities") or {}).values():
        if isinstance(name, str):
            out[to_id(name)] = name
    return out


def _base_stats(snap: dict[str, Any], sid: str) -> dict[str, int]:
    entry = snap["species"].get(sid) or {}
    raw = entry.get("baseStats") or entry.get("base_stats") or {}
    return {k: int(v) for k, v in raw.items()} if isinstance(raw, dict) else {}


def _pool_index(legal_pool: list[str], snap: dict[str, Any]) -> dict[str, str]:
    allowed = {to_id(s) for s in legal_pool}
    out: dict[str, str] = {}
    for sid in allowed:
        entry = snap["species"].get(sid)
        if not entry:
            out[sid] = next((s for s in legal_pool if to_id(s) == sid), sid)
            continue
        if not is_species_legal(snap, sid):
            continue
        out[sid] = str(entry.get("name") or sid)
    return out


def _admit_move_delivery(*, usage_proven: bool, independent_reinforce: bool) -> bool:
    """Shared Rain/Redirection bar: learnset alone is not membership."""
    return usage_proven or independent_reinforce


def _discount_outcome(mech_tier: str) -> str | None:
    """Showdown-discounted usage: Excellent-on-mechanism → Acceptable; else reject (None)."""
    if mech_tier == "Excellent":
        return "Acceptable"
    return None


def _excellent_secondary(
    *,
    has_friend_guard: bool,
    secondary_move_ids: set[str] | frozenset[str],
    excellent_move_ids: frozenset[str] = _REDIRECTION_EXCELLENT_SECONDARY_MOVES,
) -> bool:
    """Two-axis Excellent floor (reliability × impact) — not presence-only.

    Friend Guard = contemporaneous_passive. Allowlisted moves here =
    persistent_after_setup with documented magnitude. Hospitality / turn_gated
    moves / Aurora Veil do not clear this bar.
    """
    if has_friend_guard:
        return True
    return bool(set(secondary_move_ids) & excellent_move_ids)


def _execution_reinforce_ok(abs_map: dict[str, str]) -> bool:
    return bool(execution_reinforce_abilities(abs_map))


def _secondary_support_notes(
    entry: dict[str, Any] | None,
    *,
    move_ids: frozenset[str] | None = None,
) -> tuple[str, list[ClaimedTrait]]:
    allow = move_ids if move_ids is not None else _SUPPORT_MOVE_IDS
    hits: list[str] = []
    traits: list[ClaimedTrait] = []
    for m in (entry or {}).get("common_moves") or []:
        mid = to_id(m.get("name") or "")
        if mid in allow:
            name = str(m.get("name") or mid)
            hits.append(name)
            traits.append(
                ClaimedTrait(
                    name=name,
                    criterion="secondary_role",
                    purpose_claimed="other-directed support stacking",
                )
            )
    note = ", ".join(hits) if hits else "none observed in usage common_moves"
    return note, traits


def _ref_members(
    reference: dict[str, Any] | RoleConstructionDraft | None,
) -> dict[str, str]:
    if reference is None:
        return {}
    if isinstance(reference, RoleConstructionDraft):
        return {c.species_id: c.tier or "" for c in reference.candidates if c.tier}
    out: dict[str, str] = {}
    for c in reference.get("candidates") or []:
        sid = c.get("species_id") or to_id(c.get("species") or "")
        tier = c.get("tier")
        if sid and tier:
            out[str(sid)] = str(tier)
    for tier, names in (reference.get("tiers") or {}).items():
        for n in names or []:
            out.setdefault(to_id(n), str(tier))
    return out


def _condition_label(sub_criteria: dict[str, Any]) -> str:
    return str(sub_criteria.get("condition") or "")


def _move_display(snap: dict[str, Any], move_id: str) -> str:
    entry = (snap.get("moves") or {}).get(move_id) or {}
    return str(entry.get("name") or move_id)


def _degree_tuple(c: CandidateEval) -> tuple[str, str, str]:
    return (c.delivery_class, c.reinforce_class or "", c.excellence_basis or "")


def construct_role_category(
    category: str,
    sub_criteria: dict[str, Any],
    legal_pool: list[str],
    *,
    snap: dict[str, Any] | None = None,
    reference_compendium: dict[str, Any] | RoleConstructionDraft | None = None,
    live_fetch: LiveFetch | None = fetch_ingame_doubles_species,
    showdown_fetch: LiveFetch | None = fetch_showdown_vgc_species,
    calculate_batch: CalculateBatch | None = _default_calculate_batch,
) -> RoleConstructionDraft:
    """Build a draft ranking from the legal pool forward — never legality-after-search."""
    snap = snap or load_snapshot()
    kind = str(sub_criteria.get("kind") or "weather_setter")
    uctx = _UsageCtx(
        live_fetch=live_fetch,
        showdown_fetch=showdown_fetch,
        mega_showdown_fallback=(kind == "setup_attacker"),
    )
    if kind == "redirection":
        return _construct_redirection(
            category,
            sub_criteria,
            legal_pool,
            snap=snap,
            uctx=uctx,
            showdown_fetch=showdown_fetch,
            reference_compendium=reference_compendium,
        )
    if kind == "trick_room_setter":
        return _construct_trick_room_setter(
            category,
            sub_criteria,
            legal_pool,
            snap=snap,
            uctx=uctx,
            showdown_fetch=showdown_fetch,
            reference_compendium=reference_compendium,
        )
    if kind == "setup_attacker":
        return _construct_setup_attacker(
            category,
            sub_criteria,
            legal_pool,
            snap=snap,
            uctx=uctx,
            showdown_fetch=showdown_fetch,
            reference_compendium=reference_compendium,
            calculate_batch=calculate_batch or _default_calculate_batch,
        )
    return _construct_weather_setter(
        category,
        sub_criteria,
        legal_pool,
        snap=snap,
        uctx=uctx,
        showdown_fetch=showdown_fetch,
        reference_compendium=reference_compendium,
    )


def _construct_weather_setter(
    category: str,
    sub_criteria: dict[str, Any],
    legal_pool: list[str],
    *,
    snap: dict[str, Any],
    uctx: _UsageCtx,
    showdown_fetch: LiveFetch | None,
    reference_compendium: dict[str, Any] | RoleConstructionDraft | None,
) -> RoleConstructionDraft:
    ability_ids, move_id, priority_abilities, _condition = _criteria_sets(sub_criteria)
    pool = _pool_index(legal_pool, snap)
    pool_ids = set(pool)
    prior = _ref_members(reference_compendium)
    members: list[CandidateEval] = []
    rejected: list[RejectedCandidate] = []
    admitted_ids: set[str] = set()
    notes: list[str] = []
    cond = _condition_label(sub_criteria)

    # Ability holders in pool.
    ability_holders: dict[str, str] = {}
    holder_aid: dict[str, str] = {}
    for sid, name in pool.items():
        abs_map = _species_abilities(snap, sid)
        hit = ability_ids & set(abs_map)
        if not hit:
            continue
        aid = next(iter(sorted(hit)))
        ability_holders[sid] = name
        holder_aid[sid] = aid

    # Showdown mega-pair attribution among ability holders.
    skip_ability: set[str] = set()  # discounted base → reject, do not Excellent
    pair_attr: dict[str, str] = {}
    sd_cache: dict[str, dict[str, Any] | None] = {}
    seen_pairs: set[tuple[str, str]] = set()
    for sid in ability_holders:
        pair = _mega_pair_ids(sid, snap, set(ability_holders))
        if not pair or pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        base_sid, mega_sid = pair
        base_name, mega_name = ability_holders[base_sid], ability_holders[mega_sid]
        base_sd = _showdown_entry(base_name, cache=sd_cache, showdown_fetch=showdown_fetch)
        mega_sd = _showdown_entry(mega_name, cache=sd_cache, showdown_fetch=showdown_fetch)

        if mega_sd is not None:
            mega_pct = float(mega_sd.get("usage_pct") or 0.0)
            base_pct = float((base_sd or {}).get("usage_pct") or 0.0) if base_sd else 0.0
            pair_attr[mega_sid] = "showdown form-separated usage"
            if (
                mega_pct > base_pct
                and base_pct < _SHOWDOWN_BASE_USAGE_RATIO * mega_pct
            ):
                skip_ability.add(base_sid)
                pair_attr[base_sid] = (
                    f"showdown usage discounted "
                    f"(base {base_pct:.3f}% < {_SHOWDOWN_BASE_USAGE_RATIO}× "
                    f"mega {mega_pct:.3f}%)"
                )
                notes.append(
                    f"Showdown attribution ({base_name}/{mega_name}): "
                    f"mega usage_pct={mega_pct:.3f} base={base_pct:.3f}; "
                    f"base discounted as attribution artifact"
                )
            else:
                pair_attr[base_sid] = "showdown form-separated usage"
                notes.append(
                    f"Showdown attribution ({base_name}/{mega_name}): "
                    f"mega usage_pct={mega_pct:.3f} base={base_pct:.3f}; "
                    f"both kept (independent usage)"
                )
        elif _stone_fallback_ability(
            base_name, base_sid, mega_sid, uctx=uctx, snap=snap
        ):
            skip_ability.add(base_sid)
            pair_attr[base_sid] = "usage attributed to Mega via mega-stone fallback"
            pair_attr[mega_sid] = "mega-stone fallback (≥80% on base CBD page)"
            notes.append(
                f"Showdown miss for {mega_name}; stone-heuristic fallback used "
                f"for {base_name}/{mega_name}"
            )
        else:
            notes.append(
                f"Showdown miss for {mega_name}; no stone fallback — "
                f"both {base_name}/{mega_name} kept on ability alone"
            )

    for sid, name in sorted(ability_holders.items(), key=lambda x: x[1]):
        aid = holder_aid[sid]
        abs_map = _species_abilities(snap, sid)
        mechanism = abs_map[aid]
        entry = uctx.entry_for(name)
        secondary_note, secondary_traits = _secondary_support_notes(
            entry, move_ids=_REDIRECTION_SECONDARY_MOVES
        )
        has_fg = bool({"friendguard"} & set(abs_map))
        has_hospitality = "hospitality" in abs_map
        secondary_move_ids = {to_id(t.name) for t in secondary_traits}
        verified_secondary = has_fg or has_hospitality or bool(secondary_traits)
        excellent_secondary = _excellent_secondary(
            has_friend_guard=has_fg, secondary_move_ids=secondary_move_ids
        )
        traits = [
            ClaimedTrait(
                name=mechanism,
                criterion="delivery",
                purpose_claimed=f"set {cond} via ability",
            ),
            ClaimedTrait(
                name=mechanism,
                criterion="execution",
                purpose_claimed="automatic on switch-in; no turn cost",
            ),
        ]
        if has_fg:
            traits.append(
                ClaimedTrait(
                    name=abs_map["friendguard"],
                    criterion="secondary_role",
                    purpose_claimed="ally damage mitigation",
                )
            )
        if has_hospitality:
            traits.append(
                ClaimedTrait(
                    name=abs_map["hospitality"],
                    criterion="secondary_role",
                    purpose_claimed="ally heal on switch-in",
                )
            )
        traits.extend(secondary_traits)
        attr = pair_attr.get(sid, "none")
        discounted = sid in skip_ability
        if discounted:
            # Ability mech is Excellent; discount → Acceptable (not reject).
            demoted = _discount_outcome("Excellent")
            assert demoted == "Acceptable"
            prev = prior.get(sid)
            change_reason = (
                f"usage discount demote / mech Excellent → Acceptable "
                f"({attr})"
            )
            if prev == "Excellent":
                change_reason = (
                    f"usage discount demote / tier Excellent → Acceptable ({attr})"
                )
            elif prev and prev != "Acceptable":
                change_reason = (
                    f"usage discount / tier {prev!r} → Acceptable ({attr})"
                )
            members.append(
                CandidateEval(
                    species=name,
                    species_id=sid,
                    tier="Acceptable",
                    delivery_class="ability",
                    mechanism=mechanism,
                    criteria_notes={
                        "delivery": "ability-guaranteed (more reliable than move)",
                        "execution": (
                            "automatic on switch-in; usage discounted vs Mega form"
                        ),
                        "secondary_role": secondary_note,
                        "verified_secondary": str(verified_secondary),
                        "excellent_secondary": str(excellent_secondary),
                        "attribution": attr,
                        "usage_proven": "False",
                    },
                    claimed_traits=traits,
                    reasoning=(
                        f"{mechanism} clears Acceptable "
                        f"(mech Excellent, Showdown usage discounted; "
                        f"excellent_secondary={excellent_secondary})."
                    ),
                    change_reason=change_reason,
                    reinforce_class="",
                    excellence_basis="usage_discounted",
                )
            )
            admitted_ids.add(sid)
            continue

        members.append(
            CandidateEval(
                species=name,
                species_id=sid,
                tier="Excellent",
                delivery_class="ability",
                mechanism=mechanism,
                criteria_notes={
                    "delivery": "ability-guaranteed (more reliable than move)",
                    "execution": "automatic on switch-in; no moveslot / priority risk",
                    "secondary_role": secondary_note,
                    "verified_secondary": str(verified_secondary),
                    "excellent_secondary": str(excellent_secondary),
                    "attribution": attr,
                    "usage_proven": "True",
                },
                claimed_traits=traits,
                reasoning=(
                    f"{mechanism} ability delivery clears Excellent bar; "
                    f"secondary kit noted but does not force-rank within tier "
                    f"({secondary_note}; excellent_secondary={excellent_secondary})."
                ),
                change_reason=None,
                reinforce_class="",
                excellence_basis="ability_delivery",
            )
        )
        admitted_ids.add(sid)

    for sid, name in sorted(pool.items(), key=lambda x: x[1]):
        if sid in admitted_ids:
            continue
        abs_map = _species_abilities(snap, sid)
        prio = priority_abilities & set(abs_map)
        if not prio:
            continue
        ls = set(resolve_learnset(snap, sid) or [])
        if move_id not in ls:
            continue
        prio_name = abs_map[next(iter(sorted(prio)))]
        move_display = _move_display(snap, move_id)
        usage_proven = uctx.delivers(name, move_id)
        if not _admit_move_delivery(
            usage_proven=usage_proven, independent_reinforce=False
        ):
            # Move mech caps at Good → discount floor still rejects (no Acceptable path).
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=(
                        f"{prio_name}+{move_display} learnset but no usage evidence "
                        f"of {move_display} delivery"
                    ),
                )
            )
            continue
        entry = uctx.entry_for(name)
        secondary_note, secondary_traits = _secondary_support_notes(
            entry, move_ids=_REDIRECTION_SECONDARY_MOVES
        )
        has_fg = bool({"friendguard"} & set(abs_map))
        has_hospitality = "hospitality" in abs_map
        secondary_move_ids = {to_id(t.name) for t in secondary_traits}
        verified_secondary = has_fg or has_hospitality or bool(secondary_traits)
        excellent_secondary = _excellent_secondary(
            has_friend_guard=has_fg, secondary_move_ids=secondary_move_ids
        )
        traits = [
            ClaimedTrait(
                name=move_display,
                criterion="delivery",
                purpose_claimed=f"set {cond} via move",
            ),
            ClaimedTrait(
                name=prio_name,
                criterion="execution",
                purpose_claimed="priority on status setup move",
            ),
            *secondary_traits,
        ]
        members.append(
            CandidateEval(
                species=name,
                species_id=sid,
                tier="Good",
                delivery_class="move_priority",
                mechanism=move_display,
                criteria_notes={
                    "delivery": "move-based (less reliable than ability)",
                    "execution": (
                        f"{prio_name}-boosted status move; blocked by Dark-types / "
                        "Good as Gold / some immunities"
                    ),
                    "secondary_role": secondary_note,
                    "verified_secondary": str(verified_secondary),
                    "excellent_secondary": str(excellent_secondary),
                    "attribution": "none",
                    "usage_proven": str(usage_proven),
                },
                claimed_traits=traits,
                reasoning=(
                    f"{prio_name} {move_display} clears Good (priority move delivery); "
                    f"below ability-guaranteed setters. Secondary: {secondary_note}."
                ),
                change_reason=None,
                reinforce_class="",
                excellence_basis="move_priority",
            )
        )
        admitted_ids.add(sid)

    _guard_pool(members, rejected, pool_ids)
    return _draft_with_tiers(
        category, sub_criteria, members, rejected, notes=notes
    )


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
    if not entry:
        return False
    if not any(_entry_has_move(entry, mid) for mid in move_ids):
        return False
    for item in entry.get("common_items") or []:
        iid = to_id(item.get("name") or "")
        try:
            pct = float(item.get("pct") or 0.0)
        except (TypeError, ValueError):
            pct = 0.0
        if pct < _MEGA_STONE_FALLBACK_PCT:
            continue
        mapped = _item_mega_forme(iid, base_sid, snap)
        if mapped == mega_sid:
            return True
    return False


def _stone_fallback_ability(
    base_name: str,
    base_sid: str,
    mega_sid: str,
    *,
    uctx: _UsageCtx,
    snap: dict[str, Any],
) -> bool:
    """Attribute weather-ability usage to Mega when base CBD shows mega-stone ≥80%."""
    entry = uctx.entry_for(base_name)
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
        mapped = _item_mega_forme(iid, base_sid, snap)
        if mapped == mega_sid:
            return True
    return False


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


def load_stat_boosts() -> dict[str, Any]:
    return json.loads(_STAT_BOOSTS_PATH.read_text())


def exclusive_self_boost_move(*, boost_stat: str, stages: int = 2) -> str:
    """Champions-legal Status/self move with boosts == {boost_stat: stages} only."""
    data = load_stat_boosts()
    want = {boost_stat: stages}
    hits = [
        mid
        for mid, ent in (data.get("moves") or {}).items()
        if ent.get("category") == "Status"
        and ent.get("target") == "self"
        and ent.get("boosts") == want
    ]
    if len(hits) != 1:
        raise ValueError(f"expected one self +{stages} {boost_stat}-only move, got {hits}")
    return hits[0]


def _setup_branch_a(
    *,
    learnset: set[str],
    abs_map: dict[str, str],
    stats: dict[str, int],
) -> bool:
    if learnset & _OFFENSIVE_PRIORITY_MOVES:
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
) -> bool:
    """True when Branch A clears only via priority (not Spe / Speed Boost)."""
    if not (learnset & _OFFENSIVE_PRIORITY_MOVES):
        return False
    return not _setup_speed_path_a(abs_map=abs_map, stats=stats)


def _setup_priority_kind(move_id: str) -> SetupPriorityKind:
    mid = to_id(move_id)
    if mid in _SETUP_CONDITIONAL_PRIORITY:
        return "conditional"
    if mid in _OFFENSIVE_PRIORITY_MOVES:
        return "unconditional"
    return "none"


def _setup_priority_mult(kind: SetupPriorityKind) -> float:
    if kind == "unconditional":
        return _SETUP_PRIORITY_SCORE_MULT
    if kind == "conditional":
        return _SETUP_CONDITIONAL_PRIORITY_MULT
    return 1.0


def _setup_turn_order_weight(
    move_id: str,
    atk_spe: int,
    def_spe: int,
    ability: str | None,
) -> float:
    """Credit weight for a panel-member damage frac under turn order.

    Missing Spe → fail open (1.0). Priority payoff acts first. Disguise/Ice Face
    absorbs the first hit when outsped. Speed Boost assumes +1 Spe after setup.
    """
    if atk_spe <= 0 or def_spe <= 0:
        return 1.0
    mid = to_id(move_id)
    if mid in _OFFENSIVE_PRIORITY_MOVES:
        return 1.0
    aid = to_id(ability) if ability else ""
    if aid in _SETUP_SURVIVE_ABILITIES:
        return 1.0
    effective = int(atk_spe * 1.5) if aid in _SETUP_SPEED_ABILITIES else atk_spe
    if effective > def_spe:
        return 1.0
    if effective == def_spe:
        return 0.5
    return 0.0


def _setup_adjusted_score(
    raw: float,
    *,
    priority_kind: SetupPriorityKind,
    both_branches: bool,
) -> float:
    adjusted = raw * _setup_priority_mult(priority_kind)
    if both_branches:
        adjusted /= _SETUP_BOTH_BRANCH_SCORE_DIV
    return adjusted


def _setup_excellent_floor(adjusted_scores: list[float]) -> float:
    """Per-category floor: 2nd-highest adjusted × 0.95 (sole member → that × 0.95)."""
    if not adjusted_scores:
        return 0.0
    ranked = sorted(adjusted_scores, reverse=True)
    anchor = ranked[1] if len(ranked) >= 2 else ranked[0]
    return anchor * _SETUP_FLOOR_SECOND_MULT


def _setup_mech_tier(adjusted: float, floor: float) -> str:
    """Excellent ≥ floor; Acceptable below floor × mult; Good between."""
    if floor <= 0:
        return "Good"
    if adjusted >= floor:
        return "Excellent"
    if adjusted < floor * _SETUP_ACCEPTABLE_FLOOR_MULT:
        return "Acceptable"
    return "Good"


def _setup_self_drop_moves(boost_stat: str) -> frozenset[str]:
    if boost_stat == "spa":
        return _SETUP_SELF_DROP_SPA
    if boost_stat == "atk":
        return _SETUP_SELF_DROP_ATK
    return frozenset()


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
) -> list[str]:
    cleared: list[str] = []
    if _setup_branch_a(learnset=learnset, abs_map=abs_map, stats=stats):
        cleared.append("A")
    if (set(abs_map) & _SETUP_SURVIVE_ABILITIES) or (
        _setup_bulk_ok(stats) and _setup_sustain_ok(learnset=learnset, entry=entry)
    ):
        cleared.append("B")
    return cleared


def _minimal_threat_state(regulation: str = "champions") -> RecommenderState:
    # get_relevant_threats only reads regulation_mod at runtime.
    return cast(
        RecommenderState,
        {
            "format_id": "",
            "game_type": "doubles",
            "regulation_mod": regulation,
            "picked_team_size": 4,
            "available_pool": [],
            "team_draft": [],
            "archetype": [],
            "rejected": [],
            "constraints": [],
            "messages": [],
        },
    )


def _setup_threat_defenders(
    n: int = _SETUP_THREAT_PANEL_N,
    *,
    regulation: str = "champions",
) -> list[dict[str, Any]]:
    """Usage-informed panel: species + common item/ability/evs from threat expand."""
    threats = get_relevant_threats(_minimal_threat_state(regulation), n=n)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for cand in threats:
        spec = dict(cand.spec)
        species = str(spec.get("species") or "")
        if not species:
            continue
        sid = to_id(species)
        if sid in seen:
            continue
        seen.add(sid)
        if not spec.get("item") or not spec.get("ability") or not spec.get("evs"):
            filled = featured_or_common_set(species, regulation=regulation)
            if filled:
                if not spec.get("item") and filled.get("item"):
                    spec["item"] = filled["item"]
                if not spec.get("ability") and filled.get("ability"):
                    spec["ability"] = filled["ability"]
                if not spec.get("evs") and filled.get("evs"):
                    spec["evs"] = dict(filled["evs"])
        defender: dict[str, Any] = {
            "species": species,
            "evs": spec.get("evs")
            or {"hp": 32, "atk": 0, "def": 32, "spa": 0, "spd": 32, "spe": 0},
        }
        if spec.get("item"):
            defender["item"] = spec["item"]
        if spec.get("ability"):
            defender["ability"] = spec["ability"]
        out.append(defender)
        if len(out) >= n:
            break
    return out


def _threat_panel_label(panel: list[dict[str, Any]]) -> str:
    return ", ".join(
        f"{d.get('species')}/{d.get('item') or 'no-item'}" for d in panel
    )


def _species_types(snap: dict[str, Any], sid: str) -> set[str]:
    entry = snap.get("species", {}).get(sid) or {}
    return {str(t).lower() for t in (entry.get("types") or [])}


def _best_payoff_move(
    snap: dict[str, Any],
    sid: str,
    learnset: set[str],
    *,
    boost_stat: str,
    usage_moves: list[str] | None = None,
    usage_only: bool = False,
) -> str | None:
    """Best damaging move matching Physical(atk)/Special(spa), prefer STAB then BP.

    When usage_only, only consider usage_moves (must be non-empty). Always skips
    banned delayed/recharge/self-drop payoffs.
    """
    want_cat = "Physical" if boost_stat == "atk" else "Special"
    types = _species_types(snap, sid)
    moves_map = snap.get("moves") or {}
    banned = _setup_banned_payoffs(boost_stat)
    if usage_only:
        candidates = list(usage_moves or [])
    else:
        candidates = list(usage_moves or []) + sorted(learnset)
    best: tuple[int, int, str] | None = None  # (stab, bp, mid)
    seen: set[str] = set()
    for raw in candidates:
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
        mtype = str(ment.get("type") or "").lower()
        stab = 1 if mtype in types else 0
        key = (stab, bp, mid)
        if best is None or key[:2] > best[:2]:
            best = key
    return best[2] if best else None


def _select_setup_payoff(
    *,
    snap: dict[str, Any],
    sid: str,
    calc_name: str,
    item: str | None,
    ability: str | None,
    boost_stat: str,
    stages: int,
    usage_move_ids: set[str],
    panel: list[dict[str, Any]],
    calculate_batch: CalculateBatch,
) -> tuple[str | None, float, str, SetupPriorityKind]:
    """Pick usage payoff with highest adjusted score (priority mult when payoff is priority).

    Returns (payoff_id, raw_score, calc_error, priority_kind).
    """
    candidates = _setup_payoff_candidates(
        snap, boost_stat=boost_stat, usage_move_ids=usage_move_ids
    )
    if not candidates:
        return None, 0.0, "no_usage_payoff", "none"
    types = _species_types(snap, sid)
    moves_map = snap.get("moves") or {}
    best: tuple[float, float, str, str, SetupPriorityKind] | None = None
    # (adjusted_without_both, raw, mid, err, priority_kind)
    for mid in candidates:
        move_disp = str(moves_map.get(mid, {}).get("name") or mid)
        ability_for = _setup_ability_for_payoff(
            ability, mid, snap=snap, types=types
        )
        raw, err = _damage_score(
            attacker_name=calc_name,
            item=item,
            ability=ability,  # ungated: Disguise / Speed Boost for turn-order
            calc_ability=ability_for,
            move=move_disp,
            move_id=mid,
            boost_stat=boost_stat,
            stages=stages,
            panel=panel,
            calculate_batch=calculate_batch,
        )
        kind = _setup_priority_kind(mid)
        adj = _setup_adjusted_score(raw, priority_kind=kind, both_branches=False)
        key = (adj, raw, mid, err, kind)
        if best is None or (adj, raw) > (best[0], best[1]):
            best = key
    assert best is not None
    return best[2], best[1], best[3], best[4]


def _calc_species_name(sid: str, name: str, snap: dict[str, Any]) -> str:
    if sid in {"aegislash", "aegislashblade", "aegislashshield"}:
        return "Aegislash-Blade"
    return name


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
        item = built.get("item")
        ability = built.get("ability")
        return calc_name, item, ability, moves
    usage_moves = [str(m.get("name") or "") for m in (entry or {}).get("common_moves") or []]
    payoff = _best_payoff_move(
        snap, sid, learnset, boost_stat=boost_stat, usage_moves=usage_moves
    )
    abs_map = _species_abilities(snap, sid)
    ability = next(iter(abs_map.values()), None) if abs_map else None
    item = None
    for it in (entry or {}).get("common_items") or []:
        item = str(it.get("name") or "") or None
        break
    moves = [payoff] if payoff else []
    return calc_name, item, ability, moves


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
) -> tuple[float, str]:
    """Mean turn-order-weighted damage/HP vs panel (soft-capped).

    `ability` is the ungated kit ability (Disguise / Speed Boost for turn-order).
    `calc_ability` is the payoff-gated ability passed to the calc (defaults to ability).
    """
    if not move or not panel:
        return 0.0, "empty_panel_or_move"
    mid = to_id(move_id or move)
    calc_ab = calc_ability if calc_ability is not None else ability
    boosts = {boost_stat: stages}
    attacker: dict[str, Any] = {
        "species": attacker_name,
        "evs": {"hp": 4, "atk": 32, "def": 0, "spa": 32, "spd": 0, "spe": 32},
        "boosts": boosts,
        "moves": [move],
    }
    if item:
        attacker["item"] = item
    if calc_ab:
        attacker["ability"] = calc_ab
    reqs = [
        {
            "attacker": attacker,
            "defender": dict(defn),
            "move": move,
            "field": {"gameType": "Doubles"},
        }
        for defn in panel
    ]
    try:
        results = calculate_batch(reqs)
    except Exception as e:  # noqa: BLE001 — construction continues with zero score
        return 0.0, f"batch_exception:{type(e).__name__}:{e}"
    fracs: list[float] = []
    errors: list[str] = []
    for i, r in enumerate(results):
        dname = str(panel[i].get("species") or i) if i < len(panel) else str(i)
        if not isinstance(r, dict):
            errors.append(f"{dname}:non_dict")
            continue
        if "error" in r:
            errors.append(f"{dname}:{r.get('error')}")
            continue
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
            errors.append(f"{dname}:bad_range")
            continue
        if hp_f <= 0:
            errors.append(f"{dname}:no_hp")
            continue
        if dmg_f <= 0:
            errors.append(f"{dname}:zero_damage")
            continue
        capped = min(dmg_f / hp_f, _SETUP_DAMAGE_FRAC_CAP)
        weight = _setup_turn_order_weight(mid, atk_spe, def_spe, ability)
        fracs.append(weight * capped)
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
    panel = _setup_threat_defenders()
    notes.append(
        "threat_panel=usage_informed "
        f"({_threat_panel_label(panel)})"
    )

    # Learners.
    eligible: dict[str, str] = {}
    for sid, name in pool.items():
        ls = set(resolve_learnset(snap, sid) or [])
        if move_id not in ls:
            continue
        eligible[sid] = name

    # Showdown discount among eligible mega pairs (Acceptable path).
    skip_discount: set[str] = set()
    pair_attr: dict[str, str] = {}
    sd_cache: dict[str, dict[str, Any] | None] = {}
    seen_pairs: set[tuple[str, str]] = set()
    for sid in eligible:
        pair = _mega_pair_ids(sid, snap, set(eligible))
        if not pair or pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        base_sid, mega_sid = pair
        base_name, mega_name = eligible[base_sid], eligible[mega_sid]
        base_sd = _showdown_entry(base_name, cache=sd_cache, showdown_fetch=showdown_fetch)
        mega_sd = _showdown_entry(mega_name, cache=sd_cache, showdown_fetch=showdown_fetch)
        if mega_sd is None:
            continue
        mega_pct = float(mega_sd.get("usage_pct") or 0.0)
        base_pct = float((base_sd or {}).get("usage_pct") or 0.0) if base_sd else 0.0
        if mega_pct > base_pct and base_pct < _SHOWDOWN_BASE_USAGE_RATIO * mega_pct:
            skip_discount.add(base_sid)
            pair_attr[base_sid] = (
                f"showdown usage discounted "
                f"(base {base_pct:.3f}% < {_SHOWDOWN_BASE_USAGE_RATIO}× "
                f"mega {mega_pct:.3f}%)"
            )
            notes.append(
                f"Showdown attribution ({base_name}/{mega_name}): base discounted"
            )

    # Pass 1: evaluate admitted candidates (no Excellent yet).
    provisional: list[dict[str, Any]] = []
    for sid, name in sorted(eligible.items(), key=lambda kv: kv[1]):
        learnset = set(resolve_learnset(snap, sid) or [])
        abs_map = _species_abilities(snap, sid)
        stats = _base_stats(snap, sid)
        entry = uctx.entry_for(name)
        branches = _setup_branches(
            learnset=learnset, abs_map=abs_map, stats=stats, entry=entry
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
        if not usage_proven:
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=f"learnset has {move_id} but no usage evidence of the setup move",
                    change_reason=None,
                )
            )
            continue

        calc_name, item, ability, kit_moves = _attacker_kit(
            name, sid, snap, learnset, boost_stat=boost_stat, entry=entry
        )
        usage_ids = _usage_payoff_move_ids(entry, kit_moves)
        payoff_id, raw_score, calc_err, priority_kind = _select_setup_payoff(
            snap=snap,
            sid=sid,
            calc_name=calc_name,
            item=item,
            ability=ability,
            boost_stat=boost_stat,
            stages=stages,
            usage_move_ids=usage_ids,
            panel=panel,
            calculate_batch=calculate_batch,
        )
        if not payoff_id:
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=(
                        "no usage-proven same-turn damaging payoff "
                        "(excluded recharge/charge/Focus Punch/Future Sight/self-drop)"
                    ),
                    change_reason=(
                        f"setup calc/membership re-eval / tier {prior.get(sid)!r} → rejected"
                        if prior.get(sid)
                        else None
                    ),
                )
            )
            continue
        move_disp = str(
            (snap.get("moves") or {}).get(payoff_id, {}).get("name") or payoff_id
        )

        both = set(branches) >= {"A", "B"}
        adjusted = _setup_adjusted_score(
            raw_score, priority_kind=priority_kind, both_branches=both
        )
        boosts: list[str] = []
        if priority_kind != "none":
            boosts.append(f"priority_x{_setup_priority_mult(priority_kind):g}")
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
                "move_disp": move_disp,
                "branch_note": branch_note,
                "branch_basis": branch_basis,
                "excellent_secondary": excellent_secondary,
                "sec_ability": sec_ability,
            }
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
        f"Acceptable floor = Excellent floor × {_SETUP_ACCEPTABLE_FLOOR_MULT:g} "
        f"→ {floor * _SETUP_ACCEPTABLE_FLOOR_MULT:.3f}"
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
        move_disp = p["move_disp"]
        calc_name = p["calc_name"]
        calc_err = p["calc_err"]
        boosts = p["boosts"]

        mech_tier = _setup_mech_tier(adjusted, floor)
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
            ClaimedTrait(
                name=move_disp,
                criterion="execution",
                purpose_claimed=(
                    f"calc damage fraction {adjusted:.3f} vs panel; branches={branch_note}"
                ),
            ),
        ]
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
                    "payoff_move": move_disp,
                    "calc_species": calc_name,
                    "damage_score_raw": f"{raw_score:.3f}",
                    "damage_score": f"{adjusted:.3f}",
                    "score_boosts": "+".join(boosts) if boosts else "none",
                    **({"calc_error": calc_err} if calc_err else {}),
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

    return _draft_with_tiers(
        category, sub_criteria, members, rejected, notes=notes
    )


def _construct_redirection(
    category: str,
    sub_criteria: dict[str, Any],
    legal_pool: list[str],
    *,
    snap: dict[str, Any],
    uctx: _UsageCtx,
    showdown_fetch: LiveFetch | None,
    reference_compendium: dict[str, Any] | RoleConstructionDraft | None,
) -> RoleConstructionDraft:
    move_ids = frozenset(to_id(m) for m in sub_criteria["move_ids"])
    ally_ids = frozenset(to_id(a) for a in sub_criteria.get("ally_reinforce_abilities") or [])
    pool = _pool_index(legal_pool, snap)
    pool_ids = set(pool)
    prior = _ref_members(reference_compendium)
    members: list[CandidateEval] = []
    rejected: list[RejectedCandidate] = []
    notes = [
        "no ability-based redirection delivery in Champions-legal data "
        "(Follow Me / Rage Powder are move-only)"
    ]
    sd_cache: dict[str, dict[str, Any] | None] = {}

    # Eligible redirectors (learnset ∩ moves), excluding Magic Bounce abandon.
    eligible: dict[str, str] = {}
    for sid, name in pool.items():
        ls = set(resolve_learnset(snap, sid) or [])
        if not (move_ids & ls):
            continue
        abs_map = _species_abilities(snap, sid)
        if set(abs_map) == {"magicbounce"}:
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=(
                        "Mega kit abandons redirection (Magic Bounce only); "
                        "redirect learnset inherited from base"
                    ),
                    change_reason=(
                        "phase2 mega abandon"
                        if prior.get(sid)
                        else None
                    ),
                )
            )
            continue
        eligible[sid] = name

    # Showdown attribution for base/Mega pairs both in the eligible pool.
    pair_usage, pair_notes, _stone_used = _mega_usage_attribution(
        eligible,
        move_ids,
        snap=snap,
        uctx=uctx,
        sd_cache=sd_cache,
        showdown_fetch=showdown_fetch,
        notes=notes,
    )

    for sid, name in sorted(eligible.items(), key=lambda x: x[1]):
        ls = set(resolve_learnset(snap, sid) or [])
        hits = sorted(move_ids & ls)
        abs_map = _species_abilities(snap, sid)
        mechanisms = [_move_display(snap, mid) for mid in hits]
        mechanism = " / ".join(mechanisms)

        entry = uctx.entry_for(name)
        qd_pct = max(
            (_move_pct(entry, mid) for mid in _COMPETING_IDENTITY_MOVES),
            default=0.0,
        )
        best_redir = max((_move_pct(entry, mid) for mid in hits), default=0.0)
        identity_conflict = bool(entry is not None and qd_pct > best_redir > 0)

        if sid in pair_usage:
            usage_proven = pair_usage[sid]
        else:
            usage_proven = any(uctx.delivers(name, mid) for mid in hits)

        has_fg = bool(ally_ids & set(abs_map))
        has_hospitality = "hospitality" in abs_map
        secondary_note, secondary_traits = _secondary_support_notes(
            entry, move_ids=_REDIRECTION_SECONDARY_MOVES
        )
        secondary_move_ids = {to_id(t.name) for t in secondary_traits}
        secondary_move_hit = bool(secondary_traits)
        verified_secondary = has_fg or has_hospitality or secondary_move_hit
        excellent_secondary = _excellent_secondary(
            has_friend_guard=has_fg, secondary_move_ids=secondary_move_ids
        )
        exec_abilities = execution_reinforce_abilities(abs_map)
        execution_ok = bool(exec_abilities)
        independent_reinforce = execution_ok or verified_secondary

        if not _admit_move_delivery(
            usage_proven=usage_proven, independent_reinforce=independent_reinforce
        ):
            attr = pair_notes.get(sid, "")
            discounted = (
                "discounted" in attr
                or "stone-heuristic" in attr
                or "attributed to Mega" in attr
                or "mega-stone fallback" in attr
            )
            # Mech Excellent ignoring usage: FG / excellent_secondary, no identity conflict.
            mech_tier = (
                "Excellent"
                if (has_fg or excellent_secondary) and not identity_conflict
                else "Good"
            )
            demoted = _discount_outcome(mech_tier) if discounted else None
            if demoted == "Acceptable":
                reinforce = "ally_mitigation" if has_fg else "none"
                members.append(
                    CandidateEval(
                        species=name,
                        species_id=sid,
                        tier="Acceptable",
                        delivery_class="move_redirect",
                        mechanism=mechanism,
                        criteria_notes={
                            "delivery": (
                                "move-based Follow Me / Rage Powder "
                                "(same reliability class)"
                            ),
                            "execution": (
                                f"Champions priority +{move_priority(hits[0])}; "
                                "usage discounted vs Mega form"
                            ),
                            "secondary_role": secondary_note,
                            "usage_proven": "False",
                            "verified_secondary": str(verified_secondary),
                            "excellent_secondary": str(excellent_secondary),
                            "reinforce_class": reinforce,
                            "qd_pct": str(qd_pct),
                            "best_redirect_pct": str(best_redir),
                            "identity_conflict": str(identity_conflict),
                            "attribution": attr or "none",
                        },
                        claimed_traits=[
                            ClaimedTrait(
                                name=mechanism,
                                criterion="delivery",
                                purpose_claimed=(
                                    "redirect attacks onto self to protect ally"
                                ),
                            ),
                            ClaimedTrait(
                                name=mechanism,
                                criterion="execution",
                                purpose_claimed=(
                                    f"Champions priority +{move_priority(hits[0])} "
                                    "status redirect"
                                ),
                            ),
                            *secondary_traits,
                        ],
                        reasoning=(
                            f"{mechanism} clears Acceptable "
                            f"(mech Excellent, Showdown usage discounted)."
                        ),
                        change_reason=(
                            f"usage discount demote / mech Excellent → Acceptable "
                            f"({attr})"
                        ),
                        reinforce_class=reinforce,
                        excellence_basis="usage_discounted",
                    )
                )
                continue
            prev = prior.get(sid)
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=(
                        f"{mechanism} learnset but no usage evidence of redirect "
                        "delivery and no independent reinforce "
                        "(hit-triggered opponent disrupt / Friend Guard / "
                        "Hospitality / closed secondary)"
                    ),
                    change_reason=(
                        "phase1+reject: learnset-only without usage/reinforce"
                        if prev
                        else None
                    ),
                )
            )
            continue

        reinforce = "ally_mitigation" if has_fg else "none"
        if identity_conflict:
            tier = "Good"
            if has_fg:
                basis = "ally_mitigation_conflicted"
            elif usage_proven and excellent_secondary:
                basis = "secondary_stack_conflicted"
            elif usage_proven:
                basis = "usage_proven_conflicted"
            else:
                basis = "reinforce_only_conflicted"
        elif usage_proven and excellent_secondary:
            tier = "Excellent"
            basis = "ally_mitigation" if has_fg else "secondary_stack"
        else:
            # usage without excellent secondary, or reinforce without usage
            tier = "Good"
            if usage_proven:
                basis = "usage_proven"
            elif has_fg:
                basis = "ally_mitigation"
            elif execution_ok:
                basis = "execution_reinforce"
            else:
                basis = "secondary_reinforce"

        stats = _base_stats(snap, sid)
        prio = move_priority(hits[0])
        hospitality = abs_map.get("hospitality")
        exec_note = (
            f"Champions priority +{prio}; bulk HP/Def/SpD="
            f"{stats.get('hp')}/{stats.get('def')}/{stats.get('spd')}"
        )
        if identity_conflict:
            exec_note += (
                f"; identity conflict Quiver Dance {qd_pct:.1f}% > "
                f"redirect {best_redir:.1f}% (Excellent capped)"
            )

        traits: list[ClaimedTrait] = [
            ClaimedTrait(
                name=mechanism,
                criterion="delivery",
                purpose_claimed="redirect attacks onto self to protect ally",
            ),
            ClaimedTrait(
                name=mechanism,
                criterion="execution",
                purpose_claimed=f"Champions priority +{prio} status redirect",
            ),
        ]
        if exec_abilities:
            for _aid, display, desc in exec_abilities:
                traits.append(
                    ClaimedTrait(
                        name=display,
                        criterion="execution",
                        purpose_claimed=(
                            "hit-triggered opponent disrupt while drawing fire "
                            "— execution reinforce for redirector "
                            "(not ally mitigation)"
                        ),
                    )
                )
                snippet = desc if len(desc) <= 120 else desc[:117] + "..."
                exec_note += f"; {display} ({snippet})"
        if has_fg:
            traits.append(
                ClaimedTrait(
                    name=abs_map[next(iter(sorted(ally_ids & set(abs_map))))],
                    criterion="secondary_role",
                    purpose_claimed="ally damage mitigation while redirecting",
                )
            )
        if has_hospitality and hospitality:
            traits.append(
                ClaimedTrait(
                    name=hospitality,
                    criterion="secondary_role",
                    purpose_claimed="ally heal on switch-in (secondary stack, not mitigate)",
                )
            )
        traits.extend(secondary_traits)
        hosp_note = ""
        if hospitality:
            hosp_note = (
                f"; {hospitality} heals ally on switch-in (other-directed, "
                "not damage mitigation during redirect)"
            )

        attr_note = pair_notes.get(sid, "")
        change_reason = None
        prev_tier = prior.get(sid)
        if prev_tier and prev_tier != tier and sid in pair_usage:
            change_reason = (
                f"phase2 showdown attribution / tier {prev_tier!r} → {tier!r}"
                + (f" ({attr_note})" if attr_note else "")
            )
        elif prev_tier == "Excellent" and tier != "Excellent":
            # Intentional demote (excellent_secondary axes / identity conflict).
            change_reason = (
                f"excellent_secondary axes / identity conflict / "
                f"tier Excellent → {tier!r}"
            )

        members.append(
            CandidateEval(
                species=name,
                species_id=sid,
                tier=tier,
                delivery_class="move_redirect",
                mechanism=mechanism,
                criteria_notes={
                    "delivery": "move-based Follow Me / Rage Powder (same reliability class)",
                    "execution": exec_note,
                    "secondary_role": secondary_note + hosp_note,
                    "usage_proven": str(usage_proven),
                    "verified_secondary": str(verified_secondary),
                    "excellent_secondary": str(excellent_secondary),
                    "reinforce_class": reinforce,
                    "qd_pct": str(qd_pct),
                    "best_redirect_pct": str(best_redir),
                    "identity_conflict": str(identity_conflict),
                    "attribution": attr_note or "none",
                },
                claimed_traits=traits,
                reasoning=(
                    f"{mechanism} clears {tier} "
                    f"(basis={basis}, reinforce={reinforce}, usage_proven={usage_proven}"
                    f", verified_secondary={verified_secondary}"
                    f", excellent_secondary={excellent_secondary}"
                    + (f" / {attr_note}" if attr_note else "")
                    + (" / identity_conflict" if identity_conflict else "")
                    + ")."
                ),
                change_reason=change_reason,
                reinforce_class=reinforce,
                excellence_basis=basis,
            )
        )

    _guard_pool(members, rejected, pool_ids)
    return _draft_with_tiers(category, sub_criteria, members, rejected, notes=notes)


def _protection_note(abs_map: dict[str, str], aids: set[str]) -> str:
    parts = []
    for aid in sorted(aids):
        entry = get_ability(aid) or {}
        display = str(abs_map.get(aid) or entry.get("name") or aid)
        desc = str(entry.get("description") or "")
        snippet = desc if len(desc) <= 120 else desc[:117] + "..."
        parts.append(f"{display} ({snippet})" if snippet else display)
    return "; ".join(parts)


def _construct_trick_room_setter(
    category: str,
    sub_criteria: dict[str, Any],
    legal_pool: list[str],
    *,
    snap: dict[str, Any],
    uctx: _UsageCtx,
    showdown_fetch: LiveFetch | None,
    reference_compendium: dict[str, Any] | RoleConstructionDraft | None,
) -> RoleConstructionDraft:
    move_ids = frozenset(to_id(m) for m in sub_criteria["move_ids"])
    pool = _pool_index(legal_pool, snap)
    pool_ids = set(pool)
    prior = _ref_members(reference_compendium)
    members: list[CandidateEval] = []
    rejected: list[RejectedCandidate] = []
    notes = [
        "delivery does not differentiate: Trick Room is move-only "
        f"(no ability sets it) and its priority is fixed at "
        f"{move_priority('trickroom')}, so every candidate resolves last "
        "regardless of how it accesses the move",
        "usage evidence prefers Champions in-game data where a row exists; "
        "Showdown is a fallback only for formes with no Champions row",
        "unproven usage costs two tiers (Excellent → Acceptable, Good → out), "
        "matching the Showdown-discount demotion rule",
        f"membership requires bulk (HP+Def+SpD) ≥ {_TRICK_ROOM_BULK_FLOOR}, "
        "waived for one-hit absorption (Disguise / Ice Face)",
        "tiers grade self-provided cover of the shared Fake Out / Taunt "
        "exposure: ability flinch denial > Ghost Fake Out immunity or Taunt "
        "immunity > none",
    ]
    sd_cache: dict[str, dict[str, Any] | None] = {}

    eligible = {
        sid: name
        for sid, name in pool.items()
        if move_ids & set(resolve_learnset(snap, sid) or [])
    }

    pair_usage, pair_notes, _stone_used = _mega_usage_attribution(
        eligible,
        move_ids,
        snap=snap,
        uctx=uctx,
        sd_cache=sd_cache,
        showdown_fetch=showdown_fetch,
        notes=notes,
    )

    flinch_ids = flinch_denial_ability_ids()
    taunt_ids = taunt_denial_ability_ids()

    for sid, name in sorted(eligible.items(), key=lambda x: x[1]):
        hits = sorted(move_ids & set(resolve_learnset(snap, sid) or []))
        abs_map = _species_abilities(snap, sid)
        stats = _base_stats(snap, sid)
        mechanism = " / ".join(_move_display(snap, mid) for mid in hits)
        entry = uctx.entry_for(name)

        # Membership floor, not a ranking axis. One-hit absorption substitutes
        # for raw bulk: it buys the same thing, a guaranteed turn to cast.
        bulk = sum(int(stats.get(k) or 0) for k in ("hp", "def", "spd"))
        absorb = set(abs_map) & _SETUP_SURVIVE_ABILITIES
        if bulk < _TRICK_ROOM_BULK_FLOOR and not absorb:
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=(
                        f"bulk {bulk} below the {_TRICK_ROOM_BULK_FLOOR} membership "
                        "floor; moving last means it must survive to cast"
                    ),
                    change_reason=(
                        f"bulk floor {_TRICK_ROOM_BULK_FLOOR} membership requirement"
                        if prior.get(sid)
                        else None
                    ),
                )
            )
            continue

        # Usage precedence: a negative Mega attribution sticks (it decides which
        # form owns the usage), then Champions data where a row exists, then
        # ladder data. Showdown prevalence tracks the ladder, not this format:
        # species common in Champions and rare on the ladder would otherwise be
        # judged on the wrong population.
        champ = uctx.champions_entry(name)
        if pair_usage.get(sid) is False:
            usage_proven = False
            usage_source = "mega attribution"
        elif champ is not None:
            usage_proven = any(_entry_has_move(champ, mid) for mid in hits)
            usage_source = "champions"
        elif sid in pair_usage:
            usage_proven = pair_usage[sid]
            usage_source = "showdown (no Champions row)"
        else:
            usage_proven = any(uctx.delivers(name, mid) for mid in hits)
            usage_source = "usage fallback (no Champions row)"

        flinch = set(abs_map) & flinch_ids
        taunt = set(abs_map) & taunt_ids
        ghost = _FAKE_OUT_IMMUNE_TYPE in _species_types(snap, sid)
        self_protected = bool(flinch or taunt or ghost)

        secondary_note, secondary_traits = _secondary_support_notes(
            entry, move_ids=_TRICK_ROOM_SECONDARY_MOVES
        )
        secondary_move_ids = {to_id(t.name) for t in secondary_traits}
        verified_secondary = bool(secondary_traits)
        excellent_secondary = _excellent_secondary(
            has_friend_guard=False,
            secondary_move_ids=secondary_move_ids,
            excellent_move_ids=_TRICK_ROOM_EXCELLENT_SECONDARY_MOVES,
        )

        # Self-protection is the only independent reinforce: a secondary role
        # does not make a species a Trick Room setter.
        if not _admit_move_delivery(
            usage_proven=usage_proven, independent_reinforce=self_protected
        ):
            attr = pair_notes.get(sid, "")
            discounted = (
                "discounted" in attr
                or "stone-heuristic" in attr
                or "attributed to Mega" in attr
                or "mega-stone fallback" in attr
            )
            mech_tier = "Excellent" if excellent_secondary else "Good"
            if discounted and _discount_outcome(mech_tier) == "Acceptable":
                members.append(
                    CandidateEval(
                        species=name,
                        species_id=sid,
                        tier="Acceptable",
                        delivery_class="move_trick_room",
                        mechanism=mechanism,
                        criteria_notes={
                            "delivery": _TRICK_ROOM_DELIVERY_NOTE,
                            "execution": (
                                f"bulk HP/Def/SpD={stats.get('hp')}/"
                                f"{stats.get('def')}/{stats.get('spd')}; "
                                "no self-provided Fake Out / Taunt protection; "
                                "usage discounted vs Mega form"
                            ),
                            "secondary_role": secondary_note,
                            "usage_proven": "False",
                            "verified_secondary": str(verified_secondary),
                            "excellent_secondary": str(excellent_secondary),
                            "reinforce_class": "none",
                            "self_protection": "none",
                            "attribution": attr or "none",
                        },
                        claimed_traits=[
                            ClaimedTrait(
                                name=mechanism,
                                criterion="delivery",
                                purpose_claimed="invert turn order for the side",
                            ),
                            *secondary_traits,
                        ],
                        reasoning=(
                            f"{mechanism} clears Acceptable "
                            "(mech Excellent, Showdown usage discounted)."
                        ),
                        change_reason=(
                            f"usage discount demote / mech Excellent → Acceptable ({attr})"
                        ),
                        reinforce_class="none",
                        excellence_basis="usage_discounted",
                    )
                )
                continue
            reason = (
                f"{mechanism} learnset but no usage evidence of Trick Room "
                "delivery and no self-provided Fake Out / Taunt protection"
            )
            if discounted:
                reason += f" ({attr})"
            elif usage_source == "champions":
                reason += " (Champions usage data shows no Trick Room on this species)"
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=reason,
                    change_reason=(
                        "learnset-only without usage/self-protection"
                        if prior.get(sid)
                        else None
                    ),
                )
            )
            continue

        # Graded protection: denying the flinch (outright priority denial or
        # flinch immunity) removes the Fake Out lockout entirely; Taunt immunity
        # only covers the slower half of the shared exposure.
        # Graded on how much of the shared Fake Out / Taunt exposure the
        # candidate covers by itself. Ability-based flinch denial is broadest
        # (all priority, or all flinch sources); Ghost typing and Taunt immunity
        # each cover one half; no self-provided cover is the baseline.
        if flinch:
            tier, basis = "Excellent", "flinch_denial"
        elif ghost:
            tier, basis = "Good", "ghost_fakeout_immunity"
        elif taunt:
            tier, basis = "Good", "taunt_denial"
        else:
            tier, basis = "Acceptable", "unprotected"
        reinforce = "self_protection" if self_protected else "none"

        # Two-tier demotion for unproven usage, the same rule the Showdown
        # discount applies: self-protection is a real execution strength but it
        # is not evidence the species is actually played in this role. Two tiers
        # below Good is below Acceptable, so those candidates leave the field.
        if not usage_proven:
            if tier != "Excellent":
                attr = pair_notes.get(sid, "")
                rejected.append(
                    RejectedCandidate(
                        species=name,
                        species_id=sid,
                        reason=(
                            f"{mechanism} learnset but no usage evidence of Trick Room "
                            f"delivery; two-tier demotion from {tier} falls below "
                            "Acceptable"
                            + (f" ({attr})" if attr else "")
                        ),
                        change_reason=(
                            f"unproven-usage two-tier demotion from {prior[sid]!r}"
                            if prior.get(sid)
                            else None
                        ),
                    )
                )
                continue
            tier, basis = "Acceptable", f"acceptable_{basis}"

        exec_note = (
            f"bulk HP/Def/SpD={stats.get('hp')}/{stats.get('def')}/{stats.get('spd')}"
        )
        traits: list[ClaimedTrait] = [
            ClaimedTrait(
                name=mechanism,
                criterion="delivery",
                purpose_claimed="invert turn order for the side",
            )
        ]
        if flinch:
            note = _protection_note(abs_map, flinch)
            exec_note += f"; self-provided flinch denial — {note}"
            traits.append(
                ClaimedTrait(
                    name=note.split(" (")[0],
                    criterion="execution",
                    purpose_claimed=(
                        "self-provided flinch denial; no teammate dependency "
                        "for the cast"
                    ),
                )
            )
        if ghost:
            exec_note += (
                "; Ghost typing is immune to Normal, so Fake Out cannot land "
                "(narrower than Armor Tail / Inner Focus: no cover vs other "
                "flinch sources)"
            )
            traits.append(
                ClaimedTrait(
                    name="Ghost typing",
                    criterion="execution",
                    purpose_claimed=(
                        "self-provided Fake Out immunity; no teammate dependency "
                        "for the cast"
                    ),
                )
            )
        if taunt:
            note = _protection_note(abs_map, taunt)
            exec_note += f"; self-provided Taunt immunity — {note}"
            traits.append(
                ClaimedTrait(
                    name=note.split(" (")[0],
                    criterion="execution",
                    purpose_claimed=(
                        "self-provided Taunt immunity; no teammate dependency "
                        "for the cast"
                    ),
                )
            )
        if absorb:
            exec_note += (
                f"; {'/'.join(sorted(abs_map[a] for a in absorb))} absorbs one hit "
                "outright, substituting for raw bulk"
            )
        if not self_protected:
            exec_note += (
                "; no self-provided protection — depends on a teammate to cover "
                "Fake Out / Taunt"
            )
        if not usage_proven:
            exec_note += "; usage unproven — two-tier demotion applied"
        traits.extend(secondary_traits)

        attr_note = pair_notes.get(sid, "")
        prev_tier = prior.get(sid)
        change_reason = None
        if prev_tier and prev_tier != tier:
            change_reason = f"tier {prev_tier!r} → {tier!r}" + (
                f" ({attr_note})" if attr_note else ""
            )

        members.append(
            CandidateEval(
                species=name,
                species_id=sid,
                tier=tier,
                delivery_class="move_trick_room",
                mechanism=mechanism,
                criteria_notes={
                    "delivery": _TRICK_ROOM_DELIVERY_NOTE,
                    "execution": exec_note,
                    "secondary_role": secondary_note,
                    "usage_proven": str(usage_proven),
                    "usage_source": usage_source,
                    "verified_secondary": str(verified_secondary),
                    "excellent_secondary": str(excellent_secondary),
                    "reinforce_class": reinforce,
                    "self_protection": "+".join(
                        p
                        for p, on in (
                            ("flinch_denial", bool(flinch)),
                            ("ghost_fakeout_immunity", ghost),
                            ("taunt_denial", bool(taunt)),
                        )
                        if on
                    )
                    or "none",
                    "bulk": str(bulk),
                    "attribution": attr_note or "none",
                },
                claimed_traits=traits,
                reasoning=(
                    f"{mechanism} clears {tier} (basis={basis}, "
                    f"usage_proven={usage_proven}, self_protection={reinforce})"
                    + (f" / {attr_note}" if attr_note else "")
                    + "."
                ),
                change_reason=change_reason,
                reinforce_class=reinforce,
                excellence_basis=basis,
            )
        )

    _guard_pool(members, rejected, pool_ids)
    return _draft_with_tiers(category, sub_criteria, members, rejected, notes=notes)


def _guard_pool(
    members: list[CandidateEval],
    rejected: list[RejectedCandidate],
    pool_ids: set[str],
) -> None:
    for c in members:
        if c.species_id not in pool_ids:
            raise ValueError(f"candidate escaped legal_pool: {c.species}")
    for r in rejected:
        if r.species_id not in pool_ids:
            raise ValueError(f"rejected escaped legal_pool: {r.species}")


def _draft_with_tiers(
    category: str,
    sub_criteria: dict[str, Any],
    members: list[CandidateEval],
    rejected: list[RejectedCandidate],
    *,
    notes: list[str],
) -> RoleConstructionDraft:
    tiers: dict[str, list[str]] = {"Excellent": [], "Good": [], "Acceptable": []}
    for c in members:
        if c.tier:
            tiers.setdefault(c.tier, []).append(c.species)
    return RoleConstructionDraft(
        category=category,
        sub_criteria=_serialize_criteria(sub_criteria),
        candidates=members,
        considered_rejected=rejected,
        tiers=tiers,
        notes=list(notes),
    )


def critique_role_ranking(
    draft: RoleConstructionDraft,
    reference_compendium: dict[str, Any] | RoleConstructionDraft | None = None,
) -> CritiqueResult:
    """Audit draft against tied-cluster / self-consistency / function-fit /
    execution_conflict. Flags only."""
    flags: list[CritiqueFlag] = []
    by_id = {c.species_id: c for c in draft.candidates if c.tier}
    members = [c for c in draft.candidates if c.tier]
    rejected_by_id = {r.species_id: r for r in draft.considered_rejected}

    for i, a in enumerate(members):
        for b in members[i + 1 :]:
            if a.tier == b.tier:
                continue
            if _degree_tuple(a) == _degree_tuple(b):
                flags.append(
                    CritiqueFlag(
                        principle="tied_cluster",
                        candidates=(a.species, b.species),
                        detail=(
                            f"{a.species} ({a.tier}) vs {b.species} ({b.tier}) share "
                            f"degree {_degree_tuple(a)!r}; no criteria-based degree gap "
                            "— merge into one unordered tier"
                        ),
                    )
                )

    prior = _ref_members(reference_compendium)
    current_tiers = {c.species_id: c.tier for c in members}
    for sid, old_tier in prior.items():
        new_tier = current_tiers.get(sid)
        cand = by_id.get(sid)
        name = cand.species if cand else sid
        if new_tier is None:
            dropped = next((c for c in draft.candidates if c.species_id == sid), None)
            rej = rejected_by_id.get(sid)
            if dropped is not None and dropped.change_reason:
                continue
            if rej is not None and rej.change_reason:
                continue
            flags.append(
                CritiqueFlag(
                    principle="self_consistency",
                    candidates=(name if cand else (rej.species if rej else sid),),
                    detail=f"prior tier {old_tier!r} dropped with no change_reason",
                )
            )
            continue
        if new_tier != old_tier and (cand is None or cand.change_reason is None):
            flags.append(
                CritiqueFlag(
                    principle="self_consistency",
                    candidates=(name,),
                    detail=(
                        f"prior tier {old_tier!r} → {new_tier!r} with no change_reason"
                    ),
                )
            )

    condition = str(draft.sub_criteria.get("condition") or "")
    for c in members:
        for trait in c.claimed_traits:
            flags.extend(_function_fit_flags(c, trait, condition))

    flags.extend(_execution_conflict_flags(draft, by_id))

    return CritiqueResult(approved=not flags, flags=flags)


def _execution_conflict_flags(
    draft: RoleConstructionDraft,
    by_id: dict[str, CandidateEval],
) -> list[CritiqueFlag]:
    out: list[CritiqueFlag] = []
    # Identity: Quiver Dance % > redirect % on an Excellent member (construct should demote).
    for c in by_id.values():
        if c.tier != "Excellent":
            continue
        try:
            qd = float(c.criteria_notes.get("qd_pct") or 0.0)
            redir = float(c.criteria_notes.get("best_redirect_pct") or 0.0)
        except (TypeError, ValueError):
            continue
        if qd > redir > 0:
            out.append(
                CritiqueFlag(
                    principle="execution_conflict",
                    candidates=(c.species,),
                    detail=(
                        f"Quiver Dance {qd}% > redirect {redir}% — should cap "
                        "Excellent → Good (turn-economy conflict)"
                    ),
                )
            )

    # Attribution: base Excellent / usage_proven above Mega when Showdown discounted base.
    snap = load_snapshot()
    pool_ids = set(by_id)
    seen: set[tuple[str, str]] = set()
    for sid in list(by_id):
        pair = _mega_pair_ids(sid, snap, pool_ids)
        if not pair or pair in seen:
            continue
        seen.add(pair)
        base_sid, mega_sid = pair
        base, mega = by_id.get(base_sid), by_id.get(mega_sid)
        if not base or not mega:
            continue
        base_proven = base.criteria_notes.get("usage_proven") == "True"
        mega_proven = mega.criteria_notes.get("usage_proven") == "True"
        discounted = "discounted" in (base.criteria_notes.get("attribution") or "")
        if discounted and base_proven and not mega_proven:
            out.append(
                CritiqueFlag(
                    principle="execution_conflict",
                    candidates=(base.species, mega.species),
                    detail=(
                        f"{base.species} usage_proven while Showdown-discounted vs "
                        f"{mega.species} — attribution inversion"
                    ),
                )
            )
        tier_rank = {"Excellent": 2, "Good": 1, "Acceptable": 0}
        if tier_rank.get(base.tier or "", 0) > tier_rank.get(mega.tier or "", 0):
            if discounted or (not mega_proven and base_proven):
                out.append(
                    CritiqueFlag(
                        principle="execution_conflict",
                        candidates=(base.species, mega.species),
                        detail=(
                            f"{base.species} ({base.tier}) outranks {mega.species} "
                            f"({mega.tier}) despite Mega being the substantial "
                            "Showdown usage bearer"
                        ),
                    )
                )
    return out


def _function_fit_flags(
    cand: CandidateEval, trait: ClaimedTrait, condition: str
) -> list[CritiqueFlag]:
    out: list[CritiqueFlag] = []
    tid = to_id(trait.name)
    purpose = trait.purpose_claimed.lower()
    criterion = trait.criterion

    field = ABILITY_TO_FIELD.get(tid)
    if field and "weather" in field:
        weather = str(field.get("weather") or "")
        if criterion == "delivery" and condition and weather != condition:
            out.append(
                CritiqueFlag(
                    principle="function_fit",
                    candidates=(cand.species,),
                    detail=(
                        f"{trait.name} sets {weather!r}, not condition {condition!r}"
                    ),
                )
            )

    if tid == "prankster" and criterion != "execution":
        out.append(
            CritiqueFlag(
                principle="function_fit",
                candidates=(cand.species,),
                detail=(
                    "Prankster only credits execution of status setup, not other criteria"
                ),
            )
        )

    allyish = "ally" in purpose or criterion == "secondary_role"
    if allyish and (
        "protect" in purpose or "ally" in purpose or criterion == "secondary_role"
    ):
        ab = get_ability(tid)
        if ab:
            tags = ab.get("tags") or []
            if tags and all(t.get("target") == "self" for t in tags):
                if "ally" in purpose or "protection" in purpose or "protect" in purpose:
                    out.append(
                        CritiqueFlag(
                            principle="function_fit",
                            candidates=(cand.species,),
                            detail=(
                                f"{trait.name} is self-targeted; does not serve "
                                f"claimed purpose {trait.purpose_claimed!r}"
                            ),
                        )
                    )
    return out


def _roles_filename(category: str, sub_criteria: dict[str, Any]) -> str:
    cond = to_id(str(sub_criteria.get("condition") or ""))
    if not cond:
        return f"{category}.v1.json"
    return f"{category}_{cond}.v1.json"


def draft_to_dict(draft: RoleConstructionDraft) -> dict[str, Any]:
    return {
        "category": draft.category,
        "condition": draft.sub_criteria.get("condition"),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "sub_criteria": draft.sub_criteria,
        "tiers": draft.tiers,
        "notes": draft.notes,
        "candidates": [
            {
                "species": c.species,
                "species_id": c.species_id,
                "tier": c.tier,
                "delivery_class": c.delivery_class,
                "mechanism": c.mechanism,
                "criteria_notes": c.criteria_notes,
                "claimed_traits": [asdict(t) for t in c.claimed_traits],
                "reasoning": c.reasoning,
                "change_reason": c.change_reason,
                "reinforce_class": c.reinforce_class,
                "excellence_basis": c.excellence_basis,
            }
            for c in draft.candidates
        ],
        "considered_rejected": [asdict(r) for r in draft.considered_rejected],
    }


def load_prior_compendium(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def persist_approved(
    draft: RoleConstructionDraft,
    roles_dir: Path,
    *,
    filename: str | None = None,
) -> Path:
    roles_dir.mkdir(parents=True, exist_ok=True)
    name = filename or _roles_filename(draft.category, draft.sub_criteria)
    current = roles_dir / name
    if current.exists():
        hist = roles_dir / "history"
        hist.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        stem = name.replace(".v1.json", "")
        shutil.copy2(current, hist / f"{stem}.{ts}.json")
    current.write_text(json.dumps(draft_to_dict(draft), indent=2) + "\n")
    return current


def legal_species_pool(snap: dict[str, Any] | None = None) -> list[str]:
    snap = snap or load_snapshot()
    out: list[str] = []
    for sid, entry in (snap.get("species") or {}).items():
        if is_species_legal(snap, sid):
            out.append(str(entry.get("name") or sid))
    return out


def rebuild_role_category(
    category: str,
    sub_criteria: dict[str, Any],
    *,
    roles_dir: Path | None = None,
    live_fetch: LiveFetch | None = fetch_ingame_doubles_species,
    showdown_fetch: LiveFetch | None = fetch_showdown_vgc_species,
    calculate_batch: CalculateBatch | None = _default_calculate_batch,
) -> RebuildResult:
    """Construct + critique; persist only on approval. Flags → human gate (no auto-revise)."""
    roles_dir = roles_dir or DEFAULT_ROLES_DIR
    snap = load_snapshot()
    pool = legal_species_pool(snap)
    path = roles_dir / _roles_filename(category, sub_criteria)
    prior = load_prior_compendium(path)
    draft = construct_role_category(
        category,
        sub_criteria,
        pool,
        snap=snap,
        reference_compendium=prior,
        live_fetch=live_fetch,
        showdown_fetch=showdown_fetch,
        calculate_batch=calculate_batch,
    )
    critique = critique_role_ranking(draft, reference_compendium=prior)
    if not critique.approved:
        return RebuildResult(
            status="needs_revision",
            draft=draft,
            critique=critique,
            path=None,
        )
    written = persist_approved(draft, roles_dir)
    return RebuildResult(
        status="approved",
        draft=draft,
        critique=critique,
        path=str(written),
    )
