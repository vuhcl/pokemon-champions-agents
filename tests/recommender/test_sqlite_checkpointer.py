"""SqliteSaver durability: serde + restart round-trip for immutable state dataclasses."""

from __future__ import annotations

import warnings
from pathlib import Path
from unittest.mock import patch

from recommender.checkpointer import default_db_path, open_sqlite_checkpointer
from recommender.graph import compile_graph
from recommender.nodes import team_phase
from recommender.state import (
    Attr,
    CandidateEvidence,
    PendingSlotIntent,
    ProvisionalSlot,
    Slot,
    TargetRoleDecision,
)

VGC_MB = "[Gen 9 Champions] VGC 2026 Reg M-B"
_SPREAD = {"hp": 32, "atk": 32, "def": 2, "spa": 0, "spd": 0, "spe": 0}


def _thread(suffix: str):
    return {"configurable": {"thread_id": f"sqlite-{suffix}"}}


def _fully_locked(species: str) -> Slot:
    """One confirmed member — enough for team_phase == single_locked."""
    return Slot(
        role=Attr("bulky_attacker", locked=True),
        species=Attr(species, locked=True),
        ability=Attr("Pressure", locked=True),
        item=Attr("Leftovers", locked=True),
        moveset=Attr(["Protect", "Tackle", "Rest", "Sleep Talk"], locked=True),
        spread=Attr(dict(_SPREAD), locked=True),
        nature=Attr("Adamant", locked=True),
    )


def test_default_db_path_respects_env(monkeypatch, tmp_path: Path):
    target = tmp_path / "custom.db"
    monkeypatch.setenv("POKEMON_CHAMPIONS_CHECKPOINT_DB", str(target))
    assert default_db_path() == target


def test_serde_msgpack_round_trips_immutable_dataclasses(tmp_path: Path):
    saver = open_sqlite_checkpointer(tmp_path / "serde.db")
    try:
        serde = saver.serde
        slot = _fully_locked("Garchomp")
        decision = TargetRoleDecision(
            role_id="trick_room_setter",
            source="support_need",
            evidence=("trick_room",),
        )
        intent = PendingSlotIntent(
            schema_version=1,
            slot_index=1,
            species="Farigiraf",
            target_role_decision=decision,
            source="need",
            evidence=(
                CandidateEvidence(
                    "compendium_backed",
                    "medium",
                    "role_category_evidence",
                    ("role:trick_room_setter",),
                ),
            ),
            base_slot_fingerprint="fp",
        )
        restored = {}
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            for obj in (slot, decision, intent):
                tag, blob = serde.dumps_typed(obj)
                assert tag == "msgpack"
                back = serde.loads_typed((tag, blob))
                assert type(back) is type(obj)
                restored[type(obj)] = back
        assert not any("unregistered type" in str(w.message) for w in caught)
        assert restored[Slot].species.value == "Garchomp"
        assert restored[Slot].species.locked is True
        assert restored[PendingSlotIntent].species == "Farigiraf"
        assert restored[TargetRoleDecision].role_id == "trick_room_setter"
        assert list(restored[TargetRoleDecision].evidence) == ["trick_room"]
    finally:
        saver.conn.close()


def test_first_run_creates_missing_db(tmp_path: Path):
    db = tmp_path / "subdir" / "fresh.db"
    assert not db.exists()
    saver = open_sqlite_checkpointer(db)
    try:
        graph = compile_graph(checkpointer=saver)
        result = graph.invoke(
            {"format_id": VGC_MB}, config=_thread("first-run")
        )
        assert result["game_type"] == "doubles"
        assert db.is_file()
    finally:
        saver.conn.close()


def test_restart_round_trips_pending_intent_and_provisional_slot(tmp_path: Path):
    db = tmp_path / "restart.db"
    thread = _thread("restart")
    moves = ["Psychic", "Hyper Voice", "Trick Room", "Protect"]
    spread = {"hp": 32, "atk": 0, "def": 0, "spa": 32, "spd": 2, "spe": 0}

    saver = open_sqlite_checkpointer(db)
    try:
        graph = compile_graph(checkpointer=saver)
        graph.invoke({"format_id": VGC_MB}, config=thread)

        draft = list(graph.get_state(thread).values["team_draft"])
        draft[0] = _fully_locked("Garchomp")
        pending = {
            "schema_version": 1,
            "kind": "candidate_selection",
            "slot_index": 1,
            "options": [
                {
                    "species": "Farigiraf",
                    "source": "both",
                    "evidence": (
                        CandidateEvidence(
                            "compendium_backed",
                            "medium",
                            "role_category_evidence",
                            ("role:trick_room_setter",),
                        ),
                    ),
                    "target_role_decision": TargetRoleDecision(
                        role_id="trick_room_setter",
                        source="support_need",
                        evidence=("trick_room",),
                    ),
                },
                {"species": "Incineroar", "source": "threat"},
            ],
        }
        graph.update_state(thread, {"team_draft": draft, "pending_presentation": pending})
        assert team_phase(graph.get_state(thread).values) == "single_locked"

        with (
            patch(
                "recommender.propose.featured_or_common_set",
                return_value={
                    "species": "Farigiraf",
                    "ability": "Armor Tail",
                    "moves": moves,
                    "item": "Sitrus Berry",
                    "nature": "Modest",
                },
            ),
            patch(
                "recommender.propose.get_resolved_build",
                return_value={
                    "spread": spread,
                    "source_tier": "test",
                    "verified": True,
                },
            ),
        ):
            selected = graph.invoke({"pending_input": "yes"}, config=thread)

        assert isinstance(selected["pending_slot_intent"], PendingSlotIntent)
        assert selected["pending_slot_intent"].species == "Farigiraf"
        assert isinstance(selected["provisional_slot"], ProvisionalSlot)
        assert selected["provisional_slot"].target_role_decision.role_id == (
            "trick_room_setter"
        )
        assert selected["provisional_slot"].ability == "Armor Tail"
        assert selected["provisional_slot"].moves == tuple(moves)
        assert selected["provisional_slot"].spread_dict() == spread
    finally:
        saver.conn.close()

    # Simulate process restart: new SqliteSaver against the same file.
    restarted = open_sqlite_checkpointer(db)
    try:
        graph2 = compile_graph(checkpointer=restarted)
        snap = graph2.get_state(thread).values
        assert team_phase(snap) == "single_locked"
        assert snap["team_draft"][0].species.value == "Garchomp"
        assert snap["team_draft"][0].species.locked is True

        intent = snap["pending_slot_intent"]
        provisional = snap["provisional_slot"]
        assert isinstance(intent, PendingSlotIntent)
        assert intent.species == "Farigiraf"
        assert intent.slot_index == 1
        assert isinstance(intent.target_role_decision, TargetRoleDecision)
        assert intent.target_role_decision.role_id == "trick_room_setter"
        assert list(intent.target_role_decision.evidence) == ["trick_room"]

        assert isinstance(provisional, ProvisionalSlot)
        assert provisional.species == "Farigiraf"
        assert provisional.ability == "Armor Tail"
        assert provisional.item == "Sitrus Berry"
        assert provisional.nature == "Modest"
        assert list(provisional.moves) == moves
        assert provisional.spread_dict() == spread
        assert provisional.target_role_decision.role_id == "trick_room_setter"
        assert provisional.target_role_decision.source == "support_need"
    finally:
        restarted.conn.close()
