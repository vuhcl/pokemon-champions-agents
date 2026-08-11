"""Tests for move narrowing, redundancy validation, and ADR-021 kit layer."""

from __future__ import annotations

from unittest.mock import patch

from recommender.ids import to_id
from recommender.move_narrowing import (
    BACKSTOP_CEILING,
    ProposedInteraction,
    _ARCHETYPE_PREF_MOVES,
    _WEATHER_MANUAL,
    assemble_moveset_fallback,
    learners_of,
    move_priority,
    narrow_candidates_for_move,
    pick_default_and_alternatives,
    validate_moveset_redundancy,
    verify_kit_interaction,
)
from recommender.propose import fill_team_draft
from recommender.state import Attr, RecommenderState, Slot, empty_slot


def _state(**overrides) -> RecommenderState:
    state: RecommenderState = {
        "format_id": "[Gen 9 Champions] VGC 2026 Reg M-B",
        "game_type": "doubles",
        "regulation_mod": "champions",
        "picked_team_size": 4,
        "available_pool": [],
        "team_draft": [empty_slot() for _ in range(6)],
        "archetype": Attr(),
        "rejected": [],
        "constraints": [],
        "messages": [],
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


def test_follow_me_stops_at_small_pool():
    r = narrow_candidates_for_move("followme", _state())
    assert r.stopped_at == 1
    assert len(r.candidates) <= 8
    assert len(r.candidates) == len(learners_of("followme"))


def test_small_pool_applies_ownership_before_return():
    pool = learners_of("followme")
    owned = pool[-1]
    only = narrow_candidates_for_move(
        "followme",
        _state(),
        available_species=[owned],
        ownership_mode="owned_only",
    )
    assert only.candidates == [owned]
    first = narrow_candidates_for_move(
        "followme",
        _state(),
        available_species=[owned],
        ownership_mode="owned_first",
    )
    assert first.candidates[0] == owned


def test_follow_me_forced_past_step1_skips_grouping():
    r = narrow_candidates_for_move("followme", _state(), small_pool=0)
    assert r.grouping_skipped is True
    assert r.stopped_at == 3


def test_trick_room_priority_skips_grouping():
    assert move_priority("trickroom") == -7
    r = narrow_candidates_for_move("trickroom", _state(), small_pool=0)
    assert r.grouping_skipped is True
    assert r.stopped_at == 3
    assert set(r.candidate_meta) == {to_id(name) for name in r.candidates}


def test_encore_delivery_groups_prankster_first():
    # Fixture commitments so order is deterministic without relying on live CBD.
    pool = learners_of("encore")
    assert len(pool) > 8
    pranksterish = ["Whimsicott", "Klefki", "Sableye", "Liepard"]
    natural = [n for n in pool if n not in pranksterish][:5]
    names = [n for n in pranksterish if n in pool] + natural
    commitment = {n: float(90 - i) for i, n in enumerate(names)}
    usage = {n: 5.0 for n in names}
    usage["Klefki"] = 0.5  # below MIN_USAGE_PCT — must NOT demote inside small group

    # Force a mid-size pool via override by monkeypatching learners — use small_pool=0
    # and commitment_override on real learners; check prankster delivery tags and order.
    r = narrow_candidates_for_move(
        "encore",
        _state(),
        small_pool=0,
        commitment_override=commitment,
        usage_override=usage,
    )
    assert r.grouping_skipped is False
    assert r.stopped_at == 3
    # First candidates with prankster delivery should come before natural_speed.
    deliveries = [r.delivery.get(c) for c in r.candidates]
    if "prankster" in deliveries and "natural_speed" in deliveries:
        first_nat = deliveries.index("natural_speed")
        assert all(d == "prankster" for d in deliveries[:first_nat])


def test_bulky_slow_high_commitment_remains():
    """Low Spe must not exclude a high-commitment candidate (old SPE_MARGIN bug)."""
    r = narrow_candidates_for_move(
        "willowisp",
        _state(),
        small_pool=0,
        commitment_override={"Sableye": 95.0, "Gengar": 40.0},
        usage_override={"Sableye": 2.0, "Gengar": 10.0},
    )
    assert "Sableye" in r.candidates


def test_klefki_within_tier_demotion_still_before_naturals():
    # BEFORE: demotion inactive when final ≤20; Klefki stayed in pure commitment
    # order among Pranksters (not shoved after clearers).
    # AFTER: within-tier demotion always applies — Klefki (low usage) sorts after
    # usage-clearing Pranksters, but still before all natural-Speed (tier boundary).
    names = [
        "Whimsicott",
        "Klefki",
        "Sableye",
        "Liepard",
        "Tornadus",
        "Thundurus",
        "Meowstic",
        "Murkrow",
    ]
    naturals = ["Incineroar", "Rillaboom", "Garchomp"]
    commitment = {n: float(80 - i * 5) for i, n in enumerate(names)}
    commitment["Klefki"] = 70.0
    commitment.update({n: 40.0 for n in naturals})
    usage = {n: 5.0 for n in names}
    usage["Klefki"] = 0.2
    usage.update({n: 5.0 for n in naturals})

    with patch(
        "recommender.move_narrowing.learners_of",
        return_value=names + naturals,
    ):
        with patch(
            "recommender.move_narrowing._has_prankster",
            side_effect=lambda snap, sp: sp in names,
        ):
            r = narrow_candidates_for_move(
                "encore",
                _state(),
                small_pool=0,
                commitment_override=commitment,
                usage_override=usage,
            )
    assert r.backstop_applied is False  # input size ≤20 → cut not engaged
    assert "Klefki" in r.candidates
    klefki_i = r.candidates.index("Klefki")
    whims_i = r.candidates.index("Whimsicott")
    assert whims_i < klefki_i  # clearer Prankster before demoted Klefki
    first_nat = next(
        i for i, c in enumerate(r.candidates) if r.delivery.get(c) == "natural_speed"
    )
    assert klefki_i < first_nat  # demoted Prankster still before any nat


def test_within_tier_demotion_when_pool_le_20_prankster_still_before_nat():
    # BEFORE: demotion inactive when final ≤20; no usage reorder; backstop_applied False.
    # AFTER: within-tier demotion visible even when pool ≤20; backstop_applied still
    # False (flag means input size > 20 / cut engaged, not "demotion ran").
    # P0 (usage clearer) before demoted P1; P1 still before N0 (tier boundary).
    prank = [f"P{i}" for i in range(8)]
    nat = [f"N{i}" for i in range(5)]
    pool = prank + nat
    commitment = {n: 50.0 for n in pool}
    usage = {n: 0.1 for n in pool}
    usage["P0"] = 10.0

    with patch("recommender.move_narrowing.learners_of", return_value=pool):
        with patch(
            "recommender.move_narrowing._has_prankster",
            side_effect=lambda snap, sp: sp.startswith("P"),
        ):
            r = narrow_candidates_for_move(
                "encore",
                _state(),
                small_pool=0,
                commitment_override=commitment,
                usage_override=usage,
            )
    assert len(r.candidates) == 13
    assert r.backstop_applied is False
    assert r.candidates.index("P0") < r.candidates.index("P1")  # within-tier demotion
    assert r.candidates.index("P1") < r.candidates.index("N0")  # tier: Prankster > nat


def test_cut_to_20_within_tier_demotion_prankster_outranks_nat():
    # BEFORE: global recombined demotion — a nat clearer could outrank a demoted
    # Prankster when competing for the top-20 cut.
    # AFTER (deliberate correction, not retrofit accident): demotion is within-tier
    # only; every kept Prankster (including demoted) outranks every natural-Speed.
    # Within each tier, clearers still precede demoted. Cut to BACKSTOP_CEILING.
    prank = [f"P{i}" for i in range(15)]
    nat = [f"N{i}" for i in range(18)]
    pool = prank + nat
    commitment = {n: float(100 - i) for i, n in enumerate(pool)}
    usage = {n: 5.0 for n in pool}
    for n in prank[10:] + nat[12:]:
        usage[n] = 0.1

    with patch("recommender.move_narrowing.learners_of", return_value=pool):
        with patch(
            "recommender.move_narrowing._has_prankster",
            side_effect=lambda snap, sp: sp.startswith("P"),
        ):
            r = narrow_candidates_for_move(
                "encore",
                _state(),
                small_pool=0,
                commitment_override=commitment,
                usage_override=usage,
            )
    assert len(r.candidates) == BACKSTOP_CEILING
    assert r.backstop_applied is True
    kept = r.candidates
    deliveries = [r.delivery.get(c) for c in kept]
    if "natural_speed" in deliveries:
        first_nat = deliveries.index("natural_speed")
        assert all(d == "prankster" for d in deliveries[:first_nat])
    # Within-tier: among kept Pranksters, clearers before demoted.
    demoted = {n for n, u in usage.items() if u < 1.0}
    kept_prank = [c for c in kept if r.delivery.get(c) == "prankster"]
    prank_clear = [c for c in kept_prank if c not in demoted]
    prank_low = [c for c in kept_prank if c in demoted]
    if prank_clear and prank_low:
        assert kept.index(prank_clear[-1]) < kept.index(prank_low[0])
    # Correction: demoted Prankster outranks any nat clearer.
    demoted_prank_kept = [c for c in kept_prank if c in demoted]
    nat_clear_kept = [
        c for c in kept if r.delivery.get(c) == "natural_speed" and c not in demoted
    ]
    if demoted_prank_kept and nat_clear_kept:
        assert kept.index(demoted_prank_kept[0]) < kept.index(nat_clear_kept[0])

def test_redundancy_a_precondition_ninetales():
    r = validate_moveset_redundancy(
        "Ninetales-Alola",
        ["auroraveil", "raindance", "moonblast", "protect"],
        ability="Snow Warning",
    )
    assert r.seeming is True
    assert r.justified is True
    assert r.pattern == "A-precondition"


def test_redundancy_a_team():
    teammate = Slot(species=Attr(value="Pelipper", locked=True))
    self_slot = Slot(species=Attr(value="Ninetales-Alola", locked=True))
    r = validate_moveset_redundancy(
        "Ninetales-Alola",
        ["raindance", "moonblast", "protect", "dazzlinggleam"],
        ability="Snow Warning",
        team_draft=[self_slot, teammate],
    )
    assert r.seeming is True
    assert r.justified is True
    assert r.pattern == "A-team"


def test_redundancy_pattern_b_charizard_y():
    r = validate_moveset_redundancy(
        "Froslass-Mega",
        ["raindance", "shadowball", "protect", "willowisp"],
        ability="Snow Warning",
        threats=[{"species": "Charizard-Mega-Y", "ability": "Drought"}],
    )
    assert r.seeming is True
    assert r.justified is True
    assert r.pattern == "B"


def test_redundancy_pelipper_rain_dance_fails():
    r = validate_moveset_redundancy(
        "Pelipper",
        ["raindance", "hurricane", "protect", "tailwind"],
        ability="Drizzle",
    )
    assert r.seeming is True
    assert r.justified is False
    assert r.ok is False


def test_pick_default_and_alternatives():
    pick = pick_default_and_alternatives(["A", "B", "C", "D"])
    assert pick["default"] == "A"
    assert pick["alternatives"] == ["B", "C"]


def test_propose_usage_miss_lands_moveset_and_default_item():
    slot = Slot(
        species=Attr(value="Whimsicott", locked=True),
        role=Attr(value="support_speed_control", locked=True),
    )
    filler = Slot(role=Attr(value="bulky_attacker"))
    state = _state(team_draft=[slot, filler, *[empty_slot() for _ in range(4)]])

    with patch("recommender.propose.featured_or_common_set", return_value=None):
        out = fill_team_draft(state)

    s = out["team_draft"][0]
    assert s.moveset.value is not None
    assert len(s.moveset.value) >= 1
    assert s.item.value == "Sitrus Berry"
    assert s.item.reason is not None
    assert s.item.reason.ref == "tier3_item_default"
    assert s.moveset.reason is not None
    assert s.moveset.reason.ref == "move_narrowing"
    assert s.moveset.reason.kind == "tier2_heuristic"


def test_kit_near_tie_prefers_verified_reinforcement():
    names = ["Alpha", "Beta"]
    commitment = {"Alpha": 50.0, "Beta": 52.0}  # within NEAR_TIE_PCT=5
    usage = {"Alpha": 5.0, "Beta": 5.0}

    def proposer(kit, move):
        if kit["species"] == "Alpha":
            return [
                ProposedInteraction(
                    kind="move_flag", claim="contact", flag="contact"
                )
            ]
        return []

    with patch("recommender.move_narrowing.learners_of", return_value=names):
        with patch(
            "recommender.move_narrowing._has_prankster", return_value=False
        ):
            with patch(
                "recommender.move_narrowing._makes_contact", return_value=True
            ):
                r = narrow_candidates_for_move(
                    "closecombat",
                    _state(),
                    small_pool=0,
                    proposer=proposer,
                    commitment_override=commitment,
                    usage_override=usage,
                )
    assert r.candidates[0] == "Alpha"
    assert r.verified_reinforcements.get("Alpha", 0) >= 1


def test_kit_false_proposal_discarded():
    assert (
        verify_kit_interaction(
            ProposedInteraction(kind="judgment", claim="vibes"),
            {"species": "Garchomp", "abilities": []},
            "earthquake",
        )
        is False
    )


def test_kit_seed_contact_flag():
    ok = verify_kit_interaction(
        ProposedInteraction(kind="move_flag", claim="tough claws", flag="contact"),
        {"species": "Charizard", "abilities": ["Tough Claws"]},
        "dragonclaw",
    )
    assert ok is True


def test_kit_seed_charge_weather():
    ok = verify_kit_interaction(
        ProposedInteraction(
            kind="move_flag", claim="solar beam", flag="charge_weather"
        ),
        {"species": "Torkoal", "abilities": ["Drought"]},
        "solarbeam",
    )
    assert ok is True


def test_kit_seed_ability_non_quantitative():
    ok = verify_kit_interaction(
        ProposedInteraction(
            kind="ability",
            claim="adaptability",
            ability="Adaptability",
            quantitative=False,
        ),
        {"species": "Crawdaunt", "abilities": ["Adaptability"]},
        "crabhammer",
    )
    assert ok is True


def test_kit_seed_ability_missing_fails():
    ok = verify_kit_interaction(
        ProposedInteraction(
            kind="ability",
            claim="fake",
            ability="Huge Power",
            quantitative=False,
        ),
        {"species": "Garchomp", "abilities": ["Rough Skin"]},
        "earthquake",
    )
    assert ok is False


def test_kit_seed_contrary_ability_present():
    # Serperior has Contrary in some formats — check snapshot; if absent, skip soft.
    from recommender.legality import load_snapshot, species_can_have_ability

    snap = load_snapshot()
    if not species_can_have_ability(snap, "Serperior", "Contrary"):
        return
    ok = verify_kit_interaction(
        ProposedInteraction(
            kind="ability", claim="contrary", ability="Contrary", quantitative=False
        ),
        {"species": "Serperior", "abilities": ["Contrary"]},
        "leafstorm",
    )
    assert ok is True


def test_assemble_pads_protect():
    slot = Slot(
        species=Attr(value="Whimsicott", locked=True),
        role=Attr(value="support_speed_control", locked=True),
    )
    moves = assemble_moveset_fallback("Whimsicott", slot, _state(team_draft=[slot]))
    assert any(m.lower().replace(" ", "") == "protect" or m == "protect" for m in moves)
    assert len(moves) <= 4


def test_assemble_preserves_pref_order_and_reserves_protect():
    """Role-defining prefs beat alphabetical tiebreak; Protect stays when legal."""
    slot = Slot(
        species=Attr(value="Hatterene", locked=True),
        role=Attr(value="trick_room_setter", locked=True),
    )
    with patch(
        "recommender.move_narrowing._commitment_pct",
        return_value=None,
    ):
        moves = assemble_moveset_fallback(
            "Hatterene",
            slot,
            _state(team_draft=[slot]),
        )
    assert len(moves) == 4
    assert to_id(moves[0]) == "trickroom"
    assert to_id(moves[-1]) == "protect"


def test_assemble_reserves_protect_after_redundancy_rebuild():
    """Post-redundancy `_with_protect` path: real drop, Protect still reserved.

    Whimsicott support_speed_control naturally yields seeming redundancy that
    drops Tailwind (not Protect). Spy the real validator so we prove the
    rebuild branch ran — do not stub its return value.
    """
    slot = Slot(
        species=Attr(value="Whimsicott", locked=True),
        role=Attr(value="support_speed_control", locked=True),
    )
    state = _state(team_draft=[slot])
    captured: list = []

    real = validate_moveset_redundancy

    def _spy(species, moves, **kwargs):
        result = real(species, moves, **kwargs)
        captured.append(result)
        return result

    with patch(
        "recommender.move_narrowing.validate_moveset_redundancy",
        side_effect=_spy,
    ):
        moves = assemble_moveset_fallback("Whimsicott", slot, state)

    assert len(captured) == 1
    red = captured[0]
    assert red.seeming is True
    assert red.justified is False
    assert red.drop_moves
    assert all(to_id(m) != "protect" for m in red.drop_moves)
    assert "protect" in {to_id(m) for m in moves}
    assert len(moves) <= 4


def test_chilly_reception_weather_maps():
    assert _WEATHER_MANUAL["chillyreception"] == "Snow"
    assert _ARCHETYPE_PREF_MOVES["Snow"] == ["snowscape", "chillyreception"]
