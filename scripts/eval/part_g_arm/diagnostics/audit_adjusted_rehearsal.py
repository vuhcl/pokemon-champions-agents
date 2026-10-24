# THROWAWAY DIAGNOSTIC, NOT SCORER CODE. End-to-end rehearsal of scorer.py + audit_adjusted.py on dev3b ALL with MOCK inputs: a mock exception log (one row of
# each type, one canary-matched row), a mock canary list (one made-up canary, NOT the real list), both in a throwaway git repo so the "committed and hashed"
# check is real. A second log adds a deliberately unprefixed row and must be refused. Run (cwd scripts/eval/part_g_arm/): python diagnostics/audit_adjusted_rehearsal.py
import csv, hashlib, json, subprocess, sys, tempfile
from pathlib import Path
HERE = Path(__file__).resolve().parent
V4 = HERE.parents[1] / "part_g_v4"
sys.path.insert(0, str(V4))
import audit_adjusted as aa, scorer as sc
ARM = HERE.parent
ANS, BAT, SPLIT, RP = ARM / "runs/dev3b/answers.jsonl", ARM / "dev_seed1/claim_battery_v4.json", ARM / "dev_split.json", ARM / "runs/dev3b/run_params.json"
claims = aa.scored_claims(ANS, BAT, "ALL", SPLIT)
def span_of(item, verdict):  # a gated claim of this verdict whose span text is unique within the item
    for k, (t, v, g) in enumerate(claims[item]):
        if g and v == verdict and t and sum(t == u for u, _, _ in claims[item]) == 1:
            return t
unique_true = next((i, span_of(i, sc.Verdict.TRUE)) for i in sorted(claims) if i != "damage_002" and span_of(i, sc.Verdict.TRUE))
canary_item = next(i for i in sorted(claims) if i not in ("damage_002", unique_true[0]) and claims[i])
HDR = ["item_id", "reviewed", "exception_type", "claim_text", "note"]
R = lambda i, t, c, n: dict(item_id=i, reviewed="1", exception_type=t, claim_text=c, note=n)  # noqa: E731
rows = [R("damage_002", "wrong_extraction", "has 32 HP", "NOW TRUE: mock, scorer FALSE becomes TRUE"),            # scorer FALSE now TRUE: false -1
        R(unique_true[0], "wrong_verdict", unique_true[1], "NOW FALSE: mock, scorer TRUE becomes FALSE"),        # scorer TRUE now FALSE: false +1
        R("ability_000", "missed_claim", "mock missed claim", "FALSE: mock"),                                    # false +1, n +1
        R("usage_000", "other", "mock other row", "FALSE: ignored, listed only"),                                # listed, never scored
        R(canary_item, "missed_claim", "mock canary target", "no prefix: would refuse if it were real")]         # canary-matched: excluded first
canaries = {"canaries": [{"item_id": canary_item, "canary_type": "missed_claim", "target_claim_text": "mock canary target"}]}
with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    git = lambda *a: subprocess.run(["git", "-C", str(d), "-c", "user.name=rehearsal", "-c", "user.email=r@example.invalid", *a], check=True, capture_output=True, text=True)  # noqa: E731
    git("init", "-q")
    (d / "canaries_mock.json").write_text(json.dumps(canaries))
    def attempt(name, log_rows):
        log = d / name
        with log.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=HDR); w.writeheader(); w.writerows(log_rows)
        git("add", name); git("commit", "-q", "-m", name)
        sha = hashlib.sha256(log.read_bytes()).hexdigest()
        out = subprocess.run([sys.executable, str(V4 / "scorer.py"), "--answers", str(ANS), "--battery", str(BAT), "--half", "ALL", "--split-file", str(SPLIT), "--run-params", str(RP),
                              "--exception-log", str(log), "--exception-log-sha256", sha], capture_output=True, text=True, check=True).stdout
        (d / (name + ".scorer.json")).write_text(out)
        r = subprocess.run([sys.executable, str(V4 / "audit_adjusted.py"), "--scorer-output", str(d / (name + ".scorer.json")), "--exceptions", str(log), "--exception-log-sha256", sha,
                            "--canaries", str(d / "canaries_mock.json"), "--answers", str(ANS), "--battery", str(BAT), "--half", "ALL", "--split-file", str(SPLIT)], capture_output=True, text=True)
        return r.returncode, json.loads(r.stdout) if r.stdout.strip() else r.stderr
    code, res = attempt("clean_log.csv", rows)
    print("CLEAN LOG exit", code); print(json.dumps({k: v for k, v in res.items() if k != "other_rows_listed_not_scored"}, indent=1)); print("other rows listed:", len(res["other_rows_listed_not_scored"]))
    e = res["adjusted"]
    exp_false, exp_n = 5 - 1 + 1 + 1, 1236 + 1
    assert code == 0 and (e["false"], e["scored"]) == (exp_false, exp_n) and e["cp_upper_bound"] == sc.cp_upper(exp_false, exp_n) and res["canary_rows_excluded"] == 1, "unexpected clean numbers"
    assert (res["scorer_true_now_false"], res["scorer_false_now_true"], res["missed_noted_false"]) == (1, 1, 1)
    print(f"expected for the clean log: false 5 -1 +1 +1 = {exp_false}, n 1236 +1 = {exp_n}: matches")
    code2, res2 = attempt("unprefixed_log.csv", rows + [R("typing_000", "missed_claim", "mock unprefixed", "looks false to me")])
    print("UNPREFIXED LOG exit", code2); print(json.dumps(res2, indent=1))
    assert code2 == 1 and "adjusted" not in res2 and [x["row"]["claim_text"] for x in res2["refused"]] == ["mock unprefixed"], "unprefixed row was not refused"
    print("expected refusal for the unprefixed row: refused, no verdict, the row listed: matches")
