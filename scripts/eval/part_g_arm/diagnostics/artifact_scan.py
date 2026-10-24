# THROWAWAY DIAGNOSTIC, NOT SCORER CODE. Lists extracted name-bearing claims (list members, ranks, usage percentages, ability and type lists) whose
# name is not in the item's tool results, with the source span text, so each can be read as a statement the arm made or an artifact (a header
# word, label, note or heading). Prints ids, claim kinds, names and spans only: no verdicts and no counts of false claims.
# Run (cwd scripts/eval/part_g_arm/): python diagnostics/artifact_scan.py runs/dev3b P|T|ALL
import json, re, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "part_g_v4"))
import extractors as ex
import scorer as sc
NAME_KINDS = {"type_list_member", "type_list_member_exact", "ability_list_member", "ability_list_member_exact", "common_items", "teammates"}
K = {i["id"]: i for i in json.load(open(HERE.parent / "dev_seed1/claim_battery_v4.json"))["items"]}
split = json.load(open(HERE.parent / "dev_split.json"))
half = sys.argv[2]
keep = {i for h in ("P", "T") for v in split[h].values() for i in v} if half == "ALL" else {i for v in split[half].values() for i in v}
A = {r["id"]: r for r in map(json.loads, open(Path(sys.argv[1]) / "answers.jsonl")) if r["id"] in keep}


def universe(a):
    names = set()
    for c in a["tool_calls"]:
        res = c["result"] or {}
        for k in ("types", "abilities", "species_abilities"):
            names |= {sc.norm(x) for x in res.get(k) or [] if isinstance(x, str)}
        for k in ("items", "rows"):
            names |= {sc.norm(x["name"]) for x in res.get(k) or [] if isinstance(x, dict) and "name" in x}
    return names


for i in sorted(A):
    u = universe(A[i])
    for c in ex.extract_item(K[i], A[i]):
        base = c.proposition.split("=")[0]
        if (c.kind in NAME_KINDS or c.kind.endswith("_rank")) and "|" not in base and sc.norm(base) not in u:
            txt = A[i]["final_text"][c.span[0]:c.span[1]] if c.span else ""
            print(f"{i} | {c.kind} | {base!r} | span {c.span} | {txt[:110]!r}")
