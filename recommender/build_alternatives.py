"""Build-confirmation alternatives: draft align, usage/vgcpastes siblings, team notes.

ponytail: vgcpastes species gate VGCPASETES_MIN_OCCURRENCES=15 is provisional
calibration — revisit with ladder data before treating as final.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

from recommender.ids import regulation_file_tag, to_id
from recommender.legality import check_set
from recommender.sp_convert import evs_to_sp
from recommender.state import (
    BuildAxis,
    BuildConfirmationOption,
    BuildFieldOverrides,
    BuildOptionGroup,
    BuildProvenance,
    ProvisionalSlot,
    RecommenderState,
    Slot,
    TargetRoleDecision,
)
from recommender.usage_data import featured_or_common_set, species_usage
from recommender.usage_spreads import effective_spe

REPO_ROOT = Path(__file__).resolve().parents[1]
TEAM_COMP_DIR = REPO_ROOT / "data" / "team-composition"

# ponytail: provisional calibration — raise/lower when ladder joint-build data exists
VGCPASETES_MIN_OCCURRENCES = 15
_MAX_SIBLINGS = 3
_STAT_KEYS = ("hp", "atk", "def", "spa", "spd", "spe")

_ALLY_SUPPORT_MOVES = frozenset(
    {
        "Light Screen",
        "Reflect",
        "Aurora Veil",
        "Tailwind",
        "Trick Room",
    }
)


def draft_has_complete_build(slot: Slot) -> bool:
    """Values present: ability, item, 4 moves, nature, 6-stat spread."""
    moves = slot.moveset.value or []
    spread = slot.spread.value or {}
    return bool(
        slot.ability.value
        and slot.item.value
        and len(moves) == 4
        and all(bool(m) for m in moves)
        and slot.nature.value
        and all(stat in spread for stat in _STAT_KEYS)
    )


def _fingerprint_for(
    *,
    slot_index: int,
    role: str,
    species: str,
    ability: str,
    item: str,
    moves: tuple[str, str, str, str],
    nature: str,
    spread: dict[str, int],
    base: str,
) -> str:
    payload = {
        "slot_index": slot_index,
        "role": role,
        "species": species,
        "ability": ability,
        "item": item,
        "moves": list(moves),
        "nature": nature,
        "spread": {stat: int(spread[stat]) for stat in _STAT_KEYS},
        "base": base,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _provisional_from_draft(
    provisional: ProvisionalSlot, slot: Slot
) -> ProvisionalSlot:
    moves_raw = list(slot.moveset.value or [])
    moves = (
        str(moves_raw[0]),
        str(moves_raw[1]),
        str(moves_raw[2]),
        str(moves_raw[3]),
    )
    spread = {stat: int((slot.spread.value or {})[stat]) for stat in _STAT_KEYS}
    decision = provisional.target_role_decision
    if not isinstance(decision, TargetRoleDecision):
        return provisional
    species = str(slot.species.value or provisional.species)
    ability = str(slot.ability.value)
    item = str(slot.item.value)
    nature = str(slot.nature.value)
    fp = _fingerprint_for(
        slot_index=provisional.slot_index,
        role=decision.role_id,
        species=species,
        ability=ability,
        item=item,
        moves=moves,
        nature=nature,
        spread=spread,
        base=provisional.base_slot_fingerprint,
    )
    return ProvisionalSlot(
        schema_version=1,
        slot_index=provisional.slot_index,
        target_role_decision=decision,
        species=species,
        ability=ability,
        item=item,
        moves=moves,
        nature=nature,
        spread=tuple((stat, spread[stat]) for stat in _STAT_KEYS),
        base_slot_fingerprint=provisional.base_slot_fingerprint,
        fingerprint=fp,
    )


def provisional_for_confirmation(
    provisional: ProvisionalSlot, state: RecommenderState
) -> ProvisionalSlot:
    """Refine/import: replace with draft-derived provisional. Else return provisional."""
    draft = state.get("team_draft") or []
    idx = provisional.slot_index
    if idx < 0 or idx >= len(draft):
        return provisional
    slot = draft[idx]
    if not draft_has_complete_build(slot):
        return provisional
    if to_id(str(slot.species.value or "")) != to_id(provisional.species):
        return provisional
    return _provisional_from_draft(provisional, slot)


def ally_support_investment_notes(
    provisional: ProvisionalSlot, state: RecommenderState
) -> tuple[str, ...]:
    """Scan other team_draft slots' movesets for support moves that change investment."""
    notes: list[str] = []
    found: set[str] = set()
    for i, slot in enumerate(state.get("team_draft") or []):
        if i == provisional.slot_index:
            continue
        moves = slot.moveset.value or []
        for move in moves:
            name = str(move)
            if name in _ALLY_SUPPORT_MOVES:
                found.add(name)
    if found & {"Light Screen", "Aurora Veil"}:
        notes.append(
            "Ally screens/veil already locked — SpD investment forks may be redundant."
        )
    if "Reflect" in found:
        notes.append(
            "Ally Reflect already locked — Def investment forks may be redundant."
        )
    if "Tailwind" in found:
        notes.append(
            "Ally Tailwind already locked — Spe investment tradeoffs shift under Tailwind."
        )
    if "Trick Room" in found:
        notes.append(
            "Ally Trick Room already locked — Spe investment tradeoffs shift under TR."
        )
    return tuple(notes)


@lru_cache(maxsize=4)
def load_vgcpastes_builds(regulation: str = "champions-reg-mb") -> dict[str, Any]:
    tag = regulation_file_tag(regulation)
    path = TEAM_COMP_DIR / f"{tag}.vgcpastes-builds.v1.json"
    if not path.exists():
        return {"meta": {}, "teams": [], "cores": []}
    return json.loads(path.read_text())


def _vgcpastes_species_counts(data: dict[str, Any]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for team in data.get("teams") or []:
        for member in team.get("members") or []:
            sid = to_id(str(member.get("species") or ""))
            if sid:
                counts[sid] += 1
    return counts


def _normalize_member_evs(raw: dict[str, Any] | None) -> dict[str, int] | None:
    if not isinstance(raw, dict):
        return None
    try:
        spread = {stat: int(raw.get(stat, 0)) for stat in _STAT_KEYS}
    except (TypeError, ValueError):
        return None
    if any(v > 32 for v in spread.values()):
        spread = evs_to_sp(spread)
    if sum(spread.values()) != 66 or any(v < 0 or v > 32 for v in spread.values()):
        return None
    return spread


def _diff_summary(base: ProvisionalSlot, overrides: BuildFieldOverrides) -> str:
    bits: list[str] = []
    if "nature" in overrides and overrides["nature"] != base.nature:
        bits.append(f"nature {base.nature}→{overrides['nature']}")
    if "spread" in overrides and overrides["spread"] != base.spread_dict():
        bits.append("spread")
    if "item" in overrides and overrides["item"] != base.item:
        bits.append(f"item {base.item}→{overrides['item']}")
    if "moves" in overrides and tuple(overrides["moves"]) != base.moves:
        bits.append("moves")
    if "ability" in overrides and overrides["ability"] != base.ability:
        bits.append(f"ability→{overrides['ability']}")
    return ", ".join(bits) if bits else "no field change"


def _is_legal(
    provisional: ProvisionalSlot,
    overrides: BuildFieldOverrides,
    state: RecommenderState,
) -> bool:
    ability = overrides.get("ability", provisional.ability)
    item = overrides.get("item", provisional.item)
    moves = list(overrides.get("moves", provisional.moves))
    result = check_set(
        provisional.species,
        moves,
        item,
        ability=ability,
        team_draft=state.get("team_draft"),
        exclude_slot=provisional.slot_index,
    )
    return bool(result.ok)


def _mechanical_notes_for_spread(
    provisional: ProvisionalSlot,
    *,
    nature: str,
    spread: dict[str, int],
    item: str,
) -> tuple[str, ...]:
    scarf = to_id(item) == "choicescarf"
    spe = effective_spe(provisional.species, spread, nature, scarf=scarf)
    base_spe = effective_spe(
        provisional.species,
        provisional.spread_dict(),
        provisional.nature,
        scarf=to_id(provisional.item) == "choicescarf",
    )
    if spe == base_spe:
        return (f"Spe {spe} (same as default)",)
    return (f"Spe {spe} vs default {base_spe}",)


def _identity_option(
    provisional: ProvisionalSlot,
    *,
    axis: BuildAxis,
    provenance: BuildProvenance,
    label: str,
    tradeoff: str,
    team_notes: tuple[str, ...] = (),
) -> BuildConfirmationOption:
    return BuildConfirmationOption(
        option_id=f"{axis}:default",
        label=label,
        axis=axis,
        provenance=provenance,
        overrides={},
        diff_summary="keep current" if provenance == "user_current" else "recommended default",
        tradeoff=tradeoff,
        team_notes=team_notes,
    )


def _option(
    *,
    option_id: str,
    label: str,
    axis: BuildAxis,
    provenance: BuildProvenance,
    overrides: BuildFieldOverrides,
    base: ProvisionalSlot,
    tradeoff: str,
    mechanical_notes: tuple[str, ...] = (),
    team_notes: tuple[str, ...] = (),
) -> BuildConfirmationOption:
    return BuildConfirmationOption(
        option_id=option_id,
        label=label,
        axis=axis,
        provenance=provenance,
        overrides=overrides,
        diff_summary=_diff_summary(base, overrides),
        tradeoff=tradeoff,
        mechanical_notes=mechanical_notes,
        team_notes=team_notes,
    )


def _usage_spread_siblings(
    provisional: ProvisionalSlot,
    state: RecommenderState,
    *,
    team_notes: tuple[str, ...],
    regulation: str,
) -> list[BuildConfirmationOption]:
    entry = species_usage(provisional.species, regulation=regulation)
    if not entry:
        return []
    rows = entry.get("top_spreads") or []
    out: list[BuildConfirmationOption] = []
    base_spread = provisional.spread_dict()
    seen: set[tuple[Any, ...]] = set()
    for i, row in enumerate(rows):
        if len(out) >= _MAX_SIBLINGS:
            break
        evs = row.get("evs") or row
        spread = _normalize_member_evs(evs if isinstance(evs, dict) else None)
        if spread is None:
            continue
        nature = str(row.get("nature") or provisional.nature)
        key = (nature, tuple(spread[s] for s in _STAT_KEYS))
        if key in seen:
            continue
        seen.add(key)
        if spread == base_spread and nature == provisional.nature:
            continue
        overrides: BuildFieldOverrides = {"nature": nature, "spread": spread}
        if not _is_legal(provisional, overrides, state):
            continue
        mech = _mechanical_notes_for_spread(
            provisional, nature=nature, spread=spread, item=provisional.item
        )
        out.append(
            _option(
                option_id=f"spread_nature:{i + 1}",
                label=f"{nature} {'/'.join(str(spread[s]) for s in _STAT_KEYS)}",
                axis="spread_nature",
                provenance="usage_spread",
                overrides=overrides,
                base=provisional,
                tradeoff="Real usage spread variant",
                mechanical_notes=mech,
                team_notes=team_notes,
            )
        )
    return out


def _vgcpastes_siblings(
    provisional: ProvisionalSlot,
    state: RecommenderState,
    *,
    team_notes: tuple[str, ...],
    regulation: str,
) -> list[BuildConfirmationOption]:
    data = load_vgcpastes_builds(regulation)
    sid = to_id(provisional.species)
    counts = _vgcpastes_species_counts(data)
    if counts.get(sid, 0) < VGCPASETES_MIN_OCCURRENCES:
        return []
    out: list[BuildConfirmationOption] = []
    seen: set[tuple[Any, ...]] = set()
    for team in data.get("teams") or []:
        if len(out) >= _MAX_SIBLINGS:
            break
        for member in team.get("members") or []:
            if to_id(str(member.get("species") or "")) != sid:
                continue
            spread = _normalize_member_evs(member.get("evs"))
            moves = member.get("moves") or []
            if spread is None or len(moves) != 4 or not all(moves):
                continue
            nature = str(member.get("nature") or provisional.nature)
            item = str(member.get("item") or provisional.item)
            ability = str(member.get("ability") or provisional.ability)
            move_t = (str(moves[0]), str(moves[1]), str(moves[2]), str(moves[3]))
            key = (
                to_id(item),
                to_id(nature),
                tuple(spread[s] for s in _STAT_KEYS),
                tuple(to_id(m) for m in move_t),
            )
            if key in seen:
                continue
            seen.add(key)
            if (
                item == provisional.item
                and nature == provisional.nature
                and spread == provisional.spread_dict()
                and move_t == provisional.moves
            ):
                continue
            overrides: BuildFieldOverrides = {
                "item": item,
                "ability": ability,
                "nature": nature,
                "spread": spread,
                "moves": move_t,
            }
            if not _is_legal(provisional, overrides, state):
                continue
            axes_changed = sum(
                [
                    item != provisional.item,
                    nature != provisional.nature or spread != provisional.spread_dict(),
                    move_t != provisional.moves,
                ]
            )
            axis: BuildAxis = "bundled" if axes_changed > 1 else (
                "item"
                if item != provisional.item
                else ("moveset" if move_t != provisional.moves else "spread_nature")
            )
            mech = _mechanical_notes_for_spread(
                provisional, nature=nature, spread=spread, item=item
            )
            out.append(
                _option(
                    option_id=f"{axis}:vgc{len(out) + 1}",
                    label=f"{item} / {nature} (paste)",
                    axis=axis,
                    provenance="vgcpastes",
                    overrides=overrides,
                    base=provisional,
                    tradeoff="Real joint paste build",
                    mechanical_notes=mech,
                    team_notes=team_notes,
                )
            )
            break
    return out


def generate_build_option_groups(
    provisional: ProvisionalSlot,
    state: RecommenderState,
) -> tuple[tuple[BuildOptionGroup, ...], tuple[str, ...]]:
    """Return (groups, default_option_ids). Assumes provisional already aligned. Never raises."""
    try:
        return _generate_build_option_groups(provisional, state)
    except Exception:
        return (), ()


def _generate_build_option_groups(
    provisional: ProvisionalSlot,
    state: RecommenderState,
) -> tuple[tuple[BuildOptionGroup, ...], tuple[str, ...]]:
    regulation = state.get("regulation_mod") or "champions-reg-mb"
    draft = state.get("team_draft") or []
    refine = False
    if 0 <= provisional.slot_index < len(draft):
        slot = draft[provisional.slot_index]
        refine = draft_has_complete_build(slot) and to_id(
            str(slot.species.value or "")
        ) == to_id(provisional.species)

    team_notes = ally_support_investment_notes(provisional, state)
    siblings = _usage_spread_siblings(
        provisional, state, team_notes=team_notes, regulation=regulation
    )
    if len(siblings) < _MAX_SIBLINGS:
        for opt in _vgcpastes_siblings(
            provisional, state, team_notes=team_notes, regulation=regulation
        ):
            if len(siblings) >= _MAX_SIBLINGS:
                break
            if any(o["option_id"] == opt["option_id"] for o in siblings):
                continue
            siblings.append(opt)

    if not siblings and not refine:
        # Still offer nothing when no honest peers — empty groups OK
        featured = featured_or_common_set(provisional.species, regulation=regulation)
        del featured  # provenance hint only; provisional already aligned
        return (), ()

    by_axis: dict[BuildAxis, list[BuildConfirmationOption]] = {}
    default_ids: list[str] = []

    if refine:
        default = _identity_option(
            provisional,
            axis="bundled",
            provenance="user_current",
            label="Keep current build",
            tradeoff="No change from imported/locked set",
            team_notes=team_notes,
        )
        by_axis.setdefault("bundled", []).append(default)
        default_ids.append(default["option_id"])
    elif siblings:
        # Greenfield: identity default in first sibling axis group
        first_axis: BuildAxis = siblings[0]["axis"]
        default = _identity_option(
            provisional,
            axis=first_axis,
            provenance="featured",
            label="Recommended default",
            tradeoff="Keep the refined usage recommendation",
            team_notes=team_notes,
        )
        by_axis.setdefault(first_axis, []).append(default)
        default_ids.append(default["option_id"])

    for sib in siblings:
        by_axis.setdefault(sib["axis"], []).append(sib)
        if sib["axis"] not in {o.split(":")[0] for o in default_ids}:
            # ensure each group has a default pointer — identity already added for first
            pass

    groups: list[BuildOptionGroup] = []
    for axis, options in by_axis.items():
        # Cap siblings already applied; ensure default id per group
        if not any(o["option_id"] in default_ids for o in options):
            # add identity for this axis if missing
            ident = _identity_option(
                provisional,
                axis=axis,
                provenance="user_current" if refine else "featured",
                label="Keep current" if refine else "Recommended default",
                tradeoff="No change on this axis",
                team_notes=team_notes,
            )
            options = [ident, *options]
            default_ids.append(ident["option_id"])
        groups.append(
            BuildOptionGroup(
                axis=axis,
                prompt=f"Choose {axis.replace('_', '/')}:",
                options=tuple(options),
            )
        )

    # One default id per group
    final_defaults: list[str] = []
    for group in groups:
        chosen = next(
            (o["option_id"] for o in group["options"] if o["option_id"] in default_ids),
            group["options"][0]["option_id"],
        )
        final_defaults.append(chosen)

    return tuple(groups), tuple(final_defaults)
