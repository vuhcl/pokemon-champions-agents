"""B2c: required regulation + ranking on M-C."""

from __future__ import annotations

import inspect
from dataclasses import MISSING

from recommender.by_usage import query_by_usage
from recommender.ids import regulation_file_tag, to_id
from recommender.move_narrowing import pick_default_and_alternatives
from recommender.slot_fill import SlotFillContext, _candidate_satisfies_need, _matching_needs_for
from recommender.usage_data import (
    ingame_ladder_species_map,
    ingame_species_map,
    load_usage,
)


def test_core_loaders_require_regulation():
    sig = inspect.signature(load_usage)
    assert sig.parameters["regulation"].default is inspect.Parameter.empty


def test_four_b2b_defaults_no_longer_tag_defaults():
    """The four B2b mc defaults are required now (no concrete default)."""
    for fn in (_candidate_satisfies_need, _matching_needs_for, pick_default_and_alternatives):
        param = inspect.signature(fn).parameters["regulation"]
        assert param.default is inspect.Parameter.empty
    field = SlotFillContext.__dataclass_fields__["regulation"]
    assert field.default is MISSING
    assert field.default_factory is MISSING


def test_query_by_usage_ranks_mc():
    """Ranks come from the M-C ingame file; do not hardcode species or rank numbers."""
    assert regulation_file_tag("champions") == "champions-reg-mc"
    snap = load_usage("champions")
    assert (snap.get("meta") or {}).get("regulation") == "champions-reg-mc"

    # Same resolution as query_by_usage: ladder usage_rank, else filtered ingame map.
    ladder = ingame_ladder_species_map("champions")
    ig = ingame_species_map("champions")
    assert ladder

    def expected_rank(sid: str) -> int | None:
        rank = (ladder.get(sid) or {}).get("usage_rank")
        if rank is None:
            rank = (ig.get(sid) or {}).get("usage_rank")
        return int(rank) if rank is not None else None

    expected = {
        sid: rank
        for sid in ladder
        if (rank := expected_rank(sid)) is not None
    }
    assert expected
    # 1-based ranks; lower rank = higher usage (descending popularity).
    rank_vals = sorted(expected.values())
    assert rank_vals[0] == 1
    assert all(rank_vals[i] < rank_vals[i + 1] for i in range(len(rank_vals) - 1))

    by_rank = sorted(expected.items(), key=lambda item: item[1])
    top_sid, top_rank = by_rank[0]
    top_name = str((ladder.get(top_sid) or {}).get("name") or top_sid)

    top_rows = query_by_usage(n=5, regulation="champions")
    assert top_rows
    assert to_id(top_rows[0].spec.get("species") or top_rows[0].form) == top_sid
    assert top_rows[0].usage_rank == top_rank
    assert (top_rows[0].spec.get("species") or top_rows[0].form) == top_name

    sample = [
        by_rank[0][0],
        by_rank[len(by_rank) // 4][0],
        by_rank[len(by_rank) // 2][0],
        by_rank[-1][0],
    ]
    got = {
        to_id(r.spec.get("species") or r.form): r.usage_rank
        for r in query_by_usage(n=500, regulation="champions")
    }
    for sid in sample:
        assert got[sid] == expected[sid]

    ordered = [
        r.usage_rank
        for r in query_by_usage(n=20, regulation="champions")
        if r.usage_rank is not None
    ]
    assert ordered == sorted(ordered)
    assert all(ordered[i] < ordered[i + 1] for i in range(len(ordered) - 1))
