# THROWAWAY HEURISTIC, NOT SCORER CODE. Registration prep: numeric sentences in a run's answers, classified by whether a scorer rule
# covers them and whether the key or the item's own tool results hold the data. Classes: RULE (a scorer rule exists), DATA (the numbers are in
# the transcript or key, but no rule), DERIVABLE (a number is absent but computable from transcript numbers: percent of HP, half of HP...),
# NONE (a number is in neither the key nor the transcript and is not derivable). Run: python c4_unscorable.py runs/devN [runs/devM ...]
import collections, itertools, json, math, re, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
K = {i['id']: i for i in json.load(open(HERE.parent / 'dev_seed1/claim_battery_v4.json'))['items']}
NUM = re.compile(r'(?<![\w.])\d+(?:\.\d+)?')
def sents(t): return [s for s in re.split(r'(?<=[.!?])\s+(?=[A-Z"*\[(])|\n+', t) if s.strip()]
def nums(x): return {float(n) for n in NUM.findall(x if isinstance(x, str) else json.dumps(x))}
RULE = [('ko count / roll count', r'\b(?:out of|of)\s*(?:the\s*)?(?:\w+\s+)?(?:possible\s*)?16\b|rolls_that_ko|\bonly (?:one|\d+) rolls?\b'),
        ('KO chance percent', r'%\s*chance|chance to ohko'),
        ('KO threshold', r'or (?:higher|more|above|greater)|at least \d|\d+\+|threshold'),
        ('HP arithmetic / comparison', r'\b(?:less|lower|greater|higher|more|above|below|exceed\w*)\b[^.]{0,30}\d|\d\s*[<>]|\bHP remaining|\bHP left'),
        ('usage percentage', r'\d+(?:\.\d+)?\s*%')]
def derivable(n, base):
    b = sorted(base)[:40]
    for x, y in itertools.product(b, b):
        for v in ((x / y * 100) if y else None, abs(x - y), x / 2, y / 2, math.ceil(x / 2), x + 1, x * y if x * y < 1e6 else None, x + y):
            if v is not None and abs(v - n) < 0.06: return True
    return False
groups = collections.defaultdict(list)
total = collections.Counter()
for run in sys.argv[1:]:
    for r in map(json.loads, open(Path(run) / 'answers.jsonl')):
        it = K[r['id']]; ty = it['claim_type']; gt = it['claims'][0]['ground_truth']
        prompt_n = nums(it['prompt']); tool_n = set().union(*[nums(c['result']) for c in r['tool_calls']]) if r['tool_calls'] else set()
        key_n = nums({k: v for k, v in gt.items() if k not in ('calc_desc', 'scoring')})
        have = prompt_n | tool_n | key_n
        for s in sents(r['final_text']):
            body = re.sub(r'^\s*(?:\d+\.|[-*•])\s*', '', s)
            ns = nums(body) - prompt_n
            if not ns: continue
            rule = next((nm for nm, pat in RULE if re.search(pat, body, re.I)), None)
            if rule and not (rule == 'usage percentage' and ty not in ('usage', 'usage_showdown')) \
                    and not (rule == 'HP arithmetic / comparison' and ty != 'damage'):
                cls = 'RULE'; pat = rule
            else:
                missing = {n for n in ns if n not in have and not (n.is_integer() and n <= 1)}
                if not missing: cls, pat = 'DATA', 'numbers present in transcript or key'
                elif all(derivable(n, tool_n | key_n | prompt_n) for n in missing): cls, pat = 'DERIVABLE', 'computable from transcript numbers'
                else: cls, pat = 'NONE', 'not in key or transcript'
            total[(run, cls)] += 1
            groups[(cls, pat)].append((run.split('/')[-1], r['id'], ty, body[:170]))
for k, v in sorted(total.items()): print(k, v)
for (cls, pat), rows in sorted(groups.items()):
    print(f'\n### {cls}: {pat} ({len(rows)} sentences, {len({(a, b) for a, b, *_ in rows})} answers)')
    if cls in ('NONE', 'DERIVABLE', 'DATA'):
        for rw in rows[:60 if cls == 'NONE' else 6]: print('  ', rw)
