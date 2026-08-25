"""query_support_needs — need-category surfacer (ADR-022 raw mechanical reasoning).

Receives RoleShapeContext from the orchestrator; does not classify role-shape.
Stops at named need options — no ranking, scoring, or candidate resolution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, cast

from recommender.calc_client import FieldSpec, PokemonSpecOptional
from recommender.coverage import ABILITY_TO_FIELD, get_relevant_threats
from recommender.ids import to_id
from recommender.legality import load_snapshot
from recommender.ability_classification import ability_self_def_drop_on_physical_hit
from recommender.stat_boosts import _self_defense_drops
from recommender.state import Attr, RecommenderState, Slot
from recommender.usage_data import SLOT_THREAT_N, featured_or_common_set
from recommender.usage_spreads import effective_spe

PrimaryFunction = Literal["offense", "support", "unknown"]
Tankiness = Literal["tanky", "glass", "unknown"]
NeedCategory = Literal[
    "defensive_coverage",
    "redirection",
    "healing_cleric",
    "screens",
    "condition_setter",
    "trick_room",
    "tailwind",
    "condition_beneficiary",
]
NeedUmbrella = Literal[
    "damage_mitigation",
    "redirection",
    "healing",
    "condition",
    "speed_control",
    "defensive_coverage",
]
SpeTier = Literal["low", "middling", "already_fast"]
Stance = Literal["need", "want"]

# Presentation order only — not a ranking.
_CATEGORY_ORDER: tuple[NeedCategory, ...] = (
    "defensive_coverage",
    "redirection",
    "healing_cleric",
    "screens",
    "condition_setter",
    "trick_room",
    "tailwind",
    "condition_beneficiary",
)

# Taxonomy only — emit/satisfiers/bans stay leaf NeedCategory.
_NEED_UMBRELLA: dict[NeedCategory, NeedUmbrella] = {
    "defensive_coverage": "defensive_coverage",
    "redirection": "redirection",
    "healing_cleric": "healing",
    "screens": "damage_mitigation",
    "condition_setter": "condition",
    "condition_beneficiary": "condition",
    "trick_room": "speed_control",
    "tailwind": "speed_control",
}

# ponytail: 1.5× Def/SpD ratio is a calibrated heuristic (Archaludon 130/65);
# Role Compendium / richer bulk models can replace later.
_ASYMMETRY_RATIO = 1.5

_SELF_HEAL_MOVES = frozenset(
    {
        "recover",
        "roost",
        "softboiled",
        "slackoff",
        "milkdrink",
        "shoreup",
        "moonlight",
        "morningsun",
        "synthesis",
        "wish",
    }
)

# Spe benefit needs no teammate (own item/status/turn progression) — suppresses TR/TW.
_SELF_SPEED_ABILITIES = frozenset({"speedboost", "unburden", "quickfeet"})

# Derived from data/abilities/all.v1.json (self+triggered + settable field in description).
# Dry Skin → Rain only (positive teammate-ask). Excluded: harvest (want), cloudnine/airlock
# (defensive_coverage). Values match ABILITY_TO_FIELD weather/terrain vocabulary.
_DOUBLES: FieldSpec = {"gameType": "Doubles"}
_CONDITION_DEPENDENT_ABILITIES: dict[str, tuple[FieldSpec, ...]] = {
    "swiftswim": ({"weather": "Rain", **_DOUBLES},),
    "chlorophyll": ({"weather": "Sun", **_DOUBLES},),
    "sandrush": ({"weather": "Sand", **_DOUBLES},),
    "slushrush": ({"weather": "Snow", **_DOUBLES},),
    "surgesurfer": ({"terrain": "Electric", **_DOUBLES},),
    "sandforce": ({"weather": "Sand", **_DOUBLES},),
    "solarpower": ({"weather": "Sun", **_DOUBLES},),
    "grasspelt": ({"terrain": "Grassy", **_DOUBLES},),
    "flowergift": ({"weather": "Sun", **_DOUBLES},),
    "sandveil": ({"weather": "Sand", **_DOUBLES},),
    "snowcloak": ({"weather": "Snow", **_DOUBLES},),
    "raindish": ({"weather": "Rain", **_DOUBLES},),
    "icebody": ({"weather": "Snow", **_DOUBLES},),
    "hydration": ({"weather": "Rain", **_DOUBLES},),
    "leafguard": ({"weather": "Sun", **_DOUBLES},),
    "dryskin": ({"weather": "Rain", **_DOUBLES},),
    "protosynthesis": ({"weather": "Sun", **_DOUBLES},),
    "quarkdrive": ({"terrain": "Electric", **_DOUBLES},),
    "forecast": (
        {"weather": "Rain", **_DOUBLES},
        {"weather": "Sun", **_DOUBLES},
        {"weather": "Snow", **_DOUBLES},
    ),
    "mimicry": (
        {"terrain": "Electric", **_DOUBLES},
        {"terrain": "Grassy", **_DOUBLES},
        {"terrain": "Misty", **_DOUBLES},
        {"terrain": "Psychic", **_DOUBLES},
    ),
}
CONDITION_DEPENDENT_ABILITIES = _CONDITION_DEPENDENT_ABILITIES

# Spe×2 field dependents only — suppress Layer 3 TR/TW when condition_setter path fires.
_SPEED_DOUBLING_ABILITIES = frozenset(
    {"swiftswim", "chlorophyll", "sandrush", "slushrush", "surgesurfer"}
)

# ponytail: legality snapshot has no priority field — extend as needed.
_OFFENSIVE_PRIORITY_MOVES = frozenset(
    {
        "aquajet",
        "bulletpunch",
        "suckerpunch",
        "extremespeed",
        "iceshard",
        "machpunch",
        "quickattack",
        "grassyglide",
        "accelerock",
        "shadowsneak",
        "watershuriken",
        "vacuumwave",
        "firstimpression",
        "fakeout",
        "feint",
        "jetpunch",
        "upperhand",
    }
)


_TRACKED_WEATHERS = frozenset({"Rain", "Sun", "Sand", "Snow"})


@dataclass(frozen=True, init=False)
class RoleShapeContext:
    primary_function: PrimaryFunction = "unknown"
    tankiness: Tankiness = "unknown"
    requires_setup_turn: bool = False
    needed_weathers: tuple[str, ...] = ()
    needed_trick_room: bool = False

    def __init__(
        self,
        primary_function: PrimaryFunction = "unknown",
        tankiness: Tankiness = "unknown",
        requires_setup_turn: bool = False,
        needed_weathers: tuple[str, ...] = (),
        needed_trick_room: bool = False,
        *,
        match_status: str | None = None,
        setup_dependent: bool | None = None,
    ) -> None:
        """Build the minimal shape; legacy keywords are accepted but not retained."""
        del match_status
        object.__setattr__(self, "primary_function", primary_function)
        object.__setattr__(self, "tankiness", tankiness)
        object.__setattr__(
            self,
            "requires_setup_turn",
            requires_setup_turn if setup_dependent is None else setup_dependent,
        )
        object.__setattr__(self, "needed_weathers", needed_weathers)
        object.__setattr__(self, "needed_trick_room", needed_trick_room)


@dataclass(frozen=True)
class SupportNeed:
    category: NeedCategory
    name: str
    description: str
    trigger: str | None
    notes: str | None = None
    weak_side: Literal["def", "spd"] | None = None
    stance: Stance | None = None


def _spe_tier(
    anchor_spe: int, threat_speeds: list[int]
) -> SpeTier | None:
    """Relative Spe band vs meta threats. Empty threats → no signal."""
    if not threat_speeds:
        return None
    faster = sum(1 for s in threat_speeds if s > anchor_spe)
    f = faster / len(threat_speeds)
    if f >= 2 / 3:
        return "low"
    if f <= 1 / 3:
        return "already_fast"
    return "middling"


def _legality_ability(snap: dict[str, Any], species: str) -> str | None:
    entry = (snap.get("species") or {}).get(to_id(species))
    if not entry:
        return None
    abilities = entry.get("abilities") or {}
    raw = abilities.get("0") or abilities.get(0)
    return str(raw) if raw else None


def _resolve_kit(
    pokemon: PokemonSpecOptional,
    *,
    regulation: str,
    snap: dict[str, Any],
) -> tuple[str | None, list[str]]:
    """Return (ability_name, moves) using key-presence, then featured, then legality."""
    species = pokemon.get("species") or ""
    featured = featured_or_common_set(species, regulation=regulation) if species else None

    if "ability" in pokemon:
        ability = pokemon.get("ability")
    else:
        feat_ab = (featured or {}).get("ability") if featured else None
        # Usage sometimes emits placeholder "noability" for megas — treat as missing.
        if feat_ab and to_id(str(feat_ab)) not in ("", "noability"):
            ability = str(feat_ab)
        else:
            ability = _legality_ability(snap, species)

    if "moves" in pokemon:
        moves = list(pokemon.get("moves") or [])
    elif featured and featured.get("moves"):
        moves = list(featured["moves"])
    else:
        moves = []

    return ability, moves


def _base_stats(snap: dict[str, Any], species: str) -> dict[str, int]:
    entry = (snap.get("species") or {}).get(to_id(species)) or {}
    raw = entry.get("base_stats") or {}
    return {k: int(raw.get(k) or 0) for k in ("hp", "atk", "def", "spa", "spd", "spe")}


def _has_offensive_priority(moves: list[str]) -> bool:
    return any(to_id(m) in _OFFENSIVE_PRIORITY_MOVES for m in moves)


def _has_self_heal(moves: list[str]) -> bool:
    return any(to_id(m) in _SELF_HEAL_MOVES for m in moves)


_SUN_WEATHERS = frozenset({"sun", "harshsunshine"})
_RAIN_WEATHERS = frozenset({"rain", "heavyrain"})


# ponytail: Hydro Steam is the only Sun-boost-on-Water calc nuance (Harsh Sunshine fails
# Water moves). Move-derived weather needs come from RoleShapeContext.needed_weathers
# (projected from benefits_from mechanisms); ability path stays in _speed_needs.
def _weather_category_match(required: str, secured: str) -> bool:
    a, b = to_id(required), to_id(secured)
    if a == b:
        return True
    if a in _SUN_WEATHERS and b in _SUN_WEATHERS:
        return True
    if a in _RAIN_WEATHERS and b in _RAIN_WEATHERS:
        return True
    return False


def _field_matches(required: FieldSpec, secured: FieldSpec) -> bool:
    rw, rt = required.get("weather"), required.get("terrain")
    sw = secured.get("weather")
    if rw and sw and _weather_category_match(str(rw), str(sw)):
        return True
    if rt and secured.get("terrain") == rt:
        return True
    return False


def field_labels_from_trigger(trigger: str) -> list[str]:
    """Parse field_condition:any:rain|sun → ['rain', 'sun']. Last :-segment, split on |."""
    parts = trigger.split(":")
    if len(parts) < 3:
        return []
    return [p for p in parts[-1].split("|") if p]


def _field_labels_from_specs(requireds: tuple[FieldSpec, ...]) -> list[str]:
    labels: list[str] = []
    for spec in requireds:
        label = spec.get("weather") or spec.get("terrain")
        if label:
            labels.append(to_id(str(label)))
    return labels


def _condition_need_copy(
    requireds: tuple[FieldSpec, ...],
) -> tuple[str, str, str, str]:
    """Return (name, description, trigger, notes) for a condition_setter need."""
    labels = _field_labels_from_specs(requireds)
    trigger = f"field_condition:any:{'|'.join(labels)}"
    if len(requireds) == 1:
        display = requireds[0].get("weather") or requireds[0].get("terrain") or "field"
        return (
            f"{display} setter",
            f"Condition-dependent ability needs a {display} setter on the team.",
            trigger,
            f"Requires {display}",
        )
    # Multi: all weather or all terrain (Forecast / Mimicry).
    kind = "Weather" if requireds[0].get("weather") else "Terrain"
    display_parts = [
        str(s.get("weather") or s.get("terrain")) for s in requireds
    ]
    joined = "/".join(display_parts)
    return (
        f"{kind} setter",
        f"Condition-dependent ability needs any of {joined} on the team.",
        trigger,
        f"Requires any of {joined}",
    )


def _secured_fields(
    team_draft: list[Slot] | None, *, regulation: str
) -> list[FieldSpec]:
    """Locked teammates whose ability maps via ABILITY_TO_FIELD (setters only)."""
    if not team_draft:
        return []
    seen: set[tuple[str | None, str | None]] = set()
    out: list[FieldSpec] = []
    for slot in team_draft:
        if not slot.species.value or not slot.species.locked:
            continue
        species = slot.species.value
        ability = slot.ability.value
        if not ability:
            featured = featured_or_common_set(species, regulation=regulation)
            ability = (featured or {}).get("ability") if featured else None
        aid = to_id(ability or "")
        field = ABILITY_TO_FIELD.get(aid)
        if not field:
            continue
        key = (field.get("weather"), field.get("terrain"))
        if key in seen:
            continue
        seen.add(key)
        out.append(field)
    return out


def _condition_secured(
    requireds: tuple[FieldSpec, ...],
    team_draft: list[Slot] | None,
    *,
    regulation: str,
) -> bool:
    secured = _secured_fields(team_draft, regulation=regulation)
    return any(
        _field_matches(req, f) for req in requireds for f in secured
    )


def _threat_speeds(state: RecommenderState | None, regulation: str) -> list[int]:
    if state is None:
        # get_relevant_threats only reads regulation_mod at runtime.
        state = cast(
            RecommenderState,
            {
                "format_id": "",
                "game_type": "doubles",
                "regulation_mod": regulation,
                "picked_team_size": 4,
                "available_pool": [],
                "team_draft": [],
                "archetype": Attr(),
                "rejected": [],
                "constraints": [],
                "messages": [],
            },
        )
    speeds: list[int] = []
    for t in get_relevant_threats(state, n=SLOT_THREAT_N):
        opp = t.spec.get("species") or ""
        if not opp:
            continue
        usage = featured_or_common_set(
            opp, regulation=state.get("regulation_mod") or regulation
        )
        opp_spread = dict((usage or {}).get("evs") or {"spe": 32})
        opp_nat = str((usage or {}).get("nature") or "Jolly")
        speeds.append(effective_spe(opp, opp_spread, opp_nat, scarf=False))
    return speeds


def _layer3_needs(
    tier: SpeTier, has_priority: bool
) -> list[SupportNeed]:
    if tier == "low":
        if has_priority:
            return [
                SupportNeed(
                    category="trick_room",
                    name="Trick Room",
                    description=(
                        "Low Spe with priority already a partial answer; "
                        "Trick Room reinforces rather than being required."
                    ),
                    trigger="speed_tier:low_with_priority",
                    stance="want",
                )
            ]
        return [
            SupportNeed(
                category="trick_room",
                name="Trick Room",
                description="Low Spe attacker with no priority — needs Trick Room.",
                trigger="speed_tier:low_no_priority",
                stance="need",
            )
        ]
    if tier == "middling":
        return [
            SupportNeed(
                category="tailwind",
                name="Tailwind",
                description="Middling Spe — Tailwind more directly closes the gap.",
                trigger="speed_tier:middling",
                stance="need",
            ),
            SupportNeed(
                category="trick_room",
                name="Trick Room",
                description=(
                    "Middling Spe — Trick Room is a real alternative if the team leans that way."
                ),
                trigger="speed_tier:middling",
                stance="want",
            ),
        ]
    # already_fast
    return [
        SupportNeed(
            category="tailwind",
            name="Tailwind",
            description="Already fast — further Speed still helps against faster threats.",
            trigger="speed_tier:already_fast",
            stance="want",
        )
    ]


def _speed_needs(
    *,
    ability: str | None,
    moves: list[str],
    primary_function: PrimaryFunction,
    species: str,
    evs: dict[str, int],
    nature: str,
    team_draft: list[Slot] | None,
    state: RecommenderState | None,
    regulation: str,
) -> list[SupportNeed]:
    aid = to_id(ability or "")
    if aid in _SELF_SPEED_ABILITIES:
        return []

    out: list[SupportNeed] = []
    requireds = _CONDITION_DEPENDENT_ABILITIES.get(aid)
    if requireds is not None:
        if not _condition_secured(requireds, team_draft, regulation=regulation):
            name, desc, trigger, notes = _condition_need_copy(requireds)
            out.append(
                SupportNeed(
                    category="condition_setter",
                    name=name,
                    description=desc,
                    trigger=trigger,
                    notes=notes,
                )
            )
            if aid in _SPEED_DOUBLING_ABILITIES:
                return out
        elif aid in _SPEED_DOUBLING_ABILITIES:
            return []
        # Non-Speed dependent secured (or already emitted): fall through to Layer 3.

    if primary_function != "offense":
        return out

    threat_speeds = _threat_speeds(state, regulation)
    anchor_spe = effective_spe(species, evs, nature)
    tier = _spe_tier(anchor_spe, threat_speeds)
    if tier is None:
        return out
    out.extend(_layer3_needs(tier, _has_offensive_priority(moves)))
    return out


def query_support_needs(
    pokemon: PokemonSpecOptional,
    role_shape_context: RoleShapeContext,
    *,
    team_draft: list[Slot] | None = None,
    state: RecommenderState | None = None,
    regulation: str = "champions-reg-mb",
) -> list[SupportNeed]:
    """Named support-need categories for an anchor; no ranking or candidate search."""
    species = pokemon.get("species") or ""
    if not species:
        return []

    snap = load_snapshot()
    ability, moves = _resolve_kit(pokemon, regulation=regulation, snap=snap)
    stats = _base_stats(snap, species)
    primary = role_shape_context.primary_function
    tankiness = role_shape_context.tankiness

    needs: list[SupportNeed] = []
    healing: SupportNeed | None = None

    # --- Attacker-universals ---
    if primary == "offense":
        healing = SupportNeed(
            category="healing_cleric",
            name="Healing / cleric support",
            description="Attacker-shaped anchors benefit from healing/cleric support.",
            trigger=None,
        )
        needs.append(healing)
        needs.append(
            SupportNeed(
                category="screens",
                name="Screens",
                description="Attacker-shaped anchors benefit from screens support.",
                trigger=None,
            )
        )

    # --- Defensive asymmetry ---
    if tankiness == "tanky" and primary in ("offense", "support"):
        defense, sp_def = stats.get("def", 0), stats.get("spd", 0)
        lo, hi = min(defense, sp_def), max(defense, sp_def)
        if lo > 0 and hi >= _ASYMMETRY_RATIO * lo:
            weak: Literal["def", "spd"] = "spd" if defense > sp_def else "def"
            tag = "offense_tank" if primary == "offense" else "support_tank"
            needs.append(
                SupportNeed(
                    category="defensive_coverage",
                    name=f"Coverage for weak {weak.upper()}",
                    description=(
                        f"Tanky {primary} anchor has asymmetric bulk; "
                        f"wants coverage for the weak {weak} side."
                    ),
                    trigger=f"def_spd_asymmetry:{tag}",
                    weak_side=weak,
                )
            )

    # --- Tank + no self-heal ---
    if tankiness == "tanky" and not _has_self_heal(moves):
        enriched = SupportNeed(
            category="healing_cleric",
            name="Healing / cleric support",
            description="Tank-shaped anchor has no reliable self-heal on its set.",
            trigger="tank_no_self_heal",
        )
        if healing is not None:
            # Replace the attacker-universal healing entry.
            needs = [n for n in needs if n.category != "healing_cleric"]
            needs.append(enriched)
            healing = enriched
        else:
            needs.append(enriched)
            healing = enriched

    # --- Redirection (offense-primary, setup, or self Def/SpD debuff) ---
    self_def_spd_debuff = ability_self_def_drop_on_physical_hit(
        ability or ""
    ) or any(_self_defense_drops(to_id(m)) for m in moves)
    hard_redir = role_shape_context.requires_setup_turn or self_def_spd_debuff
    if primary == "offense" or hard_redir:
        if role_shape_context.requires_setup_turn:
            redir_trigger = "requires_setup_turn:redirection"
            redir_desc = (
                "Turn-limited/setup-dependent role wants Follow Me / Rage Powder."
            )
            redir_stance = None
        elif self_def_spd_debuff:
            redir_trigger = "kit:self_def_spd_debuff"
            redir_desc = (
                "Kit self-lowers Def/SpD (move or Weak Armor); wants "
                "Follow Me / Rage Powder."
            )
            redir_stance = None
        else:
            redir_trigger = "offense:redirection"
            redir_desc = (
                "Offense-primary anchor wants Follow Me / Rage Powder redirection."
            )
            # Soft ask — same tier as already_fast Tailwind; must not alone
            # flip anchor_has_obvious_need for self-sufficient offense anchors.
            redir_stance = "want"
        needs.append(
            SupportNeed(
                category="redirection",
                name="Redirection",
                description=redir_desc,
                trigger=redir_trigger,
                stance=redir_stance,
            )
        )

    # --- Speed axis ---
    needs.extend(
        _speed_needs(
            ability=ability,
            moves=moves,
            primary_function=primary,
            species=species,
            evs=dict(pokemon.get("evs") or {}),
            nature=str(pokemon.get("nature") or "Hardy"),
            team_draft=team_draft,
            state=state,
            regulation=regulation,
        )
    )

    # --- Strategy Trick Room (RoleShapeContext.needed_trick_room) ---
    if role_shape_context.needed_trick_room and not any(
        n.category == "trick_room" for n in needs
    ):
        needs.append(
            SupportNeed(
                category="trick_room",
                name="Trick Room",
                description=(
                    "Strategic Trick Room sweeper identity expects "
                    "a teammate Trick Room setter."
                ),
                trigger="strategy:trick_room_sweeper",
                stance="want",
            )
        )

    # --- Move-derived weather (RoleShapeContext.needed_weathers) ---
    covered_labels: set[str] = set()
    for need in needs:
        if need.category == "condition_setter" and need.trigger:
            covered_labels.update(field_labels_from_trigger(need.trigger))
    for weather in role_shape_context.needed_weathers:
        if weather not in _TRACKED_WEATHERS:
            continue
        label = to_id(weather)
        if label in covered_labels:
            continue
        requireds: tuple[FieldSpec, ...] = ({"weather": weather},)
        if _condition_secured(requireds, team_draft, regulation=regulation):
            continue
        name, desc, trigger, notes = _condition_need_copy(requireds)
        needs.append(
            SupportNeed(
                category="condition_setter",
                name=name,
                description=desc,
                trigger=trigger,
                notes=notes,
            )
        )
        covered_labels.add(label)

    order = {c: i for i, c in enumerate(_CATEGORY_ORDER)}
    needs.sort(key=lambda n: order.get(n.category, 99))
    return needs
