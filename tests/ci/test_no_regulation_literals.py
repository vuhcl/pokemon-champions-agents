"""AST regulation-literal scanner (enforce after PR-B2c)."""

from __future__ import annotations

import ast
from pathlib import Path

from recommender.regulation_registry import (
    CHAMPIONS_MOD_DEFAULT_ALLOWLIST,
    _PRODUCT_MOD_LITERAL,
    _TAG_LITERAL,
    iter_regulation_literal_hits,
    iter_regulation_parameter_default_hits,
    iter_required_regulation_default_hits,
)

# Product + CI paths allowed to carry concrete regulation literals.
_ALLOW_PREFIXES = (
    "recommender/regulation_registry.py",
    "recommender/ids.py",
    "recommender/format.py",
    "recommender/session.py",
    "recommender/usage_live.py",
    "recommender/usage_data.py",
    "recommender/usage_split.py",
    "recommender/usage_chaos.py",
    "recommender/role_compendium_setup_constants.py",
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
    "tests/ci/test_spread_pct_kind.py",
    "tests/ci/test_showdown_teammates_descriptor.py",
    "tests/ci/test_split_usage_monolith.py",
    "tests/recommender/test_usage_archive_fallback.py",
    "tests/recommender/test_usage_live_mc.py",
    "tests/recommender/test_usage_split.py",
    "tests/recommender/test_query_counters.py",
    "scripts/eval/",
)


def _allowed_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _ALLOW_PREFIXES)


def test_no_tag_literals_outside_allowlist():
    """Concrete regulation tags in product ``recommender/`` outside allowlisted paths."""
    bad = []
    for path, ln, value in iter_regulation_literal_hits(roots=None):
        if not path.startswith("recommender/"):
            continue
        if _PRODUCT_MOD_LITERAL.search(value):
            continue
        if _allowed_path(path):
            continue
        if _TAG_LITERAL.search(value) or "Reg M-" in value:
            bad.append(f"{path}:{ln}: {value!r}")
    assert not bad, "tag/format literals outside allowlist:\n" + "\n".join(bad[:40])


def test_no_regulation_tag_parameter_defaults():
    """Tag literals as param defaults always fail; ``champions`` only via allowlist."""
    bad = []
    for path, ln, fn, value in iter_regulation_parameter_default_hits():
        if not path.startswith("recommender/"):
            continue
        if _TAG_LITERAL.search(value):
            bad.append(f"{path}:{ln}: {fn} default={value!r}")
            continue
        if _PRODUCT_MOD_LITERAL.search(value):
            if (path, fn) not in CHAMPIONS_MOD_DEFAULT_ALLOWLIST:
                bad.append(f"{path}:{ln}: {fn} default={value!r} (not in allowlist)")
    assert not bad, "illegal regulation parameter defaults:\n" + "\n".join(bad[:40])


def test_required_regulation_apis_have_no_default():
    hits = iter_required_regulation_default_hits()
    assert not hits, "required regulation APIs still have defaults:\n" + "\n".join(
        f"{p}:{ln}: {fn}" for p, ln, fn, _ in hits
    )


def test_red_first_slot_fill_context_regulation_has_no_tag_default():
    """One of the four B2b mc defaults: SlotFillContext.regulation must be required."""
    src = Path("recommender/slot_fill.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "SlotFillContext":
            for stmt in node.body:
                if not isinstance(stmt, ast.AnnAssign):
                    continue
                if not isinstance(stmt.target, ast.Name):
                    continue
                if stmt.target.id != "regulation":
                    continue
                assert stmt.value is None, (
                    "SlotFillContext.regulation must not have a concrete default "
                    f"(found {ast.dump(stmt.value)})"
                )
                return
    raise AssertionError("SlotFillContext.regulation field not found")
