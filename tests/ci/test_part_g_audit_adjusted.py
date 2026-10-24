"""audit_adjusted.py on synthetic exception CSVs: every branch of the adjustment and every refusal."""

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

T, F = sc.Verdict.TRUE, sc.Verdict.FALSE
GATE = {"false": 2, "scored": 300, "cp_upper_bound": sc.cp_upper(2, 300), "max_false_tolerated_at_n": sc.max_false_tolerated(300), "passes_gate": True}
CLAIMS = {"i1": [("speed is 100", T), ("hp 99", F)], "i2": [("alpha", T)], "i3": [("beta", F)], "i4": [("dup", T), ("dup", T)]}
CAN = [{"item_id": "c_1", "canary_type": "missed_claim", "target_claim_text": "canary text"}]


def row(item, typ, text, note):
    return {"item_id": item, "reviewed": "1", "exception_type": typ, "claim_text": text, "note": note}


def adj(rows, canaries=CAN, claims=CLAIMS):
    return aa.adjust(GATE, rows, canaries, claims)


def test_missed_claims_add_to_numerator_and_denominator_case_and_space_insensitive():
    r = adj([row("m1", "missed_claim", "a", "FALSE: wrong HP"), row("m2", "missed_claim", "b", "  true: ok"), row("m3", "missed_claim", "c", "false:x")])
    assert (r["missed_noted_false"], r["missed_noted_true"]) == (2, 1)
    assert (r["adjusted"]["false"], r["adjusted"]["scored"]) == (4, 303) and r["adjusted"]["cp_upper_bound"] == sc.cp_upper(4, 303)
    assert r["adjusted"]["max_false_tolerated_at_n"] == sc.max_false_tolerated(303) and r["scorer_only"]["false"] == 2 and r["scorer_only"]["scored"] == 300


@pytest.mark.parametrize("note", ["", "FALSE", "TRUE", "unclear", "NOW FALSE: x"])
def test_missed_claim_without_the_prefix_refuses_and_lists(note):
    bad = row("m1", "missed_claim", "a", note)
    r = adj([row("m2", "missed_claim", "b", "TRUE:"), bad])
    assert list(r) == ["refused"] and r["refused"][0]["row"] == bad


def test_wrong_rows_flip_in_both_directions_and_leave_n_alone():
    r = adj([row("i1", "wrong_verdict", "the speed is 100 here", "NOW FALSE: it is 101"),  # scorer TRUE -> false: +1
             row("i1", "wrong_extraction", "hp 99", "now true: the key says 99"),  # scorer FALSE -> true: -1
             row("i2", "wrong_verdict", "alpha", "NOW TRUE: agrees"),  # already TRUE: no change
             row("i3", "wrong_verdict", "beta", "NOW FALSE: agrees")])  # already FALSE: no change
    assert (r["scorer_true_now_false"], r["scorer_false_now_true"], r["wrong_rows_matched"]) == (1, 1, 4)
    assert (r["adjusted"]["false"], r["adjusted"]["scored"]) == (2, 300)
    assert adj([row("i2", "wrong_verdict", "alpha", "NOW FALSE: x")])["adjusted"]["false"] == 3
    assert adj([row("i3", "wrong_verdict", "beta", "NOW TRUE: x")])["adjusted"]["false"] == 1


@pytest.mark.parametrize("bad", [row("i2", "wrong_verdict", "alpha", "FALSE: x"), row("i2", "wrong_extraction", "alpha", "NOW MAYBE: x"), row("i2", "wrong_verdict", "alpha", ""),
                                 row("i2", "wrong_verdict", "something else", "NOW FALSE: x"),  # no claim matches
                                 row("zz", "wrong_verdict", "alpha", "NOW FALSE: x"),  # unknown item
                                 row("i4", "wrong_verdict", "dup", "NOW FALSE: x"),  # two claims match: ambiguous
                                 row("i2", "bogus", "alpha", "NOW FALSE: x")])
def test_wrong_rows_unprefixed_unmatched_or_ambiguous_refuse(bad):
    r = adj([bad])
    assert list(r) == ["refused"] and r["refused"][0]["row"] == bad


def test_two_rows_cannot_claim_the_same_claim_but_can_claim_two_duplicates():
    two = [row("i4", "wrong_verdict", "dup", "NOW FALSE: x")] * 2
    assert list(adj(two)) == ["refused"]  # each row sees two candidates the first time
    assert list(adj([row("i2", "wrong_verdict", "alpha", "NOW FALSE: x")] * 2)) == ["refused"]  # the second row finds the claim already used


def test_other_rows_are_listed_never_scored_and_canaries_leave_first():
    o = row("i1", "other", "x", "FALSE: whatever")
    r = adj([o, row("c_1", "missed_claim", "canary text", "no prefix at all")])  # the canary row would refuse if it were real
    assert r["other_rows_listed_not_scored"] == [o] and r["canary_rows_excluded"] == 1 and r["adjusted"]["false"] == 2 and r["adjusted"]["scored"] == 300
    assert adj([row("c_1", "missed_claim", "canary text", "no prefix at all")], canaries=[])["refused"]


def write(tmp_path, rows, gate):
    log, out, can = tmp_path / "log.csv", tmp_path / "out.json", tmp_path / "can.json"
    with log.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["item_id", "reviewed", "exception_type", "claim_text", "note"])
        w.writeheader()
        w.writerows(rows)
    out.write_text(json.dumps({"gate": gate} if gate else {"headline": "withheld"}))
    can.write_text(json.dumps({"canaries": CAN}))
    return log, out, can


def test_refuses_an_unverified_log(tmp_path):
    log, out, can = write(tmp_path, [], GATE)
    r = subprocess.run([sys.executable, str(V4 / "audit_adjusted.py"), "--scorer-output", str(out), "--exceptions", str(log), "--exception-log-sha256", "0" * 64, "--canaries", str(can),
                        "--answers", "a", "--battery", "b"], capture_output=True, text=True)
    assert r.returncode != 0 and "not committed and hashed" in r.stderr


def run_main(monkeypatch, tmp_path, gate, claims, rows=()):
    log, out, can = write(tmp_path, list(rows), gate)
    monkeypatch.setattr(sc, "exception_log_verified", lambda *a, **k: (True, ""))
    monkeypatch.setattr(aa, "scored_claims", lambda *a, **k: claims)
    monkeypatch.setattr(sys, "argv", ["x", "--scorer-output", str(out), "--exceptions", str(log), "--exception-log-sha256", "x", "--canaries", str(can), "--answers", "a", "--battery", "b"])
    return aa.main()


def test_refuses_without_a_gate_block_or_when_the_reextraction_disagrees(tmp_path, monkeypatch):
    with pytest.raises(SystemExit, match="no gate block"):
        run_main(monkeypatch, tmp_path, None, CLAIMS)
    with pytest.raises(SystemExit, match="re-extraction gives"):
        run_main(monkeypatch, tmp_path, GATE, CLAIMS)
    ok = {"false": 1, "scored": 2, "cp_upper_bound": sc.cp_upper(1, 2), "max_false_tolerated_at_n": -1, "passes_gate": False}
    assert run_main(monkeypatch, tmp_path, ok, {"i1": [("a", T), ("b", F)]}) == 0
    assert run_main(monkeypatch, tmp_path, ok, {"i1": [("a", T), ("b", F)]}, [row("i1", "missed_claim", "z", "oops")]) == 1  # a refusal exits non-zero
