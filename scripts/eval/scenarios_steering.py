"""Multi-turn steering correctness scenarios (state-machine contract checks)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from unittest.mock import patch

from scripts.eval.harness import (
    ScenarioResult,
    seed_state,
    start_graph_sqlite,
    turn,
)
from recommender.state import (
    Attr,
    MatchupResult,
    PendingSlotIntent,
    ProvisionalSlot,
    ReasonRef,
    Slot,
    TargetRoleDecision,
    ThreatCandidate,
    ThreatCounterCandidate,
    empty_slot,
)
from recommender.team_candidates import merge_multi_locked_candidates
from recommender.threat_counters import aggregate_verified


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    path: str
    doc: str
    run: Callable[[Any, dict, dict], ScenarioResult]


class TurnAssertError(AssertionError):
    """Assertion failure that already includes turn/scenario context."""


def attr_snap(slot: Slot, name: str) -> tuple[Any, bool]:
    a = getattr(slot, name)
    return (a.value, a.locked)


def _fmt(obj: Any) -> str:
    return repr(obj)


def assert_state(
    state: dict[str, Any],
    *,
    turn_i: int,
    scenario_id: str,
    team: dict[tuple[int, str], tuple[Any, bool]] | None = None,
    rejected_species: set[str] | None = None,
    superseded: list[dict[str, Any]] | None = None,
    pending_flag_kinds: set[str] | None = None,
    turn_intent: str | None = None,
    pending_is_none: bool | None = None,
    provisional_is_none: bool | None = None,
) -> None:
    diffs: list[str] = []
    if team is not None:
        draft = state.get("team_draft") or []
        for (idx, name), expected in team.items():
            if idx >= len(draft):
                diffs.append(f"team[{idx}].{name}: missing slot")
                continue
            actual = attr_snap(draft[idx], name)
            if actual != expected:
                diffs.append(
                    f"team[{idx}].{name}: expected {_fmt(expected)}, got {_fmt(actual)}"
                )
    if rejected_species is not None:
        got = {str(r.get("species") or "") for r in (state.get("rejected") or [])}
        if got != rejected_species:
            diffs.append(
                f"rejected species: expected {_fmt(rejected_species)}, got {_fmt(got)}"
            )
    if superseded is not None:
        got = state.get("superseded") or []
        if len(got) != len(superseded):
            diffs.append(
                f"superseded len: expected {len(superseded)}, got {len(got)} ({_fmt(got)})"
            )
        else:
            for i, (exp, act) in enumerate(zip(superseded, got)):
                for key, val in exp.items():
                    if act.get(key) != val:
                        diffs.append(
                            f"superseded[{i}].{key}: expected {_fmt(val)}, got {_fmt(act.get(key))}"
                        )
    if pending_flag_kinds is not None:
        got = {f.get("flag_kind") for f in (state.get("pending_flags") or [])}
        if got != pending_flag_kinds:
            diffs.append(
                f"pending_flag kinds: expected {_fmt(pending_flag_kinds)}, got {_fmt(got)}"
            )
    if turn_intent is not None and state.get("turn_intent") != turn_intent:
        diffs.append(
            f"turn_intent: expected {_fmt(turn_intent)}, got {_fmt(state.get('turn_intent'))}"
        )
    if pending_is_none is True and state.get("pending_presentation") is not None:
        diffs.append("pending_presentation: expected None")
    if pending_is_none is False and state.get("pending_presentation") is None:
        diffs.append("pending_presentation: expected set, got None")
    if provisional_is_none is True and state.get("provisional_slot") is not None:
        diffs.append("provisional_slot: expected None")
    if provisional_is_none is False and state.get("provisional_slot") is None:
        diffs.append("provisional_slot: expected set, got None")
    if diffs:
        raise TurnAssertError(
            f"[{scenario_id} turn {turn_i}] " + "; ".join(diffs)
        )


def _locked_slot(
    species: str,
    *,
    role: str,
    ability: str,
    item: str,
    moves: list[str],
    nature: str,
    spread: dict[str, int],
) -> Slot:
    return Slot(
        role=Attr(role, locked=True),
        species=Attr(species, locked=True),
        ability=Attr(ability, locked=True),
        item=Attr(item, locked=True),
        moveset=Attr(moves, locked=True),
        spread=Attr(spread, locked=True),
        nature=Attr(nature, locked=True),
    )


def _two_locked_anchors() -> list[Slot]:
    return [
        _locked_slot(
            "Pelipper",
            role="support_speed_control",
            ability="Drizzle",
            item="Focus Sash",
            moves=["Hurricane", "Weather Ball", "Tailwind", "Wide Guard"],
            nature="Modest",
            spread={"hp": 32, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 2},
        ),
        _locked_slot(
            "Archaludon",
            role="bulky_special_attacker",
            ability="Stamina",
            item="Leftovers",
            moves=["Electro Shot", "Flash Cannon", "Protect", "Dragon Pulse"],
            nature="Calm",
            spread={"hp": 32, "atk": 0, "def": 1, "spa": 5, "spd": 25, "spe": 3},
        ),
        empty_slot(),
        empty_slot(),
        empty_slot(),
        empty_slot(),
    ]


def _ok(scenario_id: str, path: str, state: dict[str, Any], notes: str = "") -> ScenarioResult:
    return ScenarioResult(
        scenario_id=scenario_id,
        path=path,
        terminal="ok",
        state=state,
        notes=notes,
    )


def _threat_counter(species: str) -> ThreatCounterCandidate:
    return ThreatCounterCandidate(
        candidate=ThreatCandidate(
            ladder_species=species,
            usage_rank=1,
            form=species,
            showdown_usage_pct=None,
            showdown_formes=(),
            spec={"species": species},
            build_source="test",
        ),
        threats_countered=("target",),
        threats_countered_count=1,
        verified_score=aggregate_verified(
            [MatchupResult(outcome="clean_kill", severity="costly")]
        ),
        verified_vs=(("target", MatchupResult(outcome="clean_kill", severity="costly")),),
    )


# --- scenarios -----------------------------------------------------------------


def _run_01(graph, config, state) -> ScenarioResult:
    sid = "01_lock_persists"
    state = turn(
        graph,
        config,
        {
            "turn_intent": "lock",
            "turn_payload": {
                "slot_index": 0,
                "attr": "species",
                "value": "Pelipper",
            },
        },
    )
    snap = attr_snap(state["team_draft"][0], "species")
    assert_state(
        state,
        turn_i=1,
        scenario_id=sid,
        team={(0, "species"): ("Pelipper", True)},
    )
    fillers = ["Archaludon", "Incineroar", "Amoonguss", "Farigiraf", "Gholdengo"]
    for i, species in enumerate(fillers, start=1):
        state = turn(
            graph,
            config,
            {
                "turn_intent": "lock",
                "turn_payload": {
                    "slot_index": i,
                    "attr": "species",
                    "value": species,
                },
            },
        )
        assert_state(
            state,
            turn_i=i + 1,
            scenario_id=sid,
            team={(0, "species"): snap},
        )
        if attr_snap(state["team_draft"][0], "species") != snap:
            raise TurnAssertError(
                f"[{sid} turn {i + 1}] slot0 species snap drifted: "
                f"expected {_fmt(snap)}, got {_fmt(attr_snap(state['team_draft'][0], 'species'))}"
            )
    return _ok(sid, "persistence", state)


def _run_02(graph, config, state) -> ScenarioResult:
    sid = "02_reject_lineage"
    draft = _two_locked_anchors()
    # Keep-lock target on slot 4 so blank slots 2–3 are first open for rediscovery.
    draft[4] = Slot(
        species=Attr(
            value="Incineroar",
            locked=True,
            reason=ReasonRef(kind="user_stated"),
        )
    )
    seed_state(
        graph,
        config,
        team_draft=draft,
        bootstrap_intake_complete=True,
        rejected=[],
        superseded=[],
        pending_flags=[],
        team_completion_preference="balanced",
        pending_presentation=None,
    )
    state = graph.get_state(config).values

    state = turn(
        graph,
        config,
        {
            "turn_intent": "rejection",
            "turn_payload": {
                "species": "Incineroar",
                "slot_index": 4,
                "reason": "dislike",
            },
        },
    )
    assert_state(
        state,
        turn_i=1,
        scenario_id=sid,
        team={(4, "species"): ("Incineroar", True)},
        rejected_species={"Incineroar"},
    )

    # Unrelated activity must not call apply_lock while X stays locked —
    # apply_lock clears rejected entries for any currently-locked species.
    # Use pending_response (finish → END) so we don't rediscover mid-setup.
    for i in range(2, 5):
        state = turn(graph, config, {"turn_intent": "pending_response"})
        assert_state(
            state,
            turn_i=i,
            scenario_id=sid,
            team={(4, "species"): ("Incineroar", True)},
            rejected_species={"Incineroar"},
        )

    real_merge = merge_multi_locked_candidates

    def _merge_inject(st, contexts, threat_candidates, shared, **kwargs):
        injected = (_threat_counter("Incineroar"), _threat_counter("Farigiraf"))
        return real_merge(st, contexts, injected, shared, **kwargs)

    with (
        patch(
            "recommender.team_candidates.merge_multi_locked_candidates",
            side_effect=_merge_inject,
        ),
        patch("recommender.nodes.query_shared_teammates", return_value=None),
        patch(
            "recommender.team_candidates.material_completion_preferences",
            return_value=(),
        ),
    ):
        state = turn(graph, config, {"turn_intent": "continue"})

    pending = state.get("pending_presentation") or {}
    options = pending.get("options") or []
    species = {str(o.get("species") or "") for o in options}
    if "Incineroar" in species:
        raise TurnAssertError(
            f"[{sid} turn rediscover] Incineroar still in candidates: {_fmt(species)}"
        )
    assert_state(
        state,
        turn_i=5,
        scenario_id=sid,
        team={(4, "species"): ("Incineroar", True)},
        rejected_species={"Incineroar"},
    )
    return _ok(sid, "rejection", state)


def _sibling_conflict_sequence(graph, config, state, *, sid: str, start_turn: int = 1):
    """Lock Scarf then status moveset; return (state, next_turn_index)."""
    state = turn(
        graph,
        config,
        {
            "turn_intent": "lock",
            "turn_payload": {
                "slot_index": 0,
                "attr": "item",
                "value": "Choice Scarf",
            },
        },
    )
    assert_state(
        state,
        turn_i=start_turn,
        scenario_id=sid,
        team={(0, "item"): ("Choice Scarf", True)},
    )
    state = turn(
        graph,
        config,
        {
            "turn_intent": "lock",
            "turn_payload": {
                "slot_index": 0,
                "attr": "moveset",
                "value": ["Sleep Powder", "Hurricane", "Bug Buzz", "Protect"],
            },
        },
    )
    assert_state(
        state,
        turn_i=start_turn + 1,
        scenario_id=sid,
        team={
            (0, "moveset"): (
                ["Sleep Powder", "Hurricane", "Bug Buzz", "Protect"],
                True,
            ),
            (0, "item"): (None, False),
        },
        superseded=[{"slot_index": 0, "attr": "item", "value": "Choice Scarf"}],
    )
    return state, start_turn + 2


def _run_03(graph, config, state) -> ScenarioResult:
    sid = "03_sibling_supersede"
    seed_state(
        graph,
        config,
        bootstrap_intake_complete=True,
        superseded=[],
        pending_flags=[],
        pending_presentation=None,
    )
    state, t = _sibling_conflict_sequence(graph, config, state, sid=sid)
    state = turn(
        graph,
        config,
        {
            "turn_intent": "restore",
            "turn_payload": {"slot_index": 0, "attr": "item"},
        },
    )
    assert_state(
        state,
        turn_i=t,
        scenario_id=sid,
        team={(0, "item"): ("Choice Scarf", True)},
        superseded=[],
    )
    return _ok(sid, "supersede", state)


def _run_04(graph, config, state) -> ScenarioResult:
    sid = "04_simultaneous_vivillon"
    seed_state(
        graph,
        config,
        bootstrap_intake_complete=True,
        superseded=[],
        pending_flags=[],
        pending_presentation=None,
    )
    state = turn(
        graph,
        config,
        {
            "turn_intent": "lock",
            "turn_payload": {
                "slot_index": 0,
                "locks": [
                    {"attr": "species", "value": "Vivillon"},
                    {
                        "attr": "moveset",
                        "value": [
                            "Sleep Powder",
                            "Hurricane",
                            "Bug Buzz",
                            "Protect",
                        ],
                    },
                    {"attr": "item", "value": "Choice Scarf"},
                ],
            },
        },
    )
    slot = state["team_draft"][0]
    if slot.species.value != "Vivillon" or not slot.species.locked:
        raise TurnAssertError(
            f"[{sid} turn 1] species should lock Vivillon, got {attr_snap(slot, 'species')}"
        )
    if slot.item.locked or slot.moveset.locked:
        raise TurnAssertError(
            f"[{sid} turn 1] item/moveset should stay unlocked "
            f"(item={attr_snap(slot, 'item')}, moveset={attr_snap(slot, 'moveset')})"
        )
    flags = [
        f
        for f in (state.get("pending_flags") or [])
        if f.get("flag_kind") == "simultaneous_lock_conflict"
    ]
    if len(flags) != 1:
        raise TurnAssertError(f"[{sid} turn 1] expected 1 conflict flag, got {flags}")
    conflict = set((flags[0].get("value") or {}).get("conflict") or [])
    if conflict != {"item", "moveset"}:
        raise TurnAssertError(
            f"[{sid} turn 1] conflict pair expected item+moveset, got {conflict}"
        )
    return _ok(sid, "simultaneous", state)


def _run_05(graph, config, state) -> ScenarioResult:
    sid = "05_archetype_reconcile"
    draft = [
        Slot(
            species=Attr(
                value="Charizard",
                locked=True,
                reason=ReasonRef(kind="archetype"),
            )
        ),
        Slot(
            species=Attr(
                value="Pelipper",
                locked=True,
                reason=ReasonRef(kind="user_stated"),
            )
        ),
        *[empty_slot() for _ in range(4)],
    ]
    seed_state(
        graph,
        config,
        team_draft=draft,
        bootstrap_intake_complete=True,
        superseded=[],
        pending_flags=[],
        pending_presentation=None,
    )
    state = turn(
        graph,
        config,
        {
            "turn_intent": "archetype_change",
            "turn_payload": {"components": ["Rain"]},
        },
    )
    assert_state(
        state,
        turn_i=1,
        scenario_id=sid,
        team={
            (0, "species"): (None, False),
            (1, "species"): ("Pelipper", True),
        },
        superseded=[{"slot_index": 0, "attr": "species", "value": "Charizard"}],
    )
    return _ok(sid, "archetype", state)


def _run_06(graph, config, state) -> ScenarioResult:
    sid = "06_reset_preserves_rejected"
    provisional = ProvisionalSlot(
        schema_version=1,
        slot_index=0,
        target_role_decision=TargetRoleDecision(
            role_id="rain_setter", source="user_choice"
        ),
        species="Pelipper",
        ability="Drizzle",
        item="Damp Rock",
        moves=("Hurricane", "Weather Ball", "Tailwind", "Wide Guard"),
        nature="Modest",
        spread=(("hp", 4), ("spa", 252), ("spe", 252)),
        fingerprint="fp-reset",
    )
    pending = {
        "schema_version": 1,
        "kind": "candidate_selection",
        "slot_index": 0,
        "options": [{"species": "Pelipper", "source": "need"}],
    }
    draft = list(state["team_draft"])
    draft[0] = Slot(species=Attr(value="Garchomp", locked=True))
    seed_state(
        graph,
        config,
        team_draft=draft,
        rejected=[{"species": "Tornadus", "reason": "nope", "turn": 1}],
        pending_presentation=pending,
        provisional_slot=provisional,
        pending_slot_intent=PendingSlotIntent(
            schema_version=1,
            slot_index=0,
            species="Pelipper",
            target_role_decision=TargetRoleDecision(
                role_id="rain_setter", source="user_choice"
            ),
            source="need",
        ),
        bootstrap_intake_complete=True,
    )
    state = turn(graph, config, {"turn_intent": "reset", "turn_payload": {}})
    assert_state(
        state,
        turn_i=1,
        scenario_id=sid,
        rejected_species={"Tornadus"},
        provisional_is_none=True,
    )
    if any(s.species.value is not None for s in state["team_draft"]):
        raise TurnAssertError(f"[{sid} turn 1] draft should be wiped")
    if state.get("pending_slot_intent") is not None:
        raise TurnAssertError(f"[{sid} turn 1] pending_slot_intent should clear")
    # reset_team clears pending, then route_team_phase reinstalls bootstrap_intake.
    pending = state.get("pending_presentation") or {}
    if pending.get("kind") == "candidate_selection":
        raise TurnAssertError(
            f"[{sid} turn 1] old candidate_selection pending should not survive reset"
        )
    return _ok(sid, "reset", state)


def _run_07(graph, config, state) -> ScenarioResult:
    sid = "07_restore_one_level"
    seed_state(
        graph,
        config,
        bootstrap_intake_complete=True,
        superseded=[],
        pending_flags=[],
        pending_presentation=None,
    )
    state, t = _sibling_conflict_sequence(graph, config, state, sid=sid)
    state = turn(
        graph,
        config,
        {
            "turn_intent": "restore",
            "turn_payload": {"slot_index": 0, "attr": "item"},
        },
    )
    assert_state(
        state,
        turn_i=t,
        scenario_id=sid,
        team={(0, "item"): ("Choice Scarf", True)},
        superseded=[],
    )
    before = attr_snap(state["team_draft"][0], "item")
    before_sup = list(state.get("superseded") or [])
    state = turn(
        graph,
        config,
        {
            "turn_intent": "restore",
            "turn_payload": {"slot_index": 0, "attr": "item"},
        },
    )
    after = attr_snap(state["team_draft"][0], "item")
    after_sup = list(state.get("superseded") or [])
    if after != before or after_sup != before_sup:
        raise TurnAssertError(
            f"[{sid} turn {t + 1}] second restore must be no-op; "
            f"item {before}->{after}, superseded {before_sup}->{after_sup}"
        )
    return _ok(sid, "restore", state)


def _run_08(graph, config, state) -> ScenarioResult:
    sid = "08_defer_pending_kinds"
    # Sub-case A: candidate_selection → deferred
    seed_state(
        graph,
        config,
        bootstrap_intake_complete=True,
        pending_presentation={
            "schema_version": 1,
            "kind": "candidate_selection",
            "slot_index": 0,
            "options": [{"species": "Pelipper", "source": "need"}],
        },
        provisional_slot=None,
    )
    state = turn(
        graph,
        config,
        {"turn_intent": "deferred", "pending_presentation": None},
    )
    assert_state(
        state,
        turn_i=1,
        scenario_id=sid,
        turn_intent="deferred",
        pending_is_none=True,
    )

    # Sub-case B: completion_preference → deferred
    seed_state(
        graph,
        config,
        pending_presentation={
            "schema_version": 2,
            "kind": "completion_preference",
            "slot_index": 0,
            "preference_options": ("attacker", "support", "balanced"),
        },
    )
    state = turn(
        graph,
        config,
        {"turn_intent": "deferred", "pending_presentation": None},
    )
    assert_state(
        state,
        turn_i=2,
        scenario_id=sid,
        turn_intent="deferred",
        pending_is_none=True,
    )

    # Sub-case C: full_build_confirmation → build_abandoned (shipped, not deferred)
    provisional = ProvisionalSlot(
        schema_version=1,
        slot_index=0,
        target_role_decision=TargetRoleDecision(
            role_id="rain_setter", source="user_choice"
        ),
        species="Pelipper",
        ability="Drizzle",
        item="Damp Rock",
        moves=("Hurricane", "Weather Ball", "Tailwind", "Wide Guard"),
        nature="Modest",
        spread=(("hp", 4), ("spa", 252), ("spe", 252)),
        fingerprint="fp-defer",
    )
    draft = _two_locked_anchors()
    seed_state(
        graph,
        config,
        team_draft=draft,
        team_completion_preference="balanced",
        pending_presentation={
            "schema_version": 1,
            "kind": "full_build_confirmation",
            "slot_index": 2,
            "options": [],
        },
        provisional_slot=provisional,
        pending_slot_intent=PendingSlotIntent(
            schema_version=1,
            slot_index=2,
            species="Pelipper",
            target_role_decision=TargetRoleDecision(
                role_id="rain_setter", source="user_choice"
            ),
            source="need",
        ),
    )
    with (
        patch("recommender.nodes.query_shared_teammates", return_value=None),
        patch(
            "recommender.team_candidates.material_completion_preferences",
            return_value=(),
        ),
    ):
        state = turn(
            graph,
            config,
            {
                "turn_intent": "build_abandoned",
                "pending_presentation": None,
                "pending_slot_intent": None,
                "provisional_slot": None,
                "provisional_refinement": None,
                "compare_analysis": None,
            },
        )
    assert_state(
        state,
        turn_i=3,
        scenario_id=sid,
        turn_intent="build_abandoned",
        provisional_is_none=True,
    )
    if state.get("pending_slot_intent") is not None:
        raise TurnAssertError(f"[{sid} turn 3] pending_slot_intent should clear")
    return _ok(sid, "defer", state)


def _run_09(graph, config, state) -> ScenarioResult:
    sid = "09_nonconflict_constraint"
    state = turn(
        graph,
        config,
        {
            "turn_intent": "lock",
            "turn_payload": {
                "slot_index": 0,
                "attr": "species",
                "value": "Pelipper",
            },
        },
    )
    snap = attr_snap(state["team_draft"][0], "species")
    assert_state(
        state,
        turn_i=1,
        scenario_id=sid,
        team={(0, "species"): snap},
    )
    state = turn(
        graph,
        config,
        {
            "turn_intent": "constraint",
            "turn_payload": {
                "type": "hard",
                "predicate": "no duplicate items",
                "scope": "team_wide",
                "groundedness": "mechanically-checkable",
            },
        },
    )
    assert_state(
        state,
        turn_i=2,
        scenario_id=sid,
        team={(0, "species"): snap},
    )
    if len(state.get("constraints") or []) != 1:
        raise TurnAssertError(f"[{sid} turn 2] expected one constraint recorded")
    return _ok(
        sid,
        "constraint_negative",
        state,
        notes="vacuous vs ADR-020: constraint turn does not reconcile locks",
    )


def _run_11(graph, config, state) -> ScenarioResult:
    sid = "11_idle_persist"
    state = turn(
        graph,
        config,
        {
            "turn_intent": "lock",
            "turn_payload": {
                "slot_index": 0,
                "attr": "species",
                "value": "Pelipper",
            },
        },
    )
    snap = attr_snap(state["team_draft"][0], "species")
    assert_state(
        state,
        turn_i=1,
        scenario_id=sid,
        team={(0, "species"): snap},
    )
    for i in range(2, 6):
        state = turn(graph, config, {"turn_intent": "continue"})
        assert_state(
            state,
            turn_i=i,
            scenario_id=sid,
            team={(0, "species"): snap},
        )
    # Reference turn: lock another attr while asserting original snap.
    state = turn(
        graph,
        config,
        {
            "turn_intent": "lock",
            "turn_payload": {
                "slot_index": 0,
                "attr": "ability",
                "value": "Drizzle",
            },
        },
    )
    assert_state(
        state,
        turn_i=6,
        scenario_id=sid,
        team={(0, "species"): snap, (0, "ability"): ("Drizzle", True)},
    )
    return _ok(sid, "idle", state)


def _run_12(_graph, _config, _state) -> ScenarioResult:
    """SQLite mid-contradiction resume — uses start_graph_sqlite, not MemorySaver."""
    import tempfile
    from pathlib import Path

    from recommender.checkpointer import open_sqlite_checkpointer
    from recommender.graph import compile_graph
    from scripts.eval.harness import eval_scenario_id, eval_turn_index

    sid = "12_sqlite_mid_contradiction"
    tok_sc = eval_scenario_id.set(sid)
    tok_turn = eval_turn_index.set(0)
    db = Path(tempfile.mkdtemp()) / "steer12.db"
    graph, config, state, review_patch, saver = start_graph_sqlite(
        db, thread_id=f"eval-{sid}", calc_degraded=True
    )
    try:
        seed_state(
            graph,
            config,
            bootstrap_intake_complete=True,
            superseded=[],
            pending_flags=[],
            pending_presentation=None,
        )
        state, t = _sibling_conflict_sequence(graph, config, state, sid=sid)
        pre = {
            "item": attr_snap(state["team_draft"][0], "item"),
            "moveset": attr_snap(state["team_draft"][0], "moveset"),
            "superseded": list(state.get("superseded") or []),
        }
        saver.conn.close()

        saver2 = open_sqlite_checkpointer(db)
        try:
            graph2 = compile_graph(checkpointer=saver2)
            snap = graph2.get_state(config).values
            if attr_snap(snap["team_draft"][0], "item") != pre["item"]:
                raise TurnAssertError(
                    f"[{sid} resume] item mismatch: {_fmt(pre['item'])} vs "
                    f"{_fmt(attr_snap(snap['team_draft'][0], 'item'))}"
                )
            if attr_snap(snap["team_draft"][0], "moveset") != pre["moveset"]:
                raise TurnAssertError(
                    f"[{sid} resume] moveset mismatch after reopen"
                )
            if len(snap.get("superseded") or []) != len(pre["superseded"]):
                raise TurnAssertError(
                    f"[{sid} resume] superseded len mismatch after reopen"
                )

            state = turn(
                graph2,
                config,
                {
                    "turn_intent": "restore",
                    "turn_payload": {"slot_index": 0, "attr": "item"},
                },
            )
            assert_state(
                state,
                turn_i=t,
                scenario_id=sid,
                team={(0, "item"): ("Choice Scarf", True)},
                superseded=[],
            )
            return _ok(sid, "sqlite_resume", state)
        finally:
            saver2.conn.close()
    finally:
        if review_patch is not None:
            review_patch.stop()
        eval_scenario_id.reset(tok_sc)
        eval_turn_index.reset(tok_turn)


SCENARIOS: list[Scenario] = [
    Scenario("01_lock_persists", "persistence", "Lock survives 5 unrelated fills", _run_01),
    Scenario(
        "02_reject_lineage",
        "rejection",
        "Locked reject keeps lock; rejected species filtered on rediscovery",
        _run_02,
    ),
    Scenario(
        "03_sibling_supersede",
        "supersede",
        "Conflicting sibling lock reopens prior + restorable superseded",
        _run_03,
    ),
    Scenario(
        "04_simultaneous_vivillon",
        "simultaneous",
        "Batch Vivillon Scarf+Sleep Powder: partial commit + pending_flags",
        _run_04,
    ),
    Scenario(
        "05_archetype_reconcile",
        "archetype",
        "Archetype change reopens only theme-mismatched locks",
        _run_05,
    ),
    Scenario(
        "06_reset_preserves_rejected",
        "reset",
        "Reset clears pending/provisional; rejected history survives",
        _run_06,
    ),
    Scenario(
        "07_restore_one_level",
        "restore",
        "Second restore is a no-op (one-level undo only)",
        _run_07,
    ),
    Scenario(
        "08_defer_pending_kinds",
        "defer",
        "Defer → deferred (2 kinds) / build_abandoned (full_build)",
        _run_08,
    ),
    Scenario(
        "09_nonconflict_constraint",
        "constraint_negative",
        "Non-conflicting constraint leaves existing lock untouched",
        _run_09,
    ),
    Scenario(
        "11_idle_persist",
        "idle",
        "Lock persists across continue/idle rediscovery turns",
        _run_11,
    ),
    Scenario(
        "12_sqlite_mid_contradiction",
        "sqlite_resume",
        "SQLite close/reopen mid-supersede sequence then restore",
        _run_12,
    ),
]
