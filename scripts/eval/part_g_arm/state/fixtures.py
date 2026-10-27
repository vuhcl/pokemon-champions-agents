"""Team fixtures for the stateful arm. Locked slots come from apply_lock."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from recommender.ids import to_id
from recommender.legality import is_item_legal, is_species_legal, load_snapshot, species_types
from recommender.state import empty_slot

from scripts.eval.part_g_arm.state.tools import lock_slot

HERE = Path(__file__).resolve().parent
REQUEST_SET = HERE.parents[1] / "part_g_v4" / "part3_request_set_v4.md"
DEV_SPECIES = ("Venusaur", "Venusaur-Mega", "Blastoise", "Bulbasaur")
DEV_ITEMS = ("Wide Lens",)
CHECKPOINT_PROMPT_SHA256 = "e74a80f424d0506ec86eb6cb554a3e401a347380233595494c34726d708aae7a"


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


def _in_request_set(name: str, text: str) -> bool:
    return re.search(rf"\b{re.escape(name)}\b", text) is not None


def dev_key_document() -> dict[str, Any]:
    """Legality from the snapshot. Expected classes are the checkpoint contract."""
    snap = load_snapshot()
    text = REQUEST_SET.read_text(encoding="utf-8")
    species: dict[str, Any] = {}
    for name in DEV_SPECIES:
        canonical = snap["species"][to_id(name)]["name"]
        entry: dict[str, Any] = {
            "canonical": canonical,
            "legal": is_species_legal(snap, name),
            "in_request_set": _in_request_set(name, text),
        }
        if name in ("Venusaur", "Bulbasaur"):
            entry["types"] = species_types(snap, name)
        species[name] = entry
    items: dict[str, Any] = {}
    for name in DEV_ITEMS:
        items[name] = {
            "canonical": name,
            "legal": is_item_legal(snap, to_id(name)),
            "in_request_set": _in_request_set(name, text),
        }
    if not species["Venusaur"]["legal"] or species["Venusaur"]["in_request_set"]:
        raise RuntimeError("Venusaur is not a usable legal dev species")
    if species["Bulbasaur"]["legal"] or species["Bulbasaur"]["in_request_set"]:
        raise RuntimeError("Bulbasaur is not a usable illegal dev species")
    if not species["Venusaur-Mega"]["legal"] or species["Venusaur-Mega"]["in_request_set"]:
        raise RuntimeError("Venusaur-Mega is not a usable legal mega form")
    if not species["Blastoise"]["legal"] or species["Blastoise"]["in_request_set"]:
        raise RuntimeError("Blastoise is not a usable legal partner")
    if not items["Wide Lens"]["legal"] or items["Wide Lens"]["in_request_set"]:
        raise RuntimeError("Wide Lens is not a usable legal dev item")
    return {
        "provenance": "load_snapshot(), the same data validate_team_value reads. Wiring check only, not a legality measurement (ADR-060).",
        "checkpoint_prompt_sha256": CHECKPOINT_PROMPT_SHA256,
        "species": species,
        "items": items,
        "rows": {
            "dev-lock": {"classes": ["wrote", "refused"], "user_slot": 2, "species_after": ["Venusaur", "Venusaur"]},
            "dev-unlock": {"classes": ["refused"]},
            "dev-commit": {"classes": ["refused"]},
            "dev-lookup": {"classes": ["lookup only"], "tool": "get_typing", "species": "Venusaur"},
            "dev-unlock-ok": {"classes": ["wrote"], "user_slot": 1, "species_after": None},
            "dev-commit-ok": {
                "classes": ["wrote"],
                "user_slot": 1,
                "species": "Venusaur",
                "fields": ["role", "species", "ability", "item", "moveset", "spread", "nature"],
            },
            "dev-hyp-item-clause": {"classes": ["lookup only"]},
            "dev-hyp-species-clause": {"classes": ["lookup only"]},
            "dev-hyp-unknown-species": {"classes": ["lookup only"]},
            "dev-hyp-legal": {"classes": ["lookup only"]},
            "dev-hyp-item-only": {"classes": ["lookup only"]},
        },
    }


def write_dev_keys(path: Path | None = None) -> dict[str, Any]:
    doc = dev_key_document()
    target = path or (HERE / "dev_keys.json")
    target.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return doc
