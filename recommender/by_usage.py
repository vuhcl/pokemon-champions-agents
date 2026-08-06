"""query_by_usage — bootstrap ranking by usage alone (ADR-022 Amendment 2026-08-02d).

Thin wrapper around rank_and_cut: no axes, no tiering, no verification.
Usage data is ordinal (usage_rank: 1 = most used), not percentage — order ascending.
"""

from __future__ import annotations

from recommender.calc_client import PokemonSpecOptional
from recommender.ids import to_id
from recommender.legality import is_species_legal, load_snapshot
from recommender.ranking import rank_and_cut
from recommender.state import ThreatCandidate
from recommender.usage_data import ingame_species_map

# Same regulation tag as counters.DEFAULT_REGULATION (duplicated to avoid coupling).
_REGULATION = "champions-reg-mb"


def _usage_key(c: ThreatCandidate) -> tuple:
    """Ordinal usage_rank: lower rank number = more popular; None last."""
    return (c.usage_rank is None, c.usage_rank if c.usage_rank is not None else 10**9)


def query_by_usage(
    pool: list[PokemonSpecOptional] | None = None,
    n: int = 20,
) -> list[ThreatCandidate]:
    """Rank a candidate pool by usage alone; cut to ``n``.

    ``pool=None`` uses the full legal species set (snapshot + is_species_legal).
    When ``pool`` is provided, rank those entries (illegal / missing species skipped).
    Caller-provided specs are preserved; default-pool specs are bare ``{species}``.
    """
    snap = load_snapshot()
    ig = ingame_species_map(_REGULATION)
    cands: list[ThreatCandidate] = []

    if pool is None:
        for sid, entry in snap["species"].items():
            if not is_species_legal(snap, sid):
                continue
            ig_entry = ig.get(sid) or {}
            rank = ig_entry.get("usage_rank")
            rank_i = int(rank) if rank is not None else None
            name = str(ig_entry.get("name") or entry.get("name") or sid)
            cands.append(
                ThreatCandidate(
                    ladder_species=name,
                    usage_rank=rank_i,
                    form=name,
                    showdown_usage_pct=None,
                    showdown_formes=(),
                    spec={"species": name},
                    build_source="ingame",
                )
            )
    else:
        seen: set[str] = set()
        for spec in pool:
            species = spec.get("species")
            if not species:
                continue
            sid = to_id(species)
            if sid in seen or not is_species_legal(snap, sid):
                continue
            seen.add(sid)
            entry = snap["species"].get(sid) or {}
            ig_entry = ig.get(sid) or {}
            rank = ig_entry.get("usage_rank")
            rank_i = int(rank) if rank is not None else None
            name = str(ig_entry.get("name") or entry.get("name") or species)
            cands.append(
                ThreatCandidate(
                    ladder_species=name,
                    usage_rank=rank_i,
                    form=name,
                    showdown_usage_pct=None,
                    showdown_formes=(),
                    spec=spec,
                    build_source="ingame",
                )
            )

    # tier=None → slack unused; flat sort-and-slice.
    return rank_and_cut(cands, key=_usage_key, n=n, tier=None, order="ascending")
