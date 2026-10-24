# MOCK AUDITS ONLY: never point this at a real audit or a real canary list (it reads the canary list to choose its actions).
# Builds a synthetic audit with canaries through the real audit_view.py, performs scripted reviewer actions in the real page (headless Chrome), exports the CSV
# from the page, commits it as an exception log in a temporary git repo, runs audit_canary_check.py, and asserts the detections it should see.
# Run (cwd repo root): uv run python scripts/eval/part_g_arm/diagnostics/canary_dry_run.py [WORKDIR]
import hashlib, json, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
V4 = ROOT / "scripts/eval/part_g_v4"
W = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="canary-dry-run-"))
W.mkdir(parents=True, exist_ok=True)
items, ans = [], []
for k in range(20):
    items.append({"id": f"typing_{k:03d}", "claim_type": "typing", "prompt": f"Does Mon{k} have Fire typing?", "n_claims": 1,
                  "claims": [{"kind": "has_type", "ground_truth": {"species": f"Mon{k}", "asked_type": "Fire", "has_type": True, "types": ["Fire", "Flying"]}}]})
    ans.append({"id": f"typing_{k:03d}", "final_text": f"Yes, Mon{k} has Fire typing. It is a Fire/Flying type Pokémon.", "tool_calls": []})
for k in range(20):
    s1, s2 = f"Alpha{k}", f"Beta{k}"
    items.append({"id": f"speed_{k:03d}", "claim_type": "speed", "prompt": f"Does {s1} (Jolly, 32 Spe SP) outspeed {s2} (Timid, 32 Spe SP)?", "n_claims": 1,
                  "claims": [{"kind": "outspeed", "ground_truth": {"s1": s1, "s2": s2, "spe1_jolly32": 170 + k, "spe2_timid32": 120 + k, "s1_outspeeds": True}}]})
    ans.append({"id": f"speed_{k:03d}", "final_text": f"Yes, {s1} (Jolly, 32 Spe SP) outspeeds {s2} (Timid, 32 Spe SP).\n- {s1} has a final Speed stat of {170 + k}.\n- {s2} has a final Speed stat of {120 + k}.", "tool_calls": []})
(W / "battery.json").write_text(json.dumps({"items": items}))
(W / "answers.jsonl").write_text("".join(json.dumps(a) + "\n" for a in ans))
(W / "ids.json").write_text(json.dumps({"ids": [i["id"] for i in items]}))
subprocess.run([sys.executable, str(V4 / "audit_view.py"), "--answers", str(W / "answers.jsonl"), "--battery", str(W / "battery.json"), "--out", str(W / "audit"), "--ids-file", str(W / "ids.json"),
                "--canaries", "--canary-seed", "7", "--canary-out", str(W / "canaries.json")], check=True, capture_output=True)
canaries = json.loads((W / "canaries.json").read_text())["canaries"]
by = lambda t, prefix: [c for c in canaries if c["canary_type"] == t and c["item_id"].startswith(prefix)]  # noqa: E731
A, B, C = by("wrong_verdict", "speed")[0], by("missed_claim", "typing")[0], by("wrong_extraction", "typing")[0]
F, G = by("missed_claim", "typing")[1], by("wrong_verdict", "speed")[1]
cset = {c["item_id"] for c in canaries}
real = next(f"typing_{k:03d}" for k in range(20) if f"typing_{k:03d}" not in cset)
clean = next(f"speed_{k:03d}" for k in range(20) if f"speed_{k:03d}" not in cset)
actions = [
    {"name": "A use-pick on a wrong_verdict canary claim", "item": A["item_id"], "mode": "click_mark_usepick", "text": A["target_claim_text"], "type": "wrong_verdict"},
    {"name": "B select-and-pick a missed_claim canary (its highlight is gone)", "item": B["item_id"], "mode": "select", "text": B["target_claim_text"], "type": "missed_claim"},
    {"name": "C use-pick on a wrong_extraction canary, wrong type chosen", "item": C["item_id"], "mode": "click_mark_usepick", "text": C["target_claim_text"], "type": "other"},
    {"name": "D real exception on a non-canary item", "item": real, "mode": "typed", "claim": "something the arm really got wrong", "type": "other"},
    {"name": "E reviewed clean answer", "item": clean, "mode": "review"},
    {"name": "F unrelated text on a canary item", "item": F["item_id"], "mode": "typed", "claim": "unrelated words", "type": "other"},
    {"name": "G claim_text '1' on a canary whose target is longer", "item": G["item_id"], "mode": "typed", "claim": "1", "type": "wrong_verdict"},
]
(W / "actions.json").write_text(json.dumps(actions))
out = subprocess.run(["node", str(Path(__file__).with_name("canary_dry_run_driver.mjs")), str(W / "audit/audit.html"), str(W / "actions.json"), str(W / "exceptions.csv")], capture_output=True, text=True, check=True)
print(out.stdout.strip())
repo = W / "logrepo"
repo.mkdir(exist_ok=True)
(repo / "exceptions.csv").write_text((W / "exceptions.csv").read_text())
for cmd in (["init", "-q"], ["add", "exceptions.csv"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "log"]):
    subprocess.run(["git", "-C", str(repo), *cmd], check=True, capture_output=True)
sha = hashlib.sha256((repo / "exceptions.csv").read_bytes()).hexdigest()
res = json.loads(subprocess.run([sys.executable, str(V4 / "audit_canary_check.py"), "--canaries", str(W / "canaries.json"), "--exceptions", str(repo / "exceptions.csv"),
                                 "--exception-log-sha256", sha, "--repo", str(repo)], capture_output=True, text=True, check=True).stdout)
print(json.dumps({k: res[k] for k in ("canaries", "detected", "type_matched", "by_type", "real_exceptions_after_removal", "real_exceptions_by_type", "real_exception_rows_on_canary_items")}, indent=1))
expect = {"detected": 3, "type_matched": 2, "real_exceptions_after_removal": 3}
assert {k: res[k] for k in expect} == expect, (expect, res)
assert {r["claim_text"] for r in res["real_exception_rows_on_canary_items"]} == {"unrelated words", "1"}
print("DRY RUN MATCHES: A, B detected and type-matched; C detected (wrong type); D, F, G stay real (F and G are listed as rows on canary items); E ignored")
