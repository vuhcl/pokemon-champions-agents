"""Weather setter Role Compendium construction (ADR-019)."""

from __future__ import annotations

from typing import Any

from recommender.ids import to_id
from recommender.legality import resolve_learnset
from recommender.role_compendium import (
    CandidateEval,
    ClaimedTrait,
    LiveFetch,
    RejectedCandidate,
    RoleConstructionDraft,
    _REDIRECTION_SECONDARY_MOVES,
    _SHOWDOWN_BASE_USAGE_RATIO,
    _USAGE_SET_PCT_FLOOR,
    _UsageCtx,
    _admit_move_delivery,
    _condition_label,
    _criteria_sets,
    _discount_outcome,
    _draft_with_tiers,
    _excellent_secondary,
    _guard_pool,
    _pool_index,
    _ref_members,
    _secondary_support_notes,
    _species_abilities,
)
from recommender.role_compendium_usage import (
    _hits_clear_set_pct_floor,
    _mega_pair_ids,
    _move_display,
    _showdown_entry,
    _stone_fallback_ability,
)

def _construct_weather_setter(
    category: str,
    sub_criteria: dict[str, Any],
    legal_pool: list[str],
    *,
    snap: dict[str, Any],
    uctx: _UsageCtx,
    showdown_fetch: LiveFetch | None,
    reference_compendium: dict[str, Any] | RoleConstructionDraft | None,
) -> RoleConstructionDraft:
    ability_ids, move_id, priority_abilities, _condition = _criteria_sets(sub_criteria)
    pool = _pool_index(legal_pool, snap)
    pool_ids = set(pool)
    prior = _ref_members(reference_compendium)
    members: list[CandidateEval] = []
    rejected: list[RejectedCandidate] = []
    admitted_ids: set[str] = set()
    notes: list[str] = []
    cond = _condition_label(sub_criteria)

    # Ability holders in pool.
    ability_holders: dict[str, str] = {}
    holder_aid: dict[str, str] = {}
    for sid, name in pool.items():
        abs_map = _species_abilities(snap, sid)
        hit = ability_ids & set(abs_map)
        if not hit:
            continue
        aid = next(iter(sorted(hit)))
        ability_holders[sid] = name
        holder_aid[sid] = aid

    # Showdown mega-pair attribution among ability holders.
    skip_ability: set[str] = set()  # discounted base → reject, do not Excellent
    pair_attr: dict[str, str] = {}
    sd_cache: dict[str, dict[str, Any] | None] = {}
    seen_pairs: set[tuple[str, str]] = set()
    for sid in ability_holders:
        pair = _mega_pair_ids(sid, snap, set(ability_holders))
        if not pair or pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        base_sid, mega_sid = pair
        base_name, mega_name = ability_holders[base_sid], ability_holders[mega_sid]
        base_sd = _showdown_entry(base_name, cache=sd_cache, showdown_fetch=showdown_fetch)
        mega_sd = _showdown_entry(mega_name, cache=sd_cache, showdown_fetch=showdown_fetch)

        if mega_sd is not None:
            mega_pct = float(mega_sd.get("usage_pct") or 0.0)
            base_pct = float((base_sd or {}).get("usage_pct") or 0.0) if base_sd else 0.0
            pair_attr[mega_sid] = "showdown form-separated usage"
            if (
                mega_pct > base_pct
                and base_pct < _SHOWDOWN_BASE_USAGE_RATIO * mega_pct
            ):
                skip_ability.add(base_sid)
                pair_attr[base_sid] = (
                    f"showdown usage discounted "
                    f"(base {base_pct:.3f}% < {_SHOWDOWN_BASE_USAGE_RATIO}× "
                    f"mega {mega_pct:.3f}%)"
                )
                notes.append(
                    f"Showdown attribution ({base_name}/{mega_name}): "
                    f"mega usage_pct={mega_pct:.3f} base={base_pct:.3f}; "
                    f"base discounted as attribution artifact"
                )
            else:
                pair_attr[base_sid] = "showdown form-separated usage"
                notes.append(
                    f"Showdown attribution ({base_name}/{mega_name}): "
                    f"mega usage_pct={mega_pct:.3f} base={base_pct:.3f}; "
                    f"both kept (independent usage)"
                )
        elif _stone_fallback_ability(
            base_name, base_sid, mega_sid, uctx=uctx, snap=snap
        ):
            skip_ability.add(base_sid)
            pair_attr[base_sid] = "usage attributed to Mega via mega-stone fallback"
            pair_attr[mega_sid] = "mega-stone fallback (≥80% on base CBD page)"
            notes.append(
                f"Showdown miss for {mega_name}; stone-heuristic fallback used "
                f"for {base_name}/{mega_name}"
            )
        else:
            notes.append(
                f"Showdown miss for {mega_name}; no stone fallback — "
                f"both {base_name}/{mega_name} kept on ability alone"
            )

    for sid, name in sorted(ability_holders.items(), key=lambda x: x[1]):
        aid = holder_aid[sid]
        abs_map = _species_abilities(snap, sid)
        mechanism = abs_map[aid]
        entry = uctx.entry_for(name)
        secondary_note, secondary_traits = _secondary_support_notes(
            entry, move_ids=_REDIRECTION_SECONDARY_MOVES
        )
        has_fg = bool({"friendguard"} & set(abs_map))
        has_hospitality = "hospitality" in abs_map
        secondary_move_ids = {to_id(t.name) for t in secondary_traits}
        verified_secondary = has_fg or has_hospitality or bool(secondary_traits)
        excellent_secondary = _excellent_secondary(
            has_friend_guard=has_fg, secondary_move_ids=secondary_move_ids
        )
        traits = [
            ClaimedTrait(
                name=mechanism,
                criterion="delivery",
                purpose_claimed=f"set {cond} via ability",
            ),
            ClaimedTrait(
                name=mechanism,
                criterion="execution",
                purpose_claimed="automatic on switch-in; no turn cost",
            ),
        ]
        if has_fg:
            traits.append(
                ClaimedTrait(
                    name=abs_map["friendguard"],
                    criterion="secondary_role",
                    purpose_claimed="ally damage mitigation",
                )
            )
        if has_hospitality:
            traits.append(
                ClaimedTrait(
                    name=abs_map["hospitality"],
                    criterion="secondary_role",
                    purpose_claimed="ally heal on switch-in",
                )
            )
        traits.extend(secondary_traits)
        attr = pair_attr.get(sid, "none")
        discounted = sid in skip_ability
        if discounted:
            # Ability mech is Excellent; discount → Acceptable (not reject).
            demoted = _discount_outcome("Excellent")
            assert demoted == "Acceptable"
            prev = prior.get(sid)
            change_reason = (
                f"usage discount demote / mech Excellent → Acceptable "
                f"({attr})"
            )
            if prev == "Excellent":
                change_reason = (
                    f"usage discount demote / tier Excellent → Acceptable ({attr})"
                )
            elif prev and prev != "Acceptable":
                change_reason = (
                    f"usage discount / tier {prev!r} → Acceptable ({attr})"
                )
            members.append(
                CandidateEval(
                    species=name,
                    species_id=sid,
                    tier="Acceptable",
                    delivery_class="ability",
                    mechanism=mechanism,
                    criteria_notes={
                        "delivery": "ability-guaranteed (more reliable than move)",
                        "execution": (
                            "automatic on switch-in; usage discounted vs Mega form"
                        ),
                        "secondary_role": secondary_note,
                        "verified_secondary": str(verified_secondary),
                        "excellent_secondary": str(excellent_secondary),
                        "attribution": attr,
                        "usage_proven": "False",
                    },
                    claimed_traits=traits,
                    reasoning=(
                        f"{mechanism} clears Acceptable "
                        f"(mech Excellent, Showdown usage discounted; "
                        f"excellent_secondary={excellent_secondary})."
                    ),
                    change_reason=change_reason,
                    reinforce_class="",
                    excellence_basis="usage_discounted",
                )
            )
            admitted_ids.add(sid)
            continue

        members.append(
            CandidateEval(
                species=name,
                species_id=sid,
                tier="Excellent",
                delivery_class="ability",
                mechanism=mechanism,
                criteria_notes={
                    "delivery": "ability-guaranteed (more reliable than move)",
                    "execution": "automatic on switch-in; no moveslot / priority risk",
                    "secondary_role": secondary_note,
                    "verified_secondary": str(verified_secondary),
                    "excellent_secondary": str(excellent_secondary),
                    "attribution": attr,
                    "usage_proven": "True",
                },
                claimed_traits=traits,
                reasoning=(
                    f"{mechanism} ability delivery clears Excellent bar; "
                    f"secondary kit noted but does not force-rank within tier "
                    f"({secondary_note}; excellent_secondary={excellent_secondary})."
                ),
                change_reason=None,
                reinforce_class="",
                excellence_basis="ability_delivery",
            )
        )
        admitted_ids.add(sid)

    for sid, name in sorted(pool.items(), key=lambda x: x[1]):
        if sid in admitted_ids:
            continue
        abs_map = _species_abilities(snap, sid)
        prio = priority_abilities & set(abs_map)
        if not prio:
            continue
        ls = set(resolve_learnset(snap, sid) or [])
        if move_id not in ls:
            continue
        prio_name = abs_map[next(iter(sorted(prio)))]
        move_display = _move_display(snap, move_id)
        usage_proven = uctx.delivers(name, move_id) and _hits_clear_set_pct_floor(
            name,
            {move_id},
            floor=_USAGE_SET_PCT_FLOOR,
            uctx=uctx,
            sd_cache=sd_cache,
            showdown_fetch=showdown_fetch,
        )
        if not _admit_move_delivery(
            usage_proven=usage_proven, independent_reinforce=False
        ):
            # Move mech caps at Good → discount floor still rejects (no Acceptable path).
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=(
                        f"{prio_name}+{move_display} learnset but no usage evidence "
                        f"of {move_display} delivery"
                    ),
                )
            )
            continue
        entry = uctx.entry_for(name)
        secondary_note, secondary_traits = _secondary_support_notes(
            entry, move_ids=_REDIRECTION_SECONDARY_MOVES
        )
        has_fg = bool({"friendguard"} & set(abs_map))
        has_hospitality = "hospitality" in abs_map
        secondary_move_ids = {to_id(t.name) for t in secondary_traits}
        verified_secondary = has_fg or has_hospitality or bool(secondary_traits)
        excellent_secondary = _excellent_secondary(
            has_friend_guard=has_fg, secondary_move_ids=secondary_move_ids
        )
        traits = [
            ClaimedTrait(
                name=move_display,
                criterion="delivery",
                purpose_claimed=f"set {cond} via move",
            ),
            ClaimedTrait(
                name=prio_name,
                criterion="execution",
                purpose_claimed="priority on status setup move",
            ),
            *secondary_traits,
        ]
        members.append(
            CandidateEval(
                species=name,
                species_id=sid,
                tier="Good",
                delivery_class="move_priority",
                mechanism=move_display,
                criteria_notes={
                    "delivery": "move-based (less reliable than ability)",
                    "execution": (
                        f"{prio_name}-boosted status move; blocked by Dark-types / "
                        "Good as Gold / some immunities"
                    ),
                    "secondary_role": secondary_note,
                    "verified_secondary": str(verified_secondary),
                    "excellent_secondary": str(excellent_secondary),
                    "attribution": "none",
                    "usage_proven": str(usage_proven),
                },
                claimed_traits=traits,
                reasoning=(
                    f"{prio_name} {move_display} clears Good (priority move delivery); "
                    f"below ability-guaranteed setters. Secondary: {secondary_note}."
                ),
                change_reason=None,
                reinforce_class="",
                excellence_basis="move_priority",
            )
        )
        admitted_ids.add(sid)

    _guard_pool(members, rejected, pool_ids)
    return _draft_with_tiers(
        category, sub_criteria, members, rejected, notes=notes
    )
