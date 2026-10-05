"""Smogon chaos stats → usage rows (no move/item cap).

common_* pct = chaos weight / Raw count * 100 (meta showdown_pct_kind =
weight_over_raw_count). top_spreads[].pct is raw chaos Spreads weight
(pct_kind=chaos_weight), not divided by Raw. Smogon published % uses
sum(Abilities) as denom — deferred (pre-B6).
"""

from __future__ import annotations

from typing import Any

from recommender.ids import to_id
from recommender.usage_data import load_usage

# Archive-tool / URL helpers may still name historical M-B chaos ids explicitly.
DEFAULT_MONTH = "2026-07"
DEFAULT_FORMAT = "gen9championsvgc2026regmb"
DEFAULT_RATING = 1500


def chaos_url(month: str, format_id: str, rating: int) -> str:
    return f"https://www.smogon.com/stats/{month}/chaos/{format_id}-{rating}.json"


def showdown_source_params(regulation: str) -> dict[str, Any]:
    """Month/format/rating/source from the offline snapshot meta for ``regulation``.

    No silent M-B fallbacks: missing month/format raises.
    """
    meta = load_usage(regulation).get("meta") or {}
    month = meta.get("showdown_month")
    format_id = meta.get("showdown_format")
    if not month or not format_id:
        raise ValueError(
            f"showdown meta incomplete for {regulation!r}: "
            f"need showdown_month and showdown_format"
        )
    try:
        rating = int(meta.get("showdown_rating") or DEFAULT_RATING)
    except (TypeError, ValueError):
        rating = DEFAULT_RATING
    source = str(meta.get("showdown_source") or "smogon-chaos")
    return {
        "month": str(month),
        "format_id": str(format_id),
        "rating": rating,
        "source": source,
        # ponytail: alias "set" until M-B archive rebuild stamps the new name
        "pct_kind": _normalize_pct_kind(meta.get("showdown_pct_kind")),
    }


def _normalize_pct_kind(raw: Any) -> str:
    kind = str(raw or "weight_over_raw_count")
    if kind == "set":
        return "weight_over_raw_count"
    return kind


def chaos_weights_to_common(
    raw: Any,
    *,
    raw_count: float | None,
    resolve=lambda name: name,
) -> list[dict[str, Any]]:
    """All non-blank keys, ranked by weight. pct = set% when Raw count is known."""
    if not isinstance(raw, dict):
        return []
    items: list[tuple[str, float]] = []
    for name, weight in raw.items():
        label = str(name).strip()
        if not label:
            continue
        try:
            w = float(weight)
        except (TypeError, ValueError):
            continue
        if w < 0:
            continue
        items.append((label, w))
    items.sort(key=lambda pair: -pair[1])
    if raw_count is not None and raw_count > 0:
        denom = float(raw_count)
    else:
        denom = sum(w for _, w in items) or 1.0
    return [
        {"name": resolve(name), "pct": round(100.0 * w / denom, 3)}
        for name, w in items
    ]


def detail_raw_count(detail: dict[str, Any]) -> float | None:
    try:
        value = float(detail.get("Raw count"))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def usage_pct_from_chaos(detail: dict[str, Any]) -> float:
    try:
        usage = float(detail.get("usage") or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return usage * 100.0 if 0.0 <= usage <= 1.0 else usage


def chaos_species_row(
    display_name: str,
    detail: dict[str, Any],
    *,
    resolve_move,
    resolve_item,
    resolve_ability,
    teammates: dict[str, Any] | None = None,
    teammates_meta: dict[str, Any] | None = None,
    spreads: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    raw_count = detail_raw_count(detail)
    moves = chaos_weights_to_common(
        detail.get("Moves"), raw_count=raw_count, resolve=resolve_move
    )
    items = chaos_weights_to_common(
        detail.get("Items"), raw_count=raw_count, resolve=resolve_item
    )
    abilities = chaos_weights_to_common(
        detail.get("Abilities"), raw_count=raw_count, resolve=resolve_ability
    )
    featured: list[dict[str, Any]] = []
    if moves and items:
        fs: dict[str, Any] = {
            "item": items[0]["name"],
            "moves": [m["name"] for m in moves[:4] if str(m.get("name") or "").strip()],
        }
        if abilities:
            fs["ability"] = abilities[0]["name"]
        if spreads and spreads[0].get("nature"):
            fs["nature"] = spreads[0]["nature"]
        featured.append(fs)
    row: dict[str, Any] = {
        "name": display_name,
        "id": to_id(display_name),
        "usage_pct": usage_pct_from_chaos(detail),
        "common_moves": moves,
        "common_abilities": abilities,
        "common_items": items,
        "top_spreads": spreads or [],
        "featured_sets": featured,
        "source": "smogon-chaos",
    }
    if teammates is not None:
        row["teammates"] = teammates
    if teammates_meta is not None:
        row["teammates_meta"] = teammates_meta
    return row
