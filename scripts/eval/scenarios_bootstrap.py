"""Bootstrap tier census + Layer 2 named harness scenarios (ADR-063)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from recommender.bootstrap import _direction_phrase_examples, discover_bootstrap_directions
from recommender.ids import to_id
from recommender.nodes import initialize, record_bootstrap_response
from recommender.present_text import _format_option_role_bit
from scripts.eval.harness import (
    VGC_MC,
    bootstrap_once_and_stop,
    run_scenario,
    turn,
)

ROOT = Path(__file__).resolve().parents[2]
DIFF_FIXTURE = ROOT / "data/legality/fixtures/championsregmb_to_champions.diff.json"
LEGALITY_SNAP = ROOT / "data/legality/champions.v1.json"
VGC_MB = "[Gen 9 Champions] VGC 2026 Reg M-B"

TierClass = Literal["tier1", "tier2", "tier3", "pre_tier"]


def load_became_legal_ids() -> list[str]:
    data = json.loads(DIFF_FIXTURE.read_text(encoding="utf-8"))
    ids = [
        str(row["id"])
        for row in data.get("species") or []
        if row.get("change") == "became_legal" and row.get("id")
    ]
    if len(ids) != 35:
        raise RuntimeError(f"expected 35 became_legal species, got {len(ids)}")
    return ids


def display_name_for_id(species_id: str, *, snap: dict[str, Any] | None = None) -> str:
    snap = snap or json.loads(LEGALITY_SNAP.read_text(encoding="utf-8"))
    entry = (snap.get("species") or {}).get(to_id(species_id))
    if not entry or not entry.get("name"):
        raise RuntimeError(f"no display name in legality snap for id={species_id!r}")
    return str(entry["name"])


def _state() -> dict[str, Any]:
    raw: dict[str, Any] = {"format_id": VGC_MB}
    return {**raw, **initialize(raw)}


def _payload(*, anchor: str) -> dict[str, Any]:
    return {
        "direction_text": None,
        "anchor_text": anchor,
        "pool_entries": None,
        "delegated": False,
        "ownership_mode": None,
    }


def _record(state: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    return {
        **state,
        **record_bootstrap_response({**state, "turn_payload": payload}),
    }


def classify_discovery(discovery) -> tuple[TierClass, str | None, str | None]:
    """Return (tier, producer_or_None, clarification_or_None)."""
    clarification = discovery.clarification
    if not discovery.candidates:
        return "tier3", None, clarification
    decision = discovery.candidates[0].target_role_decision
    producer = getattr(decision, "producer_name", None) if decision is not None else None
    if producer == "bootstrap_kit_role_policy":
        return "tier1", producer, clarification
    if producer == "bootstrap_movepool_family_nn":
        return "tier2", producer, clarification
    return "pre_tier", producer, clarification


def census_one(species_id: str, *, snap: dict[str, Any]) -> dict[str, Any]:
    name = display_name_for_id(species_id, snap=snap)
    state = _record(_state(), _payload(anchor=name))
    discovery = discover_bootstrap_directions(state)
    tier, producer, clarification = classify_discovery(discovery)
    first = discovery.candidates[0] if discovery.candidates else None
    return {
        "id": species_id,
        "name": name,
        "tier": tier,
        "producer_name": producer,
        "role_id": getattr(getattr(first, "target_role_decision", None), "role_id", None)
        if first
        else None,
        "candidate_species": first.species if first else None,
        "clarification": clarification,
    }


def _decision_fields(option: dict[str, Any]) -> tuple[Any, Any, tuple]:
    trd = option.get("target_role_decision")
    if trd is None:
        return None, None, ()
    role_id = getattr(trd, "role_id", None)
    if role_id is None and isinstance(trd, dict):
        role_id = trd.get("role_id")
    producer = getattr(trd, "producer_name", None)
    if producer is None and isinstance(trd, dict):
        producer = trd.get("producer_name")
    evidence = getattr(trd, "evidence", None)
    if evidence is None and isinstance(trd, dict):
        evidence = trd.get("evidence")
    return role_id, producer, tuple(evidence or ())


# Layer 2 named cases: (id, species, bucket, expected_role_id|None, soft_neighbor|None)
NAMED_CASES: list[tuple[str, str, str, str | None, str | None]] = [
    ("writeup_baxcalibur", "Baxcalibur", "writeup", "standard_physical_attacker", None),
    ("writeup_pawmot", "Pawmot", "writeup", "fast_physical_attacker", None),
    ("writeup_baxcalibur_mega", "Baxcalibur-Mega", "writeup", "standard_physical_attacker", None),
    ("nn_sirfetchd", "Sirfetch’d", "nn_clean", "swords_dance_attacker", "Scizor"),
    ("nn_toxtricity", "Toxtricity", "nn_clean", "fast_pivot", "Simipour"),
    ("nn_toxtricity_low_key", "Toxtricity-Low-Key", "nn_clean", "fast_pivot", None),
    ("nn_swalot", "Swalot", "nn_clean", "swords_dance_attacker", "Scizor"),
    ("nn_persian", "Persian", "nn_clean", "fast_pivot", None),
    ("thin_gogoat", "Gogoat", "thin_ref", None, None),
    ("thin_grapploct", "Grapploct", "thin_ref", None, None),
    ("hard_cinderace", "Cinderace", "hard_multi", None, None),
    ("hard_salamence", "Salamence", "hard_multi", None, None),
    ("fail_msg_mabosstiff", "Mabosstiff", "fail_closed_msg", None, None),
]


def _assert_fail_closed(row: dict[str, Any], *, require_examples: bool = False) -> list[str]:
    fails: list[str] = []
    if row["terminal"] != "fail_closed":
        fails.append(f"terminal={row['terminal']!r} want fail_closed")
        return fails
    msg = row.get("error_message") or ""
    if "Couldn't resolve a starting role" not in msg and "Couldn't identify" not in msg:
        # role-resolution fail-closed still carries clarification in error
        if "Couldn't resolve" not in msg and "Name a direction" not in msg:
            fails.append(f"unexpected fail message: {msg[:120]!r}")
    if require_examples:
        examples = _direction_phrase_examples()
        if examples not in msg:
            fails.append("missing _direction_phrase_examples in message")
        if "standard_" in msg:
            fails.append("message contains standard_ role ids")
    return fails


def _accept_first_and_inspect_provisional(graph, config, state: dict[str, Any]) -> dict[str, Any]:
    pending = state.get("pending_presentation") or {}
    options = pending.get("options") or []
    if not options:
        return {"ok": False, "detail": "no options to accept"}
    state = turn(
        graph,
        config,
        {
            "turn_intent": "slot_candidate_selected",
            "selected_option": options[0],
        },
    )
    provisional = state.get("provisional_slot")
    if provisional is None:
        return {"ok": False, "detail": "no provisional_slot after select", "state_keys": list(state)}
    label = getattr(provisional, "ability_source_label", None)
    if label is None and isinstance(provisional, dict):
        label = provisional.get("ability_source_label")
    spread = None
    if hasattr(provisional, "spread_dict"):
        spread = provisional.spread_dict()
    elif hasattr(provisional, "spread"):
        spread = provisional.spread
    elif isinstance(provisional, dict):
        spread = provisional.get("spread")
    spread_sum = sum((spread or {}).values()) if isinstance(spread, dict) else None
    return {
        "ok": True,
        "ability_source_label": label,
        "spread": spread,
        "spread_sum": spread_sum,
        "pending_kind": (state.get("pending_presentation") or {}).get("kind"),
    }


def run_named_case(
    case_id: str,
    species: str,
    bucket: str,
    expected_role: str | None,
    soft_neighbor: str | None,
) -> dict[str, Any]:
    payload = _payload(anchor=species)

    def runner(graph, config, state):
        state, terminal = bootstrap_once_and_stop(graph, config, state, payload)
        from scripts.eval.harness import ScenarioResult, locked_pairs

        notes_parts: list[str] = []
        err = state.get("candidate_discovery_error")
        err_msg = ""
        if err is not None:
            err_msg = str(getattr(err, "message", None) or "")
            if not err_msg and isinstance(err, dict):
                err_msg = str(err.get("message") or "")
        pending = state.get("pending_presentation") or {}
        if not err_msg and pending.get("notices"):
            err_msg = " | ".join(str(n) for n in pending.get("notices") or ())

        option = (pending.get("options") or [None])[0]
        role_id = producer = None
        evidence: tuple = ()
        role_bit = None
        if isinstance(option, dict):
            role_id, producer, evidence = _decision_fields(option)
            role_bit = _format_option_role_bit(option.get("target_role_decision"))

        checks: list[str] = []
        provisional_info: dict[str, Any] | None = None
        soft: list[str] = []

        if bucket in {"thin_ref", "hard_multi"}:
            checks.extend(_assert_fail_closed({"terminal": terminal, "error_message": err_msg}))
        elif bucket == "fail_closed_msg":
            checks.extend(
                _assert_fail_closed(
                    {"terminal": terminal, "error_message": err_msg},
                    require_examples=True,
                )
            )
        elif bucket in {"writeup", "nn_clean"}:
            if terminal != "candidates_ready":
                checks.append(f"terminal={terminal!r} want candidates_ready")
            else:
                want_producer = (
                    "bootstrap_kit_role_policy"
                    if bucket == "writeup"
                    else "bootstrap_movepool_family_nn"
                )
                if producer != want_producer:
                    checks.append(f"producer={producer!r} want {want_producer}")
                if expected_role and role_id != expected_role:
                    checks.append(f"role_id={role_id!r} want {expected_role}")
                if bucket == "nn_clean":
                    has_nn = any(
                        isinstance(t, str) and t.startswith("nn_similar:") for t in evidence
                    )
                    has_similar = role_bit is not None and "similar to" in role_bit
                    if not (has_nn or has_similar):
                        checks.append("missing nn_similar evidence / similar-to role bit")
                    if soft_neighbor:
                        if not any(
                            isinstance(t, str) and t.startswith(f"nn_similar:{soft_neighbor}:")
                            for t in evidence
                        ):
                            soft.append(f"soft neighbor miss: want nn_similar:{soft_neighbor}:")
                if bucket == "writeup":
                    provisional_info = _accept_first_and_inspect_provisional(
                        graph, config, state
                    )
                    if not provisional_info.get("ok"):
                        checks.append(f"provisional: {provisional_info.get('detail')}")
                    else:
                        label = str(provisional_info.get("ability_source_label") or "")
                        if species == "Baxcalibur-Mega":
                            if "base Baxcalibur" not in label:
                                checks.append(f"mega disclosure missing in {label!r}")
                        elif "writeup" not in label.lower():
                            checks.append(f"writeup label missing in {label!r}")
                        ssum = provisional_info.get("spread_sum")
                        if ssum != 66:
                            checks.append(f"spread_sum={ssum} want 66")

        passed = not checks
        notes_parts.append("PASS" if passed else "FAIL: " + "; ".join(checks))
        return ScenarioResult(
            scenario_id=case_id,
            path=bucket,
            terminal=terminal,
            pairs=locked_pairs(state),
            state={
                "role_id": role_id,
                "producer_name": producer,
                "evidence": list(evidence),
                "role_bit": role_bit,
                "error_message": err_msg,
                "provisional": provisional_info,
                "soft": soft,
                "checks": checks,
                "passed": passed,
            },
            notes=" | ".join(notes_parts),
        )

    result = run_scenario(case_id, bucket, runner, format_id=VGC_MC)
    return {
        "id": case_id,
        "species": species,
        "bucket": bucket,
        "terminal": result.terminal,
        "passed": bool((result.state or {}).get("passed")),
        "checks": (result.state or {}).get("checks") or [],
        "soft": (result.state or {}).get("soft") or [],
        "role_id": (result.state or {}).get("role_id"),
        "producer_name": (result.state or {}).get("producer_name"),
        "role_bit": (result.state or {}).get("role_bit"),
        "error_message": (result.state or {}).get("error_message"),
        "provisional": (result.state or {}).get("provisional"),
        "notes": result.notes,
    }


def run_all_named() -> list[dict[str, Any]]:
    return [run_named_case(*row) for row in NAMED_CASES]
