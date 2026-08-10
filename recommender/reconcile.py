"""Theme/archetype reconciliation (ADR-020)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Literal, Optional

from recommender.calc_client import CalcClient, CalcRequest, FieldSpec
from recommender.ids import to_id
from recommender.legality import load_snapshot
from recommender.matchup import Severity
from recommender.recommend import infer_role
from recommender.state import (
    Attr,
    PendingFlag,
    RecommenderState,
    Slot,
    SupersededEntry,
)

Groundedness = Literal[
    "mechanically-checkable",
    "enumerable-but-uncoded",
    "judgment-only",
]

SLOT_ATTRS = ("role", "species", "item", "moveset", "spread", "nature")

_CHOICE_ITEMS = frozenset({"choiceband", "choicespecs", "choicescarf"})
_ITEM_SWAP_MOVES = frozenset({"trick", "switcheroo"})

# Narration/classify only — never used by fit-check logic.
COMPOSITE_ARCHETYPE_LABELS: dict[str, list[str]] = {
    "TailRoom": ["Tailwind", "TrickRoom"],
}

_POKEMON_TYPES = frozenset(
    {
        "Normal",
        "Fire",
        "Water",
        "Electric",
        "Grass",
        "Ice",
        "Fighting",
        "Poison",
        "Ground",
        "Flying",
        "Psychic",
        "Bug",
        "Rock",
        "Ghost",
        "Dragon",
        "Dark",
        "Steel",
        "Fairy",
    }
)

_WEATHER_COMMITMENTS: dict[str, str] = {
    "Rain": "Rain",
    "Sun": "Sun",
    "Sand": "Sand",
    "Snow": "Snow",
}

_COMPONENT_ROLE_FIT: dict[str, frozenset[str]] = {
    "TrickRoom": frozenset({"trick_room_sweeper"}),
    "Tailwind": frozenset(
        {
            "support_speed_control",
            "fast_attacker",
            "fast_physical_attacker",
            "fast_special_attacker",
            "fast_mixed_attacker",
            "fast_pivot",
        }
    ),
}


@dataclass
class FitResult:
    satisfies: bool
    groundedness: Groundedness
    severity: Optional[Severity] = None
    ambiguous: bool = False
    detail: Optional[str] = None


def check_theme_fit(
    slot: Slot,
    commitment: str,
    *,
    snap: dict[str, Any] | None = None,
    calc_client: CalcClient | None = None,
) -> FitResult | None:
    """Four-tier fit check; returns None when no tier can resolve."""
    snap = snap or load_snapshot()
    for tier in (
        lambda: _tier1_direct(slot, commitment, snap),
        lambda: _tier2_calc_diff(slot, commitment, calc_client),
        lambda: _tier3_role(slot, commitment),
        lambda: _tier4_judgment(commitment),
    ):
        result = tier()
        if result is not None:
            return result
    return None


def check_archetype_fit(
    slot: Slot,
    components: list[str],
    *,
    snap: dict[str, Any] | None = None,
    calc_client: CalcClient | None = None,
) -> FitResult:
    if not components:
        return FitResult(
            satisfies=True,
            groundedness="judgment-only",
            detail="no archetype components",
        )
    per_component: list[FitResult] = []
    for component in components:
        fit = check_theme_fit(slot, component, snap=snap, calc_client=calc_client)
        if fit is None:
            continue
        per_component.append(fit)
        if fit.satisfies and not fit.ambiguous:
            return FitResult(
                satisfies=True,
                groundedness=fit.groundedness,
                severity=fit.severity,
                ambiguous=fit.ambiguous,
                detail=fit.detail or f"fits {component}",
            )
    if not per_component:
        return FitResult(
            satisfies=False,
            groundedness="judgment-only",
            detail="unresolvable for all components",
        )
    # None satisfied — pick the strongest mechanical signal for action routing.
    mechanical = [
        r
        for r in per_component
        if r.groundedness in ("mechanically-checkable", "enumerable-but-uncoded")
        and not r.ambiguous
    ]
    if mechanical:
        worst = mechanical[0]
        return FitResult(
            satisfies=False,
            groundedness=worst.groundedness,
            severity=worst.severity,
            ambiguous=any(r.ambiguous for r in per_component),
            detail=worst.detail,
        )
    ambiguous = [r for r in per_component if r.ambiguous]
    if ambiguous:
        return ambiguous[0]
    return FitResult(
        satisfies=False,
        groundedness="judgment-only",
        detail=per_component[-1].detail,
    )


def reconcile_on_archetype_change(
    state: RecommenderState,
    new_components: list[str],
    *,
    calc_client: CalcClient | None = None,
) -> dict:
    draft = list(state["team_draft"])
    superseded = list(state.get("superseded", []))
    pending_flags = list(state.get("pending_flags", []))
    turn = state.get("turn", 0)
    changed = False

    for slot_index, slot in enumerate(draft):
        for attr_name in SLOT_ATTRS:
            attr: Attr[Any] = getattr(slot, attr_name)
            if not attr.locked or attr.value is None:
                continue
            fit = check_archetype_fit(
                slot, new_components, calc_client=calc_client
            )
            if fit.satisfies or fit.ambiguous:
                continue
            updates, new_sup, new_flags = _apply_mismatch(
                slot_index,
                attr_name,
                attr,
                fit,
                turn,
                sibling_change=False,
            )
            if updates:
                slot = draft[slot_index]
                draft[slot_index] = replace(slot, **updates)
                changed = True
            superseded.extend(new_sup)
            pending_flags.extend(new_flags)

    out: dict = {}
    if changed:
        out["team_draft"] = draft
    if superseded != state.get("superseded", []):
        out["superseded"] = superseded
    if pending_flags != state.get("pending_flags", []):
        out["pending_flags"] = pending_flags
    return out


def reconcile_on_sibling_change(
    slot: Slot,
    changed_attr: str,
    *,
    slot_index: int,
    turn: int,
    components: list[str] | None = None,
) -> tuple[Slot, list[SupersededEntry], list[PendingFlag]]:
    """Re-check other locked attrs after a sibling lock; flags non-decisive mismatches."""
    superseded: list[SupersededEntry] = []
    pending_flags: list[PendingFlag] = []
    updates: dict[str, Attr[Any]] = {}

    for attr_name in SLOT_ATTRS:
        if attr_name == changed_attr:
            continue
        attr: Attr[Any] = getattr(slot, attr_name)
        if not attr.locked or attr.value is None:
            continue
        fit = _check_sibling_fit(slot, changed_attr, attr_name, components)
        if fit.satisfies or fit.ambiguous:
            continue
        if fit.severity in ("costly", "toss-up"):
            pending_flags.append(
                _pending_flag(slot_index, attr_name, attr.value, "sibling_mismatch")
            )
            continue
        slot_updates, new_sup, new_flags = _apply_mismatch(
            slot_index,
            attr_name,
            attr,
            fit,
            turn,
            sibling_change=True,
        )
        updates.update(slot_updates)
        superseded.extend(new_sup)
        pending_flags.extend(new_flags)

    if updates:
        slot = replace(slot, **updates)
    return slot, superseded, pending_flags


def _check_sibling_fit(
    slot: Slot,
    changed_attr: str,
    target_attr: str,
    components: list[str] | None,
) -> FitResult:
    """Sibling checks: mechanical attr-pair first, then calc diff, then archetype."""
    pair = {changed_attr, target_attr}
    if pair & {"item", "moveset"}:
        mech = _tier1_choice_status_moves(slot) or _tier1_speed_direction(slot)
        if mech is not None:
            return mech
    tier2 = _tier2_sibling_diff(slot, changed_attr, target_attr)
    if tier2 is not None:
        return tier2
    if components:
        return check_archetype_fit(slot, components)
    return FitResult(satisfies=True, groundedness="judgment-only")


def _locked_choice_item_id(slot: Slot) -> str | None:
    if not slot.item.locked or not slot.item.value:
        return None
    iid = to_id(slot.item.value)
    return iid if iid in _CHOICE_ITEMS else None


def _moveset_has_disallowed_status(slot: Slot, snap: dict[str, Any]) -> bool:
    if not slot.moveset.locked or not slot.moveset.value:
        return False
    moves_meta = snap.get("moves") or {}
    for m in slot.moveset.value:
        mid = to_id(m)
        if mid in _ITEM_SWAP_MOVES:
            continue
        meta = moves_meta.get(mid) or {}
        if (meta.get("category") or "") == "Status":
            return True
    return False


def _moveset_has_trick_room(slot: Slot) -> bool:
    if not slot.moveset.locked or not slot.moveset.value:
        return False
    return any(to_id(m) == "trickroom" for m in slot.moveset.value)


def _tier1_choice_status_moves(
    slot: Slot, snap: dict[str, Any] | None = None
) -> FitResult | None:
    """Choice item + non-damaging move (except Trick/Switcheroo) is a mismatch."""
    if _locked_choice_item_id(slot) is None:
        return None
    snap = snap or load_snapshot()
    if not _moveset_has_disallowed_status(slot, snap):
        return None
    return FitResult(
        satisfies=False,
        groundedness="mechanically-checkable",
        detail="choice item incompatible with non-damaging move",
    )


def _tier1_speed_direction(slot: Slot) -> FitResult | None:
    """Choice Scarf + Trick Room moveset: opposite Speed directions."""
    if _locked_choice_item_id(slot) != "choicescarf":
        return None
    if not _moveset_has_trick_room(slot):
        return None
    return FitResult(
        satisfies=False,
        groundedness="mechanically-checkable",
        detail="Choice Scarf conflicts with Trick Room Speed direction",
    )


def simultaneous_lock_conflicts(
    slot: Slot, snap: dict[str, Any] | None = None
) -> list[tuple[str, ...]]:
    """Attr groups that conflict under Part 2 rules (for N-attr simultaneous locks)."""
    snap = snap or load_snapshot()
    groups: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()

    def add(group: tuple[str, ...]) -> None:
        key = tuple(sorted(group))
        if key not in seen:
            seen.add(key)
            groups.append(key)

    if _tier1_choice_status_moves(slot, snap) is not None:
        add(("item", "moveset"))
    if _tier1_speed_direction(slot) is not None:
        add(("item", "moveset"))
    return groups


def _apply_mismatch(
    slot_index: int,
    attr_name: str,
    attr: Attr[Any],
    fit: FitResult,
    turn: int,
    *,
    sibling_change: bool,
) -> tuple[dict[str, Attr[Any]], list[SupersededEntry], list[PendingFlag]]:
    mechanical = fit.groundedness in (
        "mechanically-checkable",
        "enumerable-but-uncoded",
    )
    pending: list[PendingFlag] = []
    superseded: list[SupersededEntry] = []

    if attr.exempt_from_theme:
        if mechanical:
            pending.append(
                _pending_flag(slot_index, attr_name, attr.value, "flag_exempt_conflict")
            )
        return {}, superseded, pending

    if fit.groundedness == "judgment-only":
        pending.append(
            _pending_flag(slot_index, attr_name, attr.value, "judgment_mismatch")
        )
        return {}, superseded, pending

    if mechanical:
        if fit.severity in ("costly", "toss-up"):
            pending.append(
                _pending_flag(
                    slot_index,
                    attr_name,
                    attr.value,
                    "sibling_mismatch" if sibling_change else "severity_mismatch",
                )
            )
            return {}, superseded, pending
        superseded.append(
            SupersededEntry(
                slot_index=slot_index,
                attr=attr_name,  # type: ignore[typeddict-item]
                value=attr.value,
                reason=fit.detail or "theme mismatch",
                turn_removed=turn,
            )
        )
        cleared = replace(
            attr,
            value=None,
            locked=False,
            still_active=False,
        )
        return {attr_name: cleared}, superseded, pending

    pending.append(_pending_flag(slot_index, attr_name, attr.value, "theme_mismatch"))
    return {}, superseded, pending


def _pending_flag(
    slot_index: int, attr_name: str, value: object, flag_kind: str
) -> PendingFlag:
    return PendingFlag(
        slot_index=slot_index,
        attr=attr_name,  # type: ignore[typeddict-item]
        value=value,
        flag_kind=flag_kind,
    )


def _tier1_direct(slot: Slot, commitment: str, snap: dict[str, Any]) -> FitResult | None:
    cid = commitment.strip()
    if cid in _WEATHER_COMMITMENTS:
        return _tier1_weather(slot, cid, snap)
    if cid in _POKEMON_TYPES:
        return _tier1_type(slot, cid, snap)
    return None


def _tier1_weather(slot: Slot, weather: str, snap: dict[str, Any]) -> FitResult | None:
    if not slot.species.value:
        return None
    formes = _reachable_formes(slot, snap)
    if not formes:
        return None
    type_sets = [_species_types(snap, f) for f in formes]
    type_sets = [t for t in type_sets if t]
    if not type_sets:
        return None
    if len({tuple(sorted(t)) for t in type_sets}) > 1:
        return FitResult(
            satisfies=False,
            groundedness="mechanically-checkable",
            ambiguous=True,
            detail="reachable formes disagree on typing",
        )
    types = type_sets[0]
    if weather == "Rain":
        if "Water" in types:
            return FitResult(
                satisfies=True,
                groundedness="mechanically-checkable",
                detail="Water-type benefits from Rain",
            )
        if "Fire" in types and "Water" not in types:
            return FitResult(
                satisfies=False,
                groundedness="mechanically-checkable",
                detail="Fire-type STAB weakened under Rain",
            )
    if weather == "Sun":
        if "Fire" in types:
            return FitResult(
                satisfies=True,
                groundedness="mechanically-checkable",
                detail="Fire-type benefits from Sun",
            )
        if "Water" in types and "Fire" not in types:
            return FitResult(
                satisfies=False,
                groundedness="mechanically-checkable",
                detail="Water-type STAB weakened under Sun",
            )
    return None


def _tier1_type(slot: Slot, want_type: str, snap: dict[str, Any]) -> FitResult | None:
    if not slot.species.value:
        return None
    formes = _reachable_formes(slot, snap)
    type_sets = [_species_types(snap, f) for f in formes]
    type_sets = [t for t in type_sets if t]
    if not type_sets:
        return None
    if len({tuple(sorted(t)) for t in type_sets}) > 1:
        has_type = any(want_type in t for t in type_sets)
        lacks_all = all(want_type not in t for t in type_sets)
        if has_type and not lacks_all:
            return FitResult(
                satisfies=False,
                groundedness="mechanically-checkable",
                ambiguous=True,
                detail=f"formes disagree on {want_type} typing",
            )
    types = set().union(*type_sets)
    if want_type in types:
        return FitResult(
            satisfies=True,
            groundedness="mechanically-checkable",
            detail=f"has {want_type} type",
        )
    return FitResult(
        satisfies=False,
        groundedness="mechanically-checkable",
        detail=f"missing {want_type} type",
    )


def _tier2_calc_diff(
    slot: Slot,
    commitment: str,
    calc_client: CalcClient | None,
) -> FitResult | None:
    weather = _WEATHER_COMMITMENTS.get(commitment)
    if not weather or not slot.verification:
        return None
    field: FieldSpec = {"weather": weather, "gameType": "Doubles"}  # type: ignore[typeddict-item]
    return _recompute_verification(slot, field, calc_client)


def _tier2_sibling_diff(
    slot: Slot,
    changed_attr: str,
    target_attr: str,
) -> FitResult | None:
    if changed_attr != "species" or target_attr != "moveset":
        return None
    if not slot.verification or not slot.species.value or not slot.moveset.value:
        return None
    # Neutral recompute under new species line — diff stored verification.
    field: FieldSpec = {"gameType": "Doubles"}
    return _recompute_verification(slot, field, None)


def _recompute_verification(
    slot: Slot,
    field: FieldSpec,
    calc_client: CalcClient | None,
) -> FitResult | None:
    calc_entries = [v for v in slot.verification if v.get("tool_called") == "calc"]
    if not calc_entries:
        return None
    client = calc_client or CalcClient()
    stored = calc_entries[-1].get("result", "")
    species = slot.species.value or ""
    moves = slot.moveset.value or []
    if not species or not moves:
        return None
    move = moves[0]
    req: CalcRequest = {
        "attacker": {"species": species, "moves": moves},
        "defender": {"species": "Garchomp"},
        "move": move,
        "field": field,
    }
    try:
        raw = client.calculate(req)
    except Exception:
        return None
    if not isinstance(raw, dict) or "error" in raw:
        return None
    new_range = raw.get("damageRange") or [0, 0]
    new_max = int(new_range[-1]) if new_range else 0
    stored_max = _parse_stored_damage_max(stored)
    if stored_max is None:
        return FitResult(
            satisfies=True,
            groundedness="mechanically-checkable",
            severity="toss-up",
            detail="calc diff inconclusive",
        )
    if stored_max <= 0:
        return FitResult(
            satisfies=new_max > 0,
            groundedness="mechanically-checkable",
            severity="decisive" if new_max == 0 else "costly",
        )
    ratio = new_max / stored_max
    if ratio >= 0.8:
        return FitResult(
            satisfies=True,
            groundedness="mechanically-checkable",
            severity="decisive",
            detail="calc within tolerance",
        )
    if ratio >= 0.5:
        return FitResult(
            satisfies=False,
            groundedness="mechanically-checkable",
            severity="costly",
            detail="calc damage reduced under new conditions",
        )
    return FitResult(
        satisfies=False,
        groundedness="mechanically-checkable",
        severity="toss-up",
        detail="calc damage materially reduced",
    )


def _parse_stored_damage_max(stored: str) -> int | None:
    import re

    nums = [int(x) for x in re.findall(r"\d+", stored)]
    return max(nums) if nums else None


def _tier3_role(slot: Slot, commitment: str) -> FitResult | None:
    allowed = _COMPONENT_ROLE_FIT.get(commitment)
    if not allowed:
        return None
    moves = slot.moveset.value or []
    item = slot.item.value or ""
    if not moves and not item:
        return None
    role = infer_role(moves, item, slot.ability.value)
    if role in allowed:
        return FitResult(
            satisfies=True,
            groundedness="mechanically-checkable",
            detail=f"role {role} fits {commitment}",
        )
    return FitResult(
        satisfies=False,
        groundedness="mechanically-checkable",
        detail=f"role {role} does not fit {commitment}",
    )


def _tier4_judgment(commitment: str) -> FitResult:
    return FitResult(
        satisfies=False,
        groundedness="judgment-only",
        detail=f"no grounded check for {commitment!r}",
    )


def _reachable_formes(slot: Slot, snap: dict[str, Any]) -> list[str]:
    species = slot.species.value
    if not species:
        return []
    sid = to_id(species)
    entry = snap.get("species", {}).get(sid)
    if not entry:
        return [sid]
    base = entry.get("base_species_id") or sid
    formes: list[str] = []
    for candidate in (sid, base):
        if candidate and candidate not in formes:
            formes.append(candidate)
    item = slot.item.value
    if item:
        mega = _item_mega_forme(to_id(item), base, snap)
        if mega and mega not in formes:
            formes.append(mega)
    return formes


def _item_mega_forme(item_id: str, base_species_id: str, snap: dict[str, Any]) -> str | None:
    if item_id.endswith("itex"):
        candidate = f"{base_species_id}megax"
    elif item_id.endswith("itey"):
        candidate = f"{base_species_id}megay"
    elif item_id.endswith("ite"):
        candidate = f"{base_species_id}mega"
    else:
        return None
    if candidate in snap.get("species", {}):
        return candidate
    return None


def _species_types(snap: dict[str, Any], species_id: str) -> list[str]:
    entry = snap.get("species", {}).get(species_id)
    if not entry:
        return []
    return list(entry.get("types") or [])
