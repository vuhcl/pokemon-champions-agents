# THROWAWAY DEVELOPMENT AID, NOT SCORER CODE. Runs the part_g_v4 extractors on dev half P only (never T) and prints, per item, the extracted
# claims for hand inspection. It prints no aggregate false rate. Run (cwd scripts/eval/part_g_arm/): python diagnostics/extract_check_P.py runs/dev3b [ids...]
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "part_g_v4"))
import extractors as ex
K = {i["id"]: i for i in json.load(open(HERE.parent / "dev_seed1/claim_battery_v4.json"))["items"]}
split = json.load(open(HERE.parent / "dev_split.json"))
P = {i for v in split["P"].values() for i in v}
A = {r["id"]: r for r in map(json.loads, open(Path(sys.argv[1]) / "answers.jsonl"))}
ids = [i for i in (sys.argv[2:] or sorted(P)) if i in P]  # T ids are refused
for i in ids:
    cs = ex.extract_item(K[i], A[i])
    print(f"\n## {i} | {A[i]['final_text'][:200]!r}")
    for c in cs:
        print(f"   {c.kind:22s} {c.proposition[:46]:46s} {str(c.verdict.value if c.verdict else None):13s} line={c.line} copied={c.copied_unchanged} {c.reason[:50]}")
