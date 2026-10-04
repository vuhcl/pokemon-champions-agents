"""AST regulation-literal scanner (warn-only until PR-B2c enforces)."""

from __future__ import annotations

from pathlib import Path

from recommender.regulation_registry import iter_regulation_literal_hits

# Paths allowed to carry regulation literals while the allowlist is warn-only.
# B2c shrinks this set and flips the test to fail on leftovers.
_ALLOW_PREFIXES = (
    "recommender/regulation_registry.py",
    "recommender/ids.py",
    "recommender/format.py",
    "recommender/session.py",
    "data/",  # not scanned (py only); listed for documentation
    "scripts/ci/regulation_",
    "scripts/ci/validate_active_regulation_schedule.py",
    "scripts/ci/champions_news.py",
    "scripts/ci/usage_refresh_mc_gate.py",
    "scripts/extract_usage/",
    "tests/ci/test_active_regulation.py",
    "tests/ci/test_no_regulation_literals.py",
    "tests/ci/test_regulation_extract_gate.py",
    "tests/ci/test_graft_showdown_mc.py",
    "tests/ci/test_mc_usage_preserve_wiring.py",
    "tests/ci/test_usage_refresh_mc_gate.py",
    "tests/ci/test_compendium_refresh_gate.py",
    "tests/ci/test_champions_news_season.py",
    "tests/ci/test_vgcpastes_",
    "tests/recommender/",
    "scripts/eval/",
)


def _allowed(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _ALLOW_PREFIXES)


def test_regulation_literal_scan_warn_only(capsys):
    hits = iter_regulation_literal_hits()
    outside = [(p, ln, v) for p, ln, v in hits if not _allowed(p)]
    # Warn-only: surface the count for CI logs; do not fail until B2c.
    print(
        f"WARN regulation_literals: total={len(hits)} "
        f"outside_allowlist={len(outside)} (warn-only until B2c)"
    )
    if outside[:10]:
        for path, ln, value in outside[:10]:
            print(f"  {path}:{ln}: {value!r}")
    assert isinstance(hits, list)
    # Scanner must see the registry itself (smoke that AST walk works).
    assert any(p == "recommender/regulation_registry.py" for p, _, _ in hits)
