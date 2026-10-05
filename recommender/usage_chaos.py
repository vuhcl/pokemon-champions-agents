"""Smogon chaos stats → usage rows (no move/item cap).

common_* pct = chaos weight / sum(Abilities weights) * 100 (meta
showdown_pct_kind = weight_over_abilities_sum). When Abilities are empty:
items/abilities use that bucket's weight sum; moves use sum(Items), or fail
closed (empty common_moves + showdown_moves_pct_unscaled). top_spreads[].pct
is raw chaos Spreads weight (pct_kind=chaos_weight), not divided by Raw.
"""

from __future__ import annotations

from typing import Any

from recommender.ids import to_id
from recommender.usage_data import load_usage

# Archive-tool / URL helpers may still name historical M-B chaos ids explicitly.
DEFAULT_MONTH = "2026-07"
DEFAULT_FORMAT = "gen9championsvgc2026regmb"
DEFAULT_RATING = 1500

SHOWDOWN_PCT_KIND_PUBLISHED = "weight_over_abilities_sum"
SHOWDOWN_PCT_KIND_LEGACY = "weight_over_raw_count"


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
    kind = str(raw or SHOWDOWN_PCT_KIND_LEGACY)
    if kind == "set":
        return SHOWDOWN_PCT_KIND_LEGACY
    return kind


def _bucket_weight_sum(raw: Any) -> float | None:
    if not isinstance(raw, dict):
        return None
    total = 0.0
    any_ok = False
    for weight in raw.values():
        try:
            w = float(weight)
        except (TypeError, ValueError):
            continue
        if w < 0:
            continue
        total += w
        any_ok = True
    if not any_ok or total <= 0:
        return None
    return total


def detail_ability_weight_sum(detail: dict[str, Any]) -> float | None:
    return _bucket_weight_sum(detail.get("Abilities"))


def detail_item_weight_sum(detail: dict[str, Any]) -> float | None:
    return _bucket_weight_sum(detail.get("Items"))


def chaos_weights_to_common(
    raw: Any,
    *,
    denom: float | None,
    resolve=lambda name: name,
) -> list[dict[str, Any]]:
    """All non-blank keys, ranked by weight. pct = 100 * w / denom."""
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
    if denom is not None and denom > 0:
        d = float(denom)
    else:
        d = sum(w for _, w in items) or 1.0
    return [
        {"name": resolve(name), "pct": round(100.0 * w / d, 3)}
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


def common_sets_from_detail(
    detail: dict[str, Any],
    *,
    resolve_move=lambda name: name,
    resolve_item=lambda name: name,
    resolve_ability=lambda name: name,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, bool],
]:
    """Moves/items/abilities on published scale; fallback flags for meta counts."""
    ab_sum = detail_ability_weight_sum(detail)
    item_sum = detail_item_weight_sum(detail)
    flags = {
        "items_bucket": False,
        "moves_via_items": False,
        "moves_unscaled": False,
    }
    if ab_sum is not None:
        moves = chaos_weights_to_common(
            detail.get("Moves"), denom=ab_sum, resolve=resolve_move
        )
        items = chaos_weights_to_common(
            detail.get("Items"), denom=ab_sum, resolve=resolve_item
        )
        abilities = chaos_weights_to_common(
            detail.get("Abilities"), denom=ab_sum, resolve=resolve_ability
        )
        return moves, items, abilities, flags

    # Empty Abilities: items/abilities → bucket sum; moves → items sum or fail closed.
    items = chaos_weights_to_common(
        detail.get("Items"), denom=None, resolve=resolve_item
    )
    abilities = chaos_weights_to_common(
        detail.get("Abilities"), denom=None, resolve=resolve_ability
    )
    if items:
        flags["items_bucket"] = True
    if item_sum is not None:
        moves = chaos_weights_to_common(
            detail.get("Moves"), denom=item_sum, resolve=resolve_move
        )
        flags["moves_via_items"] = True
    else:
        moves = []
        if isinstance(detail.get("Moves"), dict) and any(
            str(k).strip() for k in detail["Moves"]
        ):
            flags["moves_unscaled"] = True
    return moves, items, abilities, flags


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
    moves, items, abilities, flags = common_sets_from_detail(
        detail,
        resolve_move=resolve_move,
        resolve_item=resolve_item,
        resolve_ability=resolve_ability,
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
    if flags["items_bucket"]:
        row["showdown_pct_fallback_items_bucket"] = True
    if flags["moves_via_items"]:
        row["showdown_pct_fallback_moves_via_items"] = True
    if flags["moves_unscaled"]:
        row["showdown_moves_pct_unscaled"] = True
    if teammates is not None:
        row["teammates"] = teammates
    if teammates_meta is not None:
        row["teammates_meta"] = teammates_meta
    return row


def fallback_counts_from_species(showdown: dict[str, Any]) -> dict[str, int]:
    """Aggregate per-species fallback flags into meta counters."""
    items_bucket = 0
    moves_via_items = 0
    moves_unscaled = 0
    for row in showdown.values():
        if not isinstance(row, dict):
            continue
        if row.get("showdown_pct_fallback_items_bucket"):
            items_bucket += 1
        if row.get("showdown_pct_fallback_moves_via_items"):
            moves_via_items += 1
        if row.get("showdown_moves_pct_unscaled"):
            moves_unscaled += 1
    return {
        "showdown_pct_fallback_items_bucket": items_bucket,
        "showdown_pct_fallback_moves_via_items": moves_via_items,
        "showdown_pct_fallback_moves_unscaled": moves_unscaled,
    }
