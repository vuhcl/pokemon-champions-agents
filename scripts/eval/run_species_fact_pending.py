#!/usr/bin/env python3
"""Live Ollama baseline: species-fact claims in pending_response clarification text.

Requires unfixed code (no rewrite_pending_response_message). Fail-closed otherwise.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recommender.cli import handle_line  # noqa: E402
from recommender.graph import compile_cli_graph  # noqa: E402
from recommender.llm_provider import resolve_llm_parsers  # noqa: E402
from recommender.session import mint_thread_id, thread_config  # noqa: E402
from recommender.turn_intent import CLASSIFY_FAIL_USER_MSG, parse_turn_intent  # noqa: E402
from scripts.eval import scenarios_species_fact as scen  # noqa: E402
from scripts.eval.species_fact_oracle import Claim, parse_claims  # noqa: E402
from scripts.eval.species_fact_oracle import _assert_self_check  # noqa: E402

VGC = "[Gen 9 Champions] VGC 2026 Reg M-B"
MAX_TURNS = 32
TARGET_SITES = (
    "idle",
    "candidate_selection",
    "completion_preference",
    "full_build_confirmation",
)

CANNED_MESSAGES: frozenset[str] = frozenset(
    {
        CLASSIFY_FAIL_USER_MSG,
        "That action isn't available here.",
        "That sounds like two requests in one — an edit and a comparison. "
        "Which would you like first?",
        "That sounds like two requests in one — an edit and a selection. "
        "Which would you like first?",
        "That took too long to process — please try again, ideally with a "
        "shorter or simpler message.",
    }
)

Elicitation = Literal["organic", "seeded"]


@dataclass
class PendingRecord:
    call_site: str
    elicitation: str
    user_text: str
    message: str
    authorship: str
    claims: list[dict[str, Any]] = field(default_factory=list)


def _abort_if_guarded() -> None:
    import inspect

    import recommender.system_claims as sc
    import recommender.turn_intent as ti

    if hasattr(sc, "rewrite_pending_response_message"):
        print(
            "ABORT: rewrite_pending_response_message present — not BASELINE tree.",
            file=sys.stderr,
        )
        sys.exit(2)
    if "rewrite_pending_response_message" in inspect.getsource(ti._payload_for):
        print("ABORT: _payload_for references rewrite guard.", file=sys.stderr)
        sys.exit(2)


def _call_site(pending: dict[str, Any] | None) -> str:
    if pending is None:
        return "idle"
    kind = str(pending.get("kind") or "")
    if kind in TARGET_SITES:
        return kind
    return "other"


def _pending_message(state: dict[str, Any]) -> str | None:
    if state.get("turn_intent") != "pending_response":
        return None
    payload = state.get("turn_payload")
    if not isinstance(payload, dict):
        return None
    msg = payload.get("message")
    return msg if isinstance(msg, str) and msg.strip() else None


def _claims_payload(claims: list[Claim]) -> list[dict[str, Any]]:
    return [
        {
            "kind": c.kind,
            "species": c.species,
            "asserted_value": c.asserted_value,
            "verdict": c.verdict,
            "display": c.display,
        }
        for c in claims
    ]


def main() -> int:
    _abort_if_guarded()
    _assert_self_check()

    os.environ.setdefault("BOOTSTRAP_OLLAMA_MODEL", "qwen2.5:7b")
    os.environ.setdefault("POKEMON_CHAMPIONS_LLM_PROVIDER", "ollama")
    model = os.environ["BOOTSTRAP_OLLAMA_MODEL"]

    bootstrap, turn_parser, warning = resolve_llm_parsers("ollama")
    if warning:
        print(warning, file=sys.stderr)
    if turn_parser is None or bootstrap is None:
        print("ABORT: Ollama parsers not configured.", file=sys.stderr)
        return 2

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name

    graph, saver = compile_cli_graph(
        path=db_path,
        bootstrap_intake_parser=bootstrap,
        turn_intent_parser=turn_parser,
    )
    thread_id = mint_thread_id()
    config = thread_config(thread_id)
    state: dict[str, Any] = dict(graph.invoke({"format_id": VGC}, config=config))

    records: list[PendingRecord] = []
    site_elicitation: dict[str, Elicitation] = {s: "organic" for s in TARGET_SITES}
    site_elicitation["other"] = "organic"
    attempts: dict[str, int] = defaultdict(int)
    elicit_left: dict[str, list[str]] = {k: list(v) for k, v in scen.ELICIT.items()}
    # How many elicit tries already fired at current visit to a site
    visit_elicits: dict[str, int] = defaultdict(int)
    force_pref_used = False
    locks_before_idle_push = 0
    notes: list[str] = []

    def send(text: str) -> None:
        nonlocal state, config, thread_id
        before = state.get("pending_presentation")
        site = _call_site(before if isinstance(before, dict) else None)
        attempts[site] += 1
        print(f">>> [{site}] {text}", file=sys.stderr)
        state_m, config, thread_id, _display, _quit = handle_line(
            graph,
            config,
            state,
            text,
            format_id=VGC,
            thread_id=thread_id,
        )
        state = dict(state_m)
        msg = _pending_message(state)
        if msg is not None:
            authorship = "canned" if msg.strip() in CANNED_MESSAGES else "llm_authored"
            claims = parse_claims(msg) if authorship == "llm_authored" else []
            records.append(
                PendingRecord(
                    call_site=site,
                    elicitation=site_elicitation.get(site, "organic"),
                    user_text=text,
                    message=msg,
                    authorship=authorship,
                    claims=_claims_payload(claims),
                )
            )
            print(
                f"<<< pending_response ({authorship}, claims={len(claims)}): "
                f"{msg[:140]!r}",
                file=sys.stderr,
            )

    def site_has_llm(site: str) -> bool:
        return any(
            r.call_site == site and r.authorship == "llm_authored" for r in records
        )

    send(scen.SETUP)

    for turn in range(1, MAX_TURNS + 1):
        pending = state.get("pending_presentation")
        kind = pending.get("kind") if isinstance(pending, dict) else None
        site = _call_site(pending if isinstance(pending, dict) else None)

        # Up to 2 elicit attempts per visit to a target site
        if site in elicit_left and elicit_left[site] and visit_elicits[site] < 2:
            visit_elicits[site] += 1
            send(elicit_left[site].pop(0))
            continue

        if kind == "candidate_selection":
            visit_elicits["candidate_selection"] = 0
            send(scen.PICK)
            continue

        if kind == "full_build_confirmation":
            visit_elicits["full_build_confirmation"] = 0
            # Affirm to lock and progress (avoid defer thrash)
            send(scen.YES)
            locks_before_idle_push += 1
            continue

        if kind == "completion_preference":
            if elicit_left["completion_preference"] and visit_elicits[site] < 2:
                visit_elicits[site] += 1
                send(elicit_left["completion_preference"].pop(0))
                continue
            visit_elicits["completion_preference"] = 0
            send(scen.PICK)
            continue

        if kind == "bootstrap_intake":
            send(scen.SETUP)
            continue

        # idle / other
        if site == "idle":
            missing_llm = [s for s in TARGET_SITES if not site_has_llm(s)]
            if (
                "completion_preference" in missing_llm
                and not force_pref_used
            ):
                force_pref_used = True
                site_elicitation["completion_preference"] = "seeded"
                notes.append(
                    "completion_preference seeded via force_completion_preference_prompt"
                )
                graph.update_state(
                    config, {"force_completion_preference_prompt": True}
                )
                state = dict(graph.get_state(config).values)
                visit_elicits["completion_preference"] = 0
                send(scen.CONTINUE)
                continue
            if elicit_left["idle"] and visit_elicits["idle"] < 2:
                visit_elicits["idle"] += 1
                send(elicit_left["idle"].pop(0))
                continue
            # Need idle llm message? try remaining idle elicits without visit cap
            if "idle" in missing_llm and elicit_left["idle"]:
                send(elicit_left["idle"].pop(0))
                continue
            send(scen.CONTINUE)
            continue

        # Unknown pending: clear with defer once then continue
        send(scen.DEFER)
        visit_elicits = defaultdict(int)

        if turn >= 28 and all(site_has_llm(s) for s in TARGET_SITES):
            break

    # Phase 2: targeted gap-fill probes (same live turn_intent_parser).
    # Graph turns alone under-produced claim-bearing clarifications on qwen2.5:7b.
    notes.append(
        "Phase 2: targeted parse_turn_intent probes after graph conversation "
        "(same Ollama parser; not classify_pending mock)."
    )
    for pending_kind, ctx, phrases in scen.GAP_FILL_PROBES:
        site = "idle" if pending_kind == "none" else pending_kind
        for phrase in phrases:
            attempts[site] += 1
            out = parse_turn_intent(
                turn_parser,
                user_text=phrase,
                pending_kind=pending_kind,
                pending_context=ctx,
                roster_summary="Hatterene locked",
                last_system_claim="",
                had_pending=pending_kind != "none",
            )
            if out.get("turn_intent") != "pending_response":
                print(
                    f"probe skip [{site}] intent={out.get('turn_intent')} {phrase!r}",
                    file=sys.stderr,
                )
                continue
            msg = (out.get("turn_payload") or {}).get("message")
            if not isinstance(msg, str) or not msg.strip():
                continue
            authorship = (
                "canned" if msg.strip() in CANNED_MESSAGES else "llm_authored"
            )
            claims = parse_claims(msg) if authorship == "llm_authored" else []
            records.append(
                PendingRecord(
                    call_site=site,
                    elicitation=site_elicitation.get(site, "organic"),
                    user_text=phrase,
                    message=msg,
                    authorship=authorship,
                    claims=_claims_payload(claims),
                )
            )
            print(
                f"probe [{site}] ({authorship}, claims={len(claims)}): {msg[:140]!r}",
                file=sys.stderr,
            )

    # Aggregates
    llm = [r for r in records if r.authorship == "llm_authored"]
    canned = [r for r in records if r.authorship == "canned"]
    claim_bearing = [r for r in llm if r.claims]
    all_claims = [c for r in llm for c in r.claims]
    by_verdict: dict[str, int] = defaultdict(int)
    for c in all_claims:
        by_verdict[c["verdict"]] += 1

    per_site: dict[str, Any] = {}
    for site_name in [*TARGET_SITES, "other"]:
        site_recs = [r for r in records if r.call_site == site_name]
        site_llm = [r for r in site_recs if r.authorship == "llm_authored"]
        site_claims = [c for r in site_llm for c in r.claims]
        v: dict[str, int] = defaultdict(int)
        for c in site_claims:
            v[c["verdict"]] += 1
        per_site[site_name] = {
            "elicitation": site_elicitation.get(site_name, "organic"),
            "attempts": attempts.get(site_name, 0),
            "pending_response_total": len(site_recs),
            "llm_authored": len(site_llm),
            "canned": len(site_recs) - len(site_llm),
            "claim_bearing_messages": len([r for r in site_llm if r.claims]),
            "claims_total": len(site_claims),
            "TRUE": v["TRUE"],
            "FALSE": v["FALSE"],
            "unverifiable_shape": v["unverifiable_shape"],
        }

    summary = {
        "label": "BASELINE",
        "model": model,
        "force_completion_preference_prompt": force_pref_used,
        "notes": notes,
        "message_level": {
            "pending_response_total": len(records),
            "llm_authored": len(llm),
            "canned": len(canned),
            "claim_bearing_messages": len(claim_bearing),
        },
        "claim_level": {
            "claims_total": len(all_claims),
            "TRUE": by_verdict["TRUE"],
            "FALSE": by_verdict["FALSE"],
            "unverifiable_shape": by_verdict["unverifiable_shape"],
        },
        "per_call_site": per_site,
        "false_claims": [
            {
                **c,
                "call_site": r.call_site,
                "message": r.message,
            }
            for r in llm
            for c in r.claims
            if c["verdict"] == "FALSE"
        ],
        "records": [asdict(r) for r in records],
    }
    out_path = ROOT / "scripts" / "eval" / "artifacts" / "species_fact_baseline.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in summary if k != "records"}, indent=2))
    print(f"Wrote {out_path}", file=sys.stderr)

    try:
        saver.conn.close()
    except Exception:
        pass
    try:
        os.unlink(db_path)
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
