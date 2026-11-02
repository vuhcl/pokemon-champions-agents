"""Map base+own Mega stone → Mega forme for tool_fields calc_damage.

Does not touch services/calc. Echoes forme_used per side.
"""

from __future__ import annotations

from typing import Any

from recommender.ids import to_id
from recommender.item_conditions import mega_stones_by_item_id
from recommender.legality import is_species_legal, load_snapshot


def mega_forme_for_base_holding_stone(species: str, item: str | None) -> str | None:
    """If species is a stone's base and item is that stone, return the Mega forme name."""
    if not item or not isinstance(item, str) or not item.strip():
        return None
    if not isinstance(species, str) or not species.strip():
        return None
    pairs = mega_stones_by_item_id().get(to_id(item))
    if not pairs:
        return None
    sid = to_id(species)
    snap = load_snapshot()
    for base_display, mega_display in pairs:
        if to_id(base_display) != sid:
            continue
        if not is_species_legal(snap, mega_display):
            return None
        return mega_display
    return None


def prepare_side_mega_stone(side: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Rewrite side.species when base holds its own Mega stone. Always returns an echo."""
    out = dict(side)
    requested = out.get("species")
    item = out.get("item")
    mapped = mega_forme_for_base_holding_stone(
        str(requested) if requested is not None else "",
        str(item) if isinstance(item, str) else None,
    )
    echo: dict[str, Any] = {
        "requested": requested,
        "forme_used": mapped if mapped else requested,
        "mapped_via": "mega_stone" if mapped else None,
    }
    if mapped:
        out["species"] = mapped
    return out, echo


def prepare_calc_damage_mega_args(
    args: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply mega-stone mapping to attacker and defender. Stamps _forme_resolution."""
    out = dict(args)
    atk, atk_echo = prepare_side_mega_stone(dict(out.get("attacker") or {}))
    de, de_echo = prepare_side_mega_stone(dict(out.get("defender") or {}))
    out["attacker"] = atk
    out["defender"] = de
    out["_forme_resolution"] = {"attacker": atk_echo, "defender": de_echo}
    return out, out["_forme_resolution"]
