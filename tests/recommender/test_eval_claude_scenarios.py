"""Thin check: Claude eval scenarios stay at 17 and force the LLM claim path."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recommender.system_claims import negation_matches_claim
from scripts.eval.scenarios_claude import build_scenarios


def test_claude_scenarios_count_and_claim_guards():
    scenarios = build_scenarios()
    assert len(scenarios) == 17
    by_comp = {}
    for sc in scenarios:
        by_comp[sc.component] = by_comp.get(sc.component, 0) + 1
        if sc.claim_for_deterministic_guard is not None:
            assert not negation_matches_claim(
                sc.user_text, sc.claim_for_deterministic_guard
            )
    assert by_comp == {
        "turn_intent_parser": 8,
        "claim_correction": 4,
        "full_build_confirmation": 5,
    }
    assert sum(1 for s in scenarios if s.known_deferred) == 1
