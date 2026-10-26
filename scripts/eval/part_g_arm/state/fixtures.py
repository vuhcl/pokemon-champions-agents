"""Team fixtures for the stateful arm. Locked slots come from apply_lock."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from recommender.arm_tools import to_id
from recommender.legality import is_species_legal, load_snapshot, species_types
from recommender.state import empty_slot

from scripts.eval.part_g_arm.state.tools import lock_slot

HERE = Path(__file__).resolve().parent
REQUEST_SET = HERE.parents[1] / "part_g_v4" / "part3_request_set_v4.md"
DEV_SPECIES = ("Venusaur", "Bulbasaur")


def empty_team() -> dict[str, Any]:
    return {
        "team_draft": [empty_slot() for _ in range(6)],
        "pending_presentation": None,
        "pending_slot_intent": None,
        "provisional_slot": None,
        "provisional_refinement": None,
    }


def one_locked_slot(species: str = "Venusaur", user_slot: int = 1) -> dict[str, Any]:
    state, patch = lock_slot(empty_team(), user_slot, species)
    if patch.get("slot_commit_error"):
        raise RuntimeError(patch["slot_commit_error"])
    return state


def dev_key_document() -> dict[str, Any]:
    """Legality from the snapshot. Expected classes are the checkpoint contract."""
    snap = load_snapshot()
    text = REQUEST_SET.read_text(encoding="utf-8")
    species: dict[str, Any] = {}
    for name in DEV_SPECIES:
        canonical = snap["species"][to_id(name)]["name"]
        species[name] = {
            "canonical": canonical,
            "legal": is_species_legal(snap, name),
            "in_request_set": re.search(rf"\b{re.escape(name)}\b", text) is not None,
            "types": species_types(snap, name),
        }
    if not species["Venusaur"]["legal"] or species["Venusaur"]["in_request_set"]:
        raise RuntimeError("Venusaur is not a usable legal dev species")
    if species["Bulbasaur"]["legal"] or species["Bulbasaur"]["in_request_set"]:
        raise RuntimeError("Bulbasaur is not a usable illegal dev species")
    return {
        "provenance": "load_snapshot(), the same data validate_team_value reads. Wiring check only, not a legality measurement (ADR-060).",
        "species": species,
        "rows": {
            "dev-lock": {"classes": ["wrote", "refused"], "user_slot": 2, "species_after": ["Venusaur", "Venusaur"]},
            "dev-unlock": {"classes": ["refused"]},
            "dev-commit": {"classes": ["refused"]},
            "dev-lookup": {"classes": ["lookup only"], "tool": "get_typing", "species": "Venusaur"},
        },
    }


def write_dev_keys(path: Path | None = None) -> dict[str, Any]:
    doc = dev_key_document()
    target = path or (HERE / "dev_keys.json")
    target.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return doc
