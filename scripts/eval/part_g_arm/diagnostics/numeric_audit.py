# THROWAWAY HEURISTIC, NOT SCORER CODE. Sentence-level numeric audit of damage and usage answers against the same item's
# tool result. Rule-based and approximate: it reports MISMATCH (a stated number or comparison contradicts the tool result)
# and UNCHECKED (a sentence with numbers no rule covers) so both can be read by hand.
# Run: python numeric_audit.py runs/devN   (cwd scripts/eval/part_g_arm/); importable: audit(run_dir) -> (mismatches, unchecked)
import json, re, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
K = {i['id']: i for i in json.load(open(HERE.parent / 'dev_seed1/claim_battery_v4.json'))['items']}
W = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'zero': 0, 'none': 0, 'no': 0, 'all': 16}
NUM = r'(\d+(?:\.\d+)?)'
KO = re.compile(r'\bKO\b|knock', re.I)


def sents(t):
    return [s for s in re.split(r'(?<=[.!?])\s+(?=[A-Z"*\[(])|\n+', t) if s.strip()]


def cmp_ok(a, op, b):
    return {'<': a < b, '>': a > b}[op]


def check_damage(iid, r, res):
    hp, lo, hi, k, rolls = res['defender_hp'], res['damage_range'][0], res['damage_range'][1], res['rolls_that_ko'], res.get('damage_rolls')
    out, unchecked = [], []
    for s in sents(r['final_text']):
        low = s.lower(); hit = False
        def bad(msg): out.append((iid, msg, s[:170]))
        # roll counts
        for m in re.finditer(rf'(?<!every )(?<!each )(?<!single )(\d+|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|none|all)\b)\s*(?:out of|of)\s*(?:the\s*)?(?:\w+\s+)?(?:possible\s*)?(?:16)\b', low):
            n = int(m.group(1)) if m.group(1).isdigit() else W[m.group(1)]; hit = True
            if KO.search(s) and n != k and 'not' not in low[:m.start()][-20:] and not re.search(r'(?:do|would|will)\s*not|wouldn.t|not\b', low[m.end():m.end() + 40]):
                bad(f'roll count {n} vs rolls_that_ko {k}')
        if re.search(r'\bonly (?:one|1) roll|\bonly the (?:max|maximum|highest|top)|\bone roll\b', low) and KO.search(s):
            hit = True
            if k != 1: bad(f'"one roll KOs" vs rolls_that_ko {k}')
        if re.search(r'\bnone of the (?:16 )?(?:damage )?rolls|\bno (?:damage )?rolls?\b', low) and KO.search(s):
            hit = True
            if k != 0: bad(f'"no roll KOs" vs rolls_that_ko {k}')
        # KO thresholds: "rolls at or above X" uses the roll-list rule; "need/require/at least X damage", "X+" and "half of N HP" must equal the HP
        gtk = K[iid]['claims'][0]['ground_truth']
        for m in re.finditer(rf'{NUM}\s*(?:or|and)\s*(?:higher|more|above|greater|up)|at least {NUM}|(?:need|needs|require|requires|threshold of|would need)[^.\d]{{0,30}}{NUM}|{NUM}\+', low):
            x = float([g for g in m.groups() if g][0]); hit = True
            if not KO.search(s) or re.match(r'\s*-?\s*(?:hit|hko)', low[m.end():]): continue
            if re.search(r'or\s*(?:higher|more|above|greater|up)', m.group(0)):
                same = {r for r in gtk['rolls'] if r >= x} == {r for r in gtk['rolls'] if r >= hp}
                if not same: bad(f'rolls at or above {x:g} are not the KO rolls (hp {hp})')
            elif x != hp:
                bad(f'KO needs {x:g} vs defender_hp {hp}')
        for m in re.finditer(rf'half of {NUM}\s*(?:HP)?', low):
            hit = True
            if KO.search(s): bad(f'half of {m.group(1)} used as a KO threshold (KO needs the full HP {hp})')
        # "N out of 10 rolls" and a chance to nHKO read as a single-hit KO share
        for m in re.finditer(r'(\d+|\b(?:one|two|three|four|five|six|seven|eight|nine)\b)\s*out of\s*(?:the\s*)?(\d+)\s*(?:damage\s*)?rolls', low):
            n = int(m.group(1)) if m.group(1).isdigit() else W[m.group(1)]; den = int(m.group(2)); hit = True
            if den != 16 and abs(100 * n / den - 100 * k / 16) > 3.125: bad(f'"{n} out of {den} rolls" vs rolls_that_ko {k} of 16')
        if re.search(rf'{NUM}\s*%\s*chance to \d+\s*hko', low) and re.search(r'(?:meaning|means|which means|so)\b[^.]{0,80}(?:single|one hit|in one|rolls?|of the time)', low):
            hit = True
            if k == 0 or not re.search(r'hko', low[low.find('meaning'):] if 'meaning' in low else ''): bad(f'chance to nHKO read as a single-hit KO share (rolls_that_ko {k})')
        if re.search(r'\bonly some\b[^.]{0,40}rolls[^.]{0,40}(?:would|could|will)?\s*(?:KO|knock)', low, re.I) and k == 0:
            hit = True; bad('"only some rolls KO" but rolls_that_ko is 0')
        for m in re.finditer(rf'out of {NUM}\s*total HP', low):
            hit = True
            if int(float(m.group(1))) != hp: bad(f'"total HP {m.group(1)}" vs defender_hp {hp}')
        # comparisons
        for m in re.finditer(rf'{NUM}\)?\s*(?:damage\s*)?(?:is|are)?\s*(less|lower|smaller|below|greater|higher|more|above|exceeds?)(?: than)?\s*(?:the\s*)?(?:defender.s\s*|its\s*)?(?:full\s*|max\w*\s*)?(?:HP\s*)?\(?{NUM}', s, re.I):
            a, op, b = float(m.group(1)), m.group(2).lower(), float(m.group(3)); hit = True
            sym = '<' if op in ('less', 'lower', 'smaller', 'below') else '>'
            if not cmp_ok(a, sym, b): bad(f'false comparison {a:g} {op} {b:g}')
        for m in re.finditer(rf'{NUM}\s*([<>])\s*{NUM}', s):
            hit = True
            if not cmp_ok(float(m.group(1)), m.group(2), float(m.group(3))): bad(f'false comparison {m.group(0)}')
        # percentages of HP and chances
        for m in re.finditer(rf'{NUM}\s*(?:%|percent)?\s*(?:-|to|and)\s*{NUM}\s*%', s):
            hit = True
            exp = (100 * lo / hp, 100 * hi / hp)
            if abs(float(m.group(1)) - exp[0]) > 0.15 or abs(float(m.group(2)) - exp[1]) > 0.15: bad(f'HP percent {m.group(1)}-{m.group(2)} vs {exp[0]:.1f}-{exp[1]:.1f}')
        for m in re.finditer(rf'{NUM}\s*%\s*chance(?!\s*to\s*\d*hko)(?:\s*to\s*ohko)?', low):
            hit = True
            if abs(float(m.group(1)) - 100 * k / 16) > 3.125: bad(f'chance {m.group(1)}% vs {100*k/16}')
        for m in re.finditer(rf'{NUM}\s*%\s*(?:of the\s*)?(?:damage\s*)?rolls', low):
            hit = True
            if abs(float(m.group(1)) - 100 * k / 16) > 3.125: bad(f'roll share {m.group(1)}% vs {100*k/16}')
        # HP remaining
        for m in re.finditer(rf'(\d+)\s*HP\s*(?:remaining|left)', s):
            hit = True
            if int(m.group(1)) not in (hp - lo, hp - hi): bad(f'HP remaining {m.group(1)} vs hp-min {hp-lo} / hp-max {hp-hi}')
        # stated defender HP (a bare "has 32 HP" is the SP value mistaken for HP)
        for m in re.finditer(r'(?:has|have|had|of|HP \(|full HP \()\s*(\d+)\s*(?:HP|\))', s):
            n = int(m.group(1))
            if n >= 100 or re.search(r'(?:has|have|had)\s*' + m.group(1) + r'\s*HP\b', s):
                hit = True
                if n != hp: bad(f'defender HP {n} vs {hp}')
        # SP ceilings
        for m in re.finditer(rf'(\d+)\s*SP\s*(?:out of|of)\s*(\d+)', s):
            hit = True
            if int(m.group(2)) != 32: bad(f'SP "of {m.group(2)}" (SP cap is 32)')
        # stated damage range
        for m in re.finditer(r'(\d+)\s*(?:-|to)\s*(\d+)\s*damage|damage range (?:is|of)?\s*(\d+)\s*(?:-|to)\s*(\d+)', low):
            g = [x for x in m.groups() if x]; hit = True
            if [int(g[0]), int(g[1])] != [lo, hi]: bad(f'damage range {g[0]}-{g[1]} vs {lo}-{hi}')
        # max/min roll described as a KO, and KO / non-KO ranges against HP
        for m in re.finditer(r'(?:maximum|max|highest)[^.\d]{0,30}?(\d+)[^.\d]{0,25}?would\s*(?:knock out|KO)', low, re.I):
            hit = True
            if int(m.group(1)) < hp: bad(f'max roll {m.group(1)} < hp {hp} described as a KO')
        for m in re.finditer(r'dealing\s*(\d+)\s*(?:-|to)\s*(\d+)\s*damage\)?\s*would\s*(?:knock out|KO)', low, re.I):
            hit = True
            if int(m.group(1)) < hp: bad(f'KO range starts at {m.group(1)} < hp {hp}')
        for m in re.finditer(r'\(?(\d+)\s*(?:-|to)\s*(\d+)\)?\s*would\s*not\s*(?:be sufficient|be enough|KO|knock)', low, re.I):
            hit = True
            if int(m.group(2)) >= hp: bad(f'non-KO range {m.group(1)}-{m.group(2)} reaches hp {hp}')
        # the roll list quoted
        m = re.search(r'\[(\d+(?:,\s*\d+){3,})\]', s)
        if m:
            hit = True
            if rolls is None: bad('quotes a roll list the result did not contain')
            elif [int(x) for x in m.group(1).split(',')] != rolls: bad('quoted roll list differs from damage_rolls')
        if not hit and re.search(r'\d', s) and not re.search(r'level 50|HKO', s): unchecked.append((iid, s[:170]))
    return out, unchecked


def check_usage(iid, r):
    out = []
    t = r['final_text']
    for c in r['tool_calls']:
        for row in (c['result'].get('rows') or c['result'].get('items') or []):
            pct = row.get('conditional_pct', row.get('pct'))
            if pct is None: continue
            for m in re.finditer(re.escape(row['name']) + r'(?![\w-])\**\s*(?:-\s*|[(:]\s*)+(\d+(?:\.\d+)?)\s*%', t):
                d = len(m.group(1).split('.')[1]) if '.' in m.group(1) else 0
                if abs(float(m.group(1)) - pct) > 0.5 * 10 ** -d + 1e-9: out.append((iid, f'{row["name"]} stated {m.group(1)} vs tool {pct}', ''))
    return out


def audit(run):
    """-> (mismatches, unchecked) for a run directory with answers.jsonl."""
    A = {r['id']: r for r in map(json.loads, open(Path(run) / 'answers.jsonl'))}
    mism, unch = [], []
    for iid, r in A.items():
        ty = K[iid]['claim_type']
        if ty == 'damage':
            ok = [c for c in r['tool_calls'] if c['name'] == 'calc_damage' and c['ok']]
            if not ok: unch.append((iid, 'no successful calc call')); continue
            res = ok[-1]['result']
            if 'rolls_that_ko' not in res:  # dev1 results predate the derived field
                res = dict(res, rolls_that_ko=sum(x >= res['defender_hp'] for x in res['damage_rolls']))
            a, b = check_damage(iid, r, res); mism += a; unch += b
        elif ty in ('usage', 'usage_showdown'):
            mism += check_usage(iid, r)
    return mism, unch


if __name__ == '__main__':
    RUN = Path(sys.argv[1])
    mism, unch = audit(RUN)
    print(f'{RUN}: MISMATCHES {len(mism)}')
    for m in mism: print('  ', m)
    print(f'UNCHECKED sentences with numbers: {len(unch)}')
    for u in unch: print('  ', u)
