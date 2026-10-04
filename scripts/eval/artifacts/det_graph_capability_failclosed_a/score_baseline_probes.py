#!/usr/bin/env python3
"""Read-only score_transcript on baseline P1-P3/S7 (and optional control/after)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from recommender.legality import load_snapshot  # noqa: E402
from scripts.eval.bare_llm_score import score_transcript  # noqa: E402

OUT = Path(__file__).resolve().parent
BASELINE_RUNS = (
    REPO
    / "scripts/eval/artifacts/det_graph_capability_baseline_88df2d7/runs"
)
PROBES = ("P1", "P2", "P3", "S7")
MODELS = ("qwen2.5_7b", "qwen3.5_latest")


def _visible(path: Path) -> str:
    data = json.loads(path.read_text())
    parts = []
    for t in data.get("turns") or []:
        v = t.get("visible")
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
        else:
            msg = ((t.get("payload") or {}).get("message") or "").strip()
            if msg:
                parts.append(msg)
    return "\n\n".join(parts)


def _tally(score: dict) -> dict:
    sp = (score.get("species_facts") or {}).get("tally") or {}
    mech = (score.get("mechanical") or {}).get("tally") or {}
    leg = score.get("legality") or {}
    struct = score.get("structural") or {}
    return {
        "false_legal": leg.get("false_legal"),
        "false_illegal": leg.get("false_illegal"),
        "false_illegal_examples": leg.get("false_illegal_examples"),
        "species_FALSE": sp.get("FALSE"),
        "species_TRUE": sp.get("TRUE"),
        "species_unv": sp.get("unverifiable_shape"),
        "mech_FALSE": mech.get("FALSE"),
        "mech_TRUE": mech.get("TRUE"),
        "mech_unv": mech.get("unverifiable_shape"),
        "item_clause_violation": struct.get("item_clause_violation"),
        "completed_team": (score.get("team") or {}).get("completed"),
    }


def score_dir(runs: Path, label: str, snap: dict, *, calc_ok: bool) -> dict:
    rows = []
    for model in MODELS:
        for rid in PROBES:
            path = runs / f"{rid}__{model}__merged_usage_dir__r0.json"
            if not path.exists():
                rows.append(
                    {
                        "id": rid,
                        "model": model,
                        "missing": True,
                        "path": str(path),
                    }
                )
                continue
            transcript = _visible(path)
            score = score_transcript(transcript, snap, calc_ok=calc_ok)
            rows.append(
                {
                    "id": rid,
                    "model": model,
                    "path": str(path),
                    "transcript_chars": len(transcript),
                    "transcript_preview": transcript[:400],
                    "tally": _tally(score),
                    "score": score,
                }
            )
    return {"label": label, "runs_dir": str(runs), "rows": rows}


def main() -> None:
    snap = load_snapshot()
    # calc may be unavailable offline; still score structural/legality/species
    calc_ok = False
    baseline = score_dir(BASELINE_RUNS, "baseline_88df2d7", snap, calc_ok=calc_ok)
    out = {
        "calc_ok": calc_ok,
        "note": (
            "Baseline scored read-only. If tallies are zero despite visible "
            "false-legal/false-rules prose in transcript_preview, the v2 "
            "false-legal gate cannot see this defect class."
        ),
        "baseline": baseline,
    }
    path = OUT / "v2_verifier_scores.json"
    path.write_text(json.dumps(out, indent=2, default=str) + "\n")
    # compact print
    compact = []
    for r in baseline["rows"]:
        if r.get("missing"):
            compact.append(r)
            continue
        compact.append(
            {
                "id": r["id"],
                "model": r["model"],
                "tally": r["tally"],
                "preview": r["transcript_preview"][:200],
            }
        )
    print(json.dumps({"wrote": str(path), "compact": compact}, indent=2))


if __name__ == "__main__":
    main()
