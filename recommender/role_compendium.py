"""Role Compendium construction / critic / rebuild (ADR-019).

Three separate callables — construct does not self-critique.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from recommender.ability_classification import (
    execution_reinforce_abilities,
    flinch_denial_ability_ids,
    get_ability,
    taunt_denial_ability_ids,
)
from recommender.calc_client import calculate_batch as _default_calculate_batch
from recommender.counters import (
    _move_base_accuracy,
    _scaled_base_power,
    effective_move_type,
)
from recommender.coverage import ABILITY_TO_FIELD
from recommender.ids import to_id
from recommender.legality import is_species_legal, load_snapshot, resolve_learnset
from recommender.matchup import (
    _CHARGE_MOVES,
    _RECHARGE_MOVES,
    _makes_contact,
    effective_accuracy,
)
from recommender.move_narrowing import move_priority
from recommender.reconcile import _item_mega_forme
from recommender.support_needs import _OFFENSIVE_PRIORITY_MOVES, _SELF_HEAL_MOVES
from recommender.usage_cbd import fetch_ingame_doubles_species
from recommender.usage_data import (
    featured_or_common_set,
    ingame_excluded_ids,
    ingame_species_map,
    load_usage,
    set_from_ingame,
    set_from_showdown,
    showdown_species_map,
)
from recommender.stat_boosts import (
    _self_boosts,
    _self_defense_drops,
    load_stat_boosts,
)
from recommender.usage_showdown import fetch_showdown_vgc_species

from recommender.role_compendium_read import (
    DEFAULT_ROLES_DIR,
    ROLE_TIER_ORDER,
    CompendiumRoleEvidence,
    ReverseCompendiumEvidence,
    _roles_filename,
    load_prior_compendium,
    load_role_category,
    role_candidates,
    role_category_evidence,
    reverse_compendium_evidence,
)

ROOT = Path(__file__).resolve().parents[1]

LiveFetch = Callable[[str], dict[str, Any] | None]
CalculateBatch = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]

# Redirection Phase 2: Quiver Dance vs redirect turn-economy.
_COMPETING_IDENTITY_MOVES = frozenset({"quiverdance"})
# Base Showdown usage_pct must be ≥ this fraction of Mega's to keep usage_proven.
_SHOWDOWN_BASE_USAGE_RATIO = 0.25
# Chaos set% floor for usage-proven (July 2026 1500 distribution).
# Screens smear starts after Whimsicott/Espeon 2.32% (next 1.98%). Sleep's 2.3
# vs 3.0 admit the same set (nothing in (1.66, 3.01)). TR has its own hole.
_USAGE_SET_PCT_FLOOR = 2.3
_TRICK_ROOM_SET_PCT_FLOOR = 22.5
# Setup-attacker admission: presence only (exclude 0.00x chaos-key ghosts).
# Calc Excellent/Good/Acceptable floors do the real filter. Support stays at 2.3.
# Fallback only when Mega has no Showdown entry: mega-stone item share on base CBD page.
_MEGA_STONE_FALLBACK_PCT = 80.0

from recommender.role_compendium_setup_constants import (  # noqa: E402
    _ALLY_HIT_DAMAGE_MOVE_IDS,
    _ALLY_HIT_TYPE_PROTECTIONS,
    _BODY_PRESS_EVS,
    _CALC_POKE_KEYS,
    _CONNECT_RECOIL_MOVES,
    _DD_SETUP_PRESENCE_FLOOR,
    _DEF_PAYOFF_DELTA_EPS,
    _DRAIN_MOVES,
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
)

SetupPriorityKind = Literal["none", "unconditional", "conditional"]

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
    # Locked judgment cut (Lycanroc-Dusk keep=37); Acceptable-largest redesign.
    "damage_admission_floor": 0.969,
    "acceptable_floor_mult": 0.85,
}

NASTY_PLOT_ATTACKER_CRITERIA: dict[str, Any] = {
    "kind": "setup_attacker",
    "condition": "",
    "move_id": "nastyplot",
    "boost_stat": "spa",
    "boost_stages": 2,
}

CALM_MIND_ATTACKER_CRITERIA: dict[str, Any] = {
    "kind": "offense_bulk_setup",
    "condition": "",
    "move_id": "calmmind",
    "boost_stat": "spa",
    "boost_stages": 1,
    "exact_boosts": {"spa": 1, "spd": 1},
    # Locked judgment cut (Mr. Rime keep=38); Acceptable-largest redesign.
    "damage_admission_floor": 0.708,
    "acceptable_floor_mult": 0.88,
}

BULK_UP_ATTACKER_CRITERIA: dict[str, Any] = {
    "kind": "offense_bulk_setup",
    "condition": "",
    "move_id": "bulkup",
    "boost_stat": "atk",
    "boost_stages": 1,
    "exact_boosts": {"atk": 1, "def": 1},
    # Locked judgment cut (Lycanroc keep=36 at 0.766); Acceptable-largest redesign.
    "damage_admission_floor": 0.766,
    "acceptable_floor_mult": 0.90,
}

DRAGON_DANCE_ATTACKER_CRITERIA: dict[str, Any] = {
    "kind": "offense_speed_setup",
    "condition": "",
    "move_id": "dragondance",
    "boost_stat": "atk",
    "boost_stages": 1,
    "exact_boosts": {"atk": 1, "spe": 1},
}

IRON_DEFENSE_BODY_PRESS_CRITERIA: dict[str, Any] = {
    "kind": "def_payoff_setup",
    "condition": "",
    "setup_move_id": "irondefense",
    "payoff_move_id": "bodypress",
    "boost_stat": "def",
    "boost_stages": 2,
}

# Dummy Def-invested spread for Body Press (uses Defense, not Attack).

TAILWIND_SETTER_CRITERIA: dict[str, Any] = {
    "kind": "tailwind_setter",
    "condition": "",
    "move_ids": frozenset({"tailwind"}),
    # No ability delivers Tailwind — criterion 1 cannot separate candidates.
    "ability_ids": frozenset(),
}

SLEEP_STATUS_SPREADER_CRITERIA: dict[str, Any] = {
    "kind": "sleep_status_spreader",
    "condition": "",
    # Core set from ADR-015 2026-07-29f; constructor also sweeps other Status
    # sleep moves present in the snapshot (Sing, Spore, Dark Void, …).
    "move_ids": frozenset({"sleeppowder", "hypnosis", "yawn"}),
    "ability_ids": frozenset(),
}

SCREENS_SUPPORT_CRITERIA: dict[str, Any] = {
    "kind": "screens_support",
    "condition": "",
    "move_ids": frozenset({"lightscreen", "reflect", "auroraveil"}),
    "ability_ids": frozenset(),
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

# Tailwind Setter: same closed support list minus the primary mechanism. Trick Room
# stays allowable as a genuine second speed-control answer (TailRoom is real).
_TAILWIND_DELIVERY_NOTE = (
    "move-only delivery; no ability sets Tailwind — weather's move→Good cap "
    "does not apply (no ability tier above move delivery)"
)
# Provisional Spe floor for non-Prankster natural-Speed landing (reviewable;
# same numeric bar as setup Branch B / _SETUP_SPE_FLOOR).
_TAILWIND_SPE_FLOOR = _SETUP_SPE_FLOOR
_TAILWIND_SECONDARY_MOVES = _REDIRECTION_SECONDARY_MOVES - {"tailwind"}
_TAILWIND_EXCELLENT_SECONDARY_MOVES = _REDIRECTION_EXCELLENT_SECONDARY_MOVES - {
    "tailwind",
}

# Sleep Status Spreader — ADR-015 2026-07-29f. Accuracies are game facts (snapshot
# strips accuracy); keep them here so pathway grading stays checkable.
_SLEEP_CORE_MOVES = frozenset({"sleeppowder", "hypnosis", "yawn"})
_SLEEP_STATUS_MOVES = frozenset(
    {
        "sleeppowder",
        "hypnosis",
        "yawn",
        "spore",
        "darkvoid",
        "sing",
        "grasswhistle",
        "lovelykiss",
    }
)
_SLEEP_ACCURACY: dict[str, int] = {
    "spore": 100,
    "sleeppowder": 75,
    "hypnosis": 60,
    "yawn": 100,  # lands 100%; sleep effect delayed one turn
    "sing": 55,
    "darkvoid": 50,
    "grasswhistle": 55,
    "lovelykiss": 85,
}
_SLEEP_IMMEDIATE = frozenset(
    {"spore", "sleeppowder", "hypnosis", "sing", "darkvoid", "grasswhistle", "lovelykiss"}
)
_SLEEP_DELAYED = frozenset({"yawn"})
_SLEEP_ACCURACY_ABILITIES = frozenset({"compoundeyes", "noguard"})
_SLEEP_TRAP_ABILITIES = frozenset({"shadowtag", "arenatrap", "magnetpull"})
_SLEEP_SPE_FLOOR = _SETUP_SPE_FLOOR  # provisional; ignored for pure Yawn
_SLEEP_SPEED_ABILITIES = frozenset(
    {
        "chlorophyll",
        "swiftswim",
        "sandrush",
        "slushrush",
        "unburden",
        "speedboost",
    }
)
_SLEEP_SECONDARY_MOVES = frozenset(
    {
        "encore",
        "lightscreen",
        "reflect",
        "auroraveil",
        "stickyweb",
        "trickroom",
        "tailwind",
        "lifedew",
        "willowisp",
        "thunderwave",
        "wideguard",
        "followme",
        "ragepowder",
    }
)
# Helping Hand is deliberately excluded — not sleep excellence (plan).
_SLEEP_EXCELLENT_SECONDARY_MOVES = frozenset(
    {"lightscreen", "reflect", "stickyweb", "trickroom", "tailwind"}
)

# Screens Support: one category (Dual / LS / Reflect / Aurora Veil). No ability
# sets screens — same move-only delivery shape as Tailwind.
_SCREENS_DELIVERY_NOTE = (
    "move-only delivery; no ability sets screens — weather's move→Good cap "
    "does not apply (no ability tier above move delivery)"
)
_SCREENS_SPE_FLOOR = _SETUP_SPE_FLOOR
_SCREENS_MOVE_IDS = frozenset({"lightscreen", "reflect", "auroraveil"})
_SCREENS_SNOW_ABILITIES = frozenset({"snowwarning"})
_SCREENS_SECONDARY_MOVES = _REDIRECTION_SECONDARY_MOVES - _SCREENS_MOVE_IDS
_SCREENS_EXCELLENT_SECONDARY_MOVES = _REDIRECTION_EXCELLENT_SECONDARY_MOVES - {
    "lightscreen",
    "reflect",
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
    criteria_notes: dict[str, Any]
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

        Presence of a CBD row is not a Showdown blackout — callers must consult
        Showdown per-move when this row lacks the move. Shares entry_for's
        live-fetch cache.
        """
        sid = to_id(species)
        if sid in ingame_excluded_ids():
            return None
        row = ingame_species_map().get(sid)
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
    maps.append(ingame_species_map())
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


def _entry_has_item(entry: dict[str, Any] | None, item_id: str) -> bool:
    if not entry:
        return False
    iid = to_id(item_id)
    for it in entry.get("common_items") or []:
        if to_id(it.get("name") or "") == iid:
            return True
    for fs in entry.get("featured_sets") or []:
        if to_id(fs.get("item") or "") == iid:
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
        mega_showdown_fallback=(
            kind
            in {
                "setup_attacker",
                "offense_bulk_setup",
                "offense_speed_setup",
                "def_payoff_setup",
            }
        ),
    )
    if kind == "redirection":
        from recommender.role_compendium_support import _construct_redirection

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
        from recommender.role_compendium_support import _construct_trick_room_setter

        return _construct_trick_room_setter(
            category,
            sub_criteria,
            legal_pool,
            snap=snap,
            uctx=uctx,
            showdown_fetch=showdown_fetch,
            reference_compendium=reference_compendium,
        )
    if kind == "tailwind_setter":
        from recommender.role_compendium_support import _construct_tailwind_setter

        return _construct_tailwind_setter(
            category,
            sub_criteria,
            legal_pool,
            snap=snap,
            uctx=uctx,
            showdown_fetch=showdown_fetch,
            reference_compendium=reference_compendium,
        )
    if kind == "sleep_status_spreader":
        from recommender.role_compendium_support import _construct_sleep_status_spreader

        return _construct_sleep_status_spreader(
            category,
            sub_criteria,
            legal_pool,
            snap=snap,
            uctx=uctx,
            showdown_fetch=showdown_fetch,
            reference_compendium=reference_compendium,
        )
    if kind == "screens_support":
        from recommender.role_compendium_support import _construct_screens_support

        return _construct_screens_support(
            category,
            sub_criteria,
            legal_pool,
            snap=snap,
            uctx=uctx,
            showdown_fetch=showdown_fetch,
            reference_compendium=reference_compendium,
        )
    if kind == "setup_attacker":
        from recommender.role_compendium_setup import _construct_setup_attacker

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
    if kind in {"offense_bulk_setup", "offense_speed_setup"}:
        from recommender.role_compendium_setup import _construct_offense_stage_setup

        return _construct_offense_stage_setup(
            category,
            sub_criteria,
            legal_pool,
            snap=snap,
            uctx=uctx,
            showdown_fetch=showdown_fetch,
            reference_compendium=reference_compendium,
            calculate_batch=calculate_batch or _default_calculate_batch,
        )
    if kind == "def_payoff_setup":
        from recommender.role_compendium_setup import _construct_def_payoff_setup

        return _construct_def_payoff_setup(
            category,
            sub_criteria,
            legal_pool,
            snap=snap,
            uctx=uctx,
            showdown_fetch=showdown_fetch,
            reference_compendium=reference_compendium,
            calculate_batch=calculate_batch or _default_calculate_batch,
        )
    from recommender.role_compendium_weather import _construct_weather_setter

    return _construct_weather_setter(
        category,
        sub_criteria,
        legal_pool,
        snap=snap,
        uctx=uctx,
        showdown_fetch=showdown_fetch,
        reference_compendium=reference_compendium,
    )






def _recoil_frac_from_result(r: Any, mid: str) -> float:
    """Attacker HP fraction lost to connect-recoil from a calc result (0 if N/A).

    Uses raw.recoil (% of attacker max HP), not ratio×dmg — OHKO-capped hits
    otherwise overstate recoil. Crash / mindblown / chloroblast stay out via
    _CONNECT_RECOIL_MOVES.
    """
    if to_id(mid) not in _CONNECT_RECOIL_MOVES or not isinstance(r, dict):
        return 0.0
    raw = (r.get("raw") or {}).get("recoil")
    if not isinstance(raw, dict):
        return 0.0
    val = raw.get("recoil")
    try:
        if isinstance(val, (list, tuple)) and val:
            pct = float(val[-1])
        else:
            pct = float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if pct <= 0:
        return 0.0
    return pct / 100.0


def _drain_frac_from_result(r: Any, mid: str) -> float:
    """Attacker HP fraction healed by a drain move from a calc result (0 if N/A).

    Uses raw.recovery.recovery (absolute HP) / raw.stats.attacker.hp. Shell Bell
    and other item healing also populate raw.recovery — gate on _DRAIN_MOVES is
    mandatory. Do not hardcode drain ratios; calc already applied them.
    """
    if to_id(mid) not in _DRAIN_MOVES or not isinstance(r, dict):
        return 0.0
    raw_top = r.get("raw") or {}
    raw = raw_top.get("recovery")
    if not isinstance(raw, dict):
        return 0.0
    val = raw.get("recovery")
    try:
        if isinstance(val, (list, tuple)) and val:
            healed = float(val[-1])
        else:
            healed = float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if healed <= 0:
        return 0.0
    try:
        max_hp = float((raw_top.get("stats") or {}).get("attacker", {}).get("hp") or 0)
    except (TypeError, ValueError):
        return 0.0
    if max_hp <= 0:
        return 0.0
    return healed / max_hp


def exclusive_self_boost_move(*, boost_stat: str, stages: int = 2) -> str:
    """Champions-legal Status move whose only stat change is +stages to the user's boost_stat."""
    want = [{"to": "self", "chance": 100, "stats": {boost_stat: stages}}]
    hits = [
        mid
        for mid, ent in (load_stat_boosts().get("moves") or {}).items()
        if ent.get("category") == "Status" and ent.get("boosts") == want
    ]
    if len(hits) != 1:
        raise ValueError(f"expected one self +{stages} {boost_stat}-only move, got {hits}")
    return hits[0]


def exact_self_boost_move(want: dict[str, int]) -> str:
    """Champions-legal Status move whose guaranteed self-boosts equal `want` exactly."""
    hits = [
        mid
        for mid, ent in (load_stat_boosts().get("moves") or {}).items()
        if ent.get("category") == "Status" and _self_boosts(ent) == want
    ]
    if len(hits) != 1:
        raise ValueError(f"expected one Status self-boost {want}, got {hits}")
    return hits[0]






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
    from recommender.role_compendium_usage import _mega_pair_ids

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


_USAGE_REEXPORTS = frozenset(
    {
        "_best_move_set_pct",
        "_cbd_base_move_implausible_vs_mega",
        "_delivery_usage_hits",
        "_hits_clear_set_pct_floor",
        "_mega_pair_ids",
        "_mega_stone_on_entry",
        "_mega_usage_attribution",
        "_move_display",
        "_move_pct",
        "_same_row_both_moves",
        "_showdown_entry",
        "_species_types",
        "_stone_fallback_ability",
        "_stone_fallback_usage",
        "_usage_has_item",
    }
)

_SETUP_REEXPORTS = frozenset(
    {
        "_AEGISLASH_FORMES",
        "_KO_BIN_RANK",
        "_ally_damage_risk_note",
        "_attach_top1_partners",
        "_attacker_kit",
        "_best_payoff_move",
        "_calc_pokemon_spec",
        "_calc_species_name",
        "_candidate_defender_spec",
        "_common_move_names",
        "_construct_def_payoff_setup",
        "_construct_offense_stage_setup",
        "_construct_setup_attacker",
        "_crossing_k",
        "_damage_score",
        "_drop_setup_choice_item",
        "_hit_frac_from_result",
        "_incoming_ohko_by_defender",
        "_is_bulk_crossing",
        "_is_spread_damage_mid",
        "_kit_damaging_mids",
        "_ko_frac_bin",
        "_move_override_extra",
        "_pair_entry_label",
        "_partition_by_admission_floor",
        "_payoff_coverage_note",
        "_payoff_sort_bp",
        "_pikalytics_panel_pair_counts",
        "_present_usage_payoff_ids",
        "_priority_finisher_combined_ko",
        "_ranked_payoff_moves",
        "_select_setup_payoff",
        "_setup_ability_for_payoff",
        "_setup_adjusted_score",
        "_setup_banned_payoffs",
        "_setup_branch_a",
        "_setup_branch_a_via_priority",
        "_setup_branches",
        "_setup_bulk_crossings",
        "_setup_bulk_ok",
        "_setup_defender_species",
        "_setup_excellent_floor",
        "_setup_kit_matrix_score",
        "_setup_mech_tier",
        "_setup_panel_build",
        "_setup_payoff_candidates",
        "_setup_payoff_notes",
        "_setup_priority_for_branch",
        "_setup_priority_kind",
        "_setup_self_drop_moves",
        "_setup_spe_crossings",
        "_setup_speed_path_a",
        "_setup_sustain_ok",
        "_setup_threat_defenders",
        "_setup_turn_order_weight",
        "_sort_members_by_crossings",
        "_sort_members_by_sweep",
        "_sweep_note_fields",
        "_threat_panel_label",
        "_usage_payoff_move_ids",
    }
)


_SUPPORT_REEXPORTS = frozenset(
    {
        "_construct_redirection",
        "_construct_screens_support",
        "_construct_sleep_status_spreader",
        "_construct_tailwind_setter",
        "_construct_trick_room_setter",
        "_protection_note",
        "_screens_dual_usage",
        "_screens_mech_dual",
        "_sleep_delivery_ids",
        "_sleep_pathway",
    }
)


def __getattr__(name: str) -> Any:
    if name in _SUPPORT_REEXPORTS:
        import recommender.role_compendium_support as _support

        return getattr(_support, name)
    if name in _USAGE_REEXPORTS:
        import recommender.role_compendium_usage as _usage

        return getattr(_usage, name)
    if name in _SETUP_REEXPORTS:
        import recommender.role_compendium_setup as _setup

        return getattr(_setup, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
