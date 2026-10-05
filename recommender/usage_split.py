"""Per-source usage file assemble/split helpers (schema v4).

Kept in recommender/ so loaders do not import scripts/ (avoids circular imports).
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = 4

_SHOWDOWN_META_KEYS = (
    "showdown_rating",
    "showdown_format",
    "showdown_month",
    "showdown_source",
    "showdown_pct_kind",
    "showdown_move_limit",
    "showdown_battles",
    "showdown_teammates_extracted_at",
    "showdown_teammates",
    "showdown_extracted_at",
)

_INGAME_META_KEYS = (
    "extracted_at",
    "ingame_doubles_extracted_at",
    "ingame_ladder_n",
    "detail_fetch_ok_n",
    "detail_fetch_fail_n",
    "join_n",
    "index_count",
    "munchstats_generated_at",
    "munchstats_published_at",
    "munchstats_captured_on",
    "munchstats_default_season",
)


def _without_snapshot_teammates(entry: dict[str, Any]) -> dict[str, Any]:
    out = dict(entry)
    out.pop("teammates", None)
    out.pop("teammates_meta", None)
    return out


def merge_species_flat(
    ingame: dict[str, dict], showdown: dict[str, dict]
) -> dict[str, dict]:
    """Prefer Showdown builds when present, else in-game (same as fetch_usage_mb)."""
    flat: dict[str, dict] = {}
    for sid, e in ingame.items():
        flat[sid] = dict(e)
    for sid, e in showdown.items():
        if sid in flat:
            merged = dict(flat[sid])
            for k in (
                "common_moves",
                "common_abilities",
                "common_items",
                "top_spreads",
                "featured_sets",
                "usage_pct",
                "name",
            ):
                if e.get(k):
                    merged[k] = e[k]
            merged["source"] = "merged"
            flat[sid] = merged
        else:
            flat[sid] = _without_snapshot_teammates(e)
    return flat


def split_monolith(monolith: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (ingame_file, showdown_file) dicts (schema v4)."""
    meta = dict(monolith.get("meta") or {})
    regulation = str(meta.get("regulation") or "")
    ingame_species = ((monolith.get("ingame_doubles") or {}).get("species")) or {}
    sd_block = monolith.get("showdown_doubles") or monolith.get("showdown_vgc_mb") or {}
    showdown_species = (sd_block.get("species")) or {}

    ingame_meta: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "regulation": regulation,
        "section": "ingame_doubles",
    }
    for k in _INGAME_META_KEYS:
        if k in meta:
            ingame_meta[k] = meta[k]
    if "attribution" in meta:
        ingame_meta["attribution"] = meta["attribution"]
    if "sources" in meta:
        ingame_meta["sources"] = list(meta["sources"])

    showdown_meta: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "regulation": regulation,
        "section": "showdown_doubles",
    }
    for k in _SHOWDOWN_META_KEYS:
        if k in meta:
            showdown_meta[k] = meta[k]
    if "attribution" in meta:
        showdown_meta["attribution"] = meta["attribution"]
    sources = list(meta.get("sources") or [])
    showdown_meta["sources"] = [
        s for s in sources if s in {"smogon-chaos", "munchstats-showdown"}
    ] or sources

    return (
        {"meta": ingame_meta, "ingame_doubles": {"species": ingame_species}},
        {"meta": showdown_meta, "showdown_doubles": {"species": showdown_species}},
    )


def assemble_from_split(
    ingame_file: dict[str, Any] | None,
    showdown_file: dict[str, Any] | None,
) -> dict[str, Any]:
    """In-memory snapshot: showdown_doubles + flat via merge_species_flat."""
    ingame_file = ingame_file or {}
    showdown_file = showdown_file or {}
    ingame_species = ((ingame_file.get("ingame_doubles") or {}).get("species")) or {}
    showdown_species = ((showdown_file.get("showdown_doubles") or {}).get("species")) or {}

    meta: dict[str, Any] = {"schema_version": SCHEMA_VERSION}
    for src in (ingame_file.get("meta") or {}, showdown_file.get("meta") or {}):
        for k, v in src.items():
            if k == "section":
                continue
            meta[k] = v
    meta["schema_version"] = SCHEMA_VERSION

    return {
        "meta": meta,
        "ingame_doubles": {"species": ingame_species},
        "showdown_doubles": {"species": showdown_species},
        "showdown_singles": {"species": {}},
        "species": merge_species_flat(ingame_species, showdown_species),
    }


def normalize_monolith(monolith: dict[str, Any]) -> dict[str, Any]:
    """Legacy monolith → in-memory shape (allowed equivalence diffs applied)."""
    return assemble_from_split(*split_monolith(monolith))
