"""Audit canaries: selection, display-only application, no marks, the list never printed, and the detection script on a synthetic audit CSV."""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

V4 = Path(__file__).resolve().parents[2] / "scripts/eval/part_g_v4"
sys.path.insert(0, str(V4))
import audit_canaries as ac  # noqa: E402
import audit_canary_check as chk  # noqa: E402
import scorer as sc  # noqa: E402

T, F = sc.Verdict.TRUE, sc.Verdict.FALSE


def make_world(n_items=30):
    """Synthetic items: each answer has a list of three names, a number, and a verdict claim, all with spans into the text."""
    by_item, answers = {}, {}
    for k in range(n_items):
        iid = f"usage_{k:03d}"
        text = f"Yes. Top items: Alpha{k}, Beta{k}, Gamma{k}. Speed is {100 + k}. Done."
        a, b, g = text.index(f"Alpha{k}"), text.index(f"Beta{k}"), text.index(f"Gamma{k}")
        n = text.index(str(100 + k))
        by_item[iid] = [
            sc.Claim("common_items", "S", f"Alpha{k}", T, ctype="usage", span=(a, a + len(f"Alpha{k}"))),
            sc.Claim("common_items", "S", f"Beta{k}", F if k % 3 == 0 else T, ctype="usage", span=(b, b + len(f"Beta{k}"))),
            sc.Claim("common_items", "S", f"Gamma{k}", T, ctype="usage", span=(g, g + len(f"Gamma{k}"))),
            sc.Claim("speed_stat", "S", f"Foo speed={100 + k}", T, ctype="speed", span=(n, n + 3)),
            sc.Claim("has_type", "True", "True", T, ctype="typing", span=(0, 4)),
        ]
        answers[iid] = {"final_text": text}
    return by_item, answers


def test_twenty_canaries_in_the_fixed_split_one_per_item_among_scored_claims_and_reproducible():
    by_item, answers = make_world()
    cs = ac.choose_canaries(by_item, answers, 11)
    assert len(cs) == 20 and [sum(1 for c in cs if c["canary_type"] == t) for t, _ in ac.COUNTS] == [7, 7, 6]
    assert len({c["item_id"] for c in cs}) == 20  # at most one per item
    assert cs == ac.choose_canaries(by_item, answers, 11) and cs != ac.choose_canaries(by_item, answers, 12)
    for c in cs:
        claim = by_item[c["item_id"]][c["claim_index"]]
        assert claim.verdict in (T, F) and claim.line == "gate" and c["target_claim_text"] == answers[c["item_id"]]["final_text"][claim.span[0]:claim.span[1]]
        assert c["change"] and c["canary_type"] in ("wrong_verdict", "wrong_extraction", "missed_claim")
    assert any("swapped" in c["change"] for c in cs if c["canary_type"] == "wrong_extraction") or any("->" in c["change"] for c in cs if c["canary_type"] == "wrong_extraction")
    with pytest.raises(SystemExit):
        ac.choose_canaries(dict(list(by_item.items())[:10]), answers, 11)  # 10 items cannot carry 20 canaries


def test_apply_changes_only_the_display_and_never_the_scorer_view():
    by_item, answers = make_world()
    before = copy.deepcopy(by_item)
    summary_before = sc.dev_headline(by_item, 100)
    cs = ac.choose_canaries(by_item, answers, 11)
    shown = ac.apply_canaries(by_item, cs)
    assert by_item == before and sc.dev_headline(by_item, 100) == summary_before  # scorer output is identical with and without canary rendering
    assert sc.gate_summary([c for v in by_item.values() for c in v], 100) == sc.gate_summary([c for v in before.values() for c in v], 100)
    for c in cs:
        orig, now = by_item[c["item_id"]], shown[c["item_id"]]
        if c["canary_type"] == "missed_claim":
            assert len(now) == len(orig) - 1 and orig[c["claim_index"]] not in now
        elif c["canary_type"] == "wrong_verdict":
            a, b = orig[c["claim_index"]], now[c["claim_index"]]
            assert a.verdict != b.verdict and (a.kind, a.proposition, a.span) == (b.kind, b.proposition, b.span)
        else:
            assert now[c["claim_index"]].proposition != orig[c["claim_index"]].proposition and len(now) == len(orig)
            assert now[c["claim_index"]].verdict == orig[c["claim_index"]].verdict  # only the displayed value changed
    assert sum(1 for i in by_item if shown[i] != by_item[i]) == 20  # untouched items are untouched


def _build_cli(tmp_path, canaries: bool):
    items = [{"id": f"typing_{k:03d}", "claim_type": "typing", "prompt": "q", "n_claims": 1,
              "claims": [{"kind": "has_type", "ground_truth": {"species": "A", "asked_type": "Fairy", "has_type": True, "types": ["Fire", "Flying"]}}]} for k in range(30)]
    bat, ans, ids = tmp_path / "b.json", tmp_path / "a.jsonl", tmp_path / "ids.json"
    bat.write_text(json.dumps({"items": items}))
    ans.write_text("".join(json.dumps({"id": i["id"], "final_text": "Yes, A has Fairy typing. It is a Fire/Flying type.", "tool_calls": []}) + "\n" for i in items))
    ids.write_text(json.dumps({"ids": [i["id"] for i in items]}))
    out = tmp_path / ("with" if canaries else "without")
    cmd = [sys.executable, str(V4 / "audit_view.py"), "--answers", str(ans), "--battery", str(bat), "--out", str(out), "--ids-file", str(ids)]
    if canaries:
        cmd += ["--canaries", "--canary-seed", "5", "--canary-out", str(tmp_path / "canaries.json")]
    return subprocess.run(cmd, capture_output=True, text=True), out


def test_cli_prints_only_the_hash_and_n_and_leaves_no_mark_on_the_page_or_the_csv(tmp_path):
    cp, out = _build_cli(tmp_path, True)
    assert cp.returncode == 0, cp.stderr
    lst = (tmp_path / "canaries.json").read_text()
    assert f"canaries: N=20 sha256={hashlib.sha256(lst.encode()).hexdigest()}" in cp.stdout
    for rec in json.loads(lst)["canaries"]:  # nothing from the list reaches the output
        assert rec["target_claim_text"] not in cp.stdout and rec["change"] not in cp.stdout and rec["canary_type"] not in cp.stdout
    cp0, out0 = _build_cli(tmp_path, False)
    page, page0 = (out / "audit.html").read_text(), (out0 / "audit.html").read_text()
    assert "canary" not in page.lower() and page.count("<section") == page0.count("<section") == 30  # no marker, same layout
    assert page != page0  # the display does differ
    assert (out / "audit.csv").read_text() == (out0 / "audit.csv").read_text()  # the exported rows carry no canary mark
    js = lambda p: p.split("<script>")[1]  # noqa: E731
    assert js(page).split("const TYPES")[1] == js(page0).split("const TYPES")[1]  # same page script and export logic
    assert "canary" not in page0.lower() and "--canaries" not in (out / "audit.html").read_text()


def test_canary_options_are_required_together():
    cp = subprocess.run([sys.executable, str(V4 / "audit_view.py"), "--answers", "x", "--battery", "y", "--out", "z", "--size", "1", "--canaries"], capture_output=True, text=True)
    assert cp.returncode != 0 and "--canary-seed and --canary-out" in cp.stderr


def test_cp_lower_bound():
    assert chk.cp_lower(0, 20) == 0.0
    assert chk.cp_lower(20, 20) == pytest.approx(0.05 ** (1 / 20), abs=1e-9)
    from math import comb

    p = chk.cp_lower(17, 20)  # defining property, computed independently: P(X >= 17 | p) = 0.05 at the lower bound
    assert sum(comb(20, i) * p ** i * (1 - p) ** (20 - i) for i in range(17, 21)) == pytest.approx(0.05, abs=1e-9)
    assert chk.cp_lower(10, 20) < chk.cp_lower(15, 20) < chk.cp_lower(20, 20)


def _git(repo, *a):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True)


def test_detection_script_on_a_synthetic_audit_csv(tmp_path):
    canaries = [
        {"item_id": "i1", "canary_type": "wrong_verdict", "target_claim_text": "Rillaboom 32.411%", "displayed_claim": "teammates | Rillaboom=32.411", "claim_index": 0},
        {"item_id": "i2", "canary_type": "wrong_extraction", "target_claim_text": "speed stat of 177", "displayed_claim": "speed_stat | Foo speed=177", "altered_claim": "speed_stat | Foo speed=178", "claim_index": 1},
        {"item_id": "i3", "canary_type": "missed_claim", "target_claim_text": "It is a Fire/Flying type", "displayed_claim": "type_list_member | Fire", "claim_index": 2},
        {"item_id": "i4", "canary_type": "missed_claim", "target_claim_text": "Chople Berry (4.0%)", "displayed_claim": "common_items | Chople Berry", "claim_index": 0},
    ]
    rows = [
        ["i1", "y", "wrong_verdict", "Rillaboom 32.411%", "found it"],  # detected and type-matched
        ["i2", "y", "wrong_verdict", "177", "right place, wrong type"],  # detected, not type-matched
        ["i3", "y", "missed_claim", "unrelated words", ""],  # same item, no overlap: a real exception
        ["i5", "y", "other", "something real", ""],  # real exception on a non-canary item
        ["i6", "y", "", "", ""],  # a reviewed clean answer: not an exception
        ["i4", "y", "missed_claim", "chople berry", ""],  # matched
        ["i4", "y", "missed_claim", "Chople Berry 4.0", "second row on the same canary item: real"],
    ]
    log = tmp_path / "log.csv"
    with log.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["item_id", "reviewed", "exception_type", "claim_text", "note"])
        w.writerows(rows)
    res = chk.check(canaries, list(csv.DictReader(log.open(newline=""))))
    assert (res["canaries"], res["detected"], res["type_matched"]) == (4, 3, 2) and res["canary_rows_removed"] == 3
    assert res["real_exceptions_after_removal"] == 3 and res["real_exceptions_by_type"] == {"missed_claim": 2, "other": 1}  # i3's row, i4's second row, i5
    assert res["by_type"]["missed_claim"] == {"canaries": 2, "detected": 1, "type_matched": 1}
    assert res["detected_lower_bound_95"] == chk.cp_lower(3, 4) and res["type_matched_lower_bound_95"] == chk.cp_lower(2, 4)
    # the script refuses until the log is committed and hashed, and never prints the list
    cfile = tmp_path / "canaries.json"
    cfile.write_text(json.dumps({"canaries": canaries}))
    sha = hashlib.sha256(log.read_bytes()).hexdigest()
    run = lambda: subprocess.run([sys.executable, str(V4 / "audit_canary_check.py"), "--canaries", str(cfile), "--exceptions", str(log), "--exception-log-sha256", sha, "--repo", str(tmp_path)],  # noqa: E731
                                 capture_output=True, text=True)
    early = run()
    assert early.returncode != 0 and "not committed and hashed" in early.stderr
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "log.csv")
    _git(tmp_path, "commit", "-qm", "log")
    late = run()
    assert late.returncode == 0 and json.loads(late.stdout)["detected"] == 3
    assert "Rillaboom" not in late.stdout and "target_claim_text" not in late.stdout
