# THROWAWAY DIAGNOSTIC, NOT SCORER CODE. Counts only (no true/false split, no rate): scored claims in the gate unit per claim type, the
# copied_unchanged share, the list-member share, claims per item, zero-claim items. Reads one dev half (P or T) of a run through the extractors.
# Run (cwd scripts/eval/part_g_arm/): python diagnostics/claim_counts.py runs/dev3b P|T|ALL
import collections, json, statistics, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "part_g_v4"))
import extractors as ex
from scorer import Verdict

LIST_MEMBER = {"common_items", "teammates", "ability_list_member", "type_list_member"}
GATE_LINES = {"gate", "ko_chance"}
K = {i["id"]: i for i in json.load(open(HERE.parent / "dev_seed1/claim_battery_v4.json"))["items"]}
split = json.load(open(HERE.parent / "dev_split.json"))
half = sys.argv[2]
keep = {i for h in ("P", "T") for v in split[h].values() for i in v} if half == "ALL" else {i for v in split[half].values() for i in v}
A = {r["id"]: r for r in map(json.loads, open(Path(sys.argv[1]) / "answers.jsonl")) if r["id"] in keep}
per_type, cu_type, lm_type = collections.Counter(), collections.Counter(), collections.Counter()
per_item, zero_claim, zero_scored, kinds = {}, [], [], collections.Counter()
for i in sorted(A):
    cs = ex.extract_item(K[i], A[i])
    if not cs:
        zero_claim.append(i)
    sc_ = [c for c in cs if c.line in GATE_LINES and c.verdict in (Verdict.TRUE, Verdict.FALSE)]
    if not sc_:
        zero_scored.append(i)
    per_item[i] = len(sc_)
    for c in sc_:
        per_type[K[i]["claim_type"]] += 1
        kinds[c.kind] += 1
        cu_type[K[i]["claim_type"]] += c.copied_unchanged
        lm_type[K[i]["claim_type"]] += c.kind in LIST_MEMBER
n, cu, lm = sum(per_type.values()), sum(cu_type.values()), sum(lm_type.values())
print(f"{sys.argv[1]} half {half}: items {len(A)}, scored claims (gate unit) {n}, items with a scored claim {len(A) - len(zero_scored)}, items with zero claims {zero_claim}, items with zero scored claims {zero_scored}")
print(f"copied_unchanged share {cu}/{n} = {cu / n:.3f}; list-member share {lm}/{n} = {lm / n:.3f}")
v = sorted(per_item.values())
print(f"scored claims per item: min {v[0]}, median {statistics.median(v)}, max {v[-1]}")
for t in sorted(per_type):
    ids = [i for i in A if K[i]["claim_type"] == t]; w = sorted(per_item[i] for i in ids)
    print(f"  {t:15s} items {len(ids):3d} scored {per_type[t]:4d} copied {cu_type[t]:4d} ({cu_type[t] / per_type[t]:.2f}) list-member {lm_type[t]:4d} ({lm_type[t] / per_type[t]:.2f}) per item min/med/max {w[0]}/{statistics.median(w)}/{w[-1]}")
print("scored claims by kind:", dict(kinds.most_common()))
