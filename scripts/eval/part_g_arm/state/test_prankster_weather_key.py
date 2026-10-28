"""Reference trajectory: one find_species per weather move; union == key (no model)."""

from __future__ import annotations

import hashlib
import json

from scripts.eval.part_g_arm.state.build_prankster_weather_key import OUT, build
from scripts.eval.part_g_arm.state.class_scorer import score_turn
from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.harness import snapshot
from scripts.eval.part_g_arm.state.tools import find_species, mechanical_class


def test_key_artifact_matches_rebuild_and_sha():
    rebuilt = build()
    on_disk = json.loads(OUT.read_text(encoding="utf-8"))
    assert on_disk["species_set"] == rebuilt["species_set"]
    assert on_disk["count"] == 6
    text = OUT.read_text(encoding="utf-8")
    sha = hashlib.sha256(text.encode()).hexdigest()
    # Pinned in LAST_FIND_SPECIES.md — fail if key drifted without regenerating the note.
    assert sha == "cbef455d7ff1610152f64fc17ad5e33796e82fd05669a8fca93d8b0fa47652d3"


def test_reference_trajectory_union_equals_key():
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
