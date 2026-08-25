"""Panel ↔ pair-file species id bridge (Champions Floette lineage only)."""

from __future__ import annotations

# Champions: only Eternal Flower Floette can Mega Evolve (not plain Floette).
_FLOETTE_DENY_SID = "floette"
_FLOETTE_ETERNAL_SID = "floetteeternal"
_FLOETTE_MEGA_SID = "floettemega"
# Pikalytics team-usage pairs label the lineage `floetteeternal`; Showdown panel
# primaries use `floettemega`. Co-occurrence lookup only — not a calc/legality alias.
_PAIR_LOOKUP_ALIASES = {_FLOETTE_MEGA_SID: _FLOETTE_ETERNAL_SID}


def pair_lookup_species_id(species_id: str) -> str:
    """Map panel species id → id used in team-composition pair files."""
    return _PAIR_LOOKUP_ALIASES.get(species_id, species_id)
