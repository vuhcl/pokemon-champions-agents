"""Support-role Role Compendium constructs (redirect/TR/TW/screens/sleep)."""

from __future__ import annotations

from typing import Any

from recommender.ability_classification import (
    execution_reinforce_abilities,
    flinch_denial_ability_ids,
    get_ability,
    taunt_denial_ability_ids,
)
from recommender.ids import to_id
from recommender.legality import resolve_learnset
from recommender.move_narrowing import move_priority
from recommender.role_compendium import (
    CandidateEval,
    ClaimedTrait,
    LiveFetch,
    RejectedCandidate,
    RoleConstructionDraft,
    _COMPETING_IDENTITY_MOVES,
    _FAKE_OUT_IMMUNE_TYPE,
    _REDIRECTION_SECONDARY_MOVES,
    _SCREENS_DELIVERY_NOTE,
    _SCREENS_EXCELLENT_SECONDARY_MOVES,
    _SCREENS_MOVE_IDS,
    _SCREENS_SECONDARY_MOVES,
    _SCREENS_SNOW_ABILITIES,
    _SCREENS_SPE_FLOOR,
    _SETUP_SURVIVE_ABILITIES,
    _SLEEP_ACCURACY,
    _SLEEP_ACCURACY_ABILITIES,
    _SLEEP_CORE_MOVES,
    _SLEEP_DELAYED,
    _SLEEP_EXCELLENT_SECONDARY_MOVES,
    _SLEEP_IMMEDIATE,
    _SLEEP_SECONDARY_MOVES,
    _SLEEP_SPE_FLOOR,
    _SLEEP_SPEED_ABILITIES,
    _SLEEP_STATUS_MOVES,
    _SLEEP_TRAP_ABILITIES,
    _TAILWIND_DELIVERY_NOTE,
    _TAILWIND_EXCELLENT_SECONDARY_MOVES,
    _TAILWIND_SECONDARY_MOVES,
    _TAILWIND_SPE_FLOOR,
    _TRICK_ROOM_BULK_FLOOR,
    _TRICK_ROOM_DELIVERY_NOTE,
    _TRICK_ROOM_EXCELLENT_SECONDARY_MOVES,
    _TRICK_ROOM_SECONDARY_MOVES,
    _TRICK_ROOM_SET_PCT_FLOOR,
    _USAGE_SET_PCT_FLOOR,
    _UsageCtx,
    _admit_move_delivery,
    _base_stats,
    _discount_outcome,
    _draft_with_tiers,
    _entry_has_move,
    _excellent_secondary,
    _guard_pool,
    _pool_index,
    _ref_members,
    _secondary_support_notes,
    _species_abilities,
    _species_id_is_mega,
)
from recommender.role_compendium_usage import (
    _delivery_usage_hits,
    _hits_clear_set_pct_floor,
    _mega_usage_attribution,
    _move_display,
    _move_pct,
    _same_row_both_moves,
    _species_types,
    _usage_has_item,
)

def _construct_redirection(
    category: str,
    sub_criteria: dict[str, Any],
    legal_pool: list[str],
    *,
    snap: dict[str, Any],
    uctx: _UsageCtx,
    showdown_fetch: LiveFetch | None,
    reference_compendium: dict[str, Any] | RoleConstructionDraft | None,
) -> RoleConstructionDraft:
    from recommender.role_compendium_usage import (
        _hits_clear_set_pct_floor,
        _mega_usage_attribution,
        _move_display,
        _move_pct,
    )

    move_ids = frozenset(to_id(m) for m in sub_criteria["move_ids"])
    ally_ids = frozenset(to_id(a) for a in sub_criteria.get("ally_reinforce_abilities") or [])
    pool = _pool_index(legal_pool, snap)
    pool_ids = set(pool)
    prior = _ref_members(reference_compendium)
    members: list[CandidateEval] = []
    rejected: list[RejectedCandidate] = []
    notes = [
        "no ability-based redirection delivery in Champions-legal data "
        "(Follow Me / Rage Powder are move-only)"
    ]
    sd_cache: dict[str, dict[str, Any] | None] = {}

    # Eligible redirectors (learnset ∩ moves), excluding Magic Bounce abandon.
    eligible: dict[str, str] = {}
    for sid, name in pool.items():
        ls = set(resolve_learnset(snap, sid) or [])
        if not (move_ids & ls):
            continue
        abs_map = _species_abilities(snap, sid)
        if set(abs_map) == {"magicbounce"}:
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=(
                        "Mega kit abandons redirection (Magic Bounce only); "
                        "redirect learnset inherited from base"
                    ),
                    change_reason=(
                        "phase2 mega abandon"
                        if prior.get(sid)
                        else None
                    ),
                )
            )
            continue
        eligible[sid] = name

    # Showdown attribution for base/Mega pairs both in the eligible pool.
    pair_usage, pair_notes, _stone_used = _mega_usage_attribution(
        eligible,
        move_ids,
        snap=snap,
        uctx=uctx,
        sd_cache=sd_cache,
        showdown_fetch=showdown_fetch,
        notes=notes,
    )

    for sid, name in sorted(eligible.items(), key=lambda x: x[1]):
        ls = set(resolve_learnset(snap, sid) or [])
        hits = sorted(move_ids & ls)
        abs_map = _species_abilities(snap, sid)
        mechanisms = [_move_display(snap, mid) for mid in hits]
        mechanism = " / ".join(mechanisms)

        entry = uctx.entry_for(name)
        qd_pct = max(
            (_move_pct(entry, mid) for mid in _COMPETING_IDENTITY_MOVES),
            default=0.0,
        )
        best_redir = max((_move_pct(entry, mid) for mid in hits), default=0.0)
        identity_conflict = bool(entry is not None and qd_pct > best_redir > 0)

        if sid in pair_usage:
            usage_proven = pair_usage[sid]
        else:
            usage_proven = any(uctx.delivers(name, mid) for mid in hits)
        if usage_proven and not _hits_clear_set_pct_floor(
            name,
            set(hits),
            floor=_USAGE_SET_PCT_FLOOR,
            uctx=uctx,
            sd_cache=sd_cache,
            showdown_fetch=showdown_fetch,
        ):
            usage_proven = False

        has_fg = bool(ally_ids & set(abs_map))
        has_hospitality = "hospitality" in abs_map
        secondary_note, secondary_traits = _secondary_support_notes(
            entry, move_ids=_REDIRECTION_SECONDARY_MOVES
        )
        secondary_move_ids = {to_id(t.name) for t in secondary_traits}
        secondary_move_hit = bool(secondary_traits)
        verified_secondary = has_fg or has_hospitality or secondary_move_hit
        excellent_secondary = _excellent_secondary(
            has_friend_guard=has_fg, secondary_move_ids=secondary_move_ids
        )
        exec_abilities = execution_reinforce_abilities(abs_map)
        execution_ok = bool(exec_abilities)
        independent_reinforce = execution_ok or verified_secondary

        if not _admit_move_delivery(
            usage_proven=usage_proven, independent_reinforce=independent_reinforce
        ):
            attr = pair_notes.get(sid, "")
            discounted = (
                "discounted" in attr
                or "stone-heuristic" in attr
                or "attributed to Mega" in attr
                or "mega-stone fallback" in attr
            )
            # Mech Excellent ignoring usage: FG / excellent_secondary, no identity conflict.
            mech_tier = (
                "Excellent"
                if (has_fg or excellent_secondary) and not identity_conflict
                else "Good"
            )
            demoted = _discount_outcome(mech_tier) if discounted else None
            if demoted == "Acceptable":
                reinforce = "ally_mitigation" if has_fg else "none"
                members.append(
                    CandidateEval(
                        species=name,
                        species_id=sid,
                        tier="Acceptable",
                        delivery_class="move_redirect",
                        mechanism=mechanism,
                        criteria_notes={
                            "delivery": (
                                "move-based Follow Me / Rage Powder "
                                "(same reliability class)"
                            ),
                            "execution": (
                                f"Champions priority +{move_priority(hits[0])}; "
                                "usage discounted vs Mega form"
                            ),
                            "secondary_role": secondary_note,
                            "usage_proven": "False",
                            "verified_secondary": str(verified_secondary),
                            "excellent_secondary": str(excellent_secondary),
                            "reinforce_class": reinforce,
                            "qd_pct": str(qd_pct),
                            "best_redirect_pct": str(best_redir),
                            "identity_conflict": str(identity_conflict),
                            "attribution": attr or "none",
                        },
                        claimed_traits=[
                            ClaimedTrait(
                                name=mechanism,
                                criterion="delivery",
                                purpose_claimed=(
                                    "redirect attacks onto self to protect ally"
                                ),
                            ),
                            ClaimedTrait(
                                name=mechanism,
                                criterion="execution",
                                purpose_claimed=(
                                    f"Champions priority +{move_priority(hits[0])} "
                                    "status redirect"
                                ),
                            ),
                            *secondary_traits,
                        ],
                        reasoning=(
                            f"{mechanism} clears Acceptable "
                            f"(mech Excellent, Showdown usage discounted)."
                        ),
                        change_reason=(
                            f"usage discount demote / mech Excellent → Acceptable "
                            f"({attr})"
                        ),
                        reinforce_class=reinforce,
                        excellence_basis="usage_discounted",
                    )
                )
                continue
            prev = prior.get(sid)
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=(
                        f"{mechanism} learnset but no usage evidence of redirect "
                        "delivery and no independent reinforce "
                        "(hit-triggered opponent disrupt / Friend Guard / "
                        "Hospitality / closed secondary)"
                    ),
                    change_reason=(
                        "phase1+reject: learnset-only without usage/reinforce"
                        if prev
                        else None
                    ),
                )
            )
            continue

        reinforce = "ally_mitigation" if has_fg else "none"
        if identity_conflict:
            tier = "Good"
            if has_fg:
                basis = "ally_mitigation_conflicted"
            elif usage_proven and excellent_secondary:
                basis = "secondary_stack_conflicted"
            elif usage_proven:
                basis = "usage_proven_conflicted"
            else:
                basis = "reinforce_only_conflicted"
        elif usage_proven and excellent_secondary:
            tier = "Excellent"
            basis = "ally_mitigation" if has_fg else "secondary_stack"
        else:
            # usage without excellent secondary, or reinforce without usage
            tier = "Good"
            if usage_proven:
                basis = "usage_proven"
            elif has_fg:
                basis = "ally_mitigation"
            elif execution_ok:
                basis = "execution_reinforce"
            else:
                basis = "secondary_reinforce"

        stats = _base_stats(snap, sid)
        prio = move_priority(hits[0])
        hospitality = abs_map.get("hospitality")
        exec_note = (
            f"Champions priority +{prio}; bulk HP/Def/SpD="
            f"{stats.get('hp')}/{stats.get('def')}/{stats.get('spd')}"
        )
        if identity_conflict:
            exec_note += (
                f"; identity conflict Quiver Dance {qd_pct:.1f}% > "
                f"redirect {best_redir:.1f}% (Excellent capped)"
            )

        traits: list[ClaimedTrait] = [
            ClaimedTrait(
                name=mechanism,
                criterion="delivery",
                purpose_claimed="redirect attacks onto self to protect ally",
            ),
            ClaimedTrait(
                name=mechanism,
                criterion="execution",
                purpose_claimed=f"Champions priority +{prio} status redirect",
            ),
        ]
        if exec_abilities:
            for _aid, display, desc in exec_abilities:
                traits.append(
                    ClaimedTrait(
                        name=display,
                        criterion="execution",
                        purpose_claimed=(
                            "hit-triggered opponent disrupt while drawing fire "
                            "— execution reinforce for redirector "
                            "(not ally mitigation)"
                        ),
                    )
                )
                snippet = desc if len(desc) <= 120 else desc[:117] + "..."
                exec_note += f"; {display} ({snippet})"
        if has_fg:
            traits.append(
                ClaimedTrait(
                    name=abs_map[next(iter(sorted(ally_ids & set(abs_map))))],
                    criterion="secondary_role",
                    purpose_claimed="ally damage mitigation while redirecting",
                )
            )
        if has_hospitality and hospitality:
            traits.append(
                ClaimedTrait(
                    name=hospitality,
                    criterion="secondary_role",
                    purpose_claimed="ally heal on switch-in (secondary stack, not mitigate)",
                )
            )
        traits.extend(secondary_traits)
        hosp_note = ""
        if hospitality:
            hosp_note = (
                f"; {hospitality} heals ally on switch-in (other-directed, "
                "not damage mitigation during redirect)"
            )

        attr_note = pair_notes.get(sid, "")
        change_reason = None
        prev_tier = prior.get(sid)
        if prev_tier and prev_tier != tier and sid in pair_usage:
            change_reason = (
                f"phase2 showdown attribution / tier {prev_tier!r} → {tier!r}"
                + (f" ({attr_note})" if attr_note else "")
            )
        elif prev_tier == "Excellent" and tier != "Excellent":
            # Intentional demote (excellent_secondary axes / identity conflict).
            change_reason = (
                f"excellent_secondary axes / identity conflict / "
                f"tier Excellent → {tier!r}"
            )

        members.append(
            CandidateEval(
                species=name,
                species_id=sid,
                tier=tier,
                delivery_class="move_redirect",
                mechanism=mechanism,
                criteria_notes={
                    "delivery": "move-based Follow Me / Rage Powder (same reliability class)",
                    "execution": exec_note,
                    "secondary_role": secondary_note + hosp_note,
                    "usage_proven": str(usage_proven),
                    "verified_secondary": str(verified_secondary),
                    "excellent_secondary": str(excellent_secondary),
                    "reinforce_class": reinforce,
                    "qd_pct": str(qd_pct),
                    "best_redirect_pct": str(best_redir),
                    "identity_conflict": str(identity_conflict),
                    "attribution": attr_note or "none",
                },
                claimed_traits=traits,
                reasoning=(
                    f"{mechanism} clears {tier} "
                    f"(basis={basis}, reinforce={reinforce}, usage_proven={usage_proven}"
                    f", verified_secondary={verified_secondary}"
                    f", excellent_secondary={excellent_secondary}"
                    + (f" / {attr_note}" if attr_note else "")
                    + (" / identity_conflict" if identity_conflict else "")
                    + ")."
                ),
                change_reason=change_reason,
                reinforce_class=reinforce,
                excellence_basis=basis,
            )
        )

    _guard_pool(members, rejected, pool_ids)
    return _draft_with_tiers(category, sub_criteria, members, rejected, notes=notes)


def _protection_note(abs_map: dict[str, str], aids: set[str]) -> str:
    parts = []
    for aid in sorted(aids):
        entry = get_ability(aid) or {}
        display = str(abs_map.get(aid) or entry.get("name") or aid)
        desc = str(entry.get("description") or "")
        snippet = desc if len(desc) <= 120 else desc[:117] + "..."
        parts.append(f"{display} ({snippet})" if snippet else display)
    return "; ".join(parts)


def _construct_trick_room_setter(
    category: str,
    sub_criteria: dict[str, Any],
    legal_pool: list[str],
    *,
    snap: dict[str, Any],
    uctx: _UsageCtx,
    showdown_fetch: LiveFetch | None,
    reference_compendium: dict[str, Any] | RoleConstructionDraft | None,
) -> RoleConstructionDraft:
    from recommender.role_compendium_usage import (
        _delivery_usage_hits,
        _hits_clear_set_pct_floor,
        _mega_usage_attribution,
        _move_display,
        _species_types,
    )

    move_ids = frozenset(to_id(m) for m in sub_criteria["move_ids"])
    pool = _pool_index(legal_pool, snap)
    pool_ids = set(pool)
    prior = _ref_members(reference_compendium)
    members: list[CandidateEval] = []
    rejected: list[RejectedCandidate] = []
    notes = [
        "delivery does not differentiate: Trick Room is move-only "
        f"(no ability sets it) and its priority is fixed at "
        f"{move_priority('trickroom')}, so every candidate resolves last "
        "regardless of how it accesses the move",
        "usage evidence prefers Champions in-game data where a row exists; "
        "Showdown is a fallback only for formes with no Champions row",
        f"membership requires Trick Room set% ≥ {_TRICK_ROOM_SET_PCT_FLOOR:g} "
        "(self-protection and Showdown-discount do not waive the floor)",
        f"membership requires bulk (HP+Def+SpD) ≥ {_TRICK_ROOM_BULK_FLOOR}, "
        "waived for one-hit absorption (Disguise / Ice Face)",
        "tiers grade self-provided cover of the shared Fake Out / Taunt "
        "exposure: ability flinch denial > Ghost Fake Out immunity or Taunt "
        "immunity > none",
    ]
    sd_cache: dict[str, dict[str, Any] | None] = {}

    eligible = {
        sid: name
        for sid, name in pool.items()
        if move_ids & set(resolve_learnset(snap, sid) or [])
    }

    pair_usage, pair_notes, _stone_used = _mega_usage_attribution(
        eligible,
        move_ids,
        snap=snap,
        uctx=uctx,
        sd_cache=sd_cache,
        showdown_fetch=showdown_fetch,
        notes=notes,
    )

    flinch_ids = flinch_denial_ability_ids()
    taunt_ids = taunt_denial_ability_ids()

    for sid, name in sorted(eligible.items(), key=lambda x: x[1]):
        hits = sorted(move_ids & set(resolve_learnset(snap, sid) or []))
        abs_map = _species_abilities(snap, sid)
        stats = _base_stats(snap, sid)
        mechanism = " / ".join(_move_display(snap, mid) for mid in hits)
        entry = uctx.entry_for(name)

        # Membership floor, not a ranking axis. One-hit absorption substitutes
        # for raw bulk: it buys the same thing, a guaranteed turn to cast.
        bulk = sum(int(stats.get(k) or 0) for k in ("hp", "def", "spd"))
        absorb = set(abs_map) & _SETUP_SURVIVE_ABILITIES
        if bulk < _TRICK_ROOM_BULK_FLOOR and not absorb:
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=(
                        f"bulk {bulk} below the {_TRICK_ROOM_BULK_FLOOR} membership "
                        "floor; moving last means it must survive to cast"
                    ),
                    change_reason=(
                        f"bulk floor {_TRICK_ROOM_BULK_FLOOR} membership requirement"
                        if prior.get(sid)
                        else None
                    ),
                )
            )
            continue

        # Usage: negative Mega attribution sticks. Otherwise CBD and/or Showdown
        # per-move — a CBD row without the move no longer suppresses Showdown.
        if pair_usage.get(sid) is False:
            usage_proven = False
            usage_source = "mega attribution"
        else:
            usage_hits, usage_source = _delivery_usage_hits(
                name,
                set(hits),
                uctx=uctx,
                sd_cache=sd_cache,
                showdown_fetch=showdown_fetch,
                set_pct_floor=_TRICK_ROOM_SET_PCT_FLOOR,
            )
            usage_proven = bool(usage_hits)

        flinch = set(abs_map) & flinch_ids
        taunt = set(abs_map) & taunt_ids
        ghost = _FAKE_OUT_IMMUNE_TYPE in _species_types(snap, sid)
        self_protected = bool(flinch or taunt or ghost)

        secondary_note, secondary_traits = _secondary_support_notes(
            entry, move_ids=_TRICK_ROOM_SECONDARY_MOVES
        )
        secondary_move_ids = {to_id(t.name) for t in secondary_traits}
        verified_secondary = bool(secondary_traits)
        excellent_secondary = _excellent_secondary(
            has_friend_guard=False,
            secondary_move_ids=secondary_move_ids,
            excellent_move_ids=_TRICK_ROOM_EXCELLENT_SECONDARY_MOVES,
        )

        # Set% floor is hard membership. Self-protection only grades tier.
        if not usage_proven:
            attr = pair_notes.get(sid, "")
            reason = (
                f"{mechanism} learnset but Trick Room set% below "
                f"{_TRICK_ROOM_SET_PCT_FLOOR:g}"
            )
            if attr:
                reason += f" ({attr})"
            elif usage_source in {"champions", "none"}:
                reason += (
                    " (Champions and Showdown usage data show no Trick Room "
                    "on this species)"
                )
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=reason,
                    change_reason=(
                        f"usage below {_TRICK_ROOM_SET_PCT_FLOOR:g}% set% floor"
                        if prior.get(sid)
                        else None
                    ),
                )
            )
            continue

        # Graded protection: denying the flinch (outright priority denial or
        # flinch immunity) removes the Fake Out lockout entirely; Taunt immunity
        # only covers the slower half of the shared exposure.
        # Graded on how much of the shared Fake Out / Taunt exposure the
        # candidate covers by itself. Ability-based flinch denial is broadest
        # (all priority, or all flinch sources); Ghost typing and Taunt immunity
        # each cover one half; no self-provided cover is the baseline.
        if flinch:
            tier, basis = "Excellent", "flinch_denial"
        elif ghost:
            tier, basis = "Good", "ghost_fakeout_immunity"
        elif taunt:
            tier, basis = "Good", "taunt_denial"
        else:
            tier, basis = "Acceptable", "unprotected"
        reinforce = "self_protection" if self_protected else "none"

        exec_note = (
            f"bulk HP/Def/SpD={stats.get('hp')}/{stats.get('def')}/{stats.get('spd')}"
        )
        traits: list[ClaimedTrait] = [
            ClaimedTrait(
                name=mechanism,
                criterion="delivery",
                purpose_claimed="invert turn order for the side",
            )
        ]
        if flinch:
            note = _protection_note(abs_map, flinch)
            exec_note += f"; self-provided flinch denial — {note}"
            traits.append(
                ClaimedTrait(
                    name=note.split(" (")[0],
                    criterion="execution",
                    purpose_claimed=(
                        "self-provided flinch denial; no teammate dependency "
                        "for the cast"
                    ),
                )
            )
        if ghost:
            exec_note += (
                "; Ghost typing is immune to Normal, so Fake Out cannot land "
                "(narrower than Armor Tail / Inner Focus: no cover vs other "
                "flinch sources)"
            )
            traits.append(
                ClaimedTrait(
                    name="Ghost typing",
                    criterion="execution",
                    purpose_claimed=(
                        "self-provided Fake Out immunity; no teammate dependency "
                        "for the cast"
                    ),
                )
            )
        if taunt:
            note = _protection_note(abs_map, taunt)
            exec_note += f"; self-provided Taunt immunity — {note}"
            traits.append(
                ClaimedTrait(
                    name=note.split(" (")[0],
                    criterion="execution",
                    purpose_claimed=(
                        "self-provided Taunt immunity; no teammate dependency "
                        "for the cast"
                    ),
                )
            )
        if absorb:
            exec_note += (
                f"; {'/'.join(sorted(abs_map[a] for a in absorb))} absorbs one hit "
                "outright, substituting for raw bulk"
            )
        if not self_protected:
            exec_note += (
                "; no self-provided protection — depends on a teammate to cover "
                "Fake Out / Taunt"
            )
        traits.extend(secondary_traits)

        attr_note = pair_notes.get(sid, "")
        prev_tier = prior.get(sid)
        change_reason = None
        if prev_tier and prev_tier != tier:
            change_reason = f"tier {prev_tier!r} → {tier!r}" + (
                f" ({attr_note})" if attr_note else ""
            )

        members.append(
            CandidateEval(
                species=name,
                species_id=sid,
                tier=tier,
                delivery_class="move_trick_room",
                mechanism=mechanism,
                criteria_notes={
                    "delivery": _TRICK_ROOM_DELIVERY_NOTE,
                    "execution": exec_note,
                    "secondary_role": secondary_note,
                    "usage_proven": str(usage_proven),
                    "usage_source": usage_source,
                    "verified_secondary": str(verified_secondary),
                    "excellent_secondary": str(excellent_secondary),
                    "reinforce_class": reinforce,
                    "self_protection": "+".join(
                        p
                        for p, on in (
                            ("flinch_denial", bool(flinch)),
                            ("ghost_fakeout_immunity", ghost),
                            ("taunt_denial", bool(taunt)),
                        )
                        if on
                    )
                    or "none",
                    "bulk": str(bulk),
                    "attribution": attr_note or "none",
                },
                claimed_traits=traits,
                reasoning=(
                    f"{mechanism} clears {tier} (basis={basis}, "
                    f"usage_proven={usage_proven}, self_protection={reinforce})"
                    + (f" / {attr_note}" if attr_note else "")
                    + "."
                ),
                change_reason=change_reason,
                reinforce_class=reinforce,
                excellence_basis=basis,
            )
        )

    _guard_pool(members, rejected, pool_ids)
    return _draft_with_tiers(category, sub_criteria, members, rejected, notes=notes)


def _construct_tailwind_setter(
    category: str,
    sub_criteria: dict[str, Any],
    legal_pool: list[str],
    *,
    snap: dict[str, Any],
    uctx: _UsageCtx,
    showdown_fetch: LiveFetch | None,
    reference_compendium: dict[str, Any] | RoleConstructionDraft | None,
) -> RoleConstructionDraft:
    """Speed-control setter peer of Trick Room — opposite execution axis (go first).

    Provisional bars (reviewable): Prankster → Excellent; Spe≥floor → Good;
    usage-proven slow → Acceptable. Does NOT reuse weather's move→Good cap.
    """
    from recommender.role_compendium_usage import (
        _delivery_usage_hits,
        _hits_clear_set_pct_floor,
        _mega_usage_attribution,
        _move_display,
    )

    move_ids = frozenset(to_id(m) for m in sub_criteria["move_ids"])
    pool = _pool_index(legal_pool, snap)
    pool_ids = set(pool)
    prior = _ref_members(reference_compendium)
    members: list[CandidateEval] = []
    rejected: list[RejectedCandidate] = []
    notes = [
        "Excellent = Prankster + usage-proven Tailwind; Good = base Spe ≥ "
        f"{_TAILWIND_SPE_FLOOR} + usage-proven; Acceptable = usage-proven "
        "below Spe floor, or Excellent demoted by Showdown-discount / "
        "unproven-usage two-tier rule",
        _TAILWIND_DELIVERY_NOTE,
        "weather move+Prankster hard-caps at Good because ability setters sit "
        "above — Tailwind has no ability delivery, so Excellent remains "
        "reachable inside move-only grading (TR/redirection pattern)",
        "do not import Trick Room bulk≥210 membership — wrong axis (go-last survival)",
        "usage evidence prefers Champions in-game data where a row exists; "
        "Showdown is a fallback only for formes with no Champions row",
        "Prankster is blocked by Dark-types / Armor Tail / Queenly Majesty — "
        "noted in execution text, not an auto-reject",
    ]
    sd_cache: dict[str, dict[str, Any] | None] = {}

    eligible = {
        sid: name
        for sid, name in pool.items()
        if move_ids & set(resolve_learnset(snap, sid) or [])
    }

    pair_usage, pair_notes, _stone_used = _mega_usage_attribution(
        eligible,
        move_ids,
        snap=snap,
        uctx=uctx,
        sd_cache=sd_cache,
        showdown_fetch=showdown_fetch,
        notes=notes,
    )

    for sid, name in sorted(eligible.items(), key=lambda x: x[1]):
        hits = sorted(move_ids & set(resolve_learnset(snap, sid) or []))
        abs_map = _species_abilities(snap, sid)
        stats = _base_stats(snap, sid)
        mechanism = " / ".join(_move_display(snap, mid) for mid in hits)
        entry = uctx.entry_for(name)
        spe = int(stats.get("spe") or 0)
        has_prankster = "prankster" in abs_map

        if pair_usage.get(sid) is False:
            usage_proven = False
            usage_source = "mega attribution"
        else:
            usage_hits, usage_source = _delivery_usage_hits(
                name,
                set(hits),
                uctx=uctx,
                sd_cache=sd_cache,
                showdown_fetch=showdown_fetch,
            )
            usage_proven = bool(usage_hits)

        attr = pair_notes.get(sid, "")
        discounted = (
            "discounted" in attr
            or "stone-heuristic" in attr
            or "attributed to Mega" in attr
            or "mega-stone fallback" in attr
        )

        # Prankster is independent execution reinforce for admission (go-first).
        if not _admit_move_delivery(
            usage_proven=usage_proven, independent_reinforce=has_prankster
        ):
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=(
                        f"{mechanism} learnset but no usage evidence of Tailwind "
                        "delivery and no Prankster reinforce"
                        + (f" ({attr})" if attr else "")
                    ),
                    change_reason=(
                        "learnset-only without usage/Prankster"
                        if prior.get(sid)
                        else None
                    ),
                )
            )
            continue

        # Provisional tier grades (go-first axis).
        if has_prankster:
            tier, basis = "Excellent", "prankster_priority"
        elif spe >= _TAILWIND_SPE_FLOOR:
            tier, basis = "Good", "natural_speed"
        else:
            tier, basis = "Acceptable", "slow_manual"

        # Showdown-discount: Excellent → Acceptable; Good/Acceptable → reject.
        if discounted and usage_proven is False:
            demoted = _discount_outcome(
                "Excellent" if has_prankster else ("Good" if tier == "Good" else "Acceptable")
            )
            if demoted == "Acceptable" and has_prankster:
                tier, basis = "Acceptable", "usage_discounted_prankster"
            else:
                rejected.append(
                    RejectedCandidate(
                        species=name,
                        species_id=sid,
                        reason=(
                            f"{mechanism} learnset; usage discounted vs Mega form "
                            f"and mech tier {tier} has no Acceptable discount path"
                            + (f" ({attr})" if attr else "")
                        ),
                        change_reason=(
                            f"usage discount reject from {prior[sid]!r}"
                            if prior.get(sid)
                            else None
                        ),
                    )
                )
                continue
        elif discounted and has_prankster and usage_proven:
            # Discounted base with proven Mega path handled above; if still
            # discounted while usage_proven True, keep mech tier (independent).
            pass

        # Unproven usage: Prankster Excellent → Acceptable; else reject.
        if not usage_proven:
            if not has_prankster:
                rejected.append(
                    RejectedCandidate(
                        species=name,
                        species_id=sid,
                        reason=(
                            f"{mechanism} learnset but no usage evidence of Tailwind "
                            f"delivery; two-tier demotion from {tier} falls below "
                            "Acceptable"
                            + (f" ({attr})" if attr else "")
                        ),
                        change_reason=(
                            f"unproven-usage two-tier demotion from {prior[sid]!r}"
                            if prior.get(sid)
                            else None
                        ),
                    )
                )
                continue
            tier, basis = "Acceptable", "acceptable_prankster_unproven"

        secondary_note, secondary_traits = _secondary_support_notes(
            entry, move_ids=_TAILWIND_SECONDARY_MOVES
        )
        secondary_move_ids = {to_id(t.name) for t in secondary_traits}
        has_fg = bool({"friendguard"} & set(abs_map))
        verified_secondary = has_fg or bool(secondary_traits)
        excellent_secondary = _excellent_secondary(
            has_friend_guard=has_fg,
            secondary_move_ids=secondary_move_ids,
            excellent_move_ids=_TAILWIND_EXCELLENT_SECONDARY_MOVES,
        )

        exec_note = f"base Spe={spe}"
        traits: list[ClaimedTrait] = [
            ClaimedTrait(
                name=mechanism,
                criterion="delivery",
                purpose_claimed="double ally Speed for four turns",
            )
        ]
        if has_prankster:
            exec_note += (
                "; Prankster +1 priority on Tailwind — blocked by Dark-types / "
                "Armor Tail / Queenly Majesty"
            )
            traits.append(
                ClaimedTrait(
                    name=abs_map["prankster"],
                    criterion="execution",
                    purpose_claimed="priority status Tailwind; go-first reliability",
                )
            )
        elif spe >= _TAILWIND_SPE_FLOOR:
            exec_note += (
                f"; natural Spe ≥ {_TAILWIND_SPE_FLOOR} provisional floor "
                "(no Prankster)"
            )
            traits.append(
                ClaimedTrait(
                    name=f"Spe {spe}",
                    criterion="execution",
                    purpose_claimed="natural Speed to land Tailwind before threats",
                )
            )
        else:
            exec_note += (
                f"; Spe {spe} below provisional floor {_TAILWIND_SPE_FLOOR}; "
                "lands Tailwind only if the opposing field is slower / disrupted"
            )
        if not usage_proven:
            exec_note += "; usage unproven — two-tier demotion applied"
        traits.extend(secondary_traits)

        prev_tier = prior.get(sid)
        change_reason = None
        if prev_tier and prev_tier != tier:
            change_reason = f"tier {prev_tier!r} → {tier!r}" + (
                f" ({attr})" if attr else ""
            )

        members.append(
            CandidateEval(
                species=name,
                species_id=sid,
                tier=tier,
                delivery_class="move_tailwind",
                mechanism=mechanism,
                criteria_notes={
                    "delivery": _TAILWIND_DELIVERY_NOTE,
                    "execution": exec_note,
                    "secondary_role": secondary_note,
                    "usage_proven": str(usage_proven),
                    "usage_source": usage_source,
                    "verified_secondary": str(verified_secondary),
                    "excellent_secondary": str(excellent_secondary),
                    "reinforce_class": "prankster" if has_prankster else "none",
                    "spe": str(spe),
                    "spe_floor_provisional": str(_TAILWIND_SPE_FLOOR),
                    "attribution": attr or "none",
                },
                claimed_traits=traits,
                reasoning=(
                    f"{mechanism} clears {tier} (basis={basis}, "
                    f"usage_proven={usage_proven}, prankster={has_prankster}, "
                    f"spe={spe})"
                    + (f" / {attr}" if attr else "")
                    + "."
                ),
                change_reason=change_reason,
                reinforce_class="prankster" if has_prankster else "none",
                excellence_basis=basis,
            )
        )

    _guard_pool(members, rejected, pool_ids)
    return _draft_with_tiers(category, sub_criteria, members, rejected, notes=notes)


def _screens_mech_dual(hits: set[str], abs_map: dict[str, str]) -> bool:
    """LS+Reflect learnset, or Veil + Snow Warning (not Chilly Reception)."""
    if "lightscreen" in hits and "reflect" in hits:
        return True
    return "auroraveil" in hits and bool(set(abs_map) & _SCREENS_SNOW_ABILITIES)


def _screens_dual_usage(
    name: str,
    hits: set[str],
    abs_map: dict[str, str],
    *,
    uctx: _UsageCtx,
    sd_cache: dict[str, dict[str, Any] | None],
    showdown_fetch: LiveFetch | None,
) -> tuple[str | None, set[str]]:
    """Usage-proven dual path at Screens' 2.3% floor. Same-row for LS+Reflect."""
    from recommender.role_compendium_usage import (
        _hits_clear_set_pct_floor,
        _same_row_both_moves,
    )

    paths: list[str] = []
    mids: set[str] = set()
    kw = dict(uctx=uctx, sd_cache=sd_cache, showdown_fetch=showdown_fetch)
    if "lightscreen" in hits and "reflect" in hits:
        if _same_row_both_moves(name, "lightscreen", "reflect", **kw) and (
            _hits_clear_set_pct_floor(
                name,
                {"lightscreen", "reflect"},
                floor=_USAGE_SET_PCT_FLOOR,
                require_all=True,
                **kw,
            )
        ):
            paths.append("ls+reflect")
            mids.update({"lightscreen", "reflect"})
    if "auroraveil" in hits and "snowwarning" in abs_map:
        if _hits_clear_set_pct_floor(
            name, {"auroraveil"}, floor=_USAGE_SET_PCT_FLOOR, **kw
        ):
            paths.append("veil+snowwarning")
            mids.add("auroraveil")
    return ("+".join(paths) if paths else None), mids


def _construct_screens_support(
    category: str,
    sub_criteria: dict[str, Any],
    legal_pool: list[str],
    *,
    snap: dict[str, Any],
    uctx: _UsageCtx,
    showdown_fetch: LiveFetch | None,
    reference_compendium: dict[str, Any] | RoleConstructionDraft | None,
) -> RoleConstructionDraft:
    """Screens Support — TW-shaped move-only setter; Veil is a snow-gated pathway."""
    from recommender.role_compendium_usage import (
        _delivery_usage_hits,
        _hits_clear_set_pct_floor,
        _mega_usage_attribution,
        _move_display,
        _usage_has_item,
    )

    move_ids = frozenset(to_id(m) for m in sub_criteria["move_ids"]) or _SCREENS_MOVE_IDS
    pool = _pool_index(legal_pool, snap)
    pool_ids = set(pool)
    prior = _ref_members(reference_compendium)
    members: list[CandidateEval] = []
    rejected: list[RejectedCandidate] = []
    notes = [
        "Excellent = dual-screen usage + Prankster; Good = dual-screen usage + "
        f"base Spe ≥ {_SCREENS_SPE_FLOOR} (no Prankster); Acceptable = dual "
        "below Spe floor, or single-screen + Prankster (Whimsicott)",
        "dual-screen = usage-proven Reflect AND Light Screen (same-row, both "
        f"≥ {_USAGE_SET_PCT_FLOOR:g}% set%) OR Aurora Veil ≥ "
        f"{_USAGE_SET_PCT_FLOOR:g}% plus Snow Warning (not Chilly Reception)",
        "Light Clay + a lone screen is not membership (Florges / Rotom-Wash); "
        "Veil without Snow Warning is not dual (Avalugg)",
        "Meowstic Excellent is male only (Prankster); female has Competitive",
        "one category folds Dual Screens / Light Screen / Reflect / Aurora Veil "
        "— splitting does not narrow a distinct search",
        _SCREENS_DELIVERY_NOTE,
        "usage evidence prefers Champions in-game data where a row exists; "
        "Showdown is a fallback only for formes with no Champions row",
        "Prankster is blocked by Dark-types / Armor Tail / Queenly Majesty — "
        "noted in execution text, not an auto-reject",
    ]
    sd_cache: dict[str, dict[str, Any] | None] = {}

    eligible = {
        sid: name
        for sid, name in pool.items()
        if move_ids & set(resolve_learnset(snap, sid) or [])
    }

    _pair_usage, pair_notes, _stone_used = _mega_usage_attribution(
        eligible,
        move_ids,
        snap=snap,
        uctx=uctx,
        sd_cache=sd_cache,
        showdown_fetch=showdown_fetch,
        notes=notes,
    )

    for sid, name in sorted(eligible.items(), key=lambda x: x[1]):
        ls = set(resolve_learnset(snap, sid) or [])
        hits = set(move_ids & ls)
        abs_map = _species_abilities(snap, sid)
        stats = _base_stats(snap, sid)
        entry = uctx.entry_for(name)
        spe = int(stats.get("spe") or 0)
        has_prankster = "prankster" in abs_map
        attr = pair_notes.get(sid, "")
        dual_path, dual_mids = _screens_dual_usage(
            name,
            hits,
            abs_map,
            uctx=uctx,
            sd_cache=sd_cache,
            showdown_fetch=showdown_fetch,
        )
        usage_mids, usage_source = _delivery_usage_hits(
            name,
            hits,
            uctx=uctx,
            sd_cache=sd_cache,
            showdown_fetch=showdown_fetch,
        )
        has_clay = _usage_has_item(
            name,
            "lightclay",
            uctx=uctx,
            sd_cache=sd_cache,
            showdown_fetch=showdown_fetch,
        )
        single_prankster = (
            dual_path is None
            and has_prankster
            and bool(usage_mids & hits)
        )
        qualify_mids = dual_mids if dual_path else (usage_mids & hits)
        mechanism = " / ".join(
            _move_display(snap, mid) for mid in sorted(qualify_mids or hits)
        )

        if dual_path is None and not single_prankster:
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=(
                        f"{mechanism} learnset but not screens_support: need "
                        "usage-proven dual LS+Reflect (same-row), Veil+Snow "
                        "Warning, or single-screen + Prankster"
                        + (f" ({attr})" if attr else "")
                    ),
                    change_reason=(
                        "failed dual/Prankster usage gate"
                        if prior.get(sid)
                        else None
                    ),
                )
            )
            continue

        if dual_path and has_prankster:
            tier, basis = "Excellent", "prankster_priority"
        elif dual_path and spe >= _SCREENS_SPE_FLOOR:
            tier, basis = "Good", "natural_speed"
        elif dual_path:
            tier, basis = "Acceptable", "slow_manual"
        else:
            tier, basis = "Acceptable", "prankster_single_screen"

        secondary_note, secondary_traits = _secondary_support_notes(
            entry, move_ids=_SCREENS_SECONDARY_MOVES
        )
        secondary_move_ids = {to_id(t.name) for t in secondary_traits}
        has_fg = bool({"friendguard"} & set(abs_map))
        verified_secondary = has_fg or bool(secondary_traits)
        excellent_secondary = _excellent_secondary(
            has_friend_guard=has_fg,
            secondary_move_ids=secondary_move_ids,
            excellent_move_ids=_SCREENS_EXCELLENT_SECONDARY_MOVES,
        )

        veil = "auroraveil" in (qualify_mids or hits)
        sets_snow = "snowwarning" in abs_map
        exec_note = f"base Spe={spe}"
        traits: list[ClaimedTrait] = [
            ClaimedTrait(
                name=mechanism,
                criterion="delivery",
                purpose_claimed="ally physical/special damage reduction via screens",
            )
        ]
        if has_prankster:
            exec_note += (
                "; Prankster +1 priority on screens — blocked by Dark-types / "
                "Armor Tail / Queenly Majesty"
            )
            traits.append(
                ClaimedTrait(
                    name=abs_map["prankster"],
                    criterion="execution",
                    purpose_claimed="priority status screens; go-first reliability",
                )
            )
        elif spe >= _SCREENS_SPE_FLOOR:
            exec_note += (
                f"; natural Spe ≥ {_SCREENS_SPE_FLOOR} floor (no Prankster)"
            )
            traits.append(
                ClaimedTrait(
                    name=f"Spe {spe}",
                    criterion="execution",
                    purpose_claimed="natural Speed to land screens before threats",
                )
            )
        else:
            exec_note += (
                f"; Spe {spe} below floor {_SCREENS_SPE_FLOOR}; "
                "lands screens only if the opposing field is slower / disrupted"
            )
        if has_clay:
            exec_note += "; Light Clay extends screen duration"
        if veil:
            exec_note += "; Aurora Veil is snow-gated"
            if sets_snow:
                exec_note += " (Snow Warning)"
            else:
                exec_note += " (no Snow Warning — not dual)"
        if dual_path:
            exec_note += f"; dual_path={dual_path}"
        elif single_prankster:
            exec_note += "; single-screen + Prankster"
        traits.extend(secondary_traits)

        prev_tier = prior.get(sid)
        change_reason = None
        if prev_tier and prev_tier != tier:
            change_reason = f"tier {prev_tier!r} → {tier!r}" + (
                f" ({attr})" if attr else ""
            )

        members.append(
            CandidateEval(
                species=name,
                species_id=sid,
                tier=tier,
                delivery_class="move_screens",
                mechanism=mechanism,
                criteria_notes={
                    "delivery": _SCREENS_DELIVERY_NOTE,
                    "execution": exec_note,
                    "secondary_role": secondary_note,
                    "usage_proven": "True",
                    "usage_source": usage_source,
                    "verified_secondary": str(verified_secondary),
                    "excellent_secondary": str(excellent_secondary),
                    "reinforce_class": "prankster" if has_prankster else "none",
                    "spe": str(spe),
                    "spe_floor_provisional": str(_SCREENS_SPE_FLOOR),
                    "light_clay": str(has_clay),
                    "aurora_veil": str(veil),
                    "dual_path": dual_path or "single_prankster",
                    "attribution": attr or "none",
                },
                claimed_traits=traits,
                reasoning=(
                    f"{mechanism} clears {tier} (basis={basis}, "
                    f"dual_path={dual_path or 'single_prankster'}, "
                    f"prankster={has_prankster}, spe={spe})"
                    + (f" / {attr}" if attr else "")
                    + "."
                ),
                change_reason=change_reason,
                reinforce_class="prankster" if has_prankster else "none",
                excellence_basis=basis,
            )
        )

    _guard_pool(members, rejected, pool_ids)
    return _draft_with_tiers(category, sub_criteria, members, rejected, notes=notes)


def _sleep_delivery_ids(snap: dict[str, Any]) -> frozenset[str]:
    """Core sleep set plus any other Status sleep move present in the snapshot."""
    found = set(_SLEEP_CORE_MOVES)
    for mid in _SLEEP_STATUS_MOVES:
        entry = (snap.get("moves") or {}).get(mid) or {}
        if not entry:
            continue
        if str(entry.get("category") or "") != "Status":
            continue
        found.add(mid)
    return frozenset(found)


def _sleep_pathway(
    *,
    delivery_hits: set[str],
    accuracy_reinforce: bool,
    has_trap: bool,
) -> tuple[str, str, str]:
    """Return (pathway_id, primary_move_id, label) for the best available delivery."""
    if "spore" in delivery_hits:
        return "P0", "spore", "Spore (100% immediate; new reliability class)"
    if "sleeppowder" in delivery_hits and accuracy_reinforce:
        return "P1", "sleeppowder", "Sleep Powder + accuracy reinforce"
    if "sleeppowder" in delivery_hits:
        return "P2", "sleeppowder", "Sleep Powder (no accuracy reinforce)"
    imperfect = sorted(
        mid for mid in delivery_hits if mid in _SLEEP_IMMEDIATE and mid != "spore"
    )
    # Hypnosis-class (includes Sing / Dark Void / etc. when legal).
    hypno_class = [m for m in imperfect if m != "sleeppowder"]
    if hypno_class and accuracy_reinforce:
        mid = "hypnosis" if "hypnosis" in hypno_class else hypno_class[0]
        return "P2", mid, f"{mid} + accuracy reinforce"
    if hypno_class:
        mid = "hypnosis" if "hypnosis" in hypno_class else hypno_class[0]
        return "P3", mid, f"bare {mid}"
    if "yawn" in delivery_hits:
        label = "Yawn + trapping" if has_trap else "Yawn (delayed; no trap)"
        return "P4", "yawn", label
    mid = next(iter(sorted(delivery_hits)))
    return "P?", mid, f"unclassified sleep delivery ({mid})"


def _construct_sleep_status_spreader(
    category: str,
    sub_criteria: dict[str, Any],
    legal_pool: list[str],
    *,
    snap: dict[str, Any],
    uctx: _UsageCtx,
    showdown_fetch: LiveFetch | None,
    reference_compendium: dict[str, Any] | RoleConstructionDraft | None,
) -> RoleConstructionDraft:
    """Sleep status role — ADR-015 2026-07-29f mechanism-dependent bars (provisional)."""
    from recommender.role_compendium_usage import (
        _delivery_usage_hits,
        _mega_usage_attribution,
        _move_display,
    )

    delivery_ids = _sleep_delivery_ids(snap)
    pool = _pool_index(legal_pool, snap)
    pool_ids = set(pool)
    prior = _ref_members(reference_compendium)
    members: list[CandidateEval] = []
    rejected: list[RejectedCandidate] = []

    # Presence check for reliability classes (construction notes, not fake rejects).
    legal_learners: dict[str, int] = {mid: 0 for mid in sorted(delivery_ids)}
    for sid in pool:
        ls = set(resolve_learnset(snap, sid) or [])
        for mid in delivery_ids:
            if mid in ls:
                legal_learners[mid] = legal_learners.get(mid, 0) + 1

    spore_learners = legal_learners.get("spore", 0)
    spore_absent = spore_learners == 0
    notes = [
        "Ranking is pathway-first by execution reliability (accuracy / whether "
        "sleep actually lands). Spe is secondary for imperfect immediate "
        "delivery (P2/P3): base Spe ≥ floor OR a speed-boosting ability "
        "(Chlorophyll / Swift Swim / Sand Rush / Slush Rush / Unburden / "
        "Speed Boost) clears the Spe bar; failing it demotes one rank. "
        "P1 (near-perfect accuracy) does not Spe-demote — ADR-015: Spe/"
        "bulk matter less when the accuracy roll is already near-guaranteed. "
        "P4 Yawn ignores Spe entirely.",
        "Natural pathway order: P0 Spore (100% immediate) > P1 Sleep Powder+"
        "accuracy reinforce > P2 Sleep Powder bare / Hypnosis+reinforce > "
        "P3 bare Hypnosis/Sing-class > P4 Yawn (delayed; switch-window).",
        "Excellent is reserved for Spore (P0). When Spore is absent from the "
        "legal pool, ADR-019 entire-class gap: push remaining pathways up one "
        "tier (P1→Excellent, P2→Good, P3→Acceptable) so Excellent is not "
        "left empty while a worse pathway occupies Good.",
        "Bare P4 (Yawn, no trapping) is below P3 and is rejected — only three "
        "tiers exist, so keeping it co-equal with P3 in Acceptable would hide "
        "the reliability gap. P4+Shadow Tag (or other trap) closes the switch "
        "window and stays Acceptable (elevated within Yawn only; still never "
        "outranks P2).",
        "Helping Hand excluded from sleep secondary excellence",
        "usage evidence prefers Champions in-game data where a row exists",
        (
            "Spore reliability class ABSENT — push-up ACTIVE"
            if spore_absent
            else f"Spore learners_in_pool={spore_learners} — no push-up"
        ),
    ]
    for mid, n in sorted(legal_learners.items()):
        acc = _SLEEP_ACCURACY.get(mid, "?")
        notes.append(
            f"delivery availability: {mid} learners_in_pool={n} "
            f"(catalog accuracy={acc})"
        )
        if n == 0 and mid in ("spore", "darkvoid"):
            notes.append(
                f"{mid} reliability class ABSENT from current legal pool "
                "(ADR-019 entire-class gap)"
            )

    sd_cache: dict[str, dict[str, Any] | None] = {}
    eligible = {
        sid: name
        for sid, name in pool.items()
        if delivery_ids & set(resolve_learnset(snap, sid) or [])
    }

    pair_usage, pair_notes, _stone_used = _mega_usage_attribution(
        eligible,
        delivery_ids,
        snap=snap,
        uctx=uctx,
        sd_cache=sd_cache,
        showdown_fetch=showdown_fetch,
        notes=notes,
    )

    for sid, name in sorted(eligible.items(), key=lambda x: x[1]):
        ls = set(resolve_learnset(snap, sid) or [])
        delivery_hits = set(delivery_ids & ls)
        abs_map = _species_abilities(snap, sid)
        stats = _base_stats(snap, sid)
        entry = uctx.entry_for(name)
        spe = int(stats.get("spe") or 0)
        bulk = sum(int(stats.get(k) or 0) for k in ("hp", "def", "spd"))

        # Exhaustive kit sweep (ADR-019) — every candidate, not opportunistic.
        kit_accuracy = sorted(set(abs_map) & _SLEEP_ACCURACY_ABILITIES)
        kit_trap = sorted(set(abs_map) & _SLEEP_TRAP_ABILITIES)
        kit_speed = sorted(set(abs_map) & _SLEEP_SPEED_ABILITIES)
        coil_learnset = "coil" in ls
        coil_usage = bool(entry) and _entry_has_move(entry, "coil")
        accuracy_reinforce = bool(kit_accuracy) or coil_usage
        has_trap = bool(kit_trap)

        pathway, primary_mid, pathway_label = _sleep_pathway(
            delivery_hits=delivery_hits,
            accuracy_reinforce=accuracy_reinforce,
            has_trap=has_trap,
        )
        # Bare P4 (Yawn, no trap) is below P3 — reject rather than share Acceptable.
        if pathway == "P4" and not has_trap:
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=(
                        f"{_move_display(snap, primary_mid)} ({pathway_label}): "
                        "bare Yawn without trapping is below P3 reliability and "
                        "is rejected (only P4+trap closes the switch-window "
                        "enough to keep Acceptable)"
                    ),
                    change_reason=(
                        "bare yawn rejected below P3" if prior.get(sid) else None
                    ),
                )
            )
            continue

        mechanism = _move_display(snap, primary_mid)
        # If multiple deliveries, list them for transparency.
        if len(delivery_hits) > 1:
            mechanism = " / ".join(
                _move_display(snap, mid) for mid in sorted(delivery_hits)
            )

        if pair_usage.get(sid) is False:
            usage_proven = False
            usage_source = "mega attribution"
        else:
            usage_hits, usage_source = _delivery_usage_hits(
                name,
                set(delivery_hits),
                uctx=uctx,
                sd_cache=sd_cache,
                showdown_fetch=showdown_fetch,
            )
            usage_proven = bool(usage_hits)

        # Pathway-matched independent reinforce for admission.
        if pathway == "P4":
            independent = has_trap
        elif pathway in {"P1", "P2", "P0"}:
            independent = accuracy_reinforce
        else:
            independent = accuracy_reinforce  # P3 bare — reinforce uncommon

        attr = pair_notes.get(sid, "")
        discounted = (
            "discounted" in attr
            or "stone-heuristic" in attr
            or "attributed to Mega" in attr
            or "mega-stone fallback" in attr
        )

        if not _admit_move_delivery(
            usage_proven=usage_proven, independent_reinforce=independent
        ):
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=(
                        f"{mechanism} learnset ({pathway_label}) but no usage "
                        "evidence of sleep delivery and no pathway-matched reinforce"
                        + (f" ({attr})" if attr else "")
                    ),
                    change_reason=(
                        "learnset-only without usage/reinforce"
                        if prior.get(sid)
                        else None
                    ),
                )
            )
            continue

        spe_applies = primary_mid in _SLEEP_IMMEDIATE
        has_speed_ability = bool(kit_speed)
        # Base Spe floor OR speed-boosting ability (Chlorophyll etc.) — ability
        # presence is the check; weather uptime is noted, not separately gated.
        spe_ok = (not spe_applies) or spe >= _SLEEP_SPE_FLOOR or has_speed_ability
        if not spe_applies:
            spe_skip_note = (
                "Speed ignored for ranking: Yawn delayed delivery"
            )
        elif spe >= _SLEEP_SPE_FLOOR:
            spe_skip_note = f"Spe {spe} ≥ {_SLEEP_SPE_FLOOR}"
        elif has_speed_ability:
            spe_skip_note = (
                f"Spe {spe} < {_SLEEP_SPE_FLOOR} but speed ability "
                f"{'/'.join(abs_map[a] for a in kit_speed)} clears Spe bar "
                "(condition-dependent in battle)"
            )
        else:
            spe_skip_note = (
                f"Spe {spe} < {_SLEEP_SPE_FLOOR} and no speed-boosting ability "
                "— demote one rank on imperfect immediate pathways (P2/P3)"
            )

        # Effective accuracy after reinforce (Compound Eyes ≈ ×1.3).
        base_acc = _SLEEP_ACCURACY.get(primary_mid, 100)
        if "noguard" in kit_accuracy:
            eff_acc = 100
        elif "compoundeyes" in kit_accuracy:
            eff_acc = min(100, int(base_acc * 1.3))
        elif coil_usage:
            # Coil +1 accuracy stage ≈ ×4/3 on next moves — approximate for notes.
            eff_acc = min(100, int(base_acc * 4 / 3))
        else:
            eff_acc = base_acc
        bulk_relevant = eff_acc < 100
        bulk_note = (
            f"bulk HP+Def+SpD={bulk} (miss-insurance; acc≈{eff_acc}%)"
            if bulk_relevant
            else f"bulk HP+Def+SpD={bulk} (miss-insurance skipped: eff acc≈{eff_acc}%)"
        )

        # Pathway reliability rank (lower = more reliable execution).
        # Bare P4 already rejected above; P4+trap elevates to P3 rank only.
        pathway_rank = {
            "P0": 0,
            "P1": 1,
            "P2": 2,
            "P3": 3,
            "P4": 3,  # trap-only survivors; equals P3 floor, never above P2
        }.get(pathway, 5)
        if pathway == "P4":
            basis = "yawn_trap"
        elif pathway == "P0":
            basis = "spore_immediate"
        elif pathway == "P1":
            basis = "sleeppowder_accuracy"
        elif pathway == "P2":
            basis = "p2_mid_accuracy"
        elif pathway == "P3":
            basis = "bare_hypnosis"
        else:
            basis = "unclassified"

        # Spore absent → push remaining pathways up one rank (Excellent not empty).
        effective_rank = pathway_rank - 1 if spore_absent else pathway_rank
        # P2/P3 Spe demotion: imperfect immediate sleep needs Spe or speed ability.
        # P1 skipped (near-perfect accuracy — ADR-015). P4 Spe-irrelevant.
        if pathway in {"P2", "P3"} and not spe_ok:
            effective_rank += 1
            basis = f"{basis}_slow"
        if effective_rank <= 0:
            tier = "Excellent"
        elif effective_rank == 1:
            tier = "Good"
        elif effective_rank <= 3:
            tier = "Acceptable"
        else:
            # P2/P3 that were already Acceptable and then Spe-demoted fall off.
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=(
                        f"{mechanism} ({pathway_label}): pathway clears only "
                        f"Acceptable after push-up, then Spe bar fails "
                        f"(Spe {spe}, speed_abil={kit_speed or ['none']}) — "
                        "below Acceptable"
                    ),
                )
            )
            continue
        if spore_absent and pathway != "P0":
            basis = f"pushup_{basis}"

        # Discount / unproven demotion: Excellent → Acceptable; else reject.
        if discounted and not usage_proven:
            if tier == "Excellent":
                demoted = _discount_outcome("Excellent")
                assert demoted == "Acceptable"
                tier, basis = "Acceptable", f"discounted_{basis}"
            else:
                rejected.append(
                    RejectedCandidate(
                        species=name,
                        species_id=sid,
                        reason=(
                            f"{mechanism} usage discounted vs Mega; mech {tier} "
                            "has no Acceptable discount path"
                            + (f" ({attr})" if attr else "")
                        ),
                    )
                )
                continue
        elif not usage_proven:
            if tier == "Excellent":
                tier, basis = "Acceptable", f"unproven_{basis}"
            else:
                rejected.append(
                    RejectedCandidate(
                        species=name,
                        species_id=sid,
                        reason=(
                            f"{mechanism} ({pathway_label}) learnset but no usage; "
                            f"two-tier demotion from {tier} falls below Acceptable"
                            + (f" ({attr})" if attr else "")
                        ),
                    )
                )
                continue

        secondary_note, secondary_traits = _secondary_support_notes(
            entry, move_ids=_SLEEP_SECONDARY_MOVES
        )
        secondary_move_ids = {to_id(t.name) for t in secondary_traits}
        has_fg = bool({"friendguard"} & set(abs_map))
        verified_secondary = has_fg or bool(secondary_traits)
        excellent_secondary = _excellent_secondary(
            has_friend_guard=has_fg,
            secondary_move_ids=secondary_move_ids,
            excellent_move_ids=_SLEEP_EXCELLENT_SECONDARY_MOVES,
        )

        kit_sweep = (
            f"accuracy_abil={kit_accuracy or ['none']}; "
            f"trap={kit_trap or ['none']}; "
            f"speed_abil={kit_speed or ['none']}; "
            f"coil_learnset={coil_learnset}; coil_usage={coil_usage}"
        )
        exec_parts = [
            pathway_label,
            spe_skip_note,
            bulk_note,
            kit_sweep,
        ]
        if not usage_proven:
            exec_parts.append("usage unproven — demotion applied")
        exec_note = "; ".join(exec_parts)

        traits: list[ClaimedTrait] = [
            ClaimedTrait(
                name=mechanism,
                criterion="delivery",
                purpose_claimed="inflict sleep on an opposing Pokémon",
            )
        ]
        for aid in kit_accuracy:
            traits.append(
                ClaimedTrait(
                    name=abs_map[aid],
                    criterion="execution",
                    purpose_claimed="accuracy reinforce on imperfect sleep delivery",
                )
            )
        if coil_usage:
            traits.append(
                ClaimedTrait(
                    name="Coil",
                    criterion="execution",
                    purpose_claimed="usage-proven +1 accuracy stage among Coil effects",
                )
            )
        for aid in kit_trap:
            purpose = (
                "closes Yawn switch-window"
                if pathway == "P4"
                else "trap present but ignored (not Yawn pathway)"
            )
            traits.append(
                ClaimedTrait(
                    name=abs_map[aid],
                    criterion="execution",
                    purpose_claimed=purpose,
                )
            )
        traits.extend(secondary_traits)

        prev_tier = prior.get(sid)
        change_reason = None
        if prev_tier and prev_tier != tier:
            change_reason = f"tier {prev_tier!r} → {tier!r}" + (
                f" ({attr})" if attr else ""
            )

        members.append(
            CandidateEval(
                species=name,
                species_id=sid,
                tier=tier,
                delivery_class=f"sleep_{pathway.lower()}",
                mechanism=mechanism,
                criteria_notes={
                    "delivery": pathway_label,
                    "execution": exec_note,
                    "secondary_role": secondary_note,
                    "usage_proven": str(usage_proven),
                    "usage_source": usage_source,
                    "verified_secondary": str(verified_secondary),
                    "excellent_secondary": str(excellent_secondary),
                    "pathway": pathway,
                    "pathway_rank": str(pathway_rank),
                    "effective_rank": str(effective_rank),
                    "spore_absent_pushup": str(spore_absent),
                    "primary_move": primary_mid,
                    "spe_applies": str(spe_applies),
                    "spe": str(spe),
                    "spe_ok": str(spe_ok),
                    "speed_abilities": ",".join(kit_speed) or "none",
                    "eff_accuracy": str(eff_acc),
                    "kit_sweep": kit_sweep,
                    "attribution": attr or "none",
                },
                claimed_traits=traits,
                reasoning=(
                    f"{mechanism} clears {tier} (pathway={pathway}, basis={basis}, "
                    f"usage_proven={usage_proven})"
                    + (f" / {attr}" if attr else "")
                    + "."
                ),
                change_reason=change_reason,
                reinforce_class=(
                    "accuracy"
                    if accuracy_reinforce
                    else ("trap" if has_trap and pathway == "P4" else "none")
                ),
                excellence_basis=basis,
            )
        )

    _guard_pool(members, rejected, pool_ids)
    return _draft_with_tiers(category, sub_criteria, members, rejected, notes=notes)
