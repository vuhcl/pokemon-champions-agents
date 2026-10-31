"""Read-only usage/meta tools (tool_fields rung). Pins only — no key-builder imports."""

from __future__ import annotations

from typing import Any

from recommender.coverage import get_relevant_threats
from recommender.ids import to_id
from recommender.usage_data import (
    TEAM_THREAT_N,
    ingame_ladder_species_map,
    showdown_species_map,
)
from recommender.usage_spreads import effective_spe

# Showdown pin retains at most 8 joints (Part 0).
_SHOWDOWN_SPREAD_LIMIT = 8
# Part 0 COMMON_SPEED: top 3 distinct Spe cells.
_COMMON_SPEED_N = 3

_SOURCE_LABEL = {
    "ingame": "in-game doubles ladder (offline snapshot)",
    "showdown": "Showdown doubles usage (offline snapshot)",
}

_KIND_FIELD = {
    "moves": "common_moves",
    "abilities": "common_abilities",
    "natures": "common_natures",
}


def _sp_vector(evs: object) -> dict[str, int]:
    raw = evs if isinstance(evs, dict) else {}
    return {
        k: int(raw.get(k, 0) or 0)
        for k in ("hp", "atk", "def", "spa", "spd", "spe")
    }


def _spread_rows(entry: dict[str, Any], *, source: str) -> dict[str, Any]:
    rows = list(entry.get("top_spreads") or [])
    limit = _SHOWDOWN_SPREAD_LIMIT
    listed = rows[:limit]
    if source == "showdown":
        pct_kind = "chaos_weight"
        note = (
            "Showdown top_spreads weight is raw chaos weight (pct_kind=chaos_weight), "
            "not a percent. Pin lists at most 8 joints."
        )
    else:
        pct_kind = "percent"
        note = (
            "In-game top_spreads nature is rank-paired with the spread "
            "(stat_alignment), not an observed joint. Weight is a percent "
            "(pct_kind=percent). Pin lists at most 8 rows."
        )
    spreads = []
    for i, row in enumerate(listed, start=1):
        spreads.append(
            {
                "rank": i,
                "nature": row.get("nature"),
                "sp": _sp_vector(row.get("evs")),
                "weight": row.get("pct"),
                "pct_kind": row.get("pct_kind") or pct_kind,
            }
        )
    return {
        "source": source,
        "source_label": _SOURCE_LABEL[source],
        "listed": len(spreads),
        "limit": limit,
        "pct_kind": pct_kind,
        "note": note,
        "spreads": spreads,
    }


def get_usage_spreads(species: object, *, regulation: str = "champions") -> dict[str, Any]:
    """Showdown and in-game top_spreads for a species. Does not invent missing rows."""
    if not isinstance(species, str) or not species.strip():
        return {"status": "error", "message": "species is required"}
    sid = to_id(species)
    ig = ingame_ladder_species_map(regulation).get(sid)
    sd = showdown_species_map(regulation).get(sid)
    if ig is None and sd is None:
        return {
            "status": "ok",
            "found": False,
            "query": species,
            "reason": "species not present in in-game or Showdown usage pins",
        }
    sources: list[dict[str, Any]] = []
    display = (sd or ig or {}).get("name") or species
    if sd is not None:
        sources.append(_spread_rows(sd, source="showdown"))
    if ig is not None:
        sources.append(_spread_rows(ig, source="ingame"))
    return {
        "status": "ok",
        "found": True,
        "species": display,
        "sources": sources,
    }


def get_common_speeds(species: object, *, regulation: str = "champions") -> dict[str, Any]:
    """Part 0 COMMON_SPEED from Showdown top_spreads (independent of key builders).

    Lines used: part3_request_set_v4.md Part 0 L38–39 —
    COMMON_JOINT = top 3 retained Showdown joints by chaos weight;
    COMMON_SPEED = top 3 distinct grouped final-Speed values (speed-only rows).
    Algorithm: take pin top_spreads[:8], Spe via effective_spe (Champions formula),
    group by final Spe summing chaos weight, rank by (−weight, −spe), keep top 3.
    """
    if not isinstance(species, str) or not species.strip():
        return {"status": "error", "message": "species is required"}
    sid = to_id(species)
    sd = showdown_species_map(regulation).get(sid)
    if sd is None:
        return {
            "status": "ok",
            "found": False,
            "query": species,
            "reason": "species not present in Showdown usage pin",
            "source": "showdown",
            "source_label": _SOURCE_LABEL["showdown"],
        }
    rows = list(sd.get("top_spreads") or [])[:_SHOWDOWN_SPREAD_LIMIT]
    if not rows:
        return {
            "status": "ok",
            "found": False,
            "query": species,
            "species": sd.get("name") or species,
            "reason": "Showdown top_spreads empty",
            "source": "showdown",
            "source_label": _SOURCE_LABEL["showdown"],
            "listed": 0,
            "limit": _COMMON_SPEED_N,
            "joint_limit": _SHOWDOWN_SPREAD_LIMIT,
        }
    by_spe: dict[int, dict[str, Any]] = {}
    for i, row in enumerate(rows, start=1):
        nat = row.get("nature") or "Serious"
        sp = _sp_vector(row.get("evs"))
        weight = float(row.get("pct") or 0)
        final = int(effective_spe(sd.get("name") or species, sp, str(nat)))
        cell = by_spe.get(final)
        if cell is None:
            cell = {
                "final_spe": final,
                "weight": 0.0,
                "pct_kind": "chaos_weight",
                "contributors": [],
            }
            by_spe[final] = cell
        cell["weight"] += weight
        cell["contributors"].append(
            {
                "nature": nat,
                "sp": sp,
                "weight": weight,
                "pct_kind": row.get("pct_kind") or "chaos_weight",
                "rank_in_pin": i,
            }
        )
    ranked = sorted(by_spe.values(), key=lambda c: (-c["weight"], -c["final_spe"]))
    cells = []
    for rank, cell in enumerate(ranked[:_COMMON_SPEED_N], start=1):
        cells.append(
            {
                "rank": rank,
                "final_spe": cell["final_spe"],
                "weight": cell["weight"],
                "pct_kind": "chaos_weight",
                "contributors": cell["contributors"],
            }
        )
    return {
        "status": "ok",
        "found": True,
        "species": sd.get("name") or species,
        "source": "showdown",
        "source_label": _SOURCE_LABEL["showdown"],
        "definition": (
            "Part 0 COMMON_SPEED: top 3 distinct final Spe from retained Showdown "
            "joints (pin limit 8), grouped by Spe with summed chaos weight"
        ),
        "part0_lines": "part3_request_set_v4.md Part 0 L38-39",
        "listed": len(cells),
        "limit": _COMMON_SPEED_N,
        "joint_limit": _SHOWDOWN_SPREAD_LIMIT,
        "pct_kind": "chaos_weight",
        "note": "cell weight is summed raw chaos weight, not a percent",
        "cells": cells,
    }


def get_meta_threats(n: object = None, *, regulation: str = "champions") -> dict[str, Any]:
    """CLI threat list via get_relevant_threats (in-game ladder + Showdown forme expand)."""
    if n is None:
        n_i = TEAM_THREAT_N
    elif isinstance(n, bool) or not isinstance(n, int) or n < 1:
        return {"status": "error", "message": "n must be a positive integer"}
    else:
        n_i = n
    state = {"regulation_mod": regulation}
    threats = get_relevant_threats(state, n=n_i)  # type: ignore[arg-type]
    out_rows = []
    for t in threats:
        pct = t.showdown_usage_pct
        out_rows.append(
            {
                "species": t.form,
                "ladder_species": t.ladder_species,
                "usage_rank": t.usage_rank,
                "showdown_usage_pct": pct,
                "pct_kind": "percent" if pct is not None else None,
                "build_source": t.build_source,
            }
        )
    return {
        "status": "ok",
        "source": "ingame",
        "source_label": _SOURCE_LABEL["ingame"],
        "how_built": (
            "get_relevant_threats: top-n in-game doubles ladder species by usage_rank "
            "(ascending), each expanded to Showdown formes when multi-form; n counts "
            "ladder species that survive expand+filter (return length may exceed n)."
        ),
        "n_requested": n_i,
        "listed": len(out_rows),
        "threats": out_rows,
        "note": (
            "usage_rank is an in-game ordinal, not a percent. showdown_usage_pct is a "
            "percent when present. This list is the CLI ladder path, not the HU2b "
            "Showdown ≥4.52% form set."
        ),
    }


def get_usage_stats(
    species: object,
    kind: object,
    *,
    regulation: str = "champions",
) -> dict[str, Any]:
    """Usage-ranked moves / abilities / natures from the same pins as get_usage_items."""
    if not isinstance(species, str) or not species.strip():
        return {"status": "error", "message": "species is required"}
    if kind not in _KIND_FIELD:
        return {
            "status": "error",
            "message": "kind must be moves|abilities|natures",
        }
    field = _KIND_FIELD[str(kind)]
    sid = to_id(species)
    ig = ingame_ladder_species_map(regulation).get(sid)
    sd = showdown_species_map(regulation).get(sid)
    if ig is None and sd is None:
        return {
            "status": "ok",
            "found": False,
            "query": species,
            "kind": kind,
            "reason": "species not present in in-game or Showdown usage pins",
        }
    sources: list[dict[str, Any]] = []
    display = (sd or ig or {}).get("name") or species

    def _one(entry: dict[str, Any], source: str) -> dict[str, Any]:
        rows = list(entry.get(field) or [])
        # Pins store percent for these buckets (Showdown moves/items/abilities are
        # weight_over_abilities_sum percents; natures mostly in-game).
        pct_kind = "percent"
        entries = []
        for i, row in enumerate(rows, start=1):
            entries.append(
                {
                    "rank": i,
                    "name": row.get("name"),
                    "weight": row.get("pct"),
                    "pct_kind": pct_kind,
                }
            )
        return {
            "source": source,
            "source_label": _SOURCE_LABEL[source],
            "listed": len(entries),
            "pct_kind": pct_kind,
            "note": (
                f"{field} weights are usage percents (pct_kind=percent), not raw chaos "
                "weights. Empty list means the pin has no rows — nothing filled in."
            ),
            "entries": entries,
        }

    if sd is not None:
        sources.append(_one(sd, "showdown"))
    if ig is not None:
        sources.append(_one(ig, "ingame"))
    out: dict[str, Any] = {
        "status": "ok",
        "found": True,
        "species": display,
        "kind": kind,
        "sources": sources,
    }
    source_names = {s["source"] for s in sources}
    if source_names == {"showdown"}:
        out["ingame_missing"] = True
        out["ingame_missing_note"] = (
            "No in-game ladder rows for this species id. Do not label these figures "
            "as in-game. For Mega formes, try the legal base forme (e.g. Floette-Eternal) "
            "for in-game data (blends base and Mega-holder usage), or keep Showdown and "
            "name that source."
        )
    if str(kind) == "abilities":
        from scripts.eval.part_g_arm.state.ability_default import lookup_top_ability

        top = lookup_top_ability(species, regulation=regulation)
        out["default_source"] = top["default_source"]
        out["default_source_missing"] = top["default_source_missing"]
        out["top_ability"] = top["top_ability"]
        out["default_source_note"] = (
            "default_source is top in-game ability, except Mega-capable bases and "
            "Mega formes use top Showdown (in-game blends base/Mega). Flip "
            "ABILITY_DEFAULT_SOURCE_MODE to 'showdown' for Showdown-everywhere."
        )
    return out


# --- tool_fields specs -------------------------------------------------------

_STR = {"type": "string"}
_INT = {"type": "integer"}


def _spec(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


USAGE_META_SPECS: list[dict[str, Any]] = [
    _spec(
        "get_usage_spreads",
        "Returns pinned Showdown and in-game top_spreads for a species (nature, SP, rank, "
        "weight, pct_kind); does not invent spreads or treat chaos weight as a percent.",
        {"species": dict(_STR)},
        ["species"],
    ),
    _spec(
        "get_common_speeds",
        "Returns Part 0 COMMON_SPEED: top 3 distinct Spe cells from Showdown joints with "
        "contributing nature/SP; does not import key builders or fill missing species.",
        {"species": dict(_STR)},
        ["species"],
    ),
    _spec(
        "get_meta_threats",
        "Returns the CLI get_relevant_threats list (in-game ladder + Showdown forme expand) "
        "with source and usage figures; does not force the HU2b ≥4.52% Showdown set.",
        {"n": dict(_INT)},
        [],
    ),
    _spec(
        "get_usage_stats",
        "Returns usage-ranked moves, abilities, or natures from the same pins as "
        "get_usage_items; for kind=abilities also returns default_source and "
        "top_ability (in-game top, Showdown for Mega-capable bases/formes); does "
        "not return the dex list or invent missing rows.",
        {"species": dict(_STR), "kind": dict(_STR)},
        ["species", "kind"],
    ),
]
