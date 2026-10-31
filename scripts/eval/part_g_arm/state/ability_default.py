"""Ability default source for tool_fields calc_damage / get_usage_stats.

Does not touch services/calc. One constant switches the source rule.
"""

from __future__ import annotations

from typing import Any, Literal

from recommender.arm_teammates import legal_mega_forme_ids, mega_capable_base_ids
from recommender.ids import to_id
from recommender.legality import load_snapshot, species_abilities
from recommender.usage_data import ingame_ladder_species_map, showdown_species_map

# Flip to "showdown" for Showdown-everywhere in one line (Vu).
ABILITY_DEFAULT_SOURCE_MODE: Literal["vu_rule", "showdown"] = "vu_rule"

SourceName = Literal["ingame", "showdown"]
AbilitySourceEcho = Literal["stated", "auto_single"]


def preferred_ability_source(species: str) -> SourceName:
    """Vu rule: top in-game; Mega-capable bases and Mega formes → Showdown."""
    if ABILITY_DEFAULT_SOURCE_MODE == "showdown":
        return "showdown"
    sid = to_id(species)
    snap = load_snapshot()
    entry = (snap.get("species") or {}).get(sid) or {}
    base_id = str(entry.get("base_species_id") or sid)
    mega_bases = mega_capable_base_ids()
    if sid in legal_mega_forme_ids() or sid in mega_bases or base_id in mega_bases:
        return "showdown"
    return "ingame"


def _map_for(source: SourceName, regulation: str) -> dict[str, Any]:
    if source == "showdown":
        return showdown_species_map(regulation)
    return ingame_ladder_species_map(regulation)


def _top_from_entry(entry: dict[str, Any] | None) -> tuple[str | None, float | None]:
    if not entry:
        return None, None
    rows = entry.get("common_abilities") or []
    if not rows:
        return None, None
    top = rows[0]
    name = top.get("name")
    pct = top.get("pct")
    return (str(name) if name else None), (float(pct) if pct is not None else None)


def lookup_top_ability(
    species: str,
    *,
    regulation: str = "champions",
) -> dict[str, Any]:
    """Resolve top_ability under preferred_ability_source; no silent switch.

    If the preferred source has no ability rows, surface the other source's top
    (labelled) and set default_source_missing=True.
    """
    preferred = preferred_ability_source(species)
    other: SourceName = "ingame" if preferred == "showdown" else "showdown"
    sid = to_id(species)
    snap = load_snapshot()
    entry = (snap.get("species") or {}).get(sid) or {}
    base_id = str(entry.get("base_species_id") or sid)
    # Mega formes may only appear under the base ladder id; gendered/cosmetic
    # formes (e.g. Meowstic-F) must not inherit the other forme's ability table.
    allow_base_fallback = sid in legal_mega_forme_ids()

    pref_map = _map_for(preferred, regulation)
    other_map = _map_for(other, regulation)

    pref_entry = pref_map.get(sid)
    if pref_entry is None and allow_base_fallback:
        pref_entry = pref_map.get(base_id)
    name, pct = _top_from_entry(pref_entry)
    if name is not None:
        return {
            "default_source": preferred,
            "default_source_missing": False,
            "top_ability": {
                "name": name,
                "pct": pct,
                "pct_kind": "percent",
                "source": preferred,
            },
        }

    other_entry = other_map.get(sid)
    if other_entry is None and allow_base_fallback:
        other_entry = other_map.get(base_id)
    o_name, o_pct = _top_from_entry(other_entry)
    out: dict[str, Any] = {
        "default_source": preferred,
        "default_source_missing": True,
        "top_ability": None,
    }
    if o_name is not None:
        out["top_ability"] = {
            "name": o_name,
            "pct": o_pct,
            "pct_kind": "percent",
            "source": other,
        }
    return out


def legal_ability_names(species: str) -> list[str]:
    snap = load_snapshot()
    return list(species_abilities(snap, species) or [])


def prepare_side_ability(
    species: object,
    ability: object,
) -> tuple[str | None, AbilitySourceEcho | None, dict[str, Any] | None]:
    """Return (ability_to_use, ability_source, refusal_or_None).

    Missing ability + exactly one legal → fill auto_single.
    Missing + multiple → refusal naming legal abilities.
    Present → stated (caller still passes through; legality of value is calc's).
    """
    if not isinstance(species, str) or not species.strip():
        return None, None, {
            "status": "error",
            "error_kind": "bad_arguments",
            "message": "attacker/defender species is required when checking ability",
        }
    if isinstance(ability, str) and ability.strip():
        return ability.strip(), "stated", None
    legal = legal_ability_names(species)
    if len(legal) == 1:
        return legal[0], "auto_single", None
    if not legal:
        return None, None, {
            "status": "error",
            "error_kind": "missing_ability",
            "message": (
                f"{species} has no legal abilities in the legality snapshot; "
                "pass ability explicitly."
            ),
            "species": species,
            "legal_abilities": [],
            "hint": 'Call get_usage_stats(species, kind="abilities") for usage-ranked abilities.',
        }
    return None, None, {
        "status": "error",
        "error_kind": "missing_ability",
        "message": (
            f"calc_damage requires an ability for {species}. "
            f"Legal abilities: {', '.join(legal)}. "
            'Call get_usage_stats(species, kind="abilities") and pass top_ability.name '
            "(or another listed ability)."
        ),
        "species": species,
        "legal_abilities": legal,
        "hint": 'get_usage_stats(species, "abilities") returns top_ability under default_source.',
    }


def prepare_calc_damage_args(args: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """tool_fields gate: ensure both sides have an ability.

    Returns (mutated_args, None) on success, or (None, refusal_dict) on failure.
    Success also stamps ability_source on the returned args under _ability_source.
    """
    out = dict(args)
    atk = dict(out.get("attacker") or {})
    de = dict(out.get("defender") or {})
    sources: dict[str, AbilitySourceEcho] = {}

    for side, spec in (("attacker", atk), ("defender", de)):
        ab, src, refusal = prepare_side_ability(spec.get("species"), spec.get("ability"))
        if refusal is not None:
            refusal = {**refusal, "side": side}
            return None, refusal
        assert ab is not None and src is not None
        spec["ability"] = ab
        sources[side] = src

    out["attacker"] = atk
    out["defender"] = de
    out["_ability_source"] = sources
    return out, None
