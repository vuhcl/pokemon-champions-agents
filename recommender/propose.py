"""Dependency-circle team_draft proposal (ADR-015 Amendment 2026-07-27c).

Single deterministic pass from currently-locked attributes — no privileged order,
no recursive re-propagation. Role Compendium / ability taxonomy remain follow-ups.
Move-narrowing is the usage-miss moveset fallback (ADR-015 27f).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, get_args

from recommender.coverage import compute_team_coverage, detect_spof, get_relevant_threats
from recommender.ids import to_id
from recommender.legality import load_snapshot
from recommender.recommend import (
    RoleArchetype,
    _DEPRECATED_ROLE_ALIASES,
    infer_role,
    role_spread,
)
from recommender.resolved_builds import get_resolved_build
from recommender.state import (
    Attr,
    ReasonRef,
    RecommenderState,
    Slot,
    StatsTable,
    TargetRoleDecision,
    TargetRoleId,
    TargetRoleResult,
    UnresolvedTargetRoleDecision,
    all_locked,
)
from recommender.usage_data import SLOT_THREAT_N, TEAM_THREAT_N, featured_or_common_set
from recommender.usage_spreads import effective_spe, select_usage_spread

_COMPONENT_TO_ROLE: dict[str, TargetRoleId] = {
    "TrickRoom": "trick_room_setter",
    "Tailwind": "tailwind_setter",
}

_ROLE_ARCHETYPES = frozenset(get_args(RoleArchetype)) | frozenset(_DEPRECATED_ROLE_ALIASES)
_CHOICE_ITEMS = frozenset({"choiceband", "choicespecs", "choicescarf"})
_ITEM_SWAP_MOVES = frozenset({"trick", "switcheroo"})
_OFFENSE_ROLES = frozenset(
    {
        "fast_attacker",
        "bulky_attacker",
        "fast_physical_attacker",
        "fast_special_attacker",
        "fast_mixed_attacker",
        "standard_physical_attacker",
        "standard_special_attacker",
        "standard_mixed_attacker",
        "bulky_physical_attacker",
        "bulky_special_attacker",
        "bulky_mixed_attacker",
        "fast_pivot",
        "trick_room_sweeper",
        "swords_dance_attacker",
        "nasty_plot_attacker",
    }
)


def fill_team_draft(state: RecommenderState) -> dict:
    draft = list(state["team_draft"])
    regulation = state.get("regulation_mod") or "champions"
    changed = False
    default_role_used = False

    components = list((state.get("archetype") or Attr()).value or [])
    present_roles = {s.role.value for s in draft if s.role.value}
    has_archetype_pick = any(
        (role := _COMPONENT_TO_ROLE.get(c)) is not None and role not in present_roles
        for c in components
    )
    needs_gap_signal = (
        any(not all_locked(s) and s.role.value is None for s in draft)
        and not present_roles
        and not has_archetype_pick
    )
    has_gap = False
    if needs_gap_signal:
        if any(s.species.value for s in draft):
            has_gap = True
        else:
            candidates = get_relevant_threats(state, n=TEAM_THREAT_N)
            specs = [c.spec for c in candidates]
            coverage = compute_team_coverage(draft, specs, regulation=regulation)
            spofs = detect_spof(draft, specs, regulation=regulation)
            has_gap = bool(
                any(not r.covering_slot_indices for r in coverage) or spofs
            )

    for i, slot in enumerate(draft):
        if all_locked(slot):
            continue

        # Team-review role fill when empty (coverage/archetype).
        if slot.role.value is None and not slot.role.locked:
            # Locked moveset may imply role via propagation below; try gap/archetype first
            # only when no locked moveset pin will set it.
            if not (slot.moveset.locked and slot.moveset.value):
                picked = _pick_role(draft, components, has_gap, default_role_used)
                if isinstance(picked, TargetRoleDecision):
                    role_name = picked.role_id
                    ref = picked.provenance[0]
                    if ref == "coverage_gap":
                        default_role_used = True
                    draft[i] = replace(
                        slot,
                        role=Attr(
                            value=role_name,
                            locked=False,
                            reason=ReasonRef(kind="core_detection", ref=ref),
                        ),
                    )
                    slot = draft[i]
                    changed = True

        new_slot, did = _propagate_and_refine(slot, state, regulation=regulation)
        if did:
            draft[i] = new_slot
            changed = True

    return {"team_draft": draft} if changed else {}


def _pick_role(
    draft: list[Slot],
    components: list[str],
    has_gap: bool,
    default_role_used: bool,
) -> TargetRoleResult | None:
    """Choose an actionable role for an open slot, never an anchor classification."""
    present = {s.role.value for s in draft if s.role.value}
    candidates = tuple(
        (comp, role)
        for comp in components
        if (role := _COMPONENT_TO_ROLE.get(comp)) and role not in present
    )
    role_ids = tuple(dict.fromkeys(role for _, role in candidates))
    if len(role_ids) > 1:
        return UnresolvedTargetRoleDecision(
            reason="ambiguous_speed_control",
            ambiguity=role_ids,
            source="_pick_role",
            evidence=tuple(comp for comp, _ in candidates),
            needed_constraints=tuple(f"role:{role}" for role in role_ids),
            provenance=("archetype_components",),
        )
    if candidates:
        comp, role = candidates[0]
        return TargetRoleDecision(
            role_id=role,
            source="_pick_role",
            evidence=(comp,),
            needed_constraints=(f"role:{role}",),
            confidence="high",
            provenance=(comp,),
        )

    if has_gap and not default_role_used and not present:
        return TargetRoleDecision(
            role_id="bulky_attacker",
            source="_pick_role",
            evidence=("coverage_gap",),
            wanted_constraints=("improve_team_coverage",),
            confidence="low",
            provenance=("coverage_gap",),
        )
    return None


def _propagate_and_refine(
    slot: Slot, state: RecommenderState, *, regulation: str
) -> tuple[Slot, bool]:
    """Single-pass dependency-circle fill from locked pins + residual defaults."""
    updates: dict[str, Attr[Any]] = {}
    implied: dict[str, Any] = {}

    item_id = to_id(slot.item.value) if slot.item.locked and slot.item.value else ""
    moves = list(slot.moveset.value) if slot.moveset.locked and slot.moveset.value else None
    has_tr = bool(moves and any(to_id(m) == "trickroom" for m in moves))

    # --- Propagation from locked pins (no overwrite of existing values) ---
    if moves is not None and slot.role.value is None and not slot.role.locked:
        item_for_role = slot.item.value or ""
        ability_for_role = slot.ability.value if slot.ability.value else None
        implied["role"] = infer_role(moves, item_for_role, ability_for_role)

    if item_id in _CHOICE_ITEMS:
        if slot.spread.value is None and not slot.spread.locked:
            implied["spread"] = _choice_spread(item_id)
        if (
            item_id == "choicescarf"
            and slot.nature.value is None
            and not slot.nature.locked
            and slot.species.value
        ):
            # secondary: after max-Spe default; may set nature below
            pass

    if has_tr and slot.spread.value is None and not slot.spread.locked:
        tr_spread = dict(role_spread("trick_room_sweeper"))
        if "spread" in implied and implied["spread"] != tr_spread:
            # Contradictory pins (e.g. Scarf + TR) — leave unset.
            implied.pop("spread", None)
        else:
            implied["spread"] = tr_spread

    # Scarf + TR both locked → drop contradictory spread implication
    if item_id == "choicescarf" and has_tr:
        implied.pop("spread", None)

    reason_prop = ReasonRef(kind="tier2_heuristic", ref="dependency_circle")
    for attr, value in implied.items():
        cur: Attr[Any] = getattr(slot, attr)
        if cur.value is not None or cur.locked:
            continue
        updates[attr] = Attr(value=value, locked=False, reason=reason_prop)

    working = replace(slot, **updates) if updates else slot

    # ponytail: role→species needs Role Compendium (ADR-019).
    if working.role.value is not None and working.species.value is None:
        return working, bool(updates)

    if working.species.value is None:
        return working, bool(updates)

    refined, did_refine = _refine_defaults(working, state, regulation=regulation)
    return refined, bool(updates) or did_refine


def _choice_spread(item_id: str) -> StatsTable:
    if item_id == "choiceband":
        return {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32}
    if item_id == "choicespecs":
        return {"hp": 2, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 32}
    # choicescarf — max Spe primary
    return {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32}


def _default_item_candidates(role: str | None) -> tuple[str, ...]:
    if role in _OFFENSE_ROLES or (role or "").endswith("_attacker"):
        return ("Life Orb", "Sitrus Berry", "Focus Sash")
    return ("Sitrus Berry", "Life Orb", "Focus Sash")


def _synthesize_item(slot: Slot, state: RecommenderState) -> str | None:
    from recommender.legality import is_item_legal, team_item_ids

    snap = load_snapshot()
    used = team_item_ids(list(state.get("team_draft") or []))
    for cand in _default_item_candidates(slot.role.value):
        if to_id(cand) in used:
            continue
        if is_item_legal(snap, cand):
            return cand
    return None


def _nature_for_spread(spread: StatsTable, role: str | None) -> str:
    spe = int(spread.get("spe", 0))
    atk = int(spread.get("atk", 0))
    spa = int(spread.get("spa", 0))
    defense = int(spread.get("def", 0))
    spd = int(spread.get("spd", 0))
    bulky_attacker = role == "bulky_attacker" or (
        bool(role) and role.startswith("bulky_") and role.endswith("_attacker")
    )
    if spe == 0:
        return "Quiet" if spa >= atk else "Brave"
    if spe >= 28:
        if atk >= spa:
            return "Adamant" if bulky_attacker else "Jolly"
        return "Modest" if bulky_attacker else "Timid"
    if atk > spa and atk > 0:
        return "Adamant"
    if spa > atk and spa > 0:
        return "Modest"
    if defense >= spd:
        return "Bold" if spa >= atk else "Impish"
    return "Calm" if spa >= atk else "Careful"


def _refine_defaults(
    slot: Slot, state: RecommenderState, *, regulation: str
) -> tuple[Slot, bool]:
    # Calc verify stays optional post-complete elsewhere; never required to emit ProvisionalSlot.
    from recommender.anchor_roles import _ability_for_target_role, _unique_legal_ability
    from recommender.move_narrowing import assemble_moveset_fallback

    species = slot.species.value
    assert species is not None

    need_ability = not slot.ability.locked and slot.ability.value is None
    need_moves = not slot.moveset.locked and slot.moveset.value is None
    need_item = not slot.item.locked and slot.item.value is None
    need_spread = not slot.spread.locked and slot.spread.value is None
    need_nature = not slot.nature.locked and slot.nature.value is None

    moves = list(slot.moveset.value) if slot.moveset.value else None
    item = slot.item.value
    usage = (
        featured_or_common_set(species, regulation=regulation)
        if need_ability or need_moves or need_item
        else None
    )
    usage_missed = False
    updates: dict[str, Attr[Any]] = {}
    spread = dict(slot.spread.value) if slot.spread.value else None

    if usage:
        if need_ability and usage.get("ability"):
            updates["ability"] = Attr(
                value=str(usage["ability"]),
                locked=False,
                reason=ReasonRef(kind="tier2_heuristic", ref="usage"),
            )
        if need_nature and usage.get("nature"):
            updates["nature"] = Attr(
                value=str(usage["nature"]),
                locked=False,
                reason=ReasonRef(kind="tier2_heuristic", ref="usage"),
            )
        if need_moves and moves is None:
            moves = list(usage.get("moves") or [])
        if need_item and item is None:
            item = usage.get("item")
    else:
        usage_missed = bool(need_moves or need_item or need_ability)
        # 1. Ability (unique legality_only, else role-constraint synthesized)
        if need_ability:
            unique = _unique_legal_ability(species)
            if unique:
                updates["ability"] = Attr(
                    value=unique,
                    locked=False,
                    reason=ReasonRef(kind="tier2_heuristic", ref="legality_only"),
                )
            else:
                role_ability = _ability_for_target_role(species, slot.role.value)
                if role_ability:
                    updates["ability"] = Attr(
                        value=role_ability,
                        locked=False,
                        reason=ReasonRef(
                            kind="tier2_heuristic", ref="tier3_role_ability"
                        ),
                    )
        # 2. Item defaults
        if need_item and item is None:
            item = _synthesize_item(slot, state)
        # 3. Moves via extended prefs
        if need_moves and moves is None:
            assembled = assemble_moveset_fallback(species, slot, state)
            moves = assembled or None

    # Soft Choice moveset bias when item locked Choice and moveset empty
    item_id = to_id(item) if item else ""
    if need_moves and moves and item_id in _CHOICE_ITEMS:
        moves = _bias_choice_moveset(moves)

    if need_moves and moves and (usage_missed or not usage):
        if usage_missed:
            updates["moveset"] = Attr(
                value=moves,
                locked=False,
                reason=ReasonRef(kind="tier2_heuristic", ref="move_narrowing"),
            )

    if need_item and item and usage_missed:
        updates["item"] = Attr(
            value=item,
            locked=False,
            reason=ReasonRef(kind="tier2_heuristic", ref="tier3_item_default"),
        )

    # 4. Spread once moves+item exist
    reason = ReasonRef(kind="tier2_heuristic", ref=species)
    if (need_moves or need_item or need_spread) and moves and item:
        cached = get_resolved_build(species, moves, item, regulation)
        if cached and need_spread and spread is None:
            if not (
                slot.item.locked
                and to_id(slot.item.value or "") == "choicescarf"
                and slot.moveset.locked
                and slot.moveset.value
                and any(to_id(m) == "trickroom" for m in slot.moveset.value)
            ):
                spread = dict(cached["spread"])
                reason = ReasonRef(kind="tier1_cache", ref=species)
            else:
                reason = ReasonRef(kind="tier2_heuristic", ref=species)
        elif cached:
            reason = ReasonRef(kind="tier1_cache", ref=species)
        else:
            reason = ReasonRef(kind="tier2_heuristic", ref=species)
            if need_spread and spread is None:
                if slot.item.locked and item_id in _CHOICE_ITEMS:
                    pass
                else:
                    role_name = slot.role.value
                    role = (
                        role_name
                        if role_name in _ROLE_ARCHETYPES
                        else infer_role(moves, item, slot.ability.value)
                    )
                    choice = select_usage_spread(
                        species,
                        role,
                        moves,
                        regulation=regulation,
                        threats=get_relevant_threats(state, n=SLOT_THREAT_N),
                    )
                    if choice:
                        spread = dict(choice.spread)
                        reason = ReasonRef(
                            kind="tier2_heuristic", ref=choice.source
                        )
                        if need_nature and choice.nature and "nature" not in updates:
                            updates["nature"] = Attr(
                                value=choice.nature,
                                locked=False,
                                reason=reason,
                            )
                    else:
                        spread = dict(role_spread(role))  # type: ignore[arg-type]
                        reason = ReasonRef(
                            kind="tier2_heuristic", ref="tier3_role"
                        )

        if need_moves and not usage_missed:
            updates["moveset"] = Attr(value=moves, locked=False, reason=reason)
        if need_item and not usage_missed:
            updates["item"] = Attr(value=item, locked=False, reason=reason)
        if need_spread and spread is not None:
            updates["spread"] = Attr(value=spread, locked=False, reason=reason)

    working = replace(slot, **updates) if updates else slot

    # 5. Nature companion when still unset and spread exists
    if (
        need_nature
        and "nature" not in updates
        and working.nature.value is None
        and working.spread.value
    ):
        nature = _nature_for_spread(working.spread.value, working.role.value)
        updates = {
            **updates,
            "nature": Attr(
                value=nature,
                locked=False,
                reason=ReasonRef(kind="tier2_heuristic", ref="tier3_nature"),
            ),
        }
        working = replace(slot, **updates)

    # Secondary Scarf Spe overshoot → nature correction
    if (
        need_nature
        and working.item.locked
        and to_id(working.item.value or "") == "choicescarf"
        and working.species.value
        and working.spread.value
    ):
        nature = _scarf_nature_correction(working, state)
        if nature:
            updates = {
                **updates,
                "nature": Attr(
                    value=nature,
                    locked=False,
                    reason=ReasonRef(kind="tier2_heuristic", ref="scarf_spe_overshoot"),
                ),
            }
            working = replace(slot, **updates)

    return working, bool(updates)


def _bias_choice_moveset(moves: list[str]) -> list[str]:
    snap = load_snapshot()
    moves_meta = snap.get("moves") or {}
    out: list[str] = []
    for m in moves:
        mid = to_id(m)
        if mid in _ITEM_SWAP_MOVES:
            out.append(m)
            continue
        meta = moves_meta.get(mid) or {}
        if (meta.get("category") or "") == "Status":
            continue
        out.append(m)
    return out or moves


def scarf_clears_benchmarks(
    slot: Slot,
    state: RecommenderState,
    *,
    nature: str = "Adamant",
) -> bool:
    """True if Scarf Spe with offensive nature already outspeeds relevant threats."""
    species = slot.species.value
    spread = slot.spread.value
    if not species or not spread:
        return False
    my_spe = effective_spe(species, spread, nature, scarf=True)
    threats = get_relevant_threats(state, n=SLOT_THREAT_N)
    if not threats:
        return False
    cleared = 0
    for t in threats:
        opp_species = t.spec.get("species") or ""
        usage = featured_or_common_set(
            opp_species, regulation=state.get("regulation_mod") or "champions"
        )
        opp_spread = dict((usage or {}).get("evs") or {"spe": 32})
        opp_nat = (usage or {}).get("nature") or "Jolly"
        opp_spe = effective_spe(opp_species, opp_spread, str(opp_nat), scarf=False)
        if my_spe > opp_spe:
            cleared += 1
    return cleared >= max(1, len(threats) // 2)


def _scarf_nature_correction(slot: Slot, state: RecommenderState) -> str | None:
    spread = slot.spread.value or {}
    atk = int(spread.get("atk", 0))
    spa = int(spread.get("spa", 0))
    offensive = "Adamant" if atk >= spa else "Modest"
    if scarf_clears_benchmarks(slot, state, nature=offensive):
        return offensive
    return None
