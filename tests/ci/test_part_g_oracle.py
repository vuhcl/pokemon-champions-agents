"""Oracle sanity: it must be able to fail. Synthetic items; a wrong key gives FALSE, a right one TRUE (no calc needed)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from recommender.arm_tools import ArmTools  # noqa: E402
from scripts.eval.part_g_arm import oracle  # noqa: E402

TOOLS = ArmTools(regulation="champions", allow_live=False)


def _typing(has_type: bool) -> dict:
    gt = {"species": "Aromatisse", "asked_type": "Fairy", "has_type": has_type, "types": ["Fairy"]}
    return {"claim_type": "typing", "claims": [{"kind": "has_type", "ground_truth": gt}]}


def test_oracle_scores_true_and_false_and_reports_diffs():
    _, claims, diffs = oracle.run_item(TOOLS, _typing(True))
    assert [c.verdict.value for c in claims] == ["TRUE"] and diffs == []
    _, claims, _ = oracle.run_item(TOOLS, _typing(False))
    assert [c.verdict.value for c in claims] == ["FALSE"]
    it = _typing(True)
    it["claims"][0]["ground_truth"]["types"] = ["Steel"]
    assert oracle.run_item(TOOLS, it)[2] == [{"check": "types", "tool": ["Fairy"], "key": ["Steel"]}]


def test_top_with_ties_extends_only_on_equal_pct():
    rows = [("a", 9.0), ("b", 8.0), ("c", 7.0), ("d", 6.0), ("e", 5.0), ("f", 5.0), ("g", 4.0)]
    assert oracle.top_with_ties(rows) == list("abcdef")
    assert oracle.top_with_ties([("x", None)] * 7) == ["x"] * 5  # no percentages: never extended


DEV_BATTERY = Path(__file__).resolve().parents[2] / "scripts/eval/part_g_arm/dev_seed1/claim_battery_v4.json"


@pytest.mark.skipif(os.environ.get("CALC_LIVE") != "1", reason="needs live calc service")
def test_derived_ko_fields_agree_with_calc_kochance_and_key_on_all_seed1_damage_items():
    tools = ArmTools(regulation="champions", allow_live=False)
    items = [i for i in json.loads(DEV_BATTERY.read_text())["items"] if i["claim_type"] == "damage"]
    assert len(items) == 53
    disagree = []  # kochance has no `chance` key for 'possible nHKO' results; absent reads as not 1
    for it in items:
        gt = it["claims"][0]["ground_truth"]
        r = tools.call("calc_damage", oracle.damage_args(gt))
        kc = r["kochance"]
        if r["guaranteed_ko"] != (kc.get("chance") == 1 and kc["n"] == 1) or r["guaranteed_ko"] != gt["guaranteed_ko"] \
                or r["rolls_that_ko"] != gt["rolls_ko_of_16"]:
            disagree.append((it["id"], r["guaranteed_ko"], r["rolls_that_ko"], kc, gt["guaranteed_ko"], gt["rolls_ko_of_16"]))
    assert disagree == []
