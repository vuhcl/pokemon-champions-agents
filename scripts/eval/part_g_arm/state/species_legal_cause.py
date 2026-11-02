"""tool_fields: enrich check_species_legal with a pin-derived cause."""

from __future__ import annotations

from typing import Any

from recommender.ids import to_id
from recommender.legality import is_species_legal, load_snapshot


def illegal_species_cause(species: str, *, snap: dict[str, Any] | None = None) -> str | None:
    """Human-readable cause when species is in the snapshot but not legal, else None."""
    snap = snap or load_snapshot()
    sid = to_id(species)
    e = (snap.get("species") or {}).get(sid)
    if not e:
        return None
    if is_species_legal(snap, sid):
        return None
    # Prefer format ban tags (Mythical / Restricted Legendary) — user-facing cause.
    ban = set((snap.get("flat_rules") or {}).get("banlist") or [])
    hit = ban & set(e.get("effective_tags") or [])
    if hit:
        for prefer in ("Mythical", "Restricted Legendary"):
            if prefer in hit:
                return prefer
        return sorted(hit)[0]
    if e.get("tier") == "Illegal":
        return "tier Illegal"
    ns = e.get("is_nonstandard")
    if ns is not None:
        return f"is_nonstandard={ns}"
    return "illegal (pin)"


def enrich_check_species_legal(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict) or result.get("status") != "ok":
        return result
    if result.get("legal") is not False:
        return result
    query = result.get("query")
    if not isinstance(query, str):
        return result
    cause = illegal_species_cause(query)
    if cause is None:
        return result
    return {**result, "cause": cause}
