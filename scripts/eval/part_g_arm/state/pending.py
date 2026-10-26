"""Load OL/H27 fixtures into arm state without inventing reachable screens.

Team rows go through apply_lock with the fixture's INTERNAL slot index (no
user_slot_to_index). OL pending screens are placed from the fixture dict
verbatim (binding rows, not commit). H27 builds candidate_selection through
present_candidates / run_slot_fill_terminal.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from recommender.ids import to_id
from recommender.legality import legal_moves_for, load_snapshot
from recommender.nodes import apply_lock
from recommender.nodes_classify import classify_pending
from recommender.slot_fill import SlotFillContext, annotate_overlap, run_slot_fill_terminal
from recommender.state import (
    PendingSlotIntent,
    ProvisionalSlot,
    TargetRoleDecision,
    ThreatCandidate,
    ThreatCounterCandidate,
    empty_slot,
    slot_fingerprint,
)
from recommender.support_needs import RoleShapeContext

from scripts.eval.part_g_arm.state.fixtures import empty_team

HERE = Path(__file__).resolve().parent
V4 = HERE.parents[1] / "part_g_v4"
OL_DIR = V4 / "ol_fixtures"
H27_PATH = V4 / "h27_candidate_fixture.json"
_DEV_ROLE = TargetRoleDecision(role_id="bulky_offense", source="user_choice")
_LOCK_ATTRS = ("species", "role", "ability", "item", "moveset", "nature", "spread")


def _resolve_path(path_or_id: str | Path) -> Path:
    raw = Path(path_or_id)
    if raw.is_file():
        return raw
    key = str(path_or_id)
    if key.upper() == "H27":
        return H27_PATH
    ol = OL_DIR / f"{key}.json"
    if ol.is_file():
        return ol
    raise FileNotFoundError(f"no fixture for {path_or_id!r}")


def _lock_internal(state: dict[str, Any], slot_index: int, attr: str, value: object) -> dict[str, Any]:
    patch = apply_lock({**state, "turn_payload": {"slot_index": slot_index, "attr": attr, "value": value}})
    if patch.get("slot_commit_error"):
        raise RuntimeError(f"apply_lock {attr}@{slot_index}: {patch['slot_commit_error']}")
    return {**state, **patch}


def _apply_team_row(state: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    """Fixture slot numbers are internal. Species (and optional ability/item) via apply_lock."""
    index = int(row["slot"])
    species = row.get("species")
    if not species:
        return state
    state = _lock_internal(state, index, "species", species)
    for attr in ("ability", "item"):
        if row.get(attr):
            state = _lock_internal(state, index, attr, row[attr])
    return state


def _load_ol(doc: dict[str, Any]) -> dict[str, Any]:
    state = empty_team()
    for row in doc.get("team") or []:
        state = _apply_team_row(state, row)
    # Binding fixtures: pending dict is placed as written. They do not carry
    # provisional_slot / pending_slot_intent, so commit_full_slot will refuse.
    state["pending_presentation"] = dict(doc["pending"])
    return state


def _threat_counter(species: str, *, usage_rank: int, verified_score: float) -> ThreatCounterCandidate:
    cand = ThreatCandidate(
        ladder_species=species,
        usage_rank=usage_rank,
        form=species,
        showdown_usage_pct=None,
        showdown_formes=(),
        spec={"species": species},
        build_source="ingame",
    )
    return ThreatCounterCandidate(
        candidate=cand,
        threats_countered=("fixture",),
        threats_countered_count=1,
        verified_score=verified_score,
        verified_vs=(),
    )


def _load_h27(doc: dict[str, Any]) -> dict[str, Any]:
    inputs = doc["inputs"]
    shape = inputs["role_shape_context"]
    ctx = SlotFillContext(
        anchor={"species": inputs["anchor"]["species"]},
        role_shape_context=RoleShapeContext(
            primary_function=shape["primary_function"],
            tankiness=shape.get("tankiness", "unknown"),
            requires_setup_turn=bool(shape.get("requires_setup_turn", False)),
        ),
        threat_counter_results=[
            _threat_counter(row["species"], usage_rank=row["usage_rank"], verified_score=row["verified_score"])
            for row in inputs["threat_counter_results"]
        ],
        support_needs=list(inputs.get("support_needs") or []),
        regulation=inputs["regulation"],
    )
    annotate_overlap(ctx)  # present_candidates reads annotated_candidates only
    state = empty_team()
    terminal = run_slot_fill_terminal(ctx, state, slot_index=int(inputs["slot_index"]))
    return {**state, **terminal.state_updates}


def load_fixture(path_or_id: str | Path) -> dict[str, Any]:
    path = _resolve_path(path_or_id)
    doc = json.loads(path.read_text(encoding="utf-8"))
    if path.name == "h27_candidate_fixture.json" or doc.get("id") == "H27":
        return _load_h27(doc)
    return _load_ol(doc)


def build_fully_locked_slot(species: str, *, user_slot: int = 1) -> dict[str, Any]:
    """Every Attr locked via apply_lock. user_slot is converted once here."""
    from recommender.slot_index import user_slot_to_index

    snap = load_snapshot()
    ability = next(iter(snap["species"][to_id(species)]["abilities"].values()))
    moves = list(legal_moves_for(species)[:4])
    index = user_slot_to_index(user_slot)
    state = empty_team()
    values = {
        "species": species,
        "role": "bulky_offense",
        "ability": ability,
        "item": "Sitrus Berry",
        "moveset": moves,
        "nature": "Modest",
        "spread": {"hp": 32, "atk": 0, "def": 0, "spa": 32, "spd": 2, "spe": 0},
    }
    for attr in _LOCK_ATTRS:
        state = _lock_internal(state, index, attr, values[attr])
    return state


def build_fbc_pending(species: str, *, slot_index: int = 0) -> dict[str, Any]:
    """Valid full_build_confirmation for commit_full_slot. No LLM, no calc.

    Built as ProvisionalSlot + PendingSlotIntent + pending_presentation with a
    matching fingerprint — the same shape commit_seed uses in tests. Not produced
    by discovery; commit_full_slot is the node that validates it.
    """
    snap = load_snapshot()
    ability = next(iter(snap["species"][to_id(species)]["abilities"].values()))
    moves = tuple(legal_moves_for(species)[:4])
    draft = [empty_slot() for _ in range(6)]
    fp = "dev-fbc-v1"
    base_fp = slot_fingerprint(draft[slot_index])
    prov = ProvisionalSlot(
        schema_version=1,
        slot_index=slot_index,
        target_role_decision=_DEV_ROLE,
        species=species,
        ability=ability,
        item="Sitrus Berry",
        moves=moves,  # type: ignore[arg-type]
        nature="Modest",
        spread=(("hp", 32), ("atk", 0), ("def", 0), ("spa", 32), ("spd", 2), ("spe", 0)),
        base_slot_fingerprint=base_fp,
        fingerprint=fp,
    )
    return {
        **empty_team(),
        "team_draft": draft,
        "provisional_slot": prov,
        "pending_slot_intent": PendingSlotIntent(
            schema_version=1,
            slot_index=slot_index,
            species=species,
            target_role_decision=_DEV_ROLE,
            source="need",
            base_slot_fingerprint=base_fp,
        ),
        "pending_presentation": {
            "schema_version": 1,
            "kind": "full_build_confirmation",
            "slot_index": slot_index,
            "provisional_fingerprint": fp,
        },
        "constraints": [],
    }


def probe_fixture(path_or_id: str | Path) -> dict[str, Any]:
    """Load a fixture and run the node that would consume its pending screen."""
    path = _resolve_path(path_or_id)
    doc = json.loads(path.read_text(encoding="utf-8"))
    fixture_id = doc.get("id") or path.stem
    try:
        state = load_fixture(path)
        loaded = True
        load_error = None
    except Exception as exc:  # noqa: BLE001 - validity report, not a crash
        return {"fixture": fixture_id, "loaded": False, "accepted": "no", "node": None, "error": f"{type(exc).__name__}: {exc}"}
    kind = (state.get("pending_presentation") or {}).get("kind")
    # Binding rows: classify_pending is the consumer (FBC affirm/defer/option ids,
    # CS ordinal/label/affirm). commit_full_slot is only for a live FBC with provisional.
    if kind in {"full_build_confirmation", "candidate_selection"}:
        reply = doc.get("reply") or ""
        result = classify_pending(reply, state["pending_presentation"], turn_intent_parser=None)
        intent = result.get("turn_intent")
        bound = None
        if intent == "slot_candidate_selected":
            bound = (result.get("selected_option") or {}).get("species")
        elif intent == "select_build_option":
            bound = (result.get("turn_payload") or {}).get("option_ids")
        needs_parser = intent == "pending_response"
        typed = intent in {
            "slot_candidate_selected", "select_build_option", "full_slot_confirmed",
            "deferred", "build_abandoned", "rejection",
        }
        return {
            "fixture": fixture_id,
            "kind": kind,
            "loaded": loaded,
            "node": "classify_pending",
            "turn_intent": intent,
            "bound": bound,
            "needs_parser": needs_parser,
            "accepted": "yes" if typed else "unknown",
            "detail": f"turn_intent={intent!r} bound={bound!r}",
            "error": None if typed else f"turn_intent={intent!r}",
        }
    return {"fixture": fixture_id, "loaded": loaded, "accepted": "unknown", "node": None, "error": f"kind={kind!r}"}


def ol_validity_table() -> list[dict[str, Any]]:
    rows = []
    for path in sorted(OL_DIR.glob("OL*.json")):
        rows.append(probe_fixture(path))
    return rows
