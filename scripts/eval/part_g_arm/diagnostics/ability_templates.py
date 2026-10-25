# THROWAWAY HEURISTIC, NOT SCORER CODE. Per-template breakdown of the ability items: tools called, and answer vs key.
# Yes/no parsing is approximate. Run (cwd scripts/eval/part_g_arm/runs/): python ../diagnostics/ability_templates.py devN
import collections, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from replay_eval import K, yn
run = sys.argv[1]
A = {r['id']: r for r in map(json.loads, open(f'{run}/answers.jsonl'))}
by = collections.defaultdict(list)
for i, it in K.items():
    if it['claim_type'] == 'ability': by[it['template']].append(i)
for tmpl, ids in by.items():
    tools = collections.Counter(); right_tool = 0; wrong = []; nonans = []
    for i in ids:
        r = A[i]; real = {c['name'] for c in r['tool_calls'] if c['name'] != 'no_lookup_needed'}
        for t in sorted(real): tools[t] += 1
        right_tool += bool(real & {'check_species_ability', 'get_abilities'})
        v = yn(r['final_text']); key = K[i]['claims'][0]['ground_truth']['has_ability']
        if v is None: nonans.append(i)
        elif v != key: wrong.append((i, sorted(real), r['final_text'][:70].replace('\n', ' '), 'key', key))
    print(f'## {tmpl!r}: {len(ids)} items | items touching check_species_ability or get_abilities: {right_tool} | tools (items using each): {dict(tools)}')
    print(f'   answer != key: {len(wrong)}; no yes/no: {nonans}')
    for w in wrong: print('   ', w)
