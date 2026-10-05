"""B2c: required regulation + ranking on M-C."""

from __future__ import annotations

import inspect
from dataclasses import MISSING

from recommender.by_usage import query_by_usage
from recommender.ids import to_id
from recommender.move_narrowing import pick_default_and_alternatives
from recommender.slot_fill import SlotFillContext, _candidate_satisfies_need, _matching_needs_for
from recommender.usage_data import load_usage


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
    rows = query_by_usage(n=5, regulation="champions")
    top = [r.spec.get("species") or r.form for r in rows]
    assert top[0] == "Rillaboom"
    ranks = {
        to_id(r.spec.get("species") or r.form): r.usage_rank
        for r in query_by_usage(n=500, regulation="champions")
    }
    assert ranks[to_id("Rillaboom")] == 1
    assert ranks[to_id("Farigiraf")] == 15
    assert ranks[to_id("Beedrill")] == 183
    assert ranks[to_id("Absol")] == 52
