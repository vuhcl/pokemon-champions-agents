#!/usr/bin/env python3
"""Offline Laya turn_intent spike — label-only arms, gates (a)–(d).

Usage:
  RECOMMENDER_TOOL_LOG=scripts/eval/artifacts/laya_intent_spike/tool_calls.jsonl \\
    uv run --extra laya --extra ollama python scripts/eval/run_laya_intent_spike.py

Optional:
  LAYA_DEVICE=mps|cpu
  LAYA_SPIKE_SKIP_LLM=1   # debug only; fails gate (b) closed
  LAYA_SPIKE_QUICK=1      # fewer latency repeats
"""

from __future__ import annotations

import json
import os
import resource
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA = ROOT / "scripts/eval/data/laya_turn_intent"
ART = ROOT / "scripts/eval/artifacts/laya_intent_spike"

TURN_INTENTS = (
    "constraint",
    "rejection",
    "lock",
    "archetype_change",
    "reset",
    "restore",
    "restore_constraint",
    "continue",
    "team_review",
    "pending_response",
    "edit",
    "select_build_option",
    "compare",
    "revise_locked_slot",
    "repick_locked_slot",
    "claim_correction",
)

CRITERIA = {
    "constraint": "hard or soft team/slot requirement (typing, items, preference)",
    "rejection": "ban or reject a species from candidates or this build",
    "lock": "lock a species or attribute onto a roster slot",
    "archetype_change": "pivot strategy weather/trick room/tailwind/sun/rain",
    "reset": "wipe the draft and start over",
    "restore": "undo a superseded slot attribute (species/item/etc)",
    "restore_constraint": "restore a previously superseded hard constraint rule",
    "continue": "proceed / keep going / next slot without changing this build detail",
    "team_review": "show or review the current locked roster",
    "pending_response": "ambiguous or clarifying question needed",
    "edit": "change ability/item/moves/nature/spread on the provisional full-build",
    "select_build_option": "pick a numbered or named build option from the menu",
    "compare": "compare two or more build options without committing",
    "revise_locked_slot": "edit a field on an already-locked roster slot",
    "repick_locked_slot": "replace the species on an already-locked roster slot",
    "claim_correction": "dispute a factual claim the bot just made",
}

QUESTIONS = {
    "intent": {
        "type": "choice",
        "instructions": (
            "Classify the user's turn into exactly one existing turn_intent label."
        ),
        "criteria": CRITERIA,
    }
}

PAYLOAD_FREE = frozenset(
    {"continue", "team_review", "restore_constraint", "reset"}
)


def _fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)


def load_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in ("dev.jsonl", "held_out.jsonl"):
        path = DATA / name
        if not path.exists():
            _fail(f"missing {path}; run write_jsonl.py first")
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def check_floors(rows: list[dict[str, Any]]) -> None:
    probe_n: Counter[str] = Counter()
    probe_h: Counter[str] = Counter()
    pair_n: Counter[str] = Counter()
    pair_h: Counter[str] = Counter()
    pair_dirs: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        pid = row.get("probe_id")
        if pid:
            probe_n[pid] += 1
            if row["split"] == "held_out":
                probe_h[pid] += 1
        pair = row.get("pair_id")
        if pair:
            pair_n[pair] += 1
            pair_dirs[pair].add(row["gold_intent"])
            if row["split"] == "held_out":
                pair_h[pair] += 1
    bad: list[str] = []
    for pid, n in probe_n.items():
        if n < 3 or probe_h[pid] < 2:
            bad.append(f"probe {pid} n={n} held={probe_h[pid]}")
    for pid, n in pair_n.items():
        if n < 3 or pair_h[pid] < 2 or len(pair_dirs[pid]) < 2:
            bad.append(
                f"pair {pid} n={n} held={pair_h[pid]} dirs={sorted(pair_dirs[pid])}"
            )
    if bad:
        _fail("gate (a) floors unmet — refuse to score:\n  " + "\n  ".join(bad))


def state_for(row: dict[str, Any]) -> dict[str, str]:
    parts = [
        f"pending_kind: {row.get('pending_kind') or 'none'}",
        f"pending_context: {row.get('pending_context') or ''}",
        f"roster_summary: {row.get('roster_summary') or ''}",
        f"last_system_claim: {row.get('last_system_claim') or ''}",
        f"user_text: {row['user_text']}",
    ]
    return {"text": "\n".join(parts)}


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def majority_arm(held_residual: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mode = Counter(r["gold_intent"] for r in held_residual).most_common(1)[0][0]
    out = []
    for row in held_residual:
        out.append(
            {
                "id": row["id"],
                "gold": row["gold_intent"],
                "pred": mode,
                "ok": row["gold_intent"] == mode,
                "arm": "majority",
            }
        )
    return out


def deterministic_arm(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from recommender.nodes_classify import (
        _try_deterministic_claim_correction,
        classify_pending,
    )
    from recommender.system_claims import negation_matches_claim

    def boom(_payload: Any) -> Any:
        raise RuntimeError("turn_intent_parser must not be called")

    from langchain_core.runnables import RunnableLambda

    stub = RunnableLambda(boom)
    out: list[dict[str, Any]] = []
    for row in rows:
        kind = row.get("pending_kind") or "none"
        gold = row["gold_intent"]
        preempt = bool(row.get("deterministic_preempt"))
        pred: str
        if kind == "none":
            claim = _parse_claim(row.get("last_system_claim") or "")
            if claim is not None:
                hit = _try_deterministic_claim_correction(row["user_text"], claim)
                if hit is not None:
                    pred = str(hit.get("turn_intent"))
                else:
                    pred = "unhandled"
            else:
                pred = "unhandled"
        elif kind == "confirm_abandon_build":
            pending = {
                "schema_version": 1,
                "kind": "confirm_abandon_build",
                "queued_turn_intent": "continue",
                "queued_turn_payload": None,
                "held_pending": {
                    "schema_version": 1,
                    "kind": "full_build_confirmation",
                    "slot_index": 0,
                    "provisional_fingerprint": "fp",
                },
            }
            result = classify_pending(row["user_text"], pending, turn_intent_parser=stub)
            pred = str(result.get("turn_intent"))
        elif kind == "full_build_confirmation":
            pending = _synthetic_fbc(row.get("pending_context") or "")
            try:
                result = classify_pending(
                    row["user_text"], pending, turn_intent_parser=stub
                )
                pred = str(result.get("turn_intent"))
            except Exception:
                pred = "unhandled"
        elif kind == "candidate_selection":
            pending = _synthetic_candidate(row.get("pending_context") or "")
            try:
                result = classify_pending(
                    row["user_text"], pending, turn_intent_parser=stub
                )
                pred = str(result.get("turn_intent"))
            except Exception:
                pred = "unhandled"
        elif kind == "completion_preference":
            pending = {
                "schema_version": 2,
                "kind": "completion_preference",
                "preference_options": ("attacker", "support", "balanced"),
            }
            try:
                result = classify_pending(
                    row["user_text"], pending, turn_intent_parser=stub
                )
                pred = str(result.get("turn_intent"))
            except Exception:
                pred = "unhandled"
        else:
            pred = "unhandled"

        if preempt:
            ok = pred == gold
        else:
            ok = pred == "unhandled"
        out.append(
            {
                "id": row["id"],
                "gold": gold,
                "pred": pred,
                "ok": ok,
                "arm": "deterministic",
                "preempt": preempt,
                "negation_matches": (
                    negation_matches_claim(row["user_text"], claim)
                    if kind == "none" and (claim := _parse_claim(row.get("last_system_claim") or ""))
                    else False
                ),
            }
        )
    return out


def _parse_claim(serialized: str) -> dict[str, Any] | None:
    if not serialized.strip():
        return None
    # Our dataset uses a compact non-JSON serialization.
    parts = dict(
        p.split("=", 1) for p in serialized.split("; ") if "=" in p
    )
    kind = parts.get("kind")
    if kind not in {"type", "ability", "item"}:
        return None
    from recommender.state import SystemClaim

    claim: SystemClaim = {
        "turn": 1,
        "kind": kind,  # type: ignore[typeddict-item]
        "subject_species": parts.get("subject") or "",
        "asserted_value": parts.get("asserted") or "",
        "source": "pending_response_message",
        "display_excerpt": parts.get("excerpt") or "",
        "verifiable": True,
        "originating_user_text": "",
    }
    return claim


def _synthetic_fbc(ctx: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "full_build_confirmation",
        "slot_index": 0,
        "provisional_fingerprint": "fp1",
        "build_option_groups": (
            {
                "axis": "spread_nature",
                "options": (
                    {"option_id": "spread_nature:1", "label": "Modest bulky"},
                    {"option_id": "spread_nature:2", "label": "Timid max Spe"},
                ),
            },
            {
                "axis": "item",
                "options": (
                    {"option_id": "item:1", "label": "Damp Rock"},
                    {"option_id": "item:2", "label": "Focus Sash"},
                ),
            },
            {
                "axis": "moveset",
                "options": (
                    {
                        "option_id": "moveset:1",
                        "label": "Hurricane / Weather Ball / Protect / Tailwind",
                    },
                ),
            },
        ),
        "_ctx": ctx,
    }


def _synthetic_candidate(ctx: str) -> dict[str, Any]:
    names = ["Heliolisk", "Abomasnow", "Whimsicott"]
    return {
        "schema_version": 1,
        "kind": "candidate_selection",
        "options": [{"species": n, "option_id": str(i + 1)} for i, n in enumerate(names)],
        "_ctx": ctx,
    }


def laya_predict(agent: Any, row: dict[str, Any], *, criteria: dict[str, str]) -> tuple[str, float, float]:
    from recommender.tool_log import timed_tool_call

    questions = {
        "intent": {
            "type": "choice",
            "instructions": QUESTIONS["intent"]["instructions"],
            "criteria": criteria,
        }
    }
    state = state_for(row)

    def _run() -> Any:
        return agent.predict(state, questions)

    t0 = time.perf_counter()
    result = timed_tool_call(
        "laya.turn_intent",
        {"id": row["id"], "pending_kind": row.get("pending_kind")},
        _run,
    )
    latency = (time.perf_counter() - t0) * 1000
    ans = result["answers"]["intent"]
    return str(ans["choice"]), float(ans.get("confidence") or 0.0), latency


def llm_predict(parser: Any, row: dict[str, Any]) -> tuple[str, float]:
    from recommender.turn_intent import parse_turn_intent

    t0 = time.perf_counter()
    result = parse_turn_intent(
        parser,
        user_text=row["user_text"],
        pending_kind=row.get("pending_kind") or "none",
        pending_context=row.get("pending_context") or "",
        roster_summary=row.get("roster_summary") or "",
        last_system_claim=row.get("last_system_claim") or "",
        had_pending=(row.get("pending_kind") or "none") != "none",
    )
    latency = (time.perf_counter() - t0) * 1000
    return str(result.get("turn_intent")), latency


def accuracy(preds: list[dict[str, Any]]) -> float:
    if not preds:
        return 0.0
    return sum(1 for p in preds if p["ok"]) / len(preds)


def confusion(preds: list[dict[str, Any]]) -> dict[str, Counter[str]]:
    matrix: dict[str, Counter[str]] = defaultdict(Counter)
    for p in preds:
        matrix[p["gold"]][p["pred"]] += 1
    return {g: dict(c) for g, c in matrix.items()}


def score_gate_a(rows: list[dict[str, Any]], preds_by_id: dict[str, str]) -> dict[str, Any]:
    """Zero-tolerance on catalog rows: wrong label that matches the inverted partner fails."""
    failures: list[dict[str, Any]] = []
    checked = 0
    for row in rows:
        if row["split"] != "held_out":
            continue
        if not row.get("pair_id") and not row.get("probe_id"):
            continue
        if "gate_a" not in (row.get("tags") or []) and not (
            row.get("pair_id") or row.get("probe_id")
        ):
            continue
        # Score all catalog-tagged held_out rows (probe_id or pair_id)
        if not (row.get("pair_id") or row.get("probe_id")):
            continue
        gold = row["gold_intent"]
        pred = preds_by_id.get(row["id"])
        checked += 1
        if pred is None:
            failures.append({"id": row["id"], "reason": "missing_pred"})
            continue
        if pred == gold:
            continue
        # Dangerous if predicted the paired opposite, or any wrong label on gate_a tags
        pair = row.get("pair_id") or ""
        dangerous = False
        if pair.startswith("pair:") and "<->" in pair:
            a, b = pair[len("pair:") :].split("<->", 1)
            if {gold, pred} == {a, b}:
                dangerous = True
        if row.get("probe_id") == "neg:ban_not_claim" and pred == "claim_correction":
            dangerous = True
        if row.get("probe_id") and row.get("probe_id") != "neg:ban_not_claim":
            if gold == "claim_correction" and pred == "rejection":
                dangerous = True
        if dangerous or "gate_a" in (row.get("tags") or []):
            # Zero-tolerance: any miss on gate_a tagged / catalog held_out fails
            failures.append(
                {
                    "id": row["id"],
                    "gold": gold,
                    "pred": pred,
                    "pair_id": row.get("pair_id"),
                    "probe_id": row.get("probe_id"),
                    "dangerous": dangerous,
                }
            )
    return {
        "pass": len(failures) == 0,
        "checked": checked,
        "failures": failures,
        "dangerous_count": sum(1 for f in failures if f.get("dangerous")),
    }


def token_probe(agent: Any, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained("answerdotai/ModernBERT-large")
    out = []
    samples = [r for r in rows if r["split"] == "held_out"][:8]
    for row in samples:
        utt = row["user_text"]
        kind = f"pending_kind={row.get('pending_kind')}"
        full = state_for(row)["text"]

        def n(text: str) -> int:
            return len(tok.encode(text, add_special_tokens=False))

        cfg = getattr(agent, "cfg", None) or {}
        out.append(
            {
                "id": row["id"],
                "utt_tokens": n(utt),
                "kind_tokens": n(kind),
                "full_state_tokens": n(full),
                "head_max_len": cfg.get("head_max_len", 192),
                "max_len": cfg.get("max_len", 512),
                "state_budget": cfg.get("max_len", 512) - cfg.get("head_max_len", 192),
            }
        )
    return out


def rss_mb() -> float:
    # macOS ru_maxrss is bytes
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)


def main() -> None:
    ART.mkdir(parents=True, exist_ok=True)
    rows = load_rows()
    check_floors(rows)
    held = [r for r in rows if r["split"] == "held_out"]
    held_residual = [r for r in held if not r.get("deterministic_preempt")]
    # Gate (a) catalog: any held_out with pair_id or probe_id
    catalog_held = [r for r in held if r.get("pair_id") or r.get("probe_id")]

    summary: dict[str, Any] = {
        "spike_ceiling": (
            "Not wholesale LLM replacement; at best skip for four payload-free "
            "intents or confidence-gated abstain into today's LLM path."
        ),
        "dataset": {
            "n_total": len(rows),
            "n_held_out": len(held),
            "n_held_residual": len(held_residual),
            "n_dev": sum(1 for r in rows if r["split"] == "dev"),
            "authorship": (
                "Hand-authored from ADR/TurnIntentName + classify_pending rules; "
                "never from classifier output. Seeded by Claude 17 fixtures."
            ),
        },
        "typed_decisions_note": (
            "laya-typed-decisions is fine-tuned on invoice/security/customer-service/"
            "agent-trace workflows — off-domain for turn_intent labels."
        ),
    }

    # --- majority ---
    maj = majority_arm(held_residual)
    write_jsonl(ART / "preds_majority.jsonl", maj)
    maj_acc = accuracy(maj)
    summary["majority_accuracy"] = maj_acc

    # --- deterministic ---
    det = deterministic_arm(rows)
    write_jsonl(ART / "preds_deterministic.jsonl", det)
    det_preempt = [p for p in det if p.get("preempt")]
    summary["deterministic_preempt_accuracy"] = accuracy(det_preempt) if det_preempt else None

    # --- Laya arms ---
    import laya

    device = os.environ.get("LAYA_DEVICE") or "mps"
    print(f"loading laya english on {device!r} ...")
    t_cold = time.perf_counter()
    try:
        agent = laya.load("convaiinnovations/laya", device=device)
    except Exception as exc:
        print(f"MPS/device={device} failed ({exc}); falling back to cpu")
        device = "cpu"
        agent = laya.load("convaiinnovations/laya", device=device)
    cold_s = time.perf_counter() - t_cold
    rss_after_en = rss_mb()
    summary["device"] = device
    summary["cold_load_s_english"] = round(cold_s, 3)
    summary["rss_mb_after_english"] = round(rss_after_en, 1)

    summary["token_probe"] = token_probe(agent, held_residual)

    def run_laya_arm(name: str, ag: Any) -> tuple[list[dict[str, Any]], dict[str, str]]:
        preds: list[dict[str, Any]] = []
        by_id: dict[str, str] = {}
        # Score residual held_out for accuracy; also score all catalog held_out for gate a
        targets = {r["id"]: r for r in held_residual}
        for row in catalog_held:
            targets[row["id"]] = row
        for row in targets.values():
            pred, conf, lat = laya_predict(ag, row, criteria=CRITERIA)
            by_id[row["id"]] = pred
            if not row.get("deterministic_preempt") and row["split"] == "held_out":
                preds.append(
                    {
                        "id": row["id"],
                        "gold": row["gold_intent"],
                        "pred": pred,
                        "confidence": conf,
                        "latency_ms": lat,
                        "ok": pred == row["gold_intent"],
                        "arm": name,
                    }
                )
            elif row.get("pair_id") or row.get("probe_id"):
                # catalog preempt still recorded for gate a
                preds.append(
                    {
                        "id": row["id"],
                        "gold": row["gold_intent"],
                        "pred": pred,
                        "confidence": conf,
                        "latency_ms": lat,
                        "ok": pred == row["gold_intent"],
                        "arm": name,
                        "catalog_only": True,
                    }
                )
        write_jsonl(ART / f"preds_{name}.jsonl", preds)
        return preds, by_id

    preds_laya, by_laya = run_laya_arm("laya", agent)
    residual_laya = [p for p in preds_laya if not p.get("catalog_only")]
    summary["laya_residual_accuracy"] = accuracy(residual_laya)
    summary["laya_confusion"] = confusion(residual_laya)
    summary["gate_a_laya"] = score_gate_a(rows, by_laya)

    print("loading laya-typed-decisions ...")
    t_td = time.perf_counter()
    agent_td = laya.load(
        "convaiinnovations/laya", subfolder="typed-decisions", device=device
    )
    summary["cold_load_s_typed_decisions"] = round(time.perf_counter() - t_td, 3)
    summary["rss_mb_after_typed"] = round(rss_mb(), 1)

    preds_td, by_td = run_laya_arm("laya_typed_decisions", agent_td)
    residual_td = [p for p in preds_td if not p.get("catalog_only")]
    summary["laya_typed_decisions_residual_accuracy"] = accuracy(residual_td)
    summary["laya_typed_decisions_confusion"] = confusion(residual_td)
    summary["gate_a_laya_typed_decisions"] = score_gate_a(rows, by_td)

    # option-order flip rate on a fixed residual subset (dev+held payload-free / continue)
    flip_rows = [r for r in held_residual if r["gold_intent"] in PAYLOAD_FREE][:5]
    flips = 0
    trials = 0
    keys = list(CRITERIA.keys())
    for row in flip_rows:
        base, _, _ = laya_predict(agent, row, criteria=CRITERIA)
        for _ in range(3):
            import random

            order = keys[:]
            random.shuffle(order)
            crit = {k: CRITERIA[k] for k in order}
            pred, _, _ = laya_predict(agent, row, criteria=crit)
            trials += 1
            if pred != base:
                flips += 1
    summary["option_order_flip_rate"] = (flips / trials) if trials else None

    # --- LLM arms ---
    skip_llm = os.environ.get("LAYA_SPIKE_SKIP_LLM") == "1"
    llm_accs: dict[str, float] = {}
    llm_latencies: list[float] = []
    if skip_llm:
        summary["llm_error"] = "LAYA_SPIKE_SKIP_LLM=1; gate (b) cannot pass"
    else:
        from recommender.turn_intent import build_ollama_turn_intent_parser

        for model in ("qwen2.5:7b", "qwen3.5:latest"):
            print(f"LLM arm {model} ...")
            try:
                parser = build_ollama_turn_intent_parser(model)
            except Exception as exc:
                _fail(f"failed to build ollama parser for {model}: {exc}")
            preds: list[dict[str, Any]] = []
            for row in held_residual:
                try:
                    pred, lat = llm_predict(parser, row)
                except Exception as exc:
                    pred, lat = f"ERROR:{type(exc).__name__}", 0.0
                preds.append(
                    {
                        "id": row["id"],
                        "gold": row["gold_intent"],
                        "pred": pred,
                        "latency_ms": lat,
                        "ok": pred == row["gold_intent"],
                        "arm": model,
                    }
                )
                if row["gold_intent"] in PAYLOAD_FREE:
                    llm_latencies.append(lat)
            safe = model.replace(":", "_").replace(".", "")
            write_jsonl(ART / f"preds_llm_{safe}.jsonl", preds)
            llm_accs[model] = accuracy(preds)
            summary[f"llm_accuracy_{safe}"] = llm_accs[model]
            summary[f"llm_confusion_{safe}"] = confusion(preds)

    # Gate (b)
    better_llm = max(llm_accs.values()) if llm_accs else None
    summary["gate_b"] = {}
    for label, acc in (
        ("laya", summary["laya_residual_accuracy"]),
        ("laya_typed_decisions", summary["laya_typed_decisions_residual_accuracy"]),
    ):
        if better_llm is None:
            summary["gate_b"][label] = {"pass": False, "reason": "no LLM baseline"}
            continue
        within = acc >= (better_llm - 0.05)
        above_maj = (acc - maj_acc) >= 0.10
        summary["gate_b"][label] = {
            "pass": within and above_maj,
            "accuracy": acc,
            "better_llm": better_llm,
            "majority": maj_acc,
            "within_5pp_of_llm": within,
            "ge_10pp_above_majority": above_maj,
        }

    # Gate (c) latency — payload-free only
    quick = os.environ.get("LAYA_SPIKE_QUICK") == "1"
    n_ex = 8 if not quick else 3
    n_rep_laya = 20 if not quick else 3
    n_rep_llm = int(os.environ.get("LAYA_SPIKE_LLM_LAT_REPS") or (5 if not quick else 3))
    pf_rows = [r for r in rows if "payload_free" in (r.get("tags") or [])][:n_ex]
    if len(pf_rows) < n_ex:
        pf_rows = [r for r in rows if r["gold_intent"] in PAYLOAD_FREE][:n_ex]

    # warmups
    for row in pf_rows[:3]:
        laya_predict(agent, row, criteria=CRITERIA)

    laya_warm: list[float] = []
    for row in pf_rows:
        for _ in range(n_rep_laya):
            _, _, lat = laya_predict(agent, row, criteria=CRITERIA)
            laya_warm.append(lat)

    llm_warm: list[float] = []
    if not skip_llm:
        from recommender.turn_intent import build_ollama_turn_intent_parser

        parser = build_ollama_turn_intent_parser("qwen2.5:7b")
        for row in pf_rows[:3]:
            try:
                llm_predict(parser, row)
            except Exception:
                pass
        for row in pf_rows:
            for _ in range(n_rep_llm):
                try:
                    _, lat = llm_predict(parser, row)
                    llm_warm.append(lat)
                except Exception:
                    pass

    laya_med = statistics.median(laya_warm) if laya_warm else None
    llm_mean = statistics.mean(llm_warm) if llm_warm else None
    summary["gate_c"] = {
        "laya_warm_median_ms": laya_med,
        "llm_warm_mean_ms": llm_mean,
        "historical_llm_mean_ms_context": 817.0,
        "n_examples": len(pf_rows),
        "n_reps_laya": n_rep_laya,
        "n_reps_llm": n_rep_llm,
        "pass": (
            laya_med is not None
            and llm_mean is not None
            and laya_med <= 0.5 * llm_mean
        ),
    }

    # Gate (d) soft
    summary["gate_d"] = {
        "rss_mb_after_english": summary["rss_mb_after_english"],
        "cold_load_s_english": summary["cold_load_s_english"],
        "note": "soft footprint gate; document only",
    }

    # ECE skipped unless easy
    summary["ece"] = {
        "skipped": True,
        "reason": "temperatures invalid/uncalibrated on load; report raw confidence only",
    }

    out_path = ART / "summary.json"
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: summary[k] for k in summary if k.startswith("gate_") or k.endswith("_accuracy") or k in {"majority_accuracy", "device"}}, indent=2))
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
