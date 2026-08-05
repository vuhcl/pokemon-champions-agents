"""Phase B: apply three-axis tags to remaining abilities.

Target vocabulary in this file may still use legacy 'other' in places;
always finish with: uv run python scripts/extract_abilities/retarget_ally_opponent.py
(npm run extract:abilities chains extract → apply_phase_b → retarget).

Run alone: uv run python scripts/extract_abilities/apply_phase_b.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "data" / "abilities" / "all.v1.json"
REPORT = ROOT / "artifacts" / "ability_phase_b_flags.md"


def T(target: str, activation: str, purpose: str) -> dict[str, str]:
    return {"target": target, "activation": activation, "purpose": purpose}


def entry(
    *tags: dict[str, str],
    field: dict | None = None,
    composed_of: list[str] | None = None,
    provisional_purpose: bool = False,
) -> dict:
    out: dict = {"tags": list(tags)}
    if field is not None:
        out["field"] = field
    if composed_of is not None:
        out["composed_of"] = composed_of
    if provisional_purpose:
        out["provisional_purpose"] = True
    return out


# Weather/terrain FieldSpec helpers (match ABILITY_TO_FIELD / support_needs vocab).
def rain() -> dict:
    return {"weather": "Rain", "gameType": "Doubles"}


def sun() -> dict:
    return {"weather": "Sun", "gameType": "Doubles"}


def sand() -> dict:
    return {"weather": "Sand", "gameType": "Doubles"}


def snow() -> dict:
    return {"weather": "Snow", "gameType": "Doubles"}


def electric() -> dict:
    return {"terrain": "Electric", "gameType": "Doubles"}


def grassy() -> dict:
    return {"terrain": "Grassy", "gameType": "Doubles"}


def misty() -> dict:
    return {"terrain": "Misty", "gameType": "Doubles"}


def psychic() -> dict:
    return {"terrain": "Psychic", "gameType": "Doubles"}


# Absorb-style: immunity (unconditional support) + on-hit heal (triggered support)
def absorb() -> dict:
    return entry(T("self", "unconditional", "support"), T("self", "triggered", "support"))


# Redirect-absorb with stat boost (Flash Fire / Lightning Rod shape without ally redirect)
def immune_boost() -> dict:
    return entry(T("self", "unconditional", "support"), T("self", "triggered", "boost"))


# Contact status/punish
def contact_disrupt() -> dict:
    return entry(T("opponent", "triggered", "disrupt"))


TAGS: dict[str, dict] = {
    # --- move modifiers / STAB-ish ---
    "aerilate": entry(T("self", "unconditional", "boost")),
    "dragonize": entry(T("self", "unconditional", "boost")),
    "galvanize": entry(T("self", "unconditional", "boost")),
    "pixilate": entry(T("self", "unconditional", "boost")),
    "refrigerate": entry(T("self", "unconditional", "boost")),
    "normalize": entry(T("self", "unconditional", "boost")),
    "liquidvoice": entry(T("self", "unconditional", "boost")),
    "analytic": entry(T("self", "unconditional", "boost")),
    "compoundeyes": entry(T("self", "unconditional", "boost")),
    "corrosion": entry(T("self", "unconditional", "boost")),
    "ironfist": entry(T("self", "unconditional", "boost")),
    "megalauncher": entry(T("self", "unconditional", "boost")),
    "reckless": entry(T("self", "unconditional", "boost")),
    "sheerforce": entry(T("self", "unconditional", "boost")),
    "skilllink": entry(T("self", "unconditional", "boost")),
    "sniper": entry(T("self", "unconditional", "boost")),
    "strongjaw": entry(T("self", "unconditional", "boost")),
    "technician": entry(T("self", "unconditional", "boost")),
    "toughclaws": entry(T("self", "unconditional", "boost")),
    "sharpness": entry(T("self", "unconditional", "boost")),
    "punkrock": entry(
        T("self", "unconditional", "boost"),
        T("self", "unconditional", "support"),
    ),
    "parentalbond": entry(T("self", "unconditional", "boost")),
    "neuroforce": entry(T("self", "unconditional", "boost")),
    "tintedlens": entry(T("self", "unconditional", "boost")),
    "stakeout": entry(T("self", "unconditional", "boost")),
    "superluck": entry(T("self", "unconditional", "boost")),
    "merciless": entry(T("self", "unconditional", "boost")),
    "longreach": entry(T("self", "unconditional", "boost")),
    "infiltrator": entry(T("self", "unconditional", "boost")),
    "scrappy": entry(
        T("self", "unconditional", "boost"),
        T("self", "unconditional", "support"),
    ),
    "mindseye": entry(
        T("self", "unconditional", "boost"),
        T("self", "unconditional", "support"),
    ),
    "serenegrace": entry(T("self", "unconditional", "boost")),
    "stench": entry(T("self", "unconditional", "boost")),
    "toxicchain": entry(T("self", "unconditional", "boost")),
    "poisontouch": entry(T("self", "unconditional", "boost")),
    "poisonpuppeteer": entry(T("opponent", "triggered", "disrupt")),
    "unseenfist": entry(T("self", "unconditional", "boost")),
    "piercingdrill": entry(T("self", "unconditional", "boost")),
    "stalwart": entry(T("self", "unconditional", "boost")),
    "propellertail": entry(T("self", "unconditional", "boost")),
    "megasol": entry(T("self", "unconditional", "boost")),
    # --- flat offensive/defensive stats ---
    "purepower": entry(T("self", "unconditional", "boost")),
    "furcoat": entry(T("self", "unconditional", "support")),
    "dragonsmaw": entry(T("self", "unconditional", "boost")),
    "firemane": entry(T("self", "unconditional", "boost")),
    "steelworker": entry(T("self", "unconditional", "boost")),
    "rockypayload": entry(T("self", "unconditional", "boost")),
    "transistor": entry(T("self", "unconditional", "boost")),
    "hustle": entry(
        T("self", "unconditional", "boost"),
        T("self", "unconditional", "disrupt"),
    ),
    "gorillatactics": entry(
        T("self", "unconditional", "boost"),
        T("self", "unconditional", "disrupt"),
    ),
    # --- HP-threshold offense (own HP state, continuous while low) ---
    "blaze": entry(T("self", "unconditional", "boost")),
    "overgrow": entry(T("self", "unconditional", "boost")),
    "torrent": entry(T("self", "unconditional", "boost")),
    "swarm": entry(T("self", "unconditional", "boost")),
    # --- status synergies ---
    "guts": entry(T("self", "unconditional", "boost")),
    "quickfeet": entry(T("self", "unconditional", "boost")),
    "marvelscale": entry(T("self", "unconditional", "support")),
    "poisonheal": entry(T("self", "unconditional", "support")),
    "flareboost": entry(T("self", "unconditional", "boost")),
    "toxicboost": entry(T("self", "unconditional", "boost")),
    "tangledfeet": entry(T("self", "unconditional", "support")),
    # --- on-KO / on-faint boosts ---
    "beastboost": entry(T("self", "triggered", "boost")),
    "battlebond": entry(T("self", "triggered", "boost")),
    "chillingneigh": entry(T("self", "triggered", "boost")),
    "grimneigh": entry(T("self", "triggered", "boost")),
    "moxie": entry(T("self", "triggered", "boost")),
    "soulheart": entry(T("self", "triggered", "boost")),
    "supremeoverlord": entry(T("self", "unconditional", "boost")),
    # --- hit-triggered self boosts ---
    "angerpoint": entry(T("self", "triggered", "boost")),
    "berserk": entry(T("self", "triggered", "boost")),
    "justified": entry(T("self", "triggered", "boost")),
    "stamina": entry(T("self", "triggered", "boost")),
    "steadfast": entry(T("self", "triggered", "boost")),
    "steamengine": entry(T("self", "triggered", "boost")),
    "rattled": entry(T("self", "triggered", "boost")),
    "watercompaction": entry(T("self", "triggered", "boost")),
    "electromorphosis": entry(T("self", "triggered", "boost")),
    "windpower": entry(T("self", "triggered", "boost")),
    "weakarmor": entry(
        T("self", "triggered", "boost"),
        T("self", "triggered", "disrupt"),
    ),
    "angershell": entry(
        T("self", "triggered", "boost"),
        T("self", "triggered", "disrupt"),
    ),
    "competitive": entry(T("self", "triggered", "boost")),
    "defiant": entry(T("self", "triggered", "boost")),
    # --- switch-in self boosts ---
    "dauntlessshield": entry(T("self", "unconditional", "boost")),
    "intrepidsword": entry(T("self", "unconditional", "boost")),
    "download": entry(T("self", "unconditional", "boost")),
    "embodyaspectcornerstone": entry(T("self", "unconditional", "boost")),
    "embodyaspecthearthflame": entry(T("self", "unconditional", "boost")),
    "embodyaspectteal": entry(T("self", "unconditional", "boost")),
    "embodyaspectwellspring": entry(T("self", "unconditional", "boost")),
    # --- immunities / bulk ---
    "battlearmor": entry(T("self", "unconditional", "support")),
    "shellarmor": entry(T("self", "unconditional", "support")),
    "bulletproof": entry(T("self", "unconditional", "support")),
    "soundproof": entry(T("self", "unconditional", "support")),
    "goodasgold": entry(T("self", "unconditional", "support")),
    "wonderguard": entry(T("self", "unconditional", "support")),
    "filter": entry(T("self", "unconditional", "support")),
    "solidrock": entry(T("self", "unconditional", "support")),
    "prismarmor": entry(T("self", "unconditional", "support")),
    "icescales": entry(T("self", "unconditional", "support")),
    "shadowshield": entry(T("self", "unconditional", "support")),
    "heatproof": entry(T("self", "unconditional", "support")),
    "thickfat": entry(T("self", "unconditional", "support")),
    "purifyingsalt": entry(
        T("self", "unconditional", "support"),
        T("self", "unconditional", "support"),
    ),  # status immunity + Ghost resist — collapse to one
    "magicguard": entry(T("self", "unconditional", "support")),
    "rockhead": entry(T("self", "unconditional", "support")),
    "sturdy": entry(T("self", "unconditional", "support")),
    "disguise": entry(T("self", "unconditional", "support")),
    "iceface": entry(T("self", "unconditional", "support")),
    "terashell": entry(T("self", "unconditional", "support")),
    "mountaineer": entry(T("self", "unconditional", "support")),
    "overcoat": entry(T("self", "unconditional", "support")),
    "wonderskin": entry(T("self", "unconditional", "support")),
    "levitate": entry(T("self", "unconditional", "support")),
    "telepathy": entry(T("self", "unconditional", "support")),
    "suctioncups": entry(T("self", "unconditional", "support")),
    "stickyhold": entry(T("self", "unconditional", "support")),
    "bigpecks": entry(T("self", "unconditional", "support")),
    "clearbody": entry(T("self", "unconditional", "support")),
    "fullmetalbody": entry(T("self", "unconditional", "support")),
    "whitesmoke": entry(T("self", "unconditional", "support")),
    "hypercutter": entry(T("self", "unconditional", "support")),
    "keeneye": entry(T("self", "unconditional", "support")),
    "illuminate": entry(T("self", "unconditional", "support")),
    "innerfocus": entry(T("self", "unconditional", "support")),
    "owntempo": entry(T("self", "unconditional", "support")),
    "oblivious": entry(T("self", "unconditional", "support")),
    "immunity": entry(T("self", "unconditional", "support")),
    "insomnia": entry(T("self", "unconditional", "support")),
    "vitalspirit": entry(T("self", "unconditional", "support")),
    "limber": entry(T("self", "unconditional", "support")),
    "magmaarmor": entry(T("self", "unconditional", "support")),
    "waterveil": entry(T("self", "unconditional", "support")),
    "shielddust": entry(T("self", "unconditional", "support")),
    "earlybird": entry(T("self", "unconditional", "support")),
    "naturalcure": entry(T("self", "unconditional", "support")),
    "shedskin": entry(T("self", "unconditional", "support")),
    "comatose": entry(T("self", "unconditional", "support")),
    # --- absorb / redirect-boost ---
    "voltabsorb": absorb(),
    "waterabsorb": absorb(),
    "eartheater": absorb(),
    "motordrive": immune_boost(),
    "sapsipper": immune_boost(),
    "wellbakedbody": immune_boost(),
    "windrider": immune_boost(),
    "thermalexchange": entry(
        T("self", "triggered", "boost"),
        T("self", "unconditional", "support"),
    ),
    "guarddog": entry(
        T("self", "unconditional", "support"),
        T("self", "triggered", "boost"),
    ),
    # Mega Eelektross-shaped native compound (Levitate + Beast Boost); NO composed_of
    "eelevate": entry(
        T("self", "unconditional", "support"),
        T("self", "triggered", "boost"),
    ),
    "waterbubble": entry(
        T("self", "unconditional", "boost"),
        T("self", "unconditional", "support"),
    ),
    # --- contact disrupt ---
    "aftermath": contact_disrupt(),
    "innardsout": contact_disrupt(),
    "cutecharm": contact_disrupt(),
    "effectspore": contact_disrupt(),
    "flamebody": contact_disrupt(),
    "static": contact_disrupt(),
    "poisonpoint": contact_disrupt(),
    "gooey": contact_disrupt(),
    "tanglinghair": contact_disrupt(),
    "spicyspray": contact_disrupt(),
    "liquidooze": contact_disrupt(),
    "synchronize": contact_disrupt(),
    "mummy": contact_disrupt(),
    "lingeringaroma": contact_disrupt(),
    "cottondown": entry(T("opponent", "triggered", "disrupt")),
    # --- trapping / denial / ruins ---
    "arenatrap": entry(T("opponent", "unconditional", "disrupt")),
    "shadowtag": entry(T("opponent", "unconditional", "disrupt")),
    "magnetpull": entry(T("opponent", "unconditional", "disrupt")),
    "unnerve": entry(T("opponent", "unconditional", "disrupt")),
    "pressure": entry(T("opponent", "unconditional", "disrupt")),
    "baddreams": entry(T("opponent", "triggered", "disrupt")),
    "airlock": entry(T("opponent", "unconditional", "disrupt")),
    "cloudnine": entry(T("opponent", "unconditional", "disrupt")),
    "aurabreak": entry(T("opponent", "unconditional", "disrupt")),
    "damp": entry(T("opponent", "unconditional", "disrupt")),
    "beadsofruin": entry(T("opponent", "unconditional", "disrupt")),
    "swordofruin": entry(T("opponent", "unconditional", "disrupt")),
    "tabletsofruin": entry(T("opponent", "unconditional", "disrupt")),
    "vesselofruin": entry(T("opponent", "unconditional", "disrupt")),
    "supersweetsyrup": entry(T("opponent", "unconditional", "disrupt")),
    "screencleaner": entry(T("opponent", "unconditional", "disrupt")),
    "moldbreaker": entry(T("opponent", "unconditional", "disrupt")),
    "teravolt": entry(T("opponent", "unconditional", "disrupt")),
    "turboblaze": entry(T("opponent", "unconditional", "disrupt")),
    "myceliummight": entry(
        T("opponent", "unconditional", "disrupt"),
        T("self", "unconditional", "disrupt"),
    ),
    # --- priority denial / ally protection ---
    "armortail": entry(T("opponent", "unconditional", "support")),
    "dazzling": entry(T("opponent", "unconditional", "support")),
    "queenlymajesty": entry(T("opponent", "unconditional", "support")),
    "aromaveil": entry(T("opponent", "unconditional", "support")),
    "sweetveil": entry(T("opponent", "unconditional", "support")),
    "pastelveil": entry(T("opponent", "unconditional", "support")),
    "flowerveil": entry(T("opponent", "unconditional", "support")),
    # --- ally boosts ---
    "powerspot": entry(T("opponent", "unconditional", "boost")),
    "steelyspirit": entry(T("opponent", "unconditional", "boost")),
    "victorystar": entry(T("opponent", "unconditional", "boost")),
    "healer": entry(T("opponent", "unconditional", "support")),
    "hospitality": entry(T("opponent", "unconditional", "support")),
    # --- field setters ---
    "grassysurge": entry(T("opponent", "unconditional", "support")),
    "mistysurge": entry(T("opponent", "unconditional", "support")),
    "psychicsurge": entry(T("opponent", "unconditional", "support")),
    "sandstream": entry(T("opponent", "unconditional", "support")),
    "snowwarning": entry(T("opponent", "unconditional", "support")),
    "deltastream": entry(T("opponent", "unconditional", "support")),
    "desolateland": entry(T("opponent", "unconditional", "support")),
    "primordialsea": entry(T("opponent", "unconditional", "support")),
    "hadronengine": entry(
        T("opponent", "unconditional", "support"),
        T("self", "unconditional", "boost"),
    ),
    "orichalcumpulse": entry(
        T("opponent", "unconditional", "support"),
        T("self", "unconditional", "boost"),
    ),
    "sandspit": entry(T("opponent", "triggered", "support")),
    "seedsower": entry(T("opponent", "triggered", "support")),
    "toxicdebris": entry(T("opponent", "triggered", "disrupt")),
    "teraformzero": entry(T("opponent", "triggered", "disrupt")),
    # --- field beneficiaries ---
    "slushrush": entry(T("self", "triggered", "boost"), field=snow()),
    "sandrush": entry(
        T("self", "triggered", "boost"),
        T("self", "unconditional", "support"),
        field=sand(),
    ),
    "sandforce": entry(
        T("self", "triggered", "boost"),
        T("self", "unconditional", "support"),
        field=sand(),
    ),
    "sandveil": entry(T("self", "triggered", "support"), field=sand()),
    "snowcloak": entry(T("self", "triggered", "support"), field=snow()),
    "icebody": entry(T("self", "triggered", "support"), field=snow()),
    "raindish": entry(T("self", "triggered", "support"), field=rain()),
    "hydration": entry(T("self", "triggered", "support"), field=rain()),
    "leafguard": entry(T("self", "triggered", "support"), field=sun()),
    "solarpower": entry(
        T("self", "triggered", "boost"),
        T("self", "triggered", "disrupt"),
        field=sun(),
    ),
    "grasspelt": entry(T("self", "triggered", "support"), field=grassy()),
    "protosynthesis": entry(T("self", "triggered", "boost"), field=sun()),
    "quarkdrive": entry(T("self", "triggered", "boost"), field=electric()),
    "flowergift": entry(
        T("self", "triggered", "boost"),
        T("opponent", "triggered", "boost"),
        field=sun(),
    ),
    "forecast": entry(T("self", "triggered", "support")),
    "mimicry": entry(T("self", "triggered", "support")),
    # --- copy / acquire (mechanism only) ---
    "costar": entry(T("self", "unconditional", "support")),
    "receiver": entry(T("self", "triggered", "support")),
    "powerofalchemy": entry(T("self", "triggered", "support")),
    "opportunist": entry(T("self", "triggered", "support")),
    "colorchange": entry(T("self", "triggered", "support")),
    "libero": entry(T("self", "unconditional", "boost")),
    "protean": entry(T("self", "unconditional", "boost")),
    "multitype": entry(T("self", "unconditional", "support")),
    "rkssystem": entry(T("self", "unconditional", "support")),
    # --- reflect / bounce ---
    "magicbounce": entry(
        T("self", "unconditional", "support"),
        T("opponent", "triggered", "disrupt"),
    ),
    "rebound": entry(
        T("self", "unconditional", "support"),
        T("opponent", "triggered", "disrupt"),
    ),
    "mirrorarmor": entry(T("opponent", "triggered", "disrupt")),
    # --- items / berries ---
    "cheekpouch": entry(T("self", "triggered", "support")),
    "cudchew": entry(T("self", "triggered", "support")),
    "gluttony": entry(T("self", "unconditional", "support")),
    "harvest": entry(T("self", "triggered", "support")),
    "ripen": entry(T("self", "unconditional", "boost")),
    "pickup": entry(T("self", "triggered", "support")),
    "pickpocket": entry(T("self", "triggered", "boost")),
    "magician": entry(T("self", "triggered", "boost")),
    "symbiosis": entry(T("opponent", "triggered", "support")),
    "unburden": entry(T("self", "triggered", "boost")),
    "klutz": entry(T("self", "unconditional", "disrupt")),
    # --- self drawbacks ---
    "truant": entry(T("self", "unconditional", "disrupt")),
    "slowstart": entry(T("self", "unconditional", "disrupt")),
    "defeatist": entry(T("self", "triggered", "disrupt")),
    "stall": entry(T("self", "unconditional", "disrupt")),
    # --- sequencing (Prankster-class → boost + provisional) ---
    "galewings": entry(T("self", "unconditional", "boost"), provisional_purpose=True),
    "triage": entry(T("self", "unconditional", "boost"), provisional_purpose=True),
    "quickdraw": entry(T("self", "unconditional", "boost"), provisional_purpose=True),
    # --- emergency switch ---
    "emergencyexit": entry(T("self", "triggered", "support")),
    "wimpout": entry(T("self", "triggered", "support")),
    # --- info ---
    "anticipation": entry(T("self", "unconditional", "support")),
    "forewarn": entry(T("self", "unconditional", "support")),
    "frisk": entry(T("self", "unconditional", "support")),
    # --- unaware ---
    "unaware": entry(
        T("self", "unconditional", "support"),
        T("self", "unconditional", "boost"),
    ),
    "persistent": entry(T("opponent", "unconditional", "support")),
    # Resolved via retarget triad (also listed here so apply_phase_b alone is complete)
    "darkaura": entry(
        T("ally", "unconditional", "boost"),
        T("opponent", "unconditional", "boost"),
    ),
    "fairyaura": entry(
        T("ally", "unconditional", "boost"),
        T("opponent", "unconditional", "boost"),
    ),
    "illusion": entry(T("opponent", "unconditional", "disrupt")),
    "commander": entry(
        T("ally", "unconditional", "boost"),
        T("self", "unconditional", "disrupt"),
        T("opponent", "unconditional", "disrupt"),
    ),
    "curiousmedicine": entry(T("ally", "unconditional", "support")),
    "fluffy": entry(
        T("self", "triggered", "support"),
        T("self", "triggered", "disrupt"),
    ),
    "dryskin": entry(
        T("self", "triggered", "support"),
        T("self", "triggered", "disrupt"),
    ),
    "dancer": entry(T("self", "unconditional", "support")),
    "rivalry": entry(
        T("self", "triggered", "boost"),
        T("self", "triggered", "disrupt"),
    ),
    "gulpmissile": entry(T("opponent", "triggered", "disrupt")),
    "heavymetal": entry(
        T("self", "unconditional", "boost"),
        T("self", "unconditional", "support"),
        T("self", "unconditional", "disrupt"),
    ),
    "lightmetal": entry(
        T("self", "unconditional", "disrupt"),
        T("self", "unconditional", "support"),
    ),
    "noguard": entry(
        T("self", "unconditional", "boost"),
        T("self", "unconditional", "disrupt"),
    ),
    "perishbody": entry(
        T("opponent", "triggered", "disrupt"),
        T("self", "triggered", "disrupt"),
    ),
    "wanderingspirit": entry(
        T("opponent", "triggered", "disrupt"),
        T("self", "triggered", "support"),
    ),
}

# Deduplicate purifyingsalt double support
TAGS["purifyingsalt"] = entry(T("self", "unconditional", "support"))

# Intentional empties only (not pending). Full ally/opponent retarget is
# scripts/extract_abilities/retarget_ally_opponent.py (runs after this in npm run extract:abilities).
FLAGS: list[dict[str, str]] = [
    {"id": "asone", "why": "placeholder", "options": "see asoneglastrier/asonespectrier"},
    {"id": "noability", "why": "no competitive effect", "options": "leave empty"},
    {"id": "ballfetch", "why": "no competitive effect", "options": "leave empty"},
    {"id": "honeygather", "why": "no competitive effect", "options": "leave empty"},
    {"id": "runaway", "why": "no competitive effect", "options": "leave empty"},
    {"id": "schooling", "why": "forme_primary_excluded", "options": "leave empty"},
    {"id": "shieldsdown", "why": "forme_primary_excluded", "options": "leave empty"},
    {"id": "stancechange", "why": "forme_primary_excluded", "options": "leave empty"},
    {"id": "zenmode", "why": "forme_primary_excluded", "options": "leave empty"},
    {"id": "zerotohero", "why": "forme_primary_excluded", "options": "leave empty"},
    {"id": "hungerswitch", "why": "forme_primary_excluded", "options": "leave empty"},
    {"id": "terashift", "why": "forme_primary_excluded", "options": "leave empty"},
    {"id": "powerconstruct", "why": "forme_primary_excluded", "options": "leave empty"},
]


def main() -> None:
    data = json.loads(PATH.read_text())
    abilities: dict = data["abilities"]
    already = {k for k, v in abilities.items() if v.get("tags")}
    flag_ids = {f["id"] for f in FLAGS}

    applied = 0
    for aid, patch in TAGS.items():
        if aid not in abilities:
            raise SystemExit(f"unknown ability id in TAGS: {aid}")
        if aid in already:
            continue  # keep Phase A sample tags
        if aid in flag_ids:
            raise SystemExit(f"{aid} is both TAGS and FLAGS")
        abilities[aid]["tags"] = patch["tags"]
        for key in ("field", "composed_of", "provisional_purpose"):
            if key in patch:
                abilities[aid][key] = patch[key]
            elif key in abilities[aid] and key != "tags":
                # don't strip unrelated keys
                pass
        applied += 1

    # Ensure flagged stay empty
    for fid in flag_ids:
        if fid not in abilities:
            raise SystemExit(f"unknown flag id: {fid}")
        abilities[fid]["tags"] = []
        abilities[fid].pop("composed_of", None)
        abilities[fid].pop("provisional_purpose", None)
        abilities[fid].pop("field", None)

    still_empty = sorted(
        k for k, v in abilities.items() if not v.get("tags") and k not in flag_ids
    )
    if still_empty:
        raise SystemExit(
            f"{len(still_empty)} abilities neither tagged nor flagged: {still_empty[:40]}"
        )

    # Prankster-class recount (self sequencing-only folded to boost)
    sequencing = [
        aid
        for aid, e in abilities.items()
        if e.get("provisional_purpose")
        or aid in {"prankster", "galewings", "triage", "quickdraw"}
    ]
    sequencing = sorted(set(sequencing))

    data["meta"]["taxonomy_status"] = "phase_b_flags_pending"
    data["meta"]["phase_b"] = {
        "newly_tagged": applied,
        "flags_open": len(FLAGS),
        "prankster_class_ids": sequencing,
        "prankster_class_count": len(sequencing),
        "prankster_recommendation": (
            "fold_into_boost"
            if len(sequencing) <= 4
            else "consider_fourth_purpose"
        ),
    }

    PATH.write_text(json.dumps(data, indent=2) + "\n")

    lines = [
        "# Ability classification Phase B — stop-and-report flags",
        "",
        f"**taxonomy_status:** `{data['meta']['taxonomy_status']}` "
        "(not `approved` — flags remain open).",
        "",
        f"**Newly tagged this pass:** {applied}",
        f"**Open flags:** {len(FLAGS)}",
        f"**Prankster-class count:** {len(sequencing)} → `{sequencing}` "
        f"(recommendation: `{data['meta']['phase_b']['prankster_recommendation']}`).",
        "",
        "## Flagged (tags left empty)",
        "",
    ]
    for f in FLAGS:
        lines.append(f"### `{f['id']}`")
        lines.append("")
        lines.append(f"- **description:** {abilities[f['id']]['description']}")
        lines.append(f"- **why:** {f['why']}")
        lines.append(f"- **options:** {f['options']}")
        lines.append("")

    lines.append("## Native compound callout")
    lines.append("")
    lines.append(
        "`eelevate` (Champions): tagged as native compound "
        "`self/unconditional/support` + `self/triggered/boost` "
        "(Levitate-like + Beast Boost-like) — **no** `composed_of`."
    )
    lines.append("")

    REPORT.write_text("\n".join(lines) + "\n")
    print(
        f"applied={applied} flags={len(FLAGS)} sequencing={sequencing} "
        f"status={data['meta']['taxonomy_status']} report={REPORT}"
    )


if __name__ == "__main__":
    main()
