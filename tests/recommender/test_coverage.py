"""Tests for team threat-coverage and SPOF (ADR-015 gaps #7/#8)."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from langgraph.checkpoint.memory import MemorySaver

from recommender.calc_client import CalcClient, CalcRequest
from recommender.coverage import (
    ABILITY_TO_FIELD,
    _slot_to_spec,
    compute_team_coverage,
    detect_spof,
    get_relevant_threats,
)
from recommender.contingent_value import TERRAIN_SETTERS, WEATHER_SETTERS
from recommender.graph import compile_graph
from recommender.ids import to_id
from recommender.legality import classify_item_failure, load_snapshot
from recommender.matchup import clear_matchup_memo
from recommender.state import (
    Attr,
    Slot,
    TeamReviewResult,
    ThreatCandidate,
    empty_slot,
)


@pytest.fixture(autouse=True)
def _clear_matchup_memo():
    clear_matchup_memo()
    yield
    clear_matchup_memo()

# --- calc mocks (mirrors test_matchup.py) ---


def _calc(
    *,
    ko_chance: str = "100% OHKO",
    damage_range: list[int] | None = None,
    attacker_spe: int = 100,
    defender_hp: int = 100,
    attacker_hp: int = 100,
    kochance_n: int = 1,
    kochance_chance: float = 1.0,
) -> dict[str, Any]:
    dmg = damage_range or [defender_hp, defender_hp]
    return {
        "damageRange": dmg,
        "koChance": ko_chance,
        "raw": {
            "damage": dmg,
            "range": dmg,
            "kochance": {"chance": kochance_chance, "n": kochance_n, "text": ko_chance},
            "stats": {
                "attacker": {"spe": attacker_spe, "hp": attacker_hp},
                "defender": {"hp": defender_hp},
            },
        },
    }


class MockCalcClient(CalcClient):
    def __init__(self, responses: dict[tuple[str, str, str], dict[str, Any]]) -> None:
        super().__init__("http://mock")
        self._responses = responses

    def calculate_batch(self, requests: list[CalcRequest]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for req in requests:
            key = (
                req["attacker"]["species"],
                req["defender"]["species"],
                req["move"],
            )
            if key not in self._responses:
                raise KeyError(f"unexpected calc request: {key}")
            out.append(self._responses[key])
        return out


class DualFieldMock(CalcClient):
    """Neutral vs weather responses keyed like MockCalcClient."""

    def __init__(
        self,
        neutral: dict[tuple[str, str, str], dict[str, Any]],
        with_field: dict[tuple[str, str, str], dict[str, Any]],
    ) -> None:
        super().__init__("http://mock")
        self._neutral = neutral
        self._with_field = with_field

    def calculate_batch(self, requests: list[CalcRequest]) -> list[dict[str, Any]]:
        table = self._with_field if requests and requests[0].get("field") else self._neutral
        out: list[dict[str, Any]] = []
        for req in requests:
            key = (
                req["attacker"]["species"],
                req["defender"]["species"],
                req["move"],
            )
            out.append(table[key])
        return out


GARCHOMP = {
    "species": "Garchomp",
    "item": "Life Orb",
    "ability": "Rough Skin",
    "moves": ["Earthquake", "Dragon Claw", "Protect"],
    "evs": {"hp": 0, "atk": 32, "spe": 32},
}
KINGAMBIT = {
    "species": "Kingambit",
    "item": "Black Glasses",
    "ability": "Defiant",
    "moves": ["Sucker Punch", "Kowtow Cleave", "Protect"],
    "evs": {"hp": 32, "atk": 32, "spe": 0},
}
SWAMPERT = {
    "species": "Swampert",
    "item": "Swampertite",
    "ability": "Swift Swim",
    "moves": ["Wave Crash", "Earthquake", "Protect"],
    "evs": {"hp": 2, "atk": 32, "spe": 32},
}
CHARIZARD = {
    "species": "Charizard",
    "item": "Charizardite Y",
    "ability": "Drought",
    "moves": ["Heat Wave", "Solar Beam", "Protect"],
    "evs": {"hp": 0, "spa": 32, "spe": 32},
}
PELIPPER = {
    "species": "Pelipper",
    "item": "Damp Rock",
    "ability": "Drizzle",
    "moves": ["Hurricane", "Protect", "Tailwind", "Helping Hand"],
    "evs": {"hp": 32, "spa": 16, "spe": 0},
}


def _slot(spec: dict[str, Any], *, locked: bool = False) -> Slot:
    return Slot(
        species=Attr(value=spec["species"], locked=locked),
        ability=Attr(value=spec.get("ability")),
        item=Attr(value=spec.get("item")),
        moveset=Attr(value=list(spec.get("moves") or [])),
        spread=Attr(value=dict(spec.get("evs") or {})),
    )


def _patch_specs(mapping: dict[str, dict[str, Any]]):
    def _fn(slot: Slot, *, regulation: str = "champions"):
        if not slot.species.value:
            return None
        return dict(mapping[slot.species.value])

    return patch("recommender.coverage._slot_to_spec", side_effect=_fn)


def test_slot_to_spec_prefers_persisted_ability_over_usage():
    slot = Slot(
        species=Attr(value="Pelipper", locked=True),
        ability=Attr(value="Keen Eye", locked=True),
    )
    with patch(
        "recommender.coverage.featured_or_common_set",
        return_value={"ability": "Drizzle"},
    ):
        assert _slot_to_spec(slot)["ability"] == "Keen Eye"  # type: ignore[index]


_CHOMP_VS_KING = {
    ("Garchomp", "Kingambit", "Earthquake"): _calc(
        ko_chance="100% OHKO",
        attacker_spe=130,
        defender_hp=170,
    ),
    ("Garchomp", "Kingambit", "Dragon Claw"): _calc(
        ko_chance="100% 2HKO",
        damage_range=[90, 95],
        attacker_spe=130,
        defender_hp=170,
        kochance_n=2,
    ),
    ("Kingambit", "Garchomp", "Sucker Punch"): _calc(
        ko_chance="100% 2HKO",
        damage_range=[80, 90],
        attacker_spe=50,
        defender_hp=183,
        kochance_n=2,
    ),
    ("Kingambit", "Garchomp", "Kowtow Cleave"): _calc(
        ko_chance="100% 2HKO",
        damage_range=[75, 85],
        attacker_spe=50,
        defender_hp=183,
        kochance_n=2,
    ),
}

_NO_ANSWER_CHOMP_KING = {
    ("Garchomp", "Kingambit", "Earthquake"): _calc(
        ko_chance="100% 2HKO",
        damage_range=[90, 95],
        attacker_spe=130,
        defender_hp=170,
        kochance_n=2,
    ),
    ("Garchomp", "Kingambit", "Dragon Claw"): _calc(
        ko_chance="100% 3HKO",
        damage_range=[55, 60],
        attacker_spe=130,
        defender_hp=170,
        kochance_n=3,
    ),
    ("Kingambit", "Garchomp", "Sucker Punch"): _calc(
        ko_chance="100% OHKO",
        attacker_spe=150,
        defender_hp=183,
    ),
    ("Kingambit", "Garchomp", "Kowtow Cleave"): _calc(
        ko_chance="100% OHKO",
        attacker_spe=150,
        defender_hp=183,
    ),
}


def test_get_relevant_threats_bounded():
    threats = get_relevant_threats({"regulation_mod": "champions"}, n=3)  # type: ignore[arg-type]
    ladder = {t.ladder_species for t in threats}
    assert len(ladder) <= 3
    assert all(isinstance(t, ThreatCandidate) for t in threats)
    assert all("species" in t.spec for t in threats)


def test_single_slot_cover_and_genuine_spof():
    draft = [_slot(GARCHOMP), empty_slot()]
    threat = KINGAMBIT
    client = MockCalcClient(_CHOMP_VS_KING)

    with _patch_specs({"Garchomp": GARCHOMP}):
        coverage = compute_team_coverage(draft, [threat], client=client)
        spofs = detect_spof(draft, [threat], client=client)

    assert len(coverage) == 1
    assert coverage[0].best_outcome.outcome == "clean_kill"
    assert coverage[0].covering_slot_indices == [0]
    assert coverage[0].forced_field is None
    assert coverage[0].flagged is False

    assert len(spofs) == 1
    assert spofs[0].slot_index == 0
    assert spofs[0].threats_lost[0]["species"] == "Kingambit"
    assert "kingambit" in spofs[0].threat_severity
    assert not hasattr(spofs[0], "should_fix")
    assert not hasattr(spofs[0], "is_problem")


def test_two_covering_slots_no_spof():
    """Shared coverage is not a single point of failure."""
    chomp2 = {**GARCHOMP, "species": "Garchomp"}
    # Second "cover" via Incineroar-shaped calc — use another Garchomp clone name.
    # Simpler: two slots both mapped to GARCHOMP so both clean_kill Kingambit.
    draft = [_slot(GARCHOMP), _slot(GARCHOMP)]
    # Distinct species keys for _slot_to_spec mapping — reuse same build under alias.
    draft[1] = Slot(
        species=Attr(value="GarchompB"),
        item=Attr(value=GARCHOMP["item"]),
        moveset=Attr(value=list(GARCHOMP["moves"])),
        spread=Attr(value=dict(GARCHOMP["evs"])),
    )
    alias = {**GARCHOMP, "species": "GarchompB"}
    responses = {
        **_CHOMP_VS_KING,
        ("GarchompB", "Kingambit", "Earthquake"): _CHOMP_VS_KING[
            ("Garchomp", "Kingambit", "Earthquake")
        ],
        ("GarchompB", "Kingambit", "Dragon Claw"): _CHOMP_VS_KING[
            ("Garchomp", "Kingambit", "Dragon Claw")
        ],
        ("Kingambit", "GarchompB", "Sucker Punch"): _CHOMP_VS_KING[
            ("Kingambit", "Garchomp", "Sucker Punch")
        ],
        ("Kingambit", "GarchompB", "Kowtow Cleave"): _CHOMP_VS_KING[
            ("Kingambit", "Garchomp", "Kowtow Cleave")
        ],
    }
    client = MockCalcClient(responses)

    with _patch_specs({"Garchomp": GARCHOMP, "GarchompB": alias}):
        coverage = compute_team_coverage(draft, [KINGAMBIT], client=client)
        spofs = detect_spof(draft, [KINGAMBIT], client=client)

    assert coverage[0].covering_slot_indices == [0, 1]
    assert spofs == []


def test_field_conditional_coverage():
    """Threat only covered once locked Drizzle forces Rain."""
    draft = [
        _slot(PELIPPER, locked=True),
        _slot(SWAMPERT),
    ]
    threat = CHARIZARD

    neutral = {
        ("Pelipper", "Charizard", "Hurricane"): _calc(
            ko_chance="100% 3HKO",
            damage_range=[50, 55],
            attacker_spe=80,
            defender_hp=180,
            kochance_n=3,
        ),
        ("Charizard", "Pelipper", "Heat Wave"): _calc(
            ko_chance="100% OHKO",
            attacker_spe=140,
            defender_hp=160,
        ),
        ("Charizard", "Pelipper", "Solar Beam"): _calc(
            ko_chance="100% OHKO",
            attacker_spe=140,
            defender_hp=160,
        ),
        ("Swampert", "Charizard", "Wave Crash"): _calc(
            ko_chance="100% 2HKO",
            damage_range=[90, 100],
            attacker_spe=120,
            defender_hp=180,
            kochance_n=2,
        ),
        ("Swampert", "Charizard", "Earthquake"): _calc(
            ko_chance="100% 3HKO",
            damage_range=[55, 60],
            attacker_spe=120,
            defender_hp=180,
            kochance_n=3,
        ),
        ("Charizard", "Swampert", "Heat Wave"): _calc(
            ko_chance="100% OHKO",
            attacker_spe=140,
            defender_hp=190,
        ),
        ("Charizard", "Swampert", "Solar Beam"): _calc(
            ko_chance="100% OHKO",
            attacker_spe=140,
            defender_hp=190,
        ),
    }
    rain = {
        ("Pelipper", "Charizard", "Hurricane"): neutral[
            ("Pelipper", "Charizard", "Hurricane")
        ],
        ("Charizard", "Pelipper", "Heat Wave"): _calc(
            ko_chance="100% 2HKO",
            damage_range=[70, 80],
            attacker_spe=140,
            defender_hp=160,
            kochance_n=2,
        ),
        ("Charizard", "Pelipper", "Solar Beam"): _calc(
            ko_chance="100% 2HKO",
            damage_range=[65, 75],
            attacker_spe=140,
            defender_hp=160,
            kochance_n=2,
        ),
        ("Swampert", "Charizard", "Wave Crash"): _calc(
            ko_chance="100% OHKO",
            damage_range=[190, 200],
            attacker_spe=220,
            defender_hp=180,
        ),
        ("Swampert", "Charizard", "Earthquake"): _calc(
            ko_chance="100% 2HKO",
            damage_range=[80, 90],
            attacker_spe=220,
            defender_hp=180,
            kochance_n=2,
        ),
        ("Charizard", "Swampert", "Heat Wave"): _calc(
            ko_chance="100% 2HKO",
            damage_range=[70, 80],
            attacker_spe=140,
            defender_hp=190,
            kochance_n=2,
        ),
        ("Charizard", "Swampert", "Solar Beam"): _calc(
            ko_chance="100% 2HKO",
            damage_range=[65, 75],
            attacker_spe=140,
            defender_hp=190,
            kochance_n=2,
        ),
    }
    client = DualFieldMock(neutral, rain)

    from recommender.state import Attr
    from recommender.team_candidates import collect_locked_anchor_contexts

    # collect_locked_anchor_contexts resolves through real species/learnset
    # data (not this file's _patch_specs mock, which only covers
    # compute_team_coverage's own matchup calls) -- needs every Attr
    # locked, unlike this file's lighter-weight _slot helper.
    fully_locked_pelipper = Slot(
        role=Attr(value="rain_setter", locked=True),
        species=Attr(value=PELIPPER["species"], locked=True),
        ability=Attr(value=PELIPPER["ability"], locked=True),
        item=Attr(value=PELIPPER["item"], locked=True),
        moveset=Attr(value=list(PELIPPER["moves"]), locked=True),
        spread=Attr(value=dict(PELIPPER["evs"]), locked=True),
        nature=Attr(value="Modest", locked=True),
    )
    locked_contexts = collect_locked_anchor_contexts(
        {"team_draft": [fully_locked_pelipper], "regulation_mod": "champions"}
    )

    with _patch_specs({"Pelipper": PELIPPER, "Swampert": SWAMPERT}):
        coverage = compute_team_coverage(
            draft, [threat], client=client, locked_contexts=locked_contexts
        )

    assert coverage[0].best_outcome.outcome == "conditionally_dependent_answer"
    assert coverage[0].forced_field is not None
    assert coverage[0].forced_field.get("weather") == "Rain"
    assert coverage[0].flagged is True
    assert 1 in coverage[0].covering_slot_indices


def test_zero_slot_gap_not_spof():
    draft = [_slot(GARCHOMP)]
    client = MockCalcClient(_NO_ANSWER_CHOMP_KING)

    with _patch_specs({"Garchomp": GARCHOMP}):
        coverage = compute_team_coverage(draft, [KINGAMBIT], client=client)
        spofs = detect_spof(draft, [KINGAMBIT], client=client)

    assert coverage[0].best_outcome.outcome == "no_answer"
    assert coverage[0].covering_slot_indices == []
    assert coverage[0].flagged is False
    assert spofs == []


def test_team_review_intent_graph_smoke():
    graph = compile_graph(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "team-review-smoke"}}
    graph.invoke({"format_id": "[Gen 9 Champions] VGC 2026 Reg M-B"}, config=cfg)

    stub = ThreatCandidate(
        ladder_species="Kingambit",
        usage_rank=3,
        form="Kingambit",
        showdown_usage_pct=None,
        showdown_formes=(),
        spec=KINGAMBIT,
        build_source="ingame",
    )
    with (
        patch(
            "recommender.nodes.classify_pending",
            return_value={"turn_intent": "team_review"},
        ),
        patch("recommender.nodes.get_relevant_threats", return_value=[stub]),
        patch("recommender.nodes.compute_team_coverage", return_value=[]),
        patch("recommender.nodes.detect_spof", return_value=[]),
    ):
        result = graph.invoke({"pending_input": "review my team"}, config=cfg)

    assert result["turn_intent"] == "team_review"
    assert result["last_team_review"] is not None
    assert isinstance(result["last_team_review"], TeamReviewResult)
    assert result["last_team_review"].threats == [stub]
    assert result["last_team_review"].coverage == []
    assert result["last_team_review"].spofs == []


def test_empty_threats_returns_empty():
    assert compute_team_coverage([_slot(GARCHOMP)], [], client=MockCalcClient({})) == []
    assert detect_spof([_slot(GARCHOMP)], [], client=MockCalcClient({})) == []


def test_hadron_orichalcum_in_ability_to_field():
    assert ABILITY_TO_FIELD["hadronengine"] == {
        "terrain": "Electric",
        "gameType": "Doubles",
    }
    assert ABILITY_TO_FIELD["orichalcumpulse"] == {
        "weather": "Sun",
        "gameType": "Doubles",
    }
    assert "hadronengine" in TERRAIN_SETTERS
    assert "orichalcumpulse" in WEATHER_SETTERS


def test_primal_weather_in_ability_to_field():
    assert ABILITY_TO_FIELD["desolateland"] == {
        "weather": "Harsh Sunshine",
        "gameType": "Doubles",
    }
    assert ABILITY_TO_FIELD["primordialsea"] == {
        "weather": "Heavy Rain",
        "gameType": "Doubles",
    }
    assert ABILITY_TO_FIELD["deltastream"] == {
        "weather": "Strong Winds",
        "gameType": "Doubles",
    }
    assert "desolateland" in WEATHER_SETTERS
    assert "primordialsea" in WEATHER_SETTERS
    assert "deltastream" in WEATHER_SETTERS


def test_silkscarf_type_locked_severity():
    snap = load_snapshot()
    assert classify_item_failure("Silk Scarf", [], snap) == "type_locked_swap"


# --- bench-slot coverage-subset tests ---


def _dummy_locked_context(slot_index: int, alias: str) -> "LockedAnchorContext":
    """Minimal-but-real LockedAnchorContext for slot_index tracking in
    candidate_improves_best_bring tests -- reuses Garchomp's real,
    resolved build/role_decision (renamed via replace, not a hand-rolled
    fake) since neither provides any weather/mega mechanism, matching
    this test's actual no-field-dependency scenario. resolved_build/
    role_decision here only feed team_field_states (weather forcing);
    the real matchup calc data comes entirely from the scripted
    MockCalcClient responses via _patch_specs, independent of this.
    """
    from dataclasses import replace as _replace

    from recommender.anchor_roles import classify_anchor_role, resolve_anchor_build
    from recommender.slot_fill import LockedAnchorContext
    from recommender.support_needs import RoleShapeContext

    build = _replace(resolve_anchor_build("Garchomp"), species=alias)
    decision = classify_anchor_role(build)
    return LockedAnchorContext(
        slot_index=slot_index,
        anchor_id=to_id(alias),
        pokemon={"species": alias},
        resolved_build=build,
        role_decision=decision,
        role_shape_context=RoleShapeContext(),
        support_needs=(),
    )


def _cloned_garchomp(alias: str) -> tuple[Slot, dict[str, Any]]:
    """A species-aliased clone of GARCHOMP -- same real build/moves under
    a distinct name, so it can be scripted with independent calc responses
    the way test_two_covering_slots_no_spof already does.
    """
    spec = {**GARCHOMP, "species": alias}
    return _slot(spec), spec


def _losing_responses(alias: str) -> dict[tuple[str, str, str], dict[str, Any]]:
    """alias loses to Kingambit -- reuses _NO_ANSWER_CHOMP_KING's real
    scripted outcome under the alias's own species name.
    """
    return {
        (alias, "Kingambit", "Earthquake"): _NO_ANSWER_CHOMP_KING[
            ("Garchomp", "Kingambit", "Earthquake")
        ],
        (alias, "Kingambit", "Dragon Claw"): _NO_ANSWER_CHOMP_KING[
            ("Garchomp", "Kingambit", "Dragon Claw")
        ],
        ("Kingambit", alias, "Sucker Punch"): _NO_ANSWER_CHOMP_KING[
            ("Kingambit", "Garchomp", "Sucker Punch")
        ],
        ("Kingambit", alias, "Kowtow Cleave"): _NO_ANSWER_CHOMP_KING[
            ("Kingambit", "Garchomp", "Kowtow Cleave")
        ],
    }


def _winning_responses(alias: str) -> dict[tuple[str, str, str], dict[str, Any]]:
    """alias beats Kingambit -- reuses _CHOMP_VS_KING's real scripted
    outcome under the alias's own species name.
    """
    return {
        (alias, "Kingambit", "Earthquake"): _CHOMP_VS_KING[
            ("Garchomp", "Kingambit", "Earthquake")
        ],
        (alias, "Kingambit", "Dragon Claw"): _CHOMP_VS_KING[
            ("Garchomp", "Kingambit", "Dragon Claw")
        ],
        ("Kingambit", alias, "Sucker Punch"): _CHOMP_VS_KING[
            ("Kingambit", "Garchomp", "Sucker Punch")
        ],
        ("Kingambit", alias, "Kowtow Cleave"): _CHOMP_VS_KING[
            ("Kingambit", "Garchomp", "Kowtow Cleave")
        ],
    }


def test_candidate_improves_best_bring_when_it_covers_a_real_gap():
    """4 locked slots (A, B, C, D) all genuinely lose to the one real
    threat (Kingambit) -- the best achievable bring-4 from the locked
    roster alone leaves it uncovered. A 5th candidate (E) genuinely beats
    Kingambit. Once E is available, the best 4-of-5 combination (drop any
    one of A/B/C/D, keep E) covers it -- E has real bench value, the
    exact "does this candidate improve the best real bring" question
    Category A should be asking for slots beyond the core, confirmed
    live (2026-08-21) it currently doesn't ask at all.
    """
    from recommender.coverage import candidate_improves_best_bring

    aliases = ["ChompA", "ChompB", "ChompC", "ChompD"]
    candidate_alias = "ChompE"
    slots = [_slot({**GARCHOMP, "species": a}) for a in aliases]
    candidate_slot = _slot({**GARCHOMP, "species": candidate_alias})
    draft = [*slots, candidate_slot]

    responses: dict[tuple[str, str, str], dict[str, Any]] = {}
    for a in aliases:
        responses.update(_losing_responses(a))
    responses.update(_winning_responses(candidate_alias))
    client = MockCalcClient(responses)

    spec_map = {a: {**GARCHOMP, "species": a} for a in aliases}
    spec_map[candidate_alias] = {**GARCHOMP, "species": candidate_alias}
    spec_map["Kingambit"] = KINGAMBIT

    locked_contexts = [_dummy_locked_context(i, a) for i, a in enumerate(aliases)]
    with _patch_specs(spec_map):
        improves = candidate_improves_best_bring(
            draft,
            locked_contexts=locked_contexts,
            candidate_slot_index=4,
            pick_count=4,
            threats=[KINGAMBIT],
            client=client,
        )
    assert improves is True


def test_candidate_does_not_improve_best_bring_when_gap_already_closed():
    """Sibling of the test above: if the locked roster's best bring-4
    already covers the threat via TWO real answers (not a SPOF), adding a
    candidate that also beats it can't improve on an already-optimal
    (0 uncovered, 0 spof) outcome -- confirms this isn't just "always True
    once the candidate is strong," it's genuinely comparative. (A single
    existing answer, by contrast, IS a real SPOF, and a candidate closing
    that SPOF is genuine improvement -- confirmed as a separate, correct
    case, not the scenario this test is about.)
    """
    from recommender.coverage import candidate_improves_best_bring

    aliases = ["ChompA", "ChompB", "ChompC", "ChompD"]
    candidate_alias = "ChompE"
    slots = [_slot({**GARCHOMP, "species": a}) for a in aliases]
    candidate_slot = _slot({**GARCHOMP, "species": candidate_alias})
    draft = [*slots, candidate_slot]

    responses: dict[tuple[str, str, str], dict[str, Any]] = {}
    # ChompA and ChompB already win -- two real answers, not a SPOF,
    # unlike the sibling test where only one locked member covers it.
    responses.update(_winning_responses("ChompA"))
    responses.update(_winning_responses("ChompB"))
    for a in aliases[2:]:
        responses.update(_losing_responses(a))
    responses.update(_winning_responses(candidate_alias))
    client = MockCalcClient(responses)

    spec_map = {a: {**GARCHOMP, "species": a} for a in aliases}
    spec_map[candidate_alias] = {**GARCHOMP, "species": candidate_alias}
    spec_map["Kingambit"] = KINGAMBIT

    locked_contexts = [_dummy_locked_context(i, a) for i, a in enumerate(aliases)]
    with _patch_specs(spec_map):
        improves = candidate_improves_best_bring(
            draft,
            locked_contexts=locked_contexts,
            candidate_slot_index=4,
            pick_count=4,
            threats=[KINGAMBIT],
            client=client,
        )
    assert improves is False


def test_candidate_improves_best_bring_returns_false_before_a_real_baseline_exists():
    """With fewer than pick_count locked slots, there's no real "best
    bring" to compare against yet -- must not fabricate a baseline or
    raise, just decline to judge.
    """
    from recommender.coverage import candidate_improves_best_bring

    slots = [_slot(GARCHOMP)]
    candidate_slot = _slot({**GARCHOMP, "species": "ChompE"})
    draft = [*slots, candidate_slot]

    locked_contexts = [_dummy_locked_context(0, "Garchomp")]
    with _patch_specs({"Garchomp": GARCHOMP, "ChompE": {**GARCHOMP, "species": "ChompE"}}):
        improves = candidate_improves_best_bring(
            draft,
            locked_contexts=locked_contexts,
            candidate_slot_index=1,
            pick_count=4,
            threats=[KINGAMBIT],
            client=MockCalcClient({}),
        )
    assert improves is False
