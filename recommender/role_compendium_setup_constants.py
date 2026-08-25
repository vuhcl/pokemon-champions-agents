"""Setup-attacker constants shared by role_compendium and role_compendium_setup."""

from __future__ import annotations

from pathlib import Path

from recommender.matchup import _CHARGE_MOVES, _RECHARGE_MOVES
from recommender.support_needs import _OFFENSIVE_PRIORITY_MOVES, _SELF_HEAL_MOVES

ROOT = Path(__file__).resolve().parents[1]

_SETUP_PRESENCE_SET_PCT_FLOOR = 0.1
# DD-only: real hole (0.390, 1.363]; 0.5% and 1.0% admit the same set (Sleep pattern).
_DD_SETUP_PRESENCE_FLOOR = 1.0

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
_BODY_PRESS_EVS = {"hp": 4, "atk": 0, "def": 32, "spa": 0, "spd": 0, "spe": 32}
_DEF_PAYOFF_DELTA_EPS = 1e-6
