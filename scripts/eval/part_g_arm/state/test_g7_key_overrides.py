"""G7 is3_is4 Scarf+TW key_overrides (errata only; derived_keys.json untouched)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.eval.part_g_arm.state.errata_read import (
    acceptance_with_key_overrides,
    key_override_hand_note,
    key_override_leaves,
    load_derived_keys_effective,
)
from scripts.eval.part_g_arm.state.hand_audit_form import _key_text_with_errata

ROOT = Path(__file__).resolve().parents[4]
RAW = json.loads(
    (ROOT / "scripts/eval/part_g_v4/key_artifacts/derived_keys.json").read_text(
        encoding="utf-8"
    )
)


def test_raw_file_unchanged_effective_overrides():
    assert RAW["is3_is4"]["Dragapult"]["plus_32_scarf_tw"] == 638
    assert RAW["is3_is4"]["Pincurchin"]["max_stack"] == 218
    eff = load_derived_keys_effective()
    assert eff["is3_is4"]["Dragapult"]["plus_32_scarf_tw"] == 639
    assert eff["is3_is4"]["Dragapult"]["max_stack"] == 639
    assert eff["is3_is4"]["Pincurchin"]["plus_32_scarf_tw"] == 219
    assert eff["is3_is4"]["Pincurchin"]["max_stack"] == 219
    leaves = key_override_leaves()
    assert leaves["is3_is4.Dragapult.plus_32_scarf_tw"] == 639


def test_hand_audit_is4_acceptance_rewrite():
    raw = "Pincurchin max stack=218 < Alakazam-Mega"
    assert "219" in acceptance_with_key_overrides("IS4", raw)
    assert "218" not in acceptance_with_key_overrides("IS4", raw)
    text = _key_text_with_errata("IS4", raw)
    assert "219" in text and "ERRATA G7" in text
    assert key_override_hand_note("IS3")
