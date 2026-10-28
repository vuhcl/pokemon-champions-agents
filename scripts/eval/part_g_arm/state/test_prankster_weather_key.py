"""Prankster weather key independence + find_species union equality (no model)."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

from scripts.eval.part_g_arm.state.build_prankster_weather_key import OUT, HERE, build
from scripts.eval.part_g_arm.state.class_scorer import score_turn
from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.harness import snapshot
from scripts.eval.part_g_arm.state.tools import find_species, mechanical_class

KEY_SHA = "6dba1caac2d45135779779f7867f6f442163bdb3fef35ca6270d7c76329fb543"


def test_builder_does_not_import_find_species():
    src = (HERE / "build_prankster_weather_key.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names = [a.name for a in node.names]
            assert "find_species" not in names
            assert not (node.module or "").endswith("tools") or "find_species" not in names
        if isinstance(node, ast.Import):
            for a in node.names:
                assert "find_species" not in a.name


def test_key_artifact_matches_rebuild_and_sha():
    rebuilt = build()
    on_disk = json.loads(OUT.read_text(encoding="utf-8"))
    assert on_disk["species_set"] == rebuilt["species_set"]
    assert on_disk["count"] == 6
    text = OUT.read_text(encoding="utf-8")
    sha = hashlib.sha256(text.encode()).hexdigest()
    assert sha == KEY_SHA


def test_key_equals_find_species_union():
    """Equality check: independent key == five-call find_species union (builder unused)."""
    key = json.loads(OUT.read_text(encoding="utf-8"))
    st = empty_team()
    before = snapshot(st)
    union: set[str] = set()
    calls: list[dict] = []
    for move in key["weather_moves"]:
        result = find_species(st, ability="Prankster", learns_move=move["name"])
        assert result["status"] == "ok"
        union.update(result["species"])
        calls.append(
            {
                "name": "find_species",
                "args": {"ability": "Prankster", "learns_move": move["name"]},
                "result": result,
            }
        )
    after = snapshot(st)
    assert union == set(key["species_set"])
    observed = mechanical_class(before, after, calls)
    assert observed == "lookup only"
    scored = score_turn(
        observed_mech=observed,
        expected_key_class="SERVED",
        turn={"state_before": before, "state_after": after},
    )
    assert scored["match"] and scored["state_expectation_met"]
