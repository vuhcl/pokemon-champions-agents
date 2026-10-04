"""M-B showdown_teammates descriptor stays byte-identical after shared-helper refactor."""

from __future__ import annotations

from recommender.teammates import TEAMMATE_LIMIT
from scripts.extract_usage.fetch_usage_mb import (
    build_snapshot,
    showdown_teammates_descriptor,
)

# Frozen pre-refactor M-B descriptor (byte-identical contract).
_EXPECTED_TEAMMATES = {
    "source_field": "Teammates",
    "weight_kind": "chaos_weight",
    "percentage_kind": "conditional_probability",
    "denominator_rule": "max(sum(valid Abilities), sum(valid Teammates) / 6, 1)",
    "limit": TEAMMATE_LIMIT,
    "caveats": [
        "weighted ladder estimate, not independent sample count",
        "not curated tournament data",
        "retained top-10 rows only",
    ],
}


def test_showdown_teammates_descriptor_matches_pre_refactor_mb():
    assert showdown_teammates_descriptor() == _EXPECTED_TEAMMATES


def test_mb_build_snapshot_meta_uses_shared_descriptor():
    snap = build_snapshot(
        {},
        {},
        {"number of battles": 1},
        month="2026-07",
        format_id="gen9championsvgc2026regmb",
        rating=1500,
        regulation="champions-reg-mb",
        source="smogon-chaos",
    )
    assert snap["meta"]["showdown_teammates"] == _EXPECTED_TEAMMATES
    assert snap["meta"]["showdown_teammates"] == showdown_teammates_descriptor()
