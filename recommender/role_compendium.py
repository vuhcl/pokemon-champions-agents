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
# Pikalytics tournament team-usage pairs (Reg M-B). Not merged with Pokemon-Zone.
_PIKALYTICS_PAIRS_PATH = (
    ROOT / "data" / "team-composition" / "champions-reg-mb.pikalytics-team-usage.v1.json"
)
# Damaging moves whose Champions calc target is allAdjacent / allAdjacentFoes.
# Expanding Force omitted: spread only under Psychic Terrain (not modeled here).
# Source: @smogon/calc Generations.get(0) move targets (item 7 discovery).
_SPREAD_DAMAGE_MOVE_IDS = frozenset(
    {
        "aircutter",
        "blizzard",
        "boomburst",
        "breakingswipe",
        "brutalswing",
        "bulldoze",
        "burningjealousy",
        "clangingscales",
        "dazzlinggleam",
        "discharge",
        "earthquake",
        "electroweb",
        "eruption",
        "explosion",
        "heatwave",
        "hypervoice",
        "icywind",
        "lavaplume",
        "makeitrain",
        "matchagotcha",
        "mistyexplosion",
        "mortalspin",
        "muddywater",
        "paraboliccharge",
        "petalblizzard",
        "rockslide",
        "selfdestruct",
        "sludgewave",
        "snarl",
        "sparklingaria",
        "strugglebug",
        "surf",
        "waterspout",
    }
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
# Damaging moves with Champions calc target allAdjacent (hits allies).
# Source: @smogon/calc Generations.get(0) — item 7 Part B Step 1.
_ALLY_HIT_DAMAGE_MOVE_IDS = frozenset(
    {
        "boomburst",
        "brutalswing",
        "bulldoze",
        "discharge",
        "earthquake",
        "explosion",
        "lavaplume",
        "mistyexplosion",
        "paraboliccharge",
        "petalblizzard",
        "selfdestruct",
        "sludgewave",
        "sparklingaria",
        "surf",
    }
)
# Ally-hit subset that are sound moves (calc flags.sound) — Soundproof applies.
_SOUND_ALLY_HIT_MOVE_IDS = frozenset({"boomburst", "sparklingaria"})
# Type → ally protection fragments (abilities/types from data/abilities + type chart).
_ALLY_HIT_TYPE_PROTECTIONS: dict[str, str] = {
    "Ground": (
        "Flying-type / Levitate / Earth Eater (absorb/heal); "
        "Gravity/Iron Ball can nullify Flying/Levitate immunity"
    ),
    "Water": "Water Absorb / Dry Skin / Storm Drain",
    "Electric": "Volt Absorb / Motor Drive / Lightning Rod",
    "Fire": "Flash Fire / Well-Baked Body",
    "Grass": "Sap Sipper",
    "Poison": "Steel-type",
    "Normal": "Ghost-type",
    # Dark / Fairy: no type-specific immunities beyond universal.
}
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
# Champions-legal drain (Showdown drain: [a,b]). Absolute HP healed is in
# raw.recovery — gated here because Shell Bell also fills that field.
_DRAIN_MOVES = frozenset(
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
    from recommender.role_compendium_usage import (
        _hits_clear_set_pct_floor,
        _mega_usage_attribution,
        _move_display,
        _move_pct,
    )

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
    from recommender.role_compendium_usage import (
        _delivery_usage_hits,
        _hits_clear_set_pct_floor,
        _mega_usage_attribution,
        _move_display,
        _species_types,
    )

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
    from recommender.role_compendium_usage import (
        _delivery_usage_hits,
        _hits_clear_set_pct_floor,
        _mega_usage_attribution,
        _move_display,
    )

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


def _screens_mech_dual(hits: set[str], abs_map: dict[str, str]) -> bool:
    """LS+Reflect learnset, or Veil + Snow Warning (not Chilly Reception)."""
    if "lightscreen" in hits and "reflect" in hits:
        return True
    return "auroraveil" in hits and bool(set(abs_map) & _SCREENS_SNOW_ABILITIES)


def _screens_dual_usage(
    name: str,
    hits: set[str],
    abs_map: dict[str, str],
    *,
    uctx: _UsageCtx,
    sd_cache: dict[str, dict[str, Any] | None],
    showdown_fetch: LiveFetch | None,
) -> tuple[str | None, set[str]]:
    """Usage-proven dual path at Screens' 2.3% floor. Same-row for LS+Reflect."""
    from recommender.role_compendium_usage import (
        _hits_clear_set_pct_floor,
        _same_row_both_moves,
    )

    paths: list[str] = []
    mids: set[str] = set()
    kw = dict(uctx=uctx, sd_cache=sd_cache, showdown_fetch=showdown_fetch)
    if "lightscreen" in hits and "reflect" in hits:
        if _same_row_both_moves(name, "lightscreen", "reflect", **kw) and (
            _hits_clear_set_pct_floor(
                name,
                {"lightscreen", "reflect"},
                floor=_USAGE_SET_PCT_FLOOR,
                require_all=True,
                **kw,
            )
        ):
            paths.append("ls+reflect")
            mids.update({"lightscreen", "reflect"})
    if "auroraveil" in hits and "snowwarning" in abs_map:
        if _hits_clear_set_pct_floor(
            name, {"auroraveil"}, floor=_USAGE_SET_PCT_FLOOR, **kw
        ):
            paths.append("veil+snowwarning")
            mids.add("auroraveil")
    return ("+".join(paths) if paths else None), mids


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
    from recommender.role_compendium_usage import (
        _delivery_usage_hits,
        _hits_clear_set_pct_floor,
        _mega_usage_attribution,
        _move_display,
        _usage_has_item,
    )

    move_ids = frozenset(to_id(m) for m in sub_criteria["move_ids"]) or _SCREENS_MOVE_IDS
    pool = _pool_index(legal_pool, snap)
    pool_ids = set(pool)
    prior = _ref_members(reference_compendium)
    members: list[CandidateEval] = []
    rejected: list[RejectedCandidate] = []
    notes = [
        "Excellent = dual-screen usage + Prankster; Good = dual-screen usage + "
        f"base Spe ≥ {_SCREENS_SPE_FLOOR} (no Prankster); Acceptable = dual "
        "below Spe floor, or single-screen + Prankster (Whimsicott)",
        "dual-screen = usage-proven Reflect AND Light Screen (same-row, both "
        f"≥ {_USAGE_SET_PCT_FLOOR:g}% set%) OR Aurora Veil ≥ "
        f"{_USAGE_SET_PCT_FLOOR:g}% plus Snow Warning (not Chilly Reception)",
        "Light Clay + a lone screen is not membership (Florges / Rotom-Wash); "
        "Veil without Snow Warning is not dual (Avalugg)",
        "Meowstic Excellent is male only (Prankster); female has Competitive",
        "one category folds Dual Screens / Light Screen / Reflect / Aurora Veil "
        "— splitting does not narrow a distinct search",
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

    _pair_usage, pair_notes, _stone_used = _mega_usage_attribution(
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
        attr = pair_notes.get(sid, "")
        dual_path, dual_mids = _screens_dual_usage(
            name,
            hits,
            abs_map,
            uctx=uctx,
            sd_cache=sd_cache,
            showdown_fetch=showdown_fetch,
        )
        usage_mids, usage_source = _delivery_usage_hits(
            name,
            hits,
            uctx=uctx,
            sd_cache=sd_cache,
            showdown_fetch=showdown_fetch,
        )
        has_clay = _usage_has_item(
            name,
            "lightclay",
            uctx=uctx,
            sd_cache=sd_cache,
            showdown_fetch=showdown_fetch,
        )
        single_prankster = (
            dual_path is None
            and has_prankster
            and bool(usage_mids & hits)
        )
        qualify_mids = dual_mids if dual_path else (usage_mids & hits)
        mechanism = " / ".join(
            _move_display(snap, mid) for mid in sorted(qualify_mids or hits)
        )

        if dual_path is None and not single_prankster:
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=(
                        f"{mechanism} learnset but not screens_support: need "
                        "usage-proven dual LS+Reflect (same-row), Veil+Snow "
                        "Warning, or single-screen + Prankster"
                        + (f" ({attr})" if attr else "")
                    ),
                    change_reason=(
                        "failed dual/Prankster usage gate"
                        if prior.get(sid)
                        else None
                    ),
                )
            )
            continue

        if dual_path and has_prankster:
            tier, basis = "Excellent", "prankster_priority"
        elif dual_path and spe >= _SCREENS_SPE_FLOOR:
            tier, basis = "Good", "natural_speed"
        elif dual_path:
            tier, basis = "Acceptable", "slow_manual"
        else:
            tier, basis = "Acceptable", "prankster_single_screen"

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

        veil = "auroraveil" in (qualify_mids or hits)
        sets_snow = "snowwarning" in abs_map
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
                f"; natural Spe ≥ {_SCREENS_SPE_FLOOR} floor (no Prankster)"
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
                f"; Spe {spe} below floor {_SCREENS_SPE_FLOOR}; "
                "lands screens only if the opposing field is slower / disrupted"
            )
        if has_clay:
            exec_note += "; Light Clay extends screen duration"
        if veil:
            exec_note += "; Aurora Veil is snow-gated"
            if sets_snow:
                exec_note += " (Snow Warning)"
            else:
                exec_note += " (no Snow Warning — not dual)"
        if dual_path:
            exec_note += f"; dual_path={dual_path}"
        elif single_prankster:
            exec_note += "; single-screen + Prankster"
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
                    "usage_proven": "True",
                    "usage_source": usage_source,
                    "verified_secondary": str(verified_secondary),
                    "excellent_secondary": str(excellent_secondary),
                    "reinforce_class": "prankster" if has_prankster else "none",
                    "spe": str(spe),
                    "spe_floor_provisional": str(_SCREENS_SPE_FLOOR),
                    "light_clay": str(has_clay),
                    "aurora_veil": str(veil),
                    "dual_path": dual_path or "single_prankster",
                    "attribution": attr or "none",
                },
                claimed_traits=traits,
                reasoning=(
                    f"{mechanism} clears {tier} (basis={basis}, "
                    f"dual_path={dual_path or 'single_prankster'}, "
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
    from recommender.role_compendium_usage import (
        _delivery_usage_hits,
        _mega_usage_attribution,
        _move_display,
    )

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


def __getattr__(name: str) -> Any:
    if name in _USAGE_REEXPORTS:
        import recommender.role_compendium_usage as _usage

        return getattr(_usage, name)
    if name in _SETUP_REEXPORTS:
        import recommender.role_compendium_setup as _setup

        return getattr(_setup, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
