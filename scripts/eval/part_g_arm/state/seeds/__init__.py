"""Start-state seeds for the 7 previously unloaded covered rows.

Built from part3_request_set_v4.md row text only. No model calls.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from scripts.eval.part_g_arm.state.seeds import builders

HERE = Path(__file__).resolve().parent

# Row id → seed builder name (MT4 shares CS with MS7 but is not-covered: no show-candidates tool).
SEED_FOR_ROW: dict[str, str] = {
    "MS7": "cs_pending",
    "MT4": "cs_pending",  # loads for dry-run; eval coverage dropped — see LAST_PART3_SEEDS.md
    "MS4": "fbc_pending",
    "MU7": "fbc_pending",
    "MT3": "mt3_after_t1",
    "HC2": "hc2_after_t1",
    "HD1": "hd1_history",
}

BUILDERS: dict[str, Callable[[], dict[str, Any]]] = {
    "cs_pending": builders.build_cs_pending_seed,
    "fbc_pending": builders.build_fbc_pending_seed,
    "mt3_after_t1": builders.build_mt3_seed,
    "hc2_after_t1": builders.build_hc2_seed,
    "hd1_history": builders.build_hd1_seed,
}


def seed_path(name: str) -> Path:
    return HERE / f"{name}.json"


def write_seed_manifests() -> dict[str, str]:
    """Materialize JSON sidecars (metadata + serializable snapshot) and return sha256 per file."""
    from recommender.arm_tools import to_jsonable

    shas: dict[str, str] = {}
    for name, builder in BUILDERS.items():
        state = builder()
        meta = {
            "seed": name,
            "justification": builders.JUSTIFICATIONS[name],
            "rows": [rid for rid, s in SEED_FOR_ROW.items() if s == name],
            "state": to_jsonable(state),
        }
        if name == "hd1_history":
            meta["message_history"] = state.get("_message_history")
        path = seed_path(name)
        blob = json.dumps(meta, indent=2, sort_keys=True) + "\n"
        path.write_text(blob, encoding="utf-8")
        shas[path.name] = hashlib.sha256(blob.encode()).hexdigest()
    (HERE / "SHA256SUMS").write_text(
        "".join(f"{h}  {n}\n" for n, h in sorted(shas.items())), encoding="utf-8"
    )
    return shas


def load_seed_state(row_id: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Return (state, meta) for a seeded row, or (None, error meta)."""
    name = SEED_FOR_ROW.get(row_id)
    if not name:
        return None, {"row": row_id, "loaded": False, "error": "no seed mapping"}
    builder = BUILDERS[name]
    state = builder()
    meta = {
        "row": row_id,
        "loaded": True,
        "complete": True,
        "source": f"seeds/{name}",
        "seed": name,
        "justification": builders.JUSTIFICATIONS[name],
        "error": None,
    }
    if row_id == "MT4":
        meta["not_covered_note"] = (
            "CS seed loads, but MT4 t2 'Show candidates' has no arm tool "
            "(no present/show_candidates); row stays not-covered for the run."
        )
    return state, meta
