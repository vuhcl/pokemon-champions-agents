"""Concrete seed builders. Species chosen from the pinned snapshot; not tool-example Megas."""

from __future__ import annotations

from typing import Any

from recommender.ids import to_id
from recommender.legality import legal_moves_for, load_snapshot
from recommender.nodes import apply_lock, record_constraint
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

JUSTIFICATIONS: dict[str, str] = {
    "cs_pending": (
        "MS7 (covered) needs a CS screen with option 2; Pelipper/Toxapex/Corviknight "
        "from present_candidates (H27 route). MT4 remains mapped for dry-run only "
        "(not covered — no show-candidates tool). Option evidence emptied so the model "
        "cannot repeat hand-written seed scores (read_pending already omits evidence)."
    ),
    "fbc_pending": (
        "MS4/MU7 need a valid FBC for one complete build; Garchomp + Sand Veil + Sitrus "
        "Berry + four legal moves is a full provisional the commit node can accept."
    ),
    "mt3_after_t1": (
        "MT3 after t1 'No Intimidate.': judgment-only predicate no_intimidate (no ban-ability "
        "mechanical kind) plus message_history so the model sees t1; runner plays t2–t3."
    ),
    "hc2_after_t1": (
        "HC2 after t1 'No weather.': judgment-only no_weather_ability (same tag family as "
        "H18b) plus message_history; runner plays t2."
    ),
    "hd1_history": (
        "HD1 after H1: prior user 'What type is Toxapex?' + assistant Poison/Water claim; "
        "no team state; runner plays only the correction turn with that history."
    ),
}

_DEV_ROLE = TargetRoleDecision(role_id="bulky_offense", source="user_choice")


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
        threats_countered=("seed",),
        threats_countered_count=1,
        verified_score=verified_score,
        verified_vs=(),
    )


def build_cs_pending_seed() -> dict[str, Any]:
    """candidate_selection with ≥3 options targeting an open slot; options carry source."""
    from recommender.regulation_registry import REGULATIONS, active_regulation

    names = ["Pelipper", "Toxapex", "Corviknight", "Garchomp"]
    mod = REGULATIONS[active_regulation()]["mod"]
    ctx = SlotFillContext(
        anchor={"species": names[0]},
        role_shape_context=RoleShapeContext(
            primary_function="offense",
            tankiness="unknown",
            requires_setup_turn=False,
        ),
        threat_counter_results=[
            _threat_counter(name, usage_rank=i + 1, verified_score=float(5 - i))
            for i, name in enumerate(names)
        ],
        support_needs=[],
        regulation=mod,
    )
    annotate_overlap(ctx)
    state = empty_team()
    # Open slot = user slot 2 → internal 1
    terminal = run_slot_fill_terminal(ctx, state, slot_index=1)
    out = {**state, **terminal.state_updates}
    pending = out.get("pending_presentation") or {}
    options = list(pending.get("options") or [])
    if len(options) < 3:
        raise RuntimeError(f"cs_pending seed needs ≥3 options, got {len(options)}")
    # Strip producer evidence / role kit strings — not pinned facts; model must not echo them.
    # present_candidates accepts empty evidence; keep species + source only.
    cleaned: list[dict[str, Any]] = []
    for opt in options:
        row = dict(opt)
        if not row.get("source"):
            row["source"] = "threat"
        row["evidence"] = ()
        trd = row.get("target_role_decision")
        if trd is not None:
            # TargetRoleDecision dataclass or dict from serialize round-trip
            if hasattr(trd, "role_id"):
                row["target_role_decision"] = TargetRoleDecision(
                    role_id=trd.role_id or "unknown",
                    source=getattr(trd, "source", None) or "other",
                    confidence=getattr(trd, "confidence", None) or "low",
                    evidence=(),
                    needed_constraints=(),
                    wanted_constraints=(),
                    ambiguity=(),
                    provenance=(),
                    producer_name=None,
                )
            elif isinstance(trd, dict):
                row["target_role_decision"] = {
                    **trd,
                    "evidence": [],
                    "needed_constraints": [],
                    "wanted_constraints": [],
                    "ambiguity": [],
                    "provenance": [],
                    "producer_name": None,
                }
        cleaned.append(row)
    pending = {
        **pending,
        "options": cleaned,
        "slot_index": 1,
        "kind": "candidate_selection",
    }
    out["pending_presentation"] = pending
    return out


def build_fbc_pending_seed() -> dict[str, Any]:
    """Valid full_build_confirmation for Garchomp (complete build fields)."""
    species = "Garchomp"
    snap = load_snapshot()
    ability = next(iter(snap["species"][to_id(species)]["abilities"].values()))
    moves = tuple(legal_moves_for(species)[:4])
    if len(moves) < 4:
        raise RuntimeError(f"Garchomp needs 4 legal moves, got {moves}")
    draft = [empty_slot() for _ in range(6)]
    slot_index = 0
    fp = "seed-fbc-garchomp-v1"
    base_fp = slot_fingerprint(draft[slot_index])
    # Lock nothing on the draft — FBC commits onto an open slot.
    prov = ProvisionalSlot(
        schema_version=1,
        slot_index=slot_index,
        target_role_decision=_DEV_ROLE,
        species=species,
        ability=ability,
        item="Sitrus Berry",
        moves=moves,  # type: ignore[arg-type]
        nature="Jolly",
        spread=(("hp", 4), ("atk", 32), ("def", 0), ("spa", 0), ("spd", 0), ("spe", 30)),
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


def _record_judgment_constraint(state: dict[str, Any], predicate: str, *, turn: int) -> dict[str, Any]:
    patch = record_constraint(
        {
            **state,
            "turn": turn,
            "turn_payload": {
                "type": "hard",
                "predicate": predicate,
                "scope": "team_wide",
                "groundedness": "judgment-only",
            },
        }
    )
    if patch.get("slot_commit_error"):
        raise RuntimeError(f"record_constraint {predicate}: {patch['slot_commit_error']}")
    return {**state, **patch}


def build_mt3_seed() -> dict[str, Any]:
    """After t1 'No Intimidate.' — judgment-only constraint + history; empty team otherwise.

    Wording of the assistant ack is taken from the request-set t1 text only
    ('No Intimidate.') — mirrors the Vu-specified note; no other claim.
    """
    state = _record_judgment_constraint(empty_team(), "no_intimidate", turn=1)
    state["_message_history"] = [
        {"role": "user", "content": "No Intimidate."},
        {
            "role": "assistant",
            "content": "Noted: no Intimidate on this team.",
        },
    ]
    return state


def build_hc2_seed() -> dict[str, Any]:
    """After t1 'No weather.' — judgment-only no_weather_ability + history.

    Assistant ack mirrors request-set t1 ('No weather.') as weather abilities;
    no other claim.
    """
    state = _record_judgment_constraint(empty_team(), "no_weather_ability", turn=1)
    state["_message_history"] = [
        {"role": "user", "content": "No weather."},
        {
            "role": "assistant",
            "content": "Noted: no weather abilities on this team.",
        },
    ]
    return state


def build_hd1_seed() -> dict[str, Any]:
    """Empty team + prior H1 Q/A history for the HD1 correction turn.

    History is stored under ``_message_history`` (not team state). The runner must
    prepend these as HumanMessage/AIMessage so the model sees them as prior turns.
    """
    state = empty_team()
    state["_message_history"] = [
        {"role": "user", "content": "What type is Toxapex?"},
        {
            "role": "assistant",
            "content": "Toxapex is Poison/Water.",
        },
    ]
    state["_runner_turns"] = ["No, Toxapex is not Water/Poison"]
    return state
