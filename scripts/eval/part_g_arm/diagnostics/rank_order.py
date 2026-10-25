# THROWAWAY DIAGNOSTIC, NOT SCORER CODE. Counts numbered usage lists in a run whose order differs from the order of the same item's tool result.
# Run (cwd scripts/eval/part_g_arm/): python diagnostics/rank_order.py runs/dev3b
import json, re, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "part_g_v4"))
import extractors as ex
import scorer as sc
K = {i["id"]: i for i in json.load(open(HERE.parent / "dev_seed1/claim_battery_v4.json"))["items"]}
split = json.load(open(HERE.parent / "dev_split.json"))
half = {i: h for h in ("P", "T") for v in split[h].values() for i in v}
A = {r["id"]: r for r in map(json.loads, open(Path(sys.argv[1]) / "answers.jsonl"))}


def tool_orders(a):
    out = {"items": [], "teammates": []}
    for c in a["tool_calls"]:
        res = c["result"] or {}
        if c["name"] == "get_usage_items":
            out["items"] = [x["name"] for x in res.get("items", [])]
        if c["name"] == "get_usage_teammates":
            out["teammates"] = [x["name"] for x in (res.get("rows") or [])]
    return out


tot = {"P": [0, 0], "T": [0, 0]}
differ = []
for i, a in sorted(A.items()):
    ty = K[i]["claim_type"]
    if ty not in ("usage", "usage_showdown"):
        continue
    tools = tool_orders(a)
    secs = ex._sections(a["final_text"])
    lists = {"items": secs["items"] or (secs["all"] if not secs["teammates"] else []), "teammates": secs["teammates"]} if ty == "usage" else {"teammates": ex._lines_pos(a["final_text"])}
    for kind, lines in lists.items():
        numbered = [(l, o) for l, o in lines if re.match(r"\s*\d+\.", l)]
        if not numbered:
            continue
        names = [n for n, *_ in ex._entry_names(numbered)]
        ref = tools[kind]
        have = [n for n in names if sc.norm(n) in {sc.norm(r) for r in ref}]
        want = [r for r in ref if sc.norm(r) in {sc.norm(n) for n in have}]
        tot[half[i]][0] += 1
        if [sc.norm(n) for n in have] != [sc.norm(n) for n in want]:
            tot[half[i]][1] += 1
            differ.append((i, kind, have, want))
print(f"{sys.argv[1]}: numbered usage lists P {tot['P'][0]} (order differs {tot['P'][1]}), T {tot['T'][0]} (order differs {tot['T'][1]}), all {tot['P'][0]+tot['T'][0]} (order differs {tot['P'][1]+tot['T'][1]})")
for d in differ:
    print("  ", d)
