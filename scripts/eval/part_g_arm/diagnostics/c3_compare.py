# THROWAWAY HEURISTIC, NOT SCORER CODE. V1/V2 comparison inputs for the pre-set decision rule: per variant, the damage items whose
# answers contain a heuristic numeric mismatch (numeric_audit), the yes/no errors against the keys, and the mismatching sentences
# so each can be adjudicated by hand. The rule itself (V2 only if >= 3 fewer damage items with a false numeric statement and no new
# yes/no errors) is applied in the report on the hand-adjudicated lists; the heuristic lists are applied the same way for comparison.
# Run (cwd scripts/eval/part_g_arm/): python diagnostics/c3_compare.py runs/dev3a runs/dev3b
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from numeric_audit import audit, K
out = {}
for name, run in zip(('V1', 'V2'), sys.argv[1:3]):
    A = {r['id']: r for r in map(json.loads, open(Path(run) / 'answers.jsonl'))}
    mism, unch = audit(run)
    items = sorted({m[0] for m in mism if m[0].startswith('damage_')})
    yn_err = []
    for i, r in A.items():
        if K[i]['claim_type'] != 'damage': continue
        m = re.search(r'\b(yes|no)\b', r['final_text'][:60].lower()) or re.search(r'\b(yes|no)\b', r['final_text'].lower())
        if not m or (m.group(1) == 'yes') != K[i]['claims'][0]['ground_truth']['guaranteed_ko']: yn_err.append(i)
    out[name] = {'items': items, 'yn': sorted(yn_err), 'mism': [m for m in mism if m[0].startswith('damage_')]}
    print(f'== {name} ({run}): damage items with a heuristic numeric mismatch: {len(items)} {items}\n   yes/no errors vs keys: {sorted(yn_err)}')
    for m in out[name]['mism']: print('   ', m[0], '|', m[1], '|', m[2][:150])
    print('   unchecked damage sentences:', len([u for u in unch if u[0].startswith('damage_')]))
v1, v2 = out['V1'], out['V2']
print(f"\nheuristic rule: V1 {len(v1['items'])} items, V2 {len(v2['items'])} items, difference {len(v1['items']) - len(v2['items'])}; new V2 yes/no errors: {sorted(set(v2['yn']) - set(v1['yn']))}")
print('V1 only:', sorted(set(v1['items']) - set(v2['items'])), '| V2 only:', sorted(set(v2['items']) - set(v1['items'])))
