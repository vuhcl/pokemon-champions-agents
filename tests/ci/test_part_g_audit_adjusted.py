"""audit_adjusted.py on a synthetic exception CSV: the adjusted counts, canary exclusion, unprefixed notes, and the refusals."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

V4 = Path(__file__).resolve().parents[2] / "scripts/eval/part_g_v4"
sys.path.insert(0, str(V4))
import audit_adjusted as aa  # noqa: E402
import scorer as sc  # noqa: E402

GATE = {"false": 2, "scored": 300, "cp_upper_bound": sc.cp_upper(2, 300), "max_false_tolerated_at_n": sc.max_false_tolerated(300), "passes_gate": True}
ROWS = [
    {"item_id": "a_1", "reviewed": "1", "exception_type": "missed_claim", "claim_text": "alpha", "note": "FALSE: wrong HP"},
    {"item_id": "a_2", "reviewed": "1", "exception_type": "missed_claim", "claim_text": "beta", "note": "TRUE"},
    {"item_id": "a_3", "reviewed": "1", "exception_type": "missed_claim", "claim_text": "gamma", "note": "TRUE, matches key"},
    {"item_id": "a_4", "reviewed": "1", "exception_type": "missed_claim", "claim_text": "delta", "note": "unclear"},
    {"item_id": "a_5", "reviewed": "1", "exception_type": "missed_claim", "claim_text": "canary text", "note": "FALSE"},  # matched to a canary below
    {"item_id": "a_6", "reviewed": "1", "exception_type": "wrong_verdict", "claim_text": "eps", "note": "FALSE"},  # not a missed_claim: ignored
    {"item_id": "a_7", "reviewed": "1", "exception_type": "", "claim_text": "", "note": "FALSE"},  # reviewed only, no exception
]
CANARIES = [{"item_id": "a_5", "canary_type": "missed_claim", "target_claim_text": "canary text"}]


def test_adjusted_counts():
    r = aa.adjust(GATE, ROWS, CANARIES)
    assert r["canary_rows_excluded"] == 1 and r["missed_claim_rows_after_canary_removal"] == 4
    assert (r["missed_noted_false"], r["missed_noted_true"], r["missed_unprefixed_not_scored"]) == (1, 2, 1)
    assert r["adjusted"]["false"] == 3 and r["adjusted"]["scored"] == 303
    assert r["adjusted"]["cp_upper_bound"] == sc.cp_upper(3, 303) and r["adjusted"]["max_false_tolerated_at_n"] == sc.max_false_tolerated(303)
    assert r["scorer_only"]["false"] == 2 and r["scorer_only"]["scored"] == 300  # the scorer-only numbers sit beside, unchanged


def test_without_a_canary_match_the_row_counts():
    assert aa.adjust(GATE, ROWS, [])["adjusted"]["false"] == 4


def run_cli(tmp_path, sha, gate=True):
    log = tmp_path / "log.csv"
    with log.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["item_id", "reviewed", "exception_type", "claim_text", "note"])
        w.writeheader()
        w.writerows(ROWS)
    out, can = tmp_path / "out.json", tmp_path / "can.json"
    out.write_text(json.dumps({"gate": GATE} if gate else {"headline": "withheld"}))
    can.write_text(json.dumps({"canaries": CANARIES}))
    return subprocess.run([sys.executable, str(V4 / "audit_adjusted.py"), "--scorer-output", str(out), "--exceptions", str(log), "--exception-log-sha256", sha, "--canaries", str(can)],
                          capture_output=True, text=True)


def test_refuses_an_unverified_log(tmp_path):
    r = run_cli(tmp_path, "0" * 64)
    assert r.returncode != 0 and "not committed and hashed" in r.stderr


def test_refuses_a_scorer_output_without_a_gate_block(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "exception_log_verified", lambda *a, **k: (True, ""))  # subprocess is separate: check main() in-process instead
    monkeypatch.setattr(sys, "argv", ["x", "--scorer-output", str(tmp_path / "o.json"), "--exceptions", "l", "--exception-log-sha256", "x", "--canaries", "c"])
    (tmp_path / "o.json").write_text(json.dumps({"headline": "withheld"}))
    with pytest.raises(SystemExit) as e:
        aa.main()
    assert "no gate block" in str(e.value)
