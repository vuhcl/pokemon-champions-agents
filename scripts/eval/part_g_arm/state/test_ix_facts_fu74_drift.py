"""FU74: ix_facts_fu74.json must match a fresh regeneration from pinned data."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.eval.part_g_arm.state.keys_fu74.build_fu74_artifacts import collect_ix_facts

FACTS = Path(__file__).resolve().parent / "keys_fu74" / "ix_facts_fu74.json"


def test_ix_facts_fu74_matches_fresh_run() -> None:
    committed = json.loads(FACTS.read_text(encoding="utf-8"))
    fresh = collect_ix_facts()
    assert fresh == committed


def test_keys_fu72_key_hash_unchanged_in_fu74_manifest() -> None:
    manifest = json.loads(
        (Path(__file__).resolve().parent / "keys_fu74" / "KEYS_MANIFEST_FU74.json").read_text(
            encoding="utf-8"
        )
    )
    fu72 = json.loads(
        (Path(__file__).resolve().parent / "keys_fu72" / "KEYS_MANIFEST_FU72.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["keys_fu72_key_hash"] == fu72["key_hash"]
    assert fu72["key_hash"] == "246e5a7daa194d42897e0ef2e89dcf470e9a9646ea232a077f42255949a0fa02"
    assert manifest.get("manifest_self_hashed") is False
    assert not any(p.endswith("KEYS_MANIFEST_FU74.json") for p in manifest["files"])


def test_ix7_optional_includes_check_item_legal() -> None:
    hand = json.loads(
        (Path(__file__).resolve().parent / "keys_fu74" / "hand_keys_fu74.json").read_text(
            encoding="utf-8"
        )
    )
    t = hand["turns"]["IX7__t1"]
    assert "check_item_legal" in t["optional_tools"].split(";")
    assert "check_item_legal" in t["points"][2]["text"]
