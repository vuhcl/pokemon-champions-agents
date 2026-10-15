"""Structural guard: every function that assigns or returns ``team_draft`` is classified.

A new writer must be added to WRITERS with a label, and a "validating" writer must
actually reach ``validate_team_value`` (spy check below). Scans ``recommender/``
for any function that assigns ``team_draft`` or builds any dict literal carrying a
``"team_draft"`` key (return values and ``out = {...}`` alike).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

VALIDATING = "validating"
CLEAR_ONLY = "clear-only"
NON_SPECIES_ITEM = "non-species/item"

# (relative path, function) -> label. Unlisted writers fail the scan.
WRITERS: dict[tuple[str, str], str] = {
    ("recommender/nodes.py", "initialize"): CLEAR_ONLY,  # empty slots
    ("recommender/nodes.py", "unlock_locked_slot"): CLEAR_ONLY,  # empty_slot()
    ("recommender/nodes.py", "commit_full_slot"): VALIDATING,
    ("recommender/nodes.py", "_apply_lock_single"): VALIDATING,
    ("recommender/nodes.py", "_apply_locks_batch"): VALIDATING,
    ("recommender/nodes.py", "record_rejection"): CLEAR_ONLY,  # species=Attr()
    ("recommender/nodes.py", "restore_superseded"): VALIDATING,
    ("recommender/nodes.py", "reset_team"): CLEAR_ONLY,
    ("recommender/reconcile.py", "_reconcile_out"): CLEAR_ONLY,  # _apply_mismatch only clears
    ("recommender/propose.py", "fill_team_draft"): NON_SPECIES_ITEM,  # role/moves/spread/ability
    ("recommender/reconcile.py", "reconcile_on_archetype_change"): CLEAR_ONLY,  # _apply_mismatch only clears
    # Scanner false positives, no team_draft write into state:
    ("recommender/constraint_enforcement.py", "matches_species"): NON_SPECIES_ITEM,  # rebinds a local
    ("recommender/nodes_classify.py", "_apply_team_review_roster_gate"): NON_SPECIES_ITEM,  # display dict
    ("recommender/support_needs.py", "_threat_speeds"): NON_SPECIES_ITEM,  # input dict to a reader
    ("recommender/usage_data.py", "_trim_unneeded_weather_moves"): NON_SPECIES_ITEM,  # input dict to a reader
}


def _touches_team_draft(fn: ast.AST) -> bool:
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                for sub in ast.walk(t):
                    if isinstance(sub, ast.Constant) and sub.value == "team_draft":
                        return True
                    if isinstance(sub, ast.Name) and sub.id == "team_draft":
                        return True
        if isinstance(node, ast.Dict) and any(
            isinstance(k, ast.Constant) and k.value == "team_draft" for k in node.keys
        ):
            return True
    return False


def _found_writers() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for path in sorted((ROOT / "recommender").rglob("*.py")):
        tree = ast.parse(path.read_text())
        rel = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _touches_team_draft(node):
                found.add((rel, node.name))
    return found


def test_every_team_draft_writer_is_classified():
    found = _found_writers()
    unlisted = sorted(found - set(WRITERS))
    assert unlisted == [], f"unclassified team_draft writers: {unlisted}"
    stale = sorted(set(WRITERS) - found)
    assert stale == [], f"allowlist entries that no longer write team_draft: {stale}"


def _calls(path: str, name: str) -> set[str]:
    tree = ast.parse((ROOT / path).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return {
                n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", "")
                for n in ast.walk(node)
                if isinstance(n, ast.Call)
            }
    raise AssertionError(f"{path}:{name} not found")


# This spy check proves each validating writer *contains* a call to
# _validated_team_value, not that the call precedes the write. Ordering (a refusal
# leaves team_draft untouched) is covered by the behavior tests in
# tests/recommender/test_team_validation.py.
@pytest.mark.parametrize(
    "path,name", sorted(k for k, v in WRITERS.items() if v == VALIDATING)
)
def test_validating_writers_reach_the_validator(path, name):
    assert "_validated_team_value" in _calls(path, name)


def test_validated_team_value_calls_validate_team_value():
    assert "validate_team_value" in _calls("recommender/nodes.py", "_validated_team_value")
