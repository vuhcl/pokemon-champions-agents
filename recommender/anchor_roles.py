"""Resolve an anchor build, classify its strategic role, and project its shape."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

from recommender.coverage import ABILITY_TO_FIELD
from recommender.ids import to_id
from recommender.legality import load_snapshot
from recommender.matchup import CHARGE_INSTANT_WEATHER
from recommender.move_narrowing import WEATHER_SETTING_MOVES
from recommender.recommend import infer_role
from recommender.resolved_builds import get_resolved_build
from recommender.role_compendium import (
    CompendiumRoleEvidence,
    ReverseCompendiumEvidence,
    reverse_compendium_evidence,
)
from recommender.state import Attr, Slot
from recommender.support_needs import CONDITION_DEPENDENT_ABILITIES, RoleShapeContext
from recommender.usage_data import featured_or_common_set, find_set_matching
from recommender.usage_spreads import select_usage_spread

FieldSource = Literal[
    "user_confirmed",
    "provisional",
    "usage_derived",
    "cached",
    "synthesized",
    "legality_only",
    "unknown",
]
_AUTHORITATIVE_ABILITY_SOURCES = frozenset(
    {"user_confirmed", "usage_derived", "legality_only"}
)
MechanismImportance = Literal["needed", "wanted", "secondary"]
PrimaryFunction = Literal["offense", "support", "unknown"]
DurabilityIntent = Literal["tanky", "glass", "balanced", "unknown"]
MatchQuality = Literal["clean", "partial", "none"]


@dataclass(frozen=True)
class FieldProvenance:
    field: str
    source: FieldSource
    confirmed: bool = False
    cooccurrence_group: str | None = None


@dataclass(frozen=True)
class ResolvedAnchorBuild:
    species: str | None
    ability: str | None
    item: str | None
    nature: str | None
    evs: tuple[tuple[str, int], ...]
    moves: tuple[str, ...]
    regulation: str
    provenance: tuple[FieldProvenance, ...]
    fingerprint: str

    @property
    def spread(self) -> dict[str, int]:
        return dict(self.evs)

    def source_for(self, field: str) -> FieldSource:
        return next((p.source for p in self.provenance if p.field == field), "unknown")

    def confirmed(self, field: str) -> bool:
        return any(p.field == field and p.confirmed for p in self.provenance)

    def as_pokemon(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.species:
            out["species"] = self.species
        # Key presence tells downstream resolution that an unknown field is
        # deliberate and must not be silently replaced by representative usage.
        out["ability"] = self.ability
        for name in ("item", "nature"):
            if (value := getattr(self, name)) is not None:
                out[name] = value
        out["moves"] = list(self.moves)
        if self.evs:
            out["evs"] = self.spread
        return out


@dataclass(frozen=True)
class MechanismEvidence:
    mechanic: str
    kind: str
    relation: Literal["provides", "benefits_from", "executes", "mitigates"]
    importance: MechanismImportance
    role_id: str | None
    present: bool
    prerequisite: bool
    activation: Literal["automatic", "passive_reactive", "move"]
    interruptible: bool
    source: FieldSource
    supply: Literal["self_supplied", "teammate_expected", "not_applicable"] = (
        "not_applicable"
    )
    evidence: tuple[str, ...] = ()
    confidence: Literal["high", "medium", "low"] = "medium"


@dataclass(frozen=True)
class AnchorRoleEvidence:
    claim: str
    source: FieldSource
    detail: str


@dataclass(frozen=True)
class AnchorRoleDecision:
    role_id: str
    secondary_role_ids: tuple[str, ...]
    match_quality: MatchQuality
    primary_function: PrimaryFunction
    durability_intent: DurabilityIntent
    mechanisms: tuple[MechanismEvidence, ...]
    kit_role: str | None
    compendium: ReverseCompendiumEvidence
    conflicts: tuple[str, ...]
    evidence: tuple[AnchorRoleEvidence, ...]
    build_fingerprint: str


_FIELDS = ("species", "ability", "item", "nature", "evs", "moves")
_ATTR_NAMES = {
    "species": "species",
    "ability": "ability",
    "item": "item",
    "nature": "nature",
    "evs": "spread",
    "moves": "moveset",
}


def _slot_value(slot: Slot, field: str) -> Attr[Any]:
    return getattr(slot, _ATTR_NAMES[field])


def _unique_legal_ability(species: str) -> str | None:
    entry = (load_snapshot().get("species") or {}).get(to_id(species)) or {}
    abilities = {
        str(value)
        for value in (entry.get("abilities") or {}).values()
        if value
    }
    return next(iter(abilities)) if len(abilities) == 1 else None


def _ability_for_target_role(species: str, role_id: str | None) -> str | None:
    """Return the sole legal ability that uniquely satisfies a setter role, else None."""
    if not role_id or not species:
        return None
    wanted_weathers = {
        weather
        for weather, setter in _SETTER_ROLE.items()
        if setter == role_id
    }
    if not wanted_weathers:
        return None
    entry = (load_snapshot().get("species") or {}).get(to_id(species)) or {}
    matches: list[str] = []
    for raw in (entry.get("abilities") or {}).values():
        if not raw:
            continue
        name = str(raw)
        field = ABILITY_TO_FIELD.get(to_id(name))
        if not field:
            continue
        weather = field.get("weather")
        if not weather:
            continue
        canonical = _canonical_weather(str(weather))
        if canonical in wanted_weathers and to_id(name) != "deltastream":
            matches.append(name)
    # Deduplicate by id while preserving first display name.
    by_id: dict[str, str] = {}
    for name in matches:
        by_id.setdefault(to_id(name), name)
    if len(by_id) != 1:
        return None
    return next(iter(by_id.values()))


def _ability_mechanism_confidence(
    source: FieldSource,
) -> Literal["high", "medium"] | None:
    """Confidence for ability-derived mechanisms, or None to omit the mechanism."""
    if source not in _AUTHORITATIVE_ABILITY_SOURCES:
        return None
    return "high" if source == "user_confirmed" else "medium"


def _ability_source_from_slot_attr(attr: Attr[Any]) -> FieldSource:
    """Map unlocked Slot.ability ReasonRef into FieldProvenance.source."""
    if attr.locked:
        return "user_confirmed"
    ref = attr.reason.ref if attr.reason is not None else None
    if ref in {"usage", "usage_derived"}:
        return "usage_derived"
    if ref == "legality_only":
        return "legality_only"
    if ref in {"tier3_role_ability", "synthesized"}:
        return "synthesized"
    return "provisional"


def _fingerprint(
    values: dict[str, Any], regulation: str, provenance: dict[str, FieldProvenance]
) -> str:
    payload = {
        "regulation": regulation,
        "values": values,
        "provenance": {
            field: {
                "source": provenance[field].source,
                "confirmed": provenance[field].confirmed,
                "group": provenance[field].cooccurrence_group,
            }
            for field in _FIELDS
        },
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def resolve_anchor_build(
    anchor: Slot | str,
    *,
    provisional: dict[str, Any] | None = None,
    synthesized: dict[str, Any] | None = None,
    role_hint: str | None = None,
    regulation: str = "champions-reg-mb",
) -> ResolvedAnchorBuild:
    """Resolve fields independently in descending precedence without fake joins."""
    slot = anchor if isinstance(anchor, Slot) else Slot(species=Attr(value=anchor))
    values: dict[str, Any] = {field: None for field in _FIELDS}
    provenance = {
        field: FieldProvenance(field, "unknown") for field in _FIELDS
    }

    for field in _FIELDS:
        attr = _slot_value(slot, field)
        if attr.value is not None:
            values[field] = attr.value
            source: FieldSource = (
                _ability_source_from_slot_attr(attr)
                if field == "ability"
                else ("user_confirmed" if attr.locked else "provisional")
            )
            provenance[field] = FieldProvenance(
                field, source, confirmed=attr.locked
            )

    aliases = {"spread": "evs", "moveset": "moves"}
    for raw_field, value in (provisional or {}).items():
        field = aliases.get(raw_field, raw_field)
        if field in values and values[field] is None and value is not None:
            values[field] = value
            provenance[field] = FieldProvenance(field, "provisional")

    species = str(values["species"] or "")
    exact = None
    if species and values["moves"] and values["item"]:
        exact = find_set_matching(
            species,
            list(values["moves"]),
            str(values["item"]),
            regulation=regulation,
        )
    if exact:
        group = "usage-exact:" + hashlib.sha1(
            json.dumps(
                [to_id(species), sorted(to_id(m) for m in values["moves"]), to_id(values["item"])],
                separators=(",", ":"),
            ).encode()
        ).hexdigest()[:12]
        for field, key in (
            ("species", "species"),
            ("ability", "ability"),
            ("item", "item"),
            ("moves", "moves"),
        ):
            if values[field] is None and exact.get(key) is not None:
                values[field] = exact[key]
                provenance[field] = FieldProvenance(
                    field, "usage_derived", cooccurrence_group=group
                )
        if values["evs"] is None and exact.get("evs") is not None:
            values["evs"] = exact["evs"]
            provenance["evs"] = FieldProvenance("evs", "usage_derived")

    if species and values["moves"] and values["item"] and values["evs"] is None:
        cached = get_resolved_build(
            species, list(values["moves"]), str(values["item"]), regulation
        )
        if cached and cached.get("spread"):
            values["evs"] = dict(cached["spread"])
            provenance["evs"] = FieldProvenance("evs", "cached")

    if species and role_hint and (values["evs"] is None or values["nature"] is None):
        choice = select_usage_spread(
            species,
            role_hint,
            list(values["moves"] or ()),
            regulation=regulation,
            live_fetch=lambda _species, _regulation: (),
        )
        if choice:
            if values["evs"] is None:
                values["evs"] = dict(choice.spread)
                provenance["evs"] = FieldProvenance("evs", "usage_derived")
            if values["nature"] is None and choice.nature:
                values["nature"] = choice.nature
                provenance["nature"] = FieldProvenance("nature", "usage_derived")

    representative = (
        featured_or_common_set(species, regulation=regulation) if species else None
    )
    for field, key in (
        ("species", "species"),
        ("ability", "ability"),
        ("item", "item"),
        ("nature", "nature"),
        ("evs", "evs"),
        ("moves", "moves"),
    ):
        if (
            representative
            and values[field] is None
            and representative.get(key) is not None
        ):
            values[field] = representative[key]
            # Representative APIs combine marginal spread evidence; deliberately
            # do not claim a co-occurrence group.
            provenance[field] = FieldProvenance(field, "usage_derived")

    for raw_field, value in (synthesized or {}).items():
        field = aliases.get(raw_field, raw_field)
        if field in values and values[field] is None and value is not None:
            values[field] = value
            provenance[field] = FieldProvenance(field, "synthesized")

    if species and values["ability"] is None:
        ability = _unique_legal_ability(species)
        if ability:
            values["ability"] = ability
            provenance["ability"] = FieldProvenance("ability", "legality_only")

    normalized = {
        **values,
        "moves": list(values["moves"] or []),
        "evs": dict(values["evs"] or {}),
    }
    return ResolvedAnchorBuild(
        species=values["species"],
        ability=values["ability"],
        item=values["item"],
        nature=values["nature"],
        evs=tuple(sorted((values["evs"] or {}).items())),
        moves=tuple(values["moves"] or ()),
        regulation=regulation,
        provenance=tuple(provenance[field] for field in _FIELDS),
        fingerprint=_fingerprint(normalized, regulation, provenance),
    )


_SETUP_MOVES = {
    "swordsdance": ("Swords Dance", "swords_dance_attacker"),
    "nastyplot": ("Nasty Plot", "nasty_plot_attacker"),
    "calmmind": ("Calm Mind", "setup_attacker"),
    "bulkup": ("Bulk Up", "setup_attacker"),
}
_SCREEN_MOVES = {
    "lightscreen": "Light Screen",
    "reflect": "Reflect",
    "auroraveil": "Aurora Veil",
}

_NEEDED_CONDITION_ABILITIES = frozenset(
    {"swiftswim", "chlorophyll", "sandrush", "slushrush"}
)
_WANTED_CONDITION_ABILITIES = frozenset(
    {
        "sandforce",
        "solarpower",
        "flowergift",
        "sandveil",
        "snowcloak",
        "raindish",
        "icebody",
        "hydration",
        "leafguard",
        "dryskin",
        "protosynthesis",
        "forecast",
    }
)
_WEATHER_CANONICAL = {
    "Rain": "Rain",
    "Heavy Rain": "Rain",
    "Sun": "Sun",
    "Harsh Sunshine": "Sun",
    "Sand": "Sand",
    "Snow": "Snow",
}
_SHAPE_WEATHERS = frozenset({"Rain", "Sun", "Sand", "Snow"})
_SETTER_ROLE = {
    "Rain": "rain_setter",
    "Sun": "sun_setter",
    "Sand": "sand_setter",
    "Snow": "snow_setter",
}


def _role_id(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _canonical_weather(label: str) -> str | None:
    return _WEATHER_CANONICAL.get(label)


def provided_weather_conditions(decision: AnchorRoleDecision) -> tuple[str, ...]:
    """Present provides-tier weathers only. Never Trick Room / Tailwind."""
    out: list[str] = []
    for m in decision.mechanisms:
        if not m.present or m.relation != "provides":
            continue
        if m.importance not in ("needed", "wanted"):
            continue
        for item in m.evidence:
            if not item.startswith("condition:"):
                continue
            name = item.removeprefix("condition:")
            if name in _SHAPE_WEATHERS and name not in out:
                out.append(name)
    return tuple(out)


def weather_beneficiary_ability_ids(condition: str) -> frozenset[str]:
    """Ability ids in _NEEDED|_WANTED whose CONDITION_DEPENDENT_ABILITIES weather canonicalizes to condition."""
    canonical = _canonical_weather(condition) or condition
    out: set[str] = set()
    for aid in _NEEDED_CONDITION_ABILITIES | _WANTED_CONDITION_ABILITIES:
        for spec in CONDITION_DEPENDENT_ABILITIES.get(aid, ()):
            w = spec.get("weather")
            if w and _canonical_weather(str(w)) == canonical:
                out.add(aid)
                break
    return frozenset(out)


def _display_name(raw: str) -> str:
    return raw.replace("-", " ").title() if raw == to_id(raw) else raw


def _mechanisms(build: ResolvedAnchorBuild) -> list[MechanismEvidence]:
    out: list[MechanismEvidence] = []
    ability = to_id(build.ability or "")
    ability_name = build.ability or ""
    ability_source = build.source_for("ability")
    ability_confidence = _ability_mechanism_confidence(ability_source)
    move_ids = {to_id(m): m for m in build.moves}

    field = ABILITY_TO_FIELD.get(ability)
    weather = field.get("weather") if field else None
    if weather and ability != "deltastream" and ability_confidence is not None:
        canonical = _canonical_weather(str(weather))
        if canonical:
            out.append(
                MechanismEvidence(
                    _display_name(ability_name or ability),
                    "automatic_condition_setting",
                    "provides",
                    "needed",
                    _SETTER_ROLE[canonical],
                    True,
                    False,
                    "automatic",
                    False,
                    ability_source,
                    "self_supplied",
                    (f"condition:{canonical}", f"ability:{ability}"),
                    ability_confidence,
                )
            )

    if ability == "stamina" and ability_confidence is not None:
        out.append(
            MechanismEvidence(
                "Stamina",
                "reactive_durability",
                "mitigates",
                "secondary",
                None,
                True,
                False,
                "passive_reactive",
                False,
                ability_source,
                "self_supplied",
                ("ability:stamina",),
                ability_confidence,
            )
        )

    for move_id, (name, role_id) in _SETUP_MOVES.items():
        if move_id in move_ids:
            out.append(
                MechanismEvidence(
                    name, "self_setup", "executes", "needed", role_id, True,
                    True, "move", True, build.source_for("moves"),
                    "self_supplied", (f"move:{move_id}",), "high",
                )
            )

    for move_id, weather_label in WEATHER_SETTING_MOVES.items():
        if move_id not in move_ids:
            continue
        canonical = _canonical_weather(weather_label)
        if not canonical:
            continue
        name = move_ids[move_id]
        out.append(
            MechanismEvidence(
                name,
                "manual_condition_setting",
                "provides",
                "wanted",
                _SETTER_ROLE[canonical],
                True,
                False,
                "move",
                True,
                build.source_for("moves"),
                "self_supplied",
                (f"condition:{canonical}", f"move:{move_id}"),
                "high",
            )
        )

    if "tailwind" in move_ids:
        out.append(
            MechanismEvidence(
                "Tailwind", "speed_control", "provides", "wanted",
                "tailwind_setter", True, False, "move", True,
                build.source_for("moves"), "self_supplied",
                ("condition:Tailwind", "move:tailwind"), "high",
            )
        )
    if "trickroom" in move_ids:
        out.append(
            MechanismEvidence(
                "Trick Room", "speed_control", "provides", "needed",
                "trick_room_setter", True, True, "move", True,
                build.source_for("moves"), "self_supplied",
                ("condition:Trick Room", "move:trickroom"), "high",
            )
        )

    present_screens = [mid for mid in _SCREEN_MOVES if mid in move_ids]
    if present_screens:
        has_aurora_veil = "auroraveil" in move_ids
        ls_reflect = [mid for mid in ("lightscreen", "reflect") if mid in move_ids]
        has_clay = to_id(build.item or "") == "lightclay"
        wanted = (
            has_aurora_veil
            or len(ls_reflect) >= 2
            or (has_clay and bool(ls_reflect))
        )
        evidence = [f"move:{mid}" for mid in present_screens]
        if has_aurora_veil:
            evidence.append("condition:Snow")
        if has_clay and wanted:
            evidence.append("item:lightclay")
        if has_aurora_veil:
            mechanic = "Aurora Veil"
        elif len(present_screens) >= 2:
            mechanic = "Screens"
        else:
            mechanic = _SCREEN_MOVES[present_screens[0]]
        out.append(
            MechanismEvidence(
                mechanic,
                "screens",
                "provides",
                "wanted" if wanted else "secondary",
                "screens_support" if wanted else None,
                True,
                False,
                "move",
                True,
                build.source_for("moves"),
                "self_supplied",
                tuple(evidence),
                "high",
            )
        )

    if (
        ability_confidence is not None
        and (
            ability in _NEEDED_CONDITION_ABILITIES
            or ability in _WANTED_CONDITION_ABILITIES
        )
    ):
        importance: MechanismImportance = (
            "needed" if ability in _NEEDED_CONDITION_ABILITIES else "wanted"
        )
        for spec in CONDITION_DEPENDENT_ABILITIES.get(ability, ()):
            w = spec.get("weather")
            if not w:
                continue
            canonical = _canonical_weather(str(w))
            if not canonical:
                continue
            out.append(
                MechanismEvidence(
                    _display_name(ability_name or ability),
                    "teammate_condition_benefit",
                    "benefits_from",
                    importance,
                    None,
                    True,
                    False,
                    "passive_reactive",
                    False,
                    ability_source,
                    "teammate_expected",
                    (f"condition:{canonical}", f"ability:{ability}"),
                    ability_confidence,
                )
            )

    for move_id, weathers in CHARGE_INSTANT_WEATHER.items():
        if move_id not in move_ids:
            continue
        canonicals = {
            c for w in weathers if (c := _canonical_weather(w)) is not None
        }
        for canonical in sorted(canonicals):
            out.append(
                MechanismEvidence(
                    move_ids[move_id],
                    "teammate_condition_benefit",
                    "benefits_from",
                    "needed",
                    None,
                    True,
                    False,
                    "move",
                    False,
                    build.source_for("moves"),
                    "teammate_expected",
                    (f"condition:{canonical}", f"move:{move_id}"),
                    "high",
                )
            )

    if "suckerpunch" in move_ids:
        out.append(
            MechanismEvidence(
                "Sucker Punch", "priority_offense", "executes", "secondary",
                None, True, False, "move", False, build.source_for("moves"),
            )
        )
    if to_id(build.item or "") == "leftovers":
        out.append(
            MechanismEvidence(
                "Leftovers", "passive_sustain", "mitigates", "secondary",
                None, True, False, "passive_reactive", False,
                build.source_for("item"),
            )
        )
    return out


def _has_present_benefit(mechanisms: list[MechanismEvidence], condition: str) -> bool:
    tag = f"condition:{condition}"
    return any(
        m.relation == "benefits_from"
        and m.present
        and tag in m.evidence
        for m in mechanisms
    )


def _primary_function(role_id: str) -> PrimaryFunction:
    if role_id.endswith("_attacker") or role_id in {
        "bulky_pivot",
        "fast_pivot",
        "trick_room_sweeper",
    }:
        return "offense"
    if role_id.endswith("_setter") or role_id in {
        "support_speed_control",
        "screens_support",
        "redirection",
    }:
        return "support"
    return "unknown"


def _durability(build: ResolvedAnchorBuild, mechanisms: list[MechanismEvidence]) -> DurabilityIntent:
    if any(m.kind == "reactive_durability" for m in mechanisms):
        return "tanky"
    if to_id(build.item or "") in {"leftovers", "sitrusberry", "rockyhelmet"}:
        return "tanky"
    if build.spread.get("hp", 0) >= 20:
        return "tanky"
    if to_id(build.item or "") == "focussash":
        return "glass"
    return "unknown"


def classify_anchor_role(
    build: ResolvedAnchorBuild,
    *,
    user_role: str | None = None,
    explicit_role: str | None = None,
    compendium: ReverseCompendiumEvidence | None = None,
) -> AnchorRoleDecision:
    """Classify by explicit role, exact compendium, mechanics, kit, unresolved."""
    mechanisms = _mechanisms(build)
    compendium = compendium or reverse_compendium_evidence(
        build.species or "",
        moves=build.moves,
        ability=build.ability,
    )
    declared = _role_id(user_role or explicit_role or "")
    evidence: list[AnchorRoleEvidence] = []
    conflicts: list[str] = []
    if declared:
        role_id = declared
        source = "user_confirmed"
        evidence.append(AnchorRoleEvidence("primary_role", source, role_id))
    elif compendium.exact:
        role_id = compendium.exact[0].role_id
        source = "usage_derived"
        evidence.append(
            AnchorRoleEvidence(
                "primary_role", source, f"exact compendium: {compendium.exact[0].source_file}"
            )
        )
    else:
        role_mechanism = next((m for m in mechanisms if m.role_id), None)
        if role_mechanism:
            role_id = role_mechanism.role_id or "unresolved"
            source = role_mechanism.source
            evidence.append(AnchorRoleEvidence("primary_role", source, role_mechanism.mechanic))
        elif build.moves or build.item:
            role_id = infer_role(list(build.moves), build.item or "", build.ability)
            source = build.source_for("moves")
            evidence.append(AnchorRoleEvidence("primary_role", source, "infer_role fallback"))
        else:
            role_id = "unresolved"
            source = "unknown"

    exact_roles = {row.role_id for row in compendium.exact}
    move_ids = {to_id(m) for m in build.moves}
    if declared == "bulky_rain_attacker" and build.ability and build.item and build.moves:
        quality: MatchQuality = "clean"
    elif declared and declared not in exact_roles:
        quality = "partial"
    elif role_id == "unresolved":
        quality = "none"
    else:
        quality = "clean"

    if role_id == "trick_room_sweeper" and "trickroom" not in move_ids:
        mechanisms.append(
            MechanismEvidence(
                mechanic="Trick Room",
                kind="teammate_condition_benefit",
                relation="benefits_from",
                importance="wanted",
                role_id=None,
                present=False,
                prerequisite=False,
                activation="passive_reactive",
                interruptible=False,
                source="user_confirmed" if declared else "unknown",
                supply="teammate_expected",
                evidence=("condition:Trick Room", "strategy:trick_room_sweeper"),
                confidence="medium",
            )
        )
        conflicts.append("strategic Trick Room role is not established by the active kit")
    if role_id == "bulky_rain_attacker" and not _has_present_benefit(mechanisms, "Rain"):
        mechanisms.append(
            MechanismEvidence(
                mechanic="Rain",
                kind="teammate_condition_benefit",
                relation="benefits_from",
                importance="wanted",
                role_id=None,
                present=False,
                prerequisite=False,
                activation="passive_reactive",
                interruptible=False,
                source="user_confirmed" if declared else "unknown",
                supply="teammate_expected",
                evidence=("condition:Rain", "strategy:bulky_rain_attacker"),
                confidence="medium",
            )
        )
    if role_id == "bulky_pivot" and not {
        "uturn", "voltswitch", "flipturn", "partingshot", "teleport"
    }.intersection(to_id(m) for m in build.moves):
        conflicts.append("coarse kit role says pivot but the build has no pivot move")

    secondary = tuple(
        dict.fromkeys(
            m.role_id
            for m in mechanisms
            if m.present
            and m.importance in ("needed", "wanted")
            and m.role_id
            and m.role_id != role_id
        )
    )
    return AnchorRoleDecision(
        role_id=role_id,
        secondary_role_ids=secondary,
        match_quality=quality,
        primary_function=_primary_function(role_id),
        durability_intent=_durability(build, mechanisms),
        mechanisms=tuple(mechanisms),
        kit_role=(
            infer_role(list(build.moves), build.item or "", build.ability)
            if build.moves or build.item
            else None
        ),
        compendium=compendium,
        conflicts=tuple(conflicts),
        evidence=tuple(evidence),
        build_fingerprint=build.fingerprint,
    )


def derive_role_shape_context(decision: AnchorRoleDecision) -> RoleShapeContext:
    """Pure projection: classification evidence stays on the decision."""
    tankiness: Literal["tanky", "glass", "unknown"] = (
        decision.durability_intent
        if decision.durability_intent in ("tanky", "glass")
        else "unknown"
    )
    requires_setup = any(
        m.present
        and m.importance in ("needed", "wanted")
        and m.prerequisite
        and m.activation == "move"
        and m.interruptible
        for m in decision.mechanisms
    )
    weathers: list[str] = []
    needed_trick_room = False
    for m in decision.mechanisms:
        if m.relation != "benefits_from":
            continue
        if m.importance not in ("needed", "wanted"):
            continue
        if not (m.present or m.supply == "teammate_expected"):
            continue
        for item in m.evidence:
            if not item.startswith("condition:"):
                continue
            name = item.removeprefix("condition:")
            if name == "Trick Room":
                needed_trick_room = True
            elif name in _SHAPE_WEATHERS and name not in weathers:
                weathers.append(name)
    return RoleShapeContext(
        primary_function=decision.primary_function,
        tankiness=tankiness,
        requires_setup_turn=requires_setup,
        needed_weathers=tuple(weathers),
        needed_trick_room=needed_trick_room,
    )
