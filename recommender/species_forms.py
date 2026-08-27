"""Species forme resolution from held items (cycle-free shared helper)."""

from __future__ import annotations

from typing import Any


def item_mega_forme(item_id: str, base_species_id: str, snap: dict[str, Any]) -> str | None:
    if item_id.endswith("itex"):
        candidate = f"{base_species_id}megax"
    elif item_id.endswith("itey"):
        candidate = f"{base_species_id}megay"
    elif item_id.endswith("ite"):
        candidate = f"{base_species_id}mega"
    else:
        return None
    species = snap.get("species") or {}
    if candidate in species:
        return candidate
    # Showdown's ungendered meowstic is the male/default; F/M Megas are
    # mechanically identical (same stats, both Trace). meowsticf already
    # resolves via {base}mega → meowsticfmega.
    if base_species_id == "meowstic" and item_id.endswith("ite") and "meowsticmmega" in species:
        return "meowsticmmega"
    return None
