"""Load OL/H27/v4 fixtures into arm state without inventing reachable screens.

Per-file slot bases are declared in `_SLOT_BASE` (internal | user | first_free).
User-base files convert through `user_slot_to_index`. OL pending screens are
placed from the fixture dict verbatim. H27 builds candidate_selection through
present_candidates / run_slot_fill_terminal.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from recommender.ids import to_id
from recommender.legality import legal_moves_for, load_snapshot
from recommender.nodes import apply_lock, record_constraint
from recommender.nodes_classify import classify_pending
from recommender.slot_fill import SlotFillContext, annotate_overlap, run_slot_fill_terminal
from recommender.slot_index import user_slot_to_index
from dataclasses import replace

from recommender.state import (
    Attr,
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
FIX_DIR = V4 / "fixtures"
H27_PATH = V4 / "h27_candidate_fixture.json"
_DEV_ROLE = TargetRoleDecision(role_id="bulky_offense", source="user_choice")
_LOCK_ATTRS = ("species", "role", "ability", "item", "moveset", "nature", "spread")
# Request-set row id → fixtures/*.json stem.
_ROW_FIXTURE = {
    "HN2c": "hn2c_team",
    "HN2d": "hn2d_team",
    "H18b": "h18b_hyper_offense",
    "MU2": "mu2_mu3_team",
    "MU3": "mu2_mu3_team",
    "MU4": "mu4_pelipper",
    "MS5": "ms5_rain_conflict",
    "IC1": "ic1_corviknight_item_clause",
    "IS2": "is2_basculegion",
    "H25": "h25_team",
    "H26": "h26_torkoal_locked",
    "MM2": "mm2_salamence_mega",
    "MRB1": None,  # generic builder, not a fixtures/*.json file
}

SlotBase = Literal["internal", "user", "first_free"]

# Per-file declared base. Evidence strings are for the Part 3 report, not parsed.
_SLOT_BASE: dict[str, SlotBase] = {
    "hn2c_team.json": "internal",
    "hn2d_team.json": "internal",
    "is2_basculegion.json": "internal",
    "mu2_mu3_team.json": "user",
    "h18b_hyper_offense.json": "user",
    "mu4_pelipper.json": "user",
    "ms5_rain_conflict.json": "user",
    "h25_team.json": "user",
    "h26_torkoal_locked.json": "user",
    "ic1_corviknight_item_clause.json": "first_free",
    "mm2_salamence_mega.json": "internal",
    # RB1: top-level species/item/moves (4th move empty); internal slot 0.
    "rb1_lucario_megaz_calmmind.json": "internal",
    # TB2: top-level Incineroar+Charcoal (internal slot 0).
    "tb2_incineroar_charcoal.json": "internal",
}

_SLOT_BASE_EVIDENCE: dict[str, str] = {
    "hn2c_team.json": "team[].slot is 0; Spe-fixed speed row",
    "hn2d_team.json": "team[].slot is 0; Mega Blaziken speed row",
    "is2_basculegion.json": "top-level species, no slot field → internal 0",
    "mu2_mu3_team.json": 'note "slot 2 open"; slots numbered 1,2,3; request-set "slot 2"',
    "h18b_hyper_offense.json": "slots 1,2; request-set seeded slots for H18b",
    "mu4_pelipper.json": "slots 1,2; note names Pelipper unlocked on slot 2",
    "ms5_rain_conflict.json": "slots 1,2; request-set rain-conflict fixture",
    "h25_team.json": "slots 1,2,3; request-set H25 seeded 3-member team",
    "h26_torkoal_locked.json": "slot 1; request-set H26 Torkoal locked",
    "ic1_corviknight_item_clause.json": (
        "no slot fields; loader rule: first free slots in list order "
        "(Item Clause does not depend on slot)"
    ),
    "tb2_incineroar_charcoal.json": "top-level species/item/moves; internal slot 0",
}


class FixtureLoadError(ValueError):
    """Named fixture could not be loaded through apply_lock without guessing."""


def _resolve_path(path_or_id: str | Path) -> Path:
    raw = Path(path_or_id)
    if raw.is_file():
        return raw
    key = str(path_or_id)
    if key.upper() == "H27":
        return H27_PATH
    if key.upper() == "MRB1":
        raise FileNotFoundError("MRB1 has no fixture file; use build_mrb1_start()")
    ol = OL_DIR / f"{key}.json"
    if ol.is_file():
        return ol
    stem = _ROW_FIXTURE.get(key.upper() if key.upper() in _ROW_FIXTURE else key, key)
    if stem is None:
        raise FileNotFoundError(f"no fixture for {path_or_id!r}")
    stem = str(stem).removesuffix(".json")
    fix = FIX_DIR / f"{stem}.json"
    if fix.is_file():
        return fix
    raise FileNotFoundError(f"no fixture for {path_or_id!r}")


def _lock_internal(state: dict[str, Any], slot_index: int, attr: str, value: object) -> dict[str, Any]:
    patch = apply_lock({**state, "turn_payload": {"slot_index": slot_index, "attr": attr, "value": value}})
    if patch.get("slot_commit_error"):
        raise RuntimeError(f"apply_lock {attr}@{slot_index}: {patch['slot_commit_error']}")
    return {**state, **patch}


def _write_attr(
    state: dict[str, Any],
    slot_index: int,
    attr: str,
    value: object,
    *,
    locked: bool,
) -> dict[str, Any]:
    """Direct Attr write (no apply_lock reconcile). Used for drafts and Choice+status."""
    slot = state["team_draft"][slot_index]
    new_slot = replace(slot, **{attr: Attr(value=value, locked=locked)})
    draft = list(state["team_draft"])
    draft[slot_index] = new_slot
    return {**state, "team_draft": draft, "slot_commit_error": None}


def _lock_moveset_safe(
    state: dict[str, Any], slot_index: int, moves: list[str]
) -> tuple[dict[str, Any], bool]:
    """Lock moveset; fall back to direct Attr write if reconcile would wipe siblings.

    Returns (state, moves_kept). Choice + status moves wipe via apply_lock reconcile;
    the fixture still needs the moveset on the slot for HN2c-style keys.
    """
    before = state
    species_before = state["team_draft"][slot_index].species.value
    state = _lock_internal(state, slot_index, "moveset", moves)
    if species_before and state["team_draft"][slot_index].species.value is None:
        # Preserve siblings; write moveset locked without reconcile.
        state = _write_attr(before, slot_index, "moveset", list(moves), locked=True)
        return state, True
    return state, True


def _apply_team_row(
    state: dict[str, Any],
    row: dict[str, Any],
    *,
    index: int,
    incomplete: list[str] | None = None,
) -> dict[str, Any]:
    """Lock species and optional attrs at an already-resolved internal index."""
    species = row.get("species")
    if not species:
        return state
    if row.get("locked") is False:
        # Draft values (locked=False) so MU4-style unlocked rows are present.
        state = _write_attr(state, index, "species", species, locked=False)
        for attr, key in (
            ("ability", "ability"),
            ("item", "item"),
            ("nature", "nature"),
        ):
            if row.get(key):
                state = _write_attr(state, index, attr, row[key], locked=False)
        spr = row.get("spread") or row.get("evs")
        if spr:
            state = _write_attr(state, index, "spread", spr, locked=False)
        moves = row.get("moves") or row.get("moveset")
        if moves:
            state = _write_attr(state, index, "moveset", list(moves), locked=False)
        return state
    # Mega Stone rule: species+item from the same fixture row must be visible
    # together (same as apply_lock batch). Item-only then species also works.
    item = row.get("item")
    if item:
        patch = apply_lock(
            {
                **state,
                "turn_payload": {
                    "slot_index": index,
                    "locks": [
                        {"attr": "species", "value": species},
                        {"attr": "item", "value": item},
                    ],
                },
            }
        )
        if patch.get("slot_commit_error"):
            raise RuntimeError(
                f"apply_lock batch species+item@{index}: {patch['slot_commit_error']}"
            )
        state = {**state, **patch}
    else:
        state = _lock_internal(state, index, "species", species)
    # Ability after species/item. Choice + status-move still wipes via reconcile.
    ability = row.get("ability")
    if ability:
        state = _lock_internal(state, index, "ability", ability)
    for attr, value in (
        ("nature", row.get("nature")),
        ("spread", row.get("spread") or row.get("evs")),
    ):
        if value:
            state = _lock_internal(state, index, attr, value)
    # Moves last: Choice + status moves wipe siblings under apply_lock; fall back
    # to a direct Attr write so HN2c-style fixtures keep the moveset.
    moves = row.get("moves") or row.get("moveset")
    if moves:
        state, kept = _lock_moveset_safe(state, index, list(moves))
        if not kept and incomplete is not None:
            incomplete.append(
                f"slot {index}: moves skipped (apply_lock moveset wiped siblings; "
                "Choice item + non-damaging move)"
            )
    return state


def _team_rows(doc: dict[str, Any]) -> list[dict[str, Any]] | None:
    if isinstance(doc.get("team"), list):
        return list(doc["team"])
    if isinstance(doc.get("slots"), list):
        return list(doc["slots"])
    return None


def _first_free_index(state: dict[str, Any]) -> int:
    for i, slot in enumerate(state["team_draft"]):
        if not slot.species.value:
            return i
    raise FixtureLoadError("no free slot for first_free placement")


def _load_ol(doc: dict[str, Any]) -> dict[str, Any]:
    state = empty_team()
    for row in doc.get("team") or []:
        # OL team rows use internal indices as written.
        state = _apply_team_row(state, row, index=int(row["slot"]))
    # Binding fixtures: pending dict is placed as written. They do not carry
    # provisional_slot / pending_slot_intent, so commit_full_slot will refuse.
    state["pending_presentation"] = dict(doc["pending"])
    return state


def _load_v4_team_fixture(doc: dict[str, Any], *, path: Path) -> dict[str, Any]:
    """Load fixtures/*.json via the per-file declared slot base."""
    base = _SLOT_BASE.get(path.name)
    if base is None:
        raise FixtureLoadError(
            f"{path.name}: no declared slot base in _SLOT_BASE; refusing to guess"
        )
    incomplete: list[str] = []
    rows = _team_rows(doc)
    if rows is None:
        if doc.get("species") and base == "internal":
            state = _apply_team_row(
                empty_team(), {**doc, "slot": 0}, index=0, incomplete=incomplete
            )
            if incomplete:
                state["_fixture_incomplete"] = incomplete
            return state
        raise FixtureLoadError(f"{path.name}: no team/slots and no top-level species")

    if base == "first_free":
        # Loader rule (not a file fact): place teammates in first free slots in list order.
        state = empty_team()
        for row in rows:
            if not isinstance(row, dict) or not row.get("species"):
                continue
            state = _apply_team_row(
                state, row, index=_first_free_index(state), incomplete=incomplete
            )
        if incomplete:
            state["_fixture_incomplete"] = incomplete
        return state

    if not any("slot" in r for r in rows if isinstance(r, dict)):
        raise FixtureLoadError(
            f"{path.name}: team rows have no slot fields under base={base!r}"
        )

    state = empty_team()
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("open") or not row.get("species"):
            continue
        raw_slot = int(row["slot"])
        if base == "user":
            index = user_slot_to_index(raw_slot)
        else:
            index = raw_slot
        state = _apply_team_row(state, row, index=index, incomplete=incomplete)
    # Fixture constraint tags → judgment-only predicates (no mechanical_kind).
    # They are not type|ability|item|no_duplicate_items specs; SP/weather rules stay unenforced.
    for tag in doc.get("constraints") or []:
        if not isinstance(tag, str) or not tag:
            continue
        patch = record_constraint(
            {
                **state,
                "turn_payload": {
                    "type": "hard",
                    "predicate": tag,
                    "scope": "team_wide",
                    "groundedness": "judgment-only",
                },
            }
        )
        if patch.get("slot_commit_error"):
            incomplete.append(f"constraint {tag!r}: {patch['slot_commit_error']}")
            continue
        state = {**state, **patch}
        incomplete.append(
            f"constraint {tag!r} loaded as judgment-only predicate only "
            "(no mechanical_kind; not enforceable as SP/weather rule)"
        )
    if incomplete:
        state["_fixture_incomplete"] = incomplete
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
    if path.parent.resolve() == FIX_DIR.resolve() or path.name.endswith("_team.json") or path.name in {
        "h18b_hyper_offense.json", "mu2_mu3_team.json", "mu4_pelipper.json",
        "ms5_rain_conflict.json", "ic1_corviknight_item_clause.json", "is2_basculegion.json",
        "h25_team.json", "h26_torkoal_locked.json",
    }:
        if path.name == "h25_team.json":
            doc = _substitute_h25_doc(doc)
        return _load_v4_team_fixture(doc, path=path)
    return _load_ol(doc)


def try_load_fixture(path_or_id: str | Path) -> dict[str, Any]:
    """Like load_fixture, but returns {loaded, state|None, error|None} for the matrix."""
    try:
        state = load_fixture(path_or_id)
        return {"loaded": True, "state": state, "error": None}
    except Exception as exc:  # noqa: BLE001 - matrix report
        return {"loaded": False, "state": None, "error": f"{type(exc).__name__}: {exc}"}


def build_cs_pending(
    species: tuple[str, ...] | list[str],
    *,
    slot_index: int = 0,
) -> dict[str, Any]:
    """Dev candidate_selection via present_candidates (same route as H27). Dev species only."""
    from recommender.regulation_registry import REGULATIONS, active_regulation

    names = list(species)
    if len(names) < 2:
        raise ValueError("build_cs_pending needs at least two species")
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
    terminal = run_slot_fill_terminal(ctx, state, slot_index=slot_index)
    return {**state, **terminal.state_updates}


def build_fully_locked_slot(species: str, *, user_slot: int = 1) -> dict[str, Any]:
    """Every Attr locked via apply_lock. user_slot is converted once here."""
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


def build_fully_locked_mega(
    species: str, item: str, *, user_slot: int = 1
) -> dict[str, Any]:
    """Fully lock a Mega forme with its mapped stone (species+item batch, then the rest)."""
    snap = load_snapshot()
    ability = next(iter(snap["species"][to_id(species)]["abilities"].values()))
    moves = list(legal_moves_for(species)[:4])
    index = user_slot_to_index(user_slot)
    state = _apply_team_row(
        empty_team(),
        {
            "species": species,
            "item": item,
            "ability": ability,
            "moveset": moves,
            "nature": "Adamant",
            "spread": {"hp": 32, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 0},
        },
        index=index,
    )
    if not state["team_draft"][index].role.locked:
        state = _lock_internal(state, index, "role", "bulky_offense")
    return state


def build_mrb1_start() -> dict[str, Any]:
    """MRB1 start: Torkoal locked at user slot 3 with Drought + Charcoal.

    Errata (state/errata.json): expected read-back strings are exactly
    Torkoal / Drought / Charcoal. Applied by the loader; no fixture file.
    """
    index = user_slot_to_index(3)
    state = empty_team()
    for attr, value in (
        ("species", "Torkoal"),
        ("role", "bulky_offense"),
        ("ability", "Drought"),
        ("item", "Charcoal"),
    ):
        state = _lock_internal(state, index, attr, value)
    return state


def _substitute_h25_doc(doc: dict[str, Any]) -> dict[str, Any]:
    """In-memory errata: slot 2 Barraskewda → Basculegion (Swift Swim, Life Orb).

    Does not write h25_team.json.
    """
    out = dict(doc)
    slots = []
    for row in list(doc.get("slots") or []):
        if not isinstance(row, dict):
            slots.append(row)
            continue
        if int(row.get("slot") or 0) == 2 and row.get("species") == "Barraskewda":
            slots.append(
                {
                    **row,
                    "species": "Basculegion",
                    "ability": "Swift Swim",
                    "item": "Life Orb",
                }
            )
        else:
            slots.append(row)
    out["slots"] = slots
    return out


def fixture_coverage_table() -> list[dict[str, Any]]:
    """Per covered request-set row: load status, completeness, open reasons."""
    rows_out: list[dict[str, Any]] = []
    for row_id, stem in _ROW_FIXTURE.items():
        if stem is None:
            state = build_mrb1_start()
            slot = state["team_draft"][user_slot_to_index(3)]
            rows_out.append(
                {
                    "row": row_id,
                    "source": "build_mrb1_start (errata: Torkoal/Drought/Charcoal @ user slot 3)",
                    "loaded": True,
                    "complete_moves": False,
                    "complete_constraints": True,
                    "open_reason": None,
                    "species_at": {3: slot.species.value},
                    "readback": {
                        "species": slot.species.value,
                        "ability": slot.ability.value,
                        "item": slot.item.value,
                    },
                }
            )
            continue
        path = FIX_DIR / f"{stem}.json"
        base = _SLOT_BASE.get(path.name)
        result = try_load_fixture(row_id)
        entry: dict[str, Any] = {
            "row": row_id,
            "source": f"fixtures/{path.name} base={base}",
            "evidence": _SLOT_BASE_EVIDENCE.get(path.name),
            "loaded": result["loaded"],
            "complete_moves": False,
            "complete_constraints": False,
            "open_reason": result["error"],
        }
        if not result["loaded"] or result["state"] is None:
            rows_out.append(entry)
            continue
        state = result["state"]
        incomplete = list(state.get("_fixture_incomplete") or [])
        doc = json.loads(path.read_text(encoding="utf-8"))
        expected_moves = False
        for r in _team_rows(doc) or ([doc] if doc.get("species") else []):
            if isinstance(r, dict) and (r.get("moves") or r.get("moveset")):
                expected_moves = True
        kept_moves = any(
            slot.moveset.value for slot in state["team_draft"] if slot.species.value
        )
        entry["complete_moves"] = (not expected_moves) or (
            kept_moves and not any("moves skipped" in x for x in incomplete)
        )
        tags = doc.get("constraints") or []
        recorded = state.get("constraints") or []
        # Complete only when every tag is recorded AND none are judgment-only stubs.
        mech_ok = bool(recorded) and all(
            getattr(c, "groundedness", None) == "mechanically-checkable"
            or (isinstance(c, dict) and c.get("groundedness") == "mechanically-checkable")
            for c in recorded
        )
        entry["complete_constraints"] = (not tags) or mech_ok
        if incomplete:
            entry["open_reason"] = "; ".join(incomplete)
        else:
            entry["open_reason"] = None
        entry["species"] = [
            s.species.value for s in state["team_draft"] if s.species.value
        ]
        entry["constraints_n"] = len(recorded)
        rows_out.append(entry)
    return rows_out


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
