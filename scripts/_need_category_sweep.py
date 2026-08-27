#!/usr/bin/env python3
"""Discovery sweep: NeedCategory detection across varied archetypes."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from recommender.anchor_roles import (
    classify_anchor_role,
    derive_role_shape_context,
    provided_weather_conditions,
    resolve_anchor_build,
)
from recommender.legality import load_snapshot
from recommender.slot_fill import _candidate_satisfies_need, _NEED_SATISFIERS
from recommender.state import Attr, Slot, empty_slot
from recommender.support_needs import SupportNeed, _CATEGORY_ORDER, query_support_needs
from recommender.team_candidates import collect_locked_anchor_contexts

REG = "champions-reg-mb"
VGC = "[Gen 9 Champions] VGC 2026 Reg M-B"


def locked_slot(species: str, *, role: str) -> Slot:
    build = resolve_anchor_build(species, role_hint=role, regulation=REG)
    return Slot(
        role=Attr(role, locked=True),
        species=Attr(build.species or species, locked=True),
        ability=Attr(build.ability or "", locked=True),
        item=Attr(build.item or "", locked=True),
        moveset=Attr(list(build.moves or ()), locked=True),
        spread=Attr(dict(build.spread or {}), locked=True),
        nature=Attr(build.nature or "Serious", locked=True),
    )


def draft(members: list[tuple[str, str]], n_locked: int) -> list[Slot]:
    locked = [locked_slot(s, role=r) for s, r in members[:n_locked]]
    return [*locked, *[empty_slot() for _ in range(6 - len(locked))]]


def state_from_draft(draft: list[Slot]) -> dict[str, Any]:
    return {
        "format_id": VGC,
        "game_type": "doubles",
        "regulation_mod": REG,
        "picked_team_size": 4,
        "available_pool": [],
        "team_draft": draft,
        "archetype": Attr(),
        "rejected": [],
        "constraints": [],
        "messages": [],
    }


# Roles use *_attacker / *_sweeper suffixes via role_taxonomy.primary_function_for_role_id.
ARCHETYPES: dict[str, list[tuple[str, str]]] = {
    "trick_room_only": [
        ("Farigiraf", "trick_room_setter"),
        ("Hatterene", "trick_room_attacker"),
        ("Annihilape", "bulky_attacker"),
        ("Iron Hands", "trick_room_attacker"),
    ],
    "hyper_offense": [
        ("Dragapult", "physical_attacker"),
        ("Garchomp", "physical_attacker"),
        ("Meowscarada", "physical_attacker"),
        ("Glimmora", "special_attacker"),
    ],
    "screens_balance": [
        ("Klefki", "support"),
        ("Grimmsnarl", "support"),
        ("Incineroar", "support"),
        ("Amoonguss", "support"),
    ],
    "mono_fire": [
        ("Incineroar", "support"),
        ("Arcanine", "physical_attacker"),
        ("Torkoal", "sun_setter"),
        ("Ceruledge", "physical_attacker"),
    ],
    # 5th: Tailwind hyper offense — speed control without weather/TR/screens as team identity
    "tailwind_offense": [
        ("Whimsicott", "tailwind_setter"),
        ("Dragapult", "physical_attacker"),
        ("Garchomp", "physical_attacker"),
        ("Meowscarada", "physical_attacker"),
    ],
    # Regression: coarse physical_sweeper role must project offense primary_function.
    "physical_sweeper_regression": [
        ("Dragapult", "physical_sweeper"),
    ],
}

PARTIAL_LOCK_COUNTS = (1, 2, 3)


def run_sweep() -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    cat_counts: dict[str, int] = defaultdict(int)
    cat_by_arch: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    beneficiary_hits: list[dict[str, Any]] = []

    for arch_id, members in ARCHETYPES.items():
        for n_locked in PARTIAL_LOCK_COUNTS:
            d = draft(members, n_locked)
            st = state_from_draft(d)
            for ctx in collect_locked_anchor_contexts(st):
                cats = {n.need.category for n in ctx.support_needs}
                fixture_id = f"{arch_id}/locked_{n_locked}"
                triggers = {n.need.category: n.need.trigger for n in ctx.support_needs}
                stances = {n.need.category: n.need.stance for n in ctx.support_needs}
                for c in cats:
                    cat_counts[c] += 1
                    cat_by_arch[arch_id][c] += 1
                weathers = provided_weather_conditions(ctx.role_decision)
                if weathers:
                    beneficiary_hits.append(
                        {
                            "fixture": fixture_id,
                            "anchor": ctx.anchor_id,
                            "weathers_provided": list(weathers),
                        }
                    )
                results.append(
                    {
                        "fixture": fixture_id,
                        "anchor": ctx.anchor_id,
                        "role_id": ctx.role_decision.role_id,
                        "primary": ctx.role_shape_context.primary_function,
                        "tankiness": ctx.role_shape_context.tankiness,
                        "needs": sorted(cats),
                        "triggers": triggers,
                        "stances": stances,
                        "shape": {
                            "needed_weathers": list(
                                ctx.role_shape_context.needed_weathers
                            ),
                            "needed_trick_room": ctx.role_shape_context.needed_trick_room,
                            "requires_setup_turn": ctx.role_shape_context.requires_setup_turn,
                        },
                        "build": {
                            "ability": ctx.resolved_build.ability,
                            "moves": list(ctx.resolved_build.moves),
                            "n_moves": len(ctx.resolved_build.moves or ()),
                        },
                    }
                )
    return {
        "total_anchor_runs": len(results),
        "cat_counts": dict(cat_counts),
        "cat_by_arch": {k: dict(v) for k, v in cat_by_arch.items()},
        "beneficiary_hits": beneficiary_hits,
        "runs": results,
    }


def probe(
    label: str,
    species: str,
    role: str,
    *,
    team: list[tuple[str, str]] | None = None,
    n_locked: int = 1,
    ability_override: str | None = None,
) -> dict[str, Any]:
    members = team or [(species, role)]
    d = draft(members, n_locked)
    if ability_override and n_locked >= 1:
        slot = d[0]
        d[0] = Slot(
            role=slot.role,
            species=slot.species,
            ability=Attr(ability_override, locked=True),
            item=slot.item,
            moveset=slot.moveset,
            spread=slot.spread,
            nature=slot.nature,
        )
    st = state_from_draft(d)
    slot = st["team_draft"][0]
    resolved = resolve_anchor_build(slot, role_hint=role, regulation=REG)
    decision = classify_anchor_role(resolved, explicit_role=role)
    shape = derive_role_shape_context(decision)
    needs = query_support_needs(
        resolved.as_pokemon(),
        shape,
        team_draft=st["team_draft"],
        state=st,
        regulation=REG,
    )
    return {
        "label": label,
        "species": resolved.species,
        "ability": resolved.ability,
        "moves": list(resolved.moves),
        "role_id": decision.role_id,
        "primary": shape.primary_function,
        "tankiness": shape.tankiness,
        "categories": sorted({n.category for n in needs}),
        "triggers": {n.category: n.trigger for n in needs},
        "stances": {n.category: n.stance for n in needs},
        "needed_weathers": list(shape.needed_weathers),
    }


def comparable_checks() -> dict[str, Any]:
    snap = load_snapshot()
    checks = [
        # Sand Force vs Swift Swim symmetry (known precedent shape)
        probe("sand_force_excadrill_no_sand", "Excadrill", "physical_attacker"),
        probe(
            "swift_swim_barraskewda_no_rain",
            "Barraskewda",
            "physical_attacker",
            ability_override="Swift Swim",
        ),
        probe(
            "sand_rush_excadrill_no_sand",
            "Excadrill",
            "physical_attacker",
            ability_override="Sand Rush",
        ),
        # Sand Force on Garchomp (wanted-tier benefits_from) vs Sand Rush (needed-tier)
        probe(
            "sand_force_garchomp",
            "Garchomp",
            "physical_attacker",
            ability_override="Sand Force",
        ),
        # Weak Armor self-def-drop redirection
        probe("weak_armor_orthworm", "Orthworm", "physical_attacker"),
        probe("weak_armor_cursola", "Cursola", "special_attacker"),
        # Support tank asymmetry — Incineroar has symmetric bulk?
        probe("support_tank_incineroar", "Incineroar", "support"),
        probe("support_tank_amonguss", "Amoonguss", "support"),
        # Terrain condition_setter (Electric) — not weather beneficiary path
        probe("surge_surfer_raichu_alola", "Raichu-Alola", "special_attacker"),
        probe("quark_drive_iron_moth", "Iron Moth", "special_attacker"),
        # Rillaboom Grassy Terrain — terrain beneficiary gap
        probe("grass_pelt_rillaboom", "Rillaboom", "bulky_attacker"),
        probe("grassy_surge_rillaboom", "Rillaboom", "bulky_attacker"),
        # Glass offense universal healing (trigger=None)
        probe("dragapult_glass_offense", "Dragapult", "physical_attacker"),
        # Tank with Roost suppresses tank_no_self_heal enrich
        probe("corviknight_roost_tank", "Corviknight", "bulky_attacker"),
        # TR strategy benefits_from with setter locked
        probe(
            "hatterene_tr_sweeper_farigiraf_locked",
            "Hatterene",
            "trick_room_attacker",
            team=ARCHETYPES["trick_room_only"],
            n_locked=2,
        ),
        # Offense-primary soft redirection (want stance)
        probe("dragapult_offense_redirection", "Dragapult", "physical_attacker"),
        # physical_sweeper role → primary unknown (role vocabulary gap)
        probe("dragapult_physical_sweeper_role", "Dragapult", "physical_sweeper"),
    ]

    healing_need = SupportNeed(
        category="healing_cleric", name="H", description="", trigger=None
    )
    tank_healing = SupportNeed(
        category="healing_cleric",
        name="H",
        description="",
        trigger="tank_no_self_heal",
    )
    satisfier_probe = []
    for sp in (
        "Incineroar",
        "Amoonguss",
        "Clefairy",
        "Toxapex",
        "Sinistcha",
        "Whimsicott",
        "Comfey",
        "Blissey",
    ):
        b = resolve_anchor_build(sp, regulation=REG)
        for need in (healing_need, tank_healing):
            satisfier_probe.append(
                {
                    "species": sp,
                    "trigger": need.trigger,
                    "satisfies": _candidate_satisfies_need(
                        sp, need, snap=snap, regulation=REG
                    ),
                    "learnset_heal_moves": sorted(
                        set(resolve_anchor_build(sp, regulation=REG).moves or ())
                        & _NEED_SATISFIERS["healing_cleric"].moves
                    ),
                }
            )

    return {"probes": checks, "healing_satisfier_probe": satisfier_probe}


def main() -> None:
    out = {"sweep": run_sweep(), "comparable": comparable_checks()}
    path = "artifacts/need_category_sweep_2026-08-26.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
