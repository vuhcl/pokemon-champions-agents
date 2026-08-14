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
    ingame_species_map,
    load_usage,
    set_from_ingame,
    set_from_showdown,
    showdown_species_map,
)
from recommender.usage_showdown import fetch_showdown_vgc_species

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROLES_DIR = ROOT / "data" / "roles"
_STAT_BOOSTS_PATH = ROOT / "data" / "moves" / "stat_boosts.v1.json"

LiveFetch = Callable[[str], dict[str, Any] | None]
CalculateBatch = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]

# Strongest first — the order a consumer should prefer members in, rather than
# whatever order the tiers happen to appear in the JSON.
ROLE_TIER_ORDER = ("Excellent", "Good", "Acceptable")

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
_SETUP_PRESENCE_SET_PCT_FLOOR = 0.1
# DD-only: real hole (0.390, 1.363]; 0.5% and 1.0% admit the same set (Sleep pattern).
_DD_SETUP_PRESENCE_FLOOR = 1.0
# Fallback only when Mega has no Showdown entry: mega-stone item share on base CBD page.
_MEGA_STONE_FALLBACK_PCT = 80.0

# Setup attacker membership / ranking (ADR-015 deferred-payoff).
_SETUP_SPE_FLOOR = 100
# ponytail: doubles bulk heuristic; Role Compendium can replace with threat-calced bulk later.
_SETUP_BULK_FLOOR = 400
_SETUP_SUSTAIN_HEALS = _SELF_HEAL_MOVES | frozenset({"rest"})
_SETUP_SUSTAIN_ITEMS = frozenset({"leftovers", "blacksludge", "sitrusberry"})
# Choice locks the first move: cannot setup then cash out. check_theme_fit
# (_tier1_choice_status_moves) already knows this; Compendium kits never ran it.
_SETUP_CHOICE_ITEMS = frozenset({"choiceband", "choicespecs", "choicescarf"})
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
# Showdown usage_pct floor: >50% chance to face the mon in k games.
# 1 - (1-p)^k > 0.5 → p > 1 - 0.5^(1/k). k=15 is Smogon modern OU (4.52%).
# Champions in-game snapshot has ranks only — threshold uses Showdown@1500.
_SETUP_THREAT_ENCOUNTER_GAMES = 15
_SETUP_THREAT_USAGE_PCT_FLOOR = 100.0 * (
    1.0 - 0.5 ** (1.0 / _SETUP_THREAT_ENCOUNTER_GAMES)
)
# Kind labels only (turn-order already grants full credit for priority).
_SETUP_CONDITIONAL_PRIORITY = frozenset({"suckerpunch", "thunderclap", "upperhand"})
_SETUP_NARROW_CONDITIONAL_PRIORITY = frozenset({"feint"})
# Switch-in-only: cannot follow Swords Dance / Nasty Plot (Branch A + payoff).
_SETUP_BRANCH_A_PRIORITY = _OFFENSIVE_PRIORITY_MOVES - frozenset({"fakeout"})
# Priority finishers for combined-KO after a non-OHKO payoff (lived_shield path).
# Hard-excluded: fakeout, firstimpression, upperhand. Deferred: grassyglide (terrain).
_SETUP_PRIORITY_FINISHER_MOVES = frozenset(
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
# Soft overkill cap: credit up to 25% beyond a KO (hard 1.0 flattened useful signal).
_SETUP_DAMAGE_FRAC_CAP = 1.25
# A+B: inverse of the former both-branch Excellent gate discount (floor × div).
_SETUP_BOTH_BRANCH_SCORE_DIV = 0.80
_SETUP_FLOOR_SECOND_MULT = 0.95
# Good/Acceptable split: anchored on the widest real gap in the SD Good field
# (0.869 | 0.768), whose stable plateau is (0.664, 0.752] × floor; 0.70 is the midpoint.
_SETUP_ACCEPTABLE_FLOOR_MULT = 0.70
_CALC_POKE_KEYS = ("species", "item", "ability", "moves", "nature", "evs", "boosts", "level")

SetupPriorityKind = Literal["none", "unconditional", "conditional"]
# Lock-in: 2-3 forced turns then self-confusion — same unmodeled multi-turn cost as charge/recharge.
# Uproar: 2-3 turn lock (no confusion); setup can fire first, but the cash-out cannot
# be a move that then traps the attacker in Uproar — same reason Choice is stripped.
_SETUP_LOCKIN_MOVES = frozenset(
    {"outrage", "petaldance", "thrash", "ragingfury", "uproar"}
)
# Same-turn unreliable / delayed / recharge / lock-in — not valid setup cash-out payoffs.
# Fake Out / First Impression: switch-in-only; cannot cash out after setup.
# Upper Hand: only hits if the opponent used priority that turn — static calc can't guarantee.
# Grassy Glide: terrain never modeled as active — fake unconditional priority.
# Last Resort: fails unless every other move has been used — unmodeled condition.
# Self-Destruct / Explosion: KO the user; not a repeatable setup cash-out.
_SETUP_BANNED_PAYOFF = (
    frozenset(
        {
            "focuspunch",
            "futuresight",
            "doomdesire",
            "fakeout",
            "upperhand",
            "grassyglide",
            "firstimpression",
            "lastresort",
            "selfdestruct",
            "explosion",
        }
    )
    | _CHARGE_MOVES
    | _RECHARGE_MOVES
    | _SETUP_LOCKIN_MOVES
)
# Champions-legal connect recoil (Showdown recoil: [a,b]). Not crash / mindblown /
# chloroblast / struggle — those are different HP-cost mechanics.
_CONNECT_RECOIL_MOVES = frozenset(
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

CALM_MIND_ATTACKER_CRITERIA: dict[str, Any] = {
    "kind": "offense_bulk_setup",
    "condition": "",
    "move_id": "calmmind",
    "boost_stat": "spa",
    "boost_stages": 1,
    "exact_boosts": {"spa": 1, "spd": 1},
}

BULK_UP_ATTACKER_CRITERIA: dict[str, Any] = {
    "kind": "offense_bulk_setup",
    "condition": "",
    "move_id": "bulkup",
    "boost_stat": "atk",
    "boost_stages": 1,
    "exact_boosts": {"atk": 1, "def": 1},
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
_BODY_PRESS_EVS = {"hp": 4, "atk": 0, "def": 32, "spa": 0, "spd": 0, "spe": 32}
_DEF_PAYOFF_DELTA_EPS = 1e-6

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
_SCREENS_SNOW_MOVES = frozenset({"snowscape", "chillyreception"})
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

        Presence of a CBD row is not a Showdown blackout — callers must consult
        Showdown per-move when this row lacks the move. Shares entry_for's
        live-fetch cache.
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
    if kind == "tailwind_setter":
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
        usage_proven = uctx.delivers(name, move_id) and _hits_clear_set_pct_floor(
            name,
            {move_id},
            floor=_USAGE_SET_PCT_FLOOR,
            uctx=uctx,
            sd_cache=sd_cache,
            showdown_fetch=showdown_fetch,
        )
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
    ingame = (load_usage().get("ingame_doubles") or {}).get("species") or {}
    ch = ingame.get(sid)
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


def load_stat_boosts() -> dict[str, Any]:
    return json.loads(_STAT_BOOSTS_PATH.read_text())


def _self_boosts(entry: dict[str, Any]) -> dict[str, int]:
    """Stat changes the move always applies to its own user (chance-gated ones excluded)."""
    out: dict[str, int] = {}
    for eff in entry.get("boosts") or []:
        if eff.get("to") != "self" or eff.get("chance") != 100:
            continue
        for stat, stages in (eff.get("stats") or {}).items():
            out[stat] = out.get(stat, 0) + int(stages)
    return out


@lru_cache(maxsize=None)
def _self_defense_drops(mid: str) -> dict[str, int]:
    """Guaranteed self Def/SpD drops for a damaging move (empty if none)."""
    ent = (load_stat_boosts().get("moves") or {}).get(to_id(mid)) or {}
    if ent.get("category") == "Status":
        return {}
    drops = {
        s: st
        for s, st in _self_boosts(ent).items()
        if s in {"def", "spd"} and st < 0
    }
    return drops


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


def _setup_mech_tier(adjusted: float, floor: float) -> str:
    """Excellent ≥ floor; Acceptable below floor × mult; Good between."""
    if floor <= 0:
        return "Good"
    if adjusted >= floor:
        return "Excellent"
    if adjusted < floor * _SETUP_ACCEPTABLE_FLOOR_MULT:
        return "Acceptable"
    return "Good"


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
    return out


def _threat_panel_label(panel: list[dict[str, Any]]) -> str:
    return ", ".join(
        f"{d.get('species')}/{d.get('item') or 'no-item'}" for d in panel
    )


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


def _species_types(snap: dict[str, Any], sid: str) -> set[str]:
    entry = snap.get("species", {}).get(sid) or {}
    return {str(t).lower() for t in (entry.get("types") or [])}


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
        fin_reqs = [
            {
                "attacker": fin_atk,
                "defender": _calc_pokemon_spec(defn),
                "move": fin_disp,
                "field": {"gameType": "Doubles"},
                **_move_override_extra(fin_mid),
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

    # mid → list aligned with panel: (kind, raw_frac, atk_spe, def_spe, result|err)
    by_mid: dict[str, list[tuple[str, float, int, int, Any]]] = {}
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
        try:
            results = calculate_batch(reqs)
        except Exception as e:  # noqa: BLE001
            return 0.0, f"batch_exception:{type(e).__name__}:{e}", [], {}
        if len(results) != len(panel):
            return 0.0, f"batch_length:{len(results)}!={len(panel)}", [], {}
        row: list[tuple[str, float, int, int, Any]] = []
        for defn, r in zip(panel, results, strict=True):
            dname = str(defn.get("species") or "")
            if not isinstance(r, dict):
                errors.append(f"{dname}:non_dict")
                row.append(("skip", 0.0, 0, 0, None))
                continue
            if "error" in r:
                errors.append(f"{dname}:{r.get('error')}")
                row.append(("skip", 0.0, 0, 0, None))
                continue
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
                row.append(("skip", 0.0, 0, 0, None))
                continue
            if hp_f <= 0:
                errors.append(f"{dname}:no_hp")
                row.append(("skip", 0.0, 0, 0, None))
                continue
            raw_frac = dmg_f / hp_f if dmg_f > 0 else 0.0
            row.append(("ok", raw_frac, atk_spe, def_spe, r))
        by_mid[mid] = row

    used: list[tuple[str, str]] = []
    fracs: list[float] = []
    remains: list[float] = []
    sweep_ohko = 0
    sweep_2hko = 0
    per_defender: list[dict[str, Any]] = []
    mid_counts: dict[str, int] = {}

    for i, defn in enumerate(panel):
        dname = str(defn.get("species") or i)
        incoming_frac = ohko_mask.get(dname)
        incoming = incoming_frac is not None and incoming_frac >= 1.0
        best: tuple[int, float, str, float, bool, int, int, Any] | None = None
        # (bin_rank, weighted, mid, raw_frac, combined, atk_spe, def_spe, r)
        for mid in mids:
            kind, raw_frac, atk_spe, def_spe, r = by_mid[mid][i]
            if kind != "ok":
                continue
            effective = (
                int(atk_spe * (2 + spe_stages) / 2) if spe_stages else atk_spe
            )
            outsped = atk_spe > 0 and def_spe > 0 and effective < def_spe
            lived_shield = (
                outsped and incoming_frac is not None and incoming_frac < 1.0
            )
            combined = False
            if (
                fin_mid is not None
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
            weighted = weight * capped
            key = (_KO_BIN_RANK[kbin], weighted, mid, raw_frac, combined, atk_spe, def_spe, r)
            if best is None or key[0] > best[0] or (
                key[0] == best[0] and (
                    key[1] > best[1] or (key[1] == best[1] and mid < best[2])
                )
            ):
                best = (
                    key[0],
                    key[1],
                    mid,
                    raw_frac,
                    combined,
                    atk_spe,
                    def_spe,
                    r,
                )
        if best is None:
            continue
        _br, weighted, mid, raw_frac, combined, atk_spe, def_spe, r = best
        kbin = "ohko" if combined else _ko_frac_bin(raw_frac)
        fracs.append(weighted)
        used.append((dname, mid))
        mid_counts[mid] = mid_counts.get(mid, 0) + 1
        if kbin == "ohko":
            sweep_ohko += 1
        if kbin in {"ohko", "2hko"}:
            sweep_2hko += 1
        per_defender.append(
            {
                "species": dname,
                "mid": mid,
                "bin": kbin,
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
            if disguise:
                remains.append(max(0.0, 1.0 - recoil_frac))
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
                    remains.append(max(0.0, seq_remain - recoil_frac))
                elif (
                    to_id(calc_name) in _AEGISLASH_FORMES
                    and raw_frac < 1.0
                ):
                    pass  # Aegislash sequence failed — no remain (legacy)
                else:
                    remains.append(
                        max(0.0, 1.0 - float(incoming_frac) - recoil_frac)
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
    """Per-defender best kit damaging move; modal mid is the display payoff_id.

    Selection: KO bin first, then weighted-capped frac. Shared incoming-OHKO once.
    Returns (payoff_id, raw_score, calc_error, priority_kind).
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


def _move_display(snap: dict[str, Any] | None, mid: str) -> str:
    if snap:
        name = (snap.get("moves") or {}).get(to_id(mid), {}).get("name")
        if name:
            return str(name)
    return mid


def _payoff_coverage_note(
    used: list[tuple[str, str]],
    *,
    snap: dict[str, Any],
    primary_mid: str,
) -> str | None:
    """Per-defender move breakdown when a candidate used more than one payoff."""
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
                    if disguise:
                        remains.append(max(0.0, 1.0 - recoil_frac))
                    elif lived_shield:
                        if seq_remain is not None:
                            remains.append(max(0.0, seq_remain - recoil_frac))
                        elif (
                            to_id(attacker_name) in _AEGISLASH_FORMES
                            and kit_moves is not None
                            and raw_frac < 1.0
                        ):
                            pass  # Aegislash sequence failed — no remain (legacy)
                        else:
                            remains.append(
                                max(0.0, 1.0 - float(incoming_frac) - recoil_frac)
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
    panel = _setup_threat_defenders()
    notes.append(
        f"threat_panel=showdown>={_SETUP_THREAT_USAGE_PCT_FLOOR:.2f}%"
        f"/{_SETUP_THREAT_ENCOUNTER_GAMES}game n={len(panel)} "
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

        calc_name, item, ability, kit_moves = _attacker_kit(
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
        move_disp = str(
            (snap.get("moves") or {}).get(payoff_id, {}).get("name") or payoff_id
        )
        coverage = _payoff_coverage_note(used, snap=snap, primary_mid=payoff_id)

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
                "move_disp": move_disp,
                "coverage": coverage,
                "branch_note": branch_note,
                "branch_basis": branch_basis,
                "excellent_secondary": excellent_secondary,
                "sec_ability": sec_ability,
                "sweep": dict(sweep),
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
        coverage = p["coverage"]
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
                name=move_disp if not coverage else f"{move_disp} + coverage",
                criterion="execution",
                purpose_claimed=(
                    f"calc damage fraction {adjusted:.3f} vs panel; branches={branch_note}"
                    + (f"; {coverage}" if coverage else "")
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
                    **({"payoff_coverage": coverage} if coverage else {}),
                    "calc_species": calc_name,
                    "damage_score_raw": f"{raw_score:.3f}",
                    "damage_score": f"{adjusted:.3f}",
                    "score_boosts": "+".join(boosts) if boosts else "none",
                    **_sweep_note_fields(p.get("sweep")),
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
    panel = _setup_threat_defenders()
    notes.append(
        f"threat_panel=showdown>={_SETUP_THREAT_USAGE_PCT_FLOOR:.2f}%"
        f"/{_SETUP_THREAT_ENCOUNTER_GAMES}game n={len(panel)} "
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
        calc_name, item, ability, kit_moves = _attacker_kit(
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
        move_disp = str((snap.get("moves") or {}).get(payoff_id, {}).get("name") or payoff_id)
        coverage = _payoff_coverage_note(used, snap=snap, primary_mid=payoff_id)
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
                "move_disp": move_disp,
                "coverage": coverage,
                "spe_note": spe_note,
                "abs_map": abs_map,
                "xk": xk,
                "xn": xn,
                "sweep": dict(sweep),
            }
        )

    floor = _setup_excellent_floor([p["raw_score"] for p in provisional])
    ranked = sorted(provisional, key=lambda p: p["raw_score"], reverse=True)
    top_label = ", ".join(f"{p['name']}={p['raw_score']:.3f}" for p in ranked[:2]) or "none"
    notes.append(
        f"Excellent damage floor = 2nd-highest × {_SETUP_FLOOR_SECOND_MULT:g} "
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
        move_disp = p["move_disp"]
        coverage = p["coverage"]
        xfield = "spe_crossings" if kind == "offense_speed_setup" else "bulk_crossings"
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
                    "payoff_move": move_disp,
                    **({"payoff_coverage": coverage} if coverage else {}),
                    "calc_species": p["calc_name"],
                    "spe_note": p["spe_note"],
                    "damage_score": f"{raw_score:.3f}",
                    xfield: xnote,
                    **_sweep_note_fields(p.get("sweep")),
                    **({"calc_error": p["calc_err"]} if p["calc_err"] else {}),
                },
                claimed_traits=[
                    ClaimedTrait(
                        name=str(
                            (snap.get("moves") or {}).get(move_id, {}).get("name") or move_id
                        ),
                        criterion="delivery",
                        purpose_claimed=f"setup via {move_id} (+{stages} {boost_stat})",
                    ),
                    ClaimedTrait(
                        name=move_disp if not coverage else f"{move_disp} + coverage",
                        criterion="execution",
                        purpose_claimed=(
                            f"calc damage fraction {raw_score:.3f} vs panel"
                            + (f"; {coverage}" if coverage else "")
                            + f"; {xfield}={xnote}"
                        ),
                    ),
                ],
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
    panel = _setup_threat_defenders()
    notes.append(
        f"threat_panel=showdown>={_SETUP_THREAT_USAGE_PCT_FLOOR:.2f}%"
        f"/{_SETUP_THREAT_ENCOUNTER_GAMES}game n={len(panel)} "
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
        calc_name, item, ability, kit_moves = _attacker_kit(
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
        if usage_proven and not _hits_clear_set_pct_floor(
            name,
            set(hits),
            floor=_USAGE_SET_PCT_FLOOR,
            uctx=uctx,
            sd_cache=sd_cache,
            showdown_fetch=showdown_fetch,
        ):
            usage_proven = False

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
        f"membership requires Trick Room set% ≥ {_TRICK_ROOM_SET_PCT_FLOOR:g} "
        "(self-protection and Showdown-discount do not waive the floor)",
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

        # Usage: negative Mega attribution sticks. Otherwise CBD and/or Showdown
        # per-move — a CBD row without the move no longer suppresses Showdown.
        if pair_usage.get(sid) is False:
            usage_proven = False
            usage_source = "mega attribution"
        else:
            usage_hits, usage_source = _delivery_usage_hits(
                name,
                set(hits),
                uctx=uctx,
                sd_cache=sd_cache,
                showdown_fetch=showdown_fetch,
                set_pct_floor=_TRICK_ROOM_SET_PCT_FLOOR,
            )
            usage_proven = bool(usage_hits)

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

        # Set% floor is hard membership. Self-protection only grades tier.
        if not usage_proven:
            attr = pair_notes.get(sid, "")
            reason = (
                f"{mechanism} learnset but Trick Room set% below "
                f"{_TRICK_ROOM_SET_PCT_FLOOR:g}"
            )
            if attr:
                reason += f" ({attr})"
            elif usage_source in {"champions", "none"}:
                reason += (
                    " (Champions and Showdown usage data show no Trick Room "
                    "on this species)"
                )
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=reason,
                    change_reason=(
                        f"usage below {_TRICK_ROOM_SET_PCT_FLOOR:g}% set% floor"
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


def _construct_tailwind_setter(
    category: str,
    sub_criteria: dict[str, Any],
    legal_pool: list[str],
    *,
    snap: dict[str, Any],
    uctx: _UsageCtx,
    showdown_fetch: LiveFetch | None,
    reference_compendium: dict[str, Any] | RoleConstructionDraft | None,
) -> RoleConstructionDraft:
    """Speed-control setter peer of Trick Room — opposite execution axis (go first).

    Provisional bars (reviewable): Prankster → Excellent; Spe≥floor → Good;
    usage-proven slow → Acceptable. Does NOT reuse weather's move→Good cap.
    """
    move_ids = frozenset(to_id(m) for m in sub_criteria["move_ids"])
    pool = _pool_index(legal_pool, snap)
    pool_ids = set(pool)
    prior = _ref_members(reference_compendium)
    members: list[CandidateEval] = []
    rejected: list[RejectedCandidate] = []
    notes = [
        "Excellent = Prankster + usage-proven Tailwind; Good = base Spe ≥ "
        f"{_TAILWIND_SPE_FLOOR} + usage-proven; Acceptable = usage-proven "
        "below Spe floor, or Excellent demoted by Showdown-discount / "
        "unproven-usage two-tier rule",
        _TAILWIND_DELIVERY_NOTE,
        "weather move+Prankster hard-caps at Good because ability setters sit "
        "above — Tailwind has no ability delivery, so Excellent remains "
        "reachable inside move-only grading (TR/redirection pattern)",
        "do not import Trick Room bulk≥210 membership — wrong axis (go-last survival)",
        "usage evidence prefers Champions in-game data where a row exists; "
        "Showdown is a fallback only for formes with no Champions row",
        "Prankster is blocked by Dark-types / Armor Tail / Queenly Majesty — "
        "noted in execution text, not an auto-reject",
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

    for sid, name in sorted(eligible.items(), key=lambda x: x[1]):
        hits = sorted(move_ids & set(resolve_learnset(snap, sid) or []))
        abs_map = _species_abilities(snap, sid)
        stats = _base_stats(snap, sid)
        mechanism = " / ".join(_move_display(snap, mid) for mid in hits)
        entry = uctx.entry_for(name)
        spe = int(stats.get("spe") or 0)
        has_prankster = "prankster" in abs_map

        if pair_usage.get(sid) is False:
            usage_proven = False
            usage_source = "mega attribution"
        else:
            usage_hits, usage_source = _delivery_usage_hits(
                name,
                set(hits),
                uctx=uctx,
                sd_cache=sd_cache,
                showdown_fetch=showdown_fetch,
            )
            usage_proven = bool(usage_hits)

        attr = pair_notes.get(sid, "")
        discounted = (
            "discounted" in attr
            or "stone-heuristic" in attr
            or "attributed to Mega" in attr
            or "mega-stone fallback" in attr
        )

        # Prankster is independent execution reinforce for admission (go-first).
        if not _admit_move_delivery(
            usage_proven=usage_proven, independent_reinforce=has_prankster
        ):
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=(
                        f"{mechanism} learnset but no usage evidence of Tailwind "
                        "delivery and no Prankster reinforce"
                        + (f" ({attr})" if attr else "")
                    ),
                    change_reason=(
                        "learnset-only without usage/Prankster"
                        if prior.get(sid)
                        else None
                    ),
                )
            )
            continue

        # Provisional tier grades (go-first axis).
        if has_prankster:
            tier, basis = "Excellent", "prankster_priority"
        elif spe >= _TAILWIND_SPE_FLOOR:
            tier, basis = "Good", "natural_speed"
        else:
            tier, basis = "Acceptable", "slow_manual"

        # Showdown-discount: Excellent → Acceptable; Good/Acceptable → reject.
        if discounted and usage_proven is False:
            demoted = _discount_outcome(
                "Excellent" if has_prankster else ("Good" if tier == "Good" else "Acceptable")
            )
            if demoted == "Acceptable" and has_prankster:
                tier, basis = "Acceptable", "usage_discounted_prankster"
            else:
                rejected.append(
                    RejectedCandidate(
                        species=name,
                        species_id=sid,
                        reason=(
                            f"{mechanism} learnset; usage discounted vs Mega form "
                            f"and mech tier {tier} has no Acceptable discount path"
                            + (f" ({attr})" if attr else "")
                        ),
                        change_reason=(
                            f"usage discount reject from {prior[sid]!r}"
                            if prior.get(sid)
                            else None
                        ),
                    )
                )
                continue
        elif discounted and has_prankster and usage_proven:
            # Discounted base with proven Mega path handled above; if still
            # discounted while usage_proven True, keep mech tier (independent).
            pass

        # Unproven usage: Prankster Excellent → Acceptable; else reject.
        if not usage_proven:
            if not has_prankster:
                rejected.append(
                    RejectedCandidate(
                        species=name,
                        species_id=sid,
                        reason=(
                            f"{mechanism} learnset but no usage evidence of Tailwind "
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
            tier, basis = "Acceptable", "acceptable_prankster_unproven"

        secondary_note, secondary_traits = _secondary_support_notes(
            entry, move_ids=_TAILWIND_SECONDARY_MOVES
        )
        secondary_move_ids = {to_id(t.name) for t in secondary_traits}
        has_fg = bool({"friendguard"} & set(abs_map))
        verified_secondary = has_fg or bool(secondary_traits)
        excellent_secondary = _excellent_secondary(
            has_friend_guard=has_fg,
            secondary_move_ids=secondary_move_ids,
            excellent_move_ids=_TAILWIND_EXCELLENT_SECONDARY_MOVES,
        )

        exec_note = f"base Spe={spe}"
        traits: list[ClaimedTrait] = [
            ClaimedTrait(
                name=mechanism,
                criterion="delivery",
                purpose_claimed="double ally Speed for four turns",
            )
        ]
        if has_prankster:
            exec_note += (
                "; Prankster +1 priority on Tailwind — blocked by Dark-types / "
                "Armor Tail / Queenly Majesty"
            )
            traits.append(
                ClaimedTrait(
                    name=abs_map["prankster"],
                    criterion="execution",
                    purpose_claimed="priority status Tailwind; go-first reliability",
                )
            )
        elif spe >= _TAILWIND_SPE_FLOOR:
            exec_note += (
                f"; natural Spe ≥ {_TAILWIND_SPE_FLOOR} provisional floor "
                "(no Prankster)"
            )
            traits.append(
                ClaimedTrait(
                    name=f"Spe {spe}",
                    criterion="execution",
                    purpose_claimed="natural Speed to land Tailwind before threats",
                )
            )
        else:
            exec_note += (
                f"; Spe {spe} below provisional floor {_TAILWIND_SPE_FLOOR}; "
                "lands Tailwind only if the opposing field is slower / disrupted"
            )
        if not usage_proven:
            exec_note += "; usage unproven — two-tier demotion applied"
        traits.extend(secondary_traits)

        prev_tier = prior.get(sid)
        change_reason = None
        if prev_tier and prev_tier != tier:
            change_reason = f"tier {prev_tier!r} → {tier!r}" + (
                f" ({attr})" if attr else ""
            )

        members.append(
            CandidateEval(
                species=name,
                species_id=sid,
                tier=tier,
                delivery_class="move_tailwind",
                mechanism=mechanism,
                criteria_notes={
                    "delivery": _TAILWIND_DELIVERY_NOTE,
                    "execution": exec_note,
                    "secondary_role": secondary_note,
                    "usage_proven": str(usage_proven),
                    "usage_source": usage_source,
                    "verified_secondary": str(verified_secondary),
                    "excellent_secondary": str(excellent_secondary),
                    "reinforce_class": "prankster" if has_prankster else "none",
                    "spe": str(spe),
                    "spe_floor_provisional": str(_TAILWIND_SPE_FLOOR),
                    "attribution": attr or "none",
                },
                claimed_traits=traits,
                reasoning=(
                    f"{mechanism} clears {tier} (basis={basis}, "
                    f"usage_proven={usage_proven}, prankster={has_prankster}, "
                    f"spe={spe})"
                    + (f" / {attr}" if attr else "")
                    + "."
                ),
                change_reason=change_reason,
                reinforce_class="prankster" if has_prankster else "none",
                excellence_basis=basis,
            )
        )

    _guard_pool(members, rejected, pool_ids)
    return _draft_with_tiers(category, sub_criteria, members, rejected, notes=notes)


def _screens_learnset_complete(hits: set[str]) -> bool:
    return "auroraveil" in hits or ("lightscreen" in hits and "reflect" in hits)


def _screens_wanted(*, usage_mids: set[str], has_clay: bool) -> bool:
    if "auroraveil" in usage_mids:
        return True
    if "lightscreen" in usage_mids and "reflect" in usage_mids:
        return True
    return has_clay and bool(usage_mids & _SCREENS_MOVE_IDS)


def _construct_screens_support(
    category: str,
    sub_criteria: dict[str, Any],
    legal_pool: list[str],
    *,
    snap: dict[str, Any],
    uctx: _UsageCtx,
    showdown_fetch: LiveFetch | None,
    reference_compendium: dict[str, Any] | RoleConstructionDraft | None,
) -> RoleConstructionDraft:
    """Screens Support — TW-shaped move-only setter; Veil is a snow-gated pathway."""
    move_ids = frozenset(to_id(m) for m in sub_criteria["move_ids"]) or _SCREENS_MOVE_IDS
    pool = _pool_index(legal_pool, snap)
    pool_ids = set(pool)
    prior = _ref_members(reference_compendium)
    members: list[CandidateEval] = []
    rejected: list[RejectedCandidate] = []
    notes = [
        "Excellent = Prankster + usage-proven screens at the wanted threshold; "
        f"Good = base Spe ≥ {_SCREENS_SPE_FLOOR} + usage-proven wanted; "
        "Acceptable = usage-proven below Spe floor, or Excellent demoted by "
        "Showdown-discount / unproven-usage two-tier rule",
        "wanted threshold = Aurora Veil OR dual Reflect+Light Screen OR "
        "Light Clay + ≥1 screen (same gate as _mechanisms / infer_role); "
        "lone LS/Reflect without Clay is incidental, not screens_support",
        "one category folds Dual Screens / Light Screen / Reflect / Aurora Veil "
        "— splitting does not narrow a distinct search",
        "Aurora Veil is a delivery pathway inside this category (snow-gated "
        "reliability note), not its own file",
        _SCREENS_DELIVERY_NOTE,
        "usage evidence prefers Champions in-game data where a row exists; "
        "Showdown is a fallback only for formes with no Champions row",
        "Prankster is blocked by Dark-types / Armor Tail / Queenly Majesty — "
        "noted in execution text, not an auto-reject",
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

    for sid, name in sorted(eligible.items(), key=lambda x: x[1]):
        ls = set(resolve_learnset(snap, sid) or [])
        hits = set(move_ids & ls)
        abs_map = _species_abilities(snap, sid)
        stats = _base_stats(snap, sid)
        entry = uctx.entry_for(name)
        spe = int(stats.get("spe") or 0)
        has_prankster = "prankster" in abs_map
        learnset_complete = _screens_learnset_complete(hits)

        if pair_usage.get(sid) is False:
            usage_proven = False
            usage_source = "mega attribution"
            usage_mids: set[str] = set()
            has_clay = False
        else:
            usage_mids, usage_source = _delivery_usage_hits(
                name,
                hits,
                uctx=uctx,
                sd_cache=sd_cache,
                showdown_fetch=showdown_fetch,
            )
            usage_proven = bool(usage_mids)
            has_clay = _usage_has_item(
                name,
                "lightclay",
                uctx=uctx,
                sd_cache=sd_cache,
                showdown_fetch=showdown_fetch,
            )

        wanted = _screens_wanted(usage_mids=usage_mids, has_clay=has_clay)
        independent = has_prankster and learnset_complete
        attr = pair_notes.get(sid, "")
        discounted = (
            "discounted" in attr
            or "stone-heuristic" in attr
            or "attributed to Mega" in attr
            or "mega-stone fallback" in attr
        )
        mechanism = " / ".join(
            _move_display(snap, mid) for mid in sorted(usage_mids or hits)
        )

        if not wanted and not independent:
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=(
                        f"{mechanism} learnset but not screens_support: "
                        "need usage-proven Aurora Veil, dual screens, or "
                        "Light Clay + a screen (lone LS/Reflect without Clay "
                        "is incidental)"
                        + (f" ({attr})" if attr else "")
                    ),
                    change_reason=(
                        "incidental screen without wanted threshold"
                        if prior.get(sid)
                        else None
                    ),
                )
            )
            continue

        if not _admit_move_delivery(
            usage_proven=usage_proven and wanted, independent_reinforce=independent
        ):
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=(
                        f"{mechanism} learnset but no usage evidence of screen "
                        "delivery and no Prankster+dual/Veil reinforce"
                        + (f" ({attr})" if attr else "")
                    ),
                    change_reason=(
                        "learnset-only without usage/Prankster"
                        if prior.get(sid)
                        else None
                    ),
                )
            )
            continue

        if has_prankster:
            tier, basis = "Excellent", "prankster_priority"
        elif spe >= _SCREENS_SPE_FLOOR:
            tier, basis = "Good", "natural_speed"
        else:
            tier, basis = "Acceptable", "slow_manual"

        if discounted and usage_proven is False:
            demoted = _discount_outcome(
                "Excellent" if has_prankster else (
                    "Good" if tier == "Good" else "Acceptable"
                )
            )
            if demoted == "Acceptable" and has_prankster:
                tier, basis = "Acceptable", "usage_discounted_prankster"
            else:
                rejected.append(
                    RejectedCandidate(
                        species=name,
                        species_id=sid,
                        reason=(
                            f"{mechanism} learnset; usage discounted vs Mega form "
                            f"and mech tier {tier} has no Acceptable discount path"
                            + (f" ({attr})" if attr else "")
                        ),
                        change_reason=(
                            f"usage discount reject from {prior[sid]!r}"
                            if prior.get(sid)
                            else None
                        ),
                    )
                )
                continue

        if not (usage_proven and wanted):
            if not has_prankster:
                rejected.append(
                    RejectedCandidate(
                        species=name,
                        species_id=sid,
                        reason=(
                            f"{mechanism} learnset but no usage evidence of "
                            f"wanted screens; two-tier demotion from {tier} "
                            "falls below Acceptable"
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
            tier, basis = "Acceptable", "acceptable_prankster_unproven"

        secondary_note, secondary_traits = _secondary_support_notes(
            entry, move_ids=_SCREENS_SECONDARY_MOVES
        )
        secondary_move_ids = {to_id(t.name) for t in secondary_traits}
        has_fg = bool({"friendguard"} & set(abs_map))
        verified_secondary = has_fg or bool(secondary_traits)
        excellent_secondary = _excellent_secondary(
            has_friend_guard=has_fg,
            secondary_move_ids=secondary_move_ids,
            excellent_move_ids=_SCREENS_EXCELLENT_SECONDARY_MOVES,
        )

        veil = "auroraveil" in (usage_mids or hits)
        sets_snow = bool(set(abs_map) & _SCREENS_SNOW_ABILITIES) or bool(
            ls & _SCREENS_SNOW_MOVES
        )
        exec_note = f"base Spe={spe}"
        traits: list[ClaimedTrait] = [
            ClaimedTrait(
                name=mechanism,
                criterion="delivery",
                purpose_claimed="ally physical/special damage reduction via screens",
            )
        ]
        if has_prankster:
            exec_note += (
                "; Prankster +1 priority on screens — blocked by Dark-types / "
                "Armor Tail / Queenly Majesty"
            )
            traits.append(
                ClaimedTrait(
                    name=abs_map["prankster"],
                    criterion="execution",
                    purpose_claimed="priority status screens; go-first reliability",
                )
            )
        elif spe >= _SCREENS_SPE_FLOOR:
            exec_note += (
                f"; natural Spe ≥ {_SCREENS_SPE_FLOOR} provisional floor "
                "(no Prankster)"
            )
            traits.append(
                ClaimedTrait(
                    name=f"Spe {spe}",
                    criterion="execution",
                    purpose_claimed="natural Speed to land screens before threats",
                )
            )
        else:
            exec_note += (
                f"; Spe {spe} below provisional floor {_SCREENS_SPE_FLOOR}; "
                "lands screens only if the opposing field is slower / disrupted"
            )
        if has_clay:
            exec_note += "; Light Clay extends screen duration"
        if veil:
            exec_note += "; Aurora Veil is snow-gated"
            if sets_snow:
                exec_note += " (self-supplies snow)"
            else:
                exec_note += " (depends on teammate snow)"
        if not (usage_proven and wanted):
            exec_note += "; usage unproven — two-tier demotion applied"
        traits.extend(secondary_traits)

        prev_tier = prior.get(sid)
        change_reason = None
        if prev_tier and prev_tier != tier:
            change_reason = f"tier {prev_tier!r} → {tier!r}" + (
                f" ({attr})" if attr else ""
            )

        members.append(
            CandidateEval(
                species=name,
                species_id=sid,
                tier=tier,
                delivery_class="move_screens",
                mechanism=mechanism,
                criteria_notes={
                    "delivery": _SCREENS_DELIVERY_NOTE,
                    "execution": exec_note,
                    "secondary_role": secondary_note,
                    "usage_proven": str(usage_proven and wanted),
                    "usage_source": usage_source,
                    "verified_secondary": str(verified_secondary),
                    "excellent_secondary": str(excellent_secondary),
                    "reinforce_class": "prankster" if has_prankster else "none",
                    "spe": str(spe),
                    "spe_floor_provisional": str(_SCREENS_SPE_FLOOR),
                    "light_clay": str(has_clay),
                    "aurora_veil": str(veil),
                    "attribution": attr or "none",
                },
                claimed_traits=traits,
                reasoning=(
                    f"{mechanism} clears {tier} (basis={basis}, "
                    f"usage_proven={usage_proven and wanted}, "
                    f"prankster={has_prankster}, spe={spe})"
                    + (f" / {attr}" if attr else "")
                    + "."
                ),
                change_reason=change_reason,
                reinforce_class="prankster" if has_prankster else "none",
                excellence_basis=basis,
            )
        )

    _guard_pool(members, rejected, pool_ids)
    return _draft_with_tiers(category, sub_criteria, members, rejected, notes=notes)


def _sleep_delivery_ids(snap: dict[str, Any]) -> frozenset[str]:
    """Core sleep set plus any other Status sleep move present in the snapshot."""
    found = set(_SLEEP_CORE_MOVES)
    for mid in _SLEEP_STATUS_MOVES:
        entry = (snap.get("moves") or {}).get(mid) or {}
        if not entry:
            continue
        if str(entry.get("category") or "") != "Status":
            continue
        found.add(mid)
    return frozenset(found)


def _sleep_pathway(
    *,
    delivery_hits: set[str],
    accuracy_reinforce: bool,
    has_trap: bool,
) -> tuple[str, str, str]:
    """Return (pathway_id, primary_move_id, label) for the best available delivery."""
    if "spore" in delivery_hits:
        return "P0", "spore", "Spore (100% immediate; new reliability class)"
    if "sleeppowder" in delivery_hits and accuracy_reinforce:
        return "P1", "sleeppowder", "Sleep Powder + accuracy reinforce"
    if "sleeppowder" in delivery_hits:
        return "P2", "sleeppowder", "Sleep Powder (no accuracy reinforce)"
    imperfect = sorted(
        mid for mid in delivery_hits if mid in _SLEEP_IMMEDIATE and mid != "spore"
    )
    # Hypnosis-class (includes Sing / Dark Void / etc. when legal).
    hypno_class = [m for m in imperfect if m != "sleeppowder"]
    if hypno_class and accuracy_reinforce:
        mid = "hypnosis" if "hypnosis" in hypno_class else hypno_class[0]
        return "P2", mid, f"{mid} + accuracy reinforce"
    if hypno_class:
        mid = "hypnosis" if "hypnosis" in hypno_class else hypno_class[0]
        return "P3", mid, f"bare {mid}"
    if "yawn" in delivery_hits:
        label = "Yawn + trapping" if has_trap else "Yawn (delayed; no trap)"
        return "P4", "yawn", label
    mid = next(iter(sorted(delivery_hits)))
    return "P?", mid, f"unclassified sleep delivery ({mid})"


def _construct_sleep_status_spreader(
    category: str,
    sub_criteria: dict[str, Any],
    legal_pool: list[str],
    *,
    snap: dict[str, Any],
    uctx: _UsageCtx,
    showdown_fetch: LiveFetch | None,
    reference_compendium: dict[str, Any] | RoleConstructionDraft | None,
) -> RoleConstructionDraft:
    """Sleep status role — ADR-015 2026-07-29f mechanism-dependent bars (provisional)."""
    delivery_ids = _sleep_delivery_ids(snap)
    pool = _pool_index(legal_pool, snap)
    pool_ids = set(pool)
    prior = _ref_members(reference_compendium)
    members: list[CandidateEval] = []
    rejected: list[RejectedCandidate] = []

    # Presence check for reliability classes (construction notes, not fake rejects).
    legal_learners: dict[str, int] = {mid: 0 for mid in sorted(delivery_ids)}
    for sid in pool:
        ls = set(resolve_learnset(snap, sid) or [])
        for mid in delivery_ids:
            if mid in ls:
                legal_learners[mid] = legal_learners.get(mid, 0) + 1

    spore_learners = legal_learners.get("spore", 0)
    spore_absent = spore_learners == 0
    notes = [
        "Ranking is pathway-first by execution reliability (accuracy / whether "
        "sleep actually lands). Spe is secondary for imperfect immediate "
        "delivery (P2/P3): base Spe ≥ floor OR a speed-boosting ability "
        "(Chlorophyll / Swift Swim / Sand Rush / Slush Rush / Unburden / "
        "Speed Boost) clears the Spe bar; failing it demotes one rank. "
        "P1 (near-perfect accuracy) does not Spe-demote — ADR-015: Spe/"
        "bulk matter less when the accuracy roll is already near-guaranteed. "
        "P4 Yawn ignores Spe entirely.",
        "Natural pathway order: P0 Spore (100% immediate) > P1 Sleep Powder+"
        "accuracy reinforce > P2 Sleep Powder bare / Hypnosis+reinforce > "
        "P3 bare Hypnosis/Sing-class > P4 Yawn (delayed; switch-window).",
        "Excellent is reserved for Spore (P0). When Spore is absent from the "
        "legal pool, ADR-019 entire-class gap: push remaining pathways up one "
        "tier (P1→Excellent, P2→Good, P3→Acceptable) so Excellent is not "
        "left empty while a worse pathway occupies Good.",
        "Bare P4 (Yawn, no trapping) is below P3 and is rejected — only three "
        "tiers exist, so keeping it co-equal with P3 in Acceptable would hide "
        "the reliability gap. P4+Shadow Tag (or other trap) closes the switch "
        "window and stays Acceptable (elevated within Yawn only; still never "
        "outranks P2).",
        "Helping Hand excluded from sleep secondary excellence",
        "usage evidence prefers Champions in-game data where a row exists",
        (
            "Spore reliability class ABSENT — push-up ACTIVE"
            if spore_absent
            else f"Spore learners_in_pool={spore_learners} — no push-up"
        ),
    ]
    for mid, n in sorted(legal_learners.items()):
        acc = _SLEEP_ACCURACY.get(mid, "?")
        notes.append(
            f"delivery availability: {mid} learners_in_pool={n} "
            f"(catalog accuracy={acc})"
        )
        if n == 0 and mid in ("spore", "darkvoid"):
            notes.append(
                f"{mid} reliability class ABSENT from current legal pool "
                "(ADR-019 entire-class gap)"
            )

    sd_cache: dict[str, dict[str, Any] | None] = {}
    eligible = {
        sid: name
        for sid, name in pool.items()
        if delivery_ids & set(resolve_learnset(snap, sid) or [])
    }

    pair_usage, pair_notes, _stone_used = _mega_usage_attribution(
        eligible,
        delivery_ids,
        snap=snap,
        uctx=uctx,
        sd_cache=sd_cache,
        showdown_fetch=showdown_fetch,
        notes=notes,
    )

    for sid, name in sorted(eligible.items(), key=lambda x: x[1]):
        ls = set(resolve_learnset(snap, sid) or [])
        delivery_hits = set(delivery_ids & ls)
        abs_map = _species_abilities(snap, sid)
        stats = _base_stats(snap, sid)
        entry = uctx.entry_for(name)
        spe = int(stats.get("spe") or 0)
        bulk = sum(int(stats.get(k) or 0) for k in ("hp", "def", "spd"))

        # Exhaustive kit sweep (ADR-019) — every candidate, not opportunistic.
        kit_accuracy = sorted(set(abs_map) & _SLEEP_ACCURACY_ABILITIES)
        kit_trap = sorted(set(abs_map) & _SLEEP_TRAP_ABILITIES)
        kit_speed = sorted(set(abs_map) & _SLEEP_SPEED_ABILITIES)
        coil_learnset = "coil" in ls
        coil_usage = bool(entry) and _entry_has_move(entry, "coil")
        accuracy_reinforce = bool(kit_accuracy) or coil_usage
        has_trap = bool(kit_trap)

        pathway, primary_mid, pathway_label = _sleep_pathway(
            delivery_hits=delivery_hits,
            accuracy_reinforce=accuracy_reinforce,
            has_trap=has_trap,
        )
        # Bare P4 (Yawn, no trap) is below P3 — reject rather than share Acceptable.
        if pathway == "P4" and not has_trap:
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=(
                        f"{_move_display(snap, primary_mid)} ({pathway_label}): "
                        "bare Yawn without trapping is below P3 reliability and "
                        "is rejected (only P4+trap closes the switch-window "
                        "enough to keep Acceptable)"
                    ),
                    change_reason=(
                        "bare yawn rejected below P3" if prior.get(sid) else None
                    ),
                )
            )
            continue

        mechanism = _move_display(snap, primary_mid)
        # If multiple deliveries, list them for transparency.
        if len(delivery_hits) > 1:
            mechanism = " / ".join(
                _move_display(snap, mid) for mid in sorted(delivery_hits)
            )

        if pair_usage.get(sid) is False:
            usage_proven = False
            usage_source = "mega attribution"
        else:
            usage_hits, usage_source = _delivery_usage_hits(
                name,
                set(delivery_hits),
                uctx=uctx,
                sd_cache=sd_cache,
                showdown_fetch=showdown_fetch,
            )
            usage_proven = bool(usage_hits)

        # Pathway-matched independent reinforce for admission.
        if pathway == "P4":
            independent = has_trap
        elif pathway in {"P1", "P2", "P0"}:
            independent = accuracy_reinforce
        else:
            independent = accuracy_reinforce  # P3 bare — reinforce uncommon

        attr = pair_notes.get(sid, "")
        discounted = (
            "discounted" in attr
            or "stone-heuristic" in attr
            or "attributed to Mega" in attr
            or "mega-stone fallback" in attr
        )

        if not _admit_move_delivery(
            usage_proven=usage_proven, independent_reinforce=independent
        ):
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=(
                        f"{mechanism} learnset ({pathway_label}) but no usage "
                        "evidence of sleep delivery and no pathway-matched reinforce"
                        + (f" ({attr})" if attr else "")
                    ),
                    change_reason=(
                        "learnset-only without usage/reinforce"
                        if prior.get(sid)
                        else None
                    ),
                )
            )
            continue

        spe_applies = primary_mid in _SLEEP_IMMEDIATE
        has_speed_ability = bool(kit_speed)
        # Base Spe floor OR speed-boosting ability (Chlorophyll etc.) — ability
        # presence is the check; weather uptime is noted, not separately gated.
        spe_ok = (not spe_applies) or spe >= _SLEEP_SPE_FLOOR or has_speed_ability
        if not spe_applies:
            spe_skip_note = (
                "Speed ignored for ranking: Yawn delayed delivery"
            )
        elif spe >= _SLEEP_SPE_FLOOR:
            spe_skip_note = f"Spe {spe} ≥ {_SLEEP_SPE_FLOOR}"
        elif has_speed_ability:
            spe_skip_note = (
                f"Spe {spe} < {_SLEEP_SPE_FLOOR} but speed ability "
                f"{'/'.join(abs_map[a] for a in kit_speed)} clears Spe bar "
                "(condition-dependent in battle)"
            )
        else:
            spe_skip_note = (
                f"Spe {spe} < {_SLEEP_SPE_FLOOR} and no speed-boosting ability "
                "— demote one rank on imperfect immediate pathways (P2/P3)"
            )

        # Effective accuracy after reinforce (Compound Eyes ≈ ×1.3).
        base_acc = _SLEEP_ACCURACY.get(primary_mid, 100)
        if "noguard" in kit_accuracy:
            eff_acc = 100
        elif "compoundeyes" in kit_accuracy:
            eff_acc = min(100, int(base_acc * 1.3))
        elif coil_usage:
            # Coil +1 accuracy stage ≈ ×4/3 on next moves — approximate for notes.
            eff_acc = min(100, int(base_acc * 4 / 3))
        else:
            eff_acc = base_acc
        bulk_relevant = eff_acc < 100
        bulk_note = (
            f"bulk HP+Def+SpD={bulk} (miss-insurance; acc≈{eff_acc}%)"
            if bulk_relevant
            else f"bulk HP+Def+SpD={bulk} (miss-insurance skipped: eff acc≈{eff_acc}%)"
        )

        # Pathway reliability rank (lower = more reliable execution).
        # Bare P4 already rejected above; P4+trap elevates to P3 rank only.
        pathway_rank = {
            "P0": 0,
            "P1": 1,
            "P2": 2,
            "P3": 3,
            "P4": 3,  # trap-only survivors; equals P3 floor, never above P2
        }.get(pathway, 5)
        if pathway == "P4":
            basis = "yawn_trap"
        elif pathway == "P0":
            basis = "spore_immediate"
        elif pathway == "P1":
            basis = "sleeppowder_accuracy"
        elif pathway == "P2":
            basis = "p2_mid_accuracy"
        elif pathway == "P3":
            basis = "bare_hypnosis"
        else:
            basis = "unclassified"

        # Spore absent → push remaining pathways up one rank (Excellent not empty).
        effective_rank = pathway_rank - 1 if spore_absent else pathway_rank
        # P2/P3 Spe demotion: imperfect immediate sleep needs Spe or speed ability.
        # P1 skipped (near-perfect accuracy — ADR-015). P4 Spe-irrelevant.
        if pathway in {"P2", "P3"} and not spe_ok:
            effective_rank += 1
            basis = f"{basis}_slow"
        if effective_rank <= 0:
            tier = "Excellent"
        elif effective_rank == 1:
            tier = "Good"
        elif effective_rank <= 3:
            tier = "Acceptable"
        else:
            # P2/P3 that were already Acceptable and then Spe-demoted fall off.
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=(
                        f"{mechanism} ({pathway_label}): pathway clears only "
                        f"Acceptable after push-up, then Spe bar fails "
                        f"(Spe {spe}, speed_abil={kit_speed or ['none']}) — "
                        "below Acceptable"
                    ),
                )
            )
            continue
        if spore_absent and pathway != "P0":
            basis = f"pushup_{basis}"

        # Discount / unproven demotion: Excellent → Acceptable; else reject.
        if discounted and not usage_proven:
            if tier == "Excellent":
                demoted = _discount_outcome("Excellent")
                assert demoted == "Acceptable"
                tier, basis = "Acceptable", f"discounted_{basis}"
            else:
                rejected.append(
                    RejectedCandidate(
                        species=name,
                        species_id=sid,
                        reason=(
                            f"{mechanism} usage discounted vs Mega; mech {tier} "
                            "has no Acceptable discount path"
                            + (f" ({attr})" if attr else "")
                        ),
                    )
                )
                continue
        elif not usage_proven:
            if tier == "Excellent":
                tier, basis = "Acceptable", f"unproven_{basis}"
            else:
                rejected.append(
                    RejectedCandidate(
                        species=name,
                        species_id=sid,
                        reason=(
                            f"{mechanism} ({pathway_label}) learnset but no usage; "
                            f"two-tier demotion from {tier} falls below Acceptable"
                            + (f" ({attr})" if attr else "")
                        ),
                    )
                )
                continue

        secondary_note, secondary_traits = _secondary_support_notes(
            entry, move_ids=_SLEEP_SECONDARY_MOVES
        )
        secondary_move_ids = {to_id(t.name) for t in secondary_traits}
        has_fg = bool({"friendguard"} & set(abs_map))
        verified_secondary = has_fg or bool(secondary_traits)
        excellent_secondary = _excellent_secondary(
            has_friend_guard=has_fg,
            secondary_move_ids=secondary_move_ids,
            excellent_move_ids=_SLEEP_EXCELLENT_SECONDARY_MOVES,
        )

        kit_sweep = (
            f"accuracy_abil={kit_accuracy or ['none']}; "
            f"trap={kit_trap or ['none']}; "
            f"speed_abil={kit_speed or ['none']}; "
            f"coil_learnset={coil_learnset}; coil_usage={coil_usage}"
        )
        exec_parts = [
            pathway_label,
            spe_skip_note,
            bulk_note,
            kit_sweep,
        ]
        if not usage_proven:
            exec_parts.append("usage unproven — demotion applied")
        exec_note = "; ".join(exec_parts)

        traits: list[ClaimedTrait] = [
            ClaimedTrait(
                name=mechanism,
                criterion="delivery",
                purpose_claimed="inflict sleep on an opposing Pokémon",
            )
        ]
        for aid in kit_accuracy:
            traits.append(
                ClaimedTrait(
                    name=abs_map[aid],
                    criterion="execution",
                    purpose_claimed="accuracy reinforce on imperfect sleep delivery",
                )
            )
        if coil_usage:
            traits.append(
                ClaimedTrait(
                    name="Coil",
                    criterion="execution",
                    purpose_claimed="usage-proven +1 accuracy stage among Coil effects",
                )
            )
        for aid in kit_trap:
            purpose = (
                "closes Yawn switch-window"
                if pathway == "P4"
                else "trap present but ignored (not Yawn pathway)"
            )
            traits.append(
                ClaimedTrait(
                    name=abs_map[aid],
                    criterion="execution",
                    purpose_claimed=purpose,
                )
            )
        traits.extend(secondary_traits)

        prev_tier = prior.get(sid)
        change_reason = None
        if prev_tier and prev_tier != tier:
            change_reason = f"tier {prev_tier!r} → {tier!r}" + (
                f" ({attr})" if attr else ""
            )

        members.append(
            CandidateEval(
                species=name,
                species_id=sid,
                tier=tier,
                delivery_class=f"sleep_{pathway.lower()}",
                mechanism=mechanism,
                criteria_notes={
                    "delivery": pathway_label,
                    "execution": exec_note,
                    "secondary_role": secondary_note,
                    "usage_proven": str(usage_proven),
                    "usage_source": usage_source,
                    "verified_secondary": str(verified_secondary),
                    "excellent_secondary": str(excellent_secondary),
                    "pathway": pathway,
                    "pathway_rank": str(pathway_rank),
                    "effective_rank": str(effective_rank),
                    "spore_absent_pushup": str(spore_absent),
                    "primary_move": primary_mid,
                    "spe_applies": str(spe_applies),
                    "spe": str(spe),
                    "spe_ok": str(spe_ok),
                    "speed_abilities": ",".join(kit_speed) or "none",
                    "eff_accuracy": str(eff_acc),
                    "kit_sweep": kit_sweep,
                    "attribution": attr or "none",
                },
                claimed_traits=traits,
                reasoning=(
                    f"{mechanism} clears {tier} (pathway={pathway}, basis={basis}, "
                    f"usage_proven={usage_proven})"
                    + (f" / {attr}" if attr else "")
                    + "."
                ),
                change_reason=change_reason,
                reinforce_class=(
                    "accuracy"
                    if accuracy_reinforce
                    else ("trap" if has_trap and pathway == "P4" else "none")
                ),
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


def load_role_category(
    category: str,
    condition: str = "",
    *,
    roles_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Shipped compendium entry for a role, or None when no entry has been built.

    Conditioned roles pass their condition separately (weather_setter + "Rain"),
    matching how construction names the file.
    """
    roles_dir = roles_dir or DEFAULT_ROLES_DIR
    return load_prior_compendium(
        roles_dir / _roles_filename(category, {"condition": condition})
    )


def role_candidates(
    category: str,
    condition: str = "",
    *,
    roles_dir: Path | None = None,
) -> list[str]:
    """Species admitted to a role, best tier first. Empty when the role has no entry."""
    evidence = role_category_evidence(category, condition, roles_dir=roles_dir)
    return [row.species for row in evidence.species]


@dataclass(frozen=True)
class CompendiumRoleEvidence:
    """One reverse lookup result, kept distinct by evidence strength."""

    species: str
    role_id: str
    category: str
    condition: str
    tier: str | None
    mechanism: str | None
    source_file: str
    reason: str | None = None


@dataclass(frozen=True)
class ReverseCompendiumEvidence:
    exact: tuple[CompendiumRoleEvidence, ...] = ()
    species: tuple[CompendiumRoleEvidence, ...] = ()
    rejected: tuple[CompendiumRoleEvidence, ...] = ()


def _strategic_role_id(category: str, condition: str) -> str:
    if category == "weather_setter" and condition:
        return f"{to_id(condition)}_setter"
    return category.strip().lower().replace("-", "_").replace(" ", "_")


def _entry_evidence(raw: dict[str, Any], source_file: str) -> ReverseCompendiumEvidence:
    category = str(raw.get("category") or "")
    condition = str(raw.get("condition") or "")
    role_id = _strategic_role_id(category, condition)
    candidates = {
        to_id(str(row.get("species_id") or row.get("species") or "")): row
        for row in raw.get("candidates") or []
    }
    admitted: list[CompendiumRoleEvidence] = []
    for tier in ROLE_TIER_ORDER:
        for species in (raw.get("tiers") or {}).get(tier) or []:
            candidate = candidates.get(to_id(str(species))) or {}
            admitted.append(
                CompendiumRoleEvidence(
                    species=str(candidate.get("species") or species),
                    role_id=role_id,
                    category=category,
                    condition=condition,
                    tier=tier,
                    mechanism=str(candidate.get("mechanism") or "") or None,
                    source_file=source_file,
                )
            )
    rejected = tuple(
        CompendiumRoleEvidence(
            species=str(candidate.get("species") or candidate.get("species_id") or ""),
            role_id=role_id,
            category=category,
            condition=condition,
            tier=None,
            mechanism=str(candidate.get("mechanism") or "") or None,
            source_file=source_file,
            reason=str(candidate.get("reason") or ""),
        )
        for candidate in raw.get("considered_rejected") or []
    )
    return ReverseCompendiumEvidence(species=tuple(admitted), rejected=rejected)


def role_category_evidence(
    category: str,
    condition: str = "",
    *,
    roles_dir: Path | None = None,
) -> ReverseCompendiumEvidence:
    """Forward role evidence; no concrete build exists to promote into exact."""
    root = roles_dir or DEFAULT_ROLES_DIR
    path = root / _roles_filename(category, {"condition": condition})
    raw = load_prior_compendium(path)
    return _entry_evidence(raw, path.name) if raw is not None else ReverseCompendiumEvidence()


def reverse_compendium_evidence(
    species: str,
    *,
    moves: list[str] | tuple[str, ...] = (),
    ability: str | None = None,
    roles_dir: Path | None = None,
) -> ReverseCompendiumEvidence:
    """Find exact-build, species-only, and rejected compendium evidence.

    Exact means the candidate's named delivery mechanism is present in this
    build. Other positive membership remains species evidence; it is never
    promoted across a different set.
    """
    root = roles_dir or DEFAULT_ROLES_DIR
    sid = to_id(species)
    present = {to_id(m) for m in moves}
    if ability:
        present.add(to_id(ability))
    exact: list[CompendiumRoleEvidence] = []
    species_only: list[CompendiumRoleEvidence] = []
    rejected: list[CompendiumRoleEvidence] = []
    for path in sorted(root.glob("*.v1.json")):
        rows = _entry_evidence(json.loads(path.read_text()), path.name)
        for row in rows.species:
            if to_id(row.species) != sid:
                continue
            (
                exact
                if row.mechanism and to_id(row.mechanism) in present
                else species_only
            ).append(row)
        for row in rows.rejected:
            if to_id(row.species) != sid:
                continue
            rejected.append(row)
    return ReverseCompendiumEvidence(
        exact=tuple(exact),
        species=tuple(species_only),
        rejected=tuple(rejected),
    )


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
